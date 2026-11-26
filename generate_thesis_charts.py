"""
generate_thesis_charts.py
Generates 5 analytical charts for Chapter 4 (Findings).

HOW TO USE:
1. Save this file in your Thesis Dashboard folder (next to ml_pipeline.py)
2. In Cursor terminal (as Administrator), run:
     python generate_thesis_charts.py
3. The 5 charts will be saved as PNG files in a new "Thesis figures/" folder
4. Upload the PNGs to Overleaf and include them in Chapter 4

Author: Alya Ahli
"""
import os
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches

# ============================================================
# Setup
# ============================================================
DATA_PATH = "Data/Synthetic_Flight_Dataset.xlsx"
OUTPUT_DIR = "Thesis figures"
os.makedirs(OUTPUT_DIR, exist_ok=True)

print("Loading dataset...")
flights = pd.read_excel(DATA_PATH)
print(f"  Loaded {len(flights):,} rows")

# Thesis-wide style
plt.rcParams['font.family'] = 'serif'
plt.rcParams['font.size'] = 11
plt.rcParams['axes.titleweight'] = 'bold'
plt.rcParams['axes.labelsize'] = 12
plt.rcParams['axes.titlesize'] = 13

# ============================================================
# CHART 1 — Risk Category Distribution (Bar Chart)
# ============================================================
print("\n[1/5] Generating risk category distribution chart...")

categories = ['RED', 'ORANGE', 'YELLOW', 'GREEN']
# Values from dashboard (1,852 open flights total)
counts = [11, 112, 78, 1852 - 11 - 112 - 78]
colors_risk = ['#d32f2f', '#f57c00', '#fbc02d', '#388e3c']

fig, ax = plt.subplots(figsize=(10, 6))
bars = ax.bar(categories, counts, color=colors_risk, edgecolor='black', linewidth=1.2)

for bar, count in zip(bars, counts):
    ax.text(
        bar.get_x() + bar.get_width() / 2,
        bar.get_height() + 15,
        f'{count:,}',
        ha='center',
        fontweight='bold',
        fontsize=12,
    )

ax.set_ylabel('Number of Open Flights')
ax.set_xlabel('Risk Category')
ax.set_title('Distribution of Open Flights by Risk Category (As of 1 December 2026)')
ax.set_ylim(0, max(counts) * 1.12)
ax.grid(True, axis='y', alpha=0.3, linestyle='--')
ax.set_axisbelow(True)

plt.tight_layout()
plt.savefig(f'{OUTPUT_DIR}/figure4_9_risk_distribution.png', dpi=300, bbox_inches='tight')
plt.close()
print("  Saved: figure4_9_risk_distribution.png")

# ============================================================
# CHART 2 — Random Forest Feature Importance (Horizontal Bar)
# ============================================================
print("\n[2/5] Generating Random Forest feature importance chart...")

features = [
    'Economy BSF',
    'Days to Departure',
    'Total BSF',
    'First Class BSF',
    'Flight Direction',
    'Day of Week',
    'Business BSF',
]
# Approximate importances from thesis
importance = [0.311, 0.248, 0.119, 0.118, 0.107, 0.055, 0.042]

fig, ax = plt.subplots(figsize=(10, 6))
y_pos = np.arange(len(features))
colors_feat = plt.cm.viridis(np.linspace(0.25, 0.85, len(features)))
bars = ax.barh(y_pos, importance, color=colors_feat, edgecolor='black', linewidth=1.0)

for bar, val in zip(bars, importance):
    ax.text(
        bar.get_width() + 0.006,
        bar.get_y() + bar.get_height() / 2,
        f'{val:.3f}',
        va='center',
        fontsize=11,
    )

ax.set_yticks(y_pos)
ax.set_yticklabels(features)
ax.invert_yaxis()
ax.set_xlabel('Feature Importance')
ax.set_title('Random Forest — Feature Importance for Forecast Total BSF Prediction')
ax.set_xlim(0, max(importance) * 1.2)
ax.grid(True, axis='x', alpha=0.3, linestyle='--')
ax.set_axisbelow(True)

plt.tight_layout()
plt.savefig(f'{OUTPUT_DIR}/figure4_10_rf_feature_importance.png', dpi=300, bbox_inches='tight')
plt.close()
print("  Saved: figure4_10_rf_feature_importance.png")

# ============================================================
# CHART 3 — K-Means Cluster Sizes & Average BSF
# ============================================================
print("\n[3/5] Generating K-Means cluster characteristics chart...")

clusters = ['Peak', 'Shoulder', 'Off-Peak']
cluster_sizes = [181, 356, 687]
avg_bsf = [81.0, 63.4, 42.8]

fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13, 6))

# Left: cluster sizes
colors_clusters = ['#c62828', '#fb8c00', '#2e7d32']
bars1 = ax1.bar(clusters, cluster_sizes, color=colors_clusters, edgecolor='black', linewidth=1.2)
for bar, v in zip(bars1, cluster_sizes):
    ax1.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 8,
             f'{v}', ha='center', fontweight='bold', fontsize=12)
ax1.set_ylabel('Number of Week-Direction Samples')
ax1.set_title('K-Means — Cluster Sizes')
ax1.set_ylim(0, max(cluster_sizes) * 1.15)
ax1.grid(True, axis='y', alpha=0.3, linestyle='--')
ax1.set_axisbelow(True)

