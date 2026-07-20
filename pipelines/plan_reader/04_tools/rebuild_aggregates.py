"""
rebuild_aggregates.py — rebuild BOTH aggregates from the per-PDF JSON records, with NO Claude calls.

The per-PDF JSON (00_input/plans/<plan_id>/<plan_id>.json) is the source of truth; 02_outputs/results.csv (wide,
one row per plan) and 02_outputs/flags.csv (long, one row per flagged gotcha/item) are just views of it.
Run this to backfill flags.csv for already-processed plans, or to regenerate both aggregates after you've
added/edited JSONs — without re-paying for extraction.

Run:
    python3 pipelines/plan_reader/04_tools/rebuild_aggregates.py
"""
import sys
import csv
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "01_pipeline"))  # 01_pipeline/ holds lib + schema
import lib
import schema
import taxonomy


def _write(path, columns, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def main():
    jsons = sorted(lib.PLANS_DIR.glob("*/*.json"))
    if not jsons:
        print("No per-PDF JSONs under 00_input/plans/*/. Run `run.py inspect <pdf>` first.")
        return
    col = lib.get_collection()
    outcomes = {}
    if lib.MANIFEST.exists():
        for r in csv.DictReader(open(lib.MANIFEST)):
            outcomes[(r.get("plan_id") or "").strip()] = (r.get("outcome") or "").strip()
    gotcha_family = {c: t["family"] for c, t in taxonomy.GOTCHA_TYPES.items()}

    result_rows, all_flags = [], []
    print(f"Rebuilding from {len(jsons)} per-PDF JSON(s):")
    for jp in jsons:
        rec = json.loads(jp.read_text())
        plan_id = rec.get("plan_id") or jp.stem
        ds = rec.get("document_structure") or {}
        n_chunks = len(col.get(where={"doc_id": plan_id})["ids"])
        meta = {"outcome": outcomes.get(plan_id, ""), "pages": ds.get("n_pages", ""), "n_chunks": n_chunks}
        result_rows.append(schema.flatten_row(rec, meta))
        flags = schema.flag_rows(rec, meta, lib.page_section_map(col, plan_id), gotcha_family)
        all_flags.extend(flags)
        print(f"  {plan_id:44} {len(flags):>3} flags")

    _write(lib.RESULTS_CSV, schema.CSV_COLUMNS, result_rows)
    _write(lib.FLAGS_CSV, schema.FLAG_COLUMNS, all_flags)
    print(f"\n✓ {lib.RESULTS_CSV.name}: {len(result_rows)} plans   ·   "
          f"{lib.FLAGS_CSV.name}: {len(all_flags)} flag rows")


if __name__ == "__main__":
    main()
