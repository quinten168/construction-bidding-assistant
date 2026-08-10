// ────────────────────────────────────────────────────────────────────────────
// Report predict-competitors proxy → the real CSI Bid Assistant backend
// (FastAPI POST /api/report/{plan_id}/predict-competitors).
//
// Between the two verify-gate popups: the browser POSTs {extraction, edits} right after the
// estimator confirms/skips extraction, so the "expected competitors" popup shows the model's
// predicted names instead of an empty list. Backend URL via BIDINTEL_API_URL (default :8010).
//
// 2026-08-10: same 300 s undici headersTimeout exposure as the other two report routes (this
// one runs the competitor-prediction cascade, a subprocess). Same fix — node:http, explicit
// 30-min inactivity ceiling, health check before blaming the backend. See src/lib/backend-proxy.ts.
// ────────────────────────────────────────────────────────────────────────────

import { BACKEND, describeProxyFailure, proxyLongRun } from "@/lib/backend-proxy";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
export const maxDuration = 1800; // was 300 — same headroom as finalize

export async function POST(req: Request, ctx: { params: Promise<{ planId: string }> }) {
  const { planId } = await ctx.params;
  const startedAt = Date.now();
  try {
    const upstream = await proxyLongRun(
      `${BACKEND}/api/report/${encodeURIComponent(planId)}/predict-competitors`,
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
