"""Session-level cache for the dashboard's machine-learning models.

Training is relatively expensive, so each bundle is stored on
``st.session_state`` and reused for the rest of the browser session.
"""

from __future__ import annotations

from typing import Final

import pandas as pd
import streamlit as st

import ml_pipeline

FORECAST_KEY: Final[str] = "ml_forecast_bundle"
CLASSIFIER_KEY: Final[str] = "ml_classifier_bundle"
CLUSTER_KEY: Final[str] = "ml_cluster_bundle"


def forecast_model(flights: pd.DataFrame) -> ml_pipeline.ForecastBundle | None:
    """Return the session's Random Forest, training it on first use."""
    if FORECAST_KEY not in st.session_state:
        st.session_state[FORECAST_KEY] = ml_pipeline.train_forecast(flights)
    return st.session_state[FORECAST_KEY]


def classifier_model(scored: pd.DataFrame) -> ml_pipeline.ClassifierBundle | None:
    """Return the session's Decision Tree, training it on first use."""
    if CLASSIFIER_KEY not in st.session_state:
        st.session_state[CLASSIFIER_KEY] = ml_pipeline.train_classifier(scored)
    return st.session_state[CLASSIFIER_KEY]


def cluster_model(flights: pd.DataFrame) -> ml_pipeline.ClusterBundle:
    """Return K-Means metrics on flown history, clustering on first use.

    Peak Detection overwrites this key after a filtered Detect Peaks run so
    Help & Guide shows the clustering currently in view.
    """
    if CLUSTER_KEY not in st.session_state:
        st.session_state[CLUSTER_KEY] = ml_pipeline.cluster_flown_history(flights)
    return st.session_state[CLUSTER_KEY]


def store_cluster(bundle: ml_pipeline.ClusterBundle) -> None:
    """Keep the latest Peak Detection clustering as the current result."""
    st.session_state[CLUSTER_KEY] = bundle


def help_metrics() -> dict:
    """Live model metrics for the Help & Guide accordion."""
    return ml_pipeline.metrics_for_help(
        st.session_state.get(CLUSTER_KEY),
        st.session_state.get(FORECAST_KEY),
        st.session_state.get(CLASSIFIER_KEY),
    )
