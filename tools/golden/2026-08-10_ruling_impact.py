"""Ruling-aware reconciliation of the BUCKET-level golden against the extraction.

Answers, per (golden contract, bucket): does our number differ from CSI's because we extracted
something wrong, or because one of CSI's 2026-08-07 rulings moved a quantity into (or out of) that
bucket AFTER the golden value was recorded?

Design — see docs/_spec/2026-08-10-ruling-aware-golden.md
--------------------------------------------------------
* `golden_dataset.csv` IS NEVER EDITED BY THIS SCRIPT OR BY THE RULINGS. It is read-only ground
  truth. A golden set that silently tracks our own rulings can never tell us a ruling is wrong.
* Three values are carried, never two: the RAW golden value, the ruling DELTA (with the rulings
  that produced it named), and the derived ruling-ADJUSTED value. The adjusted value is computed,
  never stored in the golden file, so it can never be mistaken for a number a source stated.
* The delta is measured by running the real crosswalk TWICE over the same extracted item rows —
  once with CSI_RULINGS_2026_08_07 / CSI_DO_NOT_COUNT_2026_08_07 active and once with both empty —
  and diffing the bucket totals. It is not a hand-maintained list, so it cannot drift from the
  rulings that actually ship.
* LIMITATION, stated on the artifact rather than buried: the delta is derived from OUR OWN
  extracted item rows. If extraction missed an item, it also missed that item's contribution to
  the adjustment, so a MATCH_RULING_ADJUSTED is a weaker claim than a MATCH_RAW. The two are
  reported on separate lines and never summed into one accuracy number here.
* Failure and empty never share a value. `GOLDEN_ABSENT` (CSI left the cell blank),
  `EXTRACTION_ABSENT` (we produced no quantity for this bucket) and a real zero are three
  different statuses, and an unresolvable plan join is `AMBIGUOUS_COUNTY`, never a guess.
* CONVERSION_REQUIRED is preserved as its own third state, out of both denominators, exactly as
  2026-08-10_golden_join.py and docs/_spec/2026-08-10-benchmark-table.md 5 define it. Rulings add
  statuses here; they remove none and they never reuse CONVERSION_REQUIRED's value.

Read-only: opens SQLite with mode=ro, writes one local CSV. No database writes, no DDL, no API.

Usage:  python tools/golden/2026-08-10_ruling_impact.py     (exit 0 = ok, 1 = empty result)
"""

from __future__ import annotations

import csv
import os
import re
import sqlite3
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
DB = os.path.join(REPO, "pipelines", "plan_reader", "csi_v2.db")
GOLDEN = os.path.join(REPO, "pipelines", "plan_reader", "00_input", "golden_dataset.csv")
OUT = os.path.join(HERE, "2026-08-10_ruling_impact.csv")

sys.path.insert(0, os.path.join(REPO, "pipelines", "plan_reader", "05_knowledge"))
import quantity_crosswalk as qc  # noqa: E402

# The live ruling lists, captured before anything is swapped out. Restored in a finally block.
RULINGS = list(qc.CSI_RULINGS_2026_08_07)
DO_NOT_COUNT = list(qc.CSI_DO_NOT_COUNT_2026_08_07)

# Stable identifiers for the rulings, so a CSV row says WHICH ruling moved a number rather than
# just that one did. Alex's 11 are CSI#1..#11 in the order of docs/_spec/2026-08-10-live-mapping-
# rulings.md; T's 8 (Mark's removal rule) are a different AUTHORITY and are labelled as such.
RULING_ID = {
    "REMOVE CONCRETE DRIVEWAY PAVEMENT": ("CSI#1", "CSI_2026-08-07"),
    "REMOVE BITUMINOUS DRIVEWAY PAVEMENT": ("CSI#2", "CSI_2026-08-07"),
    "CEMENT STABILIZED SUBGRADE": ("CSI#3", "CSI_2026-08-07"),
    "PORTLAND CEMENT": ("CSI#4", "CSI_2026-08-07"),
    "REMOVE BITUMINOUS PAVEMENT": ("CSI#5", "CSI_2026-08-07"),
    "REMOVAL OF BITUMINOUS SURFACING": ("CSI#6", "CSI_2026-08-07"),
    "GRAVEL SURFACING": ("CSI#7", "CSI_2026-08-07"),
    "TRAFFIC SERVICE AGGREGATE": ("CSI#8", "CSI_2026-08-07"),
    "FULL DEPTH RECLAMATION": ("CSI#9", "CSI_2026-08-07"),
    "SALVAGE AND REUSE EXISTING AGGREGATE": ("CSI#10", "CSI_2026-08-07"),
    "CLEAN ROCK": ("CSI#11", "CSI_2026-08-07"),
}
T_RULE = ("T#removal", "T_2026-08-07")

