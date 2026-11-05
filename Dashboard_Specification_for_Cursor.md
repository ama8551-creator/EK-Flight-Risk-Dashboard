# Real-Time Decision Support Dashboard — Full Specification

## Project Overview

Build a **Streamlit dashboard** in Python that helps airline inventory analysts identify and prioritize high-risk flights. The dashboard reads a synthetic dataset and displays flights ranked by a composite risk score, with filtering, drill-down, and real-time replay capabilities.

**Snapshot date:** December 1, 2026 (analyst is viewing the system "as of" this date)

---

## 1. Data Source

**File:** `Synthetic_Flight_Dataset.xlsx` (main sheet: "Flights")

**Total rows:** ~12,945
**Structure:** Multi-year synthetic airline dataset with FLN (past) and Open (upcoming) flights

### Column Reference

| Column | Type | Description |
|---|---|---|
| Flight No | Text | e.g., "EK953" |
| Route | Text | e.g., "DXB-BEY" |
| Origin | Text | Origin airport code |
| Destination | Text | Destination airport code |
| Dep Date | Date | Scheduled departure date |
| Dep Time | Text | Departure time (e.g., "08:30") |
| Year | Number | 2024, 2025, 2026, 2027 |
| Season | Text | "Peak", "Shoulder", "Off-Peak" |
| Period | Text | e.g., "Summer Return Full Peak (AMM)", "New Year Return", "Off-Peak" |
| Status | Text | "FLN" (flown) or "Open" (upcoming) |
| F Cap | Number | First class capacity |
| J Cap | Number | Business class capacity |
| Y Cap | Number | Economy class capacity |
| F Bkg | Number | First class bookings |
| J Bkg | Number | Business class bookings |
| Y Bkg | Number | Economy class bookings |
| F BSF | Percentage | F Bkg / F Cap |
| J BSF | Percentage | J Bkg / J Cap |
| Y BSF | Percentage | Y Bkg / Y Cap |
| Total BSF | Percentage | Total bookings / Total capacity |
| Days to Departure | Number | Snapshot days before departure (0, 1, 3, 7, 14, 21, 30, 45, 60, 75, 90, 120) |
| F Fcst BSF | Percentage | Forecast BSF for F at departure |
| J Fcst BSF | Percentage | Forecast BSF for J at departure |
| Y Fcst BSF | Percentage | Forecast BSF for Y at departure |
| No-Show Count | Number | Expected no-show passengers |
| BSF vLY | Percentage | BSF versus last year (difference) |

**Important:**
- FLN flights have 1 row each (final state)
- Open flights have multiple rows (one per snapshot day still in the past)
- Y BSF can exceed 100% (overbooking scenarios)
- Total BSF can exceed 100% (overall overbooking)

---

## 2. Prioritization Model (Core Logic)

### Risk Categories

Apply these rules to **Open flights only** (FLN flights get no risk category):

| Category | Rule | Meaning |
|---|---|---|
| 🔴 **RED** | Current Total BSF > 100% | Flight overbooked NOW — immediate action needed |
| 🟠 **ORANGE** | Y BSF > 100% AND Total BSF ≤ 100% AND Days to Departure < 45 | Y over, but F/J still have room. Monitor closely. |
| 🟡 **YELLOW** | Forecast Total BSF > 100% AND not RED and not ORANGE | Projected to be overbooked by departure |
| 🟢 **GREEN** | Everything else | Normal operations |

### Risk Score (0-100)

Composite score for ranking flights within categories:

**Step 1 — Base score by category:**
- RED: base = 75
- ORANGE: base = 45
- YELLOW: base = 20
- GREEN: base = 0

**Step 2 — Urgency bonus (based on Days to Departure):**
- 0–3 days: +25
- 4–7 days: +20
- 8–14 days: +15
- 15–30 days: +10
- 31–60 days: +5
- 60+ days: 0

**Step 3 — Severity bonus (based on Total BSF over 100%):**
- Total BSF > 110%: +15
- Total BSF 105–110%: +10
- Total BSF 101–105%: +5
- Otherwise: 0

**Final score:** Sum of the three, capped at 100.

### For Open flights with multiple snapshots

Use the **latest snapshot per flight** (smallest Days to Departure ≤ today) as the "current state" for the dashboard. Older snapshots are available for booking curve views.

---

## 3. Dashboard Layout

### Overall Design

**Theme:** Emirates-style — red and cream/white color palette
- Primary red: `#D71921` (Emirates red)
- Secondary red: `#B01218` (darker for hover/emphasis)
- Cream/off-white: `#FAF8F5`
- Charcoal for text: `#2C2C2C`
- Green accent: `#4CAF50`
- Orange accent: `#FF9800`
- Yellow accent: `#FFC107`
- Neutral gray: `#E0E0E0`

**Font:** Modern sans-serif (Streamlit default is fine, or use "Inter" or "Roboto")

