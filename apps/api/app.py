"""
Bid Assistant — application entry point.

A FastAPI app exposing the JSON API that the Next.js frontend (apps/web) talks to:
/api/chat (SSE), /api/report, /api/report/export. Run locally with:

    cd apps/api
    uvicorn app:app --port 8010
    #   API docs: http://localhost:8010/docs
    #   the UI   : see apps/web (npm run dev -> :3000)

The Chainlit chat UI that used to mount at /chat was removed on the t/live-stack branch — the
Next.js frontend replaced it and the Chainlit path was dead. Only ONE backend may run at a time:
two uvicorn instances writing the same persistent Chroma index corrupt the HNSW segment.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Make the app root importable (so `backend...` and the mounted chat resolve regardless of cwd).
APP_ROOT = Path(__file__).resolve().parent
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

import json
import tempfile
from pathlib import Path as _Path
from typing import Dict, List, Optional, Union

from fastapi import Body, FastAPI, File, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from pydantic import BaseModel

from backend import config as config_mod
from backend.config import settings
from backend import plan_reader_bridge as pr, trace
from backend import report as report_svc, final_report as fr
from backend.rag import agentic_answer
from backend.observability import get_logger
from backend import bid_results_admin, competitor_registry_admin, pit_list_admin, project_admin
from backend.ci_db import ConfigError

log = get_logger("bid_assistant.app")

app = FastAPI(
    title="CSI Bid Assistant API",
    description="Conversational RAG + plan analysis over the CSI plan corpus.",
    version="0.1.0",
)


@app.on_event("startup")
def _on_startup() -> None:
    """Log the resolved config and surface any problems loudly (don't fail silently)."""
    log.info("starting · model=%s · k=%d", settings.chat_model, settings.retrieve_k)
    for w in settings.warnings():
        log.warning("config: %s", w)
    # Hard-fail on a missing/placeholder Supabase DSN, naming the exact file and variable. Silent
    # unset is what made this "works on one machine": the app booted fine and failed later with an
    # error that pointed nowhere near the cause. ALLOW_NO_SUPABASE=1 opts out.
    config_mod.require_supabase_dsn()


# --- schemas (Pydantic gives validation + the auto-generated /docs) ------------------------------
class HealthResponse(BaseModel):
    status: str                      # "ok" | "degraded"
    model: str
    indexed_plans: Optional[int] = None
    warnings: List[str] = []


class SearchHit(BaseModel):
    source_file: str
    page: Optional[Union[str, int]] = None
    section: Optional[str] = None
    distance: float
    text: str


class Turn(BaseModel):
    """One prior turn of the conversation, as the client replays it back to this stateless API."""
    role: str                        # "user" | "assistant"
    content: str


class ChatRequest(BaseModel):
    question: str
    history: List[Turn] = []         # prior turns (the frontend owns conversation state)
    active_plan_id: Optional[str] = None
    session_id: Optional[str] = None  # groups turns into a conversation; the frontend supplies it
    user_id: Optional[str] = None


class FeedbackRequest(BaseModel):
    turn_id: str
    rating: int                      # +1 (good) | -1 (bad)
    reason: Optional[str] = None


class ReportFinalizeIn(BaseModel):
    extraction: dict                 # the unverified `extraction` payload from POST /api/report
    edits: Dict[str, str] = {}       # {field: value} — only what the user actually confirmed/changed
    manual_competitors: List[str] = []  # names the estimator typed into the optional 2nd verify popup


# --- CI-data admin schemas (bid results / pit list / competitor registry) -----------------------
class BidEntryIn(BaseModel):
    raw_bidder_name: str
    bid_amount: float
    is_winner: bool = False


class BidResultsIn(BaseModel):
    entries: List[BidEntryIn]


class BidResultUpdateIn(BaseModel):
    raw_bidder_name: Optional[str] = None
    bid_amount: Optional[float] = None
    did_win: Optional[bool] = None


class ProjectMaterialsUpdateIn(BaseModel):
    mix_tons: Optional[float] = None
    grading_yards: Optional[float] = None
    base_tons: Optional[float] = None
    shldr_tons: Optional[float] = None
    mill_sy: Optional[float] = None
    crush_tons: Optional[float] = None
    stock_tons: Optional[float] = None


class PitIn(BaseModel):
    """Create-only model — every field is required here (the system boundary for the "make all
    fields required" pit-list rule). PitUpdateIn below stays fully optional; partial edits are a
    different, legitimate use case."""
    latitude: float
    longitude: float
    name: str
    access: str
    county: str
    rating: int
    state: str
    access_type: str
    access_company: str
    force: bool = False


class PitUpdateIn(BaseModel):
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    name: Optional[str] = None
    access: Optional[str] = None
    county: Optional[str] = None
    rating: Optional[int] = None
    state: Optional[str] = None
    access_type: Optional[str] = None
    access_company: Optional[str] = None
    force: bool = False


class CompetitorIn(BaseModel):
    name: str
    top_competitors_tag: Optional[str] = None
    force: bool = False


class ConsolidateIn(BaseModel):
    raw_name_variants: List[str]
    target_comp_name: str


# --- endpoints -----------------------------------------------------------------------------------
@app.get("/health", response_model=HealthResponse, tags=["meta"])
def health() -> HealthResponse:
    """Readiness: confirm the vector store loads and config is sane. Reports 'degraded' (not a 500)
    with details if something's off, so a load balancer / you can see *why* at a glance."""
    warnings = settings.warnings()
    indexed = None
    try:
        indexed = len(pr.indexed_plans())
    except Exception as e:                                   # noqa: BLE001
        warnings.append(f"Vector store not reachable: {e}")
    return HealthResponse(status="ok" if not warnings else "degraded",
                          model=settings.chat_model, indexed_plans=indexed, warnings=warnings)


@app.get("/api/search", response_model=List[SearchHit], tags=["rag"])
async def search(q: str, k: int = 5) -> List[SearchHit]:
    """Raw retrieval — useful for inspecting *what* the vector store returns for a query
    (the debugging window into the RAG, separate from the conversational answer)."""
    hits = pr.retrieve(q, k)
    return [SearchHit(source_file=h["meta"].get("source_file", "?"),
                      page=h["meta"].get("page"), section=h["meta"].get("section"),
                      distance=h["distance"], text=h["text"]) for h in hits]


# --- conversational API (frontend-agnostic; the Next.js app calls this instead of Chainlit) ------
# The SAME agent loop, capture, and tools serve both Chainlit and any HTTP client. We stream Server-
# Sent Events with a small, explicit JSON protocol — one event per line:
#   {"type":"token","text":"…"}        incremental answer text (many)
#   {"type":"turn","turn_id":"…"}      the captured turn's id (use it to POST /api/feedback)
#   {"type":"sources","sources":[…]}   the cited passages (once, at the end)
#   {"type":"done"}                    stream complete
# A thin Next.js route (or a custom useChat transport) maps these to the AI SDK's UI stream.
@app.post("/api/chat", tags=["chat"])
async def chat(req: ChatRequest):
    """Stream an agentic, cited answer over SSE. Conversation state is client-owned (the frontend
    replays `history`); every turn is still captured server-side via the agent loop."""
    history = [{"role": t.role, "content": t.content} for t in req.history]

    async def event_stream():
        try:
            async for kind, payload in agentic_answer(
                history, req.question, active_plan_id=req.active_plan_id,
                session_id=req.session_id, user_id=req.user_id,
            ):
                if kind == "token":
                    yield _sse({"type": "token", "text": payload})
                elif kind == "turn":
                    yield _sse({"type": "turn", "turn_id": payload})
                elif kind == "sources":
                    yield _sse({"type": "sources", "sources": [
                        {"source_file": h["meta"].get("source_file"),
                         "page": h["meta"].get("page"), "section": h["meta"].get("section"),
                         "doc_id": h["meta"].get("doc_id"), "distance": h.get("distance"),
                         # the REAL retrieved passage (truncated) so the UI shows the actual cited
                         # text on click, not a mock excerpt
                         "text": (h.get("text") or "")[:700]}
                        for h in payload]})
                elif kind == "usage":
                    # real per-turn token usage + the real model id (the honest context signal)
                    yield _sse({"type": "usage", **payload})
            yield _sse({"type": "done"})
        except Exception as e:                              # noqa: BLE001 — close the stream cleanly
            log.exception("/api/chat stream failed")
            yield _sse({"type": "error", "message": f"{type(e).__name__}: {e}"})

    return StreamingResponse(event_stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.post("/api/feedback", tags=["chat"])
async def feedback(req: FeedbackRequest):
    """Attach a thumbs rating to a captured turn (patches both the SQLite row and the JSONL archive).
    The cheapest, highest-signal label for the over-time eval framework."""
    found = await trace.update_feedback(req.turn_id, rating=req.rating, reason=req.reason)
    return {"ok": found, "turn_id": req.turn_id}


# --- report API (PDF drop → structured final report; the Next.js report-card consumes this) -------
# Two-phase as of 2026-07-31 (human-in-the-loop verify gate between extraction and assembly):
#   ① POST /api/report            — report_svc.process_pdf only. Returns {extraction} for the verify
#                                    UI, UNLESS this exact content was already verified before (cache
#                                    hit — process_pdf returns verified=True), in which case it skips
#                                    straight to assemble() and returns {final}, same as pre-2026-07-31.
#   ② POST /api/report/{id}/finalize — report_svc.apply_verification (bakes the human's edits into the
#                                    SAME payload quantities live in, and caches it) → final_report.
#                                    assemble(). This is where the competitor-intel subprocess fires.
# Synchronous-ish: a new plan takes ~2 min (convert → index → 2 Claude passes) for step ①; step ② is
# whatever assemble()'s competitor-intel generation takes. The blocking work runs in a threadpool.
@app.post("/api/report", tags=["report"])
async def report(file: UploadFile = File(...)):
    """Run the Plan Reader pipeline on an uploaded PDF and return either an unverified `extraction`
    (the normal case — frontend shows the verify gate next) or an already-`final` report (re-drop of
    previously-verified content). On a drawings-only plan-set returns {ok: False, message}."""
    # Persist the upload under its original name; the pipeline's caches key off CONTENT (hash), not
    # the path, so a re-drop under any name still hits the cache.
    tmp = _Path(tempfile.mkdtemp()) / (file.filename or "plan.pdf")
    tmp.write_bytes(await file.read())

    try:
        rep = await run_in_threadpool(report_svc.process_pdf, str(tmp))
    except Exception as e:                                  # noqa: BLE001
        log.exception("/api/report processing failed")
        return {"ok": False, "message": f"Could not read that PDF ({type(e).__name__})."}

    if not rep.get("ok"):                                  # handled case (e.g. plan-set-only)
        return {"ok": False, "message": rep.get("message", "Could not read that PDF."),
                "reason": rep.get("reason")}

    if rep.get("verified"):                                # cache hit on an already-finalized plan
        final = await run_in_threadpool(fr.assemble, plan_payload=rep)
        return {"ok": True, "final": final}

    return {"ok": True, "extraction": rep}


@app.post("/api/report/{plan_id}/finalize", tags=["report"])
async def report_finalize(plan_id: str, req: ReportFinalizeIn):
    """Step ② of the verify gate: bake the human's confirmed/edited fields into the extraction
    payload, cache it, and assemble the final report (this is where the competitor-intel subprocess
    runs). `plan_id` is accepted for URL/logging clarity but the actual payload lookup is via
    `req.extraction["content_hash"]`, round-tripped from step ①'s response."""
    rep = await run_in_threadpool(report_svc.apply_verification, req.extraction, req.edits)
    final = await run_in_threadpool(fr.assemble, plan_payload=rep,
                                    manual_competitors=req.manual_competitors)
    return {"ok": True, "final": final}


def _safe_filename(final: dict) -> str:
    """A tidy download stem from the report title/plan_id: 'Chippewa Co, MN' -> 'chippewa-co-mn'."""
    import re as _re
    raw = (final.get("title") or final.get("plan_id") or "bid-report")
    stem = _re.sub(r"[^a-z0-9]+", "-", str(raw).lower()).strip("-")
    return stem or "bid-report"


@app.post("/api/report/export", tags=["report"])
async def report_export(payload: dict = Body(...)):
    """Render an already-assembled `final` report to a downloadable file. The frontend POSTs the
    same `final` dict it got from /api/report plus a `fmt` (md|csv|pdf) — no pipeline re-run, so a
    download is instant. PDF goes through pandoc+xelatex; if that toolchain is missing we fall back
    to markdown so the button never silently fails."""
    fmt = str(payload.get("fmt") or "md").lower()
    final = payload.get("final")
    if not isinstance(final, dict) or not final.get("plan_id"):
        return Response('{"ok": false, "message": "no report payload"}',
                        media_type="application/json", status_code=400)
    stem = _safe_filename(final)

    if fmt == "csv":
        return Response(fr.to_csv(final), media_type="text/csv",
                        headers={"Content-Disposition": f'attachment; filename="{stem}.csv"'})
    if fmt == "pdf":
        out = _Path(tempfile.mkdtemp()) / f"{stem}.pdf"
        path = await run_in_threadpool(fr.to_pdf, final, str(out))
        if path:
            return FileResponse(str(path), media_type="application/pdf", filename=f"{stem}.pdf")
        # pandoc/xelatex unavailable → hand back markdown (with the real extension) rather than 500
        return Response(fr.to_markdown(final), media_type="text/markdown",
                        headers={"Content-Disposition": f'attachment; filename="{stem}.md"',
                                 "X-Export-Fallback": "pdf-unavailable"})
    return Response(fr.to_markdown(final), media_type="text/markdown",
                    headers={"Content-Disposition": f'attachment; filename="{stem}.md"'})


# --- CI-data admin API (bid results / pit list / competitor registry) ---------------------------
# First place this backend writes to Postgres directly (Supabase's `scratch` schema — see
# docs/DATA_ACCESS_SCRATCH.md) rather than a local CSV. See backend/ci_db.py, backend/
# bid_results_admin.py, backend/pit_list_admin.py, backend/competitor_registry_admin.py.
def _ci_error(e: Exception) -> JSONResponse:
    if isinstance(e, ConfigError):
        return JSONResponse({"ok": False, "message": str(e)}, status_code=503)
    if isinstance(e, (bid_results_admin.ValidationError, pit_list_admin.ValidationError,
                      competitor_registry_admin.ValidationError, project_admin.ValidationError)):
        return JSONResponse({"ok": False, "message": str(e)}, status_code=400)
    if isinstance(e, (pit_list_admin.DuplicateWarning, competitor_registry_admin.DuplicateWarning)):
        return JSONResponse({"ok": False, **e.payload}, status_code=409)
    log.exception("CI-data admin endpoint failed")
    return JSONResponse({"ok": False, "message": f"{type(e).__name__}: {e}"}, status_code=500)


@app.get("/api/ci-data/projects", tags=["ci-data"])
async def ci_list_projects(search: Optional[str] = None):
    """Every scratch.bid_projects row — the projects table (view + edit materials, no create)."""
    try:
        rows = await run_in_threadpool(project_admin.list_projects, search)
        return {"ok": True, "projects": rows}
    except Exception as e:                                  # noqa: BLE001
        return _ci_error(e)


@app.patch("/api/ci-data/projects/{project_natural_key}/materials", tags=["ci-data"])
async def ci_update_project_materials(project_natural_key: str, req: ProjectMaterialsUpdateIn):
    """Inline-edit one project's material-quantity fields. Everything else on this table (identity,
    location, project_type) is read-only from this endpoint."""
    try:
        fields = req.model_dump(exclude_none=True)
        result = await run_in_threadpool(
            project_admin.update_project_materials, project_natural_key, fields)
        return {"ok": True, **result}
    except Exception as e:                                  # noqa: BLE001
        return _ci_error(e)


@app.get("/api/ci-data/projects/missing-results", tags=["ci-data"])
async def ci_projects_missing_results(search: Optional[str] = None):
    """Projects with zero bid_results rows yet — the picker for the bid-results-entry feature."""
    try:
        rows = await run_in_threadpool(bid_results_admin.list_projects_missing_results, search)
        return {"ok": True, "projects": rows}
    except Exception as e:                                  # noqa: BLE001
        return _ci_error(e)


@app.post("/api/ci-data/projects/{project_natural_key}/bid-results", tags=["ci-data"])
async def ci_submit_bid_results(project_natural_key: str, req: BidResultsIn):
    """Record up to 5 bidders (one marked winner) for a project that has no results yet."""
    try:
        entries = [e.model_dump() for e in req.entries]
        result = await run_in_threadpool(bid_results_admin.submit_bid_results, project_natural_key, entries)
        return {"ok": True, **result}
    except Exception as e:                                  # noqa: BLE001
        return _ci_error(e)


@app.get("/api/ci-data/bid-results", tags=["ci-data"])
async def ci_list_bid_results(search: Optional[str] = None):
    """Every recorded bid result, joined to its project — one row per bidder, the full table."""
    try:
        rows = await run_in_threadpool(bid_results_admin.list_bid_results, search)
        return {"ok": True, "results": rows}
    except Exception as e:                                  # noqa: BLE001
        return _ci_error(e)


@app.patch("/api/ci-data/bid-results/{project_natural_key}/{competitor_unit_id}", tags=["ci-data"])
async def ci_update_bid_result(project_natural_key: str, competitor_unit_id: str, req: BidResultUpdateIn):
    """Inline-edit one bidder's name/amount/winner-flag on a project that already has results."""
    try:
        fields = req.model_dump(exclude_none=True)
        result = await run_in_threadpool(
            bid_results_admin.update_bid_result, project_natural_key, competitor_unit_id, fields)
        return {"ok": True, **result}
    except Exception as e:                                  # noqa: BLE001
        return _ci_error(e)


@app.get("/api/ci-data/pits", tags=["ci-data"])
async def ci_list_pits(search: Optional[str] = None):
    try:
        rows = await run_in_threadpool(pit_list_admin.list_pits, search)
        return {"ok": True, "pits": rows}
    except Exception as e:                                  # noqa: BLE001
        return _ci_error(e)


@app.post("/api/ci-data/pits", tags=["ci-data"])
async def ci_create_pit(req: PitIn):
    """Add a pit. Blocks on an exact (latitude, longitude) match; returns a 409 warning (not a
    hard block) on a name+county match at different coordinates unless `force` is set."""
    try:
        fields = req.model_dump(exclude={"force"})
        result = await run_in_threadpool(pit_list_admin.create_pit, fields, req.force)
        return {"ok": True, **result}
    except Exception as e:                                  # noqa: BLE001
        return _ci_error(e)


@app.patch("/api/ci-data/pits/{lat}/{lon}", tags=["ci-data"])
async def ci_update_pit(lat: float, lon: float, req: PitUpdateIn):
    try:
        fields = req.model_dump(exclude_none=True)
        result = await run_in_threadpool(pit_list_admin.update_pit, lat, lon, fields)
        return {"ok": True, **result}
    except Exception as e:                                  # noqa: BLE001
        return _ci_error(e)


@app.delete("/api/ci-data/pits/{lat}/{lon}", tags=["ci-data"])
async def ci_delete_pit(lat: float, lon: float):
    try:
        await run_in_threadpool(pit_list_admin.delete_pit, lat, lon)
        return {"ok": True}
    except Exception as e:                                  # noqa: BLE001
        return _ci_error(e)


@app.get("/api/ci-data/competitors", tags=["ci-data"])
async def ci_list_competitors(needs_review_only: bool = False, search: Optional[str] = None):
    try:
        rows = await run_in_threadpool(competitor_registry_admin.list_registry, needs_review_only, search)
        return {"ok": True, "competitors": rows}
    except Exception as e:                                  # noqa: BLE001
        return _ci_error(e)


@app.post("/api/ci-data/competitors", tags=["ci-data"])
async def ci_add_competitor(req: CompetitorIn):
    """Bootstrap a brand-new canonical competitor. Blocks on an exact normalized-name match;
    returns a 409 warning (not a hard block) on a fuzzy near-match unless `force` is set."""
    try:
        result = await run_in_threadpool(
            competitor_registry_admin.add_competitor, req.name, req.top_competitors_tag, req.force)
        return {"ok": True, **result}
    except Exception as e:                                  # noqa: BLE001
        return _ci_error(e)


@app.post("/api/ci-data/competitors/consolidate", tags=["ci-data"])
async def ci_consolidate_competitors(req: ConsolidateIn):
    """Merge one or more existing raw-name rows onto one canonical name. Registry-only — does not
    touch bid_results.competitor_unit_id (see competitor_registry_admin.py's module docstring)."""
    try:
        result = await run_in_threadpool(
            competitor_registry_admin.consolidate, req.raw_name_variants, req.target_comp_name)
        return {"ok": True, **result}
    except Exception as e:                                  # noqa: BLE001
        return _ci_error(e)


@app.delete("/api/ci-data/competitors/{comp_name}", tags=["ci-data"])
async def ci_remove_competitor(comp_name: str):
    """Remove a competitor. Blocked (400) if any bid_results row still references it — no
    reassignment flow; consolidate those rows into another competitor first."""
    try:
        result = await run_in_threadpool(competitor_registry_admin.remove_competitor, comp_name)
        return {"ok": True, **result}
    except Exception as e:                                  # noqa: BLE001
        return _ci_error(e)


def _sse(obj: dict) -> str:
    """Format one Server-Sent Event frame."""
    return f"data: {json.dumps(obj, default=str, ensure_ascii=False)}\n\n"
