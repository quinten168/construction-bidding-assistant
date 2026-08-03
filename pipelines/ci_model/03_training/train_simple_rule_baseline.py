#!/usr/bin/env python3
"""
Simple rule-based competitor score, built from segment-level win rates
(project type, county, state) rather than the existing rule_score's
bid-activity heuristic in build_ranking_features.py.

Segments are independent (not nested): "win rate on mill_overlay jobs"
counts wins in any state/county, etc. County matching is scoped to
(state, county) together since county names are not globally unique
(e.g. "CASS CO" collides across ND/MN/SD in this dataset).

State-level win rate has the most volume of the three, so it is used
as the shrinkage anchor for the sparser county/type rates:

    rate_state        = w_state / n_state, falling back to the
                         competitor's all-time global win rate if they
                         have never bid in this state, else 0
    rate_<seg>_shrunk  = (w_segment + k * rate_state) / (n_segment + k)

k = 5 pseudo-observations: with 5+ real bids in a segment the shrunk
rate is dominated by the segment's own history; with 0 it collapses
exactly to rate_state.

Win counts lead the score; shrunk rates only break exact ties. Tie-break
weighting follows the same tiny-epsilon convention already used for
tree_score_tiebreak in train_decision_tree_baseline.py, so the rate
terms can never overturn a count-based ordering.

The four primary-term weights (county/type/state win counts + size fit)
are FIT, not guessed: a small logistic regression on those 4 features
(train split only, same class_weight="balanced"/C=1.0 convention as
train_logistic_baseline.py) learns the coefficients, which are then
un-standardized back into raw-feature-space weights so `primary` stays
a plain, human-readable linear combination of the raw log1p(win_count)
/ size_fit values -- see fit_primary_weights(). The fitted weights are
written to outputs/simple_rule_baseline_weights.json for inspection.
Falls back to the historical hand-picked weights (3/2/1/1 -- originally
chosen from an ad hoc AUC decomposition: win counts AUC 0.71-0.80,
rate terms only 0.53-0.56) if the train split is too small or single-class
to fit.

Project size is added as one combined, competitor-specific "size fit"
term -- NOT the plain project-level log_mix_tons/log_grading_yards/etc.
columns already in build_ranking_features.py, which are identical for
every candidate in a project and therefore mathematically cannot change
a within-project ranking (that's also why they show exactly 0.0
importance in the logistic model). Size fit instead compares each
project's active materials (mix_tons, grading_yards, base_tons,
shldr_tons, mill_sy, crush_tons, stock_tons -- whichever are > 0 for
this project) against this competitor's own historical average handled
quantity for that material:

    size_fit_m   = -abs(log1p(project_qty_m) - competitor_avg_log1p_qty_m)
                   (0 = perfect scale match, more negative = bigger
                   mismatch; only computed once a competitor has >= 3
                   qualifying prior bids with material m present)
    size_fit_raw = mean(size_fit_m for active materials with enough data)

A competitor with no qualifying material history falls back to the
population mean of size_fit_raw over the TRAIN split (leakage-safe) --
NOT 0, since 0 is the best possible value in this metric's range and
would otherwise silently reward missing data. An AUC check on the test
split found size_fit_score alone at ~0.63 with this fallback (vs. 0.38
if defaulted to 0) -- real but moderate signal, weaker than the win
count terms, so it gets a matching moderate weight in primary:

    primary  = 3.0 * log1p(win_count_county)
             + 2.0 * log1p(win_count_type)
             + 1.0 * log1p(win_count_state)
             + 1.0 * size_fit_score
    tiebreak = rate_county_shrunk + rate_type_shrunk + rate_state
    simple_rule_score = primary + 1e-6 * tiebreak

All history is strictly before each project's bid_date (no leakage).

Input:  outputs/model1/ranking_predictions.csv  (for project_natural_key/competitor_unit_id/
                                                  bid_date/state/county/project_type keys)
        data/processed/projects.csv, data/processed/bidder_results.csv (history)
Output: outputs/model1/ranking_predictions.csv  (adds simple_rule_score column)
        outputs/simple_rule_baseline_weights.json (the fitted primary-term weights)

Run alongside train_logistic_baseline.py / train_xgboost.py, before evaluate_ranking.py.
"""
from __future__ import annotations

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "shared"))

import argparse
import json

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

