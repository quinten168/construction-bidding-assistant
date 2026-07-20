# Project archetype rules — quick reference

Inputs: the 7 bid-schedule quantities (`MIX_TN, GRADE_CY, BASE_TN, SHLDR_TN, MILL_SY, CRUSH_TN, STOCK_TN`).
First matching row wins (top to bottom).

`mix_share = MIX_TN / (MIX_TN + BASE_TN + SHLDR_TN + CRUSH_TN + STOCK_TN)`
`paving = (mix_share ≥ 0.15) OR (MIX_TN ≥ 1,000 t)`

| # | Work-type | Condition (plain) | Rule / cut-offs | CSI edge |
|---|---|---|---|---|
| 1 | **Reconstruct / Rebuild** | Regrade the roadbed **and** pave | `paving` **and** `GRADE_CY ≥ 500` | **High** |
| 2 | **Mill & Overlay** | Mill off old asphalt, lay new (commodity) | `paving`, `GRADE_CY < 500`, `MILL_SY ≥ 1,000` | **Low** |
| 3 | **HMA Overlay / Resurface** | New asphalt over the surface — no mill, no regrade | `paving`, `GRADE_CY < 500`, `MILL_SY < 1,000` | Medium |
| 4 | **Grading / Earthwork** | Move/shape dirt — no real paving | `not paving`, `GRADE_CY ≥ 500` | Medium |
| 5 | **Aggregate / Base / Gravel** | Base/shoulder/gravel — no asphalt surface | `not paving`, `BASE_TN > 0 or SHLDR_TN > 0` | Low–Med |
| — | **Unknown / NoQty** | No quantities — data gap, not a real type | no quantities | N/A |
| — | **Other** | Has quantities but none of the above | else | N/A |

### The four cut-offs
| Threshold | Value | Meaning |
|---|---|---|
| `MIX_SHARE_MIN` | **0.15** | mix ≥ 15% of total tons → it's a paving job |
| `MIX_ABS_MIN` | **1,000 t** | …or ≥ 1,000 t of mix → paving even if its share is low |
| `GRADE_MIN_CY` | **500 CY** | grading above this is a real regrade (not approach grading) |
| `MILL_MIN_SY` | **1,000 SY** | milling above this is real (not edge mills) |


## Why this rule (the design choices)

- **Shares, not raw magnitude.** Across the data, the *amounts* of MIX/BASE overlap heavily between
  types — they don't separate. The **share** of mix-vs-aggregate cleanly draws the paving / non-paving
  line, and the **presence of grading vs milling** splits the paving types. (Evidence: the distribution
  and tonnage-share analyses cited in `README.md`.)
- **Magnitude gates kill "trivial triggers."** The earlier binary-presence rule labeled a job
  "Reconstruct" on as little as 30 CY of grading, or "Mill & Overlay" on 237 SY of edge milling. That
  over-labeled **Reconstruct by ~25%** (615 → 461 projects). The floors fix it.
- **Grade-vs-surface is CSI's own distinction** (rebuild vs resurface) and the most cost-meaningful split
  (earthwork crews vs paving crews). It makes the types mutually exclusive.
- **BASE is deliberately *not* a routing trigger.** It is present in 85–95% of every paving type, so it
  separates nothing; and base *intensity* was tested as a CSI-edge signal and **rejected** (no predictive
  relationship — see `scripts/2026-06-17_base_intensity_edge_validation.py`).
- **MILL is deliberately *not* used in the non-paving branch.** The "Aggregate jobs that carry milling"
  are a data artifact (levee / landfill / grading jobs with blank MIX & GRADE and a mis-loaded MILL_SY),
  not a real reclaim type.