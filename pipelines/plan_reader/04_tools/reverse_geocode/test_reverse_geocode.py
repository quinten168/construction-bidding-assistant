"""Tests for the reverse-geocode stage. No network: every test stubs the HTTP call.

The component-parsing logic is the part worth testing — it is where the original implementation's
behaviour is carried over, and where this version deliberately diverges (short_name for state).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
import reverse_geocode as rg  # noqa: E402


def _component(long_name, short_name, types):
    return {"long_name": long_name, "short_name": short_name, "types": types}


STEARNS = {
    "status": "OK",
    "results": [{
        "formatted_address": "Melrose, MN 56352, USA",
        "address_components": [
            _component("Melrose", "Melrose", ["locality", "political"]),
            _component("Stearns County", "Stearns County", ["administrative_area_level_2"]),
            _component("Minnesota", "MN", ["administrative_area_level_1"]),
            _component("United States", "US", ["country"]),
            _component("56352", "56352", ["postal_code"]),
        ],
    }],
}


class _Resp:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._payload


@pytest.fixture(autouse=True)
def _key_and_clean_cache(monkeypatch):
    monkeypatch.setenv("GOOGLE_GEOCODING_API_KEY", "test-key-not-real")
    rg._cache.clear()
    monkeypatch.setattr(rg.time, "sleep", lambda _s: None)
    yield
    rg._cache.clear()


def _stub(monkeypatch, payload, status=200, recorder=None):
    def fake_get(url, params=None, timeout=None):
        if recorder is not None:
            recorder.append(params)
        return _Resp(payload, status)
    monkeypatch.setattr(rg.requests, "get", fake_get)


def test_parses_all_four_fields(monkeypatch):
    _stub(monkeypatch, STEARNS)
    out = rg.reverse_geocode_latlon(45.6752, -94.8083)
    assert out["city"] == "Melrose"
    assert out["county"] == "Stearns County"
    assert out["zip"] == "56352"
    assert out["provenance"] == "reverse_geocode"


def test_state_is_the_two_letter_code_not_the_full_name(monkeypatch):
    """Deliberate divergence from the original, which used long_name and would give 'Minnesota'.

    bid_projects.state and the contract §3 join_key prefix are both two-letter.
    """
    _stub(monkeypatch, STEARNS)
    assert rg.reverse_geocode_latlon(45.6752, -94.8083)["state"] == "MN"


def test_county_keeps_its_suffix_for_join_key_to_strip(monkeypatch):
    """join_key.normalize_county strips a trailing 'county' per contract §3, so leaving it here
    keeps the raw API answer inspectable without breaking the key."""
    _stub(monkeypatch, STEARNS)
    county = rg.reverse_geocode_latlon(45.6752, -94.8083)["county"]
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "01_pipeline"))
    from join_key import normalize_county
    assert normalize_county(county) == "stearns"


def test_zero_results_is_none_not_an_error(monkeypatch):
    _stub(monkeypatch, {"status": "ZERO_RESULTS", "results": []})
    assert rg.reverse_geocode_latlon(0.0, 0.0) is None


def test_application_error_in_a_200_body_returns_none(monkeypatch):
    """Google reports quota/key errors as HTTP 200 with a status field — the same 'don't trust an
    HTTP 200' class as CLAUDE.md rough edges 2 and 6."""
    _stub(monkeypatch, {"status": "OVER_QUERY_LIMIT", "results": [],
                        "error_message": "You have exceeded your daily request quota"})
    assert rg.reverse_geocode_latlon(45.0, -94.0) is None


def test_http_failure_returns_none_never_raises(monkeypatch):
    def boom(*a, **k):
        raise ConnectionError("DNS is having a day")
    monkeypatch.setattr(rg.requests, "get", boom)
    assert rg.reverse_geocode_latlon(45.0, -94.0) is None


def test_missing_api_key_returns_none_rather_than_raising(monkeypatch):
    monkeypatch.delenv("GOOGLE_GEOCODING_API_KEY", raising=False)
    assert rg.reverse_geocode_latlon(45.0, -94.0) is None


@pytest.mark.parametrize("lat,lon", [(None, -94.0), (45.0, None), (None, None), ("x", "y")])
def test_missing_or_unparseable_coords_return_none(lat, lon):
    assert rg.reverse_geocode_latlon(lat, lon) is None


def test_cache_collapses_coords_within_rounding(monkeypatch):
    calls = []
    _stub(monkeypatch, STEARNS, recorder=calls)
    a = rg.reverse_geocode_cached(45.67521, -94.80831)
    b = rg.reverse_geocode_cached(45.67519, -94.80834)  # same to 3dp
    assert a == b
    assert len(calls) == 1, "second lookup should have been served from cache"


