"""
2026-08-10_nondeterminism_measurement.py — how reproducible is the live material mapping?

WHY THIS EXISTS
---------------
The live PDF-drop path's material mapping IS the seven quantity field descriptions in
01_pipeline/schema.py — a prompt, interpreted by a model at temperature=0. On 2026-08-10 a re-warm
of 14 cached plans moved 12 field values on the same documents. Some of those moves are CSI's
2026-08-07 rulings firing (the point of the change). Some may be sampling noise. Nothing in the
repo currently distinguishes them, because the re-warm produced N=1 per plan.

This script produces the missing denominator: N runs of the SAME extractor over the SAME input
string, so the only thing that can vary is the model.

WHAT IT HOLDS CONSTANT, AND WHY THAT IS THE WHOLE POINT
-------------------------------------------------------
report.py::process_pdf does NOT send the whole document to the extractor. It sends

    convert.pages_to_markdown([p for p in md_pages if p["page"] in structure["proposal_pages"]])

then extract.smart_truncate(..., MAX_CHARS). A harness that feeds every page (including the
tabloid map pages) is measuring a different prompt than the one that shipped, and will report
different numbers. So the input here is built ONCE per plan through exactly that chain, hashed,
and reused verbatim for all N runs. The build is logged with the hash and character count so a
reader can confirm the arm was constant.

Chroma is touched ZERO times. process_pdf is never called — it re-ingests, and a teammate is live
on that collection. This calls the extractor only.

STANDING RULE, ENFORCED HERE
----------------------------
A failure and a legitimate empty answer never share a return value. s3_extract.extract_fields()
turns a failed/unparseable model response into a full record of clean null cells — indistinguishable
from "this plan states no quantities". Recording that as a null in a distribution would corrupt the
very measurement being made, so this script does NOT call extract_fields(). It rebuilds the same
prompt from schema.extract_prompt_fields(), calls s3_extract.call_json() directly, and records:

    status = "OK"     -> the model answered and the answer parsed; per-field null means null
    status = "ERROR"  -> parse failure, truncation at the token cap, or an API exception.
                         `values` is None, not a dict of nulls. Excluded from every distribution,
                         and counted out loud in the report.

Coercion of a parsed answer reuses s3_extract._coerce_cell, so a value here is the same value the
live path would have written.

Usage:
    python 2026-08-10_nondeterminism_measurement.py --n 10 --out outputs/2026-08-10_nondet.json
    python 2026-08-10_nondeterminism_measurement.py --report outputs/2026-08-10_nondet.json
"""

import argparse
import concurrent.futures as futures
import hashlib
import json
import statistics
import subprocess
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
_PIPE = REPO / "pipelines" / "plan_reader" / "01_pipeline"
sys.path.insert(0, str(_PIPE))

import lib          # noqa: E402  — detect_structure
import s1_convert as convert   # noqa: E402
import s3_extract   # noqa: E402
import schema       # noqa: E402

CORPUS = Path("/Users/t/Library/Mobile Documents/com~apple~CloudDocs/00 MSBA + Coding/"
              "00_summer 2026/00_CSI_ELP/CSI ELP 2026")

