"""
CSI Sweet-Spot Analysis — Step 2 (WS-A): project archetyping, both-compared
===========================================================================
Two independent archetype labelings on the material-mix SHAPE of each project,
then an agreement test:

  (1) RULE-BASED  — codifies CSI's five named archetypes (CLAUDE.md) as
      thresholds on the parsed tonnage / material proportions.
  (2) DISCOVERED  — PCA + K-means on the standardized material-PROPORTION vector
      (scale-free: a $50k and a $5M job of the same shape cluster together).

Runs on the quantity-complete subsample (~1,376 projects). Projects with no
quantity get rule label 'Unknown/NoQty' and no cluster.

CAVEAT: proportions mix units (TN, CY, SY) in a shared denominator — a rough
compositional fingerprint, not a physical fraction. Adequate for shape
clustering; flagged for interpretation.

Input : 2026-06-04_project_base.csv
Output: 2026-06-04_project_archetypes.csv      (Contract_Id + both labels)
        2026-06-04_archetype_pca.png            (PCA scatter, colored by cluster)
        2026-06-04_archetype_cluster_profiles.csv
"""

from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from sklearn.preprocessing import StandardScaler
from sklearn.decomposition import PCA
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score, adjusted_rand_score

HERE = Path(__file__).resolve().parent.parent / "outputs"
BASE = HERE / "2026-06-04_project_base.csv"
OUT_CSV = HERE / "2026-06-04_project_archetypes.csv"
OUT_PNG = HERE / "2026-06-04_archetype_pca.png"
OUT_PROF = HERE / "2026-06-04_archetype_cluster_profiles.csv"

MAT = ["MIX_TN", "GRADE_CY", "BASE_TN", "SHLDR_TN", "MILL_SY", "CRUSH_TN", "STOCK_TN"]
PROP = ["prop_" + m for m in MAT]
SEED = 42


# ── (1) Rule-based archetypes (CSI's work-types) ──────────────────────────────
# CANONICAL (v2, share-gated; 2026-06-17) — KEEP IN SYNC with dashboard/utils/data.py:
# _rule_archetype and 2026-06-15_size_within_archetype.py:work_type.
# See 2026-06-15_project_type_definitions.md.
# v2 gates each trigger by magnitude so a TOKEN of a material can't flip the label.
MIX_SHARE_MIN = 0.15      # mix is "real paving" at >=15% of tonnage ...
MIX_ABS_MIN = 1000.0      # ... OR >=1000 t absolute (big-mix jobs that also carry more aggregate)
GRADE_MIN_CY = 500.0      # real regrade, not approach/driveway grading
MILL_MIN_SY = 1000.0      # real milling, not edge mills
TON_COLS = ["MIX_TN", "BASE_TN", "SHLDR_TN", "CRUSH_TN", "STOCK_TN"]   # the summable family


def rule_archetype(r):
    """Layer 1: is it genuinely a paving job? (mix is a real SHARE or a real ABSOLUTE amount)
    Layer 2: route by GRADE / MILL presence (each gated so token amounts don't count)."""
    if not r["has_quantity"]:
        return "Unknown/NoQty"
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


