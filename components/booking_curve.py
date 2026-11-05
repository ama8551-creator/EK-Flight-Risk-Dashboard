"""Booking Curve sub-tab of Flight Analysis.

Two modes share the same axes (days to departure 120 → 0, BSF 0–120%):

* A specific flight overlays this year's F/J/Y curves on last year's, dashed.
* All Flights plots average total BSF by the chosen grouping, this year solid
  and last year dashed.
"""

from __future__ import annotations

from typing import Final

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import approved_peaks
import utils
from components import yoy
from data_loader import (
    CABINS,
    FLIGHT_KEY,
    SNAPSHOT_DAYS,
    STATUS_FLOWN,
    STATUS_OPEN,
    infer_hub,
    outstation,
)
from styling import theme

Y_AXIS_RANGE: Final[tuple[float, float]] = (0.0, 1.20)
CAPACITY_LINE: Final[float] = 1.0

GROUP_DIRECTION: Final[str] = "Group by Direction"
GROUP_ROUTE: Final[str] = "Group by Route"
GROUP_CABIN: Final[str] = "Group by Cabin (F, J, Y averaged)"
GROUPING_OPTIONS: Final[tuple[str, ...]] = (
    GROUP_DIRECTION,
    GROUP_ROUTE,
    GROUP_CABIN,
)

CABIN_NAMES: Final[dict[str, str]] = {
    "F": "F BSF (First)",
    "J": "J BSF (Business)",
    "Y": "Y BSF (Economy)",
}

_BSF_COLUMNS: Final[list[str]] = [f"{cabin} BSF" for cabin in CABINS] + ["Total BSF"]


def _template_by(
    snaps: pd.DataFrame, keys: list[str]
) -> dict[tuple[object, ...], pd.DataFrame]:
    """Mean BSF at each snapshot day, keyed by ``keys``."""
    if snaps.empty:
        return {}
    grouped = (
        snaps.groupby(keys + ["Days to Departure"], sort=False)[_BSF_COLUMNS]
        .mean()
        .reset_index()
    )
    templates: dict[tuple[object, ...], pd.DataFrame] = {}
    for key, part in grouped.groupby(keys, sort=False):
        if not isinstance(key, tuple):
            key = (key,)
        templates[key] = part.set_index("Days to Departure")[_BSF_COLUMNS]
    return templates


def _pick_template(
    row: pd.Series,
    by_flight: dict[tuple[object, ...], pd.DataFrame],
    by_route: dict[tuple[object, ...], pd.DataFrame],
) -> pd.DataFrame | None:
    """Prefer the same flight number's curve, else the same route."""
    template = by_flight.get((row["Flight No"],))
    if template is not None and not template.empty:
        return template
    template = by_route.get((row["Route"],))
    if template is not None and not template.empty:
        return template
    return None


def _reconstruct_leg(row: pd.Series, template: pd.DataFrame) -> pd.DataFrame:
    """Build a 120→0 curve for a flown leg, scaled to its final BSF."""
    nearest = int(template.index.min())
    rows = [row]
    for dtd in SNAPSHOT_DAYS:
        if dtd == 0 or dtd not in template.index:
            continue
        synthetic = row.copy()
        synthetic["Days to Departure"] = dtd
        for column in _BSF_COLUMNS:
            base = float(template.loc[nearest, column])
            observed = float(template.loc[dtd, column])
            final = float(row[column])
            synthetic[column] = (
                observed * (final / base) if base else observed
            )
        rows.append(synthetic)
    frame = pd.DataFrame(rows).sort_values("Days to Departure", ascending=False)
    return frame.reset_index(drop=True)


def expand_snapshot_history(
    flights: pd.DataFrame, selected: pd.DataFrame
) -> tuple[pd.DataFrame, bool]:
    """Ensure every selected leg has a full snapshot-grid curve.

    Open legs already carry their observed 120→0 (or remaining) snapshots.
    Flown legs in this workbook store only the terminal DTD=0 row, so their
    intermediate points are reconstructed from the same flight number's
    observed booking curve and scaled to that leg's final BSF.

    Args:
        flights: Full preprocessed frame, used as the template source.
        selected: Snapshots matching the Flight Analysis selectors.

    Returns:
        The expanded frame, and whether any leg was reconstructed.
    """
    if selected.empty:
        return selected, False

    open_snaps = flights[flights["Status"] == STATUS_OPEN]
    source = open_snaps if not open_snaps.empty else flights
    by_flight = _template_by(source, ["Flight No"])
    by_route = _template_by(source, ["Route"])

    pieces: list[pd.DataFrame] = []
    reconstructed = False
    for _, leg in selected.groupby(FLIGHT_KEY, sort=False):
        terminal = leg.iloc[-1]
        if (
            int(leg["Days to Departure"].nunique()) > 1
            or str(terminal["Status"]) != STATUS_FLOWN
        ):
            pieces.append(leg)
            continue
        template = _pick_template(terminal, by_flight, by_route)
        if template is None:
            pieces.append(leg)
            continue
        pieces.append(_reconstruct_leg(leg.iloc[-1], template))
        reconstructed = True
    return pd.concat(pieces, ignore_index=True), reconstructed


