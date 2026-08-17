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
from typing import NamedTuple
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


# 2026-08-11 — cell shape reordered to reason-before-value, project-wide. Caught live: a Pope Co MN
# plan's base_tons cell wrote "AGGREGATE SURFACING CLASS 1 MOD ... Value is null" in its own reason
# text, then returned value=8225 anyway — the exact wrong figure the reasoning had just excluded, and
# also double-counted (correctly) into shoulder_tons for the same line. Root cause: the old shape was
# {"value": ..., ..., "reason": ...} — value FIRST. JSON is generated left-to-right/top-to-bottom, so
# the model commits to a number before it has finished reasoning; a mid-"reason" self-correction
# ("however... re-evaluating...") can no longer reach the "value" key already written. Same mechanism
# as the milling_sy fix earlier the same day (Grant Co plan, 83,777 vs. reasoning's own 92,123) — that
# fix worked around it for one field (raw-item capture, arithmetic moved to code); THIS fix addresses
# the shared root cause directly, for every field. Verified empirically before shipping, not assumed:
# reordering alone (nothing else changed) fixed both the Pope Co base/shoulder case (base_tons: 8225 ->
# 0, matching "Value is null") and the Grant Co milling_sy case (92123 on 2/2 fresh runs, previously
# wrong on every run) — see docs/_session/2026-08-11-reason-before-value.md.
EXTRACTION_PROMPT = """You are reading a highway-construction RFP / bid plan for a paving contractor.
Extract the fields listed below into a single JSON object. For EVERY field, return an OBJECT with
"reason" BEFORE "value" — work out and write your reasoning FIRST, then decide "value" LAST, so the
value you write is the conclusion of the reasoning rather than a number you commit to before you've
finished thinking it through:
  {{"reason": <short explanation, written BEFORE you decide the value>, "confidence": "high" | "low", "page": <page number or null>, "value": <the value you land on AFTER writing "reason" — or null if not stated>}}

Rules:
- Do NOT guess. If the document doesn't state a field, use "value": null.
- Write "reason" first and let it be where you actually work out the answer — including reconsidering
  or ruling out a candidate item — and only then commit to "value". If "reason" concludes an item is
  excluded or belongs elsewhere, "value" must reflect that conclusion (null or the corrected number),
  never the pre-correction number.
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


# ── The three-state contract for one Claude JSON call ──────────────────────────
#
# A failure and a legitimate empty answer must never share a return value. One Claude JSON call has
# exactly three outcomes and they are now three distinct values, not one None:
#
#   OK        — the model answered and the answer parsed. `data` may legitimately be {} / [] —
#               that is an EMPTY ANSWER, not a failure, and it is only ever reachable here.
#   TRUNCATED — resp.stop_reason == "max_tokens". The answer was cut off mid-JSON. Read off the
#               API's own stop_reason, never inferred from the JSONDecodeError text.
#   MALFORMED — the response ended normally but did not parse.
#
# Vocabulary is deliberately the one s4_extract_rag already uses for the same class of problem
# (`record["rag_scalar_parse_failures"]`, 2026-08-10): the *word* for "the model's reply was
# unreadable" is a PARSE FAILURE, and truncation is one named kind of it. No second vocabulary.
OK = "ok"
TRUNCATED = "truncated"
MALFORMED = "malformed"


class JsonResult(NamedTuple):
    """One Claude JSON call's outcome. `status` is OK / TRUNCATED / MALFORMED; `data` is the parsed
    JSON on OK and None otherwise; `message` names the cause in one line (log/UI-ready)."""
    status: str
    data: object
    message: str
    stop_reason: str

    @property
    def is_ok(self) -> bool:
        return self.status == OK


class ExtractionParseFailure(RuntimeError):
    """The whole-doc extraction call did not produce a usable answer. Raised — never returned as an
    empty record — so a truncated or unreadable extraction surfaces as an ERROR instead of a full
    record of clean null cells that reads exactly like a plan stating nothing.

    `kind` is s3_extract.TRUNCATED or s3_extract.MALFORMED. It is also exposed as the duck-typed
    attribute `extraction_failure_kind`, which is what apps/api/backend/report.py's
    _classify_read_error branches on (so report.py needs no import of this class)."""

    def __init__(self, result: "JsonResult"):
        super().__init__(result.message)
        self.kind = result.status
        self.extraction_failure_kind = result.status   # what report.py::_classify_read_error reads
        self.stop_reason = result.stop_reason


def _first_balanced_json(text: str):
    """The first BALANCED top-level {...} or [...] in `text`, as (parsed, preamble_length).

    Returns None when there is nothing salvageable — never a partial parse, and never a bare
    exception: the caller has to be able to tell "salvaged" from "genuinely malformed", so those
    must not share a return value.

    Balanced rather than regex because a brace or bracket inside a STRING value would truncate a
    naive match mid-object and hand back a plausible-looking half record. Tracks string state and
    backslash escapes for that reason.
    """
    for start, opener in enumerate(text):
        if opener not in "{[":
            continue
        closer = "}" if opener == "{" else "]"
        depth, in_string, escaped = 0, False, False
        for i in range(start, len(text)):
            ch = text[i]
            if escaped:
                escaped = False
                continue
            if ch == "\\" and in_string:
                escaped = True
                continue
            if ch == '"':
                in_string = not in_string
                continue
            if in_string:
                continue
            if ch == opener:
                depth += 1
            elif ch == closer:
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[start:i + 1]), start
                    except json.JSONDecodeError:
                        break   # this candidate is not valid JSON; try the next opener
        # unbalanced to end of text, or invalid — fall through to the next candidate
    return None


def call_json_result(prompt: str, max_tokens: int = 2048) -> JsonResult:
    """One Claude call → JsonResult (the three-state contract above). This is the shared low-level
    call; `call_json` below is the legacy shim over it."""
    client = anthropic.Anthropic(api_key=API_KEY)
    # temperature=0: extraction is a deterministic task. The default (1.0) made the gotcha/date pass
    # FLAKY — the same plan returned 3 gotchas on one run and 0 on the next (~1 in 3 empty). Pinning
    # to 0 makes extraction reproducible and reliable (the single biggest fix for the "0 gotchas" bug).
    resp = client.messages.create(model=MODEL, max_tokens=max_tokens, temperature=0,
                                  messages=[{"role": "user", "content": prompt}])
    stop_reason = getattr(resp, "stop_reason", None)
    raw = resp.content[0].text.strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        # PREAMBLE SALVAGE, added 2026-08-10 from the ruling-#9 measurement. Making the field
        # descriptions more procedural ("do X, then Y") measurably improved WHAT the model
        # extracted and cost parseability: 9 of 9 unparseable runs across 30 failed with
        # `Expecting value: line 1 column 1` — a sentence of prose in front of otherwise valid
        # JSON. That is a 6.7% total loss of correct answers to a formatting habit.
        #
        # Salvage the first BALANCED top-level object/array rather than regexing for braces, so a
        # brace inside a string value cannot truncate the payload mid-object.
        #
        # Deliberately AFTER the strict parse and BEFORE the truncation branch: a cut-off response
        # must stay TRUNCATED. A salvaged prefix of a truncated answer would be a partial record
        # wearing an OK status, which is the exact defect this function was written to kill.
        if stop_reason != "max_tokens":
            salvaged = _first_balanced_json(raw)
            if salvaged is not None:
                data, span = salvaged
                print(f"  NOTE: stripped a {span}-char preamble before valid JSON "
                      f"(salvaged, not a failure)")
                return JsonResult(OK, data, "", stop_reason)
        # NAME THE CAUSE, and name it from stop_reason rather than from the exception text. Seen
        # live 2026-08-10: adding six schema fields pushed the whole-doc extraction to exactly 2048
        # output tokens on plan 9786015 — the "failure" was a full, correct answer that ran out of
        # room, and the shipped code reported it as bad JSON and returned a null record.
        if stop_reason == "max_tokens":
            msg = (f"extraction response was CUT OFF at the max_tokens cap ({max_tokens}) — this is "
                   f"TRUNCATION, not bad JSON; raise the token budget")
            status = TRUNCATED
        else:
            msg = f"malformed JSON from the model ({e})"
            status = MALFORMED
        print(f"  WARNING: JSON parse failed — {msg}. Raw:\n{raw[:400]}")
        return JsonResult(status, None, msg, stop_reason)
    if stop_reason == "max_tokens":
        # Parsed *and* cut off: possible when the cut happens to land on a syntactically complete
        # prefix. The answer is still incomplete, so it is TRUNCATED, not OK — a partial record must
        # not be handed on as a finished one.
        msg = (f"extraction response hit the max_tokens cap ({max_tokens}) — the JSON parsed but is "
               f"INCOMPLETE; raise the token budget")
        print(f"  WARNING: {msg}")
        return JsonResult(TRUNCATED, None, msg, stop_reason)
    return JsonResult(OK, data, "", stop_reason)


def call_json(prompt: str, max_tokens: int = 2048):
    """Legacy shim: parsed JSON, or None on ANY failure (truncated or malformed).

    Kept for the callers that only have one non-null branch anyway — s4_extract_rag's gotcha /
    special-requirements / scalar passes (which already convert a None into an explicit
    `rag_scalar_parse_failures` entry rather than a null cell) and the 03_evaluation runners. New
    code should call `call_json_result` and branch on the three states; this shim exists so that
    fixing the whole-doc collapse did not require editing four other callers the night before a demo.
    """
    return call_json_result(prompt, max_tokens=max_tokens).data


# Output-token budget for the whole-doc extraction. Sized to the FIELD COUNT, not guessed: every
# extract field returns a {value, confidence, page, reason} cell and the `reason` is prose, so the
# response grows with the schema. At 24 fields the old shared default of 2048 was hit exactly (plan
# 9786015, 2026-08-10) and the whole extraction came back as null cells. Raise this when fields are
# added — see the truncation note in call_json.
EXTRACT_MAX_TOKENS = 6000


def extract_fields(document_text: str) -> dict:
    """One Claude call → {field_name: cell} for the schema's whole-doc (source=='extract') fields."""
    prompt = EXTRACTION_PROMPT.format(
        field_list=schema.extract_prompt_fields(),
        archetypes=archetype_choices(),
        document_text=document_text,
    )
    print("  Sending to Claude for whole-doc extraction...")
    result = call_json_result(prompt, max_tokens=EXTRACT_MAX_TOKENS)
    if not result.is_ok:
        # The old code was `call_json(...) or {}`, which turned BOTH failure states into a full
        # record of clean null cells — byte-identical to a plan that states nothing, and (worse)
        # cacheable by report.py::apply_verification as if it were finished. Raise instead: the
        # caller classifies it (report.py returns ok:False, reason extraction_truncated /
        # extraction_unreadable) and nothing empty is ever written anywhere as a result.
        raise ExtractionParseFailure(result)
    data = result.data if isinstance(result.data, dict) else {}
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
    try:
        fill_extract_fields(record, text)
    except ExtractionParseFailure as e:
        # Exit non-zero rather than writing a results.csv row of nulls that looks like a real read.
        print(f"\nERROR: extraction failed ({e.kind}) — {e}")
        print("       Nothing was written to results.csv. Re-run; if this is 'truncated', "
              "raise EXTRACT_MAX_TOKENS.")
        sys.exit(2)

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
