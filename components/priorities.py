"""Today's Priorities — actionable list on the Overview tab.

Built from the currently filtered flights. RED first, then ORANGE, YELLOW,
and underperforming-versus-last-year, stopping at seven items.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

import pandas as pd
import streamlit as st

import risk_scoring
import utils
from components.overview_table import (
    DRILLDOWN_DATE_KEY,
    DRILLDOWN_FLIGHT_KEY,
    FOCUS_KEY,
    FOCUS_PAGED_KEY,
)

MAX_ITEMS: Final[int] = 7
EMPTY_MESSAGE: Final[str] = (
    "✓ All flights operating within expected parameters. "
    "No urgent action required."
)


@dataclass(frozen=True)
class PriorityItem:
    """One line in Today's Priorities."""

    icon: str
    flight_no: str
    dep_date: pd.Timestamp
    rest: str


def _overbooked_seats(row: pd.Series) -> int:
    """Positive seats over capacity, else zero."""
    pax = row.get("Pax at Risk")
    if pax is not None and pd.notna(pax):
        return max(0, int(pax))
    return max(0, int(row["Total Bkg"]) - int(row["Total Cap"]))


def _leg_key(row: pd.Series) -> tuple[str, pd.Timestamp]:
    """Identity used to avoid listing the same flight twice."""
    return str(row["Flight No"]), pd.Timestamp(row["Dep Date"])


def _collect(current: pd.DataFrame) -> list[PriorityItem]:
    """Build up to seven items in the specified priority order."""
    items: list[PriorityItem] = []
    seen: set[tuple[str, pd.Timestamp]] = set()

    def add(row: pd.Series, icon: str, rest: str) -> bool:
        key = _leg_key(row)
        if key in seen:
            return len(items) >= MAX_ITEMS
        seen.add(key)
        items.append(
            PriorityItem(
                icon=icon,
                flight_no=str(row["Flight No"]),
                dep_date=pd.Timestamp(row["Dep Date"]),
                rest=rest,
            )
        )
        return len(items) >= MAX_ITEMS

    dtd = risk_scoring.DTD_COLUMN
    red = current[current["Risk Category"] == risk_scoring.RED].sort_values(
        dtd, ascending=True
    )
    for _, row in red.iterrows():
        extra = _overbooked_seats(row)
        if add(
            row,
            "🔴",
            f"{row['Dep Date']:%Y-%m-%d} — overbooked +{extra}, "
            "consider reducing Y OB parameter",
        ):
            return items

    orange = current[current["Risk Category"] == risk_scoring.ORANGE].sort_values(
        dtd, ascending=True
    )
    for _, row in orange.iterrows():
        if add(
            row,
            "🟠",
            f"{row['Dep Date']:%Y-%m-%d} — Y at "
            f"{utils.format_pct(row['Y BSF'])} with F/J still building",
        ):
            return items

    yellow = current[current["Risk Category"] == risk_scoring.YELLOW].sort_values(
        "Fcst Total BSF", ascending=False
    )
    for _, row in yellow.iterrows():
        if add(
            row,
            "🟡",
            f"{row['Dep Date']:%Y-%m-%d} — projected Total BSF "
            f"{utils.format_pct(row['Fcst Total BSF'])} at departure",
        ):
            return items

    if "Underperforming vs LY" in current.columns:
        weak = current[current["Underperforming vs LY"].fillna(False).astype(bool)]
        weak = weak.sort_values("BSF vLY", ascending=True)
        for _, row in weak.iterrows():
            if pd.isna(row.get("BSF vLY")):
                continue
            points = abs(float(row["BSF vLY"]) * 100)
            if add(
                row,
                "⚫",
                f"{row['Dep Date']:%Y-%m-%d} — {points:.1f}% below last year",
            ):
                return items

    return items


def _open_flight(flight_no: str, dep_date: pd.Timestamp) -> None:
    """Hand the flight to the Overview table detail panel."""
    st.session_state[FOCUS_KEY] = (flight_no, pd.Timestamp(dep_date))
    st.session_state[FOCUS_PAGED_KEY] = False
    st.session_state[DRILLDOWN_FLIGHT_KEY] = flight_no
    st.session_state[DRILLDOWN_DATE_KEY] = pd.Timestamp(dep_date).date()
    st.rerun()


def render(current: pd.DataFrame) -> None:
    """Draw Today's Priorities between the KPI cards and the table.

    Args:
        current: Filtered, scored open flights in the current view.
    """
    st.markdown(
        "<div class='ek-priorities'>"
        "<div class='ek-priorities-title'>📋 Today's Priorities</div>"
        "</div>",
        unsafe_allow_html=True,
    )

    if current.empty:
        st.caption("No flights in the current view.")
        return

    items = _collect(current)
    if not items:
        st.markdown(
            f"<div class='ek-priorities-empty'>{EMPTY_MESSAGE}</div>",
            unsafe_allow_html=True,
        )
        return

    for index, item in enumerate(items):
        icon, link, text = st.columns([0.06, 0.16, 0.78], vertical_alignment="center")
        icon.markdown(item.icon)
        verb = (
            "Review"
            if item.icon == "🔴"
            else "Monitor"
            if item.icon == "🟠"
            else "Watch"
            if item.icon == "🟡"
            else "Investigate"
        )
        if link.button(
            item.flight_no,
            key=f"priority_flight_{index}",
            type="secondary",
        ):
            _open_flight(item.flight_no, item.dep_date)
        text.markdown(f"{verb} {item.rest}")
