# 2026-08-11 — Alex conformance audit, layer 2: do the rulings FIRE on the live path?

Branch `2026-08-10-mapping-honesty`. **Measurement only. Nothing was patched.** `schema.py` was
byte-identical (`sha256 239ed041…`) before the first run and after the last, and clean in
`git status` throughout, so every arm below shares one field set. Repo HEAD `90745a9`.

Layer 1 (a parallel agent) owns whether a ruling is **ENCODED** in the prose. This owns whether the
shipped extractor **puts the material where Alex said**. Encoded and firing are different questions
and this pass found a case where the answer differs: `TRAFFIC SERVICE AGGREGATE` is encoded
correctly, the model quotes the ruling back verbatim, and the number still does not move.

Harness: `pipelines/plan_reader/03_evaluation/2026-08-11_alex_conformance_behavior.py`
Raw data: `03_evaluation/outputs/2026-08-11_alex_behavior_*.json`,
`outputs/2026-08-11_alex_inventory.json`.

**Live-path input, not a whole-document harness.** `build_input` is imported from
`2026-08-10_nondeterminism_measurement.py`, so the extractor input is built through the shipped
chain — `lib.detect_structure` → `s1_convert.convert_pages` → `pages_to_markdown` restricted to
`structure["proposal_pages"]` → `s3_extract.smart_truncate(180,000)` — built **once** per plan,
hashed, and reused for all N runs. **`process_pdf` was never called. Chroma was touched zero times.
No Supabase, no DDL, no golden edit, no `crushing_tons`/`stockpile_tons` work.**

**39 extraction calls, 39 OK, 0 ERROR.** A parse failure would have been `status=ERROR` with
`values=None` and excluded from every rate; there were none, so no rate below is contaminated by
one.

---

## 0. Two findings to read before the table

### 0a. The tolerant matcher's zero is not an absence — it cost two false `untested-no-plan`s

The first pass of the inventory reported `REMOVE CONCRETE DRIVEWAY PAVEMENT` and
`REMOVE BITUMINOUS DRIVEWAY PAVEMENT` as matching **zero** corpus lines. Both are priced bid items
in the cache. The matcher inherited from `test_material_vocabulary_coverage.py` allows up to 12
non-alphanumeric characters between words; Stearns 9813645 p77 prints

```
|~~4 ~~<br><br>|~~2104.504/00080~~<br><br>|~~REMOVE CONCRETE~~<br>DRIVEWAY PAVEMENT<br><br>|~~S Y~~<br><br>|~~44~~<br><br>|||
```

— **15** characters of markup between `CONCRETE` and `DRIVEWAY`. The fix in this harness strips
`<br>`/`~~`/`**`/`|`/`_` **before** matching (`_denoise`). This is the standing rule's own shape: a
negative from a fixed-tolerance check is not proof of absence. **The same 12-char matcher is live in
`01_pipeline/test_material_vocabulary_coverage.py` and will under-report there too** — not fixed
here (measure-only), flagged for whoever owns that file.

### 0b. A wording mismatch this audit cannot settle

The task lists the FDR ruling as **"Full Depth Reclamation → base"**. What ships splits it: the
`base_tons` description says *"'FULL DEPTH RECLAMATION' is base work, but its quantity belongs in
`milling_sy`, not here"*, and `milling_sy` carries the SY. Everything below is measured against the
**shipped** target (`milling_sy`), which is what `docs/_session/2026-08-10-ruling9-and-cl13.md`
records CSI ruling #9 as saying. If Alex meant the *quantity* to land under base, then FDR is wrong
on every plan in the corpus, including Dunn's 408,216 SY. **Escalate; do not resolve in code.**

---

## 1. Material → plan inventory (step 1, cost: zero API calls)

18 cached plans (`00_input/_md_cache/*.json`, `*.hybrid.json` skipped), 156,214 non-blank lines.
"Pay item" means a **priced bid-schedule row** — a unit and a quantity — as opposed to the same
words in specification prose. That distinction is the whole value of this step: three rulings have
plenty of prose mentions and **no priced item anywhere in the cache**, so there is nothing for them
to move and inventing a test would have manufactured a result.