def test_cache_does_not_merge_genuinely_different_places(monkeypatch):
    calls = []
    _stub(monkeypatch, STEARNS, recorder=calls)
    rg.reverse_geocode_cached(45.675, -94.808)
    rg.reverse_geocode_cached(46.877, -96.789)
    assert len(calls) == 2


def test_a_none_result_is_cached_too(monkeypatch):
    """Otherwise a coordinate that legitimately has no locality re-hits the API every time."""
    calls = []
    _stub(monkeypatch, {"status": "ZERO_RESULTS", "results": []}, recorder=calls)
    assert rg.reverse_geocode_cached(0.0, 0.0) is None
    assert rg.reverse_geocode_cached(0.0, 0.0) is None
    assert len(calls) == 1


def test_missing_city_component_yields_none_city_not_a_crash(monkeypatch):
    """A rural midpoint can land outside any locality. The key degrades; nothing fails."""
    payload = {
        "status": "OK",
        "results": [{
            "formatted_address": "Unnamed Road, ND, USA",
            "address_components": [
                _component("Morton County", "Morton County", ["administrative_area_level_2"]),
                _component("North Dakota", "ND", ["administrative_area_level_1"]),
            ],
        }],
    }
    _stub(monkeypatch, payload)
    out = rg.reverse_geocode_latlon(46.5, -100.9)
    assert out["city"] is None
    assert out["county"] == "Morton County"
    assert out["state"] == "ND"


def test_the_api_key_is_never_returned_in_the_result(monkeypatch):
    _stub(monkeypatch, STEARNS)
    assert "test-key-not-real" not in repr(rg.reverse_geocode_latlon(45.6752, -94.8083))


# --- issue #56: a failed request and a genuine empty answer must not look alike -----------------

REQUEST_DENIED = {
    "status": "REQUEST_DENIED",
    "results": [],
    "error_message": "You must enable Billing on the Google Cloud Project ...",
}


def test_request_denied_is_logged_at_error_with_googles_verbatim_message(monkeypatch, caplog):
    """The failure that hid the 2026-08-03 billing outage. HTTP 200, empty results, real cause
    only in `status`/`error_message` — it must not be mistaken for 'no city at this coordinate'."""
    _stub(monkeypatch, REQUEST_DENIED)
    with caplog.at_level("DEBUG", logger="plan_reader.reverse_geocode"):
        assert rg.reverse_geocode_latlon(47.2897, -101.0290) is None
    errors = [r for r in caplog.records if r.levelname == "ERROR"]
    assert errors, "a REQUEST_DENIED must log at ERROR, not pass silently"
    msg = errors[0].getMessage()
    assert "REQUEST_DENIED" in msg
    assert "enable Billing" in msg, "Google's error_message must be surfaced verbatim"


def test_zero_results_does_not_log_an_error(monkeypatch, caplog):
    """The counterpart: a legitimately locality-free coordinate is not a failure and must stay
    quiet, or the ERROR channel becomes noise and stops being read."""
    _stub(monkeypatch, {"status": "ZERO_RESULTS", "results": []})
    with caplog.at_level("DEBUG", logger="plan_reader.reverse_geocode"):
        assert rg.reverse_geocode_latlon(0.0, 0.0) is None
    assert not [r for r in caplog.records if r.levelname == "ERROR"]


def test_a_failed_lookup_is_never_cached_so_it_recovers_after_the_outage(monkeypatch):
    """The second-order bug. A cached failure survived the fix: every coordinate tried during an
    outage kept returning None afterwards, so an in-flight batch could not recover."""
    calls = []
    _stub(monkeypatch, REQUEST_DENIED, recorder=calls)
    assert rg.reverse_geocode_cached(45.0, -95.0) is None
    assert rg.reverse_geocode_cached(45.0, -95.0) is None
    assert len(calls) == 2, "a failure must be retried, not memoised"

    # ...and once the outage clears, the same coordinate resolves without a restart.
    _stub(monkeypatch, STEARNS, recorder=calls)
    out = rg.reverse_geocode_cached(45.0, -95.0)
    assert out is not None and out["city"] == "Melrose"


def test_missing_api_key_logs_an_error_rather_than_disabling_silently(monkeypatch, caplog):
    """An unset key made the stage a no-op and sent every natural key to the UNKNOWN sentinel."""
    monkeypatch.delenv("GOOGLE_GEOCODING_API_KEY", raising=False)
    with caplog.at_level("DEBUG", logger="plan_reader.reverse_geocode"):
        assert rg.reverse_geocode_latlon(45.0, -95.0) is None
    assert [r for r in caplog.records if r.levelname == "ERROR"]
