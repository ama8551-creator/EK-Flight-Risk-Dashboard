"""The KPI card row (specification section 5).

Six equal-width cards summarising the currently filtered flights. The three
risk-category cards, the passenger-exposure card and the underperforming-vs-LY
card carry a trend arrow comparing today's figure with the same filtered
population a week earlier, which tells the analyst whether a problem is
building or clearing.
"""

from __future__ import annotations

from typing import Final

import pandas as pd
import streamlit as st

import risk_scoring
from styling import theme

#: How far back the trend arrows look.
TREND_LOOKBACK_DAYS: Final[int] = 7

def card(
    label: str,
    value: str,
    subtitle: str = "",
    accent: str = theme.EMIRATES_RED,
    value_color: str | None = None,
    trend: str = "",
) -> str:
    """Build the HTML for one KPI card.

    Args:
        label: Small uppercase heading.
        value: The headline figure.
        subtitle: Optional explanatory line beneath the figure. Omitted when
            empty so Overview cards stay compact.
        accent: Colour of the card's left border.
        value_color: Colour of the headline figure. Defaults to charcoal.
        trend: Optional pre-rendered trend line.

    Returns:
        HTML for a single card.
    """
    colour = value_color or theme.CHARCOAL
    sub_html = (
        f"<div class='ek-kpi-sub'>{subtitle}</div>" if subtitle else ""
    )
    return (
        f"<div class='ek-kpi' style='border-left-color:{accent};'>"
        f"<div class='ek-kpi-label'>{label}</div>"
        f"<div class='ek-kpi-value' style='color:{colour};'>{value}</div>"
        f"{sub_html}"
        f"{trend}"
        f"</div>"
    )


def _trend_line(current: int, previous: int | None) -> str:
    """Render the week-on-week movement for a category count.

    Args:
        current: Count in the current view.
        previous: Count a week earlier, or ``None`` if unavailable.

    Returns:
        HTML for the trend line, or an empty string when there is no
        comparison or no change.
    """
    if previous is None:
        return ""
    delta = current - previous
    if delta == 0:
        return (
            f"<div class='ek-kpi-trend' style='color:#7A7A7A;'>"
            f"▬ no change vs {TREND_LOOKBACK_DAYS}d ago</div>"
        )
    # More flights in a risk bucket is bad news, hence red for an increase.
    colour = theme.EMIRATES_RED if delta > 0 else theme.GREEN
    arrow = "▲" if delta > 0 else "▼"
    return (
        f"<div class='ek-kpi-trend' style='color:{colour};'>"
        f"{arrow} {abs(delta)} vs {TREND_LOOKBACK_DAYS}d ago</div>"
    )


def render(current: pd.DataFrame, previous: pd.DataFrame | None = None) -> None:
    """Draw the KPI card row.

    Args:
        current: Filtered, scored flights making up the current view.
        previous: The same filters applied a week earlier, for trend arrows.
            Pass ``None`` to omit the arrows.
    """
    counts = risk_scoring.category_counts(current)
    previous_counts = (
        risk_scoring.category_counts(previous) if previous is not None else None
    )

    def prior(category: str) -> int | None:
        """Look up a category's count a week ago, if available."""
        return None if previous_counts is None else previous_counts[category]

    # Null outside RED, so the sum is already "across RED flights only".
    pax_at_risk = (
        int(current["Pax at Risk"].sum()) if "Pax at Risk" in current else 0
    )
    previous_pax = (
        int(previous["Pax at Risk"].sum())
        if previous is not None and "Pax at Risk" in previous
        else None
    )

    underperforming = (
        int(current["Underperforming vs LY"].sum())
        if "Underperforming vs LY" in current
        else 0
    )
    previous_under = (
        int(previous["Underperforming vs LY"].sum())
        if previous is not None and "Underperforming vs LY" in previous
        else None
    )

    cards = [
        card(
            "Total open flights",
            f"{len(current):,}",
            accent=theme.CHARCOAL,
        ),
        card(
            "Red flights",
            f"{counts[risk_scoring.RED]:,}",
            accent=theme.EMIRATES_RED,
            value_color=theme.EMIRATES_RED,
            trend=_trend_line(counts[risk_scoring.RED], prior(risk_scoring.RED)),
        ),
        card(
            "Orange flights",
            f"{counts[risk_scoring.ORANGE]:,}",
            accent=theme.ORANGE,
            value_color=theme.ORANGE,
            trend=_trend_line(counts[risk_scoring.ORANGE], prior(risk_scoring.ORANGE)),
        ),
        card(
            "Yellow flights",
            f"{counts[risk_scoring.YELLOW]:,}",
            accent=theme.YELLOW,
            value_color="#C79100",  # Darkened for legibility on cream.
            trend=_trend_line(counts[risk_scoring.YELLOW], prior(risk_scoring.YELLOW)),
        ),
        card(
            "Total pax at risk",
            f"{pax_at_risk:,}",
            accent=theme.EMIRATES_RED_DARK,
            value_color=theme.EMIRATES_RED_DARK,
            trend=_trend_line(pax_at_risk, previous_pax),
        ),
        card(
            "Underperforming vs LY",
            f"{underperforming:,}",
            accent=theme.BLACK_FLAG,
            value_color=theme.BLACK_FLAG,
            trend=_trend_line(underperforming, previous_under),
        ),
    ]

    cells = "".join(f"<div class='ek-kpi-cell'>{html}</div>" for html in cards)
    st.markdown(f"<div class='ek-kpi-row'>{cells}</div>", unsafe_allow_html=True)
