"""Flight Analysis tab — Booking Curve and Point of Sale.

Selectors sit above both sub-tabs. Flight No defaults to All Flights; a date
range replaces the old single departure-date picker. The tab-level Route
filter intersects with the sidebar Route filter. Grouping appears only in
aggregate mode when a route or direction is selected.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Final

import pandas as pd
import streamlit as st

import utils
from components import booking_curve, flight_picker, pos
from components.filters import FilterState
from components.overview_table import DRILLDOWN_DATE_KEY, DRILLDOWN_FLIGHT_KEY
from data_loader import FLIGHT_KEY, infer_hub, outstation

ALL_FLIGHTS: Final[str] = "All Flights"

#: Default window requested for the restructured tab (October 2026).
DEFAULT_FROM: Final[date] = date(2026, 10, 1)
DEFAULT_TO: Final[date] = date(2026, 10, 31)


def _consume_drilldown() -> tuple[str | None, date | None]:
    """Read a flight handed over from Overview, then clear the session keys."""
    flight_no = st.session_state.pop(DRILLDOWN_FLIGHT_KEY, None)
    raw_date = st.session_state.pop(DRILLDOWN_DATE_KEY, None)
    dep_date = pd.Timestamp(raw_date).date() if raw_date is not None else None
    return flight_no, dep_date


def _filter_snaps(
    flights: pd.DataFrame,
    *,
    flight_no: str | None,
    date_from: date,
    date_to: date,
    directions: list[str],
    cities: list[str] | None = None,
    hub: str | None = None,
) -> pd.DataFrame:
    """Snapshots matching the optional Flight Analysis selectors."""
    start, end = sorted((pd.Timestamp(date_from), pd.Timestamp(date_to)))
    mask = (flights["Dep Date"] >= start) & (flights["Dep Date"] <= end)
    if flight_no:
        mask &= flights["Flight No"] == flight_no
    if cities and hub:
        mask &= flights["Route"].map(lambda route: outstation(route, hub)).isin(
            cities
        )
    if directions:
        mask &= flights["Route"].isin(directions)
    return flights.loc[mask].copy()


def _prior_year_snaps(
    flights: pd.DataFrame,
    *,
    flight_no: str | None,
    date_from: date,
    date_to: date,
    directions: list[str],
    cities: list[str] | None = None,
    hub: str | None = None,
) -> pd.DataFrame:
    """Same selector window shifted back by the weekday-aligned year offset."""
    offset = timedelta(days=utils.YOY_OFFSET_DAYS)
    return _filter_snaps(
        flights,
        flight_no=flight_no,
        date_from=date_from - offset,
        date_to=date_to - offset,
        directions=directions,
        cities=cities,
        hub=hub,
    )


def _pick_leg(
    snaps: pd.DataFrame, preferred_date: date | None
) -> flight_picker.Selection | None:
    """Choose one departure in the range — preferred date, else soonest."""
    if snaps.empty:
        return None
    dates = sorted(pd.Timestamp(d).date() for d in snaps["Dep Date"].unique())
    chosen = preferred_date if preferred_date in dates else dates[0]
    rows = snaps[snaps["Dep Date"] == pd.Timestamp(chosen)].sort_values(
        "Days to Departure", ascending=False
    )
    if rows.empty:
        return None
    return flight_picker.Selection(
        flight_no=str(rows.iloc[0]["Flight No"]),
        dep_date=pd.Timestamp(chosen),
        rows=rows,
    )


def _apply_sidebar_routes(
    snaps: pd.DataFrame, state: FilterState | None, hub: str
) -> pd.DataFrame:
    """Keep snapshots whose route/direction match the sidebar selection."""
    if snaps.empty or state is None:
        return snaps
    mask = pd.Series(True, index=snaps.index)
    if state.cities:
        mask &= snaps["Route"].map(lambda route: outstation(route, hub)).isin(
            state.cities
        )
    if state.directions:
        mask &= snaps["Route"].isin(state.directions)
    return snaps.loc[mask].copy()


def render(
    flights: pd.DataFrame,
    suggested: tuple[str, object] | None = None,
    state: FilterState | None = None,
) -> None:
    """Draw the Flight Analysis tab.

    Args:
        flights: Preprocessed frame from ``data_loader.load_flights``.
        suggested: Unused; kept so the app call site stays unchanged.
        state: Sidebar filters. Route and Direction intersect with the
            tab-level selectors on the aggregate curve.
    """
    del suggested
    st.markdown(
        "Inspect booking build-up and point of sale for one flight or for "
        "every flight in a date range. Last year is overlaid as dashed lines."
    )
    st.caption(
        "Date range and Flight No cover the whole dataset, including flown "
        "flights. The tab-level Route filter intersects with the sidebar "
        "Route filter. Direction filters combine the same way."
    )

    handed_no, handed_date = _consume_drilldown()
    hub = infer_hub(flights["Route"].dropna().unique())
    flight_numbers = [ALL_FLIGHTS] + sorted(flights["Flight No"].unique().tolist())
    route_cities = sorted(
        {outstation(route, hub) for route in flights["Route"].dropna().unique()}
    )
    directions = sorted(flights["Route"].dropna().unique().tolist())
    min_date = pd.Timestamp(flights["Dep Date"].min()).date()
    max_date = pd.Timestamp(flights["Dep Date"].max()).date()
    default_from = min(max(DEFAULT_FROM, min_date), max_date)
    default_to = min(max(DEFAULT_TO, min_date), max_date)

    if handed_no and handed_no in flight_numbers:
        st.session_state["analysis_flight_no"] = handed_no
    if handed_date is not None:
        st.session_state["analysis_date_from"] = handed_date
        st.session_state["analysis_date_to"] = handed_date

    selectors = st.columns([1.2, 1.2, 1.0, 1.0, 1.4])
    selectors[0].markdown("**Flight No**")
    flight_choice = selectors[0].selectbox(
        "Flight No",
        options=flight_numbers,
        index=0,
        key="analysis_flight_no",
        label_visibility="collapsed",
    )
    selectors[1].markdown("**Route**")
    selected_cities = selectors[1].multiselect(
        "Route",
        options=route_cities,
        default=[],
        key="analysis_route_cities",
        label_visibility="collapsed",
        placeholder="All routes",
    )
    selectors[2].markdown("**Date from**")
    date_from = selectors[2].date_input(
        "Date from",
        value=default_from,
        min_value=min_date,
        max_value=max_date,
        key="analysis_date_from",
        label_visibility="collapsed",
    )
    selectors[3].markdown("**Date to**")
    date_to = selectors[3].date_input(
        "Date to",
        value=default_to,
        min_value=min_date,
        max_value=max_date,
        key="analysis_date_to",
        label_visibility="collapsed",
    )
    selectors[4].markdown("**Direction**")
    selected_directions = selectors[4].multiselect(
        "Direction",
        options=directions,
        default=[],
        key="analysis_directions",
        label_visibility="collapsed",
        placeholder="All directions",
    )

    grouping = booking_curve.GROUP_DIRECTION
    specific = flight_choice != ALL_FLIGHTS
    sidebar_cities = list(state.cities) if state else []
    sidebar_narrowed = bool(state and (state.cities or state.directions))
    tab_narrowed = bool(selected_cities or selected_directions)
    route_narrowed = tab_narrowed or sidebar_narrowed
    if not specific and route_narrowed:
        grouping = st.selectbox(
            "Grouping",
            options=list(booking_curve.GROUPING_OPTIONS),
            index=0,
            key="analysis_grouping",
        )

    if selected_cities and sidebar_cities:
        if not set(selected_cities) & set(sidebar_cities):
            st.warning(
                "No flights match the combined filters. The tab-level Route "
                "filter and sidebar Route filter must have at least one city "
                "in common."
            )

    this_year = _apply_sidebar_routes(
        _filter_snaps(
            flights,
            flight_no=flight_choice if specific else None,
            date_from=date_from,
            date_to=date_to,
            directions=selected_directions,
            cities=selected_cities,
            hub=hub,
        ),
        state,
        hub,
    )
    last_year = _apply_sidebar_routes(
        _prior_year_snaps(
            flights,
            flight_no=flight_choice if specific else None,
            date_from=date_from,
            date_to=date_to,
            directions=selected_directions,
            cities=selected_cities,
            hub=hub,
        ),
        state,
        hub,
    )

    selection = _pick_leg(this_year, handed_date) if specific else None
    if specific and selection is not None:
        flight_picker.render_identity(selection)

    curve_tab, pos_tab = st.tabs(["Booking Curve", "Point of Sale"])
    with curve_tab:
        if specific:
            prior_leg = None
            if selection is not None:
                matches = utils.find_prior_year_flight(
                    flights, selection.flight_no, selection.dep_date
                )
                if not matches.empty:
                    prior_date = matches.iloc[0]["Dep Date"]
                    prior_leg = matches[matches["Dep Date"] == prior_date].sort_values(
                        "Days to Departure", ascending=False
                    )
            booking_curve.render_flight(
                selection.rows if selection else this_year,
                prior_leg,
                flight_no=flight_choice,
                dep_date=selection.dep_date if selection else pd.Timestamp(date_from),
                flights=flights,
            )
        else:
            booking_curve.render_aggregate(
                this_year,
                last_year,
                grouping,
                flights,
                collapsed=not route_narrowed,
            )

    with pos_tab:
        if specific:
            if selection is None:
                st.markdown(
                    utils.empty_state("No flight in the selected range."),
                    unsafe_allow_html=True,
                )
            else:
                pos.render_flight(selection.latest)
        else:
            latest = this_year
            if not latest.empty:
                keep = latest.groupby(FLIGHT_KEY, sort=False)["Days to Departure"].idxmin()
                latest = latest.loc[keep]
            pos.render_aggregate(latest)
