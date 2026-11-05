"""Tab 1 — the ranked flight table (specification section 6, Tab 1).

The analyst's primary work queue: every filtered flight ordered by risk score,
with the BSF cells colour-coded so problems are visible without reading
numbers. Selecting a row opens a detail panel explaining that flight's score.
"""

from __future__ import annotations

import math
from typing import Final

import pandas as pd
import streamlit as st

import approved_peaks
import ml_pipeline
import risk_scoring
import utils
from components import recommendations
from styling import theme

#: Rows per page. The spec asks for pagination beyond 50 rows.
PAGE_SIZE: Final[int] = 50

#: Default widget-key namespace. The Replay tab renders a second instance of
#: this table, so every widget key is derived from a prefix.
KEY_PREFIX: Final[str] = "overview"

#: Session keys shared with the drill-down and per-flight tabs.
DRILLDOWN_FLIGHT_KEY: Final[str] = "drilldown_flight"
DRILLDOWN_DATE_KEY: Final[str] = "drilldown_date"

#: Set by Today's Priorities to open this flight's detail panel.
FOCUS_KEY: Final[str] = "overview_focus_leg"
FOCUS_PAGED_KEY: Final[str] = "overview_focus_paged"

#: Table columns in the order the specification lists them.
DISPLAY_COLUMNS: Final[list[str]] = [
    "Priority",
    "Risk Score",
    "ML Confidence",
    "Flight No",
    "Route",
    "Dep Date",
    "Dep Time",
    "DOW",
    "Days to Dep",
    "F BSF",
    "J BSF",
    "Y BSF",
    "Total BSF",
    "Fcst Total BSF",
    "Pax at Risk",
    "BSF vLY",
    "Period",
]

#: Cells that get the red/orange/green load-factor colouring.
_COLOURED_BSF: Final[list[str]] = [
    "F BSF",
    "J BSF",
    "Y BSF",
    "Total BSF",
    "Fcst Total BSF",
]

_PERCENT_COLUMNS: Final[list[str]] = [
    "F BSF",
    "J BSF",
    "Y BSF",
    "Total BSF",
    "Fcst Total BSF",
]


def _format_vly(value: object) -> str:
    """Format BSF vLY with a direction arrow for the Overview table.

    Near-zero moves (|Δ| ≤ 0.1 percentage points) use a flat marker so they
    are not coloured as a gain or a drop.
    """
    if value is None or pd.isna(value):
        return "–"
    number = float(value)
    if abs(number) <= theme.VLY_NEAR_ZERO:
        return f"▬ {number * 100:+.1f}%"
    arrow = "▲" if number > 0 else "▼"
    return f"{arrow} {number * 100:+.1f}%"


def _vly_css(value: object) -> str:
    """Colour BSF vLY text: green up, red down, charcoal when flat."""
    if not isinstance(value, str) or value in {"", "–"}:
        return f"color: {theme.VLY_FLAT};"
    if value.startswith("▲"):
        return f"color: {theme.VLY_UP}; font-weight: 600;"
    if value.startswith("▼"):
        return f"color: {theme.VLY_DOWN}; font-weight: 600;"
    return f"color: {theme.VLY_FLAT}; font-weight: 600;"


def _build_display_frame(ranked: pd.DataFrame) -> pd.DataFrame:
    """Shape scored flights into the table's display columns.

    Args:
        ranked: Flights already ordered by ``risk_scoring.rank_by_risk``.

    Returns:
        Frame containing exactly :data:`DISPLAY_COLUMNS`, values still numeric
        so the table sorts correctly when headers are clicked.
    """
    table = ranked.copy()
    icons = table["Risk Category"].map(theme.CATEGORY_ICONS).fillna("").astype(str)
    table["Priority"] = icons
    if ml_pipeline.ML_DISAGREE_COL in table.columns:
        disagree = table[ml_pipeline.ML_DISAGREE_COL].fillna(False).astype(bool)
        table.loc[disagree, "Priority"] = (
            table.loc[disagree, "Priority"] + f" {ml_pipeline.ML_DISAGREE_ICON}"
        )
    if "Underperforming vs LY" in table.columns:
        flagged = table["Underperforming vs LY"].fillna(False).astype(bool)
        table.loc[flagged, "Priority"] = (
            table.loc[flagged, "Priority"] + f" {risk_scoring.BLACK_FLAG_ICON}"
        )
    if ml_pipeline.ML_CONFIDENCE_COL in table.columns:
        table["ML Confidence"] = table[ml_pipeline.ML_CONFIDENCE_COL]
    else:
        table["ML Confidence"] = pd.NA
    # Real days left, not the snapshot grid position the workbook stores.
    table["Days to Dep"] = table[risk_scoring.DTD_COLUMN]
    peaks = approved_peaks.load_approved_peaks()
    table["Period"] = table.apply(
        lambda row: approved_peaks.display_period(row, peaks), axis=1
    )
    table["DOW"] = table["DOW Label"]
    # Blank rather than 0 or "None" for non-RED flights: they have nobody
    # at risk yet. Converted to text here so Streamlit cannot stringify NA.
    table["Pax at Risk"] = table["Pax at Risk"].map(
        lambda v: "" if pd.isna(v) else f"{int(v)}"
    )
    # Pre-format so a missing comparison renders as "–", not Streamlit's "None".
    table["BSF vLY"] = table["BSF vLY"].map(_format_vly)
    return table[DISPLAY_COLUMNS]