# golden_dataset.csv contract_id -> plans.plan_id.
#
# EXPLICIT, not fuzzy: a wrong plan match silently corrupts every number downstream and looks
# exactly like an extraction error. Resolution methods, in precedence order, are recorded per row:
#   contract_id      -- plans.contract_id carries the golden key outright (5 plans)
#   state_county_year-- exactly ONE 2025 plan in that state+county, so the match is forced
#   evidence         -- state+county is ambiguous AND a bucket total identifies the plan uniquely
# Counties where 2025 holds more than one plan and no evidence separates them are NOT guessed;
# they are listed in AMBIGUOUS below and emitted with status AMBIGUOUS_COUNTY.
CONTRACT_TO_PLAN = {
    # -- plans.contract_id (rank 1) -------------------------------------------------------------
    "1633": ("2025_JACKSON-CO-MN_SAP-032-629-048_NOBID", "contract_id"),
    "1641": ("2025_STUTSMAN-CO-ND_CR-68_NOBID", "contract_id"),
    "1644": ("2025_WATONWAN-CO-MN_WATLINE-TRAIL_NOBID", "contract_id"),
    "1649": ("2025_DOUGLAS-CO-MN_SAP-021-600-023_NOBID", "contract_id"),
    "1654": ("2025_HAND-CO-SD_08MQ_NOBID", "contract_id"),
    # -- unique 2025 plan in that state+county (rank 2) -------------------------------------------
    "1622": ("2025_DAY-CO-SD_PCN-09GX_NOBID", "state_county_year"),
    "1623": ("2025_YANKTON-CO-SD_9738173_NOBID", "state_county_year"),
    "1625": ("2025_POPE-CO-MN_9776825_NOBID", "state_county_year"),
    "1626": ("2025_JACKSON-CO-SD_09MD_NOBID", "state_county_year"),
    "1628": ("2025_DUNN-CO-ND_9782095_NOBID", "state_county_year"),
    "1631": ("2025_DIVIDE-CO-ND_9776856_NOBID", "state_county_year"),
    "1630": ("2025_MURRAY-CO-MN_CSAH-2_NOBID", "state_county_year"),
    "1632": ("2025_RENVILLE-CO-MN_SAP-065-599-097_NOBID", "state_county_year"),
    "1634": ("2025_CASS-CO-MN_SAP-011-636-007_NOBID", "state_county_year"),
    "1635": ("2025_SHERBURNE-CO-MN_9747843_NOBID", "state_county_year"),
    "1637": ("2025_PENNINGTON-CO-SD_PCN-09GR_NOBID", "state_county_year"),
    "1640": ("2025_MINNEHAHA-CO-SD_UNKNOWN_NOBID", "state_county_year"),
    "1642": ("2025_MORTON-CO-ND_JOB-24133_NOBID", "state_county_year"),
    "1643": ("2025_MOUNTRAIL-CO-ND_9790217_NOBID", "state_county_year"),
    "1647": ("2025_HUBBARD-CO-MN_SP-2905-39_NOBID", "state_county_year"),
    "1648": ("2025_BUFFALO-CO-SD_9809453_NOBID", "state_county_year"),
    "1651": ("2025_BEADLE-CO-SD_SD-2025_NOBID", "state_county_year"),
    "1652": ("2025_KOOCHICHING-CO-MN_SAP-036-624-026_NOBID", "state_county_year"),
    "1653": ("2025_MELLETTE-CO-SD_PCN-09A6_UNKNOWN", "state_county_year"),
    "1655": ("2025_PERKINS-CO-SD_PCN-09V7_NOBID", "state_county_year"),
    "1656": ("2025_LYMAN-CO-SD_PCN-080A_NOBID", "state_county_year"),
    # -- ambiguous state+county, separated by evidence (rank 3) -----------------------------------
    # Stearns MN has two 2025 plans. Golden 1659 states MILL SY = 70,263; CP-073-123's non-FDR
    # milling items sum to exactly 70,263 SY and its hot mix to exactly 14,480 TON (= golden
    # MIX TN), while SAP-073-590-007 has no extracted materials at all. Two independent bucket
    # totals agreeing to the unit is evidence, not a guess; it is recorded as its own method so a
    # reader can see it is weaker than a contract_id.
    "1659": ("2025_STEARNS-CO-MN_CP-073-123_NOBID", "evidence_bucket_total"),
}

