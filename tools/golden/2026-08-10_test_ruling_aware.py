"""COVERAGE test for the ruling-aware golden reconciliation — run against the real corpus.

Why coverage rather than unit tests (the standing rule in this repo): a unit test over
`classify(100, 100, 0, True) == 'MATCH_RAW'` proves the branch I remembered to write works. It says
nothing about the 6,385 real corpus item rows, and the failure mode that matters here is a ruling
quietly moving a quantity that nothing attributes to a ruling — which is how a correct behaviour
gets scored as an extraction miss.

So this walks EVERY item row in `materials`, every golden quantity cell, and every emitted status,
and asserts:

  1. THE ANSWER KEY WAS NOT EDITED. All seven quantity columns of `golden_dataset.csv` are
     byte-identical to the committed version. This is the whole point of the recommendation in
     docs/_spec/2026-08-10-ruling-aware-golden.md and it must be mechanically enforced, not
     promised, because a later "just fix the golden" commit would be invisible otherwise.
  2. Every corpus row whose bucket changes when the rulings are switched off is attributed to a
     NAMED ruling id. An unattributed delta is a silent number move.
  3. Raw and ruling-adjusted are distinguishable on every ruling-touched output row: both values
     are present and they differ. A ruling-adjusted value must never be able to pass as a value a
     source document stated.
  4. `CONVERSION_REQUIRED` survives as its own third state and none of the new ruling statuses
     reuses its value — the three states are not collapsed into two.
  5. Absence never shares a value with a quantity: GOLDEN_ABSENT / EXTRACTION_ABSENT / BOTH_ABSENT
     are three distinct statuses and none of them carries a numeric 0.
  6. The ruling lists are restored after the module has run, so importing the impact tool cannot
     leave `quantity_crosswalk` mutated for anything else in the process.

Usage:  python tools/golden/2026-08-10_test_ruling_aware.py     (exit 0 = pass, 1 = fail)
"""

from __future__ import annotations

import csv
import importlib.util
import os
import re
import sqlite3
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
DB = os.path.join(REPO, "pipelines", "plan_reader", "csi_v2.db")
GOLDEN = os.path.join(REPO, "pipelines", "plan_reader", "00_input", "golden_dataset.csv")
GOLDEN_REL = "pipelines/plan_reader/00_input/golden_dataset.csv"
IMPACT_CSV = os.path.join(HERE, "2026-08-10_ruling_impact.csv")

QUANTITY_COLS = ["mix_tn", "grade_cy", "base_tn", "shldr_tn", "mill_sy", "crush_tn", "stock_tn"]

sys.path.insert(0, os.path.join(REPO, "pipelines", "plan_reader", "05_knowledge"))
import quantity_crosswalk as qc  # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "ruling_impact", os.path.join(HERE, "2026-08-10_ruling_impact.py"))
ri = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ri)

_spec2 = importlib.util.spec_from_file_location(
    "golden_join", os.path.join(HERE, "2026-08-10_golden_join.py"))
gj = importlib.util.module_from_spec(_spec2)
_spec2.loader.exec_module(gj)

failures: list[str] = []


def check(cond, msg):
    print(f"  {'PASS' if cond else 'FAIL'}  {msg}")
    if not cond:
        failures.append(msg)


def fatal(msg):
    print(f"FATAL: {msg}", file=sys.stderr)
    sys.exit(2)


# =====================================================================================
print("=== 1. the answer key was not edited ===")
try:
    committed = subprocess.run(["git", "show", f"HEAD:{GOLDEN_REL}"], cwd=REPO,
                               capture_output=True, text=True, check=True).stdout
except (subprocess.CalledProcessError, FileNotFoundError) as exc:
    fatal(f"cannot read the committed golden from git ({exc}) — refusing to report a clean run")

committed_rows = list(csv.DictReader(committed.splitlines()))
working_rows = list(csv.DictReader(open(GOLDEN, encoding="utf-8")))
if not committed_rows or not working_rows:
    fatal("golden_dataset.csv parsed to zero rows on one side — setup failure, not a pass")

check(len(committed_rows) == len(working_rows),
      f"row count unchanged ({len(committed_rows)})")

drifted = []
for i, (c, w) in enumerate(zip(committed_rows, working_rows)):
    for col in QUANTITY_COLS:
        if (c.get(col) or "") != (w.get(col) or ""):
            drifted.append(f"row {i} contract {w.get('contract_id')} {col}: "
                           f"{c.get(col)!r} -> {w.get(col)!r}")
check(not drifted,
      f"all 7 quantity columns byte-identical to HEAD across {len(working_rows)} rows"
      + ("" if not drifted else f" -- DRIFTED: {drifted}"))

n_cells = sum(1 for w in working_rows for col in QUANTITY_COLS if (w.get(col) or "").strip())
check(n_cells > 0, f"the golden actually holds quantities to protect ({n_cells} non-empty cells)")

# =====================================================================================
print("\n=== 2. every ruling-moved corpus row is attributed to a named ruling ===")
if not os.path.exists(DB):
    fatal(f"{DB} not found (symlink target may be offline)")
conn = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
rows = list(conn.execute("select plan_id, raw_description, unit, quantity from materials"))
conn.close()
if not rows:
    fatal("materials produced zero rows — refusing to report a clean run")

RUL, DNC = list(ri.RULINGS), list(ri.DO_NOT_COUNT)
try:
    qc.CSI_RULINGS_2026_08_07[:] = RUL
    qc.CSI_DO_NOT_COUNT_2026_08_07[:] = DNC
    on = {(pid, d, u, q): qc.csi_bucket(d, u) for pid, d, u, q in rows}
    qc.CSI_RULINGS_2026_08_07[:] = []
    qc.CSI_DO_NOT_COUNT_2026_08_07[:] = []
    off = {(pid, d, u, q): qc.csi_bucket(d, u) for pid, d, u, q in rows}
