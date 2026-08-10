# 2026-08-10 — timeout demo-safety

Demo-blocking item. Three parts: raise the timeout headroom, stop a timeout from lying about the
backend being down, and report the state of the payload cache.

**Bottom line.** The "Cannot reach the backend. Is uvicorn running?" message was produced by a
**300-second default inside Node's global `fetch`**, not by anything being unreachable. Measured:
`300976 ms`. The three report routes no longer use `fetch`, and no failure message may now claim
the backend is down without a `/health` probe saying so first.

---

## 1. Root cause — measured, not inferred

Node's global `fetch` is undici. Undici's default `headersTimeout` is **300 000 ms**. FastAPI sends
no response headers until the whole plan-reader run finishes, so a plan that takes ~5 minutes trips
that default. Undici throws `TypeError: fetch failed` with `cause.code = UND_ERR_HEADERS_TIMEOUT`,
which landed in the route's bare `catch {}` and printed the "Is uvicorn running?" string.

Two independent verifications, both named:

1. **Source constant.** `apps/web/node_modules/undici/lib/dispatcher/client.js:262` —
   `headersTimeout != null ? headersTimeout : 300e3`.
2. **Live measurement.** `/tmp/2026-08-10-t_undici_default.mjs` — an HTTP server that withholds
   response headers for 310 s, called with an *unmodified* global `fetch` on this machine's Node
   v22.20.0:
   `THREW after 300976ms: TypeError | fetch failed | cause: UND_ERR_HEADERS_TIMEOUT`.

A supporting A/B (`/tmp/2026-08-10-t_undici.mjs`) shows the same request over `node:http` with no
timeout set resolves normally (`resolved 200 after 6005ms`) — `http.request` has **no** default
response timeout, which is why the fix moves to it.

`maxDuration = 300` was **not** the cause under `next dev` (it is a Vercel/serverless deployment
hint, not enforced by the dev server), but it was the same wrong number one layer out and is raised
too, so a deployed build does not reintroduce the bug.

## 2. Every timeout changed — old → new, by layer

| # | Layer | File | Old | New |
|---|---|---|---|---|
| 1 | Next route config | `apps/web/src/app/api/report/route.ts` | `maxDuration = 300` (5 min) | `maxDuration = 1800` (30 min) |
| 2 | Next route config | `apps/web/src/app/api/report/[planId]/finalize/route.ts` | `maxDuration = 300` | `maxDuration = 1800` |
| 3 | Next route config | `apps/web/src/app/api/report/[planId]/predict-competitors/route.ts` | `maxDuration = 300` | `maxDuration = 1800` |
| 4 | Outbound call, `/api/report` | same file | global `fetch` → undici **implicit 300 000 ms headers timeout + 300 000 ms body timeout** | `proxyLongRun` over `node:http`, **1 800 000 ms socket-inactivity timeout**, no header/body deadline |
| 5 | Outbound call, `finalize` | same file | as above (implicit 300 000 ms) | as above (1 800 000 ms) |
| 6 | Outbound call, `predict-competitors` | same file | as above (implicit 300 000 ms) | as above (1 800 000 ms) |
| 7 | Health probe (new) | `apps/web/src/lib/backend-proxy.ts` | — | `HEALTH_TIMEOUT_MS = 4 000` |
| 8 | Health probe route (new) | `apps/web/src/app/api/backend-health/route.ts` | — | `maxDuration = 30` |
| 9 | Client-side abort | `apps/web/src/components/chat/use-chat-store.ts` | none (no `AbortController` on `uploadReport`/`finalizeReport`) | **still none, deliberately** — documented in-file. The browser must be allowed to wait out a real multi-minute run; the server route owns the only deadline. |

Notes on the numbers:

- **30 min is headroom, not a target.** The worst observed plan is ~5 min. The point is that the
  ceiling is now 6× the worst case instead of exactly equal to it.
- The new ceiling is a **socket-inactivity** clock, not a wall clock. Silence is what a long
  extraction looks like on the wire, so this is the knob that matters.
- `/api/report/export` (`apps/web/src/app/api/report/export/route.ts`) was checked and **left
  alone**: it renders an already-assembled report with no pipeline re-run, sets no `maxDuration`,
  and returns immediately. It still uses global `fetch`. If export ever grows a slow path it has
  the same latent bug — noted, not fixed, to keep this change scoped.
- `/api/chat` and `/api/ci-data/*` were not touched (streaming SSE and fast reads respectively).

## 3. The new failure-message logic

The rule being applied: **a timeout and an unreachable backend must not render identically**, and a
failure must never share a return value with a legitimate empty answer.

New module `apps/web/src/lib/backend-proxy.ts`:

