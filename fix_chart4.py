"""
fix_chart4.py — Regenerate ONLY Chart 4 (booking curve by route)

Save this in your Thesis Dashboard folder and run:
    python fix_chart4.py
"""
import os
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

DATA_PATH = "Data/Synthetic_Flight_Dataset.xlsx"
OUTPUT_DIR = "Thesis figures"
os.makedirs(OUTPUT_DIR, exist_ok=True)

print("Loading dataset...")
flights = pd.read_excel(DATA_PATH)
print(f"  Loaded {len(flights):,} rows")

plt.rcParams['font.family'] = 'serif'
plt.rcParams['font.size'] = 11
plt.rcParams['axes.titleweight'] = 'bold'
plt.rcParams['axes.labelsize'] = 12
plt.rcParams['axes.titlesize'] = 13

print("\nGenerating booking curve by route...")

# Filter to flown flights only (historical data)
if 'Status' in flights.columns:
    historical = flights[flights['Status'] == 'FLN'].copy()
    print(f"  Historical (flown) flights: {len(historical):,} snapshots")
else:
    historical = flights

# Aggregate by Route and Days to Departure
curve_data = (
    historical.groupby(['Route', 'Days to Departure'])['Total BSF']
    .mean()
    .reset_index()
)

routes = sorted(curve_data['Route'].dropna().unique())
print(f"  Routes found: {routes}")

fig, ax = plt.subplots(figsize=(12, 7))

# Color scheme: pair outbound/inbound by city
route_colors = {
    'DXB-BEY': '#1976d2', 'BEY-DXB': '#1976d2',
    'DXB-AMM': '#388e3c', 'AMM-DXB': '#388e3c',
    'DXB-JED': '#d32f2f', 'JED-DXB': '#d32f2f',
    'DXB-RUH': '#f57c00', 'RUH-DXB': '#f57c00',
}

for route in routes:
    subset = curve_data[curve_data['Route'] == route].sort_values('Days to Departure', ascending=False)

    # Convert BSF to percentage if fractional
    y_vals = subset['Total BSF']
    if y_vals.max() <= 1.5:
        y_vals = y_vals * 100

    # Use solid for outbound (DXB-XXX), dashed for inbound (XXX-DXB)
    linestyle = '-' if route.startswith('DXB') else '--'
    color = route_colors.get(route, 'gray')

    ax.plot(
        subset['Days to Departure'],
        y_vals,
        marker='o',
        markersize=5,
        linewidth=2,
        linestyle=linestyle,
        color=color,
        label=route,
    )

ax.axhline(100, color='red', linestyle=':', alpha=0.5, label='100% Capacity')
ax.set_xlabel('Days to Departure')
ax.set_ylabel('Average Total BSF (%)')
ax.set_title('Average Historical Booking Curve by Route\n(Solid = Outbound from DXB, Dashed = Inbound to DXB)')
ax.invert_xaxis()  # Departure at right → booking build-up visible left-to-right
ax.legend(loc='upper left', ncol=2, fontsize=10, framealpha=0.95)
ax.grid(True, alpha=0.3, linestyle='--')
ax.set_axisbelow(True)
ax.set_ylim(0, max(ax.get_ylim()[1], 110))

plt.tight_layout()
plt.savefig(f'{OUTPUT_DIR}/figure4_12_booking_curve.png', dpi=300, bbox_inches='tight')
plt.close()

print(f"\n✅ Saved: {OUTPUT_DIR}/figure4_12_booking_curve.png")
print("\nChart 4 regenerated with real data by route!")
