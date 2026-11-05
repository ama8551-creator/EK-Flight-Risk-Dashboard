"""Action recommendations: what the analyst should actually do about a flight.

The risk score says how urgent a flight is; this module says what to do about
it. Each recommendation is derived from the flight's own cabin numbers, so the
advice names concrete seat counts rather than restating the category.

Shown only in detail panels, never in the ranked table, where it would crowd
out the figures the ranking depends on.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

import pandas as pd
import streamlit as st

import risk_scoring
import utils
from styling import theme

#: Icon per category: a tick for "nothing to do", escalating warnings above.
CATEGORY_ICONS: Final[dict[str, str]] = {
    risk_scoring.RED: "🚨",
    risk_scoring.ORANGE: "⚠️",
    risk_scoring.YELLOW: "🔔",
    risk_scoring.GREEN: "✅",
}

#: Days before departure by which overbooking parameters should be revisited.
YELLOW_REVIEW_DAY: Final[int] = 30

#: How soon an ORANGE flight should be looked at again.
ORANGE_REVIEW_WINDOW: Final[str] = "3-5 days"


@dataclass(frozen=True)
class Recommendation:
    """A single piece of advice about one flight.

    Attributes:
        icon: Status glyph shown beside the headline.
        headline: The action to take, rendered in bold.
        details: Supporting lines: current state, then expected outcome.
        accent: Panel border colour, matching the risk category.
    """

    icon: str
    headline: str
    details: tuple[str, ...]
    accent: str


def _seats(flight: pd.Series, cabin: str) -> tuple[int, int]:
    """Return a cabin's bookings and capacity.

    Args:
        flight: A scored flight row.
        cabin: Cabin code, ``"F"``, ``"J"`` or ``"Y"``.

    Returns:
        Bookings and capacity, as integers.
    """
    return int(flight[f"{cabin} Bkg"]), int(flight[f"{cabin} Cap"])


def _total_bsf_if_y_capped(flight: pd.Series) -> float:
    """Total load factor if Economy were trimmed back to its capacity.

    Models the outcome of the RED recommendation: First and Business are left
    untouched, Economy is reduced to exactly its seat count.

    Args:
        flight: A scored flight row.

    Returns:
        The resulting total BSF as a fraction.
    """
    f_booked, _ = _seats(flight, "F")
    j_booked, _ = _seats(flight, "J")
    _, y_capacity = _seats(flight, "Y")
    return (f_booked + j_booked + y_capacity) / int(flight["Total Cap"])


def recommend(flight: pd.Series) -> Recommendation:
    """Derive the recommended action for one flight.

    Args:
        flight: A flight row already scored by ``risk_scoring.assign_risk``.

    Returns:
        The recommendation for that flight's category.
    """
    category = flight.get("Risk Category", risk_scoring.NO_CATEGORY)
    accent = theme.CATEGORY_COLORS.get(category, theme.NEUTRAL_GRAY)
    icon = CATEGORY_ICONS.get(category, "ℹ️")

    if category == risk_scoring.NO_CATEGORY:
        return Recommendation(
            icon="ℹ️",
            headline="No action available.",
            details=("This flight has already flown, so it carries no risk "
                     "category or recommended action.",),
            accent=theme.NEUTRAL_GRAY,
        )

    y_booked, y_capacity = _seats(flight, "Y")
    y_over = y_booked - y_capacity
    days_left = int(flight[risk_scoring.DTD_COLUMN])

    if category == risk_scoring.RED:
        # Always advise shedding at least one seat: a flight can be over on
        # total capacity while Economy alone is only fractionally over.
        reduce_by = max(1, y_over)
        over_capacity_pct = (float(flight["Total BSF"]) - 1.0) * 100
        exposed = int(flight["Total Bkg"]) - int(flight["Total Cap"])
        return Recommendation(
            icon=icon,
            headline=(
                f"Reduce Y overbooking by {reduce_by} seats to prevent "
                "denied boarding risk."
            ),
            details=(
                f"{exposed} pax at risk of denied boarding.",
                f"Current state: Y overbooked by +{y_over}, "
                f"F at {utils.format_pct(flight['F BSF'])}, "
                f"J at {utils.format_pct(flight['J BSF'])}, "
                f"Total {over_capacity_pct:.1f}% over capacity. "
                f"{days_left} days to departure.",
                f"If reduced to Y capacity: Total BSF would be "
                f"~{utils.format_pct(_total_bsf_if_y_capped(flight))}, "
                "within safe operating range.",
            ),
            accent=accent,
        )

    if category == risk_scoring.ORANGE:
        f_booked, f_capacity = _seats(flight, "F")
        j_booked, j_capacity = _seats(flight, "J")
        f_empty = f_capacity - f_booked
        j_empty = j_capacity - j_booked
        return Recommendation(
            icon=icon,
            headline=(
                f"Monitor closely. Y currently overbooked by +{y_over}, "
                "but F/J have capacity to absorb."
            ),
            details=(
                f"F has {f_empty} empty, J has {j_empty} empty, "
                f"total buffer = {f_empty + j_empty} seats.",
                f"If F/J fill up, +{max(0, y_over)} pax at risk.",
                "If F or J fills up further, total may exceed capacity. "
                f"Review in {ORANGE_REVIEW_WINDOW}.",
            ),
            accent=accent,
        )

    if category == risk_scoring.YELLOW:
        return Recommendation(
            icon=icon,
            headline="Early warning: projected to exceed capacity at departure.",
            details=(
                f"Forecast Total BSF at departure: "
                f"{utils.format_pct(flight['Fcst Total BSF'])}. "
                "Current overbooking parameters may need adjustment.",
                f"Review Y overbooking parameters before day "
                f"{YELLOW_REVIEW_DAY}.",
            ),
            accent=accent,
        )

    return Recommendation(
        icon=icon,
        headline="No action required.",
        details=("Flight tracking within expected parameters.",),
        accent=accent,
    )


def render(flight: pd.Series) -> None:
    """Draw the recommendation panel for one flight.

    Args:
        flight: A flight row already scored by ``risk_scoring.assign_risk``.
    """
    recommendation = recommend(flight)
    details = "".join(
        f"<div class='ek-reco-detail'>{line}</div>"
        for line in recommendation.details
    )
    st.markdown(
        f"""
        <div class="ek-reco" style="border-left-color:{recommendation.accent};">
          <div class="ek-reco-head">
            <span class="ek-reco-icon">{recommendation.icon}</span>
            <span class="ek-reco-headline">{recommendation.headline}</span>
          </div>
          {details}
        </div>
        """,
        unsafe_allow_html=True,
    )