- `backendHealth()` returns a **three-state** value, never a bare boolean:
  `{reachable: true, status, detail}` / `{reachable: true, status: "http_5xx", detail}` /
  `{reachable: false, detail}`. A failed probe is a *value*, not an exception the caller has to
  interpret.
- `describeProxyFailure(err, startedAt)` health-checks **before** blaming anyone, and returns a
  machine-readable `code` alongside the prose:

| Health probe | `code` | What the user reads |
|---|---|---|
| answers | `backend_still_processing` | "The connection … dropped after ~N min (…), but the backend is **UP** — backend answered /health with status="ok". The plan is most likely still processing; a large plan set takes several minutes. Watch the uvicorn log, then re-drop the same PDF …" |
| fails | `backend_unreachable` | "Cannot reach the bid-assistant backend at `<url>` (…); /health probe failed (ECONNREFUSED). Is uvicorn running?" |

The response also carries `elapsed_ms` and the full `health` object, so the two cases differ in the
payload as well as in the sentence.

**Client side** (`use-chat-store.ts`): a browser-side fetch can fail on its own — reloaded tab,
dropped connection, dev server restart — and the old code answered *every* such case with
`"Network error reading the plan."`, which reads as "your upload failed". Now
`explainClientFailure(stage)` probes the new `GET /api/backend-health` route and produces the same
three-way distinction, including a third branch for "the probe itself could not run", which means
*this Next.js server* is the problem and says so instead of blaming uvicorn on no evidence.

### How the discrimination was verified

`backend-proxy.ts` was compiled standalone (`npx tsc … --outDir /tmp/2026-08-10-bp`) and driven by
`/tmp/2026-08-10-t_discriminate.mjs` against both a live and a dead backend, feeding it *both*
error shapes it can actually receive (undici's `TypeError: fetch failed` and our own
`BIDINTEL_IDLE_TIMEOUT`):

- **Backend up** (`127.0.0.1:8010`, the running instance):
  `health = {"reachable":true,"status":"ok",…}` → both error shapes produced
  `code=backend_still_processing`, message says the backend is UP.
- **Backend down** (`BIDINTEL_API_URL=http://127.0.0.1:8099`):
  `health = {"reachable":false,"detail":"/health probe failed (ECONNREFUSED)"}` → both error shapes
  produced `code=backend_unreachable`, message says "Is uvicorn running?".

Positive control in the same run: `proxyLongRun GET /health -> 200 {"status":"ok",…}` against the
live backend, and `THREW ECONNREFUSED` against the dead port.

Long-run positive control (`/tmp/2026-08-10-t_longrun.mjs`): `proxyLongRun` against a server that
withholds headers for **310 s** — the exact case that used to fail — see §6.

Static checks: `npx tsc --noEmit` clean; `npx eslint` on all changed/added files reports **one**
error, `react-hooks/set-state-in-effect` in `use-chat-store.ts`, which was confirmed **pre-existing**
by linting the unmodified `HEAD` copy of that file inside the project (same rule, same code, line
233 before my +28 lines shifted it to 261). `npm run build` was deliberately **not** run — a
teammate has `next dev` live against the same `.next` directory.

## 4. Payload cache — cached, fast, and mostly stale

Cache: `pipelines/plan_reader/00_input/_report_payload_cache/`, keyed by PDF content hash only
(`apps/api/backend/report.py:57-58`). **12 entries. Nothing removed** — owner decision, it stays as
the speed layer, and a teammate is running the app live.

The live mapping (`pipelines/plan_reader/01_pipeline/schema.py`, the seven quantity field
descriptions) last changed **2026-08-10T13:06:13-05:00** (commits `5972199`, `b8d283a` — CSI's 11
rulings). **All 12 cached payloads predate that**, so every re-drop returns pre-ruling numbers,
instantly, with no signal that it did.

