# CLAUDE.md — read this before you touch anything

This file defines what this system is and how it is meant to be designed, so that every session
starts from the same picture. If something you are about to do contradicts this file, stop and ask
rather than deciding on your own.

For the full system architecture — the three orchestrations, every external API call, the diagram —
see [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md). This file is the working contract; that one is
the reference.

---

## What this system is

Decision support for CSI's bid/no-bid decisions on Minnesota DOT highway lettings. A user uploads a
project plan set (PDF) and asks questions about it. The system answers from two sources: facts
extracted from that PDF, and CSI's historical bid corpus, which also drives a model predicting
which competitors are likely to bid.

It is **decision support, not a classifier**. The output is meant to inform a human estimator, not
to emit a bid/no-bid verdict.

## Folder responsibilities

Each directory has one job. Do not move work across these boundaries without asking.

| Directory | Owns | Does NOT |
|---|---|---|
| `apps/api/` | The FastAPI backend (:8010). The chat agent loop, report assembly, tool implementations, and (as of 2026-07-30) the CI-data admin endpoints. | Contain pipeline logic. It calls pipelines, it does not reimplement them. |
| `apps/web/` | The Next.js frontend (:3000). UI only. | Call any LLM. It proxies to `apps/api` for everything except Google Maps — the pit-list page (2026-07-31) calls Google's Geocoding + Maps JavaScript APIs directly from the browser with a public, referrer-restricted key, since map tiles can't be proxied through our own backend. |
| `pipelines/plan_reader/` | PDF → structured facts. Conversion, chunking, indexing, extraction. | Know anything about competitors or bid history. |
| `pipelines/ci_model/` | Historical bids → competitor participation ranking and reports. | Know anything about PDFs. |
| `research/` | Notebooks, one-off analysis, model experiments. | Appear in any runtime path. Nothing in `apps/` may import it. |
| `data/` | Shared inputs/outputs and the scripts that produce them. | Hold module-private intermediates — those stay in the module. |
| `docs/` | Architecture, changelog, archived documents. | — |
| `reference/` | Three competitor CSVs. See rough edge 3 below before touching. | — |

## Architectural invariants

These are load-bearing. Breaking one will not fail loudly.

**1. `apps/` and `pipelines/` are not coupled by imports.**
There are no Python imports from `apps/` into `pipelines/` or back. The backend invokes the CI
model as a **subprocess** (`apps/api/backend/competitor_live.py:111`) and reads its outputs as
**CSVs by path**. Do not "simplify" this into a direct import — the two trees have separate
dependency sets and separate owners.

**2. `pipelines/` is path-referenced, never imported as a package.**
It is referred to only by path strings, concentrated in `apps/api/backend/config.py`. The only
`__init__.py` under `pipelines/` or `research/` is `research/model1/__init__.py`. Before adding one,
understand that the numbered directory names (`01_pipeline/`, `06_reporting/`) are not importable
identifiers — the current design depends on them never needing to be.

**3. Anthropic is the only LLM provider.**
No OpenAI, Gemini, Cohere, LangChain, or LiteLLM anywhere in the tree. Embeddings are **local**
(MiniLM via Chroma), not an API call. Keep it that way unless asked.

Non-LLM outbound calls: a US Census TIGER shapefile download in `data/clean_mn_pit_list.py:67`, and
(as of the route/milepost midpoint feature) up to 6 state DOT GIS REST endpoints called from
`apps/api/backend/midpoint_bridge.py` → `pipelines/plan_reader/04_tools/road_midpoint/road_midpoint.py`,
the 5th `process_pdf` stage (`apps/api/backend/report.py`). Gated by
`settings.midpoint_lookup_enabled`; fails open (null latitude/longitude) on any error or timeout —
never raises into the report.

**4. Gitignored does not mean unnecessary.**
Two artifacts are gitignored as "regenerable" but are required at runtime. See rough edge 1.

**5. Apply the fresh-clone test, not the provenance test.**
When deciding where a file belongs, the question is **"does a fresh clone need this to run?"** — not
"was this authored or generated?". The provenance question has produced five silent dependency
misclassifications in this repo. Every one of them was a directory that looked uniformly derived but
held something load-bearing.

**6. `apps/api` now makes one direct Postgres connection — new as of 2026-07-30.**
`apps/api/backend/ci_db.py` connects straight to Supabase's `scratch` schema (`SUPABASE_TEAM_DB_URL`
— the same `csi_team` DSN/role `data/push_supabase_bid_data.py` already uses) for the three CI-data
admin features: bid-results entry, pit-list CRUD, and competitor-registry CRUD (`/api/ci-data/*` in
`app.py`, backed by `backend/bid_results_admin.py` / `pit_list_admin.py` /
`competitor_registry_admin.py`). This is genuinely new, not an extension of the existing pattern:
every other read in this backend is a local CSV by path; this is the first live read/write.
See `docs/ARCHITECTURE.md` §9 and rough edge 7 below for the cascade-rename detail and current
verification status.

