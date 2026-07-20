"""
2026-06-17  Base-intensity -> CSI edge validation  (READ-ONLY analysis, no production code touched)

THE QUESTION WE ARE ANSWERING
-----------------------------
Earlier we asked: "should the work-type rule (rows 1 & 2) use BASE in its
distinguishing logic?"  The distribution said BASE does NOT discriminate work-TYPE
(it is present in 85-95% of all paving jobs and its magnitude does not separate
Reconstruct from Mill & Overlay).  BUT a rough, noisy run hinted that base
*intensity* might track CSI's margin (the "edge").  That earlier run used an
arbitrary bidder's margin, not CSI's own -- so it cannot be trusted.

This script re-runs that check CLEANLY, on CSI's OWN bid rows only, so the margin /
win / bomb numbers are genuinely CSI's outcomes.  The verdict here decides ONE thing:
is base intensity a real edge signal worth feeding the model, or noise we drop?

It changes nothing in production -- it only reads the master CSV and writes one
dated scorecard CSV.  The work-type rule, the dashboard, and the schema are untouched.
"""

from pathlib import Path
import pandas as pd
import numpy as np

# --- paths (this script lives in sweet_spot/scripts/; outputs sit one level up) -------------------
HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]                                    # .../01_Summer_2026
MASTER_CSV = REPO / "01_data" / "2026-06-03_csi_bid_master.csv"
OUT_DIR = HERE.parent / "outputs"
OUT_CSV = OUT_DIR / "2026-06-17_base_intensity_edge_scorecard.csv"

# --- the 5 quantity flags the work-type rule keys on (native units; we DO NOT change the rule) -----
MAT = ["MIX_TN", "GRADE_CY", "BASE_TN", "SHLDR_TN", "MILL_SY", "CRUSH_TN", "STOCK_TN"]

# --- CSI "won well" vs "bomb" buckets -- same definitions the dashboard uses (utils/data.py) -------
WIN_WELL = {"Excellent Win", "Acceptable Win"}


def to_num(s: pd.Series) -> pd.Series:
    """Parse CSI's hand-typed numbers: strip $ and thousands-commas, blanks -> NaN.
    Same parsing the dashboard uses, so our numbers line up with the console."""
    return pd.to_numeric(
        s.astype(str).str.replace(",", "", regex=False)
                     .str.replace("$", "", regex=False)
                     .str.strip().replace("", np.nan),
        errors="coerce",
    )


