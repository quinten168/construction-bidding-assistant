"""Coverage test for the phasing carry-through (2026-08-10).

WHAT IT PROVES. `phasing_requirements` is extracted by s4_extract_rag, paid for with a Claude call,
written into `record` — and, until today, dropped at payload assembly (it was in neither
`report.py::identity_fields` nor `final_report.py::_payload_from_plan_id`, and appears in 0 of the
12 cached payloads). These tests run a plan KNOWN to have phasing through BOTH assembly sites and
the renderer and assert the value arrives NON-EMPTY. A test on a plan with no phasing would pass
without the fix, so the empty case is only ever asserted as the != counterpart.

THE NAMED PLAN: `2023_MOUNTRAIL-CO-ND_8371604_NOBID`. Its phasing is real and cited —
csi_v2.db.gotchas carries its `phasing_staging` flag on p.8 with the verbatim evidence
"Construction in this phase may not begin until Phases 1 & 2 are completed."
The phasing text is READ OUT OF THE DATABASE at run time rather than hardcoded: a frozen fixture
would keep passing even if the corpus stopped containing a single phased plan, which is exactly the
kind of hollow green the working rules warn about.

Spec: docs/_spec/2026-08-10-payload-carry-through.md. Diagnosis:
docs/_session/2026-08-10-key-dates-phasing.md §2.

File naming: pytest imports test modules by name, so a `2026-08-10-` prefix is not a legal
identifier — same runtime-module exemption the repo's other tests take.
"""
from __future__ import annotations

import json
import sqlite3
import sys
import types
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend import final_report as fr        # noqa: E402
from backend import payload_carry as pc       # noqa: E402
from backend.config import CSI_DB             # noqa: E402

PHASED_PLAN_ID = "2023_MOUNTRAIL-CO-ND_8371604_NOBID"
PHASED_PAGE = 8


def _report_module():
    """Import backend.report, stubbing the one optional dep this sandbox lacks.

    report.py pulls in the whole plan-reader pipeline at module scope. `rapidfuzz` is imported
    transitively and is not installed here; nothing on the identity-assembly path touches it, so a
    stub is honest rather than a way of dodging a real failure. Anything ELSE missing is a genuine
    environment problem and skips loudly with the reason attached.
    """
    if "rapidfuzz" not in sys.modules:
        stub = types.ModuleType("rapidfuzz")
        stub.fuzz = types.SimpleNamespace()
        stub.process = types.SimpleNamespace()
        sys.modules["rapidfuzz"] = stub
        sys.modules["rapidfuzz.fuzz"] = types.ModuleType("rapidfuzz.fuzz")
        sys.modules["rapidfuzz.process"] = types.ModuleType("rapidfuzz.process")
    try:
        from backend import report
    except ImportError as e:                          # pragma: no cover - environment, not logic
        pytest.skip(f"backend.report is not importable in this environment: {e}")
    return report


def _real_phasing_text() -> str:
    """The phasing evidence the corpus actually holds for the named plan, read live."""
    if not Path(CSI_DB).exists():
        pytest.skip(f"csi_v2.db not reachable at {CSI_DB}")
    try:
        conn = sqlite3.connect(f"file:{CSI_DB}?mode=ro", uri=True)
    except sqlite3.OperationalError as e:             # pragma: no cover - symlink into iCloud
        pytest.skip(f"csi_v2.db could not be opened: {e}")
    with conn:
        row = conn.execute(
            "select evidence, page from gotchas "
            "where plan_id = ? and flag_type = 'phasing_staging' and page = ?",
            (PHASED_PLAN_ID, PHASED_PAGE),
        ).fetchone()
    assert row is not None, (
        f"{PHASED_PLAN_ID} p.{PHASED_PAGE} no longer carries a phasing_staging gotcha. Either the "
        "corpus changed or this test lost its grounding — pick another plan with REAL phasing, do "
        "not hardcode the string."
    )
    text = (row[0] or "").strip()
    assert text, "the corpus row exists but its evidence is empty — nothing to carry through"
    return text


def _record_for_phased_plan() -> dict:
    """A minimal extraction record in the real schema-cell shape, phasing text from the corpus."""
    cell = lambda v, c="high", p=None: {"value": v, "confidence": c, "page": p}
    return {
        "plan_id": PHASED_PLAN_ID,
        "state": cell("ND"), "county": cell("Mountrail"),
        "project_location": cell("ND 8371604"), "sp_number": cell("8371604"),
        "prevailing_wages": cell(True), "traffic_level": cell(None, ""),
        "construction_start": cell(None, ""), "construction_end": cell(None, ""),
        "bid_deadline": cell(None, ""), "substantial_completion": cell(None, ""),
        "final_completion": cell(None, ""),
        "phasing_requirements": cell(_real_phasing_text(), "high", PHASED_PAGE),
        "gotchas": [],
    }


# --- site 1: the live PDF-drop path (report.py) --------------------------------------------------

def test_live_path_carries_nonempty_phasing_from_a_known_phased_plan():
    """The plan HAS phasing; the payload's identity must show it, non-empty."""
    report = _report_module()
    expected = _real_phasing_text()

    fields = report.identity_fields_from_record(_record_for_phased_plan())

    assert "phasing_requirements" in fields, (
        "identity_fields dropped phasing_requirements — this is the exact regression: extracted, "
        "paid for with a Claude call, discarded at assembly."
    )
    assert report._val(fields["phasing_requirements"]) == expected
    assert report._val(fields["phasing_requirements"]).strip() != ""


