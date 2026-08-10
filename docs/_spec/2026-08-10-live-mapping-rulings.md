# Spec — CSI's rulings applied to the live mapping (the seven `schema.py` descriptions)

Date: 2026-08-10 · Status: **proposed, awaiting owner review** · Task board P0 #3

The live PDF-drop path derives every quantity from Claude being asked for the seven bucket totals
directly. The complete mapping is the seven field descriptions in
`pipelines/plan_reader/01_pipeline/schema.py`. That is the artifact CSI's rulings are missing from.
Verified in `docs/_session/2026-08-08_live-path-mapping.md` §1.

This spec is the old text, the proposed new text, and the ruling that justifies every clause.
**Nothing is deleted.** `crushing_tons` and `stockpile_tons` are untouched by design.

---

## Where the rulings come from

`pipelines/plan_reader/05_knowledge/quantity_crosswalk.py`:

- `CSI_RULINGS_2026_08_07` lines 185–202 — **Alex's 11**: 4 exclusions, 5 moves, 2 previously
  unassigned resolved.
- Lines 218–225 are **T's 8**, not Alex's — Mark's standing rule that pavement/base removal is
  grading work. Recorded separately here because they are a different authority.
- `CSI_DO_NOT_COUNT_2026_08_07` — 13 patterns that match nothing in `SPEC_MAP` today, so they move
  no number in the batch path. They *can* move a number in the live path, because an LLM matches on
  meaning rather than on a substring. Carried into the prose where relevant.

Alex's 11, verbatim:

| # | Item | Ruling |
|---|---|---|
| 1 | `REMOVE CONCRETE DRIVEWAY PAVEMENT` | do not count |
| 2 | `REMOVE BITUMINOUS DRIVEWAY PAVEMENT` | do not count |
| 3 | `CEMENT STABILIZED SUBGRADE` | do not count |
| 4 | `PORTLAND CEMENT` | do not count — binder/additive, not aggregate base |
| 5 | `REMOVE BITUMINOUS PAVEMENT` | grading → milling |
| 6 | `REMOVAL OF BITUMINOUS SURFACING` | grading → milling |
| 7 | `GRAVEL SURFACING` | shoulder → base |
| 8 | `TRAFFIC SERVICE AGGREGATE` | shoulder → base |
| 9 | `FULL DEPTH RECLAMATION` | base **work**; quantity stays SY in `milling_sy` |
| 10 | `SALVAGE AND REUSE EXISTING AGGREGATE` | unassigned → grading |
| 11 | `CLEAN ROCK` | unassigned → grading |

---

## The seven descriptions

### 1. `hot_mix_tons`

**Old:** `Total tons of hot mix asphalt (HMA) from the bid schedule.`

**Proposed:**

> Total tons of hot mix asphalt PLACED on this project. The three states write it differently and
> all three mean hot mix — count all of them: MN `BITUMINOUS MIXTURE` / `TYPE SP` (e.g.
> `SPWEA240B`), ND `SUPERPAVE` (including `RAP - SUPERPAVE FAA 43` — recycled hot mix, it counts),
> SD `ASPHALT CONCRETE`. Count wearing course, non-wearing course, leveling and patching mixtures.
> Do NOT count milling or removal of existing bituminous — that is `milling_sy`. Do NOT count
> aggregate.

**Justifying rulings:** #5, #6 (removal is not mix). State vocabulary is not a CSI ruling — it is
the fix for the 605× Dunn miss (`docs/_session/2026-08-08_dunn-extraction-failure.md`), where the
prompt said "HMA" and NDDOT writes `SUPERPAVE`. ND is 35.8% of CSI's bidding.

### 2. `base_tons`

**Old:** `Total tons of aggregate/granular base material.`

**Proposed:**

> Total tons of aggregate/granular base material PURCHASED AND PLACED — for example
> `AGGREGATE BASE CLASS 5 / 6 / 13`, `GRAVEL SURFACING`, `TRAFFIC SERVICE AGGREGATE`. Do NOT count
> `REMOVE AGGREGATE BASE` or `REMOVAL OF AGGREGATE BASE`: that is demolition of existing material,
> not aggregate bought for this job. Do NOT count `PORTLAND CEMENT` or `CEMENT STABILIZED SUBGRADE`
> — binder and additive, not aggregate. `FULL DEPTH RECLAMATION` is base work, but its quantity
> belongs in `milling_sy`, not here.

**Justifying rulings:** #4, #3, #7, #8, #9, plus T's removal rule. **This is the clause the Dunn
drop test checks** — 72,153 TON of `REMOVE AGGREGATE BASE` must not appear in `base_tons`.

The old text had no "placed"/"purchased" qualifier at all. That is the structural hole flagged in
`2026-08-08_live-path-mapping.md` §3: the crosswalk carried this exact bug for months.

### 3. `grading_quantity`

**Old:** `Total cubic yards of grading / earthwork.`

**Proposed:**

> Total cubic yards (CY) of grading / earthwork — common excavation, subgrade excavation,
> embankment, borrow. Also count `SALVAGE AND REUSE EXISTING AGGREGATE` and `CLEAN ROCK`. Pavement
> and base removal is grading work, so count it here WHEN the bid schedule measures it in cubic
> yards. When a removal is measured in square yards or tons, do NOT convert it and do NOT move it
> into another bucket — no verified depth or density factor exists, so leave it out of every total.

