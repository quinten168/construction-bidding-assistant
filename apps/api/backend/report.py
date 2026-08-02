"""
PDF → report.

Runs the Plan Reader pipeline on an uploaded plan PDF and returns a structured report payload
(archetype + key fields + gotchas + quantities). This is the same read path as
`plan_reader/run.py inspect`, invoked programmatically (minus the file-writing), and it ingests the
plan into the vector store so the user can then *chat about the plan they just dropped*.

The heavy lifting (PDF→Markdown, indexing, two Claude extraction passes) lives in the Plan Reader;
we just orchestrate it and shape the result for the chat UI.
"""
from __future__ import annotations

import datetime
import json
from pathlib import Path

from . import midpoint_bridge
from . import plan_reader_bridge  # noqa: F401 — ensures 01_pipeline is on sys.path
from . import project_registry
from .config import settings
from .observability import get_logger, timed

import lib                # noqa: E402
import schema             # noqa: E402
import s1_convert as convert        # noqa: E402
import s2_indexer as indexer        # noqa: E402
import s3_extract as extract        # noqa: E402
import s4_extract_rag as extract_rag  # noqa: E402

log = get_logger("bid_assistant.report")

# plan-reader field name → the MAT code the archetype rule expects
_QMAP = {"hot_mix_tons": "MIX_TN", "grading_quantity": "GRADE_CY", "base_tons": "BASE_TN",
         "shoulder_tons": "SHLDR_TN", "milling_sy": "MILL_SY", "crushing_tons": "CRUSH_TN",
         "stockpile_tons": "STOCK_TN"}
_UNIT = {"MIX_TN": "t", "GRADE_CY": "CY", "BASE_TN": "t", "SHLDR_TN": "t", "MILL_SY": "SY",
         "CRUSH_TN": "t", "STOCK_TN": "t"}


# Re-drop short-circuit: the same file content yields the same report, so cache the assembled
# payload by CONTENT HASH (reusing the converter's hash). A re-drop of a seen PDF then skips convert
# + ingest + BOTH Claude passes and returns in ~0s — the single biggest win for the test loop, where
# the same plan is dropped over and over under fresh UUID filenames.
#
# The cache is written ONLY by apply_verification() (below), not by process_pdf() itself — a payload
# isn't "final" the moment extraction finishes, it's final once a human has been through the verify
# gate. process_pdf() still checks the cache first (a re-drop of an already-verified plan skips the
# whole pipeline AND the verify step, same instant-return behavior as before), it just never writes
# it — an unverified extraction is never cached, so it can't be mistaken for a finished one.
_PAYLOAD_CACHE = lib.DATA_DIR / "_report_payload_cache"


def _payload_cache_path(content_hash: str) -> Path:
    return _PAYLOAD_CACHE / (content_hash + ".json")


def _val(field):
    """Scalar fields are {value, confidence, page}; unwrap to the value."""
    return field.get("value") if isinstance(field, dict) else field


def _conf(field) -> dict:
    """Scalar fields are {value, confidence, page}; pull confidence/page for the verify UI (the
    value itself is handled separately by _val()). confidence is a 3-level string enum
    ("high"|"medium"|"low") per s3_extract.py's extraction prompt, not a numeric score."""
    if isinstance(field, dict):
        return {"confidence": field.get("confidence"), "page": field.get("page")}
    return {"confidence": None, "page": None}


def _classify_read_error(e: Exception) -> tuple[str, str]:
    """Map a raw pipeline exception to a (reason_code, human_message) so the UI can tell the user
    *why* a PDF couldn't be read instead of a bare 'ValueError'."""
    msg = str(e).lower()
    if "textpage" in msg or "no text" in msg or "cannot extract text" in msg or "empty" in msg:
        return ("no_text_layer",
                "This PDF has no selectable text — it looks scanned or image-based (a photographed "
                "proposal or a CAD drawing). The reader works on text-based bid proposals; scanned "
                "documents need OCR (LlamaParse), which isn't wired into the MVP yet.")
    if isinstance(e, TimeoutError) or "timeout" in msg or "timed out" in msg:
        return ("timeout",
                "This PDF is large or complex and timed out while being read. Try the core proposal "
                "document rather than a full combined plan set.")
    if "password" in msg or "encrypt" in msg:
        return ("encrypted", "This PDF is password-protected / encrypted, so it can't be read. "
                             "Re-export it without protection and try again.")
    return ("read_error",
            f"Could not read this PDF ({type(e).__name__}). It may be corrupt or an unsupported "
            f"format — confirm it's a text-based bid proposal.")


