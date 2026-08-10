"""Join golden bid-item rows to extracted `materials` and score the extraction.

Reads the normalised golden table produced by 2026-08-10_golden_parse.py and the
local SQLite store, and emits a per-item comparison plus per-bucket precision /
recall / absolute variance. Writes a LOCAL CSV only. No database writes, no DDL.

Design notes
------------
* Golden file -> plan_id is an EXPLICIT mapping (below), derived from the state
  project number (SAP/SP/CP) that appears in both the corpus folder name and
  `plans.dot_project_id`. It is explicit rather than fuzzy because a wrong match
  would silently corrupt every number downstream.
* Item-level join key is the state spec item number: golden `spec_item_number`
  against `materials.bid_item_no`. That column holds the spec number on some
  plans and a bare line number on others, so the loader CLASSIFIES each plan
  first and refuses to join a plan whose bid_item_no is line-numbered -- rather
  than joining it and reporting a misleading 0% recall.
* Failure and empty never share a return value: every result carries a `status`
  field, and `NO_GOLDEN`, `NO_EXTRACTION`, `KEY_UNUSABLE` and `OK` are distinct.
* CONVERSION_REQUIRED is its OWN category -- not a hit and not a miss. When the
  keys match, both sides carry a quantity, and the units disagree (the golden bid
  schedule states SY or CY, our extraction states TON, or vice versa), what is
  missing is the CONVERSION LAYER, not the extraction. Scoring it as a miss
  reports a recall failure the extractor does not deserve; scoring it as a match
  inflates precision and produces a variance figure computed across two different
  units, which is not a number that means anything. So it is excluded from
  `matched`, excluded from BOTH the recall and precision denominators, carries no
  variance, and is printed on its own line so the gap stays visible.
  Designed in docs/_spec/2026-08-10-benchmark-table.md 2.3 / 5; the concrete case
  is NDDOT milling, which is paid by the TON (NDDOT 411.06) against a bucket
  named `milling_sy` -- see docs/_spec/2026-08-10-milling-unit-capture.md.
* A unit string that normalises to nothing on EITHER side is unknown, not
  agreement: such a row keeps its previous status and `unit_match` is left blank,
  rather than being promoted to CONVERSION_REQUIRED on a guess.
"""

from __future__ import annotations

import csv
import os
import re
import sqlite3
import sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
GOLDEN_CSV = os.path.join(HERE, "2026-08-10_golden_rows.csv")
DB = os.path.join(REPO, "pipelines", "plan_reader", "csi_v2.db")

SPEC_RE = re.compile(r"^\d{4}\.\d{3}(/\d+)?$")

# corpus project folder  ->  plans.plan_id      (None = no extracted plan exists)
# Matched on the state project number present in both strings; verified by hand
# against `select plan_id, county, dot_project_id from plans where state='MN'`.
FOLDER_TO_PLAN = {
    "02.22.23 BLUE EARTH CO MN - CONTRACT NO. 230416 SAP 007-616-035 CSAH 16 LESUEUR RIVER BRIDGE":
        "2023_BLUE-EARTH-CO-MN_SAP-007-616-035_NOBID",
    "02.22.23 CROW WING CO MN - SAP 018-603-024 & SAP 018-611-029 CSAH 3 & CSAH 11 ROUNDABOUT":
        "2023_CROW-WING-CO-MN_SAP-018-603-024_NOBID",
    "04.26.23 BLUE EARTH CO MN - CONTRACT NO 234264 SAP 007-626-019 CSAH 26 RECONSTRUCTION":
        "2023_BLUE-EARTH-CO-MN_SAP-007-626-019_NOBID",
    "04.27.23 POPE CO MN - SAP 061-615-008 CSAH 15 GRADING, AGGREGATEBASE, CULVERT REPLACEMENT":
        "2023_POPE-CO-MN_SAP-061-615-008_NOBID",
    "08.19.25 WATONWAN CO MN SAP 083-090-007 WATLINE TRAIL & CSAH 10":
        "2025_WATONWAN-CO-MN_WATLINE-TRAIL_NOBID",
    "25049 Marshall 2025 Bituminous Surfacing": None,
    "25051 Murray County (CSAH 42, 47, CR 67)": None,
    "12.12.24 CARVER CO MN SP 1008-106, SP 10-610-058, ETC CSAH 10 & TH 41 RECONST PROJECT": None,
}

