// ────────────────────────────────────────────────────────────────────────────
// Report EXPORT proxy → FastAPI /api/report/export.
//
// The browser POSTs { final, fmt } (the assembled report + a format md|csv|pdf),
// same-origin; we forward as JSON and stream the resulting file back with its
// Content-Disposition intact so the browser downloads it. No pipeline re-run —
// the backend just renders the already-assembled report, so this is instant.
// Backend URL via BIDINTEL_API_URL (default :8010).
// ────────────────────────────────────────────────────────────────────────────

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const BACKEND = process.env.BIDINTEL_API_URL ?? "http://127.0.0.1:8010";

export async function POST(req: Request) {
  try {
    const body = await req.text(); // { final, fmt }
    const upstream = await fetch(`${BACKEND}/api/report/export`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body,
    });
    // Pass the file bytes + the download headers straight through.
    const headers = new Headers();
    for (const h of ["content-type", "content-disposition", "x-export-fallback"]) {
      const v = upstream.headers.get(h);
      if (v) headers.set(h, v);
    }
    headers.set("cache-control", "no-store");
    return new Response(upstream.body, { status: upstream.status, headers });
  } catch {
    return Response.json(
      { ok: false, message: `Cannot reach the bid-assistant backend at ${BACKEND}.` },
      { status: 200 },
    );
  }
}
