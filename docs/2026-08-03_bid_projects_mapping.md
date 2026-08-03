# P0-A: plan_reader → `scratch.bid_projects`, field by field

**2026-08-03. For review before any insert code is written.**

The machine-readable mapping is `pipelines/plan_reader/01_pipeline/bid_projects_mapping.yaml`. The
insert code reads that file. It does **not** fuzzy-match column names — a payload field that is not
listed there is not written, which is deliberate: a rename can then never silently drop data.

This document is the argument around that file: what it reuses from the contract, what is new, and
the six things I want a decision on rather than a guess.

---

## What this reuses from the seam contract (PR #32, now merged as `2a3c1b9`)

Reused directly, not re-derived:

| Contract | Reused as |
|---|---|
| §3 join key | `join_key` / `unkeyable_reason` columns, computed by `01_pipeline/join_key.py` (7 tests green) |
| §4.1 identity | `state`, `county`, `sp_number`→`source_project_id`, `project_location`, `source_file`, `plan_uid` |
| §4.2 quantities | the seven quantity columns, and the "absent ≠ zero" rule below |
| §4.4 dates | dates kept **unparsed** — hence `*_raw` columns alongside the parsed `bid_date` |
| §4.5 provenance | `coordinate_provenance`, and the same pattern extended to `geocode_provenance` |
| §5 missing-is-an-error | `row_status` + `missing_fields` |

**Where the contract and current code disagree, and the code wins:**

1. **§4.2 names.** The contract says `hot_mix_tons`, `shoulder_tons`, `grading_quantity`,
   `milling_sy`, `crushing_tons`, `stockpile_tons`. `bid_projects` already uses the CI model's
   names: `mix_tons`, `shldr_tons`, `grading_yards`, `mill_sy`, `crush_tons`, `stock_tons`. **The
   table wins** — it exists and has ~1,591 rows in it.
2. **§4.2 unit columns.** The contract requires every quantity to ship as value + unit +
   `unit_source`. `bid_projects` has **no unit columns at all**. I have *not* proposed adding 8 of
   them — see open question 5.
3. **§4.5 coordinates.** The contract says there is no producer. There is one now
   (`midpoint_bridge.py`, 5th stage), and as of today a reverse-geocode 6th stage. §4.5 is stale in
   your favour.

---

## Case 1 — maps to an existing column (13 fields)

`state`, `county`, `project_location`, `source_project_id`, `project_latitude`,
`project_longitude`, and the seven quantities. Full detail in the YAML.

Two transform notes worth reading:

**Quantities are a list, and zeros are already gone.** `payload.quantities` is
`[{label, value, unit}]`, and `report.py` drops any entry whose value is `None`, `""` or `0`. So an
absent quantity and a genuine zero are **indistinguishable in the payload**. The mapping writes
`NULL`, never `0`, when a label is absent. That is contract §5 applied literally, and it is the
exact failure that made ten CI features hard zeros for months.

**`source_project_id` is the raw `sp_number`, not the normalized one.** Contract §4.1 is explicit.
The normalized form goes to `join_key`.

---

## Case 2 — no column exists; proposed additions (25 columns)

All additive (`add column if not exists`), all nullable except four with defaults. Grouped:

- **Identity/provenance:** `plan_uid`, `join_key`, `unkeyable_reason`, `processed_at`,
  `source_file`, `mapping_version`, `row_source`
- **Geocoded second opinions:** `geocoded_city`, `geocoded_county`, `geocoded_state`,
  `geocoded_zip`, `coordinate_provenance`, `geocode_provenance`
- **Classification:** `plan_reader_archetype`
- **Unparsed dates:** `bid_deadline_raw`, `construction_start_raw`, `construction_end_raw`
- **Extracted, no home today:** `prevailing_wages`, `traffic_level`, `gotcha_count`
- **Completeness:** `row_status`, `missing_fields`
- **Dedupe visibility:** `duplicate_flag`, `duplicate_reason`

**`processed_at` is the column you asked for**, and it is distinct from the existing `updated_at`:
`processed_at` records when the plan went through the pipeline and never changes; `updated_at`
moves on any later edit, including an admin-UI edit.

**`plan_reader_archetype` is a new column, not a mapping onto `project_type`.** As instructed. The
two are different hierarchies, the README claims 10 project types while the code emits 6, and
Quinten is verifying the archetype logic separately. Both stay visible side by side.

**`geocoded_county` is reported, never substituted.** The reverse-geocode stage returns a county,
and the brief asked it be used for the 10 rows where the extracted county is `?` or names two
counties. It lands in its own column with a `geocode_provenance` tag. I have **not** written logic
that overwrites the extracted `county` — that would destroy the evidence that the two disagree.
What the run report will show you is: for each of those 10 rows, extracted vs geocoded, side by
side, so you can decide the rule.

---

## Case 3 — columns plan_reader cannot populate (6)

