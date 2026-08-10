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

from . import bid_date_bridge
from . import geocode_bridge
from . import midpoint_bridge
from . import payload_carry
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


# Sibling cache for the competitor-prediction cascade (final_report.predict_competitors), keyed the
# same way (content hash) so the predict-competitors endpoint's result can be reused by finalize
# instead of re-running the CI subprocess / live SQL a second time. Stores {"comp": <dict or null>} —
# the null case (cascade ran and found nothing) is itself worth caching, so finalize doesn't retry it.
_COMPETITOR_PREDICTION_CACHE = lib.DATA_DIR / "_report_competitor_prediction_cache"


def _competitor_prediction_cache_path(content_hash: str) -> Path:
    return _COMPETITOR_PREDICTION_CACHE / (content_hash + ".json")


def cache_competitor_prediction(content_hash: str, comp: dict | None) -> None:
    """Best-effort write, same fail-open convention as apply_verification's payload cache write."""
    if not content_hash:
        return
    try:
        _COMPETITOR_PREDICTION_CACHE.mkdir(parents=True, exist_ok=True)
        _competitor_prediction_cache_path(content_hash).write_text(json.dumps({"comp": comp}))
    except Exception:
        pass


def cached_competitor_prediction(content_hash: str) -> tuple[bool, dict | None]:
    """Returns (found, comp). `found=False` means no cache entry exists (caller should compute
    fresh); `found=True, comp=None` means the cascade already ran and found nothing (caller should
    NOT recompute)."""
    if not content_hash:
        return False, None
    path = _competitor_prediction_cache_path(content_hash)
    try:
        if not path.exists():
            return False, None
        return True, json.loads(path.read_text()).get("comp")
    except Exception:
        return False, None


def _val(field):
    """Scalar fields are {value, confidence, page}; unwrap to the value."""
    return field.get("value") if isinstance(field, dict) else field


def _conf(field) -> dict:
    """Scalar fields are {value, confidence, page, reason}; pull confidence/page/reason for the
    verify UI (the value itself is handled separately by _val()). confidence is "high"|"low" per
    s3_extract.py's extraction prompt, not a numeric score. reason is the model's own short
    justification — a citation for "high", what's missing/uncertain for "low"."""
    if isinstance(field, dict):
        return {"confidence": field.get("confidence"), "page": field.get("page"),
                "reason": field.get("reason") or None}
    return {"confidence": None, "page": None, "reason": None}


