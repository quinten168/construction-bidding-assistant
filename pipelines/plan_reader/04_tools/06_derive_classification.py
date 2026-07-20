#!/usr/bin/env python3
"""
06_derive_classification.py  —  PHASE 1.5: deterministic project-type classification.

Derives three plan-knowable axes from the Phase 1 bucket quantities — NO LLM, NO post-auction data:
  • Axis 1  work_type   — the canonical rule (synced verbatim across dashboard + sweet_spot).
  • Axis 3  size_*      — size_basis / size_value / size_tier / pctile_within_type, per-type cuts.
  • Axis 2  messiness   — the INPUT columns only (n_spec_categories, bid_item_count,
                          has_structures_work already exist from Phase 1; contract_duration_days
                          if dates are present). The 1-10 messiness_score is DEFERRED (stays NULL).

The script does TWO clearly separate things:
  1. BACK-TEST (validation gate) — re-derive work_type + size_tier over the 1,591 historical projects
     in sweet_spot's project_base.csv and prove the rule reproduces the known distribution
     (Reconstruct 615 · Mill & Overlay 321 · Grading 212 · HMA Overlay 109 · Aggregate/Base 84 ·
     Other 35 · Unknown 215). Read-only; uses the post-auction $ ONLY to sanity-check correlation.
  2. LIVE DERIVATION (the deliverable) — classify the plans in csi_v2.db and write the columns.

LEAKAGE (HR10): the derivation reads quantities ONLY. outcome / Project_Size_Dollars / Winner_Amount /
CSI_Margin_Pct / CSI_Won never enter a derivation — they appear solely in the back-test comparison block.

Run:
    cd 01_Summer_2026
    python3 pipelines/plan_reader/04_tools/06_derive_classification.py              # back-test + live
    python3 pipelines/plan_reader/04_tools/06_derive_classification.py --backtest-only
"""
import sys
import sqlite3
from pathlib import Path

import pandas as pd

TOOLS_DIR   = Path(__file__).resolve().parent
MODULE_ROOT = TOOLS_DIR.parent                                  # .../plan_reader
REPO_ROOT   = MODULE_ROOT.parents[1]                            # .../01_Summer_2026
DB_PATH     = MODULE_ROOT / "csi_v2.db"
BASE_CSV    = REPO_ROOT / "research" / "sweet_spot" / "outputs" / "2026-06-04_project_base.csv"

# --- the canonical work_type rule (DO NOT alter — synced with dashboard + sweet_spot) ---------------
def work_type(mix, grade, mill, base, shldr, has_quantity):   # bools = "bucket quantity > 0"
    if not has_quantity:  return "Unknown/NoQty"
    if grade and mix:     return "Reconstruct/Rebuild"
    if mix and mill:      return "Mill & Overlay"
    if mix:               return "HMA Overlay/Resurface"
    if grade:             return "Grading/Earthwork"
    if base or shldr:     return "Aggregate/Base/Gravel"
    return "Other"


# --- Axis 3 size cuts (from 2026-06-15_worktype_size_thresholds.csv) --------------------------------
# basis fields use the readable bucket names; "Large" iff size_value >= large_cut. Types not listed
# (Other / Unknown/NoQty) get NO size tier (size_value/size_tier stay NULL).
SIZE_RULES = {
    "Reconstruct/Rebuild":   (["hot_mix_tons", "base_tons", "shoulder_tons"], 7187),
    "Mill & Overlay":        (["hot_mix_tons"],                               2776),
    "HMA Overlay/Resurface": (["hot_mix_tons"],                               1562),
    "Grading/Earthwork":     (["grading_quantity"],                          4342),
    "Aggregate/Base/Gravel": (["base_tons", "shoulder_tons"],                2596),
}
# HARD RULE (HR): crushing_tons + stockpile_tons are production inputs that double-count base/mix — they
# must NEVER appear in a size_value basis. Enforced in code so a future edit can't silently break it.
FORBIDDEN_IN_SIZE = {"crushing_tons", "stockpile_tons"}
for _wt, (_basis, _cut) in SIZE_RULES.items():
    assert not (set(_basis) & FORBIDDEN_IN_SIZE), f"CRUSH/STOCK leaked into size basis for {_wt}"

# Readable bucket name -> the historical _num column (back-test only; live uses the readable names).
BUCKET_TO_NUM = {
    "hot_mix_tons": "MIX_TN_num", "base_tons": "BASE_TN_num", "grading_quantity": "GRADE_CY_num",
    "shoulder_tons": "SHLDR_TN_num", "milling_sy": "MILL_SY_num",
}

# The distribution the back-test must reproduce (from the thresholds CSV + the archetype script).
EXPECTED_DISTRIBUTION = {
    "Reconstruct/Rebuild": 615, "Mill & Overlay": 321, "Grading/Earthwork": 212,
    "HMA Overlay/Resurface": 109, "Aggregate/Base/Gravel": 84, "Other": 35, "Unknown/NoQty": 215,
}


