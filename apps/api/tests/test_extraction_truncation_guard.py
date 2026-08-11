"""Coverage test for the truncation guard (2026-08-10).

WHAT IT PROVES. `s3_extract.call_json` used to return `None` on a JSON *parse* failure and could not
tell that apart from a response cut off at `max_tokens`. `extract_fields` then did
`call_json(...) or {}` and produced a full record of clean null cells: an overflowing extraction was
byte-identical to a plan with nothing in it, and `report.py::apply_verification` would cache that
forever. Measured on 2026-08-10: six new schema fields pushed the whole-doc extraction to 2,100-2,176
output tokens against the old 2,048 cap on 3 of 18 corpus plans, `stop_reason='max_tokens'`, and the
shipped code logged "JSON parse failed (Unterminated string...)" and returned `county=None`,
`milling_sy=None`.

These tests assert the two halves of the fix together, which is why they are a coverage test rather
than two unit tests:
  1. a response that hits the token cap is a DISTINGUISHABLE ERROR (`s3_extract.TRUNCATED`), separate
     both from a malformed response and from a legitimate empty answer, and
  2. it never reaches the payload cache — end to end through `report.process_pdf`, asserting on the
     cache DIRECTORY (no file written), not on a return value.

RED PROOF (see docs/_session/2026-08-10-truncation-guard.md §4): run against HEAD~ in a detached
git worktree, the file fails at collection with
`AttributeError: module 's3_extract' has no attribute 'call_json_result'`, and the two tests that
import nothing new (`test_apply_verification_refuses_to_cache_a_non_ok_payload`,
`test_a_truncated_extraction_never_lands_in_the_payload_cache`) fail on behaviour.

The live-API test at the bottom forces a real `stop_reason == "max_tokens"` with a tiny max_tokens
rather than a huge document — it costs one ~20-token call and is skipped without an API key.

File naming: pytest imports test modules by name, so a `2026-08-10-` prefix is not a legal
identifier — same runtime-module exemption the repo's other tests take.
"""
from __future__ import annotations

import json
import os
import sys
import types
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend import report                    # noqa: E402
import s3_extract                             # noqa: E402  (on sys.path via plan_reader_bridge)


# ── a fake Anthropic client: one response, one stop_reason, no network ─────────────────────────

def _fake_anthropic(text: str, stop_reason: str):
    """Stand-in for the `anthropic` module s3_extract calls, returning one canned response."""
    resp = types.SimpleNamespace(content=[types.SimpleNamespace(text=text)], stop_reason=stop_reason)
    client = types.SimpleNamespace(messages=types.SimpleNamespace(create=lambda **kw: resp))
    return types.SimpleNamespace(Anthropic=lambda **kw: client)


CUT_OFF = '{"state": {"value": "MN", "confidence": "high", "page": 1, "reason": "the advertis'


# ── 1. the three states are three states ──────────────────────────────────────────────────────

def test_a_response_cut_off_at_the_token_cap_is_TRUNCATED_read_from_stop_reason(monkeypatch):
    monkeypatch.setattr(s3_extract, "anthropic", _fake_anthropic(CUT_OFF, "max_tokens"))
    r = s3_extract.call_json_result("prompt", max_tokens=2048)
    assert r.status == s3_extract.TRUNCATED
    assert not r.is_ok
    assert r.data is None
    assert "cut off" in r.message.lower() or "cap" in r.message.lower()
    assert "2048" in r.message, "the message must name the budget that was hit"


def test_the_same_unparseable_text_without_the_cap_is_MALFORMED_not_truncated(monkeypatch):
    """The SAME bytes, differing only in stop_reason. This is what proves the classification comes
    from `resp.stop_reason` and not from the JSONDecodeError text (which is identical here)."""
    monkeypatch.setattr(s3_extract, "anthropic", _fake_anthropic(CUT_OFF, "end_turn"))
    r = s3_extract.call_json_result("prompt", max_tokens=2048)
    assert r.status == s3_extract.MALFORMED
    assert not r.is_ok
    assert r.data is None


