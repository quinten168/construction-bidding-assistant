"""
2026-08-11_alex_conformance_behavior.py — layer 2 of the Alex conformance audit:
does each of CSI's (Alex's) rulings actually FIRE on the LIVE path?

Layer 1 (a parallel agent) owns whether a ruling is ENCODED in the prose. This file owns whether
the shipped extractor, on a real corpus document, actually puts the material where Alex said.

TWO STEPS, CHEAP ONE FIRST
--------------------------
  --inventory   Scan 00_input/_md_cache/*.json (page-level markdown of the already-converted
                corpus plans; *.hybrid.json skipped) for every material named in a ruling, and
                report which plans carry a matching bid-schedule line, verbatim, with its page.
                Costs nothing. A ruling whose material appears on NO cached plan is
                `untested-no-plan` — a legitimate result, not a gap to be papered over with a
                synthetic fixture.

                This doubles as a COVERAGE test: --inventory exits non-zero if a material that
                the report claims was measured matched zero corpus lines.

  --measure     For the plans the inventory pointed at, rebuild the LIVE PATH's extractor input
                (lib.detect_structure -> s1_convert.convert_pages -> pages_to_markdown restricted
                to structure["proposal_pages"] -> s3_extract.smart_truncate), hash it, and call
                the extractor N times on that identical string.

WHY THE LIVE-PATH INPUT AND NOT THE WHOLE DOCUMENT
--------------------------------------------------
report.py::process_pdf sends only the proposal pages. A harness that feeds every page measures a
different prompt than the one that ships — that mistake already produced a wrong conclusion on this
project. build_input() is imported from 2026-08-10_nondeterminism_measurement.py rather than
re-implemented, so both harnesses construct the input through one chain.

process_pdf is NEVER called (it re-ingests Chroma). Chroma is touched zero times.

STANDING RULE, ENFORCED
-----------------------
A failure and a legitimate empty answer never share a value. An unparseable model response is
status=ERROR with values=None, excluded from every distribution and counted out loud. It is never
recorded as "the ruling did not fire".

THREE OUTCOMES, NEVER TWO
-------------------------
For each ruling this records, per run:
    FIRES          the material's quantity is in Alex's target bucket
    MISPLACED      it is in some OTHER bucket (which one is named)
    DROPPED        it is in no bucket at all  <- the silent-failure case, the one that matters
The classifier works on the numeric quantity printed on the matched corpus line, so "left the old
bucket but never arrived in the new one" is distinguishable from "never moved".

Usage:
    python 2026-08-11_alex_conformance_behavior.py --inventory
    python 2026-08-11_alex_conformance_behavior.py --measure --plan 9786015 --n 10
    python 2026-08-11_alex_conformance_behavior.py --report outputs/....json
"""

from __future__ import annotations

import argparse
import concurrent.futures as futures
import importlib.util
import json
import re
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
_PIPE = REPO / "pipelines" / "plan_reader" / "01_pipeline"
sys.path.insert(0, str(_PIPE))

import corpus_match  # noqa: E402
import schema        # noqa: E402
import s3_extract    # noqa: E402

MD_CACHE = HERE.parent / "00_input" / "_md_cache"
PAYLOAD_CACHE = HERE.parent / "00_input" / "_report_payload_cache"

QUANTITY_FIELDS = ["hot_mix_tons", "base_tons", "grading_quantity", "shoulder_tons",
                   "milling_sy", "crushing_tons", "stockpile_tons"]
COMPANION_FIELDS = ["milling_tons", "milling_measured_unit",
                    "base_measured_unit", "base_unconverted",
                    "shoulder_measured_unit", "shoulder_unconverted",
                    "hot_mix_measured_unit", "hot_mix_unconverted",
                    # 2026-08-11: grading's off-unit capture. CLEAN ROCK is Alex's grading pick and
                    # Dunn prices it in TONS, so grading_quantity alone cannot show whether the
                    # ruling fired. docs/_spec/2026-08-11-grading-unit-capture.md.
                    "grading_measured_unit", "grading_unconverted"]


