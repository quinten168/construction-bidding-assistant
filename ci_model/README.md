# Model 1 Candidate Generation Framework

This module builds the candidate-generation foundation for Model 1. It does not train a ranking model yet.

## Core Objects

### `rule_candidate_set`

Competitors that the system would be allowed to rank at prediction time.

Rules use only information available before the project bid date. This is the future-facing candidate pool.

### `training_audit_panel`

Audit table used to measure filter performance.

```text
training_audit_panel = rule_candidate_set + missed actual bidders
```

Missed actual bidders are included only so the team can measure candidate recall and diagnose why the filter failed. They should not be treated as normal ranking-model training rows.

### `ranking_training_panel`

Rows available to the ranking model.

```text
ranking_training_panel = training_audit_panel where was_rule_candidate = 1
```

This avoids train-serve mismatch: if a competitor would not enter the future candidate set, the ranking model should not be trained as if it had a chance to rank that competitor.

## Candidate Rule Versions

Current candidate filters are transparent rule versions for backtesting:

- `state_broad`
- `county_only`
- `state_type`
- `county_or_state_type`
- `county_state_type_plus_recent_90d`
- `county_state_type_plus_recent_180d`
- `county_state_type_plus_current_season`
- `county_state_type_plus_12m`
- `county_state_type_plus_24m`
- `county_state_type_plus_state_recent_90d`
- `county_state_type_plus_state_recent_180d`
- `county_state_type_plus_state_current_season`
- `county_state_type_plus_state_recent_12m`
- `county_or_state_type_or_family`
- `county_state_type_family_plus_state_recent_12m`

The `state_recent` variants are narrower MVP candidates for the next rule
iteration:

```text
same county
OR same state and same project type
OR recent activity in the same state
OR priority competitor
```

The priority source is the hybrid-shortlist guardrail: client-designated top
competitors from `reference/competitor_priority.csv` are always included in the
candidate set, while geography, project-type, recency, and pit-location signals
still allow auction-specific competitors to enter the shortlist.

They are intended to compare recall against candidate-pool width without
allowing recent activity in unrelated states to inflate every project.

The `family` variants additionally test same-state competitors with history in
the same `project_family`. This is meant to reduce overfitting for low-sample
detailed types while staying narrower than broad same-state history.

`state_type` is available now that normalized `project_type` is populated.
`project_type` is populated by an MVP rule-based normalizer in
`data/build_project_competitor_panel.py`. The canonical field name for this
version is `rule_based_primary_project_type_v1`; `project_type` is kept as a
compatibility alias for candidate-filter code.

These labels are transparent and reviewable. They are candidate-filter
features, not a claim that the project has one true business category.
Mixed-scope projects are represented with one primary type plus multi-label
flags.

Current scope and treatment flags include:

- `has_paving`
- `has_grading`
- `has_utility`
- `has_structure`
- `has_drainage`
- `has_reclamation`
- `has_trail`
- `is_reconstruction`
- `is_structure_replacement`

Audit lineage fields:

- `matched_keywords`
- `project_type_rule`
- `project_type_source`
- `project_family`

Current `project_family` values:

- `roadway_paving`
- `grading_earthwork`
- `utility_drainage`
- `structure`
- `pedestrian`
- `aggregate_material`
- `other`

Current MVP project-type labels include:

- `mill_and_overlay`
- `reconstruction`
- `grading_and_paving`
- `aggregate_only`
- `utility_with_paving`
- `structure_related`
- `turn_lane_or_widening`
- `reclamation`
- `trail_or_sidewalk`
- `culvert_or_drainage`
- `paving_general`
- `grading_general`
- `other`

## Outputs

