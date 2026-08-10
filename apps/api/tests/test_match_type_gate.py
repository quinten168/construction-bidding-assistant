"""
The county+state+date reverse-lookup's work-type gate (CLAUDE.md rough edge 11, step 1 of the
staged fix): when the plan's archetype is known and at least one corpus/report candidate sits
within MATCH_REVIEW_GAP_DAYS but NONE of them shares the plan's work type, the match is refused
(TYPE_GATE_MODE=enforce), logged-but-returned (log_only, the default), or not even detected (off).

These tests pin the gate to a real, verified collision in the corpus:
IA_CASS_CO_ATLANTIC_2025-01-22_1 (Grading/Earthwork) and _2 (Reconstruct/Rebuild) — two genuinely
different projects let the same day in the same county (the motivating case for the gate).

No database needed — find_project_key reads data/processed/projects.csv, a tracked/required
file; skips gracefully on a clone without it.
"""
from __future__ import annotations

import dataclasses

import pytest

from backend import competitor_live as cl
from backend import competitor_report as cr
from backend.config import settings

pytestmark = pytest.mark.skipif(
    not cl.available(), reason="CI corpus (projects.csv / orchestrator) not present on disk",
)

COLLISION = dict(county="Cass County", state="IA", bid_date="2025-01-22")


@pytest.fixture
def gate_mode(monkeypatch):
    """settings is a frozen dataclass; swap the whole object in the module that reads it."""
    def _set(mode: str):
        patched = dataclasses.replace(settings, type_gate_mode=mode)
        monkeypatch.setattr("backend.competitor_live.settings", patched)
    return _set


def test_norm_work_type_bridges_the_two_spellings():
    assert cr.norm_work_type("Reconstruct/Rebuild") == cr.norm_work_type("Reconstruct / Rebuild")
    assert cr.norm_work_type("Aggregate/Base/Gravel") == cr.norm_work_type("Aggregate / Base / Gravel")
    # the two non-types are 'unknown', never a matchable identity
    assert cr.norm_work_type("Other") == ""
    assert cr.norm_work_type("Unknown/NoQty") == ""
    assert cr.norm_work_type("") == ""


def test_enforce_refuses_when_type_matches_no_near_candidate(gate_mode):
    gate_mode("enforce")
    assert cl.find_project_key(**COLLISION, project_type="Mill & Overlay") is None


def test_log_only_detects_but_returns_the_match(gate_mode, caplog):
    gate_mode("log_only")
    with caplog.at_level("WARNING"):
        found = cl.find_project_key(**COLLISION, project_type="Mill & Overlay", plan_id="P_TEST")
    assert found is not None                      # behavior unchanged in log_only
    assert any("would_reject" in r.message and "type_all_excluded" in r.message
               and "P_TEST" in r.message for r in caplog.records)


def test_off_mode_does_not_even_detect(gate_mode, caplog):
    gate_mode("off")
    with caplog.at_level("WARNING"):
        found = cl.find_project_key(**COLLISION, project_type="Mill & Overlay")
    assert found is not None
    assert not any("type_all_excluded" in r.message for r in caplog.records)


def test_gate_passes_when_a_near_candidate_type_matches(gate_mode):
    gate_mode("enforce")
    found = cl.find_project_key(**COLLISION, project_type="Grading/Earthwork")
    assert found is not None
    key, gap = found
    assert gap == 0
    assert key.startswith("IA_CASS_CO_ATLANTIC_2025-01-22")


def test_gate_off_when_type_unknown_or_other(gate_mode):
    gate_mode("enforce")
    # legacy behavior must be preserved exactly when the gate has no type to work with
    for t in (None, "", "Other", "Unknown/NoQty"):
        found = cl.find_project_key(**COLLISION, project_type=t)
        assert found is not None, f"gate wrongly fired for project_type={t!r}"


def test_gate_does_not_fire_on_far_only_matches(gate_mode):
    gate_mode("enforce")
    # No candidate within the window -> the FAR-ONLY bucket keeps its needs_review path;
    # the type gate must not turn it into a refusal.
    found = cl.find_project_key("Cass County", "ND", "2020-01-01", project_type="Mill & Overlay")
    assert found is not None
    _, gap = found
    assert gap > cr.MATCH_REVIEW_GAP_DAYS


# (A mirror test for the static-match tier's gate lived here until 2026-08-09, when that tier —
# competitor_report.match_report — was removed from the cascade entirely; see
# final_report.predict_competitors' docstring.)
