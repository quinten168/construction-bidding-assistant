"""
2026-06-17  Archetype labeling rule v2 (share-gated)  +  diff vs current rule.

WHAT THIS IS
------------
The new work-type labeling rule, grounded in the separability work of 2026-06-17:
  * tonnage SHARES (not raw magnitude) draw the paving / non-paving boundary and kill
    "trivial triggers" (a job with a token of MIX is not a paving job);
  * GRADE / MILL PRESENCE (gated by a magnitude floor so token amounts don't count)
    route WITHIN the paving family.

It applies v2 to all projects and DIFFS the new labels against the current ("v1") rule,
per Hard Rule 12 (test a new method against the baseline before scaling). It writes the
new labels + the diff, but it does NOT modify the 3 synced production functions -- that
propagation happens only after the diff is reviewed.

WHY THE THRESHOLDS ARE WHERE THEY ARE (from the distributions we already looked at)
-----------------------------------------------------------------------------------
  MIX_SHARE_MIN = 0.15  -- paving jobs sit at mix-share p25 ~0.18-0.26; the 17-28% of
                           "paving" labels that were really aggregate jobs sit below ~0.20.
                           0.15 is conservative: it demotes only clearly-token mix.
  GRADE_MIN_CY  = 500   -- Reconstruct GRADE p10/p25 = 200/668 CY; <500 CY is approach /
                           driveway-scale grading, not a roadbed regrade.
  MILL_MIN_SY   = 1000  -- Mill&Overlay MILL p25 = 1664 SY; 19% sit <1000 SY (edge mills).
These three are the tunables. The diff shows how sensitive the labels are to them.
"""

from pathlib import Path
import pandas as pd
import numpy as np

# --- paths -----------------------------------------------------------------------------------------
HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
MASTER_CSV = REPO / "01_data" / "2026-06-03_csi_bid_master.csv"
OUT_DIR = HERE.parent / "outputs"
OUT_LABELS = OUT_DIR / "2026-06-17_archetype_labels_v2.csv"
OUT_DIFF = OUT_DIR / "2026-06-17_archetype_v1_v2_diff.csv"

# --- the tunable thresholds (justification in the docstring) ---------------------------------------
MIX_SHARE_MIN = 0.15      # mix is "real paving" if it is >=15% of tonnage ...
MIX_ABS_MIN = 1000        # ... OR >=1000 tons absolute. The OR is essential: a 39,000-t mill&overlay
                          #     that also carries more aggregate dips below 15% share but is obviously
                          #     paving. Real paving jobs sit at mix p25 ~1,300 t; token-mix demote
                          #     candidates have <100 t -- so 1,000 t cleanly splits them.
GRADE_MIN_CY = 500        # grade must be >=500 CY to count as a real regrade (token = approach grading)
MILL_MIN_SY = 1000        # mill must be >=1000 SY to count as real milling (token = edge mills)

MAT = ["MIX_TN", "GRADE_CY", "BASE_TN", "SHLDR_TN", "MILL_SY", "CRUSH_TN", "STOCK_TN"]
TONS = ["MIX_TN", "BASE_TN", "SHLDR_TN", "CRUSH_TN", "STOCK_TN"]


def to_num(s: pd.Series) -> pd.Series:
    return pd.to_numeric(
        s.astype(str).str.replace(",", "", regex=False)
                     .str.replace("$", "", regex=False)
                     .str.strip().replace("", np.nan),
        errors="coerce",
    )


def work_type_v1(r) -> str:
    """CURRENT rule -- binary presence, magnitude-blind. The baseline we diff against."""
    g = lambda k: (r[k + "_n"] if pd.notna(r[k + "_n"]) else 0) > 0
    if not any(g(k) for k in MAT):
        return "Unknown/NoQty"
    mix, grade, mill = g("MIX_TN"), g("GRADE_CY"), g("MILL_SY")
    base, shldr = g("BASE_TN"), g("SHLDR_TN")
    if grade and mix:    return "Reconstruct/Rebuild"
    if mix and mill:     return "Mill & Overlay"
    if mix:              return "HMA Overlay/Resurface"
    if grade:            return "Grading/Earthwork"
    if base or shldr:    return "Aggregate/Base/Gravel"
    return "Other"


