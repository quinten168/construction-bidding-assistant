// ────────────────────────────────────────────────────────────────────────────
// Report predict-competitors proxy → the real CSI Bid Assistant backend
// (FastAPI POST /api/report/{plan_id}/predict-competitors).
//
// Between the two verify-gate popups: the browser POSTs {extraction, edits} (same shape as the
// finalize proxy below it) right after the estimator confirms/skips extraction, so the "expected
// competitors" popup can show the model's predicted names instead of an empty list. Same
// buffered-JSON shape as the finalize proxy — no streaming needed. Backend URL via
// BIDINTEL_API_URL (default :8010).
// ────────────────────────────────────────────────────────────────────────────

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
export const maxDuration = 300; // competitor-intel generation can take a while, same as finalize

const BACKEND = process.env.BIDINTEL_API_URL ?? "http://127.0.0.1:8010";

export async function POST(req: Request, ctx: { params: Promise<{ planId: string }> }) {
  const { planId } = await ctx.params;
  try {
    const upstream = await fetch(`${BACKEND}/api/report/${encodeURIComponent(planId)}/predict-competitors`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: await req.text(),
    });
    const text = await upstream.text();
    return new Response(text, {
      status: upstream.status,
      headers: { "content-type": "application/json", "cache-control": "no-store" },
    });
  } catch {
    return Response.json(
      { ok: false, message: `Cannot reach the bid-assistant backend at ${BACKEND}. Is uvicorn running?` },
      { status: 200 }, // 200 so the client renders the message instead of throwing
    );
  }
}
