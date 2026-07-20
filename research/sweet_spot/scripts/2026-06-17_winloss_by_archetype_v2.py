"""
2026-06-17  Win/loss by archetype, refreshed on the v2 (share-gated) labels.

Recomputes CSI's competitive performance inside each work-type using the canonical win
definition (row-derived: CSI won iff its own bid is rank 1). Compares v1 (old binary rule)
vs v2 so we can see how the cleaner labels move the picture. Writes the sweet-spot table.

Read-only on the master CSV. Output: outputs/2026-06-17_winloss_by_archetype_v2.csv
"""
from pathlib import Path
import pandas as pd
import numpy as np

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
MASTER = REPO / "01_data" / "2026-06-03_csi_bid_master.csv"
OUT = HERE.parent / "outputs" / "2026-06-17_winloss_by_archetype_v2.csv"

MIX_SHARE_MIN, MIX_ABS_MIN, GRADE_MIN_CY, MILL_MIN_SY = 0.15, 1000.0, 500.0, 1000.0
MAT = ["MIX_TN", "GRADE_CY", "BASE_TN", "SHLDR_TN", "MILL_SY", "CRUSH_TN", "STOCK_TN"]
TON_COLS = ["MIX_TN", "BASE_TN", "SHLDR_TN", "CRUSH_TN", "STOCK_TN"]
WIN_WELL = {"Excellent Win", "Acceptable Win"}
ORDER = ["Reconstruct/Rebuild", "Mill & Overlay", "HMA Overlay/Resurface",
         "Grading/Earthwork", "Aggregate/Base/Gravel", "Unknown/NoQty", "Other"]


def to_num(s):
    return pd.to_numeric(s.astype(str).str.replace(",", "", regex=False)
                         .str.replace("$", "", regex=False).str.strip().replace("", np.nan),
                         errors="coerce")


def _val(q, k):
    """numeric value for material k, NaN/missing -> 0.0 (matches the production functions)."""
    v = q.get(k)
    return float(v) if pd.notna(v) else 0.0


def v2(q):
    g = lambda k: _val(q, k)
    if not any(g(k) > 0 for k in MAT):
        return "Unknown/NoQty"
    tt = sum(g(k) for k in TON_COLS)
    ms = (g("MIX_TN") / tt) if tt > 0 else 0.0
    paving = (ms >= MIX_SHARE_MIN) or (g("MIX_TN") >= MIX_ABS_MIN)
    grade, mill = g("GRADE_CY") >= GRADE_MIN_CY, g("MILL_SY") >= MILL_MIN_SY
    if paving:
        if grade: return "Reconstruct/Rebuild"
        if mill:  return "Mill & Overlay"
        return "HMA Overlay/Resurface"
    if grade: return "Grading/Earthwork"
    if g("BASE_TN") > 0 or g("SHLDR_TN") > 0: return "Aggregate/Base/Gravel"
    return "Other"


def v1(q):  # old binary-presence rule, for the before/after comparison
    g = lambda k: _val(q, k) > 0
    if not any(g(k) for k in MAT): return "Unknown/NoQty"
    mix, grade, mill, base, shldr = (g("MIX_TN"), g("GRADE_CY"), g("MILL_SY"), g("BASE_TN"), g("SHLDR_TN"))
    if grade and mix: return "Reconstruct/Rebuild"
    if mix and mill:  return "Mill & Overlay"
    if mix:           return "HMA Overlay/Resurface"
    if grade:         return "Grading/Earthwork"
    if base or shldr: return "Aggregate/Base/Gravel"
    return "Other"


# --- one row per project, with CSI's own outcome ---------------------------------------------------
df = pd.read_csv(MASTER, dtype=str)
for k in MAT:
    df[k] = to_num(df[k])
df["Margin_Pct"] = to_num(df["Margin_Pct"])
proj = df.sort_values("Contract_Id").drop_duplicates("Contract_Id").copy()
proj["v2"] = proj.apply(lambda r: v2({k: r[k] for k in MAT}), axis=1)
proj["v1"] = proj.apply(lambda r: v1({k: r[k] for k in MAT}), axis=1)

# CSI's own row -> outcome
csi = df[df["Is_CSI"] == "TRUE"].copy()
csi["_w"] = (csi["Is_Winner"] == "TRUE").astype(int)
csi = csi.sort_values("_w", ascending=False).drop_duplicates("Contract_Id")
# rename CSI's outcome cols so they don't collide with proj's (project-level) columns
csi = (csi[["Contract_Id", "Is_Winner", "Bid_Quality", "Margin_Pct"]]
       .rename(columns={"Is_Winner": "csi_winner", "Bid_Quality": "csi_quality",
                        "Margin_Pct": "csi_margin"}))
proj = proj.merge(csi, on="Contract_Id", how="left")
proj["is_bid"] = proj["CSI_Participated"] == "TRUE"      # proj's own (project-level) flag
proj["is_win"] = proj["csi_winner"] == "TRUE"
proj["is_win_well"] = proj["csi_quality"].isin(WIN_WELL)
proj["is_bomb"] = proj["csi_quality"] == "Bomb"
proj["csi_margin"] = to_num(proj["csi_margin"])


def summarize(g):
    bid = g[g["is_bid"]]
    wins = bid[bid["is_win"]]
    return pd.Series({
        "n_projects": len(g),
        "bid_rate_%": round(g["is_bid"].mean() * 100, 1),
        "n_bid": len(bid),
        "win_rate_%": round(bid["is_win"].mean() * 100, 1) if len(bid) else np.nan,
        "win_well_rate_%": round(bid["is_win_well"].mean() * 100, 1) if len(bid) else np.nan,
        "bomb_rate_%": round(bid["is_bomb"].mean() * 100, 1) if len(bid) else np.nan,
        "bomb_share_of_wins_%": round(wins["is_bomb"].mean() * 100, 1) if len(wins) else np.nan,
        "median_margin_%": round(bid["csi_margin"].median() * 100, 2) if len(bid) else np.nan,
    })


tbl = proj.groupby("v2").apply(summarize).reindex(ORDER).dropna(how="all")
tbl.to_csv(OUT)
print("=== Win/loss by archetype — v2 (share-gated) labels ===")
print(tbl.to_string())

# before/after on the headline metric (bomb-share-of-wins) for the paving types
print("\n=== v1 -> v2 shift in bomb-share-of-wins (paving types) ===")
for lab in ["Reconstruct/Rebuild", "Mill & Overlay", "HMA Overlay/Resurface"]:
    def bsw(col):
        b = proj[(proj[col] == lab) & proj["is_bid"]]
        w = b[b["is_win"]]
        return round(w["is_bomb"].mean() * 100, 1) if len(w) else np.nan
    print(f"  {lab:24s}  v1={bsw('v1'):>5}%   v2={bsw('v2'):>5}%")
print(f"\nscorecard -> {OUT}")
