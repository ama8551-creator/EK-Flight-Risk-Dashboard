"""Screenshot the running dashboard and measure real button contrast.

Renders the app in a headless browser, so the computed styles reflect what a
viewer actually sees rather than what the stylesheet intends. Development aid,
not part of the dashboard. Run with ``python screenshot.py``.
"""

from __future__ import annotations

import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

PORT = 8591
ROOT = Path(__file__).resolve().parent
OUTPUT_DIR = ROOT / "screenshots"

#: WCAG AA needs 4.5:1 for body text; 3.0:1 is the large/UI-component floor.
MIN_CONTRAST = 4.5


def _relative_luminance(rgb: tuple[float, float, float]) -> float:
    """Compute WCAG relative luminance for an sRGB colour."""
    channels = []
    for value in rgb:
        srgb = value / 255
        channels.append(
            srgb / 12.92 if srgb <= 0.03928 else ((srgb + 0.055) / 1.055) ** 2.4
        )
    red, green, blue = channels
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


def _parse_rgb(value: str) -> tuple[float, float, float] | None:
    """Extract an RGB triple from a CSS colour string."""
    if not value or "rgb" not in value:
        return None
    inner = value[value.index("(") + 1 : value.index(")")]
    parts = [p.strip() for p in inner.split(",")]
    if len(parts) < 3:
        return None
    # A fully transparent background tells us nothing useful.
    if len(parts) >= 4 and float(parts[3]) == 0:
        return None
    return tuple(float(p) for p in parts[:3])  # type: ignore[return-value]


def contrast_ratio(foreground: str, background: str) -> float | None:
    """Return the WCAG contrast ratio between two CSS colours."""
    fg, bg = _parse_rgb(foreground), _parse_rgb(background)
    if fg is None or bg is None:
        return None
    light, dark = sorted(
        (_relative_luminance(fg), _relative_luminance(bg)), reverse=True
    )
    return (light + 0.05) / (dark + 0.05)


def _scroll_main(page, offset: int, absolute: bool = False) -> None:
    """Scroll Streamlit's main pane, which scrolls independently of the window.

    Args:
        page: The Playwright page.
        offset: Pixels to scroll.
        absolute: Treat ``offset`` as a position rather than a delta.
    """
    for selector in ('[data-testid="stMain"]', "section.main"):
        element = page.locator(selector)
        if element.count():
            element.first.evaluate(
                "(el, args) => { el.scrollTop = args.absolute "
                "? args.offset : el.scrollTop + args.offset; }",
                {"offset": offset, "absolute": absolute},
            )
            return
    page.evaluate(
        "args => window.scrollTo(0, args.absolute ? args.offset "
        ": window.scrollY + args.offset)",
        {"offset": offset, "absolute": absolute},
    )


def _click_tab(page, name: str, wait_ms: int = 4000) -> None:
    """Switch to a Streamlit tab and wait for it to paint.

    Args:
        page: The Playwright page.
        name: Visible tab label.
        wait_ms: How long to wait after the click.
    """
    tab = page.get_by_role("tab", name=name)
    if tab.count():
        tab.first.click()
        page.wait_for_timeout(wait_ms)
        _scroll_main(page, 0, absolute=True)
        page.wait_for_timeout(600)


