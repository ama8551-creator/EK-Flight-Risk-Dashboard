"""Overview-only status chrome: the critical-flight banner and summary line.

The Overview tab reads as banner → cards → Today's Priorities →
one-sentence briefing → ranked table. Nothing here is shown on any other tab.
"""

from __future__ import annotations

from typing import Final

import pandas as pd
import streamlit as st

import ml_pipeline
import risk_scoring
from components import kpi_cards, priorities

#: Session key for the dismissible banner. Cleared on a full page refresh.
DISMISS_KEY: Final[str] = "overview_alert_dismissed"


def _join(parts: list[str]) -> str:
    """Join clause fragments with an Oxford comma.

    Args:
        parts: Clauses already phrased, in display order.

    Returns:
        A single sentence body, without a trailing full stop.
    """
    if len(parts) == 1:
        return parts[0]
    if len(parts) == 2:
        return f"{parts[0]}, and {parts[1]}"
    return f"{parts[0]}, {parts[1]}, and {parts[2]}"


def summary_sentence(red: int, orange: int, yellow: int) -> str:
    """Build the one-line briefing from the three elevated counts.

    Args:
        red: RED flights in the current filtered view.
        orange: ORANGE flights in the current filtered view.
        yellow: YELLOW flights in the current filtered view.

    Returns:
        A complete sentence. Zero counts are dropped rather than spoken.
    """
    if red == 0 and orange == 0 and yellow == 0:
        return "All visible flights are operating within expected parameters."

    parts: list[str] = []
    if red:
        parts.append(
            "1 flight needs immediate action"
            if red == 1
            else f"{red} flights need immediate action"
        )
    if orange:
        parts.append(
            "1 flight to monitor over the next 45 days"
            if orange == 1
            else f"{orange} flights to monitor over the next 45 days"
        )
    if yellow:
        parts.append(
            "1 flight trending toward overbooking by departure"
            if yellow == 1
            else f"{yellow} flights trending toward overbooking by departure"
        )

    body = _join(parts)
    if red == 0:
        return f"No flights need immediate action. {body}."
    return f"{body}."


def _dismiss() -> None:
    """Hide the banner for the rest of this session."""
    st.session_state[DISMISS_KEY] = True


def _render_banner(red: int) -> None:
    """Draw the dismissible critical-flight banner.

    Args:
        red: RED flights in the current filtered view.
    """
    if red <= 0 or st.session_state.get(DISMISS_KEY):
        return

    verb = "requires" if red == 1 else "require"
    noun = "flight" if red == 1 else "flights"
    message = (
        f"⚠️ {red} {noun} {verb} immediate action — denied boarding "
        "risk. See table below for details."
    )

    text, close = st.columns([18, 1], vertical_alignment="center")
    text.markdown(
        f"<div class='ek-alert-banner'>{message}</div>",
        unsafe_allow_html=True,
    )
    close.button(
        "×",
        on_click=_dismiss,
        key="overview_alert_dismiss",
        type="primary",
        width="stretch",
    )


def _render_summary(red: int, orange: int, yellow: int) -> None:
    """Draw the cream briefing box under the KPI cards.

    Args:
        red: RED count.
        orange: ORANGE count.
        yellow: YELLOW count.
    """
    st.markdown(
        f"<div class='ek-overview-summary'>{summary_sentence(red, orange, yellow)}</div>",
        unsafe_allow_html=True,
    )


def render(
    ranked: pd.DataFrame,
    previous: pd.DataFrame | None = None,
    forecast: ml_pipeline.ForecastBundle | None = None,
) -> None:
    """Draw banner, KPI cards and summary for the Overview tab.

    Args:
        ranked: Filtered, scored flights in the current view.
        previous: The same filters a week earlier, for KPI trend arrows.
        forecast: Trained Random Forest used for Fcst Total BSF, if available.
    """
    counts = risk_scoring.category_counts(ranked)
    red = counts[risk_scoring.RED]
    orange = counts[risk_scoring.ORANGE]
    yellow = counts[risk_scoring.YELLOW]

    _render_banner(red)
    kpi_cards.render(ranked, previous)
    if forecast is not None:
        st.caption(
            f"Forecast values predicted by Random Forest "
            f"(Test R²: {forecast.r2:.3f}, MAE: {forecast.mae:.3f})"
        )
    priorities.render(ranked)
    _render_summary(red, orange, yellow)
    st.write("")
