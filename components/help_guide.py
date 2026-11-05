"""The Help & Guide tab: every explanation in the dashboard, in one place.

Deliberately the *only* place explanations live. No column or filter carries a
hover tooltip, because a tooltip hides the thing it explains behind a gesture
the analyst has to already know to make, and it cannot be read away from the
screen. A single reference section can be skimmed, searched and printed.

Content comes from :mod:`help_content` and the PDF from :mod:`help_pdf`, so
the tab, the document and the running model all agree by construction.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

import help_content
import help_pdf


def _render_table(block: help_content.Table) -> None:
    """Draw a content table.

    Args:
        block: The table to draw.
    """
    st.dataframe(
        pd.DataFrame(list(block.rows), columns=list(block.headers)),
        width="stretch",
        hide_index=True,
    )


def _render_block(block: help_content.Block) -> None:
    """Draw one content block.

    Args:
        block: The block to draw.
    """
    if isinstance(block, help_content.Para):
        st.markdown(block.text)
    elif isinstance(block, help_content.Bullets):
        for index, item in enumerate(block.items, start=1):
            marker = f"{index}." if block.numbered else "-"
            st.markdown(f"{marker} {item}")
    elif isinstance(block, help_content.Definitions):
        for term, meaning in block.items:
            st.markdown(f"**{term}** — {meaning}")
    elif isinstance(block, help_content.Table):
        _render_table(block)


def render(ml_metrics: dict | None = None) -> None:
    """Draw the Help & Guide tab.

    Args:
        ml_metrics: Live model scores from the current session.
    """
    st.markdown(
        "Everything the dashboard assumes you know, written down. "
        "Nothing here is hidden behind a hover tooltip."
    )

    sections = help_content.sections(ml=ml_metrics)
    for number, section in enumerate(sections, start=1):
        with st.expander(
            f"Section {number}: {section.title}", expanded=section.expanded
        ):
            for block in section.blocks:
                _render_block(block)

    st.divider()
    st.markdown(f"#### Section {len(sections) + 1}: Download PDF version")
    st.markdown(
        "The whole guide as a themed document, generated from this running "
        "dashboard rather than written separately."
    )

    try:
        document = help_pdf.build_pdf(ml=ml_metrics)
    except Exception as error:  # noqa: BLE001 - surfaced to the analyst
        # A missing or broken PDF backend must not take the tab down with it;
        # the on-screen guide above is the primary copy.
        st.warning(
            "The PDF could not be generated, so the on-screen guide above is "
            f"the only copy right now. Reason: {error}"
        )
        return

    st.download_button(
        "Download PDF guide",
        data=document,
        file_name=help_content.PDF_FILENAME,
        mime="application/pdf",
        type="primary",
    )
    st.caption(f"{len(document) / 1024:.0f} KB · {help_content.PDF_FILENAME}")
