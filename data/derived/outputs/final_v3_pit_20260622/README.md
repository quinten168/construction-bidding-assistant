# Final V3 + Pit Logistic Model

This folder contains the final Model 1 run used for the midterm presentation.

- Model: weighted logistic regression
- Candidate rule: `v3_90d_warmup_targeted_fallback`
- Competitor identity source: reviewed 724-company registry
- Features: historical ranking features plus 28 pit-location features
- Evaluation: held-out test projects from 2025-05-01 through 2025-08-28

## Main files

- `v3_pit_model_performance.xlsx`: PPT-ready performance table and metric definitions.
- `v3_pit_ppt_metrics.csv`: six headline test-set metrics.
- `v3_pit_project_metrics_test.csv`: project-level test metrics.
- `v3_pit_logistic_predictions.csv.gz`: all 238,752 scored candidate rows for 1,591 projects. Decompress with `gzip -dk v3_pit_logistic_predictions.csv.gz`.
- `logistic_v3_pit_model.json`: trained coefficients and feature scaling values.
- `candidate_filter_audit.csv`: V3 candidate-pool diagnostics.
- `competitor_mapping_audit.csv`: raw-name to reviewed competitor mapping.
- `qa_summary.json`: final completeness checks.

Winner Hit Rate@K is the share of test projects whose true winner appears in the model's Top K. A winner excluded by the candidate pool remains in the denominator and counts as a miss.