def _style(table: pd.DataFrame) -> "pd.io.formats.style.Styler":
    """Apply number formatting and load-factor colouring.

    Args:
        table: Display frame from :func:`_build_display_frame`.

    Returns:
        Styler ready to hand to ``st.dataframe``.
    """
    formats: dict[str, object] = {col: "{:.1%}" for col in _PERCENT_COLUMNS}
    formats["Risk Score"] = lambda v: "–" if pd.isna(v) else f"{v:.0f}"
    formats["ML Confidence"] = (
        lambda v: "–" if pd.isna(v) else f"{float(v):.1%}"
    )
    formats["Dep Date"] = lambda d: pd.Timestamp(d).strftime("%Y-%m-%d")

    styler = table.style.format(formats)
    styler = utils.style_bsf_columns(styler, _COLOURED_BSF)
    if "BSF vLY" in table.columns:
        styler = styler.map(_vly_css, subset=["BSF vLY"])
    return styler


def _paginate(
    table: pd.DataFrame, key_prefix: str
) -> tuple[pd.DataFrame, int, int]:
    """Slice the table to the currently selected page.

    Args:
        table: The full display frame.
        key_prefix: Widget-key namespace for this table instance.

    Returns:
        The visible rows, the 1-based page number, and the total page count.
    """
    page_key = f"{key_prefix}_page"
    total_pages = max(1, math.ceil(len(table) / PAGE_SIZE))
    # Clamp, because a tightened filter can leave the stored page out of range.
    page = min(int(st.session_state.get(page_key, 1)), total_pages)

    if total_pages > 1:
        controls = st.columns([1, 3])
        page = controls[0].number_input(
            "Page",
            min_value=1,
            max_value=total_pages,
            value=page,
            step=1,
            key=page_key,
        )
        first = (page - 1) * PAGE_SIZE + 1
        last = min(page * PAGE_SIZE, len(table))
        controls[1].caption(
            f"Showing flights {first:,}–{last:,} of {len(table):,} "
            f"(page {page} of {total_pages})"
        )

    start = (page - 1) * PAGE_SIZE
    return table.iloc[start : start + PAGE_SIZE], page, total_pages


def _render_detail(flight: pd.Series, key_prefix: str) -> None:
    """Draw the detail panel for the selected row.

    Args:
        flight: The selected scored flight.
        key_prefix: Widget-key namespace for this table instance.
    """
    category = flight.get("Risk Category", risk_scoring.NO_CATEGORY)
    icon = theme.CATEGORY_ICONS.get(category, "")
    raw_flag = flight.get("Underperforming vs LY", False)
    flagged = False if pd.isna(raw_flag) else bool(raw_flag)
    flag = f" {risk_scoring.BLACK_FLAG_ICON}" if flagged else ""
    st.markdown(f"#### {icon}{flag} {utils.flight_label(flight)}")

    # BSF is shown as the metric label rather than a tooltip: the Help & Guide
    # tab is the single place explanations live, so nothing hides on hover.
    cabin_columns = st.columns(4)
    for column, cabin in zip(cabin_columns, ("F", "J", "Y")):
        booked = int(flight[f"{cabin} Bkg"])
        capacity = int(flight[f"{cabin} Cap"])
        over = booked - capacity
        column.metric(
            f"{cabin} cabin · {utils.format_pct(flight[f'{cabin} BSF'])}",
            f"{booked} / {capacity}",
            delta=f"{over:+d} seats" if over else None,
            delta_color="inverse",
        )
    cabin_columns[3].metric(
        f"Total · {utils.format_pct(flight['Total BSF'])}",
        f"{int(flight['Total Bkg'])} / {int(flight['Total Cap'])}",
    )

    info_columns = st.columns(4)
    info_columns[0].metric("Risk score", f"{flight['Risk Score']:.0f}")
    info_columns[1].metric(
        "Fcst total BSF", utils.format_pct(flight["Fcst Total BSF"])
    )
    info_columns[2].metric("Day of week", flight["DOW Label"])
    info_columns[3].metric("vs last year", utils.format_signed_pct(flight["BSF vLY"]))

    disagree = bool(flight.get(ml_pipeline.ML_DISAGREE_COL, False))
    if disagree:
        ml_category = flight.get(ml_pipeline.ML_CATEGORY_COL, "—")
        confidence = flight.get(ml_pipeline.ML_CONFIDENCE_COL)
        confidence_text = (
            "—" if pd.isna(confidence) else f"{float(confidence):.1%}"
        )
        st.markdown(
            "<div class='ek-ml-note'>"
            f"<strong>Rule Category:</strong> {category} &nbsp;·&nbsp; "
            f"<strong>ML Category:</strong> {ml_category} &nbsp;·&nbsp; "
            f"<strong>ML Confidence:</strong> {confidence_text}"
            "<br/>The ML classifier produced a different categorization than "
            "the rule-based model. This flight may represent an edge case "
            "worth reviewing."
            "</div>",
            unsafe_allow_html=True,
        )

    st.markdown("**Recommended action**")
    recommendations.render(flight)

    if flagged and pd.notna(flight.get("BSF vLY")):
        points = abs(float(flight["BSF vLY"]) * 100)
        st.markdown(
            f"{risk_scoring.BLACK_FLAG_ICON} This flight is **{points:.1f}** "
            "percentage points below last year's BSF for the same date. "
            "Investigate: pricing, competition, market demand, or scheduling "
            "changes."
        )

    st.markdown("**Why this score**")
    for line in risk_scoring.score_breakdown(flight):
        st.markdown(f"- {line}")


