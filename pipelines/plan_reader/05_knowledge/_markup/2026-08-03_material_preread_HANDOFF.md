# Handoff — finalise the Material Roll-Up Pre-Read for CSI

Date: 2026-08-03 · Status: **v3 is client-ready and can be sent.** T's readability pass is applied in
full (proposal framing, clickable checkboxes, no em dashes, internal sections stripped, Superpave
grouped). The items in "What is still left" are mapping-quality work, not blockers on sending.

---

## The agent prompt

> Copy everything in this block as the starting prompt for the next agent.

---

You are finishing a client-facing document for **CSI (Central Specialties Inc.)**, a highway paving
contractor in MN/ND/SD. It is the **proposed material mapping** they will mark up in a review
meeting, confirming how we roll plan pay-items into the buckets they track. The framing is
deliberate and set by T: *this is the mapping we intend to use; if there are no objections, we will
use it.* It is not a menu of options.

**Read these first, in this order:**

1. `/Users/t/dev/csi/csi-bid-intelligence/CLAUDE.md` — repo contract and folder responsibilities
2. `/Users/t/dev/csi/csi-bid-intelligence/pipelines/plan_reader/05_knowledge/_markup/2026-08-03_material_preread_HANDOFF.md` — this file, the full background below the prompt
3. `/Users/t/dev/csi/csi-bid-intelligence/pipelines/plan_reader/05_knowledge/_markup/2026-08-03_material_mapping_for_CSI_v3.md` — **the current version, client-ready**
4. `~/Downloads/2026-06-17_gotcha_preread_final.docx` — the house format this must match

**The six buckets** (use these exact names): `Mixed_tons` · `base_tons` · `shldr_tons` ·
`grading_yards` · `mill_sy` · `other`. The stated goal is to land the **majority of spec'd materials**
in one of the six — `other` is a real destination for work CSI does not quantify, not a dumping
ground for anything unmatched.

**Your job.** T's readability feedback is fully applied and v3 can be sent as it stands. The four
items under "What is still left" are mapping-quality work that has not been started.

**Already done in v3 (do not redo):**

- **Reframed from "What we ARE tracking" to a proposal.** v2 had rows marked *not counted* sitting
  inside a section headed "What we ARE tracking" — contradictory. v3 leads with *"This is the mapping
  we intend to use. If there are no objections, we will use this."*
- **`Today` replaced by `Change`** — `NEW — missed today` / `MOVED from base_tons` / `partly NEW` /
  `no change`. Same underlying fact, but it now argues FOR the mapping instead of confusing the
  reader. `NEW` and `MOVED` render red.
- **`Total qty` column dropped.**
- **Plan count fixed to 66**, computed by `n_plans()` rather than hardcoded.
- **`other` is now a formal sixth bucket** listed alongside the five, not a separate "not tracking"
  concept.
- **The Superpave family is grouped.** `base_name()` was already folding `SUPERPAVE FAA 45` and
  `RAP - SUPERPAVE FAA 43` into one group; what was missing was the RAP flag in the Classes column,
  so the grouped row silently swallowed the fact that some of it is recycled. `classes_seen()` now
  emits `FAA 45, FAA 43, FAA 42, RAP`, with RAP last because it is a flag, not a grade. The other
  buckets were checked for the same pattern: `Aggregate Base` (CL 5/6/13) and `Aggregate Surfacing`
  (Class 1/2/5/Special) were already grouped correctly.
- **The checkboxes are clickable in the .docx.** `w:sdt` + `w14:checkbox` content controls, not
  legacy `FORMCHECKBOX` fields — those are only clickable under form protection, which would lock
  the "Move to ____" blanks and the empty "anything missing" tables. Helpers live in `13_`
  (`add_checkbox`, `checkbox_line`, `cell_checkboxes`); `build_table` and `callout` treat a **list**
  cell value as checkbox labels. The opening callout tells CSI to click rather than print. Verified:
  544 controls, `w14` on the document root.
- **No em dashes anywhere in the client-facing output.** T's instruction, 2026-08-03. Prose is
  written without them and `nd()` scrubs the ones arriving from pay-item names and from `12_`, which
  still uses an em dash as its empty-quantity placeholder. `audit_dashes()` fails the build if one
  reappears, in the .md or in any docx paragraph or table cell.
