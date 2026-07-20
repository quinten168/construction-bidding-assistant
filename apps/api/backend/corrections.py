"""
Human-in-the-loop corrections.

The extraction is an automated first pass — estimators must be able to confirm it and fill in what
the model couldn't get (above all the project's lat/long, which plans almost never state explicitly,
and any quantity the reader misread). This module persists those user corrections to a per-plan
sidecar file and exposes them as a tool the agent calls whenever the user states a correction.

Corrections live OUTSIDE the shared plan corpus (in this module's data/ dir) so verifying an upload
never mutates the Plan Reader's source-of-truth JSONs. Downstream consumers can merge them in.
"""
from __future__ import annotations

import datetime
import json
from pathlib import Path

from .observability import get_logger

log = get_logger("bid_assistant.corrections")

CORR_DIR = Path(__file__).resolve().parent.parent / "data" / "corrections"

# canonical fields a user may verify/add, with the aliases the model might pass
_FIELD_ALIASES = {
    "lat_long": {"lat_long", "latlong", "lat/long", "latlon", "coordinates", "coords",
                 "location_coordinates", "lat_lon"},
    "location": {"location", "project_location", "address"},
    "hot_mix_tons": {"hot_mix_tons", "mix", "mix_tn", "hot_mix", "hma"},
    "grading_quantity": {"grading_quantity", "grade", "grade_cy", "grading"},
    "base_tons": {"base_tons", "base", "base_tn", "aggregate_base"},
    "shoulder_tons": {"shoulder_tons", "shoulder", "shldr_tn", "shldr"},
    "milling_sy": {"milling_sy", "mill", "mill_sy", "milling"},
    "crushing_tons": {"crushing_tons", "crush", "crush_tn"},
    "stockpile_tons": {"stockpile_tons", "stock", "stock_tn", "stockpile"},
    "prevailing_wages": {"prevailing_wages", "prevailing_wage", "wages"},
    "traffic_level": {"traffic_level", "traffic"},
    "construction_start": {"construction_start", "start_date", "start"},
    "construction_end": {"construction_end", "completion", "end_date", "completion_date"},
    "sp_number": {"sp_number", "sp", "project_number", "project_no", "cp_number", "pcn"},
}
_ALIAS_TO_CANON = {a: canon for canon, aliases in _FIELD_ALIASES.items() for a in aliases}
EDITABLE_FIELDS = sorted(_FIELD_ALIASES)


def _canonical(field: str) -> str:
    return _ALIAS_TO_CANON.get(field.strip().lower().replace(" ", "_"), field.strip().lower())


def _path(plan_id: str) -> Path:
    safe = "".join(c if c.isalnum() or c in "-_." else "_" for c in plan_id)
    return CORR_DIR / f"{safe}.json"


def save_correction(plan_id: str, field: str, value) -> dict:
    """Record one user correction. Returns {field, value} (canonicalized)."""
    CORR_DIR.mkdir(parents=True, exist_ok=True)
    canon = _canonical(field)
    data = get_corrections(plan_id)
    data[canon] = {"value": value, "source": "user",
                   "at": datetime.datetime.now().isoformat(timespec="seconds")}
    _path(plan_id).write_text(json.dumps(data, indent=2, default=str))
    log.info("correction saved: %s · %s = %r", plan_id, canon, value)
    return {"field": canon, "value": value}


def get_corrections(plan_id: str) -> dict:
    """All saved corrections for a plan: {canonical_field: {value, source, at}}."""
    p = _path(plan_id)
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text())
    except Exception:
        return {}


def corrected_values(plan_id: str) -> dict:
    """Flat {field: value} of the user's confirmed/added values (for display + downstream)."""
    return {k: v.get("value") for k, v in get_corrections(plan_id).items()}


# --- agent tool ----------------------------------------------------------------------------------
TOOL_SCHEMA = {
    "name": "record_correction",
    "description": (
        "Save a user's correction or added detail for a plan they're reviewing — e.g. the project's "
        "lat/long coordinates (which plans rarely state), a corrected quantity, prevailing-wage "
        "status, or a date. Call this whenever the user states a value to confirm/fix/add. Use the "
        "active plan's id. After saving, briefly confirm what you recorded.\n"
        f"Canonical field names: {', '.join(EDITABLE_FIELDS)} (map the user's wording to one)."),
    "input_schema": {
        "type": "object",
        "properties": {
            "plan_id": {"type": "string", "description": "The plan being corrected."},
            "field": {"type": "string", "description": "One of the canonical field names."},
            "value": {"type": "string", "description": "The user's value (e.g. '45.62,-95.05', '5200')."},
        },
        "required": ["plan_id", "field", "value"],
    },
}


def run(tool_input: dict) -> dict:
    return save_correction(tool_input["plan_id"], tool_input["field"], tool_input["value"])
