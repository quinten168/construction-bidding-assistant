# Clustering Analysis: CSI Project Types

Complete clustering analysis implementation for categorizing 1,661 CSI highway projects into 5 meaningful project types.

## 📁 Folder Structure

```
clustering/
├── scripts/                  # Reusable Python analysis code
│   ├── clustering_analysis.py              # Main K-Medoids + K-Modes clustering
│   ├── visualize_tuning_decisions.py       # Gamma & k parameter tuning visualization
│   └── interpret_pca_results.py            # PCA component interpretation
├── results/                  # Clustering outputs (data)
│   ├── CSI_data_combined_with_clusters.csv # Main result: original data + cluster labels
│   ├── cluster_statistics.csv              # Summary: material averages per cluster
│   ├── gamma_tuning_summary.csv            # Gamma parameter tuning results
│   └── k_validation_summary.csv            # K validation results (k=3,4,5)
├── visualizations/          # All charts and plots
│   ├── clusters_visualization.png          # PCA scatter plots (PC1/PC2, PC3/PC4)
│   ├── silhouette_plot.png                 # Cluster quality assessment
│   ├── gamma_tuning_analysis.png           # Parameter tuning visualization
│   ├── k_validation_analysis.png           # K validation visualization
│   ├── pca_component_loadings.png          # How materials contribute to PCA components
│   └── clusters_in_pca_space_annotated.png # Clusters in PC1-PC4 space
└── README.md                # This file
```

## 🚀 Quick Start

### Run Complete Clustering Analysis
```bash
cd clustering/scripts/
python clustering_analysis.py
# Generates: CSI_data_combined_with_clusters.csv, cluster_statistics.csv, 
#            clusters_visualization.png, silhouette_plot.png
```

### Visualize Tuning Decisions
```bash
cd clustering/scripts/
python visualize_tuning_decisions.py
# Generates: gamma_tuning_analysis.png, k_validation_analysis.png,
#            gamma_tuning_summary.csv, k_validation_summary.csv
```

### Interpret PCA Components
```bash
cd clustering/scripts/
python interpret_pca_results.py
# Generates: pca_component_loadings.png, clusters_in_pca_space_annotated.png,
#            PCA_INTERPRETATION_GUIDE.txt
```

## 📊 Key Results

- **Model**: K-Medoids + K-Modes Hybrid
- **Clusters Found**: 5 project types (vs. planned 4)
- **Silhouette Score**: 0.5700 (exceeds 0.4 target)
- **Gamma Parameter**: 0.1 (materials dominate over infrastructure type)
- **Cluster Distribution**:
  - Cluster 0: 1,197 projects (72%) - Routine/Maintenance
  - Cluster 1: 360 projects (22%) - Medium Asphalt Overlay
  - Cluster 2: 78 projects (5%) - Large Projects
  - Cluster 3: 15 projects (1%) - Extreme Structural
  - Cluster 4: 11 projects (1%) - **Extreme Grading** (NEW DISCOVERY)

## 📋 File Descriptions

### Scripts

| Script | Purpose | Output |
|--------|---------|--------|
| `clustering_analysis.py` | Main clustering implementation (K-Medoids + K-Modes) | clustered data + visualizations |
| `visualize_tuning_decisions.py` | Shows how gamma and k were tuned | tuning plots + summary CSVs |
| `interpret_pca_results.py` | Explains what each PCA component means | interpretation guide + plots |

### Results

| File | Contains |
|------|----------|
| `CSI_data_combined_with_clusters.csv` | Original 1,661 projects with cluster assignments (0-4) |
| `cluster_statistics.csv` | Per-cluster statistics: material averages, BOX %, counts |
| `gamma_tuning_summary.csv` | Silhouette scores for γ = 0.1, 0.3, 0.5, 1.0, 2.0 |
| `k_validation_summary.csv` | Silhouette scores for k = 3, 4, 5 |

### Visualizations

| Plot | Shows |
|------|-------|
| `clusters_visualization.png` | Clusters in PCA space (PC1 vs PC2, PC3 vs PC4) |
| `silhouette_plot.png` | Silhouette analysis: cluster quality & cohesion |
| `gamma_tuning_analysis.png` | How silhouette score changes with gamma |
| `k_validation_analysis.png` | How silhouette score changes with k |
| `pca_component_loadings.png` | How each material loads on PC1-PC4 |
| `clusters_in_pca_space_annotated.png` | Cluster separation in PC1-PC4 space |

## 🔍 Understanding the Results

### What are the 5 Clusters?

**Cluster 0 (72%)**: Routine/Maintenance Projects
- Small material quantities across all types
- Typical: small overlay, minor repairs, shoulder work
- Median asphalt: 2,266 tons

**Cluster 1 (22%)**: Medium Asphalt Overlay
- High asphalt (30K tons) and milling (120K SY)
- Typical: reclamation, wear course, shouldering
- Medium-scale overlay projects

**Cluster 2 (5%)**: Large Projects
- Very high shoulder material (313K tons)
- Significant asphalt (71K tons)
- Major resurfacing with extensive shoulders

**Cluster 3 (1%)**: Extreme Structural
- Massive milling (1.3M SY)
- **40% have BOX culverts** (vs 11% average)
- Major reconstruction with infrastructure replacement

**Cluster 4 (1%)**: Extreme Grading ← **NEW DISCOVERY**
- Extreme grading: 1.7M cubic yards average
- Low asphalt, high earthwork
- Rare specialty projects in land reconfiguration

## 🎯 Next Steps

1. **Competitor Analysis**: Which competitors bid on which clusters?
2. **Bidding Strategy**: How should CSI approach each cluster differently?
3. **Cost Estimation**: Material-to-price ratios per cluster
4. **Market Gaps**: Under-served project types

## 📚 Reference

For detailed methodology and full results, see:
- `../../docs/CLUSTERING_PLAN.md` — Complete plan + implementation results
- `../../docs/PCA_INTERPRETATION_GUIDE.txt` — How to interpret PCA components
- `../../docs/CHANGELOG.md` — Data cleaning lineage

## 🔧 Technical Details

- **Language**: Python 3.7+
- **Main Libraries**: scikit-learn, scikit-learn-extra, scipy, pandas, matplotlib
- **Algorithm**: K-Medoids + K-Modes Hybrid with gamma-weighted distance
- **Data Input**: `../../data/processed/CSI_data_combined.csv` (1,661 projects)
- **Random State**: 42 (reproducible results)

## 📝 Notes

- All scripts use relative paths, so run from the `scripts/` directory
- Output files are automatically saved to `../results/` and `../visualizations/`
- To regenerate all outputs: `python clustering_analysis.py && python visualize_tuning_decisions.py && python interpret_pca_results.py`
