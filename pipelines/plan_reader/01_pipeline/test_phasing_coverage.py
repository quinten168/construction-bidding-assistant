"""
test_phasing_coverage.py — COVERAGE tests for the phasing detector.

Spec: docs/_spec/2026-08-10-phasing-gotcha.md §6.

The point of this file is NOT to prove the regexes are syntactically fine. It is to fail loudly the
day a pattern stops matching real plans. Every pattern in phasing.py is asserted against the actual
corpus text in csi_v2.db (37,261 sections, 100 plans). A pattern that matches zero corpus rows is a
dead pattern and fails here — which is exactly how this project has previously shipped matchers
that quietly matched nothing.

The corpus tests skip (not pass) when csi_v2.db is absent, so a fresh clone does not get a false
green. `test_every_break_pattern_matches_real_corpus_text` is the one that must never be deleted.

    .venv/bin/python -m pytest pipelines/plan_reader/01_pipeline/test_phasing_coverage.py -q
"""
from __future__ import annotations

import re
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import phasing  # noqa: E402

DB = Path(__file__).resolve().parents[1] / "csi_v2.db"
needs_db = pytest.mark.skipif(not DB.exists(), reason="csi_v2.db not present (see README)")

MD_CACHE = Path(__file__).resolve().parents[1] / "00_input" / "_md_cache"
needs_md = pytest.mark.skipif(not MD_CACHE.is_dir(),
                              reason="00_input/_md_cache not present (gitignored; see README)")


@pytest.fixture(scope="module")
def sections():
    conn = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    rows = list(conn.execute(
        "SELECT plan_id, page_start, raw_text FROM sections WHERE raw_text IS NOT NULL"))
    conn.close()
    assert rows, "sections table is empty — the corpus fixture itself is broken"
    return rows


# ── 1. Layer 1: the multi-season detector fires on the two known plans ──────────
# Both come from the per-plan JSON under 00_input/plans/. These are the ONLY two corpus plans whose
# extracted construction_start/end span a winter, and phasing_requirements is wrong or null on both
# — which is the entire argument for having a deterministic layer.

KNOWN_MULTI_SEASON = [
    ("2023_WATONWAN-CO-MN_SP-8303-48", "2023-07-10", "2024-06-01"),
    ("2025_WATONWAN-CO-MN_WATLINE-TRAIL", "2025-09-15", "2026-06-15"),
]

KNOWN_SINGLE_SEASON = [
    ("2023_BROOKINGS-CO-SD_SURFACING", "2023-08-01", "2023-10-15"),
    ("2023_DUNN-CO-ND_CP-13", "2023-04-01", "2023-10-14"),
    ("2025_STUTSMAN-CO-ND_CR-68", "2025-05-01", "2025-11-15"),
]


@pytest.mark.parametrize("plan_id,start,end", KNOWN_MULTI_SEASON)
def test_multi_season_detector_fires_on_known_plans(plan_id, start, end):
    got = phasing.detect(construction_start=start, construction_end=end)
    assert got["status"] == phasing.STATUS_DETECTED, plan_id
    assert got["pattern"] == phasing.PATTERN_BREAK, plan_id
    assert "multi_season_span" in got["signals"], plan_id
    # the deliverable shape: a summary naming dates, not a bare true
    assert start in got["summary"] and end in got["summary"], got["summary"]


@pytest.mark.parametrize("plan_id,start,end", KNOWN_SINGLE_SEASON)
def test_single_season_plans_are_not_flagged_as_breaks(plan_id, start, end):
    got = phasing.detect(construction_start=start, construction_end=end)
    assert got["status"] == phasing.STATUS_NONE, f"{plan_id} false-positived: {got}"


# ── 2. Every pattern must match real corpus text ───────────────────────────────

@needs_db
@pytest.mark.parametrize("name,pat", phasing.BREAK_PATTERNS)
def test_every_break_pattern_matches_real_corpus_text(name, pat, sections):
    """A break pattern that matches nothing is dead code pretending to be coverage."""
    rx = re.compile(pat, re.I)
    hits = {pid for pid, _pg, txt in sections if rx.search(txt)}
    assert hits, f"BREAK pattern {name!r} matched zero corpus sections — dead pattern"


