"""
CSI Sweet-Spot Analysis — Step 4 (WS-2): Q2 "When CSI bids, does it win?"
=========================================================================
On the 603 projects CSI bid (117 wins, 19.4%):
  PRIMARY (modeled)   : P(win | job characteristics, archetype). Same
                        RFP-knowable feature set as Q1 so the win signal lives
                        in job-characteristic space (the "sweet spot"), not in
                        realized competition.
  SECONDARY (overlay) : competitive gap-to-winner via CSI_Bid_Quality.
                        Bomb = WON but left >14% on the table (median margin
                        -14.5%); Excellent/Acceptable Win = won, priced well.

Outputs P(win|archetype), bomb-rate, win-well-rate per archetype — the money-
left-on-table lens. NO predictive margin regression (per plan §8.3).

Input : 2026-06-04_project_base.csv + 2026-06-04_project_archetypes.csv
Output: 2026-06-04_win_by_archetype.csv, 2026-06-04_win_model.png
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

warnings.filterwarnings("ignore", category=RuntimeWarning)
HERE = Path(__file__).resolve().parent.parent / "outputs"
SEED = 42

NUM_FEATS = ["log_size", "n_mat_types", "BOX_i", "PW_yes", "PW_unknown",
             "prop_MIX_TN", "prop_GRADE_CY", "prop_BASE_TN", "prop_SHLDR_TN",
             "prop_MILL_SY", "prop_STOCK_TN", "has_quantity_i"]
CAT_FEATS = ["State", "rule_archetype"]
WIN_WELL = {"Excellent Win", "Acceptable Win"}


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
    bid = df[df["CSI_Participated"] == True].copy()
    y = bid["CSI_Won"].astype(int).values
    print(f"Bid projects: {len(bid)} | wins: {y.sum()} ({y.mean()*100:.1f}%)")

    pre = ColumnTransformer([
        ("num", Pipeline([("imp", SimpleImputer(strategy="median")), ("sc", StandardScaler())]), NUM_FEATS),
        ("cat", OneHotEncoder(handle_unknown="ignore", min_frequency=10), CAT_FEATS),
    ])
    cv = StratifiedKFold(5, shuffle=True, random_state=SEED)
    print("\n-- 5-fold CV win model (out-of-fold) — small N, report honestly --")
    for name, clf in [("logistic", LogisticRegression(max_iter=2000, class_weight="balanced")),
                      ("hist_gb", HistGradientBoostingClassifier(random_state=SEED))]:
        pipe = Pipeline([("pre", pre), ("clf", clf)])
        p = cross_val_predict(pipe, bid, y, cv=cv, method="predict_proba")[:, 1]
        print(f"  {name:9s}  ROC-AUC={roc_auc_score(y,p):.3f}  PR-AUC={average_precision_score(y,p):.3f}"
              f"  (baseline PR={y.mean():.3f})")

    # ── Gap overlay by archetype (the headline of WS-2) ───────────────────────
    bid["is_win"] = bid["CSI_Won"] == True
    bid["is_bomb"] = bid["CSI_Bid_Quality"] == "Bomb"
    bid["is_win_well"] = bid["CSI_Bid_Quality"].isin(WIN_WELL)

    def summarize(gcol):
        g = bid.groupby(gcol).agg(
            n_bid=("is_win", "size"),
            win_rate=("is_win", "mean"),
            win_well_rate=("is_win_well", "mean"),
            bomb_rate=("is_bomb", "mean"),
            med_size=("Project_Size_Dollars", "median"),
        )
        g["bomb_share_of_wins"] = (bid[bid["is_win"]].groupby(gcol)["is_bomb"].mean())
        for c in ["win_rate", "win_well_rate", "bomb_rate", "bomb_share_of_wins"]:
            g[c] = (g[c] * 100).round(1)
        g["med_size"] = g["med_size"].round(0)
        return g.sort_values("win_well_rate", ascending=False)

    by_rule = summarize("rule_archetype")
    by_cluster = summarize("cluster_label")
    print("\n-- WS-2 gap overlay by RULE archetype --")
    print(by_rule.to_string())
    print("\n-- WS-2 gap overlay by DISCOVERED cluster --")
    print(by_cluster.to_string())
    by_rule.to_csv(HERE / "2026-06-04_win_by_archetype.csv")

    # plot: win-well vs bomb rate by rule archetype
    fig, ax = plt.subplots(figsize=(9, 6))
    g = by_rule
    ax.scatter(g["bomb_rate"], g["win_well_rate"], s=g["n_bid"]*1.5, alpha=0.6, color="teal")
    for name, r in g.iterrows():
        ax.annotate(f"{name}\n(n={r['n_bid']})", (r["bomb_rate"], r["win_well_rate"]),
                    fontsize=8, ha="center", va="center")
    ax.set_xlabel("Bomb rate — won but overpaid (% of bids)")
    ax.set_ylabel("Win-well rate — won, priced tight (% of bids)")
    ax.set_title("WS-2: where CSI wins WELL vs BOMBS, by archetype\n(bubble = # bids; upper-left = healthy, lower-right = leaky)")
    fig.tight_layout(); fig.savefig(HERE / "2026-06-04_win_model.png", dpi=130)
    print("\nWrote 2026-06-04_win_model.png")


if __name__ == "__main__":
    main()