| ruling | material | priced pay item found? | plan(s) · page · verbatim line |
|---|---|---|---|
| R-FDR | FULL DEPTH RECLAMATION | **yes, 3 plans** | Dunn Job 23388 p13 `\|**046**\|**306**\|**0510**\|**FULL DEPTH RECLAMATION**\|**SY**\|**408,216.**` · Stearns 9813645 p77 `\|~~13~~\|~~2215.504/00010~~\|~~FULL DEPTH~~<br>RECLAMATION\|~~S Y~~\|~~70167~~` · White Shield 8370470 p25 `20 306.0510 Full Depth Reclamation SY 3650` |
| R-GRAVSURF | GRAVEL SURFACING | **no** — 39 lines on 7 plans, all prose | 9804001 p239 is a CAD title block; 8428114 p218 `Type A3: Class 13 (gravel surfacing)` is a materials spec; Dunn p242 `temporary bypass or gravel surface`. No priced row. |
| R-TSA | TRAFFIC SERVICE AGGREGATE | **yes, 1 plan** | Dunn Job 23388 p13 `\|**043**\|**302**\|**0050**\|**TRAFFIC SERVICE AGGREGATE**\|**TON**\|**820.**` |
| R-RBP | REMOVE BITUMINOUS PAVEMENT | **yes, 3 plans** | 9786015 (DEMO) p26 `\|7\|Remove Bituminous Pavement\|SY\|<br>7,097` · Crow Wing p220 `\|14\|2104.504\|REMOVE BITUMINOUS <br>PAVEMENT\|S Y\|15067` · 187bbb4f (MN SP 2905-39) p359 `\|6\|2104.504\|REMOVE BITUMINOUS PAVEMENT<br>(P)\|SQ YD\|2978` |
| R-ROBS | REMOVAL OF BITUMINOUS SURFACING | **yes, 2 plans** | Job 24133 p7 `\|**005**\|**202**\|**0132**\|**REMOVAL OF BITUMINOUS SURFACING**\|**SY**\|**152.**` · Dunn p7 `\|**011**\|**202**\|**0135**\|…\|**TON**\|**3,915.**` |
| X-PC | PORTLAND CEMENT | **yes, 1 plan** | Dunn p13 `\|**048**\|**320**\|**0200**\|**PORTLAND CEMENT**\|**TON**\|**8,175.**` |
| X-CSS | CEMENT STABILIZED SUBGRADE | **yes, 1 plan** | 9786015 (DEMO) p27 `\|42\|12" Cement Stabilized Subgrade (CV) (P)\|SY\|<br>1,566` |
| X-RCDP | REMOVE CONCRETE DRIVEWAY PAVEMENT | **yes, 1 plan** (missed on pass 1, see §0a) | Stearns 9813645 p77 `\|~~4 ~~\|~~2104.504/00080~~\|~~REMOVE CONCRETE~~<br>DRIVEWAY PAVEMENT\|~~S Y~~\|~~44~~` |
| X-RBDP | REMOVE BITUMINOUS DRIVEWAY PAVEMENT | **yes, 1 plan** (missed on pass 1) | Crow Wing p220 `\|13\|2104.504\|REMOVE BITUMINOUS <br>DRIVEWAY PAVEMENT\|S Y\|326` |
| X-RDP | REMOVE DRIVEWAY PAVEMENT (the corpus's unqualified spelling) | **yes, 1 plan** | 9786015 (DEMO) p26 `\|8\|Remove Driveway Pavement\|SY\|<br>236` |
| C-SURF13 | AGGREGATE SURFACE COURSE CL 13 | **yes, 1 plan** | Job 24133 p8 `\|**018**\|**302**\|**0356**\|**AGGREGATE SURFACE COURSE CL 13**\|**TON**\|**170.**` |
| C-BASE13 | AGGREGATE BASE CL 13 | **no** — 2 lines, both a fuel/price-adjustment table | Job 24133 p17 and Dunn p48, both `\|100\|9954\|302.04 B\|Aggregate Base and Surface Course\|Aggregate Base CL 13\|$40.00 per Ton1\|` — a price index row, no quantity |
| U-SALV | SALVAGE AND REUSE EXISTING AGGREGATE | **yes, 1 plan** | White Shield 8370470 p25 `22 302.0121 Salvage and Reuse Existing Aggregate CY 1000` |
| U-CLEANROCK | CLEAN ROCK | **yes, 1 plan** | Dunn p13 `\|**045**\|**302**\|**2000**\|**CLEAN ROCK**\|**TON**\|**758.**` |
| U-GRANBED | GRANULAR BEDDING | **no** — 12 lines on 7 plans, all prose/gradation-testing tables | 9809481 p56 `All costs of granular bedding and encasement of sewer pipe shall be incidental.` |
| U-FDBSR | FULL DEPTH BITUMINOUS STREET REPAIR | **no** — zero lines, exact or alias | — |

**The inventory is the coverage test.** `--inventory` names every ruling whose material matched zero
corpus lines, and that list is reproduced verbatim in §3 rather than quietly omitted.

---

## 2. Behavior table — worst first

Worst = largest quantity at stake × most likely to be on screen Wednesday. Firing rate is over
**parseable** runs; every arm here was 39/39 OK.

Three outcomes, never two: **FIRES** (in Alex's bucket) · **MISPLACED** (in a different bucket,
named) · **DROPPED** (in no bucket — the silent-failure case).

| # | ruling | Alex's target | status | rate (n/N) | plan | verbatim line · page |
|---|---|---|---|---|---|---|
| 1 | **R-TSA** Traffic Service Aggregate | `base_tons` | **DOES NOT FIRE — DROPPED** | **0 / 23** | Dunn Job 23388 | `\|**043**\|**302**\|**0050**\|**TRAFFIC SERVICE AGGREGATE**\|**TON**\|**820.**` p13 |
| 2 | **U-CLEANROCK** Clean Rock | `grading_quantity` | **DOES NOT FIRE — DROPPED** | **0 / 13** | Dunn Job 23388 | `\|**045**\|**302**\|**2000**\|**CLEAN ROCK**\|**TON**\|**758.**` p13 |
| 3 | **R-FDR** Full Depth Reclamation (Stearns arm) | `milling_sy` | **FIRES (identification) but the TOTAL regressed** | item found 3/3; correct total **1 / 3** | Stearns 9813645 | `~~FULL DEPTH~~<br>RECLAMATION\|~~S Y~~\|~~70167~~` p77 |
| 4 | **R-FDR** (Dunn + White Shield arms) | `milling_sy` | **FIRES** | **13 / 13** (Dunn 10/10, White Shield 3/3) | Dunn; White Shield 8370470 | `FULL DEPTH RECLAMATION\|SY\|408,216.` p13; `20 306.0510 Full Depth Reclamation SY 3650` p25 |
| 5 | **R-RBP** Remove Bituminous Pavement | `milling_sy` | **FIRES** | **13 / 13** (demo 10/10, Crow Wing 3/3) | **9786015 DEMO**; Crow Wing | `\|7\|Remove Bituminous Pavement\|SY\|<br>7,097` p26 |
| 6 | **R-ROBS** Removal Of Bituminous Surfacing | `milling_sy` | **FIRES** (SY plan); on the TON plan it lands in `milling_tons` by the unit guard, not `milling_sy` | 3/3 SY · 13/13 mill-family on Dunn | Job 24133; Dunn | `REMOVAL OF BITUMINOUS SURFACING\|SY\|152.` p7; `…\|TON\|3,915.` p7 |
| 7 | **C-SURF13** Aggregate Surface Course Cl 13 | `shoulder_tons` | **FIRES — no drift** | **3 / 3** at HEAD (plus 8/8 parseable on 2026-08-10) | Job 24133 | `\|**018**\|**302**\|**0356**\|**AGGREGATE SURFACE COURSE CL 13**\|**TON**\|**170.**` p8 |
| 8 | **U-SALV** Salvage And Reuse Existing Aggregate | `grading_quantity` | **FIRES** | **3 / 3** | White Shield 8370470 | `22 302.0121 Salvage and Reuse Existing Aggregate CY 1000` p25 |
| 9 | **X-PC** Portland Cement (do not count) | no bucket | **FIRES (correctly excluded)** | **13 / 13** | Dunn | `PORTLAND CEMENT\|TON\|8,175.` p13 |
| 10 | **X-CSS** Cement Stabilized Subgrade (do not count) | no bucket | **FIRES (correctly excluded)** — but see caveat | **10 / 10** | **9786015 DEMO** | `\|42\|12" Cement Stabilized Subgrade (CV) (P)\|SY\|<br>1,566` p27 |
| 11 | **X-RBDP** Remove Bituminous Driveway Pavement | no bucket | **FIRES (correctly excluded)** | **3 / 3** at HEAD (plus 10/10 on 2026-08-10) | Crow Wing | `REMOVE BITUMINOUS <br>DRIVEWAY PAVEMENT\|S Y\|326` p220 |
| 12 | **X-RDP** Remove Driveway Pavement | no bucket | **FIRES (correctly excluded)** | **10 / 10** | **9786015 DEMO** | `\|8\|Remove Driveway Pavement\|SY\|<br>236` p26 |
| 13 | **X-RCDP** Remove Concrete Driveway Pavement | no bucket | **FIRES (correctly excluded)** | **3 / 3** | Stearns 9813645 | `~~REMOVE CONCRETE~~<br>DRIVEWAY PAVEMENT\|~~S Y~~\|~~44~~` p77 |
| 14 | **R-GRAVSURF** Gravel Surfacing | `base_tons` | **UNTESTED-NO-PLAN** | — | — | no priced pay item in 18 cached plans |
| 15 | **C-BASE13** Aggregate Base Cl 13 | `base_tons` | **UNTESTED-NO-PLAN** | — | — | appears only in a $/ton price-index table |
| 16 | **U-GRANBED** Granular Bedding | `grading_quantity` | **UNTESTED-NO-PLAN** | — | — | prose only; on 9786015 it is explicitly *incidental*, i.e. never a pay item |
| 17 | **U-FDBSR** Full Depth Bituminous Street Repair | `Mixed_tons` / `hot_mix_tons` | **UNTESTED-NO-PLAN** | — | — | zero corpus lines, exact or alias |

**Per-arm N and input hashes** — 9786015 demo **N=10** (`354a57ea30dce3e6`, proposal pages 1–426,
180,040 chars) ·
Dunn Job 23388 **N=10** (`50f0082f7d2a57a0`) + **N=3** raw-cell arm · Job 24133 **N=3**
(`bebfefc10a1c31ec` — the identical input string as the 2026-08-10 N=10 arm, so the two combine) ·
White Shield 8370470 **N=3** (`a7df0d02b49b9ce3`) · Stearns 9813645 **N=3** · Crow Wing **N=3**.

---

## 3. `untested-no-plan` — the explicit list

Four rulings have **no priced pay item on any of the 18 cached plans**, so no measurement was made
and none was manufactured:

1. **R-GRAVSURF — Gravel Surfacing → base_tons.** 39 corpus lines across 7 plans, every one prose.
2. **C-BASE13 — Aggregate Base Cl 13 → base_tons.** Two lines, both the NDDOT fuel/price-adjustment
   index (`$40.00 per Ton`), which carries no project quantity.
3. **U-GRANBED — Granular Bedding → grading_yards.** 12 lines on 7 plans, all specification or
   gradation-testing tables. On 9809481 the document says the cost is *incidental* — on that plan it
   structurally cannot become a pay item.
4. **U-FDBSR — Full Depth Bituminous Street Repair → Mixed_tons.** Zero lines, under the exact
   phrase and under every alias tried.

For 1, 3 and 4 the honest reading is that the corpus in the cache does not exercise them; whether
the wider (uncached) corpus does is a different question this pass did not open. **2 is different
and stronger**: the item name exists on two plans and is definitionally a price-index row, so a CL 13
*base* line may simply be rarer than the CL 13 *surface* line the split was written for.

---

## 4. The two does-not-fire claims, with their named methods

### 4.1 R-TSA — `TRAFFIC SERVICE AGGREGATE` (820 T) is DROPPED. Three methods.

**Method 1 — N=10 on the held-constant live-path input (2026-08-11, HEAD).**
`base_tons = 6,506` on **10 of 10** runs. 6,506 is exactly `AGGREGATE BASE COURSE CL 5` (item 044)
alone. 820 is not in it on any run.

**Method 2 — the neighbouring bucket, read directly.** `shoulder_tons = null` on 10 of 10, and its
raw cell states the reason: *"No AGGREGATE SHOULDERING or AGGREGATE SURFACE COURSE items appear in
the bid schedule; TRAFFIC SERVICE AGGREGATE was moved to base_tons per CSI ruling."* So the item
**left** `shoulder_tons` (Alex's "from" bucket) and **never arrived** in `base_tons`. That is
DROPPED, and it is a materially different failure from "never moved at all" — the ruling half-fired.
`base_unconverted` is also null 10/10, so the 820 T is not parked there either.

**Method 3 — value/reason divergence inside one response object.** The raw cell, captured verbatim
in `outputs/2026-08-11_alex_behavior_dunn23388_raw.json`, on **3 of 3** runs of the confirmation arm
and by reason text on **10 of 10** of the main arm:

```json
{"value": 6506, "confidence": "high", "page": 13,
 "reason": "AGGREGATE BASE COURSE CL 5 = 6,506 TON (item 044). TRAFFIC SERVICE AGGREGATE
            (820 TON, item 043) goes to base_tons per CSI ruling; ... Adding: 6,506 + 820 = 7,326.
            Wait — re-reading: 'TRAFFIC SERVICE AGGREGATE' is moved to base_tons by CSI.
            So base_tons = 6,506 + 820 = 7,326."}
```

**The model states the answer 7,326 and emits 6,506, with `confidence: high`, every time.** This is
not a vocabulary gap and not a placement ambiguity — the ruling is encoded, quoted back, and applied
in prose, and the number still does not move. Prose alone cannot fix it; the item-number layer can.

Independent corroboration, 24 hours apart: the 2026-08-10 N=10 arm
(`outputs/2026-08-10_nondeterminism.json`, a different schema revision) also returned Dunn
`base_tons = 6,506` on 10 of 10 — **0 of 23 across three arms and two field sets.**

### 4.2 U-CLEANROCK — `CLEAN ROCK` (758 T) is DROPPED. Two methods.

**Method 1 — N=13 across two arms.** `grading_quantity` on Dunn takes 7 distinct values across the
N=10 arm (38,535×4, 44,035, 41,535, 43,035, 38,538, 38,035, 41,035) and 38,535×3 in the N=3 arm.
**No observed value contains 758**, and every stated decomposition sums CY items only.

**Method 2 — the model names the exclusion and its cause.** Raw cell, 3 of 3 in the confirmation
arm and in 4 of 10 stated reasons in the main arm: *"CLEAN ROCK (Item 045) is listed under grading
definition but is measured in TON not CY so not counted here."* `base_tons` is 6,506 (item 044
alone) and `shoulder_tons` is null, so it is in no other bucket either.

**This one is a self-contradiction inside the shipped prose, not a model failure.**
`grading_quantity` says *"Also count 'SALVAGE AND REUSE EXISTING AGGREGATE' and 'CLEAN ROCK'"* and,
two sentences later, *"When a removal is measured in square yards or tons, do NOT convert it and do
NOT count it here."* Dunn's clean rock is TON. The model obeyed the second clause. Note the contrast
with **U-SALV**, which fires 3/3 — on White Shield the salvage item is measured in **CY**, so no
clause conflicts. **The two unassigned picks differ only in the unit the state happened to use.**

### 4.3 Not a does-not-fire, recorded separately: the Stearns FDR arithmetic regressed

`milling_sy` on Stearns at HEAD, N=3: **208,597 ×2, 140,430 ×1**. The FDR line is *identified* in
3/3 stated reasons, so R-FDR fires; the failure is the same in-context double count recorded on
2026-08-10 (`208,4xx = the milling subtotal added twice`), which was 2/10 then and is 2/3 now. N=3
cannot distinguish a real regression from the small-sample tail of an 80/20 distribution — **this
needs N=10 before anyone calls it a regression**, and it is flagged rather than claimed. Stearns'
correct value remains 140,430 (68,167 + 96 + 2,000 + 70,167).

### 4.4 A caveat on X-CSS, so the pass is not overclaimed

`CEMENT STABILIZED SUBGRADE` (1,566 SY on the demo plan) is correctly in no bucket 10/10 — but it is
measured in **SY**, and `grading_quantity` refuses non-CY items anyway. **The exclusion is confirmed
behaviourally; it is not confirmed to be *because of the ruling*.** A CY-measured cement-stabilized
item would be the real test and no cached plan has one.

---

## 5. Incidental observations (not rulings, recorded because they were visible)

- **Binder exclusion behaves.** Dunn's `PG 58S-34 ASPHALT CEMENT` (5,468 T) is named and excluded
  from `hot_mix_tons` in the stated reason, 10/10 — consistent with binder/coatings being a
  deliberate flag-only exclusion.
- **`grading_quantity` on Dunn is still the worst field measured** — 7 distinct values in 10 runs
  (38,035–44,035). Unchanged in character from 2026-08-10. Do not put Dunn GRADE on a slide.
- **Demo plan 9786015 is stable on every field**: MIX null, BASE null, GRADE 2,495, SHLDR null,
  MILL **15,828** — all 10/10. MILL decomposes exactly as `8,731` (Mill Bituminous Surface 2.0")
  `+ 7,097` (Remove Bituminous Pavement), with the 236 SY driveway line excluded. Its four
  tons-buckets are null because the demo plan prices hot mix, base and shouldering in **SY/CY**, and
  the unit guard refuses to convert — `*_unconverted` carries them, 10/10.

## 6. What this pass deliberately did not do

1. **No patch.** No edit to `schema.py`, `quantity_crosswalk.py`, the golden, or any source file.
   The real fix for R-TSA is the item-number layer after Wednesday.
2. **The 12-char matcher in `01_pipeline/test_material_vocabulary_coverage.py` is still narrow**
   (§0a). It will under-report the same way. Handed over, not fixed.
3. **No N=10 on Stearns** to settle §4.3. One 10-run arm on one plan.
4. **The encoding-audit agent's mid-run flags had not arrived** when this was written. The harness
   is per-plan and additive (`--measure --plan … --n …` writes its own JSON), so any flagged ruling
   can be topped up to N=10 without re-running anything already measured.
