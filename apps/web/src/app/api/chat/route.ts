// ────────────────────────────────────────────────────────────────────────────
// Chat proxy → the real CSI Bid Assistant backend (FastAPI, bid_assistant/app.py).
//
// The browser POSTs here (same-origin, no CORS); we forward to the FastAPI
// `/api/chat` endpoint and stream its Server-Sent Events straight back. Keeping
// the backend URL server-side means it's configurable per-environment and never
// exposed to the client. Set BIDINTEL_API_URL to point at a deployed backend;
// it defaults to the local uvicorn dev server (`uvicorn app:app --port 8010`).
// ────────────────────────────────────────────────────────────────────────────

export const runtime = "nodejs"; // streaming proxy; needs the Node fetch/stream, not edge
export const dynamic = "force-dynamic"; // never cache a live chat stream

const BACKEND = process.env.BIDINTEL_API_URL ?? "http://127.0.0.1:8010";

export async function POST(req: Request) {
  // Pass the client's JSON body through untouched — it already matches the
  // backend's ChatRequest schema (question, history, active_plan_id, …).
  const body = await req.text();

  let upstream: Response;
  try {
    upstream = await fetch(`${BACKEND}/api/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body,
    });
  } catch {
    // Backend unreachable (not started, wrong port) — surface a clean SSE error
    // frame so the UI shows a message instead of hanging on "thinking".
    return sseError(`Cannot reach the bid-assistant backend at ${BACKEND}. Is uvicorn running?`);
  }

  if (!upstream.ok || !upstream.body) {
    return sseError(`Backend returned ${upstream.status}.`);
  }

  // Pipe the SSE body straight through — one transparent passthrough.
  return new Response(upstream.body, {
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache, no-transform",
      Connection: "keep-alive",
      "X-Accel-Buffering": "no",
    },
  });
}

// A single-frame SSE error stream, shaped like the backend's own error event so
// the client parser handles it with no special-casing.
function sseError(message: string): Response {
  const frame = `data: ${JSON.stringify({ type: "error", message })}\n\n`;
  return new Response(frame, {
    headers: { "Content-Type": "text/event-stream", "Cache-Control": "no-cache" },
  });
}
