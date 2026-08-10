// ────────────────────────────────────────────────────────────────────────────
// Report finalize proxy → the real CSI Bid Assistant backend
// (FastAPI POST /api/report/{plan_id}/finalize).
//
// Phase ② of the verify gate: the browser POSTs {extraction, edits} (plain JSON — the
// unverified payload from POST /api/report, plus whatever the user confirmed/changed in the
// verify modal); FastAPI bakes the edits in, caches the payload, and runs the rest of the
// pipeline (competitor-intel generation). Backend URL via BIDINTEL_API_URL (default :8010).
//
// 2026-08-10: had the SAME 300 s undici headersTimeout problem as api/report/route.ts —
// competitor-intel generation is a subprocess that can run for minutes with no bytes on the
// wire. Same fix: node:http with an explicit 30-min inactivity ceiling, and a health check
// before any message claims the backend is down. See src/lib/backend-proxy.ts.
// ────────────────────────────────────────────────────────────────────────────

import { BACKEND, describeProxyFailure, proxyLongRun } from "@/lib/backend-proxy";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
export const maxDuration = 1800; // was 300 — same headroom as the upload route

export async function POST(req: Request, ctx: { params: Promise<{ planId: string }> }) {
  const { planId } = await ctx.params;
  const startedAt = Date.now();
  try {
    const upstream = await proxyLongRun(
      `${BACKEND}/api/report/${encodeURIComponent(planId)}/finalize`,
      { method: "POST", headers: { "content-type": "application/json" }, body: await req.text() },
    );
    return new Response(upstream.text, {
      status: upstream.status,
      headers: { "content-type": "application/json", "cache-control": "no-store" },
    });
  } catch (err) {
    return Response.json(await describeProxyFailure(err, startedAt), { status: 200 });
  }
}
