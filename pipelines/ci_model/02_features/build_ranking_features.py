#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "shared"))

import argparse

import numpy as np
import pandas as pd

from config import (
    DEFAULT_CANDIDATE_RULE,
    PIT_RANKING_FEATURE_COLUMNS,
    RANKING_FEATURE_COLUMNS,
)
from io_utils import read_table, write_table


BASE_RANKING_FEATURE_COLUMNS = [
    col for col in RANKING_FEATURE_COLUMNS if col not in PIT_RANKING_FEATURE_COLUMNS
]

# Scope-match features, one per bid-schedule quantity — every material we have real quantity
# data for gets its own match feature, keyed by that quantity alone (no keyword-guessed flags;
# those, e.g. has_paving/has_grading/has_base, were removed as unconfirmed by the client).
QUANTITY_MATCH_SPECS = {
    "mix_tons_match": ("mix_tons",),
    "grading_yards_match": ("grading_yards",),
    "base_tons_match": ("base_tons",),
    "shldr_tons_match": ("shldr_tons",),
    "mill_sy_match": ("mill_sy",),
    "crush_tons_match": ("crush_tons",),
    "stock_tons_match": ("stock_tons",),
}

# The 7 bid-schedule quantities project_size_proxy averages over (non-zero ones only).
_SIZE_QUANTITIES = [
    "mix_tons", "grading_yards", "base_tons", "shldr_tons",
    "mill_sy", "crush_tons", "stock_tons",
]


def _safe_numeric(series: pd.Series | int | float, default: float = 0.0) -> pd.Series:
    if isinstance(series, pd.Series):
        return pd.to_numeric(series, errors="coerce").fillna(default)
    return pd.Series([series]).astype(float)


def _history_count(prior: pd.DataFrame, mask: pd.Series) -> pd.Series:
    return prior.loc[mask].groupby("competitor_unit_id").size()


def _add_rule_score(features: pd.DataFrame) -> pd.DataFrame:
    result = features.copy()
    recency_penalty = np.minimum(result["days_since_last_bid"].fillna(9999), 9999) / 365.0
    recent_12m_activity = (
        result["bids_0_3m"] + result["bids_3_6m"] + result["bids_6_12m"]
    )
    result["rule_score"] = (
        3.0 * result["same_county_prior_bid_count"]
        + 2.0 * result["same_project_type_bid_count"]
        + 1.0 * recent_12m_activity
        + 0.5 * result["prior_win_count"]
        - 0.25 * recency_penalty
    )
    return result


def _feature_default(col: str) -> float:
    if col.startswith("nearest_") or col.endswith("_miles"):
        return 9999.0
    return 0.0


def _merge_pit_features(
    features: pd.DataFrame,
    pit_features: pd.DataFrame | None,
) -> pd.DataFrame:
    result = features.copy()
    if pit_features is None:
        for col in PIT_RANKING_FEATURE_COLUMNS:
            result[col] = _feature_default(col)
        return result

    keys = ["project_natural_key", "competitor_unit_id"]
    missing = [col for col in keys if col not in pit_features.columns]
    if missing:
        raise ValueError(f"Pit features are missing required columns: {missing}")

    pit = pit_features.drop_duplicates(keys).copy()
    pit["competitor_unit_id"] = pit["competitor_unit_id"].astype(str)
    keep_cols = [
        col
        for col in [
            *keys,
            "project_location_source",
            "project_location_confidence",
            *PIT_RANKING_FEATURE_COLUMNS,
        ]
        if col in pit.columns
    ]
    result["competitor_unit_id"] = result["competitor_unit_id"].astype(str)
    result = result.merge(pit[keep_cols], on=keys, how="left", validate="many_to_one")
    for col in PIT_RANKING_FEATURE_COLUMNS:
        if col not in result.columns:
            result[col] = _feature_default(col)
        result[col] = pd.to_numeric(result[col], errors="coerce").fillna(_feature_default(col))
    return result