def work_type(r) -> str:
    """The CURRENT canonical work-type rule -- copied verbatim from the 3 synced
    functions so this analysis classifies projects exactly the way production does.
    We are validating base as an EDGE signal, NOT proposing to change this tree."""
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
    # --- step 1: load the master, keep CSI's OWN rows only -----------------------------------------
    # Each CSI row carries the project's quantities (a project attribute, repeated per bidder)
    # AND CSI's own bid outcome (margin / winner / quality).  That co-location is exactly what lets
    # us tie base intensity to CSI's edge without a noisy join.
    df = pd.read_csv(MASTER_CSV, dtype=str, low_memory=False)
    csi = df[df["Is_CSI"] == "TRUE"].copy()

    # A handful of projects have 2 CSI rows (joint ventures / dupes).  Keep the winning row if there
    # is one, else the first -- this reproduces the canonical 603-bid / 117-win frame.
    csi["_win_sort"] = (csi["Is_Winner"] == "TRUE").astype(int)
    csi = (csi.sort_values("_win_sort", ascending=False)
              .drop_duplicates("Contract_Id"))

    # --- step 2: parse the numbers we need ---------------------------------------------------------
    for c in MAT + ["Margin_Pct"]:
        csi[c + "_n"] = to_num(csi[c])

    # --- step 3: label each project's work-type (current rule) -------------------------------------
    csi["work_type"] = csi.apply(work_type, axis=1)

    # --- step 4: build the base-intensity signal under test ----------------------------------------
    # "Base intensity" = how much base + shoulder aggregate the job carries PER ton of hot mix.
    # We test it only on the paving universe (MIX > 0), because base-to-mix is undefined without mix
    # and the non-paving types (Grading, Aggregate) are a different conversation.
    csi["base_all"] = csi["BASE_TN_n"].fillna(0) + csi["SHLDR_TN_n"].fillna(0)
    pav = csi[csi["MIX_TN_n"].fillna(0) > 0].copy()
    pav["base_to_mix"] = pav["base_all"] / pav["MIX_TN_n"]

    # Cut into 4 readable bands.  Thresholds are intuitive (not yet optimized) -- the point of this
    # run is to SEE whether edge rises monotonically across the bands, not to tune the cut.
    pav["base_band"] = pd.cut(
        pav["base_to_mix"], [0, 0.05, 0.15, 0.50, np.inf],
        labels=["~0 incidental", "light", "moderate", "heavy"], include_lowest=True,
    )

    # --- step 5: CSI outcome flags (CSI's own row) -------------------------------------------------
    pav["is_win"] = pav["Is_Winner"] == "TRUE"
    pav["is_win_well"] = pav["Bid_Quality"].isin(WIN_WELL)
    pav["is_bomb"] = pav["Bid_Quality"] == "Bomb"

    def summarize(g: pd.DataFrame) -> pd.Series:
        """One row of edge metrics for a group of CSI bids."""
        return pd.Series({
            "n_bids": len(g),
            "win_rate_%": round(g["is_win"].mean() * 100, 1),
            "win_well_rate_%": round(g["is_win_well"].mean() * 100, 1),
            "bomb_rate_%": round(g["is_bomb"].mean() * 100, 1),
            "median_margin_%": round(g["Margin_Pct_n"].median() * 100, 2),
            "mean_margin_%": round(g["Margin_Pct_n"].mean() * 100, 2),
        })

    # --- step 6a: the headline test -- edge across base bands, ALL paving types pooled --------------
    overall = pav.groupby("base_band", observed=True).apply(summarize).reset_index()
    overall.insert(0, "work_type", "ALL PAVING")

    # --- step 6b: the strict test -- edge across base bands, WITHIN each work-type ------------------
    # This is the one that matters: if base intensity only looks predictive because heavy-base jobs
    # happen to be Reconstructs, the signal vanishes here.  If edge still rises within a type, base
    # carries information the type label does not.
    within = (pav.groupby(["work_type", "base_band"], observed=True)
                 .apply(summarize).reset_index())

    scorecard = pd.concat([overall, within], ignore_index=True)

    # --- step 7: write + print ---------------------------------------------------------------------
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    scorecard.to_csv(OUT_CSV, index=False)

    print(f"CSI paving bids analyzed: {len(pav)}  (of {len(csi)} total CSI bids)")
    print(f"scorecard -> {OUT_CSV}\n")
    print("=== EDGE BY BASE INTENSITY -- all paving types pooled ===")
    print(overall.to_string(index=False))
    print("\n=== EDGE BY BASE INTENSITY -- within each work-type (the strict test) ===")
    print(within.to_string(index=False))

    # --- step 8: a plain-language verdict prompt ---------------------------------------------------
    # We are NOT auto-deciding -- T reads the trend.  The question to answer from the table above:
    #   * Does median_margin_% / win_well_rate_% rise monotonically from "~0 incidental" -> "heavy"?
    #   * Does that rise SURVIVE inside Reconstruct and inside Mill & Overlay (within-type)?
    # If yes on both -> base intensity is a real edge signal (feed it to the margin model).
    # If it only shows up pooled but not within-type -> it was just proxying for work-type -> drop it.
    print("\nVERDICT RULE: base is a real edge signal ONLY if margin/win-well rises with the band "
          "AND that rise survives WITHIN work-type. Pooled-only rise = base was just proxying type.")


if __name__ == "__main__":
    main()
