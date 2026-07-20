"""
eval_extraction.py  —  score the structured extraction against the golden set, side by side.

For every golden row with a local PDF, we get the Plan Reader's structured record (the per-PDF JSON
written by `run.py inspect` if present, else a quick whole-doc extract) and compare each field to the
golden value via the schema's golden map (`01_pipeline/schema.py: GOLDEN_MAP`):

    numeric (hot_mix_tons, …)  -> "within 10%"          (auto)
    boolean (prevailing…)      -> exact after normalize (auto)
    state / location           -> code / county-containment (auto)
    date / text                -> exact / fuzzy          (auto)
    traffic_level, phasing, gotchas, special_requirements, dates -> verdict 'review'  (HUMAN-judged:
        golden has no ground truth for these yet — shown side-by-side so Alex fills golden as he scans)

Output (the thing to open): 02_02_outputs/scorecards/<date>_extraction_vs_golden.csv — one row per (plan, field):
    plan_id, field, golden, extracted, verdict, page, confidence

IMPORTANT framing unchanged: golden quantities are an UNVERIFIED master-join baseline (~146 rows may be
mis-attributed), so a numeric 'miss' means "PDF and master DISAGREE — adjudicate by hand", not proof the
extractor is wrong. Plan-set-only packages (e.g. 08MQ) are skipped (no proposal → no bid fields).

Run:
    .venv/bin/python pipelines/plan_reader/03_evaluation/eval_extraction.py            # use per-PDF JSON / cache
    .venv/bin/python pipelines/plan_reader/03_evaluation/eval_extraction.py --fresh    # re-extract (Claude calls)
"""
import csv
import sys
import json
import datetime
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / ".." / "01_pipeline"))  # 01_pipeline/ holds lib + step modules
import lib
import schema
import s3_extract as extract
import s1_convert as convert
from rapidfuzz import fuzz

GOLDEN = lib.GOLDEN_CSV
LEDGER = lib.LEDGER_CSV
PLANS_DIR = lib.PLANS_DIR
OUT_CSV = lib.OUT_SCORECARDS / f"{datetime.date.today().isoformat()}_extraction_vs_golden.csv"

_STATE_ABBR = {"minnesota": "MN", "north dakota": "ND", "south dakota": "SD",
               "iowa": "IA", "nebraska": "NE", "wisconsin": "WI"}


def norm_state(v):
    s = str(v).strip().lower()
    return _STATE_ABBR.get(s, s).lower()


def county_token(location):
    s = str(location).strip()
    for sep in (" CO ", " CO.", " COUNTY"):
        if sep in s.upper():
            return s[: s.upper().index(sep)].strip().lower()
    return s.split()[0].lower() if s.split() else ""


def to_num(v):
    if v is None:
        return None
    s = str(v).replace("$", "").replace(",", "").strip()
    try:
        return float(s)
    except ValueError:
        return None


def to_bool(v):
    s = str(v).strip().lower()
    if s in ("yes", "true", "y", "x", "1"):
        return True
    if s in ("no", "false", "n", "0", ""):
        return False
    return None


def compare(kind, golden, extracted):
    """'match' | 'miss' | 'n/a' (n/a = golden blank, nothing to score)."""
    g_blank = golden is None or str(golden).strip() == ""
    if kind == "num":
        gv, ev = to_num(golden), to_num(extracted)
        if gv is None:
            return "n/a"
        if ev is None:
            return "miss"
        return "match" if abs(ev - gv) <= 0.10 * max(abs(gv), 1) else "miss"
    if kind == "bool":
        if g_blank:
            return "n/a"
        return "match" if to_bool(golden) == to_bool(extracted) else "miss"
    if g_blank:
        return "n/a"
    if kind == "state":
        return "match" if norm_state(golden) == norm_state(extracted) else "miss"
    if kind == "location":
        tok = county_token(golden)
        return "match" if tok and tok in str(extracted).lower() else "miss"
    if kind == "date":
        return "match" if str(golden).strip() == str(extracted).strip() else "miss"
    return "match" if fuzz.ratio(str(golden).lower(), str(extracted).lower()) >= 85 else "miss"


def extracted_cell(record, field):
    """Return (value, page, confidence) for a schema field from a record. Array fields (gotchas,
    special_requirements) flatten to a readable string with no single page/confidence."""
    if field == "gotchas":
        return "; ".join(g.get("code", "") for g in (record.get("gotchas") or [])), None, ""
    if field == "special_requirements":
        return "; ".join(x.get("text", "") for x in (record.get("special_requirements") or [])), None, ""
    c = record.get(field) or {}
    return c.get("value"), c.get("page"), c.get("confidence", "")


EVAL_CACHE = lib.OUT_SCORECARDS / "_eval_records.json"   # whole-doc records for PDFs that have no per-PDF JSON


