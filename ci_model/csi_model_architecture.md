# CSI Competitor Intelligence System — Model Architecture Reference

## Overview

Two-model pipeline that answers two distinct questions:

- **Model 1:** Given a new job, which competitors are likely to bid?
- **Model 2:** Given the competitive landscape, should CSI bid on this job?

---

## Full Pipeline

```
New Job Comes In
       ↓
  [ Stage 1: Candidate Generation ]
  Filter full competitor pool (50-100) down to ~10-20
  plausible candidates for THIS job
  (geography / recent activity / county+type relevance)
       ↓
  [ Model 1: Competitor Bid Prediction ]
  Run only candidate competitors against this job
       ↓
  Competitor probability scores
  + derived competition features
  (n_bidders, top_threat, etc.)
       ↓
  [ Model 2: CSI Go / No-Go Recommendation ]
  + CSI's own position features
  + Job features
       ↓
  Win probability score
       ↓
  GO / NO-GO recommendation + SHAP explanation
```

---

## Model 1: Competitor Bid Prediction

### Problem Framing

Binary classification. One model covers all competitors.

- Each training row = one **(job × competitor) pair**
- Label = `did_bid` (1 = competitor bid on this job, 0 = did not)
- At inference: run candidate competitors against a new job, rank by predicted probability

### Stage 1: Candidate Generation (for large competitor pools)

With a small competitor set, scoring every (job × competitor) pair is fine. With **50-100 competitors** it breaks down: each job generates ~100 rows but only 3-5 are real bidders, so 95%+ of rows are negatives — and most are *trivial* negatives (a company 200 miles away that has never bid in the county). These dominate the data, and the model can reach 96% accuracy by predicting all-zero while learning nothing useful.

**Fix: two-stage retrieval → ranking** (same pattern as a recommender system).

- **Stage 1 (candidate generation):** cheap rules narrow the full pool to ~10-20 plausible candidates for *this* job.
- **Stage 2 (ranking):** the XGBoost model below scores only those candidates.

Keep a **single pooled model** — do NOT train one model per competitor. The model learns *behavioral patterns* (close pit + matching type + free capacity → likely bid); per-competitor identity is captured through features, not separate models. More competitors just means more rows, which helps a pooled model.

**Candidate generation filters** (tune for high recall, not precision):

| Filter | Rule |
|---|---|
| Geography | Competitor has at least one pit within X miles of the job (reuses `pit_distance`) |
| Recent activity | Competitor has bid at least once in the last 12-18 months |
| Relevance | Competitor has bid in this county OR on this job_type at least once historically |

The metric that matters here is **recall**: what % of actual bidders survive the filter. Target 95%+. A bidder dropped at Stage 1 can never be recovered at Stage 2, so keep the filters loose.

**Apply candidate generation at BOTH train and inference time** so the row distribution matches. Training rows become `(job × candidate)` pairs, not `(job × all competitors)`.

**Effect on class balance:** after filtering (~15 candidates, ~4 bidders) the positive rate rises to ~25-30%, far healthier and less reliant on `scale_pos_weight`.

