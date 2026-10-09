# AGENTS.md

Context for AI coding assistants working in this repository. Humans should start with
`README.md` (setup and how to run it) and `docs/ARCHITECTURE.md` (the system reference).

---

## What this system is

Decision support for a highway construction contractor's bid/no-bid decisions on Minnesota DOT
highway lettings. A user uploads a project plan set (PDF) and asks questions about it. The system
answers from two sources: facts extracted from that PDF, and the client's historical bid corpus,
which also drives a model predicting which competitors are likely to bid.

It is decision support, not a classifier. The output informs a human estimator; it does not emit a
bid/no-bid verdict.

## Folder responsibilities

Each directory has one job.

| Directory | Owns | Does NOT |
|---|---|---|
| `apps/api/` | The FastAPI backend (:8010). Chat agent loop, report assembly, tool implementations, CI-data admin endpoints. | Contain pipeline logic. It calls pipelines, it does not reimplement them. |
| `apps/web/` | The Next.js frontend (:3000). UI only. | Call any LLM. It proxies to `apps/api` for everything except Google Maps on the pit-list page. |
| `pipelines/plan_reader/` | PDF to structured facts. Conversion, chunking, indexing, extraction. | Know anything about competitors or bid history. |
| `pipelines/ci_model/` | Historical bids to competitor participation ranking and reports. | Know anything about PDFs. |
| `data/` | Shared inputs/outputs and the scripts that produce them. | Hold module-private intermediates. Those stay in the module. |
| `docs/` | `ARCHITECTURE.md` (system reference), data access and inventory notes. | |
| `reference/` | Competitor reference CSVs. | |

## Architectural invariants

These are load-bearing. Breaking one will not fail loudly.

**1. `apps/` and `pipelines/` are not coupled by imports.**
There are no Python imports from `apps/` into `pipelines/` or back. The two trees have separate
dependency sets. Where the backend needs pipeline logic it either shells out or maintains a
deliberate hand-written mirror.

One such mirror matters: `apps/api/backend/competitor_predict_live.py::_candidate_pool()` reproduces
6 of the 10 signals in `pipelines/ci_model/01_candidates/candidate_filter.py::build_v3_candidate_set`
as hand-written SQL. It WILL drift if `candidate_filter.py` or `pipelines/ci_model/shared/config.py`'s
`V3_*` constants change without a matching edit here. `apps/api/tests/test_candidate_pool_consistency.py`
catches that drift, but only when `SUPABASE_TEAM_DB_URL` is set.

**2. `pipelines/` is path-referenced, never imported as a package.**
It is referred to only by path strings, concentrated in `apps/api/backend/config.py`. The numbered
directory names (`01_pipeline/`, `06_reporting/`) are not importable identifiers, and the design
depends on them never needing to be. Do not add `__init__.py` files under `pipelines/`.

**3. Anthropic is the only LLM provider.**
No OpenAI, Gemini, Cohere, LangChain, or LiteLLM anywhere in the tree. Embeddings are local
(MiniLM via Chroma), not an API call.

Non-LLM outbound calls: a US Census TIGER shapefile download in `data/clean_mn_pit_list.py`, and up
to 6 state DOT GIS REST endpoints called from `apps/api/backend/midpoint_bridge.py`. The latter is
gated by `settings.midpoint_lookup_enabled` and fails open (null latitude/longitude) on any error
or timeout. It never raises into the report.

**4. Gitignored does not mean unnecessary.**
See the fresh-clone section of `README.md` for the two large gitignored artifacts and what each
one's absence actually changes.

**5. Ask "does a fresh clone need this to run?", not "was this generated?"**
When deciding where a file belongs, provenance is the wrong question. Directories that look
uniformly derived (an `outputs/` folder of JSON, a knowledge folder of CSVs) routinely hold
something load-bearing. Grep for the basename before concluding a file is dead.

## Working rules

- **Verify paths with `git ls-files` before writing them into code or docs.** If you cannot verify
  a behavior, write `UNVERIFIED` rather than inferring it.
- **A success signal at the wrong layer is not evidence.** HTTP 200 is a transport fact, not an
  application fact. A SQL statement completing is a syntax fact, not an effect fact. Verify by
  observing the changed state, and never let a failure and a legitimate empty answer share a
  return value. This applies to the state DOT GIS endpoints in particular: ArcGIS returns
  application errors as HTTP 200 with an `{"error": {...}}` body, so a genuine bad route number
  and a DOT outage currently look identical in the logs.
- **A negative result from a fixed set of checks is not proof of absence.** When code answers
  "is this safe / ambiguous / a duplicate?", enumerate the ways the underlying operation can lose
  data and confirm each has a check. Do not enumerate the checks and assume they cover it.
- **Do not add features while cleaning.** Cleanup commits and behavior commits stay separate.

## Things to know before debugging

- **Material tonnage conversion is behind a flag that is OFF.**
  `pipelines/plan_reader/01_pipeline/material_tons_merge.py::CONVERSION_ENABLED` is computed at
  import from three gates and evaluates to False. CY and SY measured bid items are extracted and
  reported with a status, but are never converted into `base_tons`/`shldr_tons`/`mix_tons`. The
  third gate is `PLAN_READER_MATERIAL_CONVERSION=on`; the other two require a signed density-factor
  table and a recorded acceptance run. Inaction is the safe state in all three, so a fresh clone is
  off with no action taken. Pinned by `apps/api/tests/test_2026_08_10_conversion_flag_off.py`.

- **Arithmetic is done in Python, never by the model.** Extraction prompts ask for raw per-item
  quantities and stated depths only. Every multiplication and sum happens in
  `schema.resolve_cy_item` / `resolve_sy_depth_product` and `material_tons_merge.py`. This is
  deliberate: the model reliably adds two already-stated numbers but does not reliably multiply,
  and it has returned values that disagreed with the arithmetic in its own reasoning text. Do not
  move arithmetic back into a prompt.

- **The CI-data admin features write live to Supabase `scratch.*`.** They do not feed back into
  `ci_model`'s local training CSVs. An estimator entering bid results or editing the pit list
  through the UI will not be reflected in the next `ci_model` training run until someone builds a
  pull script for `bid_results`/`mn_pit_list`.

- **The PDF-drop path is two phases with a human verify gate between them.** `POST /api/report`
  runs extraction and returns it unverified. `POST /api/report/{plan_id}/finalize` is what a human
  triggers to run the rest of the report. See `docs/ARCHITECTURE.md`.

- **`plan_reader` and `ci_model` do not connect.** A freshly uploaded plan's coordinates reach the
  report, not the competitor-prediction pipeline. Do not write code that assumes otherwise.

- **`apps/api` and `pipelines/ci_model` each own a separate direct Postgres connection**
  (`apps/api/backend/ci_db.py` and `pipelines/ci_model/06_reporting/tools/capacity_live.py`), both
  using `SUPABASE_TEAM_DB_URL`. Each Postgres-facing script in this repo owns its own connector
  rather than sharing one across the `apps/`/`pipelines/`/`data/` boundary. Keep it that way.
