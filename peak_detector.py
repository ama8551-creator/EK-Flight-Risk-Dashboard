"""Detect recurring peak-demand windows from flown (FLN) history.

The algorithm is deliberately simple and inspectable:

1. Restrict to flown legs matching the analyst's filters.
2. Split by direction (the Route column).
3. Aggregate each ISO week-direction and cluster with K-Means (Peak /
   Shoulder / Off-Peak). Weeks in the Peak cluster are candidates.
4. Classify the day-of-week pattern inside each flagged week.
5. Merge adjacent flagged weeks into continuous ranges.
6. Name each range from the majority Period label, or a week-number fallback.

A single year of confirmation is enough; there is no multi-year requirement.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import asdict, dataclass
from datetime import date
from typing import Any, Final

import pandas as pd

import ml_pipeline
from data_loader import DOW_NAMES, infer_hub, outstation

PEAK_BSF_THRESHOLD: Final[float] = 0.85
FULL_WEEK_MIN_DAYS: Final[int] = 5


@dataclass
class DetectedPeak:
    """One recommended peak window for the analyst to review."""

    id: str
    name: str
    route: str
    direction: str
    start: date
    end: date
    avg_bsf: float
    dow_pattern: str
    confidence: str
    flight_count: int

    def as_dict(self) -> dict[str, Any]:
        """JSON-friendly copy (dates as ISO strings)."""
        payload = asdict(self)
        payload["start"] = self.start.isoformat()
        payload["end"] = self.end.isoformat()
        return payload

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> DetectedPeak:
        """Rebuild from :meth:`as_dict` output."""
        return cls(
            id=str(payload["id"]),
            name=str(payload["name"]),
            route=str(payload["route"]),
            direction=str(payload["direction"]),
            start=date.fromisoformat(str(payload["start"])),
            end=date.fromisoformat(str(payload["end"])),
            avg_bsf=float(payload["avg_bsf"]),
            dow_pattern=str(payload["dow_pattern"]),
            confidence=str(payload["confidence"]),
            flight_count=int(payload["flight_count"]),
        )


def _strip_parenthetical(label: str) -> str:
    """Drop city-specific suffixes such as ``(XYZ)`` from a Period name."""
    return re.sub(r"\s*\([^)]*\)", "", str(label)).strip()


def _is_consecutive(days: list[int]) -> bool:
    """Whether ISO weekdays form a contiguous block (no week wrap)."""
    if len(days) <= 1:
        return True
    ordered = sorted(days)
    return ordered[-1] - ordered[0] + 1 == len(ordered)


def _dow_pattern(rows: pd.DataFrame) -> str:
    """Classify whether demand is a full week or concentrated on some days."""
    if rows.empty:
        return "Full Week"
    by_dow = rows.groupby("DOW")["Total BSF"].mean()
    high = [
        int(day)
        for day in range(1, 8)
        if day in by_dow.index and float(by_dow.loc[day]) >= PEAK_BSF_THRESHOLD
    ]
    if len(high) >= 6 or (
        len(high) >= FULL_WEEK_MIN_DAYS and len(high) == len(by_dow)
    ):
        return "Full Week"
    if not high:
        take = min(3, len(by_dow))
        high = [int(day) for day in by_dow.nlargest(take).index]
    high = sorted(set(high))
    names = [DOW_NAMES[day] for day in high]
    if _is_consecutive(high) and len(names) > 1:
        return f"{names[0]}–{names[-1]}"
    return ", ".join(names)


def _confidence(avg_bsf: float) -> str:
    """Label how far the window sits above the 85% threshold."""
    if avg_bsf >= 0.95:
        return "High"
    if avg_bsf >= 0.90:
        return "Medium"
    return "Low"


def _peak_name(rows: pd.DataFrame, direction: str, hub: str) -> str:
    """Prefer the majority Period label; otherwise ``Peak Week N (sense)``."""
    inbound = str(direction).endswith(f"-{hub}")
    sense = "Return" if inbound else "Outbound"
    periods = rows["Period"].dropna()
    skip = {"Off-Peak", "Corporate Weekday", "Weekend Lull"}
    if not periods.empty:
        mode = _strip_parenthetical(str(periods.mode().iloc[0]))
        if mode and mode not in skip:
            return mode
    week = int(rows["Dep Date"].dt.isocalendar().week.mode().iloc[0])
    return f"Peak Week {week} ({sense})"


def _adjacent(left: tuple[int, int], right: tuple[int, int]) -> bool:
    """Whether ``right`` is the ISO week immediately after ``left``."""
    left_year, left_week = left
    right_year, right_week = right
    if left_year == right_year and right_week == left_week + 1:
        return True
    if right_year == left_year + 1 and right_week == 1 and left_week >= 52:
        return True
    return False


def _weeks_for_direction(part: pd.DataFrame) -> list[dict[str, Any]]:
    """Average Total BSF per ISO week, before clustering assigns Peak flags."""
    if part.empty:
        return []
    iso = part["Dep Date"].dt.isocalendar()
    tagged = part.assign(
        iso_year=iso.year.astype(int),
        iso_week=iso.week.astype(int),
    )
    weeks: list[dict[str, Any]] = []
    for (year, week), rows in tagged.groupby(["iso_year", "iso_week"], sort=True):
        avg = float(rows["Total BSF"].mean())
        weeks.append(
            {
                "key": (int(year), int(week)),
                "iso_year": int(year),
                "iso_week": int(week),
                "avg": avg,
                "flagged": False,
                "rows": rows,
            }
        )
    return weeks


def _apply_cluster_flags(
    weeks: list[dict[str, Any]], cluster: ml_pipeline.ClusterBundle, direction: str
) -> list[dict[str, Any]]:
    """Mark weeks that landed in the K-Means Peak cluster."""
    labels = cluster.labels
    if labels.empty or "cluster" not in labels.columns:
        return weeks
    peak_keys = set(
        zip(
            labels.loc[labels["cluster"] == "Peak", "iso_year"],
            labels.loc[labels["cluster"] == "Peak", "iso_week"],
            labels.loc[labels["cluster"] == "Peak", "direction"],
        )
    )
    for week in weeks:
        week["flagged"] = (
            week["iso_year"],
            week["iso_week"],
            direction,
        ) in peak_keys
    return weeks


def _merge_flagged(weeks: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    """Collapse runs of adjacent flagged ISO weeks."""
    runs: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    for week in weeks:
        if not week["flagged"]:
            if current:
                runs.append(current)
                current = []
            continue
        if current and _adjacent(current[-1]["key"], week["key"]):
            current.append(week)
        else:
            if current:
                runs.append(current)
            current = [week]
    if current:
        runs.append(current)
    return runs


def detect_peaks(
    fln: pd.DataFrame, hub: str | None = None
) -> tuple[list[DetectedPeak], ml_pipeline.ClusterBundle]:
    """Return peak recommendations for every direction in ``fln``.

    Args:
        fln: Flown snapshots already reduced by the Peak Detection filters.
        hub: Hub airport. Inferred from ``fln`` when omitted.

    Returns:
        Peaks sorted by average Total BSF, highest first, and the K-Means
        clustering used to flag Peak weeks.
    """
    cluster = ml_pipeline.cluster_week_directions(fln)
    if fln.empty:
        return [], cluster
    resolved_hub = hub or infer_hub(fln["Route"].dropna().unique())
    detected: list[DetectedPeak] = []
    for direction, part in fln.groupby("Route", sort=True):
        weeks = _apply_cluster_flags(
            _weeks_for_direction(part), cluster, str(direction)
        )
        runs = _merge_flagged(weeks)
        for run in runs:
            rows = pd.concat([item["rows"] for item in run], ignore_index=True)
            avg = float(rows["Total BSF"].mean())
            start = pd.Timestamp(rows["Dep Date"].min()).date()
            end = pd.Timestamp(rows["Dep Date"].max()).date()
            detected.append(
                DetectedPeak(
                    id=str(uuid.uuid4()),
                    name=_peak_name(rows, str(direction), resolved_hub),
                    route=outstation(str(direction), resolved_hub),
                    direction=str(direction),
                    start=start,
                    end=end,
                    avg_bsf=avg,
                    dow_pattern=_dow_pattern(rows),
                    confidence=_confidence(avg),
                    flight_count=int(len(rows)),
                )
            )
    detected.sort(key=lambda peak: peak.avg_bsf, reverse=True)
    return detected, cluster
