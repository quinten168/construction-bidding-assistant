"""
CSI Sweet-Spot — Size WITHIN each work-type archetype (the two-axis model)
==========================================================================
Replaces the flawed single "Large Volume = MIX>10k" archetype with CSI's own
mental model (from the kickoff transcripts):

  Axis 1  WORK-TYPE archetype  — what kind of job, from which scopes are present
  Axis 2  MESSINESS            — clean<->messy (proxy here; real score is post-RAG)
  Axis 3  SIZE                 — large/small derived *within* each archetype, in
                                 that archetype's native unit (no cross-unit sums)
  Target  PROFIT               — margin by archetype x size = the "sweet spot"

Why per-archetype size: MIX/GRADE/BASE are INDEPENDENT, non-overlapping size
drivers (VIF~1.2, MIX-GRADE corr ~ -0.01) and which one matters depends on the
job type, so no single pooled measure works. Each archetype is sized by its
dominant native quantity. Project_Size_Dollars is NOT used as an input (it's the
post-auction winning bid = leakage / HR10); it's available only for back-test.

Plan-knowable inputs only (the 7 quantities + BOX), so the same logic runs on a
NEW plan via the Plan Reader extraction. Reads derived CSVs; never raw data (HR1).

Input : outputs/2026-06-04_project_base.csv  (+ project_archetypes.csv for ref)
Output: outputs/2026-06-15_worktype_size_thresholds.csv  (per-archetype size cuts)
        outputs/2026-06-15_archetype_size_profit.csv      (the sweet-spot table)
        outputs/2026-06-15_projects_classified.csv         (1 row/project: type+size)

Run:  /usr/bin/python3 02_modules/sweet_spot/scripts/2026-06-15_size_within_archetype.py
"""
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.mixture import GaussianMixture

OUT = Path(__file__).resolve().parent.parent / "outputs"
BASE = OUT / "2026-06-04_project_base.csv"
WIN_WELL = {"Excellent Win", "Acceptable Win"}
SEED = 42

# ── Axis 1: work-type archetype from which scopes are present (plan-knowable) ──
# Distinguishable from the 7 roll-up quantities TODAY. Reclaim/Stabilization and a
# clean Mill&Overlay-vs-HMA-Resurface split need bid-schedule SPEC codes (Plan Reader).
# CANONICAL (v2, share-gated; 2026-06-17) — KEEP IN SYNC with dashboard/utils/data.py:
# _rule_archetype and 2026-06-04_02_archetypes.py:rule_archetype.
# See 2026-06-15_project_type_definitions.md. v2 gates each trigger by magnitude so a
# TOKEN of a material can't flip the label.
MIX_SHARE_MIN = 0.15      # mix is "real paving" at >=15% of tonnage ...
MIX_ABS_MIN = 1000.0      # ... OR >=1000 t absolute (big-mix jobs that also carry more aggregate)
GRADE_MIN_CY = 500.0      # real regrade, not approach/driveway grading
MILL_MIN_SY = 1000.0      # real milling, not edge mills
TON_COLS = ["MIX_TN", "BASE_TN", "SHLDR_TN", "CRUSH_TN", "STOCK_TN"]   # the summable family


def work_type(r):
    """Layer 1: is it genuinely a paving job? (mix is a real SHARE or a real ABSOLUTE amount)
    Layer 2: route by GRADE / MILL presence (each gated so token amounts don't count)."""
    if not r["has_quantity"]:    return "Unknown/NoQty"
    q = lambda k: (float(r[k + "_num"]) if (k + "_num" in r and pd.notna(r[k + "_num"])) else 0.0)
    total_tons = sum(q(k) for k in TON_COLS)
    mix_share = (q("MIX_TN") / total_tons) if total_tons > 0 else 0.0
    paving = (mix_share >= MIX_SHARE_MIN) or (q("MIX_TN") >= MIX_ABS_MIN)
    grade, mill = q("GRADE_CY") >= GRADE_MIN_CY, q("MILL_SY") >= MILL_MIN_SY
    has_agg = (q("BASE_TN") > 0) or (q("SHLDR_TN") > 0)
    if paving:
        if grade:   return "Reconstruct/Rebuild"     # real regrade + real paving
        if mill:    return "Mill & Overlay"          # real milling, no regrade (avoid)
        return "HMA Overlay/Resurface"               # pave over, no mill, no regrade
    if grade:       return "Grading/Earthwork"       # dirt, no real paving
    if has_agg:     return "Aggregate/Base/Gravel"   # base/gravel, no paving
    return "Other"


