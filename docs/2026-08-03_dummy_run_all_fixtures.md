# Dummy-table run, all fixtures — 2026-08-03

Target `scratch.bid_projects_dummy`. **The real `scratch.bid_projects` was not touched.**

Re-run after the collision fix: `project_natural_key` gains a content-hash suffix when any
component is a sentinel, recorded in `key_provisional` / `key_provisional_reason`.

---

## Run A — the original three

**3 plans in → 3 rows out.** ✅ no overwrites

| plan_uid | source | project_natural_key | prov | reason | status | missing | dup |
|---|---|---|---|---|---|---|---|
| `19396892` | 9758035.pdf | `ND_MORTON_CO_UNKNOWN_2025-08-15_19396892` | Y | sentinel:city | complete | — | no |
| `e9ae6f09` | 25-001.pdf | `ND_UNKNOWN_UNKNOWN_1900-01-01_e9ae6f09` | Y | sentinel:county,city,bid_date | partial | county,bid_date | no |
| `2c83fa4e` | 22913.pdf | `ND_UNKNOWN_UNKNOWN_1900-01-01_2c83fa4e` | Y | sentinel:county,city,bid_date | partial | county,bid_date | no |

Distinct keys stored: **3** of 3 plans. All plan_uids present: **True**

---

## Run B — all seven

**7 plans in → 7 rows out.** ✅ no overwrites

| plan_uid | source | project_natural_key | prov | reason | status | missing | dup |
|---|---|---|---|---|---|---|---|
| `19396892` | 9758035.pdf | `ND_MORTON_CO_UNKNOWN_2025-08-15_19396892` | Y | sentinel:city | complete | — | no |
| `e9ae6f09` | 25-001.pdf | `ND_UNKNOWN_UNKNOWN_1900-01-01_e9ae6f09` | Y | sentinel:county,city,bid_date | partial | county,bid_date | no |
| `2c83fa4e` | 22913.pdf | `ND_UNKNOWN_UNKNOWN_1900-01-01_2c83fa4e` | Y | sentinel:county,city,bid_date | partial | county,bid_date | no |
| `6c906b58` | 9804001.pdf | `MN_DOUGLAS_CO_UNKNOWN_1900-01-01_6c906b58` | Y | sentinel:city,bid_date | partial | bid_date | no |
| `760e9a1d` | 8391182.pdf | `SD_BROOKINGS_CO_UNKNOWN_1900-01-01_760e9a1d` | Y | sentinel:city,bid_date | partial | bid_date | no |
| `d3c6880e` | 8435627.pdf | `ND_EMMONS_CO_UNKNOWN_1900-01-01_d3c6880e` | Y | sentinel:city,bid_date | partial | bid_date | no |
| `f19c9df6` | 9813645.pdf | `MN_STEARNS_CO_UNKNOWN_1900-01-01_f19c9df6` | Y | sentinel:city,bid_date | partial | bid_date | no |

Distinct keys stored: **7** of 7 plans. All plan_uids present: **True**

---

## Detail — all seven

### Sentinels and provenance

| plan_uid | state | county extracted → column | city | bid_date | unparsed? |
|---|---|---|---|---|---|
| `19396892` | ND | `Morton` → `MORTON CO` | `None` | `2025-08-15` | no |
| `e9ae6f09` | ND | `None` → `None` | `None` | `1900-01-01` | **yes** |
| `2c83fa4e` | ND | `None` → `None` | `None` | `1900-01-01` | **yes** |
| `6c906b58` | MN | `Douglas` → `DOUGLAS CO` | `None` | `1900-01-01` | **yes** |
| `760e9a1d` | SD | `Brookings` → `BROOKINGS CO` | `None` | `1900-01-01` | **yes** |
| `d3c6880e` | ND | `Emmons` → `EMMONS CO` | `None` | `1900-01-01` | **yes** |
| `f19c9df6` | MN | `Stearns` → `STEARNS CO` | `None` | `1900-01-01` | **yes** |

### Quantities and units

