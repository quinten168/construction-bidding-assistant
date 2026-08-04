"""
Bridge to the standalone reverse_geocode.py tool (04_tools/reverse_geocode/) — turns the
coordinates produced by the midpoint stage into city / county / state / zip.

Same shape and rationale as midpoint_bridge.py: reverse_geocode.py has no __init__.py and is not on
any package path (CLAUDE.md invariant #2 — `pipelines/` is path-referenced, never imported as a
package), so sys.path is primed here, once, and the module imported directly.

Why this exists: `scratch.bid_projects` is keyed on
`project_natural_key = {state}_{county}_{city}_{bid_date}`, and **city is the one component
plan_reader cannot extract from a plan set**. The midpoint stage already produces coordinates; a
coordinate yields a city. See reverse_geocode.py's module docstring for the accepted imprecision.
"""
from __future__ import annotations

import sys
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from typing import Optional

from .config import REVERSE_GEOCODE_DIR, settings
from .observability import get_logger

log = get_logger("bid_assistant.geocode_bridge")

if str(REVERSE_GEOCODE_DIR) not in sys.path:
    sys.path.insert(0, str(REVERSE_GEOCODE_DIR))

import reverse_geocode  # noqa: E402 — path primed just above

_executor = ThreadPoolExecutor(max_workers=1)  # bounds wall-clock time, mirroring midpoint_bridge


def reverse_geocode_latlon(latitude, longitude) -> Optional[dict]:
    """{city, county, state, zip, provenance, formatted_address}, or None.

    Never raises. A missing city degrades `project_natural_key`; it must never fail the report —
    same fail-open convention as midpoint_bridge.compute_midpoint and competitor_live.generate.
    """
    if latitude is None or longitude is None:
        return None
    if not settings.reverse_geocode_enabled:
        return None

    try:
        future = _executor.submit(reverse_geocode.reverse_geocode_cached, latitude, longitude)
        return future.result(timeout=settings.reverse_geocode_timeout)
    except FutureTimeoutError:
        log.warning("geocode: timed out after %ss for (%s, %s)",
                    settings.reverse_geocode_timeout, latitude, longitude)
        return None
    except Exception as e:                                     # noqa: BLE001 — never break the report
        log.warning("geocode: lookup failed for (%s, %s) — %s", latitude, longitude, e)
        return None
