#!/usr/bin/env bash
# Backend only, in the foreground. Use when you want the API without the Next.js noise.
#   ./scripts/api.sh            RELOAD=1 ./scripts/api.sh

source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

require_venv
require_api_key
require_free_port "$API_PORT" api
check_artifacts

args=(app:app --port "$API_PORT")
[ "${RELOAD:-0}" = "1" ] && args+=(--reload)

c_dim "api → http://localhost:$API_PORT/docs   (Ctrl-C to stop)"
cd "$ROOT/apps/api"
exec "$ROOT/.venv/bin/uvicorn" "${args[@]}"
