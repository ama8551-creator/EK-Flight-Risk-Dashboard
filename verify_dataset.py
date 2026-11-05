"""Verify the dataset supports the prioritization model, then report on it.

Run after replacing the workbook:

    python -X utf8 verify_dataset.py

Checks the overbooking the risk model depends on, and — most importantly —
whether that overbooking reaches *open* flights at their current snapshot,
since only those are categorised. Development aid, not part of the dashboard.
"""

from __future__ import annotations

import sys
from datetime import datetime

import pandas as pd

import risk_scoring as rs
from data_loader import (
    SNAPSHOT_DATE,
    latest_snapshots,
    load_flights,
    resolve_data_path,
)

#: Expected counts at each open flight's latest snapshot, agreed with the
#: dataset author. Only these rows are categorised, so they determine what the
#: dashboard actually shows.
EXPECTED_TOTAL_OVER = 3
EXPECTED_Y_OVER = 33
EXPECTED_FCST_OVER = 36

#: Tolerance on the counts the author specified approximately ("~33", "~36").
COUNT_TOLERANCE = 2

#: Flights whose real days-to-departure were verified by hand, as
#: ``(flight number, departure date, expected days left on the snapshot date)``.
#: These guard against a regression of the bug where the snapshot grid position
#: (45, 60, 75...) was displayed and scored as the days actually remaining.
EXPECTED_DTD_CASES = (
    ("EK906", "2026-12-05", 4),
    ("EK902", "2027-01-01", 31),
    ("EK902", "2027-01-10", 40),
)

#: Passenger counts on the three currently-RED flights, used as a regression
#: guard for the Pax at Risk feature (Total Bkg - Total Cap, RED only).
EXPECTED_PAX_AT_RISK = 68


PASS = "PASS"
FAIL = "FAIL"
WARN = "WARN"


def _line(status: str, message: str) -> None:
    """Print one check result."""
    print(f"  [{status}] {message}")


def _check_current_snapshot_breaches(flights: pd.DataFrame) -> bool:
    """Confirm the overbooking reaches open flights at their current snapshot.

    This is the check that matters. Flown flights carry no risk category, and
    older snapshots of open flights are not the dashboard's "now", so
    overbooking outside this set cannot light up any category.
    """
    current = latest_snapshots(flights)

    total_over = int((current["Total BSF"] > 1.0).sum())
    exact = total_over == EXPECTED_TOTAL_OVER
    _line(
        PASS if exact else FAIL,
        f"Total BSF > 100%: {total_over} legs "
        f"(expected {EXPECTED_TOTAL_OVER}) — drives RED",
    )

    y_over = int((current["Y BSF"] > 1.0).sum())
    y_ok = abs(y_over - EXPECTED_Y_OVER) <= COUNT_TOLERANCE
    _line(
        PASS if y_ok else FAIL,
        f"Y BSF > 100%: {y_over} legs "
        f"(expected ~{EXPECTED_Y_OVER}) — drives ORANGE",
    )

    fcst_over = int((current["Fcst Total BSF"] > 1.0).sum())
    fcst_ok = abs(fcst_over - EXPECTED_FCST_OVER) <= COUNT_TOLERANCE
    _line(
        PASS if fcst_ok else FAIL,
        f"Fcst Total BSF > 100%: {fcst_over} legs "
        f"(expected ~{EXPECTED_FCST_OVER}) — drives YELLOW",
    )

    return exact and y_ok and fcst_ok


def _check_red_flights(flights: pd.DataFrame) -> bool:
    """Report which flights breach total capacity, the RED population."""
    current = latest_snapshots(flights)
    red = current[current["Total BSF"] > 1.0].sort_values("Total BSF", ascending=False)
    if red.empty:
        _line(FAIL, "No open flight breaches 100% total BSF, so RED stays empty")
        return False

    for _, flight in red.iterrows():
        _line(
            PASS,
            f"RED: {flight['Flight No']} {flight['Route']} "
            f"{flight['Dep Date']:%Y-%m-%d} in {flight[rs.DTD_COLUMN]}d — "
            f"total {flight['Total BSF']:.2%}, {flight['Period']}",
        )
    return True


def _check_orange_window(flights: pd.DataFrame) -> bool:
    """Report where ORANGE candidates sit relative to the 45-day window.

    Measured in real days to departure, not the snapshot grid position.
    """
    current = latest_snapshots(flights)
    candidates = current[
        (current["Y BSF"] > 1.0) & (current["Total BSF"] <= 1.0)
    ]
    if candidates.empty:
        _line(WARN, "No ORANGE candidates (Y over, total within capacity)")
        return True

    dtd = candidates[rs.DTD_COLUMN]
    inside = int((dtd <= 45).sum())
    outside = int((dtd > 45).sum())
    _line(
        PASS,
        f"ORANGE candidates: {len(candidates)} "
        f"({inside} within 45 real days, {outside} beyond); "
        f"actual DTD spans {dtd.min()}-{dtd.max()} days",
    )
    return True


