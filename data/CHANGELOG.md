# CSI Data Change Log

All changes made to the raw source data are recorded here for client transparency.

---

## CSI_data_combined.csv

**Created:** 2026-06-06  
**Source files:** `CSI_data_2024.csv`, `CSI_data_2025.csv`  
**Output file:** `CSI_data_combined.csv`

### Changes Applied

1. **Combined two annual files into one**
   - `CSI_data_2024.csv` (695 rows) and `CSI_data_2025.csv` (966 rows) were concatenated vertically using `pd.concat`.
   - No rows were dropped or modified during the merge.
   - Total rows: 1,661.

2. **Added `bid_year` column**
   - Values: `2024` or `2025`, derived from the source file name (not the date field in the sheet).
   - Purpose: Explicitly labels which bidding year each row belongs to, for analysis and filtering.

3. **Removed `source` column**
   - A redundant `source` column (duplicate of `bid_year`) was dropped from the final file.

### No Data Cleaned or Modified
- All original columns and values are preserved as-is from the source files.
- No rows were removed, no values were altered, no types were converted.
- Cleaning is to be performed separately by the analyst.

---

---

## Cleaning Pass 1 — 2026-06-06 (Quinten)

### Changes Applied

1. **Reformatted `DATE` column**
   - Converted from mixed string format (e.g. `2/18/2025`) to ISO standard `YYYY-MM-DD` (e.g. `2025-02-18`).
   - 0 nulls before and after conversion.

2. **Reformatted `TIME` column**
   - Converted from 12-hour AM/PM strings to 24-hour `HH:MM` format (e.g. `10:00 AM` → `10:00`, `2:00 PM` → `14:00`).
   - 72 values had extra timezone labels (`MDT`, `MST`, `MT`, `MTD`) and/or extra seconds (`10:00:00 AM`) — all stripped and parsed correctly.
   - Some values had parenthetical timezone labels (e.g. `10:20:00 AM (MT)`) — parentheticals stripped before parsing.
   - 1 value (`2:00 MT`) had no AM/PM indicator — interpreted as `14:00` based on context (hour ≤ 8 → PM).
   - 0 nulls after conversion.

---

4. **Parsed `LOCATION` into `County`, `City`, and `State` columns**
   - `County`: Extracted county name(s). Multi-county rows (e.g. "BROOKINGS, HAMLIN, KINGSBURY CO SD") stored as comma-separated list.
   - `City`: Extracted from "CITY OF X", "- CITY", or trailing comma/dash segments. Null when no city was specified (1,245 rows — expected, most LOCATIONs are county-level only).
   - `State`: Converted 2-letter abbreviation to full name (e.g. `MN` → `Minnesota`). Two extraction strategies are used in priority order:
     1. State abbreviation at end of string (e.g. `STEARNS CO MN` → `Minnesota`)
     2. State abbreviation embedded after city (e.g. `STEARNS CO MN, MELROSE` → city extracted first, then `MN` found in remaining text)
   - 3 rows were missing state abbreviations entirely and were resolved by geographic keyword matching (Kenmare → North Dakota, Collegeville → Minnesota, Alexander → North Dakota).
   - Parenthetical notes (e.g. `(MOVED FROM 08/03/23)`) stripped before parsing.
   - 0 nulls in County and State after fix.

5. **Moved `bid_year` to the first column position**

---

