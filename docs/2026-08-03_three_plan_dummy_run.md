# Three-plan dummy run — 2026-08-03

Target: `scratch.bid_projects_dummy`. **The real `scratch.bid_projects` was not touched.**

Three plans written, **2 rows landed**. That discrepancy is the headline finding.

---

## Why these three

**1. `193968928775465b` (9758035.pdf)** — THE ONLY FIXTURE WITH A PARSEABLE bid_deadline ('09:30AM Central Time on August 15, 2025'). Every other cached payload has bid_deadline=None and takes the 1900-01-01 sentinel for free, so this is the only one that exercises the real date-parse path and the only one that can produce a non-sentinel key. Also has 3 quantities and a full county, so it is the 'healthy row' baseline.

**2. `e9ae6f092ccca1bf` (25-001.pdf)** — ZERO quantities (archetype 'Unknown/NoQty') AND county=None. Exercises the few-or-none case, the county sentinel, and my rule that unit_source must be NULL rather than a confident 'observed' when there is nothing to have observed a unit on.

**3. `2c83fa4ee425fe1b` (22913.pdf)** — PICKED TO COLLIDE. Also ND with county=None and bid_deadline=None, so it assembles the SAME key as plan 2 (ND_UNKNOWN_UNKNOWN_1900-01-01) from a DIFFERENT PDF. This is the sentinel collision the mapping doc worries about, occurring naturally in a 7-row fixture set rather than being contrived.

---

## What each row produced

| # | plan_uid | key | row_status | missing_fields | dup | n_qty | gotchas |
|---|---|---|---|---|---|---|---|
| 1 | `193968928775465b` | `ND_MORTON_CO_UNKNOWN_2025-08-15` | complete | — | no | 3 | 11 |
| 2 | `e9ae6f092ccca1bf` | `ND_UNKNOWN_UNKNOWN_1900-01-01` | partial | county,bid_date | no | 0 | 11 |
| 3 | `2c83fa4ee425fe1b` | `ND_UNKNOWN_UNKNOWN_1900-01-01` | partial | county,bid_date | **YES** | 3 | 8 |

## Sentinels

| # | state | county (extracted → column) | city | bid_date | took UNKNOWN? | took 1900-01-01? |
|---|---|---|---|---|---|---|
| 1 | ND | `Morton` → `MORTON CO` | `None` | `2025-08-15` | **yes** | no |
| 2 | ND | `None` → `None` | `None` | `1900-01-01` | **yes** | **yes** |
| 3 | ND | `None` → `None` | `None` | `1900-01-01` | **yes** | **yes** |

## Extracted vs geocoded county

| # | extracted county | geocoded county | agree? |
|---|---|---|---|
| 1 | `Morton` | `None` | — |
| 2 | `None` | `None` | — |
| 3 | `None` | `None` | — |

**Every geocoded county is NULL**, so the comparison cannot be made on this run. These seven cached payloads predate the geocode stage entirely — their `identity` blocks have no `geocoded_*` keys at all. The comparison needs plans processed *after* the 6th stage existed and with a working midpoint; it is not a defect in the mapping.

## Units

| # | mix | base | shldr | mill | crush | grading | stock | unit_source |
|---|---|---|---|---|---|---|---|---|
| 1 | — | t | — | SY | — | CY | — | `observed` |
| 2 | — | — | — | — | — | — | — | `None` |
| 3 | t | t | — | — | — | CY | — | `observed` |

## Rows actually in the table afterwards

| key | plan_uid | source_file | row_status | duplicate_flag | duplicate_reason |
|---|---|---|---|---|---|
| `ND_MORTON_CO_UNKNOWN_2025-08-15` | `193968928775465b` | 9758035.pdf | complete | False | — |
| `ND_UNKNOWN_UNKNOWN_1900-01-01` | `2c83fa4ee425fe1b` | 22913.pdf | partial | True | same_key_different_plan_uid:e9ae6f092ccca1bf (25-001.pdf) — THIS UPSERT OVERWRITES THAT ROW |


