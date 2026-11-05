"""Sidebar filters (specification section 4) and the row filtering they drive.

Every filter is held in a :class:`FilterState` so all tabs apply the same
selection.

Two conventions worth knowing:

* **An empty multi-select means "show everything".** Leaving a filter untouched
  never hides flights, so the dashboard opens on the full population and the
  analyst narrows down from there.
* **Cabin class does not remove rows.** Per spec 4.4 its purpose is to focus
  the drill-down and BSF charts on a cabin, so it is carried as a display
  scope rather than a row predicate.

Route is filtered at two levels: *Route* selects an outstation city (both
directions of travel) and *Direction* selects a specific origin-destination
leg. Both lists are read from the loaded dataset. They combine, so picking a
city with one inbound direction shows only that inbound leg.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from typing import Final

import pandas as pd
import streamlit as st

import risk_scoring
from data_loader import (
    CABINS,
    DOW_NAMES,
    PERIOD_GROUPS,
    POS_NAMES,
    SNAPSHOT_DATE,
    dow_label,
    infer_hub,
    outstation,
)
from styling import theme

# --- Filter defaults (spec section 4) --------------------------------------
DEFAULT_DATE_HORIZON_DAYS: Final[int] = 90
DTD_SLIDER_MIN: Final[int] = 0
DTD_SLIDER_MAX: Final[int] = 120
DEFAULT_DTD_RANGE: Final[tuple[int, int]] = (DTD_SLIDER_MIN, DTD_SLIDER_MAX)

#: A selected POS country matches a flight when it contributes more than this
#: share of that flight's total bookings.
POS_MIN_SHARE: Final[float] = 0.05

CABIN_LABELS: Final[dict[str, str]] = {
    "F": "F (First)",
    "J": "J (Business)",
    "Y": "Y (Economy)",
}

#: Widget keys, so "Clear all" can reset them in one sweep.
_KEYS: Final[dict[str, str]] = {
    "cities": "flt_cities",
    "directions": "flt_directions",
    "date_from": "flt_date_from",
    "date_to": "flt_date_to",
    "categories": "flt_categories",
    "cabins": "flt_cabins",
    "dtd": "flt_dtd",
    "dow": "flt_dow",
    "periods": "flt_periods",
    "flight_numbers": "flt_flight_numbers",
    "underperforming": "flt_underperforming",
    "pos": "flt_pos",
}

_ALL_PLACEHOLDER: Final[str] = "All (no filter)"


@dataclass
class FilterState:
    """The analyst's current filter selection.

    Every list attribute follows the same rule: empty means "no filter", so
    all rows qualify.

    Attributes:
        cities: Outstation cities to include (both directions of each city).
        directions: Specific origin-destination legs to include.
        date_from: Earliest departure date to include.
        date_to: Latest departure date to include.
        categories: Risk categories to include.
        cabins: Cabins to focus charts on. Never filters rows.
        dtd_range: Inclusive days-to-departure bounds. Always applied.
        dow: ISO departure weekdays (1 = Monday) to include.
        period_groups: Consolidated commercial periods to include.
        flight_numbers: Flight numbers to include.
        underperforming: ``Yes`` / ``No`` for the BLACK vLY flag.
        pos_countries: ISO POS codes that must contribute more than 5% of
            bookings on a flight.
    """

    cities: list[str] = field(default_factory=list)
    directions: list[str] = field(default_factory=list)
    date_from: date = SNAPSHOT_DATE.date()
    date_to: date = (SNAPSHOT_DATE + pd.Timedelta(days=DEFAULT_DATE_HORIZON_DAYS)).date()
    categories: list[str] = field(default_factory=list)
    cabins: list[str] = field(default_factory=list)
    dtd_range: tuple[int, int] = DEFAULT_DTD_RANGE
    dow: list[int] = field(default_factory=list)
    period_groups: list[str] = field(default_factory=list)
    flight_numbers: list[str] = field(default_factory=list)
    underperforming: list[str] = field(default_factory=list)
    pos_countries: list[str] = field(default_factory=list)

    @property
    def focus_cabins(self) -> list[str]:
        """Cabins the charts should show, in F/J/Y order. Never empty."""
        selected = [c for c in CABINS if c in self.cabins]
        return selected or list(CABINS)


def _clear_all() -> None:
    """Drop every filter widget's stored value so defaults are rebuilt."""
    for key in _KEYS.values():
        st.session_state.pop(key, None)


def _label(container, text: str, hint: str = "") -> None:
    """Render a filter's heading above its widget.

    Streamlit's own widget labels sit low-contrast against the themed sidebar,
    so each filter gets an explicit heading and its built-in label is hidden.

    Args:
        container: The sidebar or column to draw into.
        text: The heading text.
        hint: Optional smaller line beneath the heading.
    """
    hint_html = f"<div class='ek-filter-hint'>{hint}</div>" if hint else ""
    container.markdown(
        f"<div class='ek-filter-label'>{text}</div>{hint_html}",
        unsafe_allow_html=True,
    )


