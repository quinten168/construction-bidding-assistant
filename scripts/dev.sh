#!/usr/bin/env bash
# Launch the whole local stack: FastAPI (:8010) + Next.js (:3000).
#
#   ./scripts/dev.sh              start both, stream logs, Ctrl-C stops both
#   RELOAD=1 ./scripts/dev.sh     restart the API on Python file changes
#   API_PORT=8011 ./scripts/dev.sh
#
# Logs are written to .dev-logs/{api,web}.log as well as the terminal.

source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

# Job control, so each background child gets its OWN process group and `kill -- -PID` below can take
# down its whole tree. Without this they share the script's group and the workers survive.
set -m

require_venv
require_node_modules
require_api_key
require_free_port "$API_PORT" api
require_free_port "$WEB_PORT" web
check_artifacts

mkdir -p "$LOGDIR"

API_PID=""
WEB_PID=""

# Kill the whole process group of each child. `next dev` spawns workers that survive a bare kill of
# the npm wrapper and would keep :3000 bound, breaking the next run's port check.
cleanup() {
  trap - INT TERM EXIT
  echo
  c_dim "stopping…"
  for pid in "$WEB_PID" "$API_PID"; do
    [ -n "$pid" ] && kill -- -"$pid" 2>/dev/null || true
  done
  wait 2>/dev/null || true
  c_dim "stopped."
}
trap cleanup INT TERM EXIT

# --- backend -------------------------------------------------------------------------------------
# uvicorn must run with apps/api as its CWD: the app is imported as `app:app`, and parts of the tree
# resolve data paths relative to the working directory.
uvicorn_args=(app:app --port "$API_PORT")
[ "${RELOAD:-0}" = "1" ] && uvicorn_args+=(--reload)

c_dim "starting api on :$API_PORT …"
( cd "$ROOT/apps/api" && exec "$ROOT/.venv/bin/uvicorn" "${uvicorn_args[@]}" ) \
  > >(tee "$LOGDIR/api.log") 2>&1 &
API_PID=$!

if ! await_api_health; then
  c_red "✗ api did not become healthy — last lines of $LOGDIR/api.log:"
  tail -20 "$LOGDIR/api.log" | grep -viE 'NotOpenSSLWarning|warnings.warn'
  exit 1
fi

# --- frontend ------------------------------------------------------------------------------------
c_dim "starting web on :$WEB_PORT …"
( cd "$ROOT/apps/web" && exec npm run dev -- --port "$WEB_PORT" ) \
  > >(tee "$LOGDIR/web.log") 2>&1 &
WEB_PID=$!

for _ in $(seq 1 60); do
  curl -sf --max-time 2 -o /dev/null "http://127.0.0.1:$WEB_PORT/" && break
  sleep 1
done

echo
c_grn "✓ stack up"
echo "    web    http://localhost:$WEB_PORT"
echo "    api    http://localhost:$API_PORT/docs"
echo "    logs   $LOGDIR/"
c_dim "    Ctrl-C stops both. Competitor intel live? → ./scripts/verify-ci.sh"
echo

wait