**Frequency baseline:** before trusting the model, rank competitors purely by historical bid count (optionally conditioned on county/type). The model must beat this baseline to justify itself — it earns its place only by adding job-specific context (this job is near competitor X's pit; competitor Y is usually active but currently at capacity) that a static ranking misses. This same ranking doubles as a candidate-generation signal.

### Training Data Structure

```
job_id | competitor | job_county | job_type | job_budget | ... | comp_pit_distance | ... | did_bid
  001  |     A      |   Hennepin |  paving  |    2100000 | ... |              12.3 | ... |       1
  001  |     B      |   Hennepin |  paving  |    2100000 | ... |              34.1 | ... |       0
  001  |     C      |   Hennepin |  paving  |    2100000 | ... |               8.7 | ... |       0
  002  |     A      |   Stearns  |  bridge  |    5400000 | ... |              41.2 | ... |       0
```

### Features

#### Job Features
*Same value for every competitor row on the same job*

| Feature | Description | Source |
|---|---|---|
| `job_county` | County where the job is located | Raw data |
| `job_type` | Work type: paving, grading, bridge, culvert, etc. | Raw data (normalize first) |
| `job_budget` | Estimated contract value in USD | Raw data (consider log transform) |
| `material_mix_*` | Per-material columns: asphalt %, aggregate %, concrete % | Aggregate from line items |
| `bid_month` | Month of bid opening date (1–12) | Derived from bid_date |
| `bid_season` | Quarter of bid opening date: Q1/Q2/Q3/Q4 | Derived from bid_date |

#### Competitor × Job Features
*Varies per competitor for the same job*

| Feature | Description | Calculation | Data Required |
|---|---|---|---|
| `pit_distance_miles` | Distance from competitor's nearest pit to job site | Haversine across all pits → take min | Competitor pit GPS coords |
| `comp_county_bid_rate` | Competitor's historical bid rate in this county | # bids in county / # total jobs in county (before bid_date) | Historical bid results |
| `comp_type_bid_rate` | Competitor's historical bid rate on this job type | # bids on type / # total jobs of type (before bid_date) | Historical bid results |
| `comp_budget_fit` | How well job budget matches competitor's typical contract size | job_budget / competitor's historical avg contract value | Historical bid results |
| `comp_recent_activity` | Competitor's bid count in last 12 months | Count of bids in rolling 12-month window before bid_date | Historical bid results |
| `comp_capacity_used_pct` | % of competitor's capacity already committed at bid_date | Sum of active contract values at bid_date / estimated max capacity | Job start/end dates (or estimated) |

#### Capacity Calculation Detail

```
Step 1: Find all jobs competitor has won where start_date <= bid_date <= end_date
Step 2: active_value = sum(contract_value) of those jobs
Step 3: max_capacity = competitor's historical peak concurrent contract value
Step 4: comp_capacity_used_pct = active_value / max_capacity
```

If start/end dates are unavailable, estimate duration by job size:
- < $1M → 3 months
- $1M–$5M → 6 months
- > $5M → 12 months

### Data Leakage Warning

All competitor statistics (`bid_rate`, `recent_activity`, `capacity`) **must be calculated using only data prior to each job's `bid_date`**. Never use the full dataset for aggregations.

### Model Output

```
Job #445 — Hennepin, paving, $2.1M

Competitor D:  0.87
Competitor A:  0.71
Competitor C:  0.45
Competitor B:  0.23
Competitor F:  0.11
```

---

## Model 2: CSI Go / No-Go Recommendation

### Problem Framing

Binary classification. Predicts whether CSI will win if they bid.

- Each training row = one job where **CSI actually bid**
- Label = `csi_won` (1 = CSI won, 0 = CSI bid but lost)
- Output = win probability → thresholded to GO / NO-GO

### Training Data Structure

Only includes jobs where CSI participated (win/loss known).

```
job_id | job_county | job_type | job_budget | expected_n_bidders | strong_competitor_count | csi_pit_distance | csi_capacity_used_pct | ... | csi_won
  001  |   Hennepin |  paving  |    2100000 |                3.4 |                       2 |             5.2  |                  0.42 | ... |       1
  002  |   Stearns  |  bridge  |    5400000 |                1.8 |                       1 |            18.7  |                  0.71 | ... |       0
```

### Features

#### Group A: Job Features
Same features as Model 1 (county, type, budget, material mix, season).

#### Group B: Competition Landscape Features
*Derived from Model 1 output*

| Feature | Description | Calculation from Model 1 output |
|---|---|---|
| `expected_n_bidders` | Expected number of competitors who will show up | Sum of all competitor probabilities |
| `strong_competitor_count` | Number of serious threats | Count of competitors with probability > 0.5 |
| `top1_competitor_prob` | Strength of the dominant competitor | Max single competitor probability |
| `avg_competitor_prob` | Overall field strength | Mean of all competitor probabilities |

#### Group C: CSI's Own Position
*CSI treated the same way as competitors in Model 1*

| Feature | Description |
|---|---|
| `csi_pit_distance` | CSI's nearest pit to this job site |
| `csi_capacity_used_pct` | % of CSI's capacity committed at bid_date |
| `csi_county_win_rate` | CSI's historical win rate in this county |
| `csi_type_win_rate` | CSI's historical win rate on this job type |
| `csi_budget_fit` | job_budget / CSI's historical avg contract value |

### Model Output

```
win_probability = 0.73 → GO
win_probability = 0.28 → NO-GO
```

Threshold is a business decision (e.g. bid only when win_prob > 0.40). Can also be weighted by job size — a $5M job at 35% might still be worth it.

### Explanation Layer (SHAP)

For each recommendation, surface the top driving factors:

```
Job #445 — GO (win probability: 73%)

  +0.21 → CSI pit only 5 miles away (strong cost advantage)
  +0.18 → Only 1 strong competitor expected
  +0.12 → CSI has 68% win rate in Hennepin County
  -0.08 → CSI capacity currently at 71% (slightly constrained)
```

---

## Data Requirements Summary

| Data | Used In | Status |
|---|---|---|
| Historical bid results (who bid, which job) | Model 1 | ✅ Available |
| Job attributes (county, type, budget, materials) | Model 1 + 2 | ✅ Available |
| Competitor pit GPS coordinates | Model 1 | ⚠️ Need to confirm / geocode |
| Job start and end dates | Model 1 (capacity) | ⚠️ May need to estimate |
| CSI's historical win/loss records | Model 2 | ✅ Should be available |
| CSI pit GPS coordinates | Model 2 | ⚠️ Same as competitor pits |

---

## Implementation Notes

- **Recommended model type:** XGBoost or Random Forest for both models (handles mixed feature types, supports SHAP natively)
- **Negative samples in Model 1:** With candidate generation, negatives = candidates who did NOT bid (not the entire pool). This removes trivial negatives and keeps the signal meaningful.
- **Class imbalance:** Candidate generation already lifts the positive rate to ~25-30%. If still skewed, use `scale_pos_weight` in XGBoost or `class_weight='balanced'` in sklearn.
- **Baseline:** Always benchmark against a frequency ranking (historical bid count). Ship the model only if it beats this.
- **Long-tail competitors:** Competitors with very few historical bids have noisy `bid_rate` features. Smooth toward the global average, or add an `n_observations` feature so the model knows how trustworthy each stat is.
- **CSI is "competitor 0":** CSI's position features in Model 2 (Group C) use the same feature logic as competitors in Model 1. Write the feature functions once so they run for any bidder, CSI included.
- **Feature store:** Competitor statistics should be precomputed as a lookup table keyed by `(competitor, county, job_type, as_of_date)` to avoid recomputation at inference time.
- **Competitor name normalization:** Apply before any groupby. Regex-based normalization should already exist in the bid parser module.

---

## Code Structure

A lean 6-file layout for the predictive pipeline. Library modules hold logic (importable, no side effects); `pipeline.py` is the only entry point the chatbot/API calls.

```
csi/
├── data.py        # CONFIG constants + data loaders + geo/distance helpers
├── features.py    # feature computation + feature store (leakage-critical)
├── model1.py      # candidate generation + dataset assembly + train/score + baseline
├── model2.py      # landscape features + CSI position + train/score + SHAP
├── evaluate.py    # recall@k, model metrics, baseline comparison
└── pipeline.py    # end-to-end: new job → GO/NO-GO + explanation
```

| File | Responsibility |
|---|---|
| `data.py` | `CONFIG` dict (paths, radius, thresholds, hyperparams) at top; `load_bids/jobs/pits()`; `haversine()` |
| `features.py` | Pure feature functions (each takes `as_of_date`) + `build_feature_store()`. **Keep separate** — leakage bugs are silent, so this logic must stay isolated and unit-tested. |
| `model1.py` | Stage 1 filters, `(job × candidate)` dataset, `train_model1()`, `score_job(job) → {competitor: prob}`, frequency baseline |
| `model2.py` | Build Group B + C features, `train_model2()`, `recommend(job) → (win_prob, shap_factors)` |
| `evaluate.py` | Candidate-gen recall@k, Model 1/2 metrics, side-by-side vs baseline |
| `pipeline.py` | Orchestrates Model 1 → Model 2 → GO/NO-GO |

**Build order (bottom-up):**

1. `data.py` — read data, compute distances
2. `features.py` — **write tests first** (leakage lives here)
3. `model1.py` — confirm it beats the frequency baseline before moving on
4. `model2.py`
5. `evaluate.py` + `pipeline.py` — wire end to end

> The one boundary not to collapse: keep `features.py` out of `model1.py`. Everything else can merge freely.

> The RAG / ChromaDB / PDF Q&A layer is a **separate subsystem** — keep it in its own `rag/` folder parallel to `csi/`, and only merge at the chatbot layer.