BUCKETS = ["hot_mix_tons", "base_tons", "grading_quantity", "milling_sy",
           "shoulder_tons", "crushing_tons", "stockpile_tons"]


# Unit normalisation. Deliberately a small EXPLICIT table: an unrecognised unit must come back as
# None ("unknown") rather than as itself, so two unrecognised strings can never compare equal and be
# read as agreement.
_UNIT_ALIASES = {
    "SY": "SY", "S Y": "SY", "SQ YD": "SY", "SQYD": "SY", "SQ. YD.": "SY", "SQUARE YARD": "SY",
    "SQUARE YARDS": "SY", "SQ YDS": "SY",
    "CY": "CY", "C Y": "CY", "CU YD": "CY", "CUYD": "CY", "CUBIC YARD": "CY", "CUBIC YARDS": "CY",
    "TON": "TON", "TONS": "TON", "TN": "TON", "T": "TON",
    "LF": "LF", "L F": "LF", "LIN FT": "LF", "LINEAR FOOT": "LF", "LINEAR FEET": "LF",
    "FT": "LF", "FOOT": "LF", "FEET": "LF",
    "SF": "SF", "S F": "SF", "SQ FT": "SF", "SQUARE FOOT": "SF", "SQUARE FEET": "SF",
    "EACH": "EACH", "EA": "EACH",
    "LS": "LS", "LUMP SUM": "LS", "LSUM": "LS", "L SUM": "LS", "L S": "LS",
    "GAL": "GAL", "GALLON": "GAL", "GALLONS": "GAL",
    "MGAL": "MGAL", "M GALLON": "MGAL", "ACRE": "ACRE", "AC": "ACRE",
    "STA": "STA", "STATION": "STA", "ROAD STA": "STA",
    "LB": "LB", "LBS": "LB", "POUND": "LB", "POUNDS": "LB", "HOUR": "HOUR", "HR": "HOUR",
}


def norm_unit(s):
    """Canonical unit token, or None when the string is absent or unrecognised.

    None means UNKNOWN and never compares equal to anything -- including another None. That is the
    failure/empty rule applied to units: 'we could not read the unit' must not be able to masquerade
    as 'the units agree'."""
    if s is None:
        return None
    # Periods are dropped wholesale: the corpus writes 'S.Y.' as well as 'SY' and 'SQ. YD.', and a
    # trailing-only strip left 'S.Y.' unrecognised — caught by the coverage test, not by inspection.
    t = str(s).replace("\xa0", " ").strip().upper().replace(".", "")
    t = re.sub(r"[()\[\]]", "", t)
    t = re.sub(r"\s+", " ", t)
    return _UNIT_ALIASES.get(t)


def units_disagree(golden_unit, extracted_unit) -> bool:
    """True only when BOTH units are known and they differ. Unknown on either side is not a
    disagreement and is not an agreement -- the caller leaves the row's status alone."""
    g, e = norm_unit(golden_unit), norm_unit(extracted_unit)
    return g is not None and e is not None and g != e


def norm_key(s: str) -> str:
    """Normalise a spec item number for joining. Extended /nnnnn suffix is kept
    separate so 2104.503 and 2104.503/00315 can be compared at both precisions."""
    return (s or "").replace("\xa0", " ").strip()


def base_key(s: str) -> str:
    return norm_key(s).split("/")[0]


def load_golden():
    if not os.path.exists(GOLDEN_CSV):
        raise SystemExit(f"missing {GOLDEN_CSV} -- run 2026-08-10_golden_parse.py first")
    rows = list(csv.DictReader(open(GOLDEN_CSV, encoding="utf-8")))
    if not rows:
        raise SystemExit("golden CSV is empty -- parser produced nothing")
    by_folder = defaultdict(list)
    for r in rows:
        by_folder[r["project_folder"]].append(r)
    return by_folder


def classify_key_column(conn, plan_id: str) -> tuple[str, int, int]:
    """Is this plan's materials.bid_item_no a spec number or a line number?"""
    rows = [r[0] for r in conn.execute(
        "select bid_item_no from materials where plan_id=?", (plan_id,))]
    if not rows:
        return "NO_ROWS", 0, 0
    spec = sum(1 for v in rows if v and SPEC_RE.match(norm_key(str(v))))
    return ("SPEC" if spec >= max(3, 0.5 * len(rows)) else "LINE"), spec, len(rows)


