"""
Clustering Analysis: Project Types by Materials (K-Medoids + K-Modes Hybrid)
===========================================================================
Implements hybrid K-Medoids + K-Modes clustering for mixed data types:
- Continuous: 7 material quantities → PCA → K-Medoids (Euclidean distance)
- Categorical: BOX infrastructure attribute → K-Modes (Hamming distance)
- Combined via gamma-weighted distance matrix

Purpose: Cluster 1,661 CSI highway projects into 4 meaningful project types
that capture construction complexity and material composition patterns.

Author: Quinten
Date: 2026-06-07
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from sklearn.preprocessing import StandardScaler
from sklearn.decomposition import PCA
from sklearn.metrics import silhouette_score, silhouette_samples
from sklearn_extra.cluster import KMedoids
from scipy.spatial.distance import cdist
import warnings
warnings.filterwarnings('ignore')

sns.set_style("whitegrid")

# Configuration
CONTINUOUS_COLS = ['MIX TN', 'GRADE CY', 'BASE TN', 'SHLDR TN', 'MILL SY', 'CRUSH TN', 'STOCK TN']
CATEGORICAL_COLS = ['BOX']
N_PCA_COMPONENTS = 4
BASELINE_K = 4
GAMMA_VALUES = [0.1, 0.3, 0.5, 1.0, 2.0]
K_VALUES = [3, 4, 5]
RANDOM_STATE = 42

# ============================================================================
# DATA LOADING & PREPARATION
# ============================================================================

def load_and_prepare_data():
    """Load CSI_data_combined.csv and prepare features (wide format, project-level)"""
    print("Loading data...")
    df = pd.read_csv('../../data/processed/CSI_data_combined.csv')
    print(f"✓ Loaded {len(df)} projects, {len(df.columns)} columns")

    # Fill nulls with 0 (no material = 0 tons/cubic yards)
    X_continuous = df[CONTINUOUS_COLS].fillna(0).astype(float)
    X_categorical = df[CATEGORICAL_COLS].fillna(0).astype(int)

    print(f"✓ Continuous features: {X_continuous.shape}")
    print(f"✓ Categorical features: {X_categorical.shape}")

    return df, X_continuous, X_categorical

# ============================================================================
# PCA ON CONTINUOUS VARIABLES
# ============================================================================

def apply_pca(X_continuous):
    """Apply StandardScaler and PCA to continuous variables"""
    print("\nApplying StandardScaler...")
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X_continuous)
    print(f"✓ Scaled: mean={X_scaled.mean():.4f}, std={X_scaled.std():.4f}")

    print(f"\nApplying PCA (n_components={N_PCA_COMPONENTS})...")
    pca = PCA(n_components=N_PCA_COMPONENTS)
    X_pca = pca.fit_transform(X_scaled)

    var_explained = pca.explained_variance_ratio_
    cumsum_var = np.cumsum(var_explained)

    print(f"✓ Variance explained per component: {var_explained}")
    print(f"✓ Cumulative variance: {cumsum_var[-1]:.3f} ({cumsum_var[-1]*100:.1f}%)")

    # Print component loadings
    print(f"\nPCA Component Loadings:")
    components_df = pd.DataFrame(
        pca.components_,
        columns=CONTINUOUS_COLS,
        index=[f'PC{i+1}' for i in range(N_PCA_COMPONENTS)]
    )
    print(components_df.round(3))

    return X_pca, pca, scaler

# ============================================================================
# HYBRID DISTANCE MATRIX
# ============================================================================

def hybrid_distance_matrix(X_pca, X_categorical, gamma=0.5):
    """
    Compute hybrid distance matrix combining:
    - Euclidean distance on continuous PCA variables
    - Hamming distance on categorical variables
    Weighted by gamma parameter: Total Cost = D_euclidean + gamma * D_hamming
    """
    D_cont = cdist(X_pca, X_pca, metric='euclidean')
    D_cat = cdist(X_categorical.values, X_categorical.values, metric='hamming')
    return D_cont + gamma * D_cat

# ============================================================================
# K-MEDOIDS FIT
# ============================================================================

def fit_kmedoids(D_hybrid, n_clusters=4):
    """Fit K-Medoids on precomputed hybrid distance matrix"""
    kmedoids = KMedoids(
        n_clusters=n_clusters,
        metric='precomputed',
        method='pam',
        init='k-medoids++',
        random_state=RANDOM_STATE
    )
    labels = kmedoids.fit_predict(D_hybrid)
    return kmedoids, labels

# ============================================================================
# GAMMA TUNING
# ============================================================================

def tune_gamma(X_pca, X_categorical, gamma_values=GAMMA_VALUES, k=BASELINE_K):
    """Tune gamma parameter and evaluate silhouette scores"""
    print(f"\n{'='*70}")
    print(f"GAMMA TUNING (k={k})")
    print(f"{'='*70}")
    print(f"{'Gamma':<8} {'Silhouette':<15} {'Cluster Distribution':<40}")
    print(f"{'-'*70}")

    results = {}
    for gamma in gamma_values:
        D = hybrid_distance_matrix(X_pca, X_categorical, gamma=gamma)
        _, labels = fit_kmedoids(D, n_clusters=k)
        score = silhouette_score(D, labels, metric='precomputed')
        dist = pd.Series(labels).value_counts().sort_index().to_dict()
        results[gamma] = {'score': score, 'labels': labels, 'dist': dist}

        print(f"{gamma:<8.1f} {score:<15.4f} {str(dist):<40}")

    best_gamma = max(results.keys(), key=lambda x: results[x]['score'])
    print(f"\n✓ Best gamma: {best_gamma} (silhouette={results[best_gamma]['score']:.4f})")
    return best_gamma, results

# ============================================================================
# K VALIDATION
# ============================================================================

def validate_k(X_pca, X_categorical, best_gamma, k_values=K_VALUES):
    """Validate optimal number of clusters"""
    print(f"\n{'='*70}")
    print(f"K VALIDATION (gamma={best_gamma})")
    print(f"{'='*70}")
    print(f"{'K':<5} {'Silhouette':<15} {'Cluster Distribution':<40}")
    print(f"{'-'*70}")

    D = hybrid_distance_matrix(X_pca, X_categorical, gamma=best_gamma)
    results = {}

    for k in k_values:
        _, labels = fit_kmedoids(D, n_clusters=k)
        score = silhouette_score(D, labels, metric='precomputed')
        dist = pd.Series(labels).value_counts().sort_index().to_dict()
        results[k] = {'score': score, 'labels': labels, 'dist': dist}

        print(f"{k:<5} {score:<15.4f} {str(dist):<40}")

    best_k = max(results.keys(), key=lambda x: results[x]['score'])
    print(f"\n✓ Best k: {best_k} (silhouette={results[best_k]['score']:.4f})")
    return best_k, results

# ============================================================================
# CLUSTER PROFILING
# ============================================================================

def profile_clusters(df, X_pca, X_categorical, labels, kmedoids):
    """Generate cluster profiles and statistics"""
    print(f"\n{'='*70}")
    print(f"CLUSTER PROFILES")
    print(f"{'='*70}")

    df_with_clusters = df.copy()
    df_with_clusters['cluster'] = labels

    stats = []
    for cluster_id in sorted(df_with_clusters['cluster'].unique()):
        c = df_with_clusters[df_with_clusters['cluster'] == cluster_id]
        n_projects = len(c)
        pct = (n_projects / len(df_with_clusters)) * 100

        medoid_idx = kmedoids.medoid_indices_[cluster_id]
        medoid_project = df.iloc[medoid_idx]['PROJECT'] if 'PROJECT' in df.columns else f"Row {medoid_idx}"

        print(f"\nCluster {cluster_id}: {n_projects} projects ({pct:.1f}%)")
        print(f"  Medoid project: {medoid_project}")

        for col in CONTINUOUS_COLS:
            avg = c[col].mean()
            print(f"  Avg {col:15s}: {avg:12.1f}")

        box_pct = c['BOX'].mean() * 100
        print(f"  % with BOX:     {box_pct:12.1f}%")

        stats.append({
            'cluster_id': cluster_id,
            'n_projects': n_projects,
            'pct_of_total': pct,
            'medoid_project': medoid_project,
            **{f'{col}_avg': c[col].mean() for col in CONTINUOUS_COLS},
            'box_pct': box_pct
        })

    return df_with_clusters, pd.DataFrame(stats)

# ============================================================================
# VISUALIZATION
# ============================================================================

def plot_pca_clusters(X_pca, labels, output_path='clusters_visualization.png'):
    """Create PCA scatter plots colored by cluster"""
    print(f"\nGenerating PCA visualizations...")
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))

    scatter1 = axes[0].scatter(X_pca[:, 0], X_pca[:, 1], c=labels, cmap='viridis', alpha=0.6, s=30)
    axes[0].set_xlabel(f'PC1 (28.1%)')
    axes[0].set_ylabel(f'PC2 (20.3%)')
    axes[0].set_title('PCA: PC1 vs PC2')
    axes[0].grid(True, alpha=0.3)
    plt.colorbar(scatter1, ax=axes[0], label='Cluster')

    scatter2 = axes[1].scatter(X_pca[:, 2], X_pca[:, 3], c=labels, cmap='viridis', alpha=0.6, s=30)
    axes[1].set_xlabel(f'PC3 (14.8%)')
    axes[1].set_ylabel(f'PC4 (14.3%)')
    axes[1].set_title('PCA: PC3 vs PC4')
    axes[1].grid(True, alpha=0.3)
    plt.colorbar(scatter2, ax=axes[1], label='Cluster')

    plt.tight_layout()
    plt.savefig(f'../visualizations/{output_path}', dpi=300)
    print(f"✓ Saved to ../visualizations/{output_path}")
    plt.close()

def plot_silhouette(D_hybrid, labels, output_path='silhouette_plot.png'):
    """Create silhouette analysis plot"""
    print(f"Generating silhouette plot...")
    silhouette_vals = silhouette_samples(D_hybrid, labels, metric='precomputed')
    silhouette_avg = silhouette_score(D_hybrid, labels, metric='precomputed')

    fig, ax = plt.subplots(figsize=(10, 6))
    y_lower = 10

    for i in sorted(np.unique(labels)):
        cluster_silhouette_vals = silhouette_vals[labels == i]
        cluster_silhouette_vals.sort()

        size_cluster_i = cluster_silhouette_vals.shape[0]
        y_upper = y_lower + size_cluster_i

        ax.fill_betweenx(np.arange(y_lower, y_upper), 0, cluster_silhouette_vals, alpha=0.7)
        y_lower = y_upper + 10

    ax.axvline(x=silhouette_avg, color="red", linestyle="--", label=f"Avg: {silhouette_avg:.3f}")
    ax.set_xlabel("Silhouette Coefficient")
    ax.set_ylabel("Cluster")
    ax.set_title(f"Silhouette Analysis (k={len(np.unique(labels))})")
    ax.legend()
    plt.tight_layout()
    plt.savefig(f'../visualizations/{output_path}', dpi=300)
    print(f"✓ Saved to ../visualizations/{output_path}")
    plt.close()

# ============================================================================
# MAIN
# ============================================================================

if __name__ == '__main__':
    print(f"\n{'='*70}")
    print(f"CSI PROJECT CLUSTERING ANALYSIS (K-Medoids + K-Modes Hybrid)")
    print(f"{'='*70}")

    # Load and prepare data
    df, X_continuous, X_categorical = load_and_prepare_data()

    # Apply PCA
    X_pca, pca, scaler = apply_pca(X_continuous)

    # Tune gamma
    best_gamma, gamma_results = tune_gamma(X_pca, X_categorical, gamma_values=GAMMA_VALUES, k=BASELINE_K)

    # Validate k
    best_k, k_results = validate_k(X_pca, X_categorical, best_gamma, k_values=K_VALUES)

    # Fit final model
    print(f"\n{'='*70}")
    print(f"FITTING FINAL MODEL (k={best_k}, gamma={best_gamma})")
    print(f"{'='*70}")

    D_final = hybrid_distance_matrix(X_pca, X_categorical, gamma=best_gamma)
    kmedoids_final, labels_final = fit_kmedoids(D_final, n_clusters=best_k)
    final_silhouette = silhouette_score(D_final, labels_final, metric='precomputed')

    print(f"✓ Final silhouette score: {final_silhouette:.4f}")
    print(f"✓ Cluster distribution: {pd.Series(labels_final).value_counts().sort_index().to_dict()}")

    # Profile clusters
    df_clustered, stats_df = profile_clusters(df, X_pca, X_categorical, labels_final, kmedoids_final)

    # Save results
    print(f"\n{'='*70}")
    print(f"SAVING RESULTS")
    print(f"{'='*70}")

    df_clustered.to_csv('../results/CSI_data_combined_with_clusters.csv', index=False)
    print(f"✓ Saved clustered data to ../results/CSI_data_combined_with_clusters.csv")

    stats_df.to_csv('../results/cluster_statistics.csv', index=False)
    print(f"✓ Saved cluster statistics to ../results/cluster_statistics.csv")

    # Visualizations
    plot_pca_clusters(X_pca, labels_final)
    plot_silhouette(D_final, labels_final)

    print(f"\n{'='*70}")
    print(f"CLUSTERING COMPLETE")
    print(f"{'='*70}")
    print(f"Final model: K-Medoids + K-Modes (k={best_k}, gamma={best_gamma})")
    print(f"Silhouette score: {final_silhouette:.4f}")
    print(f"Output files: CSI_data_combined_with_clusters.csv, cluster_statistics.csv")
    print(f"             clusters_visualization.png, silhouette_plot.png")
