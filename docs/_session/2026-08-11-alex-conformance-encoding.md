# Alex conformance audit — layer 1: is each ruling ENCODED?

Date: 2026-08-11 · Branch `2026-08-10-mapping-honesty` · **READ-ONLY audit. Nothing was edited.**

Scope: parse Alex's marks from the returned `.docx` XML, reconcile against the independently
supplied list, then assert every ruling against the two encoding surfaces:

- `pipelines/plan_reader/01_pipeline/schema.py` — the **live** mapping (the seven quantity field
  descriptions + the unit-capture fields). This is what a dropped PDF actually uses.
- `pipelines/plan_reader/05_knowledge/quantity_crosswalk.py` — `SPEC_MAP`,
  `CSI_RULINGS_2026_08_07`, `CSI_DO_NOT_COUNT_2026_08_07`. **Batch only.**

Whether a ruling FIRES is the parallel behaviour audit's job, not this one. No extraction was run.

Parser: `pipelines/plan_reader/04_tools/2026-08-11_parse_alex_marks.py` (committed with this report).

---

## 1. The parse

Source: `05_knowledge/_markup/2026-08-03_ALEX RESPONSES_material_mapping_for_CSI_v3.docx`.
The form's checkboxes are `w:sdt` content controls built by
`13_render_preread_docx.py::add_checkbox`; state lives in `<w14:checkbox><w14:checked w14:val>`.

**Totals: 272 checkboxes. 81 CHECKED, 191 UNCHECKED, 0 ABSENT, 0 MALFORMED.**

The parser emits four distinct states and never collapses them —
`ABSENT_NO_CHECKBOX_ELEMENT` / `ABSENT_NO_CHECKED_ELEMENT` (structural failure),
`CHECKED_IMPLICIT_NO_VAL`, `MALFORMED_VAL` — so "the control is missing" can never be reported as
"the box is unticked". Neither absence state occurred here.

**Two independent verification methods, both named, and they agree exactly:**
1. XML attribute parse of `w14:checked/@w14:val` → 81 true / 191 false.
2. Visible-glyph text scan of `word/document.xml` after tag-stripping → `☒` × 81, `☐` × 191.

**Tracked changes and comments: none.** `w:ins` = 0, `w:del` = 0, `w:comment` = 0, and the `.docx`
zip contains **no** `comments.xml` part. No answer is hiding in a revision or a margin note.

**Write-in tables: all empty.** Every "Material we did not list / Why it belongs here" table (5 of
them) has empty cells. Alex added no materials.

**Coverage: every material row is marked exactly once.** No row carries two ticks; exactly one row
in the whole document carries checkboxes and zero ticks — the riprap callout (§2, mismatch M1).

Typed-in blanks were captured from the label runs verbatim: `Move to ___base___`,
`Move to _base_____`, `Move to _mill_____`, `Move to __base____`.

---

## 2. Reconciliation against the supplied list

**One hard mismatch, and four material rulings the supplied list's catch-all clause conceals.**

### M1 — RIPRAP IS NOT CONFIRMED. The supplied list is wrong. (loud)

The supplied list states "riprap confirmed **not** asphalt". **Alex left the riprap callout blank.**
Both boxes — `Agree, riprap is not asphalt` and `No, count riprap in Mixed_tons` — are
`w14:val="0"`, and the visible glyphs are `☐ ☐`. Two methods, same answer. It is the *only*
unmarked question in the document, which is itself notable: he answered 81 of 82 and skipped this
one.

**The code is right and the list is wrong.** Both files already record riprap as OPEN:
`quantity_crosswalk.py::CSI_OPEN_QUESTIONS_2026_08_07 = ["riprap classification", ...]` and
`schema.py:129`'s comment. Do not "encode the riprap confirmation" — there isn't one.

### M2–M5 — rulings hidden inside "everything else, confirm no drift"

