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
   - 1 value (`2:00 MT`) had no AM/PM indicator — interpreted as `14:00 PM` based on context.
   - 0 nulls after conversion.

---

4. **Parsed `LOCATION` into `County`, `City`, and `State` columns**
   - `County`: Extracted county name(s). Multi-county rows (e.g. "BROOKINGS, HAMLIN, KINGSBURY CO SD") stored as comma-separated list.
   - `City`: Extracted from "CITY OF X", "- CITY", or trailing comma segments. Null when no city was specified (1,237 rows — expected, most LOCATIONs are county-level only).
   - `State`: Converted 2-letter abbreviation to full name (e.g. `MN` → `Minnesota`). 3 rows were missing state abbreviations in the raw LOCATION string and were manually resolved using geographic context (Kenmare → North Dakota, Collegeville → Minnesota, Alexander → North Dakota).
   - Parenthetical notes (e.g. `(MOVED FROM 08/03/23)`) stripped before parsing.
   - 0 nulls in County and State after fix.

5. **Moved `bid_year` to the first column position**

---

6. **Added `location_flag` column**
   - Purpose: Flags rows where the `PROJECT LOCATION` coordinates may not match the stated county, to allow analysts to exclude suspect rows during modeling.
   - Method: Computed each county's centroid (median lat/lon of all projects in that county) then measured the distance in miles from each project's coordinates to its county centroid. Rows > 75 miles from centroid are flagged — the 99th percentile of all distances is only 44 miles, so 75 miles is a conservative but defensible threshold.
   - Flag values:
     - `ok` — coordinates within 75 miles of county centroid (1,552 rows)
     - `review` — coordinates more than 75 miles from county centroid, or confirmed label error (8 rows)
     - `multi_county` — row spans multiple counties; single centroid verification not possible (94 rows)
     - `no_centroid` — county appeared too rarely to compute a reliable centroid (7 rows)
   - `review` rows detail:
     - RICHLAND CO MT (555 mi off) — coordinates appear completely wrong
     - HAND CO SD, MILLER (276 mi off) — coordinates appear completely wrong
     - BROWN CO SD, ABERDEEN (209 mi off) — coordinates appear completely wrong
     - HUGHES CO SD - YANKTON (176 mi off) — Yankton is in Yankton County, not Hughes County
     - DUNN CO ND row 242 (369 mi off) — coordinates appear completely wrong
     - DUNN CO ND row 7 (154 mi off) — coordinates appear completely wrong
     - CASS CO, WEST FARGO MN (113 mi off) — West Fargo is in ND, not MN; state label likely wrong
     - MORTON CO MN, CITY OF MANDAN — Mandan is in Morton County ND, not MN; state label likely wrong

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
   - Current review table contains 17 rows.
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
   - Parsed as float64 for numerical operations (competitor bid analysis, cost aggregations).
   - Null/empty/`"NAN"` values converted to `NaN` (standard pandas null representation for float columns).
   - Applied across all 15 BIDDER_*_TOTAL columns.
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
- BIDDER_NAME values are still raw (not yet standardized); standardization will be applied post-client-review via lookup table.
- Wide format file (CSI_data_combined.csv) is preserved; both formats coexist.

---

## Cleaning Pass 3c — 2026-06-07 (Quinten)

### Changes Applied

1. **Applied client-approved bidder name merges**
   - Generated merge mapping from 19 client-approved groups in bidder_potential_duplicates.csv.
   - Mapping file: 38 raw names → 19 standardized company names.
   - Applied mapping to create `standardized_company_name` column in long format.
   - Example: "RJ ZAVORAL & SONS INC" + "R J ZAVORAL & SONS INC" → "RJ ZAVORAL & SONS" (96 total bids)

2. **Deleted non-competitor entries (ENGINEERS ESTIMATE)**
   - Removed all entries matching "ENGINEER*" pattern (engineering estimates, not actual competitors).
   - Deleted: 732 rows (includes "ENGINEERS ESTIMATE", "ENGINEER'S ESTIMATE", "ENG ESTIMATE", etc.)
   - Rationale: These are cost estimates, not competitor bids.

3. **Updated long format output**
   - Input: CSI_data_long_format.csv (7,626 rows, 40 columns)
   - Output: CSI_data_long_format.csv (6,894 rows, 41 columns)
   - New column: `standardized_company_name` (ready for competitor analysis)
   - Removed: Non-competitors, merged: 19 company groups

### Results
- **Total bidder records**: 6,894 (from 7,626, -732 deleted, -0 lost to merges)
- **Unique competitors**: 880 (from 922, -42 merged into 19 groups)
- **Top competitor**: CENTRAL SPECIALTIES (497 bids)
- **Ready for**: Competitor scoring engine (similarity, distance, capacity analysis)

### Data Integrity Notes
- BIDDER_NAME = raw company names (original from source)
- standardized_company_name = client-approved merged names (ready for analysis)
- Both columns preserved for auditability and manual review.
- No rows lost; only consolidation and non-competitor removal.

---

*Future changes should be appended below this line with date, description, and analyst name.*

## Cleaning Pass 4 — 2026-06-08 (Quinten)

### Changes Applied

1. **Standardized bidder names based on client review**
   - Source: `bidder_potential_duplicates.csv` (client-approved decision log)
   - Created standardization mapping from 134 variations → 58 canonical names
   - Applied mapping to all BIDDER_*_NAME columns (15 columns across 134 variation rows)
   - Total bidder records affected: 2087 replacements across 1105 project rows

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