**Layout:**
- Top: Header bar with title and today's date
- Below header: KPI cards (row of 4-5 cards)
- Left sidebar: All filters
- Main area: Tabbed views

### Layout Structure

```
┌────────────────────────────────────────────────────────────────┐
│  ✈  Flight Prioritization Dashboard          As of: Dec 1, 2026 │
├────────────────────────────────────────────────────────────────┤
│  [KPI 1]   [KPI 2]   [KPI 3]   [KPI 4]   [KPI 5]              │
├──────────┬─────────────────────────────────────────────────────┤
│          │  ┌ Tabs ────────────────────────────────────────┐  │
│ FILTERS  │  │ Overview | Drill-Down | Trends | YoY | Replay│  │
│          │  ├───────────────────────────────────────────────┤  │
│ Route    │  │                                                │  │
│ Date     │  │        Main content per tab                   │  │
│ Category │  │                                                │  │
│ Cabin    │  │                                                │  │
│ Days     │  │                                                │  │
│ Period   │  │                                                │  │
│ Flight # │  │                                                │  │
│          │  │                                                │  │
└──────────┴──└────────────────────────────────────────────────┘─┘
```

---

## 4. Sidebar Filters (7 filters)

All filters should apply to the visible flights across all tabs. Use "clear all" button at bottom of sidebar.

### 4.1 Route (multi-select)
Options: DXB-BEY, BEY-DXB, DXB-AMM, AMM-DXB
Default: All selected

### 4.2 Date Range (from/to date pickers)
Options: Dep Date from and to
Default: Today (Dec 1, 2026) to 90 days from now

### 4.3 Risk Category (multi-select)
Options: 🔴 RED, 🟠 ORANGE, 🟡 YELLOW, 🟢 GREEN
Default: All selected

### 4.4 Cabin Class (multi-select)
Options: F (First), J (Business), Y (Economy)
Default: All selected
Purpose: When filtering by cabin, the drill-down and BSF trend charts should focus on that cabin

### 4.5 Days to Departure Range (slider)
Options: 0 to 120 days
Default: 0 to 60 days

### 4.6 Period (multi-select)
Options: All unique values in the "Period" column
Default: All selected

### 4.7 Flight Number (dropdown search)
Options: All 12 flight numbers
Default: None selected (show all)

---

## 5. KPI Cards (Top Row)

Row of 5 cards showing key metrics for the currently filtered flights.

### KPI 1: Total Open Flights
- Big number
- Subtitle: "Currently visible"

### KPI 2: RED Flights (critical)
- Big number in red color
- Subtitle: "Immediate action needed"
- Small trend arrow if trending up/down

### KPI 3: ORANGE Flights (watch)
- Big number in orange
- Subtitle: "Monitor closely"

### KPI 4: YELLOW Flights (warning)
- Big number in yellow
- Subtitle: "Projected overbooking"

### KPI 5: Average Total BSF
- Percentage value
- Subtitle: "Across filtered flights"

---

## 6. Main Tabs

### Tab 1: Overview (Main Table)

**Purpose:** Show all filtered flights ranked by risk score.

**Table columns:**
1. Priority icon (🔴🟠🟡🟢)
2. Risk Score (0-100)
3. Flight No
4. Route
5. Dep Date
6. Dep Time
7. Days to Departure
8. F BSF (color coded)
9. J BSF (color coded)
10. Y BSF (color coded)
11. Total BSF (color coded)
12. Fcst Total BSF
13. No-Show Count
14. BSF vLY (with up/down arrow)
15. Period

**Features:**
- Default sort: Risk Score DESC
- Clicking a row highlights it and shows details in an expander below
- Color code BSF cells: RED (>100%), ORANGE (90-100%), GREEN (<90%)
- Ability to sort by clicking column headers
- Export to CSV button
- Pagination if > 50 rows

### Tab 2: Individual Flight Drill-Down

**Purpose:** Detailed view of a single flight.

**Selection:** Flight dropdown + Dep Date picker at the top

**Content:**
- Flight identity card: Flight No, Route, Dep Date, Aircraft type, Risk Score, Category
- Current state cards: F/J/Y bookings vs capacity, Total, Fcst
- Booking curve chart (see below in charts section)
- Historical comparison: This flight's performance vs. same flight in prior year
- Key insights box: Bullet points explaining why this flight is scored the way it is

Example insights:
- "⚠️ Y is overbooked by 8 seats"
- "⚠️ F/J filling up rapidly in the last 7 days"
- "✓ Historical pattern matches expectation"

### Tab 3: BSF Trends Over Time

**Purpose:** See how BSF evolves across a time period.

**Charts:**
1. **Line chart:** X-axis = Dep Date, Y-axis = Total BSF at latest snapshot, multiple lines per route
2. **Stacked area chart:** Total flight count by category over time
3. **Bar chart:** Average BSF by Period

