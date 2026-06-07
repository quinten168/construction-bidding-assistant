"""
PCA Component Selection Analysis
=================================
Demonstrates different methods to determine optimal number of PCA components:

1. Cumulative Explained Variance (most common)
2. Elbow Method
3. Kaiser Criterion
4. Scree Plot visualization

Author: Quinten
Date: 2026-06-07
"""

import pandas as pd
import numpy as np
from sklearn.preprocessing import StandardScaler
from sklearn.decomposition import PCA
import matplotlib.pyplot as plt

# Load data
df = pd.read_csv("CSI_data_long_format.csv")
material_cols = ['MIX TN', 'GRADE CY', 'BASE TN', 'SHLDR TN', 'MILL SY', 'CRUSH TN', 'STOCK TN']
X = df[material_cols].fillna(0)
X_scaled = StandardScaler().fit_transform(X)

# Fit PCA with all components
pca_full = PCA()
pca_full.fit(X_scaled)

print("=" * 100)
print("PCA COMPONENT SELECTION METHODS")
print("=" * 100)

# ============================================================================
# METHOD 1: CUMULATIVE EXPLAINED VARIANCE
# ============================================================================
print("\n1. CUMULATIVE EXPLAINED VARIANCE METHOD")
print("-" * 100)

cum_var = np.cumsum(pca_full.explained_variance_ratio_)
print(f"\nExplained variance by component:")
for i, (var, cum) in enumerate(zip(pca_full.explained_variance_ratio_, cum_var), 1):
    print(f"  PC{i}: {var:6.1%} variance | Cumulative: {cum:6.1%}")

print(f"\n✓ To explain 80% variance: need {np.argmax(cum_var >= 0.80) + 1} components")
print(f"✓ To explain 90% variance: need {np.argmax(cum_var >= 0.90) + 1} components")
print(f"✓ To explain 95% variance: need {np.argmax(cum_var >= 0.95) + 1} components")

# ============================================================================
# METHOD 2: ELBOW METHOD
# ============================================================================
print("\n\n2. ELBOW METHOD")
print("-" * 100)

# Calculate differences between consecutive components
variance_diff = np.diff(pca_full.explained_variance_ratio_, prepend=0)
print(f"\nMarginal gain from each component:")
for i, (var, diff) in enumerate(zip(pca_full.explained_variance_ratio_, variance_diff), 1):
    print(f"  PC{i}: {var:6.1%} variance | Marginal gain: {diff:6.1%}")

# Find elbow (where marginal gain drops significantly)
elbow_threshold = 0.05  # 5% drop
print(f"\n✓ Elbow point (where marginal gain < {elbow_threshold*100:.0f}%): PC{np.argmax(pca_full.explained_variance_ratio_ < elbow_threshold) + 1}")

# ============================================================================
# METHOD 3: KAISER CRITERION
# ============================================================================
print("\n\n3. KAISER CRITERION (eigenvalue > 1)")
print("-" * 100)

eigenvalues = pca_full.explained_variance_
print(f"\nEigenvalues by component:")
for i, eig in enumerate(eigenvalues, 1):
    print(f"  PC{i}: eigenvalue = {eig:.3f} {'✓' if eig > 1 else '❌'}")

kaiser_components = np.sum(eigenvalues > 1)
print(f"\n✓ Kaiser criterion suggests: {kaiser_components} components (eigenvalue > 1)")

# ============================================================================
# VISUALIZATION
# ============================================================================
print("\n\n4. CREATING VISUALIZATIONS...")
print("-" * 100)

fig, axes = plt.subplots(2, 2, figsize=(14, 10))

# Scree Plot
axes[0, 0].bar(range(1, len(pca_full.explained_variance_ratio_) + 1),
               pca_full.explained_variance_ratio_, alpha=0.7, color='steelblue')
axes[0, 0].set_xlabel('Principal Component')
axes[0, 0].set_ylabel('Explained Variance Ratio')
axes[0, 0].set_title('Scree Plot: Variance per Component')
axes[0, 0].set_xticks(range(1, len(pca_full.explained_variance_ratio_) + 1))
axes[0, 0].grid(axis='y', alpha=0.3)

