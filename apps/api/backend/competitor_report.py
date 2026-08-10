"""
Competitor Intelligence — shared county/state normalizers.

Originally this module also parsed the CI team's `bid_report_*.md` markdown output
(`parse_report`/`load_reports`) for the county+state+date corpus-match cascade tier. That whole
mechanism — matching a plan to a historical project and shelling out to the CI orchestrator
subprocess — was removed: every competitor prediction is now live against Postgres
(`competitor_predict_live.py`), using the plan's own data instead of a snapshot of a possibly
different project. See CLAUDE.md invariant #1 and rough edge 11.

`norm_county`/`norm_state` outlive that removal — they're still load-bearing for
`competitor_record.py` and the live stats/prediction modules (`competitor_stats_live.py`,
`competitor_predict_live.py`), which all need the same "is this the same county/state" comparison
regardless of which source (a plan's extracted location vs. a Postgres row) it's comparing.
"""
from __future__ import annotations

import re

# Two-letter state is what both sides share; normalize spellings to it.
_STATE_ABBR = {"minnesota": "MN", "north dakota": "ND", "south dakota": "SD",
               "iowa": "IA", "nebraska": "NE", "montana": "MT"}


def norm_county(s: str) -> str:
    """Bare, comparable county token: lowercase, drop a trailing 'county'/'co', strip punctuation.
    'DOUGLAS CO, MN' header gives 'douglas'; a plan's 'Douglas County' gives 'douglas' too."""
    s = (s or "").lower()
    s = re.sub(r",.*$", "", s)                          # drop ', MN' tail if the whole loc was passed
    s = re.sub(r"\b(county|co)\b\.?", "", s)
    return re.sub(r"[^a-z0-9 ]", " ", s).strip()


def norm_state(s: str) -> str:
    """Anything (full name, abbreviation, 'DEUEL CO, SD') -> a two-letter code, uppercased."""
    s = (s or "").strip()
    if not s:
        return ""
    low = s.lower()
    for full, ab in _STATE_ABBR.items():
        if full in low:
            return ab
    m = re.search(r"\b([a-z]{2})\b\s*$", low)           # trailing 2-letter code, e.g. '... , sd'
    if m and m.group(1).upper() in _STATE_ABBR.values():
        return m.group(1).upper()
    return s.upper()[:2] if len(s) <= 3 else ""