# state+county pairs that hold more than one 2025 golden row AND more than one 2025 plan, with no
# evidence separating them. Emitted, never guessed.
AMBIGUOUS = {"1627": "SD/Hand: 3 plans, 2 golden rows, no distinguishing quantity",
             "1629": "MN/Kandiyohi: 2 plans, 2 golden rows, no distinguishing quantity",
             "1650": "MN/Kandiyohi: 2 plans, 2 golden rows, no distinguishing quantity",
             "1639": "MN/Stearns: 2 golden rows; 1659 resolved by evidence, 1639 not",
             "1636": "SD/Lincoln: no 2025 plan extracted",
             "1645": "IA/Poweshiek: no 2025 plan extracted",
             "1646": "IA/Worth: no 2025 plan extracted",
             "1658": "NE/Knox: no 2025 plan extracted",
             "1660": "NE/Cuming: no 2025 plan extracted",
             "1661": "NE/Sarpy: no 2025 plan extracted"}

# extracted bucket -> golden_dataset.csv column
FIELD_MAP = {"hot_mix_tons": "mix_tn", "grading_quantity": "grade_cy", "base_tons": "base_tn",
             "shoulder_tons": "shldr_tn", "milling_sy": "mill_sy", "crushing_tons": "crush_tn",
             "stockpile_tons": "stock_tn"}

# The unit each bucket is denominated in, reused from the crosswalk rather than restated, so the
# CONVERSION_REQUIRED check here cannot drift from the one the crosswalk enforces.
BUCKET_UNIT = qc.BUCKET_UNIT

TOL = 0.08   # same 8% tolerance validate_quantities.py uses, so the two are comparable


def num(s):
    """Parse a golden cell. Returns None for an EMPTY cell -- which is 'CSI stated nothing here',
    never a zero. A zero would score as a 100% error against every real extracted quantity."""
    s = re.sub(r"[^\d.]", "", str(s or "").replace(",", ""))
    try:
        return float(s) if s not in ("", ".") else None
    except ValueError:
        return None


def bucket_totals(rows, rulings, do_not_count):
    """Sum extracted item quantities into buckets under a given ruling regime."""
    qc.CSI_RULINGS_2026_08_07[:] = rulings
    qc.CSI_DO_NOT_COUNT_2026_08_07[:] = do_not_count
    totals, units = {}, {}
    for desc, unit, qty in rows:
        if qty is None:
            continue
        b = qc.csi_bucket(desc, unit)
        if b:
            totals[b] = totals.get(b, 0.0) + qty
            units.setdefault(b, set()).add(qc._normalize_unit(unit))
    return totals, units


def ruling_for(desc):
    """(ruling_id, basis) for the ruling that fires on this description, or (None, None)."""
    upper = qc.normalize_description(desc)
    for pattern, _cat, _ov, _note in qc.CSI_RULINGS_2026_08_07:
        if pattern in upper:
            return RULING_ID.get(pattern, T_RULE)
    for pattern in qc.CSI_DO_NOT_COUNT_2026_08_07:
        if pattern in upper:
            return ("CSI#do_not_count", "CSI_2026-08-07")
    return (None, None)


def moved_items(rows):
    """Per bucket, the items the rulings moved in (+) or out (-), with the ruling that did it."""
    # Attribution MUST be captured while the rulings are still installed: `ruling_for` reads the
    # live lists, so calling it after they are emptied silently returns (None, None) for every row
    # and the CSV ships with a blank `ruling_ids` column. That defect shipped once and was caught
    # by 2026-08-10_test_ruling_aware.py, not by reading this function.
    qc.CSI_RULINGS_2026_08_07[:] = RULINGS
    qc.CSI_DO_NOT_COUNT_2026_08_07[:] = DO_NOT_COUNT
    on = {}
    for desc, unit, qty in rows:
        on[(desc, unit, qty)] = (qc.csi_bucket(desc, unit), ruling_for(desc))
    qc.CSI_RULINGS_2026_08_07[:] = []
    qc.CSI_DO_NOT_COUNT_2026_08_07[:] = []
    per_bucket = {}
    for (desc, unit, qty), (b_on, (rid, basis)) in on.items():
        if qty is None:
            continue
        b_off = qc.csi_bucket(desc, unit)
        if b_on == b_off:
            continue
        if b_on:
            per_bucket.setdefault(b_on, []).append((+qty, rid, basis, desc, unit))
        if b_off:
            per_bucket.setdefault(b_off, []).append((-qty, rid, basis, desc, unit))
    return per_bucket


