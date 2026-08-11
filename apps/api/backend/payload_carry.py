"""
Extracted record fields that must survive into the assembled report payload.

WHY THIS EXISTS. `phasing_requirements` was extracted by s4_extract_rag, paid for with a Claude
call, written into `record` — and then silently dropped at payload assembly: it was in neither
`report.py::identity_fields` nor `final_report.py::_payload_from_plan_id`. That one gap is the
literal mechanism behind "phasing is invisible to us" (diagnosis:
`docs/_session/2026-08-10-key-dates-phasing.md` §2; carry-through decision:
`docs/_spec/2026-08-10-payload-carry-through.md`).

It is a registry rather than two more hardcoded `record.get("phasing_requirements")` lines because
the same seam is about to take more fields (the phasing spec's `interim_completion_dates` /
`phase_break_interval`, and a captured raw milling value + unit). Adding one is a tuple entry here,
not an edit in four files.

Dependency-free ON PURPOSE: `report.py` imports the plan-reader pipeline (chromadb /
sentence_transformers / pymupdf4llm) at module scope and `final_report.py` imports none of it and
must not start. This module is the only shape both can import.
"""
from __future__ import annotations

# Record field names carried through to payload["identity"]. Each contributes TWO keys: the value
# under its own name, and a three-valued presence under f"{name}_status" (see presence_status).
CARRIED_FIELDS: tuple[str, ...] = (
    "phasing_requirements",
    # The tons buckets' off-unit capture (2026-08-10, eleventh instance of the standing rule).
    # hot_mix_tons/base_tons/shoulder_tons are TONS by name and by destination column, so a bucket
    # the bid schedule measures in CY or SY used to come back as a bare null — indistinguishable
    # from "this plan has no base at all". CSI hit it on plan 9786015, whose base is 2,485 CY.
    # Each of these carries the ITEM, its VALUE and its UNIT verbatim, unconverted and unsummed; the
    # REASON it was not counted is the sibling `schema.bucket_unit_status()` on identity, and the
    # `_status` this registry adds keeps "the plan has none" apart from "we never read it".
    # Spec: docs/_spec/2026-08-10-tons-bucket-unit-capture.md.
    "hot_mix_unconverted",
    "base_unconverted",
    "shoulder_unconverted",
    # grading's off-unit capture (2026-08-11, twelfth instance of the same rule). grading_quantity
    # is CUBIC YARDS, and CSI assigned it CLEAN ROCK — which Dunn prices in TONS. The shipped prose
    # named the item and then forbade tons-measured items two sentences later, so 758 T was in no
    # bucket on 13 of 13 measured runs with nothing to say so. Same contract as the three above:
    # the ITEM, its VALUE and its UNIT verbatim, unconverted and unsummed; the REASON is the
    # sibling `schema.grading_unit_status()` on identity.
    # Spec: docs/_spec/2026-08-11-grading-unit-capture.md.
    "grading_unconverted",
)

DETECTED = "detected"
NONE_FOUND = "none_found"
EXTRACTION_FAILED = "extraction_failed"

# Rendered labels. Standing rule: a failure and a legitimate empty answer never share a value, and
# NEITHER may render blank. `extraction_failed` must never reach an estimator as "no phasing".
_STATUS_LABEL = {
    NONE_FOUND: "_None stated in the plan._",
    EXTRACTION_FAILED: "⚠️ **Not captured** — this plan's extraction did not return the field.",
}
_MAX_CHARS = 300                     # same budget as gotcha evidence in final_report


def _unwrap(raw):
    """A schema cell is {value, confidence, page}; older/looser artifacts store a bare scalar."""
    if isinstance(raw, dict):
        return raw.get("value")
    return raw


def presence_status(record: dict, name: str) -> str:
    """detected | none_found | extraction_failed for one carried field.

    A MISSING KEY is `extraction_failed`, not `none_found`: the extractor never wrote the field
    (stale per-plan JSON, schema skew, a stage that did not run), and reporting that as "the plan
    has no phasing" is exactly the failure-vs-empty collapse the standing rules ban.

    Known residual hole, declared in the spec §3.1 and NOT fixed here: upstream,
    s3_extract.call_json returns None on a JSON parse failure and _coerce_cell then writes a clean
    null cell, indistinguishable from an honest "the plan states none". `none_found` therefore
    means "the record held a null", not "Claude successfully said no".
    """
    if name not in record:
        return EXTRACTION_FAILED
    value = _unwrap(record.get(name))
    if value in (None, "", "null"):
        return NONE_FOUND
    return DETECTED


def carried_values(record: dict) -> dict:
    """{field: raw cell} for every carried field the record actually has — feeds identity_fields
    (and therefore field_confidence) in report.py, so provenance survives alongside the value."""
    return {name: record.get(name) for name in CARRIED_FIELDS if name in record}


def carried_statuses(record: dict) -> dict:
    """{f"{field}_status": status} for every carried field, present or not."""
    return {f"{name}_status": presence_status(record, name) for name in CARRIED_FIELDS}


def render_value(identity: dict, name: str) -> str:
    """The §① Plan Snapshot / CSV cell for one carried field. Never returns an empty string.

    An identity carrying NEITHER key is treated as `extraction_failed` — that is the truthful
    reading of a payload cached before the field was plumbed through (all 12 as of 2026-08-10),
    not evidence that those plans have no phasing.
    """
    status = identity.get(f"{name}_status") or EXTRACTION_FAILED
    if status != DETECTED:
        return _STATUS_LABEL.get(status, _STATUS_LABEL[EXTRACTION_FAILED])
    text = str(_unwrap(identity.get(name)) or "").replace("\n", " ").strip()
    if not text:
        # `detected` with nothing to show would render blank; say so rather than print a gap.
        return _STATUS_LABEL[EXTRACTION_FAILED]
    return text if len(text) <= _MAX_CHARS else text[:_MAX_CHARS].rstrip() + "…"


def render_label(name: str) -> str:
    """Human label for a carried field, e.g. 'phasing_requirements' → 'Phasing'."""
    return _LABELS.get(name, name.replace("_", " ").capitalize())


_LABELS = {
    "phasing_requirements": "Phasing",
    "hot_mix_unconverted": "Hot mix not counted (unit is not tons)",
    "base_unconverted": "Base not counted (unit is not tons)",
    "shoulder_unconverted": "Shoulder not counted (unit is not tons)",
    "grading_unconverted": "Grading not counted (unit is not cubic yards)",
    "interim_completion_dates": "Interim completion dates",
    "phase_break_interval": "Phase break",
}