from io_utils import read_table

SHRINKAGE_K = 5.0
MATERIALS = ["mix_tons", "grading_yards", "base_tons", "shldr_tons", "mill_sy", "crush_tons", "stock_tons"]
MIN_MATERIAL_BIDS = 3

# Historical hand-picked fallback (see module docstring) — used only if the train split is too
# small or single-class for fit_primary_weights() to fit a meaningful logistic regression.
PRIMARY_FEATURES = ["county", "type", "state", "size_fit"]
FALLBACK_WEIGHTS = {"county": 3.0, "type": 2.0, "state": 1.0, "size_fit": 1.0}
MIN_FIT_ROWS = 50


def build_history(projects_path: str, bidder_results_path: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    projects = read_table(projects_path)
    bidder_results = read_table(bidder_results_path)
    projects["bid_date"] = pd.to_datetime(projects["bid_date"], errors="coerce")
    for m in MATERIALS:
        projects[m] = pd.to_numeric(projects[m], errors="coerce").fillna(0)

    history = bidder_results.merge(
        projects[["project_natural_key", "bid_date", "state", "county", "project_type", *MATERIALS]],
        on="project_natural_key",
        how="left",
        validate="many_to_one",
    )
    history["competitor_unit_id"] = history["competitor_unit_id"].astype(str)
    history["did_win"] = pd.to_numeric(history["did_win"], errors="coerce").fillna(0)
    return history, projects.set_index("project_natural_key")


def fit_primary_weights(
    primary_features: pd.DataFrame,
    did_bid: np.ndarray,
    train_mask: np.ndarray,
) -> tuple[dict[str, float], dict]:
    """Fit a small logistic regression on the 4 primary-term features (train split only) and
    return raw-feature-space weights -- i.e. weights that apply directly to the UNSTANDARDIZED
    columns of `primary_features`, so the caller can keep computing `primary` as a plain linear
    combination (matching the historical hand-picked-constant formula's shape) instead of having
    to carry a fitted scaler through to scoring time.

    Un-standardizing: for a fitted decision function coef @ ((x - mean) / std), the equivalent
    raw-space weight per feature is coef / std (mean folds into the intercept, which is dropped --
    a ranking score's absolute scale doesn't matter, only its ordering, and ROC-AUC/PR-AUC are
    invariant to a per-row-constant shift).

    Falls back to FALLBACK_WEIGHTS (with a printed warning) if the train split is too small or
    single-class to fit meaningfully -- this is a baseline model; it should degrade gracefully,
    not crash a multi-stage pipeline run over a data quirk.

    Also returns the fitted scaler + standardized-space coefficients/intercept in `meta`, under the
    same key names `predict_and_explain.py` already reads from the sklearn-format model json
    (feature_columns/intercept/feature_weights/scaler_mean/scaler_std) -- this is what lets this
    baseline serve live reports (probability + per-feature contributions) through the existing
    reporting pipeline unmodified, not just rank candidates.
    """
    X_train = primary_features.to_numpy()[train_mask]
    y_train = np.asarray(did_bid)[train_mask]

    if len(y_train) < MIN_FIT_ROWS or len(np.unique(y_train)) < 2:
        print(f"  WARNING: train split too small/single-class for fit_primary_weights "
              f"({len(y_train)} rows, {len(np.unique(y_train))} classes) -- "
              f"falling back to hand-picked weights {FALLBACK_WEIGHTS}.")
        return dict(FALLBACK_WEIGHTS), {
            "fit": False, "reason": "insufficient_train_data",
            # Identity scaler + FALLBACK_WEIGHTS-as-coefs so predict_and_explain.py still runs (no
            # KeyError) in this degraded case -- probability won't be calibrated, but won't crash.
            "feature_columns": PRIMARY_FEATURES,
            "intercept": 0.0,
            "feature_weights": dict(FALLBACK_WEIGHTS),
            "scaler_mean": [0.0] * len(PRIMARY_FEATURES),
            "scaler_std": [1.0] * len(PRIMARY_FEATURES),
        }

    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X_train)
    clf = LogisticRegression(C=1.0, class_weight="balanced")
    clf.fit(X_scaled, y_train)

    raw_coef = clf.coef_[0] / scaler.scale_
    weights = dict(zip(PRIMARY_FEATURES, raw_coef.tolist()))
    meta = {
        "fit": True,
        "features": PRIMARY_FEATURES,
        "train_rows": int(len(y_train)),
        "train_positive_rate": round(float(y_train.mean()), 6),
        "sklearn_coef_standardized": dict(zip(PRIMARY_FEATURES, clf.coef_[0].tolist())),
        "sklearn_intercept": float(clf.intercept_[0]),
        # Serving-ready fields (sklearn model-json format) -- see docstring.
        "feature_columns": PRIMARY_FEATURES,
        "intercept": float(clf.intercept_[0]),
        "feature_weights": dict(zip(PRIMARY_FEATURES, clf.coef_[0].tolist())),
        "scaler_mean": scaler.mean_.tolist(),
        "scaler_std": scaler.scale_.tolist(),
    }
    return weights, meta