def classify(golden, extracted, delta, extracted_unit_ok):
    """The status vocabulary of docs/_spec/2026-08-10-ruling-aware-golden.md 3.

    Every distinct fact keeps a distinct value. In particular a MATCH that only holds after the
    ruling adjustment is NOT the same claim as a raw match, and a ruling that moves us AWAY from a
    golden the raw value already matched is a question for CSI, not an extraction bug."""
    if golden is None and extracted is None:
        return "BOTH_ABSENT"
    if golden is None:
        return "GOLDEN_ABSENT"
    if extracted is None:
        return "EXTRACTION_ABSENT"
    if not extracted_unit_ok:
        # Same bucket, both sides quantified, the extracted side is not in the bucket's own unit.
        # Out of both denominators -- a missing conversion layer, not a missing extraction.
        return "CONVERSION_REQUIRED"

    def within(g):
        return bool(g) and abs((extracted - g) / g) <= TOL

    raw_ok, adj_ok = within(golden), within(golden + delta)
    if delta == 0:
        return "MATCH_RAW" if raw_ok else "MISMATCH"
    if raw_ok and not adj_ok:
        return "RULING_CONTRADICTS_GOLDEN"
    if adj_ok and not raw_ok:
        return "MATCH_RULING_ADJUSTED"
    if raw_ok and adj_ok:
        return "MATCH_RAW"          # the adjustment is inside tolerance; the raw claim still holds
    return "MISMATCH"