def main() -> int:
    if not os.path.exists(DB):
        print(f"ERROR: {DB} not found (symlink target may be offline)", file=sys.stderr)
        return 2
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    golden = load_golden()

    detail = []
    summary = []

    for folder, grows in sorted(golden.items()):
        if folder not in FOLDER_TO_PLAN:
            summary.append(dict(project_folder=folder, plan_id="", status="UNMAPPED_FOLDER",
                                golden_rows=len(grows), extracted_rows=0, matched=0, conversion_required=0,
                                precision="", recall=""))
            continue
        plan_id = FOLDER_TO_PLAN[folder]
        if plan_id is None:
            summary.append(dict(project_folder=folder, plan_id="", status="NO_EXTRACTION",
                                golden_rows=len(grows), extracted_rows=0, matched=0, conversion_required=0,
                                precision="", recall=""))
            continue

        kind, nspec, ntot = classify_key_column(conn, plan_id)
        if kind == "NO_ROWS":
            summary.append(dict(project_folder=folder, plan_id=plan_id, status="EXTRACTED_ZERO_ITEMS",
                                golden_rows=len(grows), extracted_rows=0, matched=0, conversion_required=0,
                                precision="", recall="0.000"))
            continue
        if kind == "LINE":
            summary.append(dict(project_folder=folder, plan_id=plan_id, status="KEY_UNUSABLE",
                                golden_rows=len(grows), extracted_rows=ntot, matched=0, conversion_required=0,
                                precision="", recall=""))
            continue

        ex = {}
        for r in conn.execute(
                "select bid_item_no,raw_description,unit,quantity,csi_bucket from materials "
                "where plan_id=?", (plan_id,)):
            k = base_key(str(r["bid_item_no"] or ""))
            if k:
                ex.setdefault(k, []).append(r)

        gmap = defaultdict(list)
        for g in grows:
            k = base_key(g["spec_item_number"])
            if k:
                gmap[k].append(g)

        matched = 0
        conversion_required = 0
        for k, gs in sorted(gmap.items()):
            es = ex.get(k, [])
            gq = sum(float(g["quantity"]) for g in gs if g["quantity"] not in ("", None))
            evals = [e["quantity"] for e in es]
            eq = sum(float(v) for v in evals if v is not None)
            gunit, eunit = gs[0]["unit"], (es[0]["unit"] if es else None)
            # unit_match is TRISTATE: True / False / "" (unknown). It is never coerced to a bool,
            # because "we could not read one of the units" is a third answer.
            if not es:
                unit_match = ""
            elif norm_unit(gunit) is None or norm_unit(eunit) is None:
                unit_match = ""
            else:
                unit_match = norm_unit(gunit) == norm_unit(eunit)
            # A NULL extracted quantity is NOT an extracted zero. Scoring them the
            # same would report a 100% variance for every lump-sum item and bury
            # the real numeric errors -- the exact failure/empty conflation this
            # project has hit nine times.
            if not es:
                status = "MISSED_BY_EXTRACTION"
            elif all(v is None for v in evals):
                status = "MATCHED_KEY_NULL_QUANTITY"
                matched += 1
            elif units_disagree(gunit, eunit):
                # Both sides quantified the SAME item in DIFFERENT units. Neither a hit nor a miss:
                # the missing piece is the conversion layer (no CSI-verified factor table exists),
                # not the extraction. No variance -- TON minus SY is not a number.
                status = "CONVERSION_REQUIRED"
                conversion_required += 1
            else:
                status = "MATCH"
                matched += 1
            detail.append(dict(
                plan_id=plan_id, spec_item_number=k, status=status,
                golden_desc=gs[0]["description"][:60], golden_unit=gunit,
                extracted_unit=eunit or "", unit_match=unit_match,
                golden_qty=gq, extracted_qty=eq if es else "",
                abs_variance=abs(gq - eq) if status == "MATCH" else "",
                pct_variance=(abs(gq - eq) / gq * 100) if status == "MATCH" and gq else "",
                csi_bucket=(es[0]["csi_bucket"] if es else ""),
                is_alternate=gs[0]["is_alternate"],
            ))
        for k in sorted(set(ex) - set(gmap)):
            e = ex[k][0]
            detail.append(dict(
                plan_id=plan_id, spec_item_number=k, status="EXTRA_NOT_IN_GOLDEN",
                golden_desc="", golden_unit="", extracted_unit=e["unit"] or "", unit_match="",
                golden_qty="",
                extracted_qty=sum(float(x["quantity"]) for x in ex[k] if x["quantity"] is not None),
                abs_variance="", pct_variance="",
                csi_bucket=e["csi_bucket"] or "", is_alternate=""))

        # CONVERSION_REQUIRED rows leave BOTH denominators (spec 2026-08-10-benchmark-table 5):
        # a known, deliberate design gap must not be reported as an extraction failure, and must
        # not be counted as a success either.
        prec_den = len(ex) - conversion_required
        rec_den = len(gmap) - conversion_required
        prec = matched / prec_den if prec_den > 0 else 0.0
        rec = matched / rec_den if rec_den > 0 else 0.0
        summary.append(dict(project_folder=folder, plan_id=plan_id, status="OK",
                            golden_rows=len(gmap), extracted_rows=len(ex), matched=matched,
                            conversion_required=conversion_required,
                            precision=f"{prec:.3f}", recall=f"{rec:.3f}"))

    out = os.path.join(HERE, "2026-08-10_golden_comparison.csv")
    if detail:
        with open(out, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=list(detail[0].keys()))
            w.writeheader()
            w.writerows(detail)

    print("=== PER-PLAN SUMMARY ===")
    hdr = (f"{'status':22} {'gold':>5} {'extr':>5} {'match':>5} {'conv':>5} "
           f"{'prec':>6} {'recall':>6}  plan")
    print(hdr)
    for s in summary:
        print(f"{s['status']:22} {s['golden_rows']:>5} {s['extracted_rows']:>5} "
              f"{s['matched']:>5} {s.get('conversion_required', 0):>5} "
              f"{s['precision']:>6} {s['recall']:>6}  "
              f"{s['plan_id'] or s['project_folder'][:44]}")
    print("conv = CONVERSION_REQUIRED: same item, both sides quantified, units disagree. "
          "NOT a miss and NOT a hit —\n       it is out of both denominators. A conversion layer "
          "is missing, not an extraction.")

    ok = [s for s in summary if s["status"] == "OK"]
    print(f"\nplans joinable: {len(ok)}/{len(summary)}")
    if ok:
        tc = sum(s.get("conversion_required", 0) for s in ok)
        tg = sum(s["golden_rows"] for s in ok) - tc
        tm = sum(s["matched"] for s in ok)
        te = sum(s["extracted_rows"] for s in ok) - tc
        rec_s = f"{tm/tg:.3f} ({tm}/{tg})" if tg > 0 else "n/a (no scoreable golden rows)"
        prec_s = f"{tm/te:.3f} ({tm}/{te})" if te > 0 else "n/a (no scoreable extracted rows)"
        print(f"pooled  recall={rec_s}  precision={prec_s}"
              f"  conversion_required={tc} (excluded from both)")

    # per-bucket variance
    print("\n=== PER-BUCKET ABSOLUTE VARIANCE (matched items only) ===")
    agg = defaultdict(lambda: [0, 0.0, 0.0])
    for d in detail:
        if d["status"] != "MATCH":
            continue
        b = d["csi_bucket"] or "(unbucketed)"
        agg[b][0] += 1
        agg[b][1] += float(d["golden_qty"] or 0)
        agg[b][2] += float(d["abs_variance"] or 0)
    print(f"{'bucket':18} {'items':>6} {'golden_total':>14} {'abs_variance':>13} {'err%':>7}")
    for b, (n, gt, av) in sorted(agg.items()):
        print(f"{b:18} {n:>6} {gt:>14,.0f} {av:>13,.0f} {(av/gt*100 if gt else 0):>6.2f}%")

    print(f"\nwrote {out}  ({len(detail)} rows)")

    if not detail:
        print("\nCOVERAGE PROBLEM: comparison produced zero rows", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
