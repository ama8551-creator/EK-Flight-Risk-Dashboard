"""Load and preprocess the synthetic flight dataset.

All Excel reading and column derivation happens here, exactly once per
session, behind ``@st.cache_data``. Downstream modules should never touch the
workbook directly.

Note on units: the workbook stores every BSF column as a *fraction*
(``0.4556`` means 45.56%). Fractions are preserved throughout the pipeline and
only converted to percentages at display time.
"""

from __future__ import annotations

from pathlib import Path
from typing import Final

import pandas as pd
import streamlit as st

# --- Workbook location -----------------------------------------------------
DATA_FILENAME: Final[str] = "Synthetic_Flight_Dataset.xlsx"
# The specification writes ``data/`` but the supplied folder is ``Data/``;
# accept either so the app runs on case-sensitive filesystems too.
_DATA_DIR_CANDIDATES: Final[tuple[str, ...]] = ("data", "Data")

FLIGHTS_SHEET: Final[str] = "Flights"
ROSTER_SHEET: Final[str] = "Flight Roster"
AIRCRAFT_SHEET: Final[str] = "Aircraft Config"

# --- Domain constants ------------------------------------------------------
# The analyst views the system "as of" this date (spec: Project Overview).
SNAPSHOT_DATE: Final[pd.Timestamp] = pd.Timestamp("2026-12-01")

STATUS_OPEN: Final[str] = "Open"
STATUS_FLOWN: Final[str] = "FLN"

CABINS: Final[tuple[str, ...]] = ("F", "J", "Y")

# Days-to-departure snapshot grid used by the dataset.
SNAPSHOT_DAYS: Final[tuple[int, ...]] = (0, 1, 3, 7, 14, 21, 30, 45, 60, 75, 90, 120)

# Columns that identify one physical flight leg.
FLIGHT_KEY: Final[list[str]] = ["Flight No", "Dep Date"]

#: Fallback hub code when a loaded dataset has no Route values to infer from.
#: Live filters infer the hub as the airport that appears most often.
HUB: Final[str] = "DXB"

#: Known POS columns, used only as a display-order hint. Actual columns are
#: discovered from the workbook at load time (any ``POS_XX`` header).
POS_COLUMNS: Final[tuple[str, ...]] = (
    "POS_AE",
    "POS_SA",
    "POS_LB",
    "POS_JO",
    "POS_AU",
    "POS_CA",
    "POS_US",
    "POS_GB",
    "POS_DE",
    "POS_FR",
)

#: ISO 2-letter code → country name, for labels and the Help tab.
#: Unknown codes fall back to the ISO code itself.
POS_NAMES: Final[dict[str, str]] = {
    "AE": "United Arab Emirates",
    "SA": "Saudi Arabia",
    "LB": "Lebanon",
    "JO": "Jordan",
    "AU": "Australia",
    "CA": "Canada",
    "US": "United States",
    "GB": "United Kingdom",
    "DE": "Germany",
    "FR": "France",
}


def infer_hub(routes: object) -> str:
    """Return the hub airport: the code that appears most often on routes.

    Args:
        routes: Iterable of ``Origin-Destination`` strings.

    Returns:
        Hub IATA code, or :data:`HUB` when nothing can be inferred.
    """
    counts: dict[str, int] = {}
    for route in routes:
        for part in str(route).split("-"):
            if part:
                counts[part] = counts.get(part, 0) + 1
    if not counts:
        return HUB
    return max(counts, key=counts.get)


def outstation(route: str, hub: str | None = None) -> str:
    """Return the non-hub city on a route such as ``DXB-XYZ``.

    Args:
        route: An ``Origin-Destination`` string.
        hub: Hub to exclude. Defaults to :data:`HUB`; pass
            :func:`infer_hub` of the full route list when the hub is not DXB.

    Returns:
        The outstation airport code.
    """
    parts = [part for part in str(route).split("-") if part]
    resolved = hub or HUB
    for part in parts:
        if part != resolved:
            return part
    return parts[-1] if parts else str(route)


def pos_code(column: str) -> str:
    """Return the ISO country code for a ``POS_XX`` column name.

    Args:
        column: A POS column name such as ``POS_AE``.

    Returns:
        The two-letter code, e.g. ``AE``.
    """
    return column.replace("POS_", "", 1)


