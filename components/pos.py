"""Point of Sale tab — where the bookings on visible flights originated.

POS columns are passenger counts by country of sale. They sum to ``Total Bkg``
on every row. This tab aggregates the currently filtered view; it does not
re-score risk.
"""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

import utils
from components import kpi_cards
from data_loader import POS_NAMES, pos_code, pos_columns_in
from styling import theme


def _active_pos(df: pd.DataFrame) -> list[str]:
    """POS columns that have at least one booking in ``df``.

    Args:
        df: Filtered flights.

    Returns:
        Column names in declared order.
    """
    return [
        column
        for column in pos_columns_in(df)
        if pd.to_numeric(df[column], errors="coerce").fillna(0).gt(0).any()
    ]


def _totals(df: pd.DataFrame, columns: list[str]) -> pd.Series:
    """Sum bookings per POS column, largest first.

    Args:
        df: Filtered flights.
        columns: POS columns to include.

    Returns:
        Country-code index, sorted descending.
    """
    totals = (
        df[columns]
        .apply(pd.to_numeric, errors="coerce")
        .fillna(0)
        .sum()
        .rename(pos_code)
    )
    return totals[totals > 0].sort_values(ascending=False)


def _render_kpis(df: pd.DataFrame, totals: pd.Series) -> None:
    """Draw the five POS summary cards.

    Args:
        df: Filtered flights.
        totals: Bookings by country code, descending.
    """
    grand = int(df["Total Bkg"].sum()) if not df.empty else 0
    unique = int((totals > 0).sum())

    def country_card(rank: int) -> str:
        """One of the top-three country cards, or an empty placeholder."""
        if rank >= len(totals):
            return kpi_cards.card(
                f"#{rank + 1} POS",
                "–",
                "No bookings",
                accent=theme.NEUTRAL_GRAY,
            )
        code = str(totals.index[rank])
        bookings = int(totals.iloc[rank])
        share = bookings / grand if grand else 0
        colour = theme.pos_color(code)
        name = POS_NAMES.get(code, code)
        return kpi_cards.card(
            f"#{rank + 1} POS · {code}",
            f"{bookings:,}",
            f"{name} · {share:.1%} of bookings",
            accent=colour,
            value_color=colour,
        )

    cards = [
        kpi_cards.card(
            "Total bookings",
            f"{grand:,}",
            "Across filtered flights",
            accent=theme.CHARCOAL,
        ),
        country_card(0),
        country_card(1),
        country_card(2),
        kpi_cards.card(
            "POS countries",
            f"{unique:,}",
            "With at least one booking",
            accent=theme.CHARCOAL,
        ),
    ]
    for column, html in zip(st.columns(len(cards)), cards):
        column.markdown(html, unsafe_allow_html=True)


def _donut_figure(totals: pd.Series) -> object:
    """Build a donut with room above for small-slice leader labels.

    Plotly's default legend sits on top of the pie and clips labels such as
    DE / LB / GB. Legend goes below; the top margin leaves ≥40px of air.
    """
    pie = totals.reset_index()
    pie.columns = ["Country", "Bookings"]
    figure = px.pie(
        pie,
        names="Country",
        values="Bookings",
        color="Country",
        color_discrete_map={
            str(code): theme.pos_color(str(code)) for code in pie["Country"]
        },
        hole=0.55,
    )
    figure.update_traces(
        textinfo="percent+label",
        textposition="outside",
        sort=False,
        rotation=90,
        domain={"x": [0.18, 0.82], "y": [0.08, 0.68]},
        outsidetextfont={"size": 11},
    )
    figure.update_layout(
        **theme.plotly_layout(
            height=600,
            showlegend=True,
            margin={"l": 80, "r": 80, "t": 140, "b": 100},
            legend={"orientation": "h", "yanchor": "top", "y": -0.14, "x": 0},
        )
    )
    return figure


def _render_donut(totals: pd.Series) -> None:
    """Donut of POS mix across the filtered view.

    Args:
        totals: Bookings by country code, descending.
    """
    st.markdown("#### Mix across filtered flights")
    st.plotly_chart(_donut_figure(totals), width="stretch")


