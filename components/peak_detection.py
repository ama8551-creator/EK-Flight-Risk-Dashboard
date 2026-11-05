"""Peak Detection tab — review, accept, and store recurring demand peaks."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any, Final

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import approved_peaks
import ml_pipeline
import ml_runtime
import peak_detector
import utils
from data_loader import (
    SNAPSHOT_DATE,
    STATUS_FLOWN,
    filter_options,
    infer_hub,
    outstation,
)
from styling import theme

_REC_KEY: Final[str] = "peak_recommendations"
_REJECTED_KEY: Final[str] = "peak_rejected_ids"
_VERIFY_KEY: Final[str] = "peak_verify_id"
_EDIT_KEY: Final[str] = "peak_edit_id"
_MANUAL_OPEN_KEY: Final[str] = "peak_manual_open"

DOW_PATTERN_OPTIONS: Final[tuple[str, ...]] = (
    "Full Week",
    "Thu-Sat (Outbound)",
    "Sat-Mon (Return)",
    "Weekdays Only (Sun-Thu)",
    "Weekends Only (Fri-Sat)",
    "Custom",
)

SOURCE_AI: Final[str] = "ai"
SOURCE_MANUAL: Final[str] = "manual"


def _hub(flights: pd.DataFrame) -> str:
    """Hub airport inferred from the loaded routes."""
    return infer_hub(flights["Route"].dropna().unique())


def _month_day(value: date) -> str:
    """Format a date as ``MM-DD`` for storage."""
    return value.strftime("%m-%d")


def _format_month_day(month_day: str) -> str:
    """Pretty-print ``MM-DD`` as ``01 Jan``."""
    try:
        return datetime.strptime(f"2026-{month_day}", "%Y-%m-%d").strftime("%d %b")
    except ValueError:
        return month_day


def _to_record(peak: peak_detector.DetectedPeak, name: str, start: date, end: date) -> dict[str, Any]:
    """Build an approved-peaks.json record from a recommendation."""
    first, last = sorted((start, end))
    start, end = first, last
    return {
        "id": peak.id,
        "name": name.strip() or peak.name,
        "route": peak.route,
        "direction": peak.direction,
        "start_month_day": _month_day(start),
        "end_month_day": _month_day(end),
        "dow_pattern": peak.dow_pattern,
        "source": SOURCE_AI,
        "notes": "",
        "accepted_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
    }


def _filter_fln(
    flights: pd.DataFrame,
    *,
    city: str,
    directions: list[str],
    date_from: date,
    date_to: date,
    pos_codes: list[str],
    flight_numbers: list[str],
) -> pd.DataFrame:
    """Flown legs matching the Peak Detection selectors."""
    hub = _hub(flights)
    start, end = sorted((pd.Timestamp(date_from), pd.Timestamp(date_to)))
    mask = (
        (flights["Status"] == STATUS_FLOWN)
        & (flights["Dep Date"] >= start)
        & (flights["Dep Date"] <= end)
    )
    mask &= flights["Route"].map(lambda route: outstation(route, hub)) == city
    if directions:
        mask &= flights["Route"].isin(directions)
    if flight_numbers:
        mask &= flights["Flight No"].isin(flight_numbers)
    selected = flights.loc[mask].copy()
    if pos_codes and not selected.empty:
        shares = []
        for code in pos_codes:
            column = f"POS_{code}"
            if column not in selected.columns:
                continue
            shares.append(selected[column].fillna(0) > 0)
        if shares:
            combined = shares[0]
            for extra in shares[1:]:
                combined = combined | extra
            selected = selected.loc[combined]
    return selected


def _render_filters(flights: pd.DataFrame) -> tuple[str | None, list[str], date, date, list[str], list[str]]:
    """Draw the filter row and return the current selection."""
    options = filter_options(flights)
    cities = options["cities"]
    hub = _hub(flights)
    min_date = pd.Timestamp(flights["Dep Date"].min()).date()
    max_date = pd.Timestamp(flights["Dep Date"].max()).date()
    default_from = max(min_date, (SNAPSHOT_DATE - timedelta(days=365)).date())
    default_to = min(max_date, SNAPSHOT_DATE.date())

    row = st.columns([1.1, 1.4, 1.0, 1.0, 1.2, 1.3])
    row[0].markdown("**Route**")
    city = row[0].selectbox(
        "Route",
        options=cities,
        index=None,
        placeholder="Select a route",
        key="peak_route",
        label_visibility="collapsed",
    )
    direction_options = [
        direction
        for direction in options["directions"]
        if city and outstation(direction, hub) == city
    ]
    row[1].markdown("**Direction**")
    directions = row[1].multiselect(
        "Direction",
        options=direction_options,
        default=[],
        key="peak_directions",
        placeholder="Both directions",
        label_visibility="collapsed",
        disabled=not city,
    )
    row[2].markdown("**From**")
    date_from = row[2].date_input(
        "From",
        value=default_from,
        min_value=min_date,
        max_value=max_date,
        key="peak_date_from",
        label_visibility="collapsed",
    )
    row[3].markdown("**To**")
    date_to = row[3].date_input(
        "To",
        value=default_to,
        min_value=min_date,
        max_value=max_date,
        key="peak_date_to",
        label_visibility="collapsed",
    )
    pos_options = options.get("pos_countries", [])
    row[4].markdown("**POS**")
    pos_codes = row[4].multiselect(
        "POS",
        options=pos_options,
        default=[],
        key="peak_pos",
        placeholder="All markets",
        label_visibility="collapsed",
        disabled=not city,
    )
    flight_options = (
        sorted(
            flights.loc[
                (flights["Status"] == STATUS_FLOWN)
                & flights["Route"].map(lambda route: outstation(route, hub)).eq(city),
                "Flight No",
            ]
            .dropna()
            .unique()
            .tolist()
        )
        if city
        else []
    )
    row[5].markdown("**Flight Number**")
    flight_numbers = row[5].multiselect(
        "Flight Number",
        options=flight_options,
        default=[],
        key="peak_flights",
        placeholder="All flights",
        label_visibility="collapsed",
        disabled=not city,
    )
    return city, directions, date_from, date_to, pos_codes, flight_numbers


def _recommendations() -> list[peak_detector.DetectedPeak]:
    """Session-stored recommendations, minus ones rejected this session."""
    rejected = set(st.session_state.get(_REJECTED_KEY, []))
    stored = st.session_state.get(_REC_KEY, [])
    return [
        peak_detector.DetectedPeak.from_dict(item)
        for item in stored
        if item.get("id") not in rejected
    ]


def _render_card(peak: peak_detector.DetectedPeak) -> None:
    """One recommendation with editable name/dates and Accept / Reject."""
    st.markdown(
        f"""
        <div class="ek-peak-card">
          <div class="ek-peak-card-title">{peak.direction}</div>
          <div>
            <span class="ek-peak-badge">{peak.dow_pattern}</span>
            <span class="ek-peak-badge">{peak.confidence} confidence</span>
          </div>
          <div class="ek-peak-meta">
            Avg Total BSF {utils.format_pct(peak.avg_bsf)} ·
            {peak.flight_count:,} flown flights
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    name = st.text_input(
        "Peak name",
        value=peak.name,
        key=f"peak_name_{peak.id}",
    )
    dates = st.columns(2)
    start = dates[0].date_input(
        "Start",
        value=peak.start,
        key=f"peak_start_{peak.id}",
    )
    end = dates[1].date_input(
        "End",
        value=peak.end,
        key=f"peak_end_{peak.id}",
    )
    actions = st.columns(3)
    if actions[0].button("Accept", type="primary", key=f"peak_accept_{peak.id}", width="stretch"):
        approved_peaks.upsert_approved_peak(_to_record(peak, name, start, end))
        rejected = list(st.session_state.get(_REJECTED_KEY, []))
        rejected.append(peak.id)
        st.session_state[_REJECTED_KEY] = rejected
        st.rerun()
    if actions[1].button("Reject", key=f"peak_reject_{peak.id}", width="stretch"):
        rejected = list(st.session_state.get(_REJECTED_KEY, []))
        rejected.append(peak.id)
        st.session_state[_REJECTED_KEY] = rejected
        st.rerun()
    if actions[2].button("Review flights", key=f"peak_verify_{peak.id}", width="stretch"):
        st.session_state[_VERIFY_KEY] = peak.id
        st.rerun()


