"""Alert Timeline — when each flight is projected to need attention.

The other tabs answer "what needs action now". This one answers "what is
coming", so an analyst can plan a week rather than react to a day.

------------------------------------------------------------------------------
How the projection works, and why it is a projection
------------------------------------------------------------------------------
The dataset contains no snapshots after the snapshot date: every one of its
open-flight rows was observed on or before 1 December 2026. So there are no
future observations to categorise, and future risk has to be modelled.

For each open flight leg this module interpolates the booking build-up between
two points it does have:

  * the flight's current observed per-cabin BSF, at its latest snapshot, and
  * the dataset's own forecast per-cabin BSF at departure
    (``F/J/Y Fcst BSF``).

Interpolation is linear in days-to-departure and evaluated at the remaining
snapshot grid points, then the per-cabin figures are recombined into a
capacity-weighted total and passed through the *same* risk rules the rest of
the dashboard uses. Nothing here re-implements the thresholds.

Linear interpolation is the conservative choice: real booking curves are
convex, accelerating as departure approaches, so a linear path tends to reach
each threshold slightly *later* than a realistic curve would. Treat projected
dates as "no earlier than".

A flight's forecast total BSF does not change between checkpoints, so YELLOW
status is effectively time-invariant: a flight is either forecast to breach
capacity or it is not. The dates that genuinely move are the ORANGE and RED
ones, which arrive as the projected current load climbs.
"""

from __future__ import annotations

from typing import Final

import pandas as pd
import plotly.express as px
import streamlit as st

import risk_scoring
import utils
from components import kpi_cards
from data_loader import CABINS, SNAPSHOT_DAYS, SNAPSHOT_DATE, STATUS_OPEN
from styling import theme

#: Checkpoints at which risk is re-evaluated, in days before departure.
CHECKPOINTS: Final[tuple[int, ...]] = SNAPSHOT_DAYS

#: Severity ladder. A flight "enters" a category when its rank increases.
SEVERITY_RANK: Final[dict[str, int]] = {
    risk_scoring.GREEN: 0,
    risk_scoring.YELLOW: 1,
    risk_scoring.ORANGE: 2,
    risk_scoring.RED: 3,
}

#: Categories that constitute an alert worth planning around.
ELEVATED: Final[list[str]] = [
    risk_scoring.RED,
    risk_scoring.ORANGE,
    risk_scoring.YELLOW,
]

#: Cumulative horizons, as (label, days from the snapshot date).
HORIZONS: Final[tuple[tuple[str, int], ...]] = (
    ("Next 7 Days", 7),
    ("Next 14 Days", 14),
    ("Next 30 Days", 30),
)

#: Disjoint buckets behind the workload summary cards, as (label, first day,
#: last day, categories that count, caption, accent, value colour).
WORKLOAD_BUCKETS: Final[tuple[tuple, ...]] = (
    (
        "This week",
        0,
        7,
        [risk_scoring.RED],
        "critical actions needed",
        theme.EMIRATES_RED,
        theme.EMIRATES_RED,
    ),
    (
        "Next week",
        8,
        14,
        [risk_scoring.RED, risk_scoring.ORANGE],
        "flights to monitor",
        theme.ORANGE,
        theme.ORANGE,
    ),
    (
        "Rest of month",
        15,
        30,
        ELEVATED,
        "flights at elevated status",
        theme.YELLOW,
        "#C79100",  # Darkened for legibility on cream.
    ),
)

#: Default and maximum number of flights drawn on the Gantt chart.
GANTT_DEFAULT_ROWS: Final[int] = 20
GANTT_MAX_ROWS: Final[int] = 60


