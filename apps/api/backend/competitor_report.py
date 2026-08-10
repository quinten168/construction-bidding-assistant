"""
Competitor Intelligence report — parse (+ shared normalizers).

The Competitor Intel module (Quentin/Wenyu's logistic-regression pipeline) emits a markdown
`bid_report_*.md` per project: a project header, a competitor list, and per-competitor deep-dives.
This module turns one of those files into a structured dict (`parse_report`) and hosts the
county/state/work-type normalizers plus `MATCH_REVIEW_GAP_DAYS`, shared with the live-generation
path (`competitor_live.py` imports all of them).

There used to be a `match_report()` here — the cascade's middle tier, matching a plan to the
nearest same-county pre-generated report file and reusing it verbatim. Removed 2026-08-09 along
with that tier (see final_report.predict_competitors' docstring): a stale copied report's only
remaining role was masking a dead CI subprocess, and the live prediction built from the plan's own
data replaced it. `parse_report`/`load_reports` stay — tier 1 parses its freshly GENERATED report
files through the exact same code.

No Claude calls, no I/O beyond reading the markdown files.
"""
from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

from .config import COMPETITOR_REPORTS

# Two-letter state is what both sides share; normalize spellings to it.
_STATE_ABBR = {"minnesota": "MN", "north dakota": "ND", "south dakota": "SD",
               "iowa": "IA", "nebraska": "NE", "montana": "MT"}

# --- report format (updated 2026-08-05 to the CI team's v3 schema) ------------------------------
# Their reporter dropped the two-TIER qualitative list (Priority = tracked/active, Discovery =
# model-surfaced) in favor of a single flat top-N ranking by simple_rule_score, plus structured
# per-competitor deep-dive attributes and pit-proximity signals. Tier never drove the ranking or
# selection (planner.py's plan() always sorted purely by score) -- it only drove this now-removed
# display grouping. This parser targets that flat v3 schema.
#   ## COMPETITOR LIST        → one indented name per line, already in rank order.
#   ## COMPETITOR DEEP DIVES  → "### NAME" then "- **Attr:** value" bullets.
_DIVE_RE = re.compile(r"^###\s+(?P<name>.+?)\s*$")
_ATTR_RE = re.compile(r"^\s*-\s+\*\*(?P<attr>.+):\*\*\s*(?P<val>.*)$")
# a competitor name line inside COMPETITOR LIST: indented, all-caps-ish, not blank.
_NAME_RE = re.compile(r"^\s{2,}(?P<name>[A-Z0-9][^─]*?)\s*$")


# --- normalization helpers ----------------------------------------------------------------------
def norm_county(s: str) -> str:
    """Bare, comparable county token: lowercase, drop a trailing 'county'/'co', strip punctuation.
    'DOUGLAS CO, MN' header gives 'douglas'; a plan's 'Douglas County' gives 'douglas' too."""
    s = (s or "").lower()
    s = re.sub(r",.*$", "", s)                          # drop ', MN' tail if the whole loc was passed
    s = re.sub(r"\b(county|co)\b\.?", "", s)
    return re.sub(r"[^a-z0-9 ]", " ", s).strip()


def norm_work_type(s: str) -> str:
    """Comparable work-type token across the two spellings in play: the plan pipeline's archetype
    vocabulary (`project_registry._archetype()`: 'Reconstruct/Rebuild', 'Mill & Overlay', ...) and
    the CI reports'/projects.csv's spaced variants ('Reconstruct / Rebuild', 'Aggregate / Base /
    Gravel'). Same six labels, different whitespace around '/'. Returns '' for the two non-types —
    'Other' (a catch-all, not a real work type: two 'Other' projects can be entirely different
    work) and 'Unknown/NoQty' (no quantities extracted) — so the type gate below treats them as
    "type unknown, gate off" rather than as a matchable identity."""
    t = re.sub(r"\s*/\s*", "/", (s or "").strip().lower())
    t = re.sub(r"\s+", " ", t)
    return "" if t in ("", "other", "unknown/noqty") else t


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


# --- parse one report ---------------------------------------------------------------------------
def _clean(s: str) -> str:
    """Strip markdown bold + surrounding whitespace from a value."""
    return re.sub(r"\*\*", "", s or "").strip()


