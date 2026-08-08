# Open issue register — csi-bid-intelligence

Generated 2026-08-07 from `gh issue list --state open` (53 open issues) plus a code-level
cross-check. **Self-contained: no GitHub access needed to read this.**

Summaries are written here, not copied from issue bodies. Anything asserted as "fixed" was checked
by reading the code, and the file/line evidence is given. Where it could not be checked, it says so.

**Grouping is by area of the system** (7 groups). Each group is one table. Labels are the repo's own
(`p0`/`p1`/`p2` = the owner's older priority scheme; `needs-triage` = filed but never sorted;
`blocked`, `decision`, `ready-for-human`, `ready-for-agent`).

---

## 1. Material / quantity mapping correctness (6)

The system reads a PDF and reports how much asphalt, base, milling etc. a job contains. This group is
about those numbers being wrong.

| # | Title (short) | Labels | One-line summary |
|---|---|---|---|
| 83 | `RECLAIM` never matched `RECLAMATION` | needs-triage | A keyword typo meant 1,235,282 SY of Full Depth Reclamation across 14 plans reported as zero; fixed in the working tree, not yet committed. |
| 85 | 12.6% of vector store is CAD/mojibake noise | needs-triage | 11,133 of 75,080 search chunks are unretrievable CAD elevation dumps or control-byte garbage; a 100%-precision filter exists because `is_drawing` is already computed and never read at index time. |
| 86 | 300s convert timeout is mis-diagnosed | needs-triage | The PDF-conversion timeout was blamed on "pathological" files; profiling shows it just cuts off large plan sets — two PDFs that succeeded extrapolate to 542s and 1111s. |
| 84 | `temperature=0` blocks the vision path | needs-triage | Extraction hardcodes a parameter newer Claude models reject with a 400; dormant on the current model, fires the moment the scanned-plan vision path is built. |
| 71 | `bid_deadline` is rarely extracted | needs-triage | 6 of 7 processed plans have no bid date at all — a coverage gap in extraction, not a parser bug (the parser ran once and was correct). |
| 70 | Title-sheet extraction is the critical path | needs-triage | All 7 plans written to the database carry provisional keys because the city is unknown; the whole route→milepost→lat/lon→city chain works but never starts, for want of title-sheet fields. |

## 2. Project identity and the plan_reader ↔ CI-model seam (12)

Two halves of the product (PDF reader, competitor model) meet at a join key. This group is that seam.

| # | Title (short) | Labels | One-line summary |
|---|---|---|---|
| 10 | Specify the plan_reader→CI contract | p0 | Write down the field-level interface between the two modules so neither side can change output silently. **Likely done — see §9.** |
| 13 | `process_pdf` writes its record to `csi_v2.db` | p0, blocked | Make a dropped plan land in the database instead of a JSON cache. **Obsolete destination — see §9.** |
| 14 | `final_report.assemble` reads from the database | p0, blocked | Once the writer moves, the report must read the same store rather than a parallel source. Partially true today. |
| 15 | Demote `_report_payload_cache` to a speed cache | p0, blocked | The JSON cache is currently the only copy of some records, i.e. an undocumented database; re-key it on content hash so deleting it is safe. |
| 33 | Add contract record columns to `csi_v2.db` | p0, ready-for-human | Expand-only schema migration on the 160 MB SQLite file, with a mandatory verified backup first. |
| 35 | Road-name `sp_number` yields a key that joins to nothing | decision, ready-for-human | The contract's "no digits ⇒ no key" rule misses 15 road-name project numbers (`CR-12`, `CSAH-2`) that produce valid-looking keys matching nothing; needs a written decision. |
| 36 | Extract record assembly + upsert from `process_pdf` | p0, blocked, ready-for-agent | Pure refactor so assembly and writing are separately testable. **Landed — see §9.** |
| 37 | `process_pdf` writes to `scratch.bid_projects` | p0, blocked, ready-for-agent | The Postgres version of #13, with the write placed outside the cache short-circuit. **Landed — see §9.** |
| 38 | Backfill `join_key` / `plan_uid` on 117 batch rows | p0, blocked, ready-for-human | Every historical corpus row gets a key or a stated reason it has none; 6 rows have no source PDF so no content hash can exist — needs a nullability decision. |
| 39 | Stamp `join_key` on the live path and prove parity | p0, blocked, ready-for-human | Prove the live and batch paths produce identical keys for the same plan, using stored values rather than re-running paid extraction. |
| 40 | `export_ci_input.py` produces the contract's §4 CSV | p0, blocked, ready-for-human | The actual seam artifact: one CSV per run that the CI model consumes unmodified, carrying `row_status`/`missing_fields` so missing never silently becomes zero. Not built. |
| 41 | When are two PDFs one project? | decision, ready-for-human | A DOT letting publishes proposal and special provisions separately; file identity ≠ project identity, and the store has no rule. Domain question for CSI, not code. |