| file | plan | county/state | mtime | cached quantities | vs 2026-08-10 13:06 |
|---|---|---|---|---|---|
| `f19c9df671fd2fd7.json` | 9813645 (**Stearns**) | Stearns / MN | 2026-07-29 12:57 | MIX=14480; BASE=270; SHLDR=460; **MILL=70263** | **STALE** — post-ruling MILL is **140 430** (the three MILL BITUMINOUS lines + 70 167 SY of FDR, which CSI ruled belongs in `milling_sy`) |
| `193968928775465b.json` | Job 24133 Request for Proposal | Morton / ND | 2026-08-03 10:10 | GRADE=4911; BASE=170; MILL=152 | **STALE** |
| `609a8b856ceed52a.json` | 8416165 | Cass / ND | 2026-08-07 13:37 | MIX=27900; MILL=193207 | **STALE** |
| `3929bfb697838f3c.json` | 25-1076 Specifications | Minnehaha / SD | 2026-08-06 14:12 | MIX=7714 | **STALE** |
| `22a6c16cf64b7cfa.json` | 9809481 | Clay / MN | 2026-08-05 09:26 | GRADE=45 | **STALE** |
| `9ff5dc83b09d4079.json` | Proposal SAP 018-603-024 / 018-611-029 | Crow Wing / MN | 2026-08-04 15:08 | MIX=4732; GRADE=7707; BASE=5849 | **STALE** |
| `2b2438a4eaaa0e79.json` | 8395536 | — / ND | 2026-08-04 11:40 | MILL=250 | **STALE** |
| `760e9a1dfd751c92.json` | 8391182 | Brookings / SD | 2026-07-30 14:59 | MIX=17432.3; MILL=1981 | **STALE** |
| `e9ae6f092ccca1bf.json` | 9462761 | — / ND | 2026-07-30 16:11 | *(no quantities)* | **STALE** |
| `d3c6880efb06473e.json` | 8435627 | Emmons / ND | 2026-07-24 13:27 | MIX=1586; GRADE=8814; MILL=75 | **STALE** |
| `2c83fa4ee425fe1b.json` | 8428114 | — / ND | 2026-07-24 10:58 | MIX=2100; GRADE=1600; BASE=1070 | **STALE** |
| `6c906b5819b25040.json` | 9804001 | Douglas / MN | 2026-07-19 18:28 | MIX=6300 | **STALE** |

Five of the twelve are marked `verified` (they went through the verify gate); the rest are
phase-① payloads. Either way the quantities are pre-ruling.

**The mechanism, stated plainly.** The cache key is the PDF content hash and nothing else. The
cached *value* depends on the PDF **and** on the seven prose field descriptions in `schema.py`. A
prose change therefore cannot invalidate anything. So "the demo plans are cached and return fast"
and "the demo shows the mapping we just fixed" are in direct conflict today, **and the cache wins**.
This is the same failure class as everything else in this repo: a fast, successful-looking response
answering from a state nobody realised was stale.

Two things worth knowing alongside it:

- The sibling `_report_competitor_prediction_cache` (`report.py:65`) is keyed the same way and has
  the same exposure. It **does not exist on disk** right now — verified two ways: `ls` returns
  "No such file or directory", and a repo-wide `find -type d` for cache dirs under
  `plan_reader/00_input` returns only `_report_payload_cache`.
- `DATA_DIR` resolves relative to `lib.py`'s own location (`plan_reader/01_pipeline/lib.py:21-28`),
  so the directory inventoried above **is** the one the running backend uses — this is not the
  "two `00_input` directories" trap from HANDOFF §5.

**Nothing was deleted and nothing is recommended for deletion by an agent.** If a demo plan's
cached numbers are not the ones you want on screen, that is an owner call. The design fix — putting
a mapping version into the cache key — is specced, not built:
`docs/_spec/2026-08-10-payload-cache-key-versioning.md`.

## 5. Files changed

| file | change |
|---|---|
| `apps/web/src/lib/backend-proxy.ts` | **new** — `proxyLongRun` (node:http, explicit inactivity ceiling), `backendHealth` (3-state), `describeProxyFailure` (coded, health-gated) |
| `apps/web/src/app/api/backend-health/route.ts` | **new** — `GET`, always 200, so the browser can discriminate too |
| `apps/web/src/app/api/report/route.ts` | fetch → `proxyLongRun`; `maxDuration` 300 → 1800; coded failure |
| `apps/web/src/app/api/report/[planId]/finalize/route.ts` | same |
| `apps/web/src/app/api/report/[planId]/predict-competitors/route.ts` | same |
| `apps/web/src/components/chat/use-chat-store.ts` | `explainClientFailure()` replaces the two "Network error …" strings; no client abort, now documented as deliberate |
| `docs/_spec/2026-08-10-payload-cache-key-versioning.md` | **new** — spec only, not built |

Not touched, per file ownership: `report-card.tsx`, the `Competitor` type,
`apps/api/backend/final_report.py`, `report.py`'s payload assembly, `schema.py`.

## 6. Long-run positive control

`/tmp/2026-08-10-t_longrun.mjs` — `proxyLongRun` POSTing to a server that withholds response
headers for 310 s, i.e. past the old 300 s cliff:

```
proxyLongRun RESOLVED 200 {"ok":true,"slow":true} after 310006ms
```

Same server, same machine, same Node — global `fetch` threw at 300 976 ms, `proxyLongRun` resolved
at 310 006 ms. That is the fix, measured end to end.

Streaming control (`/tmp/2026-08-10-t_stream.mjs`) — the `/api/report` route forwards a *web*
`ReadableStream` (the multipart upload), so that path was proven separately: a chunked multipart
body with 50 ms gaps round-tripped **20 090 bytes intact** with the `content-type` boundary
preserved (`multipart/form-data; boundary=----X`).