def test_a_legitimately_empty_answer_is_OK_and_is_not_a_failure(monkeypatch):
    """The third state, and the one the old contract destroyed: an empty answer the model actually
    gave. It must be reachable and must NOT look like either failure."""
    monkeypatch.setattr(s3_extract, "anthropic", _fake_anthropic("{}", "end_turn"))
    r = s3_extract.call_json_result("prompt")
    assert r.status == s3_extract.OK and r.is_ok
    assert r.data == {}


def test_truncated_malformed_and_empty_are_three_distinct_values(monkeypatch):
    seen = []
    for text, stop in ((CUT_OFF, "max_tokens"), (CUT_OFF, "end_turn"), ("{}", "end_turn")):
        monkeypatch.setattr(s3_extract, "anthropic", _fake_anthropic(text, stop))
        seen.append(s3_extract.call_json_result("p").status)
    assert len(set(seen)) == 3, f"a failure and an empty answer share a return value: {seen}"


def test_parsed_but_still_capped_counts_as_truncated(monkeypatch):
    """A cut that lands on a syntactically complete prefix parses fine and is still incomplete."""
    monkeypatch.setattr(s3_extract, "anthropic",
                        _fake_anthropic('{"state": {"value": "MN"}}', "max_tokens"))
    r = s3_extract.call_json_result("p", max_tokens=64)
    assert r.status == s3_extract.TRUNCATED and r.data is None


def test_the_legacy_shim_still_returns_none_on_both_failures(monkeypatch):
    """s4_extract_rag and the 03_evaluation runners call `call_json`; its contract is unchanged."""
    for stop in ("max_tokens", "end_turn"):
        monkeypatch.setattr(s3_extract, "anthropic", _fake_anthropic(CUT_OFF, stop))
        assert s3_extract.call_json("p") is None
    monkeypatch.setattr(s3_extract, "anthropic", _fake_anthropic('[{"a": 1}]', "end_turn"))
    assert s3_extract.call_json("p") == [{"a": 1}]


# ── 2. extract_fields raises instead of returning a record of clean nulls ──────────────────────

def test_extract_fields_raises_on_truncation_instead_of_returning_null_cells(monkeypatch):
    monkeypatch.setattr(s3_extract, "anthropic", _fake_anthropic(CUT_OFF, "max_tokens"))
    with pytest.raises(s3_extract.ExtractionParseFailure) as ei:
        s3_extract.extract_fields("some document text")
    assert ei.value.kind == s3_extract.TRUNCATED
    assert ei.value.extraction_failure_kind == s3_extract.TRUNCATED   # what report.py branches on
    assert ei.value.stop_reason == "max_tokens"


def test_extract_fields_raises_on_malformed_too_with_a_different_kind(monkeypatch):
    monkeypatch.setattr(s3_extract, "anthropic", _fake_anthropic(CUT_OFF, "end_turn"))
    with pytest.raises(s3_extract.ExtractionParseFailure) as ei:
        s3_extract.extract_fields("some document text")
    assert ei.value.kind == s3_extract.MALFORMED


def test_a_genuinely_empty_extraction_still_returns_a_record(monkeypatch):
    """The counterpart that keeps the guard from being 'raise on everything': a model that answers
    `{}` is an empty ANSWER and must still produce a (null-celled) record, not an exception."""
    monkeypatch.setattr(s3_extract, "anthropic", _fake_anthropic("{}", "end_turn"))
    rec = s3_extract.extract_fields("some document text")
    assert rec and all(c["value"] is None for c in rec.values())


def test_the_six_thousand_token_budget_is_kept():
    assert s3_extract.EXTRACT_MAX_TOKENS == 6000


# ── 3. report.py: classified ERROR, and never cached ──────────────────────────────────────────

def _failure(kind):
    return s3_extract.ExtractionParseFailure(
        s3_extract.JsonResult(kind, None, f"synthetic {kind}", "max_tokens"))


def test_classify_read_error_gives_truncation_its_own_reason_code():
    reason, message = report._classify_read_error(_failure(s3_extract.TRUNCATED))
    assert reason == "extraction_truncated"
    assert "cut off" in message.lower()
    other, _ = report._classify_read_error(_failure(s3_extract.MALFORMED))
    assert other == "extraction_unreadable"
    assert other != reason, "truncation and unreadable must not share a reason code"
    generic, _ = report._classify_read_error(ValueError("something else entirely"))
    assert generic == "read_error" and generic not in (reason, other)