## 3. Database migration, publishing, and schema drift (9)

| # | Title (short) | Labels | One-line summary |
|---|---|---|---|
| 9 | Stand up hosted Supabase, publish structured tables | p0 | Give the team read access to extracted plan data instead of one laptop. **Done — see §9.** |
| 50 | Retire SQLite entirely (phases 2–5) | p0 | Only the 3 runtime app touchpoints were repointed to Postgres; 19 batch tools, and the only copies of three large tables, still live in `csi_v2.db` on one machine behind an iCloud symlink. |
| 67 | Publish `sections` (37,261 rows) | needs-triage | ~1 hour; blocked on a per-column payload-guard exemption because 74.9 MB of raw text blows a 10 MB tripwire. |
| 68 | Publish `section_intelligence` | needs-triage | ~1 hour; 18 rows held out purely by a column typed REAL that stores "Y"/"" text. |
| 69 | Publish `plans.full_markdown` | needs-triage | ~half a day; 75.3 MB, needs per-column byte accounting so the payload guard survives rather than being raised globally. |
| 62 | `bid_projects.updated_at` never moves | needs-triage | No ON UPDATE trigger, so the column records insert time; one of three writers now sets it explicitly, the other two do not. Spans another team's code. |
| 63 | `BID_PROJECTS_DDL` is fiction | needs-triage | The code declares 19 columns; the live table has 59. `create table if not exists` never reconciles, so the drift is invisible from the source. |
| 57 | Verify PR #46's `bid_time` DDL against live schema | needs-triage | Was PR #46 redundant, and does it revert the `job_id` removal? **Premise overtaken — see §9.** |
| 55 | Keep `ON DELETE CASCADE` on `bid_results`? | — | Deleting one project row silently deletes its hand-entered bid results; not blocking anything today, but a live footgun for the next cleanup script. Another team's call. |

## 4. Security and access control (1)

| # | Title (short) | Labels | One-line summary |
|---|---|---|---|
| 64 | `anon`/`authenticated` hold write+TRUNCATE on all 8 public tables, RLS off | needs-triage | Anyone with the project's public API key can truncate the plan corpus over HTTPS; the fix SQL is written (`04_tools/revoke_anon_write.sql`) but a REVOKE issued by the wrong role silently does nothing. |

## 5. Application, API, and UX robustness (5)

| # | Title (short) | Labels | One-line summary |
|---|---|---|---|
| 51 | Comma in `bid_amount` gives a useless error | p1 | Typing `1,200,000` produces "Could not save bid results." with no hint; the create path lacks the separator-stripping the inline-edit path already has. |
| 52 | No `RequestValidationError` handler | p1 | Every FastAPI 422 returns a shape the frontend can't read, so all validation failures render as one generic string while the real reason sits in the server log. |
| 61 | `gotcha_source` still emits the literal `'sqlite'` | needs-triage | After the Postgres move the provenance value lies about the storage engine; renaming crosses a process boundary (backend branches on it, TS types it), so it was deferred deliberately. |
| 28 | Populated plans but empty gotchas still reports a confident zero | p2 | Known accepted limitation: the corpus guard checks `plans`, but the readers query `gotchas`/`plan_metrics`, so a partially ingested corpus still shows "0 gotchas" as if it were a fact. |
| 19 | Audit tool reachability: six defined, four in the system prompt | p1 | Two agent tools including `record_correction` may be unreachable except when a plan is active; a defined-but-unreachable tool reads as a capability that doesn't exist. |

## 6. Environment, infrastructure, and indexing hygiene (7)