# The five plans named in the measurement task. Each is one of the documents whose values moved in
# the 2026-08-10 re-warm (or, for Dunn, the demo plan whose GRADE moved).
PLANS = [
    ("Stearns 9813645 (MN)",
     CORPUS / "2025 Bid year (9.1.24-8.31.25) - CURRENT" / "12 - AUGUST" / "Plans Proposals"
            / "08.28.25 STEARNS CO MN CP 073-123-025 (CR 123) PAVEMENT RESURFACING AND REHAB"
            / "9813645.pdf"),
    ("Crow Wing SAP 018-603-024 (MN)",
     CORPUS / "2023 Bid year (8.1.22-7.31.23)" / "7 February 2023" / "Plans Proposals"
            / "02.22.23 CROW WING CO MN - SAP 018-603-024 & SAP 018-611-029 CSAH 3 & CSAH 11 ROUNDABOUT"
            / "Proposal SAP 018-603-024  SAP 018-611-029.pdf"),
    ("Dunn Job 23388 (ND)",
     CORPUS / "2026 JOBS" / "26051 DUNN COUNTY ND (ND 200)" / "Job 23388 Request for Proposal.pdf"),
    ("8428114 Burleigh (ND)",
     CORPUS / "2023 Bid year (8.1.22-7.31.23)" / "9 April 2023" / "Plans Proposals"
            / "04.21.23 BURLEIGH CO ND - ND GAME AND FISH DEPARTMENT HEADQUARTERS PARKING LOT REPLACEMENT"
            / "8428114.pdf"),
    ("9809481 Clay/Moorhead (MN)",
     CORPUS / "2025 Bid year (9.1.24-8.31.25) - CURRENT" / "12 - AUGUST" / "Plans Proposals"
            / "08.20.25 CLAY CO MN, MOORHEAD PROJ 25-A6-03 PARTRIDGE CREEK 1ST ADD UNDERGOUNG UT IMPS"
            / "9809481.pdf"),
]

# EXTENSION SET. The five plans above are the ones the measurement task named. These three carry the
# remaining rows of the 12-move table, and without them five of those twelve rows could only be
# answered "cannot tell". Two of them are the sub-percent moves the task asks about specifically
# (8435627 MIX 1,586 -> 1,588; 8416165 MILL 193,207 -> 192,521) and one is the clean-looking bucket
# move (Job 24133 BASE 170 -> SHLDR 170). Run with --set extension.
EXTENSION_PLANS = [
    ("8416165 Cass (ND)",
     CORPUS / "2023 Bid year (8.1.22-7.31.23)" / "8 March 2023" / "Plans Proposals"
            / "03.29.23 CASS CO ND - PR-23-E1 ASPHALT AND MILL OVERLAY" / "8416165.pdf"),
    ("8435627 Emmons/Linton airport (ND)",
     CORPUS / "2023 Bid year (8.1.22-7.31.23)" / "9 April 2023" / "Plans Proposals"
            / "04.27.23 EMMONS, ND - KLJ#2105-01702 LINTON AIRPORT APRON REPLACEMENT" / "8435627.pdf"),
    ("Job 24133 Morton (ND)",
     CORPUS / "2025 Bid year (9.1.24-8.31.25) - CURRENT" / "12 - AUGUST" / "Plans Proposals"
            / "08.15.25 MORTON CO ND JOB 24133 (ND 1806) SS-1-806(058)057 FIELD APPROACH"
            / "Job 24133 Request for Proposal.pdf"),
]

# The seven quantity fields — the shipped material mapping. Reported whether or not they moved:
# a field that is stable across N runs is an equally important result.
QUANTITY_FIELDS = ["hot_mix_tons", "base_tons", "grading_quantity", "shoulder_tons",
                   "milling_sy", "crushing_tons", "stockpile_tons"]

# The 2026-08-10 unit-capture companions. Recorded because they are part of the SHIPPED field set
# (they change the prompt and the response length), and because milling_tons carries real quantity
# on ND plans. Reported separately from the seven so the two are never conflated.
COMPANION_FIELDS = ["milling_tons", "milling_measured_unit",
                    "hot_mix_measured_unit", "hot_mix_unconverted",
                    "base_measured_unit", "base_unconverted",
                    "shoulder_measured_unit", "shoulder_unconverted"]

REPORT_LABEL = {"hot_mix_tons": "MIX", "base_tons": "BASE", "grading_quantity": "GRADE",
                "shoulder_tons": "SHLDR", "milling_sy": "MILL", "crushing_tons": "CRUSH",
                "stockpile_tons": "STOCK"}