def process_pdf(pdf_path: str | Path, plan_id: str | None = None) -> dict:
    """Run the read path on one PDF and return a report payload. Raises nothing fatal — returns
    {"ok": False, ...} for handled cases (e.g. a drawings-only plan set)."""
    pdf_path = Path(pdf_path)
    plan_id = plan_id or pdf_path.stem
    content_hash = convert._hash(pdf_path)

    cache = _payload_cache_path(content_hash)               # same content → same (verified) report
    if cache.exists():
        try:
            rep = json.loads(cache.read_text())
            log.info("report: payload cache hit (%s) — skipping convert/ingest/extract", cache.name)
            return rep
        except Exception:                                  # corrupt cache → fall through and rebuild
            pass

    structure = lib.detect_structure(pdf_path)
    if structure["type"] == "plan_set":
        return {"ok": False, "reason": "plan_set", "plan_id": plan_id,
                "message": "This looks like a drawings/plan-set-only PDF (no bid-proposal pages). "
                           "The reader works on bid proposals — try the proposal document."}

    log.info("report: processing %s (%s, %d pages)", plan_id, structure["type"], structure["n_pages"])
    # The read pipeline (convert → ingest → extract) can fail on a scanned/image PDF, a CAD drawing,
    # an encrypted file, or a timeout. Catch it and return a CLASSIFIED reason so the UI explains why.
    try:
        with timed(log, f"convert {plan_id}"):
            md_pages = convert.convert_pages(pdf_path)

        col = lib.get_collection()
        with timed(log, f"ingest {plan_id}"):
            indexer.ingest_pdf(pdf_path, col, rec={"plan_id": plan_id},
                               disp_table=lib.load_disposition(), trace=[])

        record = schema.blank_record(plan_id, pdf_path.name, datetime.date.today().isoformat())
        prop = set(structure["proposal_pages"])
        proposal_md = convert.pages_to_markdown([p for p in md_pages if p["page"] in prop])
        with timed(log, f"extract {plan_id}"):
            extract.fill_extract_fields(record, extract.smart_truncate(proposal_md, extract.MAX_CHARS))
        with timed(log, f"extract_rag {plan_id}"):
            extract_rag.fill_rag_fields(record, col, plan_id, map_pages=structure["map_pages"])
    except Exception as e:                                  # noqa: BLE001
        reason, message = _classify_read_error(e)
        log.warning("report: read failed for %s — %s (%s)", plan_id, reason, e)
        return {"ok": False, "reason": reason, "plan_id": plan_id, "message": message}

    # 5th stage: route/milepost fields → lat/long, via state DOT GIS lookups (midpoint_bridge.py).
    # Never allowed to fail the report — a lookup miss just leaves latitude/longitude null, and a
    # human can fill them in via record_correction (merged in at render time, final_report.py).
    latitude = longitude = None
    if settings.midpoint_lookup_enabled:
        try:
            with timed(log, f"midpoint {plan_id}"):
                result = midpoint_bridge.compute_midpoint(
                    state=_val(record.get("state")),
                    route=_val(record.get("route_number")),
                    begin_mp_raw=_val(record.get("begin_milepost")),
                    total_length=_val(record.get("total_gross_length")),
                    end_mp_raw=_val(record.get("end_milepost")),
                )
        except Exception as e:                                  # noqa: BLE001 — never break the report
            log.warning("report: midpoint stage errored for %s — %s", plan_id, e)
            result = None
        if result:
            latitude, longitude = result

    # archetype from the extracted quantities (v2 rule, reused from the resolver)
    qrow = {dst: _val(record.get(src)) for src, dst in _QMAP.items()}
    archetype = project_registry._archetype(qrow)

    # Identity fields, keyed the way they're shown in the UI (e.g. "location", not the underlying
    # record field "project_location") — built once here so field_confidence and identity below
    # stay in lockstep instead of two separate lists of record.get(...) calls that could drift.
    identity_fields = {
        "state": record.get("state"), "county": record.get("county"),
        "location": record.get("project_location"), "sp_number": record.get("sp_number"),
        "prevailing_wages": record.get("prevailing_wages"),
        "traffic_level": record.get("traffic_level"),
        "construction_start": record.get("construction_start"),
        "construction_end": record.get("construction_end"),
        "bid_deadline": record.get("bid_deadline"),
        "substantial_completion": record.get("substantial_completion"),
        "final_completion": record.get("final_completion"),
    }
    # field_confidence: identity fields first, quantities appended below — for the verify-gate UI.
    # latitude/longitude are deliberately absent here: they come from midpoint_bridge's lookup, not
    # an extraction cell, so there's no comparable confidence value; the verify UI treats location
    # as its own dedicated block instead of folding it into this confidence-flagged field list.
    field_confidence = {k: _conf(v) for k, v in identity_fields.items()}

    quantities = []
    for src, dst in _QMAP.items():
        field = record.get(src)
        value = _val(field)
        if value in (None, "", 0):
            continue
        label = dst.replace("_TN", "").replace("_CY", "").replace("_SY", "")
        quantities.append({"label": label, "value": value, "unit": _UNIT[dst]})
        field_confidence[label] = _conf(field)

    gotchas = [{"code": g.get("code"), "evidence": g.get("evidence"),
                "page": g.get("page"), "confidence": g.get("confidence")}
               for g in (record.get("gotchas") or [])]

    rep = {
        "ok": True, "plan_id": plan_id, "archetype": archetype,
        "structure": {k: structure[k] for k in ("type", "n_pages", "proposal_ranges", "map_ranges")},
        "identity": {
            **{k: _val(v) for k, v in identity_fields.items()},
            "latitude": latitude, "longitude": longitude,
        },
        "quantities": quantities,
        "gotchas": gotchas,
        "field_confidence": field_confidence,
        "content_hash": content_hash,
        # False until a human has been through the verify gate and apply_verification() writes the
        # cache below — see apply_verification()'s docstring for why caching moved out of here.
        "verified": False,
    }
    return rep