def build_ranking_features(
    ranking_panel: pd.DataFrame,
    projects: pd.DataFrame,
    bidder_results: pd.DataFrame,
    candidate_rule: str,
    pit_features: pd.DataFrame | None = None,
    combined_data: pd.DataFrame | None = None,
) -> pd.DataFrame:
    panel = ranking_panel[
        ranking_panel["candidate_rule_version"] == candidate_rule
    ].copy()
    projects = projects.copy()
    bidder_results = bidder_results.copy()

    panel["bid_date"] = pd.to_datetime(panel["bid_date"], errors="coerce")
    projects["bid_date"] = pd.to_datetime(projects["bid_date"], errors="coerce")

    # Build date → bid_year lookup from CSI combined data
    date_to_bid_year: dict = {}
    if combined_data is not None and "bid_year" in combined_data.columns:
        _cd = combined_data.copy()
        _cd["DATE"] = pd.to_datetime(_cd.get("DATE"), errors="coerce")
        date_to_bid_year = (
            _cd.dropna(subset=["DATE", "bid_year"])
            .drop_duplicates("DATE")
            .set_index("DATE")["bid_year"]
            .to_dict()
        )

    history_cols = [
        "project_natural_key",
        "bid_date",
        "state",
        "county",
        "project_type",
        *_SIZE_QUANTITIES,
    ]
    history = bidder_results.merge(
        projects[[col for col in history_cols if col in projects.columns]],
        on="project_natural_key",
        how="left",
        validate="many_to_one",
    )
    history["bid_date"] = pd.to_datetime(history["bid_date"], errors="coerce")
    history["competitor_unit_id"] = history["competitor_unit_id"].astype(str)
    history["did_win"] = pd.to_numeric(history["did_win"], errors="coerce").fillna(0)
    # Quantities behind QUANTITY_MATCH_SPECS' historical (prior-project) side — all 7, one per
    # scope-match feature.
    for _qcol in _SIZE_QUANTITIES:
        if _qcol not in history.columns:
            history[_qcol] = 0
        history[_qcol] = pd.to_numeric(history[_qcol], errors="coerce").fillna(0)
    history["bid_year"] = history["bid_date"].map(date_to_bid_year)

    feature_frames = []
    for project_natural_key, frame in panel.groupby("project_natural_key", sort=False):
        project = frame.iloc[0]
        bid_date = project["bid_date"]
        state = project.get("state")
        county = project.get("county")
        project_type = project.get("project_type")
        candidate_ids = frame["competitor_unit_id"].astype(str)
        prior = history[history["bid_date"] < bid_date].copy()

        base = pd.DataFrame(
            {
                "project_natural_key": project_natural_key,
                "competitor_unit_id": candidate_ids,
            },
            index=frame.index,
        )

        prior_project_count = max(int(prior["project_natural_key"].nunique()), 1)
        if prior.empty:
            for col in BASE_RANKING_FEATURE_COLUMNS:
                base[col] = 0
            base["days_since_last_bid"] = 9999
            feature_frames.append(base)
            continue

        same_state = prior["state"] == state
        same_county = same_state & (prior["county"] == county)
        same_type = same_state & (prior["project_type"] == project_type)
        recent_3m  = prior["bid_date"] >= bid_date - pd.Timedelta(days=90)
        recent_6m  = prior["bid_date"] >= bid_date - pd.Timedelta(days=180)
        recent_9m  = prior["bid_date"] >= bid_date - pd.Timedelta(days=270)
        recent_12m = prior["bid_date"] >= bid_date - pd.Timedelta(days=365)
        recent_24m = prior["bid_date"] >= bid_date - pd.Timedelta(days=730)

        maps = {
            "prior_bid_count": prior.groupby("competitor_unit_id").size(),
            "prior_win_count": prior.groupby("competitor_unit_id")["did_win"].sum(),
            "recent_3m_bid_count":  _history_count(prior, recent_3m),
            "recent_6m_bid_count":  _history_count(prior, recent_6m),
            "recent_9m_bid_count":  _history_count(prior, recent_9m),
            "recent_12m_bid_count": _history_count(prior, recent_12m),
            "recent_24m_bid_count": _history_count(prior, recent_24m),
            "same_state_prior_bid_count": _history_count(prior, same_state),
            "same_county_prior_bid_count": _history_count(prior, same_county),
            "same_project_type_bid_count": _history_count(prior, same_type),
        }
        for col, values in maps.items():
            base[col] = candidate_ids.map(values).fillna(0).to_numpy()

        # Non-overlapping windows keep each activity period independently interpretable.
        base["bids_0_3m"] = base["recent_3m_bid_count"]
        base["bids_3_6m"] = base["recent_6m_bid_count"] - base["recent_3m_bid_count"]
        base["bids_6_12m"] = base["recent_12m_bid_count"] - base["recent_6m_bid_count"]
        base["bids_12_24m"] = base["recent_24m_bid_count"] - base["recent_12m_bid_count"]
        base["active_in_0_3m"] = (base["bids_0_3m"] > 0).astype(int)

        base["prior_bid_rate"] = base["prior_bid_count"] / prior_project_count
        base["prior_win_rate"] = np.where(
            base["prior_bid_count"] > 0,
            base["prior_win_count"] / base["prior_bid_count"],
            0,
        )
        base["ever_bid_same_project_type"] = (base["same_project_type_bid_count"] > 0).astype(int)

        last_bid = prior.groupby("competitor_unit_id")["bid_date"].max()
        last_dates = candidate_ids.map(last_bid)
        base["days_since_last_bid"] = (bid_date - last_dates).dt.days.fillna(9999).to_numpy()

        def _pv(key: str) -> float:
            return float(pd.to_numeric(pd.Series([project.get(key, 0)]), errors="coerce").fillna(0).iloc[0])

        # Scope-match features, one per bid-schedule quantity. Quantities are actual bid-schedule
        # data, never guessed from keyword matches, and we have one for every material.
        for match_col, qcols in QUANTITY_MATCH_SPECS.items():
            if match_col not in RANKING_FEATURE_COLUMNS:
                continue
            prior_mask = pd.Series(False, index=prior.index)
            for qc in qcols:
                prior_mask |= pd.to_numeric(prior.get(qc, 0), errors="coerce").fillna(0) > 0
            prior_flag_count = prior.loc[prior_mask].groupby("competitor_unit_id").size()
            current_has = any(_pv(qc) > 0 for qc in qcols)
            base[match_col] = (
                int(current_has)
                * (candidate_ids.map(prior_flag_count).fillna(0).to_numpy() > 0).astype(int)
            )

        base["log_mix_tons"]     = np.log1p(max(_pv("mix_tons"), 0))
        base["log_grading_yards"] = np.log1p(max(_pv("grading_yards"), 0))
        base["log_base_tons"]    = np.log1p(max(_pv("base_tons"), 0))
        base["log_shldr_tons"]   = np.log1p(max(_pv("shldr_tons"), 0))
        base["log_mill_sy"]      = np.log1p(max(_pv("mill_sy"), 0))
        base["log_crush_tons"]   = np.log1p(max(_pv("crush_tons"), 0))
        base["log_stock_tons"]   = np.log1p(max(_pv("stock_tons"), 0))
        # Project size: average log1p(quantity) over whichever of the 7 quantities this project
        # actually has (non-zero) — not a sum (rewards touching more material types, not true
        # size) and not an average over all 7 including zeros (penalizes a narrow-scope project,
        # e.g. milling-only, for legitimately lacking the other 6).
        _present_logs = [v for v in (np.log1p(max(_pv(q), 0)) for q in _SIZE_QUANTITIES) if v > 0]
        base["project_size_proxy"] = float(np.mean(_present_logs)) if _present_logs else 0.0

        # Mix ton capacity ratio: YTD won mix_tons in current bid_year ÷ mean won per prior bid_year
        if date_to_bid_year:
            current_bid_year = date_to_bid_year.get(bid_date)
            won = prior[prior["did_win"] == 1].copy()
            if current_bid_year is not None and not won.empty and "bid_year" in won.columns:
                ytd_won = won[won["bid_year"] == current_bid_year]
                ytd_mix = ytd_won.groupby("competitor_unit_id")["mix_tons"].sum()

                hist_won = won[won["bid_year"] < current_bid_year]
                if not hist_won.empty:
                    per_year = hist_won.groupby(["competitor_unit_id", "bid_year"])["mix_tons"].sum()
                    hist_avg = per_year.groupby(level=0).mean()
                else:
                    hist_avg = pd.Series(dtype=float)

                ytd_per = candidate_ids.map(ytd_mix).fillna(0).to_numpy()
                avg_per = candidate_ids.map(hist_avg).fillna(0).to_numpy()
                base["mix_ton_capacity_ratio"] = np.where(avg_per > 0, ytd_per / avg_per, 0.0)
            else:
                base["mix_ton_capacity_ratio"] = 0.0
        else:
            base["mix_ton_capacity_ratio"] = 0.0

        feature_frames.append(base)

    features = pd.concat(feature_frames).sort_index()
    new_cols = features.drop(columns=["project_natural_key", "competitor_unit_id"])
    new_cols = new_cols.drop(
        columns=[col for col in new_cols.columns if col in panel.columns],
        errors="ignore",
    )
    result = panel.join(new_cols)
    result = _merge_pit_features(result, pit_features)
    for col in RANKING_FEATURE_COLUMNS:
        result[col] = pd.to_numeric(result[col], errors="coerce").fillna(_feature_default(col))
    result = _add_rule_score(result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Build leakage-safe Model 1 ranking features.")
    parser.add_argument("--ranking-panel", default="data/processed/model1/ranking_training_panel.parquet")
    parser.add_argument("--projects", default="data/processed/projects.parquet")
    parser.add_argument("--bidder-results", default="data/processed/bidder_results.parquet")
    parser.add_argument("--pit-features", default="data/processed/model1/pit_features.parquet")
    parser.add_argument("--combined-data", default="data/processed/CSI_data_combined.parquet")
    parser.add_argument("--candidate-rule", default=DEFAULT_CANDIDATE_RULE)
    parser.add_argument("--output", default="data/processed/model1/ranking_features.parquet")
    args = parser.parse_args()

    ranking_panel = read_table(args.ranking_panel)
    projects = read_table(args.projects)
    bidder_results = read_table(args.bidder_results)
    pit_features = read_table(args.pit_features) if args.pit_features else None
    # read_table falls back to the .csv twin automatically if no .parquet exists yet (see
    # shared/io_utils.py) — CSI_data_combined.parquet isn't produced by any script yet, so this
    # relies on that fallback rather than requiring a new writer.
    combined_data = read_table(args.combined_data)[["DATE", "bid_year"]] if args.combined_data else None
    features = build_ranking_features(
        ranking_panel=ranking_panel,
        projects=projects,
        bidder_results=bidder_results,
        candidate_rule=args.candidate_rule,
        pit_features=pit_features,
        combined_data=combined_data,
    )
    written = write_table(features, args.output)
    print("Ranking features complete")
    print(f"  candidate rule: {args.candidate_rule}")
    print(f"  output:         {written}")
    print(f"  rows:           {len(features):,}")
    print(f"  projects:       {features['project_natural_key'].nunique():,}")
    print(f"  positive rate:  {features['did_bid'].mean():.4f}")


if __name__ == "__main__":
    main()