def _interpolate_cabin_bsf(projected: pd.DataFrame) -> pd.DataFrame:
    """Fill in each cabin's projected BSF at every checkpoint.

    Args:
        projected: Cross join of legs and checkpoints, carrying the observed
            BSF (``<cabin> BSF Now``), the forecast at departure
            (``<cabin> Fcst BSF``) and ``Elapsed Fraction``.

    Returns:
        ``projected`` with ``<cabin> BSF`` set for each cabin.
    """
    for cabin in CABINS:
        observed = projected[f"{cabin} BSF Now"]
        forecast = projected[f"{cabin} Fcst BSF"]
        projected[f"{cabin} BSF"] = observed + projected["Elapsed Fraction"] * (
            forecast - observed
        )
    return projected


@st.cache_data(show_spinner="Projecting risk timeline…")
def project_timeline(current: pd.DataFrame) -> pd.DataFrame:
    """Project every open leg's risk category forward to departure.

    Args:
        current: One scored row per open leg, from
            ``data_loader.latest_snapshots``.

    Returns:
        One row per leg per checkpoint, with ``Checkpoint DTD``,
        ``Projected Date`` and the risk columns. Empty if ``current`` is.
    """
    if current.empty:
        return current.copy()

    legs = current.copy()
    for cabin in CABINS:
        legs[f"{cabin} BSF Now"] = legs[f"{cabin} BSF"]

    # Every checkpoint still ahead of the flight, plus "today" as the baseline
    # so the first projected transition is measured against the current state.
    grid = pd.DataFrame({"Checkpoint DTD": list(CHECKPOINTS)})
    ahead = legs.merge(grid, how="cross")
    ahead = ahead[ahead["Checkpoint DTD"] < ahead["Actual DTD"]]

    baseline = legs.copy()
    baseline["Checkpoint DTD"] = baseline["Actual DTD"]

    projected = pd.concat([baseline, ahead], ignore_index=True)

    # 0 at today, 1 at departure. Guard the same-day case, where no time
    # passes: `where` blanks the zero denominator as a float NaN, keeping the
    # series numeric rather than promoting it to object dtype.
    remaining = projected["Actual DTD"].astype("float64")
    projected["Elapsed Fraction"] = (
        (projected["Actual DTD"] - projected["Checkpoint DTD"])
        / remaining.where(remaining != 0.0)
    ).fillna(0.0)

    projected = _interpolate_cabin_bsf(projected)

    # Recombine cabins into a capacity-weighted total, as data_loader does.
    seats = projected["Total Cap"]
    projected["Total Bkg"] = sum(
        (projected[f"{cabin} BSF"] * projected[f"{cabin} Cap"]).round()
        for cabin in CABINS
    )
    projected["Total BSF"] = projected["Total Bkg"] / seats
    for cabin in CABINS:
        projected[f"{cabin} Bkg"] = (
            projected[f"{cabin} BSF"] * projected[f"{cabin} Cap"]
        ).round()

    # Re-score using the real rules: the checkpoint is the time remaining.
    projected["Actual DTD Now"] = projected["Actual DTD"]
    projected["Actual DTD"] = projected["Checkpoint DTD"]
    projected["Status"] = STATUS_OPEN
    projected = risk_scoring.assign_risk(projected)

    projected["Projected Date"] = projected["Dep Date"] - pd.to_timedelta(
        projected["Checkpoint DTD"], unit="D"
    )
    projected["Days From Now"] = (
        projected["Projected Date"] - SNAPSHOT_DATE
    ).dt.days
    projected["Severity"] = projected["Risk Category"].map(SEVERITY_RANK)

    return projected.sort_values(
        ["Flight No", "Dep Date", "Checkpoint DTD"], ascending=[True, True, False]
    ).reset_index(drop=True)


