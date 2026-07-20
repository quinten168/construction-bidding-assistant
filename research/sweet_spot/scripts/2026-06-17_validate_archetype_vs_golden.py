"""
2026-06-17  Validate the v2 archetype rule against the GOLDEN dataset (read-only).

The golden dataset (02_modules/plan_reader/00_input/golden_dataset.csv) holds the team's
HAND-VERIFIED bid-schedule quantities for 36 plans. It has no archetype label, so we validate
two ways:
  (A) run v2 on the golden hand-quantities and eyeball each label vs the project location;
  (B) for plans that also exist in the master CSV, confirm v2 gives the SAME label from both
      data sources (hand-verified plan quantities vs CSI's historical roll-ups). Agreement =
      the rule is stable across where the numbers come from (which is the whole point of a
      forward-runnable rule).
Writes a side-by-side scorecard for human sign-off.
"""

from pathlib import Path
import pandas as pd
import numpy as np

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
GOLDEN = REPO / "02_modules" / "plan_reader" / "00_input" / "golden_dataset.csv"
MASTER = REPO / "01_data" / "2026-06-03_csi_bid_master.csv"
OUT = HERE.parent / "outputs" / "2026-06-17_archetype_vs_golden.csv"

# --- canonical v2 thresholds (mirror of the 3 synced production functions) -------------------------
MIX_SHARE_MIN, MIX_ABS_MIN, GRADE_MIN_CY, MILL_MIN_SY = 0.15, 1000.0, 500.0, 1000.0
MAT = ["MIX_TN", "GRADE_CY", "BASE_TN", "SHLDR_TN", "MILL_SY", "CRUSH_TN", "STOCK_TN"]
TON_COLS = ["MIX_TN", "BASE_TN", "SHLDR_TN", "CRUSH_TN", "STOCK_TN"]


def to_num(s):
    return pd.to_numeric(s.astype(str).str.replace(",", "", regex=False)
                         .str.replace("$", "", regex=False).str.strip().replace("", np.nan),
                         errors="coerce")


def work_type(q):
    """q: dict {MIX_TN:.., ...} in native units. Same logic as the 3 production functions."""
    g = lambda k: (float(q.get(k)) if pd.notna(q.get(k)) else 0.0)  # NaN/missing -> 0
    if not any(g(k) > 0 for k in MAT):
        return "Unknown/NoQty"
    total_tons = sum(g(k) for k in TON_COLS)
    mix_share = (g("MIX_TN") / total_tons) if total_tons > 0 else 0.0
    paving = (mix_share >= MIX_SHARE_MIN) or (g("MIX_TN") >= MIX_ABS_MIN)
    grade, mill = g("GRADE_CY") >= GRADE_MIN_CY, g("MILL_SY") >= MILL_MIN_SY
    has_agg = (g("BASE_TN") > 0) or (g("SHLDR_TN") > 0)
    if paving:
        if grade: return "Reconstruct/Rebuild"
        if mill:  return "Mill & Overlay"
        return "HMA Overlay/Resurface"
    if grade:   return "Grading/Earthwork"
    if has_agg: return "Aggregate/Base/Gravel"
    return "Other"


# --- (A) label the golden plans from their hand-verified quantities --------------------------------
g = pd.read_csv(GOLDEN, dtype=str)
gcols = {"MIX_TN": "mix_tn", "GRADE_CY": "grade_cy", "BASE_TN": "base_tn", "SHLDR_TN": "shldr_tn",
         "MILL_SY": "mill_sy", "CRUSH_TN": "crush_tn", "STOCK_TN": "stock_tn"}
for k, c in gcols.items():
    g[k] = to_num(g[c])
g["v2_golden"] = g.apply(lambda r: work_type({k: r[k] for k in MAT}), axis=1)
gq = g[g["v2_golden"] != "Unknown/NoQty"].copy()

# --- (B) compare to the master-CSV label for the same contract_id ----------------------------------
m = pd.read_csv(MASTER, dtype=str)
for k in MAT:
    m[k] = to_num(m[k])
m = m.sort_values("Contract_Id").drop_duplicates("Contract_Id")
m["v2_master"] = m.apply(lambda r: work_type({k: r[k] for k in MAT}), axis=1)
mlab = m[["Contract_Id", "v2_master"]].rename(columns={"Contract_Id": "contract_id"})

gq["contract_id"] = gq["contract_id"].astype(str).str.strip()
mlab["contract_id"] = mlab["contract_id"].astype(str).str.strip()
out = gq.merge(mlab, on="contract_id", how="left")

show = out[["contract_id", "project_location"] + MAT + ["v2_golden", "v2_master"]].copy()
matched = show[show["v2_master"].notna()].copy()
matched["agree"] = matched["v2_golden"] == matched["v2_master"]

out.to_csv(OUT, index=False)

print(f"Golden plans with quantities: {len(gq)}   |   matched to master: {len(matched)}")
print("\n=== (A) v2 label from golden hand-quantities (sanity-check vs location) ===")
print(show[["contract_id", "project_location", "MIX_TN", "GRADE_CY", "MILL_SY", "BASE_TN", "v2_golden"]]
      .to_string(index=False))
print("\n=== v2 label distribution on the golden set ===")
print(gq["v2_golden"].value_counts().to_string())

if len(matched):
    print(f"\n=== (B) golden-vs-master agreement: {matched['agree'].mean()*100:.0f}% "
          f"({int(matched['agree'].sum())}/{len(matched)}) ===")
    dis = matched[~matched["agree"]]
    if len(dis):
        print("\n  disagreements (inspect — usually the two sources recorded different quantities):")
        print(dis[["contract_id", "project_location", "MIX_TN", "GRADE_CY", "MILL_SY",
                   "v2_golden", "v2_master"]].to_string(index=False))
    else:
        print("  no disagreements.")
print(f"\nscorecard -> {OUT}")
