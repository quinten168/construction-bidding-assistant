"""
CSI Sweet-Spot — Is "Large Volume = MIX_TN > 10,000" defensible?
================================================================
The "Large Volume" archetype boundary (2026-06-04_02_archetypes.py:61) is a
HARDCODED domain guess copied from CLAUDE.md ("high MIX TN (>10,000 tons)"). It
was never derived from the data. This script asks the data where "large" actually
begins for the projects CSI bids on, using methods straight from the MSBA EDA 6411
curriculum, and reports whether 10k is defensible.

Methods (course-grounded):
  - Descriptive distribution + skewness + log-transform   (EDA 6411 Wk 1-3)
  - Upper-tail fences: 1.5xIQR and mean+3sigma             (EDA 6411 Wk 6/7 Anomaly Detection)
  - 1-D K-means + silhouette sweep on log(MIX)             (EDA 6411 Wk 5 Clustering;
                                                            mirrors 02_archetypes.py:84-99)
  - Gaussian Mixture by BIC (soft-boundary alternative)    (EDA 6411 Wk 5)
  - KDE antimode (density valley) as a visual cross-check
Then: percentile candidates, outcome-linkage binning (does behavior shift at the
line?), regional stratification, and a synthesis table with a verdict.

SCOPE: analysis + presentation only. This does NOT change the live 10_000 threshold.
Read-only on data (reads the derived base table, never raw).

Input : 2026-06-04_project_base.csv          (one row per project; built by step 01)
Output: 2026-06-15_tonnage_distribution.png  (4-panel distribution + outcome figure)
        2026-06-15_threshold_candidates.csv  (synthesis table; consumed by dashboard pg 8)
        2026-06-15_tonnage_binned.csv         (tonnage band x outcome; consumed by dashboard pg 8)

Run with the interpreter that has pandas/sklearn/scipy/matplotlib:
    /usr/bin/python3 02_modules/sweet_spot/scripts/2026-06-15_large_project_threshold_analysis.py
"""

from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from scipy import stats
from sklearn.preprocessing import StandardScaler
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score
from sklearn.mixture import GaussianMixture

HERE = Path(__file__).resolve().parent.parent / "outputs"
BASE = HERE / "2026-06-04_project_base.csv"
OUT_PNG = HERE / "2026-06-15_tonnage_distribution.png"
OUT_CAND = HERE / "2026-06-15_threshold_candidates.csv"
OUT_BINNED = HERE / "2026-06-15_tonnage_binned.csv"

CURRENT = 10_000.0           # the threshold under test
WIN_WELL = {"Excellent Win", "Acceptable Win"}   # matches dashboard/utils/data.py:36
SEED = 42


def pct_rank(series: pd.Series, value: float) -> float:
    """Percentile of `value` within `series` (share strictly below)."""
    return float((series < value).mean() * 100)


