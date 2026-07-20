# Is "Large Volume = MIX_TN > 10,000" defensible? — data-derived findings
*2026-06-15 · sweet_spot · analysis only (the live `10_000` is unchanged)*

## TL;DR — verdict: **keep 10k as the floor, but it's a "small-vs-large" divider, not a "big job" flag**

The 10,000-ton cutoff was a hardcoded domain guess (copied from CLAUDE.md, never
derived). Running the data through the EDA-6411 toolkit, **10k turns out to be
genuinely defensible as the natural boundary between CSI's two tonnage populations** —
but it is *not* an "unusually large / top-tier" line. It sits **below the median**
asphalt bid, so it labels the **majority** of CSI's asphalt bids "Large Volume." Where
CSI's competitive payoff actually concentrates is much higher, around **40k tons**.

| What the data says | Number |
|---|---|
| 10k's percentile among CSI's asphalt bids | **44th** (below the 15,120-ton median) |
| Share of CSI asphalt bids that **exceed** 10k | **56%** (vs 39% of the whole market) |
| **GMM crossover** (BIC-preferred 2-component split) | **9,236 t ≈ 10k** ✅ validates 10k as the natural divide |
| K-means (k=2, silhouette 0.64) top-two boundary | 5,940 t |
| Where win-well rate actually jumps | **>40k** (24% vs ~11% below) |
| "Large" P75 / P90 reference | 31,960 / 57,800 t |

## How to read this (the key reframe)

There are **two different questions** hiding inside "what is a large project," and they
have different answers:

1. **"Where do small jobs end and large jobs begin?"** → ~**9–10k**. The
   BIC-selected Gaussian Mixture (2 components, EDA Wk 5) splits the log-tonnage
   distribution into a small-job mode (~1–2k) and a large-job mode (~20–30k), with the
   **crossover at 9,236 t**. Panel (b) of the figure shows this bimodality directly.
   **10k is essentially right on that natural seam — so as a binary small/large divider
   it is data-validated, not arbitrary.**

2. **"Which jobs are *big* — the ones worth flagging?"** → ~**40k+**. Because 10k is
   only the 44th percentile, calling everything above it "Large Volume" tags 56% of
   CSI's asphalt bids — the label loses its punch. The competitive signal (panel d):
   - **Bomb rate** halves across 10k (≈11% below → 4–7% above) — modest support for 10k.
   - **Win-well rate** is flat (~7→11%) until **>40k, where it jumps to 24%**. That is
     where CSI's edge on big jobs really shows up.

## Evidence by method (all EDA-6411 grounded)

- **Distribution / skew (Wk 1–3).** Right-skewed (skew 1.81); `log10` nearly symmetric
  (−0.76) → treat as ~log-normal and do all break-finding on the log scale.
- **Upper-tail fences (Wk 6/7 anomaly detection).** 1.5×IQR upper fence = **75,443 t**;
  mean+3σ is degenerate on a heavy tail (raw 97k; log-3σ explodes to 1.36M) — a useful
  negative result: σ-based outlier rules don't define "large" well for log-normal
  tonnage; percentile/mixture methods do.
- **K-means + silhouette (Wk 5; mirrors `02_archetypes.py:84-99`).** k=2 wins
  (silhouette 0.64); centers 1,344 and 26,259 t; boundary ~5,940 t.
- **GMM by BIC (Wk 5).** 2 components beat 1 (BIC 796 vs 882) → a real second mode
  exists; **crossover 9,236 t**. This is the single strongest vindication of ~10k.
- **KDE antimode.** None — the two modes overlap enough that the summed density has no
  visible valley (so the split is "soft," consistent with GMM over hard K-means).

## Two caveats that change how the label should be used

1. **"Large" is strongly state-relative.** Median asphalt bid by state: ND **8,942**,
   MN **15,435**, SD **29,513**, IA **30,403**. A single national 10k means "above
   median" in ND but "small" in SD. A state-aware floor (or a within-state percentile)
   would be more honest — relevant because CSI's haul economics already differ by state
   (MN pit-dependent, ND supplier-aggregate).
2. **207 of 603 bid projects carry no asphalt at all.** "Large Volume" is a MIX-tonnage
   label, so it is undefined for earthwork/base/shoulder-only jobs (a third of CSI's
   bids). Those are correctly captured by the *other* archetypes — but it means
   "Large Volume" only ever describes the 396 asphalt bids, not the full book.

## Recommendation

- **Keep `MIX_TN > 10_000` as the "Large Volume" floor.** It coincides with the
  data's natural small-vs-large seam (GMM 9.2k), so it is defensible and needs no
  apology in the writeup — we can now show *why* it's there instead of citing folklore.
- **Consider a second tier — "Major/Mega Volume" at ~40k** — where the win-well payoff
  actually concentrates (24% vs ~11%). This is where CSI's edge on big jobs is real and
  is the more decision-useful flag.
- **Document it as a floor, not a "big job" signal**, and note the state-relativity.
- **Out of scope here (deliberate):** this analysis does *not* change the live `10_000`
  in `02_archetypes.py`. Flipping it (or adding the second tier) is a follow-up once the
  team agrees on the framing above.

## Reproduce

```
/usr/bin/python3 02_modules/sweet_spot/scripts/2026-06-15_large_project_threshold_analysis.py
```
Outputs (in `02_modules/sweet_spot/outputs/`): `2026-06-15_tonnage_distribution.png`,
`2026-06-15_threshold_candidates.csv`, `2026-06-15_tonnage_binned.csv`. The dashboard
**page 8 "Archetype Rationale"** renders these. Methods grounded in EDA 6411
(Wk 1–3 distributions, Wk 5 clustering, Wk 6/7 anomaly detection) + the project's own
`02_archetypes.py` silhouette pattern. Data caveats inherited from the master CSV
(~85% quantity coverage; ~146 date+county key conflicts) apply.