def test_a_truncated_extraction_never_lands_in_the_payload_cache(monkeypatch, tmp_path):
    """END TO END through process_pdf, asserting on the cache DIRECTORY. This is the required
    coverage assertion: an overflowing extraction must produce an error AND leave no cache file."""
    cache_dir = tmp_path / "_report_payload_cache"
    cache_dir.mkdir()
    monkeypatch.setattr(report, "_PAYLOAD_CACHE", cache_dir)
    monkeypatch.setattr(report.convert, "_hash", lambda p: "deadbeefdeadbeef")
    monkeypatch.setattr(report.lib, "detect_structure", lambda p: {
        "type": "proposal", "n_pages": 3, "proposal_pages": [1, 2, 3], "map_pages": [],
        "proposal_ranges": "1-3", "map_ranges": ""})
    monkeypatch.setattr(report.convert, "convert_pages", lambda p: [{"page": 1, "md": "x"}])
    monkeypatch.setattr(report.convert, "pages_to_markdown", lambda pages: "x")
    monkeypatch.setattr(report.lib, "get_collection", lambda *a, **k: object())
    monkeypatch.setattr(report.indexer, "ingest_pdf", lambda *a, **k: None)

    def _boom(record, text):
        raise _failure(s3_extract.TRUNCATED)
    monkeypatch.setattr(report.extract, "fill_extract_fields", _boom)

    rep = report.process_pdf(tmp_path / "plan.pdf", plan_id="TRUNCATED-PLAN")

    assert rep["ok"] is False, "a truncated extraction must not come back as a valid payload"
    assert rep["reason"] == "extraction_truncated"
    assert not rep.get("identity") and not rep.get("quantities"), \
        "no null-celled record may be handed on"
    assert list(cache_dir.iterdir()) == [], "a truncated extraction was written to the payload cache"


def test_apply_verification_refuses_to_cache_a_non_ok_payload(monkeypatch, tmp_path):
    cache_dir = tmp_path / "_report_payload_cache"
    monkeypatch.setattr(report, "_PAYLOAD_CACHE", cache_dir)
    out = report.apply_verification(
        {"ok": False, "reason": "extraction_truncated", "content_hash": "cafebabe0000",
         "identity": {}, "quantities": []}, {})
    assert not (cache_dir / "cafebabe0000.json").exists()
    assert out["ok"] is False


def test_apply_verification_still_caches_a_good_payload(monkeypatch, tmp_path):
    """The guard must not be vacuous — the normal path still writes."""
    cache_dir = tmp_path / "_report_payload_cache"
    monkeypatch.setattr(report, "_PAYLOAD_CACHE", cache_dir)
    report.apply_verification(
        {"ok": True, "content_hash": "0123456789ab", "identity": {"state": "MN"},
         "quantities": [{"label": "MILL", "value": 10, "unit": "SY"}]}, {"county": "Stearns"})
    written = json.loads((cache_dir / "0123456789ab.json").read_text())
    assert written["verified"] is True and written["identity"]["county"] == "Stearns"


# ── 4. the same thing against the real API, forced cheaply ────────────────────────────────────

@pytest.mark.skipif(not (os.environ.get("ANTHROPIC_API_KEY") or s3_extract.API_KEY),
                    reason="needs an Anthropic API key")
def test_live_a_tiny_max_tokens_really_does_come_back_TRUNCATED():
    """Forces a real stop_reason == 'max_tokens' with a 24-token cap instead of a huge document.
    Costs one small call; this is the half a fake client cannot prove (that the API field is spelled
    and populated the way call_json_result reads it)."""
    r = s3_extract.call_json_result(
        'Return ONLY a JSON object with 40 keys named k1..k40, each a 12-word sentence.',
        max_tokens=24)
    assert r.stop_reason == "max_tokens"
    assert r.status == s3_extract.TRUNCATED
    assert r.data is None
