"""
CSI Sweet-Spot Analysis — Step 5: headline sweet-spot map
=========================================================
Combines Q1 (bid-rate, WS-1) and Q2 (win-well rate, WS-2) into one
archetype-faceted 2x2, with the bomb (overpay) overlay as color. Locates:
  - SWEET SPOT  : high bid-rate + high win-well rate
  - LEAK / avoid: low win-well + high bomb-share

Input : 2026-06-04_project_base.csv + 2026-06-04_project_archetypes.csv
Output: 2026-06-04_sweetspot_summary.csv, 2026-06-04_sweetspot_map.png
"""

import warnings
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

warnings.filterwarnings("ignore", category=RuntimeWarning)
HERE = Path(__file__).resolve().parent.parent / "outputs"
WIN_WELL = {"Excellent Win", "Acceptable Win"}


def main():
    base = pd.read_csv(HERE / "2026-06-04_project_base.csv")
    arch = pd.read_csv(HERE / "2026-06-04_project_archetypes.csv")
    df = base.merge(arch, on="Contract_Id", how="left")

    df["is_win"] = df["CSI_Won"] == True
    df["is_bomb"] = df["CSI_Bid_Quality"] == "Bomb"
    df["is_win_well"] = df["CSI_Bid_Quality"].isin(WIN_WELL)

    rows = []
    for name, g in df.groupby("rule_archetype"):
        bid = g[g["CSI_Participated"] == True]
        wins = bid[bid["is_win"]]
        rows.append(dict(
            archetype=name,
            n_projects=len(g),
            bid_rate=g["CSI_Participated"].mean() * 100,
            n_bid=len(bid),
            win_rate=bid["is_win"].mean() * 100 if len(bid) else np.nan,
            win_well_rate=bid["is_win_well"].mean() * 100 if len(bid) else np.nan,
            bomb_rate=bid["is_bomb"].mean() * 100 if len(bid) else np.nan,
            bomb_share_of_wins=wins["is_bomb"].mean() * 100 if len(wins) else np.nan,
            med_size_dollars=g["Project_Size_Dollars"].median(),
        ))
    s = pd.DataFrame(rows).round(1).sort_values("bid_rate", ascending=False)
    s.to_csv(HERE / "2026-06-04_sweetspot_summary.csv", index=False)
    print(s.to_string(index=False))

    # Headline 2x2: bid-rate (x) vs win-well rate (y), color = bomb-share, size = n_bid
    plot = s[s["archetype"] != "Unknown/NoQty"].copy()
    bx, by = plot["bid_rate"].median(), plot["win_well_rate"].median()
    fig, ax = plt.subplots(figsize=(10, 7))
    sc = ax.scatter(plot["bid_rate"], plot["win_well_rate"],
                    s=plot["n_bid"] * 3, c=plot["bomb_share_of_wins"],
                    cmap="RdYlGn_r", vmin=20, vmax=75, alpha=0.85, edgecolor="k")
    for _, r in plot.iterrows():
        ax.annotate(r["archetype"], (r["bid_rate"], r["win_well_rate"]),
                    fontsize=9, fontweight="bold", ha="center",
                    xytext=(0, 12), textcoords="offset points")
    ax.axvline(bx, ls=":", c="gray"); ax.axhline(by, ls=":", c="gray")
    ax.set_xlabel("Q1 — CSI bid rate (% of available projects it bids)")
    ax.set_ylabel("Q2 — win-well rate (% of bids won at a tight price)")
    ax.set_title("CSI competitive sweet spot, by archetype\n"
                 "upper-right = bid often & win well (lean in) · "
                 "color = % of wins that are BOMBS (overpaid)")
    cb = fig.colorbar(sc); cb.set_label("bomb share of wins (%)  — red = leaky")
    # quadrant note
    ax.text(0.98, 0.02, "bubble size = # bids", transform=ax.transAxes,
            ha="right", va="bottom", fontsize=8, color="gray")
    fig.tight_layout(); fig.savefig(HERE / "2026-06-04_sweetspot_map.png", dpi=140)
    print("\nWrote 2026-06-04_sweetspot_map.png + 2026-06-04_sweetspot_summary.csv")

    # correlation: does CSI bid most where it wins well?
    p = s[s["archetype"] != "Unknown/NoQty"]
    print(f"\nCorr(bid_rate, win_well_rate) across archetypes: "
          f"{p['bid_rate'].corr(p['win_well_rate']):.2f}  "
          f"(positive => selection is well-calibrated at archetype level)")


if __name__ == "__main__":
    main()
