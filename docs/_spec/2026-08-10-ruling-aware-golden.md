# Spec — reconciling the golden dataset with CSI's rulings

**2026-08-10 · Task 2c · Status: RECOMMENDATION, awaiting owner approval for the one edit in §7.**
Branch `2026-08-10-mapping-honesty`. Evidence report: `docs/_session/2026-08-10-golden-reconcile.md`.

---

## 1. The question

The golden `MILL SY` for plan `9786015.pdf` (contract 1630, Murray Co MN / Fulda) is **8,731**.
The report now produces **15,828**, which is correct under Alex's ruling #5
(`REMOVE BITUMINOUS PAVEMENT` moves from grading to milling). The benchmark scores that as a miss.

Two options were on the table:

- **(A) Edit the golden values the rulings changed.**
- **(B) Make the benchmark ruling-aware** — keep the raw plan/CSI value, record the ruling
  adjustment alongside it, score against both.

## 2. Recommendation: **(B), ruling-aware. Do not edit a single golden quantity.**

Three reasons, in descending order of force. The first two are measured, not argued.

### 2.1 A blanket ruling edit makes 2 of 8 affected golden values *worse* and 1 of them impossible

Applying the ruling delta to the golden mechanically produces this (full table in the report):

| contract | bucket | golden raw | ruling delta | golden if edited | extracted | raw verdict | edited verdict |
|---|---|---|---|---|---|---|---|
| 1630 Murray MN | milling_sy | 8,731 | +7,097 | 15,828 | 15,828 | miss | **HIT** |
| 1634 Cass MN | milling_sy | 116,072 | +114,708 | 230,780 | 230,780 | miss | **HIT** |
| 1659 Stearns MN | milling_sy | 70,263 | +70,167 | 140,430 | 140,430 | miss | **HIT** |
| 1635 Sherburne MN | milling_sy | 32,000 | +2,500 | 34,500 | 34,500 | HIT | HIT |
| 1648 Buffalo SD | base_tons | 804 | +335 | 1,139 | 335 | miss | miss |
| 1652 Koochiching MN | milling_sy | 300,253 | +12,480 | 312,733 | 118,237 | miss | miss |
| **1622 Day SD** | base_tons | 444 | +444 | **888** | 444 | **HIT** | **miss** |
| **1642 Morton ND** | base_tons | 170 | −378 | **−208** | 170 | **HIT** | **miss** |

`−208 TON of aggregate base` is not a quantity. It is the arithmetic telling us the premise is
wrong: the golden is not uniformly "pre-ruling". On Day and Morton, CSI's own spreadsheet already
records exactly what the post-ruling pipeline produces, so "adjusting" it breaks a true match.

### 2.2 The golden is the only artifact that can tell us a ruling changed practice — and it says four of them did

Four of the eight ruling-touched golden values equal the **pre-ruling** extraction **to the unit**:

```
1630 Murray      MILL SY  golden 8,731   == pre-ruling 8,731     (ruling #5 adds 7,097)
1634 Cass        MILL SY  golden 116,072 == pre-ruling 116,072   (rulings #5 + #9 add 114,708)
1635 Sherburne   MILL SY  golden 32,000  == pre-ruling 32,000    (ruling #5 adds 2,500)
1659 Stearns     MILL SY  golden 70,263  == pre-ruling 70,263    (ruling #9 adds 70,167)
```

Three of the eight equal the **post-ruling** extraction:

```
1622 Day SD      BASE TN  golden 444     == post-ruling 444.4    (ruling #7, GRAVEL SURFACING)
1642 Morton ND   BASE TN  golden 170     == post-ruling 170      (T's removal rule)
1648 Buffalo SD  BASE TN  golden 804     -- ruling #7 moves toward it (0 -> 335), does not close it
```

