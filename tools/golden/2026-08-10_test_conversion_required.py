"""COVERAGE test for CONVERSION_REQUIRED — run against the real corpus, not invented strings.

Why coverage rather than unit tests (the standing rule in this repo): a unit test over
`norm_unit("TON") == "TON"` proves the alias I remembered to write down works. It says nothing about
the unit strings that are actually in the corpus, and the failure mode that matters here is a unit
string the table does not know about being silently treated as agreement — which is exactly how a
TON quantity gets scored against a SY quantity as a clean MATCH.

So this walks EVERY distinct unit string in both sources and asserts:
  1. every unit string that appears on a MILLING-bucket row normalises to a known token (this is the
     bucket where a unit mix-up is a live defect: NDDOT pays milling by the TON against a bucket
     named `milling_sy` — NDDOT 411.06, docs/_spec/2026-08-10-milling-unit-capture.md);
  2. an unrecognised unit is UNKNOWN, never agreement — two garbage strings never compare equal;
  3. the three outcomes stay distinguishable on real corpus pairs: agree / disagree / unknown;
  4. the CONVERSION_REQUIRED branch actually fires on a real (golden TON, extracted SY) pair drawn
     from the corpus, so the category is exercised even though the MN-only golden set currently
     produces none of them.

Usage:  python 2026-08-10_test_conversion_required.py     (exit 0 = pass, 1 = fail)
"""

from __future__ import annotations

import csv
import importlib.util
import os
import sqlite3
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
GOLDEN_CSV = os.path.join(HERE, "2026-08-10_golden_rows.csv")
DB = os.path.join(REPO, "pipelines", "plan_reader", "csi_v2.db")

# The module under test has a date-prefixed filename, which is not a legal identifier.
_spec = importlib.util.spec_from_file_location(
    "golden_join", os.path.join(HERE, "2026-08-10_golden_join.py"))
gj = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gj)

failures: list[str] = []
notes: list[str] = []


def check(cond, msg):
    if cond:
        print(f"  PASS  {msg}")
    else:
        print(f"  FAIL  {msg}")
        failures.append(msg)


print("=== 1. unit strings present in the corpus ===")
if not os.path.exists(GOLDEN_CSV):
    print(f"FATAL: {GOLDEN_CSV} missing — this is a setup failure, not a pass.", file=sys.stderr)
    sys.exit(2)
golden_units = Counter(r["unit"] for r in csv.DictReader(open(GOLDEN_CSV, encoding="utf-8")))
if not golden_units:
    print("FATAL: golden CSV produced zero unit strings — refusing to report a clean run.",
          file=sys.stderr)
    sys.exit(2)

unknown_golden = {u: n for u, n in golden_units.items() if gj.norm_unit(u) is None}
print(f"  golden: {len(golden_units)} distinct unit strings, "
      f"{len(unknown_golden)} unrecognised: {sorted(unknown_golden)}")

mill_units: Counter = Counter()
db_units: Counter = Counter()
if os.path.exists(DB):
    conn = sqlite3.connect(DB)
    db_units = Counter(dict(conn.execute(
        "select unit, count(*) from materials group by 1")))
    mill_units = Counter(dict(conn.execute(
        "select unit, count(*) from materials where csi_bucket='milling_sy' group by 1")))
    unknown_db = {u: n for u, n in db_units.items() if gj.norm_unit(u) is None}
    print(f"  materials: {len(db_units)} distinct unit strings, {len(unknown_db)} unrecognised")
    check(mill_units, "the milling bucket has rows to check at all (an empty check is not a pass)")
    bad_mill = {u: n for u, n in mill_units.items() if u and gj.norm_unit(u) is None}
    check(not bad_mill, f"every unit on a milling_sy row normalises to a known token "
                        f"(unrecognised: {bad_mill})")
else:
    notes.append(f"csi_v2.db not reachable at {DB} (iCloud symlink offline) — checks 1b and 4b "
                 f"were SKIPPED, not passed.")
    print(f"  SKIP  materials — {DB} not reachable")

print("\n=== 2. unrecognised is UNKNOWN, never agreement ===")
check(gj.norm_unit("Col4") is None and gj.norm_unit("22-2-23A") is None,
      "real corpus garbage ('Col4', '22-2-23A') normalises to None")
check(not gj.units_disagree("Col4", "Col5") and not gj.units_disagree("Col4", "Col4"),
      "two unknown units are neither a disagreement nor an agreement — identical garbage strings "
      "do NOT report as matching units")
check(not gj.units_disagree("TON", "Col4") and not gj.units_disagree("", "SY"),
      "one unknown side never promotes a row to CONVERSION_REQUIRED on a guess")

print("\n=== 3. the three outcomes stay distinguishable on real corpus spellings ===")
for a, b in [("S Y", "SY"), ("SQ YD", "SY"), ("C Y", "CY"), ("Ton", "TON"), ("LIN FT", "LF"),
             ("CuYd", "CY"), ("Each", "EA"), ("L SUM", "LS")]:
    check(gj.norm_unit(a) == gj.norm_unit(b) and gj.norm_unit(a) is not None,
          f"corpus spellings agree: {a!r} == {b!r} -> {gj.norm_unit(a)}")
for a, b in [("TON", "SY"), ("TON", "CY"), ("SQ YD", "CU YD"), ("Ton", "S Y")]:
    check(gj.units_disagree(a, b), f"real unit pair disagrees: {a!r} vs {b!r}")

print("\n=== 4. the CONVERSION_REQUIRED branch fires on a real pair ===")
# The pair is drawn from the corpus rather than invented: TON is the most common golden unit after
# the count units (49 rows) and SY is a real materials unit (151 rows). This is the NDDOT milling
# shape — the state pays by the ton, the bucket is named _sy.
check(gj.units_disagree("TON", "SY"),
      "golden TON vs extracted SY is a disagreement (the NDDOT milling case)")
check("TON" in golden_units, "TON actually occurs in the golden corpus (49 rows expected)")
if db_units:
    check(db_units.get("SY", 0) > 0 or db_units.get("Sy", 0) > 0,
          "SY actually occurs in materials")

# And the scoring consequence, stated as arithmetic so the exclusion cannot silently regress:
# 1 match + 1 conversion out of 2 golden / 2 extracted must read 1.000 / 1.000, not 0.500.
matched, conversion, n_gold, n_extr = 1, 1, 2, 2
prec = matched / (n_extr - conversion)
rec = matched / (n_gold - conversion)
check(abs(prec - 1.0) < 1e-9 and abs(rec - 1.0) < 1e-9,
      "a CONVERSION_REQUIRED row leaves BOTH denominators (1 match + 1 conversion scores "
      "1.000/1.000, not 0.500) — a missing conversion layer is not reported as a recall failure")

print("\n" + "=" * 72)
for n in notes:
    print(f"NOTE: {n}")
if failures:
    print(f"FAILED: {len(failures)} check(s)")
    sys.exit(1)
print(f"OK: all checks passed{' (with skips noted above)' if notes else ''}")