def size_for(wt, buckets):
    """Given a work_type and a dict of readable bucket -> quantity (None treated as 0), return
    (size_basis, size_value, size_tier). Types without a size rule return (None, None, None)."""
    rule = SIZE_RULES.get(wt)
    if rule is None:
        return None, None, None
    basis_fields, cut = rule
    size_value = sum((buckets.get(f) or 0) for f in basis_fields)
    tier = "Large" if size_value >= cut else "Small"
    basis_label = "+".join(basis_fields)
    return basis_label, round(size_value, 2), tier


# --- (1) BACK-TEST — validation gate over the historical 1,591 projects ------------------------------
def run_backtest():
    """Re-derive work_type + size over project_base.csv and check it reproduces the known distribution.
    Returns True if the distribution matches EXACTLY. Read-only; the post-auction $ is used ONLY for the
    correlation sanity check, never as a derivation input."""
    df = pd.read_csv(BASE_CSV)
    print(f"\n=== BACK-TEST (validation) — {len(df):,} historical projects from project_base.csv ===")

    def derive_wt(r):
        # has_quantity is the precomputed plan-knowable gate (same column the archetype script uses).
        g = lambda col: (r[col] if pd.notna(r[col]) else 0) > 0
        return work_type(g("MIX_TN_num"), g("GRADE_CY_num"), g("MILL_SY_num"),
                         g("BASE_TN_num"), g("SHLDR_TN_num"), bool(r["has_quantity"]))

    df["wt"] = df.apply(derive_wt, axis=1)
    actual = df["wt"].value_counts().to_dict()

    # Distribution: actual vs expected, per type.
    print(f"\n  {'work_type':24s} {'actual':>7} {'expected':>9} {'diff':>6}")
    all_match = True
    for wt, exp in EXPECTED_DISTRIBUTION.items():
        act = actual.get(wt, 0)
        diff = act - exp
        if diff != 0:
            all_match = False
        print(f"  {wt:24s} {act:>7} {exp:>9} {diff:>+6}")
    extra = set(actual) - set(EXPECTED_DISTRIBUTION)
    for wt in extra:
        all_match = False
        print(f"  {wt:24s} {actual[wt]:>7} {'(unexpected)':>9}")

    # If any type is off, list the specific projects that classified unexpectedly (NULL-vs-0 / boundary
    # edges usually explain a 1-2 count drift) — per the instruction, REPORT, don't adjust the rule.
    if not all_match:
        print("\n  !! Distribution mismatch — investigating boundary/NULL edges (NOT adjusting the rule):")
        _report_backtest_edges(df)

    # size_value rank-correlation with Project_Size_Dollars per type (sanity ONLY — $ never fed in).
    print("\n  size_value vs Project_Size_Dollars — Spearman ρ per type (expect ~0.4–0.66):")
    for wt in SIZE_RULES:
        sub = df[df["wt"] == wt].copy()
        basis_num = [BUCKET_TO_NUM[f] for f in SIZE_RULES[wt][0]]
        sub["size_value"] = sub[basis_num].fillna(0).sum(axis=1)
        sub = sub[sub["Project_Size_Dollars"].notna() & (sub["size_value"] > 0)]
        rho = sub["size_value"].corr(sub["Project_Size_Dollars"], method="spearman") if len(sub) > 2 else None
        flag = "" if rho is None else ("ok" if 0.30 <= rho <= 0.75 else "outside ~0.4-0.66")
        print(f"    {wt:24s} n={len(sub):>4}  ρ={rho if rho is None else round(rho,3)}  {flag}")

    print(f"\n  BACK-TEST: {'PASS — distribution reproduced exactly' if all_match else 'FAIL — see mismatch above'}")
    return all_match


def _report_backtest_edges(df):
    """List projects whose classification sits on a boundary likely to explain a small count drift:
    has_quantity True but every work-type bucket is 0/NULL (→ 'Other'), or has_quantity disagrees with
    'any bucket > 0'. These are NULL-vs-zero / boundary cases, not rule errors."""
    wt_buckets = ["MIX_TN_num", "GRADE_CY_num", "MILL_SY_num", "BASE_TN_num", "SHLDR_TN_num"]
    any_bucket = (df[wt_buckets].fillna(0) > 0).any(axis=1)
    # has_quantity says yes but no work-type bucket is positive → lands in 'Other'.
    edge = df[df["has_quantity"].astype(bool) & ~any_bucket]
    print(f"     has_quantity=True but all 5 work-type buckets 0/NULL: {len(edge)} "
          f"(these classify 'Other'; often CRUSH/STOCK-only rows)")
    for _, r in edge.head(10).iterrows():
        print(f"       {r['Contract_Id']}  CRUSH={r.get('CRUSH_TN_num')}  STOCK={r.get('STOCK_TN_num')}")
    # has_quantity disagrees with 'any of the 7 materials > 0' (a NULL-vs-zero source).
    mat7 = wt_buckets + ["CRUSH_TN_num", "STOCK_TN_num"]
    any7 = (df[mat7].fillna(0) > 0).any(axis=1)
    disagree = df[df["has_quantity"].astype(bool) != any7]
    print(f"     has_quantity != (any of 7 materials > 0): {len(disagree)} rows (NULL-vs-zero edge)")


