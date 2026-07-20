#!/usr/bin/env python3
"""
validate_quantities.py — VALIDATION HARNESS for extracted bid quantities.

Scores what the pipeline extracted (plan_metrics buckets in csi_v2.db) against GROUND TRUTH
(golden_dataset.csv — CSI's review schema). Per field: extracted vs golden, % diff, match within
tolerance. Turns "looks right" into an accuracy number. READ-ONLY. No API.

Run:
    cd 01_Summer_2026
    python3 pipelines/plan_reader/03_evaluation/validate_quantities.py
Writes: 02_outputs/scorecards/<date>_quantity_validation.csv  +  prints a summary.
"""
import re
import csv
import sqlite3
from pathlib import Path

MODULE = Path(__file__).resolve().parent.parent
DB = MODULE / "csi_v2.db"
GOLDEN = MODULE / "00_input" / "golden_dataset.csv"
OUT = MODULE / "02_outputs" / "scorecards" / "2026-06-17_quantity_validation.csv"
TOL = 0.08   # within 8% counts as a match

# bucket (extracted)  ->  golden column
FIELD_MAP = {
    "hot_mix_tons": "mix_tn", "grading_quantity": "grade_cy", "base_tons": "base_tn",
    "shoulder_tons": "shldr_tn", "milling_sy": "mill_sy", "crushing_tons": "crush_tn",
    "stockpile_tons": "stock_tn",
}


def num(s):
    s = re.sub(r"[^\d.]", "", str(s or "").replace(",", ""))
    try:
        return float(s) if s not in ("", ".") else None
    except ValueError:
        return None


def basekey(s):
    """normalize a filename/id for fuzzy matching"""
    return re.sub(r"[^a-z0-9]", "", Path(str(s or "")).stem.lower())


def main():
    conn = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    plans = conn.execute(
        "SELECT p.plan_id, p.source_pdf_path, m.has_quantity, "
        + ", ".join(f"m.{b}" for b in FIELD_MAP)
        + " FROM plans p LEFT JOIN plan_metrics m ON m.plan_id=p.plan_id").fetchall()
    conn.close()

    # index corpus plans by a normalized key from their PDF filename
    by_key = {}
    extracted = {}
    for row in plans:
        pid, pdf = row[0], row[1]
        extracted[pid] = dict(zip(FIELD_MAP, row[3:]))
        extracted[pid]["_has_q"] = row[2]
        if pdf:
            by_key[basekey(Path(pdf).name)] = pid
        by_key.setdefault(basekey(pid), pid)   # also match on plan_id

    golden = list(csv.DictReader(open(GOLDEN)))
    rows, matched = [], 0
    per_field = {b: {"n": 0, "hit": 0, "miss": 0} for b in FIELD_MAP}
    for g in golden:
        src = g.get("source_file") or ""
        if not src:
            continue
        pid = by_key.get(basekey(src)) or by_key.get(basekey(g.get("sp_number")))
        if not pid:
            continue
        matched += 1
        for bucket, gcol in FIELD_MAP.items():
            gv, ev = num(g.get(gcol)), num(extracted[pid].get(bucket))
            if gv is None:                      # no ground truth for this field on this plan
                continue
            per_field[bucket]["n"] += 1
            if ev is None or ev == 0:
                per_field[bucket]["miss"] += 1
                verdict = "MISS (extracted empty)"
                dpct = ""
            else:
                d = (ev - gv) / gv * 100 if gv else 0
                dpct = round(d, 1)
                if abs(d) <= TOL * 100:
                    per_field[bucket]["hit"] += 1; verdict = "match"
                else:
                    per_field[bucket]["miss"] += 1; verdict = "OFF"
            rows.append({"plan_id": pid, "field": bucket, "golden": gv, "extracted": ev,
                         "pct_diff": dpct, "verdict": verdict})

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["plan_id", "field", "golden", "extracted", "pct_diff", "verdict"])
        w.writeheader(); w.writerows(rows)

    # --- summary ---
    print(f"Golden rows with a source_file: {sum(1 for g in golden if g.get('source_file'))}  |  "
          f"matched to a corpus plan: {matched}")
    print(f"\n{'field':18s} {'compared':>8s} {'match':>6s} {'miss/off':>9s} {'accuracy':>9s}")
    print("-" * 56)
    tot_n = tot_hit = 0
    for b, s in per_field.items():
        acc = f"{100*s['hit']/s['n']:.0f}%" if s["n"] else "—"
        print(f"{b:18s} {s['n']:>8d} {s['hit']:>6d} {s['miss']:>9d} {acc:>9s}")
        tot_n += s["n"]; tot_hit += s["hit"]
    print("-" * 56)
    print(f"{'OVERALL':18s} {tot_n:>8d} {tot_hit:>6d} {tot_n-tot_hit:>9d} "
          f"{(f'{100*tot_hit/tot_n:.0f}%' if tot_n else '—'):>9s}")
    print(f"\nscorecard -> {OUT}")
    print("NOTE: validates only the plans with golden ground truth (small set). The accuracy number grows")
    print("as ground truth grows; expand later with CSI_data_2024/25 hand-keyed quantities (harder join).")


if __name__ == "__main__":
    main()
