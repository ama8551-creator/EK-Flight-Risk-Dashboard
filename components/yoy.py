"""Tab 5 — versus-last-year comparison (specification section 6, Tab 5).

Answers "is this flight unusually full, or is it always like this?". A 95%
Economy load factor is alarming in isolation and unremarkable if the same
flight ran 97% last year, so the comparison is what turns a number into a
judgement.

------------------------------------------------------------------------------
A dataset limitation worth knowing
------------------------------------------------------------------------------
Flown flights carry exactly one row in the workbook — their terminal state —
so last year's flight usually has no snapshot history. When last year does
have a curve, both years are overlaid against days-to-departure. When it
does not, last year appears as a reference level plus a marker at departure,
so the comparison is still visible: where this year's curve sits relative to
where last year finished.
"""

from __future__ import annotations

from typing import Final

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import approved_peaks
import risk_scoring
import utils
from components import flight_picker, kpi_cards
from data_loader import CABINS
from styling import theme

#: Colour for the prior-year series, distinct from the cabin palette.
PRIOR_YEAR_COLOR: Final[str] = "#1F6FB2"

#: A deviation smaller than this is reported as "broadly flat" rather than
#: being dressed up as a trend. One percentage point of load factor.
MATERIAL_DEVIATION: Final[float] = 0.01

#: Full cabin names used in prose.
CABIN_NAMES: Final[dict[str, str]] = {
    "F": "First",
    "J": "Business",
    "Y": "Economy",
}


def _state_card(
    title: str,
    row: pd.Series,
    subtitle: str,
    period: str | None = None,
) -> str:
    """Build a KPI-style card summarising one year's state of the flight.

    Args:
        title: Card heading, "This Year" or "Last Year".
        row: The flight row being summarised.
        subtitle: Line beneath the headline figure.
        period: Approved peak name, or an em dash when none is approved.

    Returns:
        HTML for the card.
    """
    cabins = "".join(
        f"<div class='ek-kpi-sub'>{cabin} ({CABIN_NAMES[cabin]}): "
        f"<strong>{utils.format_pct(row[f'{cabin} BSF'])}</strong></div>"
        for cabin in CABINS
    )
    label = (
        period
        if period is not None
        else approved_peaks.display_period(row)
    )
    period_line = f"<div class='ek-kpi-sub'>Period: {label}</div>"
    return kpi_cards.card(
        title,
        utils.format_pct(row["Total BSF"]),
        subtitle,
        accent=theme.EMIRATES_RED if title == "This Year" else PRIOR_YEAR_COLOR,
        trend=cabins + period_line,
    )


def _deviation_summary(current: pd.Series, prior: pd.Series) -> str:
    """Describe the vs-last-year change and what is driving it.

    The driver is the cabin with the largest *capacity-weighted* contribution
    to the total change, not the largest percentage-point move. A cabin with
    12 seats can swing 20% and barely shift the flight.

    Args:
        current: This year's flight state.
        prior: Last year's flight state.

    Returns:
        A sentence describing the deviation.
    """
    total_change = float(current["Total BSF"]) - float(prior["Total BSF"])

    contributions = {
        cabin: (
            float(current[f"{cabin} BSF"]) - float(prior[f"{cabin} BSF"])
        )
        * float(current[f"{cabin} Cap"])
        / float(current["Total Cap"])
        for cabin in CABINS
    }
    driver = max(contributions, key=lambda c: abs(contributions[c]))
    driver_change = float(current[f"{driver} BSF"]) - float(
        prior[f"{driver} BSF"]
    )

    if abs(total_change) < MATERIAL_DEVIATION:
        return (
            f"This flight is broadly flat versus last year "
            f"({total_change * 100:+.1f}% total BSF). No cabin is moving the "
            "flight materially."
        )

    direction = "stronger" if driver_change > 0 else "weaker"
    return (
        f"This flight is **{total_change * 100:+.1f}%** vs last year, driven "
        f"primarily by {direction} {driver} demand."
    )


def _build_chart(
    rows: pd.DataFrame, prior_rows: pd.DataFrame, prior_date: pd.Timestamp
) -> go.Figure:
    """Overlay this year's booking curve on last year's.

    Last year's flown legs are stored as a single terminal row, so the overlay
    falls back to a reference level plus a marker at departure when there is
    no prior-year curve to draw. When last year does have snapshots, both
    curves are plotted against days-to-departure.

    Args:
        rows: Every snapshot of this year's leg, oldest observation first.
        prior_rows: Every snapshot of last year's matching leg.
        prior_date: Last year's departure date.

    Returns:
        The configured figure.
    """
    figure = go.Figure()
    prior = prior_rows.iloc[-1]

    figure.add_trace(
        go.Scatter(
            x=rows["Days to Departure"],
            y=rows["Total BSF"],
            name="This year — total BSF",
            mode="lines+markers",
            line={"color": theme.EMIRATES_RED, "width": 2.5},
            marker={"size": 7},
            hovertemplate="This year: %{y:.1%}<extra></extra>",
        )
    )

    if len(prior_rows) > 1:
        figure.add_trace(
            go.Scatter(
                x=prior_rows["Days to Departure"],
                y=prior_rows["Total BSF"],
                name=f"Last year — {prior_date:%d %b %Y}",
                mode="lines+markers",
                line={"color": PRIOR_YEAR_COLOR, "width": 2, "dash": "dot"},
                marker={"size": 7, "color": PRIOR_YEAR_COLOR},
                hovertemplate="Last year: %{y:.1%}<extra></extra>",
            )
        )
    else:
        figure.add_trace(
            go.Scatter(
                x=[0],
                y=[float(prior["Total BSF"])],
                name=f"Last year — final ({prior_date:%d %b %Y})",
                mode="markers",
                marker={
                    "size": 14,
                    "color": PRIOR_YEAR_COLOR,
                    "symbol": "diamond",
                },
                hovertemplate="Last year final: %{y:.1%}<extra></extra>",
            )
        )
        figure.add_hline(
            y=float(prior["Total BSF"]),
            line_width=2,
            line_dash="dot",
            line_color=PRIOR_YEAR_COLOR,
            annotation_text="last year's final total BSF",
            annotation_position="bottom left",
        )

    figure.add_hline(
        y=1.0,
        line_width=2,
        line_dash="dash",
        line_color=theme.CHARCOAL,
        annotation_text="100% capacity",
        annotation_position="top left",
    )

    figure.update_xaxes(title="Days to departure", autorange="reversed")
    figure.update_yaxes(
        title="Total booked seat factor", range=[0.0, 1.20], tickformat=".0%"
    )
    figure.update_layout(
        **theme.plotly_layout(height=440, hovermode="x unified")
    )
    return figure


