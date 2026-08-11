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
| 4a-i | **Query split shipped, `bid_deadline` measured within k=5** | **DONE** | `bid_deadline` now has its own `SCALAR_QUERIES` entry. Murray p.9 (the Fulda advertisement, "until Thursday, August 7, 2025, at 11:00am") went **rank 40 → rank 3**, inside the k=5 `s4_extract_rag` actually pulls. Corpus-wide hit@5 over the 33 plans that state a deadline: **12 → 20**. Completion query left **byte-identical** so those two cannot regress — verified 7/24 before and after. Cost: one extra Claude call per plan (~6 → ~7). Spec `docs/_spec/2026-08-10-bid-date-query-split.md`, coverage test `01_pipeline/test_bid_deadline_retrieval.py`, report `docs/_session/2026-08-10-bid-date-query-split.md` |
| 4a-ii | **`substantial_completion` + `final_completion` need the same split, and have no deterministic fallback** | **TODO, not started tonight — owner's explicit instruction** | They keep the old diluted query. Measured on the same corpus: hit@5 **7/24 (29%)**, and the chunk that actually STATES the date has a **median rank of 37** — Murray's is 71st. Six alternative completion queries were measured and **none beat the incumbent at hit@5**, so unlike `bid_deadline` this is not fixed by rewording: the completion date is stated in far more varied places (EJCDC Article 4 Contract Times, an SD project-manual cover, an ND "Contract Time:" clause) than the bid date is. Whoever picks this up should expect to need a deterministic layer like `04_tools/bid_date/`, **not** a better query. Do not rediscover the diagnosis — it is in `docs/_session/2026-08-10-bid-date.md` §2 and re-measured in the query-split report |
| 4a-iii | **`CONFIDENCES` in `schema.py` is stale as of upstream #90** | note, not fixed | #90 (`origin/main`, not merged locally) changed `SCALAR_PROMPT` to emit only `high`/`low` plus a `reason`, but `schema.CONFIDENCES` still accepts `"medium"` and `_coerce_cell` still lets it through. Nothing emits it today, so it is not a bug — it is a value that can never occur being treated as valid. `schema.py` was owned by another agent this round, so flagged not fixed |
| 4a-iv | ~~**CONFIDENCE LEVELS — open, and client-facing**~~ | **ANSWERED by #90, stop calling it open** | Upstream now defines them: **high = stated verbatim in the source text** (or an unambiguous line-item sum), **low = inferred, interpreted or uncertain**, each with a one-sentence `reason` surfaced in the verify UI. That is a real answer for Wednesday |
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

## MERGE + PUSH — done 2026-08-10 late. What is now on `origin/main`.

`origin/main` was 9 commits ahead; merged once at `3f91d97`, pushed `f52226b..82d132f`. 0 ahead,
0 behind. 69 files, 1.2 MB, code and docs only — no PDFs, and **no commit of ours touches
`data/processed/`**.

**Two conflicts, both "keep both".** `final_report.py` imports (kept `payload_carry` *and*
`plan_reader_bridge`), and `predict_competitors` — **flatten before cap, and the order is
load-bearing**: slicing a list of objects truncates fine and still crashes the renderer, because it
is the SHAPE that breaks it, not the length. `report-card.tsx` took upstream's body (#90 removed the
match-confidence chip) and kept our `export` (the react-dom/server test needs it) and the flatten.

**Rulings verified intact after the merge:** all 16 ruling tokens present across the five
descriptions, milling capture fields present, `crushing_tons`/`stockpile_tons` byte-identical.
Re-warm through the real live path confirms it end to end — Stearns `MILL` **140,430**, Dunn `MIX`
**121,421**, `MILL` **408,216**, `BASE` **6,506**, `MILL_TON` **67,007**.

