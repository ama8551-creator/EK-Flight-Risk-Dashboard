"""Emirates-inspired colour palette and global CSS for the dashboard.

The styling here is aesthetic only; this is not an Emirates product.
"""

from __future__ import annotations

from typing import Final

# --- Core palette (from specification section 3) ---------------------------
EMIRATES_RED: Final[str] = "#D71921"
EMIRATES_RED_DARK: Final[str] = "#B01218"
CREAM: Final[str] = "#FAF8F5"
CHARCOAL: Final[str] = "#2C2C2C"
GREEN: Final[str] = "#4CAF50"
ORANGE: Final[str] = "#FF9800"
YELLOW: Final[str] = "#FFC107"
NEUTRAL_GRAY: Final[str] = "#E0E0E0"
WHITE: Final[str] = "#FFFFFF"

# --- Risk category colours -------------------------------------------------
CATEGORY_COLORS: Final[dict[str, str]] = {
    "RED": EMIRATES_RED,
    "ORANGE": ORANGE,
    "YELLOW": YELLOW,
    "GREEN": GREEN,
}

CATEGORY_ICONS: Final[dict[str, str]] = {
    "RED": "🔴",
    "ORANGE": "🟠",
    "YELLOW": "🟡",
    "GREEN": "🟢",
}

# Display order used for legends, filters and sorting.
CATEGORY_ORDER: Final[list[str]] = ["RED", "ORANGE", "YELLOW", "GREEN"]

# --- Cabin colours (spec section 6, Tab 4: red for Y, cream/gold for J) ----
CABIN_COLORS: Final[dict[str, str]] = {
    "F": "#8C8C8C",  # subtle grey for First
    "J": "#C9A227",  # muted gold for Business
    "Y": EMIRATES_RED,  # Emirates red for Economy
}

#: Last-year overlay on booking curves — one grey, always dashed.
LAST_YEAR_LINE: Final[str] = "#9CA3AF"

#: This-year cabin colours on the booking curve (distinct from LAST_YEAR_LINE).
CURVE_CABIN_COLORS: Final[dict[str, str]] = {
    "F": "#1F6FB2",
    "J": "#C9A227",
    "Y": EMIRATES_RED,
}

#: Dark grey used for the underperforming-vs-LY KPI and flag.
BLACK_FLAG: Final[str] = "#4A4A4A"

#: Overview BSF vLY text: up vs last year, down, and near-zero.
VLY_UP: Final[str] = "#2E7D32"
VLY_DOWN: Final[str] = EMIRATES_RED
VLY_FLAT: Final[str] = CHARCOAL
#: Fractional band treated as "no movement" (|Δ| ≤ 0.1 percentage points).
VLY_NEAR_ZERO: Final[float] = 0.001

#: ISO country code → colour, used on every POS chart so a country never
#: changes colour between the donut and the table.
POS_COLORS: Final[dict[str, str]] = {
    "AE": EMIRATES_RED,
    "SA": "#006C35",
    "LB": "#1F6FB2",
    "JO": "#C9A227",
    "AU": "#4CAF50",
    "CA": "#7B4B94",
    "US": "#E07A5F",
    "GB": CHARCOAL,
    "DE": "#00838F",
    "FR": "#5C6BC0",
}

#: Fallback colours for POS codes not listed above.
_POS_FALLBACK_COLORS: Final[list[str]] = [
    "#8D6E63",
    "#455A64",
    "#D81B60",
    "#00897B",
]

# Qualitative palette for per-route chart series.
ROUTE_COLORS: Final[list[str]] = [
    EMIRATES_RED,
    "#1F6FB2",
    "#C9A227",
    "#4CAF50",
    "#7B4B94",
    "#E07A5F",
    "#006C35",
    "#455A64",
]


def pos_color(code: str) -> str:
    """Return a stable colour for a POS country code."""
    if code in POS_COLORS:
        return POS_COLORS[code]
    palette = ROUTE_COLORS + _POS_FALLBACK_COLORS
    return palette[sum(ord(character) for character in code) % len(palette)]