- **Two internal sections are no longer rendered.** The "Why this changed" Stearns write-up and the
  seven judgment-call questions are internal. They are kept in `14_` as `WHY_INTERNAL` and
  `QUESTIONS` with a comment saying they are deliberately unrendered — **do not let a
  "remove unused code" pass delete them.** The seven questions are the agenda for the review
  meeting; a page of open questions at the back of a proposal invites the meeting to end
  unresolved. The `Change` column stays: T asked for it, and its cell values read on their own now
  that the section explaining them is gone.
- **The "Plus N material(s) seen on only one plan" footnotes are gone.** All five of them.
  Consequence to know: those 61 one-off materials are now in **no** client-facing document. v1 is
  the complete record.
- **Riprap is flagged inside `Mixed_tons`**, with its own two checkboxes, instead of sitting in a
  note under `other`. "Is riprap asphalt?" is a `Mixed_tons` question, and an estimator who agrees
  with the `Mixed_tons` table will never scroll to a footnote three sections later.

**What is still left** (mapping quality — none of these block sending v3):

1. **Apply the same reframe and column logic to v1** (`2026-07-30_material_preread_for_CSI.{md,docx}`,
   generated by `12_` and `13_`), which stays as the detailed per-class record. It still has the old
   "What we ARE tracking" framing and the old `Today` column.
2. **Check `grading_yards`.** 26 rows, triple any other bucket — see Known weaknesses.
3. **Decide the `Still unassigned` section.** 45 materials have no bucket. The stated goal is to map
   the majority of spec'd materials into the six buckets, so most of these should probably land in
   `other` with a short list genuinely put to CSI. Right now all 45 are punted to them.
4. **`Portland Cement` (BA2, 13,322 TON, 4 plans) is in `base_tons` and is probably wrong.** It is a
   binder / stabilising additive, not aggregate base. It arrived there via the `PORTLAND CEMENT`
   keyword on the `stabilized_base` family. Either move it to `other` or make it an explicit question
   — do not leave it silently in `base_tons`.

**How to regenerate — never hand-edit the .md or .docx.** They are generated:

```bash
cd /Users/t/dev/csi/csi-bid-intelligence
python3 pipelines/plan_reader/04_tools/11_build_material_map.py        # the matcher + engineering CSVs
python3 pipelines/plan_reader/04_tools/12_build_material_preread.py    # v1 markdown
python3 pipelines/plan_reader/04_tools/13_render_preread_docx.py       # v1 docx (styled)
python3 pipelines/plan_reader/04_tools/14_build_material_preread_v2.py # v3 markdown + docx
```

Edit the scripts, re-run, re-read the output. `14_` imports `12_` and `13_`, so the data and the
styling have one home each.

**Hard constraints — do not break these:**

- **Do not hardcode a final mapping.** T's standing instruction: *"we don't want to do hardcoding
  mapping before testing with them."* The document is a proposal with checkboxes; CSI decides.
- **Never collapse a class or grade designator away.** `FAA 45`, `CL 5`, `Class Special`, `SP 12.5`,
  `PG 58S-28` drive aggregate source and price — FAA number decides quarried rock vs pit gravel. They
  may be *grouped under* a material heading, but every one must remain visible. (An earlier draft
  collapsed them and T corrected it.)
- **Do not wire any of this into the live pipeline.** `05_knowledge/quantity_crosswalk.py` and the
  extraction path stay untouched until CSI answers. No re-runs of `plan_metrics`, no Supabase publish.
- **No em dashes in anything CSI sees.** T's instruction. `audit_dashes()` in `14_` enforces it and
  will fail the build; do not weaken it, fix the string instead.
- **The docx checkboxes must stay clickable.** If you switch them back to plain `☐` glyphs or to
  legacy form fields you have undone the point of the version. See `13_.add_checkbox`.
- **Hard Rule 12** — if you do change extraction behaviour, diff against the current output first.
- Match the gotcha pre-read's styling exactly: navy `1F3A5F`, blue `1F6FB2`, red `C0392B`, fills
  `EEF3F8`/`F4F6F8`/`FFF6DC`, borders `E3E7EB`, Calibri. `13_render_preread_docx.py` already holds
  these as constants and the OOXML helpers for cell shading and table borders (python-docx has no API
  for either).