def build_input(pdf_path: Path) -> dict:
    """Reproduce report.py::process_pdf's extractor input EXACTLY, once.

    Returns a dict with the text plus the evidence that it is the live-path input: the structure
    classification, the proposal page ranges, pre- and post-truncation lengths, and a sha256 of the
    final string. A caller that cannot build the input gets status BUILD_ERROR — never an empty
    string that would run N extractions over nothing.
    """
    rec = {"pdf": str(pdf_path), "status": None, "text": None, "error": None}
    if not pdf_path.exists():
        rec["status"] = "BUILD_ERROR"
        rec["error"] = f"PDF not found: {pdf_path}"
        return rec
    try:
        structure = lib.detect_structure(pdf_path)
        if structure["type"] == "plan_set":
            rec["status"] = "BUILD_ERROR"
            rec["error"] = "detect_structure says plan_set — the live path refuses this PDF"
            return rec
        md_pages = convert.convert_pages(pdf_path)
        prop = set(structure["proposal_pages"])
        proposal_md = convert.pages_to_markdown([p for p in md_pages if p["page"] in prop])
        text = s3_extract.smart_truncate(proposal_md, s3_extract.MAX_CHARS)
    except Exception as e:                                    # noqa: BLE001
        rec["status"] = "BUILD_ERROR"
        rec["error"] = f"{type(e).__name__}: {e}"
        return rec
    if len(text) < 100:
        rec["status"] = "BUILD_ERROR"
        rec["error"] = f"extractor input is only {len(text)} chars — not a usable document"
        return rec
    rec.update({
        "status": "OK", "text": text,
        "doc_type": structure["type"], "n_pages": structure["n_pages"],
        "proposal_ranges": structure["proposal_ranges"], "map_ranges": structure["map_ranges"],
        "n_proposal_pages": len(structure["proposal_pages"]),
        "chars_before_truncate": len(proposal_md), "chars_sent": len(text),
        "truncated": len(proposal_md) > s3_extract.MAX_CHARS,
        "input_sha256": hashlib.sha256(text.encode()).hexdigest(),
    })
    return rec


def one_run(text: str, run_idx: int) -> dict:
    """One extraction over the held-constant input. Never conflates failure with an empty plan."""
    rec = {"run": run_idx, "status": None, "values": None, "confidence": None, "error": None}
    prompt = s3_extract.EXTRACTION_PROMPT.format(
        field_list=schema.extract_prompt_fields(),
        archetypes=s3_extract.archetype_choices(),
        document_text=text,
    )
    try:
        data = s3_extract.call_json(prompt, max_tokens=s3_extract.EXTRACT_MAX_TOKENS)
    except Exception as e:                                    # noqa: BLE001 — API/network/overload
        rec["status"] = "ERROR"
        rec["error"] = f"API call raised {type(e).__name__}: {e}"
        return rec
    if data is None:
        # call_json prints WHICH cause (max_tokens truncation vs malformed JSON) and returns None
        # for both. Either way it is a FAILURE, not a plan with no quantities.
        rec["status"] = "ERROR"
        rec["error"] = "model response did not parse (truncation at the token cap, or malformed JSON)"
        return rec
    if not isinstance(data, dict):
        rec["status"] = "ERROR"
        rec["error"] = f"model returned a {type(data).__name__}, not a JSON object"
        return rec
    values, conf = {}, {}
    by_name = {f["name"]: f for f in schema.EXTRACT_FIELDS}
    for name in QUANTITY_FIELDS + COMPANION_FIELDS:
        f = by_name.get(name)
        if f is None:
            # A field named here that is not in the shipped schema is a SETUP error, not a null.
            rec["status"] = "ERROR"
            rec["error"] = f"field {name!r} is not in schema.EXTRACT_FIELDS — harness is out of date"
            return rec
        cell = s3_extract._coerce_cell(f, data.get(name))
        values[name] = cell["value"]
        conf[name] = cell["confidence"] or None
    rec["status"] = "OK"
    rec["values"] = values
    rec["confidence"] = conf
    return rec


