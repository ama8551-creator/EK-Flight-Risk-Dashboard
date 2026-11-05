"""Run the dashboard script headlessly and assert it renders without errors.

Uses Streamlit's AppTest harness, which executes ``app.py`` the same way the
server does, so genuine runtime exceptions surface here. Development aid, not
part of the dashboard. Run with ``python smoke_test.py``.
"""

from __future__ import annotations

import sys

from streamlit.testing.v1 import AppTest

from data_loader import filter_options, load_flights

RUN_TIMEOUT_SECONDS = 240


def main() -> int:
    """Execute the app and report any exceptions it raised."""
    app = AppTest.from_file("app.py", default_timeout=RUN_TIMEOUT_SECONDS)
    app.run()

    if app.exception:
        print("FAIL: the app raised during render")
        for exception in app.exception:
            print(f"  {exception.value}")
        return 1

    print("OK: app rendered without exceptions")
    print(f"  tabs:            {len(app.tabs)}")
    print(f"  dataframes:      {len(app.dataframe)}")
    print(f"  sidebar selects: {len(app.sidebar.multiselect)}")
    print(f"  sidebar dates:   {len(app.sidebar.date_input)}")
    print(f"  sidebar sliders: {len(app.sidebar.slider)}")

    # Five top-level tabs plus two Flight Analysis sub-tabs.
    expected_tabs = 7
    if len(app.tabs) != expected_tabs:
        print(f"FAIL: expected {expected_tabs} tabs, found {len(app.tabs)}")
        return 1

    # Every multi-select must start empty, since empty means "show all".
    preselected = [
        select.label for select in app.sidebar.multiselect if select.value
    ]
    if preselected:
        print(f"FAIL: these filters are pre-selected on load: {preselected}")
        return 1
    print("  all multi-selects start empty (empty = show all)")

    options = filter_options(load_flights())
    print(f"  route cities:    {options['cities']}")
    print(f"  directions:      {len(options['directions'])} ({', '.join(options['directions'])})")
    print(f"  POS countries:   {options['pos_countries']}")
    if "SA" not in options["pos_countries"]:
        print("FAIL: POS filter is missing SA even though POS_SA is in the dataset")
        return 1
    if not options["cities"] or not options["directions"]:
        print("FAIL: Route or Direction options are empty")
        return 1
    sample_city = options["cities"][0]
    sample_direction = next(
        direction
        for direction in options["directions"]
        if sample_city in direction
    )

    # Narrowing to one city must reduce, not empty, the table.
    app.sidebar.multiselect(key="flt_cities").set_value([sample_city]).run()
    if app.exception:
        print("FAIL: raised after narrowing the Route filter")
        for exception in app.exception:
            print(f"  {exception.value}")
        return 1
    print("  Route filter (city level) applied cleanly")

    # Route and Direction must combine rather than conflict.
    app.sidebar.multiselect(key="flt_directions").set_value(
        [sample_direction]
    ).run()
    if app.exception:
        print("FAIL: raised combining Route with Direction")
        for exception in app.exception:
            print(f"  {exception.value}")
        return 1
    print("  Route + Direction combined cleanly")

    app.sidebar.multiselect(key="flt_periods").set_value(["Christmas"]).run()
    if app.exception:
        print("FAIL: raised after selecting a consolidated period")
        for exception in app.exception:
            print(f"  {exception.value}")
        return 1
    print("  consolidated Period filter applied cleanly")

    app.sidebar.multiselect(key="flt_dow").set_value(["6 (Sat)"]).run()
    if app.exception:
        print("FAIL: raised after selecting a day of week")
        for exception in app.exception:
            print(f"  {exception.value}")
        return 1
    print("  Day of Week filter applied cleanly")

    clear = [b for b in app.sidebar.button if "Clear" in b.label]
    if not clear:
        print("FAIL: no 'Clear all filters' button found")
        return 1
    clear[0].click().run()
    if app.exception:
        print("FAIL: raised after 'Clear all filters'")
        for exception in app.exception:
            print(f"  {exception.value}")
        return 1
    still_set = [s.label for s in app.sidebar.multiselect if s.value]
    if still_set:
        print(f"FAIL: 'Clear all' left these set: {still_set}")
        return 1
    print("  'Clear all filters' reset every selection")

    app.sidebar.multiselect(key="flt_underperforming").set_value(["Yes"]).run()
    if app.exception:
        print("FAIL: raised after selecting Underperforming vs LY")
        for exception in app.exception:
            print(f"  {exception.value}")
        return 1
    print("  Underperforming vs LY filter applied cleanly")

    app.sidebar.multiselect(key="flt_underperforming").set_value([]).run()
    app.sidebar.multiselect(key="flt_pos").set_value(["AE"]).run()
    if app.exception:
        print("FAIL: raised after selecting Point of Sale")
        for exception in app.exception:
            print(f"  {exception.value}")
        return 1
    print("  Point of Sale filter applied cleanly")

    analysis_route = app.multiselect(key="analysis_route_cities")
    if list(analysis_route.options) != options["cities"]:
        print(
            "FAIL: Flight Analysis Route options "
            f"{list(analysis_route.options)} != {options['cities']}"
        )
        return 1
    print("  Flight Analysis Route options match the dataset")

    other_city = next(
        (city for city in options["cities"] if city != sample_city), None
    )
    if other_city is None:
        print("FAIL: need at least two route cities to test intersect")
        return 1
    app.sidebar.multiselect(key="flt_pos").set_value([]).run()
    app.sidebar.multiselect(key="flt_cities").set_value([sample_city]).run()
    app.multiselect(key="analysis_route_cities").set_value([other_city]).run()
    if app.exception:
        print("FAIL: raised on disjoint tab-level and sidebar Route")
        for exception in app.exception:
            print(f"  {exception.value}")
        return 1
    print("  disjoint tab-level and sidebar Route filters applied cleanly")

    # No column or filter may carry a hover tooltip: the Help & Guide tab is
    # the single place explanations live.
    tooltipped = [
        widget.label
        for group in (app.sidebar.multiselect, app.sidebar.slider, app.button)
        for widget in group
        if getattr(widget.proto, "help", "")
    ]
    if tooltipped:
        print(f"FAIL: these widgets still have tooltips: {tooltipped}")
        return 1
    print("  no filter or button carries a hover tooltip")

    # Playback must advance the replay date and stop at the snapshot date.
    play = [b for b in app.button if "Play" in b.label]
    if not play:
        print("FAIL: no replay Play button found")
        return 1
    play[0].click().run()
    if app.exception:
        print("FAIL: raised after starting replay playback")
        for exception in app.exception:
            print(f"  {exception.value}")
        return 1
    # AppTest's session_state proxies attributes to keys, so no .get().
    if not app.session_state["replay_playing"]:
        print("FAIL: Play did not set the playing flag")
        return 1
    print(f"  replay playback started, as-of = {app.session_state['replay_date']}")

    pause = [b for b in app.button if "Pause" in b.label]
    pause[0].click().run()
    if app.session_state["replay_playing"]:
        print("FAIL: Pause did not stop playback")
        return 1
    print("  replay playback paused")

    return 0


if __name__ == "__main__":
    sys.exit(main())