@st.cache_data(show_spinner=False)
def category_entries(projected: pd.DataFrame) -> pd.DataFrame:
    """Find the date each leg first escalates into each category.

    An "entry" is a step *up* the severity ladder, so a flight that is already
    YELLOW today is not reported as newly entering YELLOW tomorrow.

    Args:
        projected: Output of :func:`project_timeline`.

    Returns:
        One row per escalation, with the category entered and its date.
    """
    if projected.empty:
        return projected.copy()

    ordered = projected.sort_values(
        ["Flight No", "Dep Date", "Checkpoint DTD"], ascending=[True, True, False]
    )
    leg = ["Flight No", "Dep Date"]
    previous = ordered.groupby(leg, sort=False)["Severity"].shift()

    # An escalation: severity rose above where this leg previously sat. The
    # baseline row has no predecessor, so it anchors the comparison instead.
    escalations = ordered[
        previous.notna()
        & (ordered["Severity"] > previous)
        & (ordered["Severity"] > SEVERITY_RANK[risk_scoring.GREEN])
    ].copy()
    escalations["Previous Category"] = ordered["Risk Category"].groupby(
        [ordered["Flight No"], ordered["Dep Date"]], sort=False
    ).shift()[escalations.index]

    # Keep only the first escalation into each category per leg.
    return escalations.sort_values("Projected Date").drop_duplicates(
        subset=leg + ["Risk Category"], keep="first"
    )


@st.cache_data(show_spinner=False)
def category_bands(projected: pd.DataFrame) -> pd.DataFrame:
    """Collapse each leg's checkpoints into contiguous category bands.

    A checkpoint only tells you the category on that date; the flight holds
    that category until the next checkpoint. Bands make that explicit, which
    is what lets the workload cards answer "how many flights need attention
    during this period" rather than "how many happen to have a checkpoint
    inside it".

    Args:
        projected: Output of :func:`project_timeline`.

    Returns:
        One row per contiguous run of a category, with ``Start`` and
        ``Finish`` dates.
    """
    if projected.empty:
        return projected.copy()

    leg = ["Flight No", "Dep Date"]
    ordered = projected.sort_values(leg + ["Projected Date"]).copy()

    # A band ends where the next checkpoint begins; the last runs to departure.
    ordered["Band Finish"] = ordered.groupby(leg, sort=False)[
        "Projected Date"
    ].shift(-1)
    ordered["Band Finish"] = ordered["Band Finish"].fillna(ordered["Dep Date"])

    # Number the runs of identical category within each leg.
    changed = ordered["Risk Category"].ne(
        ordered.groupby(leg, sort=False)["Risk Category"].shift()
    )
    ordered["Run"] = changed.groupby(
        [ordered["Flight No"], ordered["Dep Date"]], sort=False
    ).cumsum()

    bands = (
        ordered.groupby(leg + ["Run"], sort=False)
        .agg(
            Route=("Route", "first"),
            Start=("Projected Date", "min"),
            Finish=("Band Finish", "max"),
            Category=("Risk Category", "first"),
            Severity=("Severity", "first"),
        )
        .reset_index()
    )
    return bands


def _legs_in_window(
    bands: pd.DataFrame, start_day: int, end_day: int, categories: list[str]
) -> int:
    """Count distinct legs holding any of ``categories`` during a window.

    Args:
        bands: Output of :func:`category_bands`.
        start_day: Window start, in days from the snapshot date.
        end_day: Window end, inclusive, in days from the snapshot date.
        categories: Categories that count as needing attention.

    Returns:
        Number of distinct flight legs.
    """
    if bands.empty:
        return 0
    start = SNAPSHOT_DATE + pd.Timedelta(days=start_day)
    end = SNAPSHOT_DATE + pd.Timedelta(days=end_day)
    overlapping = bands[
        bands["Category"].isin(categories)
        & (bands["Start"] <= end)
        & (bands["Finish"] >= start)
    ]
    return overlapping.groupby(["Flight No", "Dep Date"]).ngroups


def entries_table(entries: pd.DataFrame) -> pd.DataFrame:
    """Shape escalations into the columns the section tables display.

    Args:
        entries: Rows from :func:`category_entries`.

    Returns:
        A display frame, soonest escalation first.
    """
    table = pd.DataFrame(
        {
            "Priority": entries["Risk Category"].map(theme.CATEGORY_ICONS),
            "Flight No": entries["Flight No"],
            "Route": entries["Route"],
            "Dep Date": entries["Dep Date"].dt.date,
            "Projected risk date": entries["Projected Date"].dt.date,
            "Days from now": entries["Days From Now"],
            "Category": entries["Risk Category"],
            "From": entries["Previous Category"],
            "Projected Total BSF": entries["Total BSF"],
        }
    )
    return table.sort_values(["Projected risk date", "Category"]).reset_index(
        drop=True
    )


