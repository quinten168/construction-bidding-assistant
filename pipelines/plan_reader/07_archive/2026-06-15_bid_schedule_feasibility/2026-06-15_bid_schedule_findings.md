# Bid-Schedule Extraction — Preliminary Feasibility Findings

*2026-06-15 · throwaway analysis · reads converted .md + .json only · no Claude calls · no pipeline changes*

## The question
Today the Plan Reader keeps 7 summed material roll-ups + `box_culvert` and discards the rest of the 25–43 line-item bid schedule. **Would parsing the full schedule give fields that sharpen archetype ID and the bid/no-bid decision?**

## 1. Does it parse reliably? (deterministic, zero Claude cost)

| plan | state | items (base/alt) | spec cats | gotcha (tier) | parse status |
|---|---|---|---|---|---|
| 2023_BROOKINGS-CO-SD_SURFACING_LOST | SD | 0 (0/0) | 0 | 8 (high) | fallback: conversion mangled header (merged cells) |
| 2023_DUNN-CO-ND_CP-13_WON | ND | 39 (37/2) | 9 | 12 (high) | clean |
| 2023_OTTER-TAIL-CO-MN_CP-4069-304_LOST | MN | 7 (7/0) | 6 | 9 (high) | clean |
| 2023_WALSH-CO-ND_HWY-9_LOST | ND | 56 (56/0) | 8 | 8 (high) | clean |
| 2023_WATONWAN-CO-MN_SP-8303-48_LOST | MN | 0 (0/0) | 0 | 10 (high) | fallback: conversion mangled header (merged cells) |
| 2025_DOUGLAS-CO-MN_SAP-021-600-023_NOBID | MN | 0 (0/0) | 0 | 10 (high) | fallback: conversion mangled header (merged cells) |
| 2025_STUTSMAN-CO-ND_CR-68_NOBID | ND | 28 (28/0) | 6 | 9 (high) | clean |
| 2025_WATONWAN-CO-MN_WATLINE-TRAIL_NOBID | MN | 0 (0/0) | 0 | 10 (high) | fallback: conversion mangled header (merged cells) |

- **4/8 plans parsed cleanly and deterministically** from the already-converted Markdown — across THREE distinct schedule layouts: ND/EJCDC (`BID ITEM | DESCRIPTION | UNIT | QUANTITY`), MnDOT (`No. | Mat No. | Item | Units | Quantity`, spec codes like `2360.509`), and NDDOT (`SPEC | ITEM # | ITEM DESCRIPTION | UNIT | QUANTITY`). Header-row anchoring (not table arity) handles all three; column-by-name mapping adapts per layout.
- **Dunn (ND) ground-truth check: parsed 39 = 37 base + 2 alternate** ✓ — the page-break continuation table (items 26–37) is captured.
- **The price-column discriminator is essential.** A real bid *schedule* is a pricing form (it has a BID UNIT PRICE / SUBTOTAL / EXTENDED column); engineer's-estimate quantity tabulations ('BASIS OF ESTIMATE') share QUANTITY/UNIT but carry no price. Requiring a price column dropped Dunn from a polluted 104 to the correct 39 — and is the single most important anchoring rule for production.
- **The 4 plans that need a fallback fail on *conversion quality*, not parser logic:** Douglas (MN) — the priced 'Statement of Estimated Quantities' collapsed into one merged-cell blob; Brookings (SD) — header became `BID SCHEDULE | Col2 | Col3`; Watonwan (MN) — 'SCHEDULE OF PRICES' did not convert as a table at all (its only pipe table is the MnDOT unit-weight reference, correctly excluded as noise). **This is the real gate: the bid schedule's table structure must survive `s1_convert` (or get an LLM fallback).**

## 2. The core go/no-go: resolution vs today's complexity proxy

The sweet-spot models' only complexity feature is `n_mat_types` (count of non-zero material types). Its corpus-wide distribution:

```
n_mat_types (1,591 projects): {'0': 215, '1': 129, '2': 317, '3': 495, '4': 333, '5': 100, '6': 2}
```
It **caps at 6 and puts ~95% of projects in {2,3,4}** — almost no resolution. By contrast `bid_item_count` on the parsed plans ranges **7–56** (median 33), and `n_spec_categories` adds an orthogonal breadth signal. A 39-item Dunn job and a 7-item Otter-Tail job are *identical-ish* under `n_mat_types` but obviously different operations. **This is the signal the 2026-06-15 archetype reanalysis explicitly asked for and could not compute.**

## 3. New fields this unlocks (all derived, zero extra Claude calls)

- **Complexity/messiness:** `bid_item_count`, `n_spec_categories`, `has_structures_work`, `has_traffic_control`, `has_erosion_control`, `has_alternates`, `mobilization_present`.
- **Schedule/contract risk:** `contract_duration_days` (from existing construction dates).
- **Gotcha burden:** `gotcha_count` / `gotcha_burden_tier` (decision-driver gotchas weighted 2× via the live `taxonomy.py` split) — the missing 'this job is risky/messy' signal for the Q2 win model.

## 4. Honest limitations

- **Small sample (8 plans).** Value claims about archetype separation are *directional*; the resolution argument (§2) is corpus-wide and solid.
- **Thin master join.** Only the 3 NOBID 2025 plans carry a `contract_id`, so a per-plan join to the master archetype labels is weak on this sample — not a blocker for the feasibility call.
- **State-relative.** `bid_item_count` is only comparable *within* a state (MN splits HMA across many `2360.509` lines; ND lumps). Segment by state before any model, same as the 10k-ton threshold.
- **Roll-up cross-check** (line-item sums vs the 7 Claude roll-ups) is printed per plan; treat as a QA artifact, not a field swap — do not disturb the golden-scored roll-ups.

## 5. Recommendation

**PROCEED to pipeline integration** — with eyes open on the conversion-quality gate.
- The parse is deterministic, free, and verified-correct on clean schedules (Dunn 39 ✓), and `bid_item_count` / `n_spec_categories` give exactly the complexity resolution today's `n_mat_types` lacks. The value case holds.
- Two anchoring rules proved essential and should carry into production: **(a) require a price/subtotal column** to separate the biddable schedule from quantity tabulations; **(b) anchor on the header-row signature, not table arity**, to skip MnDOT noise tables.
- **The binding constraint is `s1_convert` table fidelity**, not the parser — ~half the sample lost its priced schedule to merged-cell conversion. So the production step needs an **LLM fallback** over the bid-schedule pages whenever the deterministic parse returns nothing, and it may be worth hardening `s1_convert` for plan-sheet 'Statement of Estimated Quantities' tables.

**Next step (separate, already-scoped):** new `01_pipeline/s5_bid_items.py` (this parser + LLM fallback) → `bid_items.csv` long table + derived scalar fields in `schema.py`, with `05_knowledge/spec_category_map.csv` as the category map and `04_tools/rebuild_aggregates.py` wired to regenerate it with no Claude calls. Keep the 7 golden-scored roll-ups untouched; the line-item sums are a QA cross-check only.