def build_simple_rule_score(
    predictions: pd.DataFrame,
    history: pd.DataFrame,
    projects_by_job: pd.DataFrame,
) -> tuple[pd.DataFrame, dict]:
    predictions = predictions.copy()
    predictions["bid_date"] = pd.to_datetime(predictions["bid_date"], errors="coerce")

    raw_frames = []
    for project_natural_key, frame in predictions.groupby("project_natural_key", sort=False):
        project = frame.iloc[0]
        bid_date = project["bid_date"]
        state = project.get("state")
        county = project.get("county")
        project_type = project.get("project_type")
        candidate_ids = frame["competitor_unit_id"].astype(str)

        cols = ["n_type", "w_type", "n_county", "w_county", "n_state", "w_state", "n_global", "w_global"]
        base = pd.DataFrame(index=frame.index)
        prior = history[history["bid_date"] < bid_date]

        if prior.empty:
            for col in cols:
                base[col] = 0.0
            base["size_fit_raw"] = np.nan
            raw_frames.append(base)
            continue

        same_type = prior["project_type"] == project_type
        same_county = (prior["county"] == county) & (prior["state"] == state)
        same_state = prior["state"] == state

        def counts_and_wins(mask: pd.Series) -> tuple[pd.Series, pd.Series]:
            subset = prior.loc[mask]
            return subset.groupby("competitor_unit_id").size(), subset.groupby("competitor_unit_id")["did_win"].sum()

        n_type, w_type = counts_and_wins(same_type)
        n_county, w_county = counts_and_wins(same_county)
        n_state, w_state = counts_and_wins(same_state)
        n_global = prior.groupby("competitor_unit_id").size()
        w_global = prior.groupby("competitor_unit_id")["did_win"].sum()

        for col, values in [
            ("n_type", n_type), ("w_type", w_type),
            ("n_county", n_county), ("w_county", w_county),
            ("n_state", n_state), ("w_state", w_state),
            ("n_global", n_global), ("w_global", w_global),
        ]:
            base[col] = candidate_ids.map(values).fillna(0).to_numpy()

        # ── Size fit: competitor's typical scale vs. this project's active materials ──
        project_row = projects_by_job.loc[project_natural_key]
        active_materials = [m for m in MATERIALS if project_row[m] > 0]
        fit_sums = pd.Series(0.0, index=candidate_ids.unique())
        fit_counts = pd.Series(0, index=candidate_ids.unique())
        for m in active_materials:
            proj_log = np.log1p(project_row[m])
            m_prior = prior[prior[m] > 0].copy()
            if m_prior.empty:
                continue
            m_prior["_log_qty"] = np.log1p(m_prior[m])
            grp = m_prior.groupby("competitor_unit_id")["_log_qty"]
            n_m = grp.size()
            avg_log_m = grp.mean()
            qualifying = n_m[n_m >= MIN_MATERIAL_BIDS].index
            for cid in qualifying:
                if cid in fit_sums.index:
                    fit_sums[cid] += -abs(proj_log - avg_log_m[cid])
                    fit_counts[cid] += 1
        with np.errstate(invalid="ignore"):
            size_fit_by_cid = (fit_sums / fit_counts.replace(0, np.nan))
        base["size_fit_raw"] = candidate_ids.map(size_fit_by_cid).to_numpy()

        raw_frames.append(base)

    raw = pd.concat(raw_frames).sort_index()

    global_rate = np.where(raw["n_global"] > 0, raw["w_global"] / raw["n_global"], 0.0)
    rate_state = np.where(raw["n_state"] > 0, raw["w_state"] / raw["n_state"], global_rate)

    k = SHRINKAGE_K
    rate_type_shrunk = (raw["w_type"] + k * rate_state) / (raw["n_type"] + k)
    rate_county_shrunk = (raw["w_county"] + k * rate_state) / (raw["n_county"] + k)

    # Leakage-safe neutral fallback: population mean of real (non-NaN) size_fit_raw
    # values on the TRAIN split only. 0 would be wrong here -- it's the ceiling of
    # this metric's range (perfect fit), so defaulting missing data to 0 would
    # silently reward competitors with no size history over ones with a real,
    # imperfect fit.
    train_mask = (predictions["time_split"] == "train").to_numpy()
    train_fit_values = raw["size_fit_raw"].to_numpy()[train_mask]
    neutral_fallback = np.nanmean(train_fit_values) if np.isfinite(np.nanmean(train_fit_values)) else 0.0
    size_fit_score = raw["size_fit_raw"].fillna(neutral_fallback).to_numpy()

    primary_features = pd.DataFrame({
        "county": np.log1p(raw["w_county"]).to_numpy(),
        "type": np.log1p(raw["w_type"]).to_numpy(),
        "state": np.log1p(raw["w_state"]).to_numpy(),
        "size_fit": size_fit_score,
    })
    weights, fit_meta = fit_primary_weights(
        primary_features, predictions["did_bid"].to_numpy(), train_mask,
    )
    fit_meta["weights"] = weights

    primary = (
        weights["county"] * primary_features["county"].to_numpy()
        + weights["type"] * primary_features["type"].to_numpy()
        + weights["state"] * primary_features["state"].to_numpy()
        + weights["size_fit"] * primary_features["size_fit"].to_numpy()
    )
    tiebreak = rate_county_shrunk.to_numpy() + rate_type_shrunk.to_numpy() + rate_state

    predictions["simple_rule_score"] = primary + 1e-6 * tiebreak
    # PRIMARY_FEATURES includes "county" and "state", which collide with the project's actual
    # state/county abbreviation columns already on `predictions` (e.g. "MN"/"STEARNS") -- the
    # overwrite loop below replaces those with the numeric feature values. Save the real identity
    # under new names FIRST so orchestrator.py/executor.py can still read a place name after this
    # function returns; see project_state/project_county at those call sites.
    predictions["project_state"] = predictions["state"]
    predictions["project_county"] = predictions["county"]
    # Persist the 4 raw (unstandardized) inputs as columns too -- serving-time predict_and_explain()
    # reads feature values straight off the predictions row via model["feature_columns"], so this
    # baseline can't produce a live probability/explanation without them sitting on the row.
    for col in PRIMARY_FEATURES:
        predictions[col] = primary_features[col].to_numpy()
    return predictions, fit_meta