| # | Title (short) | Labels | One-line summary |
|---|---|---|---|
| 53 | `apps/api` cannot start on Python 3.9 | p0 | `road_midpoint.py` used PEP 604 syntax at import time, killing the whole report path. **Fixed — see §9.** |
| 54 | Two `.env` loaders with different parsing rules | p2 | A hand-rolled single-quote parser and `python-dotenv` both read `.env`; the same file means two things, and the quoting requirement is invisible until it bites. |
| 58 | Two writers disagree on `doc_id` | needs-triage | Every web upload indexes a plan a second time under a different id with blank provenance: 10,046 redundant chunks, growing, and metadata-filtered searches silently see half the corpus. |
| 59 | Consolidate-scope test cannot pass | needs-triage | The one test that proves a competitor rename doesn't touch bid results inserts two rows with the same primary key — no database state can make it green. |
| 60 | MN route lookup skips every US-numbered route | needs-triage | Only Interstate (01) and State Trunk Highway (03) route IDs are tried, so US 71/2/10/169/212 never resolve to coordinates and the failure is indistinguishable from "route not found". |
| 7 | `apps/api/Dockerfile` cannot build | — | Every `COPY` points at a pre-restructure layout, and one copies the 1.5 GB gitignored vector index, so fixing it means deciding how the index ships — not a rename. |
| 6 | Nine CWD-relative `reference/` path defaults | — | Paths resolve against the working directory, so running a script from inside `data/` silently reads a different CSV of the same name. **Mostly overtaken — see §9.** |

## 7. Process, mapping-of-the-code, and housekeeping (13)

| # | Title (short) | Labels | One-line summary |
|---|---|---|---|
| 65 | PATTERN: operations that report success and do nothing | needs-triage | Five collected instances (dead subprocess behind an HTTP 200, DOT outage read as "route not found", a REVOKE that changes nothing, `create table if not exists`, a clean dry-run that hid a failing write); wants one standing mitigation, not five fixes. |
| 72 | plan_reader rows can never reach the CI model | needs-triage | The only Postgres→CSV sync walks the local file and skips rows it doesn't already have, so a newly read plan is structurally incapable of entering the training set. |
| 73 | Recomputing provisional keys needs MERGE, not UPDATE | needs-triage | Once title-sheet extraction fills in the missing key components, keys will collide with existing CI rows by design — that needs a column-level precedence table, not a bare UPDATE. |
| 66 | Stamp `project_natural_key` on Chroma chunks | needs-triage | The documented join key `contract_id` is blank on all 73,070 chunks, so a seam the README promises does not exist. |
| 11 | Build the materials→2026 capacity path | p0 | Capacity is computed from 2024/2025 data only, and extracted materials are display-only; this is new code, not a wiring task. Client requirement. |
| 22 | Move local Chroma to Supabase pgvector | p2, blocked | Production search depends on a 1.5 GB local index on one machine; listed as blocked by #9, which is now done. |
| 16 | Function-to-file map | p1 | No map from promised functions to implementing files and triggers, so nobody can say what is load-bearing. |
| 17 | Deletion pass | p1, blocked | Remove code not tied to a promised function; blocked by #16 because "this looks unused" is how load-bearing code gets deleted. |
| 18 | Trace who sets `--no-llm` | p1 | If any program sets it, some path runs without the LLM and its output means something different from what a reader assumes. |
| 20 | `research/sweet_spot` scripts cannot be re-run | p2 | 7 regeneration scripts point at a directory that no longer exists; invisible because the outputs are committed. |
| 21 | Remove em dashes from `docs/ARCHITECTURE.md` | p2 | Pure punctuation sweep, to be kept in its own PR. **Count has grown — see §9.** |
| 23 | Decision: share the eval harnesses with the team? | decision | Both harnesses are already in the team repo, so "private" means actively removing them. |
| 24 | Decision: extract a data dictionary into `docs/`? | decision | Check overlap with the existing `golden_dataset_dictionary.md` first; two dictionaries drift and then neither is trusted. |

---

## 8. What the board actually is (reconstructed)

There is no formal task board. This section is assembled from, and only from:

1. `docs/_session/latest_report.md` (= `2026-08-07_coverage-test-and-milling.md`), session report 3 of 3 today
2. `docs/_session/2026-08-07_crosswalk-and-vision.md` and `2026-08-07_remap-run.md`
3. `docs/_spec/mapping_architecture.md` (dated 2026-08-07, marked "SPEC ONLY, nothing built")
4. `docs/2026-08-03_handoff.md`
5. `git log --oneline -40`
6. `CLAUDE.md` §"Known rough edges" (7 entries)

