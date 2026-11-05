"""Verify the Help & Guide content and its downloadable PDF.

Run after changing scoring constants, help_content, or help_pdf:

    python -X utf8 verify_help.py

The on-screen tab and the PDF are generated from the same ``help_content``
sections, so this checks that the document is well-formed and that Section 5
still describes the scoring bands the running model actually uses.
Development aid, not part of the dashboard.
"""

from __future__ import annotations

import sys
from pathlib import Path

import help_content
import help_pdf
import risk_scoring

PASS = "PASS"
FAIL = "FAIL"

#: Expected numbered sections before the PDF download block.
EXPECTED_SECTION_COUNT = 10
EXPECTED_TITLES = (
    "About this Dashboard",
    "Risk Categories Explained",
    "Column Definitions",
    "Filter Guide",
    "How Risk Scores Are Calculated",
    "Dashboard Tabs Guide",
    "Recommended Analyst Workflow",
    "Methodology Notes",
    "Machine Learning Models",
    "Frequently Asked Questions",
)


def _line(status: str, message: str) -> None:
    """Print one check result."""
    print(f"  [{status}] {message}")


def _check_sections() -> bool:
    """Confirm the guide still has the specified sections, in order."""
    sections = help_content.sections()
    titles = tuple(section.title for section in sections)
    ok = titles == EXPECTED_TITLES
    _line(
        PASS if ok else FAIL,
        f"{len(sections)} sections (expected {EXPECTED_SECTION_COUNT}): "
        + ", ".join(titles),
    )
    return ok


def _check_score_bands() -> bool:
    """Confirm Section 5 is generated from the live scoring constants."""
    urgency = help_content.urgency_band_lines()
    first_band = risk_scoring.URGENCY_BANDS[0]
    expected_first = f"0-{first_band[0]} days to departure: +{first_band[1]}"
    ok = urgency[0] == expected_first
    _line(
        PASS if ok else FAIL,
        f"first urgency band is '{urgency[0]}' (live model: '{expected_first}')",
    )
    example = help_content.score_example_line()
    _line(PASS, f"worked example: {example}")
    return ok


def _check_pdf() -> bool:
    """Build the PDF and confirm it is a well-formed document."""
    try:
        data = help_pdf.build_pdf()
    except Exception as error:  # noqa: BLE001 - this is the check
        _line(FAIL, f"PDF build raised: {error}")
        return False

    magic = data[:5] == b"%PDF-"
    eof = b"%%EOF" in data[-1024:]
    pages = data.count(b"/Type /Page") - data.count(b"/Type /Pages")
    ok = magic and eof and pages >= 1 and len(data) > 5_000
    _line(
        PASS if ok else FAIL,
        f"PDF {len(data):,} bytes, ~{pages} pages, magic={magic}, eof={eof}",
    )

    out = Path("screenshots") / help_content.PDF_FILENAME
    out.parent.mkdir(exist_ok=True)
    out.write_bytes(data)
    _line(PASS, f"wrote {out}")
    return ok


def main() -> int:
    """Run every check and return a shell exit code."""
    print("Help & Guide checks:\n")
    results = [
        _check_sections(),
        _check_score_bands(),
        _check_pdf(),
    ]
    if all(results):
        print("\nAll checks passed.")
        return 0
    print("\nSome checks failed.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
