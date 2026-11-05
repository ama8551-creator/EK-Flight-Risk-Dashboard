# A Real-Time Decision Support Dashboard for Prioritizing High-Risk Flights in Airline Inventory Management

A Streamlit dashboard that helps airline inventory analysts identify and prioritize high-risk flights, built for a Master's thesis at Rochester Institute of Technology, Dubai. Flights are ranked by a composite risk score derived from current bookings, forecast load factors, and time remaining before departure.

The dashboard views the world "as of" **1 December 2026**, the snapshot date of the synthetic dataset.

---

## 📘 About This Project

This dashboard is the practical artifact of a Master's thesis titled *"A Real-Time Decision Support Dashboard for Prioritizing High-Risk Flights in Airline Inventory Management."*

- **Author**: Alya Ahli
- **Program**: Master of Science in Professional Studies, Data Analytics
- **Institution**: Rochester Institute of Technology, Dubai
- **Mentor**: Dr. Khalil Al Hussaeni
- **Committee Chair**: Dr. Sanjay Modak
- **Year**: 2026

### Data confidentiality

The dataset used in this project is **fully synthetic**. It was generated to reflect realistic airline operational patterns (seasonal demand, weekday effects, overbooking behavior, point-of-sale distribution) without using any proprietary or confidential operational data. No internal systems, reports, or company-specific information from any airline were referenced. The Emirates-inspired styling is aesthetic only and this is not an Emirates product.

---

## 🧠 Machine Learning Integration

Three machine learning techniques are integrated into the analytical pipeline:

1. **K-Means Clustering** — unsupervised classification of operational weeks into Low / Mid / High demand clusters for automated peak detection (silhouette score 0.740)
2. **Random Forest Regression** — supervised prediction of Forecast BSF at departure based on current bookings, days to departure, and route characteristics (test MAE 0.0215, test R² 0.979)
3. **Decision Tree Classification** — supervised validation of the rule-based risk categorization (test accuracy 100%)

The ML models follow a human-in-the-loop design: predictions inform the dashboard but final decisions remain with the analyst.

---

## 🚀 Setup

Requires Python 3.9 or newer.

```bash
python -m pip install -r requirements.txt
streamlit run app.py
```

The app opens at <http://localhost:8501>.

---

## 📂 Project layout

```
.
├── app.py                 # Entry point: page config, header, tabs
├── data_loader.py         # Excel loading, derived columns, snapshot selection
├── risk_scoring.py        # Prioritization model (categories + 0-100 score)
├── ml_pipeline.py         # K-Means, Random Forest, Decision Tree training
├── ml_runtime.py          # Cached ML model execution for Streamlit
├── peak_detector.py       # Peak detection using K-Means clustering
├── approved_peaks.py      # Human-in-the-loop peak approval
├── help_content.py        # Help & Guide tab content
├── help_pdf.py            # PDF generator for the user guide
├── utils.py               # Formatting, CSV export, lookup helpers
├── components/            # One module per dashboard view, plus filters/KPIs
├── styling/theme.py       # Colour palette and global CSS
├── Data/
│   └── Synthetic_Flight_Dataset.xlsx   # Fully synthetic dataset
├── screenshots/           # Dashboard screenshots used in the thesis
└── requirements.txt
```

---

## 📊 The prioritization model

Risk categories apply to upcoming ("Open") flights only. They are evaluated in priority order, so every flight lands in exactly one bucket:

| Category | Rule | Meaning |
|---|---|---|
| 🔴 RED | Total BSF > 100% | Overbooked now; immediate action |
| 🟠 ORANGE | Y BSF > 100%, Total BSF ≤ 100%, and 45 or fewer days out | Economy is over but First/Business have room |
| 🟡 YELLOW | Forecast Total BSF > 100% | Projected to be overbooked by departure |
| 🟢 GREEN | Everything else | Normal operations |

The 0-100 score ranks flights *within* a category and is the sum of three parts, capped at 100:

