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


def _bid_year(d) -> int:
    """Bid year for a date (Sept 1 → April 30 bidding season). Returns the April-30 year.
    May–Aug are off-season; treat as the prior completed season's year."""
    if d.month >= 9:    # Sept–Dec: season closes next April
        return d.year + 1
    else:               # Jan–Aug: season closes this April (or already closed)
        return d.year


def _compute_win_stats(
    all_predictions: pd.DataFrame,
    competitor_unit_id: str,
    row: pd.Series,
    tons_lookup: dict | None = None,
) -> dict:
    """County-, state-, project-type-level win rates + season capacity from full historical data."""
    comp = all_predictions[
        (all_predictions["competitor_unit_id"] == competitor_unit_id)
        & (all_predictions["did_bid"] == 1)
    ].copy()

    def _counts(mask: pd.Series) -> tuple[int, int]:
        subset = comp[mask]
        return int((subset["did_win"] == 1).sum()), len(subset)

    def _season_tons(season_df: pd.DataFrame) -> float:
        """Sum mix_tons for all won projects in a season slice using the tons_lookup
        (tons_lookup is keyed by project_natural_key -- see orchestrator.py)."""
        if not tons_lookup:
            return 0.0
        won = season_df[season_df["did_win"] == 1]
        return sum(float(tons_lookup.get(pk, 0) or 0) for pk in won["project_natural_key"])

    # "county"/"state" hold the simple-rule model's numeric input features, not the project's
    # actual state/county abbreviation -- see train_simple_rule_baseline.py's project_state/
    # project_county comment for why. Use the preserved identity columns instead.
    county = row.get("project_county")
    state  = row.get("project_state")
    ptype  = row.get("project_type")

    county_w, county_b = _counts(comp["project_county"] == county) if county else (0, 0)
    state_w,  state_b  = _counts(comp["project_state"]  == state)  if state  else (0, 0)
    type_w,   type_b   = _counts(comp["project_type"] == ptype) if ptype else (0, 0)

    # ── Season capacity ────────────────────────────────────────────────────────
    season_wins = None
    season_tons = None
    season_bids = 0
    season_label = ""
    historical_avg_wins = None
    historical_avg_tons = None
    historical_seasons = 0

    bid_date_str = str(row.get("bid_date", "") or "")
    if bid_date_str:
        try:
            from datetime import datetime, date as _date
            target = datetime.strptime(bid_date_str[:10], "%Y-%m-%d").date()
            cur_by = _bid_year(target)
            cur_start = _date(cur_by - 1, 9, 1)

            comp["_date"] = pd.to_datetime(comp["bid_date"], errors="coerce").dt.date
            comp_dated = comp.dropna(subset=["_date"])

            # Current season: season_start ≤ date < min(project bid date, season end Apr 30)
            cur_end = _date(cur_by, 4, 30)
            cur_cutoff = min(target, cur_end)
            cur = comp_dated[
                (comp_dated["_date"] >= cur_start) & (comp_dated["_date"] < cur_cutoff)
            ]
            season_wins = int((cur["did_win"] == 1).sum())
            season_tons = _season_tons(cur)
            season_bids = len(cur)
            season_label = f"{cur_by - 1}–{cur_by} season (Sept–Apr)"

            # Prior complete seasons (up to 3); each is Sept 1 → Apr 30
            prior_wins_list = []
            prior_tons_list = []
            for by in range(cur_by - 1, cur_by - 4, -1):
                ps_start = _date(by - 1, 9, 1)
                ps_end   = _date(by, 4, 30)
                ps = comp_dated[
                    (comp_dated["_date"] >= ps_start) & (comp_dated["_date"] <= ps_end)
                ]
                if len(ps) > 0:
                    prior_wins_list.append(int((ps["did_win"] == 1).sum()))
                    prior_tons_list.append(_season_tons(ps))

            historical_seasons = len(prior_wins_list)
            if prior_wins_list:
                historical_avg_wins = sum(prior_wins_list) / len(prior_wins_list)
                historical_avg_tons = sum(prior_tons_list) / len(prior_tons_list)
        except Exception:
            pass

    return {
        "county":               county or "—",
        "county_wins":          county_w,  "county_bids":  county_b,
        "state_wins":           state_w,   "state_bids":   state_b,
        "type_wins":            type_w,    "type_bids":    type_b,
        "season_wins":          season_wins,
        "season_tons":          season_tons,
        "season_bids":          season_bids,
        "season_label":         season_label,
        "historical_avg_wins":  historical_avg_wins,
        "historical_avg_tons":  historical_avg_tons,
        "historical_seasons":   historical_seasons,
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
        win_stats = _compute_win_stats(all_predictions, competitor_unit_id, row, tons_lookup)
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
) -> list[dict]:
    """Run execute_one for every competitor in the planned list."""
    results = []
    for cid in competitor_ids:
        result = execute_one(
            cid, project_rows, model, client, llm_model, verbose,
            name_lookup=name_lookup, all_predictions=all_predictions,
            tons_lookup=tons_lookup,
        )
        if result is not None:
            results.append(result)
    return results