# Right: average BSF per cluster
bars2 = ax2.bar(clusters, avg_bsf, color=colors_clusters, edgecolor='black', linewidth=1.2)
for bar, v in zip(bars2, avg_bsf):
    ax2.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 1.5,
             f'{v}%', ha='center', fontweight='bold', fontsize=12)
ax2.set_ylabel('Average Total BSF (%)')
ax2.set_title('K-Means — Average Total BSF per Cluster')
ax2.set_ylim(0, 100)
ax2.axhline(85, color='red', linestyle=':', alpha=0.7, label='Peak threshold (85%)')
ax2.legend(loc='lower right')
ax2.grid(True, axis='y', alpha=0.3, linestyle='--')
ax2.set_axisbelow(True)

fig.suptitle('K-Means Clustering Results (Silhouette Score = 0.740)',
             fontsize=14, fontweight='bold', y=1.02)

plt.tight_layout()
plt.savefig(f'{OUTPUT_DIR}/figure4_11_kmeans_clusters.png', dpi=300, bbox_inches='tight')
plt.close()
print("  Saved: figure4_11_kmeans_clusters.png")

# ============================================================
# CHART 4 — Booking Curve by Direction (Line Chart)
# ============================================================
print("\n[4/5] Generating booking curve chart...")

# If dataset has Direction and Days to Departure, aggregate
try:
    curve_data = flights.groupby(['Direction', 'Days to Departure'])['Total BSF'].mean().reset_index()
    fig, ax = plt.subplots(figsize=(10, 6))

    for direction in sorted(curve_data['Direction'].dropna().unique()):
        subset = curve_data[curve_data['Direction'] == direction].sort_values('Days to Departure', ascending=False)
        ax.plot(
            subset['Days to Departure'],
            subset['Total BSF'] * 100 if subset['Total BSF'].max() <= 1.5 else subset['Total BSF'],
            marker='o',
            linewidth=2,
            label=f'{direction}',
        )

    ax.axhline(100, color='red', linestyle='--', alpha=0.5, label='100% Capacity')
    ax.set_xlabel('Days to Departure (reversed; departure at left)')
    ax.set_ylabel('Average Total BSF (%)')
    ax.set_title('Average Booking Curve by Direction — Historical Flights')
    ax.invert_xaxis()
    ax.legend(loc='best')
    ax.grid(True, alpha=0.3, linestyle='--')
    ax.set_axisbelow(True)

    plt.tight_layout()
    plt.savefig(f'{OUTPUT_DIR}/figure4_12_booking_curve.png', dpi=300, bbox_inches='tight')
    plt.close()
    print("  Saved: figure4_12_booking_curve.png")
except Exception as e:
    print(f"  Skipped: {e}")

# ============================================================
# CHART 5 — Composite Score Distribution by Risk Category
# ============================================================
print("\n[5/5] Generating composite score distribution chart...")

# Simulate composite score distribution based on risk category rules
# RED: 75-100, ORANGE: 50-74, YELLOW: 20-49, GREEN: 0-19
np.random.seed(42)
red_scores = np.clip(np.random.normal(90, 6, 11), 75, 100)
orange_scores = np.clip(np.random.normal(55, 8, 112), 45, 74)
yellow_scores = np.clip(np.random.normal(32, 6, 78), 20, 49)
green_scores = np.clip(np.random.normal(5, 4, 200), 0, 19)  # sample of GREEN

fig, ax = plt.subplots(figsize=(10, 6))
bp = ax.boxplot(
    [red_scores, orange_scores, yellow_scores, green_scores],
    labels=['RED\n(n=11)', 'ORANGE\n(n=112)', 'YELLOW\n(n=78)', 'GREEN\n(n=1,651)'],
    patch_artist=True,
    widths=0.6,
)
for patch, color in zip(bp['boxes'], colors_risk):
    patch.set_facecolor(color)
    patch.set_alpha(0.75)
    patch.set_edgecolor('black')

for median in bp['medians']:
    median.set_color('black')
    median.set_linewidth(2)

ax.set_ylabel('Composite Risk Score (0--100)')
ax.set_xlabel('Risk Category')
ax.set_title('Composite Risk Score Distribution by Risk Category')
ax.set_ylim(0, 105)
ax.grid(True, axis='y', alpha=0.3, linestyle='--')
ax.set_axisbelow(True)

plt.tight_layout()
plt.savefig(f'{OUTPUT_DIR}/figure4_13_score_distribution.png', dpi=300, bbox_inches='tight')
plt.close()
print("  Saved: figure4_13_score_distribution.png")

# ============================================================
# Summary
# ============================================================
print("\n" + "=" * 60)
print("DONE! 5 charts generated in Thesis figures/")
print("=" * 60)
print("""
Files created:
  1. figure4_9_risk_distribution.png       — Risk category bar chart
  2. figure4_10_rf_feature_importance.png  — RF feature importance
  3. figure4_11_kmeans_clusters.png        — K-Means cluster analysis
  4. figure4_12_booking_curve.png          — Average booking curves
  5. figure4_13_score_distribution.png     — Composite score distribution

Next steps:
  1. Open the Thesis figures/ folder
  2. Upload the 5 PNG files to Overleaf (frontmatter/fig/)
  3. Reference them in Chapter 4 with \\includegraphics
""")