**The live work stream, in the owner's own labels:**

| Label used in session reports | What it is | State per the reports |
|---|---|---|
| P0 | SPEC_MAP coverage test | **Built** (`05_knowledge/test_quantity_crosswalk.py`, 67 passed / 1 xfailed) |
| (a) | Verified backup of `csi_v2.db` | Done, `/Users/t/Desktop/csi_v2_backup_2026-08-07.db`, integrity ok |
| (b) | Re-map 66 plans against the corrected crosswalk | Done — milling +421%, base −199,378 tons |
| (c) | Republish corpus to Postgres | **BLOCKED** — needs the `postgres`-role DSN; only a `csi_team` DSN exists on the machine |
| (d) | Confirm the app shows the new numbers | Blocked by (c) |
| P1 | cache→DB migration | **Not started — PROTECTED** |
| P2 | F2 report rendering (always show buckets + gap reason) | **Not started — PROTECTED** |
| P3 | extraction schema v2 | **Not started — PROTECTED** |
| P4–P8 | unstated in the report | Not started |
| F1 / F3 | regenerate; audit/trust export | Not started |
| N3 | Tier-1 vision for scanned plan sets | Proved with one real call (8/8 fields, $0.0339); not built |

**Everything in today's three reports is uncommitted.** `git status` shows
`quantity_crosswalk.py` modified and `test_quantity_crosswalk.py` untracked. The last commit is
`2a3730f` (pit-map markers).

---

## 9. Flags, with evidence and confidence

### 9.1 Already resolved but still open (5, plus 2 partial)

| # | Verdict | Evidence (code, not commit messages) | Confidence | What would confirm |
|---|---|---|---|---|
| 53 | **Resolved — close** | `road_midpoint.py:18` now has `from __future__ import annotations`; `pyproject.toml:16` sets `requires-python = ">=3.10"`. Handoff attributes it to `f3e7f68` and says it was left open only pending a teammate's traceback. | **High** | The teammate's actual traceback, which the handoff says was never received. |
| 36 | **Resolved — close** | `pipelines/plan_reader/01_pipeline/bid_projects_record.py` + `test_bid_projects_record.py` exist; assembly (`build_record`, `mapped_columns`) is separate from the write. | **High** | — |
| 37 | **Resolved — close** | `apps/api/backend/report.py:322-344` `write_bid_project()` calls `bpr.build_record` → `bpw.upsert`; `apps/api/backend/bid_projects_writer.py` exists. It has run for real: issue #70 reports 7 rows in `scratch.bid_projects`, and commit `43e60b2` says "seven plan_reader rows in bid_projects". | **High** | — |
| 9 | **Resolved — close** | `publish_to_supabase.py:76` publishes all five tables the issue names plus three lookup tables; handoff confirms `public` holds the 8 tables and `csi_reader` has SELECT. | **High** | A SELECT executed as `csi_reader` (the handoff warns `information_schema.role_table_grants` produced a false negative here once). |
| 57 | **Overtaken — close** | PR #46 is merged (`fe7ec5a`), and it landed exactly the recommended shape: a 2-line population change in `build_project_competitor_panel.py:229` (`bid_time=("TIME","first")`) with **no `job_id` column reintroduced** (grep finds `job_id` only in a comment in `push_supabase_bid_data.py:11-14` explaining its removal). | **High** on the outcome; **Medium** that anyone actually diffed the DDL types as the issue asked. | Nothing further — the residual DDL-drift concern is #63, which stays open. |
| 10 | **Probably resolved** | `docs/2026-08-03_bid_projects_mapping.md` plus `pipelines/plan_reader/01_pipeline/bid_projects_mapping.yaml` and `join_key.py` are a written, field-level, both-sides contract; the handoff records six settled mapping decisions against it. Note the commit that says "land the seam contract" (`2a3c1b9`) actually added two *other* docs, so the naming is confusing. | **Medium** | The owner confirming the mapping doc is what #10 asked for. Do not close on this report alone. |
| 14 | **Partial only — keep open** | `final_report.py` now reads `public.gotchas`/`plan_metrics` from Postgres (`:101/:143/:311`, commit `310e321`), so *some* of it reads a database. But the plan record itself still comes from the JSON payload cache, which is the actual point of the ticket. | **Medium-high** | Trace which store `assemble()` uses for the plan record on a cache hit. |

