"""Tab 6 — real-time replay (specification section 6, Tab 6).

Rewinds the dashboard to a past date and rebuilds it from scratch, so an
analyst can watch risk emerge rather than only see where it ended up. This is
the tab that makes the case for the whole dashboard: it shows what a static
weekly report would have missed.

------------------------------------------------------------------------------
What "rewinding" actually involves
------------------------------------------------------------------------------
Nothing is cached from the live view. For each simulated date the pipeline is
re-run end to end:

  1. ``snapshots_as_of`` keeps, per leg, the newest observation on or before
     the simulated date, and drops legs that had already departed.
  2. ``Actual DTD`` is recomputed as ``Dep Date - simulated date``, so urgency
     scoring reflects the time the analyst genuinely had, not the time left
     today.
  3. ``assign_risk`` re-categorises and re-scores from those values.

Step 2 is the one that matters. A flight 45 days out on 15 October was a very
different problem from the same flight today, and scoring it with today's
clock would quietly rewrite history.

------------------------------------------------------------------------------
Playback
------------------------------------------------------------------------------
Streamlit has no timer, so playback uses ``st.fragment(run_every=...)``: the
replay body re-executes once a second and advances the date by the chosen
speed, leaving the rest of the page untouched. Advancing several days per tick
rather than ticking several times per second keeps the rebuild affordable —
each tick rescores the full snapshot set.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Final

import pandas as pd
import streamlit as st

import ml_pipeline
import ml_runtime
import risk_scoring
import utils
from components import filters, kpi_cards, overview_table
from data_loader import SNAPSHOT_DATE, snapshots_as_of
from styling import theme

#: How far back the slider reaches, in days before the snapshot date.
REPLAY_WINDOW_DAYS: Final[int] = 60

#: Playback speeds, as days advanced per tick. 1x is one day per second.
SPEEDS: Final[tuple[int, ...]] = (1, 2, 5)

#: Seconds between automatic advances while playing.
TICK_SECONDS: Final[float] = 1.0

#: Widget and state keys.
DATE_KEY: Final[str] = "replay_date"
PLAYING_KEY: Final[str] = "replay_playing"
SPEED_KEY: Final[str] = "replay_speed"

#: Namespace for the replayed copy of the Overview table.
TABLE_PREFIX: Final[str] = "replay_overview"

REPLAY_START: Final[date] = (
    SNAPSHOT_DATE - pd.Timedelta(days=REPLAY_WINDOW_DAYS)
).date()
REPLAY_END: Final[date] = SNAPSHOT_DATE.date()


def _as_of() -> date:
    """Return the currently simulated date, defaulting to the window start."""
    return st.session_state.get(DATE_KEY, REPLAY_START)


def _set_as_of(value: date) -> None:
    """Move the simulated date, clamped to the replay window.

    Args:
        value: The requested date.
    """
    st.session_state[DATE_KEY] = min(max(value, REPLAY_START), REPLAY_END)


def _play() -> None:
    """Start playback, restarting from the beginning if already at the end."""
    if _as_of() >= REPLAY_END:
        _set_as_of(REPLAY_START)
    st.session_state[PLAYING_KEY] = True


def _pause() -> None:
    """Stop playback."""
    st.session_state[PLAYING_KEY] = False


def _rebuild(
    flights: pd.DataFrame, state: filters.FilterState, as_of: date
) -> pd.DataFrame:
    """Rescore and filter the dataset as it stood on a past date.

    Args:
        flights: Preprocessed frame from ``data_loader.load_flights``.
        state: The sidebar selection, applied to the rebuilt view.
        as_of: The simulated date.

    Returns:
        Scored, filtered legs ranked by risk, as visible on ``as_of``.
    """
    rebuilt = risk_scoring.assign_risk(
        snapshots_as_of(flights, pd.Timestamp(as_of))
    )
    rebuilt = ml_pipeline.apply_classifier(
        rebuilt, st.session_state.get(ml_runtime.CLASSIFIER_KEY)
    )
    return risk_scoring.rank_by_risk(filters.apply_filters(rebuilt, state))


def _render_controls() -> int:
    """Draw the playback controls and return the selected speed.

    Returns:
        Days to advance per tick.
    """
    playing = st.session_state.get(PLAYING_KEY, False)
    controls = st.columns([1, 1, 1, 2, 3])

    controls[0].button(
        "▶ Play",
        on_click=_play,
        disabled=playing,
        width="stretch",
        type="primary",
        key="replay_play",
    )
    controls[1].button(
        "⏸ Pause",
        on_click=_pause,
        disabled=not playing,
        width="stretch",
        type="secondary",
        key="replay_pause",
    )
    controls[2].button(
        "⏮ Reset",
        on_click=lambda: (_pause(), _set_as_of(REPLAY_START)),
        width="stretch",
        type="secondary",
        key="replay_reset",
    )

    controls[3].markdown("**Speed**")
    speed = controls[3].selectbox(
        "Speed",
        options=SPEEDS,
        format_func=lambda s: f"{s}x ({s} day/sec)"
        if s == 1
        else f"{s}x ({s} days/sec)",
        key=SPEED_KEY,
        label_visibility="collapsed",
    )

    status = "playing" if playing else "paused"
    controls[4].markdown(
        f"<div class='ek-kpi-trend' style='color:"
        f"{theme.EMIRATES_RED if playing else '#7A7A7A'};'>"
        f"{'● ' if playing else '■ '}{status}</div>",
        unsafe_allow_html=True,
    )
    return int(speed)


def _render_body(flights: pd.DataFrame, state: filters.FilterState) -> None:
    """Draw the slider, the rebuilt KPI cards and the rebuilt table.

    Called from inside the playback fragment, so this is the part that
    re-executes on every tick.

    Args:
        flights: Preprocessed frame from ``data_loader.load_flights``.
        state: The sidebar selection.
    """
    playing = st.session_state.get(PLAYING_KEY, False)
    speed = int(st.session_state.get(SPEED_KEY, SPEEDS[0]))

    # Advance before the slider is drawn: Streamlit forbids writing a widget's
    # key after the widget exists in the same run.
    if playing:
        if _as_of() >= REPLAY_END:
            _pause()
        else:
            _set_as_of(_as_of() + timedelta(days=speed))

    st.markdown("**As of date**")
    as_of = st.slider(
        "As of date",
        min_value=REPLAY_START,
        max_value=REPLAY_END,
        value=_as_of(),
        step=timedelta(days=1),
        format="YYYY-MM-DD",
        key=DATE_KEY,
        label_visibility="collapsed",
    )

    days_back = (REPLAY_END - as_of).days
    st.caption(
        f"Showing the dashboard as it would have looked on "
        f"**{as_of:%A %d %B %Y}** — {days_back} day(s) before the "
        f"{REPLAY_END:%d %b %Y} snapshot date."
        if days_back
        else f"Showing **{as_of:%A %d %B %Y}**, the live snapshot date."
    )

    ranked = _rebuild(flights, state, as_of)
    if ranked.empty:
        st.markdown(
            utils.empty_state(
                "No flights were visible on this date under the current "
                "filters."
            ),
            unsafe_allow_html=True,
        )
        return

    kpi_cards.render(ranked)
    st.write("")

    overview_table.render(
        ranked,
        key_prefix=TABLE_PREFIX,
        caption=f"**{len(ranked):,} flights** as ranked on {as_of:%d %b %Y}, "
        "scored against the time remaining on that date.",
        export_name=f"flight_priorities_{as_of:%Y%m%d}.csv",
    )


def render(flights: pd.DataFrame, state: filters.FilterState) -> None:
    """Draw the Replay tab.

    Args:
        flights: Preprocessed frame from ``data_loader.load_flights``.
        state: The sidebar selection, applied to the rebuilt view.
    """
    st.markdown(
        "Rewind the dashboard and watch risk build. Every date is rescored "
        "from the snapshots available then, with days-to-departure measured "
        "from that date."
    )

    speed = _render_controls()
    playing = st.session_state.get(PLAYING_KEY, False)

    # run_every is fixed when the fragment is created, so build it per run.
    # Ticking once a second and stepping `speed` days keeps each rebuild
    # affordable, and the fragment is inert while paused.
    interval = TICK_SECONDS if playing else None
    del speed  # Read inside the fragment, from session state.

    body = st.fragment(run_every=interval)(_render_body)
    body(flights, state)
