"""
fix_chart4_v2.py — Regenerate Chart 4 using multi-snapshot data (open flights)
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

# Diagnostic: what days-to-departure values do we actually have?
dtd_values = flights['Days to Departure'].value_counts().sort_index()
print(f"\nDays to Departure values in dataset:")
print(dtd_values.head(20))

# Use ALL records where days-to-departure > 0 (snapshots during booking window)
historical = flights[flights['Days to Departure'] > 0].copy()
print(f"\nSnapshots with Days to Departure > 0: {len(historical):,}")
print(f"Unique DTD values: {sorted(historical['Days to Departure'].unique())}")

plt.rcParams['font.family'] = 'serif'
plt.rcParams['font.size'] = 11
plt.rcParams['axes.titleweight'] = 'bold'
plt.rcParams['axes.labelsize'] = 12
plt.rcParams['axes.titlesize'] = 13

curve_data = historical.groupby(['Route', 'Days to Departure'])['Total BSF'].mean().reset_index()
routes = sorted(curve_data['Route'].dropna().unique())
print(f"\nRoutes found: {routes}")

fig, ax = plt.subplots(figsize=(12, 7))

route_colors = {
    'DXB-BEY': '#1976d2', 'BEY-DXB': '#1976d2',
    'DXB-AMM': '#388e3c', 'AMM-DXB': '#388e3c',
    'DXB-JED': '#d32f2f', 'JED-DXB': '#d32f2f',
    'DXB-RUH': '#f57c00', 'RUH-DXB': '#f57c00',
}

for route in routes:
    subset = curve_data[curve_data['Route'] == route].sort_values('Days to Departure', ascending=False)

    y_vals = subset['Total BSF']
    if y_vals.max() <= 1.5:
        y_vals = y_vals * 100

    linestyle = '-' if route.startswith('DXB') else '--'
    color = route_colors.get(route, 'gray')

    ax.plot(
        subset['Days to Departure'],
        y_vals,
        marker='o',
        markersize=6,
        linewidth=2,
        linestyle=linestyle,
        color=color,
        label=route,
    )

ax.axhline(100, color='red', linestyle=':', alpha=0.5, label='100% Capacity')
ax.set_xlabel('Days to Departure (reversed; departure at right)')
ax.set_ylabel('Average Total BSF (%)')
ax.set_title('Average Booking Curve by Route (Across All Open-Flight Snapshots)\n(Solid = Outbound from DXB, Dashed = Inbound to DXB)')
ax.invert_xaxis()
ax.legend(loc='upper left', ncol=2, fontsize=10, framealpha=0.95)
ax.grid(True, alpha=0.3, linestyle='--')
ax.set_axisbelow(True)

plt.tight_layout()
plt.savefig(f'{OUTPUT_DIR}/figure4_12_booking_curve.png', dpi=300, bbox_inches='tight')
plt.close()

print(f"\n✅ Saved: {OUTPUT_DIR}/figure4_12_booking_curve.png")
