"""Coverage test for the raw-extraction cache (2026-08-15).

WHAT IT PROVES. Two independent uploads of the IDENTICAL PDF, both before either one reached the
verify gate, used to run two fully independent extraction passes (no cache existed yet for either —
`_PAYLOAD_CACHE` is only written by `apply_verification()`, post-confirmation). The model's
RAG-extracted route/milepost fields are not guaranteed byte-identical across two separate runs even
at temperature=0, and `midpoint_bridge.compute_midpoint()` turns those fields into a lat/long that
feeds `project_natural_key` (`bid_projects_record.py`) — so the two uploads of the SAME file could,
and once did (2026-08-15, Grant Co MN), get two DIFFERENT natural keys and land as two separate rows
in `scratch.bid_projects` instead of one.

This test proves `process_pdf`'s new `_RAW_EXTRACTION_CACHE` closes that at the source: a second
`process_pdf` call for the same content hash must not re-run extraction at all, and must return the
exact same result (including a field the fake extractor deliberately makes non-deterministic) as the
first call — while still coming back `verified: False`, so app.py's verify-gate routing
(`rep.get("verified")`) is unaffected by this cache existing.
"""
from __future__ import annotations

import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend import report  # noqa: E402


def _patch_pipeline(monkeypatch, tmp_path, extract_calls: list[int]):
    monkeypatch.setattr(report, "_PAYLOAD_CACHE", tmp_path / "_report_payload_cache")
    monkeypatch.setattr(report, "_RAW_EXTRACTION_CACHE", tmp_path / "_report_raw_extraction_cache")
    monkeypatch.setattr(report.convert, "_hash", lambda p: "sameContentHash123")
    monkeypatch.setattr(report.lib, "detect_structure", lambda p: {
        "type": "proposal", "n_pages": 3, "proposal_pages": [1, 2, 3], "map_pages": [],
        "proposal_ranges": "1-3", "map_ranges": ""})
    monkeypatch.setattr(report.convert, "convert_pages", lambda p: [{"page": 1, "md": "x"}])
    monkeypatch.setattr(report.convert, "pages_to_markdown", lambda pages: "x")
    monkeypatch.setattr(report.lib, "get_collection", lambda *a, **k: object())
    monkeypatch.setattr(report.indexer, "ingest_pdf", lambda *a, **k: None)
    monkeypatch.setattr(report.extract, "smart_truncate", lambda md, n: md)
    monkeypatch.setattr(report.extract, "MAX_CHARS", 100_000)
    monkeypatch.setattr(report.extract_rag, "fill_rag_fields", lambda *a, **k: None)
    monkeypatch.setattr(report.bid_date_bridge, "compute_bid_deadline", lambda md, p: None)

    def _fake_extract(record, text):
        extract_calls.append(1)
        record["route_number"] = {
            "value": str(random.randint(1, 999)), "confidence": "high", "page": 1, "reason": "",
        }
    monkeypatch.setattr(report.extract, "fill_extract_fields", _fake_extract)

    # Simulate the exact failure mode: a "genuinely different" lat/long every run, standing in for
    # route/milepost extraction not being reproducible run-to-run.
    monkeypatch.setattr(
        report.midpoint_bridge, "compute_midpoint",
        lambda **kw: (46.0 + random.random(), -95.0 - random.random()))


def test_second_drop_of_the_same_content_reuses_the_raw_extraction_not_a_fresh_run(
    monkeypatch, tmp_path,
):
    extract_calls: list[int] = []
    _patch_pipeline(monkeypatch, tmp_path, extract_calls)

    rep1 = report.process_pdf(tmp_path / "plan.pdf", plan_id="P1")
    rep2 = report.process_pdf(tmp_path / "plan.pdf", plan_id="P1")

    assert rep1["ok"] is True and rep2["ok"] is True
    assert len(extract_calls) == 1, (
        "a second drop of identical content must reuse the raw-extraction cache, not re-run "
        "fill_extract_fields"
    )
    assert rep1["identity"]["latitude"] == rep2["identity"]["latitude"]
    assert rep1["identity"]["longitude"] == rep2["identity"]["longitude"], (
        "two drops of the same content must not be able to compute different coordinates — this is "
        "the exact bug (divergent project_natural_key) this cache exists to close"
    )
    # The raw cache is a distinct tier from _PAYLOAD_CACHE — a hit here must NOT be mistaken for a
    # verified/finalized report by app.py's `rep.get("verified")` routing.
    assert rep2["verified"] is False


def test_raw_extraction_cache_is_not_reused_once_the_payload_cache_has_a_verified_hit(
    monkeypatch, tmp_path,
):
    """Once a plan is verified, process_pdf must prefer the _PAYLOAD_CACHE (verified=True) hit over
    the raw-extraction cache — the raw cache is a fallback for the unverified case only, never a
    shadow copy that could serve stale pre-edit values after a human has corrected something."""
    extract_calls: list[int] = []
    _patch_pipeline(monkeypatch, tmp_path, extract_calls)

    rep1 = report.process_pdf(tmp_path / "plan.pdf", plan_id="P1")
    verified = report.apply_verification(rep1, {"latitude": "46.5", "longitude": "-95.9"})

    rep2 = report.process_pdf(tmp_path / "plan.pdf", plan_id="P1")

    assert rep2["verified"] is True
    assert rep2["identity"]["latitude"] == 46.5
    assert rep2["identity"]["longitude"] == -95.9
    assert len(extract_calls) == 1, "a verified re-drop must not re-run extraction either"
