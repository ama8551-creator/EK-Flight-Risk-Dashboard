"""The Help & Guide content, as data rather than markup.

Written once here and rendered twice — to the Help & Guide tab and to the
downloadable PDF — so the two can never drift apart. Adding a section means
editing this file only.

Section 5 is **generated from the scoring constants** rather than typed out.
Hand-written documentation of a formula is the first thing to go stale, and a
dashboard whose help text contradicts its own arithmetic is worse than one
with no help text. Change a band in ``risk_scoring`` and this updates with it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Final, Union

import pandas as pd

import risk_scoring
from data_loader import (
    DOW_NAMES,
    POS_NAMES,
    SNAPSHOT_DATE,
    SNAPSHOT_DAYS,
    dow_label,
)

GUIDE_TITLE: Final[str] = "Flight Prioritization Dashboard — User Guide"
PDF_FILENAME: Final[str] = "Flight_Dashboard_User_Guide.pdf"


# --- Content blocks --------------------------------------------------------
@dataclass(frozen=True)
class Para:
    """A paragraph of prose.

    Attributes:
        text: The paragraph text.
    """

    text: str


@dataclass(frozen=True)
class Bullets:
    """A bulleted or numbered list.

    Attributes:
        items: The list entries.
        numbered: Render as an ordered list.
    """

    items: tuple[str, ...]
    numbered: bool = False


@dataclass(frozen=True)
class Definitions:
    """Term-and-meaning pairs, e.g. column definitions.

    Attributes:
        items: ``(term, meaning)`` pairs.
    """

    items: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class Table:
    """A grid of values.

    Attributes:
        headers: Column headings.
        rows: Row values, matching ``headers`` in length.
        pdf_drop: Column indices omitted from the PDF, used for emoji columns
            the PDF's base fonts cannot render.
        colour_column: Index of a column whose text is coloured by risk
            category, or ``None``.
    """

    headers: tuple[str, ...]
    rows: tuple[tuple[str, ...], ...]
    pdf_drop: tuple[int, ...] = ()
    colour_column: int | None = None


Block = Union[Para, Bullets, Definitions, Table]


@dataclass(frozen=True)
class Section:
    """One numbered section of the guide.

    Attributes:
        title: Section heading, without its number.
        blocks: The section's content, in order.
        expanded: Whether the on-screen accordion starts open.
    """

    title: str
    blocks: tuple[Block, ...] = field(default_factory=tuple)
    expanded: bool = False


# --- Section 5, generated from the live scoring constants ------------------
def urgency_band_lines() -> tuple[str, ...]:
    """Describe the urgency bonus bands exactly as the code applies them.

    Returns:
        One line per band, nearest departure first.
    """
    lines = []
    lower = 0
    for upper, bonus in risk_scoring.URGENCY_BANDS:
        span = f"{lower}" if lower == upper else f"{lower}-{upper}"
        lines.append(f"{span} days to departure: +{bonus}")
        lower = upper + 1
    lines.append(
        f"{lower} days or more: +{risk_scoring.URGENCY_BONUS_BEYOND}"
    )
    return tuple(lines)


def severity_band_lines() -> tuple[str, ...]:
    """Describe the severity bonus bands exactly as the code applies them.

    Returns:
        One line per band, most severe first.
    """
    line = risk_scoring.DEFAULT_THRESHOLDS.red_total_bsf
    lines = []
    previous: float | None = None
    for offset, bonus in risk_scoring.SEVERITY_BANDS:
        threshold = line + offset
        if previous is None:
            lines.append(f"Total BSF above {threshold:.0%}: +{bonus}")
        else:
            lines.append(
                f"Total BSF {threshold:.0%} to {previous:.0%}: +{bonus}"
            )
        previous = threshold
    lines.append(f"Total BSF at or below {previous:.0%}: +0")
    return tuple(lines)


def score_example_line() -> str:
    """Work a concrete scoring example using the real scoring functions.

    Computed rather than quoted, so the example cannot disagree with the
    model it is explaining.

    Returns:
        A sentence showing the arithmetic and the final score.
    """
    total_bsf, days_left = 1.08, 4
    base = risk_scoring.BASE_SCORES[risk_scoring.RED]
    urgency = int(risk_scoring.urgency_bonus(pd.Series([days_left])).iloc[0])
    severity = int(risk_scoring.severity_bonus(pd.Series([total_bsf])).iloc[0])
    raw = base + urgency + severity
    final = min(raw, risk_scoring.MAX_SCORE)
    capped = (
        f" The raw total is {raw}, capped at {final}."
        if raw > final
        else f" Total: {final}."
    )
    return (
        f"A RED flight {total_bsf:.0%} booked with {days_left} days to "
        f"departure scores {base} (base) + {urgency} (urgency) + {severity} "
        f"(severity).{capped}"
    )


def _snapshot_day_list() -> str:
    """Render the snapshot grid as a descending, comma-separated list."""
    return ", ".join(str(d) for d in sorted(SNAPSHOT_DAYS, reverse=True))


def _dow_option_list() -> str:
    """Render the day-of-week filter's options."""
    return ", ".join(dow_label(d) for d in sorted(DOW_NAMES))