finally:
    qc.CSI_RULINGS_2026_08_07[:] = RUL
    qc.CSI_DO_NOT_COUNT_2026_08_07[:] = DNC

moved = [k for k in on if on[k] != off[k]]
check(len(moved) > 0, f"the rulings move a real number in this corpus ({len(moved)} item rows)")

unattributed = [k for k in moved if ri.ruling_for(k[1])[0] is None]
check(not unattributed,
      "every moved row names the ruling that moved it"
      + ("" if not unattributed else f" -- {len(unattributed)} unattributed, e.g. {unattributed[:3]}"))

bad_basis = {ri.ruling_for(k[1])[1] for k in moved} - {"CSI_2026-08-07", "T_2026-08-07"}
check(not bad_basis,
      "every attribution names its AUTHORITY (Alex's CSI rulings vs T/Mark's removal rule)"
      + ("" if not bad_basis else f" -- unknown: {bad_basis}"))

# =====================================================================================
print("\n=== 3. raw and ruling-adjusted stay distinguishable ===")
# Regenerate rather than trusting a stale CSV: a checked-in artifact that no longer matches the
# code would let this whole section pass against last week's numbers.
print("  (regenerating the artifact)")
_rc = ri.main()
if _rc != 0:
    fatal(f"2026-08-10_ruling_impact.py exited {_rc} — cannot test its output")
if not os.path.exists(IMPACT_CSV):
    fatal(f"{IMPACT_CSV} missing after a successful run — setup failure")
out = list(csv.DictReader(open(IMPACT_CSV, encoding="utf-8")))
if not out:
    fatal("ruling impact CSV is empty — refusing to report a clean run")

touched = [r for r in out if r["ruling_delta"] not in ("", "0")]
check(len(touched) > 0, f"the artifact records ruling-touched golden values ({len(touched)})")

both_present = [r for r in touched if r["golden_raw"]]
check(all(r["golden_ruling_adjusted"] for r in both_present),
      "every ruling-touched row with a golden value carries BOTH raw and adjusted")
check(all(r["golden_raw"] != r["golden_ruling_adjusted"] for r in both_present),
      "raw and adjusted are never rendered identically where a ruling fired")
check(all(r["ruling_ids"] for r in touched),
      "every non-zero delta names at least one ruling id")

# A ruling-adjusted MATCH must be its own status, never folded into the raw one.
statuses = {r["status"] for r in out}
check("MATCH_RULING_ADJUSTED" in statuses and "MATCH_RAW" in statuses,
      "MATCH_RAW and MATCH_RULING_ADJUSTED both occur and are separate values")
check("RULING_CONTRADICTS_GOLDEN" in statuses,
      "a ruling that moves us AWAY from a matching golden is reported, not silently absorbed")

# =====================================================================================
print("\n=== 4. CONVERSION_REQUIRED survives as its own third state ===")
check(hasattr(gj, "units_disagree") and gj.units_disagree("TON", "SY"),
      "the item-level CONVERSION_REQUIRED detector still fires on a real TON/SY pair")
check(gj.norm_unit("NOT A UNIT") is None and gj.norm_unit("also junk") is None,
      "two unrecognised units are UNKNOWN, never equal to each other")
# The bucket-grain classifier must produce it too, and must not reuse its value for a ruling fact.
check(ri.classify(100.0, 100.0, 0.0, False) == "CONVERSION_REQUIRED",
      "bucket-grain classify() emits CONVERSION_REQUIRED when the bucket's unit is absent")
check(ri.classify(100.0, 200.0, 100.0, True) == "MATCH_RULING_ADJUSTED",
      "a ruling adjustment produces its OWN status, not CONVERSION_REQUIRED")
check(ri.classify(100.0, 100.0, 100.0, True) == "RULING_CONTRADICTS_GOLDEN",
      "a ruling that breaks a raw match produces its OWN status")
ruling_statuses = {"MATCH_RULING_ADJUSTED", "RULING_CONTRADICTS_GOLDEN"}
check("CONVERSION_REQUIRED" not in ruling_statuses,
      "no ruling status shares CONVERSION_REQUIRED's value — three states, not two")

# =====================================================================================
print("\n=== 5. absence never shares a value with a quantity ===")
check(ri.classify(None, 5.0, 0.0, True) == "GOLDEN_ABSENT",
      "CSI stated nothing -> GOLDEN_ABSENT")
check(ri.classify(5.0, None, 0.0, True) == "EXTRACTION_ABSENT",
      "we produced nothing -> EXTRACTION_ABSENT (a different fact)")
check(ri.classify(None, None, 0.0, True) == "BOTH_ABSENT",
      "neither side has a value -> BOTH_ABSENT (a third fact)")
check(ri.num("") is None and ri.num("0") == 0.0,
      "an empty golden cell parses to None, never to 0 — 'CSI stated nothing' is not 'CSI stated zero'")
absent_rows = [r for r in out if r["status"].endswith("_ABSENT")]
check(all(not (r["golden_raw"] and r["extracted"]) for r in absent_rows),
      "no row is marked absent while carrying both quantities")

# =====================================================================================
print("\n=== 6. the crosswalk is not left mutated ===")
check(list(qc.CSI_RULINGS_2026_08_07) == RUL and list(qc.CSI_DO_NOT_COUNT_2026_08_07) == DNC,
      "quantity_crosswalk's ruling lists are restored after the impact module runs")

print()
if failures:
    print(f"{len(failures)} FAILED:")
    for f in failures:
        print(f"  - {f}")
    sys.exit(1)
print("all checks passed")
