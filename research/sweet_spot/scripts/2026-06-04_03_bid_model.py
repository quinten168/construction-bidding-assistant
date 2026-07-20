"""
CSI Sweet-Spot Analysis — Step 3 (WS-1): Q1 "When does CSI decide to bid?"
==========================================================================
Binary classifier for CSI_Participated over all 1,591 projects (603 bid / 988
not). Archetype enters as a feature; we also report P(bid | archetype) and the
within-archetype drivers (the descriptive-selection story).

LEAKAGE GUARD (Hard Rule 10): features must be knowable from the RFP BEFORE CSI
decides to bid. Excluded as post-decision / realized outcomes:
  Num_Valid_Bidders, Num_Bidders, Market_Tightness_Category  (realized competition)
  Winner_Amount, Second_Place_Amount, Bid_Quality, Margin_*, Bid_Rank, CSI_* outcomes

Input : 2026-06-04_project_base.csv  +  2026-06-04_project_archetypes.csv
Output: 2026-06-04_bid_model_importance.csv, 2026-06-04_bid_by_archetype.csv,
        2026-06-04_bid_model.png
"""

import warnings
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from sklearn.pipeline import Pipeline
from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import StandardScaler, OneHotEncoder
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.model_selection import cross_val_predict, StratifiedKFold
from sklearn.metrics import roc_auc_score, average_precision_score
from sklearn.inspection import permutation_importance

warnings.filterwarnings("ignore", category=RuntimeWarning)  # spurious BLAS matmul noise
HERE = Path(__file__).resolve().parent.parent / "outputs"
SEED = 42

NUM_FEATS = ["log_size", "n_mat_types", "BOX_i", "PW_yes", "PW_unknown",
             "prop_MIX_TN", "prop_GRADE_CY", "prop_BASE_TN", "prop_SHLDR_TN",
             "prop_MILL_SY", "prop_STOCK_TN", "has_quantity_i"]
CAT_FEATS = ["State", "rule_archetype"]


def build_features(df):
    df = df.copy()
    df["log_size"] = np.log10(df["Project_Size_Dollars"].clip(lower=1))
    df["BOX_i"] = df["BOX"].astype(int)
    df["PW_yes"] = (df["PREVAILING_WAGES"] == True).astype(int)
    df["PW_unknown"] = df["PREVAILING_WAGES"].isna().astype(int)
    df["has_quantity_i"] = df["has_quantity"].astype(int)
    for p in ["prop_MIX_TN", "prop_GRADE_CY", "prop_BASE_TN", "prop_SHLDR_TN",
              "prop_MILL_SY", "prop_STOCK_TN"]:
        df[p] = df[p].fillna(0.0)
    df["State"] = df["State"].fillna("UNK")
    return df


def main():
    base = pd.read_csv(HERE / "2026-06-04_project_base.csv")
    arch = pd.read_csv(HERE / "2026-06-04_project_archetypes.csv")
    df = base.merge(arch, on="Contract_Id", how="left")
    df = build_features(df)
    y = df["CSI_Participated"].astype(int).values
    print(f"Projects: {len(df):,} | CSI bid: {y.sum()} ({y.mean()*100:.1f}%)")

    pre = ColumnTransformer([
        ("num", Pipeline([("imp", SimpleImputer(strategy="median")),
                          ("sc", StandardScaler())]), NUM_FEATS),
        ("cat", OneHotEncoder(handle_unknown="ignore", min_frequency=10), CAT_FEATS),
    ])
    cv = StratifiedKFold(5, shuffle=True, random_state=SEED)

    models = {
        "logistic": Pipeline([("pre", pre),
                              ("clf", LogisticRegression(max_iter=2000, class_weight="balanced"))]),
        "hist_gb": Pipeline([("pre", pre),
                             ("clf", HistGradientBoostingClassifier(random_state=SEED))]),
    }
    print("\n-- 5-fold CV (out-of-fold) --")
    oof = {}
    for name, pipe in models.items():
        p = cross_val_predict(pipe, df, y, cv=cv, method="predict_proba")[:, 1]
        oof[name] = p
        print(f"  {name:9s}  ROC-AUC={roc_auc_score(y,p):.3f}  PR-AUC={average_precision_score(y,p):.3f}"
              f"  (baseline PR={y.mean():.3f})")

    # Fit hist_gb on the feature columns only so permutation importance aligns 1:1
    raw_cols = NUM_FEATS + CAT_FEATS
    Xsub = df[raw_cols]
    best = models["hist_gb"].fit(Xsub, y)
    r = permutation_importance(best, Xsub, y, n_repeats=10, random_state=SEED,
                               scoring="roc_auc")
    imp = pd.DataFrame({"feature": raw_cols,
                        "importance": r.importances_mean,
                        "std": r.importances_std}).sort_values("importance", ascending=False)
    imp.to_csv(HERE / "2026-06-04_bid_model_importance.csv", index=False)
    print("\n-- Permutation importance (hist_gb, drop in ROC-AUC) --")
    print(imp.to_string(index=False))

    # P(bid | archetype) — descriptive selection
    print("\n-- P(CSI bids | rule archetype) --")
    g = df.groupby("rule_archetype").agg(n=("CSI_Participated", "size"),
                                         bid_rate=("CSI_Participated", "mean")).sort_values("bid_rate", ascending=False)
    g["bid_rate"] = (g["bid_rate"] * 100).round(1)
    print(g.to_string())
    gc = df.dropna(subset=["cluster_label"]).groupby("cluster_label").agg(
        n=("CSI_Participated", "size"), bid_rate=("CSI_Participated", "mean")).sort_values("bid_rate", ascending=False)
    gc["bid_rate"] = (gc["bid_rate"] * 100).round(1)
    print("\n-- P(CSI bids | discovered cluster) --")
    print(gc.to_string())
    g.to_csv(HERE / "2026-06-04_bid_by_archetype.csv")

    # Plot: importance + bid-rate by archetype
    fig, ax = plt.subplots(1, 2, figsize=(13, 5))
    top = imp.head(10).iloc[::-1]
    ax[0].barh(top["feature"], top["importance"], color="steelblue")
    ax[0].set_title("Q1 bid/no-bid: permutation importance (ROC-AUC drop)")
    ax[0].set_xlabel("mean importance")
    gg = g.sort_values("bid_rate")
    ax[1].barh(gg.index, gg["bid_rate"], color="darkorange")
    ax[1].axvline(y.mean()*100, ls="--", c="gray", label=f"overall {y.mean()*100:.0f}%")
    ax[1].set_title("P(CSI bids) by rule archetype")
    ax[1].set_xlabel("bid rate (%)"); ax[1].legend()
    fig.tight_layout(); fig.savefig(HERE / "2026-06-04_bid_model.png", dpi=130)
    print(f"\nWrote 2026-06-04_bid_model.png")


if __name__ == "__main__":
    main()
