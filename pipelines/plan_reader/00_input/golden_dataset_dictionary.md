# Golden Dataset — Data Dictionary

**File:** `2026-06-09_golden_dataset.csv` · **Date:** 2026-06-09 · 37 rows (1 per project)

This is the **single canonical schema** for the Plan Reader: the columns the extractor
should produce AND the columns the golden (ground-truth) set holds. Every column is tagged
by **SOURCE** so it's clear who fills it:

- **`PDF`** — the Plan Reader extracts it from the plan document
- **`MASTER`** — comes from the client's bid/results data (the master CSV), not the plan
- **`HAND`** — a human labels it (verification, gotcha sign-off, notes)

| # | Column | Type | Source | Notes |
|--:|---|---|---|---|
| — | `contract_id` | string | MASTER | **Join key to the master CSV.** Not in the original 30-col spec, kept as the primary key (see ⚠️ below). |
| 1 | `letting_number` | string | PDF/MASTER | DOT letting/control number. **Blank for now** — not a clean field in the master; often embedded in the project name as a PCN/SP number. |
| 2 | `sp_number` | string | PDF | State project number (e.g. `SAP 032-629-048`, `SP 8303-48`). Extractable from the plan title sheet. |
| 3 | `state` | MN/ND/SD | PDF | 2-letter code. Extractor infers from location. |
| 4 | `district` | string | PDF/MASTER | DOT district number. Blank for now. |
| 5 | `county` | string | PDF | County where work occurs. |
| 6 | `project_location` | string | PDF | Specific road/route/highway + stationing. |
| 7 | `date` | date | MASTER ⚠️ | **TRAP:** in this golden set `date` = the date **the client placed its bid** (from the master), NOT the DOT letting date. The PDF's letting date is a *different* value. Do **not** cross-match on date alone (see crosswalk caveat). Currently excluded from eval scoring for this reason. |
| 8 | `time` | HH:MM | PDF | Letting time. Blank for now. |
| 9 | `prevailing_wages` | bool | PDF | Davis-Bacon or state prevailing wage required (YES/NO). |
| 10 | `price_of_diesel` | float | — | the client internal estimating input (constant 3.735), **not on the plan**. Excluded from eval. |
| 11 | `mix_tn` | float | PDF | Hot mix asphalt tonnage (bid schedule). |
| 12 | `grade_cy` | float | PDF | Grading cubic yards. |
| 13 | `base_tn` | float | PDF | Aggregate base tonnage. |
| 14 | `shldr_tn` | float | PDF | Shoulder material tonnage. |
| 15 | `mill_sy` | float | PDF | Milling square yards. |
| 16 | `crush_tn` | float | PDF | Crushed aggregate tonnage. |
| 17 | `stock_tn` | float | PDF | Stockpile tonnage. |
| 18 | `box` | int | PDF | Box culvert **count**. ⚠️ Master only knows *presence*, so prefilled rows use `1` = "≥1 present", blank = unknown. The extractor should return a true count. |
| 19 | `project_duration` | int | PDF | Duration in calendar/working days. Blank for now. |
| 20 | `completion_date` | date | PDF | Required completion date. Blank for now. |
| 21 | `special_provisions` | string | PDF | Comma-separated SP codes/descriptions. Blank for now. |
| 22 | `gotcha_types` | string | PDF→HAND | Comma-separated tags from `taxonomy.py` (20 canonical types). **Blank until Alex signs off** on the taxonomy. |
| 23 | `gotcha_summary` | string | PDF | One sentence describing key constraints. |
| 24 | `bid_outcome` | enum | MASTER | `no_bid` / `bid_lost` / `bid_won` / `unknown`. |
| 25 | `csi_bid_amount` | float | MASTER | the client's submitted bid (if bid). |
| 26 | `winning_bid_amount` | float | MASTER | Winning bid from results. |
| 27 | `gross_margin` | float | MASTER | the client's estimated gross margin % (if bid). |
| 28 | `source_file` | string | — | Filename of the source PDF (only 2 rows have a local PDF today). |
| 29 | `manually_verified_by` | string | HAND | Who verified this row (T / Jay / Alex). Blank until verified. |
| 30 | `notes` | string | HAND | Anything that doesn't fit above. |