6. **Added `location_flag` column**
   - Purpose: Flags rows where the `PROJECT LOCATION` coordinates may not match the stated county, to allow analysts to exclude suspect rows during modeling.
   - Method: Computed each county's centroid (median lat/lon of all projects in that county) then measured the distance in miles from each project's coordinates to its county centroid. Rows > 75 miles from centroid are flagged — the 99th percentile of all distances is only 44 miles, so 75 miles is a conservative but defensible threshold.
   - Flag values:
     - `ok` — coordinates within 75 miles of county centroid (1,541 rows)
     - `review` — coordinates more than 75 miles from county centroid (88 rows)
     - `multi_county` — row spans multiple counties; single centroid verification not possible (32 rows)
   - The higher `review` count relative to earlier estimates reflects improved location parsing: better city/state extraction reduces false `multi_county` rows, so more rows are verified against county centroids and more coordinate anomalies are detected.
   - `review` rows cluster around counties with systematically mismatched coordinates. Key groups (sorted by maximum distance):
     - **POLK CO MN** (6 rows, ~433–468 mi off) — coordinates appear to be in North Dakota range
     - **MARSHALL CO IA** (1 row, ~465 mi off) — coordinates appear completely wrong
     - **PENNINGTON CO MN** (1 row, ~423 mi off) — coordinates appear completely wrong
     - **RENVILLE CO ND** (4 rows, ~410–422 mi off) — coordinates appear completely wrong
     - **CASS CO IA** (3 rows, ~395–403 mi off) — coordinates appear completely wrong
     - **RICHLAND CO MT** (3 rows, ~196–388 mi off) — coordinates appear completely wrong
     - **DUNN CO ND row 242** (~369 mi off) — coordinates appear completely wrong
     - **TODD CO SD** (2 rows, ~350–354 mi off) — coordinates appear completely wrong
     - **JACKSON CO SD** (2 rows, ~323–327 mi off) — coordinates appear completely wrong
     - **DOUGLAS CO NE** (1 row, ~322 mi off) — coordinates appear completely wrong
     - **STEELE CO ND** (3 rows, ~302–321 mi off) — coordinates appear completely wrong
     - **SIOUX CO ND** (3 rows, ~289–299 mi off) — coordinates appear completely wrong
     - **CLAY CO SD, VERMILLION** (1 row, ~284 mi off) — coordinates appear completely wrong
     - **HAND CO SD, MILLER** (1 row, ~276 mi off) — coordinates appear completely wrong
     - **CLAY CO IA** (3 rows, ~271–277 mi off) — coordinates appear completely wrong
     - **STANLEY CO ND** (1 row, ~261 mi off) — coordinates appear completely wrong
     - **GRANT CO ND** (1 row, ~255 mi off) — coordinates appear completely wrong
     - **CUSTER CO NE** (6 rows, ~211–257 mi off) — coordinates appear completely wrong
     - **CUSTER CO MT** (2 rows, ~228–241 mi off) — coordinates appear completely wrong
     - **DOUGLAS CO SD** (1 row, ~229 mi off) — coordinates appear completely wrong
     - **BUTLER CO NE** (1 row, ~229 mi off) — coordinates appear completely wrong
     - **BROWN CO SD** (8 rows, ~185–218 mi off) — coordinates appear completely wrong
     - **HUGHES CO SD - YANKTON** (1 row, ~176 mi off) — Yankton is in Yankton County, not Hughes County; label likely wrong
     - **WRIGHT CO IA** (2 rows, ~166–174 mi off) — coordinates appear completely wrong
     - **MARSHALL CO SD** (4 rows, ~159–170 mi off) — coordinates appear completely wrong
     - **DUNN CO ND row 7** (~155 mi off) — coordinates appear completely wrong
     - **CASS CO MN** (12 rows, ~103–139 mi off) — coordinates in North Dakota range; state label likely wrong (should be ND)
     - **SHERIDAN CO ND / SHERIDAN CO MT** (2 rows, ~101 mi off each) — coordinates appear completely wrong
     - **LINCOLN CO MN** (3 rows, ~80–99 mi off) — coordinates appear completely wrong
     - **MADISON CO IA / MADISON CO NE** (2 rows, ~94 mi off each) — coordinates appear completely wrong
     - **LYON CO IA** (4 rows, ~78–88 mi off) — coordinates appear completely wrong

---

7. **Split `PROJECT LOCATION` into `Latitude` and `Longitude` columns**
   - `Latitude` and `Longitude` extracted as separate float columns from the combined "lat, lon" string in `PROJECT LOCATION`.
   - 0 nulls in both columns.

---

8. **Extracted `csi_job_id` and `state_project_id` from `PROJECT` column**
   - `csi_job_id`: CSI's internal 5-digit job number, extracted from `JOB XXXXX` pattern. Found in 95 rows.
   - `state_project_id`: Primary state/federal project identifier extracted in priority order: SAP → CONTRACT ID → SP → IM → NH → BRJ → BW → ER → ARP → PCN. Found in 477 rows.
   - 31 rows have both identifiers (CSI job number and a state project ID in the same project name).
   - 1,120 rows have no identifier in either column — these are typically city/municipal or local projects not assigned a state/federal project number. For these rows, the composite key `DATE + LOCATION + PROJECT` should be used for identification.

---

9. **Converted `PREVAILING WAGES` from YES/NO to 1/0**
   - `YES` → `1` (1,041 rows), `NO` → `0` (620 rows). 0 nulls.

---

10. **Converted material quantity columns from string to float**
    - Columns: `MIX TN`, `GRADE CY`, `BASE TN`, `SHLDR TN`, `MILL SY`, `CRUSH TN`, `STOCK TN`
    - Removed comma formatting (e.g. `"2,425"` → `2425.0`) and cast to float64. Null counts unchanged.

---

11. **Converted `BOX` column from X/null to 1/0**
    - `X` → `1` (173 rows), null → `0` (1,488 rows).

---

## Cleaning Pass 2 — 2026-06-07 (Wenyu)

### Changes Applied

1. **Expanded project ID extraction with typed identifier fields**
   - Replaced the earlier two-field-only extraction logic with a typed extractor that preserves both normalized and raw ID values.
   - Existing compatibility fields are still present:
     - `csi_job_id`
     - `state_project_id` (now an alias of `state_federal_project_id`)
   - New ID fields added:
     - `state_federal_project_id`
     - `contract_id`
     - `local_project_id`
     - `project_id_type`
     - `project_id_raw`
     - `primary_project_id`
     - `secondary_project_ids`
   - Extraction priority is: `CSI_JOB` → `STATE_FEDERAL` → `CONTRACT_ID` → `PCN` → `COUNTY_PROJECT` → `AIP` → `IOWA_CALL` → `LOCAL_OWNER_CODE`.

2. **Added regex coverage for previously missed ID formats**
   - Added support for CSI job IDs with optional hash marks, e.g. `JOB #23347`.
   - Added abbreviated contract IDs, e.g. `CONT ID #240081` and `CONT NO 05R24`.
   - Added spaced and variant state/federal IDs, e.g. `SP 4310- 95`, `SAP'S 047-602-014`, `BRO-B 8006(56)`, `BRF 6293(12)`, `NH-TA0037(157)`, `IM-EM 0908(97)362`, and `PH 0044(238)172`.
   - Added PCN IDs, e.g. `PCN 08N8` and `PCN X06L`.
   - Added county/local/airport formats, e.g. `CP-13(24)01`, `CP #23-16DEF`, `CP 25:71`, `AIP 3-38-0021-0018-2024`, and `AIG NO. 3-38-0068-023 & 24-2024`.
   - Added Iowa letting formats, e.g. `CALL 155 60-C060-130` and `CALL 105 DPS-S12A(107)`.
   - Added local owner/project-code formats, e.g. `PROJ 2024-10827`, `BMI NO 0W1.131187`, `ST23-279`, `BR-24-A1`, and `SW-311`.