### Tab 4: Individual Booking Curve

**Purpose:** For a selected flight, show how bookings built up over time.

**Selection:** Flight No + Dep Date

**Chart:**
- X-axis: Days to Departure (120 → 0, reversed so time flows left to right)
- Y-axis: BSF %
- Three lines: F BSF, J BSF, Y BSF
- Optional: horizontal line at 100% (capacity)
- Emirates red for Y, cream for J, subtle for F

**Below chart:** Table showing snapshot values

### Tab 5: Year-over-Year Comparison

**Purpose:** Compare current year to prior year.

**Selection:** Flight No, Dep Date (aligns to same date prior year)

**Features:**
- Side-by-side BSF comparison
- Line chart: This year vs prior year on same axes
- Deviation column: BSF vLY per cabin
- Summary: "This flight is +5% vs last year, driven by strong Y demand"

### Tab 6: Real-Time Replay Slider

**Purpose:** Simulate what the dashboard would have shown at earlier dates.

**Interface:**
- Slider at top: "As of date" — from earliest snapshot date to Dec 1, 2026
- Playback controls: Play, Pause, Speed (1x, 2x, 5x)
- Below slider: The Overview table AS IT WOULD HAVE LOOKED at the selected date

**Logic:**
- For each flight, use the snapshot closest to but not after the selected date
- Recompute the risk score based on that snapshot
- Show how the ranking changes as time progresses

### Tab 7: Route Comparison

**Purpose:** Compare performance across routes side-by-side.

**Charts:**
1. **Bar chart:** Average Total BSF by Route
2. **Grouped bar chart:** Risk category distribution by Route
3. **Line chart:** BSF over time, one line per route
4. **Summary table:** Route-level KPIs (Total flights, Avg BSF, RED count, etc.)

---

## 7. Interactive Features

### Global
- All filters and tabs should update dynamically
- Loading spinner when data is being processed
- Empty state message when no flights match filters ("No flights match your filters")

### Table interactions
- Click a row → highlight
- Double-click a row → jump to drill-down tab with that flight selected
- Right-click (or context menu) → "Export this flight," "Compare to LY"

### Charts
- Hover for tooltip with details
- Click a bar/point → filter dashboard to that value
- Legend clickable to show/hide series

---

## 8. Technical Requirements

### Tech Stack
- **Language:** Python 3.9+
- **Dashboard framework:** Streamlit
- **Data processing:** pandas, numpy
- **Charts:** Plotly (for interactive) or Altair
- **File reading:** openpyxl for Excel

### Project Structure
```
thesis_dashboard/
├── app.py                    # Main Streamlit app
├── data_loader.py            # Load and preprocess Excel data
├── risk_scoring.py           # Prioritization model logic
├── utils.py                  # Helper functions
├── components/
│   ├── kpi_cards.py
│   ├── overview_table.py
│   ├── drill_down.py
│   ├── booking_curve.py
│   ├── yoy_comparison.py
│   ├── replay.py
│   └── route_comparison.py
├── styling/
│   └── theme.py              # Emirates color palette, CSS
├── data/
│   └── Synthetic_Flight_Dataset.xlsx
├── requirements.txt
└── README.md
```

### Performance
- Cache data loading using `@st.cache_data`
- Cache risk scoring computation
- Data preprocessing should happen ONCE at startup
- Filters should be responsive (< 1 second)

### Requirements file
```
streamlit>=1.28.0
pandas>=2.0.0
numpy>=1.24.0
openpyxl>=3.1.0
plotly>=5.15.0
```

---

## 9. Code Style

- Add docstrings to every function
- Use type hints
- Comment complex logic (especially the risk scoring)
- Keep components in separate files (modular)
- Use constants at top of each file (colors, thresholds, etc.)

---

## 10. Deliverable

Please provide:
1. All code files (fully working)
2. A README.md with setup instructions
3. `requirements.txt`
4. Comments explaining the risk scoring formula
5. Example screenshots (if possible)

---

## 11. Development Order (Suggested)

Build in this order to avoid getting stuck:
1. Set up project structure + data loading + risk scoring logic
2. Build sidebar filters
3. Build KPI cards
4. Build Overview table (Tab 1) — most important
5. Build Individual Flight Drill-Down (Tab 2)
6. Build Booking Curve (Tab 4)
7. Build BSF Trends (Tab 3)
8. Build Route Comparison (Tab 7)
9. Build YoY Comparison (Tab 5)
10. Build Real-Time Replay (Tab 6) — most complex, save for last

## 12. Notes

- The dataset is fully synthetic but reflects realistic operational patterns
- Overbooking scenarios (Y BSF > 100%) are intentional and should be flagged
- The dashboard is for demonstration purposes as part of a Master's thesis
- Emirates-inspired styling is aesthetic only; this is not an Emirates product