def apply_verification(rep: dict, edits: dict) -> dict:
    """The verify-gate finalize step. `edits` is a flat {field: value} map from the verify UI —
    identity field keys (matching process_pdf's identity_fields above) and/or quantity `label`s,
    plus "latitude"/"longitude" — and is applied directly onto this payload's identity/quantities,
    the SAME place auto-extracted values already live (by explicit 2026-07-31 request: a
    user-entered lat/long or corrected quantity is written into the same payload-cache JSON as the
    quantities, not into corrections.py's separate sidecar file — that mechanism is for a different,
    later-in-time use case, fixing a field via chat *after* a report already exists).

    Marks the payload verified and writes it to the payload cache — this is what makes a re-drop of
    the same PDF, post-verification, return instantly with the verified values (process_pdf's
    cache-hit check at the top of this file only ever finds payloads written from here)."""
    rep = dict(rep)  # shallow copy — don't mutate the caller's in-memory extraction
    identity = dict(rep.get("identity") or {})
    quantities = [dict(q) for q in (rep.get("quantities") or [])]
    by_label = {q["label"]: q for q in quantities}

    for field, value in (edits or {}).items():
        if field in ("latitude", "longitude"):
            try:
                identity[field] = float(value)
            except (TypeError, ValueError):
                identity[field] = value
        elif field in by_label:
            try:
                by_label[field]["value"] = float(value)
            except (TypeError, ValueError):
                by_label[field]["value"] = value
        else:
            identity[field] = value

    rep["identity"] = identity
    rep["quantities"] = quantities
    rep["verified"] = True

    content_hash = rep.get("content_hash")
    if content_hash:
        try:
            _PAYLOAD_CACHE.mkdir(parents=True, exist_ok=True)
            _payload_cache_path(content_hash).write_text(json.dumps(rep))
        except Exception:                                     # best-effort, same as the old cache write
            pass
    return rep