| # | Item | Status | Notes |
|---|---|---|---|
| M1 | **10 of 12 cached payloads are still stale** | **decision for you** | Only Stearns and Dunn were re-warmed — the two you named. The other 10 still serve pre-ruling numbers instantly with no signal. **If any of them is on the demo path it will show old numbers on stage.** Re-warming all 12 is ~20 min and a few dollars; say the word. `python tools/2026-08-10_rewarm_demo_cache.py --check` lists them with mtimes |
| M2 | Mapping-version cache key | **SPEC, build post-demo** | `docs/_spec/2026-08-10-payload-cache-key-versioning.md`. Hash the seven descriptions into the key so old entries stop being *found* rather than being destroyed. The "version field inside the payload" variant was rejected: absent-means-current is one sign flip from re-creating this exact bug |
| M3 | **The push bypassed a branch-protection rule** | **your call** | GitHub replied *"Bypassed rule violations for refs/heads/main: Changes must be made through a pull request."* You asked for a push and it went straight to `main` on admin rights. Worth knowing before the next one, and worth deciding whether agents should use PRs |
| M4 | `bidder_results.csv` local mods are stashed, not lost | pending | Pre-existing local modifications blocked the merge (origin changed the file in #97). Stashed rather than discarded: `stash@{0}`, message `2026-08-10 pre-merge: local bidder_results.csv mods`. Origin's version is what is checked out now. Decide whether to drop the stash or re-apply |
| M5 | **Post-Wednesday: `data/processed/bidder_results.csv` history purge** | **TODO, post-Wednesday** | It is tracked and has been in history since PR #46, so untracking now removes nothing from the remote and adds risk. A proper fix is a history purge (`git filter-repo`/BFG), a force-push, and coordination — none of which happens this week. **Pair it with a CSI conversation**: this is CSI's competitor bid data sitting in a GitHub repo, which is a "what may we ship / what must stay private" question, not just a git one. Related: the repo-taxonomy task already on the board wants CSI *data* separated from our *method* |
| M6 | Two test suites cannot run on the same interpreter | TODO | `.venv` has `chromadb` but **cannot open `csi_v2.db`** (iCloud symlink) — 14 phasing tests error. `python3` opens the DB but **lacks `chromadb`** — 6 retrieval tests error. Each group passes on the interpreter that has its dependency (11/11 and 39/39). **Both cases ERROR rather than SKIP**, so "the dependency is missing" and "the test failed" look identical to anyone reading CI — the standing rule, in the test harness itself |

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

## 2026-08-10 — D1 and D2 are BUILT (appended by the milling unit-capture agent)

Report: `docs/_session/2026-08-10-milling-unit-capture.md` · Spec:
`docs/_spec/2026-08-10-milling-unit-capture.md`

- **D2 (ND milling in TONS) — done on the extraction side.** New `milling_tons` + a closed-vocabulary
  `milling_measured_unit` (`SY`/`TON`/`SY+TON`/`OTHER`/`NONE`/null), plus a derived
  `schema.milling_unit_status()` with seven explicit states. **Dunn now returns
  `milling_sy = 408,216` AND `milling_tons = 67,007`** — nothing converted, no depth assumed.
  Per-unit subtotals rather than one (value, unit) pair, because Dunn is SY and TON simultaneously.
- **No-regression: MN/SD `milling_sy` did not move** (Stearns 140,430, Crow Wing 15,067, SD
  `not_present`). Two ND movements declared: Fargo `milling_sy` +14 (0.007%, stable across repeat
  runs, baseline is the correct sum) and Dunn `grading_quantity` (noisy on that document
  independently of this change).
- **D1 (`CONVERSION_REQUIRED`) — implemented as its own category** in
  `tools/golden/2026-08-10_golden_join.py`: out of `matched` and out of **both** denominators, no
  variance, own `conv` column. Pooled 0.667 / 0.983 unchanged; `conversion_required = 0` today
  because the golden set is MN-only. Covered by `tools/golden/2026-08-10_test_conversion_required.py`
  (walks all 1,891 corpus unit strings; caught `S.Y.` normalising to unknown on its first run).
- **STILL NEEDS THE OWNER:** the payload-assembly edit to `report.py` (spec §5.1) — a `MILL_TON`
  quantities row and `milling_unit_status` on identity. Deliberately **not** applied; `report.py` was
  owned by other agents. The label must not be `MILL`: that label is written into the column named
  `mill_sy` and into a competitor-model feature, neither of which reads `mill_unit`.
- **Still open:** the conversion factor itself (needs CSI), and a `mill_tons` column in
  `bid_projects` (DDL). Until then the tons value reaches the report but not the database.

## 2026-08-10 — task 2b placed-material conversion is SPEC'd, NOT built (appended by the 2b agent)

Spec: `docs/_spec/2026-08-10-placed-material-conversion.md`. **No code written. No `.py` file in this
repo gained a multiplication from this task.** Sits ON TOP of task 2a
(`docs/_spec/2026-08-10-tons-bucket-unit-capture.md`, already shipped in `schema.py`), never replaces it.

- **All three of CSI's numbers on plan 9786015 reproduce from the proposed factors.** Mix 1,901.34 t
  (Δ −0.002 against CSI's total), base 3,851.75 t (exact), shoulder 13.09 t (exact to 2 dp).
  Arithmetic shown line by line in spec §10.1. **CSI's per-item 909.86 is a rounding artifact, not a
  factor problem** — CSI's own four per-item figures sum to 1,901.32 while their stated total is
  1,901.34, which is exactly the unrounded computation. No factor was adjusted to fit.
- **Proposed factors, for ALEX to bless — not decided here:** bituminous mix **113 lb/SY per inch**;
  Class 5 base **3,100 lb/CY (1.55 ton/CY)**; shoulder = SY × depth ÷ 36 → CY, then the base factor.
  None has an external citation in this repo. They reproduce what CSI *used*; that is not evidence of
  what CSI *endorses*.
- **The gate is class-based, not depth-based.** `Class 5 Aggregate Base | 2,485 | CY` needs no depth
  (CY is already a volume) and is the largest tonnage on the plan; a depth gate would refuse it.
  Conversely `Mill Bituminous Surface (2.0")` HAS a depth and must never convert.
- **Depth availability, measured on `csi_v2.db` v2 (6,385 rows, 66 plans, noise-filtered):** genuine
  placed-mix SY rows state a depth **15/16 = 93.8%**; raw `hma`+SY is 15/19 = 78.9% and **the 4
  misses include a removal, an FDR and a seal coat that the bare `BITUMINOUS` keyword mis-routes into
  `hma`** — reported as a finding, not fixed. Placed base is mostly CY (no depth needed); 11 of the
  16 base+SY rows are FDR, which ruling #9 excludes anyway. **Most of the corpus already states TON**
  (hma 71/177, base 41/94), so this is a minority-case fix with a large per-plan effect.
- **Flag design so "not ready" is automatic:** `enabled = G1_blessed and G2_reproduces and
  operator_opt_in`, computed not configured. An unsigned factor table leaves `blessed_by` empty,
  which is False, which is off. Off emits status `disabled` — never `none_converted`, never null.
  **Recommendation: ship Aug 12 with opt-in unset even if both gates pass** — 9786015's `hot_mix_tons`
  going null → 1,901 is a visible change on a plan CSI knows by hand (same lesson as P1 #20/Stearns).
- **Rulings sit ABOVE conversion.** `milling_sy` / `milling_tons` must be bit-identical before and
  after; that is blocking test A7. FDR and milling are protected structurally (no milling class in the
  blessed table), not by a bolted-on special case.
- **Two board corrections.** (a) `quantity_crosswalk.py::CSI_OPEN_QUESTIONS_2026_08_07` literally
  contains only `["riprap classification", "crushing/stockpile exclusion"]` — the aggregate-surfacing
  question lives in the live-mapping spec, not in that constant. (b) The "67,000 T in `shldr_tons`"
  figure does not reproduce against the current store: `csi_v2.db` v2 shows **18 rows / 33,771 TON**
  of `AGGREGATE SURFACING` (bucket total 57,173 T). Not reconciled; does not affect the spec. The
  bucket question is **noted and NOT resolved** — all 18 rows are already in TON, so it is a ruling,
  not a conversion.
- **`bucket_hierarchy.csv`'s 1.75 Ton/CY and SDDOT's 1.50 tons/CY are NOT interchangeable with these**
  and must never be harmonised — placed vs removed vs salvaged, three states, three provenances
  (unsourced / citable / client-signed). Full table in spec §12. Third document to say this.
- **Flagged, not fixed (other agents' files):** `schema.py`'s *"no verified depth or density factor
  exists"* is the right conclusion for the wrong stated reason — **21 of 79 milling rows DO state a
  depth**. Removals stay unconverted because CSI ruled the bucket and unit, and because no removal
  *density* factor is verified. Two reasons, neither of them "depth unknown".
- **CSI's historical 1,850 t vs the computed 1,901.34 t (2.8%) is NOT an acceptance criterion** — it
  is plan quantity vs CSI's spreadsheet, exactly what P1 #16's three-way column exists to explain.
  Do not tune a factor toward 1,850.

## Explicitly NOT doing

- Bulk rewrites of `csi_v2.db` — the archive is frozen with its version stamp
- Re-running the 11 `bid_projects` rows — LLM-fed via `_QMAP`, the crosswalk never touched them
- Pinecone; pgvector unless Supabase billing transfers
- Verb-before-noun as a general rule — tested, breaks 8 real cases
- Deleting `crushing_tons` / `stockpile_tons` — "delete nothing" stands, and CSI has not ruled