def render(
    ranked: pd.DataFrame,
    key_prefix: str = KEY_PREFIX,
    *,
    caption: str | None = None,
    export_name: str = "flight_priorities.csv",
) -> None:
    """Draw the ranked flight table and its detail panel.

    Rendered twice: once as the Overview tab, and once by the Replay tab
    showing the same table as it stood on a past date. Every widget key is
    namespaced so the two instances hold independent page and row selections.

    Args:
        ranked: Filtered flights ordered by ``risk_scoring.rank_by_risk``.
        key_prefix: Widget-key namespace for this table instance.
        caption: Replaces the default line above the table.
        export_name: File name offered by the export button.
    """
    if ranked.empty:
        st.markdown(utils.empty_state(), unsafe_allow_html=True)
        return

    header = st.columns([4, 1])
    header[0].markdown(
        caption
        or (
            f"**{len(ranked):,} flights** ranked by risk score. "
            "Click a row for details; click a column header to re-sort. "
            "Export covers every filtered flight, not just this page."
        )
    )
    header[1].download_button(
        "Export CSV",
        data=utils.to_csv_bytes(_build_display_frame(ranked)),
        file_name=export_name,
        mime="text/csv",
        width="stretch",
        type="secondary",
        key=f"{key_prefix}_export",
    )

    table = _build_display_frame(ranked)
    focus_index: int | None = None
    if key_prefix == KEY_PREFIX:
        focus = st.session_state.get(FOCUS_KEY)
        if focus:
            flight_no, dep_date = focus
            match = (ranked["Flight No"] == flight_no) & (
                ranked["Dep Date"] == pd.Timestamp(dep_date)
            )
            if match.any():
                focus_index = int(match.to_numpy().nonzero()[0][0])
                if not st.session_state.get(FOCUS_PAGED_KEY):
                    st.session_state[f"{key_prefix}_page"] = (
                        focus_index // PAGE_SIZE + 1
                    )
                    st.session_state[FOCUS_PAGED_KEY] = True

    page_rows, page, _ = _paginate(table, key_prefix)

    event = st.dataframe(
        _style(page_rows),
        width="stretch",
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
        key=f"{key_prefix}_selection",
        # No column tooltips by design — every definition lives in the
        # Help & Guide tab so nothing is hidden behind a hover.
        column_config={
            "Priority": st.column_config.TextColumn("Risk", width="medium"),
            "Risk Score": st.column_config.NumberColumn("Score"),
            "ML Confidence": st.column_config.TextColumn(
                "ML Confidence", width="small"
            ),
            "DOW": st.column_config.TextColumn("DOW", width="small"),
            "Pax at Risk": st.column_config.TextColumn(
                "Pax at Risk", width="small"
            ),
            "BSF vLY": st.column_config.TextColumn("BSF vLY"),
        },
    )

    selected_rows = event.selection.rows if event and event.selection else []
    if selected_rows:
        if key_prefix == KEY_PREFIX:
            st.session_state.pop(FOCUS_KEY, None)
            st.session_state.pop(FOCUS_PAGED_KEY, None)
        absolute_index = (page - 1) * PAGE_SIZE + selected_rows[0]
    elif focus_index is not None:
        absolute_index = focus_index
    else:
        st.caption("Select a row above to see that flight's details.")
        return

    with st.container(border=True):
        _render_detail(ranked.iloc[absolute_index], key_prefix)
