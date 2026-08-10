"""
phasing.py — the break-and-resume detector and the DateExpr carrier.

Spec: docs/_spec/2026-08-10-phasing-gotcha.md (read it before changing shapes here).

WHY THIS EXISTS. `phasing_requirements` (schema.py, source='rag') and the `phasing_staging`
taxonomy code already exist, and `plan_metrics.has_phasing` is 1 on 57 of 100 corpus plans. None of
that told an estimator anything, for two measured reasons:

  1. It is a boolean at a 57% base rate, and it collapses three different things — a real
     break-and-resume, an in-season sequence of operations, and traffic staging drawn on the plan.
  2. Retrieval finds the wrong text. On 2023_WATONWAN-CO-MN_SP-8303-48 — the corpus's clearest
     overwinter contract (proposal p.1: `Starting Date 7/10/2023  Completion Date 6/1/2024`,
     `This Contract Contains Intermediate Completion Dates`) — the extracted phasing_requirements
     is MnDOT's Primavera Work-Breakdown-Structure provision. It matched the word "phase" in a
     section about scheduling software.

So the strongest signal is NOT a retrieval result: it is arithmetic on construction_start and
construction_end, two fields the whole-doc extractor already fills. Layers 1-4 below are
deterministic and free; the LLM narrative is layer 5 and only supplies quotes and citations.

NAMING NOTE: this module is deliberately NOT date-prefixed, unlike the standalone scripts in
03_evaluation/. It is imported by name from the pipeline, and `2026-08-10-phasing` is not a legal
Python identifier. Every non-importable artifact of this task IS date-prefixed.
"""
from __future__ import annotations

import datetime as _dt
import re

# ── Status vocabularies. Three-valued on purpose; see spec §4.2 rule 1. ──────────
# "a failure and a legitimate empty answer must never share a return value" (CLAUDE.md standing
# rule). none_found means we looked and there is nothing. extraction_failed means we could not look.
STATUS_DETECTED = "detected"
STATUS_NONE = "none_found"
STATUS_FAILED = "extraction_failed"

PATTERN_BREAK = "break_and_resume"
PATTERN_SEQUENCED = "sequenced_within_season"
PATTERN_STAGED = "staged_traffic"

# DateExpr.resolution_status — four values, and "absent" is NOT the same as either unresolved case.
RES_RESOLVED = "resolved"
RES_NO_ANCHOR = "unresolved_anchor_missing"
RES_NOT_A_DATE = "unresolved_not_a_date"
RES_ABSENT = "absent"


# ── DateExpr ────────────────────────────────────────────────────────────────────

_ISO = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")
_US = re.compile(r"^(\d{1,2})/(\d{1,2})/(\d{4})$")
_MONTHS = ("january february march april may june july august september october november december"
           .split())
_LONG = re.compile(
    r"\b(" + "|".join(_MONTHS) + r")\.?\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})\b", re.I)

# A relative expression names an anchor it is measured from. These are the anchors this corpus uses.
_ANCHORS = [
    (r"substantial(?:ly)?\s+complet\w*", "substantial_completion"),
    (r"notice\s+to\s+proceed|\bNTP\b", "notice_to_proceed"),
    (r"final\s+complet\w*", "final_completion"),
    (r"(?:date\s+of\s+)?award", "award"),
    (r"execution\s+of\s+the\s+(?:contract|agreement)", "contract_execution"),
]
_OFFSET = re.compile(
    r"\bwithin\s+(?:(\d+)|\w+)\s*(?:\((\d+)\))?\s*(calendar|working|business)?\s*days?\b", re.I)
_DURATION = re.compile(r"\b(\d+)\s+(calendar|working|business)\s+days?\b", re.I)