# Each work-type's SIZE is measured on its dominant native quantity (no unit-mixing).
SIZE_BASIS = {
    "Reconstruct/Rebuild":    ("placed_tons", "placed tons (MIX+BASE+SHLDR)"),
    "Mill & Overlay":         ("MIX_TN_num",  "MIX tons"),
    "HMA Overlay/Resurface":  ("MIX_TN_num",  "MIX tons"),
    "Grading/Earthwork":      ("GRADE_CY_num", "GRADE cubic yards"),
    "Aggregate/Base/Gravel":  ("base_shldr",  "BASE+SHLDR tons"),
}


def size_cut(values):
    """Derive the small/large split for one archetype from its (log) size distribution.
    GMM(2) crossover if BIC supports two modes, else the median. Returns (cut, method)."""
    v = np.asarray(values, float)
    v = v[v > 0]
    if len(v) < 30:
        return float(np.median(v)) if len(v) else np.nan, "median (n<30)"
    x = np.log10(v).reshape(-1, 1)
    g1 = GaussianMixture(1, random_state=SEED).fit(x)
    g2 = GaussianMixture(2, random_state=SEED, n_init=5).fit(x)
    lo, hi_p = np.percentile(v, [10, 90])
    if g2.bic(x) < g1.bic(x):
        grid = np.linspace(x.min(), x.max(), 4000).reshape(-1, 1)
        hi = int(np.argmax(g2.means_.ravel()))
        sw = np.where(g2.predict(grid) == hi)[0]
        if len(sw):
            cut = float(10 ** grid[sw[0], 0])
            # guard against degenerate splits: a real small/large seam sits inside
            # the bulk of the data, not at the extreme tail.
            if lo <= cut <= hi_p:
                return cut, "GMM(2) crossover"
    return float(np.median(v)), "median (no clean 2-mode seam)"


