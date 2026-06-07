# Documentation

Complete reference materials for the CSI clustering project.

## 📄 Documents

### 📋 `CLUSTERING_PLAN.md` (29 KB) - **PRIMARY REFERENCE**

**Status**: ✅ Complete (Plan + Implementation Results)

**Contains**:
- Executive summary with key results
- Data challenges & solutions
- PCA methodology (4 components, 77.2% variance)
- K-Medoids + K-Modes hybrid model explanation
- **Full implementation results** (Section 11):
  - Gamma tuning results (5 gamma values tested)
  - K validation results (k=3,4,5 tested)
  - Final model parameters (gamma=0.1, k=5)
  - Actual cluster profiles (5 clusters with material statistics)
  - Quality assessment (silhouette=0.5700)
  - Reproducibility instructions
  - Output files list
- Next steps after clustering

**Read this for**: Understanding the complete clustering approach and results

**Audience**: Quinten, team members, stakeholders

---

### 📋 `CHANGELOG.md` (14 KB) - DATA LINEAGE

**Status**: ✅ Complete (Documentation of all data transformations)

**Contains**:
- CSI_data_combined.csv creation (2024+2025 merge)
- 3 cleaning passes with specific changes:
  - Pass 1: Date/time reformatting, location parsing, ID extraction
  - Pass 2: Expanded ID extraction (recovered 774 missing project IDs)
  - Pass 3: Bidder name standardization, long format pivot, duplicate removal
- Data integrity notes
- Before/after statistics for each pass

**Read this for**: Understanding data quality decisions and transformations

**Audience**: Data analysts, QA reviewers, auditors

---


## 🗂️ Which Document to Read When

| Question | Document |
|----------|----------|
| "What are the 5 project clusters?" | CLUSTERING_PLAN.md (Section 11.4) |
| "How were clusters decided?" | CLUSTERING_PLAN.md (Section 11.1-11.2) |
| "What's the silhouette score?" | CLUSTERING_PLAN.md (Section 11.5) |
| "What data cleaning was done?" | CHANGELOG.md |
| "Why 5 clusters instead of 4?" | CLUSTERING_PLAN.md (Section 11.6) |
| "What do PC1, PC2, PC3, PC4 mean?" | CLUSTERING_PLAN.md (Section 4 - PCA Components) |
| "How do I reproduce this?" | CLUSTERING_PLAN.md (Section 11.8) |
| "What files were generated?" | CLUSTERING_PLAN.md (Section 11.7) |

---

## 📊 Document Relationships

```
CLUSTERING_PLAN.md ← Main reference
    ├─ References data from CHANGELOG.md
    ├─ References interpretation from PCA_INTERPRETATION_GUIDE.txt
    └─ Points to output files in ../clustering/

CHANGELOG.md ← Data quality
    └─ Explains transformations leading to CSI_data_combined.csv
       (input for clustering)

PCA_INTERPRETATION_GUIDE.txt ← Technical details
    └─ Explains what the PCA components mean
       (referenced in CLUSTERING_PLAN.md)
```

---

## ✅ When These Were Created/Updated

| Document | Created | Last Updated | Status |
|----------|---------|--------------|--------|
| CLUSTERING_PLAN.md | 2026-06-07 | 2026-06-07 | ✅ Complete with results + PCA interpretation |
| CHANGELOG.md | 2026-06-06 | 2026-06-07 | ✅ Complete |

---

## 🔄 Recommended Reading Order

**For Project Overview** (5 min):
1. CLUSTERING_PLAN.md - Executive Summary (top)
2. CLUSTERING_PLAN.md - Section 11.4 (Cluster Profiles)

**For Technical Understanding** (20 min):
1. CLUSTERING_PLAN.md - Sections 1-5 (Methodology + PCA explanation)
2. CLUSTERING_PLAN.md - Section 4 (Detailed PCA Component Interpretation)
3. CLUSTERING_PLAN.md - Section 11 (Results)

**For Data Quality** (10 min):
1. CHANGELOG.md (Data transformations)
2. CLUSTERING_PLAN.md - Section 11.7 (Output files)

**For Implementation/Reproducibility** (15 min):
1. CLUSTERING_PLAN.md - Section 11.8 (How to run)
2. ../clustering/README.md (Scripts guide)
3. ../data/README.md (Data guide)

---

## 📚 External References (if needed)

- Scikit-learn K-Medoids: https://scikit-learn-extra.readthedocs.io/
- PCA concept: https://scikit-learn.org/stable/modules/decomposition.html#pca
- Silhouette score: https://scikit-learn.org/stable/modules/generated/sklearn.metrics.silhouette_score.html

---

## 📝 Notes

- All files are in Markdown or plain text for easy viewing/editing
- Documents are in git version control for change tracking
- Updates should maintain version history (don't overwrite without notes)
- Mathematical notation: See CLUSTERING_PLAN.md Section 5 for distance formula