3. **Improved missing-ID coverage**
   - Previous output had 1,120 rows with both `csi_job_id` and `state_project_id` missing.
   - After validation refinements, 771 of those 1,120 rows now have a machine-extracted `primary_project_id`.
   - 349 rows remain without a machine-extracted project ID and should use composite-key logic or targeted review.
   - Across all 1,661 rows, 1,312 rows now have `primary_project_id`; 349 rows remain without any extracted ID.
   - ID type counts by primary ID:
     - `STATE_FEDERAL`: 670
     - `LOCAL_OWNER_CODE`: 278
     - `CSI_JOB`: 151
     - `COUNTY_PROJECT`: 89
     - `IOWA_CALL`: 71
     - `PCN`: 35
     - `AIP`: 16
     - `CONTRACT_ID`: 2

4. **Added composite keys for local/municipal projects**
   - Added `strict_key`: `DATE + State + County + City + normalized PROJECT`.
   - Added `project_group_key`: `State + County + City + normalized PROJECT`.
   - Purpose:
     - `strict_key` identifies a specific bid event.
     - `project_group_key` groups likely same-project records across date changes, rebids, or year carryover.

5. **Added duplicate candidate review output**
   - Added `duplicate_candidate`, `duplicate_match_key`, and `duplicate_match_reason` fields.
   - Generated `duplicate_project_review.csv` for rows that should be manually reviewed as possible duplicates, rebids, phases, add-ons, or reused local IDs.
   - Current review table contains 24 rows.
   - The `decision` column is intentionally blank for analyst review.

6. **Removed unnecessary `geopy` dependency**
   - Replaced `geopy.distance.geodesic` with an internal haversine distance function.
   - The `location_flag` method still uses the same 75-mile county-centroid threshold.

### Data Integrity Notes

- No source rows were dropped.
- Raw source files `CSI_data_2024.csv` and `CSI_data_2025.csv` were not modified.
- `project_id_raw` preserves the matched original text for auditability.
- Regex type counts can overlap through `secondary_project_ids`; do not sum type counts to infer unique recovered rows.
- The official recovery metric for this pass is: 771 of the prior 1,120 missing-ID rows now have `primary_project_id`.

---

## Validation Pass — 2026-06-07

### Stratified ID Extraction QA

- Created `qa_project_id_validation_sample.csv` from the 771 rows that were previously missing both `csi_job_id` and `state_project_id` but now have `primary_project_id`.
- Stratified sample size: 117 rows.
- Sample mix:
  - `LOCAL_OWNER_CODE`: 40 rows
  - `STATE_FEDERAL`: 20 rows
  - `CSI_JOB`: 12 rows
  - `COUNTY_PROJECT`: 12 rows
  - `IOWA_CALL`: 12 rows
  - `PCN`: 10 rows
  - `AIP`: 10 rows
  - `CONTRACT_ID`: 1 row
- QA focus:
  - Checked whether road numbers such as `US-183`, `TH87`, and `TH94` were being incorrectly captured as local project IDs.
  - Checked whether parentheses were preserved in IDs such as `CP-2800(023)` and `CALL 600 DPS-183-3(125)`.
  - Checked whether leading zeros and letters were preserved in `PCN`, `AIP`, `SP`, and `CALL` identifiers.
  - Checked whether `project_id_raw` points back to the original matched text.
  - Checked whether `secondary_project_ids` captured lower-priority IDs without overriding the primary ID.

### Validation Findings

- 114 of 117 sampled rows passed the automated/visual QA checks.
- 3 sampled rows were flagged for manual review, all in `LOCAL_OWNER_CODE`:
  - `#157`
  - `#23141`
  - `#22288`
- These are not confirmed false positives; they are weak numeric/hash identifiers that may be owner/bid numbers rather than stable project IDs.

### Fixes Applied From QA

- Preserved missing closing parentheses in extracted IDs, e.g. `CP-2800(023)` and `CALL 600 DPS-183-3(125)`.
- Tightened ID normalization so description words such as `COLD`, `BOX`, and `PIPE` do not remain in `primary_project_id`.
- Excluded common road-number forms from `LOCAL_OWNER_CODE`, including `US-183`, `TH87`, and `TH94`.

---

## Cleaning Pass 3 — 2026-06-07 (Quinten)

### Changes Applied

1. **Standardized BIDDER_*_NAME columns**
   - Normalized ampersand spacing: `" AND "`, `"&"`, `" &"`, `"& "` all converted to `" & "` (376 company names with ampersands standardized).
   - Trimmed extra internal spaces (consolidated multiple spaces to single spaces).
   - Converted null/empty/`"NAN"` values to `None` for consistency in aggregation and groupby operations.
   - All names remain uppercase (already standardized from source data).
   - 0 rows removed; standardization applied across all 15 BIDDER_*_NAME columns.