1. **Base score** from the category — RED 75, ORANGE 45, YELLOW 20, GREEN 0.
2. **Urgency bonus** from days to departure — 0-3d +25, 4-7d +20, 8-14d +15, 15-30d +10, 31-60d +5, beyond +0. The same problem is more actionable three days out than ninety days out.
3. **Severity bonus** from how far past capacity the flight already is — above 110% +15, 105-110% +10, 101-105% +5, otherwise +0.

Urgency and severity apply regardless of category, so a GREEN flight departing tomorrow still outranks a GREEN flight departing in three months.

Full commentary lives in the module docstring of `risk_scoring.py`.

---

## 🔍 Filters

Nine sidebar filters apply across every tab, with a "Clear all filters" button to reset them.

| Filter | Options | Default |
|---|---|---|
| Route | outstation cities parsed from the Route column | all |
| Direction | unique origin-destination values in the Route column | all |
| Date Range | departure from / to | today to today + 90 days |
| Risk Category | RED, ORANGE, YELLOW, GREEN | all |
| Cabin Class | F, J, Y | all |
| Days to Departure | 0-120 slider | full range |
| Day of Week | 1 (Mon) … 7 (Sun), ISO 8601 | all |
| Period / Peak Holiday | consolidated seasons present in the dataset | all |
| Flight Number | flight numbers in the loaded dataset | all |

### Behaviours worth knowing

- **An empty multi-select means "show everything".** Leaving a filter untouched never hides flights, so the dashboard opens on the full population and the analyst narrows from there.
- **Route and Direction combine.** Route selects the outstation city and matches both legs of travel; Direction pins a single origin-destination leg. Both lists are generated from the loaded dataset.
- **Period is consolidated.** The workbook splits each season into granular variants. The sidebar offers top-level seasons, and selecting one matches every sub-variant of it. The mapping lives in `PERIOD_GROUPS` in `data_loader.py`.
- **Cabin class does not remove flights.** Per spec its purpose is to focus the drill-down and BSF charts, so it is carried as a display scope rather than a row filter.

One consequence of the 90-day default date range: the YELLOW flights in the current dataset depart in mid-March 2027, just outside that window, so they do not appear until the date range is widened. YELLOW is a forecast-driven early warning, and the near-term default view is not where it shows up.

---

## 🖼 Screenshots

See the `screenshots/` folder for annotated screenshots of each dashboard tab:

| File | Tab |
|---|---|
| `01_dashboard.png` | Overview |
| `02_sidebar.png` / `02b_sidebar_bottom.png` | Filter sidebar |
| `03_row_detail.png` | Row detail popover |
| `04_sidebar_collapsed.png` | Full-width view |
| `05_alert_timeline.png` / `06_alert_timeline_sections.png` | Alert Timeline |
| `07_booking_curve.png` | Flight Analysis — Booking Curve |
| `08_yoy.png` | Flight Analysis — vLY |
| `09_replay.png` | Replay tab |
| `10_help_guide.png` / `10b_help_guide_lower.png` | Help & Guide tab |

The folder also contains `Flight_Dashboard_User_Guide.pdf`, auto-generated from `help_content.py`, so the document cannot describe a different scoring model from the one running.

---

## 🎨 Theming and accessibility

`.streamlit/config.toml` pins the app to a light base theme. Without it Streamlit follows the viewer's OS dark-mode preference, which produced dark-text-on-dark-background buttons that the custom CSS then had to fight.

Buttons follow a two-tier scheme: primary actions are solid Emirates red with white text, secondary actions are white with red text and a red hairline border. `screenshot.py` renders the app in a headless browser and asserts every visible button clears the WCAG AA 4.5:1 contrast threshold, measuring computed styles rather than trusting the stylesheet.

---

## 🧪 Development aids

These are not part of the dashboard, but are useful when changing it:

```bash
python verify_dataset.py   # confirm the workbook supports the risk model
python verify_timeline.py  # check the Alert Timeline projection's invariants
python verify_help.py      # rebuild the Help PDF and check it is well-formed
python smoke_test.py       # execute app.py and assert it renders + filters work
python screenshot.py       # capture screenshots and audit button contrast
```

