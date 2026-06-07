"""
PCA Interpretation: Understanding the 4 Components
==================================================
Shows what each PCA component means in terms of original materials,
and maps clusters back to interpretable material characteristics.
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from sklearn.preprocessing import StandardScaler
from sklearn.decomposition import PCA

CONTINUOUS_COLS = ['MIX TN', 'GRADE CY', 'BASE TN', 'SHLDR TN', 'MILL SY', 'CRUSH TN', 'STOCK TN']

def load_and_analyze_pca():
    """Load data, apply PCA, analyze components"""
    print("="*80)
    print("PCA INTERPRETATION ANALYSIS")
    print("="*80)

    # Load data
    df = pd.read_csv('../../data/processed/CSI_data_combined.csv')
    X = df[CONTINUOUS_COLS].fillna(0).astype(float)

    # Standardize
    print("\n[STEP 1] StandardScaling the 7 material variables...")
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)
    print(f"✓ Scaled to mean=0, std=1")

    # Apply PCA
    print("\n[STEP 2] Applying PCA (4 components)...")
    pca = PCA(n_components=4)
    X_pca = pca.fit_transform(X_scaled)

    print(f"✓ Transformed 7 dimensions → 4 components")
    print(f"  Variance explained: {np.array2string(pca.explained_variance_ratio_, precision=3)}")
    print(f"  Cumulative: {np.cumsum(pca.explained_variance_ratio_)[-1]:.1%}")

    return df, X, X_scaled, X_pca, pca, scaler

def interpret_loadings(pca):
    """Analyze and interpret PCA component loadings"""
    print("\n" + "="*80)
    print("PCA COMPONENT LOADINGS")
    print("="*80)
    print("\nLoadings = How much each original variable contributes to each component")
    print("(Higher absolute value = stronger influence)\n")

    loadings_df = pd.DataFrame(
        pca.components_,
        columns=CONTINUOUS_COLS,
        index=[f'PC{i+1}' for i in range(len(pca.components_))]
    )

    print(loadings_df.round(3))

    # Find dominant variables for each component
    print("\n" + "-"*80)
    print("DOMINANT VARIABLES PER COMPONENT (Interpretation)")
    print("-"*80)

    interpretations = {}

    for i, component in enumerate(pca.components_):
        pc_name = f'PC{i+1}'
        abs_loadings = np.abs(component)
        top_indices = np.argsort(abs_loadings)[-3:][::-1]  # Top 3

        print(f"\n{pc_name} ({pca.explained_variance_ratio_[i]:.1%} variance):")
        top_vars = [(CONTINUOUS_COLS[j], component[j], abs_loadings[j]) for j in top_indices]

        for var, loading, abs_loading in top_vars:
            direction = "↑" if loading > 0 else "↓"
            print(f"  {direction} {var:15s}: {loading:7.3f} (weight: {abs_loading:.3f})")

        # Manual interpretation based on loadings
        if i == 0:  # PC1
            interpretations[pc_name] = {
                'name': 'Project Scale',
                'meaning': 'Larger projects have more materials overall',
                'drivers': ['BASE TN', 'STOCK TN', 'MILL SY'],
                'business': 'Projects with more base layer, stockpile, and milling = bigger projects'
            }
        elif i == 1:  # PC2
            interpretations[pc_name] = {
                'name': 'Asphalt Focus',
                'meaning': 'Contrast between asphalt-heavy vs other materials',
                'drivers': ['MIX TN', 'SHLDR TN'],
                'business': 'High = overlay/resurfacing projects (asphalt + shoulders)'
            }
        elif i == 2:  # PC3
            interpretations[pc_name] = {
                'name': 'Grading Intensity',
                'meaning': 'Projects focused on earthwork/grading',
                'drivers': ['GRADE CY'],
                'business': 'High = grading-heavy projects (extensive earthwork)'
            }
        elif i == 3:  # PC4
            interpretations[pc_name] = {
                'name': 'Material Crushing',
                'meaning': 'Separation by crushing operations',
                'drivers': ['CRUSH TN'],
                'business': 'High = aggregate/crushing operations; Low = asphalt/overlay'
            }

    print("\n" + "="*80)
    print("COMPONENT INTERPRETATIONS")
    print("="*80)

    for pc, interp in interpretations.items():
        print(f"\n{pc}: {interp['name']} ({pca.explained_variance_ratio_[int(pc[2])-1]:.1%})")
        print(f"  Meaning: {interp['meaning']}")
        print(f"  Business: {interp['business']}")

    return loadings_df, interpretations

def plot_loadings(pca, loadings_df):
    """Visualize PCA loadings"""
    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    axes = axes.flatten()

    for i in range(len(pca.components_)):
        ax = axes[i]
        pc_name = f'PC{i+1}'
        loadings = pca.components_[i]
        var_explained = pca.explained_variance_ratio_[i]

        # Bar plot
        colors = ['red' if x < 0 else 'steelblue' for x in loadings]
        ax.barh(CONTINUOUS_COLS, loadings, color=colors, alpha=0.7, edgecolor='black')
        ax.set_xlabel('Loading Value', fontsize=11, fontweight='bold')
        ax.set_title(f'{pc_name}: {var_explained:.1%} Variance', fontsize=12, fontweight='bold')
        ax.axvline(x=0, color='black', linewidth=0.8)
        ax.grid(axis='x', alpha=0.3)

        # Add value labels
        for j, (label, val) in enumerate(zip(CONTINUOUS_COLS, loadings)):
            ax.text(val + 0.02 if val > 0 else val - 0.02, j, f'{val:.3f}',
                   va='center', ha='left' if val > 0 else 'right', fontsize=9)

    plt.tight_layout()
    plt.savefig('../visualizations/pca_component_loadings.png', dpi=300, bbox_inches='tight')
    print("\n✓ Saved: ../visualizations/pca_component_loadings.png")
    plt.close()

def map_clusters_to_materials():
    """Load final clusters and show what they mean in original material space"""
    print("\n" + "="*80)
    print("CLUSTERS IN ORIGINAL MATERIAL SPACE")
    print("="*80)
    print("\nWhat do the 5 clusters actually mean in terms of materials?\n")

    df = pd.read_csv('../results/CSI_data_combined_with_clusters.csv')

    for cluster_id in sorted(df['cluster'].unique()):
        cluster_data = df[df['cluster'] == cluster_id]
        n_projects = len(cluster_data)
        pct = n_projects / len(df) * 100

        print(f"CLUSTER {cluster_id}: {n_projects} projects ({pct:.1f}%)")
        print(f"{'─'*70}")

        # Material characteristics
        for col in CONTINUOUS_COLS:
            avg = cluster_data[col].mean()
            median = cluster_data[col].median()
            print(f"  {col:15s}:  avg={avg:12,.0f}  |  median={median:12,.0f}")

        # BOX characteristic
        box_pct = cluster_data['BOX'].mean() * 100
        print(f"  {'BOX (%)':15s}:  {box_pct:5.1f}%")

        # Business interpretation
        print(f"\n  Business Meaning:")
        if cluster_id == 0:
            print(f"    → ROUTINE/MAINTENANCE: Low material quantities across all types")
            print(f"    → Typical: Small overlay, minor repairs, shoulder work")
        elif cluster_id == 1:
            print(f"    → MEDIUM ASPHALT OVERLAY: High asphalt & milling, moderate others")
            print(f"    → Typical: Reclamation, wear course, shouldering projects")
        elif cluster_id == 2:
            print(f"    → LARGE PROJECTS: Very high shoulder material, significant asphalt")
            print(f"    → Typical: Major resurfacing with extensive shoulders")
        elif cluster_id == 3:
            print(f"    → EXTREME STRUCTURAL: Massive milling, 40% have BOX culverts")
            print(f"    → Typical: Major reconstruction with infrastructure replacement")
        elif cluster_id == 4:
            print(f"    → EXTREME GRADING: 1.7M+ cubic yards grading average")
            print(f"    → Typical: Large-scale earthwork, major reconstruction")

        print()

def plot_pca_space_by_cluster(X_pca, cluster_labels):
    """Visualize clusters in PCA space"""
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))

    # PC1 vs PC2
    scatter1 = axes[0].scatter(X_pca[:, 0], X_pca[:, 1], c=cluster_labels,
                               cmap='viridis', alpha=0.6, s=30, edgecolors='black', linewidth=0.3)
    axes[0].set_xlabel('PC1: Project Scale (28.1%)', fontsize=11, fontweight='bold')
    axes[0].set_ylabel('PC2: Asphalt Focus (20.3%)', fontsize=11, fontweight='bold')
    axes[0].set_title('Clusters in PCA Space: PC1 vs PC2', fontsize=12, fontweight='bold')
    axes[0].grid(True, alpha=0.3)
    plt.colorbar(scatter1, ax=axes[0], label='Cluster')

    # PC3 vs PC4
    scatter2 = axes[1].scatter(X_pca[:, 2], X_pca[:, 3], c=cluster_labels,
                               cmap='viridis', alpha=0.6, s=30, edgecolors='black', linewidth=0.3)
    axes[1].set_xlabel('PC3: Grading Intensity (14.8%)', fontsize=11, fontweight='bold')
    axes[1].set_ylabel('PC4: Material Crushing (14.3%)', fontsize=11, fontweight='bold')
    axes[1].set_title('Clusters in PCA Space: PC3 vs PC4', fontsize=12, fontweight='bold')
    axes[1].grid(True, alpha=0.3)
    plt.colorbar(scatter2, ax=axes[1], label='Cluster')

    plt.tight_layout()
    plt.savefig('../visualizations/clusters_in_pca_space_annotated.png', dpi=300, bbox_inches='tight')
    print("✓ Saved: ../visualizations/clusters_in_pca_space_annotated.png")
    plt.close()

def create_interpretation_guide():
    """Create a simple interpretation guide"""
    guide = """
