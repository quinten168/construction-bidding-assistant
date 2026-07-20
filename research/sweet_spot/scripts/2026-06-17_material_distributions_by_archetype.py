"""
2026-06-17  Foundational view: material distributions by archetype  (READ-ONLY, no rule changes)

GOAL
----
Before changing any classification rule, just LOOK at the raw structure of the data.
For each of the 5 work-type archetypes, show the distribution of all 7 quantity
materials in their NATIVE units (no unit-mixing, no normalization):
    tons -> MIX, BASE, SHLDR, CRUSH, STOCK   |   CY -> GRADE   |   SY -> MILL

Two outputs:
  1) a stats table (present-only: median / p25 / p75 / min / max) with the PRESENCE RATE
     next to it, so we never let zeros collapse a distribution; and
  2) a faceted log-scale boxplot (one panel per material, archetypes on the x-axis) so the
     overlap between archetypes is visible at a glance.

This proposes nothing. It is the picture we look at before deciding the fix.
"""

from pathlib import Path
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use("Agg")                                    # headless: write a PNG, don't open a window
import matplotlib.pyplot as plt

# --- paths -----------------------------------------------------------------------------------------
HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]                                    # .../01_Summer_2026
MASTER_CSV = REPO / "01_data" / "2026-06-03_csi_bid_master.csv"
OUT_DIR = HERE.parent / "outputs"
OUT_TABLE = OUT_DIR / "2026-06-17_material_distributions_by_archetype.csv"
OUT_FIG = OUT_DIR / "2026-06-17_material_distributions_by_archetype.png"

# --- the 7 materials and their native units --------------------------------------------------------
UNITS = {"MIX_TN": "tons", "GRADE_CY": "CY", "MILL_SY": "SY", "BASE_TN": "tons",
         "SHLDR_TN": "tons", "CRUSH_TN": "tons", "STOCK_TN": "tons"}
MAT = list(UNITS)

# --- the 5 real archetypes (drop Unknown/Other from the picture) -----------------------------------
ARCHES = ["Reconstruct/Rebuild", "Mill & Overlay", "HMA Overlay/Resurface",
          "Grading/Earthwork", "Aggregate/Base/Gravel"]


def to_num(s: pd.Series) -> pd.Series:
    """Parse CSI's hand-typed numbers: strip $ and thousands-commas, blanks -> NaN."""
    return pd.to_numeric(
        s.astype(str).str.replace(",", "", regex=False)
                     .str.replace("$", "", regex=False)
                     .str.strip().replace("", np.nan),
        errors="coerce",
    )


def work_type(r) -> str:
    """Current canonical work-type rule, copied verbatim so this picture matches production labels."""
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
    # --- load, collapse to one row per project, label work-type ------------------------------------
    df = pd.read_csv(MASTER_CSV, dtype=str, low_memory=False)
    for c in MAT:
        df[c + "_n"] = to_num(df[c])
    proj = df.sort_values("Contract_Id").drop_duplicates("Contract_Id").copy()
    proj["wt"] = proj.apply(work_type, axis=1)

    n_by_arch = proj["wt"].value_counts()

    # --- build the present-only stats table --------------------------------------------------------
    # For each archetype x material: presence rate over ALL jobs in that archetype, but the
    # min/p25/median/p75/max are computed ONLY over jobs where the material is present (>0).
    rows = []
    for arch in ARCHES:
        sub = proj[proj["wt"] == arch]
        n_arch = len(sub)
        for mat in MAT:
            vals = sub[mat + "_n"]
            present = vals[vals.fillna(0) > 0]
            rows.append({
                "archetype": arch,
                "material": mat,
                "unit": UNITS[mat],
                "n_archetype": n_arch,
                "n_present": len(present),
                "presence_rate_%": round(len(present) / n_arch * 100, 1) if n_arch else np.nan,
                "min": round(present.min(), 0) if len(present) else np.nan,
                "p25": round(present.quantile(0.25), 0) if len(present) else np.nan,
                "median": round(present.median(), 0) if len(present) else np.nan,
                "p75": round(present.quantile(0.75), 0) if len(present) else np.nan,
                "max": round(present.max(), 0) if len(present) else np.nan,
            })
    table = pd.DataFrame(rows)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    table.to_csv(OUT_TABLE, index=False)

    # --- print it grouped by material so we can read overlap across archetypes ---------------------
    print(f"Projects: {len(proj)}   archetype counts: "
          + ", ".join(f"{a}={int(n_by_arch.get(a, 0))}" for a in ARCHES) + "\n")
    for mat in MAT:
        print(f"=== {mat}  ({UNITS[mat]})  -- present-only distribution by archetype ===")
        block = (table[table["material"] == mat]
                 [["archetype", "presence_rate_%", "n_present", "min", "p25", "median", "p75", "max"]])
        print(block.to_string(index=False))
        print()

    # --- faceted log-scale boxplot: one panel per material, archetypes on x ------------------------
    # Log scale because ranges span ~5 orders of magnitude (min 11 -> max 2.8M); a linear axis would
    # crush every box to a line. Present-only values feed each box.
    fig, axes = plt.subplots(3, 3, figsize=(18, 13))
    axes = axes.flatten()
    short = {"Reconstruct/Rebuild": "Recon", "Mill & Overlay": "Mill&OL",
             "HMA Overlay/Resurface": "HMA-OL", "Grading/Earthwork": "Grade", "Aggregate/Base/Gravel": "Agg"}

    for i, mat in enumerate(MAT):
        ax = axes[i]
        data, labels, rates = [], [], []
        for arch in ARCHES:
            v = proj.loc[proj["wt"] == arch, mat + "_n"]
            v = v[v.fillna(0) > 0].dropna()
            if len(v):
                data.append(v.values)
                rate = len(v) / max(1, len(proj[proj["wt"] == arch])) * 100
                labels.append(f"{short[arch]}\n{rate:.0f}% (n={len(v)})")
                rates.append(rate)
        if data:
            ax.boxplot(data, labels=labels, showfliers=True, whis=(5, 95),
                       medianprops=dict(color="crimson", linewidth=2))
            ax.set_yscale("log")
        ax.set_title(f"{mat}  ({UNITS[mat]})", fontsize=12, fontweight="bold")
        ax.tick_params(axis="x", labelsize=8)
        ax.grid(axis="y", alpha=0.3, which="both")

    # hide the 2 unused panels (7 materials in a 3x3 grid)
    for j in range(len(MAT), len(axes)):
        axes[j].axis("off")

    fig.suptitle("Material distributions by archetype (native units, present-only, log scale)\n"
                 "whiskers = 5th-95th pct; red line = median; x-label shows presence rate & n",
                 fontsize=14, fontweight="bold")
    fig.tight_layout(rect=(0, 0, 1, 0.96))
    fig.savefig(OUT_FIG, dpi=130)
    print(f"table -> {OUT_TABLE}")
    print(f"figure -> {OUT_FIG}")


if __name__ == "__main__":
    main()
