"""
Visualize Cluster Statistics
============================
Creates comprehensive visualizations of the 5 project clusters
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns

# Load data
stats_df = pd.read_csv('../results/cluster_statistics.csv')

# Set style
sns.set_style("whitegrid")
plt.rcParams['figure.figsize'] = (16, 12)

# Material columns
materials = ['MIX TN_avg', 'GRADE CY_avg', 'BASE TN_avg', 'SHLDR TN_avg',
             'MILL SY_avg', 'CRUSH TN_avg', 'STOCK TN_avg']
material_names = ['Asphalt\n(tons)', 'Grading\n(cubic yds)', 'Base\n(tons)',
                  'Shoulder\n(tons)', 'Milling\n(sq yds)', 'Crushing\n(tons)', 'Stockpile\n(tons)']

# Create figure with subplots - larger to accommodate all clusters
fig = plt.figure(figsize=(20, 14))

# 1. Cluster Sizes (Pie Chart)
ax1 = plt.subplot(3, 3, 1)
colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd']
wedges, texts, autotexts = ax1.pie(stats_df['n_projects'],
                                     labels=[f"Cluster {i}" for i in range(5)],
                                     autopct='%1.1f%%',
                                     colors=colors,
                                     startangle=90)
ax1.set_title('Cluster Distribution\n(% of 1,661 projects)', fontsize=12, fontweight='bold')
for autotext in autotexts:
    autotext.set_color('white')
    autotext.set_fontweight('bold')

# 2. Project Count per Cluster (Bar Chart)
ax2 = plt.subplot(3, 3, 2)
bars = ax2.bar(stats_df['cluster_id'], stats_df['n_projects'], color=colors, edgecolor='black', linewidth=1.5)
ax2.set_xlabel('Cluster', fontsize=11, fontweight='bold')
ax2.set_ylabel('Number of Projects', fontsize=11, fontweight='bold')
ax2.set_title('Projects per Cluster', fontsize=12, fontweight='bold')
ax2.set_xticks(range(5))
for bar in bars:
    height = bar.get_height()
    ax2.text(bar.get_x() + bar.get_width()/2., height,
            f'{int(height)}',
            ha='center', va='bottom', fontweight='bold')
ax2.grid(axis='y', alpha=0.3)

# 3. BOX Culvert Prevalence
ax3 = plt.subplot(3, 3, 3)
bars = ax3.bar(stats_df['cluster_id'], stats_df['box_pct'], color=colors, edgecolor='black', linewidth=1.5)
ax3.set_xlabel('Cluster', fontsize=11, fontweight='bold')
ax3.set_ylabel('% with BOX Culverts', fontsize=11, fontweight='bold')
ax3.set_title('Infrastructure Complexity\n(% with BOX)', fontsize=12, fontweight='bold')
ax3.set_xticks(range(5))
for bar in bars:
    height = bar.get_height()
    ax3.text(bar.get_x() + bar.get_width()/2., height,
            f'{height:.1f}%',
            ha='center', va='bottom', fontweight='bold', fontsize=9)
ax3.grid(axis='y', alpha=0.3)

# 4-10. Material quantities per cluster (heatmap + individual bars)

# Heatmap with row normalization (0-1 scale within each material)
ax4 = plt.subplot(3, 3, (4, 6))
material_data = stats_df[materials].values

# Normalize each row (material) from 0 to 1
material_data_normalized = np.zeros_like(material_data, dtype=float)
for i in range(material_data.shape[0]):  # for each material
    min_val = material_data[i].min()
    max_val = material_data[i].max()
    material_data_normalized[i] = (material_data[i] - min_val) / (max_val - min_val)

# Create heatmap with annotations showing both normalized (color) and actual values
sns.heatmap(material_data_normalized.T,
            annot=material_data.T,
            fmt='.0f',
            cmap='RdYlGn',
            xticklabels=[f'C{i}' for i in range(5)],
            yticklabels=material_names,
            cbar_kws={'label': 'Relative Intensity (0=min, 1=max)'},
            ax=ax4,
            linewidths=0.5,
            vmin=0,
            vmax=1)
ax4.set_title('Material Quantities per Cluster\n(Row-normalized: each material scaled 0-1)',
              fontsize=12, fontweight='bold')
ax4.set_xlabel('Cluster', fontsize=11, fontweight='bold')

# 7. Asphalt (MIX TN)
ax7 = plt.subplot(3, 3, 7)
asphalt = stats_df['MIX TN_avg']
bars = ax7.bar(stats_df['cluster_id'], asphalt, color=colors, edgecolor='black', linewidth=1.5)
ax7.set_xlabel('Cluster', fontsize=10, fontweight='bold')
ax7.set_ylabel('Tons', fontsize=10, fontweight='bold')
ax7.set_title('Asphalt Mix (MIX TN)', fontsize=11, fontweight='bold')
ax7.set_xticks(range(5))
ax7.ticklabel_format(style='plain', axis='y')
ax7.grid(axis='y', alpha=0.3)

# 8. Grading (GRADE CY)
ax8 = plt.subplot(3, 3, 8)
grading = stats_df['GRADE CY_avg']
bars = ax8.bar(stats_df['cluster_id'], grading, color=colors, edgecolor='black', linewidth=1.5)
ax8.set_xlabel('Cluster', fontsize=10, fontweight='bold')
ax8.set_ylabel('Cubic Yards', fontsize=10, fontweight='bold')
ax8.set_title('Grading (GRADE CY)', fontsize=11, fontweight='bold')
ax8.set_xticks(range(5))
ax8.ticklabel_format(style='plain', axis='y')
ax8.grid(axis='y', alpha=0.3)

# 9. Milling (MILL SY)
ax9 = plt.subplot(3, 3, 9)
milling = stats_df['MILL SY_avg']
bars = ax9.bar(stats_df['cluster_id'], milling, color=colors, edgecolor='black', linewidth=1.5)
ax9.set_xlabel('Cluster', fontsize=10, fontweight='bold')
ax9.set_ylabel('Square Yards', fontsize=10, fontweight='bold')
ax9.set_title('Milling (MILL SY)', fontsize=11, fontweight='bold')
ax9.set_xticks(range(5))
ax9.ticklabel_format(style='plain', axis='y')
ax9.grid(axis='y', alpha=0.3)

plt.suptitle('Cluster Statistics: 5 Project Types\n1,661 CSI Projects (2024-2025)',
             fontsize=16, fontweight='bold', y=0.995)

# Adjust layout to prevent cutoff - add more horizontal space
plt.tight_layout(rect=[0, 0, 1, 0.99])
# Manually adjust subplots positions to ensure all clusters visible
plt.subplots_adjust(wspace=0.35, hspace=0.35, right=0.98, left=0.06)
plt.savefig('../visualizations/cluster_statistics_overview.png', dpi=300, bbox_inches='tight')
print("✅ Saved: ../visualizations/cluster_statistics_overview.png")
plt.close()

# Create a detailed comparison table visualization
fig, ax = plt.subplots(figsize=(14, 6))
ax.axis('tight')
ax.axis('off')

# Prepare data for table
table_data = []
table_data.append(['Cluster', 'Size', '%', 'Asphalt', 'Grading', 'Shoulder', 'Milling', 'BOX %', 'Type'])

cluster_names = [
    'Routine',
    'Medium Overlay',
    'Large Projects',
    'Extreme Structural',
    'Extreme Grading'
]

for idx, row in stats_df.iterrows():
    table_data.append([
        f"C{int(row['cluster_id'])}",
        f"{int(row['n_projects'])}",
        f"{row['pct_of_total']:.1f}%",
        f"{row['MIX TN_avg']:.0f}T",
        f"{row['GRADE CY_avg']:.0f}CY",
        f"{row['SHLDR TN_avg']:.0f}T",
        f"{row['MILL SY_avg']:.0f}SY",
        f"{row['box_pct']:.1f}%",
        cluster_names[idx]
    ])

table = ax.table(cellText=table_data, cellLoc='center', loc='center',
                colWidths=[0.08, 0.08, 0.08, 0.1, 0.1, 0.1, 0.1, 0.08, 0.19])

table.auto_set_font_size(False)
table.set_fontsize(10)
table.scale(1, 2.5)

# Style header row
for i in range(9):
    table[(0, i)].set_facecolor('#4472C4')
    table[(0, i)].set_text_props(weight='bold', color='white')

# Style data rows with cluster colors
for i in range(1, 6):
    for j in range(9):
        table[(i, j)].set_facecolor(colors[i-1])
        table[(i, j)].set_alpha(0.3)
        table[(i, j)].set_text_props(weight='bold')

plt.title('Cluster Summary: Material Characteristics & Types',
         fontsize=14, fontweight='bold', pad=20)

plt.savefig('../visualizations/cluster_summary_table.png', dpi=300, bbox_inches='tight')
print("✅ Saved: ../visualizations/cluster_summary_table.png")
plt.close()

# Print summary to console
print("\n" + "="*80)
print("CLUSTER STATISTICS SUMMARY")
print("="*80)
for idx, row in stats_df.iterrows():
    print(f"\n{cluster_names[idx].upper()} (Cluster {int(row['cluster_id'])})")
    print(f"  Projects: {int(row['n_projects'])} ({row['pct_of_total']:.1f}%)")
    print(f"  Asphalt: {row['MIX TN_avg']:.0f} tons")
    print(f"  Grading: {row['GRADE CY_avg']:.0f} cubic yards")
    print(f"  Shoulders: {row['SHLDR TN_avg']:.0f} tons")
    print(f"  Milling: {row['MILL SY_avg']:.0f} square yards")
    print(f"  BOX Culverts: {row['box_pct']:.1f}%")

print("\n✅ Visualization complete!")