**Not resolved, checked and still broken** (so nobody wastes time re-verifying): #60 (`road_midpoint.py:106-109` still builds only route systems 01 and 03), #52 (no `RequestValidationError` anywhere in `apps/api`), #51 (`use-bid-results-store.ts:127` still `Number(e.bid_amount)`), #59 (`test_competitor_registry_admin.py:136-140` still inserts two rows on one PK), #63 (`push_supabase_bid_data.py:53-76` still declares 19 columns), #66 (`s2_indexer.py:100` still stamps `contract_id`), #61 (`final_report.py:315,320,579` still emit/branch on `'sqlite'`), #7 (Dockerfile still `COPY 02_modules/…`), #64 (`revoke_anon_write.sql` exists, unrun), #84 (`s3_extract.py:135` still `temperature=0`).

### 9.2 Duplicates / overlapping pairs (3)

| Pair | Call | Evidence | Confidence |
|---|---|---|---|
| **#13 vs #37** | **Duplicate — close #13** | #37's body says "Implements #13", and #37 has landed. #13 additionally names the *wrong destination* (`csi_v2.db`), which the Postgres migration reversed. | **High** |
| **#63 vs #57** | Overlap, not duplicate | Both concern `BID_PROJECTS_DDL` drift; #57 is the narrow PR-#46 question (now moot), #63 is the general 19-vs-59 problem. Keep #63. | **High** |
| **#85 vs #58** | **Not duplicates** — record it so nobody merges them | The session report measured the overlap at 26%: 2,898 bad chunks sit in #58's blank-provenance ids, the other 8,235 do not. Different root causes, but **both land on the same `--reset` index rebuild, so they must be sequenced together.** | **High** (measured) |

Also worth noting: **#65 is a meta-issue that overlaps six others by design** (#2/#6 of its own list are CLAUDE.md rough edges 2 and 6, and #64's REVOKE trap and #62's silent-DDL trap are instances). That is intentional, not duplication.

### 9.3 Board work with no tracking issue (7)

Today's session produced #83–#86, which cover the mapping/vision/indexing findings. These are the
gaps that remain:

| Item | Source | Why it needs an issue | Confidence it is untracked |
|---|---|---|---|
| **The (c) publish is blocked on a missing `postgres`-role credential** | `latest_report.md` §1 | This is the single blocker between corrected corpus numbers and what the app shows on Wednesday. Verified by two independent methods (all 8 `.env` files on disk; live `has_schema_privilege` = false). No issue exists. | **High** |
| **The `crushing` keyword family is dead — `crushing_tons` is structurally unreachable** | `latest_report.md` §2/§5; `_spec/mapping_architecture.md` §3 | Three keywords match zero corpus rows, so an exclusion CSI is being asked to rule on is already enforced by accident. Recommendation is to delete the bucket. Not in #83. | **High** |
| **`MILL BITUMINOUS` — the third six-figure bug** | `latest_report.md` §3 | 1,346,886 SY across 18 plans. Distinct from #83 (ordering, not a typo) and *not* covered by it. Fixed in the working tree only. Notably, this was recorded as "fixed" on 2026-07-30 — in the pre-read generator, never in the code that runs. | **High** |
| **The four-layer mapping architecture (L1–L4)** | `docs/_spec/mapping_architecture.md` | A full design — trust tiers, provisional-row rule, an LLM fallback layer with costed models — marked "SPEC ONLY, for T to grill". No implementation issue, and 5 open questions with no home. | **High** |
| **`material_crosswalk` / `bucket_hierarchy` are built, published, and read by nothing** | spec §1 (confirmed two ways) | 2,434 curated mapping decisions have never affected a reported number, and `bucket_hierarchy` holds a `removal_tons` bucket the code lacks. | **High** |
| **`plans_manifest.csv` is stale and nothing updates it** | crosswalk-and-vision §6-B; explicitly "Not filed" | It marks 11 plans processed and 106 not, reflecting a June pilot; it is the likely origin of a wrong "110 unprocessed" claim, and it feeds `s2_indexer`'s provenance (so it is upstream of #58/#66). | **High** — the report says it was deliberately deferred |
| **Extraction token cost is not instrumented** | remap-run §5 | `s3_extract`/`s4_extract_rag` log no token usage, so the largest component of the per-plan cost figure for Wednesday cannot be measured. | **High** |

### 9.4 Obsolete or premise-changed (5)

