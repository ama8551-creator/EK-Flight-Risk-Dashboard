# Synthetic Flight Dataset

This folder contains the synthetic dataset used by the dashboard.

## Important: This data is fully synthetic

- **No proprietary, confidential, or internal operational data from any airline was used.**
- The dataset was generated with Python (`pandas`, `numpy`) using a reproducible random seed to reflect realistic airline operational patterns without referencing real company data.
- Any resemblance to actual flight performance is coincidental and reflects the structural patterns of airline operations (e.g. seasonal travel, weekday corporate demand) rather than any specific airline's data.

## Dataset summary

| Attribute | Value |
|---|---|
| **File** | `Synthetic_Flight_Dataset.xlsx` |
| **Rows** | ~31,449 flight-snapshot rows |
| **Routes covered** | 4 routes (8 directions) |
| **Snapshot date** | December 1, 2026 |
| **Data period** | January 2024 – March 2027 |
| **Flown (FLN) rows** | ~21,718 (terminal rows, one per flight) |
| **Open rows** | ~9,731 (multiple snapshots per flight) |

## Variable groups

- **Flight identifiers**: flight number, route, origin, destination, departure date, departure time
- **Time context**: year, season, period (peak/off-peak), day of week
- **Capacity and bookings**: F, J, Y cabin capacity and bookings, plus totals
- **Booked seat factor (BSF)**: per-cabin and total BSF
- **Forecast BSF**: projected per-cabin BSF at departure
- **Point of Sale**: representative two-letter country codes (ISO 3166-1 alpha-2)
- **Status**: `FLN` (flown) or `Open` (upcoming)

## Peak-period logic

The dataset encodes realistic peak-period behaviour across the four routes:

- **Summer**: Jun–Aug outbound family traffic, Aug return peak
- **Winter holidays**: Dec–Jan return traffic
- **Religious tourism**: Ramadan and weekend Umrah windows
- **Hajj**: late-stage Hajj return pattern
- **Corporate weekday**: Sun–Thu business travel
- **Public holidays**: National Day, Eid Al-Adha, Eid Al-Fitr

Overbooking is applied selectively during peak windows following historical airline revenue management norms (moderate +20% to +35% total overbooking, varying by cabin).

## Reproducibility

The dataset was generated with:
- Python 3.9+
- pandas, numpy, openpyxl
- Fixed random seed = 42

See the thesis document for the full generation methodology (Chapter 3, Section 3.3).