def main():
    df = pd.read_csv(BASE)
    # ----- populations -------------------------------------------------------
    # tonnage is only meaningful for projects that have asphalt; "Large Volume"
    # is an asphalt-tonnage label, so we study MIX_TN_num > 0.
    has_mix = df["MIX_TN_num"] > 0
    allm = df.loc[has_mix].copy()
    bid = df.loc[has_mix & (df["CSI_Participated"] == True)].copy()
    m = bid["MIX_TN_num"].astype(float)          # PRIMARY series: CSI's asphalt bids
    m_all = allm["MIX_TN_num"].astype(float)      # OVERLAY: whole market w/ asphalt
    logm = np.log10(m.values)

    print("=" * 72)
    print("CSI 'Large Volume' threshold — data-derived confirmation")
    print("=" * 72)
    print(f"Projects total: {len(df):,}  |  with asphalt (MIX_TN>0): all={len(allm):,}  bid={len(bid):,}")
    print(f"({int((df['CSI_Participated']==True).sum())} bid projects total; "
          f"{int((df['CSI_Participated']==True).sum()) - len(bid)} of them carry NO asphalt tonnage)")

    # ----- (1) descriptive distribution -------------------------------------
    print("\n-- (1) Distribution of MIX_TN among CSI's asphalt bids --")
    desc = m.describe()
    print(desc.round(0).to_string())
    print(f"  skewness raw = {stats.skew(m):.2f}   skewness log10 = {stats.skew(logm):.2f}")
    pcts = [10, 25, 50, 75, 90, 95, 99]
    pctvals = {p: float(np.percentile(m, p)) for p in pcts}
    print("  percentiles:", {p: round(v) for p, v in pctvals.items()})
    print(f"\n  >>> 10,000 sits at the {pct_rank(m, CURRENT):.0f}th percentile of CSI's asphalt bids")
    print(f"  >>> {(m > CURRENT).mean()*100:.0f}% of asphalt bids EXCEED 10k  "
          f"(vs {(m_all > CURRENT).mean()*100:.0f}% of the whole market)")

    # ----- (2) log-normality -------------------------------------------------
    # Anderson-Darling on the logs: if log looks normal, tonnage is ~log-normal,
    # so all break-finding should run on log scale.
    ad = stats.anderson(logm, dist="norm")
    crit = dict(zip(ad.significance_level, ad.critical_values))
    is_lognorm = ad.statistic < crit.get(5.0, np.inf)
    print(f"\n-- (2) Log-normality (Anderson-Darling on log10) --")
    print(f"  A^2 = {ad.statistic:.2f}  (5% crit = {crit.get(5.0):.2f}) -> "
          f"{'log-normal-ish (work on log scale)' if is_lognorm else 'not strictly normal, but log is far less skewed'}")

    # ----- (3) upper-tail fences (anomaly-detection methods) ----------------
    q1, q3 = np.percentile(m, [25, 75])
    iqr = q3 - q1
    iqr_fence = q3 + 1.5 * iqr                       # textbook "unusually large"
    sigma3_raw = float(m.mean() + 3 * m.std())        # inflated by right skew
    sigma3_log = float(10 ** (logm.mean() + 3 * logm.std()))
    print("\n-- (3) Upper-tail fences (EDA anomaly detection) --")
    print(f"  1.5xIQR upper fence : {iqr_fence:,.0f} TN")
    print(f"  mean+3sigma (raw)   : {sigma3_raw:,.0f} TN   (skew-inflated; shown for completeness)")
    print(f"  mean+3sigma (log)   : {sigma3_log:,.0f} TN")

    # ----- (4) natural breaks: 1-D K-means + silhouette ---------------------
    X = logm.reshape(-1, 1)
    Xs = StandardScaler().fit_transform(X)
    print("\n-- (4a) K-means on log(MIX): silhouette sweep (mirrors 02_archetypes.py) --")
    best_k, best_s, best_km = None, -1.0, None
    for k in range(2, 6):
        km = KMeans(n_clusters=k, n_init=25, random_state=SEED).fit(Xs)
        s = silhouette_score(Xs, km.labels_)
        print(f"   k={k}: silhouette={s:.3f}")
        if s > best_s:
            best_k, best_s, best_km = k, s, km
    print(f"   -> chose k={best_k} (silhouette={best_s:.3f})")
    # boundary between the TWO highest clusters = midpoint of their centroids (log space)
    centers_log = sorted(best_km.cluster_centers_.ravel())            # standardized
    sc = StandardScaler().fit(X)
    centers_tn = (10 ** sc.inverse_transform(np.array(centers_log).reshape(-1, 1)).ravel())
    kmeans_break = float(10 ** ((np.log10(centers_tn[-1]) + np.log10(centers_tn[-2])) / 2))
    # empirical: smallest member of the top cluster
    top_lab = int(np.argmax(best_km.cluster_centers_.ravel()))
    top_min = float(m.values[best_km.labels_ == top_lab].min())
    print(f"   cluster centers (TN): {[round(c) for c in centers_tn]}")
    print(f"   top-two boundary (midpoint, log): {kmeans_break:,.0f} TN  | empirical min of top cluster: {top_min:,.0f} TN")

    # ----- (4b) GMM by BIC ---------------------------------------------------
    print("\n-- (4b) Gaussian Mixture on log(MIX): BIC model selection --")
    best_g, best_bic, best_n = None, np.inf, None
    for n in range(1, 5):
        g = GaussianMixture(n_components=n, random_state=SEED, n_init=5).fit(X)
        bic = g.bic(X)
        print(f"   n={n}: BIC={bic:.0f}")
        if bic < best_bic:
            best_g, best_bic, best_n = g, bic, n
    if best_n >= 2:
        grid = np.linspace(logm.min(), logm.max(), 4000).reshape(-1, 1)
        comp = best_g.predict(grid)
        hi = int(np.argmax(best_g.means_.ravel()))
        switch = np.where(comp == hi)[0]
        gmm_cross = float(10 ** grid[switch[0], 0]) if len(switch) else np.nan
        print(f"   -> {best_n} components; crossover into the top component at {gmm_cross:,.0f} TN")
    else:
        gmm_cross = np.nan
        print("   -> BIC prefers 1 component: the data is a single smooth tail, no distinct 'large' mode.")

    # ----- (4c) KDE antimode -------------------------------------------------
    kde = stats.gaussian_kde(logm)
    grid = np.linspace(logm.min(), logm.max(), 2000)
    dens = kde(grid)
    valleys = [grid[i] for i in range(1, len(grid) - 1)
               if dens[i] < dens[i - 1] and dens[i] < dens[i + 1]]
    kde_antimode = float(10 ** max(valleys)) if valleys else np.nan
    print(f"\n-- (4c) KDE antimode (density valley) --  {('%.0f TN' % kde_antimode) if valleys else 'none (unimodal)'}")

    # ----- (5) outcome-linkage binning --------------------------------------
    # does competitive behavior actually shift with tonnage? (decision-support,
    # conditional on bidding). Reuse dashboard win-well / bomb definitions.
    bid = bid.copy()
    bid["is_win_well"] = bid["CSI_Bid_Quality"].isin(WIN_WELL)
    bid["is_bomb"] = bid["CSI_Bid_Quality"] == "Bomb"
    bid["margin"] = pd.to_numeric(bid["CSI_Margin_Pct"], errors="coerce")
    bid["n_comp"] = pd.to_numeric(bid["Num_Valid_Bidders"], errors="coerce")
    edges = [0, 5_000, 10_000, 20_000, 40_000, np.inf]
    labels = ["<5k", "5-10k", "10-20k", "20-40k", ">40k"]
    bid["band"] = pd.cut(bid["MIX_TN_num"], bins=edges, labels=labels, right=False)
    binned = bid.groupby("band", observed=True).agg(
        n=("Contract_Id", "size"),
        win_well_rate=("is_win_well", lambda s: round(s.mean() * 100, 1)),
        bomb_rate=("is_bomb", lambda s: round(s.mean() * 100, 1)),
        med_margin=("margin", lambda s: round(s.median(), 1)),
        med_competitors=("n_comp", lambda s: round(s.median(), 1)),
        med_mix=("MIX_TN_num", lambda s: round(s.median())),
    ).reset_index()
    binned.to_csv(OUT_BINNED, index=False)
    print("\n-- (5) Outcome by tonnage band (bid projects; conditional on bidding) --")
    print(binned.to_string(index=False))

    # ----- (6) regional stratification --------------------------------------
    print("\n-- (6) Is 'large' state-relative? (median / P90 of MIX_TN by state) --")
    reg = bid.groupby("State")["MIX_TN_num"].agg(
        n="size", median="median", p90=lambda s: float(np.percentile(s, 90))).round(0)
    reg = reg[reg["n"] >= 10].sort_values("median", ascending=False)
    print(reg.to_string())

    # ----- (7) synthesis table ----------------------------------------------
    cands = [
        ("Current rule (10k)", CURRENT, "hardcoded domain guess"),
        ("P75", pctvals[75], "upper-quartile reference"),
        ("P90", pctvals[90], "top-decile reference"),
        ("P95", pctvals[95], "top-5% reference"),
        ("1.5xIQR upper fence", iqr_fence, "EDA anomaly: unusually large"),
        ("mean+3sigma (log)", sigma3_log, "EDA anomaly: log-scale 3-sigma"),
        ("K-means break (k=%d)" % best_k, kmeans_break, "EDA clustering: top-two boundary"),
        ("GMM crossover", gmm_cross, "EDA clustering: soft boundary"),
        ("KDE antimode", kde_antimode, "density valley"),
    ]
    rows = []
    for name, thr, note in cands:
        if thr is None or (isinstance(thr, float) and np.isnan(thr)):
            rows.append(dict(candidate=name, threshold_tn=np.nan, pctile_in_bid=np.nan,
                             pct_bid_above=np.nan, pct_market_above=np.nan, note=note))
            continue
        rows.append(dict(
            candidate=name,
            threshold_tn=round(float(thr)),
            pctile_in_bid=round(pct_rank(m, thr)),
            pct_bid_above=round(float((m > thr).mean()) * 100, 1),
            pct_market_above=round(float((m_all > thr).mean()) * 100, 1),
            note=note))
    cand_df = pd.DataFrame(rows)
    cand_df.to_csv(OUT_CAND, index=False)
    print("\n-- (7) Threshold candidates (vs the current 10k) --")
    print(cand_df.to_string(index=False))

    # ----- figure ------------------------------------------------------------
    _figure(m, m_all, logm, dens, grid, kde, binned, labels,
            kmeans_break, iqr_fence, pctvals)

    print(f"\nWrote:\n  {OUT_PNG.name}\n  {OUT_CAND.name}\n  {OUT_BINNED.name}")
    print("\nScope: analysis only — the live 10_000 in 02_archetypes.py is unchanged.")