PCA INTERPRETATION GUIDE FOR CSI CLUSTERING
============================================

WHAT IS PCA?
PCA (Principal Component Analysis) reduces 7 correlated material variables into
4 uncorrelated components while keeping 77.2% of the information.

WHY USE PCA?
- Removes multicollinearity (materials are correlated—larger projects need more of everything)
- Makes clustering more robust (noise reduction)
- Enables visualization of 4D data
- Speeds up computation

THE 4 COMPONENTS EXPLAINED
==========================

PC1 (28.1% variance): PROJECT SCALE
  ├─ High values: Larger projects with more materials overall
  ├─ Driven by: BASE TN (base layer), STOCK TN (stockpile), MILL SY (milling)
  └─ Business: Projects requiring substantial base prep and material storage

PC2 (20.3% variance): ASPHALT FOCUS
  ├─ High values: Asphalt overlay/resurfacing projects
  ├─ Driven by: MIX TN (hot mix asphalt), SHLDR TN (shoulder gravel)
  └─ Business: Overlay vs reconstruction vs grading-heavy projects

PC3 (14.8% variance): GRADING INTENSITY
  ├─ High values: Earthwork and grading-focused projects
  ├─ Driven by: GRADE CY (cubic yards of grading)
  └─ Business: Major grading operations; land reconfiguration