**7. `pipelines/ci_model` now also makes a direct Postgres connection — new as of 2026-08-03.**
`pipelines/ci_model/06_reporting/tools/capacity_live.py` queries `scratch.bid_results` /
`scratch.bid_projects` live, once per report (batched for the whole competitor shortlist), so the
report's Capacity bullet reflects the current database state instead of the local
`ranking_predictions.csv` snapshot. Same `SUPABASE_TEAM_DB_URL` DSN as invariant 6 above, but its
own standalone `connect()` — not an import of `apps/api/backend/ci_db.py` — matching the existing
pattern of every Postgres-facing script in this repo owning its own connector rather than sharing
one across the `apps/`/`pipelines/`/`data/` boundary. Fail-open: `orchestrator.py` falls back to
the local-file computation on any connection or query error, same philosophy as invariant 2's CI
subprocess fallback.

## Working rules

- **Verify paths with `git ls-files` before writing them into code or docs.** Several documents in
  this repo cite paths and line numbers that have drifted. If you cannot verify a behavior, write
  `UNVERIFIED` rather than inferring it.
- **Do not delete or relocate a directory because it looks like dead output.** Grep for the basename
  first, and check whether hits are reads or writes. Watch for basename collisions — `outputs/`
  produces false hits across four different modules.
- **Prove a subprocess ran; do not trust an HTTP 200.** See rough edge 2.
- **A success signal at the wrong layer is not evidence.** HTTP 200 is a transport fact, not an
  application fact. A SQL statement completing is a syntax fact, not an effect fact. Five instances
  are collected in #65, including `create table if not exists` never reconciling a table, and a
  `REVOKE` by a non-grantor returning success while changing nothing. **Verify by observing the
  changed state, and never let a failure and a legitimate empty answer share a return value.**
- **A negative result from a fixed set of checks is not proof of absence.** When code answers "is
  this safe / ambiguous / a duplicate?", enumerate the ways the underlying operation can lose data
  and confirm each has a check — do not enumerate the checks and assume they cover it. This cost a
  destroyed row on 2026-08-03: a duplicate check tested two conditions, neither of which was the one
  that overwrites, and returned clean while a project disappeared.
- **Do not add features while cleaning.** Cleanup commits and behavior commits stay separate.

---

## Known rough edges

Real constraints, not TODOs. Read these before debugging anything that looks inexplicable.

**1. Two large artifacts a fresh clone cannot run without.**

| Artifact | Size | Recovery |
|---|---|---|
| `pipelines/ci_model/03_training/outputs/ranking_predictions.csv` | 94 MB | `pipelines/ci_model/README.md` |
| `pipelines/plan_reader/06_chroma/` | 1.5 GB | `pipelines/plan_reader/README.md` |

Both are gitignored as regenerable training/index outputs. Neither is optional at runtime.

**2. CI subprocess failures are silent, and there are two reasons for that.**

