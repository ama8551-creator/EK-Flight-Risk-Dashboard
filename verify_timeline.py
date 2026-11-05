"""Verify the Alert Timeline projection, then report what it predicts.

Run after changing the projection or replacing the workbook:

    python -X utf8 verify_timeline.py

The tab's dates are modelled rather than observed, so they cannot be checked
against the dataset. What *can* be checked are the properties the model must
hold to be defensible: projections never point into the past, a flight never
escalates into a category it already occupies, the interpolation always moves
towards the forecast, and the bands covering each flight leave no gaps.
Development aid, not part of the dashboard.
"""

from __future__ import annotations

import sys

import pandas as pd

import risk_scoring as rs
from components.alert_timeline import (
    ELEVATED,
    HORIZONS,
    WORKLOAD_BUCKETS,
    _legs_in_window,
    category_bands,
    category_entries,
    project_timeline,
)
from data_loader import SNAPSHOT_DATE, latest_snapshots, load_flights

#: Flights hand-checked as already RED on the snapshot date. The workload
#: cards must count these as needing action this week even though they never
#: "enter" RED — the regression that band-based counting was built to fix.
EXPECTED_CRITICAL_THIS_WEEK = 3

PASS = "PASS"
FAIL = "FAIL"


def _line(status: str, message: str) -> None:
    """Print one check result."""
    print(f"  [{status}] {message}")


def _check_projection_horizon(projected: pd.DataFrame) -> bool:
    """No projected checkpoint may fall before the snapshot date."""
    before = int((projected["Projected Date"] < SNAPSHOT_DATE).sum())
    _line(
        PASS if before == 0 else FAIL,
        f"Projected dates span {projected['Projected Date'].min():%Y-%m-%d} to "
        f"{projected['Projected Date'].max():%Y-%m-%d} "
        f"({before} before {SNAPSHOT_DATE.date()})",
    )
    return before == 0


def _check_escalations_are_future(entries: pd.DataFrame) -> bool:
    """Every escalation must be strictly after today.

    An escalation dated today would mean the projection disagrees with the
    observed current state it was seeded from.
    """
    if entries.empty:
        _line(FAIL, "No escalations at all — the projection found nothing")
        return False

    past = int((entries["Projected Date"] <= SNAPSHOT_DATE).sum())
    _line(
        PASS if past == 0 else FAIL,
        f"{len(entries)} escalations across "
        f"{entries.groupby(['Flight No', 'Dep Date']).ngroups} legs, "
        f"{entries['Projected Date'].min():%Y-%m-%d} to "
        f"{entries['Projected Date'].max():%Y-%m-%d} ({past} not in the future)",
    )
    return past == 0


def _check_no_reentry(current: pd.DataFrame, entries: pd.DataFrame) -> bool:
    """A leg already RED today must not be reported as entering RED."""
    red_now = current[current["Risk Category"] == rs.RED][["Flight No", "Dep Date"]]
    overlap = entries.merge(red_now, on=["Flight No", "Dep Date"])
    _line(
        PASS if overlap.empty else FAIL,
        f"{len(red_now)} legs are already RED; they generate "
        f"{len(overlap)} escalation events (expected 0)",
    )
    return overlap.empty


def _check_monotonic(projected: pd.DataFrame) -> bool:
    """Interpolation must always move towards the forecast, never away."""
    leg = ["Flight No", "Dep Date"]
    ordered = projected.sort_values(leg + ["Checkpoint DTD"], ascending=[True, True, False])
    grouped = ordered.groupby(leg, sort=False)

    first = grouped[["Total BSF", "Fcst Total BSF"]].first()
    rising = first["Fcst Total BSF"] > first["Total BSF"]
    steps = grouped["Total BSF"].diff()

    falls = steps.lt(-1e-9).groupby([ordered["Flight No"], ordered["Dep Date"]]).any()
    climbs = steps.gt(1e-9).groupby([ordered["Flight No"], ordered["Dep Date"]]).any()
    wrong_way = int((rising & falls).sum() + (~rising & climbs).sum())

    _line(
        PASS if wrong_way == 0 else FAIL,
        f"{grouped.ngroups:,} legs projected; {wrong_way} move away from their "
        f"forecast",
    )
    return wrong_way == 0


def _check_bands_gapless(projected: pd.DataFrame, bands: pd.DataFrame) -> bool:
    """Bands must tile each leg's timeline with no gaps and no overlaps."""
    leg = ["Flight No", "Dep Date"]
    ordered = bands.sort_values(leg + ["Start"])
    next_start = ordered.groupby(leg, sort=False)["Start"].shift(-1)
    gaps = int((next_start.notna() & (ordered["Finish"] != next_start)).sum())

    # Every leg must appear, and its bands must end at departure.
    missing = projected.groupby(leg).ngroups - bands.groupby(leg).ngroups
    last_finish = ordered.groupby(leg, sort=False).last()
    short = int((last_finish["Finish"] != last_finish.index.get_level_values(
        "Dep Date"
    )).sum())

    ok = gaps == 0 and missing == 0 and short == 0
    _line(
        PASS if ok else FAIL,
        f"{len(bands):,} bands over {bands.groupby(leg).ngroups:,} legs: "
        f"{gaps} gaps, {missing} legs missing, {short} not ending at departure",
    )
    return ok