`screenshot.py` additionally needs `playwright` and its Chromium build:

```bash
python -m pip install playwright
python -m playwright install chromium
```

---

## 📝 Data notes

- The workbook stores BSF columns as fractions (`0.4556` = 45.56%). Fractions are preserved throughout and converted to percentages only for display.
- Flown (`FLN`) flights have one terminal row each and carry no risk category.
- Open flights have one row per snapshot day already in the past. The newest snapshot on or before the snapshot date is treated as the flight's current state; older snapshots feed the booking curve and replay views.
- `Fcst Total BSF` is not in the workbook. It is derived as the capacity-weighted combination of the per-cabin forecast BSF columns.

### Two different "days to departure"

The workbook's `Days to Departure` is the **snapshot grid position** — which observation point a row was taken at (120, 90, 75, 60, 45, 30, 21, 14, 7, 3, 1). It is not how long the analyst has left to act. A flight last observed at the 45-day snapshot but departing on 1 January 2027 is only 31 days away from the 1 December snapshot date.

The derived `Actual DTD` column holds the real figure, `Dep Date - snapshot date`, and it is what everything time-sensitive uses: the urgency bonus, the ORANGE window, the sidebar slider, and the table's "Days to Dep" column. The original `Days to Departure` survives for exactly one purpose — picking which snapshot represents a flight's current state.

The two differ for 922 of the 1,010 open legs, so conflating them materially distorts the scoring. The replay tab recomputes `Actual DTD` against the simulated date, so a past view reports the time an analyst genuinely had.

### Projected risk, and why the Alert Timeline is a model

Every open-flight row in the workbook was observed on or before the snapshot date, so there are no future observations to categorise. The Alert Timeline tab therefore *models* forward risk rather than reading it off the data.

For each leg, per-cabin BSF is interpolated linearly between two points the dataset does provide — the latest observed BSF, and the workbook's own `F/J/Y Fcst BSF` at departure — and evaluated at the snapshot checkpoints still ahead of the flight. Those per-cabin figures are recombined into a capacity-weighted total and passed through the same RED/ORANGE/YELLOW rules as every other tab; no thresholds are re-implemented.

Two consequences worth stating in the write-up:

- Real booking curves are convex, accelerating towards departure, so a linear path crosses each threshold no *earlier* than reality would. Projected dates read as "no sooner than this".
- A flight's forecast total does not vary by checkpoint, so YELLOW is effectively time-invariant. The dates that genuinely move are ORANGE and RED.

The tab reports two different things, and the distinction matters. The horizon sections list **escalations** — the date a flight first steps *up* the severity ladder — so a flight that is already RED is not re-reported. The workload cards instead count flights **holding** a category during a window, because a flight that is already RED today still has to be worked this week. `verify_timeline.py` asserts both behaviours, along with the projection never pointing into the past and the per-leg category bands tiling the timeline without gaps.

### Passenger exposure ("Pax at Risk")

For RED flights the number of passengers currently without a seat is `Total Bkg - Total Cap`. It appears in three places: a KPI summing it across the filtered RED set, an Overview column that is blank for every other category, and the RED recommendation text. ORANGE flights instead carry a *potential* count (`Y Bkg - Y Cap`): how many passengers would be at risk if First and Business filled to capacity. No currency values are attached to either figure.

### Help & Guide

Explanations live in one tab, not in hover tooltips. The same content is rendered on screen and written to `Flight_Dashboard_User_Guide.pdf`, so the document cannot describe a different scoring model from the one running.

---

## 📄 License

This project is released under the MIT License — see the `LICENSE` file.

## 📚 Citation

If you use or reference this work, please cite:

> Ahli, A. (2026). *A Real-Time Decision Support Dashboard for Prioritizing High-Risk Flights in Airline Inventory Management* (Master's thesis). Rochester Institute of Technology, Dubai.

---

Emirates-inspired styling is aesthetic only; this is not an Emirates product.