def _verification_table(fln: pd.DataFrame, peak: peak_detector.DetectedPeak) -> pd.DataFrame:
    """Flown flights inside the peak window, for the evidence table."""
    start, end = sorted((pd.Timestamp(peak.start), pd.Timestamp(peak.end)))
    rows = fln[
        (fln["Route"] == peak.direction)
        & (fln["Dep Date"] >= start)
        & (fln["Dep Date"] <= end)
    ].copy()
    if rows.empty:
        return rows
    table = rows[
        [
            "Dep Date",
            "DOW Label",
            "Flight No",
            "Route",
            "F BSF",
            "J BSF",
            "Y BSF",
            "Total BSF",
            "Period",
        ]
    ].sort_values(["Dep Date", "Flight No"])
    table = table.rename(columns={"DOW Label": "DOW", "Period": "Period (originally assigned)"})
    table["Dep Date"] = table["Dep Date"].dt.date
    return table.reset_index(drop=True)


def _daily_chart(fln: pd.DataFrame, peak: peak_detector.DetectedPeak) -> go.Figure:
    """Daily average Total BSF across the verification window."""
    start, end = sorted((pd.Timestamp(peak.start), pd.Timestamp(peak.end)))
    rows = fln[
        (fln["Route"] == peak.direction)
        & (fln["Dep Date"] >= start)
        & (fln["Dep Date"] <= end)
    ]
    daily = (
        rows.groupby(rows["Dep Date"].dt.date)["Total BSF"].mean()
        if not rows.empty
        else pd.Series(dtype=float)
    )
    figure = go.Figure()
    if not daily.empty:
        figure.add_trace(
            go.Scatter(
                x=[str(day) for day in daily.index],
                y=list(daily.values),
                mode="lines+markers",
                name="Avg Total BSF",
                line={"color": theme.EMIRATES_RED, "width": 2.5},
                marker={"size": 7, "color": theme.EMIRATES_RED},
            )
        )
    figure.add_hline(
        y=peak_detector.PEAK_BSF_THRESHOLD,
        line_dash="dash",
        line_color=theme.CHARCOAL,
        annotation_text="85% threshold",
        annotation_position="top left",
    )
    figure.update_yaxes(title="Average total booked seat factor", tickformat=".0%", range=[0, 1.20])
    figure.update_xaxes(title="Departure date")
    figure.update_layout(**theme.plotly_layout(height=360))
    return figure


