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
from typing import List, Optional, Union

from fastapi import Body, FastAPI, File, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, Response, StreamingResponse
from pydantic import BaseModel

from backend.config import settings
from backend import plan_reader_bridge as pr, trace
from backend import report as report_svc, final_report as fr
from backend.rag import agentic_answer
from backend.observability import get_logger

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
# The SAME pipeline Chainlit's _handle_pdf runs (report.process_pdf → final_report.assemble), exposed
# as one HTTP call. Returns the canonical `final` dict so the frontend can render the report card AND
# scope the chat to the just-dropped plan (set active_plan_id = final.plan_id). Synchronous-ish: a new
# plan takes ~2 min (convert → index → 2 Claude passes); a re-drop of seen content returns in ~0s
# (content-hash payload cache). The blocking work runs in a threadpool so the event loop stays free.
@app.post("/api/report", tags=["report"])
async def report(file: UploadFile = File(...)):
    """Run the Plan Reader pipeline on an uploaded PDF and return the assembled final report.
    On a drawings-only plan-set (no proposal pages) returns {ok: False, message} instead of raising."""
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

    final = await run_in_threadpool(fr.assemble, plan_payload=rep)
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


def _sse(obj: dict) -> str:
    """Format one Server-Sent Event frame."""
    return f"data: {json.dumps(obj, default=str, ensure_ascii=False)}\n\n"
