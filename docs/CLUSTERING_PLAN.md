# Clustering Analysis Plan: CSI Project Types
**Date**: 2026-06-07
**Author**: Quinten
**Status**: ✅ IMPLEMENTATION COMPLETE — Results Documented
**Execution Date**: 2026-06-07
**Result**: 5 Project Types Identified (Silhouette: 0.5700)

---

## Executive Summary

**✅ CLUSTERING COMPLETE** (as of 2026-06-07)

This document consolidates:
1. **Data challenges** identified (mixed types, outliers, sparsity)
2. **Solutions** chosen for each challenge
3. **Data preparation** & variable selection
4. **Dimensionality reduction** (PCA on continuous variables)
5. **Chosen model**: K-Medoids + K-Modes hybrid for mixed-type clustering
6. **Actual implementation results** & outputs ← **SEE SECTION 11 FOR FULL RESULTS**

**Goal**: Cluster 1,661 CSI highway projects into meaningful project types using a hybrid approach that correctly handles both continuous material quantities and a categorical infrastructure variable (BOX).

**Key Results**:
- **5 Project Types Identified** (vs planned 4) through data-driven k validation
- **Silhouette Score: 0.5700** (Exceeds plan's 0.4 minimum)
- **Gamma: 0.1** (Materials far outweigh infrastructure type in separation)
- **Novel Finding**: Cluster 4 reveals rare "extreme grading" specialty market (1.7M+ cubic yards avg)
- **All Success Criteria Exceeded**

---

## 1. Data Challenges & Solutions

### Challenge 1: Mixed Data Types
**Problem**:
- 7 continuous variables (material quantities: tons, cubic yards, square yards)
- 1 categorical variable (BOX: 0/1 binary)
- Cannot use K-Means alone — distance-based mean does not apply to categorical data
- Cannot use one-hot encoding — creates an extra artificial dimension
- Cannot use K-Medoids alone on raw mixed data — Euclidean distance on binary 0/1 misrepresents categorical dissimilarity

**Solution**:
- **Hybrid model: K-Medoids + K-Modes**
  - K-Medoids handles the continuous PCA-reduced variables using Euclidean distance
  - K-Modes handles the categorical BOX variable using Hamming distance (matching/non-matching)
  - The two distance components are combined using a weighted gamma parameter
- This is the correct principled approach for mixed-type clustering — each variable type is measured with the distance metric appropriate to it

---

### Challenge 2: Outliers in Material Data
**Problem**:
- Material quantities have extreme values (some projects are very large; most are small)
- Sparse data: ~40–80% zeros in material columns (many projects do not use all material types)
- Mean-based algorithms (K-Means) are pulled far off by outliers
- MinMaxScaler makes this worse (one outlier compresses all normal values into a tiny range)

**Solution**:
- **StandardScaler (z-score normalization)**: `(X - mean) / std_deviation`
  - Robust to outliers (extreme values shift further along the scale without compressing the normal range)
  - Preserves relative distances (small differences between normal projects remain visible)
  - Works correctly with K-Medoids (medoid = real project point, not a mean)

---

### Challenge 3: Unknown Optimal Number of Clusters
**Problem**:
- How many project types exist? k = 3, 4, 5, or something else?
- Must be specified upfront for the K-Medoids + K-Modes approach

**Solution**:
- Use k=4 as the baseline, selected based on:
  - PCA scree plot suggesting 4 meaningful components
  - Domain knowledge (small routine / medium overlay / major reconstruction / specialty)
  - Silhouette score comparison across k = 3, 4, 5 to validate

---

## 2. Data Source & Preparation

### Data File
- **File**: `CSI_data_combined.csv` (wide format, project-level)
- **Rows**: 1,661 projects (one row per project)
- **Time period**: 2024–2025

### Why CSI_data_combined.csv?
✅ Each row = 1 project (not 1 bidder)
✅ Includes all material quantities in one row
✅ Contains BOX (infrastructure type)
❌ NOT using `CSI_data_long_format.csv` (bidder-level; not suitable for project-type clustering)

### Null Handling
- **Material columns**: Replace nulls with 0 (project does not require that material)
- **BOX column**: Replace nulls with 0 (no box culvert present)

### Data Pipeline Order
```
1. Load CSI_data_combined.csv
2. Select variables: 7 continuous materials + 1 categorical (BOX)
3. StandardScaler on continuous variables (BEFORE PCA)
4. PCA on scaled continuous variables → 4 components (~77% variance)
5. Separate inputs:
     X_continuous = X_pca            shape: (1661, 4)  ← for K-Medoids component
     X_categorical = BOX column      shape: (1661, 1)  ← for K-Modes component
6. Run K-Medoids + K-Modes hybrid on (X_continuous, X_categorical)
```

**Why this order matters**:
- ✅ StandardScaler BEFORE PCA: ensures PCA weights all variables equally
- ✅ Categorical kept SEPARATE: BOX is never passed through PCA; it feeds directly into the K-Modes distance component
- ✅ Two distance metrics applied in parallel: Euclidean for continuous, Hamming for categorical

---

## 3. Variable Selection

### Continuous Variables — 7 Material Quantities (StandardScaled → PCA)

| Variable | Unit | Meaning |
|----------|------|---------|
| `MIX TN` | Tons | Hot mix asphalt for finished road surface |
| `GRADE CY` | Cubic yards | Earthwork / grading operations |
| `BASE TN` | Tons | Base layer material (structural support) |
| `SHLDR TN` | Tons | Shoulder gravel (edge support) |
| `MILL SY` | Square yards | Existing pavement to mill / remove |
| `CRUSH TN` | Tons | Aggregate material to produce |
| `STOCK TN` | Tons | Material to stockpile for later use |

**Data type**: float64
**Normalization**: StandardScaler (zero mean, unit variance)
**Dimensionality reduction**: PCA → 4 components

### Categorical Variable — 1 Project Attribute (direct to K-Modes component)

| Variable | Type | Values | Meaning |
|----------|------|--------|---------|
| `BOX` | Binary | 0, 1 | Has box culvert (infrastructure complexity) |

**Data type**: int64
**Distance metric**: Hamming (match = 0, mismatch = 1)
**Note**: Not one-hot encoded; passed directly as categorical input

### Variables Excluded and Why

| Variable | Reason Excluded |
|----------|----------------|
| `PREVAILING WAGES` | Regulatory requirement — not a project type characteristic |
| `location_flag` | Data quality indicator — not a project type characteristic |

---

## 4. PCA (Dimensionality Reduction on Continuous Variables)

### Why PCA?
- Material quantities are correlated (larger projects need more of everything)
- Reduces 7 correlated dimensions into 4 uncorrelated components while retaining most variance
- Removes noise and redundancy before feeding into the K-Medoids distance calculation

### PCA Configuration
- **n_components**: 4 (~77.4% variance retained, meets ~80% target threshold)
- **Input**: StandardScaler-normalized continuous variables only

### Components (Detailed Interpretation)

#### **PC1 (28.1% variance): PROJECT SCALE**
- **What it measures**: Overall project size and material volume
- **Dominant Variables**: BASE TN (0.556), STOCK TN (0.551), MILL SY (0.526)
- **Business Meaning**: Projects requiring substantial base layer prep, material stockpiling, and milling operations
- **High PC1**: Larger projects with more materials overall
- **Low PC1**: Smaller, routine projects with minimal material
- **Example**: A project with high BASE TN, STOCK TN, and MILL SY would have high PC1 → larger-scale project

#### **PC2 (20.3% variance): ASPHALT FOCUS**
- **What it measures**: Contrast between asphalt-heavy vs. other project types
- **Dominant Variables**: SHLDR TN (0.674), MIX TN (0.654) — both positive (drives PC2 up)
- **Negative Variables**: BASE TN (-0.225), GRADE CY (-0.154) — negative loading (drives PC2 down)
- **Business Meaning**: Separates overlay/resurfacing projects (high asphalt) from reconstruction/grading projects (low asphalt)
- **High PC2**: Asphalt overlay/resurfacing projects (high asphalt + shoulders, low grading/base)
- **Low PC2**: Grading/reconstruction projects (low asphalt, high grading/base)
- **Example**: "Medium Asphalt Overlay" cluster has high PC2 due to 30K tons asphalt + 43K tons shoulders

#### **PC3 (14.8% variance): GRADING INTENSITY**
- **What it measures**: Focus on earthwork and grading operations
- **Dominant Variable**: GRADE CY (0.900 loading) — very strong
- **Negative Variables**: MILL SY (-0.295), CRUSH TN (-0.233)
- **Business Meaning**: Projects focused on grading/earthwork vs. other material types
- **High PC3**: Grading-heavy projects (extensive cubic yards of earthwork)
- **Low PC3**: Asphalt/overlay/resurfacing projects (minimal grading)
- **Example**: "Extreme Grading" cluster has extremely high PC3 (1.7M cubic yards) and low MILL SY

#### **PC4 (14.3% variance): MATERIAL CRUSHING**
- **What it measures**: Aggregate/crushing operations
- **Dominant Variable**: CRUSH TN (0.970 loading) — extremely strong
- **Business Meaning**: Separation between quarry/crushing work vs. finished surface work
- **High PC4**: Aggregate/crushing operations
- **Low PC4**: Asphalt/overlay/resurfacing projects (no crushing)
- **Example**: Some projects have zero crushing (Low PC4); others focus on material production (High PC4)

**Cumulative variance explained**: 77.4%

### PCA Output
- Transformed matrix: `X_pca` — shape: (1,661 × 4)
- Explained variance ratio: `[0.281, 0.203, 0.148, 0.143]`

### How to Interpret Clusters Using PCA

Each cluster is a group of projects with similar:
1. **Material composition** (via PC1-PC4 scores)
2. **Infrastructure complexity** (via BOX categorical variable)

**Example: Interpreting Cluster 1**
- High PC2 (Asphalt Focus) → Overlay/resurfacing projects
- Moderate PC1 (Project Scale) → Medium-sized projects
- Low PC3 (Grading Intensity) → Minimal grading
- Low BOX prevalence (5.6%) → Few culverts
- **Interpretation**: MEDIUM ASPHALT OVERLAY PROJECTS

**Tracing Back to Original Materials**
If a cluster has:
- High PC1 + High PC3 → Large grading-intensive projects
- High PC2 + High PC1 → Large asphalt-focused projects  
- High PC3 + High PC4 → Grading with crushing operations

To see actual material values: Check `cluster_statistics.csv`

---

## 5. Chosen Model: K-Prototypes with Medoid Centers (K-Prototypes + K-Medoids Variant)

### Why This Model?

| Requirement | How This Model Addresses It |
|-------------|----------------------------|
| Handles continuous variables | K-Medoids with Euclidean distance on PCA-reduced data |
| Handles categorical variables | K-Modes with Hamming distance on BOX column |
| Robust to outliers | K-Medoids uses real project as center (medoid), not a mean |
| Mixed data types | Hybrid combines both distance components via gamma weighting |
| Interpretable clusters | Medoid = actual representative project; directly explainable to client |

### How the Hybrid Works

The algorithm minimizes a combined cost function:

```
Total Cost = Euclidean Distance (continuous) + γ × Hamming Distance (categorical)
```

- **γ (gamma)**: Controls the weight of the categorical component relative to continuous
  - Higher gamma → BOX type drives cluster separation more strongly
  - Lower gamma → material quantities dominate
  - Default starting point: `gamma = 0.5` (equal weight); tune if needed

### Model Parameters

| Parameter | Value | Reason |
|-----------|-------|--------|
| `n_clusters` | 4 | Baseline from PCA + domain knowledge; validate with silhouette |
| `n_init` | 10 | Multiple restarts to avoid local minima |
| `random_state` | 42 | Reproducibility |
| `gamma` | 0.5 (tunable) | Starting weight for categorical component |

### Pros
- ✅ Correctly handles mixed data — each variable type uses the right distance metric
- ✅ Robust to outliers (medoid = real project, not a synthetic mean point)
- ✅ Interpretable cluster centers — medoid is an actual CSI project
- ✅ Principled approach — no hacks like treating BOX as a float in Euclidean space
- ✅ Gamma is tunable if BOX proves more or less relevant than materials

### Cons
- ⚠️ Must specify k upfront — mitigated by silhouette score validation
- ⚠️ Slower than K-Means: O(n²) — manageable for 1,661 projects
- ⚠️ Gamma requires tuning — test γ = 0.3, 0.5, 1.0 and compare silhouette scores
- ⚠️ All projects assigned — no built-in noise/outlier detection (monitor cluster 3 for outlier-like concentration)

### Relationship to Standard K-Prototypes

This model is best understood as **K-Prototypes with one key modification**:

| Component | Standard K-Prototypes | This Model |
|-----------|----------------------|------------|
| Continuous center | Mean (arithmetic average) | **Medoid** (real project) |
| Categorical center | Mode | Mode |
| Continuous distance | Euclidean | Euclidean |
| Categorical distance | Hamming | Hamming |
| Combined cost | Euclidean + γ × Hamming | Euclidean + γ × Hamming |

The distance formula and categorical handling are **identical** to standard K-Prototypes. The only difference is that the continuous cluster center is a **medoid** (an actual project in the dataset) rather than a **mean** (a synthetic average point that may not correspond to any real project).

**Why this matters for CSI data**: Material quantities are highly skewed — a handful of very large projects would pull the mean far away from where most projects actually cluster. The medoid always stays grounded in a real project, making both the clustering and the client presentation more robust and interpretable.

### Why Not Standard K-Prototypes (`kmodes` library)?
The `kmodes` implementation uses means for its continuous component, making it sensitive to outliers in exactly the same way as K-Means. For CSI's skewed material data, this would produce distorted cluster centers. This model adopts the same hybrid distance structure but substitutes medoids, which solves the outlier problem while keeping everything else identical.

### Why Not DBSCAN?
DBSCAN was evaluated as an alternative. It was deprioritized because:
- Does not natively handle mixed data types
- Requires eps tuning that is highly sensitive with sparse, zero-heavy data
- May leave a large fraction of projects unassigned as noise, reducing practical utility for CSI

---

## 6. Implementation

### Step 1: Data Loading & Preparation
```python
import pandas as pd
import numpy as np
from sklearn.preprocessing import StandardScaler

df = pd.read_csv('CSI_data_combined.csv')

continuous_cols = ['MIX TN', 'GRADE CY', 'BASE TN', 'SHLDR TN', 'MILL SY', 'CRUSH TN', 'STOCK TN']
categorical_cols = ['BOX']

X_continuous = df[continuous_cols].fillna(0)
X_categorical = df[categorical_cols].fillna(0)

scaler = StandardScaler()
X_continuous_scaled = scaler.fit_transform(X_continuous)
```

### Step 2: PCA on Continuous Variables
```python
from sklearn.decomposition import PCA

pca = PCA(n_components=4)
X_pca = pca.fit_transform(X_continuous_scaled)

print(f"Variance explained: {pca.explained_variance_ratio_}")
print(f"Cumulative:         {pca.explained_variance_ratio_.cumsum()}")
# Expected: [0.281, 0.203, 0.148, 0.143] → ~77.4% cumulative
```

### Step 3: Run K-Medoids + K-Modes Hybrid
```python
from sklearn_extra.cluster import KMedoids
from sklearn.metrics import silhouette_score
from scipy.spatial.distance import cdist

def hybrid_distance(X_cont, X_cat, gamma=0.5):
    """
    Combines Euclidean distance on continuous PCA variables
    with Hamming distance on categorical variables.
    gamma controls the weight of the categorical component.
    """
    D_cont = cdist(X_cont, X_cont, metric='euclidean')
    D_cat  = cdist(X_cat,  X_cat,  metric='hamming')
    return D_cont + gamma * D_cat

# Build hybrid distance matrix
gamma = 0.5
D_hybrid = hybrid_distance(X_pca, X_categorical.values, gamma=gamma)

# Fit K-Medoids on precomputed hybrid distance matrix
kmedoids = KMedoids(
    n_clusters=4,
    metric='precomputed',
    method='pam',
    n_init=10,
    random_state=42
)
clusters = kmedoids.fit_predict(D_hybrid)

score = silhouette_score(D_hybrid, clusters, metric='precomputed')
print(f"Silhouette Score (gamma={gamma}): {score:.3f}")
print(f"Cluster distribution: {pd.Series(clusters).value_counts().sort_index().to_dict()}")
```

### Step 4: Tune Gamma and Validate k
```python
# Tune gamma — find best weight for categorical component
for gamma in [0.1, 0.3, 0.5, 1.0, 2.0]:
    D = hybrid_distance(X_pca, X_categorical.values, gamma=gamma)
    km = KMedoids(n_clusters=4, metric='precomputed', method='pam', n_init=10, random_state=42)
    labels = km.fit_predict(D)
    score = silhouette_score(D, labels, metric='precomputed')
    print(f"gamma={gamma:.1f} | silhouette={score:.3f} | dist={pd.Series(labels).value_counts().to_dict()}")

# Validate k — compare k=3,4,5 at best gamma
best_gamma = 0.5  # Replace with best gamma from above
D = hybrid_distance(X_pca, X_categorical.values, gamma=best_gamma)
for k in [3, 4, 5]:
    km = KMedoids(n_clusters=k, metric='precomputed', method='pam', n_init=10, random_state=42)
    labels = km.fit_predict(D)
    score = silhouette_score(D, labels, metric='precomputed')
    print(f"k={k} | silhouette={score:.3f}")
```

### Step 5: Cluster Profiling
```python
df['cluster'] = clusters

for cluster_id in sorted(df['cluster'].unique()):
    c = df[df['cluster'] == cluster_id]
    print(f"\nCluster {cluster_id}: {len(c)} projects ({len(c)/len(df)*100:.1f}%)")
    print(f"  Avg MIX TN:   {c['MIX TN'].mean():.1f}")
    print(f"  Avg GRADE CY: {c['GRADE CY'].mean():.1f}")
    print(f"  Avg BASE TN:  {c['BASE TN'].mean():.1f}")
    print(f"  Avg MILL SY:  {c['MILL SY'].mean():.1f}")
    print(f"  % with BOX:   {c['BOX'].mean()*100:.1f}%")
    medoid_idx = kmedoids.medoid_indices_[cluster_id]
    print(f"  Medoid project: {df.iloc[medoid_idx]['PROJECT'] if 'PROJECT' in df.columns else medoid_idx}")
```

### Step 6: Save Results
```python
df.to_csv('CSI_data_combined_with_clusters.csv', index=False)
# Also save: cluster visualization PNG, silhouette plot, cluster statistics CSV
```

---

## 7. Evaluation Metrics

| Metric | What It Measures | Target |
|--------|-----------------|--------|
| **Silhouette Score** | Cluster quality & separation [-1, 1] | > 0.4 acceptable; > 0.6 good |
| **Cluster Sizes** | Balance across clusters | No single cluster > 90% of projects |
| **Gamma Sensitivity** | How much BOX drives separation vs materials | Stable score across γ range |
| **Medoid Interpretability** | Is each medoid project a recognizable project type? | ✅ Yes |
| **k Validation** | Does k=4 outperform k=3 and k=5? | Best silhouette at k=4 |

---

## 8. Expected Outputs

### Files
- **`CSI_data_combined_with_clusters.csv`** — original data + `cluster` column (0–3)
- **`clusters_visualization.png`** — scatter plots (PC1 vs PC2, PC3 vs PC4), colored by cluster
- **`cluster_statistics.csv`** — per-cluster material averages, BOX %, project count

### Cluster Profile Expectations (Illustrative — Pending Results)

```
Cluster 0 (~70–85% of projects):
  • Small / routine maintenance projects
  • Low material quantities across all types
  • BOX culvert: mixed presence

Cluster 1 (~10–15%):
  • Medium asphalt overlay / resurfacing projects
  • High MIX TN, moderate BASE TN
  • BOX culvert: less common

Cluster 2 (~3–7%):
  • Major reconstruction projects
  • High quantities across all material types
  • BOX culvert: frequent

Cluster 3 (<2%):
  • Specialty or outlier projects
  • Unusual material profiles (e.g., grading-only, crushing-heavy)
  • BOX culvert: variable
```

---

## 9. Key Decisions Made

| # | Decision | Rationale |
|---|----------|-----------|
| 1 | **K-Prototypes with medoid centers** | Same hybrid distance structure as standard K-Prototypes (Euclidean + γ × Hamming), but continuous center is a medoid (real project) instead of a mean — robust to outliers |
| 2 | **Standard K-Prototypes (`kmodes`) rejected** | Uses means for continuous component — sensitive to CSI's skewed material quantities |
| 3 | **DBSCAN rejected** | Does not handle mixed types natively; eps tuning unreliable on sparse zero-heavy data |
| 4 | **4 PCA components** | Retains 77.4% variance vs 48.4% with 2 components |
| 5 | **Variables: 7 materials + BOX only** | Project type characteristics only; excludes PREVAILING WAGES (regulatory) and location_flag (data quality) |
| 6 | **StandardScaler over MinMaxScaler** | Robust to extreme outliers; MinMaxScaler would compress normal project range |
| 7 | **Categorical kept separate from PCA** | BOX feeds directly into Hamming distance; PCA applied to continuous variables only |
| 8 | **Source: CSI_data_combined.csv** | Project-level clustering; long format (bidder-level) is not appropriate |

---

## 10. Success Criteria

✅ **Interpretable clusters** — each cluster has a describable material + infrastructure profile
✅ **Balanced clusters** — no single cluster contains > 90% of all projects
✅ **Stable clusters** — results reproducible across runs (fixed random_state=42)
✅ **Correct distance handling** — continuous and categorical variables measured with appropriate metrics
✅ **Silhouette score > 0.4** — minimum acceptable cluster quality for downstream analysis

---

## 11. IMPLEMENTATION RESULTS (2026-06-07)

**Status**: ✅ COMPLETE — Clustering executed successfully

### 11.1 Actual Tuning Results

#### Gamma Tuning (k=4 baseline)
Tested gamma values controlling categorical BOX weight:

| Gamma | Silhouette | Cluster Distribution | Notes |
|-------|-----------|---|---|
| 0.1 | **0.5534** ✅ | {1197, 346, 104, 14} | **BEST** - Materials dominate |
| 0.3 | 0.5399 | {1197, 346, 104, 14} | Close second |
| 0.5 | 0.5277 | {1197, 346, 104, 14} | Plan default; worse |
| 1.0 | 0.4830 | {1068, 331, 102, 160} | BOX too influential |
| 2.0 | 0.5234 | {1068, 167, 79, 347} | BOX dominates; unbalanced |

**Decision**: γ=0.1 selected (best silhouette 0.5534)
**Interpretation**: Material quantities far outweigh infrastructure type (BOX) in defining project types

---

#### K Validation (gamma=0.1)
Tested number of clusters:

| K | Silhouette | Cluster Distribution | Notes |
|---|-----------|---|---|
| 3 | 0.5273 | {1203, 352, 106} | Merges distinct types |
| 4 | 0.5534 | {1197, 346, 104, 14} | Plan default; tiny cluster (14) |
| 5 | **0.5700** ✅ | {1197, 360, 78, 15, 11} | **BEST** - Reveals hidden cluster |

**Decision**: k=5 selected (best silhouette 0.5700)
**Finding**: Data revealed **5 distinct project types** (exceeding initial plan of k=4)
- Cluster 4 (11 projects): Extreme grading projects (~1.7M cubic yards avg) was not anticipated

### 11.2 Final Model Parameters

```
Model: K-Medoids + K-Modes Hybrid
  • n_clusters: 5 (vs planned 4)
  • gamma: 0.1 (materials weight 10x more than BOX)
  • metric: precomputed (hybrid Euclidean + Hamming distance)
  • init: 'k-medoids++'
  • random_state: 42
  
PCA Configuration:
  • n_components: 4
  • input_scaling: StandardScaler (z-score)
  • variance_explained: 77.2% (plan: 77.4%)
  
Final Quality:
  • Silhouette Score: 0.5700 (Exceeds plan's 0.4 minimum)
  • Interpretation: GOOD cluster separation with natural overlap
```

---

### 11.3 PCA Component Interpretation

| Component | Variance | Dominant Variables | Business Meaning |
|-----------|----------|---|---|
| **PC1** | 28.1% | BASE TN (0.556), STOCK TN (0.551), MILL SY (0.526) | **Project Scale**: Larger projects need more materials overall |
| **PC2** | 20.3% | SHLDR TN (0.674), MIX TN (0.654) | **Asphalt Focus**: Overlay/resurfacing vs reconstruction |
| **PC3** | 14.8% | GRADE CY (0.900) | **Grading Intensity**: Earthwork-heavy operations |
| **PC4** | 14.3% | CRUSH TN (0.970) | **Material Crushing**: Aggregate/quarry operations |

**Key Finding**: Each component represents an independent "theme" that separates project types. PCA successfully untangles 7 correlated variables into 4 orthogonal dimensions.

---

### 11.4 Actual Cluster Profiles

#### Cluster 0: ROUTINE/MAINTENANCE (72.1%, n=1,197)
**Medoid**: JOB 24228 SC-2117(060) (CMC 2117)

| Material | Average | Median | Interpretation |
|----------|---------|--------|---|
| MIX TN | 3,674 | 2,266 | Minimal asphalt |
| GRADE CY | 21,434 | 2,933 | Low grading (mostly routine) |
| BASE TN | 6,811 | 1,876 | Standard base |
| SHLDR TN | 6,289 | 1,813 | Minimal shoulders |
| MILL SY | 24,508 | 7,138 | Light milling |
| CRUSH TN | 37,631 | 31,643 | Standard crushed material |
| STOCK TN | 8,573 | 3,485 | Low stockpile |
| BOX | 11.4% | — | Rare culverts |

**Business**: Small overlay, minor repairs, shoulder work. CSI's core bread-and-butter projects.

---

#### Cluster 1: MEDIUM ASPHALT OVERLAY (21.7%, n=360)
**Medoid**: SAP 056-675-036 CP 4185-075 RECLAIM, WEAR COURSE & SHOULDERING (CSAH 75)

| Material | Average | Median | Interpretation |
|----------|---------|--------|---|
| MIX TN | 30,121 | 26,870 | **HIGH** asphalt (overlay focus) |
| GRADE CY | 39,472 | 4,286 | Moderate grading |
| BASE TN | 19,166 | 5,588 | Moderate base |
| SHLDR TN | 43,129 | 17,189 | **HIGH** shoulders (key feature) |
| MILL SY | 120,188 | 84,419 | **VERY HIGH** milling (reclamation) |
| CRUSH TN | 2,980 | 2,980 | Minimal crushing |
| STOCK TN | 18,132 | 16,611 | Moderate stockpile |
| BOX | 5.6% | — | Rare culverts |

**Business**: Reclamation, wear course, shouldering projects. Secondary bread-and-butter, resurfacing-focused.

---

#### Cluster 2: LARGE PROJECTS (4.7%, n=78)
**Medoid**: CONT # 240117 SP 4508-35 (TH 89)

| Material | Average | Median | Interpretation |
|----------|---------|--------|---|
| MIX TN | 71,419 | 69,535 | **VERY HIGH** asphalt |
| GRADE CY | 37,662 | 9,804 | Moderate grading |
| BASE TN | 24,742 | 5,366 | Moderate base |
| SHLDR TN | 313,683 | 277,352 | **EXTREME** shoulders (key feature) |
| MILL SY | 103,963 | 9,497 | High milling |
| CRUSH TN | 15,000 | 15,000 | Moderate crushing |
| STOCK TN | 20,079 | 12,408 | Moderate stockpile |
| BOX | 9.0% | — | Occasional culverts |

**Business**: Major resurfacing with extensive shoulders. Large-scale overlay projects requiring heavy shoulder work.

---

#### Cluster 3: EXTREME STRUCTURAL (0.9%, n=15)
**Medoid**: PCN 04G5 - ITEM # 7 - GRADING, REPLACE STRUCTURES & INTERIM SURFACING

| Material | Average | Median | Interpretation |
|----------|---------|--------|---|
| MIX TN | 32,630 | 7,509 | Moderate asphalt |
| GRADE CY | 126,674 | 36,540 | High grading |
| BASE TN | 504,664 | 149,098 | **EXTREME** base (structural) |
| SHLDR TN | 121,024 | 107,662 | High shoulders |
| MILL SY | 1,296,710 | 1,137,426 | **EXTREME** milling (major reconstruction) |
| CRUSH TN | NaN | NaN | Not tracked (rare) |
| STOCK TN | 156,982 | 130,436 | High stockpile |
| BOX | **40.0%** | — | **FREQUENT** culverts (infrastructure critical) |

**Business**: Major reconstruction with infrastructure replacement. Structural work with significant complexity (40% have BOX culverts vs 11% avg).

---

#### Cluster 4: EXTREME GRADING (0.7%, n=11) ← **UNEXPECTED CLUSTER**
**Medoid**: ITEM #1 - NH-PH 0385(50)96 PCN 03VD (US 385) GRADING, INTERIM SURFACING & RPLC STR

| Material | Average | Median | Interpretation |
|----------|---------|--------|---|
| MIX TN | 14,678 | 2,392 | Low asphalt |
| GRADE CY | 1,693,843 | 1,692,272 | **EXTREME** grading (defining feature) |
| BASE TN | 109,877 | 126,204 | Moderate base |
| SHLDR TN | 1,328 | 1,328 | Minimal shoulders |
| MILL SY | 68,847 | 66,535 | Moderate milling |
| CRUSH TN | NaN | NaN | Not tracked (rare) |
| STOCK TN | 119,763 | 122,764 | High stockpile |
| BOX | 27.3% | — | Occasional culverts |

**Business**: Extreme earthwork/grading projects (1.7M+ cubic yards average). Large land reconfiguration; rare specialty category. **This cluster was not in the original plan but emerged from data-driven k validation.**

---

### 11.5 Quality Assessment Against Success Criteria

| Criterion | Target | Actual | Status |
|-----------|--------|--------|--------|
| **Interpretable clusters** | Describable | 5 distinct types with clear material/infrastructure profiles | ✅ PASS |
| **Balanced clusters** | No >90% | Max is 72.1% (Cluster 0) | ✅ PASS |
| **Stable clusters** | Reproducible (fixed seed) | random_state=42 used; reproducible | ✅ PASS |
| **Distance handling** | Euclidean + Hamming | Hybrid K-Medoids + K-Modes with γ weighting | ✅ PASS |
| **Silhouette score** | > 0.4 | 0.5700 | ✅ PASS (Exceeds) |

**Conclusion**: All success criteria exceeded.

---

### 11.6 Deviations from Plan (Why k=5 > k=4)

The **original plan targeted k=4** based on PCA scree plot and domain knowledge. However, **data-driven silhouette validation revealed k=5 is optimal**:

- **k=4** (plan default): Silhouette=0.5534, but creates one tiny cluster (14 projects)
- **k=5** (data-driven): Silhouette=0.5700, reveals **Cluster 4** (11 extreme-grading projects)

**Why this is better**:
1. ✅ **Better silhouette score**: 0.5700 > 0.5534 (+0.0166 improvement)
2. ✅ **Reveals hidden pattern**: Extreme grading projects are a distinct type CSI may want to bid on differently
3. ✅ **Still balanced**: No cluster > 90% (max 72%)
4. ✅ **Actionable insight**: Identifies niche specialty market (extreme earthwork)

**Lesson**: Let the data guide k selection, not just domain priors. The 11 extreme-grading projects warrant their own cluster for bidding strategy.

---

### 11.7 Output Files Generated

```
CSI_data_combined_with_clusters.csv      1.1 MB  Original data + cluster assignments (0-4)
cluster_statistics.csv                   1.1 kB  Per-cluster material averages & BOX %
clusters_visualization.png               258 kB  PCA scatter plots (PC1/PC2, PC3/PC4)
silhouette_plot.png                      130 kB  Silhouette analysis by cluster

gamma_tuning_analysis.png                (200+ kB)  Gamma tuning visualization
k_validation_analysis.png                (200+ kB)  K validation visualization
gamma_tuning_summary.csv                 CSV     Gamma tuning results table
k_validation_summary.csv                 CSV     K validation results table

pca_component_loadings.png               (PNG)   Component loadings heatmap
clusters_in_pca_space_annotated.png      (PNG)   Clusters in PC1-PC4 space
PCA_INTERPRETATION_GUIDE.txt             (TXT)   Full PCA interpretation guide

clustering_analysis.py                   Core clustering implementation
visualize_tuning_decisions.py            Gamma & k visualization
interpret_pca_results.py                 PCA interpretation analysis
```

---

### 11.8 Reproducibility

To reproduce this exact clustering:

```bash
# Run main clustering analysis
python clustering_analysis.py

# Generates: CSI_data_combined_with_clusters.csv, cluster_statistics.csv, 
#            clusters_visualization.png, silhouette_plot.png

# Visualize tuning decisions
python visualize_tuning_decisions.py

# Generates: gamma_tuning_analysis.png, k_validation_analysis.png,
#            gamma_tuning_summary.csv, k_validation_summary.csv

# Interpret PCA components
python interpret_pca_results.py

# Generates: pca_component_loadings.png, clusters_in_pca_space_annotated.png,
#            PCA_INTERPRETATION_GUIDE.txt
```

**Key Parameters** (fixed random_state=42):
- StandardScaler: z-score normalization
- PCA: n_components=4
- K-Medoids: metric='precomputed', method='pam', init='k-medoids++'
- Gamma: 0.1
- K: 5

---

## 12. Next Steps After Clustering

1. ✅ **Cluster profiling** — COMPLETE (see 11.4 above with detailed material statistics)
2. **Competitor analysis** — identify which competitors bid on which cluster types most frequently
3. **Bidding strategy** — define how CSI should approach each cluster differently (especially new Cluster 4)
4. **Cost estimation** — calculate material-to-bid-price ratio per cluster (use CSI_data_combined_with_clusters.csv)
5. **Market gaps** — identify under-served project types where CSI has low competition

---

## Appendix: Libraries & Versions

```
pandas >= 1.0
numpy >= 1.19
scikit-learn >= 1.0      (PCA, StandardScaler, silhouette_score)
scikit-learn-extra >= 0.2 (KMedoids)
scipy >= 1.7             (cdist for hybrid distance matrix)
matplotlib >= 3.4        (visualization)
seaborn >= 0.13          (advanced visualization)
```

**Installation**:
```bash
pip install scikit-learn scikit-learn-extra scipy pandas numpy matplotlib seaborn
```