def _render_verification(fln: pd.DataFrame, peak: peak_detector.DetectedPeak) -> None:
    """Section B: last-year flights and the daily BSF chart."""
    table = _verification_table(fln, peak)
    year = peak.start.year
    if table.empty:
        st.markdown(
            utils.empty_state("No flown flights in this window."),
            unsafe_allow_html=True,
        )
        return
    peak_day = table.loc[table["Total BSF"].idxmax()]
    st.markdown(f"#### Verification: {peak.name} — Last Year Data")
    st.caption(
        f"Over this period in {year}, {len(table):,} flights departed with "
        f"an average Total BSF of {utils.format_pct(float(table['Total BSF'].mean()))} "
        f"and a peak day of {peak_day['Dep Date']:%d %b %Y} at "
        f"{utils.format_pct(float(peak_day['Total BSF']))}."
    )
    st.dataframe(
        table.style.format(
            {
                "F BSF": lambda v: utils.format_pct(v),
                "J BSF": lambda v: utils.format_pct(v),
                "Y BSF": lambda v: utils.format_pct(v),
                "Total BSF": lambda v: utils.format_pct(v),
            }
        ),
        width="stretch",
        hide_index=True,
    )
    st.plotly_chart(_daily_chart(fln, peak), width="stretch")


def _source_label(peak: dict[str, Any]) -> str:
    """Human-readable source badge for an approved peak."""
    source = str(peak.get("source", SOURCE_AI)).lower()
    return "Manual" if source == SOURCE_MANUAL else "AI-Detected"


