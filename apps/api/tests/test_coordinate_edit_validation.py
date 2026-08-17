"""Coverage test for the coordinate-edit fail-closed fix (2026-08-15).

WHAT IT PROVES. `apply_verification()` used to fall back to `identity[field] = value` (the raw,
non-numeric string) when `float(edits["latitude"])`/`float(edits["longitude"])` raised — no crash,
no error, just a report whose `identity.latitude` silently held `"abc"` instead of a number. A
teammate caught this could happen at all (the verify UI's coordinate inputs had no numeric
validation either — fixed separately in verify-extraction.tsx's CoordInput/isValidCoord).

This is the backend half, kept independent of the frontend fix as defense in depth for any other
caller of apply_verification: a non-numeric latitude/longitude edit must be REJECTED, not silently
stored, and whatever value was already in the payload must be left untouched.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend import report  # noqa: E402


def _base_rep():
    return {
        "ok": True, "content_hash": "abc123",
        "identity": {"latitude": 46.5, "longitude": -95.9},
        "quantities": [],
    }


def test_non_numeric_latitude_edit_is_rejected_not_stored(monkeypatch, tmp_path):
    monkeypatch.setattr(report, "_PAYLOAD_CACHE", tmp_path / "_report_payload_cache")
    out = report.apply_verification(_base_rep(), {"latitude": "abc"})
    assert out["identity"]["latitude"] == 46.5, (
        "a non-numeric latitude edit must be rejected, leaving the existing value untouched — "
        "not silently stored as the raw string"
    )
    assert isinstance(out["identity"]["latitude"], float)


def test_non_numeric_longitude_edit_is_rejected_not_stored(monkeypatch, tmp_path):
    monkeypatch.setattr(report, "_PAYLOAD_CACHE", tmp_path / "_report_payload_cache")
    out = report.apply_verification(_base_rep(), {"longitude": "not-a-number"})
    assert out["identity"]["longitude"] == -95.9
    assert isinstance(out["identity"]["longitude"], float)


def test_valid_numeric_coordinate_edit_still_applies(monkeypatch, tmp_path):
    monkeypatch.setattr(report, "_PAYLOAD_CACHE", tmp_path / "_report_payload_cache")
    out = report.apply_verification(_base_rep(), {"latitude": "47.5", "longitude": "-102.3"})
    assert out["identity"]["latitude"] == 47.5
    assert out["identity"]["longitude"] == -102.3