---

## The headline: three plans in, two rows out

Plan 2 (`e9ae6f092ccca1bf`, `25-001.pdf`) **no longer exists**. Plan 3 overwrote it, because both
assemble the identical key `ND_UNKNOWN_UNKNOWN_1900-01-01` — neither has an extractable county,
neither has a parseable bid date, and neither has a geocoded city. `on conflict
(project_natural_key) do update` then treats two different projects as one.

This is not a contrived case. It occurred on the **first three-row sample drawn from a seven-row
fixture set**. The sentinels are not a rare fallback; on this corpus they are the common path, and
any two plans that both take them collide.

`duplicate_flag` is now `true` with a reason naming the overwritten plan and its source file. **That
makes the loss visible; it does not prevent it.** The old row is gone either way.

### Two bugs found by running this, both mine

1. **`find_conflicts` hardcoded the module-level `TABLE` constant** instead of the `table`
   parameter. So the first pass of this run probed the **real `scratch.bid_projects`** for
   conflicts while writing to the dummy — the wrong answer, and a read of production during a run
   whose entire purpose was not to touch it. Fixed; `table` is now a parameter.
2. **Nothing detected a same-key/different-plan collision at all.** The original checks covered
   same-`join_key`/different-`plan_uid` and same-`plan_uid`/different-key, but not the one that
   actually destroys data. Added.

## Rows I would NOT be comfortable writing to the real table

**Plans 2 and 3, and any future plan that takes both sentinels.** Reason: they do not identify a
project. `ND_UNKNOWN_UNKNOWN_1900-01-01` is not a key, it is a bucket, and every plan that lands in
it overwrites the last. Writing these to `scratch.bid_projects` would mean the corpus silently loses
a project every time two sentinel rows meet — and because `bid_results` has `ON DELETE CASCADE` on
this key, a later cleanup touching that bucket would take bid results with it.

**Plan 1 is fine.** `ND_MORTON_CO_UNKNOWN_2025-08-15` — real county, real parsed bid date,
`row_status = complete`, `missing_fields` empty. Only the city is a sentinel, which is expected
until the geocode stage runs on freshly-processed plans.

### Options, none of which I have implemented

- **Make the key unique by construction** — append `plan_uid` (or a short hash of it) when either
  sentinel fires. `ND_UNKNOWN_UNKNOWN_1900-01-01_2c83fa4e`. Ugly, and diverges from the existing
  1,591-row convention, but no plan is ever lost.
- **Refuse to write a double-sentinel row**, and report it for human keying. Contradicts settled
  decision 3 ("never reject the row"), so it needs an explicit reversal.
- **Accept the collision** and rely on `duplicate_flag` plus `plan_uid` to reconstruct afterwards —
  except the overwritten row's data is gone, so there is nothing to reconstruct from.

This is a decision, not a bug fix, and it is above my line. It also changes the shape of
`project_natural_key`, which touches the CI workstream.

## Other observations

- **The date parser works.** Plan 1's `'09:30AM Central Time on August 15, 2025'` → `2025-08-15`,
  `bid_date_unparsed = false`. It was the only fixture that could exercise this, and it passed.
- **`unit_source` behaved as intended**: `observed` for plans 1 and 3, `NULL` for plan 2, which has
  no quantities. No confident-looking claim about nothing.
- **`row_status` / `missing_fields` are doing real work** — plan 1 `complete`; plans 2 and 3
  `partial` naming `county,bid_date` rather than defaulting them silently.
- **Surprise: plan 3 has 3 quantities but `row_status = partial`.** Quantities are not in
  `REQUIRED_FIELDS`, which is correct per contract §5 (identity is required, quantities are not) —
  but it means a data-rich row can read as `partial`. Worth knowing before anyone filters on it.
- **The extracted-vs-geocoded county comparison could not be run at all** — all seven cached
  payloads predate the 6th stage and carry no `geocoded_*` keys. That comparison needs plans
  processed after the geocode stage, on a state whose DOT endpoint is up.
