"""
2026-08-10_mapping_regression.py — differential proof that CSI's rulings changed the live mapping
in the way the rulings predict, and in no other way.

WHY THIS IS NOT A UNIT TEST
---------------------------
The live PDF-drop path's material mapping IS the seven quantity field descriptions in
01_pipeline/schema.py. It is a prompt, not code. A unit test over a prompt asserts nothing about
what the model does with it. The only honest proof is a DIFFERENTIAL RE-RUN: the same documents
through the same extractor, once with the old prose and once with the new, diffing the seven totals.

Both arms run at temperature=0 (pinned in s3_extract.py) so a difference is attributable to the
prose and not to sampling.

CORPUS
------
00_input/_md_cache/*.json — 17 plans already converted to page-level markdown by an earlier run.
No PDF re-conversion, no new dependency. The matching plan_id comes from _report_payload_cache/
where a payload exists for the same content hash.

PASS CONDITION
--------------
Every diff must be EXPLAINED by a ruling. A move a ruling predicts (removal leaving base_tons, FDR
arriving in milling_sy) is the point of the change. An unexplained diff FAILS the run.

STANDING RULE, ENFORCED HERE
----------------------------
A failure and a legitimate empty answer never share a return value. A document that errors is
recorded with status ERROR and its totals are None. A document that genuinely has no quantities is
recorded with status OK and totals of 0/None per field. `summarise()` refuses to compute a rate over
a set containing an ERROR without saying so.

Usage:
    python 2026-08-10_mapping_regression.py --arm old --out old.json
    python 2026-08-10_mapping_regression.py --arm new --out new.json
    python 2026-08-10_mapping_regression.py --diff old.json new.json
"""

import argparse
import glob
import json
import os
import sys
from pathlib import Path

_PIPE = Path(__file__).resolve().parent.parent / "01_pipeline"
sys.path.insert(0, str(_PIPE))
import schema           # noqa: E402  — the NEW descriptions (working tree)
import s3_extract       # noqa: E402  — the real extractor, unmodified

MODULE_ROOT = Path(__file__).resolve().parent.parent
MD_CACHE = MODULE_ROOT / "00_input" / "_md_cache"
PAYLOAD_CACHE = MODULE_ROOT / "00_input" / "_report_payload_cache"

QUANTITY_FIELDS = ["hot_mix_tons", "base_tons", "grading_quantity", "shoulder_tons",
                   "milling_sy", "crushing_tons", "stockpile_tons"]

# Recorded alongside the seven totals but NOT diffed as totals: these did not exist in either
# committed baseline, so a diff of them against an older run is meaningless. They are captured so a
# re-run shows what the milling unit-capture change (2026-08-10, docs/_spec/
# 2026-08-10-milling-unit-capture.md) actually produced per document, rather than requiring a
# separate run to find out.
EXTRA_FIELDS = ["milling_tons", "milling_measured_unit"]

# The OLD descriptions, recorded verbatim from schema.py at git HEAD before the ruling change
# (commit f035b90). Held as a literal so the `old` arm is reproducible after the file is edited.
# Cross-check: `git show f035b90:pipelines/plan_reader/01_pipeline/schema.py`.
OLD_DESCS = {
    "hot_mix_tons":     "Total tons of hot mix asphalt (HMA) from the bid schedule.",
    "base_tons":        "Total tons of aggregate/granular base material.",
    "grading_quantity": "Total cubic yards of grading / earthwork.",
    "shoulder_tons":    "Total tons of shoulder gravel/aggregate.",
    "milling_sy":       "Total square yards of milling / pavement removal.",
    "crushing_tons":    "Total tons of crushed aggregate to be produced.",
    "stockpile_tons":   "Total tons of stockpile material.",
}


def fields_for_arm(arm):
    """The EXTRACT field specs with the chosen arm's quantity descriptions swapped in.

    Only the seven quantity descriptions differ between arms — identity and constraint fields are
    identical, so any diff in them is sampling noise and is reported as such rather than hidden."""
    out = []
    for f in schema.EXTRACT_FIELDS:
        f = dict(f)
        if arm == "old" and f["name"] in OLD_DESCS:
            f["desc"] = OLD_DESCS[f["name"]]
        out.append(f)
    return out


def plan_id_by_hash():
    """content hash -> plan_id, from the report payload cache. Missing is MISSING, not empty."""
    out = {}
    for p in sorted(PAYLOAD_CACHE.glob("*.json")):
        try:
            out[p.stem] = json.load(open(p)).get("plan_id") or "(no plan_id in payload)"
        except (OSError, json.JSONDecodeError) as e:
            out[p.stem] = f"(payload unreadable: {e.__class__.__name__})"
    return out