def _check_actual_dtd(flights: pd.DataFrame) -> bool:
    """Confirm days-to-departure is measured from the snapshot date.

    Guards the bug where the snapshot grid position (45, 60, 75...) was shown
    and scored as if it were the days actually remaining.
    """
    current = latest_snapshots(flights)
    expected = (current["Dep Date"] - SNAPSHOT_DATE).dt.days
    mismatched = int((current[rs.DTD_COLUMN] != expected).sum())
    _line(
        PASS if mismatched == 0 else FAIL,
        f"Actual DTD equals (Dep Date - {SNAPSHOT_DATE.date()}) for all "
        f"{len(current):,} open legs ({mismatched} mismatched)",
    )

    diverging = int((current[rs.DTD_COLUMN] != current["Days to Departure"]).sum())
    _line(
        PASS,
        f"{diverging:,} legs where actual days differ from the snapshot grid "
        f"position — these are the rows the old bug mis-scored",
    )

    cases_ok = True
    for flight_no, dep_date, expected_days in EXPECTED_DTD_CASES:
        leg = current[
            (current["Flight No"] == flight_no)
            & (current["Dep Date"] == pd.Timestamp(dep_date))
        ]
        if leg.empty:
            _line(FAIL, f"{flight_no} on {dep_date} is not in the current view")
            cases_ok = False
            continue
        actual = int(leg.iloc[0][rs.DTD_COLUMN])
        snapshot = int(leg.iloc[0]["Days to Departure"])
        ok = actual == expected_days
        cases_ok &= ok
        _line(
            PASS if ok else FAIL,
            f"{flight_no} on {dep_date}: {actual} days left "
            f"(expected {expected_days}; snapshot grid says {snapshot})",
        )

    return mismatched == 0 and cases_ok


def _check_dow(flights: pd.DataFrame) -> bool:
    """Confirm day-of-week is ISO 8601 via ``date.isoweekday()``."""
    current = latest_snapshots(flights)
    expected = current["Dep Date"].map(lambda ts: ts.date().isoweekday())
    mismatched = int((current["DOW"] != expected).sum())
    values = sorted(current["DOW"].unique().tolist())
    ok = mismatched == 0 and values == list(range(1, 8))
    _line(
        PASS if ok else FAIL,
        f"DOW equals date.isoweekday() for all {len(current):,} open legs "
        f"({mismatched} mismatched); values {values}",
    )
    return ok


def _check_pax_at_risk(flights: pd.DataFrame) -> bool:
    """Confirm Pax at Risk is Total Bkg - Total Cap, and only on RED."""
    scored = rs.assign_risk(latest_snapshots(flights))
    red = scored[scored["Risk Category"] == rs.RED]
    others = scored[scored["Risk Category"] != rs.RED]

    expected = (red["Total Bkg"] - red["Total Cap"]).astype(float)
    actual = red["Pax at Risk"].astype(float)
    mismatch = int((actual != expected).sum()) if len(red) else 0
    leaked = int(others["Pax at Risk"].notna().sum())
    total = int(scored["Pax at Risk"].sum())
    ok = mismatch == 0 and leaked == 0 and total == EXPECTED_PAX_AT_RISK
    _line(
        PASS if ok else FAIL,
        f"Pax at Risk: {total} across {len(red)} RED flights "
        f"(expected {EXPECTED_PAX_AT_RISK}; {mismatch} formula mismatches, "
        f"{leaked} non-RED filled)",
    )
    return ok


def _report_categories(flights: pd.DataFrame) -> dict[str, int]:
    """Score the current view and print the resulting category counts."""
    scored = rs.assign_risk(latest_snapshots(flights))
    counts = rs.category_counts(scored)
    print("\nRisk categories at the current snapshot "
          f"({SNAPSHOT_DATE.date()}), {len(scored):,} open legs:")
    for category in rs.CATEGORIES:
        print(f"  {category:<7} {counts[category]:>5,}")

    empty = [c for c in rs.CATEGORIES if counts[c] == 0]
    if empty:
        print(f"\n  Note: no flights in {', '.join(empty)}.")
    return counts


def main() -> int:
    """Run every check and return a shell exit code."""
    path = resolve_data_path()
    modified = datetime.fromtimestamp(path.stat().st_mtime)
    print(f"Workbook: {path}")
    print(f"Modified: {modified:%Y-%m-%d %H:%M:%S}\n")

    flights = load_flights()
    print(f"Loaded {len(flights):,} rows.\n")
    print("Checks:")

    results = [
        _check_actual_dtd(flights),
        _check_dow(flights),
        _check_pax_at_risk(flights),
        _check_current_snapshot_breaches(flights),
        _check_red_flights(flights),
        _check_orange_window(flights),
    ]
    _report_categories(flights)

    if all(results):
        print("\nAll checks passed.")
        return 0
    print("\nSome checks failed.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
