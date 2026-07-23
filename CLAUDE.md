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
| `apps/api/` | The FastAPI backend (:8010). The chat agent loop, report assembly, tool implementations. | Contain pipeline logic. It calls pipelines, it does not reimplement them. |
| `apps/web/` | The Next.js frontend (:3000). UI only. | Call any LLM. It proxies to `apps/api` and nothing else. |
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
No OpenAI, Gemini, Cohere, LangChain, or LiteLLM anywhere in the tree. The only other outbound
network call is a US Census TIGER shapefile download in `data/clean_mn_pit_list.py:67`. Embeddings
are **local** (MiniLM via Chroma), not an API call. Keep it that way unless asked.

**4. Gitignored does not mean unnecessary.**
Two artifacts are gitignored as "regenerable" but are required at runtime. See rough edge 1.

**5. Apply the fresh-clone test, not the provenance test.**
When deciding where a file belongs, the question is **"does a fresh clone need this to run?"** — not
"was this authored or generated?". The provenance question has produced five silent dependency
misclassifications in this repo. Every one of them was a directory that looked uniformly derived but
held something load-bearing.

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

**5. `plan_reader` and `ci_model` do not connect.**

`plan_reader` emits **stationing** (`project_stationing`,
`pipelines/plan_reader/04_tools/_scan_field_locations.py:111`). `ci_model` consumes **latitude and
longitude** (`orchestrator.py:173`) to reach pit-distance features. **Nothing in this repo converts
stationing to coordinates.** The only path between them is a human typing coordinates through the
`record_correction` tool. Do not write code that assumes the two modules share a location format.

## Agent skills

### Issue tracker

Issues live in GitHub Issues (Tobias-V-Knight/csi-bid-intelligence) via the `gh` CLI; external PRs are not a triage surface. See `docs/agents/issue-tracker.md`.

### Triage labels

Default vocabulary: `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: one `CONTEXT.md` + `docs/adr/` at the repo root (neither exists yet, created lazily). See `docs/agents/domain.md`.