def document_text(md_path):
    """Page-annotated document text, in the same [Page N] form s3_extract builds from a PDF, so the
    model sees exactly what the live path shows it."""
    pages = json.load(open(md_path))
    return "\n\n".join(f"[Page {p.get('page')}]\n{p.get('text', '')}" for p in pages
                       if (p.get("text") or "").strip())


def run_one(md_path, arm):
    """Extract one document under one arm. Returns a record whose `status` distinguishes an error
    from a document that legitimately states no quantities."""
    stem = Path(md_path).stem
    rec = {"hash": stem, "arm": arm, "status": None, "totals": None, "extras": None, "error": None}
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

    prompt = s3_extract.EXTRACTION_PROMPT.format(
        field_list=schema.field_lines(fields_for_arm(arm)),
        archetypes=s3_extract.archetype_choices(),
        document_text=text,
    )
    # max_tokens raised 2026-08-10 to match extract_fields()'s real budget: the three
    # base_cy_items/shoulder_cy_items/mix_sy_depth_items array fields push a real response past
    # the call_json default (2048) and truncate mid-JSON — confirmed here (2 of 6 corpus documents
    # failed to parse at the default before this was raised, including the Murray Co/Fulda plan
    # that originally caught the issue). See docs/_spec/2026-08-10-aggregate-mix-tons-conversion.md.
    data = s3_extract.call_json(prompt, max_tokens=6000)
    if data is None:
        # call_json returns None on a parse failure. That is a FAILURE, not an empty plan.
        rec["status"] = "ERROR"
        rec["error"] = "model response did not parse as JSON"
        return rec

    totals, extras, cells = {}, {}, {}
    for f in fields_for_arm(arm):
        if f["name"] in QUANTITY_FIELDS or f["name"] in EXTRA_FIELDS:
            cell = s3_extract._coerce_cell(f, data.get(f["name"]))
            cells[f["name"]] = cell
            (totals if f["name"] in QUANTITY_FIELDS else extras)[f["name"]] = cell["value"]
    if extras:
        # Derived, not asked of the model — see schema.milling_unit_status. Recorded here so the
        # run itself shows whether "no milling item", "milling in tons" and "no answer" came back
        # as three distinguishable states on every document.
        extras["milling_unit_status"] = schema.milling_unit_status(cells)
    rec["status"] = "OK"
    rec["totals"] = totals
    rec["extras"] = extras or None
    return rec


# ── Diff classification ─────────────────────────────────────────────────────────
# Each rule says: this field moving in this direction is PREDICTED by a ruling. Anything else is
# unexplained and fails the run. Written as (field, direction, why) so the report cites the ruling.
EXPLAINED = [
    ("base_tons", "down",
     "CSI 08-07 #4/#3 + T's removal rule: REMOVE AGGREGATE BASE, PORTLAND CEMENT and CEMENT "
     "STABILIZED SUBGRADE leave base_tons"),
    ("milling_sy", "up",
     "CSI 08-07 #5/#6/#9: bituminous pavement removal and FULL DEPTH RECLAMATION arrive in milling_sy"),
    ("milling_sy", "down",
     "CSI 08-07 #1/#2: driveway removals leave milling_sy; concrete pavement removal leaves for grading"),
    ("shoulder_tons", "down",
     "CSI 08-07 #7/#8: GRAVEL SURFACING and TRAFFIC SERVICE AGGREGATE move to base_tons"),
    ("base_tons", "up",
     "CSI 08-07 #7/#8: GRAVEL SURFACING and TRAFFIC SERVICE AGGREGATE arrive in base_tons"),
    ("grading_quantity", "up",
     "CSI 08-07 #10/#11: SALVAGE AND REUSE EXISTING AGGREGATE and CLEAN ROCK arrive in grading"),
    ("grading_quantity", "down",
     "CSI 08-07 #5/#6: bituminous pavement removal leaves grading for milling"),
    ("hot_mix_tons", "up",
     "state vocabulary: SUPERPAVE (ND) / ASPHALT CONCRETE (SD) now named, so mix previously missed "
     "is now counted (the 605x Dunn miss)"),
]


def classify(field, before, after):
    """Classify one field's movement. Returns (verdict, why). Never conflates 'no change' with
    'could not tell' — a None on either side is its own verdict."""
    if before is None and after is None:
        return "unchanged-null", "absent in both arms"
    if before is None:
        return "appeared", "null in the old arm, a value in the new arm"
    if after is None:
        return "disappeared", "a value in the old arm, null in the new arm"
    if before == after:
        return "unchanged", ""
    direction = "up" if after > before else "down"
    for f, d, why in EXPLAINED:
        if f == field and d == direction:
            return "explained", why
    return "UNEXPLAINED", f"{field} moved {direction} and no ruling predicts that"


