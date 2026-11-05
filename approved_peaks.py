"""Approved peak calendar, stored as JSON in the data folder.

Until the analyst accepts peaks on the Peak Detection tab, the file is missing
or empty and every flight's displayed Period is a dash. The workbook's own
Period column is unchanged and still drives the sidebar filter.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from data_loader import HUB, infer_hub, outstation, resolve_data_path

APPROVED_FILENAME = "approved_peaks.json"
EMPTY_PERIOD = "—"


def approved_peaks_path() -> Path:
    """Return the path of ``approved_peaks.json`` next to the workbook."""
    return resolve_data_path().parent / APPROVED_FILENAME


def load_approved_peaks() -> list[dict[str, Any]]:
    """Read accepted peaks, or an empty list when the file is absent.

    Returns:
        Peak records as dictionaries.
    """
    path = approved_peaks_path()
    if not path.is_file():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(payload, list):
        return []
    return [item for item in payload if isinstance(item, dict)]


def save_approved_peaks(peaks: list[dict[str, Any]]) -> None:
    """Write the accepted-peak list to ``approved_peaks.json``."""
    path = approved_peaks_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(
        json.dumps(peaks, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    tmp.replace(path)


def upsert_approved_peak(record: dict[str, Any]) -> None:
    """Insert or replace one accepted peak by ``id``."""
    peaks = load_approved_peaks()
    peak_id = str(record.get("id", ""))
    updated = [peak for peak in peaks if str(peak.get("id", "")) != peak_id]
    updated.append(record)
    save_approved_peaks(updated)


def delete_approved_peak(peak_id: str) -> None:
    """Remove one accepted peak by ``id``."""
    peaks = [
        peak
        for peak in load_approved_peaks()
        if str(peak.get("id", "")) != str(peak_id)
    ]
    save_approved_peaks(peaks)


def _month_day(value: object) -> str:
    """Format a departure date as ``MM-DD``."""
    return pd.Timestamp(value).strftime("%m-%d")


def _in_month_day_window(month_day: str, start: str, end: str) -> bool:
    """Whether ``month_day`` sits in ``start``–``end``, wrapping the year."""
    if not start or not end:
        return False
    if start <= end:
        return start <= month_day <= end
    return month_day >= start or month_day <= end


def matching_peak(row: pd.Series, peaks: list[dict[str, Any]] | None = None) -> dict[str, Any] | None:
    """Return the approved peak that covers this flight, if any.

    Args:
        row: A flight row with ``Route`` and ``Dep Date``.
        peaks: Pre-loaded peaks. Loaded from disk when omitted.

    Returns:
        The matching peak record, or ``None``.
    """
    records = peaks if peaks is not None else load_approved_peaks()
    if not records:
        return None
    hub = infer_hub([str(row.get("Route", "")), HUB])
    city = outstation(row.get("Route", ""), hub)
    direction = str(row.get("Route", ""))
    month_day = _month_day(row.get("Dep Date"))
    for peak in records:
        if str(peak.get("route", "")) != city:
            continue
        if str(peak.get("direction", "")) != direction:
            continue
        if _in_month_day_window(
            month_day,
            str(peak.get("start_month_day", "")),
            str(peak.get("end_month_day", "")),
        ):
            return peak
    return None


def display_period(row: pd.Series, peaks: list[dict[str, Any]] | None = None) -> str:
    """Period label for display: approved name, otherwise an em dash."""
    peak = matching_peak(row, peaks)
    if peak and peak.get("name"):
        return str(peak["name"])
    return EMPTY_PERIOD
