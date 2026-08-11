# 2026-08-11 — Alex's conformance fixes APPLIED, and measured

Branch `2026-08-10-mapping-honesty` (PR #104). This is layer 3 of the conformance work: layer 1
asked whether each ruling was **encoded** (`2026-08-11-alex-conformance-encoding.md`), layer 2 asked
whether it **fires** (`2026-08-11-alex-conformance-behavior.md`), and this pass **applies the fixes
and re-measures**.

Every change is decoded from a checkbox in the returned
`05_knowledge/_markup/2026-08-03_ALEX RESPONSES_material_mapping_for_CSI_v3.docx` — the client's
decisions, not our inference.

**Measurement discipline, unchanged from the two prior passes.** Every arm builds the extractor
input through the shipped chain via `build_input` imported from the 2026-08-10 non-determinism
harness (`detect_structure` → `convert_pages` → proposal pages only → `smart_truncate(180,000)`),
built **once per plan**, hashed, and reused for all N runs. **`process_pdf` was never called.
Chroma was touched zero times. No Supabase, no DDL, no golden edit, no `crushing_tons` /
`stockpile_tons` work, no bulk write.** A parse failure is `status=ERROR` with `values=None`,
excluded from every rate and counted out loud — it is never recorded as "the ruling did not fire".

**55 targeted extraction calls, 55 OK, 0 ERROR**, plus two 18-document differential arms.
Two prose descriptions were tightened *after* the first arms, in response to a leak the differential
harness found (§6.2), so every plan was **re-measured against the final shipped prose** and it is
those numbers that are quoted as "after".

---

## 0. Headline — before → after, per ruling

Rates are over parseable runs. "Before" is the arm committed with the 2026-08-11 behaviour audit
(`outputs/2026-08-11_alex_behavior_*.json`); "after" is the **final-prose** arm of this pass
(`outputs/2026-08-11_conformance_*_final.json`). The pre-final arms
(`..._n10.json`, `..._n5.json`) are kept and cited where they differ, because the difference between
them is itself a finding (§6.2).

| # | Ruling (Alex's mark) | before | after | verdict |
|---|---|---|---|---|
| 1 | **FDR's QUANTITY → base** (`Move to __base____`) | 0 / 13 — the quantity was in `milling_sy` by design | **20 / 20** — `base_unconverted` carries it verbatim (Dunn `FULL DEPTH RECLAMATION \| 408,216 \| SY` ×10, Stearns `\| 70167 \| SY` ×10) | **FIXED, unanimous** |
| 3 | **P1 binder & coatings, flag-only** | no clause existed; behaviour happened to comply | **10 / 10** on Dunn, and now *attributable*: the stated reason cites the rule ("PG 58S-34 ASPHALT CEMENT is excluded per rules") | **ENCODED + fires** |
| 4a | **P2 topsoil → grading** | Dunn `grading_quantity` 34,338 (baseline); 7 distinct values in 10 runs; topsoil absent from every stated decomposition | fires — every stated decomposition now names `TOPSOIL 6,447` and `TOPSOIL-IMPORTED 1,898`, and the CY total rises (38,035–44,035 → 39,035–43,755). **Still 6 distinct values in 10 runs** — see §4.1 | **FIRES; the field is still noisy** |
| 5 | **P3 `SALVAGED BASE COURSE` → `base_tons`** | — | `SALVAGED BASE COURSE` itself is **untested-no-plan** (19 corpus lines on 6 plans, **0 priced bid rows**). Its sibling `REMOVE AND RELAY BLENDED BASE COURSE \| 3650 \| SY` **fires 5/5** on White Shield, into `base_unconverted` | encoded; measurable only via the sibling |
| 6 | **P4 Full Depth Bituminous Street Repair → Mixed_tons** | — | **untested-no-plan**: zero corpus lines, exact or alias | encoded, unmeasurable here |
| 2 | **Clean Rock → grading** | **0 / 13 — DROPPED** | **3 / 10** captured in `grading_unconverted` on Dunn (4/10 on the pre-final arm) | **partially fixed — see §4** |
| 4b | **`GRANULAR BEDDING` → grading** | inverted in the crosswalk | encoded both surfaces; **untested-no-plan** (12 corpus lines, all prose; one plan states it is *incidental*) | inversion fixed |
| 7 | crosswalk inversions un-inverted | 2 patterns asserted `excluded_by_csi` | both now `CSI_RULINGS_2026_08_07` (`mixed` / `grading`) | **FIXED** |
| — | **U-SALV Salvage And Reuse Existing Aggregate → grading** | 3 / 3 | **4 / 5** on White Shield — *and it briefly went to 0/5*, see §6.2 | held, after a scare |
| — | **R-TSA Traffic Service Aggregate** | 0 / 23 | **0 / 10** on the final arm (`base_tons` 6,506 ×10) | **STILL FAILS — expected, see §5** |

---

## 1. The FDR reversal — what actually happened to Stearns and Dunn

This is the change that reverses what shipped the night before, so it is reported in full.

### Stearns 9813645 (MN) — N=15 across two arms (10 + 5), input `sha256 fa8ea4beba…`, 15/15 OK

| field | 2026-08-10 (N=10, `after4`) | 2026-08-11 behaviour arm (N=3) | **after this pass (N=10 + N=5 final)** |
|---|---|---|---|
| `milling_sy` | 140,430 ×8, 208,430 ×1, 208,593 ×1 | 208,597 ×2, 140,430 ×1 | **70,263 ×15** |
| `base_unconverted` | null | null ×3 | **`FULL DEPTH RECLAMATION \| 70167 \| SY` ×15** |
| `base_measured_unit` | TON | TON ×3 | **TON+OTHER ×15** |
| `base_tons` | 270 | 270 ×3 | **270 ×15** |
| `hot_mix_tons` / `shoulder_tons` / `grading_quantity` | 14,480 / 460 / 200 | same | **14,480 ×15 / 460 ×15 / 200 ×15** |
| `milling_unit_status` (derived) | `sy_only` | `sy_only` | **`sy_only` ×15** |
| `bucket_unit_status(base_tons)` | `tons_only` | `tons_only` | **`tons_and_unconverted` ×15** |

Stearns is **unanimous on every field in both arms** — 15 runs, zero variance anywhere.

**`milling_sy` dropped back to 70,263 exactly as predicted** — `68,167 + 96 + 2,000`, the three
`MILL BITUMINOUS SURFACE` lines, and the model's stated reason cites items 15/16/17 on 10 of 10.
The 70,167 SY of reclamation is not lost: it is one field over, verbatim, with its unit.

**The Stearns FDR-arithmetic question the task asked me to settle is now RETIRED, not answered.**
It was "does `milling_sy` return ~208,4xx (the milling subtotal double-counted) more often than the
N=3 arm suggested?" That arithmetic existed only because `milling_sy` was a sum of **two kinds** of
line. With kind (b) removed there is no second addend to double, and the new arms are
**70,263 ×15 — zero variance across two independently-built arms**. What can still be said about the old prose, pooling the two arms
that ran it (N=10 on 2026-08-10 + N=3 on 2026-08-11, N=13 total): **140,430 ×9, ~208,4xx ×4**, i.e.
roughly 69/31 rather than 80/20 — the N=3 arm was the tail of a wider distribution than believed,
not a regression. Stated as a pooled estimate, not as a fresh 10-run of prose that no longer ships.

### Dunn Job 23388 (ND), N=10 final prose, 10/10 OK — `milling_sy` DID go null

| field | before (N=10) | **after (N=10, final prose)** |
|---|---|---|
| `milling_sy` | 408,216 ×10 | **null ×10** |
| `milling_tons` | 67,007 ×6, 66,007 ×3, 66,907 ×1 | **67,007 ×10** (unanimous — an improvement) |
| `milling_measured_unit` | SY+TON ×10 | **TON ×10** |
| `milling_unit_status` (derived) | `sy_and_tons` | **`tons_only` ×10** |
| `base_unconverted` | null ×10 | **`FULL DEPTH RECLAMATION \| 408,216 \| SY` ×10** |
| `base_measured_unit` | TON ×10 | **TON+OTHER ×10** |
| `base_tons` | 6,506 ×10 | **6,506 ×10** |
| `hot_mix_tons` | 121,421 ×10 | **121,421 ×10** |
| `bucket_unit_status(base_tons)` | `tons_only` | **`tons_and_unconverted` ×10** |
| `grading_unit_status` (new) | — | **`cy_and_unconverted` ×10** |

**Dunn's `milling_sy` = 408,216 was entirely the FDR line, and it did go null — exactly as the task
anticipated.** The task's condition on that outcome is met and this is the load-bearing sentence of
this report:

> **It is a STATUS, not a silent null.** `milling_measured_unit = TON` on 10 of 10, so
> `schema.milling_unit_status()` returns **`tons_only`** — "milling is measured in TONS, `milling_sy`
> is null BY DESIGN, `milling_tons` has it" — and `milling_tons = 67,007` carries the quantity
> (63,092 T `MILLING PAVEMENT SURFACE` + 3,915 T `REMOVAL OF BITUMINOUS SURFACING`). `tons_only`,
> `not_present` and `unknown` are three distinct values; Dunn is in the first, and a reader can tell.

There is **no plan in this measurement with no milling figure at all.** The one plan whose
`milling_sy` went null has its milling in `milling_tons` with a status saying so.

---

## 2. The Dunn drop test — RE-CONFIRMED, explicitly

**`REMOVE AGGREGATE BASE | TON | 72,153` is still excluded from `base_tons` on Dunn: 10 runs of 10.**

This is the clause P3 widened (`PURCHASED AND PLACED` → `PURCHASED OR SALVAGED AND PLACED`), so it
is the one that had to be re-proved. Three methods:

1. **The values.** `base_tons` = **6,506 on 10 of 10** on the final arm (and 6,506 ×9 / 7,326 ×1 on
   the pre-final arm). 6,506 is `AGGREGATE BASE COURSE CL 5` (item 044) alone; 7,326 is that plus
   the 820 T `TRAFFIC SERVICE AGGREGATE`. **Neither contains 72,153, and no third value occurred
   across 20 runs.**
2. **A whole-record scan.** The string `72153` / `72,153` appears in **0 of 20** complete run
   records across both Dunn arms — not in a value, not in a stated reason, not in any capture field.
3. **`base_unconverted`, read directly.** It holds the FDR line only. The removal did not sneak in
   through the off-unit route the FDR move opened.

The prose keeps the two apart explicitly: *"that is demolition of existing material being disposed
of, which is a different pay item from salvaging base and placing it back."* Salvaged-and-reused ≠
removed, and the extractor honoured the distinction on every run.

**Stearns cross-check:** `base_tons` 270 ×15 (Class 2 + Class 6), unchanged from before.
**White Shield cross-check:** `base_tons` null ×5 — the plan's `Aggregate Base Course Cl 5` is
2,700 **CY**, so a null there is correct and `base_unconverted` names it, `unconverted_only`.

---

## 3. Demo plan 9786015 — N=15 across two arms, what CSI sees

15/15 OK, and **unanimous on every one of the seven totals in both arms**:

`MIX null · BASE null · GRADE 2,495 · SHLDR null · MILL 15,828 · CRUSH null · STOCK null` — all ×15,
byte-identical to the 2026-08-10 and the earlier 2026-08-11 arms. **No regression on the demo
plan**, including after the two late prose edits of §6.2.

`MILL 15,828` still decomposes as `8,731` (Mill Bituminous Surface 2.0") + `7,097` (Remove
Bituminous Pavement), with the 236 SY driveway line excluded — X-RDP fires 15/15. The four tons
buckets are null because this plan prices hot mix, base and shouldering in SY/CY, and all three
`*_unconverted` fields carry them 15/15 (`Class 5 Aggregate Base (CV) (P) | 2,485 | CY` etc.), with
`bucket_unit_status = unconverted_only`.

**Cement Stabilized Subgrade (1,566 SY) is still in no total, 15/15** — the exclusion holds. But see
§5.2: it is wrongly *named* in `grading_unconverted` on 5 of the first 10 runs.

---

## 4. Clean Rock — improved from 0/13 to 3–4/10, and that is not "fixed"

`CLEAN ROCK | TON | 758` (Dunn item 045) is now captured in `grading_unconverted` on **3 of 10 runs**
of the final arm (4 of 10 on the pre-final arm — **7 of 20 pooled**), against **0 of 13** before.
`grading_unit_status` is `cy_and_unconverted` on **20 of 20** — so on every run the record says
"there are grading items this CY total does not contain", even on the runs that name
`SUBCUT AGGREGATE | 2,482 | TON` and not clean rock.

Two named methods for the residual failure:

1. **Value distribution, N=20 pooled.** The `grading_unconverted` string contains "CLEAN ROCK" on 7
   runs. The others list `SUBCUT AGGREGATE`, `REMOVAL OF CONCRETE PAVEMENT | 182 | SY`,
   `EMBANKMENT SPECIAL | 1 | L SUM` or `FORESLOPE RESHAPING | 2,318 | STA` instead — the model
   picks *some* off-unit grading items, not all of them.
2. **The stated reason, read directly.** On the runs that do capture it the reason says
   *"SUBCUT AGGREGATE (TON) and CLEAN ROCK (TON) are non-CY and go to grading_unconverted"* — the
   mechanism works and the model knows the rule. On the runs that miss it the reason names a subset
   and simply stops. This is an **enumeration completeness** failure, not a placement failure.

**Honest verdict: the structural gap is closed and the recall is not.** The self-contradiction Alex's
mark exposed is gone (there is now a place for a TON-measured grading item, and the record always
says one exists), but a client asking "is my clean rock in there?" gets a yes 4 times in 10. The
same class of problem as the `milling_tons` "scan the WHOLE schedule" clause, and the same fix
shape: a per-line enumeration is what the item-number layer gives, and prose does not.

### 4.1 A claim I had to retract mid-pass — Dunn `grading_quantity` is NOT stabilised

The pre-final Dunn arm returned `grading_quantity` **43,755 ×10 — unanimous**, against 7 distinct
values in 10 runs before, and I wrote that the off-unit capture had stabilised the noisiest field on
this project. **The final arm, after two words of prose changed elsewhere, returned 6 distinct
values in 10 runs** (39,035 ×2, 39,535, 41,035 ×2, 41,535 ×2, 41,555, 43,755 ×2). The unanimity was
not reproducible and the claim was wrong.

What *is* supported: topsoil now appears in every stated decomposition (it appeared in none before),
and the range moved up (38,035–44,035 → 39,035–43,755). What is **not** supported is any statement
about stability. Recorded here rather than quietly corrected, because a one-arm unanimity that
evaporates on the next arm is precisely the thing this project keeps getting caught by.

---

## 5. What still does not fire, or fires wrongly — stated, not buried

1. **R-TSA `TRAFFIC SERVICE AGGREGATE` (820 T) — 0 / 10 on the final arm.** Pooled with the
   pre-final arm (1 / 10) and everything before it: **1 hit in 43 runs across five arms and three
   field sets.** The failure is unchanged in character and is quoted in
   full in the behaviour audit §4.1: the model writes *"So base_tons = 6,506 + 820 = 7,326"* inside
   the `reason` string and emits `6506` in the `value`, at `confidence: high`. **Not chased with more
   prose, per the brief.** It is the standing argument for the item-number layer
   (`docs/_spec/2026-08-10-spec-item-number-layer.md`): value and reason disagreeing inside one
   response object cannot be fixed by making the reason more emphatic.
2. **`grading_unconverted` names items it was told to exclude.** *(numbered §5.2 in the text above)* On 9786015, 5 of 10 runs list
   `12" Cement Stabilized Subgrade (CV) (P) | 1,566 | SY` — which the field's own prose forbids
   (CSI ruled CSS out) — and 10 of 10 list the shoulder aggregate item, which belongs to
   `shoulder_unconverted` (where it also correctly appears). **No total is corrupted by this**: CSS
   is in no bucket on 10/10 and the capture fields are never summed. It is a *presentation* defect
   in a new field, recorded rather than fixed tonight.
3. **Three rulings are untested-no-plan** — encoded, with nothing in the 18 cached plans to fire on:
   `SALVAGED BASE COURSE` (19 lines on 6 plans, **0 priced rows** — all specification prose),
   `GRANULAR BEDDING` (12 lines, all prose; one plan states it is *incidental*, so on that plan it
   structurally cannot be a pay item), `FULL DEPTH BITUMINOUS STREET REPAIR` (**zero lines**, exact
   or alias). Asserted as such in `test_material_vocabulary_coverage.py` rather than left to look
   like a pass — the FDBSR test **fails if the item ever enters the corpus**, which is the signal to
   measure it.
4. **`AGGREGATE SURFACING` still says `ASSUMPTION, not a CSI ruling` in `shoulder_tons`.** Alex's
   M5 mark resolves it (he ticked Agree on SH1 in the `shldr_tons` table). The target is already
   right; only the justification is stale. **Not changed here** — it is a documentation edit with no
   behavioural intent, and this pass kept cleanup out of a behaviour commit.
5. **Riprap remains OPEN and nothing was encoded.** Alex left that callout blank — the only one of
   82 questions he skipped, confirmed by two methods (the `w14:checked` attribute and the visible
   `☐ ☐` glyphs). `CSI_OPEN_QUESTIONS_2026_08_07` and the `schema.py` comment both still carry it as
   open, which is correct.

---

## 6. The differential harness

`03_evaluation/2026-08-10_mapping_regression.py --arm new`, diffed against the committed baseline
`outputs/2026-08-10_mapping_regression_new.json`. Output:
`outputs/2026-08-11_mapping_regression_new.json`; printed diff:
`outputs/2026-08-11_mapping_regression_diff.txt`.

### A harness defect the change exposed, and it is not a mapping regression

The first attempt returned **9 errors of 18 documents** —
`extraction response hit the max_tokens cap (2048) — the JSON parsed but is INCOMPLETE`.

**The harness was giving the model a smaller token budget than production.** It called
`s3_extract.call_json(prompt)`, taking that function's **default `max_tokens=2048`**, while the live
path (`s3_extract.extract_fields`, `s3_extract.py:316`) uses **`EXTRACT_MAX_TOKENS = 6000`**. It
went unnoticed because the 2026-08-10 field set happened to fit in 2048; the two grading capture
fields pushed it over. A harness that under-budgets production is not measuring production, so it
was fixed and the arm re-run at 6000. **This cannot inflate or deflate a total** — it only stops the
answer being cut off mid-JSON. The disclosure that matters: **the committed baseline was produced
at 2048**, so the two arms differ in budget as well as in prose. Every diff below is read with that
in mind, and no diff is attributed to the budget without saying so.

### The diff

**18 documents, 0 errors, both arms comparable on 17 of them.**
**11 field movements · 0 UNEXPLAINED · 1 document could not be compared** (9786015 is in the new
arm's corpus and not the baseline's — it is reported as an ERROR row, not as a pass and not as a
zero).

| plan | field | old | new | verdict |
|---|---|---|---|---|
| 8416165 | `milling_sy` | 193,507 | 192,221 | explained — FDR leaves milling |
| 9813645 Stearns | `milling_sy` | 140,430 | **70,263** | explained — FDR leaves milling |
| Job 23388 Dunn | `milling_sy` | 408,216 | **null** | **disappeared** — verified below |
| 823d011b White Shield | `milling_sy` | 3,650 | **null** | **disappeared** — verified below |
| Job 23388 Dunn | `grading_quantity` | 34,338 | 43,755 | explained — P2 topsoil |
| Crow Wing | `grading_quantity` | 9,371 | 15,876 | explained — P2 topsoil |
| 8428114 | `grading_quantity` | 1,600 | 4,500 | explained — P2 topsoil |
| 187bbb4f | `grading_quantity` | 18,471 | 47,313 | explained — P2 topsoil |
| 823d011b White Shield | `grading_quantity` | 14,775 | 13,775 | explained *(wrongly — see §6.2)* |
| 823d011b White Shield | `base_tons` | null | 1,000 | **appeared — this is the leak, see §6.2** |
| Job 24133 | `shoulder_tons` | null | 170 | appeared — the **2026-08-10** CL 13 fix, which post-dates the baseline |

### 6.1 The two `disappeared` rows are moves, and the harness can prove it

Both are `milling_sy` going null, which is exactly what a silent drop looks like. The `extras` block
recorded on the same document distinguishes them:

- **Dunn** — `base_unconverted: FULL DEPTH RECLAMATION | 408,216 | SY`, `base_measured_unit:
  TON+OTHER`, `milling_measured_unit: TON`, `milling_tons: 67,007`, `milling_unit_status:
  **tons_only**`. Every square yard is accounted for and the null carries a reason.
- **White Shield 8370470** — `base_unconverted: Aggregate Base Course Cl 5 | 2700 | CY` +
  `Full Depth Reclamation | 3650 | SY` + `Remove And Relay Blended Base Course | 3650 | SY`;
  `milling_unit_status: **not_present**`. That status is correct and is the *other* legitimate empty
  answer: once FDR is no longer a milling item, this plan genuinely has no milling item, and
  `not_present` says so rather than leaving a bare null.

`EXTRA_FIELDS` was extended for exactly this reason before the arm was run — without the capture
fields in the output, a move and a drop would have been indistinguishable in the diff.

### 6.2 The leak the harness caught, and the two-step fix — reported in full

The `823d011b` row **`base_tons` null → 1,000** is not a ruling firing. That plan's
`Salvage and Reuse Existing Aggregate | 1000 | CY` — which **CSI assigned to GRADING** — was pulled
into `base_tons` as if it were 1,000 tons, and simultaneously dropped out of `grading_quantity`
(14,775 → 13,775, which the diff classified as "explained" under the wrong rule). **P3's widening
caused it**: telling the model that base_tons counts *salvaged* base made "salvage and reuse
existing aggregate" read as base.

This is a genuine cross-ruling collision between two of Alex's own answers, and it is a
**unit corruption** (a CY quantity in a TON field), which is the class of defect this whole project
exists to prevent. Two prose edits, each measured:

| attempt | change | White Shield result (N=5) |
|---|---|---|
| 1 | `base_tons` / `base_unconverted` name `SALVAGE AND REUSE EXISTING AGGREGATE` as an exclusion | `base_tons` null ×4 / 0 ×1 — **leak closed**, but `grading_quantity` 13,775 ×5: the item was now in **no bucket at all**. Over-corrected: U-SALV went 3/3 → **0/5** |
| 2 (shipped) | + `grading_quantity` claims it back symmetrically: *"CSI ruled that item is GRADING, so count its cubic yards here and do NOT put it in base_tons, even though the words look like salvaged base course"* | `base_tons` **null ×5**, `grading_quantity` **14,775 ×4 / 13,775 ×1** — leak closed AND U-SALV restored to **4/5** |

Attempt 1 is recorded rather than deleted because it is the finding: **closing a leak by naming an
exclusion moved the item from the wrong bucket into no bucket** — a silent drop, which is worse than
the leak it fixed. Only naming *both* ends of the pair held. All three other plans were re-measured
after edit 2 (§1, §3) and none moved.

**Disclosure about the diff above:** it was produced by the arm that ran *before* these two edits.
Re-running the full 18-document arm a third time was not done. The four plans that carry the
affected items were each re-measured directly instead, at N=10 / N=5, and those numbers — not the
diff's — are what §0–§3 report.

---

## 7. What changed in the tree

| file | change |
|---|---|
| `01_pipeline/schema.py` | `hot_mix_tons` (P1 binder exclusion, P4 street repair); `base_tons` (P3 salvaged + the `SALVAGE AND REUSE` exclusion of §6.2, FDR quantity → base); `base_unconverted` / `base_measured_unit` (FDR lands here); `grading_quantity` (P2 topsoil, granular bedding, the symmetric `SALVAGE AND REUSE` claim of §6.2, CY-only guard pointing at the new field); **new** `grading_measured_unit` / `grading_unconverted`; **new** `grading_unit_status()` + `GRADING_UNIT_TOKENS` / `GRADING_UNIT_STATUSES`; `milling_sy` (kind (b) removed, FDR explicitly excluded and redirected); `milling_measured_unit` (FDR is not a milling item) |
| `01_pipeline/corpus_match.py` | **new** — the one denoising matcher, shared |
| `01_pipeline/test_material_vocabulary_coverage.py` | uses `corpus_match`; reclamation assertions moved to `base_unconverted`; new direction assertion on `milling_sy`; 9 new conformance-vocabulary pairs; the FDBSR ruled-but-absent test; the two driveway-removal tests that were RED under the old matcher |
| `01_pipeline/test_grading_unit_capture.py` | **new**, 10 tests |
| `05_knowledge/quantity_crosswalk.py` | the two inversions un-inverted |
| `apps/api/backend/payload_carry.py` | `grading_unconverted` in `CARRIED_FIELDS` + `_LABELS` |
| `apps/api/backend/report.py` | emits `grading_unit_status` |
| `03_evaluation/2026-08-10_mapping_regression.py` | token budget matched to the live path; `EXTRA_FIELDS` gains the base/grading capture fields; two `EXPLAINED` entries extended and one added |
| `03_evaluation/2026-08-11_alex_conformance_behavior.py` | shared matcher; R-FDR target reversed; U-CLEANROCK retargeted; three new rulings; grading companions |
| `docs/_spec/2026-08-11-grading-unit-capture.md` | **new** — written before the code |

`apps/web` deliberately untouched: `gap-status.ts` still holds `BUCKET_UNIT_CELL = undefined` (the
shape-dependent half, held open by `2026-08-10-frontend-gap-rendering.md` §5) and both parity tests
skip on that rather than passing vacuously. A py-only status token cannot break a TS→py assertion.

### Verification

- `pytest pipelines/plan_reader/01_pipeline/ 05_knowledge/test_quantity_crosswalk.py -q` →
  **182 passed, 1 xfailed** (was 150 / 1).
- `quantity_crosswalk` after the un-inversion, checked directly:
  `GRANULAR BEDDING` → category `grading`, bucket `grading_quantity` at CY;
  `FULL DEPTH BITUMINOUS STREET REPAIR` → category `mixed`, bucket `hot_mix_tons` at TON;
  `SALVAGED BASE COURSE` → `base` / `base_tons`; `REMOVE AGGREGATE BASE` → `grading` / no bucket
  (Mark's rule, unchanged). **`CSI_DO_NOT_COUNT_2026_08_07` is now 11 entries — exactly the number
  of genuinely-unassigned rows on the form**, which is the fingerprint the commit message records.
- **RED before green, measured:** the two driveway-removal phrases returned **0 hits** under the old
  12-character raw-line matcher and **1 hit each** under `corpus_match.denoise`. That red is the
  reason item 8 exists.
- `apps/api` pytest: 2 failures, **both pre-existing** (`test_midpoint_bridge` — rough edge 6's DOT
  flake; `test_candidate_pool_consistency` — no `pyarrow` in this env). `apps/web` `node --test`:
  2 failures, **both pre-existing** — confirmed identical with these changes stashed.
- No `process_pdf`, no Chroma write, no Supabase, no DDL, no golden edit, no PR touched.
- **No conversion built.** No SY→TON, CY→TON or TON→CY factor, constant, or code path, dormant or
  otherwise. That remains PR #105.