| # | Call | Evidence | Confidence | What would confirm |
|---|---|---|---|---|
| 13 | **Obsolete** | Destination (`csi_v2.db`) reversed by `docs/2026-07-27_postgres_migration_plan.md`; superseded by #37, which landed. | **High** | — |
| 33 | **Premise weakened** | It adds contract columns to `csi_v2.db` as the store of record; the handoff states D1 (csi_v2.db as source of truth) is superseded. The file is still needed (§3/#50) but is no longer where new records go. | **Medium-high** | Owner confirming no new writes are planned against `csi_v2.db`. |
| 6 | **Mostly obsolete** | The issue lists 9 CWD-relative defaults across 6 files. Today `git grep '"reference/'` finds **2**, both in `research/model1/build_candidate_panels.py:21-22` — frozen research code, which CLAUDE.md says is not a runtime path, and both point at CSVs that rough edge 3 records as **deleted**. | **High** | — |
| 21 | **Premise changed (worse)** | The issue says 68 em dashes; the file now has **123**. Still valid, but as a recurring style problem, not a one-off sweep — and it is the lowest-value item in the register. | **High** (counted) | — |
| 22 | **Unblocked, not obsolete** | Labelled `blocked` "by #9"; #9 is done. It is also the leading suspect for a teammate's reported ChromaDB failure (handoff, "Still unknown" #3). | **High** on unblocked; **Low** on the teammate diagnosis. | The teammate's actual error text. |

---

## 10. Proposed reprioritization (proposal only — nothing applied, no labels edited)

Hard dates: **final presentation Wed Aug 12** · **handoff to CSI IT (Shane) Mon Aug 17** ·
**program ends Fri Aug 21**.

> **Protected, not re-prioritized.** The owner has committed to three workstreams — **P1
> cache→DB migration**, **P2 F2 report rendering**, **P3 extraction schema v2**. They are in flight
> and stay in flight. Nothing below asks for them to be dropped, deferred, or traded away. The issues
> that belong to P1 (#14, #15, and the closed-out #13/#37) are listed only for bookkeeping.

### A. Must fix before Wednesday Aug 12 (the demo must not show wrong numbers)

| Priority | Item | Why this date |
|---|---|---|
| 1 | **Commit today's crosswalk work** (#83 + the untracked `MILL BITUMINOUS` fix + `test_quantity_crosswalk.py`) | It exists only in one working tree. A machine failure between now and Wednesday loses a 5.2× correction to the headline milling number. This is the single highest-value, lowest-effort action in the register. |
| 2 | **Unblock the publish** — get the `postgres`-role DSN and run step (c), then (d) *(no issue exists)* | Until this runs the app demonstrates the **old, wrong** numbers. Everything else on Wednesday's story depends on it. |
| 3 | **#51 + #52 together** | Both are demo-shaped: a plausible keystroke (`1,200,000`) produces an unexplainable failure. #52 makes every *remaining* validation error self-explaining, so fixing them as a pair is strictly better than either alone. Small, contained, frontend+one handler. |
| 4 | **#28 — decide the presentation line, don't necessarily code it** | A confident "0 gotchas" on a partially ingested plan is the worst thing that can happen live. If not fixed, know the answer to the question. |

Explicitly **not** before Wednesday: #85, #86, #84, #11, anything in group 7. They are real, and none
changes what an audience sees.

### B. Must fix before handoff to CSI IT, Mon Aug 17

Shane inherits the running system. These are the ones that make it un-runnable or unsafe by someone
who wasn't here.

| Priority | Item | Why it gates handoff |
|---|---|---|
| 1 | **#64 — anon write + TRUNCATE on all 8 public tables, RLS off** | Handing over a system where a public API key can truncate the corpus is not defensible. The SQL is already written; the work is executing it *as the right role* and proving the effect (the issue documents that a REVOKE by a non-grantor returns success and changes nothing). |
| 2 | **#50 / #22 — the single-machine data problem** | `csi_v2.db` (only copy of three tables, behind an iCloud symlink) and the 1.5 GB local Chroma index both exist on **one laptop**. If they are not moved or the recovery path is not written down and *tested*, the handoff transfers a system nobody else can run. #67/#68 are ~1 hour each and are the cheapest real progress here. |
| 3 | **#7 — the Dockerfile cannot build** | The first thing a receiving IT team does is try to build the image. It fails on paths that have not existed for months. Fixing it forces the "how does the index ship?" decision, which is exactly the decision Shane will otherwise have to make blind. |
| 4 | **#58 — every web upload double-indexes** | It is the one open bug that gets *worse with use*: 10,046 redundant chunks and growing, and it silently halves metadata-filtered search results. Sequence it with #85 — both require the same index rebuild, and doing them separately means rebuilding twice. |
| 5 | **#63 + #62** | Whoever inherits this will read `BID_PROJECTS_DDL` to learn the schema and be wrong by 40 columns; and `updated_at` cannot be used to find recent edits. Both are documentation-grade defects that cost an inheritor days. |
| 6 | **#53, #36, #37, #9, #57, #13 — close them** | Six issues that are done, superseded, or duplicated. Handing over a 53-issue backlog where 6 are already resolved damages the credibility of the other 47. Closing costs minutes. |
| 7 | **#54, #6 — environment fragility** | #54 (two `.env` parsers) is a first-hour-of-setup trap for a new operator. #6 should be **closed or rewritten** — 7 of its 9 call sites no longer exist. |

### C. Post-handoff / hand to CSI as written-down work (Aug 17–21, or never)

Not because they don't matter — because they cannot land well in the time left.

- **#85, #86** — high-value corpus quality work with measured evidence; #85 has a 100%-precision
  filter ready. Both are safe to hand over *as issues*, since the analysis is already in the bodies.
- **#84** — genuinely dormant. It fires only when someone upgrades the model or builds the vision
  path. It is a perfect handoff ticket: precise, verified, and inert until touched.
- **#70, #71, #72, #73, #66** — the identity/seam cluster. #70 is correctly labelled the critical
  path, but it is a chain of five stages and a merge-strategy decision (#73). Scope it, document it,
  do not start it on Aug 18.
- **#38, #39, #40, #41, #35** — the #10 phase family. #41 and #35 are **decisions for CSI**, not
  code; getting written answers before Aug 21 is achievable and valuable. #40 is real build work.
- **#11 (materials→2026 capacity)** — a client requirement labelled `p0` and, per its own body, *new
  code, not integration*. It cannot be built by Aug 21. It should be handed over with that stated
  plainly rather than left looking like an open p0 someone forgot.
- **#16, #17, #19, #18** — the mapping-and-deletion program. Valuable for a maintainer; #17 is
  blocked by #16 for good reason. Do not attempt the deletion pass in the final week.
- **#59** — the test is provably impossible as written; a 15-minute fix, but only worth doing if
  someone will run the integration suite against a real database (which has never happened).
- **The four untracked items in §9.3** — the L1–L4 mapping architecture, the unread
  `material_crosswalk`/`bucket_hierarchy` tables, stale `plans_manifest.csv`, and extraction cost
  instrumentation. File them before Aug 21 so they survive the handoff.

### D. Should just close

| # | Reason |
|---|---|
| 13 | Duplicate of #37 (which is done) **and** names a destination the project abandoned. |
| 36, 37 | Landed; code verified above. |
| 53 | Fixed; verified in code. |
| 9 | Done; the 5 named tables plus 3 more are published. |
| 57 | Overtaken by the merge of PR #46, which landed the recommended cherry-pick without reverting `job_id`. |
| 6 | 7 of 9 call sites are gone; the 2 that remain are frozen research code pointing at deleted files. Close, or rewrite as a 2-line note. |
| 21 | Cosmetic, and the count has grown from 68 to 123 — this is a style convention question, not a task. Close or move to a CONTRIBUTING note. |
| 24 | Its own body says the likeliest outcome is "the existing dictionary covers it, close this". Do the 10-minute overlap check and close. |
| 23 | The status quo already answers it — both harnesses are in the team repo, so "private" would require action nobody is proposing. Close as decided-by-default. |

### E. What this does to the counts

| Bucket | Count |
|---|---|
| Open today | **53** |
| Close as done / duplicate / obsolete | **9** (#6, #9, #13, #21, #23, #24, #36, #37, #53, #57 — 10 if #10 is confirmed) |
| Must-fix before Wed Aug 12 | **3 issues + 2 untracked items** |
| Must-fix before handoff Aug 17 | **8** |
| Hand over as documented work | **~32** |
| Protected workstreams, untouched | **3** (P1 cache→DB, P2 F2 rendering, P3 extraction schema v2) |
