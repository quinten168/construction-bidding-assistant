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

from . import plan_reader_bridge  # noqa: F401 — ensures 01_pipeline is on sys.path
from . import project_registry
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
_PAYLOAD_CACHE = lib.DATA_DIR / "_report_payload_cache"


def _payload_cache_path(pdf_path: Path) -> Path:
    return _PAYLOAD_CACHE / (convert._hash(pdf_path) + ".json")


def _val(field):
    """Scalar fields are {value, confidence, page}; unwrap to the value."""
    return field.get("value") if isinstance(field, dict) else field


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

    cache = _payload_cache_path(pdf_path)                  # same content → same report
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

    # archetype from the extracted quantities (v2 rule, reused from the resolver)
    qrow = {dst: _val(record.get(src)) for src, dst in _QMAP.items()}
    archetype = project_registry._archetype(qrow)

    quantities = [{"label": dst.replace("_TN", "").replace("_CY", "").replace("_SY", ""),
                   "value": _val(record.get(src)), "unit": _UNIT[dst]}
                  for src, dst in _QMAP.items() if _val(record.get(src)) not in (None, "", 0)]

    gotchas = [{"code": g.get("code"), "evidence": g.get("evidence"),
                "page": g.get("page"), "confidence": g.get("confidence")}
               for g in (record.get("gotchas") or [])]

    rep = {
        "ok": True, "plan_id": plan_id, "archetype": archetype,
        "structure": {k: structure[k] for k in ("type", "n_pages", "proposal_ranges", "map_ranges")},
        "identity": {
            "state": _val(record.get("state")), "county": _val(record.get("county")),
            "location": _val(record.get("project_location")), "sp_number": _val(record.get("sp_number")),
            "prevailing_wages": _val(record.get("prevailing_wages")),
            "traffic_level": _val(record.get("traffic_level")),
            "construction_start": _val(record.get("construction_start")),
            "construction_end": _val(record.get("construction_end")),
            "bid_deadline": _val(record.get("bid_deadline")),
            "substantial_completion": _val(record.get("substantial_completion")),
            "final_completion": _val(record.get("final_completion")),
        },
        "quantities": quantities,
        "gotchas": gotchas,
    }
    try:                                                   # cache for instant re-drops (best-effort)
        _PAYLOAD_CACHE.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(rep))
    except Exception:
        pass
    return rep
