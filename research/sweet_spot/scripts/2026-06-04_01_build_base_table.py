"""
CSI Sweet-Spot Analysis — Step 1: clean project-level base table
================================================================
Collapses the bid-level master (one row per project x bidder) to ONE ROW PER
PROJECT, with parsed numeric tonnage, material-mix proportions, complexity
proxies, and CSI's own outcome (rank / bid-quality / gap-to-winner).

Input : 2026-06-03_csi_bid_master.csv   (READ ONLY)
Output: 2026-06-04_project_base.csv     (one row per Contract_Id)

Quantity columns are project-level (constant across a project's bidders), so a
project-level collapse is loss-free for them. CSI-specific outcome fields are
pulled from CSI's bidder row (Is_CSI == TRUE).
"""

import re
from pathlib import Path
import numpy as np
import pandas as pd

HERE = Path(__file__).parent
SRC = HERE.parents[2] / "01_data" / "2026-06-03_csi_bid_master.csv"   # <repo>/01_data/
OUT = HERE.parent / "outputs" / "2026-06-04_project_base.csv"

MAT_COLS = ["MIX_TN", "GRADE_CY", "BASE_TN", "SHLDR_TN", "MILL_SY", "CRUSH_TN", "STOCK_TN"]


def to_num(s: pd.Series) -> pd.Series:
    """Parse comma-thousand strings ('20,626') to float; blanks -> NaN."""
    return pd.to_numeric(s.str.replace(",", "", regex=False).str.strip().replace("", np.nan), errors="coerce")


def to_bool(s: pd.Series) -> pd.Series:
    return s.str.strip().str.upper().map({"TRUE": True, "FALSE": False})


def first_nonblank(s: pd.Series):
    nb = s[s.astype(str).str.strip() != ""]
    return nb.iloc[0] if len(nb) else ""