def work_type_v2(r) -> str:
    """NEW rule -- share-gated two-layer.
    Layer 1: is this genuinely a paving job? (MIX is a real share of tonnage, not a token)
    Layer 2 (paving):     GRADE? -> Reconstruct ; else MILL? -> Mill&Overlay ; else HMA Overlay
    Layer 2 (non-paving): GRADE? -> Grading      ; else BASE/SHLDR? -> Aggregate ; else Other
    Note: MILL is deliberately NOT used in the non-paving branch -- the Aggregate/MILL jobs are
    a data artifact (blank MIX/GRADE + mis-loaded MILL_SY on levee/landfill/grading work)."""
    q = lambda k: (r[k + "_n"] if pd.notna(r[k + "_n"]) else 0)
    if not any(q(k) > 0 for k in MAT):
        return "Unknown/NoQty"

    total_tons = sum(q(k) for k in TONS)
    mix_share = (q("MIX_TN") / total_tons) if total_tons > 0 else 0.0

    # gated: a real share OR a real absolute amount of mix makes it a paving job; a token of mix does not
    paving = (mix_share >= MIX_SHARE_MIN) or (q("MIX_TN") >= MIX_ABS_MIN)
    grade = q("GRADE_CY") >= GRADE_MIN_CY      # gated: token grading does NOT count
    mill = q("MILL_SY") >= MILL_MIN_SY         # gated: token milling does NOT count
    has_agg = (q("BASE_TN") > 0) or (q("SHLDR_TN") > 0)

    if paving:
        if grade:   return "Reconstruct/Rebuild"
        if mill:    return "Mill & Overlay"
        return "HMA Overlay/Resurface"
    # non-paving (includes token-paving jobs demoted out of the paving family)
    if grade:       return "Grading/Earthwork"
    if has_agg:     return "Aggregate/Base/Gravel"
    return "Other"


def main() -> None:
    df = pd.read_csv(MASTER_CSV, dtype=str, low_memory=False)
    for c in MAT:
        df[c + "_n"] = to_num(df[c])
    proj = df.sort_values("Contract_Id").drop_duplicates("Contract_Id").copy()

    proj["v1"] = proj.apply(work_type_v1, axis=1)
    proj["v2"] = proj.apply(work_type_v2, axis=1)
    proj["changed"] = proj["v1"] != proj["v2"]

    # --- save labels --------------------------------------------------------------------------------
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    keep = ["Contract_Id", "Project_Name", "State"] + [c + "_n" for c in MAT] + ["v1", "v2", "changed"]
    proj[keep].to_csv(OUT_LABELS, index=False)

    # --- counts before/after ------------------------------------------------------------------------
    order = ["Reconstruct/Rebuild", "Mill & Overlay", "HMA Overlay/Resurface",
             "Grading/Earthwork", "Aggregate/Base/Gravel", "Other", "Unknown/NoQty"]
    counts = pd.DataFrame({"v1": proj["v1"].value_counts(), "v2": proj["v2"].value_counts()}).reindex(order).fillna(0).astype(int)
    counts["delta"] = counts["v2"] - counts["v1"]
    print(f"Projects: {len(proj)}   changed label: {int(proj['changed'].sum())} "
          f"({proj['changed'].mean()*100:.1f}%)\n")
    print("=== label counts: v1 -> v2 ===")
    print(counts.to_string())

    # --- the migration crosstab (where did the moved jobs go) ---------------------------------------
    moved = proj[proj["changed"]]
    xt = pd.crosstab(moved["v1"], moved["v2"])
    xt.to_csv(OUT_DIFF)
    print("\n=== migration of CHANGED jobs (rows = old v1, cols = new v2) ===")
    print(xt.to_string())

    # --- sanity-check the biggest migration cells with real examples --------------------------------
    print("\n=== examples from the largest migration cells (sanity check) ===")
    cell_sizes = xt.stack().sort_values(ascending=False)
    for (v1, v2), n in cell_sizes.head(4).items():
        ex = moved[(moved["v1"] == v1) & (moved["v2"] == v2)].copy()
        ex["mix_sh"] = (ex["MIX_TN_n"].fillna(0) /
                        ex[[c + "_n" for c in TONS]].fillna(0).sum(axis=1).replace(0, np.nan)).round(2)
        print(f"\n  [{v1}]  ->  [{v2}]   ({n} jobs)")
        print(ex[["Project_Name", "State", "MIX_TN_n", "GRADE_CY_n", "MILL_SY_n", "BASE_TN_n", "mix_sh"]]
              .head(6).to_string(index=False))

    print(f"\nlabels -> {OUT_LABELS}\ndiff   -> {OUT_DIFF}")


if __name__ == "__main__":
    main()
