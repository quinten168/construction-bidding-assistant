# CSI Bid Assistant

A conversational **bid-intelligence assistant** for highway construction — a FastAPI backend
serving a Next.js frontend (`apps/web`), answering questions about CSI's plans and
bidding record with grounded, cited answers.

> **t/live-stack note:** the Chainlit UI that used to mount at `/chat` was removed on this branch.
> The Next.js frontend replaced it; `app.py` no longer imports chainlit and `chat/` is not shipped.

## What it does
The assistant is **agentic**: Claude (Sonnet 4.6) is given tools and decides which to use per question.

| Question | Tool | Source |
|---|---|---|
| What does a plan require? (wages, phasing, gotchas) | `search_plans` | plan PDFs via ChromaDB — answers cite the page |
| How many bids has CSI placed / won? (by state/year) | `query_bid_history` | the master bid CSV |
| Tell me about a specific named/located project | `find_projects` | a unified registry (1,700 projects) → drills into the others |

## Run it
From the repo root (`01_Summer_2026/`), with the interpreter that has the RAG stack:
```bash
cd apps/api
../../.venv/bin/python3 -m uvicorn app:app --reload --port 8000
#   chat UI : http://localhost:8000/chat
#   API docs: http://localhost:8000/docs   ·   health: /health
```
Tests (no API calls): `../../.venv/bin/python3 -m pytest`

## Architecture
```
app.py                       FastAPI entry — /health, /api/chat (SSE), /api/report, /api/report/export, /docs
backend/
  config.py                  env-driven settings + startup validation (12-factor)
  observability.py           structured stdout logging + per-tool timing/tracing
  tools.py                   the tool registry (uniform schema+run interface; add a tool here)
  rag.py                     the agentic answer loop (stream → run tools off-thread → repeat)
  plan_reader_bridge.py      reuses the Plan Reader's Chroma store + retriever (single source of truth)
  bid_data.py                query_bid_history tool (pandas over the master CSV)
  project_registry.py        find_projects tool (entity resolution: identifier > location > fuzzy name)
  final_report.py            fuses Plan Reader output + competitor report into the one-pager
  competitor_report.py       parses the CI team's bid_report_P*.md (pipelines/ci_model/reports)
tests/                       pytest suite for the data tools
Dockerfile / .dockerignore   deploy-ready (build from repo root)
```

### Backend engineering notes
- **Non-blocking tools.** The Chroma query and pandas work are synchronous; the agent loop runs them
  via `asyncio.to_thread` so a slow retrieval doesn't block the event loop / other users.
- **Tool registry.** Tools share one `(schema, run) → (text, sources)` contract; the loop is generic.
  Adding a capability = one entry in `tools.py`.
- **Resilient.** A tool failure becomes an error *result the model can recover from*, not a crashed
  stream. The whole turn is wrapped so a fatal error yields a clean message.
- **Observable.** Every turn logs the question, each tool call (args, result size, latency), to stdout
  (captured by Docker/Railway). Set `BID_LOG_LEVEL=DEBUG` for more.
- **Grounded.** Answers come only from tool results; the model is instructed to say "not found" rather
  than guess, and to cite plan pages as `[n]`.

## Config (env vars, all optional)
`ANTHROPIC_API_KEY` (falls back to `plan_reader/.env`) · `BID_CHAT_MODEL` · `BID_RETRIEVE_K` ·
`BID_MAX_HISTORY` · `BID_ANSWER_MAX_TOKENS` · `BID_LOG_LEVEL`. See `.env.example`.

## Status
v1: conversational, agentic (3 tools), grounded + cited, tested, deploy-ready. **Next:** PDF-drop →
report card (archetype + gotchas + charts); per-plan scope control; theming; Railway deploy.
