# `02_modules/` — T's live stack (branch `t/live-stack`)

Branch only. **Not merged, no PR.** This is T's current working stack copied in for team review.
It shares no git history with T's own repo — the files were exported with `git archive` and
committed here as normal work.

## What's here

| Path | What it is |
|---|---|
| `02_modules/plan_reader/` | The current Plan Reader: PDF → Markdown → Chroma → structured extraction. **Replaces the old root `plan_reader/`** (a 2026-06-11 snapshot; 8 files had diverged). |
| `02_modules/bid_assistant/` | FastAPI backend: a 6-tool agentic chat + PDF→report-card endpoint. |
| `02_modules/frontend/` | The live Next.js UI (previously unversioned on T's laptop — this is its first time in git). |
| `02_modules/competitor_intel/reports/` | 20 `bid_report_P*.md` from the CI team's pipeline. Required by the report's competitor section. |
| `01_data/2026-06-03_csi_bid_master.csv` | The bid master. Required by 3 of the 6 chat tools. |

**Nothing outside `01_data/` and `02_modules/` was touched.** `ci_model/`, `clustering/`, `data/`,
`docs/`, `model1/`, `outputs/`, `reference/`, `archived/` are untouched.

## Why the `02_modules/` nesting (don't flatten it)

Three constants climb above their own module and resolve to the repo root:

```
02_modules/bid_assistant/backend/config.py:19   REPO      = HERE.parents[3]
02_modules/plan_reader/01_pipeline/lib.py:25    REPO_ROOT = MODULE_ROOT.parents[1]
```

At this depth they resolve correctly. Flattened to the repo root they resolve to the directory
*containing* this repo — and they wouldn't crash, they'd silently build paths outside the repo and
fail later at `.exists()`. If you ever flatten, fix those constants first.

## Run it

Requires an Anthropic API key and Python 3.9+.

```bash
# 1. backend
cd 02_modules/bid_assistant
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-ant-...        # or create 02_modules/plan_reader/.env  (see .env.example)
.venv/bin/python -m uvicorn app:app --port 8010 --host 127.0.0.1
curl -s localhost:8010/health              # {"status":"ok","model":"claude-sonnet-4-6",...}

# 2. frontend  (separate terminal)
cd 02_modules/frontend
npm install                                # .npmrc sets legacy-peer-deps — see "Known issues"
npm run dev -- -p 3002                     # http://localhost:3002
#   points at 127.0.0.1:8010 by default; override with BIDINTEL_API_URL

# 3. the pipeline on one PDF, no UI
.venv/bin/python 02_modules/plan_reader/run.py inspect path/to/plan.pdf
```

**Only ONE backend may run at a time.** Two uvicorn instances writing the same persistent Chroma
index corrupt the HNSW segment (this has happened).

## What a fresh clone does NOT have

These are gitignored on purpose — they're large, regenerable, or client data:

- **`06_chroma/` (~1.3 GB)** — the vector store. Rebuilds as you ingest plans. Until you ingest,
  corpus-wide `search_plans` returns nothing. Dropping a PDF ingests it.
- **`csi_v2.db` (~160 MB)** — the structured store. **Not required**: `trace.py` self-creates its
  schema on first write, and `final_report.py` guards on `DB_PATH.exists()` and falls back to a
  live gotcha pass. You lose the curated cross-corpus gotcha set, not the report.
- **plan PDFs** — client documents. Bring your own.
- **`~/dev/csi-ci-model`** — the CI team's repo, for live competitor generation and the
  `competitor_record` tool. Point at it with `CI_MODEL_REPO=/path/to/clone`. Without it, the
  report falls back to the static `bid_report_P*.md` files included here.

## Deliberately excluded

`dashboard/`, `sweet_spot/`, `margin_retro/`, `03_docs/`, `99_archive/`, plan_reader's
`07_archive/`/`02_outputs/`/`04_tools/`/`03_evaluation/`, and notebooks. This branch is the
runnable stack, not the whole workspace.

**Chainlit is gone.** `app.py` used to `mount_chainlit(...)` at `/chat`. The Next.js frontend
replaced it, the path was dead, so the import, the mount, and the `chainlit` + `deepeval`
dependencies were removed. Nothing imports chainlit any more.

## Known issues

- **`npm install` needs `legacy-peer-deps`** (set via `02_modules/frontend/.npmrc`, so plain
  `npm install` works). `react-simple-maps@3.0.0` declares a peer of react ≤18; this project is on
  react 19.2.4. It's pulled in only by `src/components/map/territory-map.tsx`, which **nothing
  imports** — delete that component and the dep, and `.npmrc` can go too.
- **`requirements.txt` was missing `pandas`, `rapidfuzz`, and `python-multipart`** until
  2026-07-15. The app imported them but never declared them, so it ran only on a machine that
  already had them. Fixed here — found by installing into a clean venv.
- The `plans_manifest.csv` shipped here is T's; your `run.py` invocations will update it.

## Verified on 2026-07-15 (clean venv, ports 8011/3003)

```
run.py inspect <196-page PDF>   → 561 chunks, extraction + 12 gotcha flags, exit 0
GET  /health                    → {"status":"ok","model":"claude-sonnet-4-6","indexed_plans":1}
POST /api/chat                  → tool query_bid_history fired (42 ms) → "603 total projects"
POST /api/report  (backend)     → HTTP 200, 53 s, 21 KB report
POST /api/report  (via Next)    → HTTP 200 — the UI's own proxy route
npx tsc --noEmit                → clean
```

Not verified: a click-driven upload in the browser. The automation tab runs backgrounded, so the
UI's mount animation never fires and synthetic file events don't reach React's handler. The UI's
exact network path (`POST /api/report` through the Next proxy) was verified and returns a real
report; the click itself was not exercised.