def _render_cabin_table(current: pd.Series, prior: pd.Series) -> None:
    """Show the per-cabin vs-last-year movement.

    Args:
        current: This year's flight state.
        prior: Last year's flight state.
    """
    rows = []
    for cabin in list(CABINS) + ["Total"]:
        column = "Total BSF" if cabin == "Total" else f"{cabin} BSF"
        booked = "Total Bkg" if cabin == "Total" else f"{cabin} Bkg"
        this_year, last_year = float(current[column]), float(prior[column])
        rows.append(
            {
                "Cabin": cabin
                if cabin == "Total"
                else f"{cabin} ({CABIN_NAMES[cabin]})",
                "This year BSF": this_year,
                "Last year BSF": last_year,
                "Change": this_year - last_year,
                "This year bkg": int(current[booked]),
                "Last year bkg": int(prior[booked]),
            }
        )

    table = pd.DataFrame(rows)
    styler = table.style.format(
        {
            "This year BSF": "{:.1%}",
            "Last year BSF": "{:.1%}",
            "Change": utils.format_signed_pct,
        }
    )
    st.dataframe(
        utils.style_bsf_columns(styler, ["This year BSF", "Last year BSF"]),
        width="stretch",
        hide_index=True,
    )


def render_content(
    flights: pd.DataFrame, selection: flight_picker.Selection
) -> None:
    """Draw the versus-last-year comparison for an already chosen leg.

    Args:
        flights: Preprocessed frame, used to find last year's counterpart.
        selection: The chosen flight leg.
    """
    if selection.rows.empty:
        st.markdown(utils.empty_state(), unsafe_allow_html=True)
        return

    st.markdown(
        "Compare this flight with its own operation a year earlier, matched "
        "on flight number and day of week."
    )
    st.caption(
        f"Last year's counterpart is the same flight "
        f"{utils.YOY_OFFSET_DAYS} days earlier, which keeps the weekday "
        "aligned; the nearest operating date within 3 days is used if that "
        "exact date did not fly."
    )

    matches = utils.find_prior_year_flight(
        flights, selection.flight_no, selection.dep_date
    )
    if matches.empty:
        st.markdown(
            utils.empty_state(
                "No comparison data available. The dataset holds no "
                f"{selection.flight_no} operation within 3 days of "
                f"{utils.prior_year_date(selection.dep_date):%d %b %Y}."
            ),
            unsafe_allow_html=True,
        )
        return

    current = selection.latest
    # Flown legs have one row; open legs would have several, so take the last.
    prior_leg = matches[
        matches["Dep Date"] == matches.iloc[0]["Dep Date"]
    ].sort_values("Days to Departure")
    prior = prior_leg.iloc[-1]
    prior_date = pd.Timestamp(prior["Dep Date"])

    if prior_date.isoweekday() != selection.dep_date.isoweekday():
        st.warning(
            f"Closest prior-year operation is {prior_date:%a %d %b %Y}, a "
            f"different weekday to this year's {selection.dep_date:%a}. "
            "Day of week drives demand strongly here, so read the comparison "
            "with that in mind."
        )

    this_year_label = (
        "Final BSF at departure" if selection.is_flown else "Current BSF"
    )
    peaks = approved_peaks.load_approved_peaks()
    cards = [
        _state_card(
            "This Year",
            current,
            this_year_label,
            period=approved_peaks.display_period(current, peaks),
        ),
        _state_card(
            "Last Year",
            prior,
            f"Final BSF · {prior_date:%d %b %Y}",
            period=approved_peaks.display_period(prior, peaks),
        ),
    ]
    for column, html in zip(st.columns(2), cards):
        column.markdown(html, unsafe_allow_html=True)

    st.write("")
    st.markdown("#### Deviation")
    st.markdown(_deviation_summary(current, prior))
    if not selection.is_flown:
        st.caption(
            f"This year is still open at {int(current[risk_scoring.DTD_COLUMN])} "
            "days out, so it is being compared against where last year "
            "*finished*. Expect this year to look lower until close to "
            "departure."
        )

    st.write("")
    if len(prior_leg) > 1:
        st.markdown("#### Booking curve vs last year")
        st.caption(
            "Both years plotted against days to departure. Click a legend "
            "entry to hide or isolate a series."
        )
    else:
        st.markdown("#### Booking curve vs last year's final position")
        st.caption(
            "Last year's matching operation is stored as a single terminal "
            "row, so there is no prior-year curve to overlay — it appears as "
            "the dotted reference level and the diamond at departure."
        )
    st.plotly_chart(
        _build_chart(selection.rows, prior_leg, prior_date), width="stretch"
    )

    st.markdown("#### Per-cabin comparison")
    _render_cabin_table(current, prior)