def _render_manual_form(flights: pd.DataFrame) -> None:
    """Form to add a peak the detector did not recommend."""
    options = filter_options(flights)
    hub = _hub(flights)
    cities = options["cities"]
    min_date = pd.Timestamp(flights["Dep Date"].min()).date()
    max_date = pd.Timestamp(flights["Dep Date"].max()).date()
    default_start = min(max(SNAPSHOT_DATE.date(), min_date), max_date)

    city = st.selectbox(
        "Route",
        options=cities,
        index=None,
        placeholder="Select a route",
        key="peak_manual_route",
    )
    direction_options = [
        direction
        for direction in options["directions"]
        if city and outstation(direction, hub) == city
    ]
    directions = st.multiselect(
        "Direction",
        options=direction_options,
        default=[],
        key="peak_manual_dirs",
        placeholder="Both directions",
        disabled=not city,
    )
    name = st.text_input("Peak Name", key="peak_manual_name")
    date_cols = st.columns(2)
    start = date_cols[0].date_input(
        "Start Date",
        value=default_start,
        min_value=min_date,
        max_value=max_date,
        key="peak_manual_start",
    )
    end = date_cols[1].date_input(
        "End Date",
        value=default_start,
        min_value=min_date,
        max_value=max_date,
        key="peak_manual_end",
    )
    pattern = st.selectbox(
        "DOW Pattern",
        options=list(DOW_PATTERN_OPTIONS),
        index=0,
        key="peak_manual_dow",
    )
    if pattern == "Custom":
        custom = st.text_input("Custom DOW pattern", key="peak_manual_dow_custom")
        pattern = custom.strip() or "Custom"
    notes = st.text_area("Notes", key="peak_manual_notes")
    actions = st.columns(2)
    if actions[0].button("Save", type="primary", key="peak_manual_save"):
        if not city:
            st.warning("Route is required.")
        elif not str(name).strip():
            st.warning("Peak name is required.")
        elif end < start:
            st.warning("End Date must be on or after Start Date.")
        else:
            chosen = directions or direction_options
            if not chosen:
                st.warning("No directions are available for that route.")
            else:
                first, last = sorted((start, end))
                for direction in chosen:
                    approved_peaks.upsert_approved_peak(
                        {
                            "id": str(uuid.uuid4()),
                            "name": str(name).strip(),
                            "route": city,
                            "direction": direction,
                            "start_month_day": _month_day(first),
                            "end_month_day": _month_day(last),
                            "dow_pattern": pattern,
                            "source": SOURCE_MANUAL,
                            "notes": str(notes).strip(),
                            "accepted_at": datetime.now(timezone.utc)
                            .replace(microsecond=0)
                            .isoformat(),
                        }
                    )
                st.session_state[_MANUAL_OPEN_KEY] = False
                st.rerun()
    if actions[1].button("Cancel", key="peak_manual_cancel"):
        st.session_state[_MANUAL_OPEN_KEY] = False
        st.rerun()


def _render_approved(flights: pd.DataFrame) -> None:
    """Section C: persisted accepted peaks, including manually added ones."""
    st.markdown("#### My Approved Peaks")
    if st.button("+ Add New Peak Manually", key="peak_manual_open_btn"):
        st.session_state[_MANUAL_OPEN_KEY] = True
        st.rerun()
    if st.session_state.get(_MANUAL_OPEN_KEY):
        with st.expander("Add Peak Manually", expanded=True):
            _render_manual_form(flights)

    peaks = approved_peaks.load_approved_peaks()
    if not peaks:
        st.caption("No peaks accepted yet. Accept a recommendation or add one manually.")
        return

    edit_id = st.session_state.get(_EDIT_KEY)
    rows = []
    for peak in peaks:
        rows.append(
            {
                "id": peak.get("id", ""),
                "Peak Name": peak.get("name", ""),
                "Route": peak.get("route", ""),
                "Direction": peak.get("direction", ""),
                "Start Date": _format_month_day(str(peak.get("start_month_day", ""))),
                "End Date": _format_month_day(str(peak.get("end_month_day", ""))),
                "DOW Pattern": peak.get("dow_pattern", ""),
                "Source": _source_label(peak),
                "Accepted At": str(peak.get("accepted_at", "")),
            }
        )
    st.dataframe(
        pd.DataFrame(rows).drop(columns=["id"]),
        width="stretch",
        hide_index=True,
    )

    for peak in peaks:
        peak_id = str(peak.get("id", ""))
        label = (
            f"{peak.get('name', '')} · {peak.get('direction', '')} · "
            f"{_source_label(peak)}"
        )
        cols = st.columns([4, 1, 1])
        cols[0].markdown(label)
        if cols[1].button("Edit", key=f"peak_edit_{peak_id}", width="stretch"):
            st.session_state[_EDIT_KEY] = peak_id
            st.rerun()
        if cols[2].button("Delete", key=f"peak_del_{peak_id}", width="stretch"):
            approved_peaks.delete_approved_peak(peak_id)
            if st.session_state.get(_EDIT_KEY) == peak_id:
                st.session_state[_EDIT_KEY] = None
            st.rerun()
        if edit_id == peak_id:
            name = st.text_input(
                "Name",
                value=str(peak.get("name", "")),
                key=f"peak_edit_name_{peak_id}",
            )
            start_md = st.text_input(
                "Start (MM-DD)",
                value=str(peak.get("start_month_day", "")),
                key=f"peak_edit_start_{peak_id}",
            )
            end_md = st.text_input(
                "End (MM-DD)",
                value=str(peak.get("end_month_day", "")),
                key=f"peak_edit_end_{peak_id}",
            )
            pattern = st.selectbox(
                "DOW pattern",
                options=list(DOW_PATTERN_OPTIONS),
                index=(
                    list(DOW_PATTERN_OPTIONS).index(str(peak.get("dow_pattern", "")))
                    if str(peak.get("dow_pattern", "")) in DOW_PATTERN_OPTIONS
                    else 0
                ),
                key=f"peak_edit_dow_{peak_id}",
            )
            notes = st.text_area(
                "Notes",
                value=str(peak.get("notes", "")),
                key=f"peak_edit_notes_{peak_id}",
            )
            save_cols = st.columns(2)
            if save_cols[0].button("Save", type="primary", key=f"peak_save_{peak_id}"):
                updated = dict(peak)
                updated["name"] = name.strip() or updated.get("name", "")
                updated["start_month_day"] = start_md.strip()
                updated["end_month_day"] = end_md.strip()
                updated["dow_pattern"] = pattern
                updated["notes"] = notes.strip()
                approved_peaks.upsert_approved_peak(updated)
                st.session_state[_EDIT_KEY] = None
                st.rerun()
            if save_cols[1].button("Cancel", key=f"peak_cancel_{peak_id}"):
                st.session_state[_EDIT_KEY] = None
                st.rerun()


