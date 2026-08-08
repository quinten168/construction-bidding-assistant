# Session report 5 — 2026-08-07 · the pressure test found two more live bugs, both mine

Fifth and final report of the session. Companions: `_crosswalk-and-vision.md`, `_remap-run.md`,
`_coverage-test-and-milling.md`, `_two-quantity-pipelines.md`, `issues.md`.

---

## Lead: what did NOT happen

- **F2 rendering — NOT STARTED.** Blocked on a scope question (see `_two-quantity-pipelines.md` §4:
  the four gap states live in code the report path never calls).
- **Extraction schema v2 — NOT STARTED.**
- **Postgres was NOT republished** after tonight's last two fixes. `public.materials` currently holds
  `milling_sy = 2,826,995`; `csi_v2.db` now holds **3,021,338**. Republishing is on the
  never-without-asking list, and the one-time GO was for the earlier run.
- No cache-migration build, no mapping restructure.

## 1. Two disputes, both resolved by measurement

### Dispute A — agent M vs a figure I committed into the code. **M was right; so was I; the comment was sloppy.**

M measured 1,218,210 SY / 17 plans for `MILL BITUMINOUS`. My committed comment said "1,346,886 SY
across 18 plans." Re-measured, both are real but they count different sets:

| set | quantity | plans |
|---|---:|---:|
| `MILL BITUMINOUS` only, **after** normalizing `\xa0` | 1,218,210 | 17 |
| `MILL BITUMINOUS` only, plain uppercase (misses the `\xa0` row) | 1,049,376 | 16 |
| any `MILL` or `COLD PLANE` | 2,122,223 | 36 |

My 1,346,886 was the wider set measured mid-fix and matches **neither** definition cleanly. The
comment has been corrected to quote both figures **with their definitions**, because a number
without its predicate is what caused the disagreement.

M's number is the better one — it caught the 168,834 SY hiding behind a non-breaking space that my
plain-uppercase query missed. That miss was itself a symptom of dispute B.

### Dispute B — **CONFIRMED. A live bug in code I wrote today.**

`spec_category()` and `_csi_ruling()` used a bare `.upper()`, while the material lookup table and
`11_build_material_map.py` both use a normalizing form. **115 real corpus rows contain a
non-breaking space.** Five of CSI's 2026-08-07 rulings were being silently bypassed:

| corpus description | should be | actually was |
|---|---|---|
| `Mill\xa0Bituminous\xa0Surfacing\xa01.5" (P)` — **168,834 SY** | milling | **hot mix** |
| `REMOVE BITUMINOUS␣␣PAVEMENT` (double space) — 15,067 SY | milling | **hot mix** |
| `REMOVE BITUMINOUS␣␣DRIVEWAY\xa0PAVEMENT` | excluded | hot mix |
| `Full\xa0Depth\xa0Reclamation (P)` — 10,182 SY | base / milling_sy | unmatched |
| `8"\xa0Concrete Valley Gutter` | excluded | unmatched |

Same failure class as Stearns — a mill/removal item landing in `hma` — reintroduced through a text
gap instead of a keyword-ordering gap. **I wrote the ruling layer this evening and it did not fire on
the largest single milling row in the corpus.**

Fixed: `normalize_description()` folds the same typographic characters and collapses whitespace, and
all three call sites route through it. A test asserts our normalizer agrees with
`08_material_universe.normalize` character-for-character, so the two artifacts cannot drift again.

## 2. A THIRD instance, found while verifying the fix

After the normalization fix, milling rose far less than the 168,834 SY it should have. Cause:

```
_normalize_unit("Square Yard")  ->  "SQUAREYARD"   # matched no known form
_normalize_unit("SQ YD")        ->  "SY"           # fine
```

The bridge accepted `SY / S Y / SQ YD / SQYD / SYD` but not the spelled-out `Square Yard`, so
**179,016 SY of correctly-categorised milling was still dropped** — this time by the unit guard
rather than the description matcher. `Cubic Yard` had the same gap.

Fixed, with a table-driven test over every unit spelling that appears in the corpus.

**Three defects in one day with an identical shape:** a value obviously right to a human, unrecognised
by a matcher, silently producing a zero rather than an error. The keyword typo (`RECLAIM`), the
description text (`\xa0`), and now the unit spelling (`Square Yard`). CLAUDE.md's rule — *never let a
failure and a legitimate empty answer share a return value* — describes all three exactly.

