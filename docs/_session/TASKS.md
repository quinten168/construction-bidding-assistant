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
| …but the golden set is **bigger** than 8, in a way the board never had | **26 item-level files across 4 states**: 8 `rtv-csv` (MN) + **8 `Bid Items.xlsx` (SD/ND/MN)** + **10 `Proposal_NDOT_*` (NE)**. Plus the real backbone, **the year spreadsheets: ~2,120 lettings carrying MIX TN / BASE TN / GRADE CY / MILL SY per project**, already keyed by date+time+location+state. 8 files, 772 rows, 0 parse failures | corpus sweep, all files parsed |
| "`Category` labels `Alternate A/B`, which resolves the duplicate 64,750 TON question" | **Wrong on both halves.** Zero alternate rows across all 8 files. And the 64,750 duplicate is **one bid item printed three times, once per proposal revision** — pages 7/8/9, all sheet `5 of 11`, stamped `Rev: 11/12/2025`, `Rev: 11/6/2025`, and unstamped. Not alternates, not a double count in the source | read the source pages; confirmed by Addendum 2 shifting item 002→003 |
| "909 `.msg` bid results" | **953**, on both mirrors | count |
| "the spec item number is the deterministic layer" | **MN-only.** 99.87% of golden rows carry a number (771/772), but **zero** ND or SD rows match MnDOT's `2xxx` scheme. ND uses `203.0101`/`202 0021`, NE uses `1010.01`. **ND is 35.8% of CSI's bidding** | both MnDOT patterns, full text, all 12 ND + 3 SD files |
| "217 standalone `AD.pdf`" | **8 strict, 22 with a broader matcher** (worth keeping — it finds 14 the strict glob misses). 327 addenda. Layer 1 covers ~22 folders and cannot be the main path | strict glob = 8 on both mirrors; broader matcher measured at 22 with a hit rate |
| "174 Daily Ads digests" | **Correct.** Now the biggest bid-date prize, since layer 1 covers only 8 folders | count |
| "bid date is NOT on the title sheet, only in the proposal" (old P0 #5 note) | **Wrong, already corrected on the current board.** It is in plan-set body text, and `_md_cache` page 1 of one plan reads "Letting Date: August 20, 2025 / Bids Close: 9:30 a.m. CST" | direct read |
| "the live path missed asphalt because the prompt says HMA and NDDOT writes SUPERPAVE" (`HANDOFF.md` §1, marked UNVERIFIED) | **CONFIRMED, and now fixed.** On the live path's own input, old descriptions give `hot_mix_tons = 200`, new descriptions give **121,421**. The spec books show the word HMA appears on **no ND pay item at all** | reproduced the live path's `proposal_pages` + truncation exactly, both arms |

**Box is unreadable in this environment** — listing works, reading times out. All corpus work uses
the local mirror. Any earlier finding that involved *opening* a Box file needs re-confirming.

---

## P0 — before Wednesday Aug 12

| # | Task | Status | Notes |
|---|---|---|---|
| 1 | **Golden dataset** | **DONE, 2 decisions for you** | **The headline this project has never been able to say: where extraction finds a bucketed item, the quantity is exactly right — 0.00% variance on all six bucketed items. Pooled precision 0.983, recall 0.667.** The failure mode is recall, not accuracy. DDL written, **not applied**: `docs/_spec/2026-08-10-benchmark-table.md` |
| 2 | **Chroma hosted** | **DONE, ready to deploy** | `chromadb/chroma:1.5.9` on Railway Hobby, 5 GB volume at `/data`, **no public domain**, Caddy basic-auth in front. Migration dress-rehearsed end to end: 581 MB tarball, **15–25 min**. Runner-up Fly lost because both its advantages were measured away |
| 2a | **🔴 Self-hosted Chroma 1.x has NO authentication** | **read before deploying** | Not a setting — the OSS build hardcodes a no-op authenticator. Tested against the real image: unauthenticated request → **HTTP 200**, wrong token → **HTTP 200**. The old doc's `CHROMA_SERVER_AUTHN_*` recipe is 0.x and silently does nothing. **A bare Chroma container on a public Railway domain is CSI's whole plan corpus, open.** Same failure shape as everything else here: a success signal at the wrong layer |
| 2b | Old un-prefixed hosting docs still sitting there | TODO, yours | `docs/_spec/vector_hosting.md` / `vector_hosting_setup.md` are superseded but un-flagged. Left alone deliberately — renaming them collides with the date-prefix rule. Rename or delete, your call |
| 3 | **Material mapping solid** | **DONE** | Commit `5972199`. Alex's 11 rulings in the seven `schema.py` descriptions; 17 docs, 0 errors, 0 unexplained diffs. Spec: `docs/_spec/2026-08-10-live-mapping-rulings.md` |
| 3b | Item-number layer | **SPEC** | `docs/_spec/2026-08-10-spec-item-number-layer.md`. Not built, per instruction |
| 4 | **Bid date and time** | **DONE** | Diagnosis: **retrieval, not the boilerplate filter** — the chunk is in Chroma intact, `DOWN_WEIGHT` not `DROP`, but ranks ~33rd so k=5 never sees it. Layer 1 **19/22 = 86%**, layer 2 **16/17**. Wenyu's field exists: `identity.bid_date`/`bid_time`/`bid_timezone` + layer/source/page/evidence. `apps/web` untouched |
| 4a | **Root cause worth fixing properly** | TODO | ONE `SCALAR_QUERIES` entry serves `bid_deadline` + `substantial_completion` + `final_completion`, so two thirds of the query is about completion and a 466-page proposal's completion boilerplate crowds out the one advertisement page. **P0 #5's two completion fields share the same diluted query and have no deterministic fallback — inherit this, do not rediscover it** |
| 4b | ~~Daily Ads as a bid-date source~~ | **do not build before Wednesday** | 53 of 174 have no text layer; the 121 that do yield 111 distinct closing dates and 77 Quest Numbers. The join key is real (`Quest Number` == numeric plan-set stem) but joins **1 of 202** stems — Daily Ads covers Sep 2025→Jun 2026, the numeric-stem folders are 2023 |
| 4c | Folder name beats both parsers for historical backfill | note | It caught two wrong-file-in-folder corpus errors the documents themselves could not. Consistent with the identity decision already made |
| 5 | **Key dates and phasing gotchas** | in flight | Phasing as a flagged gotcha with page citation and interval, not a boolean |
| — | **Do not demo an ND plan** | **cleared for Dunn** | The live-path test now returns 121,421 where it returned 200. One plan. SD `ASPHALT CONCRETE` still untested — test one SD plan before demoing SD |
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
| 19 | ~~Re-test Dunn through the live path's own page selection~~ | **DONE** | Done same session. Old arm 200, new arm 121,421. Follow-on: **test one SD plan** the same way, since SD `ASPHALT CONCRETE` is untested |
| 19b | **`phasing_requirements` is extracted and then thrown away** | **TODO, new** | We pay for a Claude call and drop it at payload assembly — `report.py`'s `identity_fields` and `final_report.py::_payload_from_plan_id` both omit the key. 0/12 cached payloads carry it. One-line plumbing fix, main session owns the file. See `docs/_spec/2026-08-10-phasing-gotcha.md` |
| 19c | **Binder double count is now answerable** | **TODO, new** | The spec books settle pre-read question 7: the mix ton already includes the binder in all three states, and **ND and SD bill binder separately by the TON**. Dunn carries `PG 58S-34 ASPHALT CEMENT TON 5,468`. Three of the four such items currently reach `other` via `never_matched`, i.e. flagged as a reader failure rather than a deliberate exclusion |
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

## DECISIONS WAITING ON YOU — these block or move a headline number

| # | Decision | Why it matters |
|---|---|---|
| D1 | **Benchmark scoring: is `CONVERSION_REQUIRED` a miss?** | CSI's spreadsheet numbers are unit-converted; the bid schedules' are not. Watonwan grading agrees exactly three ways (19,042), but the plan states base in CY and mix in SY while CSI states TON, and our unit-guarded bucketing emits NULL. Scoring those as misses reports a recall failure that is really the known missing conversion layer. **Moves the headline accuracy number either way** |
| D2 | **ND milling measured in TONS** | Dunn drops **67,007 tons** silently on one plan. Needs a `milling_tons` field or a gotcha. Board open item #2 |
| D3 | **Does `PATCHING` count as hot mix?** | The 2026-08-10 prose counts it (+200 t on Dunn). ND section 430 covers both `RAP - SUPERPAVE FAA 43` and `PATCHING`, which supports it. Spec books also show MN's `Bituminous Patching Mixture` matches while ND's `Patching` matches nothing, so the same work currently buckets inconsistently across states |
| D4 | **Binder / tack / prime** | Now answerable from the spec books rather than assumed: the mix ton already includes the binder in all three states, and **ND and SD bill binder separately by the TON**. Counting it would double count mass. Dunn carries `PG 58S-34 ASPHALT CEMENT TON 5,468` |
| D5 | **Load `2023 Spreadsheet.xlsx` into `bid_projects`?** | ~486 lettings of CSI bucket truth, and it holds 6 of the 8 MN bid schedules. Cheapest coverage expansion available. **Not done — it is a write to `bid_projects`, which needs your say-so** |

## 🔴 NEW SILENT-FAILURE MODE — add to the standing list

**A superseded proposal revision page is indistinguishable from a second line item, and it inflates.**
The two 64,750 TON `REMOVE AGGREGATE BASE & SURFACING` rows are **one item printed three times**,
once per revision (pages 7/8/9, all sheet `5 of 11`, two `Rev:` stamps and one unstamped). Every
other bug on the standing list under-reports; this one over-reports. Instance ten.

**Also seen this session:** a Box listing succeeds while every read of the same file times out, so a
filename sweep looks identical whether the corpus is readable or not.

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