| Column | Resolution | Anything downstream break on NULL? |
|---|---|---|
| `project_natural_key` | **assembled**, not sourced — see below | It is the PK; cannot be null |
| `bid_date` | parsed from free-text `bid_deadline`, NULL when unparseable | No |
| `bid_year` | derived from `bid_date` | No |
| `project_name` | **always NULL** — no equivalent anywhere in `schema.py` | No |
| `project_type` | **always NULL** — deliberately, see above | No |
| `updated_at` | DB default `now()` | No |

**On "does anything downstream break on a NULL here":** I checked the CI-side consumers.
`project_admin.py` does `select *` and the front end renders nulls as blanks. `bid_results_admin.py`
joins on `project_natural_key` only. The CI model reads `data/processed/projects.csv`, not this
table. **I found nothing that breaks.** Caveat, stated rather than buried: every `/api/ci-data/*`
route uses `select *` with no `response_model`, so response shape is defined by the live schema —
adding 25 columns changes what those endpoints return. It should be additive-safe, but it is not
type-checked on either side (that is issue #52).

---

## Six things I want you to decide, not me

**1. Two writers, one table — this is the real risk.**
`data/push_supabase_bid_data.py::push_projects` does `insert … on conflict (project_natural_key) do
update` over `PROJECT_COLUMNS`. If a plan_reader row's assembled key ever collides with a CI batch
key, **the next CI push overwrites the plan_reader row's columns**. `row_source` makes the
collision *visible* afterwards; it does not prevent it. Options: (a) accept it for now, (b) add a
`where bid_projects.row_source is distinct from 'plan_reader'` guard to the CI upsert, (c) separate
tables. I lean (b) — one clause, and it makes the CI push non-destructive by construction. **Needs
your call, and probably Quinten's.**

**2. The city sentinel.** You said use a documented sentinel rather than blocking the write. What
string? I suggest `UNKNOWNCITY` — it slugs cleanly, sorts obviously, and greps as one token. A key
then reads `MN_STEARNS_UNKNOWNCITY_2025-08-15`. Confirm or replace.

**3. An unparseable `bid_date`.** `bid_deadline` is genuinely free text
(`"09:30AM Central Time on August 15, 2025"`, `"11/15/2025"`). When the parse fails, the natural key
loses its date component too. Same question as the city: sentinel (`UNKNOWNDATE`), or refuse to
write the row? I lean sentinel, consistent with your instruction on city, but a key with two
sentinels is very weak and I would rather you saw that trade-off explicitly.

**4. The FK cascade — a live footgun.**
`scratch.bid_results.project_natural_key references scratch.bid_projects(...) on delete cascade`.
Any dedupe strategy that ever *deletes* a `bid_projects` row silently deletes its bid results. My
proposed dedupe never deletes (insert-and-flag), so this is not triggered today. Flagging it because
the next person to write a cleanup script will not know.

**5. Unit columns — I did not add them.** Contract §4.2 wants value + unit + `unit_source` per
quantity. That is 8 more columns on top of the 25, and `bid_projects`' quantity columns are already
implicitly `t`/`CY`/`SY` by the CI model's convention. The `unit_source` distinction
(`observed` vs `assumed`) is real and the contract warns not to trust `assumed` units for
arithmetic. **Cheapest honest option:** one `unit_source` column, not eight unit columns, since the
units themselves are fixed per column. Say if you want the full eight.

**6. 25 new columns on a table the CI workstream also uses.** Additive and non-breaking, but it
takes `bid_projects` from 19 columns to 44, and more than half will be NULL on the ~1,591 historical
rows. That is the right trade per your "I would rather carry an extra column than lose data" — I
just want it stated plainly rather than discovered in a `select *`.

---

## Fields I am NOT confident about

Per your instruction to flag rather than pick:

- **`traffic_level` and `prevailing_wages`** — these are RAG-extracted (`s4_extract_rag`), not
  bid-schedule facts, so their confidence profile is different from the rest. I carried them because
  dropping data is worse, but I do not know whether the CI side wants them and they may be noise.
- **`gotcha_count`** — I reduced the gotchas list to a count. A one-row-per-project table is the
  wrong grain for 1,435 gotcha records. If gotchas need to cross the seam properly, that is a second
  table and a separate ticket, not a column here.
- **`structure`** (`type`, `n_pages`, `proposal_ranges`, `map_ranges`) — dropped entirely. It is
  document metadata, not project data. Say if you want it.

---

## What happens next, on your go

1. Additive DDL for the 25 columns (`add column if not exists`), applied to `scratch`.
2. Record assembly extracted as a pure function (#36), reading this YAML.
3. Upsert on `project_natural_key`, insert-and-flag on ambiguity (#37).
4. **One plan** end to end, row shown against this mapping field by field.
5. **6–10 plans into a dummy table**, diff shown.
6. Only then does the write point at `scratch.bid_projects`.

Steps 4 and 5 are the validation gate and are not skippable. At ~3 cents per plan, cost is not a
reason to shorten them.