## ⚠️ Three things to confirm

1. **`contract_id` vs `letting_number` as primary key.** Your spec lists `letting_number`
   as the PK, but the value that actually links a row back to the client's master data is
   `contract_id` (1633, 1654, …). I kept `contract_id` as the first column so the golden
   set stays joinable. `letting_number` is blank because the master doesn't carry a clean
   DOT letting number. **OK to keep contract_id, or do you want it dropped?**

2. **`project_name` was dropped** (not in your 30-col spec). It's the only human-readable
   label (e.g. "SAP 032-629-048 (CSAH 29) GRADING, CULVERTS, PAVING"). Recommend adding it
   back as a non-extracted reference column. **Add it back?**

3. **`date` semantics** — see row 7. In the golden set it's the client's bid date, not the plan's
   letting date. The extractor would produce the *letting* date. These must not be compared,
   which is why `date` is currently out of eval scope.

## Status of the 37 rows

- **2 rows have a local PDF** (`SAP 032-629-048 Plan.pdf`, `08MQ_NonSection.pdf`) → these
  are the only rows the extractor can be scored against today.
- **All 37 rows** have MASTER columns prefilled (outcome, quantities, margins) from the
  master join. `verified=false`: the quantities are auto-filled and not yet human-checked,
  and ~146 master rows may be mis-attributed (the date+county key collision).
- **PDF-only and HAND columns are blank** awaiting (a) more local plan PDFs and (b) the
  extractor being aligned to this schema.

---

## ⛔ The seven quantity columns are NOT to be edited to track the client ruling — 2026-08-10

`mix_tn` / `grade_cy` / `base_tn` / `shldr_tn` / `mill_sy` / `crush_tn` / `stock_tn` hold **the client's
own recorded practice at the time the letting was bid**. They predate the 2026-08-07 rulings in
`pipelines/plan_reader/05_knowledge/quantity_crosswalk.py::CSI_RULINGS_2026_08_07`. Where a ruling
changed which bucket a quantity belongs in, this file **still states the pre-ruling number, and
that is correct** — it is what makes the file independent ground truth rather than a second copy of
our own crosswalk.

Concretely: contract **1630** (Murray Co MN / Fulda, `9786015.pdf`) states `mill_sy = 8,731`. The
pipeline now produces **15,828**, because Alex's ruling #5 moved `REMOVE BITUMINOUS PAVEMENT`
(7,097 SY on that plan) from grading into milling. **Both numbers are right for their own rule
set.** Editing 8,731 to 15,828 would erase the only evidence that ruling #5 changes how the client's own
`MILL SY` column was filled.

**The benchmark is ruling-aware instead.** It carries three values, never two — the raw golden, the
ruling delta with the ruling that produced it named, and the derived adjusted value — and reports
`MATCH_RAW`, `MATCH_RULING_ADJUSTED` and `RULING_CONTRADICTS_GOLDEN` as separate statuses:

| | |
|---|---|
| design | `docs/_spec/2026-08-10-ruling-aware-golden.md` |
| tool | `tools/golden/2026-08-10_ruling_impact.py` → `2026-08-10_ruling_impact.csv` |
| evidence | `docs/_session/2026-08-10-golden-reconcile.md` |
| enforcement | `tools/golden/2026-08-10_test_ruling_aware.py` asserts all seven quantity columns are byte-identical to the committed version. A "just fix the golden" commit fails this test. |

Correcting a **transcription error** (a value that never matched what the client wrote) is a different
thing and is allowed — record it in `notes` and set `manually_verified_by`.
