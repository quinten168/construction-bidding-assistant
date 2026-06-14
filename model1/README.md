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

`state_type` is expected to be unavailable until normalized `project_type` is populated.

## Outputs

```text
data/processed/model1/rule_candidate_set.parquet
data/processed/model1/training_audit_panel.parquet
data/processed/model1/ranking_training_panel.parquet
outputs/model1/candidate_filter_audit.csv
outputs/model1/missed_actual_bidders.csv
outputs/model1/missed_actual_bidders_reason_summary.csv
```

## Leakage Rule

All candidate membership and future ranking features must be calculated as of the current project bid date:

```text
historical_record_date < current_project_bid_date
```

Actual bidders are added after rule-candidate generation only for audit, not for future ranking input.

## Run

```bash
PYTHONPATH=".python_packages" python3 model1/build_candidate_panels.py
PYTHONPATH=".python_packages" python3 model1/qa_candidate_panels.py
```
