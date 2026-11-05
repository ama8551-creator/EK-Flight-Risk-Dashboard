"""Shared formatting and lookup helpers used across the dashboard components."""

from __future__ import annotations

from typing import Final

import pandas as pd

from styling import theme

# --- BSF cell colour thresholds (spec section 6, Tab 1) --------------------
BSF_CRITICAL: Final[float] = 1.00  # above capacity
BSF_WARNING: Final[float] = 0.90  # filling up

#: Days used to align a flight to "the same flight last year". 364 keeps the
#: day of week aligned, which matters because demand is strongly day-of-week
#: driven in this dataset.
YOY_OFFSET_DAYS: Final[int] = 364


def format_pct(value: float | None, decimals: int = 1) -> str:
    """Render a fractional BSF as a percentage string.

    Args:
        value: Fraction such as ``0.4556``.
        decimals: Decimal places to show.

    Returns:
        Formatted percentage, or ``"–"`` when the value is missing.
    """
    if value is None or pd.isna(value):
        return "–"
    return f"{value * 100:.{decimals}f}%"


def format_signed_pct(value: float | None, decimals: int = 1) -> str:
    """Render a BSF difference with an explicit sign and direction arrow.

    Args:
        value: Fractional difference such as ``-0.032``.
        decimals: Decimal places to show.

    Returns:
        Formatted delta, e.g. ``"▲ +3.2%"``.
    """
    if value is None or pd.isna(value):
        return "–"
    arrow = "▲" if value > 0 else ("▼" if value < 0 else "▬")
    return f"{arrow} {value * 100:+.{decimals}f}%"


def bsf_color(value: float | None) -> str:
    """Pick the cell colour for a BSF value.

    Args:
        value: Fractional BSF.

    Returns:
        Hex colour: red above capacity, orange when filling up, else green.
    """
    if value is None or pd.isna(value):
        return theme.NEUTRAL_GRAY
    if value > BSF_CRITICAL:
        return theme.EMIRATES_RED
    if value >= BSF_WARNING:
        return theme.ORANGE
    return theme.GREEN


def style_bsf_columns(
    styler: "pd.io.formats.style.Styler", columns: list[str]
) -> "pd.io.formats.style.Styler":
    """Colour-code BSF columns in place on a pandas ``Styler``.

    Args:
        styler: Styler for the table being rendered.
        columns: BSF column names to colour.

    Returns:
        The same styler, for chaining.
    """

    def _colour(value: float) -> str:
        return f"color: {bsf_color(value)}; font-weight: 600;"

    present = [c for c in columns if c in styler.data.columns]
    return styler.map(_colour, subset=present)


def to_csv_bytes(df: pd.DataFrame) -> bytes:
    """Encode a frame for a Streamlit download button.

    Args:
        df: Frame to export.

    Returns:
        UTF-8 (BOM) encoded CSV bytes so Excel opens it cleanly.
    """
    return df.to_csv(index=False).encode("utf-8-sig")


def flight_label(row: pd.Series) -> str:
    """Build a readable one-line identifier for a flight leg.

    Args:
        row: A flight row.

    Returns:
        Label such as ``"EK953 · DXB-XYZ · 2026-12-04"``.
    """
    return (
        f"{row['Flight No']} · {row['Route']} · "
        f"{pd.Timestamp(row['Dep Date']).date()}"
    )


def prior_year_date(dep_date: pd.Timestamp, offset_days: int = YOY_OFFSET_DAYS) -> pd.Timestamp:
    """Map a departure date onto its comparable date a year earlier.

    Args:
        dep_date: Departure date in the current year.
        offset_days: Days to subtract. Defaults to :data:`YOY_OFFSET_DAYS`.

    Returns:
        The aligned prior-year date.
    """
    return pd.Timestamp(dep_date) - pd.Timedelta(days=offset_days)


def find_prior_year_flight(
    flights: pd.DataFrame,
    flight_no: str,
    dep_date: pd.Timestamp,
    tolerance_days: int = 3,
) -> pd.DataFrame:
    """Locate last year's equivalent operation of a flight.

    Looks for the same flight number around the day-of-week aligned date a year
    back, widening to ``tolerance_days`` either side because the schedule does
    not run every flight number daily.

    Candidates are ranked by day-of-week match first and date proximity
    second. Ranking purely by proximity would happily return a Monday as the
    comparison for a Friday, which defeats the point of the 364-day offset in
    a dataset this day-of-week driven.

    Args:
        flights: Preprocessed frame from ``data_loader.load_flights``.
        flight_no: Flight number to match.
        dep_date: Current-year departure date.
        tolerance_days: How far either side of the aligned date to search.

    Returns:
        Matching rows, best comparison first. Empty when none exists.
    """
    target = prior_year_date(dep_date)
    window = pd.Timedelta(days=tolerance_days)
    matches = flights[
        (flights["Flight No"] == flight_no)
        & (flights["Dep Date"] >= target - window)
        & (flights["Dep Date"] <= target + window)
    ].copy()
    if matches.empty:
        return matches

    matches["Date Gap"] = (matches["Dep Date"] - target).abs()
    matches["DOW Aligned"] = (
        matches["Dep Date"].dt.isocalendar().day
        == pd.Timestamp(dep_date).isoweekday()
    )
    return matches.sort_values(
        ["DOW Aligned", "Date Gap"], ascending=[False, True]
    ).drop(columns=["Date Gap", "DOW Aligned"])


def booking_curve(
    flights: pd.DataFrame, flight_no: str, dep_date: pd.Timestamp
) -> pd.DataFrame:
    """Return every snapshot of one flight leg, oldest observation first.

    Args:
        flights: Preprocessed frame from ``data_loader.load_flights``.
        flight_no: Flight number to isolate.
        dep_date: Departure date to isolate.

    Returns:
        Snapshots sorted by descending days to departure, so time flows
        forward.
    """
    leg = flights[
        (flights["Flight No"] == flight_no)
        & (flights["Dep Date"] == pd.Timestamp(dep_date))
    ]
    return leg.sort_values("Days to Departure", ascending=False)


def empty_state(message: str = "No flights match your filters.") -> str:
    """Build the HTML shown when a filter combination returns nothing.

    Args:
        message: Text to display.

    Returns:
        HTML string for ``st.markdown(..., unsafe_allow_html=True)``.
    """
    return (
        f"<div class='ek-panel' style='text-align:center; color:#7A7A7A;'>"
        f"<h4 style='color:{theme.EMIRATES_RED_DARK};'>Nothing to show</h4>"
        f"{message}</div>"
    )
