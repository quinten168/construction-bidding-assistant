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

## Working rules

- **Verify paths with `git ls-files` before writing them into code or docs.** Several documents in
  this repo cite paths and line numbers that have drifted. If you cannot verify a behavior, write
  `UNVERIFIED` rather than inferring it.
- **Do not delete or relocate a directory because it looks like dead output.** Grep for the basename
  first, and check whether hits are reads or writes. Watch for basename collisions — `outputs/`
  produces false hits across four different modules.
- **Prove a subprocess ran; do not trust an HTTP 200.** See rough edge 2.
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

`apps/api/backend/competitor_live.py:113–122` returns `None` on timeout, `CalledProcessError`, or
any exception. The caller then falls back to a **stale pre-generated report**, so the API returns
HTTP 200 with plausible competitive output while the subprocess is dead. This is documented at
`apps/api/backend/config.py:56–60`.

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
- **Not verified**: no run against a real Supabase connection. `SUPABASE_TEAM_DB_URL` was never
  configured in the dev sandbox this was built in, so the 15 new integration tests
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

## Agent skills

### Issue tracker

Issues live in GitHub Issues (Tobias-V-Knight/csi-bid-intelligence) via the `gh` CLI; external PRs are not a triage surface. See `docs/agents/issue-tracker.md`.

### Triage labels

Default vocabulary: `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: one `CONTEXT.md` + `docs/adr/` at the repo root (neither exists yet, created lazily). See `docs/agents/domain.md`.