def date_expr(raw, page=None, confidence="", resolved_anchors=None):
    """Carry ONE key date without ever destroying what the plan actually said.

    A relative expression ("within 90 days of substantial completion") survives verbatim in `raw`
    with kind='relative'. It is never coerced to null and never to a guessed calendar date — the
    board calls that out explicitly for the project start date. `resolved` is filled only when the
    anchor it depends on is itself a known date; otherwise `resolution_status` names WHICH kind of
    null this is, so a plan that is silent and a plan we could not resolve never look alike.
    """
    if raw in (None, "", "null"):
        return {"raw": None, "kind": None, "resolved": None, "anchor": None, "offset_days": None,
                "offset_basis": None, "resolution_status": RES_ABSENT, "page": page,
                "confidence": confidence}

    raw = str(raw).strip()
    out = {"raw": raw, "kind": None, "resolved": None, "anchor": None, "offset_days": None,
           "offset_basis": None, "resolution_status": RES_NOT_A_DATE, "page": page,
           "confidence": confidence}

    iso = _to_iso(raw)
    if iso and _looks_like_a_bare_date(raw):
        out.update(kind="calendar", resolved=iso, resolution_status=RES_RESOLVED)
        return out

    anchor = next((name for pat, name in _ANCHORS if re.search(pat, raw, re.I)), None)
    off, basis = _offset_days(raw)

    if anchor:
        out.update(kind="relative", anchor=anchor, offset_days=off, offset_basis=basis)
        base = (resolved_anchors or {}).get(anchor)
        # Only a CALENDAR-day offset from a known anchor is arithmetic we can actually do. A
        # working-day count needs a state holiday calendar we do not own; guessing one is the exact
        # failure mode this project keeps repeating, so it stays unresolved and says so.
        if base and off is not None and basis != "working" and basis != "business":
            try:
                d = _dt.date.fromisoformat(base) + _dt.timedelta(days=off)
                out.update(resolved=d.isoformat(), resolution_status=RES_RESOLVED)
                return out
            except ValueError:
                pass
        out["resolution_status"] = RES_NO_ANCHOR
        return out

    if off is not None or _DURATION.search(raw):
        m = _DURATION.search(raw)
        out.update(kind="duration",
                   offset_days=off if off is not None else int(m.group(1)),
                   offset_basis=basis or (m.group(2).lower() if m else None),
                   resolution_status=RES_NO_ANCHOR)
        return out

    if iso:
        # A calendar date embedded in a longer sentence ("...be completed on or before October 17th,
        # 2025"). Resolvable, but the sentence is kept because it may carry a condition.
        out.update(kind="calendar", resolved=iso, resolution_status=RES_RESOLVED)
        return out

    out["kind"] = "unparsed"          # visible, not silently dropped
    return out


def _looks_like_a_bare_date(raw):
    return bool(_ISO.match(raw) or _US.match(raw)
                or (_LONG.match(raw) and len(raw) < 25))


def _to_iso(raw):
    if m := _ISO.match(raw):
        return raw
    if m := _US.match(raw):
        mo, d, y = (int(x) for x in m.groups())
        return _safe(y, mo, d)
    if m := _LONG.search(raw):
        mo = _MONTHS.index(m.group(1).lower()) + 1
        return _safe(int(m.group(3)), mo, int(m.group(2)))
    return None


def _safe(y, mo, d):
    try:
        return _dt.date(y, mo, d).isoformat()
    except ValueError:
        return None


def _offset_days(raw):
    if m := _OFFSET.search(raw):
        n = m.group(2) or m.group(1)
        return (int(n) if n else None), (m.group(3).lower() if m.group(3) else "calendar")
    if m := _DURATION.search(raw):
        return int(m.group(1)), m.group(2).lower()
    return None, None


# ── Layer 1: the multi-season span (free, and the layer that actually fires) ─────

# A Northern-Plains construction season runs roughly April through November. A contract that starts
# in one season and ends in the next necessarily contains a winter shutdown, whether or not any
# prose in the document says so. Both Watonwan plans in the corpus are found this way and by
# nothing else.
SEASON_END_MONTH = 11          # work is done for the year after November
SEASON_START_MONTH = 4         # and does not resume before April


