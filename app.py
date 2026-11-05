"""Real-Time Decision Support Dashboard — flight prioritization for analysts.

Entry point. Run with:

    python -m streamlit run app.py

"""

from __future__ import annotations

from typing import Final

import pandas as pd
import streamlit as st

import ml_pipeline
import ml_runtime
import risk_scoring
import utils
from data_loader import (
    SNAPSHOT_DATE,
    filter_options,
    latest_snapshots,
    load_flights,
    snapshots_as_of,
)
from components import (
    filters,
    flight_analysis,
    help_guide,
    kpi_cards,
    overview_status,
    overview_table,
    peak_detection,
    replay,
)
from styling import theme

PAGE_TITLE: Final[str] = "Flight Prioritization Dashboard"
PAGE_ICON: Final[str] = "✈"

#: Canonical tab names, in display order.
TAB_NAMES: Final[list[str]] = [
    "Overview",
    "Flight Analysis",
    "Peak Detection",
    "Replay",
    "Help & Guide",
]


def render_header(as_of: pd.Timestamp) -> None:
    """Draw the branded header bar.

    Args:
        as_of: The date the analyst is viewing the system as of.
    """
    st.markdown(
        f"""
        <div class="ek-header">
          <div class="ek-header-title">{PAGE_ICON}&nbsp; {PAGE_TITLE}</div>
          <div class="ek-header-date">As of: {as_of.strftime('%b %d, %Y')}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def main() -> None:
    """Configure the page and render the dashboard."""
    st.set_page_config(
        page_title=PAGE_TITLE,
        page_icon=PAGE_ICON,
        layout="wide",
        initial_sidebar_state="expanded",
    )
    st.markdown(theme.global_css(), unsafe_allow_html=True)  # KPI row CSS lives in the theme.
    render_header(SNAPSHOT_DATE)

    flights_raw = load_flights()
    options = filter_options(flights_raw)
    state = filters.render_sidebar(options)

    with st.spinner("Training machine learning models…"):
        forecast = ml_runtime.forecast_model(flights_raw)
        flights = ml_pipeline.apply_forecast(flights_raw, forecast)
        ml_runtime.cluster_model(flights_raw)

    with st.spinner("Scoring flights…"):
        current = risk_scoring.assign_risk(latest_snapshots(flights))
        classifier = ml_runtime.classifier_model(current)
        current = ml_pipeline.apply_classifier(current, classifier)
        visible = filters.apply_filters(current, state)

        # Same filters a week ago, so the KPI cards can show a direction.
        lookback = SNAPSHOT_DATE - pd.Timedelta(days=kpi_cards.TREND_LOOKBACK_DAYS)
        previous = filters.apply_filters(
            risk_scoring.assign_risk(snapshots_as_of(flights, lookback)), state
        )

    if visible.empty:
        st.markdown(
            utils.empty_state(
                "No flights match your filters. Active filters: "
                + "; ".join(filters.active_filter_summary(state))
                + "."
            ),
            unsafe_allow_html=True,
        )
        # The guide must stay reachable even when nothing matches — a filter
        # combination that returns nothing is exactly when it gets consulted.
        with st.expander("Help & Guide"):
            help_guide.render(ml_metrics=ml_runtime.help_metrics())
        return

    ranked = risk_scoring.rank_by_risk(visible)
    # The per-flight tabs open on the flight that most needs attention,
    # unless the analyst handed one over from the Overview tab.
    top_flight = (
        ranked.iloc[0]["Flight No"],
        pd.Timestamp(ranked.iloc[0]["Dep Date"]).date(),
    )
    tabs = st.tabs(TAB_NAMES)

    with tabs[0]:
        overview_status.render(ranked, previous, forecast=forecast)
        overview_table.render(ranked)

    with tabs[TAB_NAMES.index("Flight Analysis")]:
        flight_analysis.render(flights, suggested=top_flight, state=state)

    with tabs[TAB_NAMES.index("Peak Detection")]:
        peak_detection.render(flights)

    with tabs[TAB_NAMES.index("Replay")]:
        replay.render(flights, state)

    with tabs[TAB_NAMES.index("Help & Guide")]:
        help_guide.render(ml_metrics=ml_runtime.help_metrics())


if __name__ == "__main__":
    main()