def main():
    df = pd.read_csv(BASE)
    for c in ["MIX_TN_num", "GRADE_CY_num", "BASE_TN_num", "SHLDR_TN_num",
              "MILL_SY_num", "Project_Size_Dollars", "CSI_Margin_Pct", "Num_Valid_Bidders"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df["placed_tons"] = df[["MIX_TN_num", "BASE_TN_num", "SHLDR_TN_num"]].fillna(0).sum(axis=1)
    df["base_shldr"] = df[["BASE_TN_num", "SHLDR_TN_num"]].fillna(0).sum(axis=1)
    df["work_type"] = df.apply(work_type, axis=1)
    df["is_bid"] = df["CSI_Participated"].astype(str).str.upper() == "TRUE"
    df["is_win"] = df["CSI_Won"].astype(str).str.upper() == "TRUE"
    df["is_win_well"] = df["CSI_Bid_Quality"].isin(WIN_WELL)
    df["is_bomb"] = df["CSI_Bid_Quality"] == "Bomb"

    print("=" * 74)
    print("Work-type archetype x per-archetype SIZE (CSI two-axis model)")
    print("=" * 74)
    print("\n-- Axis 1: work-type distribution (quantity-complete) --")
    print(df.loc[df["has_quantity"] == True, "work_type"].value_counts().to_string())

    # ── per-archetype size thresholds (Axis 3) ────────────────────────────────
    print("\n-- Axis 3: size cut derived WITHIN each archetype (native unit) --")
    rows, df["size_tier"], df["size_value"] = [], pd.NA, np.nan
    for wt, (basis, label) in SIZE_BASIS.items():
        sub = df[df["work_type"] == wt]
        vals = sub[basis]
        cut, method = size_cut(vals)
        rows.append(dict(work_type=wt, size_basis=label, n=len(sub),
                         large_cut=round(cut) if pd.notna(cut) else np.nan,
                         method=method,
                         median=round(float(vals[vals > 0].median())) if (vals > 0).any() else np.nan))
        m = df["work_type"] == wt
        df.loc[m, "size_value"] = df.loc[m, basis]
        df.loc[m, "size_tier"] = np.where(df.loc[m, basis] >= cut, "Large", "Small")
        print(f"  {wt:24s} {label:28s} n={len(sub):4d}  Large >= {cut:>10,.0f}  [{method}]")
    thresh = pd.DataFrame(rows)
    thresh.to_csv(OUT / "2026-06-15_worktype_size_thresholds.csv", index=False)

    # back-test sanity: does the within-archetype size rank-track realized $ ?
    print("\n-- Back-test (NOT an input): size_value vs Project_Size_Dollars (Spearman) --")
    for wt in SIZE_BASIS:
        s = df[(df["work_type"] == wt) & (df["Project_Size_Dollars"] > 0) & (df["size_value"] > 0)]
        if len(s) > 10:
            print(f"  {wt:24s} rho={s['size_value'].corr(s['Project_Size_Dollars'], method='spearman'):+.2f}  (n={len(s)})")

    # ── Axis 1 x Axis 3 x PROFIT — the sweet-spot table ───────────────────────
    print("\n-- Sweet spot: bid/win/profit by work-type x size (CSI bids only) --")
    bid = df[df["is_bid"] & df["work_type"].isin(SIZE_BASIS)].copy()
    g = bid.groupby(["work_type", "size_tier"], observed=True).agg(
        n_bid=("Contract_Id", "size"),
        win_rate=("is_win", lambda s: round(s.mean() * 100, 1)),
        win_well_rate=("is_win_well", lambda s: round(s.mean() * 100, 1)),
        bomb_rate=("is_bomb", lambda s: round(s.mean() * 100, 1)),
        med_margin=("CSI_Margin_Pct", lambda s: round(s.median(), 3)),
        med_bidders=("Num_Valid_Bidders", lambda s: round(s.median(), 1)),
    ).reset_index()
    # add bid_rate (needs the field denominator = all projects of that type+size)
    field = df[df["work_type"].isin(SIZE_BASIS)].groupby(
        ["work_type", "size_tier"], observed=True)["Contract_Id"].size().rename("n_field").reset_index()
    g = g.merge(field, on=["work_type", "size_tier"], how="left")
    g["bid_rate"] = (g["n_bid"] / g["n_field"] * 100).round(1)
    g = g[["work_type", "size_tier", "n_field", "n_bid", "bid_rate", "win_rate",
           "win_well_rate", "bomb_rate", "med_margin", "med_bidders"]]
    g.to_csv(OUT / "2026-06-15_archetype_size_profit.csv", index=False)
    print(g.to_string(index=False))

    # ── per-project classification (the forward-applicable record) ────────────
    df["pctile_within_type"] = np.nan
    for wt in SIZE_BASIS:
        m = (df["work_type"] == wt) & (df["size_value"] > 0)
        if m.any():
            df.loc[m, "pctile_within_type"] = df.loc[m, "size_value"].rank(pct=True) * 100
    out = df[["Contract_Id", "State", "work_type", "size_basis_col" if False else "size_value",
              "size_tier", "pctile_within_type", "n_mat_types", "BOX",
              "is_bid", "is_win", "CSI_Margin_Pct"]].copy()
    out["messiness_proxy"] = df["n_mat_types"] + df["BOX"].astype(str).str.upper().isin(["TRUE", "X"]).astype(int) * 2
    out.to_csv(OUT / "2026-06-15_projects_classified.csv", index=False)

    # ── forward demo: classify a hypothetical NEW plan from plan-knowable qty ──
    print("\n-- Forward classify (plan-knowable inputs only) — demo --")
    demo = {"MIX_TN_num": 0, "GRADE_CY_num": 48442, "BASE_TN_num": 6546,
            "SHLDR_TN_num": 0, "MILL_SY_num": 0, "has_quantity": True}  # Stutsman grade-raise
    print("  ", classify_new_plan(demo, thresh))

    print(f"\nWrote: 2026-06-15_worktype_size_thresholds.csv, "
          f"2026-06-15_archetype_size_profit.csv, 2026-06-15_projects_classified.csv")
    print("Scope: analysis only; live 10_000 rule unchanged; no $ used as a live input.")


def classify_new_plan(q: dict, thresholds: pd.DataFrame) -> dict:
    """Forward-applicable: plan-knowable quantities -> {work_type, size_tier}.
    Leakage-safe (no auction $). `thresholds` is the per-archetype cut table."""
    r = {k: float(q.get(k, 0) or 0) for k in
         ["MIX_TN_num", "GRADE_CY_num", "BASE_TN_num", "SHLDR_TN_num", "MILL_SY_num",
          "CRUSH_TN_num", "STOCK_TN_num"]}
    r["has_quantity"] = q.get("has_quantity", any(v > 0 for v in r.values()))
    wt = work_type(r)
    basis = SIZE_BASIS.get(wt, (None, None))[0]
    val = {"placed_tons": r["MIX_TN_num"] + r["BASE_TN_num"] + r["SHLDR_TN_num"],
           "base_shldr": r["BASE_TN_num"] + r["SHLDR_TN_num"]}.get(basis,
           r.get(basis) if basis else np.nan)
    cut = thresholds.loc[thresholds["work_type"] == wt, "large_cut"]
    tier = ("Large" if (len(cut) and pd.notna(cut.iloc[0]) and val >= cut.iloc[0]) else "Small") \
           if basis else "n/a"
    return {"work_type": wt, "size_basis": SIZE_BASIS.get(wt, (None, "n/a"))[1],
            "size_value": round(val) if val == val else None, "size_tier": tier}


if __name__ == "__main__":
    main()
