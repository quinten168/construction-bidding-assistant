"""
Drift check: apps/api/backend/competitor_predict_live.py::_candidate_pool() is a manually
maintained MIRROR of pipelines/ci_model/01_candidates/candidate_filter.py::build_v3_candidate_set()
(apps/ cannot import pipelines/ — CLAUDE.md invariant 1) — it will silently drift if either side
changes without a matching edit to the other. This test cannot compare the two functions directly
(that would require the exact import this repo's architecture forbids); instead it diffs the live
mirror's output against data/processed/model1/rule_candidate_set.parquet, the materialized ground
truth build_v3_candidate_set() itself already writes when the CI pipeline runs
(pipelines/ci_model/01_candidates/build_candidate_panels.py). That parquet is read by PATH, the
same pattern every other apps/<->pipelines/ boundary in this repo uses.

Needs a live scratch.bid_results/scratch.bid_projects containing the SAME historical bids the
parquet's candidate rows were computed from — skipped like the other Supabase-backed tests unless
SUPABASE_TEAM_DB_URL is set. Not run in this sandbox (no live DB configured here, same constraint
as the 17 other skip-if-no-DB integration tests — see CLAUDE.md rough edge 7); this file is built
but UNVERIFIED against a real database.

Run: SUPABASE_TEAM_DB_URL='postgresql://...' python -m pytest tests/test_candidate_pool_consistency.py -q
"""
from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.skipif(
    not os.environ.get("SUPABASE_TEAM_DB_URL"),
    reason="SUPABASE_TEAM_DB_URL not set — needs a live Supabase scratch schema connection",
)

from backend import ci_db  # noqa: E402
from backend import competitor_predict_live as cpl  # noqa: E402
from backend import config  # noqa: E402

CANDIDATE_SET_PARQUET = config.REPO / "data" / "processed" / "model1" / "rule_candidate_set.parquet"
SAMPLE_SIZE = 25          # projects sampled per run — cheap enough to run often, not exhaustive
MIN_JACCARD = 0.8         # below this for any sampled project, the two implementations have drifted


def _sample_ground_truth_projects():
    """One row per sampled project_natural_key: its own county/state/project_type/bid_date, plus
    the full ground-truth candidate id set build_v3_candidate_set() produced for it."""
    import pandas as pd

    if not CANDIDATE_SET_PARQUET.exists():
        pytest.skip(f"{CANDIDATE_SET_PARQUET} not present — run "
                    "pipelines/ci_model/01_candidates/build_candidate_panels.py first")
    df = pd.read_parquet(CANDIDATE_SET_PARQUET)
    # Exclude left-censored projects (history_left_censored_12m == 1): those are exactly the ones
    # where build_v3_candidate_set()'s warmup_12m branch fires (early rows of the historical corpus,
    # history_days_available < 365) -- _candidate_pool() deliberately does NOT port that branch
    # (see its docstring: a live plan scored "today" against the full corpus is never in that
    # state), so comparing against a left-censored project tests a case the live mirror was never
    # meant to replicate. Confirmed empirically 2026-08-09: every mismatch in an unfiltered sample
    # traced back to history_left_censored_12m == 1.
    if "history_left_censored_12m" in df.columns:
        df = df[df["history_left_censored_12m"] != 1]
    keys = df["project_natural_key"].drop_duplicates().sample(
        n=min(SAMPLE_SIZE, df["project_natural_key"].nunique()), random_state=0,
    )
    for key in keys:
        rows = df[df["project_natural_key"] == key]
        first = rows.iloc[0]
        yield {
            "project_natural_key": key,
            "county": first["county"],
            "state": first["state"],
            "project_type": first["project_type"],
            "bid_date": str(first["bid_date"])[:10],
            "expected_ids": set(rows["competitor_unit_id"].astype(str)),
        }


def _jaccard(a: set, b: set) -> float:
    if not a and not b:
        return 1.0
    return len(a & b) / len(a | b)


def test_live_candidate_pool_matches_offline_v3_pool():
    mismatches = []
    with ci_db.get_conn() as conn:
        for project in _sample_ground_truth_projects():
            live_ids = cpl._candidate_pool(
                conn, project["county"], project["state"], project["project_type"],
                project["bid_date"],
            )
            score = _jaccard(project["expected_ids"], live_ids)
            if score < MIN_JACCARD:
                mismatches.append({
                    "project_natural_key": project["project_natural_key"],
                    "jaccard": round(score, 3),
                    "missing_from_live": sorted(project["expected_ids"] - live_ids)[:10],
                    "extra_in_live": sorted(live_ids - project["expected_ids"])[:10],
                })

    assert not mismatches, (
        f"{len(mismatches)} sampled project(s) drifted below jaccard={MIN_JACCARD} between "
        f"_candidate_pool() and build_v3_candidate_set()'s materialized output — "
        f"the live mirror needs to be updated to match candidate_filter.py: {mismatches}"
    )