PC4 (14.3% variance): MATERIAL CRUSHING
  ├─ High values: Aggregate/crushing operations
  ├─ Driven by: CRUSH TN (tons of material to crush)
  └─ Business: Quarry work; aggregate production vs finished surfaces

HOW TO INTERPRET CLUSTERS
==========================

Each cluster is a group of projects with similar:
1. Material composition (via PC1-PC4)
2. Infrastructure complexity (via BOX categorical variable)

Example:
  Cluster 1 (High PC2, moderate PC1)
    → Medium-scale projects
    → Asphalt-focused (overlay/resurfacing)
    → Less likely to have BOX culverts
    → Interpretation: MEDIUM ASPHALT OVERLAY PROJECTS

TRACING BACK TO ORIGINAL MATERIALS
===================================

If a cluster has high PC1 and PC3:
  • PC1 high = large projects
  • PC3 high = grading-heavy
  → Interpretation: Large grading-intensive projects

To see actual material values: Check cluster_statistics.csv

WHY NOT SKIP PCA?
=================

Direct clustering on 7 materials would:
  ❌ Be slower (O(n²) computation)
  ❌ Give more weight to correlated variables (unfair)
  ❌ Be noisier (multicollinearity)
  ❌ Be harder to visualize

With PCA:
  ✅ Faster computation
  ✅ Fair weighting of independent information
  ✅ Cleaner clusters (noise reduced)
  ✅ Can visualize in 2D/3D
  ✅ Still interpretable (via loadings)

KEY TAKEAWAY
============

The 5 clusters represent 5 distinct PROJECT TYPES, each with a characteristic
material and infrastructure profile. The PCA transformation lets us find these
types cleanly; the loadings let us interpret what they mean in business terms.

Think of it like this:
  Original space: 7 confusing, correlated variables
  ↓ PCA ↓
  Reduced space: 4 independent "themes" (Scale, Asphalt, Grading, Crushing)
  ↓ K-Medoids ↓
  Clusters: 5 meaningful project types

"""

    with open('../../docs/PCA_INTERPRETATION_GUIDE.txt', 'w') as f:
        f.write(guide)

    print(guide)
    print("\n✓ Saved: ../../docs/PCA_INTERPRETATION_GUIDE.txt")

def main():
    df, X, X_scaled, X_pca, pca, scaler = load_and_analyze_pca()
    loadings_df, interpretations = interpret_loadings(pca)
    plot_loadings(pca, loadings_df)

    # Load final clusters for interpretation
    df_clustered = pd.read_csv('CSI_data_combined_with_clusters.csv')
    map_clusters_to_materials()
    plot_pca_space_by_cluster(X_pca, df_clustered['cluster'].values)

    create_interpretation_guide()

    print("\n" + "="*80)
    print("PCA INTERPRETATION COMPLETE")
    print("="*80)
    print("\nGenerated files:")
    print("  ✓ pca_component_loadings.png - Visualize how variables load on each component")
    print("  ✓ clusters_in_pca_space_annotated.png - See clusters in PC1-PC2 and PC3-PC4 space")
    print("  ✓ PCA_INTERPRETATION_GUIDE.txt - Full interpretation guide")

if __name__ == '__main__':
    main()
