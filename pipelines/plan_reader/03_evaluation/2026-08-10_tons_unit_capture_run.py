"""
2026-08-10_tons_unit_capture_run.py — the RED-BEFORE-GREEN proof for the tons-bucket off-unit
capture, and the no-regression sweep that goes with it.

WHY THIS IS NOT A UNIT TEST
---------------------------
The live PDF-drop path's material mapping IS the quantity field descriptions in
01_pipeline/schema.py. It is a prompt. A unit test over a prompt asserts nothing about what the
model does with it. So the defect is proved on the real document, both arms, same extractor,
temperature=0 (pinned in s3_extract.py).

THE DEFECT (CSI live test, plan 9786015 — CSAH 2 / Maryland Ave, Murray Co MN)
-----------------------------------------------------------------------------
The bid schedule states `Class 5 Aggregate Base (CV) (P) | CY | 2,485` (page 27 of the converted
markdown). `base_tons` is TONS by name and by destination column, so the CY line had nowhere to go
and the extraction returned a bare null — indistinguishable from a plan with no aggregate base.

  --arm old   : the field set WITHOUT the six new fields. Expected RED — base_tons null, and
                nothing anywhere in the record says the 2,485 CY item exists.
  --arm new   : the working tree's field set. Expected GREEN — base_measured_unit names the unit,
                base_unconverted names the ITEM, its VALUE and its UNIT verbatim, and
                schema.bucket_unit_status(record, "base_tons") == "unconverted_only".

NOTHING IS CONVERTED. Spec: docs/_spec/2026-08-10-tons-bucket-unit-capture.md.

STANDING RULE, ENFORCED HERE
----------------------------
A failure and a legitimate empty answer never share a return value. A document that errors is
recorded with status ERROR and null totals; a document that genuinely states no quantities is
recorded with status OK. The two are never merged.

Usage:
    python 2026-08-10_tons_unit_capture_run.py --plan a3171c2187e8af85 --arm old --out old.json
    python 2026-08-10_tons_unit_capture_run.py --plan a3171c2187e8af85 --arm new --out new.json
    python 2026-08-10_tons_unit_capture_run.py --sweep --out sweep.json   # every cached plan, new arm
"""

import argparse
import json
import sys
from pathlib import Path

_PIPE = Path(__file__).resolve().parent.parent / "01_pipeline"
sys.path.insert(0, str(_PIPE))
import schema           # noqa: E402
import s3_extract       # noqa: E402

MODULE_ROOT = Path(__file__).resolve().parent.parent
MD_CACHE = MODULE_ROOT / "00_input" / "_md_cache"

QUANTITY_FIELDS = ["hot_mix_tons", "base_tons", "grading_quantity", "shoulder_tons",
                   "milling_sy", "crushing_tons", "stockpile_tons"]

# The six fields under test. The `old` arm is the field set with these REMOVED, which is exactly
# what shipped before this change — not a paraphrase of it.
NEW_FIELDS = ["hot_mix_measured_unit", "hot_mix_unconverted",
              "base_measured_unit", "base_unconverted",
              "shoulder_measured_unit", "shoulder_unconverted"]


def fields_for_arm(arm):
    if arm == "old":
        return [f for f in schema.EXTRACT_FIELDS if f["name"] not in NEW_FIELDS]
    return list(schema.EXTRACT_FIELDS)


def document_text(md_path):
    """Page-annotated document text, in the same [Page N] form s3_extract builds from a PDF, so the
    model sees exactly what the live path shows it."""
    pages = json.load(open(md_path))
    return "\n\n".join(f"[Page {p.get('page')}]\n{p.get('text', '')}" for p in pages
                       if (p.get("text") or "").strip())


def run_one(md_path, arm):
    stem = Path(md_path).stem
    rec = {"hash": stem, "arm": arm, "status": None, "totals": None,
           "capture": None, "statuses": None, "error": None}
    try:
        text = s3_extract.smart_truncate(document_text(md_path), s3_extract.MAX_CHARS)
    except (OSError, json.JSONDecodeError, KeyError) as e:
        rec["status"] = "ERROR"
        rec["error"] = f"markdown unreadable: {e.__class__.__name__}: {e}"
        return rec
    if len(text) < 100:
        rec["status"] = "ERROR"
        rec["error"] = f"document text too short to extract from ({len(text)} chars)"
        return rec

    fields = fields_for_arm(arm)
    prompt = s3_extract.EXTRACTION_PROMPT.format(
        field_list=schema.field_lines(fields),
        archetypes=s3_extract.archetype_choices(),
        document_text=text,
    )
    data = s3_extract.call_json(prompt, max_tokens=s3_extract.EXTRACT_MAX_TOKENS)
    if data is None:
        rec["status"] = "ERROR"
        rec["error"] = "model response did not parse as JSON"
        return rec

    cells, totals, capture = {}, {}, {}
    for f in fields:
        cell = s3_extract._coerce_cell(f, data.get(f["name"]))
        cells[f["name"]] = cell
        if f["name"] in QUANTITY_FIELDS:
            totals[f["name"]] = cell["value"]
        if f["name"] in NEW_FIELDS:
            capture[f["name"]] = cell["value"]

    rec["status"] = "OK"
    rec["totals"] = totals
    rec["capture"] = capture or None
    # Derived, never asked of the model. Recorded on BOTH arms so the run itself shows that the old
    # arm can only ever say "unknown" — it has no field to say anything else with.
    rec["statuses"] = {b: schema.bucket_unit_status(cells, b) for b in schema.TONS_BUCKETS}
    return rec


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan", help="md_cache stem (content hash) of one plan")
    ap.add_argument("--arm", choices=["old", "new"], default="new")
    ap.add_argument("--sweep", action="store_true", help="run every cached plan on the new arm")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    if a.sweep:
        paths = sorted(p for p in MD_CACHE.glob("*.json") if not p.name.endswith(".hybrid.json"))
    else:
        if not a.plan:
            ap.error("--plan is required unless --sweep")
        paths = [MD_CACHE / f"{a.plan}.json"]

    out = []
    for p in paths:
        r = run_one(p, "new" if a.sweep else a.arm)
        out.append(r)
        print(f"{r['hash']}  {r['status']}  base_tons={(r['totals'] or {}).get('base_tons')!r}  "
              f"base={r['statuses']['base_tons'] if r['statuses'] else '-'}  "
              f"{(r['capture'] or {}).get('base_unconverted') or ''}")
    Path(a.out).write_text(json.dumps(out, indent=2))
    print(f"\nwrote {a.out}  ({len(out)} documents, "
          f"{sum(1 for r in out if r['status'] == 'ERROR')} ERROR)")


if __name__ == "__main__":
    main()
