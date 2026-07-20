"""
Competitor-record tool — a named competitor's bid/win record, filterable by county / state / year.

Answers the class of question the old CSI-centric tool couldn't: "how many times did Midwest
Contracting win in Crow Wing County last year", "who wins most in Stearns County", "what's
Duininck's record in ND". It reads the Competitor Intel team's AUTHORITATIVE bidder history
(`bidder_results.csv` joined to `projects.csv`) — the same data their model + reports use. That set
covers every bidder × project × county, not just the projects CSI also bid on, and normalizes names
to a canonical form (so "Midwest Contracting" resolves to "MIDWEST CONTRACTING LLC").

Read-only, no LLM. Returns a compact structured dict the agent narrates.
"""
from __future__ import annotations

from functools import lru_cache

import pandas as pd

from . import competitor_report as cr
from .config import CI_BIDDER_RESULTS, CI_PROJECTS_CSV
from .observability import get_logger

log = get_logger("bid_assistant.competitor_record")


def available() -> bool:
    return CI_BIDDER_RESULTS.exists() and CI_PROJECTS_CSV.exists()


@lru_cache(maxsize=1)
def _joined() -> pd.DataFrame:
    """bidder_results ⨝ projects, once. One row per (competitor, project) with win flag + county/year."""
    b = pd.read_csv(CI_BIDDER_RESULTS, dtype=str).fillna("")
    p = (pd.read_csv(CI_PROJECTS_CSV, dtype=str, usecols=["job_id", "bid_date", "state", "county"])
         .fillna(""))
    j = b.merge(p, on="job_id", how="left")
    j["won"] = j["did_win"].str.lower().isin(("true", "1", "yes"))
    j["year"] = j["bid_date"].str[:4]
    j["county_n"] = j["county"].map(cr.norm_county)
    j["state_n"] = j["state"].map(cr.norm_state)
    return j


def _resolve_names(query: str) -> list[str]:
    """Map a free-text competitor name to canonical_name(s): exact first, else substring either way."""
    names = list(_joined()["canonical_name"].dropna().unique())
    q = (query or "").strip().lower()
    if not q:
        return []
    exact = [n for n in names if n.lower() == q]
    if exact:
        return exact
    return [n for n in names if q in n.lower() or n.lower() in q]


def competitor_record(competitor_name: str, county: str | None = None,
                      state: str | None = None, year: str | int | None = None) -> dict:
    """A competitor's bid/win record, optionally scoped to a county, state, and/or year."""
    if not available():
        return {"found": False, "note": "The competitor-intel bidder history isn't available on this host."}
    names = _resolve_names(competitor_name)
    if not names:
        return {"found": False, "query": competitor_name,
                "note": f"No competitor matching '{competitor_name}' in the competitor-intel bid history."}

    j = _joined()
    sub = j[j["canonical_name"].isin(names)]
    scope = {"competitor": names[0] if len(names) == 1 else names,
             "county": county or None, "state": state or None, "year": str(year) if year else None}
    if state:
        sub = sub[sub["state_n"] == cr.norm_state(state)]
    if county:
        sub = sub[sub["county_n"] == cr.norm_county(county)]
    if year:
        sub = sub[sub["year"] == str(year)]

    total = int(len(sub))
    wins = int(sub["won"].sum())
    by_year = {y: {"bids": int(len(g)), "wins": int(g["won"].sum())}
               for y, g in sub.groupby("year") if y}
    top_counties = [{"county": r["county"], "state": r["state"], "bids": int(r["n"]), "wins": int(r["w"])}
                    for _, r in (sub.groupby(["county", "state"])
                                 .agg(n=("won", "size"), w=("won", "sum"))
                                 .reset_index().sort_values("n", ascending=False).head(6).iterrows())
                    if r["county"]]

    return {
        "found": True,
        "competitor": names,
        "scope": {k: v for k, v in scope.items() if v},
        "total_bids": total,
        "wins": wins,
        "win_rate_pct": round(wins / total * 100, 1) if total else None,
        "by_year": by_year,
        "top_counties": top_counties,
        "note": ("Source: Competitor Intelligence bidder history (bidder_results ⨝ projects) — the "
                 "authoritative bidder record, broader than CSI's own shared-bid data. 'wins' = ranked "
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
        "not just CSI's shared bids) and resolves loose names to canonical ones. Prefer this over "
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