def parse_report(path: str | Path) -> dict:
    """Parse one v3 `bid_report_*.md` into a structured dict (see module docstring for the shape).

    `competitors` is a flat, rank-ordered list of names (no tiers as of v3 -- CSI's tracked-list
    membership never drove ranking or selection, only a display grouping that's now gone).
    `deep_dives` (name -> bullet list) and `attrs` (name -> {attr: value}) key off the same names."""
    path = Path(path)
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()

    def _field(label: str) -> str:
        """Value after '**Label:**' (or 'Label:') in the PROJECT INTRODUCTION block (first hit)."""
        for ln in lines:
            m = re.match(rf"^\s*\*{{0,2}}{re.escape(label)}:?\*{{0,2}}\s*:?\s*(.+?)\s*$", ln)
            if m:
                return _clean(m.group(1))
        return ""

    # header line: "Project: P000008 | LYON CO, MN"
    pid, header_loc = "", ""
    if m := re.search(r"^Project:\s*(P\d+)\s*\|\s*(.+?)\s*$", text, re.M):
        pid, header_loc = m.group(1), m.group(2)

    location = _field("Location") or header_loc
    state = norm_state(location)
    county = norm_county(re.sub(r"\b(co|county)\b.*$", "", location, flags=re.I))

    bid_date = ""
    if m := re.search(r"Bid Date:\s*(\d{4}-\d{2}-\d{2})", text):
        bid_date = m.group(1)

    # --- competitor list: a single flat ranking, names only (no scores in v3) ---
    names: list[str] = []
    in_list = False
    for ln in lines:
        if ln.startswith("## "):
            in_list = "COMPETITOR LIST" in ln
            continue
        if not in_list:
            continue
        if nm := _NAME_RE.match(ln):
            name = nm.group("name").strip()
            if name and name not in names:
                names.append(name)

    # --- deep dives: "### NAME" then "- **Attr:** value" bullets, keyed by name ---
    deep_dives: dict[str, list[str]] = {}
    attrs: dict[str, dict] = {}
    current = None
    for ln in lines:
        if ln.startswith("## "):
            current = None
        elif dm := _DIVE_RE.match(ln):
            current = dm.group("name").strip()
            deep_dives.setdefault(current, [])
            attrs.setdefault(current, {})
        elif current and (am := _ATTR_RE.match(ln)):
            key = am.group("attr").strip()
            val = _clean(am.group("val"))
            attrs[current][key] = val
            deep_dives[current].append(f"{key}: {val}" if val else key)
        elif current and (bm := re.match(r"^\s*-\s+(.*)$", ln)):
            deep_dives[current].append(_clean(bm.group(1)))

    summary = {"analyzed": len(names),
               "narrative": _field("Condition")}    # v2 has no exec-summary prose; use the Condition line

    return {
        "project_id": pid,
        "location": location,
        "county": county,
        "state": state,
        "bid_date": bid_date,
        "work_type": _field("Work Type") or _field("Type"),
        "condition": _field("Condition"),
        "materials": [m.strip() for m in _field("Materials").split(",") if m.strip()],
        "pits": {"public": _field("Public-access pits near site"),
                 "private": _field("Private pits")},
        "summary": summary,
        "competitors": names,
        "attrs": attrs,
        "deep_dives": deep_dives,
        "source_file": path.name,
    }


# --- load + match -------------------------------------------------------------------------------
@lru_cache(maxsize=1)
def load_reports(reports_dir: str | None = None) -> tuple[dict, ...]:
    """Parse every `bid_report_*.md` in the reports dir once. Tuple (not list) so it is hashable
    and lru-cacheable; cache is keyed on the dir string (None = the configured default)."""
    d = Path(reports_dir) if reports_dir else COMPETITOR_REPORTS
    if not d.exists():
        return ()
    out = []
    for p in sorted(d.glob("bid_report_*.md")):
        try:
            out.append(parse_report(p))
        except Exception:                               # a malformed report must not kill the rest
            continue
    return tuple(out)


def _date_gap_days(a: str, b: str) -> int:
    """Absolute day gap between two YYYY-MM-DD strings; large number if either is missing/unparseable."""
    import datetime as dt
    try:
        da = dt.date.fromisoformat(a[:10])
        db = dt.date.fromisoformat(b[:10])
        return abs((da - db).days)
    except Exception:
        return 10_000


# Same threshold and rationale as competitor_live.py's MATCH_REVIEW_GAP_DAYS (duplicated, not
# imported, matching this module's existing _date_gap_days duplication convention -- see CLAUDE.md
# rough edge 11 for the collision statistics behind the number).
MATCH_REVIEW_GAP_DAYS = 45


# --- manual smoke test --------------------------------------------------------------------------
if __name__ == "__main__":
    for rep in load_reports():
        print(f"{rep['project_id']}  {rep['county']}/{rep['state']}  {rep['bid_date']}  "
              f"work={rep['work_type']!r}  competitors={len(rep['competitors'])}  "
              f"dives={len(rep['deep_dives'])}  "
              f"analyzed={rep['summary']['analyzed']}")
