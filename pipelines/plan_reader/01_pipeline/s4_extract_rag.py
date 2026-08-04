"""
s4_extract_rag.py  —  STEP 4b: STRUCTURED retrieval for the mid-document fields.

The whole-doc extractor (s3_extract.py) loses the middle of long plans to smart_truncate — exactly
where traffic level, construction dates, phasing, and most gotchas live. This module recovers them
the RAG way (retrieve the relevant section, ground Claude in it) but returns STRUCTURED values with
provenance — {value, confidence, page} and gotcha OBJECTS — not the prose the old rag_* columns held.

Fills the schema's source=="rag" fields into a record:
    traffic_level · construction_start · construction_end · phasing_requirements   (scalars)
    special_requirements [{text,page}]                                            (array)
    gotchas [{code, evidence, page, confidence}]  — over the full 20-type taxonomy (array)

~6 Claude calls per plan (3 scalar groups + special requirements + 1 gotcha classification).
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lib
import schema
import retriever
import taxonomy
import s3_extract as extract   # reuse call_json + _coerce_cell (one Claude/JSON path)

# A healthy gotcha pass unions ~10-20 chunks across the 5 family queries. Fewer than this right
# after ingest means the vector index is still cold — thin context yields partial gotchas with
# null pages and drops the rarer pricing codes (material_source/prevailing_wage/dbe_goal). We warm
# the retrieval and re-pull before spending the Claude call, so pages + pricing come through.
MIN_GOTCHA_CHUNKS = 8

# Each (field_names, retrieval_query): retrieve the right section, extract those fields from it.
# (construction dates moved to the whole-doc extractor — they sit in the agreement near the front,
# which smart_truncate keeps, and RAG was missing them.)
SCALAR_QUERIES = [
    (["traffic_level"],
     "traffic level aggregate spec class Superpave FAA Marshall gyrations 28S 34 44 58H Class 41 "
     "crushed quarry fractured faces base course surfacing mix design"),
    (["phasing_requirements"],
     "construction phasing staging sequence of operations stage construction prosecution of work"),
    (["bid_deadline", "substantial_completion", "final_completion"],
     "bid opening date bids due proposal deadline letting date substantial completion final "
     "completion contract time working days calendar days notice to proceed completion deadline "
     "liquidated damages complete the work by"),
    (["route_number", "begin_milepost", "end_milepost", "total_gross_length"],
     "title sheet route number highway REF POINT reference point begin project end project "
     "station STA gross length net length project length mileage reference marker MRM mile "
     "post MP design data"),
]

# One broad query per gotcha family — union the hits, then one classification call over the taxonomy.
FAMILY_QUERIES = {
    "Schedule & sequencing": "phasing staging sequence tight schedule completion deadline seasonal window night work",
    "Traffic & access":      "traffic control maintenance of traffic detour lane closure flagger pilot car",
    "Environmental & cultural": "environmental endangered species wetland dewatering historic cultural Section 4(f) SWPPP permit",
    "Site & scope risk":     "utility conflict box culvert bridge retaining wall earthwork borrow material source aggregate quality",
    "Contract & compliance": "prevailing wage Davis-Bacon DBE liquidated damages density failure QC inspection coordination",
}

SCALAR_PROMPT = """You are reading retrieved excerpts from a highway bid plan. Extract ONLY the fields
below from these excerpts. Return a JSON object; each field an OBJECT
  {{"value": <value or null>, "confidence": "high"|"medium"|"low", "page": <the p.PAGE from the [n] tag, or null>}}
Use null if the excerpts don't contain it — do NOT use outside knowledge or guess.

Fields:
{fields}

Excerpts (each tagged "[n] file p.PAGE (section)"):
{context}

Return ONLY the JSON object."""

SPECIAL_PROMPT = """From these retrieved excerpts of a highway bid plan, list NON-STANDARD special
requirements that affect cost or scope (skip routine/boilerplate contract language). Return a JSON
array of objects {{"text": <short description>, "page": <the p.PAGE from the [n] tag, or null>}}.
Return [] if none. Do not use outside knowledge.

Excerpts:
{context}

Return ONLY the JSON array."""

GOTCHA_PROMPT = """You are reviewing retrieved excerpts from a highway bid plan for cost/risk "gotchas".
From the TAXONOMY below, return a JSON array of the gotcha types ACTUALLY PRESENT in the excerpts.
Each item: {{"code": <exact taxonomy code>, "evidence": <short quote/paraphrase from the excerpt>,
"page": <the p.PAGE from the [n] tag, or null>, "confidence": "high"|"medium"|"low"}}.
Only include a gotcha the excerpts actually support. Do not invent. Use the exact codes. [] if none.

TAXONOMY (code — definition):
{taxonomy}

Excerpts:
{context}

