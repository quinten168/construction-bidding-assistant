#!/usr/bin/env python3
"""
gotcha_progress.py  —  live progress + ETA for the Phase-2a gotcha run (07_gotcha_extract.py).

Why this exists: while 07_gotcha_extract.py is running it holds the SQLite write lock, so a plain
`sqlite3 ... "SELECT ..."` from another shell returns "database is locked (5)". This monitor opens a
READ-ONLY connection with a long busy-timeout, so it waits for the brief gap between the tool's
per-plan commits and slips a read in — giving a count of plans done / left plus a wall-clock ETA.

Done-marker: a plan is "done" once 07_gotcha_extract writes its rollup — i.e. plan_metrics.
gotcha_extraction_cost IS NOT NULL (the tool does INSERT OR IGNORE + UPDATE, so this is set for
every processed plan, including ones with zero gotchas). Total = converted plans (the run's scope).

The ETA needs to know how long the run has been going: we read the elapsed time of the live
07_gotcha_extract process (`ps -o etimes=`), so rate = done / elapsed and ETA = remaining / rate.

Run (anytime, in another shell, while the gotcha run is going):
    cd 01_Summer_2026
    ./.venv/bin/python3 pipelines/plan_reader/04_tools/gotcha_progress.py
"""
import sqlite3
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

# --- paths ----
TOOLS_DIR   = Path(__file__).resolve().parent
MODULE_ROOT = TOOLS_DIR.parent                       # .../plan_reader
DB_PATH     = MODULE_ROOT / "csi_v2.db"

# --- find the running gotcha process + its elapsed seconds (for the ETA) ----
def _parse_etime(s):
    """Parse BSD/macOS `ps -o etime` ([[dd-]hh:]mm:ss) into seconds."""
    days = 0
    if "-" in s:
        d, s = s.split("-", 1)
        days = int(d)
    parts = [int(p) for p in s.split(":")]
    while len(parts) < 3:                 # pad to h:m:s
        parts.insert(0, 0)
    h, m, sec = parts
    return days * 86400 + h * 3600 + m * 60 + sec

def gotcha_process_elapsed_seconds():
    """Return (pid, elapsed_seconds) for the live 07_gotcha_extract run, or (None, None) if not running."""
    try:
        pid = subprocess.check_output(["pgrep", "-f", "07_gotcha_extract"], text=True).split()[0]
    except (subprocess.CalledProcessError, IndexError):
        return None, None
    # macOS `ps` has no etimes(seconds) keyword — use etime ([[dd-]hh:]mm:ss) and parse it.
    etime = subprocess.check_output(["ps", "-o", "etime=", "-p", pid], text=True).strip()
    return pid, _parse_etime(etime)

# --- read progress from the DB without getting blocked by the writer ----
def read_progress():
    # Read-only + 30s busy timeout: wait through the writer's per-plan commit, then read in the gap.
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True, timeout=30)
    total = conn.execute("SELECT COUNT(*) FROM plans WHERE convert_status='converted'").fetchone()[0]
    done  = conn.execute("""SELECT COUNT(*) FROM plan_metrics pm JOIN plans p ON p.plan_id = pm.plan_id
                            WHERE p.convert_status='converted' AND pm.gotcha_extraction_cost IS NOT NULL"""
                         ).fetchone()[0]
    gotchas = conn.execute("SELECT COUNT(*) FROM gotchas").fetchone()[0]
    cost = conn.execute("SELECT COALESCE(SUM(gotcha_extraction_cost), 0) FROM plan_metrics").fetchone()[0]
    conn.close()
    return total, done, gotchas, cost

# --- main ----
def main():
    now = datetime.now()
    total, done, gotchas, cost = read_progress()
    remaining = total - done
    pid, elapsed = gotcha_process_elapsed_seconds()

    print(f"[{now:%Y-%m-%d %H:%M:%S}]  gotcha run progress")
    print(f"  plans loaded : {done}/{total}   ({remaining} left)")
    print(f"  gotchas so far: {gotchas:,}")
    print(f"  cost so far  : ${cost:,.2f}")

    if pid is None:
        print(f"  status       : process NOT running (finished, or not started)")
        return
    # rate + ETA from the live process's elapsed time
    if done > 0 and elapsed:
        per_plan = elapsed / done
        eta_secs = remaining * per_plan
        finish = now + timedelta(seconds=eta_secs)
        print(f"  running      : PID {pid}, elapsed {timedelta(seconds=elapsed)}")
        print(f"  rate         : {per_plan:.0f}s/plan")
        print(f"  ETA          : ~{timedelta(seconds=int(eta_secs))}  →  finish ~{finish:%H:%M:%S}")
        print(f"  proj. cost   : ${cost / done * total:,.2f} (if rate holds)")
    else:
        print(f"  running      : PID {pid}, elapsed {timedelta(seconds=elapsed or 0)} (warming up — no ETA yet)")

if __name__ == "__main__":
    main()