@needs_db
@pytest.mark.parametrize("name,pat", phasing.BOILERPLATE_PATTERNS)
def test_every_boilerplate_pattern_still_occurs_in_the_corpus(name, pat, sections):
    """The deny-list is only useful while the boilerplate it denies is actually present. A dead
    deny-list entry is a silent hole: it stops excluding anything and nothing says so."""
    rx = re.compile(pat, re.I)
    hits = {pid for pid, _pg, txt in sections if rx.search(txt)}
    assert hits, f"BOILERPLATE fingerprint {name!r} matched zero corpus sections — stale deny-list"


@needs_db
def test_break_detection_reaches_a_minimum_number_of_plans(sections):
    """The whole task fails if the detector matches ~nobody. Threshold is deliberately low: the
    real break-and-resume rate in this corpus is single-digit plans, and a HIGH count would mean we
    have re-created the 57%-base-rate has_phasing flag we are replacing."""
    by_plan = {}
    for pid, pg, txt in sections:
        s = phasing.scan_text(txt)
        if s["break"]:
            by_plan.setdefault(pid, []).extend(s["break"])
    assert len(by_plan) >= 3, f"only {len(by_plan)} plans matched a break signal: {list(by_plan)}"
    assert len(by_plan) <= 40, (
        f"{len(by_plan)} plans matched — too broad to be the remobilization signal; "
        "this is the has_phasing 57%-base-rate failure returning")


@needs_db
def test_the_known_overwinter_plans_are_found_by_text_too(sections):
    """Murray CSAH-2 states the overwinter hold in words ('following construction season') and
    Watonwan declares intermediate dates on the cover. Both must be reachable from text alone,
    independently of layer 1."""
    found = set()
    for pid, _pg, txt in sections:
        if phasing.scan_text(txt)["break"]:
            found.add(pid)
    assert any("MURRAY" in p for p in found), f"Murray CSAH-2 overwinter hold not found: {found}"
    assert any("WATONWAN-CO-MN_SP-8303-48" in p for p in found), \
        f"Watonwan intermediate-completion declaration not found: {found}"


# ── 2b. End-to-end over 17 whole plan sets, no DB / no API ─────────────────────
# 00_input/_md_cache holds page-level markdown for 17 already-converted plan sets, each element
# {"page": N, "text": ...}. This is the closest thing we have to running the detector on the real
# thing, and it costs nothing. Numbers below were measured 2026-08-10; they are asserted as a RANGE,
# not an equality, so re-converting a plan does not fail the suite but a collapse to zero does.

@pytest.fixture(scope="module")
def md_cache_plans():
    import json
    out = []
    for p in sorted(MD_CACHE.glob("*.json")):
        if p.name.endswith(".hybrid.json"):
            continue
        els = json.loads(p.read_text())
        if isinstance(els, dict):
            els = els.get("pages") or els.get("elements") or []
        secs = [(e.get("page"), e.get("text") or "") for e in els if isinstance(e, dict)]
        if secs:
            out.append((p.stem, secs))
    return out


@needs_md
def test_detector_runs_over_whole_plan_sets_and_finds_the_break_plans(md_cache_plans):
    """Measured 2026-08-10 over 17 plan sets: 3 break_and_resume, 2 sequenced_within_season,
    12 none_found. The break plans are Brookings 8391182 (NTP gated on Aug 1 2023), Watonwan
    SP-8303-48 and one further MnDOT proposal, both via the cover-page intermediate-dates line."""
    assert len(md_cache_plans) >= 10, f"only {len(md_cache_plans)} cached plans — fixture is thin"
    breaks = [pid for pid, secs in md_cache_plans
              if phasing.detect(sections=secs)["pattern"] == phasing.PATTERN_BREAK]
    assert breaks, "detector found break_and_resume in ZERO whole plan sets — it is dead"
    # The signal must stay rare. If it ever exceeds a third of plans we have rebuilt has_phasing.
    assert len(breaks) <= len(md_cache_plans) // 3 + 1, \
        f"{len(breaks)}/{len(md_cache_plans)} flagged — too broad to be a remobilization signal"