def _load_nondet():
    """Import the 2026-08-10 harness by path — its filename is not an importable identifier."""
    spec = importlib.util.spec_from_file_location(
        "nondet", HERE / "2026-08-10_nondeterminism_measurement.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ── The rulings under test ──────────────────────────────────────────────────────
# `target` is ALEX's answer. `kind`:
#   move        material must land in `target`
#   exclude     material must land in NO bucket (target None)
#   assign      an unassigned pick / split — the bucket the schema now claims
RULINGS = [
    # -- moves -------------------------------------------------------------------
    # 2026-08-11: TARGET REVERSED. Alex's returned .docx ticks `Move to __base____`, so the
    # QUANTITY moves to base — and since FDR is SY and base_tons is TON, its home is the off-unit
    # capture field `base_unconverted`, verbatim and unconverted. Until 2026-08-10 this measured
    # against milling_sy; that arm's numbers are still in outputs/2026-08-11_alex_behavior_*.json
    # and are the BEFORE half of the conformance report.
    dict(id="R-FDR", phrase="FULL DEPTH RECLAMATION", target="base_unconverted",
         kind="move", note="Alex: FDR's quantity is BASE. Measured in SY, so it is reported in "
                           "base_unconverted (never converted to tons; depth is stated on 1 of 15 "
                           "corpus FDR rows)."),
    dict(id="R-GRAVSURF", phrase="GRAVEL SURFACING", target="base_tons", kind="move",
         note="shoulder -> base"),
    dict(id="R-TSA", phrase="TRAFFIC SERVICE AGGREGATE", target="base_tons", kind="move",
         note="shoulder -> base. KNOWN not to fire on Dunn (820 T stayed out of base_tons)."),
    dict(id="R-RBP", phrase="REMOVE BITUMINOUS PAVEMENT", target="milling_sy", kind="move",
         note="grading -> mill"),
    dict(id="R-ROBS", phrase="REMOVAL OF BITUMINOUS SURFACING", target="milling_sy", kind="move",
         note="grading -> mill"),
    # -- do not count ------------------------------------------------------------
    dict(id="X-PC", phrase="PORTLAND CEMENT", target=None, kind="exclude"),
    dict(id="X-CSS", phrase="CEMENT STABILIZED SUBGRADE", target=None, kind="exclude"),
    dict(id="X-RCDP", phrase="REMOVE CONCRETE DRIVEWAY PAVEMENT", target=None, kind="exclude"),
    dict(id="X-RBDP", phrase="REMOVE BITUMINOUS DRIVEWAY PAVEMENT", target=None, kind="exclude"),
    dict(id="X-RDP", phrase="REMOVE DRIVEWAY PAVEMENT", target=None, kind="exclude",
         note="the un-qualified spelling the demo plan uses; Alex ruled on the concrete and "
              "bituminous spellings, this is the same exclusion under the corpus's own name"),
    # -- the CL 13 split (agreed as proposed; confirm no drift) -------------------
    dict(id="C-SURF13", phrase="AGGREGATE SURFACE COURSE CL 13", target="shoulder_tons",
         kind="assign", note="CL 13 split, surface half"),
    dict(id="C-BASE13", phrase="AGGREGATE BASE CL 13", target="base_tons",
         kind="assign", note="CL 13 split, base half"),
    # -- unassigned picks --------------------------------------------------------
    dict(id="U-SALV", phrase="SALVAGE AND REUSE EXISTING AGGREGATE", target="grading_quantity",
         kind="assign"),
    # Alex assigned grading; Dunn prices it in TON and grading_quantity is CY, so the honest
    # target after 2026-08-11 is the off-unit capture, not the CY total. 0/13 before.
    dict(id="U-CLEANROCK", phrase="CLEAN ROCK", target="grading_unconverted", kind="assign"),
    dict(id="P-SALVBASE", phrase="SALVAGED BASE COURSE", target="base_tons", kind="assign",
         note="Alex ticked Agree on BA5 Salvaged Base Course -> base_tons (P3)."),
    dict(id="P-TOPSOIL", phrase="TOPSOIL", target="grading_quantity", kind="assign",
         note="Alex ticked Agree on all five topsoil rows, each printed 'NEW, not counted today' "
              "(P2). ~539,000 CY corpus-wide, the largest quantity in the audit."),
    dict(id="P-BINDER", phrase="ASPHALT CEMENT", target=None, kind="exclude",
         note="Alex: 'Agree, flag only' on binder & coatings (P1). A DELIBERATE EXCLUSION, which "
              "is a different fact from a reader failure."),
    dict(id="U-GRANBED", phrase="GRANULAR BEDDING", target="grading_quantity", kind="assign"),
    dict(id="U-FDBSR", phrase="FULL DEPTH BITUMINOUS STREET REPAIR", target="hot_mix_tons",
         kind="assign"),
]

# Extra spellings the corpus is known to use for the same pay item. Recorded separately so a hit on
# an alias is never silently reported as a hit on the ruling's own phrase.
ALIASES = {
    "R-FDR": ["FDR", "STABILIZED FULL DEPTH RECLAMATION", "BITUMINOUS PAVEMENT RECLAMATION",
              "RECLAIM", "FULL DEPTH RECLAIM"],
    "C-BASE13": ["AGGREGATE BASE COURSE CL 13", "AGGREGATE BASE CLASS 13"],
    "R-ROBS": ["REMOVAL OF BITUMINOUS", "REMOVE BITUMINOUS SURFACING"],
    "R-GRAVSURF": ["GRAVEL SURFACE"],
}


# The denoising matcher this harness discovered the need for (15 characters of converter markup
# between CONCRETE and DRIVEWAY on Stearns p77 made a priced 44 SY bid item look absent) was
# promoted on 2026-08-11 into 01_pipeline/corpus_match.py and adopted by
# 01_pipeline/test_material_vocabulary_coverage.py, which had the same defect. ONE matcher, not
# three — a second copy is how the first one stayed wrong.
_denoise = corpus_match.denoise
_pat = corpus_match.phrase_pattern


def plan_names() -> dict:
    """content hash -> plan_id. Missing is stated as missing, never blanked."""
    out = {}
    for p in sorted(PAYLOAD_CACHE.glob("*.json")):
        try:
            out[p.stem] = json.loads(p.read_text()).get("plan_id") or "(no plan_id)"
        except (OSError, json.JSONDecodeError) as e:
            out[p.stem] = f"(payload unreadable: {type(e).__name__})"
    return out


def corpus_lines():
    """(file, page, line) for every non-blank cached line. A cache file that will not parse RAISES
    — a shrunken corpus must not look like a clean negative."""
    files = [p for p in sorted(MD_CACHE.glob("*.json")) if not p.name.endswith(".hybrid.json")]
    if not files:
        raise SystemExit("no non-hybrid md_cache files — cannot run the inventory")
    out = []
    for p in files:
        for pg in json.loads(p.read_text()):
            for line in (pg.get("md") or pg.get("text") or "").splitlines():
                line = line.strip()
                if line:
                    out.append((p.stem, pg.get("page"), line))
    return out, [p.stem for p in files]


_NUM = re.compile(r"(\d[\d,]*(?:\.\d+)?)")
_UNIT = re.compile(r"\b(S\s?Y|SQ\s?\s?YD|TON|C\s?Y|CU\s?YD|LSUM|L\s?F|EACH|EA)\b", re.I)


def _is_pay_item(line: str) -> bool:
    """Does this line look like a BID-SCHEDULE ROW (a pay item with a unit and a quantity), as
    opposed to a mention of the same words in specification prose?

    This distinction is the whole point of the inventory. 'GRAVEL SURFACING' appears on six plans,
    but on every one of them it is prose ('provide a temporary gravel surface') — no bid schedule
    in the cached corpus prices it as an item, so there is nothing for the ruling to move and the
    honest verdict is untested-no-plan, not does-not-fire.

    Deliberately conservative: it requires a unit token AND a quantity >= 1 on the same line. A
    heuristic that over-called pay items would manufacture tests; one that under-calls them only
    costs coverage, which is then visible as untested-no-plan.
    """
    if not _UNIT.search(line):
        return False
    nums = [v for v in _quantities_on(line)]
    if not nums:
        return False
    # A spec-prose sentence rarely reaches a table pipe or a leading item number followed by a
    # spec code; a bid row almost always does one of the two.
    return ("|" in line) or bool(re.match(r"^\s*\d+\s+[\d.]{3,}\s", line))


def _quantities_on(line: str):
    """Plausible pay quantities printed on a matched bid line, largest first.

    Deliberately loose: it returns candidates, and the caller only ever uses them to ASK whether an
    extracted bucket total contains one. It is never used to assert a total is correct.
    """
    vals = []
    for m in _NUM.finditer(line):
        try:
            v = float(m.group(1).replace(",", ""))
        except ValueError:
            continue
        if v >= 1:
            vals.append(v)
    return sorted(set(vals), reverse=True)


def inventory(verbose=True):
    lines, files = corpus_lines()
    names = plan_names()
    inv = {}
    for r in RULINGS:
        pats = [(r["phrase"], _pat(r["phrase"]))]
        pats += [(a, _pat(a)) for a in ALIASES.get(r["id"], [])]
        hits = []
        for f, pg, ln in lines:
            clean = _denoise(ln)
            for label, pat in pats:
                if pat.search(clean):
                    hits.append({"hash": f, "plan": names.get(f, "(not in payload cache)"),
                                 "page": pg, "line": ln[:400],
                                 "matched": label,
                                 "exact_phrase": label == r["phrase"],
                                 "pay_item": _is_pay_item(ln),
                                 "quantities": _quantities_on(ln)[:4]})
                    break
        by_plan = {}
        for h in hits:
            by_plan.setdefault(h["hash"], []).append(h)
        pay_plans = sorted({h["hash"] for h in hits if h["pay_item"]})
        inv[r["id"]] = {"ruling": r, "n_hits": len(hits),
                        "plans": sorted(by_plan), "by_plan": by_plan,
                        "pay_item_plans": pay_plans,
                        "n_pay_item_lines": sum(1 for h in hits if h["pay_item"]),
                        "exact_hits": sum(1 for h in hits if h["exact_phrase"])}
    if verbose:
        print(f"corpus: {len(files)} cached plans, {len(lines):,} non-blank lines\n")
        for rid, rec in inv.items():
            r = rec["ruling"]
            print(f"=== {rid}  {r['phrase']!r} -> "
                  f"{r['target'] or 'NO BUCKET (exclude)'}  [{r['kind']}]")
            if not rec["n_hits"]:
                print("    UNTESTED-NO-PLAN — matches zero corpus lines "
                      "(including aliases). Not a failure; no plan carries it.\n")
                continue
            print(f"    {rec['n_hits']} line(s) on {len(rec['plans'])} plan(s) "
                  f"({rec['exact_hits']} on the ruling's exact phrase); "
                  f"{rec['n_pay_item_lines']} look like BID-SCHEDULE ROWS on "
                  f"{len(rec['pay_item_plans'])} plan(s)")
            if not rec["pay_item_plans"]:
                print("    UNTESTED-NO-PLAN (as a pay item) — the words appear only in "
                      "specification prose. Nothing for the ruling to move.")
            for h_hash in rec["pay_item_plans"] or rec["plans"]:
                hs = [h for h in rec["by_plan"][h_hash] if h["pay_item"]] or rec["by_plan"][h_hash]
                print(f"    - {hs[0]['plan']}  ({h_hash[:12]})  {len(hs)} line(s)")
                for h in hs[:3]:
                    tag = "PAY ITEM" if h["pay_item"] else "prose"
                    print(f"        p{h['page']} [{tag}/{h['matched']}] {h['line'][:170]}")
            print()
    return inv


# ── Measurement ─────────────────────────────────────────────────────────────────

def one_run(text: str, idx: int) -> dict:
    rec = {"run": idx, "status": None, "values": None, "reasons": None, "error": None}
    prompt = s3_extract.EXTRACTION_PROMPT.format(
        field_list=schema.extract_prompt_fields(),
        archetypes=s3_extract.archetype_choices(),
        document_text=text,
    )
    try:
        data = s3_extract.call_json(prompt, max_tokens=s3_extract.EXTRACT_MAX_TOKENS)
    except Exception as e:                                   # noqa: BLE001
        rec["status"] = "ERROR"
        rec["error"] = f"API call raised {type(e).__name__}: {e}"
        return rec
    if data is None or not isinstance(data, dict):
        rec["status"] = "ERROR"
        rec["error"] = "model response did not parse as a JSON object (truncation or malformed)"
        return rec
    by_name = {f["name"]: f for f in schema.EXTRACT_FIELDS}
    values, reasons = {}, {}
    for name in QUANTITY_FIELDS + COMPANION_FIELDS:
        f = by_name.get(name)
        if f is None:
            rec["status"] = "ERROR"
            rec["error"] = f"{name!r} not in schema.EXTRACT_FIELDS — harness is out of date"
            return rec
        cell = s3_extract._coerce_cell(f, data.get(name))
        values[name] = cell["value"]
        raw = data.get(name)
        if isinstance(raw, dict):
            for k in ("reason", "why", "source", "evidence", "note"):
                if raw.get(k):
                    reasons[name] = str(raw[k])[:600]
                    break
    rec["status"] = "OK"
    rec["values"] = values
    rec["reasons"] = reasons
    # The model's RAW cell for each of the seven, kept verbatim. This is the third independent
    # method behind a does-not-fire claim: on Dunn the raw cell's own `reason` string concludes
    # "6,506 + 820 = 7,326" while its `value` says 6506. Value and reason disagreeing inside ONE
    # response object is a different failure from the model never seeing the item, and only the
    # raw cell can tell them apart.
    rec["raw_quantity_cells"] = {n: data.get(n) for n in QUANTITY_FIELDS}
    return rec


def measure(plan_label, pdf_path, n, workers, out_path):
    nd = _load_nondet()
    built = nd.build_input(Path(pdf_path))
    if built["status"] != "OK":
        print(f"BUILD_ERROR: {built['error']}")
        blob = {"plan": plan_label, "input": {k: v for k, v in built.items() if k != "text"},
                "n": n, "runs": []}
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(blob, indent=2))
        return 1
    print(f"{plan_label}: {built['doc_type']}, {built['n_pages']}p, "
          f"proposal {built['proposal_ranges']}, {built['chars_sent']:,} chars sent"
          f"{' (TRUNCATED)' if built['truncated'] else ''}, sha256 {built['input_sha256'][:16]}")
    text = built["text"]
    runs = [None] * n
    with futures.ThreadPoolExecutor(max_workers=workers) as ex:
        fut = {ex.submit(one_run, text, i): i for i in range(n)}
        for f in futures.as_completed(fut):
            i = fut[f]
            try:
                runs[i] = f.result()
            except Exception as e:                            # noqa: BLE001
                runs[i] = {"run": i, "status": "ERROR", "values": None, "reasons": None,
                           "error": f"worker raised {type(e).__name__}: {e}"}
    n_err = sum(1 for r in runs if r["status"] != "OK")
    print(f"  {n - n_err}/{n} runs OK" + (f", {n_err} ERROR (excluded, not nulls)" if n_err else ""))
    for r in runs:
        if r["status"] != "OK":
            print(f"    run {r['run']}: {r['error']}")
    blob = {"plan": plan_label, "pdf": str(pdf_path),
            "input": {k: v for k, v in built.items() if k != "text"},
            "n": n, "runs": runs,
            "field_set": {"n_extract_fields": len(schema.EXTRACT_FIELDS),
                          "model": s3_extract.MODEL, "max_chars": s3_extract.MAX_CHARS}}
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(blob, indent=2))
    print(f"  wrote {out_path}")
    return 0


