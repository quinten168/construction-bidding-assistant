Stage 1 — Candidate Generation (01_candidates/candidate_filter.py, build_candidate_panels.py)

Core function: build_v3_candidate_set() in candidate_filter.py. For each project, iterates chronologically and looks only at bids with bid_date < current bid_date (strict no-leakage cutoff). For every competitor it computes boolean membership sets:

- same_county_ids, same_type_ids (same state + same project_type)
- recent_90d_ids (same-state bid within 90 days)
- warmup_ids (same-state bid within 365 days, only active when the project's history_days_available < 365 — i.e. it's one of the first year's worth of auctions, so there isn't enough history yet for the 90-day rule to be fair)
- historical_winner_ids (won in-state within the last 730 days)
- recurring_regional_ids (≥3 same-state bids in the last 730 days)
- priority_ids (resolved in build_candidate_panels.py via a company-name registry — Top Competitors Tag propagated across all raw name variants of the same comp_name,
  then matched into bidder_results to get competitor_unit_ids)

A competitor enters the candidate pool if in_default_90d OR in_warmup Ohere fallback_score = 3.0*priority + 2.0*historical_winner +1.5*recurring_regional.

For each project, loops candidates and computes, again strictly before bid_date: prior bid/win counts, non-overlapping recency buckets (bids_0_3m, 3_6m, 6_12m, 12_24m),
same-state/county/type counts, scope-match flags (paving/grading/base —f has that flag AND the competitor has prior history with it),log-scaled project-size features, and mix_ton_capacity_ratio (YTD won tonnage this bid-season ÷ competitor's historical average per season, using a Sept–Apr season year derived from CSI_data_combined.csv). Merges in Stage-2 pit features, and computes a transparent rule_score = 3×same_county + 2×same_type + 1×recent_12m_activity +
0.5×prior_win_count − 0.25×recency_penalty as a non-ML sanity baseline.

Out: ranking_features.parquet, label = did_bid.

Stage 4 — Model Training (03_training/*.py)

Four models (logistic, decision tree, SVM, XGBoost) each independently uet, split by bid_date (train <2025-01-01, val 2025-01-01–2025-05-01,test after), and each appends its own score column to a shared ranking_predictions.csv. XGBoost uses RandomizedSearchCV (50 iters) with a PredefinedSplit scored on
validation PR-AUC, tuning scale_pos_weight for the ~2.3% positive rate.ler + class_weight="balanced" L2 logistic regression — this is the oneStage 6/7 actually explain, because its coefficients are interpretable log-odds contributions.

Stage 5 — Evaluation (evaluate_ranking.py)

Re-derives the Tier 1/Tier 2 split independently at evaluation time (same registry-lookup logic as candidate generation, duplicated rather than reused). Computes project-level P@5/10/20, NDCG, and a graded NDCG for Tier 1 where relevance = max(0, 1 - gap_to_low) (so the actual auction winner scores 1.0, and near-low bids score partial credit) — this rewards ranking real threats above marginal ones, not just any bidder. Also computes an analytical random-ranking baseline (closed-form
expectation, no permutation sampling) to contextualize whether the modeauto-logs to experiment_tracker.py.

Stage 6 — Explainability (logistic_feature_importance.py)
Just reads the logistic model JSON's feature_weights (already comparabled) and ranks by |coefficient|.
Stage 7 — Reporting Agent (06_reporting/agent/)

- planner.py: plan() sorts all candidates by logistic_score descending and truncates to top_n. Note: the docstring says "Tier 1 (priority) always goes first," but the actual code does not sort by tier at all — it's a flat score sort. If a Tier 1 (client-priority) competitor scores low, it can be excluded from the top-N entirely and never reach the Executor. Worth flagging if that's not intended behavior.                                                                                              - executor.py: for each planned competitor, calls predict_and_explain() sigmoid manually from the model JSON and decomposes log_odds =intercept + Σ(coef_i × zscore(x_i)) into per-feature contributions — then _compute_win_stats() (county/state/type win rates, plus a hand-rolled Sept–Apr bid-season    calendar for capacity tracking), then generate_narrative().
- generate_narrative.py: two-layer — Layer A rule-synthesizes bullet points (bid rate, recency, season capacity vs. historical pace, pit advantage, experience, win rates) directly from feature values (not the LLM); Layer B sends those bullets to Claude to polish into 2-3 sentences. If no API client, it skips Layer B and returns traw bullets.
- reflector.py: sends the narrative to Claude for a pass/fail self-critique (up to 2 revision attempts), flags for human review if still failing.
- reporter.py: assembles markdown — groups deep-dives by tier (Priority vs Discovery) and threat level (HIGH/MEDIUM shown in depth; LOW priority-tier competitors get their own "low engagement expected" section); converts each feature's log-odds contribution to a probability-scale delta via a leave-one-out logit calculation for the ✓/✗ signal lines; never shows raw probabilities except in a final appen

If useful, I can dig into the discrepancy in planner.py (Tier 1 competi of top-N) — that looked like a real gap between intent andimplementation.
