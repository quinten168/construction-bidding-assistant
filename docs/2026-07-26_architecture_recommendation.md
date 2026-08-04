# Architecture recommendation: connecting plan_reader and ci_model

**2026-07-26. For Quinten and Wenyu. Author: T.**

This is a **contract**, not a design proposal. It states what crosses the seam between
`pipelines/plan_reader` and `pipelines/ci_model`, in what shape, and who produces each field. It
is meant to be argued with. Where something is undecided it says so.

Companion documents: `docs/2026-07-26_ci_model_issues.md` (what is broken on the CI side and why
this contract alone will not close #11), and `docs/DATA_INVENTORY.md` (field-level evidence).

---

## AMENDMENT — 2026-08-03

**This document is merged as a historical record plus a still-valid field spec. Two of its
premises have since changed. Read this block before acting on anything below.**

**1. D1 is superseded. `csi_v2.db` is no longer the intended source of truth.**
`docs/2026-07-27_postgres_migration_plan.md` reverses it: Supabase Postgres becomes the store every
writer writes to, and `csi_v2.db` becomes a dated archive. Everywhere this document says
"plan_reader writes the agreed record to `csi_v2.db`" (§1, §9 phases 1-3), read "writes to
Postgres." The §1 flow diagram's `export_ci_input.py -> ci_model_input.csv` hop may no longer be
needed at all, since both sides can now read the same database.

**2. The target table exists, and it is not the one this document imagined.**
`scratch.bid_projects` (`data/push_supabase_bid_data.py`, `BID_PROJECTS_DDL`) was created by
`5381953` and holds ~1,591 rows. It has 19 columns, a `project_natural_key` primary key, and
`scratch.bid_results` foreign-keyed to it `on delete cascade`.

This matters because **`project_natural_key` is not this document's `join_key`**:

```
this document §3   join_key             = STATE~county~SPNUMBER
bid_projects       project_natural_key  = {state}_{county}_{city}_{bid_date}
```

They are built from different fields. `project_natural_key` needs a **city** and a **parsed bid
date**; plan_reader produces neither (its `bid_deadline` is free text such as
`"09:30AM Central Time on August 15, 2025"`, and there is no city field in `schema.py` at all).
Which key a plan_reader-sourced row carries is an **open decision** — see the identity-key brief
and issue #10. Do not assume §3's key is what lands in `bid_projects`.

**3. §4.5 is stale in your favour: latitude/longitude now have a producer.**
The document says "no producer exists on the plan_reader side." Since 2026-07-30 there is one.
`plan_reader` extracts `route_number`/`begin_milepost`/`end_milepost`/`total_gross_length` and
`apps/api/backend/midpoint_bridge.py` converts them to coordinates as the 5th `process_pdf` stage.
`coordinate_provenance` (§4.5) becomes more important, not less — it is now the only way to
distinguish a DOT-GIS midpoint from a human-entered correction from a genuine null. Note the CLI
path (`run.py`) was not extended with this stage, so batch-ingested plans still have no coordinates.

**What is unchanged and still authoritative:** §3's normalization rules (implemented and tested at
`pipelines/plan_reader/01_pipeline/join_key.py`, 7 tests green), the §4 field definitions and
types, `unit_source` (§4.2), the archetype vocabularies and their mapping (§4.3), and — most
importantly — **§5, "a missing required field is an error, not a zero."** §5 is storage-agnostic
and is the single most valuable clause in this document.

Per the repo's working rules, this amendment is appended rather than rewriting the body: the
document's value is as a record of what was decided on 2026-07-26 and why.

---

## 1. What this replaces

There is no orchestration agent and no new `pipelines/orchestration/` folder. The two modules
already run in sequence at runtime. What they lack is a shared vocabulary, not a faster messenger.

**How it works today:** `report.py::process_pdf` extracts a plan into a JSON payload cache. Nothing
reaches `csi_v2.db`. `competitor_live.py:60-72` reverse-looks-up an **existing** `job_id` by county
and state, and returns nothing if there is no match. So a genuinely new plan cannot produce a
competitor report at all.

**How it will work:** plan_reader writes the agreed record to `csi_v2.db`. An export script
produces a CSV in the shape below. ci_model reads that CSV. No imports between modules, no LLM in
the middle of a deterministic data flow.

```
PDF -> process_pdf -> csi_v2.db -> export_ci_input.py -> ci_model_input.csv -> ci_model
                      (source of truth)                  (what you read)
```

---