def _latest_legs(snaps: pd.DataFrame) -> pd.DataFrame:
    """One current-state row per flight leg."""
    if snaps.empty:
        return snaps
    keep = snaps.groupby(FLIGHT_KEY, sort=False)["Days to Departure"].idxmin()
    return snaps.loc[keep]


def _mean_by_dtd(snaps: pd.DataFrame, column: str) -> pd.Series:
    """Average a BSF column at each snapshot grid point, 120 days first.

    Uses every matching snapshot in the selected window — not the latest
    row per flight — then reindexes onto the canonical snapshot grid.
    """
    if snaps.empty or column not in snaps.columns:
        return pd.Series(dtype=float)
    means = snaps.groupby("Days to Departure")[column].mean()
    ordered = [day for day in SNAPSHOT_DAYS if day in means.index]
    return means.reindex(ordered)


def _add_capacity_line(figure: go.Figure) -> None:
    """Draw the 100% reference line."""
    figure.add_hline(
        y=CAPACITY_LINE,
        line_width=2,
        line_dash="dash",
        line_color=theme.CHARCOAL,
        annotation_text="100% capacity",
        annotation_position="top left",
    )


def _axis_layout(figure: go.Figure, y_title: str) -> None:
    """Apply the shared 120→0 / 0–120% axes."""
    figure.update_xaxes(
        title="Days to departure",
        range=[120, 0],
        tickmode="array",
        tickvals=list(SNAPSHOT_DAYS),
        constrain="domain",
    )
    figure.update_yaxes(
        title=y_title,
        range=list(Y_AXIS_RANGE),
        tickformat=".0%",
    )
    figure.update_layout(**theme.plotly_layout(height=460, hovermode="x unified"))


def _add_series(
    figure: go.Figure,
    x: pd.Series,
    y: pd.Series,
    name: str,
    color: str,
    *,
    dashed: bool,
) -> None:
    """Add one booking-curve trace."""
    figure.add_trace(
        go.Scatter(
            x=list(x),
            y=list(y),
            name=name,
            mode="lines+markers",
            line={
                "color": color,
                "width": 2 if dashed else 2.5,
                "dash": "dash" if dashed else "solid",
            },
            marker={"size": 7, "color": color},
            connectgaps=True,
            hovertemplate=f"{name}: %{{y:.1%}}<extra></extra>",
        )
    )


def _build_flight_chart(
    rows: pd.DataFrame, prior_rows: pd.DataFrame | None
) -> go.Figure:
    """Six cabin lines: this year solid in cabin colours, last year grey dashed."""
    figure = go.Figure()
    for cabin in CABINS:
        _add_series(
            figure,
            rows["Days to Departure"],
            rows[f"{cabin} BSF"],
            f"{cabin} this year",
            theme.CURVE_CABIN_COLORS[cabin],
            dashed=False,
        )
        if prior_rows is not None and not prior_rows.empty:
            _add_series(
                figure,
                prior_rows["Days to Departure"],
                prior_rows[f"{cabin} BSF"],
                f"{cabin} last year",
                theme.LAST_YEAR_LINE,
                dashed=True,
            )
    _add_capacity_line(figure)
    _axis_layout(figure, "Booked seat factor")
    return figure


def _group_color(index: int) -> str:
    """Pick a stable colour for an aggregate series."""
    return theme.ROUTE_COLORS[index % len(theme.ROUTE_COLORS)]


def _group_key(snaps: pd.DataFrame, grouping: str, hub: str) -> pd.Series:
    """Label each snapshot by the active grouping, from the loaded routes.

    ``hub`` must come from the full dataset so a one-direction slice cannot
    mis-identify the hub airport.
    """
    if grouping == GROUP_ROUTE:
        return snaps["Route"].map(lambda route: outstation(route, hub))
    return snaps["Route"]


