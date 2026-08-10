# Key dates and phasing gotchas — P0 #5

2026-08-10. Board: `docs/_session/2026-08-08-tasks-deployment.md` §5.
Spec: `docs/_spec/2026-08-10-phasing-gotcha.md`. Code: `pipelines/plan_reader/01_pipeline/phasing.py`.

**Bottom line: the gap is retrieval and shape, not schema.** Five of the six fields exist, are
wired, and fill at a usable rate. `phasing_requirements` exists, fills at 1 in 8, returns the wrong
text when it does fill, and — the actual reason it is "invisible" — **is dropped on the floor
between the extractor and the report.** No schema field was missing. Two were worth adding anyway
and their exact text is in spec §7.

---

## 1. Fill rates for the six existing fields

Measured 2026-08-10. Three storage surfaces, and they disagree, so all three are reported.

### 1.1 Live PDF-drop path — `00_input/_report_payload_cache/*.json`, n = 12

The path the demo shows. This is the only surface where all six fields have somewhere to land.

| Field | Filled | Rate |
|---|---|---|
| `construction_end` | 11 / 12 | **92%** |
| `final_completion` | 7 / 12 | 58% |
| `substantial_completion` | 5 / 12 | 42% |
| `construction_start` | 4 / 12 | 33% |
| `bid_deadline` | 2 / 12 | 17% |
| `phasing_requirements` | **0 / 12** | **0% — the key is not in the payload at all** |

### 1.2 Batch corpus — per-plan JSON, n = 8 of 120 plan directories

Only 8 of the 120 plan dirs under `00_input/plans/` contain a JSON. `results.csv` has the same 8 rows.

| Field | Filled |
|---|---|
| `construction_end` | 8 / 8 |
| `construction_start` | 3 / 8 |
| `phasing_requirements` | **1 / 8**, and that one is wrong — see §3 |
| `substantial_completion` | **key absent from every JSON** |
| `final_completion` | **key absent** |
| `bid_deadline` | **key absent** |

Those three JSON keys and their `results.csv` columns predate the fields being added to `schema.py`.
The artifacts are stale, not the schema.

### 1.3 Batch corpus — `csi_v2.db`, n = 117 plans

**Zero. There is no column for any of the six.** `plan_metrics` has 35 columns; not one is a date.
The only related column is `has_phasing`, a boolean.

Two verification methods, both named:
1. `PRAGMA table_info(plan_metrics)` — no `construction_start`/`_end`/`substantial_completion`/
   `final_completion`/`bid_deadline` column.
2. `grep -cE` for those five names across `04_tools/00_init_db.py`, the file that creates the
   schema → **0**.

`plan_metrics.contract_duration_days` exists and is **NULL on all 100 rows**.

> **Naming trap for whoever touches this next.** `plan_metrics.schedule_status`,
> `schedule_signal`, and `schedule_pages` are about the **bid schedule** (the item list), not the
> time schedule. `schedule_status='extracted'` on 60 plans says nothing about dates.

---

## 2. Is `phasing_requirements` usable, and who consumes it?

**It produces prose that no downstream consumer reads.** Traced to its consumers:

| Consumer | Reads it? |
|---|---|
| `s4_extract_rag.fill_rag_fields` | **writes** it into `record` (SCALAR_QUERIES entry 2) |
| `schema.flag_rows` | reads it → `02_outputs/flags.csv` (batch only, 8 plans) |
| `schema.flatten_row` | reads it → `results.csv` (batch only, 8 plans) |
| `apps/api/backend/report.py::process_pdf` | **does not** — `identity_fields` (l.220-231) omits it |
| `apps/api/backend/final_report.py::_payload_from_plan_id` | **does not** — same omission |
| the report an estimator sees | **never** |

So on the live path the field is extracted, paid for with a Claude call, written into `record`, and
then silently discarded at payload assembly. Two verification methods for "no consumer in `apps/`":
1. `grep -rn "phasing_requirements" apps/ --include=*.py --include=*.ts --include=*.tsx` → **0 hits**.
2. Empirical — the key is absent from all 12 `_report_payload_cache` JSONs (§1.1).

That is the mechanism behind "currently invisible to us." It is a plumbing break, one line long.

---

## 3. The `has_phasing` flag, and why 57% is worse than nothing

`plan_metrics.has_phasing = 1` on **57 of 100** plans, set by `04_tools/07_gotcha_extract.py` (and
`07_gotcha_prefilter.py`) from the `phasing_staging` gotcha. Reading the 57 evidence strings, it is
collapsing three different things that price completely differently:

