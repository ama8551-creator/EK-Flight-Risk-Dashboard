"""The prioritization model: risk categories and the 0-100 composite score.

This module implements specification section 2 and is the analytical core of
the dashboard. Everything is vectorised so a whole snapshot set can be rescored
in one pass, which is what the replay tab needs.

Units: every BSF value is a *fraction*, so "100% booked" is ``1.0``.

------------------------------------------------------------------------------
Risk categories (open flights only; flown flights are never categorised)
------------------------------------------------------------------------------
Evaluated in strict priority order, so each flight lands in exactly one bucket:

  RED     Total BSF > 100%
          The flight is overbooked right now. Immediate action.
  ORANGE  Y BSF > 100% AND Total BSF <= 100% AND Actual DTD <= 45
          Economy is over, but First/Business still have room to reaccommodate.
  YELLOW  Forecast Total BSF > 100% (and not already RED or ORANGE)
          On track to be overbooked by departure.
  GREEN   Everything else. Normal operations.

------------------------------------------------------------------------------
Composite risk score (0-100)
------------------------------------------------------------------------------
The score ranks flights *within* a category, so it is the sum of three parts:

  1. Base score       - how bad the situation already is (category).
                        RED 75, ORANGE 45, YELLOW 20, GREEN 0.
  2. Urgency bonus    - how little time is left to act. A problem 3 days out is
                        far more actionable than the same problem 90 days out.
                        0-3d +25, 4-7d +20, 8-14d +15, 15-30d +10, 31-60d +5,
                        60+d +0.
  3. Severity bonus   - how far past capacity the flight already is.
                        >110% +15, 105-110% +10, 101-105% +5, else +0.

The total is capped at 100. Because the urgency and severity bonuses are added
regardless of category, a GREEN flight departing tomorrow still outranks a
GREEN flight departing in three months, which keeps the ordering useful.

------------------------------------------------------------------------------
Passenger exposure
------------------------------------------------------------------------------
Alongside the score, :func:`assign_risk` quantifies how many passengers the
situation actually affects, which is what makes a category concrete to an
analyst. See :func:`pax_at_risk`.

Time is always measured with ``Actual DTD`` — real days left until departure —
never with the dataset's ``Days to Departure``, which is only the snapshot
grid position. See :func:`data_loader.add_actual_dtd`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

import numpy as np
import pandas as pd

from data_loader import STATUS_OPEN

# --- Categories ------------------------------------------------------------
RED: Final[str] = "RED"
ORANGE: Final[str] = "ORANGE"
YELLOW: Final[str] = "YELLOW"
GREEN: Final[str] = "GREEN"

#: Categories ordered most to least urgent.
CATEGORIES: Final[list[str]] = [RED, ORANGE, YELLOW, GREEN]

#: Label used for flown flights, which carry no risk category.
NO_CATEGORY: Final[str] = "N/A"

# --- Scoring constants (spec section 2) ------------------------------------
BASE_SCORES: Final[dict[str, int]] = {RED: 75, ORANGE: 45, YELLOW: 20, GREEN: 0}

#: ``(inclusive upper bound on days to departure, bonus)``, nearest first.
URGENCY_BANDS: Final[tuple[tuple[int, int], ...]] = (
    (3, 25),
    (7, 20),
    (14, 15),
    (30, 10),
    (60, 5),
)
URGENCY_BONUS_BEYOND: Final[int] = 0

#: ``(load factor above the capacity line, bonus)``, most severe first.
SEVERITY_BANDS: Final[tuple[tuple[float, int], ...]] = (
    (0.10, 15),
    (0.05, 10),
    (0.01, 5),
)

MAX_SCORE: Final[int] = 100

#: The time column every time-sensitive rule reads. Deliberately *not* the
#: dataset's "Days to Departure", which is the snapshot grid position.
DTD_COLUMN: Final[str] = "Actual DTD"

#: Columns added by :func:`assign_risk`.
RISK_COLUMNS: Final[list[str]] = [
    "Risk Category",
    "Risk Score",
    "Base Score",
    "Urgency Bonus",
    "Severity Bonus",
    "Pax at Risk",
    "Potential Pax at Risk",
    "Underperforming vs LY",
]

#: Secondary flag: BSF vLY at or below this (a 10-point drop vs last year).
#: Independent of RED/ORANGE/YELLOW/GREEN — a flight can carry both.
UNDERPERFORM_VLY_THRESHOLD: Final[float] = -0.10

#: Icon shown next to the traffic-light category when the flag is on.
BLACK_FLAG_ICON: Final[str] = "⚫"


@dataclass(frozen=True)
class RiskThresholds:
    """The load factors at which each risk category triggers.

    Defaults reproduce the specification exactly: the capacity line sits at
    100% of seats. They are parameterised because the model's sensitivity is
    itself a subject of analysis, and because a dataset whose load factors
    never breach 100% would otherwise classify every flight as GREEN.

    Attributes:
        red_total_bsf: Current total BSF above which a flight is RED.
        orange_y_bsf: Current Y BSF above which Economy counts as over.
        orange_max_dtd: ORANGE only applies at or inside this many real days
            to departure. Inclusive.
        yellow_fcst_total_bsf: Forecast total BSF above which a flight is
            YELLOW.
    """

    red_total_bsf: float = 1.0
    orange_y_bsf: float = 1.0
    orange_max_dtd: int = 45
    yellow_fcst_total_bsf: float = 1.0

    @property
    def is_spec_default(self) -> bool:
        """Whether these thresholds are the unmodified specification values."""
        return self == RiskThresholds()


#: Threshold set used unless a caller overrides it.
DEFAULT_THRESHOLDS: Final[RiskThresholds] = RiskThresholds()


def urgency_bonus(days_to_departure: pd.Series) -> pd.Series:
    """Score the time pressure on each flight.

    Args:
        days_to_departure: Real days remaining before departure, i.e. the
            ``Actual DTD`` column.

    Returns:
        Urgency bonus per row.
    """
    conditions = [days_to_departure <= bound for bound, _ in URGENCY_BANDS]
    bonuses = [bonus for _, bonus in URGENCY_BANDS]
    return pd.Series(
        np.select(conditions, bonuses, default=URGENCY_BONUS_BEYOND),
        index=days_to_departure.index,
        dtype="int64",
    )


def severity_bonus(
    total_bsf: pd.Series, thresholds: RiskThresholds = DEFAULT_THRESHOLDS
) -> pd.Series:
    """Score how far past the capacity line a flight already is.

    Bands are measured relative to ``thresholds.red_total_bsf`` so that
    lowering the capacity line shifts the severity ladder with it.

    Args:
        total_bsf: Current total BSF as a fraction.
        thresholds: Threshold set defining the capacity line.

    Returns:
        Severity bonus per row.
    """
    line = thresholds.red_total_bsf
    conditions = [total_bsf > line + offset for offset, _ in SEVERITY_BANDS]
    bonuses = [bonus for _, bonus in SEVERITY_BANDS]
    return pd.Series(
        np.select(conditions, bonuses, default=0),
        index=total_bsf.index,
        dtype="int64",
    )


def pax_at_risk(df: pd.DataFrame, category: pd.Series) -> pd.DataFrame:
    """Count the passengers exposed to denied boarding.

    Two measures, because RED and ORANGE flights are exposed differently:

    * **Pax at Risk** — RED only. The flight is already selling more seats
      than the aircraft has, so ``Total Bkg - Total Cap`` passengers currently
      have no seat.
    * **Potential Pax at Risk** — ORANGE only. Total bookings still fit, but
      only because First and Business have empty seats absorbing the Economy
      overbooking. If those cabins fill, ``Y Bkg - Y Cap`` passengers lose the
      seat they were being reaccommodated into.

    Both are null outside their category, so the Overview column stays blank
    rather than showing a misleading zero.

    Args:
        df: Rows carrying the booking and capacity columns.
        category: Risk category per row, from :func:`categorise`.

    Returns:
        A frame with ``Pax at Risk`` and ``Potential Pax at Risk``.
    """
    overbooked = df["Total Bkg"] - df["Total Cap"]
    y_overbooked = df["Y Bkg"] - df["Y Cap"]
    return pd.DataFrame(
        {
            "Pax at Risk": overbooked.where(category == RED).astype("Float64"),
            "Potential Pax at Risk": y_overbooked.where(
                category == ORANGE
            ).astype("Float64"),
        },
        index=df.index,
    )


def categorise(
    df: pd.DataFrame, thresholds: RiskThresholds = DEFAULT_THRESHOLDS
) -> pd.Series:
    """Assign one risk category per row.

    Only open flights are categorised; flown flights return
    :data:`NO_CATEGORY`.

    Args:
        df: Rows carrying ``Total BSF``, ``Y BSF``, ``Fcst Total BSF``,
            ``Actual DTD`` and ``Status``.
        thresholds: Threshold set defining each category's trigger.

    Returns:
        Category label per row.
    """
    is_open = df["Status"] == STATUS_OPEN

    is_red = df["Total BSF"] > thresholds.red_total_bsf
    # Economy is over capacity but the cabin mix overall still has room, and
    # departure is close enough that reaccommodation must be planned now.
    is_orange = (
        (df["Y BSF"] > thresholds.orange_y_bsf)
        & (df["Total BSF"] <= thresholds.red_total_bsf)
        & (df[DTD_COLUMN] <= thresholds.orange_max_dtd)
    )
    is_yellow = df["Fcst Total BSF"] > thresholds.yellow_fcst_total_bsf

    # np.select honours priority order, so RED wins over ORANGE over YELLOW.
    category = np.select(
        [is_open & is_red, is_open & is_orange, is_open & is_yellow, is_open],
        [RED, ORANGE, YELLOW, GREEN],
        default=NO_CATEGORY,
    )
    return pd.Series(category, index=df.index, dtype="object")


def assign_risk(
    df: pd.DataFrame, thresholds: RiskThresholds = DEFAULT_THRESHOLDS
) -> pd.DataFrame:
    """Attach risk category, composite score and the score's components.

    Safe to call on any set of snapshot rows, including historical ones, which
    is how the replay tab rescores the past.

    Args:
        df: Snapshot rows to score.
        thresholds: Threshold set to apply.

    Returns:
        Copy of ``df`` with the columns in :data:`RISK_COLUMNS` added. Flown
        flights receive :data:`NO_CATEGORY` and a null score.
    """
    scored = df.copy()
    if scored.empty:
        for column in RISK_COLUMNS:
            if column == "Underperforming vs LY":
                scored[column] = pd.Series(dtype="bool")
            elif column == "Risk Category":
                scored[column] = pd.Series(dtype="object")
            else:
                scored[column] = pd.Series(dtype="float64")
        return scored

    scored["Risk Category"] = categorise(scored, thresholds)
    scored["Base Score"] = (
        scored["Risk Category"].map(BASE_SCORES).astype("float64")
    )
    scored["Urgency Bonus"] = urgency_bonus(scored[DTD_COLUMN])
    scored["Severity Bonus"] = severity_bonus(scored["Total BSF"], thresholds)

    total = (
        scored["Base Score"] + scored["Urgency Bonus"] + scored["Severity Bonus"]
    )
    scored["Risk Score"] = total.clip(upper=MAX_SCORE)

    exposure = pax_at_risk(scored, scored["Risk Category"])
    scored[exposure.columns] = exposure

    if "BSF vLY" in scored.columns:
        scored["Underperforming vs LY"] = scored["BSF vLY"].notna() & (
            scored["BSF vLY"] <= UNDERPERFORM_VLY_THRESHOLD
        )
    else:
        scored["Underperforming vs LY"] = False

    # Flown flights are not part of the prioritization model.
    not_scored = scored["Risk Category"] == NO_CATEGORY
    scored.loc[not_scored, ["Risk Score", "Base Score", "Urgency Bonus", "Severity Bonus"]] = np.nan

    return scored


def rank_by_risk(df: pd.DataFrame) -> pd.DataFrame:
    """Order flights the way an analyst should work through them.

    Highest risk score first; ties broken by the nearest departure, then by the
    fullest flight.

    Args:
        df: Rows already scored by :func:`assign_risk`.

    Returns:
        Sorted copy of ``df`` with a fresh index.
    """
    if df.empty:
        return df.copy()
    return df.sort_values(
        by=["Risk Score", DTD_COLUMN, "Total BSF"],
        ascending=[False, True, False],
        kind="mergesort",
    ).reset_index(drop=True)


def category_counts(df: pd.DataFrame) -> dict[str, int]:
    """Count flights per risk category, including categories with zero rows.

    Args:
        df: Rows already scored by :func:`assign_risk`.

    Returns:
        Mapping of every category in :data:`CATEGORIES` to its flight count.
    """
    counts = df["Risk Category"].value_counts() if not df.empty else pd.Series(dtype=int)
    return {category: int(counts.get(category, 0)) for category in CATEGORIES}


def score_breakdown(row: pd.Series) -> list[str]:
    """Explain one flight's score in plain language.

    Feeds the drill-down tab's insight box.

    Args:
        row: A single scored flight.

    Returns:
        Human-readable lines describing how the score was composed.
    """
    category = row.get("Risk Category", NO_CATEGORY)
    if category == NO_CATEGORY or pd.isna(row.get("Risk Score")):
        return ["This flight has already flown, so it carries no risk score."]

    lines = [
        f"Category **{category}** contributes a base of "
        f"{int(row['Base Score'])} points.",
        f"Departing in {int(row[DTD_COLUMN])} day(s) adds "
        f"{int(row['Urgency Bonus'])} urgency points.",
    ]
    if row["Severity Bonus"] > 0:
        lines.append(
            f"Being {row['Total BSF']:.1%} booked adds "
            f"{int(row['Severity Bonus'])} severity points."
        )
    else:
        lines.append("Current bookings are within capacity, so no severity points.")
    lines.append(f"**Total risk score: {int(row['Risk Score'])} / {MAX_SCORE}.**")
    return lines