**Resolved since the first draft of this handoff:** the `other` category is now built as a formal
sixth bucket, replacing the old "Part 2 — What we are NOT tracking" section. The remaining piece is
item 3 above — the 45 still-unassigned materials, most of which should probably resolve to `other`.

---

## Background — what happened and why the document exists

### The trigger

CSI reported that materials were being extracted wrong. Tested on
**Stearns County CP 073-123-025** (`CSI ELP 2026/2025 Bid year…/12 - AUGUST/Plans Proposals/08.28.25
STEARNS CO MN CP 073-123-025…/9813645.pdf`, bid schedule on pages 77–78).

**Line-item extraction was perfect — 26 of 26 captured.** Every error was in the description→bucket
mapping:

| Pay item | Qty | Was mapped to | Should be |
|---|---|---|---|
| Mill Bituminous Surface (1.0"/1.5"/4.0") | 70,263 SY | asphalt → dropped | milling |
| Full Depth Reclamation | 70,167 SY | unrecognised | *open question* |
| Remove Concrete Driveway Pavement | 44 SY | unrecognised | removal |
| Motor Grader / trucks / loaders | hourly | unrecognised | equipment rental |

The plan reported **zero milling** on a job that is almost entirely milling and reclamation.

### Root cause (fixed)

`05_knowledge/quantity_crosswalk.py` is a **flat first-match-wins keyword list**, so the *material
noun* beat the *action verb*: `MILL BITUMINOUS SURFACE` hit `BITUMINOUS → hma` before it could reach
milling. Corpus-wide that stranded **1.6M SY of milling** and **1.2M SY of reclamation**.

The replacement matcher (`11_build_material_map.py`) resolves **action before material**, and the
family ordering in that file is load-bearing — there is a comment saying so. Two independent bugs of
this exact class were caught during the build by running the matcher against the corpus rather than
reasoning about it.

### Second defect found and fixed

**Typographic characters.** `AGGREGATE\xa0BASE\xa0COURSE\xa0CL\xa05` (21,107 TON) never matched the
`AGGREGATE BASE` keyword because the PDF used non-breaking spaces. Also found U+2010 hyphens
(`EXCAVATION ‐COMMON`) and smart quotes. **34,739 tons recovered** by one normalisation function
(`mmap.normalize`).

### Noise in the `materials` table — important context

The table holds **CAD sheet text as well as bid-schedule lines**: plan legends, stationing runs
(`60+00 61+00 62+00`), sieve-analysis spec tables. These contain material keywords and will match
families if not filtered. `11_` imports `is_noise()` from `08_material_universe.py` rather than
duplicating the rules. Of 6,385 rows, **2,260 are noise**; 4,125 are real pay items.

Coverage, stated honestly two ways: **50.7%** of real pay items match a family, but **91.0%** of rows
carrying a real TON/SY/CY quantity — the only ones that can move a CSI number.

---

## Facts you will need (verify, do not trust)

```bash
cd /Users/t/dev/csi/csi-bid-intelligence/pipelines/plan_reader
sqlite3 csi_v2.db "SELECT COUNT(*) FROM plans;"                              -- 117
sqlite3 csi_v2.db "SELECT COUNT(DISTINCT plan_id) FROM materials;"           -- 66  <- the real N
sqlite3 csi_v2.db "SELECT state, COUNT(*) FROM plans GROUP BY 1;"            -- MN 47, ND 41, SD 24, XX 4, MT 1
```

DB: `pipelines/plan_reader/csi_v2.db` (SQLite). A hosted Supabase mirror exists — read-only for this
work, do not publish.

Current v2 size: **48 rows** (`Mixed_tons` 7 · `base_tons` 5 · `shldr_tons` 5 · `grading_yards` 26 ·
`mill_sy` 5). The 61 one-off materials that used to sit in footnotes are DROPPED from the
document entirely (T, 2026-08-03), so v1's 149 rows are now the only place they appear.

---

## Files

**Deliverables** (all in `pipelines/plan_reader/05_knowledge/_markup/`):

| File | What |
|---|---|
| `2026-08-03_material_mapping_for_CSI_v3.{md,docx}` | **the one to finish** — proposal framing, 48 rows |
| `2026-07-30_material_preread_for_CSI_v2.{md,docx}` | superseded by v3, kept for diffing |
| `2026-07-30_material_preread_for_CSI.{md,docx}` | v1, full detail, stays as the record |
| `2026-07-30_material_mapping_for_CSI.md` | earlier prose version — superseded, keep for the question list |
| `2026-07-30_material_map_MASTER.md` | engineering view: 33 families, one page |
| `2026-07-30_material_map_PROPOSED.csv` | 33 families with blank `csi_answer`/`csi_notes` columns |
| `2026-07-30_material_map_EVIDENCE.csv` | 1,103 rows — every pay-item name per family + unmatched queue |

**Generators** (`pipelines/plan_reader/04_tools/`): `11_build_material_map.py` (matcher — edit
`FAMILIES` here to change any mapping) · `12_build_material_preread.py` (v1 md, `collect()`,
`spec_name()`, `base_name()`) · `13_render_preread_docx.py` (docx styling + OOXML helpers) ·
`14_build_material_preread_v2.py` (**v3** both formats — filename still says v2, the output is v3).

**Prior art:** `05_knowledge/quantity_crosswalk.py` (the LIVE mapping — the "Today" column comes from
it) · `05_knowledge/material_crosswalk.csv` (2,434 LLM-classified keys, built 07-03, never wired in).

---

## Known weaknesses — disclose, do not quietly fix

- **`grading_yards` over-collects.** 26 rows, triple any other column. The generic `EXCAVATION`
  keyword is a wide net, and word-order duplicates (`Common Excavation` vs `Excavation - Common`) are
  only partly folded. Most likely place for a wrong mapping.
- **`Shot Rock` (8,078 T, SD) and `Granular Material, Furnish` (9,825 T, SD)** are in `shldr_tons` on
  a keyword guess. They may be base or embankment. Flag for CSI rather than deciding.
- **`Graunular Material, Furnish`** is misspelled in the source plan — a good live example for CSI of
  why we match on patterns, not an exact item list.
- **Plan-sheet titles still pass the noise filter** (`Williams County, ND STA 90+00 to 110+00…`).
  They only appear in flag-only groups, so no CSI quantity is affected.
- **Spec numbers are discarded.** MnDOT bid schedules carry a `Mat No.` column (`2232.504` milling,
  `2360.509` hot mix, `2215.504` FDR). That is the DOT's own classification and would be far more
  durable than keywords, but the parser stores line numbers instead (0 of 6,385 rows retain one).
  Capturing it is a parser change plus a corpus re-run — **out of scope for this handoff**, but it is
  the right long-term fix and is raised as a question at the end of the document.

## The seven open questions the document asks CSI

Ordered by quantity at stake. These are the point of the exercise — do not answer them, and do not
let a simplification pass delete one.

1. **Full Depth Reclamation** — 1,166,000 SY, 14 plans, currently counted as nothing. `mill_sy`,
   `grading_yards`, or its own column?
2. **ND measures milling in TONS** — 230,625 T. `mill_sy` cannot hold both units.
3. **Topsoil** — 539,000 CY, filed as erosion control so it never reaches `grading_yards`.
4. **Pavement removal → grading.** Mark said it converts to CY. Does the rule apply only to
   pavement/base removal (158 removal item types are mostly fence/sign/pipe)? Is 1.75 Ton/CY standard?
5. **Aggregate Surfacing Class 1 vs 5 vs Special** — 67,000 T, all currently `shldr_tons`.
6. **Salvaged / remove-and-relay base** — re-used, not bought. Counts toward `base_tons`?
7. **PG binder, tack, prime** — 56,029 T, proposed excluded from `Mixed_tons` to avoid double-count.

Plus two closing questions: which source CSI trusts when the proposal bid schedule and the plan-set
quantity sheets disagree, and whether pay-item wording changes by letting agency.

**Not attempted:** state-by-state vocabulary comparison (MN "Type SP" vs ND "Superpave" vs SD
"Asphalt Concrete"). T scoped this as separate work.
