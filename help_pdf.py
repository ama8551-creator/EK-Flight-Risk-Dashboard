"""Render the Help & Guide content to a themed PDF.

Reads the same :mod:`help_content` sections the on-screen tab does, so the
document can never describe a different dashboard from the one it ships with.

One constraint shapes the output: reportlab's built-in Type 1 fonts cover
WinAnsi only, so emoji and a few typographic characters cannot be drawn. They
are substituted rather than dropped — see :data:`_SUBSTITUTIONS` — and the
risk-category table replaces its emoji column with coloured category text,
which carries the same meaning without needing a glyph that does not exist.
"""

from __future__ import annotations

import html
from io import BytesIO
from typing import Final

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    KeepTogether,
    ListFlowable,
    ListItem,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

import help_content
from data_loader import SNAPSHOT_DATE
from styling import theme

#: Characters the base fonts cannot render, and what to show instead.
_SUBSTITUTIONS: Final[dict[str, str]] = {
    "🔴": "",
    "🟠": "",
    "🟡": "",
    "🟢": "",
    "⚫": "(BLACK FLAG)",
    "⚠": "(!)",
    "≤": "<=",
    "−": "-",
    "≥": ">=",
    "–": "-",
    "—": "-",
    "·": "-",
    "→": "->",
    "’": "'",
    "“": '"',
    "”": '"',
    "▲": "up",
    "▼": "down",
    "▬": "flat",
    "²": "2",
}

_PAGE_MARGIN: Final[float] = 18 * mm
_HEADER_HEIGHT: Final[float] = 16 * mm


def _safe(text: str) -> str:
    """Make text renderable by reportlab's base fonts and XML-safe.

    Args:
        text: Source text, possibly containing emoji or smart punctuation.

    Returns:
        Escaped text using only characters the fonts can draw.
    """
    for character, replacement in _SUBSTITUTIONS.items():
        text = text.replace(character, replacement)
    return html.escape(text.strip())


def _styles() -> dict[str, ParagraphStyle]:
    """Build the paragraph styles used throughout the document.

    Returns:
        Mapping of style name to style.
    """
    base = getSampleStyleSheet()["BodyText"]
    body = ParagraphStyle(
        "EkBody",
        parent=base,
        fontName="Helvetica",
        fontSize=9.5,
        leading=13.5,
        textColor=colors.HexColor(theme.CHARCOAL),
        alignment=TA_LEFT,
        spaceAfter=5,
    )
    return {
        "body": body,
        "heading": ParagraphStyle(
            "EkHeading",
            parent=body,
            fontName="Helvetica-Bold",
            fontSize=13,
            leading=17,
            textColor=colors.HexColor(theme.EMIRATES_RED),
            spaceBefore=12,
            spaceAfter=6,
        ),
        "term": ParagraphStyle(
            "EkTerm",
            parent=body,
            fontName="Helvetica-Bold",
            textColor=colors.HexColor(theme.CHARCOAL),
            spaceAfter=1,
        ),
        "cell": ParagraphStyle(
            "EkCell", parent=body, fontSize=8.5, leading=11, spaceAfter=0
        ),
        "cellHead": ParagraphStyle(
            "EkCellHead",
            parent=body,
            fontName="Helvetica-Bold",
            fontSize=8.5,
            leading=11,
            textColor=colors.white,
            spaceAfter=0,
        ),
        "subtitle": ParagraphStyle(
            "EkSubtitle",
            parent=body,
            fontSize=9,
            textColor=colors.HexColor("#6B6B6B"),
            spaceAfter=10,
        ),
    }


def _draw_page(canvas, document) -> None:
    """Paint the branded header band and footer on every page.

    Args:
        canvas: The reportlab canvas.
        document: The document being rendered.
    """
    canvas.saveState()
    width, height = A4

    canvas.setFillColor(colors.HexColor(theme.EMIRATES_RED))
    canvas.rect(0, height - _HEADER_HEIGHT, width, _HEADER_HEIGHT, stroke=0, fill=1)
    canvas.setFillColor(colors.white)
    canvas.setFont("Helvetica-Bold", 11)
    canvas.drawString(
        _PAGE_MARGIN,
        height - _HEADER_HEIGHT + 5.5 * mm,
        _safe(help_content.GUIDE_TITLE),
    )
    canvas.setFont("Helvetica", 8.5)
    canvas.drawRightString(
        width - _PAGE_MARGIN,
        height - _HEADER_HEIGHT + 5.5 * mm,
        f"As of {SNAPSHOT_DATE:%d %b %Y}",
    )

    canvas.setFillColor(colors.HexColor("#8A8A8A"))
    canvas.setFont("Helvetica", 8)
    canvas.drawRightString(
        width - _PAGE_MARGIN, 10 * mm, f"Page {document.page}"
    )
    canvas.setStrokeColor(colors.HexColor(theme.NEUTRAL_GRAY))
    canvas.line(_PAGE_MARGIN, 14 * mm, width - _PAGE_MARGIN, 14 * mm)
    canvas.restoreState()