def identity_fields_from_record(record: dict) -> dict:
    """Extraction record → the payload's identity cells, keyed the way the UI shows them (e.g.
    "location", not the underlying record field "project_location").

    Built once, here, so field_confidence and payload["identity"] stay in lockstep instead of two
    separate lists of record.get(...) calls that could drift. Module-level rather than inline in
    process_pdf() so the carry-through can be coverage-tested on a real record without a PDF, a
    Chroma index, or a Claude call.
    """
    return {
        "state": record.get("state"), "county": record.get("county"),
        "location": record.get("project_location"), "sp_number": record.get("sp_number"),
        "prevailing_wages": record.get("prevailing_wages"),
        "traffic_level": record.get("traffic_level"),
        "construction_start": record.get("construction_start"),
        "construction_end": record.get("construction_end"),
        "bid_deadline": record.get("bid_deadline"),
        "substantial_completion": record.get("substantial_completion"),
        "final_completion": record.get("final_completion"),
        # Narrative RAG fields (phasing_requirements today). Until 2026-08-10 these were extracted,
        # paid for with a Claude call, written into `record` — and dropped right here, which is the
        # whole mechanism behind "phasing is invisible to us". Registry-driven so the next field to
        # need this seam is a tuple entry in payload_carry.py, not a fifth hardcoded name.
        **payload_carry.carried_values(record),
    }


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

    # 6th stage: coordinates → city / county / state / zip (geocode_bridge.py). city is the one
    # location component plan_reader cannot extract from a plan set directly. Note:
    # project_natural_key itself no longer depends on city (rebuilt on lat/long instead — #70) —
    # this stage still runs because geocoded_city/county/state/zip are useful data in their own
    # right (cross-checking the extracted county, display), not because the key needs them.
    #
    # These NEVER overwrite an extracted value — they are carried alongside, with a provenance tag,
    # per contract §4.5's coordinate_provenance pattern. county in particular is available from both
    # sources and they disagree: 10 of the 117 corpus rows have an extracted county that is "?" or
    # names two counties at once. Both values ship; the consumer chooses (contract §5).
    geo = None
    if latitude is not None and longitude is not None:
        try:
            with timed(log, f"geocode {plan_id}"):
                geo = geocode_bridge.reverse_geocode_latlon(latitude, longitude)
        except Exception as e:                                  # noqa: BLE001 — never break the report
            log.warning("report: geocode stage errored for %s — %s", plan_id, e)
            geo = None

    # 7th stage: bid submission deadline (date AND time), deterministically, off the markdown
    # pages already in hand — no extra PDF read, no embedding, no Claude call (bid_date_bridge.py).
    #
    # This exists because `bid_deadline` is a RAG field and retrieval was missing it: on the City
    # of Fulda plan the Advertisement for Bids page IS in Chroma, but it ranks ~33rd for the
    # bid_deadline query and s4_extract_rag retrieves k=5. The RAG value is kept as the fallback —
    # the deterministic read only overrides it when it actually found something.
    # A deterministic regex read of a document that states the deadline in as many words is a
    # "high"-confidence cell in the same 3-level enum s3_extract uses, and it carries the page it
    # came from — so the verify UI can show a human where to look.
    bid_deadline = bid_date_bridge.compute_bid_deadline(md_pages, pdf_path)
    if bid_deadline:
        record["bid_deadline"] = {
            "value": bid_deadline["deadline_iso"] + (
                f" {bid_deadline['timezone']}" if bid_deadline["timezone"] else ""),
            "confidence": "high",
            "page": bid_deadline["page"],
        }

    # archetype from the extracted quantities (v2 rule, reused from the resolver)
    qrow = {dst: _val(record.get(src)) for src, dst in _QMAP.items()}
    archetype = project_registry._archetype(qrow)

    identity_fields = identity_fields_from_record(record)
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

    # ND measures milling in TONS (NDDOT §411.06 pay unit is "Ton or Square Yard"), and milling_sy
    # is square yards by name and by contract. Dunn Job 23388 is BOTH at once — 408,216 SY of FDR
    # and 67,007 TON of milling/bituminous removal — so the tons are carried as their own row,
    # unconverted. No depth is assumed: conversion waits on a CSI-supplied factor.
    # See docs/_spec/2026-08-10-milling-unit-capture.md.
    #
    # THE LABEL MUST NOT BE "MILL". bid_projects_record.py writes that label straight into the
    # column literally named `mill_sy`, and competitor_predict_live.py maps "MILL" -> mill_sy into
    # the fitted competitor weights. Neither reads a unit. Tons under "MILL" would be a silent unit
    # corruption — the same defect class as everything else here, pointed the other way.
    mill_tons_field = record.get("milling_tons")
    mill_tons_value = _val(mill_tons_field)
    if mill_tons_value not in (None, "", 0):
        quantities.append({"label": "MILL_TON", "value": mill_tons_value, "unit": "TON"})
        field_confidence["MILL_TON"] = _conf(mill_tons_field)

    gotchas = [{"code": g.get("code"), "evidence": g.get("evidence"),
                "page": g.get("page"), "confidence": g.get("confidence")}
               for g in (record.get("gotchas") or [])]

    rep = {
        "ok": True, "plan_id": plan_id, "archetype": archetype,
        "structure": {k: structure[k] for k in ("type", "n_pages", "proposal_ranges", "map_ranges")},
        "identity": {
            **{k: _val(v) for k, v in identity_fields.items()},
            # Three-valued presence per carried field. "the plan states none" and "extraction did
            # not return it" must never share a value, and neither may render blank downstream —
            # payload_carry.render_value owns the rendering half of that rule.
            **payload_carry.carried_statuses(record),
            # Which unit(s) this plan actually measured milling in: sy_only / tons_only /
            # sy_and_tons / other_unit / not_present / unknown / inconsistent. Derived, never asked
            # of the model. "milling in tons", "no milling item" and "extraction failed" stay three
            # distinguishable states rather than collapsing to one null.
            "milling_unit_status": schema.milling_unit_status(record),
            "latitude": latitude, "longitude": longitude,
            "coordinate_provenance": "midpoint" if latitude is not None else None,
            # Geocoded, never overwriting the extracted equivalents above. Separate keys so an
            # extracted county and a geocoded one stay distinguishable (contract §4.5 pattern).
            "geocoded_city": (geo or {}).get("city"),
            "geocoded_county": (geo or {}).get("county"),
            "geocoded_state": (geo or {}).get("state"),
            "geocoded_zip": (geo or {}).get("zip"),
            "geocode_provenance": (geo or {}).get("provenance"),
            # Bid deadline, split. `bid_deadline` above stays the free-text-shaped field every
            # existing consumer already reads (report-card, verify UI, bid_projects_record's
            # parse_bid_date). These are the machine-readable halves CI actually needs — the
            # season is derived from bid_date, and bid_time is what the corpus filenames carry
            # ("BID RESULTS 02_16_23 10_00 AM …"). All null when no layer produced one, which is
            # the signal for layer 3 (human entry) rather than a silent fallback to a completion
            # date — the exact failure that reports zero capacity.
            "bid_date": (bid_deadline or {}).get("bid_date"),
            "bid_time": (bid_deadline or {}).get("bid_time"),
            "bid_timezone": (bid_deadline or {}).get("timezone"),
            "bid_deadline_layer": (bid_deadline or {}).get("layer"),
            "bid_deadline_source": (bid_deadline or {}).get("source_file"),
            "bid_deadline_page": (bid_deadline or {}).get("page"),
            "bid_deadline_evidence": (bid_deadline or {}).get("raw"),
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

    # LAYER 3 of the bid-date extraction. When a human types or corrects `bid_deadline` in the
    # verify popup, re-derive the machine-readable halves CI reads (bid_date / bid_time) from what
    # they typed — otherwise the human fixes the display string and CI still sees a null bid_date
    # and still lands in the wrong season. The typed text is kept verbatim in `bid_deadline`
    # regardless, so an entry we cannot parse is visible to the human rather than discarded.
    if "bid_deadline" in (edits or {}):
        parsed = bid_date_bridge.parse_human_entry(edits["bid_deadline"])
        identity["bid_date"] = (parsed or {}).get("bid_date")
        identity["bid_time"] = (parsed or {}).get("bid_time")
        identity["bid_timezone"] = (parsed or {}).get("timezone")
        identity["bid_deadline_layer"] = (parsed or {}).get("layer")
        identity["bid_deadline_source"] = "human"
        identity["bid_deadline_page"] = None
        identity["bid_deadline_evidence"] = str(edits["bid_deadline"])
        identity["bid_deadline_parsed"] = parsed is not None

    # Re-derive the carried fields' presence from the POST-edit identity. A human who types phasing
    # into the verify gate for a plan we came back `extraction_failed` on must not leave a payload
    # that carries their text and still claims the extraction failed — and one who blanks a field
    # must land on `none_found`, not on a stale `detected`. Cheap, and keeps the value and its
    # status from drifting apart in the one place a human can move them independently.
    identity.update(payload_carry.carried_statuses(identity))

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


def write_bid_project(rep: dict) -> dict | None:
    """Best-effort: upsert this verified plan into scratch.bid_projects (#36/#37), so it becomes a
    durable row a human can later attach real bid_results to and a future model retrain can learn
    from. Never blocks or breaks finalize on failure — same fail-open philosophy as the live
    competitor prediction (competitor_predict_live.py) and the midpoint lookup above."""
    try:
        import bid_projects_record as bpr          # noqa: E402 — sys.path via plan_reader_bridge
        from . import bid_projects_writer as bpw
        row = bpr.build_record(
            rep, content_hash=rep.get("content_hash"),
            source_file=rep.get("plan_id"),
            processed_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        )
        result = bpw.upsert(row, bpr.mapped_columns())
        log.info("bid_projects: wrote %s (inserted=%s, duplicate_flag=%s)",
                  result.get("project_natural_key"), result.get("inserted"), result.get("duplicate_flag"))
        return result
    except Exception as e:                            # noqa: BLE001 — must never break finalize
        log.warning("bid_projects write failed for %s: %s", rep.get("plan_id"), e)
        return None
