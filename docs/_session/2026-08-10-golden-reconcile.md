# Golden ↔ rulings reconciliation

**2026-08-10 · Task 2c · branch `2026-08-10-mapping-honesty`.**
Decision spec: `docs/_spec/2026-08-10-ruling-aware-golden.md`. Nothing was written to Supabase, no
DDL was run, and **no golden quantity was edited.**

---

## 1. Recommendation — ruling-aware benchmark. Do not edit the golden.

The choice was **not** close, and the arithmetic is what decided it rather than the principle.

**A blanket "update the golden for the rulings" edit makes 2 of the 8 affected values worse and
produces one value that cannot exist.** On contract 1642 (Morton Co ND), applying the ruling delta
to the golden `BASE TN` of 170 gives **−208 tons of aggregate base**. On 1622 (Day Co SD) it turns a
true match into a miss. The premise that the golden is uniformly "pre-ruling" is false: it is
pre-ruling on milling and already post-ruling on base.

The principle then reinforces it. A golden that is rewritten whenever we change a rule can never
report that a rule is wrong — and in this corpus it is already reporting something worth hearing
(§3).

## 2. Every golden value a ruling moves — 11 rows, 8 with a golden quantity

Produced by `tools/golden/2026-08-10_ruling_impact.py` (full CSV:
`tools/golden/2026-08-10_ruling_impact.csv`, 74 rows). `pre-ruling` is the same extraction with
`CSI_RULINGS_2026_08_07` and `CSI_DO_NOT_COUNT_2026_08_07` emptied — measured, not reconstructed
by hand, so it cannot drift from the rulings that ship.

| contract | plan | bucket | golden (raw) | ruling | delta | golden if edited | extracted **now** | extraction **pre-ruling** | status |
|---|---|---|---|---|---|---|---|---|---|
| 1630 | `2025_MURRAY-CO-MN_CSAH-2_NOBID` (`9786015.pdf`) | `milling_sy` | **8,731** | CSI#5 | +7,097 | 15,828 | **15,828** | 8,731 | `MATCH_RULING_ADJUSTED` |
| 1634 | `2025_CASS-CO-MN_SAP-011-636-007_NOBID` | `milling_sy` | **116,072** | CSI#5, CSI#9 | +114,708 | 230,780 | **230,780** | 116,072 | `MATCH_RULING_ADJUSTED` |
| 1659 | `2025_STEARNS-CO-MN_CP-073-123_NOBID` | `milling_sy` | **70,263** | CSI#9 | +70,167 | 140,430 | **140,430** | 70,263 | `MATCH_RULING_ADJUSTED` |
| 1635 | `2025_SHERBURNE-CO-MN_9747843_NOBID` | `milling_sy` | **32,000** | CSI#5 | +2,500 | 34,500 | **34,500** | 32,000 | `MATCH_RAW` (7.8%, inside the 8% band both ways) |
| 1622 | `2025_DAY-CO-SD_PCN-09GX_NOBID` | `base_tons` | **444** | CSI#7 | +444.4 | 888.4 | **444.4** | — | ⚠ `RULING_CONTRADICTS_GOLDEN` |
| 1622 | " | `shoulder_tons` | — | CSI#7 | −444.4 | — | — | 444.4 | `BOTH_ABSENT` (CSI left `SHLDR TN` blank) |
| 1642 | `2025_MORTON-CO-ND_JOB-24133_NOBID` | `base_tons` | **170** | T#removal | −378 | **−208** | **170** | 548 | ⚠ `RULING_CONTRADICTS_GOLDEN` |
| 1642 | " | `milling_sy` | — | CSI#6 | +152 | — | 152 | — | `GOLDEN_ABSENT` |
| 1648 | `2025_BUFFALO-CO-SD_9809453_NOBID` | `base_tons` | **804** | CSI#7 | +335 | 1,139 | **335** | — | `MISMATCH` both ways |
| 1648 | " | `shoulder_tons` | — | CSI#7 | −335 | — | — | 335 | `BOTH_ABSENT` |
| 1652 | `2025_KOOCHICHING-CO-MN_SAP-036-624-026_NOBID` | `milling_sy` | **300,253** | CSI#9 | +12,480 | 312,733 | **118,237** | 105,757 | `MISMATCH` both ways (a recall failure, not a ruling one) |

