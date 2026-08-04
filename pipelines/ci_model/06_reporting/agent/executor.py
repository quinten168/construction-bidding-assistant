"""
Executor Agent (ReAct loop)

For each competitor:
  Thought → predict_and_explain → Observe
  Thought → generate_narrative  → Observe
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.planner import classify_threat
from tools.predict_and_explain import predict_and_explain
from tools.get_competitor_profile import get_competitor_profile
from tools.generate_narrative import generate_narrative
from tools.capacity_live import bucket_seasons


def _compute_win_stats(
    all_predictions: pd.DataFrame,
    competitor_unit_id: str,
    row: pd.Series,
    tons_lookup: dict | None = None,
    live_capacity_df: pd.DataFrame | None = None,
) -> dict:
    """County-, state-, project-type-level win rates + season capacity from full historical data.

    Capacity (season-by-season win/tonnage history) prefers `live_capacity_df` -- a live Supabase
    query result, one row per (competitor, historical bid), fetched once for the whole report by
    orchestrator.py -- and falls back to building the same shape from the local `all_predictions` +
    `tons_lookup` snapshot when no live data was supplied (DSN unset, or the query failed; see
    tools/capacity_live.py's fail-open contract). Either way the season bucketing itself is the
    same function (tools/capacity_live.py::bucket_seasons), so the two sources produce identical
    output shape and a caller downstream (generate_narrative.py) doesn't need to know which one
    fired.
    """
    # "county"/"state" hold the simple-rule model's numeric input features, not the project's
    # actual state/county abbreviation -- see train_simple_rule_baseline.py's project_state/
    # project_county comment for why. Use the preserved identity columns instead.
    comp = all_predictions[
        (all_predictions["competitor_unit_id"] == competitor_unit_id)
        & (all_predictions["did_bid"] == 1)
    ].copy()

    def _counts(mask: pd.Series) -> tuple[int, int]:
        subset = comp[mask]
        return int((subset["did_win"] == 1).sum()), len(subset)

    county = row.get("project_county")
    state  = row.get("project_state")
    ptype  = row.get("project_type")

    county_w, county_b = _counts(comp["project_county"] == county) if county else (0, 0)
    state_w,  state_b  = _counts(comp["project_state"]  == state)  if state  else (0, 0)
    type_w,   type_b   = _counts(comp["project_type"] == ptype) if ptype else (0, 0)

    # ── Season capacity ────────────────────────────────────────────────────────
    if live_capacity_df is not None:
        history = live_capacity_df[live_capacity_df["competitor_unit_id"] == competitor_unit_id]
    else:
        history = comp[["bid_date", "project_natural_key", "did_win"]].copy()
        history["mix_tons"] = history["project_natural_key"].map(
            lambda pk: float((tons_lookup or {}).get(pk, 0) or 0)
        )
    capacity = bucket_seasons(history, str(row.get("bid_date", "") or ""))

    return {
        "county":               county or "—",
        "county_wins":          county_w,  "county_bids":  county_b,
        "state_wins":           state_w,   "state_bids":   state_b,
        "type_wins":            type_w,    "type_bids":    type_b,
        "capacity":             capacity,   # {"current", "prior_seasons", "trend"} or None
        "capacity_live":        live_capacity_df is not None,
    }


def execute_one(
    competitor_unit_id: str,
    project_rows: pd.DataFrame,
    model: dict,
    client=None,
    llm_model: str = "claude-sonnet-4-6",
    verbose: bool = False,
    name_lookup: dict | None = None,
    all_predictions: pd.DataFrame | None = None,
    tons_lookup: dict | None = None,
    live_capacity_df: pd.DataFrame | None = None,
) -> dict | None:
    """
    Run the ReAct loop for a single competitor.

    Returns a dict with all data needed by the Reflector and Reporter,
    or None if the competitor row is missing.
    """
    rows = project_rows[project_rows["competitor_unit_id"] == competitor_unit_id]
    if rows.empty:
        return None
    row = rows.iloc[0]

    # ── Thought: "What do we know about this competitor?" ─────────────────────
    if verbose:
        print(f"    [Executor] Analyzing {competitor_unit_id}")

    # ── Action 1: predict_and_explain ─────────────────────────────────────────
    prediction = predict_and_explain(row, model)
    profile    = get_competitor_profile(row, name_lookup)

    prob         = prediction["bid_probability"]
    threat_level = classify_threat(prob)

    if verbose:
        print(f"      probability={prob:.3f}  threat={threat_level}")

    # ── Action 2: compute win stats from full history ─────────────────────────
    win_stats = None
    if all_predictions is not None:
        win_stats = _compute_win_stats(
            all_predictions, competitor_unit_id, row, tons_lookup, live_capacity_df,
        )
        win_stats["mix_tons"]    = float(row.get("mix_tons", 0) or 0)
        win_stats["bid_date"]    = str(row.get("bid_date", "") or "")
        win_stats["project_type"] = str(row.get("project_type", "") or "")

    # ── Action 3: generate_narrative ──────────────────────────────────────────
    narrative = generate_narrative(
        contributions    = prediction["raw_contributions"],
        feature_values   = prediction["feature_values"],
        competitor_name  = profile["display_name"],
        probability      = prob,
        threat_level     = threat_level,
        win_stats        = win_stats,
        client           = client,
        model            = llm_model,
        temperature      = 0.3,
    )

    tier = int(row.get("tier", 2))

    return {
        "competitor_id":          competitor_unit_id,
        "display_name":           profile["display_name"],
        "bid_probability":        prob,
        "threat_level":           threat_level,
        "tier":                   tier,          # 1 = priority, 2 = discovery
        "narrative":              narrative,
        "top_reasons_to_bid":     prediction["top_reasons_to_bid"],
        "top_reasons_not_to_bid": prediction["top_reasons_not_to_bid"],
        "raw_contributions":      prediction["raw_contributions"],
        "feature_values":         prediction["feature_values"],
        "profile":                profile,
    }


def execute_all(
    competitor_ids: list[str],
    project_rows: pd.DataFrame,
    model: dict,
    client=None,
    llm_model: str = "claude-sonnet-4-6",
    verbose: bool = False,
    name_lookup: dict | None = None,
    all_predictions: pd.DataFrame | None = None,
    tons_lookup: dict | None = None,
    live_capacity_df: pd.DataFrame | None = None,
) -> list[dict]:
    """Run execute_one for every competitor in the planned list."""
    results = []
    for cid in competitor_ids:
        result = execute_one(
            cid, project_rows, model, client, llm_model, verbose,
            name_lookup=name_lookup, all_predictions=all_predictions,
            tons_lookup=tons_lookup, live_capacity_df=live_capacity_df,
        )
        if result is not None:
            results.append(result)
    return results
