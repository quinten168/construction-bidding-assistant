"""
Competitor-record tool — a named competitor's bid/win record, filterable by county / state / year.

Answers the class of question the old client-centric tool couldn't: "how many times did Midwest
Contracting win in Crow Wing County last year", "who wins most in Stearns County", "what's
Duininck's record in ND". Queries Postgres live (`scratch.bid_results` joined to
`scratch.bid_projects`) — the same tables the live prediction/stats modules read — instead of the
local CSV snapshot this used to read, so an admin-UI edit (a new bid result, a corrected quantity)
is reflected the moment it's saved, not whenever a CSV happened to last be synced. That set covers
every bidder × project × county, not just the projects the client also bid on.

`competitor_unit_id` doubles as the canonical display name here — `data/build_project_competitor_panel.py`
sets `canonical_name` to a straight copy of it, so there's no separate registry-resolution step.

Read-only, no LLM. Returns a compact structured dict the agent narrates. Fail-open: any connection
or query error returns `{"found": False, ...}` rather than raising, same convention as
`competitor_stats_live.py`/`competitor_predict_live.py`.
"""
from __future__ import annotations

from . import ci_db
from . import competitor_report as cr
from .observability import get_logger

log = get_logger("bid_assistant.competitor_record")


def _resolve_names(conn, query: str) -> list[str]:
    """Map a free-text competitor name to competitor_unit_id(s): exact first, else substring either
    way. Same matching logic as before this moved to live SQL -- only the source of the name
    universe changed (a live distinct-values query instead of a cached CSV column)."""
    q = (query or "").strip().lower()
    if not q:
        return []
    with conn.cursor() as cur:
        cur.execute("select distinct competitor_unit_id from scratch.bid_results")
        names = [r["competitor_unit_id"] for r in cur.fetchall() if r["competitor_unit_id"]]
    exact = [n for n in names if n.lower() == q]
    if exact:
        return exact
    return [n for n in names if q in n.lower() or n.lower() in q]


def _fetch_bids(conn, names: list[str]) -> list[dict]:
    """One row per (competitor, project) the named competitor(s) bid on, with win flag +
    county/state/year -- the same join competitor_stats_live.py::_win_bid_rates() uses."""
    with conn.cursor() as cur:
        cur.execute(
            """
            select br.competitor_unit_id, br.did_win, bp.county, bp.state, bp.bid_date
            from scratch.bid_results br
            join scratch.bid_projects bp using (project_natural_key)
            where br.competitor_unit_id = any(%(names)s) and bp.deleted_at is null
            """,
            {"names": names},
        )
        rows = cur.fetchall()
    out = []
    for r in rows:
        bid_date = str(r["bid_date"] or "")
        out.append({
            "competitor_unit_id": r["competitor_unit_id"],
            "won": bool(r["did_win"]),
            "county": r["county"] or "",
            "state": r["state"] or "",
            "year": bid_date[:4],
            "county_n": cr.norm_county(r["county"] or ""),
            "state_n": cr.norm_state(r["state"] or ""),
        })
    return out


def competitor_record(competitor_name: str, county: str | None = None,
                      state: str | None = None, year: str | int | None = None) -> dict:
    """A competitor's bid/win record, optionally scoped to a county, state, and/or year."""
    try:
        with ci_db.get_conn() as conn:
            names = _resolve_names(conn, competitor_name)
            if not names:
                return {"found": False, "query": competitor_name,
                        "note": f"No competitor matching '{competitor_name}' in the competitor-intel bid history."}
            rows = _fetch_bids(conn, names)
    except Exception as e:                                  # noqa: BLE001 — tool must never raise
        log.warning("competitor_record: query failed for %r: %s", competitor_name, e)
        return {"found": False, "note": "The competitor-intel bidder history isn't reachable right now."}

    scope = {"competitor": names[0] if len(names) == 1 else names,
             "county": county or None, "state": state or None, "year": str(year) if year else None}
    if state:
        target_state = cr.norm_state(state)
        rows = [r for r in rows if r["state_n"] == target_state]
    if county:
        target_county = cr.norm_county(county)
        rows = [r for r in rows if r["county_n"] == target_county]
    if year:
        target_year = str(year)
        rows = [r for r in rows if r["year"] == target_year]

    total = len(rows)
    wins = sum(1 for r in rows if r["won"])

    by_year: dict[str, dict] = {}
    for r in rows:
        if not r["year"]:
            continue
        bucket = by_year.setdefault(r["year"], {"bids": 0, "wins": 0})
        bucket["bids"] += 1
        bucket["wins"] += r["won"]

    county_counts: dict[tuple[str, str], dict] = {}
    for r in rows:
        if not r["county"]:
            continue
        key = (r["county"], r["state"])
        bucket = county_counts.setdefault(key, {"bids": 0, "wins": 0})
        bucket["bids"] += 1
        bucket["wins"] += r["won"]
    top_counties = [
        {"county": county_, "state": state_, "bids": v["bids"], "wins": v["wins"]}
        for (county_, state_), v in sorted(county_counts.items(), key=lambda kv: kv[1]["bids"], reverse=True)[:6]
    ]

    return {
        "found": True,
        "competitor": names,
        "scope": {k: v for k, v in scope.items() if v},
        "total_bids": total,
        "wins": wins,
        "win_rate_pct": round(wins / total * 100, 1) if total else None,
        "by_year": by_year,
        "top_counties": top_counties,
        "note": ("Source: Competitor Intelligence bidder history (bid_results ⨝ bid_projects, live) — "
                 "the authoritative bidder record, broader than the client's own shared-bid data. 'wins' = ranked "
                 "1st. If a county/year scope returns 0 bids, the competitor has no recorded bids there."),
    }


TOOL_SCHEMA = {
    "name": "competitor_record",
    "description": (
        "Look up a SPECIFIC named competitor's bid and win record — total bids, wins, win-rate, "
        "broken down by year and county — optionally scoped to a county, state, and/or year. Use for "
        "questions like 'how many times did Midwest Contracting win in Crow Wing County last year', "
        "'who wins most in Stearns County', 'what is Duininck's record in North Dakota'. This reads the "
        "Competitor Intelligence team's authoritative bidder history (every bidder on every project, "
        "not just the client's shared bids) and resolves loose names to canonical ones. Prefer this over "
        "query_competitors when the question names a SPECIFIC competitor or a SPECIFIC county."),
    "input_schema": {
        "type": "object",
        "properties": {
            "competitor_name": {"type": "string",
                                "description": "The competitor to look up, e.g. 'Midwest Contracting'."},
            "county": {"type": "string", "description": "Optional county filter, e.g. 'Crow Wing'."},
            "state": {"type": "string", "description": "Optional state filter, full name or 2-letter code."},
            "year": {"type": "string", "description": "Optional year filter, e.g. '2025'."},
        },
        "required": ["competitor_name"],
    },
}


def run(tool_input: dict) -> dict:
    return competitor_record(
        competitor_name=tool_input.get("competitor_name", ""),
        county=tool_input.get("county"), state=tool_input.get("state"), year=tool_input.get("year"))