Ruling ids follow `docs/_spec/2026-08-10-live-mapping-rulings.md`: **CSI#5** `REMOVE BITUMINOUS
PAVEMENT` → milling · **CSI#6** `REMOVAL OF BITUMINOUS SURFACING` → milling · **CSI#7**
`GRAVEL SURFACING` shoulder → base · **CSI#9** `FULL DEPTH RECLAMATION`, quantity stays in
`milling_sy` · **T#removal** Mark's rule, removal = grading work (a *different authority* from
Alex's 11, and the tool labels it as such).

The item rows behind each delta, verbatim from `materials`:

```
1630  Remove Bituminous Pavement                  SY    7,097   CSI#5
1634  REMOVE BITUMINOUS PAVEMENT                  SY      506   CSI#5
1634  FULL DEPTH RECLAMATION                      SY  114,202   CSI#9
1659  FULL DEPTH RECLAMATION                      S Y  70,167   CSI#9
1635  REMOVE BITUMINOUS PAVEMENT (ROAD)           SY    2,500   CSI#5
1652  FULL DEPTH RECLAMATION (10")             SQ YD   12,480   CSI#9
1622  Gravel Surfacing                           Ton    444.4   CSI#7   (shoulder -> base)
1648  Gravel Surfacing                           Ton      335   CSI#7   (shoulder -> base)
1642  REMOVE AGGREGATE BASE                      TON      378   T#removal (base -> nowhere)
1642  REMOVAL OF BITUMINOUS SURFACING             SY      152   CSI#6
```

Two further ruling-touched plans have no golden row to move and are listed for completeness:
`2025_KANDIYOHI-CO-MN_9353968_NOBID` (CSI#5, 19,926 + 125 SY — golden ambiguous, two Kandiyohi
lettings and two plans) and `2025_STEARNS-CO-MN_SAP-073-590-007_NOBID` (no extracted materials).

## 3. The finding this whole exercise exists to preserve

Line up the golden against **both** regimes and it separates cleanly:

**Four golden `MILL SY` values equal the PRE-ruling extraction to the unit** — 1630 (8,731),
1634 (116,072), 1635 (32,000), 1659 (70,263). Not approximately. Exactly.

**Two golden `BASE TN` values equal the POST-ruling extraction to the unit** — 1622 (444) and
1642 (170); a third, 1648, moves toward it without closing.

> **Alex's rulings #5/#6 and #9 do not describe how CSI's own `MILL SY` column was filled — they
> change it. Ruling #7 and Mark's removal rule describe it exactly.**

The estimator who wrote `MILL SY = 8,731` for Fulda did not count `REMOVE BITUMINOUS PAVEMENT`, and
the one who wrote 70,263 for Stearns did not count FDR. Editing those four cells to 15,828 /
230,780 / 34,500 / 140,430 deletes the only evidence this divergence exists — and deletes the
question that belongs in front of Alex before Wednesday:

> *Do rulings #5/#6/#9 apply retroactively to the historical `MILL SY` column, or are they a change
> of practice from 2026-08-07 forward?*

Both answers are defensible. Until it is answered the raw value stands, the divergence is recorded,
and no number is quietly rewritten. That question is the deliverable here, not the 8,731.

## 4. Effect on the headline: **0.983 / 0.667 / 0.00% — unchanged, in both directions**

The headline is **item-level**: golden item quantity vs extracted item quantity, joined on the spec
item number (`tools/golden/2026-08-10_golden_join.py`). A ruling changes which **bucket** an item is
summed into; it does not change the item's quantity. So it cannot move precision, recall, or
per-item variance. Verified two ways, both named:

1. **Re-ran the join on this branch.** `pooled recall=0.667 (58/87) precision=0.983 (58/59)`,
   `conversion_required=0`; `base_tons` / `grading_quantity` / `hot_mix_tons` / `shoulder_tons` all
   still `0.00%` variance. Byte-identical to the figures in the inventory report.
2. **Scanned all 88 comparison rows through `quantity_crosswalk._csi_ruling`.** Exactly **two** are
   ruling-touched — `2104.504 REMOVE BITUMINOUS DRIVEWAY PAVEMENT` (Crow Wing, CSI#2) and
   `2401.507 STRUCTURAL CONCRETE` (Watonwan, do-not-count). Both are `MATCH` with **zero** variance
   and both sit in `(unbucketed)` under either regime, so neither the score nor the per-bucket table
   moves.

**No headline number improves because we edited an answer key — because neither option touches the
values the headline is computed from.** That claim is safe to make on Wednesday.

### The bucket-level number, which *is* ruling-sensitive

The rulings live entirely in the **bucket-level** golden (`golden_dataset.csv` and the Tier-3 year
spreadsheets). That benchmark is much weaker today: `03_evaluation/validate_quantities.py` scores
**4/11 = 36%** across 5 plans, because it requires a non-empty `source_file` and only 11 of 43 rows
have one. **None of those 5 plans is ruling-touched, so today's 36% is unaffected either way.**

Widening the join to all 18 contracts that have both a golden row and extracted materials
(explicit `contract_id`, unique state+county+year, or evidence — never fuzzy; 10 contracts are
emitted as `AMBIGUOUS_COUNTY` rather than guessed):

| answer key | comparisons | within ±8% | accuracy |
|---|---|---|---|
| **raw golden** (recommended) | 48 | 19 | **40%** |
| golden edited by the ruling delta | 48 | 20 | **42%** |

**+2 points, and 100% of it is answer-key editing** — three flip to hit (1630, 1634, 1659), two flip
to miss (1622, 1642). If a bucket-level figure is shown Wednesday it must be **40%**, with the
ruling split beside it. The tool prints both, labels the second `ANSWER KEY EDITED`, and prints the
warning unconditionally so the number cannot be quoted out of context.

## 5. `CONVERSION_REQUIRED` and the three-state property — preserved and now tested

Nothing was removed. `CONVERSION_REQUIRED` remains its own status, out of `matched` and out of
**both** denominators, at item grain (`2026-08-10_golden_join.py`) and now at bucket grain too. The
ruling layer only **adds** statuses, and a ruling-adjusted value is distinguishable from a raw one
by construction: the raw value stays in the golden file and the adjusted value is only ever
computed, so it can never be mistaken for something a source document stated.

`tools/golden/2026-08-10_test_ruling_aware.py` (coverage, over the real corpus — 6,385 `materials`
rows, 43 golden rows, 74 output rows) asserts:

1. all seven golden quantity columns are **byte-identical to the committed version** — a later
   "just fix the golden" commit fails this test rather than passing silently;
2. every one of the 39 corpus item rows the rulings move is attributed to a **named** ruling id and
   a named authority (`CSI_2026-08-07` vs `T_2026-08-07`);
3. raw and adjusted are both present and never rendered identically on a ruling-touched row;
4. `CONVERSION_REQUIRED` still fires and **no ruling status reuses its value** — three states, not
   two;
5. `GOLDEN_ABSENT` / `EXTRACTION_ABSENT` / `BOTH_ABSENT` are three distinct statuses, and an empty
   golden cell parses to `None`, never to `0`;
6. the ruling lists are restored, so the tool cannot leave `quantity_crosswalk` mutated.

**The test earned its place on the first run.** It failed check 2: `ruling_for()` reads the live
ruling lists, and `moved_items()` was calling it *after* emptying them, so every `ruling_ids` cell
shipped blank while the deltas looked perfectly correct. Same signature as the four defects fixed on
2026-08-07 — a matcher handed an empty input and returning "no match" indistinguishably from "no
ruling". Fixed by capturing attribution in the rulings-on pass.

## 6. Limitation, stated rather than buried

The ruling delta is computed from **our own extracted item rows**. If extraction missed an item, it
also missed that item's contribution to the adjustment — so `MATCH_RULING_ADJUSTED` is a **weaker**
claim than `MATCH_RAW`, and the two are never summed into a single accuracy figure. Contract 1652
shows the shape: its `milling_sy` gap (300,253 golden vs 118,237) is a recall failure that the
+12,480 FDR adjustment barely touches.

## 7. Artifacts

| path | what |
|---|---|
| `docs/_spec/2026-08-10-ruling-aware-golden.md` | the recommendation, the statuses, and the three additive columns `scratch.extraction_benchmark` needs before it is loaded |
| `tools/golden/2026-08-10_ruling_impact.py` | the reconciliation; read-only SQLite, one local CSV, exits non-zero if no golden value is ruling-touched |
| `tools/golden/2026-08-10_ruling_impact.csv` | 74 rows, one per (contract, bucket) with a golden or extracted value |
| `tools/golden/2026-08-10_test_ruling_aware.py` | the coverage test above |
| `pipelines/plan_reader/00_input/golden_dataset_dictionary.md` | new §"The seven quantity columns are NOT to be edited to track a CSI ruling" |

**`pipelines/plan_reader/00_input/golden_dataset.csv` is unchanged.**

## 8. Open, for the owner

1. **§3's question to Alex** — retroactive, or change of practice from 2026-08-07? Nothing built
   here depends on the answer; it only decides whether `RULING_CONTRADICTS_GOLDEN` means "revisit
   the rule" or "backfill the spreadsheet".
2. **`golden_dataset.csv`'s `source_file` is blank on 32 of 43 rows**, which is the only reason
   `validate_quantities.py` scores 5 plans instead of 18. Filling it is a pure-coverage change with
   no decision in it, but it *will* move the 36% figure, so it should not land the day before a
   presentation without being called out.
3. **10 contracts are `AMBIGUOUS_COUNTY`** (Hand SD ×2, Kandiyohi MN ×2, Stearns 1639, and five
   states with no extracted 2025 plan). Resolving them needs a letting-date or project-number join,
   not a guess.
