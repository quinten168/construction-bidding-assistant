"""
Bridge to the standalone road_midpoint.py tool (04_tools/road_midpoint/) — converts a plan's
extracted route/milepost fields into a (latitude, longitude) via state DOT GIS lookups.

road_midpoint.py has no __init__.py and is not on any package path (CLAUDE.md invariant #2:
`pipelines/` is path-referenced, never imported as a package). This mirrors plan_reader_bridge.py's
pattern for 01_pipeline: prime sys.path here, once, then import the module directly.
"""
from __future__ import annotations

import sys
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from typing import Optional

from .config import ROAD_MIDPOINT_DIR, settings
from .observability import get_logger

log = get_logger("bid_assistant.midpoint_bridge")

if str(ROAD_MIDPOINT_DIR) not in sys.path:
    sys.path.insert(0, str(ROAD_MIDPOINT_DIR))

import road_midpoint  # noqa: E402 — path primed just above

# Keep in sync with road_midpoint.find_midpoint's state dispatch (road_midpoint.py:486-508).
# road_midpoint.py is a standalone tool from a prior session; out of scope to edit here, so this
# is duplicated locally rather than exported from it.
SUPPORTED_STATES = {"MN", "ND", "SD", "NE", "IA", "MT"}

_executor = ThreadPoolExecutor(max_workers=1)  # bounds wall-clock time; road_midpoint's own
                                                # per-request timeouts (30s, hardcoded) are not
                                                # ours to override without editing that file.


def _lookup(state: str, route: str, begin_mp: float, total_length: float,
            end_mp: float | None) -> tuple[float, float]:
    return road_midpoint.find_midpoint(state, route, begin_mp, total_length, end_mp)


def compute_midpoint(state, route, begin_mp_raw, total_length, end_mp_raw=None) -> Optional[tuple]:
    """(latitude, longitude), or None on any missing input, an unsupported state, a state-DOT-API
    failure, or a timeout. Never raises — same fail-safe convention as competitor_live.py::generate
    (catch broadly, return None, caller falls back)."""
    state = (state or "").strip().upper()
    route = (route or "").strip()
    if state not in SUPPORTED_STATES or not route or not begin_mp_raw or not total_length:
        return None
    try:
        begin_mp = road_midpoint.parse_milepost(str(begin_mp_raw), state)
        end_mp = road_midpoint.parse_milepost(str(end_mp_raw), state) if end_mp_raw else None
        fut = _executor.submit(_lookup, state, route, begin_mp, float(total_length), end_mp)
        return fut.result(timeout=settings.midpoint_lookup_timeout)
    except FutureTimeoutError:
        log.warning("midpoint lookup timed out (%ss) for %s route %s",
                    settings.midpoint_lookup_timeout, state, route)
        return None
    except Exception as e:                                    # noqa: BLE001 — never break the report
        log.warning("midpoint lookup failed for %s route %s: %s", state, route, e)
        return None