## 2. Decisions already made

These are settled. Raise them if you disagree, but they are not open by default.

| # | Decision |
|---|---|
| D1 | `csi_v2.db` is the source of truth. You get a CSV, generated from it, regenerated per run |
| D2 | All material quantities cross. Consume what you need, ignore the rest |
| D3 | plan_reader reports the raw value **and its unit**. Any conversion to a canonical unit is yours |
| D4 | Internal row identity is the PDF content hash. Stable across re-uploads and renames |
| D5 | The join key is normalized `(state, county, sp_number)`. **Not** `job_id` |
| D6 | The contract carries tonnage. How capacity is computed from it is your design decision |
| D7 | One-directional. Bid-result write-back and retraining are a separate feature |

---

## 3. Identity and key

Two different things, deliberately.

**`plan_uid`** is plan_reader's internal row identity: the 16-character content hash that already
exists at `s1_convert.py:79-92`. It is opaque. You do not need it, but it is in the export so a row
can be traced back.

**`join_key`** is what you join on.

```
state       upper(trim(x))                          ->  "MN"
county      lower(trim(x)), THEN collapse whitespace and hyphens to one space,
            THEN strip a trailing "county"
              "Otter Tail County"  ->  "otter tail"
              "Otter-Tail-County"  ->  "otter tail"
              "  OTTER   TAIL  "   ->  "otter tail"
sp_number   upper(x), remove every non-alphanumeric character
              "SP 8303-48"       ->  "SP830348"
              "CP-13(23)01"      ->  "CP132301"
              "SAP 021-600-023"  ->  "SAP021600023"

join_key = state + "~" + county + "~" + sp_number
```

**Both sides must implement this identically** or the join silently returns zero matches.

**The county step order is load-bearing, which is why it is spelled out above.** Collapse separators
*before* stripping the trailing `county`. Doing it the other way round leaves `Otter-Tail-County`
untouched, because its trailing token is joined by a hyphen rather than a space, and the two orders
then produce different keys for the same county. No value in the current 117-plan corpus is
order-sensitive, so this costs nothing today and prevents a silent zero-match later. The first
revision of this document listed the two steps in the opposite order.

**Unkeyable rows.** If `sp_number` normalizes to a string containing no digits, `join_key` is null
and `unkeyable_reason` is set. The row is still stored and exported with a null key.

**Measured against the current 117-plan corpus, this rule catches exactly 1 row**, whose
`sp_number` is the literal string `UNKNOWN`.

**It does not catch what it was written to catch.** A further 15 rows hold a road name rather than a
project number (`Cty Hwy 9`, `CSAH-2`, `CSAH-82`, `CR-1`, `CR-8`, `CR-12` and similar). Every one of
them contains a digit, so every one passes the digit test and produces a syntactically valid
`join_key` that will match nothing on your side. **That is worse than a null**, because it fails
silently instead of declaring itself.

Widening the rule is deliberately not done here. The value is present and the trust level is what is
missing, which is the same problem `unit_source` solves for units in §4.2, so a provenance or
confidence column is the likely answer rather than a stricter reject pattern. Tracked as #35, under
#10.

> **This requires work on your side.** There is no `sp_number` column anywhere in `data/` or
> `pipelines/ci_model/`. The number is embedded in free text in `source_project_id`, mixed with
> SAP, CP, PROJ #, CALL and PCN formats, sometimes several in one cell
> (`P 0079(88)133, NH 0212(202)38 (PCN 06G1, 06G2)`). Either a normalized key column gets added, or
> this key cannot be joined. See `2026-07-26_ci_model_issues.md`, Issue 6.

---

## 4. The record

One row per plan.

### 4.1 Identity and location

| field | type | null? | producer | notes |
|---|---|---|---|---|
| `plan_uid` | text | yes | plan_reader | content hash, opaque. Always present for a plan arriving through the live path. See the note below |
| `join_key` | text | yes | plan_reader | null when unkeyable |
| `unkeyable_reason` | text | yes | plan_reader | set only when `join_key` is null |
| `source_file` | text | no | plan_reader | original PDF filename, for humans |
| `state` | text(2) | yes | plan_reader | expected `MN` / `ND` / `SD`. The current corpus also holds 4 rows of `XX` and 1 of `MT`, which corrupt the key prefix. Tracked with the road-name issue |
| `county` | text | yes | plan_reader | bare name, no "County" suffix |
| `sp_number` | text | yes | plan_reader | as extracted, **not** normalized. Normalize with §3 |
| `project_location` | text | yes | plan_reader | free text: route, termini, road name |