Return ONLY the JSON array."""


def _doc_where(plan_id, pages=None):
    """A ChromaDB filter for one plan, optionally restricted to a set of page numbers (used to focus
    plan-set fields like traffic_level on the actual MAP pages of a combined doc)."""
    if pages:
        return {"$and": [{"doc_id": plan_id}, {"page": {"$in": list(pages)}}]}
    return {"doc_id": plan_id}


def _context(col, query, plan_id, k=5, pages=None):
    """Retrieve top-k chunks for this plan (optionally only `pages`) and format with citation tags."""
    hits = retriever.retrieve(col, query, k, where=_doc_where(plan_id, pages))
    return retriever.build_context(hits), hits


def _taxonomy_block():
    return "\n".join(f"- {code} — {t['definition']}" for code, t in taxonomy.GOTCHA_TYPES.items())


def _conf(v):
    v = str(v or "").lower()
    return v if v in schema.CONFIDENCES else ""


def _int(v):
    try:
        return int(v) if v not in (None, "", "null") else None
    except (ValueError, TypeError):
        return None


def _retrieve_gotcha_chunks(col, plan_id, _warm=3):
    """Union the top hits across all gotcha-family queries (deduped) for one plan.

    Warms up on a cold index: process_pdf ingests then immediately calls this, and the first
    query against a not-yet-warm index can return thin context. If we get fewer than
    MIN_GOTCHA_CHUNKS, pause briefly and re-pull (retrieval is cheap — no LLM cost) so the Claude
    call sees the FULL context. This is what makes pages + the pricing gotcha come through
    consistently instead of ~half the time."""
    seen, chunks = set(), []
    for query in FAMILY_QUERIES.values():
        for h in retriever.retrieve(col, query, 4, where={"doc_id": plan_id}):
            key = (h["meta"].get("page"), h["text"][:60])
            if key not in seen:
                seen.add(key)
                chunks.append(h)
    if len(chunks) < MIN_GOTCHA_CHUNKS and _warm > 1:
        time.sleep(0.4)                                  # let the index warm, then re-pull
        return _retrieve_gotcha_chunks(col, plan_id, _warm - 1)
    return chunks


def detect_gotchas(col, plan_id, _attempts=3):
    """Retrieve per gotcha family, union the chunks, one Claude call → validated gotcha objects.

    Retries when the result is empty AND chunks were retrieved. Rationale: process_pdf ingests then
    immediately calls this, so the FIRST retrieval can hit a not-yet-warm vector index and return
    thin/empty context → 0 gotchas (the flaky "0 gotchas" bug). A re-pull once the index is warm is
    reliable. We only retry when chunks exist but the LLM returned none — a genuinely gotcha-free plan
    (no chunks / stable empty) still resolves to []."""
    chunks = _retrieve_gotcha_chunks(col, plan_id)
    if not chunks:
        return []
    ctx = retriever.build_context(chunks)
    data = extract.call_json(GOTCHA_PROMPT.format(taxonomy=_taxonomy_block(), context=ctx), max_tokens=2000)
    if not data and _attempts > 1:                       # empty/parse-fail on a plan that HAS content
        return detect_gotchas(col, plan_id, _attempts - 1)
    valid = set(taxonomy.GOTCHA_TYPES)
    # One object per gotcha CODE (the clean interface): keep the first/highest-confidence hit.
    _rank = {"high": 3, "medium": 2, "low": 1, "": 0}
    by_code = {}
    for g in data or []:
        if not (isinstance(g, dict) and g.get("code") in valid):
            continue
        item = {"code": g["code"], "evidence": str(g.get("evidence", ""))[:300],
                "page": _int(g.get("page")), "confidence": _conf(g.get("confidence"))}
        prev = by_code.get(item["code"])
        if prev is None or _rank[item["confidence"]] > _rank[prev["confidence"]]:
            by_code[item["code"]] = item
    return list(by_code.values())


def fill_rag_fields(record, col, plan_id, map_pages=None):
    """Fill the schema's source=='rag' fields (scalars + special_requirements + gotchas) into an
    existing record (in place). `col` is the ChromaDB collection; `plan_id` scopes retrieval.
    `map_pages` (from lib.detect_structure) focuses plan-set fields (doc=='plan_set', e.g.
    traffic_level) on the actual map pages of a combined doc — they live in the plan set, not the
    proposal. Fields tagged doc=='either' (phasing) still search the whole plan."""
    # scalar RAG fields, grouped by retrieval query
    for names, query in SCALAR_QUERIES:
        fields = [f for f in schema.RAG_SCALAR_FIELDS if f["name"] in names]
        # restrict to map pages only when every field in the group is a plan-set field
        pages = map_pages if (map_pages and all(f.get("doc") == "plan_set" for f in fields)) else None
        ctx, _ = _context(col, query, plan_id, k=5, pages=pages)
        data = extract.call_json(SCALAR_PROMPT.format(fields=schema.field_lines(fields), context=ctx)) or {}
        for f in fields:
            record[f["name"]] = extract._coerce_cell(f, data.get(f["name"]))

    # special_requirements (array of {text, page})
    ctx, _ = _context(col, "special provisions special requirements non-standard certification requirement", plan_id, k=6)
    sr = extract.call_json(SPECIAL_PROMPT.format(context=ctx)) or []
    record["special_requirements"] = [
        {"text": str(x.get("text", "")).strip(), "page": _int(x.get("page"))}
        for x in sr if isinstance(x, dict) and str(x.get("text", "")).strip()
    ]

    # gotchas (array of {code, evidence, page, confidence}) over the full taxonomy
    record["gotchas"] = detect_gotchas(col, plan_id)
    return record