def discover_pos_columns(columns: object) -> list[str]:
    """Return ``POS_XX`` headers found on a frame, in workbook order.

    Known names in :data:`POS_COLUMNS` keep their declared order; any extra
    market column is appended. Adding a country to the dataset is enough —
    no code change is required for it to appear in filters and charts.

    Args:
        columns: Column names from a flights frame.

    Returns:
        POS column names present in ``columns``.
    """
    present = [
        str(column)
        for column in columns
        if str(column).startswith("POS_") and str(column)[4:].isalpha()
    ]
    preferred = [column for column in POS_COLUMNS if column in present]
    extras = [column for column in present if column not in POS_COLUMNS]
    return preferred + extras


def pos_columns_in(df: pd.DataFrame) -> list[str]:
    """POS columns actually present on ``df``.

    Args:
        df: A flights frame.

    Returns:
        Column names discovered from ``df``.
    """
    return discover_pos_columns(df.columns)


def pos_label(code: str) -> str:
    """Return a display name for an ISO POS country code."""
    return POS_NAMES.get(code, code)

#: ISO 8601 weekday numbers mapped to their abbreviation. Monday is 1.
#: Day of week drives demand strongly in this dataset — weekend returns are
#: typically the peak legs — so it is both a column and a filter.
DOW_NAMES: Final[dict[int, str]] = {
    1: "Mon",
    2: "Tue",
    3: "Wed",
    4: "Thu",
    5: "Fri",
    6: "Sat",
    7: "Sun",
}


def dow_label(iso_weekday: int) -> str:
    """Render an ISO weekday as the number and its abbreviation.

    Args:
        iso_weekday: ISO 8601 weekday, 1 (Monday) through 7 (Sunday).

    Returns:
        Label such as ``"4 (Thu)"``.
    """
    return f"{iso_weekday} ({DOW_NAMES[iso_weekday]})"

#: Consolidated commercial periods mapped to the substrings that identify them
#: in the raw "Period" column.
#:
#: The workbook splits each season into many granular variants — outbound vs
#: return, city, and shoulder day-of-week — 37 in total. Analysts think in
#: terms of the holiday, not the variant, so the sidebar offers these nine
#: groups and matches any row whose Period contains one of the group's
#: substrings.
PERIOD_GROUPS: Final[dict[str, tuple[str, ...]]] = {
    "Christmas": ("Christmas",),
    "New Year Return": ("New Year Return",),
    "Summer Outbound": ("Summer Outbound",),
    "Summer Return": ("Summer Return",),
    "Eid al Fitr": ("Eid al Fitr",),
    "Eid al Adha": ("Eid al Adha",),
    "UAE National Day": ("UAE National Day",),
    "School Break Return": ("School Break Return",),
    "Hajj": ("Hajj",),
    "Ramadan Umrah": ("Ramadan Umrah",),
    "Weekend Umrah": ("Weekend Umrah",),
    "Corporate Weekday": ("Corporate Weekday",),
    "Weekend Lull": ("Weekend Lull",),
    "Off-Peak": ("Off-Peak",),
}


def period_group_of(period: str) -> str | None:
    """Map a raw Period value onto its consolidated group.

    Args:
        period: A value from the "Period" column.

    Returns:
        The matching group name, or ``None`` if nothing matches.
    """
    for group, substrings in PERIOD_GROUPS.items():
        if any(substring in period for substring in substrings):
            return group
    return None


def resolve_data_path(filename: str = DATA_FILENAME) -> Path:
    """Locate the dataset workbook relative to this file.

    Args:
        filename: Workbook file name to look for.

    Returns:
        Path to the workbook.

    Raises:
        FileNotFoundError: If the workbook is not in any expected location.
    """
    root = Path(__file__).resolve().parent
    candidates = [root / d / filename for d in _DATA_DIR_CANDIDATES]
    candidates.append(root / filename)
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    searched = "\n  ".join(str(c) for c in candidates)
    raise FileNotFoundError(
        f"Could not find {filename!r}. Looked in:\n  {searched}"
    )


