"""
s3_extract.py  —  STEP 4: whole-document field extraction (the structured MVP extractor).

Pulls the SCHEMA's whole-doc fields (source=="extract": identity + bid-schedule quantities +
prevailing wages) from a plan PDF in one Claude call. The full doc fits in context — no vector
store needed. Each field comes back with PROVENANCE: {value, confidence, page}.

Mid-document fields (traffic_level, construction dates, phasing, gotchas) are NOT here — they sit
in the part smart_truncate drops, so they're pulled by structured retrieval in 01_pipeline/s4_extract_rag.py.
The canonical per-PDF JSON + results.csv row are assembled in run.py from both halves; the schema
is defined once in 01_pipeline/schema.py.

Usage (fields-only quick check; updates 02_outputs/results.csv):
    python s3_extract.py <path_to_pdf>
"""

import sys
import json
import csv
import os
import re
import datetime
from pathlib import Path
import pdfplumber
import anthropic

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lib       # single source of paths (.env, 02_outputs/)
import schema    # the canonical field schema

API_KEY = os.environ.get("ANTHROPIC_API_KEY") or lib.ENV_PATH.read_text().split("'")[1]
MAX_CHARS = 180_000   # ~45k tokens — leave headroom for prompt + response
MODEL = "claude-sonnet-4-6"


def archetype_choices():
    """The project_type choices, from knowledge/project_archetypes.csv (editable as data)."""
    if lib.ARCHETYPES_CSV.exists():
        rows = list(csv.DictReader(open(lib.ARCHETYPES_CSV)))
        return ", ".join(f'"{r["archetype"]}"' for r in rows)
    return ('"Reconstruct/Rebuild", "Mill & Overlay", "HMA Overlay/Resurface", '
            '"Grading/Earthwork", "Aggregate/Base/Gravel"')


EXTRACTION_PROMPT = """You are reading a highway-construction RFP / bid plan for a paving contractor.
Extract the fields listed below into a single JSON object. For EVERY field, return an OBJECT:
  {{"value": <the value, or null if not stated>, "confidence": "high" | "low", "page": <page number or null>, "reason": <short explanation>}}

Rules:
- Do NOT guess. If the document doesn't state a field, use "value": null.
- confidence is "high" ONLY when the value is stated directly in the text you were given (verbatim,
  or an unambiguous sum of explicit bid-schedule line items) — set "page" to where it appears.
- confidence is "low" for everything else: a value you had to infer, interpret, or aren't fully
  certain is correct. Low-confidence fields get flagged for a human to double-check, so use "low"
  whenever the value isn't directly and clearly supported by the text.
- "reason" is one short sentence justifying the confidence: for "high", quote or point to exactly
  where the text states it (e.g. "Bid Schedule Item 2105.501, line total"); for "low", say what's
  missing or uncertain (e.g. "not stated anywhere in the text — inferred from project type" or
  "two conflicting values found on p.3 and p.9"). Leave "" only when value is null.
- The document is annotated with page markers (e.g. `<!-- page 12 -->` or `[Page 12]`). Set "page" to that number where you found the value (null if unknown).
- Numbers (the *_tons / *_quantity / *_sy fields): return a plain number — no commas, no units. Sum the bid-schedule line items if needed.
- Booleans (box_culvert, prevailing_wages): return true or false.
- Items fields (name ends in "_items", e.g. base_cy_items): "value" is a JSON ARRAY, not a number —
  one object per qualifying bid item, in the exact shape that field's own instructions describe.
  Return an empty array [] (not null) if no item qualifies. Each item object holds ONLY numbers you
  read directly off the page (a quantity, a stated thickness) — do NOT multiply, sum, or convert
  anything yourself for an items field, even though you convert/sum for ordinary number fields.
  List one entry per qualifying bid item; downstream code does every calculation.
- For project_type, "value" must be one of: {archetypes}

Fields:
{field_list}

Document text (annotated with [Page N]; may be truncated for very large files):
---
{document_text}
---

Return ONLY the JSON object, with exactly one key per field above, no other text."""