```text
data/processed/model1/rule_candidate_set.parquet
data/processed/model1/training_audit_panel.parquet
data/processed/model1/ranking_training_panel.parquet
outputs/model1/candidate_filter_audit.csv
outputs/model1/candidate_filter_audit_by_project_type.csv
outputs/model1/missed_actual_bidders.csv
outputs/model1/missed_actual_bidders_reason_summary.csv
outputs/model1/missed_actual_bidders_reason_by_project_type.csv
outputs/model1/ranking_baseline_metrics.json
outputs/model1/ranking_baseline_predictions.csv
outputs/model1/ranking_baseline_topk_by_project.csv
data/processed/model1/ranking_features.parquet
outputs/model1/ranking_metrics.csv
outputs/model1/ranking_predictions.csv
outputs/model1/ranking_metrics_by_project_type.csv
outputs/model1/ranking_metrics_by_state.csv
outputs/model1/top_k_precision.csv
outputs/model1/ranking_error_analysis.csv
outputs/model1/ranking_error_summary.csv
outputs/model1/shallow_decision_tree.json
outputs/model1/shallow_decision_tree.txt
outputs/model1/shallow_decision_tree_tuning.csv
outputs/project_competitor_panel/project_type_audit.csv
```

## Ranking Baseline Scaffold

The ranking baseline is split into four explicit steps:

- `build_ranking_features.py`: builds leakage-safe historical features using
  only records before the current project bid date.
- `train_logistic_baseline.py`: trains a small numpy logistic regression
  baseline and also preserves the transparent rule-based score.
- `train_decision_tree_baseline.py`: tunes a shallow weighted-Gini decision
  tree over validation ranking metrics and adds a tree probability score with
  logistic/rule-score tie-breaks.
- `evaluate_ranking.py`: reports project-level Precision@5/10/20, MAP, and NDCG.
- `error_analysis.py`: categorizes actual bidders as filter misses, ranking
  misses, cold-start/cross-state/inactive-history cases, or captured bidders.

Current feature groups:

- same-county, same-state, same-type, and same-family history counts
- 3-month, 6-month, 9-month, 12-month, and 24-month recent bid counts
- historical bid and win counts
- days since last bid
- project-type scope flags
- pit-derived distance and access features from the MN pit list

This baseline validates ranking data flow and evaluation, not final model
quality. The default split is time-based:

```text
train:      bid_date < 2025-01-01
validation: 2025-01-01 <= bid_date < 2025-05-01
test:       bid_date >= 2025-05-01
```

## Leakage Rule

All candidate membership and future ranking features must be calculated as of the current project bid date:

```text
historical_record_date < current_project_bid_date
```

Actual bidders are added after rule-candidate generation only for audit, not for future ranking input.

## Pit List Feature Block

`build_pit_features.py` keeps the modeling unit at `job_id × competitor_unit_id`.
It uses `data/processed/MN_pit_list_cleaned.csv` only to derive aggregated
features such as nearest accessible pit distance, nearby open pit counts,
restricted-access pit indicators, Knife River pending pit proximity, and clear
restricted-pit advantage flags.

Access rules:

- `open`: available to every competitor.
- `unknown`: treated as potentially available and flagged separately.
- `competitor`: available only when `access_company` maps to the row's
  `competitor_unit_id` through `reference/competitor_entities.csv`.
- `knife_river_pending`: retained as a separate proximity signal until entity
  ownership is confirmed.
- `client` and `closed`: excluded from competitor-accessible pit features.

If project latitude/longitude columns are not available, the script can fall
back to a low-confidence `pit_county_centroid` location so distance features are
auditable rather than silently treated as precise coordinates.

## Run

```bash
python3 ci_model/model_1_wenyu/01_candidates/build_candidate_panels.py
python3 ci_model/model_1_wenyu/01_candidates/qa_candidate_panels.py
python3 ci_model/model_1_wenyu/01_candidates/build_pit_features.py
python3 ci_model/model_1_wenyu/02_features/build_ranking_features.py
python3 ci_model/model_1_wenyu/03_training/train_logistic_baseline.py
python3 ci_model/model_1_wenyu/03_training/train_decision_tree_baseline.py
python3 ci_model/model_1_wenyu/04_evaluation/evaluate_ranking.py
python3 ci_model/model_1_wenyu/04_evaluation/error_analysis.py
```