def _render_cluster_summary(cluster: ml_pipeline.ClusterBundle | None) -> None:
    """Show the K-Means badge, silhouette score, and cluster sizes."""
    st.markdown(
        "<span class='ek-ml-badge'>ML Model: K-Means Clustering "
        "(3 clusters)</span>",
        unsafe_allow_html=True,
    )
    if cluster is None or cluster.n_weeks == 0:
        st.caption("Cluster metrics appear after Detect Peaks has enough flown weeks.")
        return
    silhouette = (
        "—"
        if pd.isna(cluster.silhouette)
        else f"{cluster.silhouette:.3f}"
    )
    sizes = cluster.sizes
    st.caption(f"Silhouette score: {silhouette}")
    st.caption(
        "Cluster sizes — "
        f"Peak: {sizes.get('Peak', 0):,}, "
        f"Shoulder: {sizes.get('Shoulder', 0):,}, "
        f"Off-Peak: {sizes.get('Off-Peak', 0):,} "
        f"({cluster.n_weeks:,} week-direction groups)"
    )


def render(flights: pd.DataFrame) -> None:
    """Draw the Peak Detection tab.

    Args:
        flights: Full preprocessed frame from ``data_loader.load_flights``.
    """
    st.info(
        "Approved peaks override the default peak calendar used across the "
        "dashboard."
    )
    _render_cluster_summary(st.session_state.get(ml_runtime.CLUSTER_KEY))
    st.markdown(
        "Detect recurring high-demand periods from flown history, then "
        "accept, adjust, or reject each recommendation."
    )

    city, directions, date_from, date_to, pos_codes, flight_numbers = _render_filters(
        flights
    )
    detect = st.button("Detect Peaks", type="primary", key="peak_detect")

    if detect:
        if not city:
            st.warning("Select a route before detecting peaks.")
        else:
            fln = _filter_fln(
                flights,
                city=city,
                directions=directions,
                date_from=date_from,
                date_to=date_to,
                pos_codes=pos_codes,
                flight_numbers=flight_numbers,
            )
            found, cluster = peak_detector.detect_peaks(fln, hub=_hub(flights))
            ml_runtime.store_cluster(cluster)
            st.session_state[_REC_KEY] = [peak.as_dict() for peak in found]
            st.session_state[_REJECTED_KEY] = []
            st.session_state[_VERIFY_KEY] = None
            st.rerun()

    recommendations = _recommendations()
    st.markdown("#### AI-Detected Peak Recommendations")
    if not st.session_state.get(_REC_KEY):
        st.caption("Set a route and click Detect Peaks to generate recommendations.")
    elif not recommendations:
        st.caption("No remaining recommendations. Rejected cards are hidden for this session.")
    else:
        for peak in recommendations:
            _render_card(peak)

    verify_id = st.session_state.get(_VERIFY_KEY)
    if verify_id:
        match = next((peak for peak in recommendations if peak.id == verify_id), None)
        if match is None:
            stored = st.session_state.get(_REC_KEY, [])
            raw = next((item for item in stored if item.get("id") == verify_id), None)
            match = peak_detector.DetectedPeak.from_dict(raw) if raw else None
        if match is not None and city:
            evidence = _filter_fln(
                flights,
                city=city,
                directions=[match.direction],
                date_from=match.start,
                date_to=match.end,
                pos_codes=pos_codes,
                flight_numbers=flight_numbers,
            )
            _render_verification(evidence, match)

    st.divider()
    _render_approved(flights)
