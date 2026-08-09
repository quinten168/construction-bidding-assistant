"""
Tool — live season capacity from Supabase.

The report's "Capacity" bullet compares a competitor's current-season win/tonnage pace against
their history. This module supplies that history from a live query against Supabase's `scratch`
schema (see docs/DATA_ACCESS_SCRATCH.md) instead of the local ranking_predictions.csv snapshot, so
an admin-UI edit (a corrected bid result, say) is reflected the same day rather than waiting for
the next local batch regeneration.

This is the first direct Postgres connection from pipelines/ci_model/ -- every other read in this
tree is a local CSV/parquet by path. Deliberately a standalone connector here (own connect(), not
importing apps/api/backend/ci_db.py), matching the existing pattern of every other Postgres-facing
script in this repo (data/push_supabase_bid_data.py, data/pull_scratch_updates.py) having its own,
rather than sharing one connector across the apps/ / pipelines/ / data/ boundary.

Fail-open by design, same as competitor_live.py's CI subprocess and
apps/api/backend/competitor_live.py::ensure_fresh_local_data: any connection or query error means
the caller (executor.py) falls back to the local-file computation it already had before this
module existed. A capacity bullet sourced from slightly-stale local data beats no report at all.
"""
from __future__ import annotations

import os
from contextlib import contextmanager
from datetime import date as _date
from typing import Iterator

import pandas as pd

HISTORY_COLUMNS = ["competitor_unit_id", "bid_date", "mix_tons", "did_win"]


@contextmanager
def connect() -> Iterator["psycopg.Connection"]:  # noqa: F821 -- psycopg imported lazily below
    import psycopg

    dsn = os.environ.get("SUPABASE_TEAM_DB_URL")
    if not dsn:
        raise RuntimeError("SUPABASE_TEAM_DB_URL is not set")
    conn = psycopg.connect(dsn)
    try:
        yield conn
    finally:
        conn.close()


def fetch_capacity_history(competitor_ids: list[str], before_date: str, conn) -> pd.DataFrame:
    """One row per (competitor, historical bid) with bid_date < before_date -- same point-in-time,
    no-leakage rule every other feature in this pipeline already follows. Batched for the whole
    report's shortlist in one query rather than one query per competitor."""
    with conn.cursor() as cur:
        cur.execute(
            "select br.competitor_unit_id, bp.bid_date, bp.mix_tons, br.did_win "
            "from scratch.bid_results br "
            "join scratch.bid_projects bp using (project_natural_key) "
            "where br.competitor_unit_id = any(%s) and bp.bid_date < %s and bp.deleted_at is null",
            (list(competitor_ids), before_date),
        )
        rows = cur.fetchall()
    df = pd.DataFrame(rows, columns=HISTORY_COLUMNS)
    df["competitor_unit_id"] = df["competitor_unit_id"].astype(str)
    return df


def _bid_year(d: _date) -> int:
    """Bid year for a date (Sept 1 → April 30 bidding season). Returns the April-30 year.
    May-Aug are off-season; treat as the prior completed season's year. Same definition as
    executor.py::_bid_year -- kept in sync, not imported, to avoid a cross-module dependency for
    one four-line function."""
    if d.month >= 9:
        return d.year + 1
    return d.year


def _season_bounds(by: int) -> tuple[_date, _date]:
    return _date(by - 1, 9, 1), _date(by, 4, 30)


def bucket_seasons(history: pd.DataFrame, target_bid_date: str, n_seasons: int = 3) -> dict | None:
    """Bucket one competitor's bid history (columns: bid_date, mix_tons, did_win) into a
    genuinely-in-progress current season (if the target date falls inside one) plus up to
    n_seasons prior COMPLETE seasons, each reported separately -- not blended into one average --
    so the report can show a real year-by-year trend.

    A bid dated during the May-Aug off-season (after a season's Apr 30 close, before the next
    one's Sept 1 open) has no in-progress season to speak of: the season that just closed is
    already complete, not partial. Getting this right matters for `trend`, not just `current`'s
    label -- an earlier version of this function always carved out a "current" bucket regardless,
    which silently excluded that already-closed season from the trend comparison entirely (it sat
    alone in `current`, never compared against anything). A May-Aug bid_date, comparing an already-
    complete season against the two before it, is a completely ordinary case, not an edge case: DOT
    lettings run through August.

    Returns None if target_bid_date can't be parsed (caller should fall back).

    {
      "current": {"label": str, "wins": int, "tons": float, "bids": int} | None,  # None off-season
      "prior_seasons": [  # most recent first, only seasons with at least one bid on record
        {"label": "2024–2025", "wins": int, "tons": float, "bids": int}, ...
      ],
      "trend": "increasing" | "decreasing" | "flat" | None,  # wins, prior_seasons[0] vs [1];
                                                                None if fewer than 2 prior seasons
    }
    """
    bid_date_str = str(target_bid_date or "")
    if not bid_date_str:
        return None
    try:
        from datetime import datetime
        target = datetime.strptime(bid_date_str[:10], "%Y-%m-%d").date()
    except ValueError:
        return None

    history = history.copy()
    history["_date"] = pd.to_datetime(history["bid_date"], errors="coerce").dt.date
    history = history.dropna(subset=["_date"])

    def _season_stats(start: _date, end: _date, *, upper_inclusive: bool) -> dict:
        if upper_inclusive:
            mask = (history["_date"] >= start) & (history["_date"] <= end)
        else:
            mask = (history["_date"] >= start) & (history["_date"] < end)
        subset = history[mask]
        won = subset[subset["did_win"] == 1]
        return {
            "wins": int(len(won)),
            "tons": float(won["mix_tons"].fillna(0).astype(float).sum()) if len(won) else 0.0,
            "bids": int(len(subset)),
        }

    cur_by = _bid_year(target)
    cur_start, cur_end = _season_bounds(cur_by)
    in_season = target <= cur_end   # False => target fell in the May-Aug gap; that season is closed

    current = None
    if in_season:
        current = _season_stats(cur_start, target, upper_inclusive=False)
        current["label"] = f"{cur_by - 1}–{cur_by} season (Sept–Apr, in progress)"
        most_recent_closed_by = cur_by - 1
    else:
        most_recent_closed_by = cur_by

    prior_seasons = []
    for by in range(most_recent_closed_by, most_recent_closed_by - n_seasons, -1):
        ps_start, ps_end = _season_bounds(by)
        stats = _season_stats(ps_start, ps_end, upper_inclusive=True)
        if stats["bids"] == 0:
            continue
        stats["label"] = f"{by - 1}–{by}"
        prior_seasons.append(stats)

    trend = None
    if len(prior_seasons) >= 2:
        delta = prior_seasons[0]["wins"] - prior_seasons[1]["wins"]
        trend = "increasing" if delta > 0 else "decreasing" if delta < 0 else "flat"

    return {"current": current, "prior_seasons": prior_seasons, "trend": trend}