def _pos_country_list() -> str:
    """Render known POS country codes as ``AE = United Arab Emirates``."""
    return ", ".join(f"{code} = {name}" for code, name in POS_NAMES.items())


def _metric(value: object, digits: int = 3) -> str:
    """Format a live model metric, or an em dash when it is missing."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "—"
    if number != number:
        return "—"
    return f"{number:.{digits}f}"


def _importance_lines(pairs: object, limit: int | None = None) -> tuple[str, ...]:
    """Render ``feature: weight`` lines from importance pairs."""
    if not isinstance(pairs, (list, tuple)):
        return ("Not yet available — open the dashboard to train the models.",)
    items = list(pairs)
    if limit is not None:
        items = items[:limit]
    if not items:
        return ("Not yet available — open the dashboard to train the models.",)
    return tuple(
        f"{name}: {_metric(weight, 3)}" for name, weight in items
    )


def _ml_section(ml: dict[str, Any] | None) -> Section:
    """Live metrics for the three models wired into the dashboard."""
    payload = ml or {}
    kmeans = payload.get("kmeans") or {}
    forecast = payload.get("forecast") or {}
    classifier = payload.get("classifier") or {}
    sizes = kmeans.get("sizes") or {}
    return Section(
        "Machine Learning Models",
        (
            Para(
                "Three scikit-learn models support the dashboard. Metrics "
                "below are from the models trained in this session."
            ),
            Para("Technique 1: K-Means Clustering (Peak Detection)"),
            Definitions(
                (
                    (
                        "Silhouette score",
                        _metric(kmeans.get("silhouette")),
                    ),
                    (
                        "Peak cluster size",
                        str(sizes.get("Peak", "—")),
                    ),
                    (
                        "Shoulder cluster size",
                        str(sizes.get("Shoulder", "—")),
                    ),
                    (
                        "Off-peak cluster size",
                        str(sizes.get("Off-Peak", "—")),
                    ),
                )
            ),
            Para("Technique 2: Random Forest Regression (Forecast BSF)"),
            Definitions(
                (
                    (
                        "Training sample count",
                        str(forecast.get("n_train", "—")),
                    ),
                    (
                        "Test sample count",
                        str(forecast.get("n_test", "—")),
                    ),
                    ("Test MAE", _metric(forecast.get("mae"))),
                    ("Test R²", _metric(forecast.get("r2"))),
                )
            ),
            Para("Top 5 feature importances"),
            Bullets(_importance_lines(forecast.get("importances"), limit=5)),
            Para("Technique 3: Decision Tree Classifier (Risk Category)"),
            Definitions(
                (
                    (
                        "Training sample count",
                        str(classifier.get("n_train", "—")),
                    ),
                    (
                        "Test sample count",
                        str(classifier.get("n_test", "—")),
                    ),
                    (
                        "Test accuracy",
                        _metric(classifier.get("accuracy")),
                    ),
                )
            ),
            Para("Feature importances"),
            Bullets(_importance_lines(classifier.get("importances"))),
        ),
    )


# --- The guide -------------------------------------------------------------
def sections(*, ml: dict[str, Any] | None = None) -> tuple[Section, ...]:
    """Build every section of the guide.

    Args:
        ml: Live model metrics from the current session, if the dashboard
            has already trained them.

    Returns:
        The sections in display order.
    """
    return (
        Section(
            "About this Dashboard",
            (
                Para(
                    "Real-time decision support dashboard for airline "
                    "inventory analysts to identify and prioritize "
                    "high-risk flights."
                ),
                Para(
                    "This dashboard is route-agnostic by design. All "
                    "route-specific filters, groupings, and visualizations "
                    "are generated dynamically from the loaded dataset. "
                    "Adding routes requires no code changes — only new "
                    "dataset rows."
                ),
                Definitions(
                    (
                        ("Target users", "Inventory revenue analysts."),
                        (
                            "Problem solved",
                            "Static reports do not reflect real-time booking "
                            "changes or prioritize analyst attention.",
                        ),
                        (
                            "Snapshot date",
                            "This dashboard reflects data as of "
                            f"{SNAPSHOT_DATE:%B} {SNAPSHOT_DATE.day}, "
                            f"{SNAPSHOT_DATE.year}.",
                        ),
                    )
                ),
            ),
            expanded=True,
        ),
        Section(
            "Risk Categories Explained",
            (
                Para(
                    "Categories apply to open flights only and are evaluated "
                    "in priority order, so each flight lands in exactly one "
                    "bucket."
                ),
                Table(
                    headers=(
                        "Category",
                        "Icon",
                        "Rule",
                        "Meaning",
                        "Analyst Action",
                    ),
                    rows=(
                        (
                            "RED",
                            "🔴",
                            "Total BSF > 100%",
                            "Flight actively overbooked",
                            "Reduce Y overbooking parameter immediately",
                        ),
                        (
                            "ORANGE",
                            "🟠",
                            "Y BSF > 100% AND Total BSF ≤ 100% AND "
                            "Days to Dep ≤ 45",
                            "Y overbooked, F/J have room",
                            "Monitor closely",
                        ),
                        (
                            "YELLOW",
                            "🟡",
                            "Forecast Total BSF > 100% "
                            "(not already RED/ORANGE)",
                            "Projected overbooking at departure",
                            "Review OB parameters proactively",
                        ),
                        (
                            "GREEN",
                            "🟢",
                            "Everything else",
                            "Normal operations",
                            "No action needed",
                        ),
                    ),
                    pdf_drop=(1,),
                    colour_column=0,
                ),
                Para(
                    "BLACK FLAG (⚫) is a secondary marker, not a fifth "
                    "category. It is applied when BSF vLY is 10 percentage "
                    "points or more below last year (BSF vLY ≤ −10%). A "
                    "flight can be GREEN and black-flagged (operating "
                    "normally, but weak versus last year) or RED and "
                    "black-flagged (overbooked now, but still below last "
                    "year's peak). Flights with no last-year comparison "
                    "are never flagged."
                ),
            ),
            expanded=True,
        ),
        Section(
            "Column Definitions",
            (
                Definitions(
                    (
                        (
                            "Risk",
                            "Traffic-light category icon. A black circle "
                            "(⚫) after the icon means the flight is "
                            "underperforming versus last year (BSF vLY ≤ "
                            "−10%). It is a secondary flag, not a fifth "
                            "category. A yellow warning (⚠) means the "
                            "Decision Tree predicted a different category "
                            "than the rules.",
                        ),
                        (
                            "Score",
                            "Composite risk score (0-100). Higher = more "
                            "urgent. Combines risk category, time to "
                            "departure, and overbooking severity.",
                        ),
                        (
                            "ML Confidence",
                            "Maximum class probability from the Decision "
                            "Tree trained on the rule-based categories. "
                            "Shown as a percentage. A ⚠ beside Risk means "
                            "the tree's predicted category disagrees with "
                            "the rules.",
                        ),
                        ("Flight No", "Flight number."),
                        (
                            "Route",
                            "Flight route (origin to destination airport "
                            "codes).",
                        ),
                        ("Dep Date", "Scheduled departure date."),
                        ("Dep Time", "Scheduled departure time."),
                        (
                            "DOW",
                            "Day of week of departure (1=Monday, 2=Tuesday, "
                            "..., 7=Sunday). Useful for identifying "
                            "weekend-driven demand patterns.",
                        ),
                        (
                            "Days to Dep",
                            "Actual days remaining until departure, "
                            "calculated from today's snapshot date.",
                        ),
                        (
                            "F BSF",
                            "First class Booked Seat Factor. Bookings as % of "
                            "F capacity. Values above 100% indicate "
                            "overbooking.",
                        ),
                        (
                            "J BSF",
                            "Business class Booked Seat Factor. Same logic.",
                        ),
                        (
                            "Y BSF",
                            "Economy class Booked Seat Factor. Same logic.",
                        ),
                        (
                            "Total BSF",
                            "Total flight Booked Seat Factor across all "
                            "cabins. Values above 100% indicate overbooking "
                            "and denied boarding risk.",
                        ),
                        (
                            "Fcst Total BSF",
                            "Projected Total BSF at departure. Open flights "
                            "use a Random Forest trained on historical "
                            "snapshots (days to departure 14 or more), not "
                            "the static workbook forecast.",
                        ),
                        (
                            "BSF vLY",
                            "Current or projected BSF compared to the same "
                            "flight on the same date last year. In the "
                            "Overview table, gains are green and declines "
                            "are red; moves of 0.1 percentage points or less "
                            "stay charcoal. A drop of 10 percentage points "
                            "or more lights the BLACK flag.",
                        ),
                        (
                            "POS_[country]",
                            "Bookings originating from the specified country "
                            "(ISO 2-letter code). Columns are discovered from "
                            "the loaded dataset. Known names: "
                            f"{_pos_country_list()}.",
                        ),
                        (
                            "Period",
                            "Shows the peak holiday or season this flight "
                            "falls within, but only after the analyst has "
                            "approved it through the Peak Detection tab. "
                            "Until a matching peak is approved, this column "
                            "shows '—'.",
                        ),
                        (
                            "Pax at Risk",
                            "Number of overbooked passengers "
                            "(Total Bkg - Total Cap). Shown for RED flights; "
                            "blank for others, which have nobody at risk "
                            "yet.",
                        ),
                    )
                ),
            ),
        ),
        Section(
            "Filter Guide",
            (
                Definitions(
                    (
                        (
                            "Route",
                            "Outstation city, either direction. Options are "
                            "the unique non-hub cities parsed from the Route "
                            "column of the loaded dataset.",
                        ),
                        (
                            "Direction",
                            "Specific origin-destination leg. Options are "
                            "the unique values of the Route column in the "
                            "loaded dataset.",
                        ),
                        ("Date Range", "Filter by scheduled departure date."),
                        (
                            "Risk Category",
                            "Filter by RED / ORANGE / YELLOW / GREEN.",
                        ),
                        (
                            "Cabin Class",
                            "Filter the analysis focus to F/J/Y. This focuses "
                            "charts rather than hiding flights.",
                        ),
                        (
                            "Days to Departure",
                            "Filter by actual days until departure.",
                        ),
                        (
                            "Day of Week",
                            f"Filter by day of week of departure. Options: "
                            f"{_dow_option_list()}.",
                        ),
                        (
                            "Period / Peak Holiday",
                            "Filter by holiday. Each option includes all of "
                            "that season's sub-periods, covering "
                            "outbound/return, each city, and shoulder "
                            "day-of-week variants.",
                        ),
                        ("Flight Number", "Filter to specific flights."),
                        (
                            "Underperforming vs LY",
                            "Yes shows only flights with the BLACK flag "
                            "(BSF vLY ≤ −10%). No shows only flights without "
                            "it. Empty shows all.",
                        ),
                        (
                            "Point of Sale",
                            "Shows flights where the selected country "
                            "contributes more than 5% of that flight's total "
                            "bookings. Empty shows all.",
                        ),
                        ("All filters", "An empty filter shows all flights."),
                    )
                ),
            ),
        ),
        Section(
            "How Risk Scores Are Calculated",
            (
                Para(
                    "The composite score runs 0-100 and is the sum of three "
                    "parts, capped at 100. The bands below are read directly "
                    "from the scoring module, so they always match the "
                    "running model."
                ),
                Para("Base score by category:"),
                Bullets(
                    tuple(
                        f"{category}: {score}"
                        for category, score in risk_scoring.BASE_SCORES.items()
                    )
                ),
                Para("Urgency bonus, based on Days to Dep:"),
                Bullets(urgency_band_lines()),
                Para("Severity bonus, based on how far Total BSF is over:"),
                Bullets(severity_band_lines()),
                Para(f"Worked example. {score_example_line()}"),
                Para(
                    "Because urgency and severity apply regardless of "
                    "category, a GREEN flight departing tomorrow still "
                    "outranks a GREEN flight departing in three months, which "
                    "keeps the ordering useful all the way down the list."
                ),
            ),
        ),
        Section(
            "Dashboard Tabs Guide",
            (
                Definitions(
                    (
                        (
                            "Overview",
                            "Main ranked list of all flights by risk score. "
                            "A red banner flags denied-boarding risk when any "
                            "RED flights are in view. Six KPI cards count "
                            "open flights, RED, ORANGE, YELLOW, passengers "
                            "at risk, and underperforming-vs-LY flights. "
                            "Today's Priorities lists up to seven actionable "
                            "flights, and a one-sentence summary restates "
                            "the RED / ORANGE / YELLOW counts.",
                        ),
                        (
                            "Flight Analysis",
                            "Booking Curve and Point of Sale for one flight "
                            "or for every flight in a date range. Flight No "
                            "defaults to All Flights. Last-year curves overlay "
                            "as dashed lines on the Booking Curve.",
                        ),
                        (
                            "Peak Detection",
                            "Detects recurring high-demand periods from "
                            "flown history. The analyst reviews each "
                            "recommendation, then accepts, adjusts, or "
                            "rejects it. Accepted peaks write to "
                            "approved_peaks.json and drive the Period "
                            "column on Overview.",
                        ),
                        (
                            "Replay",
                            "Simulate the dashboard view at past dates.",
                        ),
                    )
                ),
                Para("Flight Analysis Tab"),
                Para(
                    "Selectors at the top apply to both sub-tabs. Leave Flight "
                    "No on All Flights to inspect the whole date range, or "
                    "pick one flight number. Route and Direction are optional "
                    "multi-selects. Grouping appears only in All Flights mode "
                    "when a route or direction is selected."
                ),
                Para(
                    "Route is populated from the unique outstation cities in "
                    "the loaded dataset. It intersects with the sidebar Route "
                    "filter: a flight must match both. Empty on either side "
                    "means that side does not restrict. If both are set and "
                    "share no city, no flights appear."
                ),
                Bullets(
                    (
                        "Booking Curve: F/J/Y this year (solid, distinct "
                        "colours) against last year (grey dashed). All "
                        "Flights with no Route or Direction selected shows "
                        "two aggregated lines; selecting a route in the "
                        "tab or the sidebar applies the grouping dropdown.",
                        "Point of Sale: where bookings on the selected "
                        "flight — or every flight in the date range — were "
                        "sold. Each POS column is a passenger count; the "
                        "countries on a flight sum to that flight's total "
                        "bookings. The sub-tab shows KPI cards (total "
                        "bookings, the top three countries, and how many "
                        "countries have data), a donut of the mix, and a "
                        "per-flight table exportable to CSV. Only countries "
                        "with at least one booking are shown.",
                    )
                ),
                Para("Peak Detection Tab"),
                Para(
                    "Approved peaks override the default peak calendar used "
                    "across the dashboard. Until a peak is accepted, the "
                    "Period column shows an em dash."
                ),
                Para(
                    "Peaks can be added in two ways: (1) accepting "
                    "AI-detected recommendations, or (2) manually adding "
                    "peaks the AI missed. Both are stored together and "
                    "integrate with the Overview tab."
                ),
                Para(
                    "Choose a route (required), optionally narrow direction, "
                    "date range, point of sale, and flight number, then "
                    "click Detect Peaks."
                ),
                Bullets(
                    (
                        "Algorithm: flown flights only. Each ISO "
                        "week-direction is clustered with K-Means (Peak / "
                        "Shoulder / Off-Peak) on average, std, and max "
                        "Total BSF plus average Y and J BSF. Weeks in the "
                        "Peak cluster are candidates; adjacent weeks are "
                        "merged. Day-of-week pattern is classified inside "
                        "each window. One year of confirmation is enough.",
                        "Each card is a recommendation. Edit the name and "
                        "dates, then Accept or Reject. Review flights opens "
                        "the verification table and daily BSF chart for "
                        "that window.",
                        "My Approved Peaks stores accepted and manually "
                        "added records in approved_peaks.json. Each row "
                        "shows a Manual or AI-Detected badge. Edit or "
                        "delete either type; Overview Period labels use "
                        "this file only.",
                    )
                ),
            ),
        ),
        Section(
            "Recommended Analyst Workflow",
            (
                Para("Daily steps:"),
                Bullets(
                    (
                        "Open dashboard, review RED flights first (urgent "
                        "action required).",
                        "Work through Today's Priorities on Overview — RED "
                        "first, then ORANGE, YELLOW, and underperforming "
                        "versus last year.",
                        "Review ORANGE flights, assess F/J booking pace.",
                        "Use Flight Analysis Booking Curve to compare a "
                        "flight with last year.",
                        "Use Real-Time Replay to understand how flights "
                        "evolved.",
                        "Document decisions and action taken.",
                    ),
                    numbered=True,
                ),
            ),
        ),
        Section(
            "Methodology Notes",
            (
                Definitions(
                    (
                        (
                            "Snapshot days",
                            f"Data is captured at days "
                            f"{_snapshot_day_list()} before departure.",
                        ),
                        (
                            "Data source",
                            "Synthetic dataset reflecting realistic "
                            "operational patterns.",
                        ),
                        (
                            "Scoring methodology",
                            "Composite rule-based approach, chosen for "
                            "interpretability: an analyst can see exactly why "
                            "a flight ranks where it does.",
                        ),
                        (
                            "Peak calendar",
                            "Christmas, New Year, Summer, Eid periods and UAE "
                            "National Day, with direction-specific logic.",
                        ),
                        (
                            "Two days-to-departure measures",
                            "The dataset's own 'Days to Departure' is the "
                            "snapshot grid position, meaning which "
                            "observation point a row came from. Every "
                            "time-sensitive decision instead uses actual days "
                            "remaining, measured from the snapshot date to "
                            "departure.",
                        ),
                        (
                            "Today's Priorities",
                            "An auto-generated list of up to seven flights "
                            "from the current filtered view: every RED "
                            "flight (soonest first), then ORANGE, YELLOW by "
                            "forecast severity, then flights underperforming "
                            "versus last year. Click a flight number to open "
                            "its detail panel.",
                        ),
                    )
                ),
            ),
        ),
        _ml_section(ml),
        Section(
            "Frequently Asked Questions",
            (
                Definitions(
                    (
                        (
                            "Why is this flight showing DTD = 4 when the "
                            "snapshot was taken 7 days ago?",
                            "DTD shows actual days to departure from today, "
                            "not snapshot age.",
                        ),
                        (
                            "Why is RED category sometimes empty?",
                            "RED only triggers when a flight is already "
                            "overbooked. In off-peak periods, this is normal.",
                        ),
                        (
                            "Can I export the current view?",
                            "Yes, use the Export CSV button in the Overview "
                            "tab.",
                        ),
                        (
                            "What's the difference between Total BSF and "
                            "Forecast Total BSF?",
                            "Total BSF is the current state. Forecast Total "
                            "BSF is the Random Forest prediction of load "
                            "factor at departure.",
                        ),
                        (
                            "Why do YELLOW flights have low current BSF?",
                            "YELLOW is a forward-looking category based on "
                            "forecast. Current may be low but trajectory "
                            "indicates overbooking.",
                        ),
                    )
                ),
            ),
        ),
    )