def category_label(category: str) -> str:
    """Return a category with its traffic-light icon, e.g. ``"🔴 RED"``."""
    return f"{CATEGORY_ICONS.get(category, '')} {category}".strip()


def global_css() -> str:
    """Return the global stylesheet injected once at app startup."""
    return f"""
    <style>
      /* ---------- Base canvas ---------- */
      .stApp {{
          background-color: {CREAM};
          color: {CHARCOAL};
      }}
      html, body, [class*="css"] {{
          font-family: "Inter", "Roboto", "Segoe UI", system-ui, sans-serif;
      }}

      /* ---------- Header bar ---------- */
      .ek-header {{
          background: linear-gradient(90deg, {EMIRATES_RED} 0%, {EMIRATES_RED_DARK} 100%);
          color: {WHITE};
          padding: 0.9rem 1.4rem;
          border-radius: 10px;
          display: flex;
          align-items: center;
          justify-content: space-between;
          margin-bottom: 1.1rem;
          box-shadow: 0 2px 6px rgba(0, 0, 0, 0.12);
      }}
      .ek-header-title {{
          font-size: 1.55rem;
          font-weight: 700;
          letter-spacing: 0.2px;
      }}
      .ek-header-date {{
          font-size: 0.95rem;
          font-weight: 500;
          opacity: 0.95;
          white-space: nowrap;
      }}

      /* ---------- KPI cards ---------- */
      [data-testid="stMarkdownContainer"]:has(.ek-kpi-row) {{
          width: 100%;
      }}
      .ek-kpi-row {{
          display: flex;
          flex-wrap: nowrap;
          align-items: stretch;
          gap: 10px;
          width: 100%;
          overflow-x: auto;
          overflow-y: hidden;
          box-sizing: border-box;
          padding-bottom: 4px;
          scrollbar-width: thin;
      }}
      .ek-kpi-cell {{
          flex: 1 0 calc((100% - 50px) / 6);
          min-width: 148px;
          box-sizing: border-box;
      }}
      .ek-kpi {{
          background-color: {WHITE};
          border: 1px solid {NEUTRAL_GRAY};
          border-left: 5px solid {EMIRATES_RED};
          border-radius: 10px;
          padding: 0.55rem 0.65rem;
          height: 100%;
          box-sizing: border-box;
          box-shadow: 0 1px 3px rgba(0, 0, 0, 0.06);
      }}
      .ek-kpi-label {{
          font-size: 0.68rem;
          font-weight: 600;
          text-transform: uppercase;
          letter-spacing: 0.4px;
          color: #6B6B6B;
          margin-bottom: 0.2rem;
          line-height: 1.25;
      }}
      .ek-kpi-value {{
          font-size: 1.45rem;
          font-weight: 700;
          line-height: 1.1;
          color: {CHARCOAL};
      }}
      .ek-kpi-sub {{
          font-size: 0.74rem;
          color: #7A7A7A;
          margin-top: 0.2rem;
          line-height: 1.3;
      }}
      .ek-kpi-trend {{
          font-size: 0.76rem;
          font-weight: 600;
          margin-top: 0.15rem;
      }}

      /* ---------- Overview alert banner ---------- */
      .ek-alert-banner {{
          background-color: {EMIRATES_RED};
          color: {WHITE};
          font-size: 1.02rem;
          font-weight: 600;
          line-height: 1.45;
          padding: 0.85rem 1.15rem;
          border-radius: 10px;
          margin: 0 0 0.85rem 0;
      }}

      /* ---------- Today's Priorities ---------- */
      .ek-priorities {{
          background-color: {CREAM};
          border: 1px solid {NEUTRAL_GRAY};
          border-left: 5px solid {EMIRATES_RED};
          border-radius: 10px;
          padding: 0.75rem 1.1rem 0.35rem 1.1rem;
          margin: 0.2rem 0 0.35rem 0;
          box-shadow: 0 1px 3px rgba(0, 0, 0, 0.06);
      }}
      .ek-priorities-title {{
          font-size: 0.95rem;
          font-weight: 700;
          color: {CHARCOAL};
          margin-bottom: 0.15rem;
      }}
      .ek-priorities-empty {{
          background-color: {CREAM};
          border: 1px solid {NEUTRAL_GRAY};
          border-left: 5px solid {EMIRATES_RED};
          border-radius: 10px;
          padding: 0.65rem 1.1rem;
          margin: 0 0 0.75rem 0;
          color: {CHARCOAL};
          font-size: 0.92rem;
      }}

      /* ---------- Overview summary sentence ---------- */
      .ek-overview-summary {{
          background-color: {CREAM};
          color: {CHARCOAL};
          font-size: 1.12rem;
          font-weight: 500;
          line-height: 1.5;
          padding: 0.9rem 1.2rem;
          border: 1px solid {NEUTRAL_GRAY};
          border-radius: 10px;
          margin: 0.35rem 0 0.9rem 0;
      }}

      /* ---------- Insight / detail boxes ---------- */
      .ek-panel {{
          background-color: {WHITE};
          border: 1px solid {NEUTRAL_GRAY};
          border-radius: 10px;
          padding: 1rem 1.15rem;
          margin-bottom: 0.8rem;
      }}
      .ek-panel h4 {{
          margin-top: 0;
          color: {EMIRATES_RED_DARK};
      }}

      /* ---------- Action recommendation panel ---------- */
      .ek-reco {{
          background-color: {WHITE};
          border: 1px solid {NEUTRAL_GRAY};
          border-left: 5px solid {EMIRATES_RED};
          border-radius: 8px;
          padding: 0.85rem 1rem;
          margin: 0.35rem 0 0.6rem 0;
      }}
      .ek-reco-head {{
          display: flex;
          align-items: flex-start;
          gap: 0.5rem;
          margin-bottom: 0.4rem;
      }}
      .ek-reco-icon {{
          font-size: 1.1rem;
          line-height: 1.35;
      }}
      .ek-reco-headline {{
          font-weight: 700;
          font-size: 0.98rem;
          color: {CHARCOAL};
          line-height: 1.35;
      }}
      .ek-reco-detail {{
          font-size: 0.87rem;
          color: #5A5A5A;
          line-height: 1.5;
          margin-top: 0.2rem;
          padding-left: 1.6rem;
      }}

      /* ---------- Tabs ---------- */
      /* Each tab is a distinct button, not a run-on sentence. The list
         scrolls horizontally rather than wrapping, so the full set of
         labels stays one row on a narrow main pane. */
      [data-testid="stTabs"] {{
          overflow: visible;
      }}
      .stTabs [data-baseweb="tab-list"] {{
          gap: 6px !important;
          display: flex !important;
          flex-wrap: nowrap !important;
          overflow-x: auto !important;
          overflow-y: hidden !important;
          border-bottom: 2px solid {NEUTRAL_GRAY};
          padding-bottom: 6px;
          scrollbar-width: thin;
      }}
      .stTabs [data-baseweb="tab"] {{
          background-color: {CREAM} !important;
          color: {CHARCOAL} !important;
          border: 1px solid {NEUTRAL_GRAY} !important;
          border-radius: 6px !important;
          padding: 8px 12px !important;
          margin: 0 !important;
          font-weight: 600 !important;
          white-space: nowrap !important;
          line-height: 1.3 !important;
          transition: background-color 150ms ease, color 150ms ease,
                      border-color 150ms ease;
      }}
      .stTabs [data-baseweb="tab"] p,
      .stTabs [data-baseweb="tab"] span,
      .stTabs [data-baseweb="tab"] div {{
          color: inherit !important;
          font-weight: inherit !important;
      }}
      .stTabs [data-baseweb="tab"]:hover:not([aria-selected="true"]) {{
          background-color: #F8E6E7 !important;
          color: {EMIRATES_RED} !important;
          border-color: {EMIRATES_RED} !important;
      }}
      .stTabs [data-baseweb="tab"][aria-selected="true"] {{
          background-color: {EMIRATES_RED} !important;
          color: {WHITE} !important;
          font-weight: 700 !important;
          border-color: {EMIRATES_RED} !important;
          border-bottom: 3px solid {EMIRATES_RED_DARK} !important;
      }}
      .stTabs [data-baseweb="tab-highlight"] {{
          background-color: {EMIRATES_RED} !important;
          height: 3px !important;
      }}

      /* ---------- Coming-soon placeholder pages ---------- */
      .ek-coming-soon {{
          background-color: {WHITE};
          border: 1px solid {NEUTRAL_GRAY};
          border-left: 5px solid {EMIRATES_RED};
          border-radius: 10px;
          padding: 1.6rem 1.8rem;
          max-width: 44rem;
      }}
      .ek-coming-soon-badge {{
          display: inline-block;
          background-color: {CREAM};
          color: {CHARCOAL};
          font-size: 0.78rem;
          font-weight: 700;
          letter-spacing: 0.5px;
          text-transform: uppercase;
          padding: 0.25rem 0.65rem;
          border-radius: 6px;
          border: 1px solid {NEUTRAL_GRAY};
          margin-bottom: 0.85rem;
      }}
      .ek-coming-soon h3 {{
          margin: 0 0 0.35rem 0;
          color: {EMIRATES_RED_DARK};
          font-size: 1.45rem;
      }}
      .ek-coming-soon-feature {{
          font-weight: 700;
          color: {CHARCOAL};
          margin: 0 0 0.7rem 0;
      }}
      .ek-coming-soon p {{
          color: {CHARCOAL};
          font-size: 1.02rem;
          line-height: 1.55;
          margin: 0 0 0.7rem 0;
      }}
      .ek-coming-soon-note {{
          color: #7A7A7A !important;
          font-size: 0.88rem !important;
          font-style: italic;
          margin: 1.1rem 0 0 0 !important;
      }}

      /* ---------- Sidebar ---------- */
      section[data-testid="stSidebar"] {{
          background-color: {WHITE};
          border-right: 1px solid {NEUTRAL_GRAY};
      }}
      section[data-testid="stSidebar"] h2 {{
          color: {EMIRATES_RED};
          font-size: 1.1rem;
      }}

      /* Filter headings, drawn explicitly because Streamlit's own widget
         labels sit too low-contrast against the themed sidebar. */
      .ek-filter-label {{
          font-size: 0.78rem;
          font-weight: 700;
          text-transform: uppercase;
          letter-spacing: 0.7px;
          color: {EMIRATES_RED};
          margin: 0.85rem 0 0.1rem 0;
      }}
      .ek-filter-hint {{
          font-size: 0.72rem;
          color: #8A8A8A;
          margin-bottom: 0.25rem;
      }}

      /* ---------- Sidebar collapse / expand control ---------- */
      /* Selector names have moved between Streamlit releases, so target all
         known variants to keep the control visible. */
      /* Streamlit keeps this control visibility:hidden until the sidebar is
         hovered, which makes it undiscoverable. Force it on. */
      [data-testid="stSidebarCollapseButton"],
      [data-testid="stExpandSidebarButton"],
      [data-testid="collapsedControl"],
      [data-testid="stSidebarCollapsedControl"] {{
          visibility: visible !important;
          opacity: 1 !important;
          display: block !important;
      }}

      /* Two shapes to cover: the collapse control is a wrapper around a
         button, while the expand control *is* the button. */
      [data-testid="stSidebarCollapseButton"] button,
      [data-testid="collapsedControl"] button,
      [data-testid="stSidebarCollapsedControl"] button,
      button[data-testid="stExpandSidebarButton"],
      button[data-testid="stSidebarCollapseButton"] {{
          background-color: {EMIRATES_RED} !important;
          color: {WHITE} !important;
          border: none !important;
          border-radius: 6px !important;
          box-shadow: 0 2px 6px rgba(0, 0, 0, 0.2) !important;
          opacity: 1 !important;
          transition: background-color 150ms ease, transform 150ms ease;
      }}
      [data-testid="stSidebarCollapseButton"] button:hover,
      [data-testid="collapsedControl"] button:hover,
      [data-testid="stSidebarCollapsedControl"] button:hover,
      button[data-testid="stExpandSidebarButton"]:hover,
      button[data-testid="stSidebarCollapseButton"]:hover {{
          background-color: {EMIRATES_RED_DARK} !important;
          transform: scale(1.06);
      }}
      /* The chevron is a Material icon span, not an SVG, in current builds. */
      [data-testid="stSidebarCollapseButton"] svg,
      [data-testid="stExpandSidebarButton"] svg,
      [data-testid="stSidebarCollapseButton"] [data-testid="stIconMaterial"],
      button[data-testid="stExpandSidebarButton"] [data-testid="stIconMaterial"],
      [data-testid="collapsedControl"] svg,
      [data-testid="stSidebarCollapsedControl"] svg {{
          fill: {WHITE} !important;
          color: {WHITE} !important;
          opacity: 1 !important;
      }}

      /* Let the main area reflow smoothly when the sidebar is dismissed. */
      section[data-testid="stSidebar"] {{
          transition: transform 200ms ease, width 200ms ease;
      }}
      .main .block-container, section.main > div {{
          transition: max-width 200ms ease, padding 200ms ease;
      }}

      /* ---------- Buttons ---------- */
      /* Secondary is the default: white fill, red text, red hairline border.
         Colours are forced because Streamlit's base theme would otherwise
         supply a text colour that can collide with the background.

         Descendant selectors, not direct-child: a button carrying help text
         gets wrapped in tooltip divs, which silently broke a `>` selector. */
      div[data-testid="stButton"] button,
      div[data-testid="stDownloadButton"] button,
      div[data-testid="stFormSubmitButton"] button,
      div[data-testid="stLinkButton"] a,
      button[data-testid="stBaseButton-secondary"],
      button[data-testid="stBaseButton-secondaryFormSubmit"] {{
          background-color: {WHITE} !important;
          color: {EMIRATES_RED} !important;
          border: 1px solid {EMIRATES_RED} !important;
          font-weight: 600 !important;
          border-radius: 6px !important;
          transition: background-color 150ms ease, color 150ms ease;
      }}
      div[data-testid="stButton"] button:hover,
      div[data-testid="stDownloadButton"] button:hover,
      div[data-testid="stFormSubmitButton"] button:hover,
      div[data-testid="stLinkButton"] a:hover,
      button[data-testid="stBaseButton-secondary"]:hover {{
          background-color: {CREAM} !important;
          color: {EMIRATES_RED_DARK} !important;
          border-color: {EMIRATES_RED_DARK} !important;
      }}

      /* Primary: solid Emirates red with white text. */
      div[data-testid="stButton"] button[kind="primary"],
      div[data-testid="stDownloadButton"] button[kind="primary"],
      div[data-testid="stFormSubmitButton"] button[kind="primaryFormSubmit"],
      button[data-testid="stBaseButton-primary"],
      button[data-testid="stBaseButton-primaryFormSubmit"] {{
          background-color: {EMIRATES_RED} !important;
          color: {WHITE} !important;
          border: 1px solid {EMIRATES_RED} !important;
      }}
      div[data-testid="stButton"] button[kind="primary"]:hover,
      div[data-testid="stDownloadButton"] button[kind="primary"]:hover,
      button[data-testid="stBaseButton-primary"]:hover,
      button[data-testid="stBaseButton-primaryFormSubmit"]:hover {{
          background-color: {EMIRATES_RED_DARK} !important;
          border-color: {EMIRATES_RED_DARK} !important;
          color: {WHITE} !important;
      }}

      /* Streamlit nests the caption in its own element, which would keep the
         theme's text colour unless told to inherit the button's. */
      div[data-testid="stButton"] button *,
      div[data-testid="stDownloadButton"] button *,
      div[data-testid="stFormSubmitButton"] button *,
      div[data-testid="stLinkButton"] a *,
      button[data-testid^="stBaseButton"] * {{
          color: inherit !important;
      }}

      /* Keyboard focus and active states must stay legible too. */
      div[data-testid="stButton"] button:focus-visible,
      div[data-testid="stDownloadButton"] button:focus-visible,
      div[data-testid="stFormSubmitButton"] button:focus-visible {{
          outline: 2px solid {EMIRATES_RED_DARK} !important;
          outline-offset: 1px;
      }}
      div[data-testid="stButton"] button:disabled,
      div[data-testid="stDownloadButton"] button:disabled,
      button[data-testid^="stBaseButton"]:disabled {{
          background-color: {NEUTRAL_GRAY} !important;
          color: #7A7A7A !important;
          border-color: {NEUTRAL_GRAY} !important;
      }}

      /* ---------- Peak Detection cards ---------- */
      .ek-peak-card {{
          background: {WHITE};
          border: 1px solid {NEUTRAL_GRAY};
          border-left: 4px solid {EMIRATES_RED};
          border-radius: 8px;
          padding: 0.85rem 1.05rem 0.35rem 1.05rem;
          margin-bottom: 0.7rem;
      }}
      .ek-peak-card-title {{
          font-weight: 700;
          color: {CHARCOAL};
          margin-bottom: 0.25rem;
      }}
      .ek-peak-badge {{
          display: inline-block;
          background: {CREAM};
          border: 1px solid {NEUTRAL_GRAY};
          border-radius: 999px;
          padding: 0.12rem 0.65rem;
          font-size: 0.78rem;
          font-weight: 600;
          margin-right: 0.35rem;
      }}
      .ek-peak-meta {{
          color: {CHARCOAL};
          font-size: 0.9rem;
          margin: 0.35rem 0 0.5rem 0;
      }}
      .ek-ml-badge {{
          display: inline-block;
          background: {CREAM};
          border: 1px solid {NEUTRAL_GRAY};
          border-left: 4px solid {EMIRATES_RED};
          border-radius: 6px;
          padding: 0.28rem 0.75rem;
          font-size: 0.82rem;
          font-weight: 700;
          color: {CHARCOAL};
          margin: 0.35rem 0 0.5rem 0;
      }}
      .ek-ml-note {{
          background: {CREAM};
          border: 1px solid {YELLOW};
          border-left: 4px solid {YELLOW};
          border-radius: 6px;
          padding: 0.7rem 0.9rem;
          margin: 0.6rem 0 0.8rem 0;
          color: {CHARCOAL};
          font-size: 0.92rem;
          line-height: 1.45;
      }}
    </style>
    """


def plotly_layout(**overrides: object) -> dict[str, object]:
    """Return a Plotly layout dict matching the dashboard theme.

    Args:
        **overrides: Layout keys that should replace the theme defaults.

    Returns:
        A layout mapping suitable for ``figure.update_layout(**layout)``.
    """
    layout: dict[str, object] = {
        "paper_bgcolor": "rgba(0,0,0,0)",
        "plot_bgcolor": WHITE,
        "font": {"family": "Inter, Roboto, Segoe UI, sans-serif", "color": CHARCOAL},
        "margin": {"l": 60, "r": 30, "t": 50, "b": 55},
        "hovermode": "closest",
        "legend": {"orientation": "h", "yanchor": "bottom", "y": 1.02, "x": 0},
    }
    layout.update(overrides)
    return layout