def render_sidebar(options: dict[str, list]) -> FilterState:
    """Draw the sidebar and return the resulting selection.

    Args:
        options: Option lists from ``data_loader.filter_options``.

    Returns:
        The analyst's current selection.
    """
    sidebar = st.sidebar
    sidebar.markdown("## Filters")
    sidebar.caption("Leave a filter empty to include everything.")

    _label(sidebar, "Route", "Outstation city, either direction")
    cities = sidebar.multiselect(
        "Route",
        options=options["cities"],
        default=[],
        key=_KEYS["cities"],
        placeholder=_ALL_PLACEHOLDER,
        label_visibility="collapsed",
    )

    _label(sidebar, "Direction", "Specific leg")
    directions = sidebar.multiselect(
        "Direction",
        options=options["directions"],
        default=[],
        key=_KEYS["directions"],
        placeholder=_ALL_PLACEHOLDER,
        label_visibility="collapsed",
    )

    _label(sidebar, "Date Range", "Departure date")
    date_columns = sidebar.columns(2)
    date_from = date_columns[0].date_input(
        "From",
        value=SNAPSHOT_DATE.date(),
        key=_KEYS["date_from"],
    )
    date_to = date_columns[1].date_input(
        "To",
        value=(SNAPSHOT_DATE + pd.Timedelta(days=DEFAULT_DATE_HORIZON_DAYS)).date(),
        key=_KEYS["date_to"],
    )
    if date_from > date_to:
        sidebar.warning("'From' is after 'To' — no flights can match.")

    _label(sidebar, "Risk Category")
    category_labels = {theme.category_label(c): c for c in risk_scoring.CATEGORIES}
    selected_labels = sidebar.multiselect(
        "Risk Category",
        options=list(category_labels),
        default=[],
        key=_KEYS["categories"],
        placeholder=_ALL_PLACEHOLDER,
        label_visibility="collapsed",
    )
    categories = [category_labels[label] for label in selected_labels]

    _label(sidebar, "Cabin Class", "Focuses charts; does not hide flights")
    cabin_labels = {CABIN_LABELS[c]: c for c in CABINS}
    selected_cabin_labels = sidebar.multiselect(
        "Cabin Class",
        options=list(cabin_labels),
        default=[],
        key=_KEYS["cabins"],
        placeholder=_ALL_PLACEHOLDER,
        label_visibility="collapsed",
    )
    cabins = [cabin_labels[label] for label in selected_cabin_labels]

    _label(sidebar, "Days to Departure", "Real days left until departure")
    dtd_range = sidebar.slider(
        "Days to Departure",
        min_value=DTD_SLIDER_MIN,
        max_value=DTD_SLIDER_MAX,
        value=DEFAULT_DTD_RANGE,
        key=_KEYS["dtd"],
        label_visibility="collapsed",
    )

    _label(sidebar, "Day of Week", "Departure weekday, 1 = Monday")
    dow_labels = {dow_label(d): d for d in sorted(DOW_NAMES)}
    selected_dow_labels = sidebar.multiselect(
        "Day of Week",
        options=list(dow_labels),
        default=[],
        key=_KEYS["dow"],
        placeholder=_ALL_PLACEHOLDER,
        label_visibility="collapsed",
    )
    dow = [dow_labels[label] for label in selected_dow_labels]

    _label(sidebar, "Period / Peak Holiday", "Covers all sub-periods")
    period_groups = sidebar.multiselect(
        "Period / Peak Holiday",
        options=options["period_groups"],
        default=[],
        key=_KEYS["periods"],
        placeholder=_ALL_PLACEHOLDER,
        label_visibility="collapsed",
    )

    _label(sidebar, "Flight Number")
    flight_numbers = sidebar.multiselect(
        "Flight Number",
        options=options["flight_numbers"],
        default=[],
        key=_KEYS["flight_numbers"],
        placeholder=_ALL_PLACEHOLDER,
        label_visibility="collapsed",
    )

    _label(
        sidebar,
        "Underperforming vs LY",
        "BLACK flag: BSF vLY at least 10 points below last year",
    )
    underperforming = sidebar.multiselect(
        "Underperforming vs LY",
        options=["Yes", "No"],
        default=[],
        key=_KEYS["underperforming"],
        placeholder=_ALL_PLACEHOLDER,
        label_visibility="collapsed",
    )

    pos_options = options.get("pos_countries", [])
    if pos_options:
        _label(
            sidebar,
            "Point of Sale",
            "Flights where the selected country is over 5% of bookings",
        )
        pos_countries = sidebar.multiselect(
            "Point of Sale",
            options=pos_options,
            default=[],
            key=_KEYS["pos"],
            placeholder=_ALL_PLACEHOLDER,
            format_func=lambda code: f"{code} ({POS_NAMES.get(code, code)})",
            label_visibility="collapsed",
        )
    else:
        pos_countries = []

    sidebar.divider()
    sidebar.button(
        "Clear all filters",
        on_click=_clear_all,
        width="stretch",
        type="secondary",
    )

    return FilterState(
        cities=cities,
        directions=directions,
        date_from=date_from,
        date_to=date_to,
        categories=categories,
        cabins=cabins,
        dtd_range=(int(dtd_range[0]), int(dtd_range[1])),
        dow=dow,
        period_groups=period_groups,
        flight_numbers=flight_numbers,
        underperforming=underperforming,
        pos_countries=pos_countries,
    )