@needs_md
def test_boilerplate_only_plans_return_none_found_not_a_flag(md_cache_plans):
    """The real false positive this deny-list prevents: a MnDOT proposal carrying both the 1803.4
    winter-suspension sentence AND the Primavera WBS provision, with no actual project phasing.
    At least one such plan must exist in the cache and must come back none_found."""
    saw = False
    for pid, secs in md_cache_plans:
        boiler = set()
        for _pg, t in secs:
            boiler |= set(phasing.is_boilerplate(t))
        got = phasing.detect(sections=secs)
        if boiler and got["status"] == phasing.STATUS_NONE:
            saw = True
            assert got.get("boilerplate_only"), \
                f"{pid} saw boilerplate {sorted(boiler)} but reported an unexplained empty result"
    assert saw, "no plan in the cache exercised the boilerplate-only path — deny-list unproven"


# ── 3. Boilerplate must not become a detection ─────────────────────────────────

BOILERPLATE_SAMPLES = [
    # EJCDC definition — matched 40 plans on a naive 'intermediate completion' grep
    ("ejcdc_milestone", "7. _Milestone_ —A principal event in the performance of the Work that the "
                        "Contract requires Contractor to achieve by an intermediate completion "
                        "date, or by a time prior to Substantial Completion of all the Work."),
    # EJCDC Article 16 — matched 57 plans on a naive 'suspension of work' grep
    ("ejcdc_article_16", "**ARTICLE 16—SUSPENSION OF WORK AND TERMINATION** 16.01 _Owner May "
                         "Suspend Work_ A. At any time and without cause, Owner may suspend the "
                         "Work or any portion thereof for a period of not more than 90 "
                         "consecutive days by written notice to Contractor and Engineer."),
    # MnDOT 1803.4 — identical sentence in 15 plans
    ("mndot_1803_4", "Do not suspend operations for the winter until meeting the requirements of "
                     "1803.4, “Temporary Suspensions”. During authorized winter "
                     "suspension, the Department will maintain traffic control devices."),
    # FHWA on-the-job training — the literal phrase 'next construction season', zero relevance
    ("fhwa_ojt", "CRD will decide, on a case-by-case basis, whether to carry the assigned positions "
                 "over to the next construction season. B. Positions carried over from the previous "
                 "construction season must be among the first positions filled at season startup."),
]


@pytest.mark.parametrize("name,text", BOILERPLATE_SAMPLES)
def test_boilerplate_is_not_detected_as_phasing(name, text):
    got = phasing.detect(sections=[(1, text)])
    assert got["status"] == phasing.STATUS_NONE, f"{name} false-positived: {got}"
    assert got.get("boilerplate_only"), \
        f"{name} produced an unexplained empty result instead of naming the boilerplate it saw"


def test_wbs_prose_is_rejected_as_phasing_narrative():
    """The exact string our extractor returned for Watonwan today. It is MnDOT's Primavera
    Work-Breakdown-Structure provision, not this project's phasing, and it must not be evidence."""
    wbs = ("The contract requires work to be organized into defined phases and stages within the "
           "Work Breakdown Structure (WBS). The WBS includes Level 2: Construction, Level 3: "
           "Phase TBD, and Level 4: Stage TBD nodes.")
    assert phasing.is_boilerplate(wbs)
    got = phasing.detect(construction_start="2023-07-10", construction_end="2024-06-01",
                         phasing_prose=wbs)
    assert got["status"] == phasing.STATUS_DETECTED          # layer 1 still fires
    assert all(e["signal"] != "phasing_requirements" for e in got["evidence"]), \
        "WBS boilerplate leaked into the evidence list"


# ── 4. Relative dates survive verbatim ─────────────────────────────────────────
# All four raws below are real values pulled from the report payload cache on 2026-08-10.

def test_relative_expression_survives_verbatim():
    raw = "within thirty (30) calendar days of substantial completion"
    d = phasing.date_expr(raw)
    assert d["raw"] == raw                      # never rewritten
    assert d["kind"] == "relative"
    assert d["anchor"] == "substantial_completion"
    assert d["offset_days"] == 30
    assert d["resolved"] is None
    assert d["resolution_status"] == phasing.RES_NO_ANCHOR


