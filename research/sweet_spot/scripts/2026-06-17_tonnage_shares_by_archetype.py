"""
2026-06-17  Tonnage-share separability by archetype  (READ-ONLY, no rule changes)

THE HYPOTHESIS UNDER TEST
-------------------------
Absolute magnitudes overlap badly (MIX medians are interchangeable across the 3 paving
types). The new idea: the separating signal is the *mix of work*, i.e. each material's
SHARE of the tonnage-comparable family, not its raw amount.

For every project we compute, within the tons-only family (MIX+BASE+SHLDR+CRUSH+STOCK):
    mix_share   = MIX   / total_tons
    base_share  = BASE  / total_tons
    shldr_share = SHLDR / total_tons
GRADE (CY) and MILL (SY) cannot be summed with tons, so they stay as native
PRESENCE flags -- the other axis of the signal.

Output: share distributions (p25/median/p75) by archetype + GRADE/MILL presence rate,
and a boxplot of the three shares so we can SEE whether the buckets pull apart.
Proposes nothing -- this is the evidence we look at before any rule.
"""

from pathlib import Path
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

# --- paths -----------------------------------------------------------------------------------------
HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
MASTER_CSV = REPO / "01_data" / "2026-06-03_csi_bid_master.csv"
OUT_DIR = HERE.parent / "outputs"
OUT_TABLE = OUT_DIR / "2026-06-17_tonnage_shares_by_archetype.csv"
OUT_FIG = OUT_DIR / "2026-06-17_tonnage_shares_by_archetype.png"

# --- material groups -------------------------------------------------------------------------------
MAT = ["MIX_TN", "GRADE_CY", "BASE_TN", "SHLDR_TN", "MILL_SY", "CRUSH_TN", "STOCK_TN"]
TONS = ["MIX_TN", "BASE_TN", "SHLDR_TN", "CRUSH_TN", "STOCK_TN"]   # summable family
ARCHES = ["Reconstruct/Rebuild", "Mill & Overlay", "HMA Overlay/Resurface",
          "Grading/Earthwork", "Aggregate/Base/Gravel"]


def to_num(s: pd.Series) -> pd.Series:
    return pd.to_numeric(
        s.astype(str).str.replace(",", "", regex=False)
                     .str.replace("$", "", regex=False)
                     .str.strip().replace("", np.nan),
        errors="coerce",
    )


def work_type(r) -> str:
    """Current rule, verbatim -- labels must match production for this comparison to mean anything."""
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


def main() -> None:
    # --- load, collapse to project level, label ----------------------------------------------------
    df = pd.read_csv(MASTER_CSV, dtype=str, low_memory=False)
    for c in MAT:
        df[c + "_n"] = to_num(df[c])
    proj = df.sort_values("Contract_Id").drop_duplicates("Contract_Id").copy()
    proj["wt"] = proj.apply(work_type, axis=1)

    # --- compute the tonnage shares ----------------------------------------------------------------
    # total_tons = the summable family only. Share is undefined when a job has zero tons of everything
    # (pure GRADE jobs) -- those are excluded from the share view and counted separately.
    proj["total_tons"] = proj[[c + "_n" for c in TONS]].fillna(0).sum(axis=1)
    has_tons = proj["total_tons"] > 0
    for c in ["MIX_TN", "BASE_TN", "SHLDR_TN"]:
        proj[c + "_share"] = np.where(has_tons, proj[c + "_n"].fillna(0) / proj["total_tons"], np.nan)

    # --- presence flags for the two non-tonnage materials ------------------------------------------
    proj["grade_present"] = proj["GRADE_CY_n"].fillna(0) > 0
    proj["mill_present"] = proj["MILL_SY_n"].fillna(0) > 0

    # --- build the table: per archetype, share quartiles + GRADE/MILL presence + no-tons count -----
    rows = []
    for arch in ARCHES:
        sub = proj[proj["wt"] == arch]
        n = len(sub)
        sub_t = sub[sub["total_tons"] > 0]            # share rows only
        n_notons = n - len(sub_t)
        rec = {"archetype": arch, "n": n, "n_with_tons": len(sub_t), "n_zero_tons": n_notons,
               "grade_present_%": round(sub["grade_present"].mean() * 100, 1),
               "mill_present_%": round(sub["mill_present"].mean() * 100, 1)}
        for c in ["MIX_TN", "BASE_TN", "SHLDR_TN"]:
            s = sub_t[c + "_share"]
            tag = c.replace("_TN", "").lower()
            rec[f"{tag}_p25"] = round(s.quantile(0.25), 2)
            rec[f"{tag}_med"] = round(s.median(), 2)
            rec[f"{tag}_p75"] = round(s.quantile(0.75), 2)
        rows.append(rec)
    table = pd.DataFrame(rows)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    table.to_csv(OUT_TABLE, index=False)

    # --- print: one block per share material so overlap across archetypes is readable --------------
    print(f"Projects: {len(proj)}   (with tons: {int(has_tons.sum())}, "
          f"zero-tons/pure-GRADE: {int((~has_tons).sum())})\n")
    print("=== GRADE / MILL presence by archetype (native presence signal, kept separate) ===")
    print(table[["archetype", "n", "n_zero_tons", "grade_present_%", "mill_present_%"]].to_string(index=False))
    for tag, name in [("mix", "MIX share"), ("base", "BASE share"), ("shldr", "SHLDR share")]:
        print(f"\n=== {name} of total tons  (p25 / median / p75) by archetype ===")
        print(table[["archetype", "n_with_tons", f"{tag}_p25", f"{tag}_med", f"{tag}_p75"]]
              .to_string(index=False))

    # --- boxplot: 3 panels (mix/base/shldr share), archetypes on x, linear 0-1 axis ----------------
    # Linear axis this time: shares live in [0,1], so no log needed -- and we WANT to see whether
    # the boxes occupy different bands of the 0-1 range (that is what "separable" looks like).
    fig, axes = plt.subplots(1, 3, figsize=(20, 7), sharey=True)
    short = {"Reconstruct/Rebuild": "Recon", "Mill & Overlay": "Mill&OL",
             "HMA Overlay/Resurface": "HMA-OL", "Grading/Earthwork": "Grade", "Aggregate/Base/Gravel": "Agg"}
    for ax, (c, title) in zip(axes, [("MIX_TN", "MIX share"), ("BASE_TN", "BASE share"),
                                      ("SHLDR_TN", "SHLDR share")]):
        data, labels = [], []
        for arch in ARCHES:
            v = proj.loc[(proj["wt"] == arch) & (proj["total_tons"] > 0), c + "_share"].dropna()
            if len(v):
                data.append(v.values)
                labels.append(f"{short[arch]}\n(n={len(v)})")
        ax.boxplot(data, tick_labels=labels, showfliers=False, whis=(10, 90),
                   medianprops=dict(color="crimson", linewidth=2))
        ax.set_title(title, fontsize=13, fontweight="bold")
        ax.set_ylim(0, 1)
        ax.grid(axis="y", alpha=0.3)
        ax.tick_params(axis="x", labelsize=9)
    axes[0].set_ylabel("share of total tons (MIX+BASE+SHLDR+CRUSH+STOCK)")
    fig.suptitle("Tonnage-share distributions by archetype (present jobs with tons>0; box = IQR, "
                 "whiskers 10-90th, red = median)", fontsize=14, fontweight="bold")
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    fig.savefig(OUT_FIG, dpi=130)
    print(f"\ntable -> {OUT_TABLE}\nfigure -> {OUT_FIG}")


if __name__ == "__main__":
    main()