def _render_table(
    df: pd.DataFrame, columns: list[str], *, export_key: str = "pos_export"
) -> None:
    """Sortable POS table and CSV export.

    Args:
        df: Filtered flights.
        columns: POS columns with data.
        export_key: Widget key for the download button.
    """
    st.markdown("#### Bookings by flight and POS")
    table = df[
        ["Flight No", "Dep Date", "Route", "Total Bkg"] + columns
    ].copy()
    table["Dep Date"] = table["Dep Date"].dt.date
    table = table.sort_values("Total Bkg", ascending=False).reset_index(drop=True)

    header = st.columns([4, 1])
    header[0].caption(
        f"{len(table):,} flights. Only POS countries with bookings are shown."
    )
    header[1].download_button(
        "Export POS CSV",
        data=utils.to_csv_bytes(table),
        file_name="point_of_sale.csv",
        mime="text/csv",
        type="secondary",
        key=export_key,
        width="stretch",
    )
    st.dataframe(table, width="stretch", hide_index=True)


def render(current: pd.DataFrame) -> None:
    """Draw the Point of Sale tab.

    Args:
        current: Filtered, scored open flights in the current view.
    """
    if current.empty:
        st.markdown(utils.empty_state(), unsafe_allow_html=True)
        return

    columns = _active_pos(current)
    if not columns:
        st.markdown(
            utils.empty_state(
                "This dataset has no Point of Sale columns, or every value "
                "is zero in the current view."
            ),
            unsafe_allow_html=True,
        )
        return

    totals = _totals(current, columns)
    st.markdown(
        "Where the bookings on the **currently filtered** flights were sold. "
        "Values are passenger counts; they sum to each flight's total bookings."
    )
    _render_kpis(current, totals)
    st.write("")
    _render_donut(totals)
    st.divider()
    _render_table(current, columns, export_key="pos_tab_export")


def render_flight(row: pd.Series) -> None:
    """Draw the per-flight Point of Sale view for one selected leg.

    Args:
        row: The flight's latest snapshot.
    """
    frame = row.to_frame().T
    columns = _active_pos(frame)
    if not columns:
        st.markdown(
            utils.empty_state(
                "This flight has no Point of Sale bookings in the dataset."
            ),
            unsafe_allow_html=True,
        )
        return

    totals = _totals(frame, columns)
    grand = int(totals.sum())
    countries = int((totals > 0).sum())
    top_code = str(totals.index[0])
    top_share = float(totals.iloc[0]) / grand if grand else 0
    noun = "country" if countries == 1 else "countries"
    st.markdown(
        f"Top market: **{top_code}** ({top_share:.1%}). This flight has "
        f"bookings from **{countries}** {noun}."
    )

    st.plotly_chart(_donut_figure(totals), width="stretch")

    table = pd.DataFrame(
        {
            "Country": totals.index,
            "Market": [POS_NAMES.get(str(code), str(code)) for code in totals.index],
            "Bookings": totals.astype(int).values,
            "Share": (totals / grand).values if grand else 0,
        }
    )
    st.dataframe(
        table.style.format({"Share": "{:.1%}"}),
        width="stretch",
        hide_index=True,
    )


def render_aggregate(current: pd.DataFrame) -> None:
    """Donut, summary and table for every flight in the analysis window.

    Args:
        current: One latest snapshot per flight leg in the selected range.
    """
    if current.empty:
        st.markdown(
            utils.empty_state("No flights match the selected date range."),
            unsafe_allow_html=True,
        )
        return

    columns = _active_pos(current)
    if not columns:
        st.markdown(
            utils.empty_state(
                "These flights have no Point of Sale bookings in the dataset."
            ),
            unsafe_allow_html=True,
        )
        return

    totals = _totals(current, columns)
    st.markdown(
        f"Point of sale across **{len(current):,}** flights in the selected "
        "date range. Values are passenger counts."
    )
    _render_kpis(current, totals)
    st.write("")
    _render_donut(totals)
    st.divider()
    _render_table(current, columns, export_key="analysis_pos_export")