def _weighted_total_bsf(
    df: pd.DataFrame, f_col: str, j_col: str, y_col: str
) -> pd.Series:
    """Combine per-cabin BSF into a capacity-weighted total BSF.

    A flight's total load factor is total bookings over total seats, so the
    cabin figures must be weighted by each cabin's capacity rather than
    averaged. Used to derive ``Fcst Total BSF``, which the workbook does not
    provide but the Overview table requires.

    Args:
        df: Frame containing the cabin capacity and BSF columns.
        f_col: Name of the First-class BSF column.
        j_col: Name of the Business-class BSF column.
        y_col: Name of the Economy-class BSF column.

    Returns:
        Capacity-weighted total BSF as a fraction.
    """
    seats = df["F Cap"] + df["J Cap"] + df["Y Cap"]
    booked = (
        df[f_col] * df["F Cap"] + df[j_col] * df["J Cap"] + df[y_col] * df["Y Cap"]
    )
    return booked / seats


def _lookup_prior_bsf(
    current: pd.DataFrame, prior_legs: pd.DataFrame, offset_days: int
) -> pd.Series:
    """Look up last year's Total BSF for the same flight, shifted by ``offset_days``.

    Args:
        current: Rows whose prior-year match is being sought.
        prior_legs: One row per historical leg, with ``Prior Total BSF``.
        offset_days: Days to subtract from ``Dep Date`` (365 = calendar date,
            364 = weekday-aligned date).

    Returns:
        Prior-year Total BSF aligned to ``current.index``. Null where no
        same-flight operation exists on that date.
    """
    keys = current[["Flight No"]].copy()
    keys["Dep Date"] = current["Dep Date"] - pd.Timedelta(days=offset_days)
    matched = keys.merge(
        prior_legs[FLIGHT_KEY + ["Prior Total BSF"]], on=FLIGHT_KEY, how="left"
    )
    return pd.Series(matched["Prior Total BSF"].to_numpy(), index=current.index)


def _fill_missing_bsf_vly(df: pd.DataFrame) -> pd.DataFrame:
    """Fill workbook gaps in ``BSF vLY``.

    The workbook stores the column as roughly ``this Fcst Total BSF minus last
    year's Total BSF on the same calendar date`` (minus 365 days). A few legs
    have no same-flight operation that day — EK902 on 5 Dec 2026 is the one
    that shows up on the first page of Overview — so those cells arrive as
    null and Streamlit renders them as "None".

    Gaps are filled, in order, from:

      1. the same flight number on the calendar date minus 365 days
      2. the same flight number on the weekday-aligned date minus 364 days
      3. the same route on the calendar date minus 365 days (a sibling that
         did operate; EK904/EK906 cover EK902's missing UAE National Day)

    Args:
        df: Preprocessed flights, with ``Fcst Total BSF`` already derived.

    Returns:
        ``df`` with null ``BSF vLY`` filled where a comparison exists.
    """
    if "BSF vLY" not in df.columns:
        df["BSF vLY"] = pd.NA
    df["BSF vLY"] = pd.to_numeric(df["BSF vLY"], errors="coerce")

    missing = df["BSF vLY"].isna()
    if not missing.any():
        return df

    # One load factor per historical leg: the terminal / latest snapshot.
    prior_legs = (
        df.sort_values("Days to Departure")
        .groupby(FLIGHT_KEY, sort=False)
        .agg(
            **{
                "Prior Total BSF": ("Total BSF", "last"),
                "Route": ("Route", "first"),
            }
        )
        .reset_index()
    )

    last_year = _lookup_prior_bsf(df, prior_legs, offset_days=365)
    last_year = last_year.fillna(_lookup_prior_bsf(df, prior_legs, offset_days=364))

    still_missing = missing & last_year.isna()
    if still_missing.any():
        route_prior = (
            prior_legs.groupby(["Route", "Dep Date"], sort=False)[
                "Prior Total BSF"
            ]
            .mean()
            .reset_index()
        )
        route_keys = df.loc[:, ["Route"]].copy()
        route_keys["Dep Date"] = df["Dep Date"] - pd.Timedelta(days=365)
        route_match = route_keys.merge(
            route_prior, on=["Route", "Dep Date"], how="left"
        )
        last_year = last_year.fillna(
            pd.Series(
                route_match["Prior Total BSF"].to_numpy(), index=df.index
            )
        )

    derived = df["Fcst Total BSF"] - last_year
    df.loc[missing, "BSF vLY"] = derived.loc[missing]
    return df


def add_actual_dtd(df: pd.DataFrame, as_of: pd.Timestamp) -> pd.DataFrame:
    """Set "Actual DTD": calendar days from ``as_of`` to departure.

    Recomputed whenever the reference date moves, which is what keeps the
    replay tab honest about how much time an analyst had on a past date.

    Args:
        df: Rows carrying a ``Dep Date`` column.
        as_of: The date to measure from.

    Returns:
        ``df`` with ``Actual DTD`` set. Negative for departed flights.
    """
    df["Actual DTD"] = (df["Dep Date"] - pd.Timestamp(as_of)).dt.days
    return df