def _render_section(title: str, window: str, entries: pd.DataFrame) -> None:
    """Draw one horizon section: per-category counts and a table.

    Args:
        title: Section heading.
        window: Human-readable date range.
        entries: Escalations falling inside the window.
    """
    st.markdown(f"#### {title}")
    st.caption(window)

    if entries.empty:
        st.markdown(
            utils.empty_state("No flights escalate in this window."),
            unsafe_allow_html=True,
        )
        return

    counts = entries["Risk Category"].value_counts()
    columns = st.columns(len(ELEVATED))
    for column, category in zip(columns, ELEVATED):
        column.markdown(
            f"<div style='font-size:0.9rem;'>"
            f"{theme.CATEGORY_ICONS[category]} <strong>"
            f"{int(counts.get(category, 0))}</strong> entering {category}"
            f"</div>",
            unsafe_allow_html=True,
        )

    table = entries_table(entries)
    st.dataframe(
        table.style.format({"Projected Total BSF": "{:.1%}"}),
        width="stretch",
        hide_index=True,
        column_config={
            "Priority": st.column_config.TextColumn("", width="small"),
            "From": st.column_config.TextColumn("From"),
        },
    )


def _render_workload_cards(bands: pd.DataFrame) -> None:
    """Draw the three disjoint workload summary cards.

    Counts flights *holding* a category during each window, not flights
    escalating into one. A flight already RED today still needs working this
    week, so excluding it would understate the workload.

    Args:
        bands: Output of :func:`category_bands`.
    """
    cards = []
    for label, start, end, categories, caption, accent, value_color in (
        WORKLOAD_BUCKETS
    ):
        count = _legs_in_window(bands, start, end, categories)
        first = SNAPSHOT_DATE + pd.Timedelta(days=start)
        last = SNAPSHOT_DATE + pd.Timedelta(days=end)
        window = f"{first:%b %d} – {last:%b %d}"
        cards.append(
            kpi_cards.card(
                label,
                f"{count:,}",
                caption,
                accent=accent,
                value_color=value_color,
                trend=(
                    "<div class='ek-kpi-trend' style='color:#7A7A7A;'>"
                    f"{' or '.join(categories)} during {window}</div>"
                ),
            )
        )

    for column, html in zip(st.columns(len(cards)), cards):
        column.markdown(html, unsafe_allow_html=True)


def _render_gantt(bands: pd.DataFrame) -> None:
    """Draw the Gantt chart of projected category bands over time.

    Args:
        bands: Output of :func:`category_bands`.
    """
    st.markdown("#### Projected risk bands by flight")

    # Rank legs by the worst category they ever reach, then by how soon.
    elevated = bands[bands["Category"].isin(ELEVATED)]
    if elevated.empty:
        st.markdown(
            utils.empty_state(
                "No flights reach an elevated category, so there is nothing "
                "to plot."
            ),
            unsafe_allow_html=True,
        )
        return

    ranking = (
        elevated.groupby(["Flight No", "Dep Date"])
        .agg(Worst=("Severity", "max"), Soonest=("Start", "min"))
        .reset_index()
        .sort_values(["Worst", "Soonest"], ascending=[False, True])
    )

    st.caption("Most severe, then soonest, first.")
    limit = st.slider(
        "Flights to show",
        min_value=5,
        max_value=min(GANTT_MAX_ROWS, len(ranking)),
        value=min(GANTT_DEFAULT_ROWS, len(ranking)),
        key="timeline_gantt_rows",
    )
    chosen = ranking.head(limit)[["Flight No", "Dep Date"]]

    segments = bands.merge(chosen, on=["Flight No", "Dep Date"], how="inner").copy()
    segments["Flight"] = segments["Flight No"] + " · " + segments[
        "Dep Date"
    ].dt.strftime("%d %b")
    # Plotly needs a non-zero span to draw a bar.
    same_day = segments["Finish"] == segments["Start"]
    segments.loc[same_day, "Finish"] = segments.loc[
        same_day, "Finish"
    ] + pd.Timedelta(days=1)

    order = (
        segments.sort_values("Dep Date", ascending=False)["Flight"]
        .drop_duplicates()
        .tolist()
    )
    figure = px.timeline(
        segments,
        x_start="Start",
        x_end="Finish",
        y="Flight",
        color="Category",
        color_discrete_map=theme.CATEGORY_COLORS,
        category_orders={
            "Flight": order,
            "Category": risk_scoring.CATEGORIES,
        },
        hover_data={"Start": "|%d %b %Y", "Finish": "|%d %b %Y"},
    )
    figure.update_yaxes(title="")
    figure.update_xaxes(title="Projected date")
    figure.add_vline(
        x=SNAPSHOT_DATE,
        line_width=2,
        line_dash="dot",
        line_color=theme.CHARCOAL,
        annotation_text="today",
    )
    figure.update_layout(
        **theme.plotly_layout(height=max(320, 26 * len(order) + 140))
    )
    st.plotly_chart(figure, width="stretch")


