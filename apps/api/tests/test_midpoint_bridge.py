"""
Unit tests for midpoint_bridge.compute_midpoint (state DOT GIS route/milepost -> lat/long lookup).

These hit real state DOT endpoints (same project convention as test_tools.py — real data, no
mocking) and check parity with road_midpoint.py's own worked README example.

Run from the bid_assistant/ directory:   ../../.venv/bin/python3 -m pytest -q
"""
from backend import midpoint_bridge


def test_compute_midpoint_matches_cli_for_known_mn_plan():
    # Known-good MN example from road_midpoint's own README (TH 94, one SP block).
    lat, lon = midpoint_bridge.compute_midpoint(
        state="MN", route="94", begin_mp_raw="71+00.444", total_length=11.997, end_mp_raw="83+00.143")
    assert lat is not None and lon is not None
    assert 46.0 < lat < 47.0 and -96.0 < lon < -95.0   # sanity band, not exact-value assert


def test_compute_midpoint_unsupported_state_returns_none():
    assert midpoint_bridge.compute_midpoint(state="WI", route="1", begin_mp_raw="1", total_length=1) is None


def test_compute_midpoint_missing_fields_returns_none():
    assert midpoint_bridge.compute_midpoint(state="MN", route="", begin_mp_raw="1", total_length=1) is None
    assert midpoint_bridge.compute_midpoint(state="MN", route="94", begin_mp_raw="", total_length=1) is None
    assert midpoint_bridge.compute_midpoint(state="MN", route="94", begin_mp_raw="1", total_length=0) is None