def _build_aggregate_chart(
    this_year: pd.DataFrame,
    last_year: pd.DataFrame,
    grouping: str,
    hub: str,
    *,
    collapsed: bool,
) -> go.Figure:
    """Average-total (or per-cabin) curves for All Flights mode.

    ``collapsed`` draws one this-year line and one last-year line across
    every matching flight, used when the sidebar has no route or direction.
    """
    figure = go.Figure()
    if collapsed:
        this_series = _mean_by_dtd(this_year, "Total BSF")
        _add_series(
            figure,
            this_series.index,
            this_series,
            "All Routes (This Year)",
            theme.EMIRATES_RED,
            dashed=False,
        )
        if not last_year.empty:
            last_series = _mean_by_dtd(last_year, "Total BSF")
            _add_series(
                figure,
                last_series.index,
                last_series,
                "All Routes (Last Year)",
                theme.LAST_YEAR_LINE,
                dashed=True,
            )
    elif grouping == GROUP_CABIN:
        for cabin in CABINS:
            color = theme.CURVE_CABIN_COLORS[cabin]
            this_series = _mean_by_dtd(this_year, f"{cabin} BSF")
            _add_series(
                figure,
                this_series.index,
                this_series,
                f"{cabin} this year",
                color,
                dashed=False,
            )
            if not last_year.empty:
                last_series = _mean_by_dtd(last_year, f"{cabin} BSF")
                _add_series(
                    figure,
                    last_series.index,
                    last_series,
                    f"{cabin} last year",
                    theme.LAST_YEAR_LINE,
                    dashed=True,
                )
    else:
        this_groups = _group_key(this_year, grouping, hub)
        last_groups = (
            _group_key(last_year, grouping, hub)
            if not last_year.empty
            else pd.Series(dtype=str)
        )
        names = sorted(set(this_groups.dropna().unique()) | set(last_groups.dropna().unique()))
        for index, name in enumerate(names):
            color = _group_color(index)
            subset = this_year.loc[this_groups == name]
            if not subset.empty:
                series = _mean_by_dtd(subset, "Total BSF")
                _add_series(
                    figure,
                    series.index,
                    series,
                    f"{name} this year",
                    color,
                    dashed=False,
                )
            if not last_year.empty:
                prior = last_year.loc[last_groups == name]
                if not prior.empty:
                    series = _mean_by_dtd(prior, "Total BSF")
                    _add_series(
                        figure,
                        series.index,
                        series,
                        f"{name} last year",
                        theme.LAST_YEAR_LINE,
                        dashed=True,
                    )
    _add_capacity_line(figure)
    y_title = (
        "Average booked seat factor"
        if not collapsed and grouping == GROUP_CABIN
        else "Average total booked seat factor"
    )
    _axis_layout(figure, y_title)
    return figure


def _render_flight_cards(current: pd.Series, prior: pd.Series | None) -> None:
    """This Year / Last Year BSF cards for a single flight."""
    peaks = approved_peaks.load_approved_peaks()
    this_card = yoy._state_card(
        "This Year",
        current,
        "Current BSF at latest snapshot",
        period=approved_peaks.display_period(current, peaks),
    )
    columns = st.columns(2)
    columns[0].markdown(this_card, unsafe_allow_html=True)
    if prior is None:
        columns[1].markdown(
            utils.empty_state("No prior year data available"),
            unsafe_allow_html=True,
        )
        return
    columns[1].markdown(
        yoy._state_card(
            "Last Year",
            prior,
            f"Same flight · {pd.Timestamp(prior['Dep Date']):%d %b %Y}",
            period=approved_peaks.display_period(prior, peaks),
        ),
        unsafe_allow_html=True,
    )


