# CSI Bid Intelligence

Decision support for CSI's bid/no-bid process on Minnesota DOT highway construction lettings.
The system reads a project plan set (PDF), extracts structured bid facts from it, and answers
questions about the project against CSI's historical bid corpus — including which competitors are
likely to bid and how threatening they are.

Two workstreams share this repo: the **plan reader** (PDF → structured facts) and the
**competitor intelligence model** (historical bids → participation ranking).

## Layout

| Directory | What lives here |
|---|---|
| `apps/` | The running product — `apps/api` (FastAPI, :8010) and `apps/web` (Next.js, :3000). |
| `pipelines/` | The two processing modules: `plan_reader/` and `ci_model/`. |
| `research/` | Notebooks and one-off analysis. Not part of any runtime path. |
| `data/` | Shared inputs and outputs — `raw/`, `processed/`, `reference/`, plus the cleaning script. |
| `docs/` | Architecture, changelog, and archived documents. |
| `reference/` | Three competitor CSVs read by nine scripts via CWD-relative paths. See ARCHITECTURE.md. |

## Running it

Backend:

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r apps/api/requirements.txt
cd apps/api && uvicorn app:app --port 8010     # docs at http://localhost:8010/docs
```

Frontend, in a second shell:

```bash
cd apps/web && npm install && npm run dev      # http://localhost:3000
```

The frontend proxies to the backend at `http://127.0.0.1:8010`; override with `BIDINTEL_API_URL`.

## Fresh-clone gotcha — read this before filing a bug

Two artifacts are gitignored because they are large and regenerable, but the system **cannot run
without them**. A fresh clone will appear to work and silently return stale results:

| Artifact | Size | Recovery |
|---|---|---|
| `pipelines/ci_model/03_training/outputs/ranking_predictions.csv` | 94 MB | `pipelines/ci_model/README.md` |
| `pipelines/plan_reader/06_chroma/` | 1.5 GB | `pipelines/plan_reader/README.md` |

Without `ranking_predictions.csv` the competitor-report subprocess fails, `live_report()` returns
`None`, and the app falls back to a **stale pre-generated report** — the UI renders normally and
nothing looks broken. If competitor reports seem out of date, check this first.

## Architecture

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — the system-level reference for the three
orchestrations, where every external API call happens, and the known rough edges. That document is
the single source of truth for system design; this README deliberately does not duplicate it.

For agent sessions working in this repo, start with [`CLAUDE.md`](CLAUDE.md).

---

_The pre-restructure README (2026-06-07) is preserved at
[`docs/ARCHIVE_README_2026-06-07.md`](docs/ARCHIVE_README_2026-06-07.md) — archived, not deleted._
