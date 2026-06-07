# Data Files

CSI bidding and project data at various stages of processing.

## 📁 Folder Structure

```
data/
├── raw/                   # Original source files (archive)
│   ├── CSI_data_2024.csv  (253 KB) - 2024 bidding data
│   └── CSI_data_2025.csv  (377 KB) - 2025 bidding data
├── processed/             # Data after cleaning (MAIN)
│   ├── CSI_data_combined.csv        (1.1 MB) - Combined 2024+2025, cleaned
│   └── CSI_data_long_format.csv     (3.8 MB) - Bidder-level format (not used for clustering)
├── cleaning_review/       # Data QA artifacts (reference)
│   ├── bidder_full_company_list.csv
│   ├── bidder_potential_duplicates.csv
│   ├── bidder_standardization_review.csv
│   └── duplicate_project_review.csv
└── README.md              # This file
```

## 🔍 File Descriptions

### raw/ - Original Source Files

| File | Records | Columns | Purpose |
|------|---------|---------|---------|
| `CSI_data_2024.csv` | 695 projects | 52 | 2024 bidding data (raw) |
| `CSI_data_2025.csv` | 966 projects | 52 | 2025 bidding data (raw) |

**Status**: Archive. These are kept for version control history but should not be modified.

---

### processed/ - Cleaned & Combined Data

#### PRIMARY FILE: `CSI_data_combined.csv` (1.1 MB, 1,661 projects × 67 columns)

**Status**: ✅ **THIS IS THE MAIN DATA FILE** - Use for all analysis

**What it contains**:
- **Project-level data** (1 row = 1 project)
- **2024-2025 projects** merged and deduplicated
- **67 columns** including:
  - Core: DATE, TIME, LOCATION, PROJECT
  - Materials: MIX TN, GRADE CY, BASE TN, SHLDR TN, MILL SY, CRUSH TN, STOCK TN
  - Infrastructure: BOX (culvert type)
  - Bidders: BIDDER_1_NAME through BIDDER_15_NAME (project-wide bids)
  - IDs: csi_job_id, state_project_id, project_id_type, etc.
  - Flags: location_flag (data quality), PREVAILING WAGES

**Data Cleaning Applied**:
1. Combined CSI_data_2024.csv + CSI_data_2025.csv
2. Reformatted DATE to YYYY-MM-DD, TIME to HH:MM 24-hour
3. Parsed LOCATION into County, City, State
4. Extracted project IDs (SAP, CONTRACT, CSI JOB, PCN, etc.)
5. Split LAT/LON from combined LOCATION field
6. Standardized bidder names (ampersands, spacing)
7. Converted material quantities to float64
8. Converted BOX (X/null) to binary (1/0)
9. Added location_flag for coordinate quality checks

**For Clustering**: Use this file. It has project-level granularity (1 row = 1 project type).

---

#### ALTERNATIVE: `CSI_data_long_format.csv` (3.8 MB, 6,894 bidders × 40 columns)

**Status**: ⚠️ **NOT USED FOR PROJECT-TYPE CLUSTERING**

**What it is**: 
- Pivoted version of CSI_data_combined.csv
- 1 row = 1 bidder per project (exploded from 15 bidder columns)
- Example: Project A with 8 bids = 8 rows (one per bidder)

**When to use**:
- Competitor analysis (which companies bid on which projects)
- Bidder frequency analysis
- Market concentration studies
- Historical bids for a specific competitor

**Why NOT for clustering**:
- Project-type clustering needs 1 row = 1 project (not 1 row per bidder)
- Material quantities are duplicated across rows (not a meaningful unit of analysis)
- Use CSI_data_combined.csv instead

---

### cleaning_review/ - Data QA Reference Files

These are outputs from the data cleaning process. They document decisions made during data preparation.

| File | Purpose | Rows | Action |
|------|---------|------|--------|
| `bidder_full_company_list.csv` | All unique company names found | 922 | Reference only |
| `bidder_potential_duplicates.csv` | Companies flagged as possible duplicates | 19 | Client-approved merges applied |
| `bidder_standardization_review.csv` | Ampersand standardization examples | ~376 | Documentation |
| `duplicate_project_review.csv` | Projects flagged for duplicate review | 17 | Manual analyst review needed |

**Status**: Archive/Reference. Cleaning decisions have been applied to CSI_data_combined.csv.

---

## 📊 Data Lineage

```
CSI_data_2024.csv (695 rows)
    ↓
    └─── MERGE ───────────┐
                          ├─→ CSI_data_combined.csv (1,661 rows) ✅ PRIMARY
    ┌─── MERGE ───────────┤
    ↓                     │
CSI_data_2025.csv (966 rows)
    ↓
    └─→ CLEANING:
        • Reformat DATE/TIME
        • Parse LOCATION
        • Extract project IDs
        • Standardize bidders
        • Add quality flags
    ↓
    └─→ CSI_data_long_format.csv (6,894 rows) ⚠️ Alternative format only
        (Pivoted: 1 row per bidder per project)
```

---

## 🗂️ When to Use Which File

| Use Case | File | Location |
|----------|------|----------|
| **Cluster projects by type** | CSI_data_combined.csv | `processed/` |
| **Analyze competitor bidding** | CSI_data_long_format.csv | `processed/` |
| **Check data quality** | Cleaning review CSVs | `cleaning_review/` |
| **Verify original source** | 2024/2025 CSVs | `raw/` |
| **Git history** | All (kept in VCS) | Any |

---

## 📝 Notes

- **No data modification**: All CSV files in this folder are read-only after creation
- **Backup in git**: Raw files are preserved in git history even if archived
- **Size**: ~13 MB total (mostly the two raw CSV files)
- **Encoding**: UTF-8
- **Delimiter**: Comma (`,`)

---

## ✅ Data Quality Flags

CSI_data_combined.csv includes a `location_flag` column for data quality assessment:

| Flag | Meaning | Count | Action |
|------|---------|-------|--------|
| `ok` | Coordinates within 75 miles of county centroid | 1,552 | Use normally |
| `review` | Coordinates suspect (100+ miles off) | 8 | Manual check |
| `multi_county` | Project spans multiple counties | 94 | Ambiguous |
| `no_centroid` | County too rare for centroid calc | 7 | Manual check |

Filtering: `df[df['location_flag'] == 'ok']` for strict location validation.

---

For detailed data cleaning decisions, see `../../docs/CHANGELOG.md`.