| What it caught | Example | Estimator cost |
|---|---|---|
| in-season sequence of operations | Watonwan p.400: "PAVE FIRST LIFT / APPLY INTERIM MARKINGS / PAVE SECOND LIFT" | crew sequencing, no second setup |
| traffic staging drawn on the plan | Jackson SAP-032 p.43: "PHASE 1 / PHASE 2 construction limits shown on plan" | traffic control |
| **a real break-and-resume** | Mountrail 8371604 p.8: "Construction in this phase may not begin until Phases 1 & 2 are completed." | **remobilization** |

At a 57% base rate a boolean is noise. This is exactly the "a `true` tells an estimator nothing"
problem the board named.

### The smoking gun

`2023_WATONWAN-CO-MN_SP-8303-48` is the corpus's clearest overwinter contract. Proposal **page 1**:

> **Starting Date:** **Completion Date:** 7/10/2023 6/1/2024
> *This Contract Contains Intermediate Completion Dates*

Our extracted `phasing_requirements` for that plan:

> "The contract requires work to be organized into defined phases and stages within the Work
> Breakdown Structure (WBS). The WBS includes Level 2: Construction, Level 3: Phase TBD, and
> Level 4: Stage TBD nodes…"

That is MnDOT's **Primavera scheduling-software** provision. Retrieval matched the word "phase" in
a section about WBS coding and returned it as the project's phasing. Meanwhile
`construction_start` and `construction_end` — both extracted correctly, both `confidence: high`,
both citing page 1 — already contained the answer.

**The design consequence: the strongest break-and-resume signal in this corpus is arithmetic on two
fields we already fill at 92%, not a retrieval result.** Retrieval supplies the narrative and the
citation; it must not be relied on for the detection.

---

## 4. The taxonomy today, and what was missing

`01_pipeline/taxonomy.py`, family **"Schedule & sequencing"**, 4 codes before today:

| Code | Definition | Corpus hits |
|---|---|---|
| `phasing_staging` | work built in defined phases/stages or a mandated sequence | 57 plans |
| `tight_schedule` | aggressive deadline, short window, or interim milestones | 94 plans |
| `seasonal_window` | calendar-restricted windows (species/weather/agency) | 67 plans |
| `night_work` | night/weekend/off-peak hours | 66 plans |

**No code existed for break-and-resume.** `phasing_staging` is about *order*; `seasonal_window` is
about *when you may work*, not *that you must leave and return*; `tight_schedule` mentions "interim
completion" in its triggers but is defined as an aggressive deadline, which is the opposite problem.

Added today (`taxonomy.py`, now 25 types): **`phase_break_remobilization`** and
**`interim_milestone_dates`**, both `decision_driver`. `phasing_staging` was left untouched — two
batch tools write it and the board says do not break what runs.

---

## 5. Corpus grounding — the verbatim language, with counts