**Note on `plan_uid`.** It is the content hash of the source PDF, so it is always computable for a
plan arriving through the live path. Six of the 117 rows already stored in `csi_v2.db` have no
recorded source PDF path, so no hash can be derived for them at all. Whether those six export with
a null `plan_uid` or are excluded from the export is open, and is being settled as part of the
backfill work in #38. This column was declared non-nullable in the first revision of this document,
which was wrong.

### 4.2 Quantities

Seven buckets. Every one ships as three columns: value, unit, and where the unit came from.

| field | type | null? | unit column | notes |
|---|---|---|---|---|
| `hot_mix_tons` | numeric | yes | `hot_mix_unit` | your `MIX TN` / `mix_tons` |
| `base_tons` | numeric | yes | `base_unit` | `BASE TN` |
| `shoulder_tons` | numeric | yes | `shoulder_unit` | `SHLDR TN` |
| `grading_quantity` | numeric | yes | `grading_unit` | `GRADE CY` |
| `milling_sy` | numeric | yes | `milling_unit` | `MILL SY` |
| `crushing_tons` | numeric | yes | `crushing_unit` | `CRUSH TN` |
| `stockpile_tons` | numeric | yes | `stockpile_unit` | `STOCK TN` |
| `unit_source` | text | no | — | `observed` or `assumed`, see below |

**`unit_source` is the important column.** plan_reader has two extraction paths and they differ:

- `observed` means the unit was read off the bid schedule and stored per line item. Trust it.
- `assumed` means the unit was inferred from the field name, not read from the document. The live
  extraction path currently instructs the model to return a bare number (`s3_extract.py:52`) and
  re-attaches a unit from a hardcoded dictionary (`report.py:35-36`). **Do not trust `assumed`
  units for arithmetic.** Fixing this is queued, not done.

**Known gap, stated plainly.** plan_reader only records a quantity into a bucket when its
`(category, unit)` pair matches one of seven hardcoded combinations
(`quantity_crosswalk.py:96-104`). Square feet is never handled. A base course bid in square yards
contributes nothing to `base_tons`. Such line items are stored but arrive as null here. This is the
behaviour Wenyu demonstrated on 2026-07-22, and it is a real data loss, not a display issue.

### 4.3 Classification

| field | type | null? | notes |
|---|---|---|---|
| `archetype` | text | no | plan_reader vocabulary, see mapping below |
| `archetype_rule` | text | no | which branch fired, for audit |

**The two sides already use the same rule.** plan_reader's live classifier
(`apps/api/backend/project_registry.py:30,55-56`) and yours
(`data/build_project_competitor_panel.py:120-148`) use identical thresholds
(`0.15 / 1000.0 / 500.0 / 1000.0`) and the same waterfall. Verified byte-identical 2026-07-26. No
change is needed on either side. Only the spelling differs:

| plan_reader | ci_model |
|---|---|
| `Reconstruct/Rebuild` | `reconstruct_rebuild` |
| `Mill & Overlay` | `mill_overlay` |
| `HMA Overlay/Resurface` | `hma_resurface` |
| `Grading/Earthwork` | `grading_earthwork` |
| `Aggregate/Base/Gravel` | `aggregate_base_gravel` |
| `Other` | `other` |
| `Unknown/NoQty` | `other` (no equivalent) |

> Note: a **third** classifier exists in `04_tools/06_derive_classification.py` using `> 0` tests
> instead of thresholds. It serves the dashboard and the sweet_spot analysis, is back-tested
> against 1,591 projects, and is **not** what crosses this seam. It is not being changed.

### 4.4 Dates

| field | type | null? | notes |
|---|---|---|---|
| `bid_deadline` | text | yes | as written on the plan, **not** normalized |
| `construction_start` | text | yes | as written |
| `construction_end` | text | yes | as written |

Dates are deliberately unparsed. plan_reader does not currently normalize them and guessing a
format would be worse than passing the source string.

### 4.5 Specified but not yet produced

These columns exist in the export and are **always null today**. They are declared now so the
contract does not change when the work happens.

| field | type | notes |
|---|---|---|
| `latitude` | numeric | no producer exists on the plan_reader side |
| `longitude` | numeric | same |
| `coordinate_provenance` | text | `surveyed` / `midpoint` / `centroid` / `user_entered` / null |
| `project_stationing` | text | not extracted today, see below |