## 3. Final corpus numbers

| bucket | start of day | final | change |
|---|---:|---:|---:|
| **`milling_sy`** | **542,262** | **3,021,338** | **+2,479,076 (5.6×)** |
| `base_tons` | 1,008,322 | 832,381 | −175,941 |
| `shoulder_tons` | 47,211 | 57,173 | +9,962 |
| `grading_quantity` | 2,137,441 | 2,140,330 | +2,889 |
| `hot_mix_tons` | 1,150,328 | 1,146,413 | −3,915 |

`integrity_check ok`. **92 tests pass**, 1 xfailed (the pinned known-broken keywords).

Four independent defects produced the milling correction: the `RECLAIM` typo (FDR), `MILL
BITUMINOUS` losing to `BITUMINOUS`, the `\xa0` normalization gap, and the `Square Yard` unit gap.

## 4. From the mapping pressure test — the numbers that change the L1/L2 decision

The full analysis is in `docs/_spec/mapping_architecture.md`. Three findings that matter most:

**The 100% lookup coverage is training-set recall and should not be used.** A leave-one-plan-out test
gives the real number: **44.0% row coverage on an unseen plan** (50.5% if `state` is dropped from the
key), and 41–74% of quantity by unit. T's decision rule — *"90% means the heuristic sees only the
tail; 40% means it is doing real work"* — lands on **doing real work**. A Montana plan is the extreme:
0/30 lookup coverage, so `SPEC_MAP` is 100% of the answer there.

**SPEC_MAP's 40.7% row coverage is 83–99% of the quantity in the three bucket-feeding units** (SY
83.8%, TON 92.8%, CY 99.6%). Row-count coverage badly understates it; the misses are EA/LF small
items that can never reach a bucket.

**The disagreement matrix: 491 genuine disagreements of 1,633 comparable rows (30.1%).** Broken out
by source — `llm` 51.8%, `removal_rule` 32.4%, **`keyword` 3.8%**. The keyword agreement is circular
(those rows were seeded from SPEC_MAP) and worth nothing as evidence. But the **26 keyword rows that
DO disagree are the most valuable finding**: 22 are `MILL BITUMINOUS` rows still labelled `hma` —
**the lookup table is still carrying the full Stearns bug**, a fossil of a fix that never propagated.

On the top-20 by quantity: SPEC_MAP wins 14, the lookup wins 6, and the pattern is clean — *SPEC_MAP
wins wherever a 2026-08-07 fix or ruling landed; the lookup wins wherever the corpus contains
vocabulary SPEC_MAP has never heard of* (Montana `PLANT MIX` 24,069 TON, SD `SHOT ROCK`, and the
misspelled `GRAUNULAR MATERIAL` — a keyword list cannot fix typos, which is itself an argument for
keeping the lookup layer).

**On "verb before noun as a rule": the pressure test recommends AGAINST the general form.** Tested
against the corpus, it changes 274 rows and **breaks 8 real cases** — it destroys the `stockpile`
bucket (`SALVAGE AND STOCKPILE` → grading), reclassifies `REMOVE & RESET DELINEATORS` as earthwork,
turns 7,350 CY of `REMOVE AND REPLACE RIPRAP` into grading, and makes `REMOVE MAILBOX` grading (140
rows of pollution). The narrow form — process verbs (`MILL`/`SAW`/`RECLAIM`) beating pavement-material
nouns only — catches all three historic six-figure bugs and breaks none of the eleven adversarial
cases, because `REMOVE`/`SALVAGE` are excluded.

## 5. Open for T

1. **Republish to Postgres?** `csi_v2.db` is 194,343 SY ahead of `public.materials`. Never-list item.
2. **F2 scope** — four states (needs the drop path to adopt the crosswalk) or two states (what the
   LLM path can produce today)?
3. **`material_crosswalk.csv` still carries the Stearns bug** on 22 rows. It is published to Postgres
   as a table. Rebuild it, or leave it until the L1/L2 decision?
4. **Everything is uncommitted** on one laptop — a 5.6× milling correction, 92 tests, five reports
   and two specs.