2. **Converted BIDDER_*_TOTAL to float64**
   - Removed comma formatting (e.g., `"1,273,463.90"` → `1273463.9`).
   - Removed leading `$` signs from 2025 source data (e.g., `"$1,566,633.52 "` → `1566633.52`). The 2025 raw file uses `$` prefix with trailing spaces; the 2024 file does not — both formats are handled.
   - Multi-component cells (e.g., `"$543,789.55 $ 160,972.51 $8,634.80 $713,396.86"`) resolved by: taking the last amount when it equals the sum of the preceding amounts (grand total pattern); otherwise taking the first amount (primary/base bid). 18 cells across 4 projects had this format.
   - Parsed as float64 for numerical operations (competitor bid analysis, cost aggregations).
   - Null/empty/`"NAN"` values converted to `NaN` (standard pandas null representation for float columns).
   - Applied across all 15 BIDDER_*_TOTAL columns.
   - 4 source-level mismatches remain (name present, total null) — all are legitimate source data anomalies:
     - HOULE EXCAVATING NOT OPENED NO LAST PAGE ENGINEERS EST (bid not opened, annotation in name field)
     - ENGINEER'S ESTIMATE $42454020 (Sherburne CO MN — estimate amount embedded in name field)
     - MICHELS ROAD & STONE (Davison CO SD — total genuinely missing from source)
     - PICARD EXCAVATING (Stark CO ND — total field contains `"addendum not acknowledged"`, not a number)
   - This enables future pivot to long format (one row per bidder per project) for competitor scoring engine.

### Data Integrity Notes

- No source rows were dropped.
- All original bidder names and bid amounts are preserved; only formatting and type conversions applied.
- Null handling now consistent: `None` for name columns (object type), `NaN` for total columns (float type).
- Ready for pivot to long format in a future pass.

---

## Cleaning Pass 3b — 2026-06-07 (Quinten)

### Changes Applied

1. **Pivoted to long format (one row per bidder per project)**
   - Converted wide format (one row per project, 15 bidder columns) to long format (one row per bidder per project).
   - Input: `CSI_data_combined.csv` (1,661 rows, 67 columns).
   - Output: `CSI_data_long_format.csv` (7,626 rows, 40 columns).
   - Each row contains: all project metadata + BIDDER_NAME + BID_AMOUNT + bidder_sequence (position 1-15).
   - Null bidders are skipped (no padding with empty rows).
   - Sorted by DATE, LOCATION, PROJECT, bidder_sequence for logical grouping.

### Purpose
- Enables competitor scoring engine: group by company, calculate frequency, distance, capacity.
- Simplifies aggregation: one row per bid vs. 15 columns per project.
- Preserves auditability: bidder_sequence tracks original bid ranking.

### Data Integrity Notes
- No rows dropped; 7,626 = sum of non-null bidders across 1,661 projects.
- All project-level metadata duplicated for each bidder in that project (intentional for analysis).
- Wide format file (CSI_data_combined.csv) is preserved; both formats coexist.

---

## Cleaning Pass 3c — 2026-06-07 (Quinten)

### Changes Applied

1. **Applied client-approved bidder name merges**
   - Mapping file: 38 raw name variations → 19 standardized company names.
   - Applied mapping to all BIDDER_*_NAME columns in wide format (1,152 replacements across 15 columns).
   - Example: "RJ ZAVORAL & SONS INC" + "R J ZAVORAL & SONS INC" → "RJ ZAVORAL & SONS"

2. **Deleted non-competitor entries (ENGINEERS ESTIMATE)**
   - Removed all entries matching "ENGINEER*" pattern from long format (engineering estimates, not actual competitors).
   - Deleted: 732 rows (includes "ENGINEERS ESTIMATE", "ENGINEER'S ESTIMATE", "ENG ESTIMATE", etc.)
   - Rationale: These are cost estimates, not competitor bids.

3. **Updated long format output**
   - Input: CSI_data_long_format.csv (7,626 rows, 40 columns)
   - Output: CSI_data_long_format.csv (6,894 rows, 40 columns)
   - Removed: Non-competitors (732 rows)

### Data Integrity Notes
- BIDDER_*_NAME columns in wide format are now standardized with the v1 merge mapping.
- No rows lost from wide format; only ENGINEERS ESTIMATE entries removed from long format.

---

*Future changes should be appended below this line with date, description, and analyst name.*

## Cleaning Pass 4 — 2026-06-08 (Quinten)

### Changes Applied

1. **Standardized bidder names based on client review**
   - Source: `bidder_standardization_v2.csv` (client-approved decision log)
   - Created standardization mapping from 134 variations → 58 canonical names
   - Applied mapping to all BIDDER_*_NAME columns (15 columns across 134 variation rows)
   - Total bidder records affected: 853 replacements (net of Pass 3c mappings already applied)

2. **Deleted non-competitor entries**
   - Deleted 3 company variations matching non-competitor patterns
   - Pattern: Companies marked as "ENGINEERS ESTIMATE" and similar (total 1089 bids removed from analysis)
   - These are engineering cost estimates, not actual competitor bids, so are excluded from competitor analysis

### Standardization Details