def _render_aggregate_table(
    this_year: pd.DataFrame,
    last_year: pd.DataFrame,
    grouping: str,
    hub: str,
    *,
    collapsed: bool,
) -> None:
    """Group / Avg BSF This Year / Last Year / vLY Change."""
    this_latest = _latest_legs(this_year)
    last_latest = _latest_legs(last_year)

    rows: list[dict[str, object]] = []
    if collapsed:
        this_avg = float(this_latest["Total BSF"].mean()) if not this_latest.empty else None
        last_avg = float(last_latest["Total BSF"].mean()) if not last_latest.empty else None
        change = (
            this_avg - last_avg
            if this_avg is not None and last_avg is not None
            else None
        )
        rows.append(
            {
                "Group": "All Routes",
                "Avg BSF This Year": this_avg,
                "Avg BSF Last Year": last_avg,
                "vLY Change": change,
            }
        )
    elif grouping == GROUP_CABIN:
        for cabin in CABINS:
            this_avg = float(this_latest[f"{cabin} BSF"].mean()) if not this_latest.empty else None
            last_avg = (
                float(last_latest[f"{cabin} BSF"].mean()) if not last_latest.empty else None
            )
            change = (
                this_avg - last_avg
                if this_avg is not None and last_avg is not None
                else None
            )
            rows.append(
                {
                    "Group": cabin,
                    "Avg BSF This Year": this_avg,
                    "Avg BSF Last Year": last_avg,
                    "vLY Change": change,
                }
            )
    else:
        this_groups = (
            _group_key(this_latest, grouping, hub)
            if not this_latest.empty
            else pd.Series(dtype=str)
        )
        last_groups = (
            _group_key(last_latest, grouping, hub)
            if not last_latest.empty
            else pd.Series(dtype=str)
        )
        names = sorted(set(this_groups.dropna().unique()) | set(last_groups.dropna().unique()))
        for name in names:
            this_avg = (
                float(this_latest.loc[this_groups == name, "Total BSF"].mean())
                if not this_latest.empty and (this_groups == name).any()
                else None
            )
            last_avg = (
                float(last_latest.loc[last_groups == name, "Total BSF"].mean())
                if not last_latest.empty and (last_groups == name).any()
                else None
            )
            change = (
                this_avg - last_avg
                if this_avg is not None and last_avg is not None
                else None
            )
            rows.append(
                {
                    "Group": name,
                    "Avg BSF This Year": this_avg,
                    "Avg BSF Last Year": last_avg,
                    "vLY Change": change,
                }
            )

    table = pd.DataFrame(rows)
    styler = table.style.format(
        {
            "Avg BSF This Year": lambda v: utils.format_pct(v),
            "Avg BSF Last Year": lambda v: utils.format_pct(v),
            "vLY Change": lambda v: utils.format_signed_pct(v),
        }
    )
    st.dataframe(
        utils.style_bsf_columns(styler, ["Avg BSF This Year", "Avg BSF Last Year"]),
        width="stretch",
        hide_index=True,
    )


def render_flight(
    rows: pd.DataFrame,
    prior_rows: pd.DataFrame | None,
    *,
    flight_no: str,
    dep_date: pd.Timestamp,
    flights: pd.DataFrame | None = None,
) -> None:
    """Mode A: one flight, six cabin lines, cards and a vLY sentence."""
    if rows.empty:
        st.markdown(
            utils.empty_state("That flight has no snapshots in the selected range."),
            unsafe_allow_html=True,
        )
        return

    reconstructed = False
    if flights is not None:
        rows, reconstructed = expand_snapshot_history(flights, rows)
        if prior_rows is not None and not prior_rows.empty:
            prior_rows, _ = expand_snapshot_history(flights, prior_rows)

    st.caption(
        f"Curve for **{flight_no}** departing {dep_date:%d %b %Y} "
        "(soonest departure in the selected range)."
    )
    if reconstructed:
        st.caption(
            "This flown leg stores only a terminal snapshot. Intermediate "
            "points are reconstructed from the same flight number's observed "
            "booking curve, scaled to this flight's final BSF."
        )
    st.plotly_chart(_build_flight_chart(rows, prior_rows), width="stretch")

    current = rows.iloc[-1]
    prior = None if prior_rows is None or prior_rows.empty else prior_rows.iloc[-1]
    _render_flight_cards(current, prior)

    st.write("")
    if prior is None:
        st.info("No prior year data available")
        return
    st.markdown(yoy._deviation_summary(current, prior))


def render_aggregate(
    this_year: pd.DataFrame,
    last_year: pd.DataFrame,
    grouping: str,
    flights: pd.DataFrame,
    *,
    collapsed: bool = False,
) -> None:
    """Mode B: All Flights average curves plus the group summary table."""
    if this_year.empty:
        st.markdown(
            utils.empty_state("No flights match the selected date range."),
            unsafe_allow_html=True,
        )
        return

    this_year, reconstructed = expand_snapshot_history(flights, this_year)
    if not last_year.empty:
        last_year, _ = expand_snapshot_history(flights, last_year)

    hub = infer_hub(flights["Route"].dropna().unique())
    if collapsed:
        st.info(
            "Showing aggregated curves across all routes. Select a route "
            "above or in the sidebar to see the breakdown."
        )
    st.caption(
        "Each point is the average Total BSF of every snapshot at that "
        "days-to-departure value in the selected date range — not the latest "
        "snapshot per flight. Last year uses the same window "
        f"{utils.YOY_OFFSET_DAYS} days earlier."
    )
    if reconstructed:
        st.caption(
            "Flown legs store only a terminal snapshot. Intermediate points "
            "are reconstructed from the same flight number's observed booking "
            "curve, scaled to each flight's final BSF, then averaged by "
            "days to departure."
        )
    st.plotly_chart(
        _build_aggregate_chart(
            this_year, last_year, grouping, hub, collapsed=collapsed
        ),
        width="stretch",
    )
    st.markdown("#### Group summary")
    _render_aggregate_table(
        this_year, last_year, grouping, hub, collapsed=collapsed
    )
