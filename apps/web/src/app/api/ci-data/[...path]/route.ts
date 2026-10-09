// ────────────────────────────────────────────────────────────────────────────
// CI-data admin proxy → the real Construction Bidding Assistant backend (FastAPI /api/ci-data/*).
//
// One catch-all route forwards every verb for the 3 admin features (bid results,
// pit list, competitor registry) to FastAPI, same buffered-JSON shape as
// api/report/route.ts (no streaming needed for plain CRUD). Backend URL via
// BIDINTEL_API_URL (default :8010).
// ────────────────────────────────────────────────────────────────────────────

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const BACKEND = process.env.BIDINTEL_API_URL ?? "http://127.0.0.1:8010";

type Ctx = { params: Promise<{ path: string[] }> };

async function proxy(req: Request, ctx: Ctx, method: string): Promise<Response> {
  const { path } = await ctx.params;
  const search = new URL(req.url).search;
  const url = `${BACKEND}/api/ci-data/${path.join("/")}${search}`;

  try {
    const upstream = await fetch(url, {
      method,
      headers: { "content-type": "application/json" },
      body: method === "GET" || method === "DELETE" ? undefined : await req.text(),
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

export async function GET(req: Request, ctx: Ctx) {
  return proxy(req, ctx, "GET");
}
export async function POST(req: Request, ctx: Ctx) {
  return proxy(req, ctx, "POST");
}
export async function PATCH(req: Request, ctx: Ctx) {
  return proxy(req, ctx, "PATCH");
}
export async function DELETE(req: Request, ctx: Ctx) {
  return proxy(req, ctx, "DELETE");
}