- **Companies merged**: 58
- **Variations consolidated**: 134
- **Examples**:
  - A & C EXCAVATING: A & C EXCAVATING, A & C EXCAVATING LLC
  - ASTECH: ASTECH, ASTECH CORP
  - B & B CONTRACTING: B & B CONTRACTING, B & B CONTRACTING INC
  - BLACKTOP SERVICE CO & SUBSIDIARY: BLACKTOP SERVICE CO & SUBSIDARY, BLACKTOP SERVICE CO & SUBSIDIARY, BLACKTOP SERVICES CO & SUBSIDIARY
  - BLUESTONE CONSTRUCTION: BLUE STONE CONSTRUCTION, BLUESTONE CONSTRUCTION INC
  - BREITBACH CONSTRUCTION: BREITBACH CONSTRUCTION CO, BREITHBACH CONSTRUCTION
  - BROUWER CONSTRUCTION: BROUWER CONSTRUCTION, BROUWER CONSTRUCTION LLC
  - C & L EXCAVATING: C & L EXCAVATING, C & L EXCAVATING INC
  - CENTRAL SPECIALTIES: CENTRAL SPECIALTIES INCORPORATED, CENTRAL SPECIALTIES LLC
  - CIVIL SPECIALTIES: CIVIL SPECIALITIES INC, CIVIL SPECIALTIES, CIVIL SPECIALTIES INC
  - ... and 48 more company groups

### Data Integrity Notes

- No source rows were dropped from the wide-format file.
- Bidder names in BIDDER_*_NAME columns are now standardized and ready for competitor analysis.
- The standardization is one-way (variation → core_name); raw names can be recovered from git history if needed.
- Ready for: Competitor scoring engine, bid aggregation by company, market analysis.


## Long Format Regeneration — 2026-06-08

### Purpose
Updated `CSI_data_long_format.csv` to reflect standardized bidder names from Cleaning Pass 4.

### Changes Applied

1. **Re-pivoted from updated wide format**
   - Source: `CSI_data_combined.csv` (with Cleaning Pass 4 standardized names)
   - Output: `CSI_data_long_format.csv` (6894 rows)
   - One row per bidder per project (from 1,661 projects with up to 15 bidders each)

2. **Removed non-competitor entries**
   - Deleted 732 ENGINEERS ESTIMATE entries (same pattern as prior pass)

3. **Results**
   - Total bidder records: 6894
   - Ready for: Competitor scoring engine (similarity, distance, capacity analysis)

### Data Integrity Notes
- All standardized company names from Cleaning Pass 4 are now reflected in long format.
- Original wide format preserved for auditability.
- Bidder sequence (1-15) preserved to track bid ranking within each project.
- No rows lost; consolidation only.


## Cleaning Pass 5 — 2026-06-08 (Quinten)

### Changes Applied

1. **Applied additional client-approved bidder name merges**
   - Source: `bidder_standardization_v3.csv` (client-reviewed and approved list)
   - Created standardization mapping from 14 variations → 14 canonical names
   - Applied mapping to all BIDDER_*_NAME columns in wide format (65 replacements)
   - Total impact: Corrected 14 naming inconsistencies across multiple projects

2. **Merged company name variations**
   - Categories of merges:
     - Spelling errors: 4 merges (CENTRAL SPECIALITES, DUINICK, SEVLIN, etc.)
     - Data artifacts: 1 merge (removed "600%" suffix from MARTIN CONSTRUCTION)
     - Spacing issues: 1 merge (NORTHSTAR vs NORTH STAR)
     - Abbreviation inconsistencies: 2 merges (MINNESOTA vs MN, DBA missing)
     - Suffix variations: 5 merges (COMPANY vs CO INC, -ING vs -TION, etc.)
     - Ampersand formatting: 1 merge (& vs space only)

### Detailed Merges Applied

  - **CENTRAL SPECIALTIES** ← CENTRAL SPECIALITES
    (Spelling error (SPECIALITES vs SPECIALTIES))
  - **MARTIN CONSTRUCTION INC** ← MARTIN CONSTRUCTION INC 600%
    (Data entry artifact - 600% appears to be pricing note)
  - **DUININCK INC** ← DUINICK INC
    (Missing letter N in name)
  - **SELLIN BROTHERS INC** ← SEVLIN BROTHERS INC
    (Spelling error (SELLIN vs SEVLIN))
  - **NORTHSTAR MATERIALS INC DBA KNIFE RIVER MATERIALS** ← NORTH STAR MATERIALS DBA KNIFE RIVER MATERIALS
    (Spacing difference (NORTHSTAR vs NORTH STAR))
  - **DAKOTA UNDERGROUND COMPANY** ← DAKOTA UNDERGROUND CO INC
    (Different legal entity suffixes (COMPANY vs CO INC))
  - **NORTHDALE CONSTRUCTION COMPANY INC** ← NORTHDALE CONSTRUCTION CO INC
    (Abbreviation difference (COMPANY INC vs CO INC))
  - **OMG MIDWEST DBA MINNESOTA PAVING** ← OMG MIDWEST MINNESOTA PAVING
    (Missing DBA text in one variation)
  - **KNIFE RIVER MATERIALS-NORTHERN MINNESOTA** ← KNIFE RIVER MATERIALS-NORTHERN MN
    (State abbreviation (MINNESOTA vs MN))
  - **MARK LEE EXCAVATING** ← MARK LEE EXCAVATION
    (Gerund vs noun form (-ING vs -TION))
  - **HOFFMAN CONSTRUCTION COMPANY** ← HOFFMAN CONSTRUCTION CO LLC
    (Different legal entity types)
  - **FIRST RATE EXCAVATE INC** ← FIRST RATE EXCAVATING INC
    (Gerund difference (-ATE vs -ATING))
  - **J & J EARTHWORKS** ← J J EARTHWORKS
    (Ampersand formatting (& vs space))
  - **MENNING EXCAVATING INC** ← MENNING EXCAVATION INC
    (Gerund vs noun form (-ING vs -TION))

