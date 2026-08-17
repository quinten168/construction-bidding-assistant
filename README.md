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
| `data/` | Shared inputs and outputs — `raw/`, `processed/`, `reference/`, plus the cleaning script. |
| `docs/` | Architecture reference plus data access and inventory notes. |

## Running it

New to this repo? [`docs/SETUP.md`](docs/SETUP.md) walks through repo access, both `.env` files
(including the two optional Google Maps keys), and running both servers, step by step.

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

The system **does run** on a fresh clone with nothing but the two secrets below — a PDF drop
extracts and predicts competitors end-to-end. Two gitignored artifacts change *what kind* of
competitor result you get, not whether the app works at all:

| Artifact | Size | Missing it means |
|---|---|---|
| `pipelines/ci_model/03_training/outputs/ranking_predictions.csv` | 94 MB | The competitor cascade's tier-1 subprocess (fresh reports for projects already in CSI's historical corpus) can't run. Every plan falls through to tier 3 — a **live prediction** built from that plan's own state/type/quantities against Postgres, with a calibrated probability per name. Not stale data (the old static-report tier that could go stale was removed 2026-08-09) — just the less-detailed of the two real cascade tiers. Recovery: `pipelines/ci_model/README.md`. |
| `pipelines/plan_reader/06_chroma/` | grows with usage, ~170 MB after a few dozen plans | Nothing, for a fresh clone — it doesn't need to pre-exist. Each PDF drop auto-creates/writes its own chunks into it on ingest (that's what builds the plan-specific RAG index the extraction step queries). The only thing NOT carried over on a new machine is chat Q&A about plans a *previous* machine already uploaded — that history lives in this directory and doesn't travel with the repo. Copy the directory over if you want it to. |

**What actually blocks a fresh clone**: `ANTHROPIC_API_KEY` and `SUPABASE_TEAM_DB_URL` in `.env`
(copy `.env.example`, ask Tobias for the Supabase password) — without the DSN, the entire
competitor cascade has no data source and prediction fails outright, tier 1 or tier 3.

## Architecture

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — the system-level reference for the three
orchestrations, where every external API call happens, and the known rough edges. That document is
the single source of truth for system design; this README deliberately does not duplicate it.

For agent sessions working in this repo, start with [`CLAUDE.md`](CLAUDE.md).
