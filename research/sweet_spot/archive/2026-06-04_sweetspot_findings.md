# CSI Competitive Sweet Spot — Findings

**Date:** 2026-06-04 · **Author:** TK · **Status:** first analytical pass
**Data:** `2026-06-03_csi_bid_master.csv` → `2026-06-04_project_base.csv`
(1,591 projects, Aug 2023–Aug 2025) · **Scripts:** `2026-06-04_01…05_*.py`

> One row of source = one (project × bidder) bid. Collapsed to **1,591 unique
> projects**; CSI bid **603 (38%)**, won **117** of those it bid (**19.4%**) —
> *not* 70%; the earlier "421/70%" was a row count (104 won projects × ~4
> bidder rows). Win definition: CSI's own bid ranked 1st (the project flag
> `CSI_Won_Project` disagrees on ~13; we use the row-derived one).

---

## Headline

**CSI's bid-selection instinct is already well-calibrated — the money leak is a
pricing problem inside the wrong archetypes, not a bid-selection problem.**

Across the six archetypes, the rate at which CSI *chooses to bid* and the rate
at which it *wins at a tight price* are correlated **0.91**. CSI bids most
exactly where it wins well. The leak is *how* it prices the low-value
archetypes it occasionally wins — not which jobs it pursues.

---

## The two questions (kept separate)

### Q1 — When does CSI decide to bid? (all 1,591 projects, 603 bid)
Predictable but not deterministic: HistGB **ROC-AUC 0.70**, PR-AUC 0.59 (vs 0.38
base). Using only RFP-knowable features (size, state, material shape,
complexity) — realized competition (`Num_Valid_Bidders`, market tightness) was
**excluded as leakage**, since CSI can't know it at bid-decision time.

Drivers (permutation importance): **job size** (largest), then **state**
(geography), then **archetype / material mix**. CSI bids bigger jobs, in its
home geography, of its preferred shapes.

P(CSI bids | archetype): **Large Volume 54%, Complex/Messy 48%** (its stated
edge) vs **Standard Paving 28%, Earthwork Heavy 26%**.

### Q2 — When CSI bids, does it win, and how well-priced? (603 bid, 117 won)
**A win model on job characteristics has no signal (ROC-AUC ≈ 0.51–0.54).**
That's a finding, not a failure: *whether* CSI wins a job it bid is driven by
**price**, not by the job's type or size. So "what CSI wins" is best read
descriptively, via the price-quality overlay — which is why no margin
regression was built.

**Bomb = a win where CSI bid >14% under 2nd place** (median margin −14.5%) —
won by leaving money on the table (the $22.3M story). Of CSI's **117 wins, 48
(41%) are bombs**; only **66 are clean** Excellent/Acceptable wins.

---

## Sweet spot (see `2026-06-04_sweetspot_map.png`)

| Archetype | bid rate | win-well rate | bomb share of wins | read |
|---|--:|--:|--:|---|
| **Large Volume** | 54% | 13.4% | 32% | ✅ sweet spot — lean in |
| **Complex/Messy** | 48% | 13.0% | 30% | ✅ sweet spot — CSI's edge |
| Shoulder/Base Only | 36% | 6.7% | 40% | ⚪ marginal |
| **Standard Paving** | 28% | 8.2% | **61%** | 🔴 pricing leak — when it wins, it overpays |
| **Earthwork Heavy** | 26% | 4.4% | **70%** | 🔴 avoid / reprice — worst on both |

(`Unknown/NoQty` — 215 projects with no quantity data — behaves like the
healthy group on outcomes; held aside from the map.)

**Two actionable zones:**
1. **Lean in (upper-right):** Large Volume + Complex/Messy. High bid, high
   win-well, low bomb. This is the defensible edge — protect and prioritize.
2. **Fix pricing (lower-right):** Standard Paving + Earthwork Heavy. CSI already
   bids these least, but **60–70% of the few it wins are bombs** — these wins
   are unprofitable. The lever is bid *price discipline* on these archetypes,
   not more/less bidding.

---

## Archetyping note (WS-A)

Two labelings, deliberately compared:
- **Rule-based** (CSI's 5 named archetypes, codified as thresholds).
- **Discovered** (PCA + K-means on the scale-free material-proportion vector;
  **k=6**, silhouette 0.57, re-seed stability ARI **0.996**) → six
  single-material-dominant shapes (MILL-, GRADE-, MIX-, BASE-, SHLDR-, CRUSH-dom).

They **agree only weakly (ARI 0.25)** — an informative disagreement: CSI's
taxonomy blends *scale* ("Large Volume") and *complexity* ("Complex/Messy")
with shape, so a pure shape-clustering cuts across it. The discovered clusters
add a finding the rules miss: the **SHLDR-dominant** cluster has by far the
**lowest bomb rate (1.4%)** — when CSI wins shoulder-heavy work it prices it
tight.

> **Teammate-facing explainer (2026-06-15):** a plain-language 3-minute walkthrough
> of how each project gets its archetype (the priority-ladder rules), where the five
> categories came from (rule-based + the PCA/K-means cross-check), and what the three
> table columns mean — `2026-06-11_how-we-classified-jobs.md`. Send this to anyone who
> needs the *what/how* without the full `00_METHODOLOGY.md`.

---

## Caveats
- **Win N is small** (117) → the win model is under-powered by design; lean on
  the descriptive overlay, not the model AUC.
- **Material proportions mix units** (TN/CY/SY in a shared denominator) — a
  compositional fingerprint, not a physical fraction.
- **Quantity coverage ~86%**; 215 projects have no material data (clustered as
  Unknown/NoQty).
- **Opportunity set** = jobs that were let and we have results for in CSI's
  regions; Q1 is "bid given awareness," not pure demand.
- **No profit data** — "win-well/bomb" uses competitive gap-to-winner as the
  proxy for leaving money on the table, not true margin.

## Outputs
`2026-06-04_project_base.csv` · `_project_archetypes.csv` ·
`_bid_by_archetype.csv` · `_win_by_archetype.csv` · `_sweetspot_summary.csv` ·
plots `_archetype_pca.png` · `_bid_model.png` · `_win_model.png` ·
`_sweetspot_map.png`