`apps/api/backend/competitor_live.py` returns `None` on timeout, `CalledProcessError`, or
any exception. The caller then falls back — until 2026-08-09 to a **stale pre-generated report**,
so the API returned HTTP 200 with plausible competitive output while the subprocess was dead. That
static-match tier was removed on 2026-08-09 (owner's call, see rough edge 11): the fallback is now
the **live prediction** (`competitor_predict_live`), so a dead subprocess shows up honestly as the
cascade log's `served_by=` shifting from `layer1-live-generated` to `layer3-live-prediction` —
watch for that shift; it is now the primary symptom of this failure mode.

Compounding it, `competitor_live.py:117` truncates subprocess stderr to **400 characters**, which
cuts off the exception line. A real `FileNotFoundError` was hidden this way.

**→ Any verification that CI works must prove the subprocess RAN** — process observation, or a
report mtime that advanced. A response coming back proves nothing.

**3. `reference/competitor_entities.csv` / `reference/competitor_priority.csv` — ✅ RESOLVED (removed).**

Both were dead weight: `competitor_priority.csv` was an empty header-only file the live pipeline
never actually consulted (priority now comes from the name registry's `Top Competitors Tag`), and
`competitor_entities.csv` contributed zero unique pit-ownership resolutions beyond what
`bidder_results.csv` already covers (verified empirically — 0 of 21 pit-owner names resolved only
through it). Both files and their `--entities`/`--priority` CLI plumbing were removed from
`data/build_project_competitor_panel.py`, `pipelines/ci_model/01_candidates/build_pit_features.py`,
and `pipelines/ci_model/01_candidates/build_candidate_panels.py` (which had an already-unused
`--entities` flag — `entities=None` was hardcoded regardless).

`research/model1/build_candidate_panels.py` (frozen research code, not runtime) still references
the old paths and would need updating before anyone tries to run it standalone.

**4. Three of the CI orchestrator's four path defaults point at a layout that never existed here.**

`pipelines/ci_model/06_reporting/agent/orchestrator.py` defaults `_DEFAULT_PREDICTIONS` (`:34-36`),
`_DEFAULT_MODEL` (`:37-39`), and `_DEFAULT_REGISTRY` (`:40-42`) to
`ci_model/competitor_prediction_model/…`, a nested layout inherited from an external clone and
present nowhere in this repo (`git ls-files | grep -c competitor_prediction_model` → 0).
`competitor_live.py` passes all of them explicitly because the defaults were always wrong.

`_DEFAULT_BIDDER_RESULTS` (`:43-45`) and `_DEFAULT_PROJECTS` (`:46-48`) are **correct** — they point
at real tracked files in `data/processed/`. They are passed explicitly for consistency, not
necessity.

**5. `plan_reader` and `ci_model` still do not connect — only the emission side is bridged now.**

`plan_reader` now extracts `route_number`/`begin_milepost`/`end_milepost`/`total_gross_length`
(`pipelines/plan_reader/01_pipeline/schema.py`) and, for MN/ND/SD/NE/IA/MT plans, automatically
converts them to a latitude/longitude via `apps/api/backend/midpoint_bridge.py` →
`04_tools/road_midpoint/road_midpoint.py`, surfaced in the report's `identity.latitude/longitude`
(`apps/api/backend/report.py`'s 5th `process_pdf` stage). A human `record_correction` for `lat_long`
takes precedence over the automated value and is merged in at render time
(`apps/api/backend/final_report.py::assemble`) — necessary because a correction can be typed in
*after* the PDF was already processed and cached.

**This closes the emission side only.** `ci_model`'s orchestrator still only reads pre-computed
coordinates from `data/processed/projects.csv` for historical projects already matched by
`project_natural_key` — there is no mechanism to feed it an ad-hoc plan's coordinates, and that
CI-owned code/data was deliberately not touched (beyond the 2026-08-01 removal of the legacy
`job_id` column, which this seam never depended on). A freshly uploaded plan's coordinates reach
the *report*, not the competitor-prediction pipeline. Do not write code that assumes otherwise.

CLI-ingested plans (`pipelines/plan_reader/run.py`) get the four new extracted fields for free but
**not** the automated lat/long — `run.py` was not extended with the 5th stage in this pass.

**6. `road_midpoint.py`'s 6 state lookups can't tell a live DOT outage from "route not found." — 2026-07-28.**

All 6 state functions in `pipelines/plan_reader/04_tools/road_midpoint/road_midpoint.py`
(`mn_measure_to_latlon`, `nd_`, `sd_`, `ne_`, `mt_`, `ia_measure_to_latlon`) call
`resp.raise_for_status()` and then read `resp.json().get("features", [])` (or equivalent). ArcGIS
REST services can return an application-level error as **HTTP 200 with an `{"error": {...}}`
body** — `raise_for_status()` never fires on that, and the missing `"features"` key collapses to an
empty list, so the code raises its normal "route not found, check the route number and milepost"
message even when the real cause is the DOT's service being down.

Confirmed live on 2026-07-28: `test_midpoint_bridge.py::test_compute_midpoint_matches_cli_for_known_mn_plan`
failed because MnDOT's `TFA/MNDOT_TRAFFIC_DATA/MapServer` was returning
`{"error":{"code":500,"message":"Service TFA/MNDOT_TRAFFIC_DATA/MapServer not started "}}` for every
query — not a bad route/milepost. Same "don't trust an HTTP 200" failure class as rough edge 2, one
layer further out (an external DOT GIS endpoint instead of the CI subprocess).

**Does not affect production behavior** — `midpoint_bridge.compute_midpoint` catches broadly
regardless of the reason and returns `None`, so the report still fails safe either way. It only
costs debugging time: a genuine bad route number and a DOT outage currently look identical in the
logs. Left as a known issue, not fixed, per 2026-07-28 decision — fix would mean checking for an
`"error"` key before treating a response as empty, across all 6 functions in `road_midpoint.py`.

**7. The CI-data admin features (bid results / pit list / competitor registry / projects) are built
but unverified against a real database — 2026-07-30, grown since.**

Originally three features and 10 endpoints (2026-07-30): `backend/ci_db.py`,
`backend/bid_results_admin.py`, `backend/pit_list_admin.py`, `backend/competitor_registry_admin.py`,
and 3 new `apps/web` pages (`/bid-results`, `/pit-list`, `/competitor-registry`, reached through a
newly-mounted `AppShell` — see below). As of 2026-07-31 there are four pages and more endpoints:
`backend/project_admin.py` (`/projects` — view every `bid_projects` row, edit the seven
material-quantity columns only), a full bid-results table (`GET /api/ci-data/bid-results`,
`PATCH .../bid-results/{project_natural_key}/{competitor_unit_id}` — the original bid-results page
only ever showed projects *missing* results, never a view of what's already recorded), and the
pit-list page grew required-field validation, a registry-restricted `access_company` picker, a
Google Maps view, and CSV export (see `docs/ARCHITECTURE.md` §9's "Google Maps" note — the first
direct browser-to-third-party call in `apps/web`). What's actually been checked, and what hasn't:

- Verified (2026-07-30, the original three features): syntax, `apps/api`'s existing pytest suite
  still passes (only the pre-existing rough edge 6 flake fails), a full `npm run build`/`lint` pass,
  and an HTTP-level smoke test — the real FastAPI app (heavy ML deps stubbed out; see below) and the
  real Next.js dev server both started, every new page returned 200 with the right heading and nav
  present, and every `/api/ci-data/*` endpoint returned a clean
  `503 {"ok": false, "message": "SUPABASE_TEAM_DB_URL is not set"}` rather than crashing.
- Verified (2026-07-31 additions — bid-results table, projects page, competitor-registry
  typeahead/consolidate-scope/CSV-export, the verify-gate report-pipeline split): `py_compile`,
  `pytest` (same result as above), `tsc --noEmit`, `eslint`, and `npm run build`, all clean. **Not**
  re-run: the HTTP-level smoke test above (real FastAPI + Next.js dev servers, live 503 check) —
  this pass is one level less verified than the 2026-07-30 baseline, static checks only.
- Added 2026-08-06: per-alias removal on the competitor registry —
  `DELETE /api/ci-data/competitor-raw-names/{raw_name_variant}`
  (`competitor_registry_admin.remove_raw_name_variant()`) deletes one `raw_name_variant` row without
  touching sibling rows under the same `comp_name`, so an individual company rolled up under a
  parent (e.g. one of the 7-8 names under "OMG Midwest") can be deleted on its own. Same two-step
  confirm/cancel UI as the existing parent-level delete, now on every row. See
  `docs/ARCHITECTURE.md` §9. Verified the same way as the 2026-07-31 additions — `py_compile`,
  `pytest`, `tsc --noEmit`, `eslint`, `npm run build`, all clean; same unverified-against-a-real-
  database gap as everything else in this rough edge.
- **Not verified**: no run against a real Supabase connection. `SUPABASE_TEAM_DB_URL` was never
  configured in the dev sandbox this was built in, so the 17 integration tests
  (`tests/test_bid_results_admin.py`, `test_pit_list_admin.py`, `test_competitor_registry_admin.py`)
  have only been confirmed to **skip cleanly** (`pytest.mark.skipif`), never to actually pass. In
  particular, `test_consolidate_only_touches_the_selected_raw_name_and_leaves_bid_results_alone` —
  the test that proves a consolidate only renames the selected raw name's registry row and never
  touches `bid_results` (registry-only scope, see below) — has never been run for real. Needs the
  `csi_team` DSN (password from Tobias) before this can be called done.
- **Not verified**: no interactive browser click-through. The dev sandbox has no headless-browser
  tool, so the typeahead, inline-edit, and warn-then-force-through flows were reviewed by reading
  the code, not by clicking them.
- The FastAPI smoke test above required stubbing `chromadb`/`sentence_transformers`/`pymupdf4llm`/
  `pdfplumber` in `sys.modules` — this sandbox's `pip install -r requirements.txt` fails on `torch`
  with a Windows max-path-length OSError, unrelated to this feature. Anyone running this for real
  needs the actual ML stack installed (as the app already requires for everything else it does).

**Explicit scope boundary, not a bug:** these features write live to Supabase `scratch.*`. They do
**not** feed back into `ci_model`'s local training CSVs/parquet — today only the competitor registry
has a pull path (`data/pull_registry_corrections.py`, and it only pulls `comp_name`/`source`/
`top_competitors_tag`/`suggested_comp`, not new rows). An estimator entering bid results or editing
the pit list through the new UI will not be reflected in the next `ci_model` training run until
someone builds and runs an equivalent pull script for `bid_results`/`mn_pit_list`. Same shape as
rough edge 5's plan_reader/ci_model seam — deliberately not attempted in this pass.

**`AppShell` is mounted (2026-07-30), turning this from a "chatbot-only MVP" (the frontend's own
former description) into a small multi-page app.** When first mounted, the nav's other
long-scaffolded-but-unbuilt links (`/chat`, `/ingest`, `/opportunities`, `/sweet-spot`, `/map`,
`/pricing`) became clickable and 404'd — that gap predated the mount (those pages never existed) but
was now visible instead of dormant. **Resolved 2026-07-31**: the pit-list commit trimmed
`NAV_GROUPS` (`apps/web/src/components/app-shell.tsx`) down to only the pages that actually exist —
Overview plus the four Data pages (Projects, Bid Results, Pit List, Competitors). No dead links in
the nav today.

**8. The PDF-drop path is now two phases with a human verify gate in between — 2026-07-31, built
but not run against a live backend.**

`POST /api/report` used to run extraction and assembly (including the competitor-intel subprocess)
in one blocking call. It now stops after extraction and returns it unverified; a new
`POST /api/report/{plan_id}/finalize` is what a human triggers (confirm or skip) to actually run the
rest of the report. Full detail in `docs/ARCHITECTURE.md` §1.1 — this note is the "what changed and
why" summary plus what's unverified about it.

- `apps/api/backend/report.py::process_pdf` now preserves per-field confidence/page (previously
  discarded by `_val()`) into a new `field_confidence` dict, and no longer writes the payload cache
  itself — a new `apply_verification()` does that, only once a human has actually confirmed or
  edited the extraction. A user-entered `latitude`/`longitude` or corrected quantity is written
  directly into that same payload-cache JSON (by explicit request), not into `corrections.py`'s
  separate sidecar file — that stays reserved for a *later*, post-hoc chat correction to an
  already-built report, a genuinely different use case that still works exactly as before.
- `apps/web/src/components/verify/verify-extraction.tsx` was previously a UI mockup over hardcoded
  data in `@/lib/mock-plan.ts`, with non-functional Confirm/Skip buttons. It now renders the real
  extraction with real 3-level confidence and drives the two-phase flow. Skip is always allowed —
  a freshly dropped plan's coordinates don't feed the competitor-intel match today regardless (see
  rough edge 5 above / `docs/ARCHITECTURE.md` §5), so nothing in that same report is blocked by
  skipping.
- The modal auto-opens off message state (`ChatMessage.verifying`) once extraction lands, instead
  of via a button that used to sit at the bottom of an already-rendered report card (removed).
- **Not verified**: no live backend in the sandbox this was built in (same constraint as rough edge
  7 above), so the two-phase HTTP round-trip has never actually run — only `py_compile`, `pytest`
  (unaffected — no test exercises `/api/report` at the HTTP level), `tsc`, `eslint`, and
  `npm run build` were checked. A gap was caught this way regardless: the first version of this
  change was missing the Next.js proxy route for the new finalize endpoint
  (`apps/web/src/app/api/report/[planId]/finalize/route.ts`) — `npm run build` doesn't fail on a
  missing API route, only a real request would have, so that one specifically was caught by
  inspection, not by a check that would have failed loudly.

**9. The pit-list "find nearest pits" search (2026-08-06) is client-side only — no new backend
endpoint, and no live verification.**

`apps/web/src/app/pit-list/page.tsx` gained a "Find nearest pits" panel: set an origin either by
picking a bid project (`apps/web/src/components/pit-list/project-midpoint-picker.tsx`, a typeahead
that lazy-loads the existing `GET /api/ci-data/projects` on first focus — no new endpoint) or by
typing a raw lat/long, then every pit already in `store.pits` gets a `distanceMiles` computed
client-side via `apps/web/src/lib/geo.ts::haversineMiles`. That formula and its Earth radius
constant are a deliberate copy of `pipelines/ci_model/01_candidates/build_pit_features.py`'s
`haversine_miles`/`EARTH_RADIUS_MILES` — kept in sync by convention, not by shared code, so a future
change to one needs the same change made by hand in the other or "nearest pit" on this page will
quietly disagree with what the competitor model actually scores off of. Adds a Distance
column/sort (defaulting to nearest-first once an origin is set and no column sort is active),
includes `distanceMiles` in CSV export when active, and draws the origin as a distinct blue circular
marker in `pit-map.tsx` (`PitMap`'s new `origin` prop) alongside the existing pit dots.

Verified the same way as rough edge 7/8's additions: `tsc --noEmit`, `eslint`, and `npm run build`
all clean. **Not verified**: no live backend in the sandbox this was built in, so the
`/api/ci-data/projects` round-trip that feeds the project picker has never actually run — reviewed
by reading the code, not by opening the picker and typing into it.

**10. `competitor_predict_live.py`'s candidate pool and scoring were rewritten 2026-08-09 — the
first change in this rough-edges list actually verified against a live Supabase, with numbers.**

**Attribution, stated up front because it's easy to get backwards**: this rewrite is usually
described as "ported the candidate pool to the CI team's 6-signal V3 logic," and that description
is technically true but misleading about *why* the pool got smaller. Measured on real data (below):
fixing one inherited registry-filter bug accounts for ~94% of the pool shrinkage and ~90% of the
recall cost; porting 2 signals to 6 accounts for the remaining ~6%/~10%. If you're citing this
change as "we aligned the live pool with V3's design," that's correct for code structure but not for
where the *numbers* came from — most of what moved, moved because a bug got fixed, not because of
the 6-signal expansion. Don't credit the signal-porting work for an effect that was mostly the bug fix.

The old `_candidate_pool()` was "everyone who has ever bid in this state" plus a registry priority
tag — a single crude signal, nothing like the CI team's actual production candidate definition
(`pipelines/ci_model/01_candidates/candidate_filter.py::build_v3_candidate_set`, 10 signal
sources). It now ports 6 of those 10 signals (same_county, same_type, recent_90d,
historical_winner_24m, recurring_regional_24m, priority — same weighted-fallback gate, not a flat
union) as hand-written SQL/Python, since `apps/` cannot import `pipelines/` (invariant 1). This is
a **manually maintained mirror, not shared code, and WILL drift** if `candidate_filter.py` or
`pipelines/ci_model/shared/config.py`'s `V3_*` constants change without a matching edit here.
`apps/api/tests/test_candidate_pool_consistency.py` catches that drift by diffing this function's
live output against `data/processed/model1/rule_candidate_set.parquet` (the real materialized
ground truth) — skipped unless `SUPABASE_TEAM_DB_URL` is set, same convention as rough edge 7's
tests. `_score_candidates()` also now attaches a genuinely calibrated win probability
(`sigmoid(raw_score + offset)`, a closed-form read of the existing fitted-model JSON, not a new
model) alongside the unchanged ranking.

**A real, pre-existing bug was caught and fixed in the process, not introduced by the rewrite**: the
priority-tag filter (`top_competitors_tag is not null and != ''`) matched the literal string `'0'`
and one stray `'Top Competitors Tag'` header value sitting in the data as a row — 889 of 897
registry rows, i.e. nearly the entire registry, were being treated as "priority." Correct filter is
`= '1'` (confirmed against `build_candidate_panels.py:84`). This was in the code before the rewrite;
it was only caught because the new consistency test could finally be run against real data.

This sandbox had `SUPABASE_TEAM_DB_URL` configured (unlike every other entry in this rough-edges
list), so the questions below were answered with real queries, not just static checks — decomposed
here because "the pool got 4.5x smaller" and "did anything break" are different claims:

- **Decomposing the pool-size drop (avg 717 → 158 candidates, MN+ND, n=39 historical projects)**:
  the priority-tag bug fix alone accounts for ~94% of it (717 → 190) and ~90% of the recall cost
  (0.997 → 0.904); porting 2 signals → 6 only trims a further 190 → 158 and 0.904 → 0.894. If this
  ever needs to be dialed back, the priority-tag fix is not a safe thing to revert (it was fixing
  data corruption, not a design choice) — the 6-signal expansion is the smaller, reversible part.
- **Top-5 precision on real historical outcomes was unchanged** (0.282 old vs 0.282 new, same
  sample) even though pool-level precision improved 4.8x (`|actual∩pool|/|pool|`, 0.0064 → 0.0310).
  The linear scoring formula already suppresses irrelevant candidates toward the bottom regardless
  of how bloated the pool is, so the old crude pool wasn't costing top-5 accuracy — it was mostly
  dead weight the ranking already ignored. Don't cite this fix as a precision improvement without
  qualifying it as "candidate-pool precision," not "top-5 precision."
- **Latency, measured**: the new pool query is real but not catastrophic overhead — mean 156ms vs
  120ms, p95 244ms vs 156ms (n=45, MN/ND/SD). Not load-tested under concurrency.
- **Empty-pool boundary, tested directly**: `_score_candidates(conn, set(), ...)` returns `[]`
  cleanly; `predict_report()` degrades to an empty `competitors` list, does not raise. In 143 real
  worst-case probes (exhaustive MT+NE, plus the rarest county in every state), the pool never
  dropped below 25 — because the 25 `top_competitors_tag = '1'` registry rows unconditionally clear
  the fallback-score gate (weight 3.0 ≥ threshold 1.5) regardless of state/county/type. That floor
  is **data-dependent, not code-guaranteed**: if the registry's priority tags were ever cleared, the
  pool could genuinely reach zero, and the code path has been confirmed not to crash when it does —
  but nothing currently alerts if that floor disappears.
- **A related but pre-existing gap, not caused by this fix**: for a state with zero bid history,
  the pool doesn't go empty — it silently falls back to the same 25 nationwide priority companies,
  scored on their out-of-state history, producing a plausible-looking report for a location the
  system has no real competitive data on. Confirmed the old code had the identical floor behavior
  (`historical | priority`, `historical=∅`); this fix neither introduced nor closed it.
- **Fix-1/Fix-2 interaction, checked directly**: scoring the same MN mill-overlay query against the
  old 718-candidate pool and the new ~176-candidate pool gives IDENTICAL scores/probabilities for
  every candidate that appears in both (a candidate's score depends only on its own win history, not
  on who else is in the pool) — the ~96-100% top-5 probability compression noted when this was first
  built is a property of the model/weights, not amplified by the smaller pool. Pool size only changes
  *which* candidates are eligible to appear, not their score once eligible.
- **Still open, not addressed by this pass**: historical projects (what was validated above) vs.
  currently-active plans may not have the same county/project-type distribution — a live plan with a
  rarer combination than anything in the 2024+ sample used here has not been specifically tested.

**11. `find_project_key()`/`match_report()`'s county+state+date reverse-lookup can silently attach
the WRONG project's competitor section — identified 2026-08-09, given a first defensive mitigation
the same day, full fix NOT done.**

This is a different, more severe bug class than rough edge 10: that one was about ranking quality
within the right project; this one is about **whether the system has the right project's data at
all**. `competitor_live.py::find_project_key()` and `competitor_report.py::match_report()` both
match a plan to a historical project by (normalized) county + state, then pick whichever candidate
in that county+state has the SMALLEST date gap — **with no cutoff**. `gaps.idxmin()` returns
*something* as long as county+state matches at all, no matter how large the gap. The `confidence`
label this produced (`high`/`medium`/`low`) was purely cosmetic: rendered as one line of markdown
text in the report (`final_report.py`), never gating auto-attach, and — until today — actually
**mislabeled**: a plan with no bid_date at all (find_project_key's `gap=10_000` sentinel /
match_report's `gap=None`) was scored `"high"` confidence, backwards from what it should be, since
having zero date information to disambiguate a county is the WEAKEST case, not the strongest.

**Measured against `data/processed/projects.csv` (1591 real historical projects), not assumed**:
- 59% of (state, county) pairs have more than one distinct historical project (max 72, ND Cass
  County). county+state alone is nowhere close to a unique identifier.
- 169 pairs of GENUINELY DIFFERENT projects share the exact same county+state+bid_date (spot-checked
  `IA_CASS_CO_ATLANTIC_2025-01-22_1`/`_2`: same day, same county, one `Grading/Earthwork` one
  `Reconstruct/Rebuild` — two real, different lettings, not a data duplicate). In these ties,
  `idxmin()` deterministically picks whichever row happens to sort first — unrelated to which
  project a real new plan actually corresponds to.
- Same-county project pairs sit within 7 days of each other 28.1% of the time, 14 days 40.7%, 30
  days 56.2% — so even an approximately-correct extracted bid_date has a real chance of landing
  closer to the WRONG same-county neighbor than the right project.
- **Leave-one-out simulation** (treat each of the 1591 historical projects as if it were a brand-new
  plan not yet in the corpus, run the same nearest-date matching logic against everyone else): a
  match is returned 91.2% of the time (8.8% have no other project in that county+state at all), and
  of those returned matches, **25.3% would now be flagged `needs_review`** (23.1% of all 1591). Zero
  test coverage existed for either function before this — no unit test, no manual sample check.

**What was done today (defensive only, does NOT change the matching logic)**: `_match` now carries
an explicit `needs_review: bool` (gap > `MATCH_REVIEW_GAP_DAYS = 45`, or no date at all, or
`match_report`'s state-only fallback), the backwards no-date-means-high-confidence mislabeling is
fixed, and the rendered markdown now prints a visible `⚠️ Needs review` line instead of burying the
signal in confidence-label text nobody reads as a warning. A caller that ignores `needs_review`
today gets byte-identical behavior to before this fix — nothing is blocked yet.
(Note: `match_report` — the whole static-match middle tier — no longer exists. First its
state-only fallback was removed after a live plan with a missing county was served another
county's 141-day-old report verbatim; then, later the same day, the owner removed the tier
entirely: its one remaining role was masking a dead CI subprocess with a plausible stale report
(rough edge 2's exact failure mode), and the live prediction built from the plan's own
state/type/quantities is strictly preferable to a verbatim copy of a possibly-different project's
old report. The cascade is now two tiers — live CI generation for corpus projects, else live
prediction — with the `served_by` log labels keeping their historical layer1/layer3 names for log
continuity.)

**Step 1 of the staged fix landed later the same day (2026-08-09): the work-type gate, behind
`TYPE_GATE_MODE` (default `log_only`).** Full leave-one-out decomposition of the 1451 matchable
cases first (all numbers measured, not assumed): 24.5% CLEAN (exactly 1 candidate within 45d),
25.3% FAR-ONLY (0 within 45d — stage 0's needs_review), and **50.2% AMBIGUOUS (≥2 candidates
within 45d, all auto-attached as "high confidence" until this step)**. Within the ambiguous half:
type fully disambiguates 26.7%, partially narrows 34.4%, is useless (all candidates same type)
5.5%, and **excludes every near candidate in 33.3%** — that last bucket (16.7% of ALL matches) is
the strongest wrong-match signal in the data, and the gate targets exactly it: when ≥1 candidate
sits within `MATCH_REVIEW_GAP_DAYS` but none matches the plan's archetype
(`competitor_report.norm_work_type()` bridges the 'Reconstruct/Rebuild' vs 'Reconstruct / Rebuild'
spelling split; 'Other'/'Unknown/NoQty' count as *unknown*, gate off), the match is a likely wrong
project. The gate and needs_review are **two independent detectors — do not merge them**: one
catches "too far in time", the other "near but nothing looks like this plan"; different failure
modes, separately toggleable, separately countable in logs.

**The hard-reject form is justified by human sampling, not just statistics** — evidence chain, so
nobody re-litigates this in six months: Wenyu manually sampled the collision cases on 2026-08-09
(drawn mainly from the 169 exact same-day same-county pairs; exact n not recorded here) and
concluded the matches are **genuine wrong-project mismatches, not archetype-extraction errors** —
which is precisely the finding that would have downgraded the gate to a soft warning, and it did
not hold. A scripted spot-check of 5 cases from the type-excludes-all bucket itself corroborates:
e.g. a Ward Co ND airport-taxiway Mill&Overlay vs a gravel-hauling project 40d away; a Cass Co MN
TH 371 mill job vs culvert/grading contracts the same month — unmistakably different real lettings
(different contract numbers, work, and quantities), consistent with the sampling conclusion.

Rollout state: `TYPE_GATE_MODE=log_only` is the default — detection + a
`type gate (would_reject): plan=... reason=type_all_excluded` WARNING per hit, behavior unchanged.
The plan is to run log-only for a week or two, compare the real would-reject rate against the
offline 16.7% estimate (the cascade-tier log line in `predict_competitors()` — `served_by=layerN`
per plan — provides the denominator), then flip `TYPE_GATE_MODE=enforce`. There is no test
environment; the env-var switch IS the rollback mechanism. The enforce-mode prerequisites are
already met: **Layer 3 concurrency was load-tested** (the launch gate for shifting ~8.8%→~25% of
traffic there): 16/16 success at each of 1/4/8 concurrent workers against live Supabase, p50
819→974ms, p95 1.3→2.0s, 6 req/s sustained — orders of magnitude above real PDF-drop traffic.
Behavior is pinned by `apps/api/tests/test_match_type_gate.py` (8 tests covering all three modes,
no DB needed), and was verified live against the real Cass County IA collision.

**Still explicitly NOT done after step 1**: the pick within the 45d window is still nearest-date,
not type-aware — a plan whose type matches the *farther* of two near candidates passes the gate but
gets the nearer wrong-type one (confirmed live: `Reconstruct/Rebuild` against the Cass IA pair
returns the Grading `_1` row). That within-window type preference is the deferred tiebreak, to be
evaluated as its own small change after log-only data lands. Also still open: `needs_review=True`
results are still auto-attached (no UI gate analogous to `field_confidence`'s flow); the FAR-ONLY /
type-ambiguous buckets (25.3% + 20.1%) are deliberately untouched pending real log data; and
enforce has not been flipped on yet.

## Agent skills

### Issue tracker

Issues live in GitHub Issues (Tobias-V-Knight/csi-bid-intelligence) via the `gh` CLI; external PRs are not a triage surface. See `docs/agents/issue-tracker.md`.

### Triage labels

Default vocabulary: `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: one `CONTEXT.md` + `docs/adr/` at the repo root (neither exists yet, created lazily). See `docs/agents/domain.md`.