def measure(n: int, out_path: Path, workers: int, plans) -> int:
    field_set = {
        "commit": subprocess.run(["git", "-C", str(REPO), "rev-parse", "HEAD"],
                                 capture_output=True, text=True).stdout.strip(),
        "dirty": bool(subprocess.run(["git", "-C", str(REPO), "status", "--porcelain",
                                      "pipelines/plan_reader/01_pipeline/schema.py"],
                                     capture_output=True, text=True).stdout.strip()),
        "n_extract_fields": len(schema.EXTRACT_FIELDS),
        "extract_field_names": [f["name"] for f in schema.EXTRACT_FIELDS],
        "model": s3_extract.MODEL,
        "max_chars": s3_extract.MAX_CHARS,
        "extract_max_tokens": s3_extract.EXTRACT_MAX_TOKENS,
    }
    print(f"field set: commit {field_set['commit'][:8]}"
          f"{' (schema.py DIRTY)' if field_set['dirty'] else ''}, "
          f"{field_set['n_extract_fields']} extract fields, model {field_set['model']}")
    print("includes the 2026-08-10 tons-bucket additions: "
          f"{'YES' if 'base_unconverted' in field_set['extract_field_names'] else 'NO'}\n")

    results = []
    for label, pdf in plans:
        print(f"=== {label}")
        built = build_input(pdf)
        if built["status"] != "OK":
            print(f"    BUILD_ERROR: {built['error']}")
            results.append({"plan": label, "input": {k: v for k, v in built.items() if k != "text"},
                            "runs": []})
            continue
        print(f"    {built['doc_type']}, {built['n_pages']} pages, "
              f"{built['n_proposal_pages']} proposal pages ({built['proposal_ranges']}), "
              f"{built['chars_before_truncate']:,} chars -> {built['chars_sent']:,} sent"
              f"{' (TRUNCATED)' if built['truncated'] else ''}, "
              f"sha256 {built['input_sha256'][:16]}")
        text = built["text"]
        runs = [None] * n
        with futures.ThreadPoolExecutor(max_workers=workers) as ex:
            fut = {ex.submit(one_run, text, i): i for i in range(n)}
            for f in futures.as_completed(fut):
                i = fut[f]
                try:
                    runs[i] = f.result()
                except Exception as e:                        # noqa: BLE001
                    runs[i] = {"run": i, "status": "ERROR", "values": None, "confidence": None,
                               "error": f"worker raised {type(e).__name__}: {e}"}
        n_err = sum(1 for r in runs if r["status"] != "OK")
        print(f"    {n - n_err}/{n} runs OK" + (f", {n_err} ERROR" if n_err else ""))
        for r in runs:
            if r["status"] != "OK":
                print(f"      run {r['run']}: {r['error']}")
        results.append({"plan": label,
                        "input": {k: v for k, v in built.items() if k != "text"},
                        "runs": runs})

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps({"field_set": field_set, "n": n, "results": results}, indent=2))
    print(f"\nWrote {out_path}")
    return 0


# ── Reporting ───────────────────────────────────────────────────────────────────

def _spread(vals):
    """Spread of the OK numeric observations. Returns (text, cv) where cv is the coefficient of
    variation over the non-null numbers, or None when there are fewer than two of them."""
    nums = [v for v in vals if isinstance(v, (int, float))]
    n_null = sum(1 for v in vals if v is None)
    if not nums:
        return ("all null" if n_null else "no values"), None
    lo, hi = min(nums), max(nums)
    if lo == hi and not n_null:
        return "0 (identical)", 0.0
    mean = statistics.fmean(nums)
    cv = (statistics.pstdev(nums) / mean) if mean else None
    rng = f"{lo:,g}–{hi:,g}"
    if n_null:
        rng += f" + {n_null} null"
    if cv is not None and lo != hi:
        rng += f"  (range {(hi - lo) / mean * 100:.1f}% of mean)"
    return rng, cv