def _start_server() -> subprocess.Popen:
    """Launch Streamlit and wait until it answers."""
    process = subprocess.Popen(
        [
            sys.executable, "-m", "streamlit", "run", "app.py",
            "--server.headless", "true",
            "--server.port", str(PORT),
        ],
        cwd=ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    for _ in range(60):
        try:
            with urllib.request.urlopen(f"http://localhost:{PORT}/healthz", timeout=2):
                return process
        except Exception:
            time.sleep(1)
    raise RuntimeError("Streamlit did not start")


def main() -> int:
    """Capture screenshots and audit button contrast."""
    OUTPUT_DIR.mkdir(exist_ok=True)
    server = _start_server()
    failures = 0

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            page = browser.new_page(viewport={"width": 1680, "height": 1050})
            page.goto(f"http://localhost:{PORT}", wait_until="networkidle")
            # Streamlit streams the script result in after first paint.
            page.wait_for_selector("[data-testid='stDataFrame']", timeout=60_000)
            page.wait_for_timeout(2500)

            page.screenshot(path=str(OUTPUT_DIR / "01_dashboard.png"), full_page=False)
            print(f"saved {OUTPUT_DIR / '01_dashboard.png'}")

            # Select a row first, before any sidebar interaction: the table is
            # a canvas grid and hovering the sidebar steals the pointer state
            # needed for the click to land. Row 1 sits ~45px below the top.
            box = page.locator("[data-testid='stDataFrame']").first.bounding_box()
            page.mouse.click(box["x"] + 18, box["y"] + 45)
            page.wait_for_timeout(3500)
            page.screenshot(path=str(OUTPUT_DIR / "03_row_detail.png"))
            print(f"saved {OUTPUT_DIR / '03_row_detail.png'}")
            drill = page.get_by_role("button", name="Open in drill-down")
            if drill.count():
                colours = drill.first.evaluate(
                    "el => { const s = getComputedStyle(el); "
                    "return {fg: s.color, bg: s.backgroundColor}; }"
                )
                primary_ratio = contrast_ratio(colours["fg"], colours["bg"])
                primary_colours = colours
            else:
                primary_ratio, primary_colours = None, None
                print("  row selection did not open the detail panel")
            page.evaluate("() => window.scrollTo(0, 0)")
            page.wait_for_timeout(600)

            sidebar = page.locator("section[data-testid='stSidebar']")
            if sidebar.count():
                sidebar.screenshot(path=str(OUTPUT_DIR / "02_sidebar.png"))
                print(f"saved {OUTPUT_DIR / '02_sidebar.png'}")
                # The "Clear all filters" button sits below the fold.
                sidebar.locator("div").first.evaluate(
                    "el => el.scrollTop = el.scrollHeight"
                )
                page.mouse.move(120, 500)
                page.wait_for_timeout(1200)
                sidebar.screenshot(path=str(OUTPUT_DIR / "02b_sidebar_bottom.png"))
                print(f"saved {OUTPUT_DIR / '02b_sidebar_bottom.png'}")

            # Report whether a sidebar collapse control is present and visible.
            print("\nSidebar collapse control:")
            for selector in (
                "[data-testid='stSidebarCollapseButton']",
                "[data-testid='stExpandSidebarButton']",
                "[data-testid='collapsedControl']",
                "[data-testid='stSidebarCollapsedControl']",
                "[data-testid='stSidebarHeader'] button",
            ):
                locator = page.locator(selector)
                if locator.count():
                    visible = locator.first.is_visible()
                    box = locator.first.bounding_box()
                    print(f"  found {selector}: visible={visible}, box={box}")

            print("\nButton contrast audit:")
            buttons = page.locator("button, div[data-testid='stDownloadButton'] button")
            seen: set[str] = set()
            for index in range(buttons.count()):
                button = buttons.nth(index)
                try:
                    if not button.is_visible():
                        continue
                    label = (button.inner_text() or "").strip().replace("\n", " ")
                    if not label or label in seen:
                        continue
                    seen.add(label)
                    colours = button.evaluate(
                        """el => {
                            const s = getComputedStyle(el);
                            let bg = s.backgroundColor, node = el;
                            while (bg === 'rgba(0, 0, 0, 0)' && node.parentElement) {
                                node = node.parentElement;
                                bg = getComputedStyle(node).backgroundColor;
                            }
                            return {fg: s.color, bg: bg};
                        }"""
                    )
                    ratio = contrast_ratio(colours["fg"], colours["bg"])
                    if ratio is None:
                        continue
                    ok = ratio >= MIN_CONTRAST
                    failures += 0 if ok else 1
                    status = "PASS" if ok else "FAIL"
                    print(
                        f"  [{status}] {ratio:5.2f}:1  {label[:42]:<42} "
                        f"text {colours['fg']} on {colours['bg']}"
                    )
                except Exception:
                    continue

            _click_tab(page, "Flight Analysis", wait_ms=6000)
            page.screenshot(path=str(OUTPUT_DIR / "07_flight_analysis.png"))
            print(f"saved {OUTPUT_DIR / '07_flight_analysis.png'}")

            _click_tab(page, "Replay", wait_ms=5000)
            page.screenshot(path=str(OUTPUT_DIR / "09_replay.png"))
            print(f"saved {OUTPUT_DIR / '09_replay.png'}")

            _click_tab(page, "Flight Analysis", wait_ms=4000)
            _click_tab(page, "Point of Sale", wait_ms=6000)
            page.screenshot(path=str(OUTPUT_DIR / "09b_point_of_sale.png"))
            print(f"saved {OUTPUT_DIR / '09b_point_of_sale.png'}")

            _click_tab(page, "Help & Guide", wait_ms=4000)
            page.screenshot(path=str(OUTPUT_DIR / "10_help_guide.png"))
            print(f"saved {OUTPUT_DIR / '10_help_guide.png'}")
            _scroll_main(page, 900)
            page.wait_for_timeout(1000)
            page.screenshot(path=str(OUTPUT_DIR / "10b_help_guide_lower.png"))
            print(f"saved {OUTPUT_DIR / '10b_help_guide_lower.png'}")

            _click_tab(page, "Overview", wait_ms=2500)

            # Collapse the sidebar and confirm the main area really widens.
            collapse = page.locator(
                "[data-testid='stSidebarCollapseButton'] button"
            ).first
            if collapse.count():
                width_before = page.evaluate(
                    "() => document.querySelector(\"section[data-testid='stMain']\")"
                    ".getBoundingClientRect().width"
                )
                collapse.click()
                page.wait_for_timeout(1500)
                page.mouse.move(1500, 950)
                page.wait_for_timeout(600)
                width_after = page.evaluate(
                    "() => document.querySelector(\"section[data-testid='stMain']\")"
                    ".getBoundingClientRect().width"
                )
                page.screenshot(path=str(OUTPUT_DIR / "04_sidebar_collapsed.png"))
                print(
                    f"\nsidebar collapse: main {width_before:.0f}px -> "
                    f"{width_after:.0f}px, expanded={width_after > width_before}"
                )
                print(f"saved {OUTPUT_DIR / '04_sidebar_collapsed.png'}")

                expand = page.locator("button[data-testid='stExpandSidebarButton']")
                if expand.count():
                    colours = expand.first.evaluate(
                        """el => {
                            const s = getComputedStyle(el);
                            const i = el.querySelector('[data-testid=stIconMaterial]');
                            return {bg: s.backgroundColor,
                                    fg: i ? getComputedStyle(i).color : s.color,
                                    visibility: s.visibility};
                        }"""
                    )
                    ratio = contrast_ratio(colours["fg"], colours["bg"])
                    status = "PASS" if ratio and ratio >= MIN_CONTRAST else "FAIL"
                    failures += 0 if ratio and ratio >= MIN_CONTRAST else 1
                    print(
                        f"  [{status}] {ratio:5.2f}:1  expand control, "
                        f"visibility={colours['visibility']}"
                    )

            if primary_ratio is not None:
                status = "PASS" if primary_ratio >= MIN_CONTRAST else "FAIL"
                failures += 0 if primary_ratio >= MIN_CONTRAST else 1
                print(
                    f"  [{status}] {primary_ratio:5.2f}:1  "
                    f"{'Open in drill-down (primary)':<42} "
                    f"text {primary_colours['fg']} on {primary_colours['bg']}"
                )

            browser.close()
    finally:
        server.terminate()
        try:
            server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            server.kill()

    if failures:
        print(f"\n{failures} button(s) below {MIN_CONTRAST}:1 contrast.")
        return 1
    print(f"\nAll buttons meet {MIN_CONTRAST}:1 contrast.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