def render(current: pd.DataFrame) -> None:
    """Draw the Alert Timeline tab.

    Args:
        current: Filtered, scored open legs making up the current view.
    """
    if current.empty:
        st.markdown(utils.empty_state(), unsafe_allow_html=True)
        return

    projected = project_timeline(current)
    entries = category_entries(projected)
    bands = category_bands(projected)

    st.markdown(
        f"Projected escalations for **{len(current):,} flights**, from each "
        "flight's current bookings toward its forecast at departure. "
        "Dates are earliest-plausible, not guaranteed."
    )
    checkpoints = ", ".join(str(d) for d in sorted(CHECKPOINTS, reverse=True))
    with st.expander("How these dates are calculated"):
        st.markdown(
            f"""
            The dataset holds no observations after the snapshot date, so
            future risk is **modelled, not measured**. For each flight the
            booking build-up is interpolated linearly between its latest
            observed per-cabin BSF and the dataset's own forecast BSF at
            departure, evaluated at the remaining snapshot checkpoints
            ({checkpoints} days out). Those
            per-cabin figures are recombined into a capacity-weighted total
            and run through the same RED/ORANGE/YELLOW rules used everywhere
            else in the dashboard.

            Real booking curves are convex, accelerating towards departure,
            so a linear path reaches each threshold no earlier than reality
            would. Read a projected date as "no sooner than this".

            A flight's forecast total does not vary by checkpoint, so YELLOW
            is effectively fixed per flight; the dates that move are ORANGE
            and RED.
            """
        )

    _render_workload_cards(bands)
    st.write("")

    _render_gantt(bands)
    st.divider()

    st.markdown("### Escalations by horizon")
    st.caption(
        "The first three horizons are cumulative, as specified — "
        "“Next 14 Days” includes the next 7."
    )
    for title, days in HORIZONS:
        end = SNAPSHOT_DATE + pd.Timedelta(days=days)
        _render_section(
            title,
            f"{SNAPSHOT_DATE:%b %d} – {end:%b %d, %Y}",
            entries[entries["Days From Now"].between(0, days)],
        )
        st.write("")

    beyond_start = SNAPSHOT_DATE + pd.Timedelta(days=HORIZONS[-1][1])
    _render_section(
        f"Beyond {HORIZONS[-1][1]} Days",
        f"After {beyond_start:%b %d, %Y}",
        entries[entries["Days From Now"] > HORIZONS[-1][1]],
    )

    st.divider()
    st.caption("Export covers all projected escalations for the filtered flights.")
    st.download_button(
        "Export timeline CSV",
        data=utils.to_csv_bytes(entries_table(entries)),
        file_name="alert_timeline.csv",
        mime="text/csv",
        type="secondary",
    )