def test_live_path_keeps_phasing_confidence_and_page_for_the_verify_gate():
    """Carried as a CELL, not a bare string, so the verify UI can show a page to look at."""
    report = _report_module()
    fields = report.identity_fields_from_record(_record_for_phased_plan())
    conf = report._conf(fields["phasing_requirements"])
    assert conf["page"] == PHASED_PAGE
    assert conf["confidence"] == "high"


def test_live_path_status_is_detected_for_the_phased_plan():
    record = _record_for_phased_plan()
    assert pc.carried_statuses(record)["phasing_requirements_status"] == pc.DETECTED


# --- site 2: the corpus path (final_report._payload_from_plan_id) --------------------------------

def _write_corpus_json(tmp_path, monkeypatch, rec: dict) -> str:
    plan_dir = tmp_path / PHASED_PLAN_ID
    plan_dir.mkdir(parents=True)
    (plan_dir / f"{PHASED_PLAN_ID}.json").write_text(json.dumps(rec))
    monkeypatch.setattr(fr, "PLANS_DIR", tmp_path)
    return PHASED_PLAN_ID


def test_corpus_path_carries_nonempty_phasing_from_a_known_phased_plan(tmp_path, monkeypatch):
    expected = _real_phasing_text()
    plan_id = _write_corpus_json(tmp_path, monkeypatch, _record_for_phased_plan())

    payload = fr._payload_from_plan_id(plan_id)

    assert payload is not None
    idn = payload["identity"]
    assert idn.get("phasing_requirements") == expected
    assert idn.get("phasing_requirements_status") == pc.DETECTED


def test_corpus_path_reports_extraction_failed_when_the_json_predates_the_field(tmp_path, monkeypatch):
    """The 8 real corpus JSONs are stale — three date fields have NO key at all. A missing key must
    read as `extraction_failed`, never as "this plan has no phasing"."""
    rec = _record_for_phased_plan()
    rec.pop("phasing_requirements")
    plan_id = _write_corpus_json(tmp_path, monkeypatch, rec)

    idn = fr._payload_from_plan_id(plan_id)["identity"]

    assert idn.get("phasing_requirements_status") == pc.EXTRACTION_FAILED
    assert idn.get("phasing_requirements") is None


# --- the standing rule: a failure and an empty answer never share a value ------------------------

def test_none_found_and_extraction_failed_are_different_values():
    present_but_null = {"phasing_requirements": {"value": None, "confidence": "", "page": None}}
    key_missing: dict = {}
    assert pc.presence_status(present_but_null, "phasing_requirements") == pc.NONE_FOUND
    assert pc.presence_status(key_missing, "phasing_requirements") == pc.EXTRACTION_FAILED
    assert pc.presence_status(present_but_null, "phasing_requirements") != \
        pc.presence_status(key_missing, "phasing_requirements")


@pytest.mark.parametrize("status", [pc.DETECTED, pc.NONE_FOUND, pc.EXTRACTION_FAILED, None])
def test_no_status_ever_renders_blank(status):
    """Rule: neither "no phasing" nor "extraction failed" may render as an empty cell. `None` is the
    12 already-cached payloads, which carry neither key."""
    idn = {"phasing_requirements": "Phase 2 follows Phase 1." if status == pc.DETECTED else None,
           "phasing_requirements_status": status}
    rendered = pc.render_value(idn, "phasing_requirements")
    assert rendered.strip(), f"blank render for status={status!r}"


def test_none_found_and_extraction_failed_render_differently():
    a = pc.render_value({"phasing_requirements_status": pc.NONE_FOUND}, "phasing_requirements")
    b = pc.render_value({"phasing_requirements_status": pc.EXTRACTION_FAILED}, "phasing_requirements")
    assert a != b
    assert "not" in b.lower() and "captured" in b.lower(), \
        "a failed extraction must not read to an estimator as 'no phasing'"


# --- the rendered report -------------------------------------------------------------------------

def _final(idn: dict) -> dict:
    return {"plan_id": PHASED_PLAN_ID, "title": "Mountrail 8371604", "archetype": "Grading",
            "identity": idn, "tldr": "test", "quantities": [],
            "gotchas": {"go_no_go": [], "pricing": []}}


def test_rendered_report_shows_the_known_plans_phasing_text():
    expected = _real_phasing_text()
    md = fr.render_markdown(_final({"phasing_requirements": expected,
                                    "phasing_requirements_status": pc.DETECTED}))
    assert "| Phasing |" in md, "§① Plan Snapshot has no Phasing row"
    assert expected[:80] in md, "the phasing text reached the payload but not the rendered report"


def test_rendered_report_distinguishes_no_phasing_from_a_failed_extraction():
    none_md = fr.render_markdown(_final({"phasing_requirements": None,
                                         "phasing_requirements_status": pc.NONE_FOUND}))
    failed_md = fr.render_markdown(_final({"phasing_requirements": None,
                                           "phasing_requirements_status": pc.EXTRACTION_FAILED}))
    assert "| Phasing |" in none_md and "| Phasing |" in failed_md
    assert none_md != failed_md, \
        "the rendered report shows the same thing for 'no phasing' and 'extraction failed'"
    assert "| Phasing |  |" not in none_md and "| Phasing |  |" not in failed_md


def test_csv_export_carries_the_status_alongside_the_value():
    expected = _real_phasing_text()
    rows = fr.to_csv(_final({"phasing_requirements": expected,
                             "phasing_requirements_status": pc.DETECTED})).splitlines()
    line = next(r for r in rows if r.startswith("snapshot,phasing_requirements"))
    assert pc.DETECTED in line and expected[:40] in line