def _preprocess(flights: pd.DataFrame, roster: pd.DataFrame) -> pd.DataFrame:
    """Add the derived columns every view depends on.

    Args:
        flights: Raw rows from the "Flights" sheet.
        roster: Raw rows from the "Flight Roster" sheet.

    Returns:
        Enriched copy of ``flights``.
    """
    df = flights.copy()
    df["Dep Date"] = pd.to_datetime(df["Dep Date"])
    df["Dep Time"] = df["Dep Time"].astype(str)

    # Calendar date on which this row's booking figures were observed.
    df["Snapshot Date"] = df["Dep Date"] - pd.to_timedelta(
        df["Days to Departure"], unit="D"
    )

    # Real days left as of the dashboard's "today".
    #
    # "Days to Departure" is the snapshot grid position (120, 90, 75, 60, 45,
    # ...), i.e. how far out the observation was taken — not how long the
    # analyst actually has left to act. A flight observed at the 45-day
    # snapshot but departing in 31 days needs to be treated as 31 days away.
    # Everything time-sensitive (urgency scoring, the ORANGE window, the
    # sidebar slider, the table) uses "Actual DTD"; "Days to Departure"
    # survives only to pick which snapshot is a flight's current state.
    df = add_actual_dtd(df, SNAPSHOT_DATE)

    # ISO 8601 day of week of departure, via date.isoweekday():
    # Monday = 1 ... Sunday = 7.
    df["DOW"] = df["Dep Date"].map(lambda ts: ts.date().isoweekday()).astype(
        "int64"
    )
    df["DOW Label"] = df["DOW"].map(dow_label)

    df["Total Cap"] = df["F Cap"] + df["J Cap"] + df["Y Cap"]
    df["Total Bkg"] = df["F Bkg"] + df["J Bkg"] + df["Y Bkg"]

    # POS columns are passenger counts by country of sale. They pass through
    # from the workbook and should already sum to Total Bkg; coerce so charts
    # never see mixed types. Discovery picks up new markets such as POS_SA.
    for column in discover_pos_columns(df.columns):
        df[column] = (
            pd.to_numeric(df[column], errors="coerce").fillna(0).astype("int64")
        )

    # Forecast total load factor at departure (not supplied by the workbook).
    df["Fcst Total BSF"] = _weighted_total_bsf(
        df, "F Fcst BSF", "J Fcst BSF", "Y Fcst BSF"
    )

    # Seats sold beyond capacity, per cabin and overall. Negative = seats left.
    for cabin in CABINS:
        df[f"{cabin} Over Seats"] = df[f"{cabin} Bkg"] - df[f"{cabin} Cap"]
    df["Total Over Seats"] = df["Total Bkg"] - df["Total Cap"]

    # Aircraft type, needed by the drill-down identity card.
    df = df.merge(
        roster[["Flight No", "Aircraft"]].drop_duplicates("Flight No"),
        on="Flight No",
        how="left",
    )

    df = _fill_missing_bsf_vly(df)

    # Flag the most recent snapshot of each open flight leg (smallest DTD).
    df["Is Latest"] = False
    open_mask = df["Status"] == STATUS_OPEN
    if open_mask.any():
        latest_idx = df.loc[open_mask].groupby(FLIGHT_KEY)[
            "Days to Departure"
        ].idxmin()
        df.loc[latest_idx, "Is Latest"] = True
    # A flown flight has a single terminal row, which is its current state.
    df.loc[df["Status"] == STATUS_FLOWN, "Is Latest"] = True

    return df


def _workbook_version() -> tuple[str, float]:
    """Identify the current workbook by path and last-modified time.

    Passed into the cached loaders as a cache key so that replacing the Excel
    file invalidates the cache automatically, instead of serving stale data
    until the server restarts.

    Returns:
        The workbook path and its modification timestamp.
    """
    path = resolve_data_path()
    return str(path), path.stat().st_mtime


