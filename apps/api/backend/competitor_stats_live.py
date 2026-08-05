"""
Live, unified competitor stats — win rate, bid rate, capacity, pit access.

One batched query family per metric, covering the WHOLE merged competitor list (model-predicted
names + user-typed names) in a single pass per report — not one query per competitor, and not two
separate computations for "predicted" vs "manually added" names. Reuses the same Postgres connector
every other apps/api CI-data admin feature already uses (`ci_db.get_conn`), against Supabase's
`scratch` schema (see docs/DATA_ACCESS_SCRATCH.md). Mirrors the SQL shape of
`pipelines/ci_model/06_reporting/tools/capacity_live.py` (same tables, same batching principle) but
lives here because it must also score names the CI subprocess never saw.

Fail-open per metric family: a query error or empty result for one family (say, pit access when a
plan's lat/long never resolved) must not blank out the others. Every family returns `None` for a
given competitor rather than raising, on any missing data or error.
"""
from __future__ import annotations

from datetime import date as _date
from datetime import datetime as _datetime
from math import asin, cos, radians, sin, sqrt

from . import ci_db
from .observability import get_logger

log = get_logger("bid_assistant.competitor_stats_live")

_EARTH_RADIUS_MILES = 3958.7613          # same constant as build_pit_features.py:18
_PIT_RADIUS_MILES = 25                   # same band as build_pit_features.py's "within 25mi" convention