def spans_two_seasons(start_iso, end_iso):
    """True when a start/end pair necessarily brackets a winter. Returns (bool, days) — days is the
    full contract span, NOT the break length, which only the plan's own words can give."""
    try:
        s = _dt.date.fromisoformat(start_iso)
        e = _dt.date.fromisoformat(end_iso)
    except (TypeError, ValueError):
        return False, None
    if e <= s:
        return False, None
    # different calendar years, and the span actually crosses a dormant winter month
    crosses = e.year > s.year and (s.month <= SEASON_END_MONTH and e.month >= SEASON_START_MONTH
                                   or e.year > s.year + 0)
    return bool(crosses), (e - s).days


# ── Layers 2-4: project-specific phrases, with the boilerplate held out ──────────

# Each: (signal name, pattern). Every one of these is verified against real corpus text by
# test_phasing_coverage.py — a pattern that matches nothing in csi_v2.db fails the suite.
BREAK_PATTERNS = [
    ("intermediate_completion_declared",
     r"This Contract Contains Intermediate Completion Dates"),
    ("wear_course_next_season",
     r"(wear course|final lift|surface course)[^.]{0,200}?"
     r"(following|next|subsequent)\s+(construction\s+)?season"),
    ("freeze_thaw_hold",
     r"(freeze[ -]?thaw|free thaw)\s+cycle"),
    ("left_over_winter",
     r"(unpaved|left|remain\w*)[^.]{0,80}over\s+(a\s+)?winter"),
    ("ntp_gated_on_date",
     r"[Nn]otice to [Pp]roceed[^.]{0,80}?(not (be )?issued|will not be issued)[^.]{0,60}"
     r"(prior to|before|until)"),
    ("phase_gated_on_phase",
     r"[Pp]hase\s+\d[^.]{0,80}?(shall|will|may)\s+not\s+(begin|start|commence)|"
     r"may not begin until Phase"),
]

SEQUENCE_PATTERNS = [
    ("sequence_of_operations", r"sequence of operations|order of construction activities"),
    ("construction_sequence", r"construction sequence"),
]

STAGING_PATTERNS = [
    ("phase_limits_on_plan", r"PHASE\s+\d\b[^.]{0,60}(limits|construction limits)"),
    ("stage_construction", r"\d(?:ST|ND|RD|TH)\s+STAGE CONSTRUCTION|stage construction|staging plan"),
]

# BOILERPLATE — contract-form clauses that mention phasing/suspension without imposing any on THIS
# project. Measured over 37,261 corpus sections: 'intermediate completion' hits 40 plans and is
# mostly the EJCDC definition; 'suspension of work' hits 57 plans and is mostly EJCDC Article 16;
# 'carryover' hits 11 plans and is entirely FHWA on-the-job-training. Matching these is worse than
# matching nothing, because it produces a confident wrong flag. Held out explicitly, and
# test_phasing_coverage.py asserts each one still occurs in the corpus so a dead entry is caught.
BOILERPLATE_PATTERNS = [
    ("ejcdc_milestone_definition",
     r"_?Milestone_?\s*—?\s*A principal event in the performance of the Work"),
    ("ejcdc_suspend_work",
     r"Owner May Suspend Work|ARTICLE 16—SUSPENSION OF WORK"),
    ("ejcdc_hazardous_resume",
     r"shall not resume Work in connection with such Hazardous Environmental Condition"),
    ("mndot_1803_4_winter",
     r"Do not suspend operations for the winter until meeting the requirements of 1803\.4"),
    ("fhwa_ojt_carryover",
     r"[Cc]arryover positions|carry the assigned positions over to the next construction season|"
     r"Check if Carryover Trainee"),
    ("wbs_scheduling_software",
     r"Work Breakdown Structure|WBS includes Level"),
]