Sources, all local, **no Box** (per the coordinator's correction; Box reads time out):
`csi_v2.db.sections` — 37,261 sections across 100 plans — and `00_input/_md_cache` — page-level
markdown for 17 whole plan sets.

### 5.1 The phrasings that are real break-and-resume

**A. The MnDOT proposal-cover declaration — the single most machine-readable signal.**
2 plans in `sections`, 2 of 17 in `_md_cache`.

> `2023_WATONWAN-CO-MN_SP-8303-48` p.1 — "**Starting Date:** **Completion Date:** 7/10/2023
> 6/1/2024 *This Contract Contains Intermediate Completion Dates*"

> `2023_WILKIN-CO-MN_TH-75` p.1 — "Length: 0.170 Miles **Starting Date:** **Completion Date:**
> 6/5/2023 10/15/2023 *This Contract Contains Intermediate Completion Dates*"

> `_md_cache/187bbb4f79af22ad` p.1 — "**Starting Date:** **Completion Date:** January 5, 2026
> October 10, 2026 *This Contract Contains Intermediate Completion Dates*"

**B. Overwinter wear-course hold — the canonical estimator complaint, stated in the plan's words.**
1 plan, 2 occurrences.

> `2025_MURRAY-CO-MN_CSAH-2` p.181 — "Final bituminous wear course along Maryland Ave. **shall not
> be placed until the following construction season** after allowing the non-wear course to be
> through a free thaw cycle. 12. Final bituminous wear course along CSAH 2 shall be placed during
> the Murray County project during the following construction season."

> same plan p.301 — "…shall be left unpaved over a winter season. B. The Final bituminous wear
> course shall not be placed until the following construction season after allowing the non-wear
> course to be through a freeze thaw cycle."

**C. Gated notice-to-proceed — a start date the contractor does not control.** 2 plans.

> `2023_BROOKINGS-CO-SD_SURFACING` and `_8391182` p.44-45 — "The Work will be substantially
> complete on or before **October 15, 2023**. Furthermore, the **Notice to Proceed will not be
> issued prior to August 1, 2023** (Note: It will be acceptable for the contractor to request to
> work prior to August 1, 2023, **pending the completion of structure replacements** on Brookings
> County 38…)"

That one is a 10-week window whose start is gated on somebody else's contract.

**D. Phase gated on a preceding phase.** 1 plan explicit.

> `2023_MOUNTRAIL-CO-ND_8371604` p.8 — "**Construction in this phase may not begin until Phases 1
> & 2 are completed.**"

**E. ROW not available this season.** 1 plan.

> `2023_BLUE-EARTH-CO-MN_SAP-007-626-019` p.54 — "The proposed right of way … **is not anticipated
> to be available until late 2023**, therefore the Contractor must plan to stay within the existing
> right of way with all construction activities in this area in 2023."

**F. The date-span signal itself.** Of the 8 corpus plans with extracted dates, **2 span a winter**:
Watonwan SP-8303-48 (2023-07-10 → 2024-06-01) and `2025_WATONWAN-CO-MN_WATLINE-TRAIL`
(2025-09-15 → 2026-06-15). `phasing_requirements` found the break in **neither**.

### 5.2 The phrasings that look right and are boilerplate — measured

This is the more important half of the finding. A naive keyword extractor for this gotcha would be
mostly wrong, and confidently so.

| Phrase | Corpus hits | What it actually is |
|---|---|---|
| `intermediate completion` | 72 matches / **40 plans** | mostly the **EJCDC definition**: "*Milestone* —A principal event in the performance of the Work that the Contract requires Contractor to achieve by an intermediate completion date" |
| `suspension of work` | 315 matches / **57 plans** | mostly **EJCDC Article 16** "Owner May Suspend Work … for a period of not more than 90 consecutive days" |
| `suspend operations for the winter` | 15 matches / **15 plans** | the identical **MnDOT 1803.4 "Temporary Suspensions"** sentence, verbatim, in all 15 |
| `carryover` / "next construction season" | 40 matches / **11 plans** | entirely **FHWA on-the-job-training** trainee carryover — zero relevance |
| `resume work` | 106 matches / **59 plans** | mostly EJCDC hazardous-environmental-condition clause |
| `Work Breakdown Structure` | — | MnDOT **Primavera** provision — the §3 false positive |

All six are now an explicit deny-list in `phasing.py::BOILERPLATE_PATTERNS`, and a coverage test
asserts each one **still occurs** in the corpus so a stale entry cannot silently stop excluding.

### 5.3 How many plans exhibit the real pattern?

**Single digits, and that is the correct answer.** Running the detector end-to-end over the 17
whole plan sets in `_md_cache`: **3 `break_and_resume`, 2 `sequenced_within_season`, 12
`none_found`.** Across `csi_v2.db`'s 100 plans the text signals reach 4–8 plans depending on
layer. Compare `has_phasing` at 57. A remobilization flag that fires on more than a third of plans
has been rebuilt into the thing it replaced, and there is a coverage test that fails on exactly that.

Notably, `_md_cache/9ff5dc83b09d4079` (Crow Wing MnDOT proposal) matches **both** `mndot_1803_4_winter`
and `wbs_scheduling_software` and correctly returns `none_found` — that is the false positive we
would otherwise have shipped.

---

## 6. Key dates 2, 3, 4 — what the corpus says about the shape

**Relative expressions are common and must survive verbatim.** Real values already in the payload
cache today:

> `2b2438a4eaaa0e79` p.47 — `final_completion` = "**within thirty (30) calendar days of substantial
> completion**"
> same plan p.47 — `substantial_completion` = "August 31, 2023, **or within 30 calendar days from
> the date on which on-site work is started, whichever is earlier**"
> `760e9a1dfd751c92` — "**thirty (30) calendar days have expired from the date the Engineer
> determines the Work to be substantially complete**"
> `f19c9df671fd2fd7` — "construction operations shall be **started on or after September 15th 2025**
> and be completed on or before October 17th, 2025"

Working/calendar-day counts appear in **16 of 17** `_md_cache` plans (213 matches), e.g.
"An additional **10 working days** shall be granted if the access road widening is awarded."

`phasing.py::date_expr` handles all of these:
- `raw` is **never** rewritten. A relative expression keeps its exact words and `kind="relative"`.
- `resolved` is filled only when the anchor is itself known; a **working**-day count is never
  resolved, because we do not own a state holiday calendar and guessing one is precisely the class
  of failure this project keeps repeating.
- **Four** `resolution_status` values, so `absent` (plan is silent) ≠ `unresolved_anchor_missing`
  (plan said it, we could not compute it) ≠ `unresolved_not_a_date` ≠ `resolved`. This is standing-
  rule instance #10 and it is asserted by a test.

---

## 7. Proposed `schema.py` text — for the main session to apply

Full text with rationale is in **`docs/_spec/2026-08-10-phasing-gotcha.md` §7**. Summary of the ask:

- **§7.1** — replace the `phasing_requirements` description so it asks for the *project's own*
  requirement and names the four boilerplate families to ignore (WBS/Primavera, EJCDC Milestone,
  EJCDC Article 16, MnDOT 1803.4). This is the one-line fix for the §3 false positive.
- **§7.2** — replace the `construction_start` description so a relative expression is returned **as
  written** instead of null. It fills at 33% today and the board flags this case by name.
- **§7.3** — **add two fields**, `interim_completion_dates` and `phase_break_interval` (both `rag`,
  `group="constraints"`, `doc="either"`).
- **§7.4** — add both new names to `FLAG_FIELD_FAMILY` under "Schedule & sequencing" and to the
  `flag_rows` field-flag loop.

Nothing else in `schema.py` is touched, and no quantity field is affected.

### The one-line plumbing fix, separate from the above

`apps/api/backend/report.py`, `identity_fields` (~l.220): add
`"phasing_requirements": record.get("phasing_requirements"),` and the same key to
`final_report.py::_payload_from_plan_id`'s `identity`. **Not applied** — task 4's owner is in the
extraction path and the main session owns report assembly. Without it, everything above stops at
the payload boundary.

---

## 8. What was built

| Path | What |
|---|---|
| `docs/_spec/2026-08-10-phasing-gotcha.md` | the spec — object shape, layer order, deny-list rationale, `schema.py` text |
| `pipelines/plan_reader/01_pipeline/phasing.py` | `date_expr` + layered detector + boilerplate deny-list |
| `pipelines/plan_reader/01_pipeline/test_phasing_coverage.py` | **39 coverage tests, all passing** |
| `pipelines/plan_reader/01_pipeline/taxonomy.py` | +2 codes (§4) |

**Naming deviation, declared:** `phasing.py` and `test_phasing_coverage.py` are **not**
date-prefixed. `2026-08-10-phasing` is not a legal Python identifier and these are imported by
name, matching every other module in `01_pipeline/`. Repo convention already reserves the date
prefix for standalone run-by-path scripts (`03_evaluation/2026-08-10_mapping_regression.py`). Every
non-importable artifact of this task is date-prefixed.

### The tests that earn their place

- `test_every_break_pattern_matches_real_corpus_text` — **each** pattern must match ≥1 real section
  in `csi_v2.db`. A pattern matching nothing fails. This is the test the working rules ask for.
- `test_every_boilerplate_pattern_still_occurs_in_the_corpus` — a dead deny-list entry is a silent
  hole; it stops excluding and nothing says so.
- `test_detector_runs_over_whole_plan_sets_and_finds_the_break_plans` — end-to-end over 17 plan
  sets, asserts non-zero **and** bounded above (rebuilding a 57%-base-rate flag fails).
- `test_failure_and_empty_do_not_share_a_value` — `extraction_failed` ≠ `none_found`, asserted `!=`.
- `test_absent_and_unresolved_are_different_values` — same rule on the date carrier.
- `test_wbs_prose_is_rejected_as_phasing_narrative` — the exact Watonwan string from §3.

Run: `python3 -m pytest pipelines/plan_reader/01_pipeline/test_phasing_coverage.py -q` → **39 passed**.
Note the repo `.venv` interpreter **cannot** open `csi_v2.db` (it is a symlink into iCloud;
`sqlite3.OperationalError: unable to open database file`) and errors 14 of them rather than
skipping. Under `python3` all 39 pass. Flagged, not fixed — it is an interpreter/sandbox issue, not
a test issue.

---

## 9. Where this meets the other agents

- **Task 4 (bid date), other owner.** `bid_deadline` is entirely theirs. This work reads it and
  never writes it, and the phasing detector does not depend on it at all. **No file is edited by
  both.** The seam worth agreeing on is `DateExpr` (spec §4.1): if their parser emits
  `{raw, kind, resolved, resolution_status}`, every key date on the report shares one shape and one
  null-vs-failure convention. If they emit a bare string, nothing here breaks.
- **Main session.** Owns `schema.py`; §7 above is the entire ask. Also owns `report.py` assembly,
  where the one-line plumbing fix belongs.

---

## 10. Open, needs a human

1. **Is a six-week in-season break priced like an overwinter break?** The board says six weeks is
   typical; every real instance in this corpus is overwinter (8–9 months). Ask Alex. Until then both
   are `break_and_resume` and the interval is reported so he can tell them apart.
2. **`results.csv` and the 8 per-plan JSONs are stale** — three schema fields have no column. Either
   re-run the batch extractor or stop citing those artifacts as coverage. They currently make the
   corpus look better covered than it is.
3. **`csi_v2.db` has nowhere to store a date.** Out of scope here (board: no more bulk rewrites of
   `csi_v2.db`), but any corpus-wide date benchmark needs the benchmark table from P0 #1, not
   `plan_metrics`.