def _check_workload_cards(bands: pd.DataFrame) -> bool:
    """The "this week" card must count flights already RED, not just new ones."""
    label, start, end, categories, _, _, _ = WORKLOAD_BUCKETS[0]
    critical = _legs_in_window(bands, start, end, categories)
    ok = critical == EXPECTED_CRITICAL_THIS_WEEK
    _line(
        PASS if ok else FAIL,
        f'"{label}" reports {critical} critical flights '
        f"(expected {EXPECTED_CRITICAL_THIS_WEEK})",
    )
    return ok


def _report_timeline(
    projected: pd.DataFrame, entries: pd.DataFrame, bands: pd.DataFrame
) -> None:
    """Print what the projection predicts, for eyeballing against the tab."""
    print(f"\nProjected {len(projected):,} leg-checkpoints.")

    print("\nEscalation transitions:")
    for (source, target), count in (
        entries.groupby(["Previous Category", "Risk Category"]).size().items()
    ):
        print(f"  {source:<7} -> {target:<7} {count:>4,}")

    print("\nEscalations by horizon (cumulative):")
    for title, days in HORIZONS:
        window = entries[entries["Days From Now"].between(0, days)]
        counts = window["Risk Category"].value_counts()
        tally = ", ".join(f"{c} {int(counts.get(c, 0))}" for c in ELEVATED)
        print(f"  {title:<14} {tally}")
    beyond = entries[entries["Days From Now"] > HORIZONS[-1][1]]
    counts = beyond["Risk Category"].value_counts()
    tally = ", ".join(f"{c} {int(counts.get(c, 0))}" for c in ELEVATED)
    print(f"  {'Beyond ' + str(HORIZONS[-1][1]) + ' Days':<14} {tally}")

    print("\nWorkload cards (legs holding a category during the window):")
    for label, start, end, categories, _, _, _ in WORKLOAD_BUCKETS:
        count = _legs_in_window(bands, start, end, categories)
        print(f"  {label:<14} days {start:>2}-{end:<2} "
              f"{'/'.join(categories):<18} {count:>4,}")

    worst = (
        bands[bands["Category"].isin(ELEVATED)]
        .sort_values(["Severity", "Start"], ascending=[False, True])
        .drop_duplicates(subset=["Flight No", "Dep Date"])
    )
    print(f"\n{len(worst):,} legs reach an elevated category. "
          "Soonest and most severe:")
    for _, band in worst.head(5).iterrows():
        print(f"  {band['Flight No']} {band['Route']} dep "
              f"{band['Dep Date']:%Y-%m-%d}: {band['Category']} from "
              f"{band['Start']:%Y-%m-%d}")


def _walk_one_leg(projected: pd.DataFrame, entries: pd.DataFrame) -> None:
    """Trace a single escalating leg checkpoint by checkpoint."""
    escalating = entries[entries["Risk Category"] == rs.RED]
    if escalating.empty:
        return

    key = escalating.iloc[0]
    walk = projected[
        (projected["Flight No"] == key["Flight No"])
        & (projected["Dep Date"] == key["Dep Date"])
    ].sort_values("Checkpoint DTD", ascending=False)

    print(f"\nWalk-through: {key['Flight No']} {key['Route']} dep "
          f"{key['Dep Date']:%Y-%m-%d}")
    for _, row in walk.iterrows():
        print(f"  {row['Projected Date']:%Y-%m-%d}  "
              f"DTD {int(row['Checkpoint DTD']):>3}  "
              f"Y {row['Y BSF']:>7.2%}  total {row['Total BSF']:>7.2%}  "
              f"fcst {row['Fcst Total BSF']:>7.2%}  "
              f"{row['Risk Category']:<7} score {row['Risk Score']:.0f}")


def main() -> int:
    """Run every check and return a shell exit code."""
    current = rs.assign_risk(latest_snapshots(load_flights()))
    print(f"Scored {len(current):,} open legs as of {SNAPSHOT_DATE.date()}.\n")

    projected = project_timeline(current)
    entries = category_entries(projected)
    bands = category_bands(projected)

    print("Checks:")
    results = [
        _check_projection_horizon(projected),
        _check_escalations_are_future(entries),
        _check_no_reentry(current, entries),
        _check_monotonic(projected),
        _check_bands_gapless(projected, bands),
        _check_workload_cards(bands),
    ]

    _report_timeline(projected, entries, bands)
    _walk_one_leg(projected, entries)

    if all(results):
        print("\nAll checks passed.")
        return 0
    print("\nSome checks failed.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