These are `Agree` ticks on rows that were *proposed as changes* (`Change` column = "NEW, not counted
today"). Ticking Agree on a NEW row is an affirmative ruling, not a no-op, and four of them resolve
questions the project had recorded as open in `14_build_material_preread_v2.py::QUESTIONS`:

| # | Row | Alex | Resolves |
|---|---|---|---|
| M2 | GR2 Topsoil (12 plans) + GR7 Common Topsoil Borrow (7) + GR15 Placing Topsoil (3) + GR17 Topsoil-Imported (3) + GR20 Topsoil-Borrow Area (2) | Agree → `grading_yards` | QUESTIONS #3, "Topsoil, 539,000 CY … Is topsoil part of your grading number?" **Answered: yes.** |
| M3 | BA5 Salvaged Base Course | Agree → `base_tons` | QUESTIONS #6, "Salvaged / remove-and-relay base … does it count toward `base_tons`?" **Answered: yes.** |
| M4 | AS7 Patching (ND) | Agree → `Mixed_tons` | — |
| M5 | SH1 Aggregate Surfacing (Cl 1/2/5/Special, 18 plans) | Agree → `shldr_tons` | QUESTIONS #5, the 67,000 T "is Class 5 really base?" question. **Answered: it stays shoulder.** Both files label this an ASSUMPTION "pending a CSI ruling" — the ruling exists. |

Nothing else diverges. Verified item by item:

- **Moves (5/5 confirmed)** — FDR → base (MI2, `Move to __base____`), Gravel Surfacing → base
  (SH4), Traffic Service Aggregate → base (SH5), Remove Bituminous Pavement → mill (GR6),
  Removal Of Bituminous Surfacing → mill (GR8).
- **Do not count (4/4 confirmed)** — Portland Cement (BA2), Cement Stabilized Subgrade (BA3),
  Remove Concrete Driveway Pavement (GR13), Remove Bituminous Driveway Pavement (GR24).
- **CL 13 split confirmed** — SH2 `Aggregate Surface Course` (Classes seen: `Cl 13`) = Agree in the
  `shldr_tons` table; BA1 `Aggregate Base` (Classes seen: `Cl 13, Cl 5, Cl 6`) = Agree in the
  `base_tons` table. Alex agreed to both sides of the split as printed.
- **Unassigned table (15/15 confirmed)** — Salvage And Reuse Existing Aggregate, Clean Rock,
  **Granular Bedding** → `grading_yards`; Full Depth Bituminous Street Repair → `Mixed_tons`; the
  other 11 → Do not count.
- **Scope flags (18/18 confirmed `Agree, flag only`)**, including
  **"Binder & coatings (tack, prime, PG cement)"**, 33 plans, examples `Tack Coat; Pg 58H; Pg 58S`.

---

## 3. The encoding table — worst first

Legend: **correct** · **INVERTED** (code says the opposite) · **wrong target** · **missing** (Alex
ruled, the file names nothing) · **crosswalk-disagrees**.

| # | Ruling | Alex's target | `schema.py` (LIVE) | `quantity_crosswalk.py` (batch) | Matches Alex | Note |
|---|---|---|---|---|---|---|
| 1 | **Binder & coatings flag-only** (tack, prime, PG cement) — 33 plans | `other`, flag only, **deliberate** | **missing — and unsafe.** No clause anywhere excludes binder from `hot_mix_tons`; `hot_mix_unconverted` tells the model to exclude "milling, removal, aggregate" and not binder. Dunn carries `PG 58S-34 ASPHALT CEMENT \| TON \| 5,468` — a ton-measured item an LLM can plausibly add to hot mix | **MIS-ENCODED.** `TACK COAT`→`never_matched`; `PG 58H`/`PG 58S`→`never_matched`. Only `ASPHALT CEMENT` reaches `untracked_category`. Same number, **opposite meaning**: the report says *we failed to read it* where Alex said *exclude it* | neither | The exact case the `GAP_*` enum exists to prevent, occurring inside the file that defines the enum. Fix is a `SPEC_MAP` row, not a comment |
| 2 | **`GRANULAR BEDDING` → `grading_yards`** | `grading_yards` | **missing** — not named in `grading_quantity`; will not be counted | **INVERTED.** Sits in `CSI_DO_NOT_COUNT_2026_08_07` → `csi_category=excluded`, `gap=excluded_by_csi`. The file asserts CSI ruled it out; CSI ruled it **in** | neither | Confirmed by parse: T16r14, `grading_yards` box `w14:val=1`. Worse than a miss — it launders our error as the client's decision |
| 3 | **`FULL DEPTH BITUMINOUS STREET REPAIR` → `Mixed_tons`** | `Mixed_tons` | **missing** — `hot_mix_tons` names "patching mixtures" but not this item (and it is SY, so it would at best belong in `hot_mix_unconverted`) | **INVERTED.** In `CSI_DO_NOT_COUNT_2026_08_07` → `excluded_by_csi` | neither | T16r15, `Mixed_tons` box `w14:val=1`. Same laundering defect as #2 |
| 4 | **Topsoil family → `grading_yards`** (M2; 5 rows, 27 plan-appearances, ~539,000 CY) | `grading_yards` | **missing.** `grading_quantity` lists "common excavation, subgrade excavation, embankment, borrow" + Salvage/Clean Rock. Topsoil is named nowhere | **wrong target.** `SPEC_MAP` `("TOPSOIL","erosion")` fires before `("BORROW","grading")` → `untracked_category` for all five variants | neither | The largest single quantity in this audit. Both surfaces silently drop it |
| 5 | **CL 13 split** — `AGGREGATE SURFACE COURSE CL 13` → `shldr_tons` | `shldr_tons` | **correct** — named explicitly in `shoulder_tons`, and `base_tons` explicitly pushes it away | **crosswalk-disagrees.** `SPEC_MAP:88 ("CL 13","base")` fires first → `base_tons` | **`schema.py`** | Known and documented at `schema.py:139` and in `2026-08-10-ruling9-and-cl13.md`. The live path is right; batch is stale |
| 6 | **`SALVAGED BASE COURSE` → `base_tons`** (M3) | `base_tons` | **mis-encoded (prose contradicts).** `base_tons` opens "PURCHASED AND PLACED" and reinforces it: "not aggregate bought for this job". Salvaged base is re-used, not bought — the qualifier reads as an instruction to drop it | **correct** — `("BASE COURSE","base")` → `base_tons` | **`quantity_crosswalk.py`** | The "purchased" wording was written to kill `REMOVE AGGREGATE BASE` (Dunn, 72,153 T) and catches salvaged base as collateral |
| 7 | **`PATCHING` → `Mixed_tons`** (M4) | `Mixed_tons` | **correct** — "Count wearing course, non-wearing course, leveling and **patching** mixtures" | **MIS-ENCODED.** No `SPEC_MAP` keyword → `never_matched` (reader failure) | **`schema.py`** | Same class as #1 |
| 8 | **`REMOVAL OF CONCRETE` → grading** (GR12, 5 plans, SY) | `grading_yards` | **correct in effect** — grading counts removal only when CY, `milling_sy` explicitly rejects concrete removal | **MIS-ENCODED.** `never_matched`. Its sibling `REMOVE CONCRETE PAVEMENT` is a `CSI_RULINGS` row and correctly returns `grading` + `no_bucket_for_unit`; the ND wording of the same item is a reader failure | **`schema.py`** | A pattern-coverage hole, not a judgment error |
| 9 | **`FOUNDATION FILL` → grading** (3 plans, CY) | `grading_yards` | **missing** | **MIS-ENCODED** — `never_matched` | neither | Small, but it is a CY item that would count if categorised |
| 10 | **`STRUCTURE EXCAVATION BOX CULVERT` → grading** (2 plans, CY) | **missing** | **wrong target** — `("STRUCTURE","structures")` precedes `("EXCAVATION","grading")`; deliberate ordering per the 2026-06-22 comment | neither | Genuine conflict: the ordering exists to stop box-culvert excavation polluting grading; Alex ticked Agree on it *being* grading. **Needs an owner call, not a one-liner** |
| 11 | **`SUBGRADE PREPARATION` → grading** (11 plans, SY) | `grading_yards` | ambiguous — `grading_quantity` says do not count non-CY *removals*; subgrade prep is not a removal, so the SY item's treatment is undefined | **honest gap** — `grading` + `no_bucket_for_unit` | crosswalk (states the gap explicitly) | Unit problem, not a mapping problem. No CY bucket can hold SY |
| 12 | **`AGGREGATE SURFACING CL 1/2/5/SPECIAL` → `shldr_tons`** (M5) | `shldr_tons` | **correct target, stale justification.** Both the description and the comment block say "ASSUMPTION, not a CSI ruling: CSI has not ruled where aggregate surfacing belongs." **He has.** | **correct** — `("AGGREGATE SURFACING","surfacing")` → `shoulder_tons` | both (on target) | Number is right in both; the live file tells the reader it is a guess when it is a decision |
| 13 | **Riprap** | **UNMARKED — no ruling exists** | **correct** — carried as open at `schema.py:129` | **correct** — `CSI_OPEN_QUESTIONS_2026_08_07` | both | See mismatch M1. Nothing to encode |
| 14 | **FDR → base** | base (work) | **correct as designed** — `base_tons` says "is base work, but its quantity belongs in `milling_sy`"; `milling_sy` counts it as kind (b) | **correct as designed** — category `base`, `bucket_override="milling_sy"` | both | The category/bucket split is deliberate and documented. Being fixed separately per the task brief; **do not** convert it to a bucket move (zeroes 1.2M SY) |
| 15 | `GRAVEL SURFACING` shoulder → base | `base_tons` | **correct** (named in `base_tons`, excluded from `shoulder_tons` *and* from `shoulder_unconverted`) | **correct** | both | |
| 16 | `TRAFFIC SERVICE AGGREGATE` shoulder → base | `base_tons` | **correct** (same three places) | **correct** | both | |
| 17 | `REMOVE BITUMINOUS PAVEMENT` grading → mill | `mill_sy` | **correct** (named in `milling_sy` kind (a) **and** in `milling_tons` for the TON case) | **correct** for SY; TON → `no_bucket_for_unit` (honest gap, batch has no `milling_tons`) | schema.py is more complete | |
| 18 | `REMOVAL OF BITUMINOUS SURFACING` grading → mill | `mill_sy` | **correct** (both `milling_sy` and `milling_tons`) | same as #17 | schema.py is more complete | |
| 19 | `PORTLAND CEMENT` do not count | excluded | **correct** (`base_tons` + `base_unconverted`) | **correct** (`CSI_RULINGS` → `excluded_by_csi`) | both | |
| 20 | `CEMENT STABILIZED SUBGRADE` do not count | excluded | **correct** (`base_tons` + `base_unconverted`) | **correct** (ruling beats `SPEC_MAP`'s `("CEMENT STABILIZED","base")`) | both | |
| 21 | `REMOVE CONCRETE DRIVEWAY PAVEMENT` do not count | excluded | **correct** (`milling_sy`) | **correct** | both | |
| 22 | `REMOVE BITUMINOUS DRIVEWAY PAVEMENT` do not count | excluded | **correct** (`milling_sy`) | **correct** | both | |
| 23 | `SALVAGE AND REUSE EXISTING AGGREGATE` → grading | `grading_yards` | **correct** (named) | **correct** | both | |
| 24 | `CLEAN ROCK` → grading | `grading_yards` | **correct** (named) | **correct** category; TON → `no_bucket_for_unit` | both | The corpus row is 758 TON, so the CY bucket cannot hold it either way |
| 25 | The other 11 unassigned rows → do not count | excluded | **missing** (none named) — low risk, they are concrete/misc items no bucket description invites | **correct** — all 11 present in `CSI_DO_NOT_COUNT_2026_08_07` | crosswalk | The 13-entry list = these 11 **+ the two inverted rows (#2, #3)**. That is the transcription error's fingerprint: all 15 unassigned rows were filed as "do not count" and the 4 that were assigned were then only half rescued |
| 26 | The other 17 scope-flag groups, flag only | `other` | **not representable** — `schema.py` has no scope-flag fields at all (only `box_culvert`) | correct in effect — all reach `untracked_category` via a real `SPEC_MAP` hit | crosswalk | Structural, not a defect: flag-only means "not one of the five quantities", which the live path achieves by omission. #1 is the one case where omission is unsafe |

**Score.** 12 of 26 correct in both files. `schema.py`: 12 correct, 6 missing, 3 mis-encoded, 5 n/a.
`quantity_crosswalk.py`: 15 correct, 2 **inverted**, 4 mis-encoded (`never_matched`), 2 wrong target.

**Where they disagree, `schema.py` matches Alex on #5 and #7–8; `quantity_crosswalk.py` matches Alex
on #6 and #25.** The live file is the more accurate of the two, which is the right way round.

---

## 4. Proposed fixes — FLAGGED FOR APPROVAL, NOT APPLIED

Every one is prose-only or a single data row. **None was applied.** All five touch the live prompt or
the batch crosswalk and therefore require `03_evaluation/2026-08-10_mapping_regression.py` to be
re-run before they ship (the mapping is a prompt; a unit test proves nothing about it).
`crushing_tons` / `stockpile_tons` are untouched by every proposal below.

**P1 — `schema.py::hot_mix_tons`, binder exclusion (ruling #1).** Append one sentence after
"Do NOT count aggregate.":

> `Do NOT count asphalt binder or coatings billed as their own pay item — 'PG 58S-34 ASPHALT CEMENT', 'PG 58H', 'TACK COAT', 'PRIME COAT'. CSI ruled these are carried as a scope flag only, and the mix tonnage already includes the binder.`

**P2 — `schema.py::grading_quantity`, topsoil + granular bedding (rulings #2, #4).** One replacement
inside the existing sentence:

> old: `common excavation, subgrade excavation, embankment, borrow. Also count 'SALVAGE AND REUSE EXISTING AGGREGATE' and 'CLEAN ROCK'.`
> new: `common excavation, subgrade excavation, embankment, borrow, and TOPSOIL items measured in cubic yards ('TOPSOIL', 'COMMON TOPSOIL BORROW', 'PLACING TOPSOIL', 'TOPSOIL - IMPORTED', 'TOPSOIL - BORROW AREA'). Also count 'SALVAGE AND REUSE EXISTING AGGREGATE', 'CLEAN ROCK' and 'GRANULAR BEDDING'.`

**P3 — `schema.py::base_tons`, salvaged base (ruling #6).** Two-word widening of the qualifier:

> old: `Total tons of aggregate/granular base material PURCHASED AND PLACED`
> new: `Total tons of aggregate/granular base material PURCHASED OR SALVAGED AND PLACED (CSI counts 'SALVAGED BASE COURSE')`

The following "Do NOT count 'REMOVE AGGREGATE BASE'" sentence still carries the Dunn exclusion, so
the drop test is unaffected — **but P3 is the one proposal that touches the clause the Dunn test
guards, so it must not ship without that test.**

**P4 — `schema.py::hot_mix_tons`, street repair (ruling #3).** Extend the existing patching clause:

> old: `Count wearing course, non-wearing course, leveling and patching mixtures.`
> new: `Count wearing course, non-wearing course, leveling and patching mixtures, including 'FULL DEPTH BITUMINOUS STREET REPAIR'.`

**P5 — `quantity_crosswalk.py`, the two inversions (rulings #2, #3).** Delete
`"FULL DEPTH BITUMINOUS STREET REPAIR"` and `"GRANULAR BEDDING"` from
`CSI_DO_NOT_COUNT_2026_08_07`, and add two rows to `CSI_RULINGS_2026_08_07` alongside the existing
"previously unassigned, resolved" pair:

> `("FULL DEPTH BITUMINOUS STREET REPAIR", "mixed", None, "CSI 08-07: unassigned -> Mixed_tons"),`
> `("GRANULAR BEDDING", "grading", None, "CSI 08-07: unassigned -> grading"),`

`test_quantity_crosswalk.py` asserts on these lists and will need reading first.

**Not proposed, needs an owner decision rather than an edit:**
- **#10 Structure Excavation Box Culvert.** Fixing it means reordering `SPEC_MAP` against a
  deliberate 2026-06-22 decision. Two plans of quantity against a known regression risk.
- **#12 the stale "ASSUMPTION, not a CSI ruling" labels** on `shoulder_tons`. The target is already
  right; only the justification is out of date. It is a comment-and-prose change with no behavioural
  intent, so it belongs in a documentation pass, not in a mapping commit.
- **#1's batch half.** Adding `TACK COAT` / `PG ` keywords to `SPEC_MAP` changes what
  `_matched_any_keyword` returns and therefore moves rows out of `never_matched`. Correct, and it is
  a behaviour change to the batch path that should be measured, not asserted.

---

## 5. Standing-rule notes

- **Failure vs empty, in the parser**: four distinct absence/malformation states, none of which can
  render as UNCHECKED. Zero occurred, so "unmarked" for riprap is a real answer and not a parse gap.
- **Two methods for every absence claim**: the riprap non-mark is asserted from the `w14:checked`
  attribute AND from the stripped visible glyph text; the "no typed answers elsewhere" claim from
  the empty write-in cells AND from `w:ins`/`w:del`/`comments.xml` all being absent from the zip.
- **Paths verified** with `git ls-files` before being written here. One consequence worth naming:
  **the `ALEX RESPONSES` docx is NOT git-tracked** (`git ls-files | grep -c "ALEX RESPONSES"` → 0)
  while the blank form it answers *is* tracked. The client's signed-off ground truth exists only on
  one disk. That is a separate risk from anything in this audit, and it is an owner call whether to
  commit it (46 KB).