That is a real, checkable finding: **rulings #5/#6 and #9 change CSI's own recorded practice on
milling; ruling #7 and Mark's removal rule describe it.** The estimator who filled in `MILL SY =
8,731` for Fulda did not count `REMOVE BITUMINOUS PAVEMENT`, and did not count FDR on Stearns.
Editing the golden to 15,828 and 140,430 deletes the only evidence that this divergence exists,
and deletes the question that ought to be put to Alex.

### 2.3 Independence

A golden that is rewritten whenever we change a rule can never report that a rule is wrong. It
stops being ground truth and becomes a second copy of the crosswalk. `CONVERSION_REQUIRED` already
exists for exactly this reason — a known design gap must not be scored as an extraction failure —
and a ruling adjustment is the same shape of fact one layer up.

## 3. What "ruling-aware" means concretely

Three values are recorded per (plan, bucket), never two:

| field | meaning | source |
|---|---|---|
| `golden_quantity_raw` | what CSI / the bid schedule states. **Never edited by us.** | golden file |
| `ruling_delta` + `ruling_ids` | the quantity the rulings move into or out of this bucket, and which rulings did it | computed from our item rows |
| `golden_quantity_ruling_adjusted` | `raw + delta`. **Derived, never stored in the golden file.** | computed |

and the comparison carries a status that keeps every distinct fact distinct:

| status | meaning |
|---|---|
| `MATCH_RAW` | agrees with the raw golden; no ruling touches this bucket |
| `MATCH_RULING_ADJUSTED` | agrees only after the ruling adjustment — **correct behaviour under a rule CSI's own historical number predates** |
| `RULING_CONTRADICTS_GOLDEN` | the ruling moves us *away* from a golden the raw value already matched (Day, Morton) — a rule to re-confirm with CSI, not an extraction bug |
| `MISMATCH` | disagrees under both. A real extraction error. |
| `CONVERSION_REQUIRED` | **unchanged.** Units differ; out of `matched` and out of both denominators. |
| `GOLDEN_ABSENT` / `EXTRACTION_ABSENT` | distinct from each other and from a zero |

`MATCH_RAW` and `MATCH_RULING_ADJUSTED` are reported separately and never summed into one
"accuracy" number without the split being shown. A ruling-adjusted match is a weaker claim than a
raw match, because the adjustment is computed from **our own extracted item rows** — if we missed
an item, we also missed its contribution to the adjustment. That limitation is stated on the
artifact, not buried.

### The three-state property this must not collapse

`CONVERSION_REQUIRED` stays a third state alongside hit and miss, out of `matched` and out of both
denominators, exactly as `tools/golden/2026-08-10_golden_join.py` and
`docs/_spec/2026-08-10-benchmark-table.md` §5 define it. The ruling layer adds statuses; it removes
none, and it never reuses `CONVERSION_REQUIRED`'s value for a ruling fact.

## 4. Effect on the headline numbers — **none, in either direction**

Pooled precision 0.983 / recall 0.667 / 0.00% variance on all six bucketed items is an
**item-level** score: golden item quantity vs extracted item quantity, joined on the spec item
number. A ruling changes which *bucket* an item is summed into. It does not change the item's
quantity, so it cannot move precision, recall, or per-item variance.

Verified two ways:
1. Re-ran `tools/golden/2026-08-10_golden_join.py` on this branch: `0.983 / 0.667`, same four
   bucket rows at `0.00%`. Unchanged.
2. Scanned all 88 comparison rows through `quantity_crosswalk._csi_ruling`: exactly **2** rows are
   ruling-touched (`2104.504 REMOVE BITUMINOUS DRIVEWAY PAVEMENT`, Crow Wing;
   `2401.507 STRUCTURAL CONCRETE`, Watonwan). Both are `MATCH` with zero variance and both sit in
   `(unbucketed)` under either regime.

**So no headline number improves because we edited an answer key — because neither option touches
the numbers the headline is computed from.** The ruling question lives entirely in the
*bucket-level* golden (`golden_dataset.csv`, and Tier 3 year spreadsheets), which is a separate,
currently much weaker benchmark: `validate_quantities.py` scores 4/11 = 36% today, over 5 plans,
and none of those 5 is ruling-touched.

The bucket-level number that *would* move, if the join were widened to all 18 plans that have both
a golden row and extracted materials:

| | field comparisons | within 8% | accuracy |
|---|---|---|---|
| raw golden (option B, recommended) | 48 | 19 | **40%** |
| golden edited by ruling delta (option A) | 48 | 20 | **42%** |

**+2 points, and every point of it is answer-key editing.** Three plans flip to hit (Murray, Cass,
Stearns), two flip to miss (Day, Morton). If a bucket-level accuracy figure is presented on
Wednesday it must be the 40%, with the ruling split shown separately — not the 42%.

## 5. What gets built

| artifact | status |
|---|---|
| `tools/golden/2026-08-10_ruling_impact.py` | the analysis: computes per-bucket totals with rulings on and off, attributes every delta to a named ruling, joins to `golden_dataset.csv`, emits the statuses in §3 |
| `tools/golden/2026-08-10_ruling_impact.csv` | its output, one row per (contract, bucket) with a golden value or an extracted value |
| `tools/golden/2026-08-10_test_ruling_aware.py` | coverage test: every ruling-touched corpus row is attributed to a named ruling; the three `CONVERSION_REQUIRED` states survive; **`golden_dataset.csv`'s seven quantity columns are byte-identical to their committed values** |
| `pipelines/plan_reader/00_input/golden_dataset_dictionary.md` | a ruling-provenance section — the seven quantity columns are pre-ruling CSI practice where CSI filled them, and are **not** to be edited to track a ruling |

Nothing writes to Supabase. No DDL. `golden_dataset.csv` quantity values are not touched.

## 6. Extending it to the benchmark table

`scratch.extraction_benchmark` (`docs/_spec/2026-08-10-benchmark-table.md` §5, still unapplied)
needs three additive columns and two `comparison_status` values before it is loaded:

```sql
    ruling_delta        double precision,   -- NULL = no ruling touches this (plan, bucket)
    ruling_ids          text,               -- e.g. 'CSI#5' or 'CSI#5,CSI#9'
    ruling_basis        text CHECK (ruling_basis IN ('CSI_2026-08-07','T_2026-08-07')),
```
plus `'MATCH_RULING_ADJUSTED'` and `'RULING_CONTRADICTS_GOLDEN'` in the `comparison_status` CHECK,
and the scorecard view counting them on their own lines rather than folding them into `matched`.
`golden_quantity` keeps holding the **raw** value; the adjusted value is a view expression
(`golden_quantity + coalesce(ruling_delta,0)`), so it can never be mistaken for something a source
document stated.

## 7. The one thing that needs owner approval

Four golden `MILL SY` values equal the pre-ruling extraction exactly, and two golden `BASE TN`
values equal the post-ruling extraction exactly. **That is a question for Alex, not a decision for
us:** do rulings #5/#6/#9 apply retroactively to how CSI's historical `MILL SY` column was filled,
or are they a change of practice starting now? Both answers are defensible and they produce
different benchmarks. Until it is answered, the raw value stands and the divergence is recorded.

Nothing in §5 depends on that answer. The answer only decides whether
`RULING_CONTRADICTS_GOLDEN` rows are a rule to revisit or a spreadsheet to backfill.
