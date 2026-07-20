#!/usr/bin/env python3
"""
10_remap_buckets.py  —  re-map stored bid-schedule line items through the crosswalk (NO API calls).

WHY this tool exists: every line item the pipeline ever extracted is already stored in the `materials`
table with its raw_description + unit + quantity. The description -> csi_bucket mapping, however, is
computed at write time and frozen into materials.csi_bucket. So when the crosswalk
(05_knowledge/quantity_crosswalk.py) grows a new keyword, the OLD rows keep their stale bucket and the
plan_metrics rollup stays wrong — even though no re-extraction is needed.

This tool closes that loop deterministically: for every plan it re-runs xwalk.map_line over the stored
materials rows, rewrites materials.csi_bucket / spec_category, and rebuilds the 7 plan_metrics quantity
buckets (+ has_quantity, bid_item_count, n_spec_categories, has_structures_work) from the re-mapped
rows. parse_method, extraction_cost, box_culvert, prevailing_wages, and all Phase-1.5/2 columns
(work_type, size_*, gotcha_*, messiness_score) are LEFT UNTOUCHED.

This mirrors the bucket math in 05_parse_bid_schedule.rollup_metrics — it is the same GROUP BY
csi_bucket sum, just driven off already-stored rows instead of a fresh parse.

Idempotent + API-free: safe to re-run any time the crosswalk changes. Run from inside 01_Summer_2026:
    python3 pipelines/plan_reader/04_tools/10_remap_buckets.py            # all plans
    python3 pipelines/plan_reader/04_tools/10_remap_buckets.py --dry-run  # report deltas, write nothing
"""
import sys
import sqlite3
from pathlib import Path

# --- paths + the single canonical crosswalk ----------------------------------
TOOLS_DIR     = Path(__file__).resolve().parent
MODULE_ROOT   = TOOLS_DIR.parent                       # .../plan_reader
KNOWLEDGE_DIR = MODULE_ROOT / "05_knowledge"
DB_PATH       = MODULE_ROOT / "csi_v2.db"
sys.path.insert(0, str(KNOWLEDGE_DIR))
import quantity_crosswalk as xwalk                      # noqa: E402  — the source of truth for the mapping

# The plan_metrics columns this tool rebuilds from the re-mapped materials rows. Everything else in
# plan_metrics (parse_method, extraction_cost, box_culvert, prevailing_wages, work_type, size_*,
# gotcha_*, messiness_score, ...) is deliberately preserved.
REBUILT_COLS = xwalk.CSI_BUCKETS + [
    "has_quantity", "bid_item_count", "n_spec_categories", "has_structures_work",
]


# --- rebuild one plan's buckets from its stored materials rows ----------------
def rebuild_plan(rows):
    """Given a plan's materials rows [(raw_description, unit, quantity), ...], re-map each line and roll
    the lines up into the bucket columns. Returns (metrics_dict, remapped_rows) where remapped_rows is
    [(csi_bucket, spec_category, raw_description, unit), ...] for writing back into materials."""
    buckets = {b: 0.0 for b in xwalk.CSI_BUCKETS}
    cats, remapped = set(), []
    for desc, unit, qty in rows:
        # Re-run the crosswalk on the already-extracted line (this is where the new keywords take effect).
        bucket, cat = xwalk.map_line(desc, unit)
        remapped.append((bucket, cat, desc, unit))
        cats.add(cat)
        # A line counts toward a bucket only when it both maps to one AND carries a numeric quantity
        # (lump-sum / null-quantity lines have qty None) — identical guard to rollup_metrics.
        if bucket and qty is not None:
            buckets[bucket] += qty
    cats.discard("other")                                # 'other' isn't a real spec category
    bucket_vals = {b: (round(v, 2) if v else None) for b, v in buckets.items()}
    metrics = {
        **bucket_vals,
        "has_quantity": 1 if any(v for v in bucket_vals.values()) else 0,
        "bid_item_count": len(rows),
        "n_spec_categories": len(cats),
        "has_structures_work": 1 if "structures" in cats else 0,
    }
    return metrics, remapped


# --- main --------------------------------------------------------------------
def main():
    dry = "--dry-run" in sys.argv
    conn = sqlite3.connect(DB_PATH)

    # Every plan that has a plan_metrics row (so we touch fallback + deterministic plans alike).
    plan_ids = [r[0] for r in conn.execute("SELECT plan_id FROM plan_metrics ORDER BY plan_id")]

    flipped, changed_grading, n_touched = [], 0, 0
    for plan_id in plan_ids:
        mats = conn.execute(
            "SELECT raw_description, unit, quantity FROM materials WHERE plan_id=?", (plan_id,)
        ).fetchall()
        if not mats:
            continue
        before = conn.execute(
            "SELECT has_quantity, grading_quantity FROM plan_metrics WHERE plan_id=?", (plan_id,)
        ).fetchone()
        metrics, remapped = rebuild_plan(mats)

        # Track the headline movements for the report.
        if (before[0] or 0) == 0 and metrics["has_quantity"] == 1:
            flipped.append(plan_id)
        if (before[1] or 0) != (metrics["grading_quantity"] or 0):
            changed_grading += 1

        if dry:
            continue

        # 1) rewrite materials.csi_bucket / spec_category in place (preserve quantity/page/etc.).
        for bucket, cat, desc, unit in remapped:
            conn.execute(
                "UPDATE materials SET csi_bucket=?, spec_category=? "
                "WHERE plan_id=? AND raw_description=? AND COALESCE(unit,'')=COALESCE(?, '')",
                (bucket, cat, plan_id, desc, unit),
            )
        # 2) rebuild ONLY the bucket-derived plan_metrics columns (everything else preserved).
        sets = ", ".join(f"{c}=?" for c in REBUILT_COLS)
        conn.execute(
            f"UPDATE plan_metrics SET {sets} WHERE plan_id=?",
            [metrics[c] for c in REBUILT_COLS] + [plan_id],
        )
        n_touched += 1

    if not dry:
        conn.commit()

    # --- report ---
    total_q = conn.execute("SELECT COUNT(*) FROM plan_metrics WHERE has_quantity=1").fetchone()[0]
    print(f"{'DRY-RUN — ' if dry else ''}re-mapped {n_touched or len(plan_ids)} plans")
    print(f"  plans now has_quantity=1:        {total_q} / {len(plan_ids)}")
    print(f"  plans flipped 0 -> has_quantity: {len(flipped)}")
    print(f"  plans with a grading_quantity change: {changed_grading}")
    for p in flipped:
        print(f"    + {p}")
    conn.close()


if __name__ == "__main__":
    main()
