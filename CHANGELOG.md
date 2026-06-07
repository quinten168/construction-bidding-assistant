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

## Cleaning Pass 1 — 2026-06-06

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

*Future changes should be appended below this line with date, description, and analyst name.*
