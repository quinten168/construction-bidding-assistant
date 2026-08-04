# Experiment: swap production model to the 4-feature simple-rule baseline

Question: what does `06_reporting/agent/orchestrator.py`'s report actually look like if we point it
at the 4-feature `simple_rule_baseline` (county/type/state/size_fit) instead of the 36-feature
`logistic_baseline_model.json` currently wired in as `_DEFAULT_MODEL`?

This does **not** touch any tracked file. It builds a self-contained model json + predictions csv
in `outputs/` and calls the real, unmodified `orchestrator.py` via its existing `--predictions`/
`--model` CLI flags, using `--skip-llm` so it needs no ANTHROPIC_API_KEY.

## Known approximation (read before trusting the numbers)

`simple_rule_baseline_weights.json` (the real, production-fitted artifact) does NOT persist a
`StandardScaler` or `intercept` — see `train_simple_rule_baseline.py:140-143`: the un-standardized
raw-space weights are kept specifically so `simple_rule_score` stays a plain linear combination for
ranking, and the scaler/intercept were discarded because ranking only needs ordering.

`predict_and_explain.py`, however, needs a scaler + intercept to produce a 0-1 `bid_probability`
(for HIGH/MEDIUM/LOW and the reasons-to-bid narrative). Since the original scaler was never saved,
`build_experiment_artifacts.py` refits `StandardScaler` + `LogisticRegression` on the 4 primary
features **using only the ~20-project reviewable sample** (`ranking_predictions_sample.csv`), not
the full training set the real weights were fit on. So:

- `experiment_predictions.csv`'s ranking of candidates within a project should be close to the real
  4-feature model (same feature definitions, same production `weights` are cross-checked below).
- The absolute `bid_probability` / HIGH-MEDIUM-LOW thresholds are an approximation for this test
  only — refit on the full corpus before this could be trusted for real threat-level thresholds.

## Run

```
python build_experiment_artifacts.py
python run_report.py --project-key <key from experiment_predictions.csv>
```