def main() -> int:
    if not os.path.exists(DB):
        print(f"ERROR: {DB} not found (symlink target may be offline)", file=sys.stderr)
        return 2
    conn = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    mats = {}
    for pid, desc, unit, qty in conn.execute(
            "select plan_id, raw_description, unit, quantity from materials"):
        mats.setdefault(pid, []).append((desc, unit, qty))
    conn.close()
    if not mats:
        print("FATAL: materials table produced zero rows -- refusing to report a clean run.",
              file=sys.stderr)
        return 2

    golden = {r["contract_id"]: r
              for r in csv.DictReader(open(GOLDEN, encoding="utf-8")) if r["contract_id"]}
    if not golden:
        print(f"FATAL: {GOLDEN} produced zero keyed rows.", file=sys.stderr)
        return 2

    out_rows = []
    for cid in sorted(golden):
        g = golden[cid]
        if cid not in CONTRACT_TO_PLAN:
            out_rows.append(dict(
                contract_id=cid, plan_id="", plan_match_method="unresolved",
                state=g["state"], county=g["county"], bucket="", golden_raw="",
                ruling_delta="", ruling_ids="", ruling_basis="", golden_ruling_adjusted="",
                extracted="", extracted_pre_ruling="", status="AMBIGUOUS_COUNTY",
                note=AMBIGUOUS.get(cid, "no unique 2025 plan for this state+county")))
            continue
        pid, method = CONTRACT_TO_PLAN[cid]
        rows = mats.get(pid, [])
        if not rows:
            out_rows.append(dict(
                contract_id=cid, plan_id=pid, plan_match_method=method,
                state=g["state"], county=g["county"], bucket="", golden_raw="",
                ruling_delta="", ruling_ids="", ruling_basis="", golden_ruling_adjusted="",
                extracted="", extracted_pre_ruling="", status="EXTRACTED_ZERO_ITEMS",
                note="plan exists, materials table has no rows for it"))
            continue

        moved = moved_items(rows)
        on, on_units = bucket_totals(rows, RULINGS, DO_NOT_COUNT)
        off, _ = bucket_totals(rows, [], [])

        for bucket, gcol in FIELD_MAP.items():
            graw = num(g[gcol])
            ev = on.get(bucket)
            pre = off.get(bucket)
            if graw is None and ev is None and bucket not in moved:
                continue
            entries = moved.get(bucket, [])
            delta = round(sum(e[0] for e in entries), 4)
            rids = ",".join(sorted({e[1] for e in entries if e[1]}))
            bases = ",".join(sorted({e[2] for e in entries if e[2]}))
            units = on_units.get(bucket, set())
            unit_ok = (ev is None) or (BUCKET_UNIT.get(bucket) in units) or not units
            out_rows.append(dict(
                contract_id=cid, plan_id=pid, plan_match_method=method,
                state=g["state"], county=g["county"], bucket=bucket,
                golden_raw="" if graw is None else f"{graw:g}",
                ruling_delta=f"{delta:g}" if delta else "0",
                ruling_ids=rids, ruling_basis=bases,
                golden_ruling_adjusted="" if graw is None else f"{graw + delta:g}",
                extracted="" if ev is None else f"{ev:g}",
                extracted_pre_ruling="" if pre is None else f"{pre:g}",
                status=classify(graw, ev, delta, unit_ok),
                note="; ".join(f"{'+' if q > 0 else ''}{q:g} {d.strip()[:44]} ({rid})"
                               for q, rid, _b, d, _u in entries)))

    qc.CSI_RULINGS_2026_08_07[:] = RULINGS
    qc.CSI_DO_NOT_COUNT_2026_08_07[:] = DO_NOT_COUNT

    with open(OUT, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(out_rows[0].keys()))
        w.writeheader()
        w.writerows(out_rows)

    # ---- report ----------------------------------------------------------------------------
    touched = [r for r in out_rows if r["ruling_delta"] not in ("", "0")]
    print("=== GOLDEN VALUES A CSI RULING MOVES (bucket grain) ===")
    print(f"{'cid':5} {'bucket':17} {'golden_raw':>11} {'delta':>10} {'adjusted':>11} "
          f"{'extracted':>11} {'pre-ruling':>11}  ruling      status")
    for r in sorted(touched, key=lambda r: (r["contract_id"], r["bucket"])):
        print(f"{r['contract_id']:5} {r['bucket']:17} {r['golden_raw'] or '-':>11} "
              f"{r['ruling_delta']:>10} {r['golden_ruling_adjusted'] or '-':>11} "
              f"{r['extracted'] or '-':>11} {r['extracted_pre_ruling'] or '-':>11}  "
              f"{r['ruling_ids']:11} {r['status']}")

    print("\n=== STATUS COUNTS ===")
    counts = {}
    for r in out_rows:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    for s, n in sorted(counts.items(), key=lambda kv: -kv[1]):
        print(f"  {s:28} {n:>4}")

    # Scored-accuracy comparison, printed BOTH ways and labelled, so nobody can quote the
    # ruling-edited number without seeing that it is the ruling-edited number.
    # Denominator = every row where CSI stated a quantity, MINUS the CONVERSION_REQUIRED rows.
    # EXTRACTION_ABSENT stays IN as a miss: we produced nothing where CSI stated something, and
    # dropping those would quietly turn a recall failure into a smaller denominator. Only
    # CONVERSION_REQUIRED leaves, because that one is a known, deliberate design gap.
    scored = [r for r in out_rows if r["golden_raw"] and r["status"] != "CONVERSION_REQUIRED"]
    raw_hits = sum(1 for r in scored if r["status"] in ("MATCH_RAW", "RULING_CONTRADICTS_GOLDEN"))
    adj_hits = sum(1 for r in scored if r["status"] in ("MATCH_RAW", "MATCH_RULING_ADJUSTED"))
    n = len(scored)
    print(f"\n=== BUCKET-LEVEL ACCURACY, {n} comparisons at +/-{TOL:.0%} "
          f"(CONVERSION_REQUIRED excluded from both) ===")
    print(f"  vs RAW golden (independent ground truth)      {raw_hits}/{n} = "
          f"{100 * raw_hits / n:.0f}%")
    print(f"  vs RULING-ADJUSTED golden (ANSWER KEY EDITED) {adj_hits}/{n} = "
          f"{100 * adj_hits / n:.0f}%")
    print("  The second number is not an accuracy improvement. It is the same extraction scored\n"
          "  against a key we moved. Present the first, with the ruling split shown separately.")
    print("  Caveat carried from the spec: the delta is computed from OUR extracted item rows, so\n"
          "  a MATCH_RULING_ADJUSTED is a weaker claim than a MATCH_RAW.")

    print(f"\nwrote {OUT}  ({len(out_rows)} rows)")
    if not touched:
        print("\nCOVERAGE PROBLEM: no golden value is ruling-touched. Either the rulings stopped\n"
              "firing or the join broke -- this is a failure, not a clean run.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    finally:
        qc.CSI_RULINGS_2026_08_07[:] = RULINGS
        qc.CSI_DO_NOT_COUNT_2026_08_07[:] = DO_NOT_COUNT
