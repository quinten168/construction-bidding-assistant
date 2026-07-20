"""
Structured bid-history tool — answers "data" questions the plan documents can't.

Questions like "how many bids have we placed in South Dakota?" or "what's our win rate in ND?"
are about CSI's *actual bidding record*, which lives in the master CSV (one row per bidder per
project), not in the plan PDFs. This module loads that record and answers a bounded set of
slice questions (by state / year) so the chat assistant can call it as a tool.

Win definition matches the rest of the platform: CSI won a project iff CSI's own bid ranked 1st.
"""
from __future__ import annotations

from functools import lru_cache

import pandas as pd

from .config import MASTER_CSV

WIN_WELL = {"Excellent Win", "Acceptable Win"}

# Let users say "SD" or "south dakota" — map abbreviations to the full names in the data.
_STATE_ALIASES = {"sd": "south dakota", "nd": "north dakota", "mn": "minnesota",
                  "ia": "iowa", "ne": "nebraska", "mt": "montana"}


@lru_cache(maxsize=1)
def _csi_projects() -> pd.DataFrame:
    """One row per CSI bid (CSI's own row per project), with outcome fields parsed."""
    df = pd.read_csv(MASTER_CSV, dtype=str, low_memory=False)
    csi = df[df["Is_CSI"] == "TRUE"].copy()
    # a few projects have 2 CSI rows (JVs); keep the winning row, else the first
    csi["_w"] = (csi["Is_Winner"] == "TRUE").astype(int)
    csi = csi.sort_values("_w", ascending=False).drop_duplicates("Contract_Id")
    csi["is_win"] = csi["Is_Winner"] == "TRUE"
    csi["is_win_well"] = csi["Bid_Quality"].isin(WIN_WELL)
    csi["is_bomb"] = csi["Bid_Quality"] == "Bomb"
    csi["state_l"] = csi["State"].astype(str).str.strip().str.lower()
    return csi


def query_bid_history(state: str | None = None, year: str | int | None = None) -> dict:
    """CSI's bidding record for an optional state / year slice. Returns a small dict of facts
    (and, if the slice is empty, what *is* available) so the model can answer precisely."""
    df = _csi_projects()
    available_years = sorted(df["Bid_Year"].dropna().unique().tolist())
    available_states = sorted(df["State"].dropna().unique().tolist())

    sub = df
    applied = {}
    if state:
        key = _STATE_ALIASES.get(state.strip().lower(), state.strip().lower())
        sub = sub[sub["state_l"] == key]
        applied["state"] = state
    if year not in (None, ""):
        sub = sub[sub["Bid_Year"].astype(str) == str(year)]
        applied["year"] = str(year)

    if len(sub) == 0:
        return {"filter": applied, "n_bids": 0,
                "note": "No CSI bids match that slice. The bid record covers these years "
                        f"{available_years} and these states {available_states}.",
                "available_years": available_years, "available_states": available_states}

    n = len(sub)
    wins = int(sub["is_win"].sum())
    return {
        "filter": applied or {"scope": "all CSI bids"},
        "n_bids": n,
        "n_wins": wins,
        "win_rate_pct": round(wins / n * 100, 1),
        "win_well_pct": round(sub["is_win_well"].mean() * 100, 1),
        "bomb_pct": round(sub["is_bomb"].mean() * 100, 1),
        "by_year": sub["Bid_Year"].value_counts().sort_index().to_dict(),
        "note": "Win = CSI's own bid ranked 1st. 'Win-well' = won at a healthy margin; "
                "'bomb' = won by overpaying. Record covers ~Aug 2023–Aug 2025.",
    }


# --- the Anthropic tool schema (what the model sees) ---------------------------------------------
TOOL_SCHEMA = {
    "name": "query_bid_history",
    "description": (
        "Look up CSI's OWN historical bidding record — how many projects CSI bid on, how many it "
        "won, win rate, and bid quality — optionally filtered by state and/or year. Use this for "
        "questions about CSI's bidding ACTIVITY or PERFORMANCE (e.g. 'how many bids have we placed "
        "in South Dakota', 'what's our win rate in North Dakota in 2025'). Do NOT use it for the "
        "contents/requirements of a specific plan — use search_plans for that. Data covers Aug "
        "2023 through Aug 2025."),
    "input_schema": {
        "type": "object",
        "properties": {
            "state": {"type": "string",
                      "description": "Full name or 2-letter code, e.g. 'South Dakota' or 'SD'. Omit for all states."},
            "year": {"type": "string",
                     "description": "Bid year, e.g. '2025'. Omit for all years."},
        },
    },
}


def run(tool_input: dict) -> dict:
    """Execute the tool from the model's arguments."""
    return query_bid_history(state=tool_input.get("state"), year=tool_input.get("year"))