def report(paths):
    """Print, per plan, every bucket's distribution plus the model's stated reason strings.

    Classification into FIRES / MISPLACED / DROPPED is done by the analyst against the inventory's
    printed quantity for the material on that plan — this prints the evidence for that call rather
    than guessing which of several line items a total is made of.
    """
    for path in paths:
        blob = json.loads(Path(path).read_text())
        ok = [r for r in blob["runs"] if r["status"] == "OK"]
        err = [r for r in blob["runs"] if r["status"] != "OK"]
        print("=" * 100)
        print(f"{blob['plan']}   N={blob['n']}   {len(ok)} OK, {len(err)} ERROR")
        if not ok:
            print("  no OK runs — nothing can be concluded about firing from this arm\n")
            continue
        for name in QUANTITY_FIELDS + ["--"] + COMPANION_FIELDS:
            if name == "--":
                print("  " + "-" * 90)
                continue
            vals = ["null" if r["values"][name] is None else r["values"][name] for r in ok]
            c = Counter(map(str, vals))
            print(f"  {name:<24} " + ", ".join(f"{k}×{v}" for k, v in c.most_common()))
        print("\n  model-stated reasons (first OK run):")
        for k, v in (ok[0].get("reasons") or {}).items():
            print(f"    {k}: {v}")
        print()
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--inventory", action="store_true")
    ap.add_argument("--measure", action="store_true")
    ap.add_argument("--label", default="plan")
    ap.add_argument("--pdf")
    ap.add_argument("--n", type=int, default=10)
    ap.add_argument("--workers", type=int, default=5)
    ap.add_argument("--out", default="outputs/2026-08-11_alex_behavior.json")
    ap.add_argument("--report", nargs="*")
    args = ap.parse_args()
    if args.inventory:
        inv = inventory()
        missing = [rid for rid, rec in inv.items() if not rec["n_hits"]]
        print(f"UNTESTED-NO-PLAN ({len(missing)}): {', '.join(missing) or 'none'}")
        (HERE / "outputs").mkdir(parents=True, exist_ok=True)
        (HERE / "outputs" / "2026-08-11_alex_inventory.json").write_text(
            json.dumps({rid: {k: v for k, v in rec.items() if k != "by_plan"} | {"by_plan": rec["by_plan"]}
                        for rid, rec in inv.items()}, indent=2))
        return 0
    if args.report:
        return report(args.report)
    if args.measure:
        out = Path(args.out) if Path(args.out).is_absolute() else HERE / args.out
        return measure(args.label, args.pdf, args.n, args.workers, out)
    ap.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