# ── PDF parsing ────────────────────────────────────────────────────────────────

def extract_text_from_pdf(pdf_path) -> str:
    """All text from the PDF, each page prefixed with a [Page N] marker (so Claude can cite)."""
    pages = []
    with pdfplumber.open(pdf_path) as pdf:
        print(f"  PDF has {len(pdf.pages)} pages")
        for i, page in enumerate(pdf.pages):
            text = page.extract_text() or ""
            if text.strip():
                pages.append(f"[Page {i+1}]\n{text}")
    full = "\n\n".join(pages)
    print(f"  Extracted {len(full):,} characters from {len(pages)} non-empty pages")
    return full


def smart_truncate(text: str, max_chars: int) -> str:
    """Keep first 60% + last 40% of the budget (bid schedule early, special provisions late).
    KNOWN LIMITATION: drops the middle — mid-doc fields (wages, phasing, traffic level) are
    recovered by 01_pipeline/s4_extract_rag.py instead."""
    if len(text) <= max_chars:
        return text
    head = int(max_chars * 0.6)
    tail = max_chars - head
    print(f"  Truncated to {max_chars:,} chars (kept first {head:,} + last {tail:,})")
    return text[:head] + f"\n\n[... {len(text) - max_chars:,} characters omitted ...]\n\n" + text[-tail:]


# ── Claude extraction → schema cells ────────────────────────────────────────────

def _coerce_num(raw_num):
    """A single item-field number (quantity/depth_in) -> float, or None if unparseable. Shares
    the same comma/dollar-stripping tolerance as a top-level 'num' field."""
    if isinstance(raw_num, (int, float)):
        return float(raw_num)
    try:
        return float(str(raw_num).replace("$", "").replace(",", "").strip())
    except (ValueError, TypeError, AttributeError):
        return None


def _coerce_items(raw_list):
    """The model's per-item list for an 'items' field -> a clean list of {quantity, unit, depth_in,
    page, note} dicts, or None if the response wasn't a list at all (extraction failure — kept
    distinguishable from a genuine, model-asserted empty list). Never raises on a malformed entry:
    a single bad item is dropped rather than failing the whole field, since the field's own
    'value is None vs value is []' distinction is what downstream status logic depends on, not
    per-item strictness."""
    if not isinstance(raw_list, list):
        return None
    items = []
    for entry in raw_list:
        if not isinstance(entry, dict):
            continue
        quantity = _coerce_num(entry.get("quantity"))
        if quantity is None:
            continue
        unit = str(entry.get("unit") or "").strip().upper()
        depth_in = _coerce_num(entry.get("depth_in"))
        page = entry.get("page")
        try:
            page = int(page) if page not in (None, "", "null") else None
        except (ValueError, TypeError):
            page = None
        note = str(entry.get("note", "") or "").strip()
        items.append({"quantity": quantity, "unit": unit, "depth_in": depth_in,
                      "page": page, "note": note})
    return items


def _coerce_cell(field, raw):
    """Normalize Claude's per-field object into a schema cell, coercing the value to the field's
    type. Accepts a bare scalar too (older/looser responses) by wrapping it."""
    if not isinstance(raw, dict):
        raw = {"value": raw}
    value = raw.get("value")
    conf = str(raw.get("confidence", "") or "").lower()
    conf = conf if conf in schema.CONFIDENCES else ""
    page = raw.get("page")
    reason = str(raw.get("reason", "") or "").strip()
    try:
        page = int(page) if page not in (None, "", "null") else None
    except (ValueError, TypeError):
        page = None
    if field["type"] == "items":
        # A list is never "absent" the way a scalar's "" / "null" is — an empty list [] is the
        # model's own asserted "no qualifying item", not a missing answer. Only a genuinely
        # missing/non-list value collapses to None here.
        value = _coerce_items(value)
        return schema.cell(value, conf, page, reason)
    if value in (None, "", "null"):
        return schema.cell(None, "", None)   # absent → no confidence/page/reason to report
    if field["type"] == "num":
        try:
            value = float(str(value).replace("$", "").replace(",", "").strip())
            value = int(value) if value == int(value) else value
        except (ValueError, TypeError):
            value = None
    elif field["type"] == "bool":
        if isinstance(value, str):
            value = value.strip().lower() in ("true", "yes", "y", "x", "1")
        else:
            value = bool(value)
    else:
        value = str(value).strip()
    return schema.cell(value, conf, page, reason)