### Results

- **Total bidder records**: 6,894 (after removing 732 ENGINEERS ESTIMATE entries)
- **Unique competitors**: 819
- **Total name replacements across all passes**: 2,070 (Pass 3c: 1,152 + Pass 4: 853 + Pass 5: 65)
- **Impact**: 14 company groups consolidated, improving data consistency
- **Ready for**: Final competitor analysis and scoring engine

### Data Integrity Notes

- No source rows were dropped from wide-format file.
- Bidder names now standardized across all variations (spellings, spacing, suffixes, abbreviations).
- Raw names can be recovered from git history if needed.
- All data files updated consistently: wide format, long format, and company list.

---

## MN Pit List — Initial Cleaning — 2026-06-16 (Quinten)

**Source file:** `data/raw/MN Pit List.xlsx`
**Output file:** `data/processed/MN_pit_list_cleaned.csv`

### Pass 1: Structural cleanup + State + County Verification

**Script:** `data/clean_mn_pit_list_pass1.py`

1. **Dropped embedded rating legend columns**
   - Columns `Unnamed: 6`, `Unnamed: 7`, `Unnamed: 8`, `Unnamed: 9` were a lookup table embedded in the Excel sheet (rating scale descriptions), not row-level data.
   - Dropped from output.

2. **Renamed columns for consistency**
   - `County ` (trailing space) → `County`
   - `Rating  1-10` (double space) → `Rating`

3. **Added `State` column**
   - All 2,398 rows set to `"MN"` (Minnesota).
   - Source: file scope — this file covers Minnesota pits only.

4. **Verified `County` against coordinates via spatial join**
   - Method: Downloaded 2022 Census TIGER MN county shapefile; performed `geopandas` point-in-polygon spatial join on `Latitude`/`Longitude`.
   - Added `county_from_coords`: county name derived from coordinates.
   - Added `county_match`: boolean, True when stated County matches spatial result (case/space normalized).
   - Results:
     - **2,213 rows matched** (92.3%)
     - **3 rows outside MN shapefile** — coordinates fall just across the Wisconsin border (Dresser Quarry, Kraemer-Hudson Quarry, Sodenbeck pit); all listed under Chisago/Pine counties.
     - **182 rows mismatched** — categorized below.

   **Mismatch categories (182 rows):**
   | Category | Example | Count | Action |
   |---|---|---|---|
   | Spelling error in County field | "Marschall" → Marshall (37), "Le Suer" → Le Sueur (35), "Mclead" → McLeod (3), "Washinton" → Washington (4), "Fairbault" → Faribault (2) | 81 | Corrected in Pass 2 |
   | Adjacent county boundary (GPS imprecision or borderline pit) | Roseau ↔ Lake of the Woods (23), Sibley ↔ McLeod/Scott/Carver (13), Crow Wing ↔ Cass (8) | 98 | County updated to match coordinates in Pass 2 |
   | Non-adjacent mismatch (suspicious) | Chisago → Dakota, Wilkin → Yellow Medicine, Clearwater → Otter Tail | 4 | Flagged `county_flag = "review"` |
   | Outside MN shapefile | Dresser Quarry, Kraemer-Hudson Quarry, Sodenbeck pit | 3 | Flagged `county_flag = "outside_mn"` |

### Data Integrity Notes
- Source file `MN Pit List.xlsx` was not modified.
- `county_match = False` does not mean the county is wrong — it includes spelling errors, boundary effects, and genuine errors.

---

### Pass 2: County Corrections Applied — 2026-06-16 (Hsin)

**Script:** `data/clean_mn_pit_list_pass2.py`

1. **Fixed 81 spelling errors in County field**
   - Mapping applied: Marschall → Marshall, Le Suer → Le Sueur, Mclead → McLeod, Washinton → Washington, Fairbault → Faribault.
   - Decision basis: these county names do not exist in Minnesota; spatial join confirmed the corrected spelling.

2. **Updated 98 adjacent-boundary County values to match coordinates**
   - For pits where stated county and coordinate county were neighboring counties, `County` was replaced with `county_from_coords`.
   - Rationale: coordinates are the objective measurement; for distance calculations in the competitor model, geographic accuracy takes precedence over handwritten county labels.

3. **Added `county_flag` column**
   - `ok` (2,391 rows): County verified or corrected to match coordinates.
   - `review` (4 rows): Non-adjacent mismatch — either county or coordinates may be wrong; requires manual verification. Rows: Agg. Industries (Chisago→Dakota), Barton S&G (Chisago→Dakota), Scott Boehne (Wilkin→Yellow Medicine), Westby Farms (Clearwater→Otter Tail).
   - `outside_mn` (3 rows): Coordinates fall just across the Wisconsin border; pits kept in dataset as they may be accessible to MN contractors.

### Data Integrity Notes
- `county_from_coords` column retained as audit trail showing the spatial-join result.
- 4 `review` rows should be manually verified against a map before use in modeling.

---

### Pass 3: Access Field Standardization — 2026-06-16 (Hsin)

**Script:** `data/clean_mn_pit_list_pass3.py`
**Lookup:** `data/cleaning_review/access_standardization.csv`

