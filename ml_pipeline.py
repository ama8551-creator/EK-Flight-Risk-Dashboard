"""Machine-learning models that support Peak Detection, forecast BSF, and risk.

Three techniques, trained from the loaded flight workbook:

1. K-Means (3 clusters) on week-direction BSF features, to find peak weeks.
2. Random Forest regression to predict Total BSF at departure.
3. Decision Tree classification as a secondary check on rule-based categories.

This module has no Streamlit imports. Session caching lives in ``ml_runtime``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Final

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.metrics import (
    accuracy_score,
    mean_absolute_error,
    r2_score,
    silhouette_score,
)
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder, StandardScaler
from sklearn.ensemble import RandomForestRegressor
from sklearn.tree import DecisionTreeClassifier

from data_loader import STATUS_FLOWN, STATUS_OPEN

CLUSTER_FEATURES: Final[tuple[str, ...]] = (
    "avg_total_bsf",
    "std_total_bsf",
    "max_total_bsf",
    "avg_y_bsf",
    "avg_j_bsf",
)
CLUSTER_LABELS: Final[tuple[str, ...]] = ("Peak", "Shoulder", "Off-Peak")
N_CLUSTERS: Final[int] = 3
KMEANS_RANDOM_STATE: Final[int] = 42
KMEANS_N_INIT: Final[int] = 10

FORECAST_FEATURES: Final[tuple[str, ...]] = (
    "F BSF",
    "J BSF",
    "Y BSF",
    "Total BSF",
    "Days to Departure",
    "DOW",
    "Direction",
)
FORECAST_MIN_DTD: Final[int] = 14
FORECAST_TARGET: Final[str] = "Fcst Total BSF"

CLASSIFIER_FEATURES: Final[tuple[str, ...]] = (
    "F BSF",
    "J BSF",
    "Y BSF",
    "Total BSF",
    "Fcst Total BSF",
    "Actual DTD",
)
CLASSIFIER_TARGET: Final[str] = "Risk Category"

ML_CATEGORY_COL: Final[str] = "ML Category"
ML_CONFIDENCE_COL: Final[str] = "ML Confidence"
ML_DISAGREE_COL: Final[str] = "ML Disagreement"
ML_DISAGREE_ICON: Final[str] = "⚠"

TEST_SIZE: Final[float] = 0.20
SPLIT_RANDOM_STATE: Final[int] = 42


@dataclass
class ClusterBundle:
    """K-Means result on week-direction aggregates."""

    silhouette: float
    sizes: dict[str, int]
    n_weeks: int
    labels: pd.DataFrame = field(default_factory=pd.DataFrame)


@dataclass
class ForecastBundle:
    """Trained Random Forest regressor and its hold-out metrics."""

    model: RandomForestRegressor
    encoder: LabelEncoder
    n_train: int
    n_test: int
    mae: float
    r2: float
    importances: list[tuple[str, float]]


@dataclass
class ClassifierBundle:
    """Trained Decision Tree and its hold-out metrics."""

    model: DecisionTreeClassifier
    n_train: int
    n_test: int
    accuracy: float
    importances: list[tuple[str, float]]
    classes: tuple[str, ...]


def _importance_pairs(names: tuple[str, ...], values: np.ndarray) -> list[tuple[str, float]]:
    """Sort feature importances high to low."""
    ranked = sorted(
        zip(names, (float(v) for v in values)),
        key=lambda item: item[1],
        reverse=True,
    )
    return list(ranked)


def aggregate_week_directions(fln: pd.DataFrame) -> pd.DataFrame:
    """One row per ISO week and direction, with clustering features.

    Args:
        fln: Flown snapshot rows.

    Returns:
        Feature table with ``direction``, ``iso_year``, ``iso_week`` plus
        :data:`CLUSTER_FEATURES`. Empty when ``fln`` is empty.
    """
    if fln.empty:
        return pd.DataFrame(
            columns=["direction", "iso_year", "iso_week", *CLUSTER_FEATURES]
        )
    tagged = fln.copy()
    iso = tagged["Dep Date"].dt.isocalendar()
    tagged["iso_year"] = iso.year.astype(int)
    tagged["iso_week"] = iso.week.astype(int)
    grouped = tagged.groupby(["Route", "iso_year", "iso_week"], sort=True)
    rows: list[dict[str, Any]] = []
    for (direction, year, week), part in grouped:
        total = part["Total BSF"]
        rows.append(
            {
                "direction": direction,
                "iso_year": int(year),
                "iso_week": int(week),
                "avg_total_bsf": float(total.mean()),
                "std_total_bsf": float(total.std(ddof=0)) if len(part) else 0.0,
                "max_total_bsf": float(total.max()),
                "avg_y_bsf": float(part["Y BSF"].mean()),
                "avg_j_bsf": float(part["J BSF"].mean()),
            }
        )
    return pd.DataFrame(rows)


def cluster_week_directions(fln: pd.DataFrame) -> ClusterBundle:
    """Standardize week-direction features and fit 3-cluster K-Means.

    Clusters are labelled by mean ``avg_total_bsf``: highest Peak, middle
    Shoulder, lowest Off-Peak.

    Args:
        fln: Flown snapshot rows to aggregate.

    Returns:
        Labels plus silhouette score and cluster sizes.
    """
    empty_sizes = {name: 0 for name in CLUSTER_LABELS}
    weeks = aggregate_week_directions(fln)
    if len(weeks) < N_CLUSTERS:
        return ClusterBundle(
            silhouette=float("nan"),
            sizes=empty_sizes,
            n_weeks=len(weeks),
            labels=weeks,
        )

    matrix = weeks.loc[:, list(CLUSTER_FEATURES)].to_numpy(dtype=float)
    scaled = StandardScaler().fit_transform(matrix)
    model = KMeans(
        n_clusters=N_CLUSTERS,
        random_state=KMEANS_RANDOM_STATE,
        n_init=KMEANS_N_INIT,
    )
    raw_labels = model.fit_predict(scaled)

    means = (
        pd.Series(weeks["avg_total_bsf"].to_numpy(), index=weeks.index)
        .groupby(raw_labels)
        .mean()
    )
    ranked = list(means.sort_values(ascending=False).index)
    name_by_raw = {
        cluster_id: CLUSTER_LABELS[index]
        for index, cluster_id in enumerate(ranked)
        if index < len(CLUSTER_LABELS)
    }
    named = pd.Series(raw_labels, index=weeks.index).map(name_by_raw)
    weeks = weeks.copy()
    weeks["cluster"] = named
    weeks["cluster_id"] = raw_labels

    n_unique = int(pd.Series(raw_labels).nunique())
    if n_unique >= 2 and len(weeks) > n_unique:
        silhouette = float(silhouette_score(scaled, raw_labels))
    else:
        silhouette = float("nan")

    sizes = {
        name: int((named == name).sum()) for name in CLUSTER_LABELS
    }
    return ClusterBundle(
        silhouette=silhouette,
        sizes=sizes,
        n_weeks=len(weeks),
        labels=weeks,
    )


def cluster_flown_history(flights: pd.DataFrame) -> ClusterBundle:
    """Run K-Means on every flown row in ``flights``."""
    fln = flights[flights["Status"] == STATUS_FLOWN]
    return cluster_week_directions(fln)


def _forecast_frame(df: pd.DataFrame, encoder: LabelEncoder | None) -> tuple[pd.DataFrame, LabelEncoder]:
    """Build the Random Forest feature matrix, fitting the encoder if needed."""
    frame = df.copy()
    frame["Direction"] = frame["Route"].astype(str)
    if encoder is None:
        encoder = LabelEncoder()
        frame["Direction"] = encoder.fit_transform(frame["Direction"])
    else:
        mapping = {label: index for index, label in enumerate(encoder.classes_)}
        frame["Direction"] = (
            frame["Direction"].map(mapping).fillna(-1).astype(int)
        )
    return frame.loc[:, list(FORECAST_FEATURES)], encoder


def train_forecast(flights: pd.DataFrame) -> ForecastBundle | None:
    """Train a Random Forest on open snapshots at least 14 days from departure.

    Args:
        flights: Preprocessed workbook, including derived ``Fcst Total BSF``.

    Returns:
        The fitted bundle, or ``None`` when there is too little data.
    """
    eligible = flights[
        (flights["Status"] == STATUS_OPEN)
        & (flights["Days to Departure"] >= FORECAST_MIN_DTD)
    ].copy()
    eligible = eligible.dropna(subset=[*FORECAST_FEATURES[:-1], FORECAST_TARGET, "Route"])
    if len(eligible) < 10:
        return None

    features, encoder = _forecast_frame(eligible, encoder=None)
    target = eligible[FORECAST_TARGET].astype(float)
    x_train, x_test, y_train, y_test = train_test_split(
        features,
        target,
        test_size=TEST_SIZE,
        random_state=SPLIT_RANDOM_STATE,
    )
    model = RandomForestRegressor(
        n_estimators=100,
        max_depth=10,
        random_state=42,
        # n_jobs=1: n_jobs=-1 deadlocks joblib/loky under Streamlit and
        # Windows when the process is not a standard __main__ entry.
        n_jobs=1,
    )
    model.fit(x_train, y_train)
    predicted = model.predict(x_test)
    return ForecastBundle(
        model=model,
        encoder=encoder,
        n_train=int(len(x_train)),
        n_test=int(len(x_test)),
        mae=float(mean_absolute_error(y_test, predicted)),
        r2=float(r2_score(y_test, predicted)),
        importances=_importance_pairs(
            FORECAST_FEATURES, model.feature_importances_
        ),
    )


def apply_forecast(flights: pd.DataFrame, bundle: ForecastBundle | None) -> pd.DataFrame:
    """Replace open-flight ``Fcst Total BSF`` with Random Forest predictions.

    Args:
        flights: Preprocessed workbook (must not be a cached object to mutate).
        bundle: Result of :func:`train_forecast`.

    Returns:
        Copy of ``flights`` with predicted forecasts on open rows.
    """
    out = flights.copy()
    if bundle is None or out.empty:
        return out
    features, _ = _forecast_frame(out, bundle.encoder)
    predicted = bundle.model.predict(features)
    open_mask = out["Status"] == STATUS_OPEN
    out.loc[open_mask, FORECAST_TARGET] = pd.Series(
        predicted, index=out.index
    ).loc[open_mask]
    return out


def train_classifier(scored: pd.DataFrame) -> ClassifierBundle | None:
    """Train a Decision Tree on rule-based categories of latest open flights.

    Args:
        scored: Latest-snapshot open flights already labelled by the rules.

    Returns:
        The fitted bundle, or ``None`` when there is too little data.
    """
    eligible = scored.dropna(subset=[*CLASSIFIER_FEATURES, CLASSIFIER_TARGET]).copy()
    eligible = eligible[eligible[CLASSIFIER_TARGET].notna()]
    if CLASSIFIER_TARGET in eligible.columns:
        eligible = eligible[eligible[CLASSIFIER_TARGET] != "N/A"]
    if len(eligible) < 10:
        return None

    features = eligible.loc[:, list(CLASSIFIER_FEATURES)].astype(float)
    target = eligible[CLASSIFIER_TARGET].astype(str)
    stratify = target if target.value_counts().min() >= 2 else None
    x_train, x_test, y_train, y_test = train_test_split(
        features,
        target,
        test_size=TEST_SIZE,
        random_state=SPLIT_RANDOM_STATE,
        stratify=stratify,
    )
    model = DecisionTreeClassifier(
        max_depth=6,
        random_state=42,
        class_weight="balanced",
    )
    model.fit(x_train, y_train)
    predicted = model.predict(x_test)
    return ClassifierBundle(
        model=model,
        n_train=int(len(x_train)),
        n_test=int(len(x_test)),
        accuracy=float(accuracy_score(y_test, predicted)),
        importances=_importance_pairs(
            CLASSIFIER_FEATURES, model.feature_importances_
        ),
        classes=tuple(str(c) for c in model.classes_),
    )


def apply_classifier(
    scored: pd.DataFrame, bundle: ClassifierBundle | None
) -> pd.DataFrame:
    """Attach ML category, confidence, and a disagreement flag.

    Args:
        scored: Rows already labelled by the rule-based model.
        bundle: Result of :func:`train_classifier`.

    Returns:
        Copy of ``scored`` with :data:`ML_CATEGORY_COL`,
        :data:`ML_CONFIDENCE_COL`, and :data:`ML_DISAGREE_COL`.
    """
    out = scored.copy()
    out[ML_CATEGORY_COL] = pd.NA
    out[ML_CONFIDENCE_COL] = pd.NA
    out[ML_DISAGREE_COL] = False
    if bundle is None or out.empty:
        return out

    feature_cols = list(CLASSIFIER_FEATURES)
    usable = out[feature_cols].notna().all(axis=1)
    if not usable.any():
        return out
    matrix = out.loc[usable, feature_cols].astype(float)
    labels = bundle.model.predict(matrix)
    proba = bundle.model.predict_proba(matrix)
    confidence = proba.max(axis=1)
    out.loc[usable, ML_CATEGORY_COL] = labels
    out.loc[usable, ML_CONFIDENCE_COL] = confidence
    rule = out.loc[usable, CLASSIFIER_TARGET].astype(str)
    ml = pd.Series(labels, index=out.index[usable], dtype="object")
    out.loc[usable, ML_DISAGREE_COL] = rule.ne(ml) & rule.ne("N/A")
    return out


def metrics_for_help(
    cluster: ClusterBundle | None,
    forecast: ForecastBundle | None,
    classifier: ClassifierBundle | None,
) -> dict[str, Any]:
    """Flatten live model metrics for Help & Guide and the PDF."""
    payload: dict[str, Any] = {}
    if cluster is not None:
        payload["kmeans"] = {
            "silhouette": cluster.silhouette,
            "n_weeks": cluster.n_weeks,
            "sizes": dict(cluster.sizes),
        }
    if forecast is not None:
        payload["forecast"] = {
            "n_train": forecast.n_train,
            "n_test": forecast.n_test,
            "mae": forecast.mae,
            "r2": forecast.r2,
            "importances": forecast.importances[:5],
        }
    if classifier is not None:
        payload["classifier"] = {
            "n_train": classifier.n_train,
            "n_test": classifier.n_test,
            "accuracy": classifier.accuracy,
            "importances": classifier.importances,
        }
    return payload