| plan_uid | archetype | n_qty | mix | base | shldr | mill | grading | unit_source | gotchas |
|---|---|---|---|---|---|---|---|---|---|
| `19396892` | Grading/Earthwork | 3 | — | t | — | SY | CY | `observed` | 11 |
| `e9ae6f09` | Unknown/NoQty | 0 | — | — | — | — | — | `None` | 11 |
| `2c83fa4e` | Reconstruct/Rebuild | 3 | t | t | — | — | CY | `observed` | 8 |
| `6c906b58` | HMA Overlay/Resurface | 1 | t | — | — | — | — | `observed` | 10 |
| `760e9a1d` | Mill & Overlay | 2 | t | — | — | SY | — | `observed` | 7 |
| `d3c6880e` | Reconstruct/Rebuild | 3 | t | — | — | SY | CY | `observed` | 13 |
| `f19c9df6` | Mill & Overlay | 4 | t | t | t | SY | — | `observed` | 10 |

### join_key

| plan_uid | sp_number | join_key | unkeyable_reason |
|---|---|---|---|
| `19396892` | `SS-1-806(058)057` | `ND~morton~SS1806058057` | — |
| `e9ae6f09` | `25-001` | `ND~~25001` | — |
| `2c83fa4e` | `22913` | `ND~~22913` | — |
| `6c906b58` | `SAP 021-600-023` | `MN~douglas~SAP021600023` | — |
| `760e9a1d` | `23000659` | `SD~brookings~23000659` | — |
| `d3c6880e` | `AIP 3-38-0033-020-2022` | `ND~emmons~AIP33800330202022` | — |
| `f19c9df6` | `CP 073-123-025` | `MN~stearns~CP073123025` | — |

### Totals

- rows stored: **7** / 7 plans
- provisional keys: **7** of 7
- `row_status = complete`: **1**
- `duplicate_flag`: **0**
- geocoded_city populated: **0**

---

## Verdict

**The collision is fixed.** Run A: 3 in, 3 out, plan 2 (`e9ae6f09`, `25-001.pdf`) intact — it was
the row destroyed on the previous run. Run B: 7 in, 7 out, 7 distinct keys, every `plan_uid`
accounted for. `duplicate_flag` fired on nothing, because there is nothing left to collide.

A fully-resolved key is byte-identical to what it was before the change — verified directly:
`MN_STEARNS_CO_MELROSE_2023-08-03` with a real city and a real date gets no suffix. The existing
1,591 rows are untouched by this.

## ⚠️ The caveat you should see before giving the go

**All seven rows are provisional.** Not most — all.

`geocoded_city` is NULL on every one, so `sentinel:city` fires universally, so every row gets a
hash suffix. These particular fixtures predate the geocode stage, but the shape holds more
generally: **the city component can only ever be filled by the reverse-geocode stage, which needs a
midpoint, which needs route + milepost + gross length off the title sheet.** Tonight's gate showed
that a proposal-only PDF has none of those. So until title-sheet extraction lands, a hash suffix on
essentially every plan_reader row is the expected steady state, not an exception.

That is not an argument against the decision — a suffixed key that survives beats a clean key that
overwrites. But it does mean:

- `where key_provisional` will return ~100% of plan_reader rows for now, so it identifies the
  writer more than it identifies a problem. Its value arrives when city starts resolving.
- The keys will not resemble the 1,591 historical rows in practice, only in principle.
- The recomputation pass we have already agreed to is not optional cleanup; it is the step that
  makes these keys match the corpus.

**Second, smaller:** `19396892` is `row_status = complete` **and** `key_provisional = true`. Those
are independent axes and that is correct — the row has everything contract §5 requires, but its key
still leans on a sentinel. Worth knowing before anyone treats `complete` as "safe to key on".

**Third:** six of seven rows have `bid_date_unparsed = true`, all because `bid_deadline` is `None`
in the payload rather than because the parser failed. The parser was exercised once, on
`19396892`, and got it right. So this run says very little about parse quality — it says the
extractor rarely populates `bid_deadline` at all, which is a different problem and probably a
bigger one.

## Rows I would be comfortable writing to the real table

**All seven now.** No row overwrites another, every row is traceable to its PDF by `plan_uid`, and
every provisional key is findable with one indexed predicate. The objection from the previous run —
that these rows destroy each other — is gone.

The remaining reservation is not about safety, it is about usefulness: seven rows whose keys are
all provisional and whose cities are all `UNKNOWN` will not join to anything on the CI side. They
are a correct record of what the plan reader currently extracts, which is the point of the
exercise, but nobody should expect them to match a historical project yet.