**Why:** stationing to lat/long conversion (Jay's midpoint script) is deferred by T as of
2026-07-26. Two things worth knowing. First, plan_reader does **not** currently emit stationing
either; `project_stationing` appears once in the codebase as a regex entry in a corpus scan
(`_scan_field_locations.py:111`), never as a stored field. `docs/ARCHITECTURE.md` §5 is wrong about
this and will be corrected. Second, your county-centroid fallback
(`build_pit_features.py:275-320`) has **never actually run**, because `projects.csv` has zero null
coordinates. A plan_reader-sourced project would be the first row to exercise it.

**`coordinate_provenance` matters more than the coordinates.** Without it, a null `latitude` is
indistinguishable between "not extracted," "extraction failed," and "a centroid was substituted."

---

## 5. The clause that matters most

**A missing required field is an error, not a zero.**

Both modules currently violate this, in the same way, on opposite sides of the seam. plan_reader
drops a quantity whose `(category, unit)` pair misses a seven-entry dictionary and stores null.
ci_model turns a missing quantity into `log1p(0) = 0` at `build_ranking_features.py:229-239`.
Neither logs anything.

That symmetry is why ten of your 33 features have been hard zeros in production without anyone
noticing. The field table above is worth less than this one rule.

**Concretely:** the export writes a `row_status` column (`complete` or `partial`) and a
`missing_fields` list. A consumer that substitutes a default for a field marked missing is
choosing to, rather than doing it by accident.

---

## 6. What this contract does not fix

**Delivering tonnage to your doorstep will not make tonnage reach your model.** Verified
2026-07-26: `log_mix_tons`, `log_grading_yards`, `log_base_tons`, `log_shldr_tons`, `log_mill_sy`,
`log_crush_tons`, `log_stock_tons` and `project_size_proxy` are all identically zero across all
237,346 rows of `ranking_predictions.csv`, carry `feature_weight = +0.0000` in both trained models,
and are labelled `inactive (zero weight)` in `logistic_feature_importance.csv`.

The cause is inside ci_model: `build_training_panel.py:118-130` merges against a five-column
projection that drops the quantities, and `build_ranking_features.py:229-239` then reads the
resulting nulls as zeros.

**Issue #11 needs both halves.** Full detail and a suggested fix order are in
`docs/2026-07-26_ci_model_issues.md`.

One thing that may be reachable sooner: the client-facing season capacity number is computed at
report time from `projects.csv`, entirely outside the model
(`06_reporting/agent/executor.py:63-112`). It may not need the model fix at all.

---

## 7. Questions that need a written answer

**Q1. Capacity semantics.** Can capacity be computed for an in-flight bid year, and from what? T's
position across three meetings has been that capacity is only computable from completed bids.
Quinten's has been that 2024/25-only capacity is not useful to the client and 2026 tonnage must
come from newly read plans. This contract ships the tonnage either way, but **the definition is
yours to state** and #11 cannot be scoped until it is.

**Q2. Where should the CSV land, and in what shape?** The proposal is one row per plan, full-file
replacement per run, same pattern as `publish_to_supabase.py`. If your pipeline wants a different
column order, dtypes, or filename, say so now.

**Q3. How does a new project enter your pipeline?** There is no append path today
(`build_project_competitor_panel.py:579` is a full regeneration), and re-running renumbers `job_id`
for every project after the inserted one. This is the last unsolved piece of the live use case.

---

## 8. Out of scope, deliberately

- **Bid-result write-back and retraining.** Separate feature, separate UI, separate triggers.
- **Jay's midpoint script, stationing extraction, lat/long production.** Deferred 2026-07-26.
  Fields are reserved above.
- **Fixing the live extractor's unit blindness.** Mitigated meanwhile by `unit_source`.
- **Unifying the third archetype classifier.** Not needed; see §4.3.

---

## 9. Sequence

| phase | who | what |
|---|---|---|
| 0 | Quinten, Wenyu | Review this document. Answer Q1 to Q3 |
| 1 | T | Live path writes to `csi_v2.db`, keyed on content hash (issue #13) |
| 2 | T | Stamp and backfill `join_key` on both paths |
| 3 | T | `export_ci_input.py` produces the CSV above |
| 4 | Quinten, Wenyu | Add the key column, restore quantities to the panel, decide the new-project path |

Phases 1 to 3 are not blocked by phase 0, but **phase 3 is worthless if phase 0 rejects the
shape**, so please read this before the phase 1 work lands.