def get_record(pdf, plan_id, fresh, cache):
    """The structured record for a PDF: prefer the per-PDF JSON (full, written by run.py inspect);
    else a quick whole-doc extract (cached in `cache`) that fills the AUTO-scored fields (no RAG).
    Returns (record, src) or (None, 'plan_set') for a plan-set-only package (skipped — no proposal)."""
    jpath = pdf.parent / f"{plan_id}.json"
    if jpath.exists() and not fresh:
        return json.loads(jpath.read_text()), "json"
    if plan_id in cache and not fresh:
        return cache[plan_id], "cached whole-doc extract"
    structure = lib.detect_structure(pdf)
    if structure["type"] == "plan_set":
        return None, "plan_set"
    rec = schema.blank_record(plan_id, pdf.name, datetime.date.today().isoformat())
    rec["document_structure"] = {k: structure[k] for k in
                                 ("type", "n_pages", "proposal_ranges", "map_ranges", "boundary_page")}
    md_pages = convert.convert_pages(pdf)
    prop = set(structure["proposal_pages"])
    text = extract.smart_truncate(
        convert.pages_to_markdown([p for p in md_pages if p["page"] in prop]), extract.MAX_CHARS)
    extract.fill_extract_fields(rec, text)
    cache[plan_id] = rec
    EVAL_CACHE.parent.mkdir(parents=True, exist_ok=True)
    EVAL_CACHE.write_text(json.dumps(cache, indent=2))
    return rec, "extract(whole-doc only — no JSON; human-judged fields blank)"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fresh", action="store_true", help="re-extract (Claude calls) instead of the per-PDF JSON")
    args = ap.parse_args()

    golden_rows = [r for r in csv.DictReader(open(GOLDEN)) if r["source_file"]]
    if not golden_rows:
        print("No golden rows have a local PDF (source_file). Nothing to eval.")
        return
    print(f"Evaluating {len(golden_rows)} golden PDF(s) against the structured extraction.")
    print("Auto-scored = quantities/location/wages/box; 'review' = human-judged (golden blank).\n")
    cache = json.loads(EVAL_CACHE.read_text()) if (EVAL_CACHE.exists() and not args.fresh) else {}

    auto_kinds = {"num", "bool", "state", "location", "date", "text"}
    # field -> (golden_col, kind). Fields with no golden column (traffic_level, phasing, …) are
    # review-only — still shown side-by-side (golden blank) so Alex can fill golden as he scans.
    field_golden = {field: (gcol, kind) for gcol, (field, kind) in schema.GOLDEN_MAP.items()}
    all_fields = [f["name"] for f in schema.SCALAR_FIELDS] + [a["name"] for a in schema.ARRAY_FIELDS]
    tally = {field: {"match": 0, "miss": 0, "n/a": 0}
             for field, (gc, kind) in field_golden.items() if kind in auto_kinds}
    diff_rows = []

    for gr in golden_rows:
        pdf = next(PLANS_DIR.rglob(gr["source_file"]), None)
        plan_id = lib.plan_id_for(pdf.stem) if pdf else gr["source_file"]
        print(f"── {gr['source_file']}  (cid {gr['contract_id'] or '—'}, {gr['bid_outcome']}) ──")
        if pdf is None:
            print(f"   PDF not found under {PLANS_DIR.name}/; skipping.\n")
            continue
        record, src = get_record(pdf, plan_id, args.fresh, cache)
        if record is None:
            print("   plan-set-only package — skipped (no proposal/bid fields).\n")
            continue
        print(f"   ({src})")

        for field in all_fields:
            gcol, kind = field_golden.get(field, (None, "review"))
            gval = gr.get(gcol) if gcol else ""
            eval_v, page, conf = extracted_cell(record, field)
            if kind in auto_kinds:
                verdict = compare(kind, gval, eval_v)
                tally[field][verdict] += 1
                if verdict != "n/a":
                    flag = "✓" if verdict == "match" else "✗"
                    print(f"   {flag} {field:18} golden={str(gval)!r:>14}  extracted={eval_v!r}")
            else:
                verdict = "review"
            diff_rows.append({"plan_id": plan_id, "field": field, "golden": gval,
                              "extracted": eval_v, "verdict": verdict,
                              "page": page if page is not None else "", "confidence": conf})
        print()

    # ── the scannable diff CSV ──
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    cols = ["plan_id", "field", "golden", "extracted", "verdict", "page", "confidence"]
    with open(OUT_CSV, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(diff_rows)
    print(f"↳ side-by-side diff (scan in VSCode): {OUT_CSV}\n")

    # ── stdout scorecard (auto-scored only) ──
    print("══ SCORECARD (auto-scored fields, across evaluated PDFs) ══")
    print(f"   {'field':18} {'scored':>6} {'match':>6} {'accuracy':>9}")
    for c, t in tally.items():
        scored = t["match"] + t["miss"]
        acc = f"{100*t['match']/scored:.0f}%" if scored else "—"
        flag = "  ⚠ <80%" if scored and t["match"] / scored < 0.8 else ""
        print(f"   {c:18} {scored:>6} {t['match']:>6} {acc:>9}{flag}")
    print("\nReminder: low accuracy = PDF/master DISAGREEMENT to adjudicate by hand (golden unverified).")
    print("Human-judged fields (traffic_level, phasing, dates, gotchas, special_requirements) are in the")
    print("diff CSV with verdict 'review' — fill the golden columns as you confirm them.")

    section_tag_precision()


def section_tag_precision():
    """Section-tag PRECISION from the human ledger + the Otter Tail p.1 cross-ref regression.
    Skips cleanly if the ledger doesn't exist."""
    if not LEDGER.exists():
        return
    rows = list(csv.DictReader(open(LEDGER)))
    reviewed = [r for r in rows if (r.get("verdict") or "").strip() in ("ok", "wrong")]
    print("\n══ SECTION-TAG PRECISION (from the human ledger) ══")
    if reviewed:
        ok = sum(1 for r in reviewed if r["verdict"].strip() == "ok")
        print(f"   precision = {ok}/{len(reviewed)} = {100*ok/len(reviewed):.0f}%")
    else:
        print("   (ledger has no reviewed verdicts yet)")
    col = lib.get_collection()
    got = col.get(where={"$and": [{"doc_id": "2023_OTTER-TAIL-CO-MN_CP-4069-304_LOST"}, {"page": 1}]},
                  include=["metadatas"])
    secs = {m.get("section") for m in got["metadatas"]}
    print(f"   regression — Otter Tail p.1 tag == proposal_front: "
          f"{'✓ PASS' if secs == {'proposal_front'} else f'✗ FAIL (got {secs})'}")


if __name__ == "__main__":
    main()