def call_json(prompt: str, max_tokens: int = 2048):
    """One Claude call that returns parsed JSON (object or array), or None on parse failure.
    Shared by the whole-doc extractor and the structured RAG step (01_pipeline/s4_extract_rag.py)."""
    client = anthropic.Anthropic(api_key=API_KEY)
    # temperature=0: extraction is a deterministic task. The default (1.0) made the gotcha/date pass
    # FLAKY — the same plan returned 3 gotchas on one run and 0 on the next (~1 in 3 empty). Pinning
    # to 0 makes extraction reproducible and reliable (the single biggest fix for the "0 gotchas" bug).
    resp = client.messages.create(model=MODEL, max_tokens=max_tokens, temperature=0,
                                  messages=[{"role": "user", "content": prompt}])
    raw = resp.content[0].text.strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"  WARNING: JSON parse failed ({e}). Raw:\n{raw[:400]}")
        return None


def extract_fields(document_text: str) -> dict:
    """One Claude call → {field_name: cell} for the schema's whole-doc (source=='extract') fields."""
    prompt = EXTRACTION_PROMPT.format(
        field_list=schema.extract_prompt_fields(),
        archetypes=archetype_choices(),
        document_text=document_text,
    )
    print("  Sending to Claude for whole-doc extraction...")
    # max_tokens raised from the call_json default (2048) on 2026-08-10: adding the three
    # base_cy_items/shoulder_cy_items/mix_sy_depth_items array fields pushed a real response past
    # 2048 tokens and truncated mid-JSON (confirmed live on the Murray Co/Fulda plan — a JSON parse
    # failure, not a clean empty result). 6000 leaves real headroom for a document with several
    # qualifying items across all three new fields plus every existing field's own citation text.
    data = call_json(prompt, max_tokens=6000) or {}
    return {f["name"]: _coerce_cell(f, data.get(f["name"])) for f in schema.EXTRACT_FIELDS}


def fill_extract_fields(record: dict, document_text: str) -> dict:
    """Run whole-doc extraction and write its cells into an existing schema record (in place)."""
    record.update(extract_fields(document_text))
    return record


# ── Standalone main (fields-only quick check; updates results.csv) ──────────────

def process_pdf(pdf_path: str):
    path = Path(pdf_path)
    if not path.exists():
        print(f"ERROR: File not found: {path}")
        sys.exit(1)
    print(f"\nProcessing: {path.name}\n" + "-" * 60)
    text = extract_text_from_pdf(path)
    if len(text) < 100:
        print("  WARNING: very little text — PDF may be image-only (needs OCR/LlamaParse).")
    text = smart_truncate(text, MAX_CHARS)

    plan_id = lib.plan_id_for(path.stem)
    record = schema.blank_record(plan_id, path.name, datetime.date.today().isoformat())
    fill_extract_fields(record, text)

    print("\nExtracted whole-doc fields (value [conf] p.page):")
    for f in schema.EXTRACT_FIELDS:
        c = record[f["name"]]
        if c["value"] is not None:
            print(f"  {f['name']:18}: {str(c['value'])[:60]:60} [{c['confidence']}] p.{c['page']}")

    # Update results.csv (merge — won't wipe RAG columns a prior run.py inspect wrote).
    lib.upsert_csv(lib.RESULTS_CSV, "plan_id", schema.flatten_row(record), schema.CSV_COLUMNS)
    print(f"\nDone. results.csv updated (whole-doc fields only — run.py inspect writes the full JSON).")
    return record


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python s3_extract.py <path_to_pdf>")
        sys.exit(1)
    process_pdf(sys.argv[1])