def _backfill_missing_winners(sample: pd.DataFrame, history: pd.DataFrame, project_natural_keys) -> pd.DataFrame:
    """Add a row for a project's actual winner when the candidate-selection rule never proposed
    them as a candidate (candidate_recall < 1 -- see candidate_filter.py's own audit; this is
    common, not a bug). This is display-only, for a REVIEWED sample: the model itself is
    correctly trained only on rule-selected candidates (build_ranking_training_panel's own
    leakage-safety rationale -- at real inference time you don't know the winner yet, so training
    on a candidate pool that always includes them would teach the model something it can never
    use). Backfilled rows are flagged `backfilled_winner=1` and left unscored (NaN in every
    model's score column) rather than fabricating a score for a competitor the model never
    actually evaluated -- the blank is itself the honest answer to "what did the model think of
    them" (nothing; it never saw them).
    """
    sample = sample.copy()
    sample["backfilled_winner"] = 0
    winners = history[history["did_win"] == 1]
    rows = []
    for project_natural_key in project_natural_keys:
        have = set(sample.loc[sample["project_natural_key"] == project_natural_key, "competitor_unit_id"].astype(str))
        for _, w in winners[winners["project_natural_key"] == project_natural_key].iterrows():
            cid = str(w["competitor_unit_id"])
            if cid in have:
                continue
            row = {col: pd.NA for col in sample.columns}
            row.update({
                "project_natural_key": project_natural_key, "competitor_unit_id": cid,
                "did_bid": 1, "did_win": 1, "backfilled_winner": 1,
            })
            if "bid_rank" in sample.columns:
                row["bid_rank"] = w.get("bid_rank")
            for col in ("time_split", "bid_date", "state", "county", "project_type"):
                if col in sample.columns:
                    existing = sample.loc[sample["project_natural_key"] == project_natural_key, col]
                    if not existing.empty:
                        row[col] = existing.iloc[0]
            rows.append(row)
    if rows:
        sample = pd.concat([sample, pd.DataFrame(rows)], ignore_index=True)
    return sample