1. **Added `access_type` column** — categorical encoding of who can access each pit:
   - `open` (433): Access = "Everyone" — all competitors may use this pit.
   - `unknown` (1,524): Access is blank — treated as open for model purposes (excluding 63% of pits would gut the distance feature).
   - `client` (83): Access = "CSI" or variant — client's own pits. Excluded from competitor distance calculation; available as input to future CSI bid-decision model.
   - `competitor` (258): Access = a named competitor — only that company may use this pit.
   - `knife_river_pending` (95): Access = "Knife River" — disambiguation pending between "KNIFE RIVER CORPORATION D/B/A KNIFE RIVER MIDWEST" and "NORTHSTAR MATERIALS INC DBA KNIFE RIVER MATERIALS". Kept separate until resolved.
   - `closed` (5): Access = "Closed up / old pit" or variant — excluded from model.

2. **Added `access_company` column** — canonical bidder name for `competitor`-type pits.
   - Method: fuzzy matched all 41 unique competitor Access names against 819 canonical bidder names using `token_sort_ratio`, then confirmed matches using Claude Code analysis.
   - 22 names mapped to canonical bidder names; 19 marked `NOT_IN_BIDDER_LIST` (private pit owners who do not appear as bidders in the CSI dataset).
   - Lookup table saved to: `data/cleaning_review/access_standardization.csv`.
   - Key mappings: Duinicks → DUININCK INC, Anderson Bros. → ANDERSON BROTHERS COMPANY, Mathowitz → THE MATHIOWETZ CONSTRUCTION COMPANY, Ferguson → FERGUSON BROTHERS EXCAVATING (most active Ferguson entity, 28 bids), Northern Imp. → NORTHERN IMPROVEMENT COMPANY - FARGO.

3. **Did not split CSI pits into a separate file** — kept in main dataset with `access_type = "client"` so they are available as a feature for the future CSI bid-decision model without requiring a file merge.

### Data Integrity Notes
- Raw `Access` field preserved as-is for audit trail.
- Knife River pits (95 rows, `access_type = "knife_river_pending"`) require disambiguation before use in modeling.
- `NOT_IN_BIDDER_LIST` competitors (87 pits) own pits but do not appear as bidders in CSI's historical data — they will not match any competitor in the scoring model.
- Name disambiguation for multi-entity companies (Ferguson: 4 entities, Northern Improvement: 2 locations) is a modeling decision; recommend treating all variants of the same family as one group during distance calculation.

---

## LOCATION State-Parsing Fix + Supabase `scratch` Push — 2026-07-28

### Bug fixed: `run_cleaning_pipeline.py` `_parse_location()`

- `STATE_ABBR` maps `"CO"` → `"Colorado"`. For `LOCATION` strings like `"MCKENZIE CO, CITY OF
  ALEXANDER"`, after city-extraction the remaining text `"MCKENZIE CO"` was matched by the
  trailing-2-letter state fallback as if `CO` were the Colorado state code, instead of what it
  actually abbreviates in this dataset's convention: **County**. This silently pre-empted the
  `MANUAL_OVERRIDES` dict (Kenmare/Collegeville/Alexander → ND/ND/MN), which existed specifically
  to handle these 3 rows but never actually ran.
- Fixed by excluding the literal token `"CO"` from both trailing-2-letter state-abbreviation
  checks in `_parse_location()`. This dataset's entire footprint is IA/MN/MT/NE/ND/SD (see
  `STATE_NAME_TO_ABBR` in `build_project_competitor_panel.py`), so `"Colorado"` should never be a
  legitimate value.
- Affected 3 of 1,661 rows (Ward Co ND, Stearns Co MN, McKenzie Co ND).

### `project_natural_key` added to `projects.csv` and `bidder_results.csv`

- `build_project_competitor_panel.py` now computes `project_natural_key` —
  `{state}_{county}_{bid_date:%Y_%m_%d}_{city_or_normalized_project_name}` — and writes it into
  both output CSVs. It reformats (not replaces) the already-unique `strict_key`/`_project_identity`
  composite key into a human-readable, state/county/date-led form for use as the primary key in
  the new Supabase tables (see below). The tiebreaker keeps both City and the normalized project
  name (not either/or) — same-day/same-county/same-city collisions exist (e.g. two separate
  Alexandria, MN street projects let the same day), so dropping either component reintroduces
  collisions.

### Pushed to Supabase `scratch` schema

- New `data/push_supabase_bid_data.py`: upserts `projects.csv` / `bidder_results.csv` into
  `scratch.bid_projects` / `scratch.bid_results`. The two tables are independently appendable
  (`--projects` / `--bidder-results` are each optional). See `docs/DATA_ACCESS_SCRATCH.md`.
- Fixed `data/update_name_registry.py`'s `REGISTRY_FILE` constant, which pointed at a nested
  `ci_model/competitor_prediction_model/...` path that doesn't exist anywhere in this repo (same
  class of stale path documented in `CLAUDE.md`'s rough edge #4 for the reporting orchestrator).
  Now matches `build_project_competitor_panel.py`'s correct default.
- Initial bulk load: 1,591 projects, 6,838 bid results. Verified idempotent (a repeat run reports
  0 inserts / all updates) and independently appendable (`--bidder-results` alone, without
  `--projects`, succeeds against projects already present in `scratch.bid_projects`).

---