# --- (2) LIVE DERIVATION — the Phase 1.5 deliverable over csi_v2.db ----------------------------------
LIVE_BUCKETS = ["hot_mix_tons", "base_tons", "grading_quantity", "shoulder_tons",
                "milling_sy", "crushing_tons", "stockpile_tons"]


def run_live():
    """Classify every plan in plan_metrics and write work_type (to plans.archetype + plan_metrics),
    size_* and pctile_within_type. Idempotent (plain UPDATEs). messiness_score stays NULL."""
    conn = sqlite3.connect(DB_PATH)
    cols = ", ".join(LIVE_BUCKETS)
    rows = conn.execute(f"SELECT plan_id, has_quantity, {cols} FROM plan_metrics").fetchall()
    print(f"\n=== LIVE DERIVATION (deliverable) — {len(rows)} plans in csi_v2.db ===")

    # First pass: derive work_type + size_value for each plan (so we can rank percentiles within type).
    derived = []
    for r in rows:
        plan_id, has_q = r[0], r[1]
        buckets = dict(zip(LIVE_BUCKETS, r[2:]))
        g = lambda b: (buckets.get(b) or 0) > 0
        wt = work_type(g("hot_mix_tons"), g("grading_quantity"), g("milling_sy"),
                       g("base_tons"), g("shoulder_tons"), bool(has_q))
        basis, size_value, tier = size_for(wt, buckets)
        derived.append({"plan_id": plan_id, "work_type": wt, "size_basis": basis,
                        "size_value": size_value, "size_tier": tier})

    # Second pass: pctile_within_type = rank of size_value within its work_type across the live corpus.
    by_type = {}
    for d in derived:
        if d["size_value"] is not None:
            by_type.setdefault(d["work_type"], []).append(d["size_value"])
    for d in derived:
        sv = d["size_value"]
        if sv is None:
            d["pctile_within_type"] = None
        else:
            peers = sorted(by_type[d["work_type"]])
            # fraction of peers at or below this value (1.0 = largest of its type)
            d["pctile_within_type"] = round(sum(1 for v in peers if v <= sv) / len(peers), 3)

    # Write back: plans.archetype + the plan_metrics classification columns (idempotent UPDATEs).
    for d in derived:
        conn.execute("UPDATE plans SET archetype=? WHERE plan_id=?", (d["work_type"], d["plan_id"]))
        conn.execute(
            "UPDATE plan_metrics SET work_type=?, size_basis=?, size_value=?, size_tier=?, "
            "pctile_within_type=? WHERE plan_id=?",
            (d["work_type"], d["size_basis"], d["size_value"], d["size_tier"],
             d["pctile_within_type"], d["plan_id"]),
        )
    conn.commit()

    # Show the result (and note the caveat: a fallback plan with empty buckets lands in Unknown/NoQty).
    print(f"  {'plan_id':42s} {'work_type':22s} {'size_tier':9s} size_value")
    for d in sorted(derived, key=lambda x: x["plan_id"]):
        sv = "" if d["size_value"] is None else f"{d['size_value']:,.0f}"
        print(f"  {d['plan_id']:42s} {d['work_type']:22s} {str(d['size_tier'] or ''):9s} {sv}")

    print("\n  Live work_type distribution:")
    dist = {}
    for d in derived:
        dist[d["work_type"]] = dist.get(d["work_type"], 0) + 1
    for wt, n in sorted(dist.items(), key=lambda x: -x[1]):
        print(f"    {wt:24s} {n}")

    # Confirm Phase 1.5 didn't touch the deferred columns.
    leaked = conn.execute("SELECT COUNT(*) FROM plan_metrics WHERE messiness_score IS NOT NULL "
                          "OR has_phasing IS NOT NULL").fetchone()[0]
    print(f"\n  Deferred columns still NULL (messiness_score + has_phasing): "
          f"{'PASS' if leaked == 0 else f'FAIL ({leaked} set)'}")
    conn.close()


def main():
    ok = run_backtest()
    if "--backtest-only" not in sys.argv:
        if not ok:
            print("\n>>> Back-test did NOT reproduce the distribution — STOPPING before live derivation. "
                  "Investigate the mismatch above; do NOT adjust the canonical rule. <<<")
            return
        run_live()


if __name__ == "__main__":
    main()