def report(path: Path) -> int:
    blob = json.loads(path.read_text())
    n = blob["n"]
    fs = blob["field_set"]
    print(f"\nField set: commit {fs['commit'][:8]}, {fs['n_extract_fields']} extract fields, "
          f"model {fs['model']}, temperature=0 (pinned in s3_extract.call_json)")
    print(f"2026-08-10 tons-bucket *_unconverted additions present: "
          f"{'YES' if 'base_unconverted' in fs['extract_field_names'] else 'NO'}")
    print(f"N = {n} per plan\n")

    for res in blob["results"]:
        ok = [r for r in res["runs"] if r["status"] == "OK"]
        err = [r for r in res["runs"] if r["status"] != "OK"]
        inp = res["input"]
        print("=" * 108)
        print(f"{res['plan']}")
        if inp.get("status") != "OK":
            print(f"  BUILD_ERROR — {inp.get('error')}\n")
            continue
        print(f"  input: {inp['doc_type']}, {inp['n_pages']}p, proposal {inp['proposal_ranges']}, "
              f"{inp['chars_sent']:,} chars sent, sha256 {inp['input_sha256'][:16]}")
        print(f"  runs: {len(ok)} OK, {len(err)} ERROR"
              + ("   <-- distributions below are over the OK runs ONLY; the errors are not nulls"
                 if err else ""))
        print(f"  {'field':<22} {'n':>4} {'distinct':>8}  {'mode':>14} {'mode n':>7}  spread")
        print("  " + "-" * 104)
        for name in QUANTITY_FIELDS + ["--"] + COMPANION_FIELDS:
            if name == "--":
                print("  " + "-" * 104)
                continue
            vals = [r["values"][name] for r in ok]
            if not vals:
                print(f"  {name:<22} {0:>4}  (no OK runs)")
                continue
            keys = ["null" if v is None else v for v in vals]
            counts = Counter(map(str, keys))
            mode, mode_n = counts.most_common(1)[0]
            sp, _cv = _spread(vals)
            label = f"{name} [{REPORT_LABEL[name]}]" if name in REPORT_LABEL else name
            print(f"  {label:<22} {len(vals):>4} {len(counts):>8}  {mode[:14]:>14} {mode_n:>7}  {sp}")
            if len(counts) > 1:
                detail = ", ".join(f"{k}×{c}" for k, c in counts.most_common())
                print(f"  {'':<22} └─ all observed: {detail}")
        print()

    # Cross-plan summary: which fields are unstable, and where the instability concentrates.
    print("=" * 108)
    print("STABILITY BY FIELD, ACROSS ALL PLANS (a plan-field is 'unstable' if its OK runs "
          "produced >1 distinct value)")
    print(f"  {'field':<22} {'plans measured':>15} {'unstable':>9}  detail")
    for name in QUANTITY_FIELDS + COMPANION_FIELDS:
        measured, unstable, detail = 0, 0, []
        for res in blob["results"]:
            ok = [r for r in res["runs"] if r["status"] == "OK"]
            if not ok:
                continue
            measured += 1
            counts = Counter(str("null" if r["values"][name] is None else r["values"][name])
                             for r in ok)
            if len(counts) > 1:
                unstable += 1
                detail.append(f"{res['plan'].split()[0]}({len(counts)})")
        print(f"  {name:<22} {measured:>15} {unstable:>9}  {', '.join(detail)}")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=10)
    ap.add_argument("--out", default="outputs/2026-08-10_nondeterminism.json")
    ap.add_argument("--workers", type=int, default=5)
    ap.add_argument("--set", dest="planset", choices=["task", "extension"], default="task",
                    help="task = the five plans the measurement task named; extension = the "
                         "three further plans carrying the remaining rows of the 12-move table")
    ap.add_argument("--report", help="read a results JSON and print the distribution tables")
    args = ap.parse_args()
    here = Path(__file__).resolve().parent
    if args.report:
        sys.exit(report(Path(args.report) if Path(args.report).is_absolute() else here / args.report))
    out = Path(args.out) if Path(args.out).is_absolute() else here / args.out
    plans = PLANS if args.planset == "task" else EXTENSION_PLANS
    sys.exit(measure(args.n, out, args.workers, plans))


if __name__ == "__main__":
    main()
