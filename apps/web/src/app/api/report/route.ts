// ────────────────────────────────────────────────────────────────────────────
// Report proxy → the real CSI Bid Assistant backend (FastAPI /api/report).
//
// The browser POSTs a multipart form (the dropped plan PDF) here, same-origin;
// we stream it through to FastAPI, which runs the Plan Reader pipeline and
// returns the assembled report JSON ({ ok, final }). A NEW plan takes ~2 min
// (convert → index → 2 Claude passes); a re-drop of seen content returns in ~0s
// (backend content-hash cache). Backend URL via BIDINTEL_API_URL (default :8010).
// ────────────────────────────────────────────────────────────────────────────

export const runtime = "nodejs"; // streams a request body; needs Node fetch, not edge
export const dynamic = "force-dynamic";
export const maxDuration = 300; // a fresh plan can take minutes; don't time out at the default

const BACKEND = process.env.BIDINTEL_API_URL ?? "http://127.0.0.1:8010";

export async function POST(req: Request) {
  try {
    const upstream = await fetch(`${BACKEND}/api/report`, {
      method: "POST",
      // Forward the multipart body untouched (keep the boundary in content-type).
      headers: { "content-type": req.headers.get("content-type") ?? "" },
      body: req.body,
      // Node's fetch requires this when sending a streamed request body.
      // @ts-expect-error — `duplex` is valid at runtime but missing from the lib types.
      duplex: "half",
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