## Competitor Name Registry Pushed to Supabase, With a Correction Pull-Back Path — 2026-07-28

### Pushed to Supabase `scratch` schema

- `data/push_supabase_bid_data.py` extended with a third independent, optional target:
  `--registry <path>` upserts the competitor name registry into
  `scratch.competitor_name_registry` (key: `raw_name_variant`), same upsert-based,
  independently-appendable pattern as `--projects`/`--bidder-results`.
- `raw_name_variant` had one exact-duplicate row ("Anderson Brothers" / pit_list, identical in
  every column) — deduped on push (`keep="first"`); the local CSV itself is untouched.
- Initial load: 891 rows (892 minus the 1 duplicate). Verified idempotent (repeat run: 0 inserted,
  891 updated).

### New: `data/pull_registry_corrections.py`

- Reads `scratch.competitor_name_registry` back from Supabase and overwrites
  `comp_name`/`source`/`top_competitors_tag`/`suggested_comp` on local rows wherever Supabase's
  value differs — this is how the client's corrections (filling in `comp_name` for needs-review
  rows, directly in Supabase) reach the local registry the pipeline actually reads.
- Deliberately narrow: never adds or removes rows. Row existence stays locally authoritative
  (`update_name_registry.py` is the only thing that creates new rows, by finding a real raw name
  in the bid data or pit list). A `raw_name_variant` present in Supabase but not locally is
  reported as a warning, not merged in.
- Verified against a real edit (`PCIROADS LLC` → `PCI ROADS`, `Top Competitors Tag` 0 → 1): the
  dry-run reported exactly that one row/two-column change; the real run applied it correctly and
  left the CSV's `"Top Competitors Tag"` header, row order, and all other rows untouched.
- Verification also re-ran `data/update_name_registry.py` against the corrected file to confirm no
  schema drift — this incidentally surfaced 6 name variants (encoding artifacts, a price-suffix
  duplicate) that the script had never processed because its `REGISTRY_FILE` path was broken until
  earlier in this same session. Unrelated to the registry-push work; pushed to Supabase in the same
  pass (`source_batch=sync_pit_list_names`). Registry is now 897 rows.

---

## MN Pit List Pushed to Supabase, With Duplicate Coordinates Flagged — 2026-07-29

### `clean_mn_pit_list.py` Pass 4: flag `(Latitude, Longitude)` duplicates

- New pass, `pass4_lat_lon_duplicates()`: `(Latitude, Longitude)` has no guaranteed uniqueness in
  the source data — 14 of 2,398 rows shared coordinates with an earlier row. Rather than silently
  dedupe, each later occurrence is flagged `duplicate_flag = 'duplicate_lat_lon'` and moved to the
  bottom of the file, for a human to resolve.
- 12 of the 14 flagged rows are exact full-row duplicates (harmless). 2 pairs ("Langaas pit",
  "Lois Cater") carry a genuinely different `Rating` at the same coordinates — a real conflict
  needing a decision, not noise. Applied directly to the existing
  `data/processed/MN_pit_list_cleaned.csv` (2,398 rows, unchanged count — flagged rows reordered,
  not removed); wired into `main()` for future full runs from raw.

### Pushed to Supabase `scratch` schema

- `data/push_supabase_bid_data.py` extended with a fourth independent, optional target:
  `--pit-list <path>` upserts the pit list into `scratch.mn_pit_list`
  (key: `(latitude, longitude)`), same pattern as the other three tables.
  `load_pit_list()` excludes any `duplicate_flag = 'duplicate_lat_lon'` row from the push
  entirely (reported, not kept-first) — a flagged row only reaches Supabase once the source file
  is fixed.
- Initial load: 2,384 rows (2,398 minus the 14 flagged). Verified idempotent (repeat run: 0
  inserted, 2,384 updated). Spot-checked both Rating-conflict pairs in the live table: exactly one
  row each, with the first-occurrence Rating preserved (5 and 4, not the flagged duplicate's 1).
- The name-registry detection loop already covered the pit list before this change —
  `update_name_registry.py` has scanned its `Access` column alongside bid data since it existed —
  so no new code was needed there, only the pit list's own rows needed a path to Supabase.

---

## MN Pit List: Dropped Audit-Only Columns — 2026-07-29

- `county_from_coords`, `county_match`, `county_flag`, `county_original` removed from
  `MN_pit_list_cleaned.csv` and `scratch.mn_pit_list`. Verified unused downstream first:
  `build_pit_features.py` (the only real consumer) derives its own `county_key` straight from the
  already-corrected `County` column, never touches these. They were Pass 1-2 QA/audit intermediates
  from the spatial-join county verification, not needed once `County` itself is corrected.
- `data/clean_mn_pit_list.py` still computes them internally — Pass 2's correction logic depends
  on them (e.g. `county_flag == "adjacent_boundary"` triggers overwriting `County` with
  `county_from_coords`) — `main()` just drops them from the saved file now (`_AUDIT_ONLY_COLUMNS`).
- Applied directly to the existing cleaned CSV (2,398 rows, unchanged) rather than a full
  from-raw re-run, same reasoning as Pass 4 last turn. `push_supabase_bid_data.py`'s
  `MN_PIT_LIST_DDL`/`PIT_LIST_COLUMNS` updated to match; live `scratch.mn_pit_list` columns
  dropped and re-pushed (2,384 rows, 0 inserted / all updated — same rows, smaller schema).
