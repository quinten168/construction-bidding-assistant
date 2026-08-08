# TASKS — the board

Last updated **2026-08-08**. Committed so it stops living in chat.
Read `HANDOFF.md` first. Dates: **presentation Wed Aug 12** · **CSI IT handoff Mon Aug 17** ·
**program ends Fri Aug 21**.

Status: `TODO` · `SPEC` (written, awaiting approval) · `BLOCKED` · `DONE`

---

## P0 — before Wednesday Aug 12

| # | Task | Status | Notes |
|---|---|---|---|
| 1 | **Add state vocabulary to the seven `schema.py` field descriptions** (SUPERPAVE / ASPHALT CONCRETE / BITUMINOUS / RAP), re-drop Dunn, confirm 121,221 appears | TODO | ~1 hour. The 605× asphalt miss. ND is 35.8% of CSI's bidding. **Highest value item on this board.** |
| 2 | Decide what `milling_sy` does with ND tons | TODO | Real open question, not a bug — the field name bakes in SY, NDDOT states TON. Pre-read open question #2 |
| 3 | Do not demo an ND plan until 1 is done | — | Constraint, not a task |
| 4 | **F2 report rendering, two states** | TODO | `never_matched` loud. Four-state needs the drop path to adopt the crosswalk — out of scope. **If the UI has no branch for a gap state it must render visibly wrong, not blank** |
| 5 | Extraction schema v2 — bid date+time, CP/SP, traffic level, city, route, gross length | TODO | ONE change, sample-tested. Note: bid date is NOT on the title sheet (it is in proposal front matter); gross length is what midpoint needs and rarely has. Treat the seven descriptions as a reviewable mapping, not prose |
| 6 | #52 + #51 — 422s render generically; a comma in `bid_amount` gives a useless error | TODO | Demo-shaped, cheap |

## P1 — before handoff Aug 17

| # | Task | Status | Notes |
|---|---|---|---|
| 7 | **#88 — two `00_input` directories, runtime points at the near-empty one** | TODO | **Handoff blocker.** Recommend a `PLAN_INPUT_DIR` env var that fails loudly at boot. Blocks any rebuild-from-source |
| 8 | **#64 — anon holds INSERT/UPDATE/TRUNCATE on all 8 public tables, RLS off** | TODO | Cannot hand CSI a system whose public key can truncate the corpus. SQL is written; the work is running it as the right role and **proving the effect** |
| 9 | Repo cleanup + file taxonomy for handoff | TODO | One table: path, what it is, needed to RUN yes/no, ship/exclude/move. Explicitly separate anything containing **CSI data** from anything containing **our method**. Knowledge docs, markup history, pre-reads move to the personal repo |
| 10 | Chroma local install + backup/restore procedure for Shane | SPEC | `docs/_spec/vector_hosting_setup.md` |
| 11 | Delete the Railway bridge | TODO | Aug 17. ~$5/mo Hobby, not free after trial |
| 12 | #7 — `apps/api/Dockerfile` references the pre-restructure layout and cannot build | TODO | Blocks anyone else running it |
| 13 | Fix `.env`'s placeholder `ANTHROPIC_API_KEY` and document real setup | TODO | A fresh machine following the README gets a 401 |
| 14 | Add `verified_at` / `verified_by` to `bid_projects` | TODO | Nothing anywhere records that a human verified a plan, so "the DB is the verification" is false until it exists |

## P1 — post-Wednesday, pre-handoff if time