# Cumulative Explained Variance
axes[0, 1].plot(range(1, len(cum_var) + 1), cum_var, 'o-', color='darkgreen', linewidth=2, markersize=8)
axes[0, 1].axhline(y=0.80, color='red', linestyle='--', label='80%')
axes[0, 1].axhline(y=0.90, color='orange', linestyle='--', label='90%')
axes[0, 1].axhline(y=0.95, color='purple', linestyle='--', label='95%')
axes[0, 1].set_xlabel('Number of Components')
axes[0, 1].set_ylabel('Cumulative Explained Variance')
axes[0, 1].set_title('Cumulative Explained Variance')
axes[0, 1].set_xticks(range(1, len(cum_var) + 1))
axes[0, 1].legend()
axes[0, 1].grid(True, alpha=0.3)
axes[0, 1].set_ylim([0, 1.05])

# Eigenvalues (Kaiser Criterion)
axes[1, 0].bar(range(1, len(eigenvalues) + 1), eigenvalues, alpha=0.7, color='coral')
axes[1, 0].axhline(y=1, color='red', linestyle='--', linewidth=2, label='Kaiser threshold (eigenvalue=1)')
axes[1, 0].set_xlabel('Principal Component')
axes[1, 0].set_ylabel('Eigenvalue')
axes[1, 0].set_title('Kaiser Criterion: Eigenvalues per Component')
axes[1, 0].set_xticks(range(1, len(eigenvalues) + 1))
axes[1, 0].legend()
axes[1, 0].grid(axis='y', alpha=0.3)

# Marginal Gain (Elbow)
axes[1, 1].bar(range(1, len(pca_full.explained_variance_ratio_) + 1),
               pca_full.explained_variance_ratio_, alpha=0.7, color='purple')
axes[1, 1].axhline(y=0.05, color='red', linestyle='--', linewidth=2, label='Elbow threshold (5%)')
axes[1, 1].set_xlabel('Principal Component')
axes[1, 1].set_ylabel('Variance Contribution')
axes[1, 1].set_title('Elbow Method: Marginal Gain per Component')
axes[1, 1].set_xticks(range(1, len(pca_full.explained_variance_ratio_) + 1))
axes[1, 1].legend()
axes[1, 1].grid(axis='y', alpha=0.3)

plt.tight_layout()
plt.savefig('pca_component_selection.png', dpi=100, bbox_inches='tight')
print("✓ Saved: pca_component_selection.png\n")

# ============================================================================
# SUMMARY & RECOMMENDATION
# ============================================================================
print("\n" + "=" * 100)
print("SUMMARY & RECOMMENDATION FOR CSI")
print("=" * 100)

print(f"""
METHOD RECOMMENDATIONS:

1. CUMULATIVE EXPLAINED VARIANCE (Most practical)
   - For 80% explanation: 3 components
   - For 90% explanation: 5 components
   - For 95% explanation: 6 components
   ➜ RECOMMENDED: Use 3-4 components for balance of information vs. visualization

2. ELBOW METHOD
   - Suggests diminishing returns after PC2 (marginal gain < 5%)
   ➜ USEFUL: For exploratory analysis to see where "information runs out"

3. KAISER CRITERION
   - Components with eigenvalue > 1: {kaiser_components} components
   ➜ BEST FOR: Statistical rigor, but often conservative

4. VISUALIZATION GOAL
   - 2 components: Easy 2D scatter plot
   - 3 components: 3D plot (harder to visualize)
   - 4+ components: Need other visualization methods
   ➜ BEST FOR: Stakeholder presentations

FOR YOUR CSI PROJECT:
✓ Used 2 components: 48.4% variance (good for visualization)
✓ Could use 3 components: ~56% variance (better info retention)
✓ Could use 4 components: ~65% variance (more info, harder to visualize)

DECISION FRAMEWORK:
- Exploratory/Visualization → 2-3 components
- Production/Analysis → 3-5 components (cumulative 80-90%)
- Maximum Info Retention → 6-7 components (cumulative 95%+)
""")