def write_predictions_sample(
    predictions: pd.DataFrame,
    history: pd.DataFrame,
    output_path: Path,
    n_projects: int = 20,
    seed: int = 0,
) -> Path:
    """A reviewable slice of the (94 MB, 230k-row) ranking_predictions.csv: pick a handful of
    whole projects rather than a flat random row sample -- a flat sample at this row count would
    be ~97% non-bidder rows (did_bid's positive rate is ~2.7%) and wouldn't show what an actual
    ranked project looks like. Keeps EVERY candidate row for each chosen project, so you can see
    the full ranked field -- who bid, who didn't, and how each model scored them -- side by side.
    Biased toward projects with at least one actual bidder (more informative to read); spans
    whichever time_splits are present. Deterministic (fixed seed).

    Also backfills each chosen project's actual winner if the candidate pool is missing them --
    see _backfill_missing_winners for why that's safe to do here but not in training.
    """
    has_bidder = predictions.groupby("project_natural_key")["did_bid"].transform("max") > 0
    pool = predictions.loc[has_bidder, "project_natural_key"].unique()
    if len(pool) == 0:
        pool = predictions["project_natural_key"].unique()
    rng = np.random.default_rng(seed)
    chosen = rng.choice(pool, size=min(n_projects, len(pool)), replace=False)

    sample = predictions[predictions["project_natural_key"].isin(chosen)].copy()
    sample = _backfill_missing_winners(sample, history, chosen)
    sort_col = "logistic_score" if "logistic_score" in sample.columns else "rule_score"
    sample = sample.sort_values(["project_natural_key", sort_col], ascending=[True, False], na_position="last")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    sample.to_csv(output_path, index=False)
    return output_path


def main() -> None:
    _STEP_OUT = Path(__file__).resolve().parent / "outputs"
    parser = argparse.ArgumentParser(description="Compute simple rule-based competitor score (segment win rates).")
    parser.add_argument("--predictions", default=str(_STEP_OUT / "ranking_predictions.csv"))
    parser.add_argument("--projects", default="data/processed/projects.parquet")
    parser.add_argument("--bidder-results", default="data/processed/bidder_results.parquet")
    parser.add_argument("--predictions-output", default=str(_STEP_OUT / "ranking_predictions.csv"))
    parser.add_argument("--weights-output", default=str(_STEP_OUT / "simple_rule_baseline_weights.json"))
    parser.add_argument("--predictions-sample-output", default=str(_STEP_OUT / "ranking_predictions_sample.csv"))
    parser.add_argument("--sample-projects", type=int, default=20)
    args = parser.parse_args()

    predictions = pd.read_csv(args.predictions)
    history, projects_by_job = build_history(args.projects, args.bidder_results)
    predictions, fit_meta = build_simple_rule_score(predictions, history, projects_by_job)

    Path(args.predictions_output).parent.mkdir(parents=True, exist_ok=True)
    predictions.to_csv(args.predictions_output, index=False)

    Path(args.weights_output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.weights_output).write_text(json.dumps(fit_meta, indent=2))

    # This is the last stage to touch ranking_predictions.csv (after logistic + xgboost have
    # already merged their score columns in), so it's the right place to snapshot a reviewable
    # sample with every model's score present.
    sample_path = write_predictions_sample(
        predictions, history, Path(args.predictions_sample_output), n_projects=args.sample_projects,
    )

    print(f"Simple rule-based score complete")
    print(f"  rows:    {len(predictions):,}")
    print(f"  output:  {args.predictions_output}")
    print(f"  weights: {args.weights_output}  {fit_meta['weights']}")
    print(f"  sample:  {sample_path}  ({args.sample_projects} projects, all candidate rows)")


if __name__ == "__main__":
    main()