def _table_flowable(
    block: help_content.Table, styles: dict[str, ParagraphStyle], width: float
) -> Table:
    """Render a content table as a themed reportlab table.

    Args:
        block: The table to render.
        styles: Paragraph styles.
        width: Available frame width.

    Returns:
        The configured table flowable.
    """
    keep = [i for i in range(len(block.headers)) if i not in block.pdf_drop]
    headers = [block.headers[i] for i in keep]

    data = [
        [Paragraph(_safe(h), styles["cellHead"]) for h in headers]
    ]
    for row in block.rows:
        cells = []
        for position, index in enumerate(keep):
            text = _safe(row[index])
            style = styles["cell"]
            if index == block.colour_column:
                colour = theme.CATEGORY_COLORS.get(row[index].strip())
                if colour:
                    style = ParagraphStyle(
                        f"EkCell{row[index]}",
                        parent=styles["cell"],
                        fontName="Helvetica-Bold",
                        textColor=colors.HexColor(colour),
                    )
            del position
            cells.append(Paragraph(text, style))
        data.append(cells)

    # Give the widest text column the slack; the rest share evenly.
    column_count = len(headers)
    weights = [1.6 if i == 0 else 3.0 for i in range(column_count)]
    total = sum(weights)
    widths = [width * w / total for w in weights]

    table = Table(data, colWidths=widths, repeatRows=1, hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(theme.EMIRATES_RED)),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor(theme.NEUTRAL_GRAY)),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                (
                    "ROWBACKGROUNDS",
                    (0, 1),
                    (-1, -1),
                    [colors.white, colors.HexColor(theme.CREAM)],
                ),
            ]
        )
    )
    return table


def _block_flowables(
    block: help_content.Block,
    styles: dict[str, ParagraphStyle],
    width: float,
) -> list:
    """Convert one content block into reportlab flowables.

    Args:
        block: The block to render.
        styles: Paragraph styles.
        width: Available frame width.

    Returns:
        Flowables for the block.
    """
    if isinstance(block, help_content.Para):
        return [Paragraph(_safe(block.text), styles["body"])]

    if isinstance(block, help_content.Bullets):
        items = [
            ListItem(
                Paragraph(_safe(item), styles["body"]), leftIndent=12
            )
            for item in block.items
        ]
        return [
            ListFlowable(
                items,
                bulletType="1" if block.numbered else "bullet",
                bulletFormat="%s." if block.numbered else None,
                bulletColor=colors.HexColor(theme.EMIRATES_RED),
                leftIndent=14,
                bulletFontSize=8,
            ),
            Spacer(1, 4),
        ]

    if isinstance(block, help_content.Definitions):
        flowables = []
        for term, meaning in block.items:
            flowables.append(
                KeepTogether(
                    [
                        Paragraph(_safe(term), styles["term"]),
                        Paragraph(_safe(meaning), styles["body"]),
                    ]
                )
            )
        return flowables

    if isinstance(block, help_content.Table):
        return [_table_flowable(block, styles, width), Spacer(1, 6)]

    return []


def build_pdf(ml: dict | None = None) -> bytes:
    """Render the whole guide to PDF.

    Args:
        ml: Live model metrics from the current session, if available.

    Returns:
        The PDF document as bytes, ready for a download button.
    """
    buffer = BytesIO()
    styles = _styles()

    document = BaseDocTemplate(
        buffer,
        pagesize=A4,
        title=help_content.GUIDE_TITLE,
        author="Flight Prioritization Dashboard",
        leftMargin=_PAGE_MARGIN,
        rightMargin=_PAGE_MARGIN,
        topMargin=_HEADER_HEIGHT + 8 * mm,
        bottomMargin=20 * mm,
    )
    frame = Frame(
        document.leftMargin,
        document.bottomMargin,
        document.width,
        document.height,
        id="body",
    )
    document.addPageTemplates(
        [PageTemplate(id="themed", frames=[frame], onPage=_draw_page)]
    )

    story: list = [
        Paragraph(
            _safe(
                "A reference for the risk model, the columns, the filters and "
                "the recommended daily workflow. Generated from the running "
                "dashboard, so the scoring bands below are the ones actually "
                "in force."
            ),
            styles["subtitle"],
        )
    ]
    for number, section in enumerate(help_content.sections(ml=ml), start=1):
        story.append(
            Paragraph(f"{number}. {_safe(section.title)}", styles["heading"])
        )
        for block in section.blocks:
            story.extend(_block_flowables(block, styles, document.width))

    document.build(story)
    return buffer.getvalue()