def _figure(m, m_all, logm, dens, grid, kde, binned, labels,
            kmeans_break, iqr_fence, pctvals):
    fig, ax = plt.subplots(2, 2, figsize=(13, 9))

    # (a) raw histogram, bid vs market, with threshold lines
    a = ax[0, 0]
    a.hist(m_all, bins=40, range=(0, 80000), alpha=0.35, color="#bdbdbd",
           density=True, label=f"market w/ asphalt (n={len(m_all)})")
    a.hist(m, bins=40, range=(0, 80000), alpha=0.65, color="#2c7fb8",
           density=True, label=f"CSI asphalt bids (n={len(m)})")
    for x, c, ls in [(10000, "#d73027", "-"), (kmeans_break, "#1a9850", "--"),
                     (pctvals[90], "#7b3294", ":")]:
        a.axvline(x, color=c, ls=ls, lw=2)
    a.set_title("(a) MIX_TN distribution — bid vs market")
    a.set_xlabel("MIX_TN (tons)"); a.set_ylabel("density"); a.legend(fontsize=8)
    a.text(10000, a.get_ylim()[1]*0.92, " 10k (current)", color="#d73027", fontsize=8)
    a.text(kmeans_break, a.get_ylim()[1]*0.80, " K-means", color="#1a9850", fontsize=8)
    a.text(pctvals[90], a.get_ylim()[1]*0.68, " P90", color="#7b3294", fontsize=8)

    # (b) log histogram + KDE
    b = ax[0, 1]
    b.hist(logm, bins=30, density=True, alpha=0.55, color="#2c7fb8")
    b.plot(grid, dens, color="#1f4e79", lw=2, label="KDE")
    for x, c in [(10000, "#d73027"), (kmeans_break, "#1a9850")]:
        b.axvline(np.log10(x), color=c, ls="--", lw=2)
    b.set_title("(b) log10(MIX_TN) — skew %.2f→%.2f" % (stats.skew(m), stats.skew(logm)))
    b.set_xlabel("log10(MIX_TN)"); b.set_ylabel("density"); b.legend(fontsize=8)

    # (c) ECDF with 10k marked
    c = ax[1, 0]
    xs = np.sort(m.values); ys = np.arange(1, len(xs) + 1) / len(xs)
    c.plot(xs, ys, color="#2c7fb8", lw=2)
    c.axvline(10000, color="#d73027", ls="--", lw=2)
    p10k = float((m < 10000).mean())
    c.axhline(p10k, color="#d73027", ls=":", lw=1)
    c.set_title("(c) ECDF — 10k is the %.0fth pctile of CSI's asphalt bids" % (p10k*100))
    c.set_xlabel("MIX_TN (tons)"); c.set_ylabel("cumulative share")
    c.set_xlim(0, 80000)
    c.text(11000, p10k - 0.06, " %.0f%% below 10k" % (p10k*100), color="#d73027", fontsize=8)

    # (d) outcome vs tonnage band
    d = ax[1, 1]
    bb = binned[binned["band"].isin(labels)]
    xpos = np.arange(len(bb))
    d.bar(xpos - 0.2, bb["win_well_rate"], width=0.4, color="#1a9850", label="win-well %")
    d.bar(xpos + 0.2, bb["bomb_rate"], width=0.4, color="#d73027", label="bomb %")
    d.set_xticks(xpos); d.set_xticklabels(bb["band"], fontsize=9)
    for i, n in enumerate(bb["n"]):
        d.text(i, 1, f"n={n}", ha="center", va="bottom", fontsize=7, color="#555")
    d.axvline(1.5, color="#d73027", ls="--", lw=1.5)   # the 10k boundary sits between 5-10k and 10-20k
    d.set_title("(d) Outcome by tonnage band (does behavior shift at 10k?)")
    d.set_xlabel("MIX_TN band"); d.set_ylabel("% of bids in band"); d.legend(fontsize=8)

    fig.suptitle("Where does 'Large Volume' actually begin? — CSI asphalt-bid tonnage",
                 fontsize=13, fontweight="bold")
    fig.tight_layout(rect=[0, 0, 1, 0.97])
    fig.savefig(OUT_PNG, dpi=130)


if __name__ == "__main__":
    main()