# A project-specific phrase has to be anchored to something concrete about THIS job, or it is
# almost certainly form language. A date, a station, a route, or a named work item.
_SPECIFIC = re.compile(
    r"\b(" + "|".join(_MONTHS) + r")\s+\d{1,2}|"        # August 1
    r"\b\d{1,2}/\d{1,2}/\d{4}\b|"                        # 8/1/2023
    r"\bSta\.?\s*\d|\bSTA\s*\d|\b\d+\+\d{2}\b|"          # station 197+00
    r"\bCSAH\s*\d|\bCR\s*\d|\bTH\s*\d|\bUS\s*\d|\bHwy\s*\d|"
    r"wear course|non-?wear|bituminous|aggregate base|grading|paving",
    re.I)


def is_boilerplate(text):
    """Which contract-form fingerprints this text matches. Non-empty => not project phasing."""
    return [name for name, pat in BOILERPLATE_PATTERNS if re.search(pat, text or "", re.I)]


def scan_text(text):
    """Deterministic layers 2-4 over one block of plan text.

    Returns {"break": [...], "sequence": [...], "staging": [...], "boilerplate": [...]} where each
    entry is {"signal", "quote"}. Boilerplate is REPORTED, not silently dropped, so a caller can see
    that a plan matched only form language rather than seeing an unexplained empty result.
    """
    text = text or ""
    out = {"break": [], "sequence": [], "staging": [], "boilerplate": is_boilerplate(text)}
    for bucket, pats, needs_specific in (("break", BREAK_PATTERNS, True),
                                         ("sequence", SEQUENCE_PATTERNS, False),
                                         ("staging", STAGING_PATTERNS, False)):
        for name, pat in pats:
            for m in re.finditer(pat, text, re.I):
                s, e = max(0, m.start() - 150), min(len(text), m.end() + 200)
                quote = re.sub(r"\s+", " ", text[s:e]).strip()
                # The declared-intermediate-dates line IS the project statement; it needs no
                # further anchor. Everything else must name a date/station/route/work item.
                if needs_specific and name != "intermediate_completion_declared" \
                        and not _SPECIFIC.search(quote):
                    continue
                if is_boilerplate(quote):
                    continue
                out[bucket].append({"signal": name, "quote": quote[:400]})
    return out


# ── Assembly ────────────────────────────────────────────────────────────────────

