#!/usr/bin/env bash
# Frontend only, in the foreground. Expects the API to already be up — the web app is a pure proxy
# (apps/web calls apps/api and nothing else), so without a backend every request will fail.
#   ./scripts/web.sh

source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

require_node_modules
require_free_port "$WEB_PORT" web

if ! curl -sf --max-time 2 -o /dev/null "http://127.0.0.1:$API_PORT/health"; then
  c_ylw "⚠ no API on :$API_PORT — start it with ./scripts/api.sh, or use ./scripts/dev.sh for both."
fi

c_dim "web → http://localhost:$WEB_PORT   (Ctrl-C to stop)"
cd "$ROOT/apps/web"
exec npm run dev -- --port "$WEB_PORT"