def main():
    df = pd.read_csv(SRC, dtype=str, keep_default_na=False)
    print(f"Loaded master: {len(df):,} rows x {df.shape[1]} cols")

    # -- Clean rows ------------------------------------------------------------
    n0 = len(df)
    df = df[df["Contract_Id"].str.strip() != ""].copy()
    print(f"Dropped {n0 - len(df)} null-Contract_Id rows -> {len(df):,}")

    n1 = len(df)
    df = df.drop_duplicates(subset=["Contract_Id", "Bidder_Clean_Name"], keep="first")
    print(f"Dropped {n1 - len(df)} duplicate (project,bidder) rows -> {len(df):,}")

    # Numeric tonnage on the bid-level frame (constant within a project)
    for c in MAT_COLS:
        df[c + "_num"] = to_num(df[c])

    # -- CSI's own outcome row (for gap overlay) -------------------------------
    df["_is_csi"] = to_bool(df["Is_CSI"])
    csi = df[df["_is_csi"] == True][
        ["Contract_Id", "Bid_Quality", "Margin_Pct", "Bid_Rank", "Bid_Amount", "Is_Winner"]
    ].rename(columns={
        "Bid_Quality": "CSI_Bid_Quality",
        "Margin_Pct": "CSI_Margin_Pct",
        "Bid_Rank": "CSI_Row_Bid_Rank",
        "Bid_Amount": "CSI_Row_Bid_Amount",
        "Is_Winner": "CSI_Row_Is_Winner",
    })
    csi = csi.drop_duplicates("Contract_Id")
    # Authoritative "CSI won": CSI's own bid row ranked 1st. The project-level
    # CSI_Won_Project flag disagrees on ~13 projects (re-bids / stale flag) — keep
    # both; use CSI_Won (row-derived) downstream.
    csi["CSI_Won"] = to_bool(csi["CSI_Row_Is_Winner"])

    # -- Collapse to one row per project --------------------------------------
    proj_cols = [
        "Contract_Id", "Project_Name", "State", "County", "City",
        "Latitude", "Longitude", "Standard_Region", "CSI_Region",
        "Date", "Bid_Year", "Bid_Quarter",
        "Project_Size_Dollars", "Num_Valid_Bidders", "Num_Bidders",
        "Market_Tightness_Category", "Winner_Amount", "Second_Place_Amount",
        "CSI_Participated", "CSI_Won_Project", "CSI_Bid_Rank",
        "BOX", "PREVAILING_WAGES",
    ] + [c + "_num" for c in MAT_COLS]

    g = df.groupby("Contract_Id", sort=False)
    proj = g[[c for c in proj_cols if c != "Contract_Id"]].agg(first_nonblank).reset_index()
    print(f"Collapsed to {len(proj):,} unique projects")

    proj = proj.merge(csi, on="Contract_Id", how="left")

    # -- Typed / derived fields -----------------------------------------------
    for c in ["Project_Size_Dollars", "Num_Valid_Bidders", "Num_Bidders",
              "Winner_Amount", "Second_Place_Amount", "CSI_Bid_Rank",
              "CSI_Margin_Pct"] + [c + "_num" for c in MAT_COLS]:
        proj[c] = pd.to_numeric(proj[c].astype(str).str.replace(",", "", regex=False)
                                .str.strip().replace("", np.nan), errors="coerce")

    proj["CSI_Participated"] = to_bool(proj["CSI_Participated"])
    proj["CSI_Won_Project"] = to_bool(proj["CSI_Won_Project"])
    proj["BOX"] = (proj["BOX"].str.strip().str.upper() == "X")
    proj["PREVAILING_WAGES"] = proj["PREVAILING_WAGES"].str.strip().str.upper().map(
        {"YES": True, "NO": False})  # NaN where unknown

    # Material-mix features: count of present types + normalized proportions
    num_cols = [c + "_num" for c in MAT_COLS]
    present = proj[num_cols].notna() & (proj[num_cols] > 0)
    proj["n_mat_types"] = present.sum(axis=1)
    proj["has_quantity"] = proj["n_mat_types"] > 0

    tot = proj[num_cols].fillna(0).sum(axis=1)
    for c in MAT_COLS:
        # proportion of total tonnage/quantity; NaN for quantity-empty projects
        proj["prop_" + c] = np.where(tot > 0, proj[c + "_num"].fillna(0) / tot, np.nan)
    proj["total_quantity"] = np.where(tot > 0, tot, np.nan)

    # -- Verify ----------------------------------------------------------------
    print("\n-- Verification --")
    print(f"  projects:            {len(proj):,}  (expect 1,591)")
    vc = proj["CSI_Participated"].value_counts(dropna=False)
    nbid = int(vc.get(True, 0))
    print(f"  CSI bid / no-bid:    {nbid} / {int(vc.get(False,0))}  (expect 603 / 988)")
    nwon_row = int((proj["CSI_Won"] == True).sum())
    nwon_flag = int((proj["CSI_Won_Project"] == True).sum())
    print(f"  CSI won (row-derived): {nwon_row}  | flag CSI_Won_Project: {nwon_flag}  (disagree on ~13)")
    print(f"  Win rate when bidding: {nwon_row/nbid*100:.1f}%  (NOT 70% — inventory's 421 was a row count)")
    print(f"  has_quantity:        {int(proj['has_quantity'].sum())} ({proj['has_quantity'].mean()*100:.1f}%)  (expect ~85%)")
    print(f"  MIX_TN_num median:   {proj['MIX_TN_num'].median():,.0f}  (expect ~5,900)")
    print(f"  CSI_Bid_Quality set: {sorted(proj.loc[proj['CSI_Participated']==True,'CSI_Bid_Quality'].dropna().unique())}")
    miss_qual = ((proj["CSI_Participated"] == True) & (proj["CSI_Bid_Quality"].fillna("") == "")).sum()
    print(f"  bid projects missing CSI_Bid_Quality: {miss_qual}")

    proj.to_csv(OUT, index=False)
    print(f"\nWrote {OUT.name}: {len(proj):,} rows x {proj.shape[1]} cols")


if __name__ == "__main__":
    main()