| # | Task | Status | Notes |
|---|---|---|---|
| 15 | **Spec-book Tier 1** — extract MEASUREMENT and BASIS OF PAYMENT clauses per section per state into a lookup | TODO | The three 2025 spec books are in `05_knowledge/`. Replaces the corpus-majority unit guess with **ground truth** and answers the FDR unit question. Also gives the **state-naming crosswalk** (MN BITUMINOUS / SD ASPHALT CONCRETE / ND SUPERPAVE) that item 1 needs. Does not require indexing 3,000 pages |
| 16 | Golden dataset column — three-way: live extraction vs crosswalk vs CSI historicals | TODO | The only way to tell "we are wrong" from "they are wrong" from "we agree and both differ from the plan". Shape of the benchmark table. Overlap measured: **60 of 64** plans (county+state), so the gate passes — but match quality is weak and needs the identity design |
| 17 | Fix the 22 `MILL BITUMINOUS` rows in `material_crosswalk.csv` still labelled `hma` | TODO | Published to Postgres as a table. **L1 is not ground truth** — it needs the same coverage testing as L2 |
| 18 | Benchmark table in `scratch` | TODO | Measurement the app produces, re-runnable so accuracy can be watched |

## P2 — post-handoff / nice to have

| # | Task | Status | Notes |
|---|---|---|---|
| 19 | Mapping architecture — L1 lookup → L2 keyword → L3 LLM → L4 confidence gate | SPEC | `docs/_spec/mapping_architecture.md`. Lead with: **40.7% of rows is 83–99% of the QUANTITY** — the heuristic handles big-ticket items, the lookup handles the tail. Inverts the usual assumption |
| 20 | Cache demotion — keep it as a speed layer, strip the verification role | SPEC | `docs/_spec/cache_to_db_migration.md`. Depends on 14 |
| 21 | Spec-book Tier 2 — index all three books so gotcha queries resolve spec references | TODO | Plans cite 2360/2211/2118; we index what the plan SAYS, not what the spec REQUIRES. Carries fractured-face-by-traffic-level, the pit-selection link. **Caveats: 2025 editions vs 2023-24 plans (numbering drift), and check whether ND/SD use MnDOT's 2xxx scheme at all — if not, per-state key** |
| 22 | #85 CAD/mojibake chunk filter · #58 doc_id namespace split | TODO | Both fixed free by a `--reset` rebuild — **blocked by #7/#88** |
| 23 | #67 / #68 — publish `sections`, `section_intelligence` | TODO | **Not handoff blockers** (owner, 2026-08-08). CSI does not need them to RUN, only to rebuild the vector store later |
| 24 | Tier 1 vision for scanned plan sets | TODO | Proven: 8/8 fields, **$0.0339/plan measured**. Blocked on #84 (`temperature=0` 400s on Opus 5). Title sheet carries an INDEX OF PLAN SHEETS that takes Tier 2 from ~$2.40 to ~$0.15 |
| 25 | Close ~9–10 obsolete issues | TODO | Matters for handoff credibility. See `issues.md` |

## Owner's, not the agent's

| Task | Notes |
|---|---|
| Estimator-hours denominator | Asking CSI directly. **Do not invent one.** Measured cost side: chat **$0.190/plan**, vision **$0.0339/plan**; extraction cost is **unmeasured** (`s3_extract`/`s4_extract_rag` log no tokens) |
| Does Supabase billing transfer to CSI after Aug 21 | Gates the pgvector option entirely |
| Batch document of open mapping questions for CSI | **After Wednesday.** Must be generated **from the live mapping**, not the pre-read — Alex marked up a document generated from an artifact that does not run |
| Riprap classification; crushing/stockpile exclusion | Unanswered by CSI. Recorded in code as open, deliberately not assumed |
| The two 64,750 TON `REMOVE AGGREGATE BASE & SURFACING` rows on `2026_BURKE-WARD-CO-ND_JOB-22484` | Same plan, different item numbers and pages. Base-bid/alternate pair or a double-count — needs an estimator's eye |

## Explicitly NOT doing

- Bulk rewrites of `csi_v2.db` — the archive is frozen with its version stamp
- Re-running the 11 `bid_projects` rows — they are LLM-fed via `_QMAP`, the crosswalk never touched them
- Pinecone; pgvector unless Supabase billing transfers
- Verb-before-noun as a general rule — tested, breaks 8 real cases