def main():
    df = pd.read_csv(BASE)
    print(f"Loaded base: {len(df):,} projects")

    df["rule_archetype"] = df.apply(rule_archetype, axis=1)
    print("\n-- Rule-based archetype distribution (all 1,591) --")
    print(df["rule_archetype"].value_counts().to_string())

    # ── (2) Discovered clusters on quantity-complete subsample ────────────────
    qc = df[df["has_quantity"]].copy()
    X = qc[PROP].fillna(0.0).values          # shape vector (scale-free)
    Xs = StandardScaler().fit_transform(X)
    print(f"\nClustering subsample: {len(qc):,} quantity-complete projects, {X.shape[1]} shape features")

    print("\n-- K selection (silhouette) --")
    best_k, best_s = None, -1
    for k in range(3, 7):
        km = KMeans(n_clusters=k, n_init=10, random_state=SEED).fit(Xs)
        s = silhouette_score(Xs, km.labels_)
        print(f"  k={k}: silhouette={s:.3f}")
        if s > best_s:
            best_k, best_s = k, s
    print(f"  -> chose k={best_k} (silhouette={best_s:.3f})")

    km = KMeans(n_clusters=best_k, n_init=25, random_state=SEED).fit(Xs)
    qc["cluster_id"] = km.labels_

    # Re-seed stability check
    km2 = KMeans(n_clusters=best_k, n_init=25, random_state=7).fit(Xs)
    print(f"  re-seed stability (ARI vs seed=42): {adjusted_rand_score(km.labels_, km2.labels_):.3f}")

    # Cluster profiles: mean proportion per material + scale + size
    prof = qc.groupby("cluster_id").agg(
        n=("Contract_Id", "size"),
        **{p: (p, "mean") for p in PROP},
        med_total_qty=("total_quantity", "median"),
        med_size_dollars=("Project_Size_Dollars", "median"),
        med_mix_tn=("MIX_TN_num", "median"),
    ).round(3)
    prof.to_csv(OUT_PROF)
    print("\n-- Cluster profiles (mean material proportions) --")
    print(prof[[ "n"] + PROP].to_string())

    # Auto-name clusters by dominant material proportion
    dom = qc.groupby("cluster_id")[PROP].mean().idxmax(axis=1).str.replace("prop_", "")
    name_map = {cid: f"C{cid}:{dom[cid]}-dom" for cid in dom.index}
    qc["cluster_label"] = qc["cluster_id"].map(name_map)
    print("\n  cluster names:", name_map)

    # ── Agreement: rule-based vs discovered ───────────────────────────────────
    ct = pd.crosstab(qc["rule_archetype"], qc["cluster_label"])
    print("\n-- Agreement: rule archetype (rows) x discovered cluster (cols) --")
    print(ct.to_string())
    # encode rule labels to compute ARI
    rule_codes = qc["rule_archetype"].astype("category").cat.codes
    ari = adjusted_rand_score(rule_codes, qc["cluster_id"])
    print(f"\n  Adjusted Rand Index (rule vs discovered): {ari:.3f}")
    print("  (near 0 = the data's natural shapes cut differently than CSI's named")
    print("   taxonomy; that disagreement is itself a finding.)")

    # ── PCA scatter ───────────────────────────────────────────────────────────
    p2 = PCA(n_components=2, random_state=SEED).fit(Xs)
    XY = p2.transform(Xs)
    ev = p2.explained_variance_ratio_
    fig, ax = plt.subplots(figsize=(8, 6))
    for cid in sorted(qc["cluster_id"].unique()):
        m = qc["cluster_id"] == cid
        ax.scatter(XY[m.values, 0], XY[m.values, 1], s=12, alpha=0.6, label=name_map[cid])
    ax.set_xlabel(f"PC1 ({ev[0]*100:.0f}% var)")
    ax.set_ylabel(f"PC2 ({ev[1]*100:.0f}% var)")
    ax.set_title(f"Project material-mix space (k={best_k} K-means)\n1,376 quantity-complete projects")
    ax.legend(fontsize=8, loc="best")
    fig.tight_layout()
    fig.savefig(OUT_PNG, dpi=130)
    print(f"\nWrote {OUT_PNG.name}  (PC1+PC2 = {ev[:2].sum()*100:.0f}% var)")

    # ── Write labels back to full project set ─────────────────────────────────
    out = df[["Contract_Id", "rule_archetype"]].merge(
        qc[["Contract_Id", "cluster_id", "cluster_label"]], on="Contract_Id", how="left")
    out.to_csv(OUT_CSV, index=False)
    print(f"Wrote {OUT_CSV.name}: {len(out):,} rows "
          f"({out['cluster_id'].notna().sum():,} clustered, "
          f"{out['cluster_id'].isna().sum():,} no-quantity)")


if __name__ == "__main__":
    main()
