# Competitor Intelligence — module placeholder

**Owners:** Quentin + Wenyu

Given a project location, produce a **conservative ranked list of likely competitors
with rationale**. This is a **decision-support tool**, not a route optimizer or cost
calculator.

Signals (per the project scope):
- **Turf / regional dominance** — historical bid-participation patterns by geography (MN/ND/SD differ).
- **Competitor capacity** — 5-year average project size, adjusted by year-to-date bids
  (near average = "full"; well below = "hungry").
- **Distance to aggregate** — primarily relevant in MN (pit-dependent haul cost).

## Interface contract (to define before wiring into the dashboard)

The dashboard's "Ask the client" page needs a stable function/CSV contract, e.g.:

```python
likely_competitors(contract_id | location) -> list[{competitor, rationale, confidence}]
```

## Reuse from Fall 2025 (do not re-derive)

- `99_archive/fall_2025/99_Fall_2025_Client_Project/scripts/competitor_bid_quality_analysis.py`
  — `NAME_MAPPING` vendor-name normalization + bid-quality bucketing.
- `.../scripts/peer_group_analysis.py` — competitor ranking methodology (4 methods + consensus).

Back-test using **only pre-bid-date data** (Hard Rule 10).
