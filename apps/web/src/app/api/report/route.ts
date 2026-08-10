// ────────────────────────────────────────────────────────────────────────────
// Report proxy → the real CSI Bid Assistant backend (FastAPI /api/report).
//
// The browser POSTs a multipart form (the dropped plan PDF) here, same-origin;
// we stream it through to FastAPI, which runs the Plan Reader pipeline and
// returns the extraction JSON. A NEW plan takes 2–5+ min (convert → index →
// 2 Claude passes); a re-drop of seen content returns in ~0s (backend
// content-hash cache). Backend URL via BIDINTEL_API_URL (default :8010).
//
// 2026-08-10: this used global fetch(), whose undici default headersTimeout is 300 s —
// exactly the ~5 min a large plan takes — so a healthy long run was reported as
// "Cannot reach the backend. Is uvicorn running?". Now proxied over node:http with an
// explicit 30-min inactivity ceiling, and any failure is health-checked before it is
// allowed to claim the backend is down. See src/lib/backend-proxy.ts.
// ────────────────────────────────────────────────────────────────────────────

import { BACKEND, describeProxyFailure, proxyLongRun } from "@/lib/backend-proxy";

export const runtime = "nodejs"; // streams a request body; needs Node, not edge
export const dynamic = "force-dynamic";
export const maxDuration = 1800; // was 300 — a large plan set is ~5 min; 30 min is headroom

export async function POST(req: Request) {
  const startedAt = Date.now();
  try {
    const upstream = await proxyLongRun(`${BACKEND}/api/report`, {
      method: "POST",
      // Forward the multipart body untouched (keep the boundary in content-type).
      headers: { "content-type": req.headers.get("content-type") ?? "" },
      body: req.body,
    });
    return new Response(upstream.text, {
      status: upstream.status,
      headers: { "content-type": "application/json", "cache-control": "no-store" },
    });
  } catch (err) {
    // 200 so the client renders the message instead of throwing; the `code` field is what
    // separates "still processing" from "server missing".
    return Response.json(await describeProxyFailure(err, startedAt), { status: 200 });
  }
}