def detect(construction_start=None, construction_end=None, sections=None,
           phasing_prose=None, interim_raw=None, break_interval_raw=None,
           resolved_anchors=None, failed=False, failure_reason=None):
    """Build the schedule_phasing object (spec §4.2).

    `sections` is an iterable of (page, text) for one plan — pass the plan's sections/chunks. Pass
    `failed=True` when retrieval or the LLM call ERRORED: that yields extraction_failed, which is a
    different value from none_found and must render differently to an estimator.
    """
    if failed:
        return {"status": STATUS_FAILED, "pattern": None, "signals": [], "segments": [],
                "break": None, "evidence": [], "confidence": "",
                "failure_reason": failure_reason or "unspecified",
                "summary": None}

    start = date_expr(construction_start, resolved_anchors=resolved_anchors)
    end = date_expr(construction_end, resolved_anchors=resolved_anchors)

    signals, evidence = [], []

    # Layer 1 — arithmetic on two fields we already fill. This is the layer that catches Watonwan,
    # where the LLM returned scheduling-software boilerplate instead of the phasing.
    multi, span_days = spans_two_seasons(start.get("resolved"), end.get("resolved"))
    if multi:
        signals.append("multi_season_span")
        evidence.append({
            "quote": f"contract runs {start['resolved']} to {end['resolved']} "
                     f"({span_days} days) — spans a winter",
            "page": start.get("page") or end.get("page"),
            "signal": "multi_season_span"})

    # Layers 2-4 over the plan text.
    hits = {"break": [], "sequence": [], "staging": [], "boilerplate": []}
    for page, text in (sections or []):
        s = scan_text(text)
        for k in ("break", "sequence", "staging"):
            for h in s[k]:
                hits[k].append({**h, "page": page})
        hits["boilerplate"].extend(s["boilerplate"])

    for h in hits["break"]:
        if h["signal"] not in signals:
            signals.append(h["signal"])
        evidence.append({"quote": h["quote"], "page": h["page"], "signal": h["signal"]})

    # Layer 5's prose, only if it is not the WBS/EJCDC form language the current field returns.
    prose_boiler = is_boilerplate(phasing_prose or "")
    if phasing_prose and not prose_boiler:
        evidence.append({"quote": str(phasing_prose)[:400], "page": None,
                         "signal": "phasing_requirements"})

    if break_interval_raw:
        signals.append("stated_break_interval")
        evidence.append({"quote": str(break_interval_raw)[:400], "page": None,
                         "signal": "phase_break_interval"})
    if interim_raw:
        signals.append("interim_completion_dates")
        evidence.append({"quote": str(interim_raw)[:400], "page": None,
                         "signal": "interim_completion_dates"})

    if signals:
        pattern = PATTERN_BREAK
    elif hits["sequence"]:
        pattern = PATTERN_SEQUENCED
        evidence += [{"quote": h["quote"], "page": h["page"], "signal": h["signal"]}
                     for h in hits["sequence"]]
    elif hits["staging"]:
        pattern = PATTERN_STAGED
        evidence += [{"quote": h["quote"], "page": h["page"], "signal": h["signal"]}
                     for h in hits["staging"]]
    else:
        # Genuinely nothing. Boilerplate matches are carried so "we only saw form language" is
        # distinguishable from "we saw nothing at all" — same rule, one level down.
        return {"status": STATUS_NONE, "pattern": None, "signals": [], "segments": [],
                "break": None, "evidence": [],
                "boilerplate_only": sorted(set(hits["boilerplate"] + prose_boiler)) or None,
                "confidence": "", "summary": None}

    brk = None
    if pattern == PATTERN_BREAK:
        brk = {"after": None, "resumes": None,
               "interval_days": None,
               "interval_stated": break_interval_raw or _stated_interval(evidence),
               "interval_source": "stated" if break_interval_raw else None,
               "page": next((e["page"] for e in evidence if e.get("page")), None)}

    cited = [e for e in evidence if e.get("page") is not None]
    # spec §4.2 rule 2: a detection with no page citation is shippable only as low confidence.
    conf = "high" if len(cited) >= 2 else ("medium" if cited else "low")

    return {"status": STATUS_DETECTED, "pattern": pattern, "signals": signals,
            "segments": [], "break": brk, "evidence": evidence, "confidence": conf,
            "summary": _summary(pattern, signals, start, end, span_days, brk, cited)}


def _stated_interval(evidence):
    for e in evidence:
        if m := re.search(r"(following|next|subsequent)\s+(construction\s+)?season", e["quote"], re.I):
            return m.group(0)
    return None


def _summary(pattern, signals, start, end, span_days, brk, cited):
    """One generated line for the report. Built from the structure, never by an LLM, so it cannot
    disagree with the fields it summarises. Must name a date or interval and a page."""
    page = f" p.{cited[0]['page']}" if cited else ""
    if pattern != PATTERN_BREAK:
        label = "in-season sequencing" if pattern == PATTERN_SEQUENCED else "traffic staging"
        return f"{label} required ({', '.join(signals[:2]) or 'see evidence'}){page}."
    bits = []
    if "multi_season_span" in signals and start.get("resolved") and end.get("resolved"):
        bits.append(f"contract runs {start['resolved']} to {end['resolved']} "
                    f"({span_days} days) and spans a winter")
    if brk and brk.get("interval_stated"):
        bits.append(f"break stated as \"{brk['interval_stated']}\"")
    other = [s for s in signals if s != "multi_season_span"]
    if other and len(bits) < 2:
        bits.append("signals: " + ", ".join(other[:3]))
    return ("Work breaks and resumes — " + "; ".join(bits) + page + ".") if bits else \
           ("Work breaks and resumes" + page + ".")