def _parse_date(d: str | None) -> _date | None:
    if not d:
        return None
    try:
        return _datetime.strptime(str(d)[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def _haversine_miles(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    lat1, lon1, lat2, lon2 = map(radians, (lat1, lon1, lat2, lon2))
    dlat, dlon = lat2 - lat1, lon2 - lon1
    a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    return 2 * _EARTH_RADIUS_MILES * asin(sqrt(a))


def _season_start(d: _date) -> _date:
    """Bid season = Sept 1 -> the following Aug 31 (a full 12-month bucket, no off-season gap).
    Deliberately separate from capacity_live.py's _bid_year/_season_bounds (Sept-Apr, with a
    May-Aug gap) -- that definition stays as-is for the existing Capacity bullet elsewhere in the
    report; this is a distinct metric with its own bucketing, not a shared one, so the two don't
    silently drift into meaning different things under the same name."""
    return _date(d.year, 9, 1) if d.month >= 9 else _date(d.year - 1, 9, 1)


# ── Win rate / bid rate ───────────────────────────────────────────────────────────────────────────
def _win_bid_rates(conn, competitor_ids: list[str], county: str, state: str,
                    project_type: str | None, before_date: str) -> dict[str, dict]:
    """One query, all competitors, all 3 scopes (state/county/project_type) at once. bid_rate's
    per-competitor numerator IS win_rate's per-scope denominator (this competitor's bid count in
    that scope) -- computed once here and reused for both metrics."""
    with conn.cursor() as cur:
        cur.execute(
            """
            select br.competitor_unit_id,
                   count(*) filter (where upper(bp.state) = upper(%(state)s)) as state_bids,
                   count(*) filter (where upper(bp.state) = upper(%(state)s) and br.did_win) as state_wins,
                   count(*) filter (where upper(bp.county) = upper(%(county)s)) as county_bids,
                   count(*) filter (where upper(bp.county) = upper(%(county)s) and br.did_win) as county_wins,
                   count(*) filter (where cast(%(ptype)s as text) is not null and upper(bp.project_type) = upper(%(ptype)s)) as type_bids,
                   count(*) filter (where cast(%(ptype)s as text) is not null and upper(bp.project_type) = upper(%(ptype)s) and br.did_win) as type_wins
            from scratch.bid_results br
            join scratch.bid_projects bp using (project_natural_key)
            where br.competitor_unit_id = any(%(ids)s) and bp.bid_date < %(before_date)s
            group by br.competitor_unit_id
            """,
            {"state": state, "county": county, "ptype": project_type,
             "before_date": before_date, "ids": list(competitor_ids)},
        )
        per_competitor = {row["competitor_unit_id"]: row for row in cur.fetchall()}

        cur.execute(
            """
            select
                count(distinct project_natural_key) filter (where upper(state) = upper(%(state)s)) as total_state,
                count(distinct project_natural_key) filter (where upper(county) = upper(%(county)s)) as total_county,
                count(distinct project_natural_key) filter (where cast(%(ptype)s as text) is not null and upper(project_type) = upper(%(ptype)s)) as total_type
            from scratch.bid_projects
            where bid_date < %(before_date)s
            """,
            {"state": state, "county": county, "ptype": project_type, "before_date": before_date},
        )
        totals = cur.fetchone() or {"total_state": 0, "total_county": 0, "total_type": 0}

    def _scope(bids: int, wins: int, total: int) -> dict:
        return {
            "win_rate": {"wins": wins, "bids": bids, "pct": (wins / bids) if bids else None},
            "bid_rate": {"bids": bids, "total": total, "pct": (bids / total) if total else None},
        }

    out: dict[str, dict] = {}
    for cid in competitor_ids:
        row = per_competitor.get(cid)
        if not row:
            out[cid] = {
                "win_rate": {"state": _scope(0, 0, 0)["win_rate"], "county": _scope(0, 0, 0)["win_rate"],
                             "project_type": _scope(0, 0, 0)["win_rate"]},
                "bid_rate": {"state": _scope(0, 0, totals["total_state"])["bid_rate"],
                             "county": _scope(0, 0, totals["total_county"])["bid_rate"],
                             "project_type": _scope(0, 0, totals["total_type"])["bid_rate"]},
            }
            continue
        state_s = _scope(row["state_bids"], row["state_wins"], totals["total_state"])
        county_s = _scope(row["county_bids"], row["county_wins"], totals["total_county"])
        type_s = _scope(row["type_bids"], row["type_wins"], totals["total_type"])
        out[cid] = {
            "win_rate": {"state": state_s["win_rate"], "county": county_s["win_rate"], "project_type": type_s["win_rate"]},
            "bid_rate": {"state": state_s["bid_rate"], "county": county_s["bid_rate"], "project_type": type_s["bid_rate"]},
        }
    return out


# ── Capacity ─────────────────────────────────────────────────────────────────────────────────────
def _capacity(conn, competitor_ids: list[str], before_date: str) -> dict[str, dict | None]:
    target = _parse_date(before_date)
    if target is None:
        return {cid: None for cid in competitor_ids}

    with conn.cursor() as cur:
        cur.execute(
            """
            select br.competitor_unit_id, bp.bid_date, bp.mix_tons
            from scratch.bid_results br
            join scratch.bid_projects bp using (project_natural_key)
            where br.competitor_unit_id = any(%(ids)s) and br.did_win and bp.bid_date < %(before_date)s
            """,
            {"ids": list(competitor_ids), "before_date": before_date},
        )
        rows = cur.fetchall()

    cur_season_start = _season_start(target)
    by_competitor: dict[str, dict[_date, float]] = {}
    for row in rows:
        cid = row["competitor_unit_id"]
        bid_date = row["bid_date"]
        if bid_date is None:
            continue
        season = _season_start(bid_date)
        tons = float(row["mix_tons"] or 0)
        by_competitor.setdefault(cid, {})
        by_competitor[cid][season] = by_competitor[cid].get(season, 0.0) + tons

    out: dict[str, dict | None] = {}
    for cid in competitor_ids:
        seasons = by_competitor.get(cid, {})
        ytd_won = seasons.get(cur_season_start, 0.0)
        historical = {s: t for s, t in seasons.items() if s < cur_season_start}
        if not historical:
            out[cid] = {"typical_capacity": None, "ytd_won": ytd_won, "capacity_pct": None, "last_year_total": None}
            continue
        typical_capacity = sum(historical.values()) / len(historical)
        most_recent_season = max(historical)
        out[cid] = {
            "typical_capacity": typical_capacity,
            "ytd_won": ytd_won,
            "capacity_pct": (ytd_won / typical_capacity) if typical_capacity else None,
            "last_year_total": historical[most_recent_season],
        }
    return out


# ── Pit access ───────────────────────────────────────────────────────────────────────────────────
def _pit_access(conn, competitor_ids: list[str], project_lat: float | None,
                 project_lon: float | None) -> dict[str, dict | None]:
    if project_lat is None or project_lon is None:
        return {cid: None for cid in competitor_ids}

    with conn.cursor() as cur:
        cur.execute(
            """
            select latitude, longitude, name, rating, access_type, access_company
            from scratch.mn_pit_list
            where access_type = 'open' or access_type = 'competitor'
            """
        )
        pit_rows = cur.fetchall()

    open_pits = [r for r in pit_rows if r["access_type"] == "open"]
    by_owner: dict[str, list] = {}
    for r in pit_rows:
        if r["access_type"] != "competitor":
            continue
        key = ci_db.normalize(r["access_company"])
        if key:
            by_owner.setdefault(key, []).append(r)

    def _with_distance(pit_list: list) -> list[tuple[float, dict]]:
        out = []
        for r in pit_list:
            if r["latitude"] is None or r["longitude"] is None:
                continue
            d = _haversine_miles(project_lat, project_lon, r["latitude"], r["longitude"])
            out.append((d, r))
        return out

    open_with_dist = _with_distance(open_pits)

    out: dict[str, dict | None] = {}
    for cid in competitor_ids:
        usable = open_with_dist + _with_distance(by_owner.get(ci_db.normalize(cid), []))
        if not usable:
            out[cid] = {"nearest_pit": None, "pits_within_25mi_count": 0, "pits_within_25mi_avg_quality": None}
            continue
        nearest_dist, nearest_row = min(usable, key=lambda p: p[0])
        within = [(d, r) for d, r in usable if d <= _PIT_RADIUS_MILES]
        ratings = [r["rating"] for _, r in within if r["rating"] is not None]
        out[cid] = {
            "nearest_pit": {"name": nearest_row["name"], "distance_miles": nearest_dist, "quality": nearest_row["rating"]},
            "pits_within_25mi_count": len(within),
            "pits_within_25mi_avg_quality": (sum(ratings) / len(ratings)) if ratings else None,
        }
    return out


# ── Entry point ──────────────────────────────────────────────────────────────────────────────────
def compute_stats(competitor_ids: list[str], county: str, state: str, project_type: str | None,
                   before_date: str, project_lat: float | None = None,
                   project_lon: float | None = None) -> dict[str, dict]:
    """Returns {competitor_unit_id: {"win_rate": {...}, "bid_rate": {...}, "capacity": {...}|None,
    "pit_access": {...}|None}}. Never raises -- a metric family that errors just comes back empty
    for every competitor rather than breaking the other families or the caller."""
    ids = list(dict.fromkeys(competitor_ids))          # de-dup, keep order
    if not ids:
        return {}

    rates: dict[str, dict] = {}
    capacity: dict[str, dict | None] = {cid: None for cid in ids}
    pit_access: dict[str, dict | None] = {cid: None for cid in ids}

    try:
        with ci_db.get_conn() as conn:
            # Postgres aborts the whole transaction on any statement error -- every later query on
            # this same connection would otherwise fail too ("current transaction is aborted") even
            # though it has nothing to do with the earlier one. Roll back after each caught failure
            # so one metric family's bug can't take the other two down with it.
            try:
                rates = _win_bid_rates(conn, ids, county, state, project_type, before_date)
            except Exception as e:                      # noqa: BLE001
                log.warning("win/bid rate computation failed: %s", e)
                conn.rollback()
            try:
                capacity = _capacity(conn, ids, before_date)
            except Exception as e:                      # noqa: BLE001
                log.warning("capacity computation failed: %s", e)
                conn.rollback()
            try:
                pit_access = _pit_access(conn, ids, project_lat, project_lon)
            except Exception as e:                      # noqa: BLE001
                log.warning("pit access computation failed: %s", e)
                conn.rollback()
    except Exception as e:                              # noqa: BLE001 -- e.g. SUPABASE_TEAM_DB_URL unset
        log.warning("competitor_stats_live: no DB connection, returning empty stats: %s", e)

    return {
        cid: {
            "win_rate": rates.get(cid, {}).get("win_rate"),
            "bid_rate": rates.get(cid, {}).get("bid_rate"),
            "capacity": capacity.get(cid),
            "pit_access": pit_access.get(cid),
        }
        for cid in ids
    }