def test_relative_expression_resolves_when_the_anchor_is_known():
    d = phasing.date_expr("within thirty (30) calendar days of substantial completion",
                          resolved_anchors={"substantial_completion": "2023-08-31"})
    assert d["resolved"] == "2023-09-30"
    assert d["resolution_status"] == phasing.RES_RESOLVED
    assert d["raw"].startswith("within thirty")     # raw STILL kept alongside the resolution


def test_working_day_counts_are_not_guessed():
    d = phasing.date_expr("60 working days from Notice to Proceed",
                          resolved_anchors={"notice_to_proceed": "2023-05-01"})
    assert d["resolved"] is None, "a working-day count was resolved against a calendar we do not own"
    assert d["offset_basis"] == "working"
    assert d["resolution_status"] == phasing.RES_NO_ANCHOR


def test_absent_and_unresolved_are_different_values():
    """The standing rule, on the date carrier. A plan that says nothing and a plan whose relative
    expression we could not resolve must not look alike to the report."""
    absent = phasing.date_expr(None)
    unresolved = phasing.date_expr("within 90 days of substantial completion")
    assert absent["resolution_status"] == phasing.RES_ABSENT
    assert unresolved["resolution_status"] == phasing.RES_NO_ANCHOR
    assert absent["resolution_status"] != unresolved["resolution_status"]
    assert absent["raw"] is None and unresolved["raw"] is not None


@pytest.mark.parametrize("raw,expect", [
    ("2025-11-15", "2025-11-15"),
    ("11/15/2025", "2025-11-15"),
    ("October 15, 2023", "2023-10-15"),
    ("October 17th, 2025", "2025-10-17"),
    ("construction operations shall be started on or after September 15th 2025 and be completed on "
     "or before October 17th, 2025", "2025-09-15"),
])
def test_real_payload_cache_date_strings_parse(raw, expect):
    """Every raw here was read out of 00_input/_report_payload_cache on 2026-08-10."""
    assert phasing.date_expr(raw)["resolved"] == expect


def test_unparseable_text_is_visible_not_silent():
    d = phasing.date_expr("whenever, probably")
    assert d["kind"] == "unparsed"
    assert d["resolution_status"] == phasing.RES_NOT_A_DATE
    assert d["raw"] == "whenever, probably"


# ── 5. Failure and empty never share a value ───────────────────────────────────

def test_failure_and_empty_do_not_share_a_value():
    failed = phasing.detect(failed=True, failure_reason="chroma query raised")
    empty = phasing.detect(construction_start="2023-05-01", construction_end="2023-10-01",
                           sections=[(1, "Nothing about phasing here at all.")])
    assert failed["status"] == phasing.STATUS_FAILED
    assert empty["status"] == phasing.STATUS_NONE
    assert failed["status"] != empty["status"]
    assert failed["failure_reason"] == "chroma query raised"


def test_detection_always_carries_a_citation_or_admits_low_confidence():
    """spec §4.2 rule 2 — an estimator cannot act on a flag he cannot look up."""
    got = phasing.detect(construction_start="2023-07-10", construction_end="2024-06-01")
    assert got["status"] == phasing.STATUS_DETECTED
    cited = [e for e in got["evidence"] if e.get("page") is not None]
    assert cited or got["confidence"] == "low"


def test_summary_is_the_deliverable_shape_not_a_boolean():
    """'Phase 1 complete by X, Phase 2 begins Y, p.34' — a date or interval plus a page."""
    got = phasing.detect(
        construction_start="2025-06-01", construction_end="2026-06-15",
        sections=[(34, "Final bituminous wear course along CSAH 2 shall be placed during the "
                       "following construction season.")],
        break_interval_raw="the following construction season")
    assert got["pattern"] == phasing.PATTERN_BREAK
    assert "p.34" in got["summary"], got["summary"]
    assert got["break"]["interval_stated"] == "the following construction season"
    assert got["summary"] not in ("True", "true", True)
