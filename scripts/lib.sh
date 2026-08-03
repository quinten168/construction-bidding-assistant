#!/usr/bin/env bash
# Shared preflight for the local dev scripts. Sourced by dev.sh / api.sh / web.sh — not run directly.
#
# Everything here exists to catch the failure modes described in CLAUDE.md "Known rough edges", which
# do NOT announce themselves at runtime: a missing artifact yields plausible-looking stale output, and
# a dead CI subprocess still returns HTTP 200.

set -euo pipefail

ROOT="$(git -C "$(dirname "${BASH_SOURCE[0]}")" rev-parse --show-toplevel)"
LOGDIR="$ROOT/.dev-logs"
API_PORT="${API_PORT:-8010}"
WEB_PORT="${WEB_PORT:-3000}"

# Artifacts that are gitignored as "regenerable" but are required at runtime (rough edge 1).
RANKING_CSV="$ROOT/pipelines/ci_model/03_training/outputs/ranking_predictions.csv"
CHROMA_DIR="$ROOT/pipelines/plan_reader/06_chroma"

c_red()  { printf '\033[31m%s\033[0m\n' "$*"; }
c_ylw()  { printf '\033[33m%s\033[0m\n' "$*"; }
c_grn()  { printf '\033[32m%s\033[0m\n' "$*"; }
c_dim()  { printf '\033[2m%s\033[0m\n' "$*"; }

die() { c_red "✗ $*"; exit 1; }

require_venv() {
  [ -x "$ROOT/.venv/bin/uvicorn" ] || die ".venv missing or incomplete. Create it with:
    python3 -m venv .venv && ./.venv/bin/pip install -r apps/api/requirements.txt"
}

require_node_modules() {
  [ -d "$ROOT/apps/web/node_modules" ] || die "apps/web/node_modules missing. Run:
    (cd apps/web && npm install)"
}

require_api_key() {
  # config.py:147 reads ANTHROPIC_API_KEY from the env, falling back to plan_reader/.env.
  if [ -z "${ANTHROPIC_API_KEY:-}" ] \
     && ! grep -qs ANTHROPIC_API_KEY "$ROOT/pipelines/plan_reader/.env" "$ROOT/apps/api/.env"; then
    die "No Anthropic key. Either export ANTHROPIC_API_KEY, or copy apps/api/.env.example to
    apps/api/.env and fill it in."
  fi
}

# Refuse to start on an occupied port rather than letting a second server fail obscurely, or —
# worse — letting you talk to a stale process from an earlier session and misread its output.
require_free_port() {
  local port="$1" name="$2" pid
  pid="$(lsof -nP -iTCP:"$port" -sTCP:LISTEN -t 2>/dev/null | head -1 || true)"
  if [ -n "$pid" ]; then
    die "port $port ($name) is already in use by PID $pid ($(ps -p "$pid" -o comm= 2>/dev/null)).
    Stop it with:  kill $pid"
  fi
}

# --- artifact policy -----------------------------------------------------------------------------
# DECISION POINT — see the note in the chat. Current behaviour: WARN and start anyway.
#
# Both artifacts are large (94 MB / 1.5 GB) and gitignored. Missing `ranking_predictions.csv` does
# not crash anything: live_report() returns None and the app silently serves a stale pre-generated
# competitor report, so the UI looks entirely normal while the numbers are old.
check_artifacts() {
  local missing=0
  [ -f "$RANKING_CSV" ] || { c_ylw "⚠ MISSING ranking_predictions.csv (94 MB)"; missing=1; }
  [ -d "$CHROMA_DIR" ]  || { c_ylw "⚠ MISSING 06_chroma/ (1.5 GB)"; missing=1; }

  if [ "$missing" -eq 1 ]; then
    c_ylw "  Competitor reports will silently fall back to STALE pre-generated output."
    c_ylw "  Recovery: pipelines/ci_model/README.md and pipelines/plan_reader/README.md"
    c_ylw "  Starting anyway — set STRICT_ARTIFACTS=1 to make this a hard failure instead."
    [ "${STRICT_ARTIFACTS:-0}" = "1" ] && die "STRICT_ARTIFACTS=1 and artifacts are missing."
  fi
}

# Poll /health and surface `warnings` loudly. A degraded backend still answers requests, so the only
# way to notice is to look. Returns non-zero if the API never came up.
await_api_health() {
  local i body
  for i in $(seq 1 60); do
    body="$(curl -sf --max-time 2 "http://127.0.0.1:$API_PORT/health" 2>/dev/null || true)"
    if [ -n "$body" ]; then
      "$ROOT/.venv/bin/python" - "$body" <<'PY'
import json, sys
d = json.loads(sys.argv[1])
status, warns = d.get("status"), d.get("warnings") or []
mark = "\033[32m✓\033[0m" if status == "ok" else "\033[33m⚠\033[0m"
print(f'{mark} api  status={status}  model={d.get("model")}  indexed_plans={d.get("indexed_plans")}')
for w in warns:
    print(f'    \033[33m! {w}\033[0m')
PY
      return 0
    fi
    sleep 1
  done
  return 1
}
