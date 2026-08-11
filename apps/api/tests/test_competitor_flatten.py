"""Coverage test for the §④ competitor-name boundary (2026-08-10).

The CI side has shipped `competitors` entries as `{"name": ..., "tier": ...}` objects as well as
plain strings. v3's intent is a flat, rank-ordered list of NAMES with no tiers, so every consumer
flattens at the boundary. These tests feed render_markdown the OBJECT shape that actually breaks
today -- a fixture full of strings would pass without proving anything.

File naming: pytest collects `test_*.py` and imports it as a module, so a `2026-08-10-` prefix is
not a legal identifier; same runtime-module exemption the repo's other tests use.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend import final_report as fr  # noqa: E402


def _final(competitors):
    return {
        "plan_id": "TEST", "title": "Test Plan", "archetype": "Mill & Overlay",
        "identity": {"state": "ND", "county": "Dunn", "location": "ND 200"},
        "tldr": "test", "quantities": [],
        "gotchas": {"go_no_go": [], "pricing": []},
        "competitor": {
            "project_id": "P", "location": "Dunn, ND", "county": "Dunn", "state": "ND",
            "bid_date": "2026-01-01", "work_type": "", "condition": "", "materials": [],
            "pits": {}, "summary": {"analyzed": len(competitors), "narrative": ""},
            "competitors": competitors, "attrs": {}, "stats": {},
            "source_file": "bid_report_TEST.md",
        },
    }


OBJECT_SHAPE = [{"name": "KNIFE RIVER MATERIALS", "tier": 1},
                {"name": "MAYO CONSTRUCTION", "tier": 2}]


def test_object_shaped_competitors_render_without_raising():
    md = fr.render_markdown(_final(OBJECT_SHAPE))
    assert "④ Competitive Landscape" in md


@pytest.mark.parametrize("include_dives", [True, False])
def test_no_competitor_renders_as_a_dict_repr(include_dives):
    md = fr.render_markdown(_final(OBJECT_SHAPE), include_dives=include_dives)
    assert "KNIFE RIVER MATERIALS" in md
    assert "MAYO CONSTRUCTION" in md
    # the failure mode this exists to catch: the whole dict printed instead of the name
    assert "'tier'" not in md
    assert "{" not in md.split("④ Competitive Landscape")[1]


def test_mixed_string_and_object_entries_both_survive():
    md = fr.render_markdown(_final(["ASTECH CORP", {"name": "KNIFE RIVER MATERIALS", "tier": 1}]))
    assert "ASTECH CORP" in md
    assert "KNIFE RIVER MATERIALS" in md


def test_assemble_flattens_before_the_manual_name_merge(monkeypatch):
    """The other crash site for the object shape: assemble()'s dedup does `c.strip()` on every
    existing name, and compute_stats() keys `stats` by name. Both need plain strings."""
    from backend import competitor_stats_live as csl
    monkeypatch.setattr(csl, "compute_stats", lambda *a, **k: {})
    monkeypatch.setattr(fr, "_gotchas_from_db", lambda *a, **k: None)
    payload = {"plan_id": "T", "title": "T", "archetype": "Mill & Overlay",
               "identity": {"state": "ND", "county": "Dunn"}, "quantities": [], "gotchas": []}
    out = fr.assemble(plan_payload=payload,
                      predicted_competitors={**_final(OBJECT_SHAPE)["competitor"]},
                      manual_competitors=["ASTECH CORP"])
    assert out["competitor"]["competitors"] == [
        "KNIFE RIVER MATERIALS", "MAYO CONSTRUCTION", "ASTECH CORP"]


def test_empty_list_and_missing_report_do_not_render_identically():
    """Rough-edge rule: a legitimate empty answer must never look like a failed lookup."""
    empty = fr.render_markdown(_final([]))
    failed = _final([])
    failed["competitor"] = None
    failed_md = fr.render_markdown(failed)
    assert "No competitor prediction available" in failed_md
    assert "No competitor prediction available" not in empty
    assert "no competitors" in empty.lower().split("④ competitive landscape")[1]