def _period_pattern(groups: list[str]) -> str:
    """Build a regex matching any raw Period in the selected groups.

    Args:
        groups: Consolidated group names.

    Returns:
        An alternation of the groups' escaped substrings.
    """
    substrings = [
        re.escape(substring)
        for group in groups
        for substring in PERIOD_GROUPS.get(group, ())
    ]
    return "|".join(substrings)


def apply_filters(
    df: pd.DataFrame, state: FilterState, *, by_category: bool = True
) -> pd.DataFrame:
    """Restrict rows to the analyst's selection.

    An empty multi-select imposes no restriction. The date range and
    days-to-departure bounds always apply.

    Args:
        df: Rows to filter. Scored already if ``by_category`` is set.
        state: The current selection.
        by_category: Whether to apply the risk-category filter. Turn off for
            unscored frames such as raw booking-curve snapshots.

    Returns:
        The matching rows.
    """
    if df.empty:
        return df.copy()

    mask = df["Dep Date"].between(
        pd.Timestamp(state.date_from), pd.Timestamp(state.date_to)
    ) & df[risk_scoring.DTD_COLUMN].between(*state.dtd_range)

    if state.cities:
        hub = infer_hub(df["Route"].dropna().unique())
        mask &= df["Route"].map(lambda route: outstation(route, hub)).isin(
            state.cities
        )
    if state.directions:
        mask &= df["Route"].isin(state.directions)
    if state.dow:
        mask &= df["DOW"].isin(state.dow)
    if state.period_groups:
        mask &= df["Period"].str.contains(
            _period_pattern(state.period_groups), regex=True, na=False
        )
    if state.flight_numbers:
        mask &= df["Flight No"].isin(state.flight_numbers)
    if by_category and state.categories and "Risk Category" in df.columns:
        mask &= df["Risk Category"].isin(state.categories)
    if (
        state.underperforming
        and "Underperforming vs LY" in df.columns
        and set(state.underperforming) != {"Yes", "No"}
    ):
        want_flagged = "Yes" in state.underperforming
        mask &= df["Underperforming vs LY"] == want_flagged
    if state.pos_countries:
        shares = []
        for code in state.pos_countries:
            column = f"POS_{code}"
            if column not in df.columns:
                continue
            share = df[column] / df["Total Bkg"].replace(0, pd.NA)
            shares.append(share.fillna(0) > POS_MIN_SHARE)
        if shares:
            combined = shares[0]
            for extra in shares[1:]:
                combined = combined | extra
            mask &= combined

    return df[mask].copy()


def active_filter_summary(state: FilterState) -> list[str]:
    """Describe the filters currently narrowing the view.

    Used to explain an unexpectedly empty table.

    Args:
        state: The current selection.

    Returns:
        Short descriptions of the active restrictions.
    """
    notes = [f"departures {state.date_from} to {state.date_to}"]
    if state.dtd_range != DEFAULT_DTD_RANGE:
        notes.append(f"days to departure {state.dtd_range[0]}–{state.dtd_range[1]}")
    if state.cities:
        notes.append(f"route: {', '.join(state.cities)}")
    if state.directions:
        notes.append(f"direction: {', '.join(state.directions)}")
    if state.categories:
        notes.append(f"category: {', '.join(state.categories)}")
    if state.dow:
        notes.append(f"day of week: {', '.join(dow_label(d) for d in state.dow)}")
    if state.period_groups:
        notes.append(f"period: {', '.join(state.period_groups)}")
    if state.flight_numbers:
        notes.append(f"flight: {', '.join(state.flight_numbers)}")
    if state.underperforming:
        notes.append(f"underperforming vs LY: {', '.join(state.underperforming)}")
    if state.pos_countries:
        notes.append(f"point of sale: {', '.join(state.pos_countries)}")
    return notes
