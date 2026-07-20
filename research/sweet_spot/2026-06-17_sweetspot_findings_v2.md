# Sweet-spot findings — refreshed on v2 labels (2026-06-17)

CSI's competitive picture, recomputed after the archetype rule was upgraded to the share-gated **v2**
rule. Win definition is the canonical one: CSI won a project iff its own bid ranked 1st.

## Validation first
Before reading outcomes through the labels, we checked the labels:
- **Golden-set check:** ran v2 on the team's 36 hand-verified plans. Every label is sensible against the
  project, and v2 gives the **same label from the golden hand-quantities as from the master CSV (100%,
  36/36)** — the rule is stable no matter which data source feeds it. *(script:
  `scripts/2026-06-17_validate_archetype_vs_golden.py`)*
- **Known limit confirmed:** the Stearns FDR job (CP-073-123) lands in Mill & Overlay, exactly as the
  canonical doc says it must (FDR is invisible to the 7 roll-up quantities).

## Win/loss by work-type

| Work-type | Projects | Bid rate | Bids | Win rate | **Win-well** | Bomb rate | **Bomb-share of wins** | Median margin |
|---|--:|--:|--:|--:|--:|--:|--:|--:|
| **Reconstruct / Rebuild** | 461 | 37% | 172 | 23% | **14.5%** | 8.1% | **35.9%** | 8.9% |
| **Mill & Overlay** | 306 | 41% | 124 | 18% | 10.5% | 7.3% | 40.9% | 9.8% |
| **HMA Overlay / Resurface** | 212 | 42% | 88 | 15% | 5.7% | 9.1% | **61.5%** | 12.8% |
| **Grading / Earthwork** | 212 | 33% | 70 | 19% | 11.4% | 7.1% | 38.5% | **23.6%** |
| **Aggregate / Base / Gravel** | 133 | 35% | 46 | 17% | 4.3% | 10.9% | **62.5%** | 17.3% |
| Unknown / NoQty | 216 | 42% | 91 | 22% | 14.3% | 5.5% | 25.0% | 10.5% |
| Other | 52 | 23% | 12 | — | — | — | — | — |

*Win-well = share of bids that won at a healthy margin (Excellent/Acceptable). Bomb-share of wins = of
the projects CSI won, the share won by overpaying (bid >14% under 2nd place) — the pricing-leak metric.*

## What it says

1. **CSI bids broadly but its edge is in win *quality*, not bid frequency.** Bid rates are flat (33–42%)
   across types. The separation shows up in win-well and bomb-share.
2. **Reconstruct and Grading are the healthy buckets.** Highest win-well (14.5%, 11.4%), lowest
   bomb-shares (~36–38%). Grading also carries the **highest median margin (23.6%)** — earthwork pays
   well when won well. This matches the "High edge on multi-scope self-performed work" thesis.
3. **The pricing leak concentrates in the commodity buckets.** HMA Overlay and Aggregate have the worst
   bomb-share of wins (**61–63%**) and the lowest win-well (4–6%). When CSI wins these, it mostly wins by
   leaving money on the table. These are the "avoid, or price with discipline" types.

## How the cleaner labels changed the picture (v1 → v2)
The share-gated rule sharpened the commodity signal by moving token-grade "reconstructs" into the
resurfacing buckets where they belong:

| Bomb-share of wins | v1 (old) | v2 (new) |
|---|--:|--:|
| Reconstruct / Rebuild | 36.5% | 35.9% |
| Mill & Overlay | 50.0% | 40.9% |
| HMA Overlay / Resurface | 50.0% | **61.5%** |

Under v1 the leak was smeared across Mill & Overlay and HMA at a flat 50%. v2 concentrates it: HMA
Overlay is now clearly the worst (61.5%), which is the more honest read — pure pave-overs are the most
commoditized work CSI overpays to win.

## Caveats
- **2023 is partial** (Aug–Dec only) — it's in the totals.
- **Unknown/NoQty (216)** is a data-coverage bucket, not a real type; it shrinks as extraction improves.
- **FDR is invisible** to these labels (no reclamation column in the 7 quantities) — some reconstruct-class
  reclaim jobs sit inside Mill & Overlay. Recovering them needs the Plan Reader's spec codes.

*Numbers from `scripts/2026-06-17_winloss_by_archetype_v2.py` → `outputs/2026-06-17_winloss_by_archetype_v2.csv`.
Replaces the old `archive/2026-06-04_sweetspot_findings.md` (computed on the superseded labels).*