@st.cache_data(show_spinner="Loading flight dataset…")
def _read_and_preprocess(path: str, mtime: float) -> pd.DataFrame:
    """Read the workbook and apply preprocessing. Cached on file version.

    Args:
        path: Workbook path.
        mtime: Workbook modification time, part of the cache key only.

    Returns:
        Enriched flights frame.
    """
    del mtime  # Participates in the cache key, not in the computation.
    workbook = pd.ExcelFile(path, engine="openpyxl")
    return _preprocess(workbook.parse(FLIGHTS_SHEET), workbook.parse(ROSTER_SHEET))


def load_flights() -> pd.DataFrame:
    """Read and preprocess the full dataset.

    Returns:
        Every row of the "Flights" sheet plus derived columns.
    """
    path, mtime = _workbook_version()
    return _read_and_preprocess(path, mtime)


@st.cache_data(show_spinner=False)
def _read_sheet(path: str, mtime: float, sheet: str) -> pd.DataFrame:
    """Read one sheet verbatim. Cached on file version.

    Args:
        path: Workbook path.
        mtime: Workbook modification time, part of the cache key only.
        sheet: Sheet name to read.

    Returns:
        The sheet's rows.
    """
    del mtime  # Participates in the cache key, not in the computation.
    return pd.ExcelFile(path, engine="openpyxl").parse(sheet)


def load_roster() -> pd.DataFrame:
    """Return the flight roster sheet (aircraft type, scheduled time, route)."""
    path, mtime = _workbook_version()
    return _read_sheet(path, mtime, ROSTER_SHEET)


def load_aircraft_config() -> pd.DataFrame:
    """Return the aircraft configuration sheet (per-cabin seat counts)."""
    path, mtime = _workbook_version()
    return _read_sheet(path, mtime, AIRCRAFT_SHEET)


def latest_snapshots(flights: pd.DataFrame) -> pd.DataFrame:
    """Reduce open flights to one row each: their current state.

    The dashboard treats the newest snapshot on or before the snapshot date as
    "now". Older snapshots remain in the full frame for booking-curve views.

    Args:
        flights: Preprocessed frame from :func:`load_flights`.

    Returns:
        One row per open flight leg.
    """
    open_flights = flights[flights["Status"] == STATUS_OPEN]
    return open_flights[open_flights["Is Latest"]].copy()


def snapshots_as_of(
    flights: pd.DataFrame, as_of: pd.Timestamp
) -> pd.DataFrame:
    """Rebuild the "current state" of every open flight at an earlier date.

    Powers the replay tab: for each flight leg, keep the snapshot closest to
    but not after ``as_of``, and drop legs that had already departed.

    Args:
        flights: Preprocessed frame from :func:`load_flights`.
        as_of: The simulated "today".

    Returns:
        At most one row per open flight leg, as visible on ``as_of``.
    """
    as_of = pd.Timestamp(as_of)
    open_flights = flights[
        (flights["Status"] == STATUS_OPEN)
        & (flights["Snapshot Date"] <= as_of)
        & (flights["Dep Date"] >= as_of)
    ]
    if open_flights.empty:
        return open_flights.copy()
    # Latest observation on or before as_of == smallest remaining DTD.
    keep = open_flights.groupby(FLIGHT_KEY)["Days to Departure"].idxmin()
    # Days remaining must be measured from the simulated date, not from the
    # dataset's snapshot date.
    return add_actual_dtd(open_flights.loc[keep].copy(), as_of)


def filter_options(flights: pd.DataFrame) -> dict[str, list]:
    """Collect the distinct values the sidebar filters offer.

    Args:
        flights: Preprocessed frame from :func:`load_flights`.

    Returns:
        Mapping of filter name to its sorted option list.
    """
    directions = sorted(flights["Route"].dropna().unique().tolist())
    hub = infer_hub(directions)
    cities = sorted({outstation(direction, hub) for direction in directions})

    raw_periods = flights["Period"].dropna().unique().tolist()
    present_groups = {period_group_of(p) for p in raw_periods}
    # Preserve the declared group order rather than sorting alphabetically.
    period_groups = [g for g in PERIOD_GROUPS if g in present_groups]

    present_pos = [
        pos_code(column)
        for column in pos_columns_in(flights)
        if flights[column].fillna(0).gt(0).any()
    ]

    return {
        "directions": directions,
        "cities": cities,
        "flight_numbers": sorted(flights["Flight No"].dropna().unique().tolist()),
        "period_groups": period_groups,
        "periods": sorted(raw_periods),
        "seasons": sorted(flights["Season"].dropna().unique().tolist()),
        "pos_countries": present_pos,
    }
