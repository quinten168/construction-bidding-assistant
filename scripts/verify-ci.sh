#!/usr/bin/env bash
# Prove the CI subprocess actually RAN — the check CLAUDE.md rough edge 2 demands.
#
# competitor_live.live_report() returns None on timeout, CalledProcessError, or any exception, and the
# caller then serves a stale pre-generated report. The API returns HTTP 200 with plausible competitive
# output while the subprocess is dead, so a successful response proves nothing. The only reliable
# tells are the `_match.basis` field and the report file's mtime.
#
#   ./scripts/verify-ci.sh                    # defaults to Douglas / MN
#   ./scripts/verify-ci.sh Stearns MN
#   ./scripts/verify-ci.sh Stearns MN 2025-08-15
#
# Does not need the servers running — it calls the module directly.

source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

require_venv
require_api_key

COUNTY="${1:-Douglas}"
STATE="${2:-MN}"
BID_DATE="${3:-}"

REPORTS="$ROOT/pipelines/ci_model/reports"
before="$(ls -t "$REPORTS"/*.md 2>/dev/null | head -1 || true)"
before_mtime="$([ -n "$before" ] && stat -f %m "$before" || echo 0)"

c_dim "generating for $COUNTY / $STATE ${BID_DATE:+(bid_date $BID_DATE)} …"

cd "$ROOT/apps/api"
"$ROOT/.venv/bin/python" - "$COUNTY" "$STATE" "$BID_DATE" <<'PY'
import sys, logging
logging.basicConfig(level=logging.INFO, format="    %(name)s · %(message)s")
county, state, bid_date = sys.argv[1], sys.argv[2], (sys.argv[3] or None)

from backend import competitor_live as cl

if not cl.available():
    print("\033[31m✗ competitor_live.available() is False — the live path is disabled or its inputs "
          "are missing. Every competitor report you see will be the STALE fallback.\033[0m")
    raise SystemExit(2)

rep = cl.live_report(county, state, bid_date)

if rep is None:
    print(f"\033[31m✗ live_report() returned None for {county}/{state} — FELL BACK TO STALE.\033[0m")
    print("\033[33m  The app would still render a normal-looking report here. Check the log lines "
          "above for the reason (no corpus job / parse failure / subprocess error).\033[0m")
    raise SystemExit(1)

m = rep.get("_match", {})
basis = m.get("basis")
ok = basis == "live-generated"
mark = "\033[32m✓\033[0m" if ok else "\033[33m⚠\033[0m"
print(f'{mark} basis={basis}  confidence={m.get("confidence")}  '
      f'date_gap_days={m.get("date_gap_days")}')
print(f'    project_id={rep.get("project_id")}  county={rep.get("county")}  state={rep.get("state")}')
if not ok:
    print("\033[33m  basis is not 'live-generated' — this is matched history, not a fresh run.\033[0m")
    raise SystemExit(1)
PY
rc=$?

# Independent of what the module reported: did a report file actually get written?
after="$(ls -t "$REPORTS"/*.md 2>/dev/null | head -1 || true)"
after_mtime="$([ -n "$after" ] && stat -f %m "$after" || echo 0)"

if [ "$after_mtime" -gt "$before_mtime" ]; then
  c_grn "✓ subprocess RAN — $(basename "$after") mtime advanced"
else
  c_ylw "⚠ no report mtime advanced. Newest is $(basename "${after:-none}"), unchanged."
  c_ylw "  A cached/parsed-only path can still return a dict, so treat the result above with care."
fi

exit $rc