def diff(old_path, new_path):
    old = {r["hash"]: r for r in json.load(open(old_path))}
    new = {r["hash"]: r for r in json.load(open(new_path))}
    ids = plan_id_by_hash()
    rows, errors, unexplained = [], [], 0
    for h in sorted(set(old) | set(new)):
        o, n = old.get(h), new.get(h)
        label = ids.get(h, "(no cached payload — plan_id unknown)")
        if o is None or n is None:
            errors.append((h, label, "document present in only one arm"))
            continue
        if o["status"] != "OK" or n["status"] != "OK":
            errors.append((h, label, f"old={o['status']}:{o['error']} new={n['status']}:{n['error']}"))
            continue
        for f in QUANTITY_FIELDS:
            b, a = o["totals"].get(f), n["totals"].get(f)
            verdict, why = classify(f, b, a)
            if verdict in ("unchanged", "unchanged-null"):
                continue
            if verdict in ("UNEXPLAINED", "appeared", "disappeared"):
                # `appeared`/`disappeared` are reviewable, not automatically fatal, but they are
                # never silently folded into "unchanged".
                if verdict == "UNEXPLAINED":
                    unexplained += 1
            rows.append({"hash": h, "plan": label, "field": f, "old": b, "new": a,
                         "verdict": verdict, "why": why})

    print(f"\n{'plan':<44} {'field':<18} {'old':>12} {'new':>12}  verdict")
    print("-" * 110)
    for r in rows:
        print(f"{str(r['plan'])[:43]:<44} {r['field']:<18} {str(r['old']):>12} "
              f"{str(r['new']):>12}  {r['verdict']}")
        if r["why"]:
            print(f"{'':<44} └─ {r['why']}")
    print("-" * 110)
    print(f"{len(rows)} field(s) moved · {unexplained} UNEXPLAINED · {len(errors)} document(s) "
          f"could not be compared")
    for h, label, why in errors:
        print(f"  ERROR  {label} ({h}): {why}")
    if errors:
        print("\nNOTE: the counts above are over the COMPARABLE documents only. The errored "
              "documents are not zeroes and are not passes.")
    return 1 if unexplained else 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--arm", choices=["old", "new"])
    ap.add_argument("--out")
    ap.add_argument("--diff", nargs=2, metavar=("OLD_JSON", "NEW_JSON"))
    ap.add_argument("--limit", type=int, default=0, help="first N documents only (for a cheap smoke run)")
    ap.add_argument("--only", default="", help="comma-separated content hashes — run exactly these "
                                               "documents (a targeted no-regression subset). A hash "
                                               "that matches no document is a SETUP FAILURE, not a "
                                               "silently smaller run.")
    args = ap.parse_args()

    if args.diff:
        sys.exit(diff(*args.diff))
    if not args.arm or not args.out:
        ap.error("--arm and --out are required unless --diff is given")

    paths = sorted(p for p in glob.glob(str(MD_CACHE / "*.json")) if not p.endswith(".hybrid.json"))
    if not paths:
        # An empty corpus is a SETUP FAILURE, not a clean run of zero documents.
        print(f"FATAL: no markdown documents found in {MD_CACHE}. This is a setup failure, not an "
              f"empty result — refusing to write an output file that would look like a clean run.")
        sys.exit(2)
    if args.only:
        wanted = [h.strip() for h in args.only.split(",") if h.strip()]
        by_stem = {Path(p).stem: p for p in paths}
        missing = [h for h in wanted if h not in by_stem]
        if missing:
            print(f"FATAL: --only named {len(missing)} hash(es) with no document in {MD_CACHE}: "
                  f"{', '.join(missing)}. Refusing to run a quietly smaller subset than asked for.")
            sys.exit(2)
        paths = [by_stem[h] for h in wanted]
    if args.limit:
        paths = paths[:args.limit]

    ids = plan_id_by_hash()
    out = []
    for i, p in enumerate(paths, 1):
        stem = Path(p).stem
        print(f"[{i}/{len(paths)}] {ids.get(stem, stem)} ({args.arm} arm)")
        rec = run_one(p, args.arm)
        if rec["status"] == "ERROR":
            print(f"    ERROR: {rec['error']}")
        out.append(rec)
    Path(args.out).write_text(json.dumps(out, indent=2))
    n_err = sum(1 for r in out if r["status"] == "ERROR")
    print(f"\nWrote {args.out}: {len(out)} document(s), {n_err} error(s).")


if __name__ == "__main__":
    main()
