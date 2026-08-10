# TASKS — the board

Last updated **2026-08-10**. Read `HANDOFF.md` first, then the current task board
`2026-08-08-tasks-deployment.md`, which supersedes this file where they conflict.
Dates: **presentation Wed Aug 12** · **CSI IT handoff Mon Aug 17** · **program ends Fri Aug 21**.

Status: `TODO` · `SPEC` (written, awaiting approval) · `BLOCKED` · `DONE`

---

## CORRECTIONS — 2026-08-10, measured against the corpus. Do not inherit the old numbers.

| Claim on the board | What is actually there | Method |
|---|---|---|
| "38 `rtv-csv-for-Bid Item List*.csv`" | **8** (6 csv + 2 xlsx), all MN. The 38 is *all* `rtv-csv-*` files: 27 Plan Holders, 8 Bid Item List, 1 undefined, 1 Projects, 1 Bid Abstract Summary | glob returns 8; kind-breakdown sums to 38; identical on both mirrors |
| "217 standalone `AD.pdf`" | **8**. The 217 is advertisements **and addenda** together; there are 180 addenda (`*a[0-9].pdf`) and 137 filenames containing "addendum" | strict glob = 8 on both mirrors; broader `AD`-token grep = 15, extra 7 are not ads on inspection |
| "174 Daily Ads digests" | **Correct.** Now the biggest bid-date prize, since layer 1 covers only 8 folders | count |
| "bid date is NOT on the title sheet, only in the proposal" (old P0 #5 note) | **Wrong, already corrected on the current board.** It is in plan-set body text, and `_md_cache` page 1 of one plan reads "Letting Date: August 20, 2025 / Bids Close: 9:30 a.m. CST" | direct read |
| "the live path missed asphalt because the prompt says HMA and NDDOT writes SUPERPAVE" (`HANDOFF.md` §1, marked UNVERIFIED) | **Probably not the cause.** The OLD prompt, unchanged, returns `hot_mix_tons = 121,221` on Dunn — exact. The difference from the live path's 200 tons is the **document text**, not the wording | differential re-run, `03_evaluation/outputs/` |

**Box is unreadable in this environment** — listing works, reading times out. All corpus work uses
the local mirror. Any earlier finding that involved *opening* a Box file needs re-confirming.

---

## P0 — before Wednesday Aug 12

| # | Task | Status | Notes |
|---|---|---|---|
| 1 | **Golden dataset** — inventory then validation join | in flight | Re-weighted by the 8-not-38 correction. One golden match already confirmed free: Crow Wing rtv-csv `7,707 CY` / `5,849 TON` vs our cached payload `GRADE 7707` / `BASE 5849`, exact. DDL to be shown, not applied |
| 2 | **Chroma hosted** | in flight | Decision doc + walkthrough. Three questions must come back answered, not UNVERIFIED |
| 3 | **Material mapping solid** | **DONE** | Commit `5972199`. Alex's 11 rulings in the seven `schema.py` descriptions; 17 docs, 0 errors, 0 unexplained diffs. Spec: `docs/_spec/2026-08-10-live-mapping-rulings.md` |
| 3b | Item-number layer | **SPEC** | `docs/_spec/2026-08-10-spec-item-number-layer.md`. Not built, per instruction |
| 4 | **Bid date and time** | in flight | Layer 1 covers 8 folders not 217. Layer 2 and Daily Ads carry the load. Chroma diagnosis required before any fix |
| 5 | **Key dates and phasing gotchas** | in flight | Phasing as a flagged gotcha with page citation and interval, not a boolean |
| — | **Do not demo an ND plan** | constraint | Strengthened, not lifted. The schema change did not demonstrably fix the 605× |
| 6 | #52 + #51 — 422s render generically; a comma in `bid_amount` gives a useless error | TODO | Demo-shaped, cheap |

### Carried over from the earlier board, still open

| # | Task | Status | Notes |
|---|---|---|---|
| 2a | Decide what `milling_sy` does with ND tons | **needs owner** | Dunn shows it concretely: `MILLING PAVEMENT SURFACE TON 63,092` + `REMOVAL OF BITUMINOUS SURFACING TON 3,915` = **67,007 tons silently dropped on one plan**. Current prose says leave null rather than convert. Needs a `milling_tons` field or a gotcha |
| 4a | **F2 report rendering, two states** | TODO | `never_matched` loud. If the UI has no branch for a gap state it must render visibly wrong, not blank |
| 5a | Extraction schema v2 — CP/SP, traffic level, city, route, gross length | TODO | Bid date and the four dates are now tasks 4 and 5. Treat the seven quantity descriptions as a reviewable mapping, not prose — they now say so in the file |

## P1 — before handoff Aug 17

| # | Task | Status | Notes |
|---|---|---|---|
| 7 | **#88 — two `00_input` directories** | TODO | **Handoff blocker.** Only one exists inside the repo today; the other is outside it. Recommend a `PLAN_INPUT_DIR` env var that fails loudly at boot |
| 8 | **#64 — anon holds INSERT/UPDATE/TRUNCATE on all 8 public tables, RLS off** | TODO | Cannot hand CSI a system whose public key can truncate the corpus. SQL is written; the work is running it as the right role and **proving the effect** |
| 9 | Repo cleanup + file taxonomy for handoff | TODO | One table: path, what it is, needed to RUN yes/no, ship/exclude/move. Separate anything containing **CSI data** from anything containing **our method** |
| 10 | Chroma local install + backup/restore for Shane | SPEC | Superseded by the 2026-08-10 hosting docs where they conflict |
| 11 | Delete the Railway bridge | TODO | Aug 17 |
| 12 | #7 — `apps/api/Dockerfile` references the pre-restructure layout | TODO | Blocks anyone else running it |
| 13 | Fix `.env`'s placeholder `ANTHROPIC_API_KEY` | TODO | A fresh machine following the README gets a 401 |
| 14 | Add `verified_at` / `verified_by` to `bid_projects` | TODO | Nothing records that a human verified a plan |
| 15 | **Spec-book Tier 1** | in flight | Confirmed already: ND uses `202 0128` / `430 0143`, **not** MnDOT's `2xxx.xxx`. Lookup must be keyed `(state, item_number)` |
| 16 | Three-way golden column — live extraction vs crosswalk vs CSI historicals | TODO | The only way to tell "we are wrong" from "they are wrong" from "we agree and both differ from the plan" |
| 17 | Fix the 22 `MILL BITUMINOUS` rows in `material_crosswalk.csv` still labelled `hma` | TODO | L1 is not ground truth |
| 18 | Benchmark table in `scratch` | in flight | Part of task 1. DDL shown, not applied |
| 19 | **Re-test Dunn through the live path's own page selection** | **TODO, new** | The differential run showed the prompt is fine and the *input text* is the suspect (`report.py:110-111` feeds only `structure["proposal_pages"]`). This is what actually decides whether ND is demo-safe |
| 20 | **Tell CSI that Stearns `milling_sy` is now 140,430, not 70,263** | **TODO, new** | Ruling #9 working as specified — FDR is now included. A number Alex validated as exact has doubled by design. Say it before it appears on screen |

## BACKLOG — good, not foundation. Do not start.

| Item | Note |
|---|---|
| **Project Estimation Checklist export** | Adam's stated pain point. Header fields map closely to what we already extract. Best demo slide on the board, and it is a feature, so it waits. Aug 13–16 at the earliest |
| **Air miles and gross length** | Shop to centre of project is filled by hand today, and `Haul.xlsx` consumes job length plus a "does haul come out to middle" flag to compute trucking cost per ton. The midpoint is an input to a cost they already calculate manually, not a map feature |
| **RAP extraction** | Straight gap. Plan quantity, a 90% availability convention, nets against mix and shouldering tons. We extract none of it. Dunn carries `RAP - SUPERPAVE FAA 43` as its main mix item, so the vocabulary is already in front of us |
| **Crushing and stockpile, reopened as checklist fields** | Closed on the evidence that under 5% of pay items mention them. That was correct about pay items and beside the point: it is a checklist question with three sub-fields the estimator answers on every job. Reopen as a checklist field, not as a bucket. Note the two `schema.py` fields were deliberately left untouched on 2026-08-10 for the same reason |
| **Addendum handling** | We have no concept of them. 180 addenda files corpus-wide, named `a1`/`a2`/`a3` consistently. **Dunn Job 23388 — the plan we keep demoing — has three.** If a plan was extracted before addendum 2 revised the quantities, our number is wrong and nothing flags it |
| **Notes & Quotes taxonomy** | 20 files in the 2023 year alone, 3 MB to 344 MB, scanned. Sample five, categorise, one page on whether there is value, stop. Easiest place on this project to spend a week and ship nothing |

**Also backlogged:** one declarative mapping source generating the other three · repo file taxonomy
and cleanup · cache demotion · F3 full-spec export · F2 four-state · rewire 19 batch writers ·
retire `csi_v2.db` · Tier 2 vision · **Tier 2 spec-book indexing** · CAD text-layer exclusion ·
multi-document model · conversion factors with CSI · front-end errors #51/#52 · `public`
drop-and-recreate to upsert · spec-book-driven aggregate class extraction · traffic level

## Owner's, not the agent's

| Task | Notes |
|---|---|
| Estimator-hours denominator | Asking CSI directly. **Do not invent one** |
| Does Supabase billing transfer to CSI after Aug 21 | Gates the pgvector option entirely |
| Batch document of open mapping questions for CSI | **After Wednesday.** Must be generated **from the live mapping** — which, as of 2026-08-10, finally carries the rulings |
| Riprap classification; crushing/stockpile exclusion | Unanswered by CSI. Recorded in code as open, deliberately not assumed |
| Does `PATCHING` count as hot mix? | New. The 2026-08-10 prose counts it (Dunn: +200 t). ND section 430 covers both `RAP - SUPERPAVE FAA 43` and `PATCHING`, which supports it. Say if you disagree |
| PG binder / tack / prime | Dunn carries `PG 58S-34 ASPHALT CEMENT TON 5,468`. Pre-read question 7 *proposed* exclusion; proposed is not ruled, so the prompt stays silent |
| The two 64,750 TON rows on `2026_BURKE-WARD-CO-ND_JOB-22484` | The `Category` column on the rtv-csv files answers this class of question where the corpus covers the project |

## Explicitly NOT doing

- Bulk rewrites of `csi_v2.db` — the archive is frozen with its version stamp
- Re-running the 11 `bid_projects` rows — LLM-fed via `_QMAP`, the crosswalk never touched them
- Pinecone; pgvector unless Supabase billing transfers
- Verb-before-noun as a general rule — tested, breaks 8 real cases
- Deleting `crushing_tons` / `stockpile_tons` — "delete nothing" stands, and CSI has not ruled
