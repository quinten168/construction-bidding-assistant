// ────────────────────────────────────────────────────────────────────────────
// Long-running proxy to the FastAPI backend, + a health probe that lets a
// timeout and an unreachable backend render differently.
//
// WHY THIS EXISTS (2026-08-10). The report routes used to call global `fetch()`.
// Node's global fetch is undici, whose default `headersTimeout` is 300_000 ms
// (`undici/lib/dispatcher/client.js`: `headersTimeout != null ? headersTimeout : 300e3`).
// FastAPI sends NO response headers until the whole plan-reader run finishes, so a
// plan that takes ~5 min tripped that default: undici threw `UND_ERR_HEADERS_TIMEOUT`,
// surfaced as a plain `TypeError: fetch failed`, and the route's catch block printed
// "Cannot reach the bid-assistant backend… Is uvicorn running?" — which was FALSE.
// The backend was fine and still working.
//
// Two fixes live here:
//  1. `proxyLongRun` uses node:http/node:https instead of fetch. `http.request` has NO
//     default response timeout; the only clock is the socket-inactivity `timeout` we set
//     explicitly (LONG_RUN_TIMEOUT_MS). A silent multi-minute run is no longer a failure.
//  2. `backendHealth` + `describeProxyFailure` health-check the backend BEFORE claiming it
//     is down, so "still processing" and "unreachable" never share a message (or a code).
// ────────────────────────────────────────────────────────────────────────────

import http from "node:http";
import https from "node:https";
import { Readable } from "node:stream";

export const BACKEND = process.env.BIDINTEL_API_URL ?? "http://127.0.0.1:8010";

/** Socket-inactivity ceiling for a report run. 30 min: a large plan is ~5 min today, so this
 *  is headroom, not a target. Was: undici's implicit 300_000 ms headers timeout. */
export const LONG_RUN_TIMEOUT_MS = 1_800_000;

/** The health probe must answer fast or it is useless as a discriminator. */
export const HEALTH_TIMEOUT_MS = 4_000;

export type ProxyResult = { status: number; text: string; headers: http.IncomingHttpHeaders };

/**
 * POST to the backend with no header/body deadline — only a socket-inactivity timeout.
 * `body` may be a string or a web ReadableStream (the multipart upload path).
 */
export function proxyLongRun(
  url: string,
  opts: {
    method?: string;
    headers?: Record<string, string>;
    body?: string | ReadableStream<Uint8Array> | null;
    timeoutMs?: number;
  } = {},
): Promise<ProxyResult> {
  const target = new URL(url);
  const mod = target.protocol === "https:" ? https : http;
  const timeoutMs = opts.timeoutMs ?? LONG_RUN_TIMEOUT_MS;

  return new Promise<ProxyResult>((resolve, reject) => {
    const req = mod.request(
      {
        protocol: target.protocol,
        hostname: target.hostname,
        port: target.port,
        path: `${target.pathname}${target.search}`,
        method: opts.method ?? "POST",
        headers: opts.headers ?? {},
        // Inactivity clock only. Nothing else in this path imposes a deadline.
        timeout: timeoutMs,
      },
      (res) => {
        const chunks: Buffer[] = [];
        res.on("data", (c: Buffer) => chunks.push(c));
        res.on("end", () =>
          resolve({
            status: res.statusCode ?? 502,
            text: Buffer.concat(chunks).toString("utf8"),
            headers: res.headers,
          }),
        );
        res.on("error", reject);
      },
    );

    req.on("timeout", () => {
      // Distinct code so the caller can say "no bytes for 30 minutes", not "server missing".
      req.destroy(Object.assign(new Error(`No response from backend for ${timeoutMs} ms`), {
        code: "BIDINTEL_IDLE_TIMEOUT",
      }));
    });
    req.on("error", reject);

    if (opts.body == null) {
      req.end();
    } else if (typeof opts.body === "string") {
      req.end(opts.body);
    } else {
      Readable.fromWeb(opts.body as Parameters<typeof Readable.fromWeb>[0])
        .on("error", (e) => req.destroy(e))
        .pipe(req);
    }
  });
}

export type BackendHealth =
  // Three states, never two: the probe answered ok, the probe answered but the backend is
  // unhappy, or the probe could not reach it at all. A failure and an empty answer must not
  // share a return value.
  | { reachable: true; status: string; detail: string }
  | { reachable: false; detail: string };

/** GET /health with a short deadline. Used to decide what a proxy failure actually means. */
export async function backendHealth(timeoutMs = HEALTH_TIMEOUT_MS): Promise<BackendHealth> {
  try {
    const res = await proxyLongRun(`${BACKEND}/health`, { method: "GET", timeoutMs });
    if (res.status < 200 || res.status >= 500) {
      return { reachable: true, status: `http_${res.status}`, detail: `backend answered HTTP ${res.status}` };
    }
    let status = "ok";
    try {
      status = (JSON.parse(res.text) as { status?: string }).status ?? "ok";
    } catch {
      status = "unparseable";
    }
    return { reachable: true, status, detail: `backend answered /health with status="${status}"` };
  } catch (e) {
    const code = (e as NodeJS.ErrnoException)?.code ?? "unknown";
    return { reachable: false, detail: `/health probe failed (${code})` };
  }
}

export type ProxyFailure = {
  ok: false;
  /** Machine-readable so a timeout and an unreachable backend never collapse into one string. */
  code: "backend_unreachable" | "backend_still_processing";
  message: string;
  elapsed_ms: number;
  health: BackendHealth;
};

/**
 * Turn a thrown proxy error into a message that tells the truth. Health-checks the backend
 * first: if it answers, the run is still going and we say so; only a failed probe is allowed
 * to say "is uvicorn running?".
 */
export async function describeProxyFailure(err: unknown, startedAt: number): Promise<ProxyFailure> {
  const elapsed = Date.now() - startedAt;
  const mins = Math.max(1, Math.round(elapsed / 60_000));
  const health = await backendHealth();
  const cause = (err as NodeJS.ErrnoException)?.code ?? (err as Error)?.message ?? "unknown error";

  if (health.reachable) {
    return {
      ok: false,
      code: "backend_still_processing",
      message:
        `The connection to the bid-assistant backend dropped after ~${mins} min (${cause}), ` +
        `but the backend is UP — ${health.detail}. The plan is most likely still processing; ` +
        `a large plan set takes several minutes. Watch the uvicorn log, then re-drop the same ` +
        `PDF: the finished run is cached by content hash and will come back immediately.`,
      elapsed_ms: elapsed,
      health,
    };
  }
  return {
    ok: false,
    code: "backend_unreachable",
    message:
      `Cannot reach the bid-assistant backend at ${BACKEND} (${cause}); ${health.detail}. ` +
      `Is uvicorn running?`,
    elapsed_ms: elapsed,
    health,
  };
}
