"""
Bridge to the standalone bid_date.py tool (04_tools/bid_date/) — extracts the bid submission
deadline (date AND time) from a dropped PDF, deterministically, with no Claude call.

Why the live path needs this (2026-08-10): `bid_deadline` is a RAG field. On the City of Fulda
plan (9786015.pdf, 466 pages) the Advertisement for Bids page IS in Chroma — verified — but the
`bid_deadline` retrieval query ranks it ~33rd, and s4_extract_rag retrieves k=5. So the field came
back null on a plan that plainly states it. Downstream, CI computes capacity per bidding season
from the bid date, and a null bid date falls back to the construction completion date, lands in
the wrong season and reports ZERO capacity.

This runs off the ALREADY-CONVERTED markdown pages that process_pdf holds anyway, so it adds no
PDF read, no embedding, and no LLM call.

bid_date.py has no __init__.py and is not on any package path (CLAUDE.md invariant #2:
`pipelines/` is path-referenced, never imported as a package). Same sys.path-priming pattern as
midpoint_bridge.py / plan_reader_bridge.py.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional, Sequence

from .config import BID_DATE_DIR
from .observability import get_logger

log = get_logger("bid_assistant.bid_date_bridge")

if str(BID_DATE_DIR) not in sys.path:
    sys.path.insert(0, str(BID_DATE_DIR))

import bid_date  # noqa: E402 — path primed just above


def compute_bid_deadline(md_pages: Sequence[dict], pdf_path: Optional[Path] = None) -> Optional[dict]:
    """The bid deadline for one dropped PDF, or None when no layer produced one.

    `md_pages` is s1_convert.convert_pages output ([{page, text}, ...]) — layer 2.
    `pdf_path`, when given, also enables layer 1: a standalone advertisement PDF sitting in the
    same folder as the plan set. That is the authoritative source where it exists, but on the
    live drop path the upload is a lone temp file, so layer 1 is normally a no-op there and
    layer 2 carries the load.

    Returns a dict shaped for the report payload, or None. NEVER raises — same fail-safe
    convention as midpoint_bridge.compute_midpoint. An unreadable document and a document that
    genuinely states no bid date are distinguished in the log, not collapsed into one silence.
    """
    try:
        result = None
        if pdf_path is not None:
            ads = bid_date.find_advertisement_pdfs(Path(pdf_path).parent)
            for ad in ads:
                if Path(ad).resolve() == Path(pdf_path).resolve():
                    continue
                res = bid_date.extract_from_pdf(ad, layer=bid_date.LAYER_ADVERTISEMENT_PDF)
                if res.ok:
                    result = res
                    break
                if res.status == bid_date.STATUS_ERROR:
                    log.warning("bid_date: layer 1 could not read %s — %s", ad.name, res.error)

        if result is None:
            pages = [(p.get("page"), p.get("text") or "") for p in (md_pages or [])]
            res = bid_date.from_plan_pages(pages)
            if res.status == bid_date.STATUS_ERROR:                # cannot happen from pages today,
                log.warning("bid_date: layer 2 errored — %s", res.error)   # but never assume it
                return None
            if not res.ok:
                log.info("bid_date: no bid deadline stated in this document "
                         "(%d date candidates considered) — layer 3 (human entry) is the path",
                         res.candidates_considered)
                return None
            result = res

        log.info("bid_date: %s %s (%s) via layer %d, %s p.%s",
                 result.bid_date, result.bid_time, result.timezone, result.layer,
                 result.source_file, result.page)
        return {
            "bid_date": result.bid_date,
            "bid_time": result.bid_time,
            "timezone": result.timezone,
            "deadline_iso": result.deadline_iso(),
            "layer": result.layer,
            "source_file": result.source_file,
            "page": result.page,
            "raw": result.raw,
        }
    except Exception as e:                                    # noqa: BLE001 — never break the report
        log.warning("bid_date stage failed: %s", e)
        return None


def parse_human_entry(value: str) -> Optional[dict]:
    """Layer 3. Parse a human-typed bid deadline from the verify popup.

    Returns the same dict shape as compute_bid_deadline, or None when the text could not be
    parsed as a date — the caller keeps the human's raw text either way (see
    report.apply_verification), so an unparseable entry is never silently discarded.
    """
    if not value:
        return None
    res = bid_date.extract(human_value=str(value))
    if not res.ok:
        log.info("bid_date: human entry %r did not parse as a date", value)
        return None
    return {
        "bid_date": res.bid_date, "bid_time": res.bid_time, "timezone": res.timezone,
        "deadline_iso": res.deadline_iso(), "layer": bid_date.LAYER_HUMAN,
        "source_file": "human", "page": None, "raw": str(value),
    }
