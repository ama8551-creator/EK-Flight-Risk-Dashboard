"""The Flight No + Dep Date selector shared by the Flight Analysis sub-tabs.

Booking Curve, versus Last Year and per-flight Point of Sale all inspect one
leg at a time, and all need the same two-step choice: pick a flight number,
then pick one of *that flight's* departure dates.

Two deliberate decisions:

* **The dropdowns draw from the whole dataset, not the sidebar filters.** The
  sidebar is tuned for the forward-looking work queue — its date range starts
  today and its days-to-departure slider starts at 0 — so applying it here
  would make every flown flight unreachable. Booking curves and prior-year
  comparisons are exactly the places where flown history is the point.
* **The selection seeds from a handed-over flight, then from the caller's
  suggestion.** The caller passes the top-ranked flight, so the tab opens on
  the flight that most needs attention rather than on whatever sorts first.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

import pandas as pd
import streamlit as st

import approved_peaks
from components.overview_table import DRILLDOWN_DATE_KEY, DRILLDOWN_FLIGHT_KEY
from data_loader import FLIGHT_KEY, STATUS_FLOWN


@dataclass(frozen=True)
class Selection:
    """One chosen flight leg.

    Attributes:
        flight_no: The chosen flight number.
        dep_date: The chosen departure date.
        rows: Every snapshot of that leg, oldest observation first.
    """

    flight_no: str
    dep_date: pd.Timestamp
    rows: pd.DataFrame

    @property
    def latest(self) -> pd.Series:
        """The leg's most recent observation, i.e. its current state."""
        return self.rows.iloc[-1]

    @property
    def is_flown(self) -> bool:
        """Whether the leg has already operated."""
        return bool(self.latest["Status"] == STATUS_FLOWN)


def _legs(flights: pd.DataFrame) -> pd.DataFrame:
    """One row per distinct flight leg, newest departure first.

    Args:
        flights: Preprocessed frame from ``data_loader.load_flights``.

    Returns:
        Unique ``Flight No``/``Dep Date`` pairs with the leg's status.
    """
    return (
        flights[FLIGHT_KEY + ["Status"]]
        .drop_duplicates(subset=FLIGHT_KEY)
        .sort_values("Dep Date", ascending=False)
    )


def _default_index(options: list, wanted: object) -> int:
    """Index of ``wanted`` in ``options``, or 0 when it is absent.

    Args:
        options: The dropdown's options.
        wanted: The value to pre-select.

    Returns:
        A valid index into ``options``.
    """
    try:
        return options.index(wanted)
    except ValueError:
        return 0


def render(
    flights: pd.DataFrame,
    key_prefix: str,
    suggested: tuple[str, object] | None = None,
) -> Selection | None:
    """Draw the two dropdowns and return the chosen leg.

    Args:
        flights: Preprocessed frame from ``data_loader.load_flights``.
        key_prefix: Namespace for the widget keys, so two tabs can each hold
            an independent selection.
        suggested: Optional ``(flight number, departure date)`` to pre-select
            when the analyst has not handed a flight over from the Overview
            tab. Usually the highest-risk flight.

    Returns:
        The selected leg, or ``None`` when the dataset has no flights.
    """
    legs = _legs(flights)
    if legs.empty:
        return None

    fallback_no, fallback_date = suggested or (None, None)
    flight_numbers = sorted(legs["Flight No"].unique().tolist())
    wanted_no = st.session_state.get(DRILLDOWN_FLIGHT_KEY) or fallback_no

    columns = st.columns(2)
    columns[0].markdown("**Flight No**")
    flight_no = columns[0].selectbox(
        "Flight No",
        options=flight_numbers,
        index=_default_index(flight_numbers, wanted_no),
        key=f"{key_prefix}_flight_no",
        label_visibility="collapsed",
    )

    # Only the dates this flight number actually operates.
    dates = (
        legs[legs["Flight No"] == flight_no]["Dep Date"]
        .dt.date.unique()
        .tolist()
    )
    wanted_date = st.session_state.get(DRILLDOWN_DATE_KEY) or fallback_date

    columns[1].markdown("**Dep Date**")
    dep_date = columns[1].selectbox(
        "Dep Date",
        options=dates,
        index=_default_index(dates, wanted_date),
        format_func=lambda d: f"{d:%Y-%m-%d} ({d:%a})",
        key=f"{key_prefix}_dep_date",
        label_visibility="collapsed",
    )

    rows = flights[
        (flights["Flight No"] == flight_no)
        & (flights["Dep Date"] == pd.Timestamp(dep_date))
    ].sort_values("Days to Departure", ascending=False)

    return Selection(
        flight_no=flight_no, dep_date=pd.Timestamp(dep_date), rows=rows
    )


#: Columns describing a leg's identity, shown above the per-flight charts.
IDENTITY_FIELDS: Final[tuple[str, ...]] = (
    "Route",
    "Dep Time",
    "DOW Label",
    "Aircraft",
    "Period",
)


def render_identity(selection: Selection) -> None:
    """Draw a one-line identity card for the selected leg.

    Args:
        selection: The chosen leg.
    """
    row = selection.latest
    status = "Flown" if selection.is_flown else "Open"
    parts = [
        f"**{selection.flight_no}**",
        f"{row['Route']}",
        f"{selection.dep_date:%a %d %b %Y}",
        f"dep {row['Dep Time']}",
        f"DOW {row['DOW Label']}",
        f"{row['Aircraft']}",
        status,
    ]
    st.caption(" · ".join(str(p) for p in parts))
    st.caption(f"Period: {approved_peaks.display_period(row)}")