**Justifying rulings:** #10, #11, plus T's 8. Depth is stated on **0 of 41** corpus removal rows,
so no SY→CY conversion is possible; the crosswalk records this as `bucket_gap_reason =
no_bucket_for_unit` rather than as a zero.

### 4. `shoulder_tons`

**Old:** `Total tons of shoulder gravel/aggregate.`

**Proposed:**

> Total tons of shoulder aggregate, e.g. `AGGREGATE SHOULDERING`. `GRAVEL SURFACING` and
> `TRAFFIC SERVICE AGGREGATE` were moved to `base_tons` by CSI — do not count them here.
> `AGGREGATE SURFACING CLASS 1 / 2 / 5 / SPECIAL` is still counted here, pending a CSI ruling.

**Justifying rulings:** #7, #8. The Aggregate Surfacing clause preserves current behaviour and is
labelled as unresolved rather than silently assumed — 67,000 T is at stake and CSI has not answered.

### 5. `milling_sy`

**Old:** `Total square yards of milling / pavement removal.`

**Proposed:**

> Total square yards (SY) of milling and bituminous pavement removal: `MILL BITUMINOUS SURFACE`,
> `REMOVE BITUMINOUS PAVEMENT`, `REMOVAL OF BITUMINOUS SURFACING`, and `FULL DEPTH RECLAMATION`
> (CSI ruled FDR is base work, but its quantity is reported here because it is measured in SY).
> Do NOT count `REMOVE CONCRETE DRIVEWAY PAVEMENT` or `REMOVE BITUMINOUS DRIVEWAY PAVEMENT`. Do NOT
> count concrete pavement removal — that is grading. Report square yards only; if the bid schedule
> measures milling in tons, leave this field null rather than converting.

**Justifying rulings:** #1, #2, #5, #6, #9.

The old text said "milling / **pavement removal**" with no qualifier, which folds *all* removal into
milling and contradicts both `bucket_hierarchy.csv` and Mark's rule. Three artifacts, three answers;
the one that ships was never reviewed. This narrows it to bituminous.

### 6. `crushing_tons` — UNCHANGED

`Total tons of crushed aggregate to be produced.` CSI has not answered whether crushing stays
excluded (`CSI_OPEN_QUESTIONS_2026_08_07`). Not touched.

### 7. `stockpile_tons` — UNCHANGED

`Total tons of stockpile material.` Same reason.

---

## Open, and NOT encoded — owner decision needed

These are places where writing a clause would mean inventing a CSI decision. Current behaviour is
preserved and the gap is named instead.

1. **ND measures milling in TONS** (230,625 T corpus-wide). The proposed `milling_sy` text says
   "leave null rather than converting". That is safe but it is silent data loss, and silence is the
   failure mode this project has been bitten by nine times. The alternatives are a separate
   `milling_tons` field, or emitting a gotcha. **This is board open item #2 and I did not decide
   it.** If you want the null, it ships as written; if you want a field, say so and it is a schema
   addition, not a prose change.
2. **PG binder / tack / prime** (56,029 T). Pre-read question 7 *proposed* excluding them from
   `Mixed_tons` to avoid a double count. Proposed ≠ ruled, so no clause was written. The prompt is
   silent today and stays silent.
3. **Riprap classification** — open per `CSI_OPEN_QUESTIONS_2026_08_07`. No clause.
4. **`AGGREGATE SURFACING CLASS 1 / 2 / 5 / SPECIAL`** — 67,000 T sitting in `shldr_tons` on a
   keyword guess. Preserved, labelled, not decided.

---

## How this is proved — no-regression harness

The mapping is a prompt, so a unit test proves nothing about it. The proof is a **differential
re-run**: the same documents through the same extractor, once with the old descriptions and once
with the new, diffing the seven totals.

- Corpus: `pipelines/plan_reader/00_input/_md_cache/` — 17 already-converted plans with page-level
  markdown. No PDF re-conversion and no new API dependency.
- Both arms run in the same harness at `temperature=0` (already pinned in `s3_extract.py:135`), so
  a difference is attributable to the prose and not to sampling.
- Harness: `pipelines/plan_reader/03_evaluation/2026-08-10_mapping_regression.py`.
- Pass condition: **no plan's total moves in a direction the rulings do not explain.** A move that
  a ruling predicts (removal leaving `base_tons`, FDR arriving in `milling_sy`) is the point of the
  change, not a regression. Every diff is classified, and an unclassified diff fails the run.
- Failure and empty are kept distinct: a document that errors is recorded as `ERROR` and never as
  a zero or a null total.

Baseline agreement to preserve, from `2026-08-08_live-path-mapping.md` §4: Walsh 4/4 exact, Dunn
CP-13 3/3 exact, Stearns `MILL = 70,263` exact to the square yard.

## Dunn drop test

Separately open, and it is the single test that decides whether the live path has a seventh defect:
does 72,153 TON of `REMOVE AGGREGATE BASE` on `2026_DUNN-CO-ND_JOB-23388` land in `base_tons`?
No cached payload covers a plan containing `REMOVE AGGREGATE BASE`, so this needs the PDF dropped
through the live path. Run before and after the change; the answer must go from whatever it is today
to zero.
