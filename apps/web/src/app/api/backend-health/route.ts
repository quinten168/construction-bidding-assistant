// ────────────────────────────────────────────────────────────────────────────
// Backend health probe (2026-08-10) → FastAPI GET /health.
//
// Exists so the BROWSER can also tell "still processing" apart from "backend down".
// The server-side report proxies do this themselves (src/lib/backend-proxy.ts), but a
// client-side fetch can fail on its own — a reloaded tab, a dropped connection, the dev
// server restarting — and the old client code answered every such failure with
// "Network error reading the plan", which reads as "your upload failed" even when the
// backend is happily mid-run.
//
// Always HTTP 200. `reachable` is the answer; a failed probe is a value here, never an
// exception the caller has to guess the meaning of.
// ────────────────────────────────────────────────────────────────────────────

import { backendHealth } from "@/lib/backend-proxy";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
export const maxDuration = 30;

export async function GET() {
  return Response.json(await backendHealth(), {
    status: 200,
    headers: { "cache-control": "no-store" },
  });
}
