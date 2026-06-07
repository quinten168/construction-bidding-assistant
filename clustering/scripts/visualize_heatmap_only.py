"""
Dedicated Heatmap Visualization
================================
Full-width normalized heatmap showing all 5 clusters clearly
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns

# Load data
stats_df = pd.read_csv('../results/cluster_statistics.csv')

# Material columns
materials = ['MIX TN_avg', 'GRADE CY_avg', 'BASE TN_avg', 'SHLDR TN_avg',
             'MILL SY_avg', 'CRUSH TN_avg', 'STOCK TN_avg']
material_names = ['Asphalt (tons)', 'Grading (cu yd)', 'Base (tons)',
                  'Shoulder (tons)', 'Milling (sq yd)', 'Crushing (tons)', 'Stockpile (tons)']

# Get data - shape is (5 clusters, 7 materials)
material_data = stats_df[materials].fillna(0).values

# TRANSPOSE to (7 materials, 5 clusters) for proper row/column layout
material_data_T = material_data.T

# Normalize each row (material) from 0 to 1
material_data_normalized = np.zeros_like(material_data_T, dtype=float)
material_data_annot = np.empty_like(material_data_T, dtype=object)

for i in range(material_data_T.shape[0]):  # For each material (row)
    min_val = material_data_T[i].min()
    max_val = material_data_T[i].max()
    material_data_normalized[i] = (material_data_T[i] - min_val) / (max_val - min_val)
    # Format annotation values with commas
    material_data_annot[i] = [f'{int(v):,}' for v in material_data_T[i]]

# Create large figure for heatmap only
fig, ax = plt.subplots(figsize=(16, 8))

# Create heatmap - rows are materials, columns are clusters
sns.heatmap(material_data_normalized,
            annot=material_data_annot,
            fmt='',
            cmap='RdYlGn',
            xticklabels=[f'Cluster {i}' for i in range(5)],
            yticklabels=material_names,
            cbar_kws={'label': 'Relative Intensity (0=minimum, 1=maximum per material)'},
            linewidths=2,
            linecolor='white',
            annot_kws={'size': 10, 'weight': 'bold'},
            vmin=0,
            vmax=1,
            ax=ax)

# Style the plot
ax.set_xlabel('Cluster', fontsize=14, fontweight='bold')
ax.set_ylabel('Material Type', fontsize=14, fontweight='bold')
ax.set_title('Material Quantities per Cluster\n(Row-normalized: Green=Max, Red=Min for each material type)',
            fontsize=14, fontweight='bold', pad=20)

# Increase font sizes
ax.tick_params(axis='x', labelsize=12)
ax.tick_params(axis='y', labelsize=12)

# Rotate x labels for clarity
plt.setp(ax.get_xticklabels(), rotation=0, ha='center')

plt.tight_layout()
plt.savefig('../visualizations/cluster_heatmap_normalized_fullwidth.png', dpi=300, bbox_inches='tight')
print("✅ Saved: ../visualizations/cluster_heatmap_normalized_fullwidth.png")
plt.close()

# Also create a version with normalized scores only
fig, ax = plt.subplots(figsize=(16, 8))

sns.heatmap(material_data_normalized,
            annot=True,
            fmt='.2f',
            cmap='RdYlGn',
            xticklabels=[f'Cluster {i}' for i in range(5)],
            yticklabels=material_names,
            cbar_kws={'label': 'Normalized Score (0-1)'},
            linewidths=2,
            linecolor='white',
            annot_kws={'size': 11, 'weight': 'bold'},
            vmin=0,
            vmax=1,
            ax=ax)

ax.set_xlabel('Cluster', fontsize=14, fontweight='bold')
ax.set_ylabel('Material Type', fontsize=14, fontweight='bold')
ax.set_title('Material Quantities per Cluster (Normalized Scores)\n(0.0=minimum, 1.0=maximum for each material)',
            fontsize=14, fontweight='bold', pad=20)

ax.tick_params(axis='x', labelsize=12)
ax.tick_params(axis='y', labelsize=12)
plt.setp(ax.get_xticklabels(), rotation=0, ha='center')

plt.tight_layout()
plt.savefig('../visualizations/cluster_heatmap_normalized_scores.png', dpi=300, bbox_inches='tight')
print("✅ Saved: ../visualizations/cluster_heatmap_normalized_scores.png")
plt.close()

print("\n" + "="*80)
print("HEATMAP INTERPRETATION")
print("="*80)
print("\nColor meanings:")
print("  🟢 GREEN (1.0) = Maximum value for that material (across all clusters)")
print("  🟡 YELLOW (0.5) = Medium value for that material")
print("  🔴 RED (0.0) = Minimum value for that material")
print("\nExamples:")
print("  • Grading: Cluster 4 is GREEN (1.7M cu yd) = max grading")
print("  • Milling: Cluster 3 is GREEN (1.3M sq yd) = max milling")
print("  • Shoulders: Cluster 2 is GREEN (313K tons) = max shoulders")
print("  • Asphalt: Cluster 2 is GREEN (71K tons) = max asphalt")
print("\nAll clusters are now equally visible despite extreme value differences!")
