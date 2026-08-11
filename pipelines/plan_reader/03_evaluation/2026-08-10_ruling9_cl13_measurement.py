"""
2026-08-10_ruling9_cl13_measurement.py — N=10 firing-rate harness for two named defects.

WHY THIS EXISTS, AND WHY IT IS NOT THE OTHER HARNESS
----------------------------------------------------
`2026-08-10_nondeterminism_measurement.py` measures the WHOLE seven-field mapping over eight plans
and reports distributions. Two specific defects came out of it and need a tighter loop:

  1. **CSI ruling #9 does not fire.** FULL DEPTH RECLAMATION is base work whose quantity CSI ruled
     is reported in `milling_sy`. On Stearns 9813645 the FDR line (70,167 SY) is printed in the text
     the model receives and `milling_sy` came back 70,263 on 10 runs out of 10 — the three MILL
     BITUMINOUS SURFACE lines only. Firing rate: 0/10.
  2. **`AGGREGATE SURFACE COURSE CL 13` is named by no field description.** On Job 24133 (ND, 170 T)
     7 runs in 10 dropped it out of EVERY bucket — a silent capture failure, not noise.

This script runs the same held-constant live-path input as that harness (it imports `build_input`
from it rather than re-implementing the chain) but records, per run, the model's own `page` and
`reason` for the fields under test. The prose is what is being changed, so the model's stated
justification is the diagnostic that says WHY a clause did or did not fire — a bare distribution
cannot.

It also carries the REGRESSION arm in the same run: Dunn Job 23388's `milling_sy` = 408,216 is
itself an FDR line and is currently stable at 10/10. Any prose change that makes Stearns fire must
leave Dunn alone, and the only way to know that is to measure it in the same pass.

STANDING RULES, ENFORCED HERE
-----------------------------
- A failure and a legitimate empty answer NEVER share a return value. A parse failure / API error is
  `status="ERROR"` with `values=None`; it is excluded from every distribution and counted out loud.
  It is never recorded as a null.
- `process_pdf` is never called. Chroma is touched ZERO times (a teammate is live on that
  collection). Only the extractor is called.
- The input string is built ONCE per plan and reused verbatim for all N runs, hashed so a reader can
  confirm the arm was constant.

Usage:
    python 2026-08-10_ruling9_cl13_measurement.py --n 10 --arm before
    python 2026-08-10_ruling9_cl13_measurement.py --n 10 --arm after
    python 2026-08-10_ruling9_cl13_measurement.py --report outputs/2026-08-10_ruling9_after.json
"""

import argparse
import concurrent.futures as futures
import importlib.util
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
_PIPE = REPO / "pipelines" / "plan_reader" / "01_pipeline"
sys.path.insert(0, str(_PIPE))

import s3_extract   # noqa: E402
import schema       # noqa: E402

# The sibling harness's module name starts with a digit, so it cannot be imported normally.
# Importing it (rather than copying build_input) is deliberate: the two arms MUST construct the
# extractor input the same way or the comparison is meaningless.
_ND_PATH = Path(__file__).resolve().parent / "2026-08-10_nondeterminism_measurement.py"
_spec = importlib.util.spec_from_file_location("_nondet", _ND_PATH)
_nondet = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_nondet)
build_input = _nondet.build_input

# The three plans under test, and what each one is FOR. Nothing else is run: this is a targeted
# harness, and the eight-plan sweep already exists next door.
PLANS = [
    # Defect 1 — ruling #9. Expected under the ruling: 70,263 (milling) + 70,167 (FDR) = 140,430.
    ("Stearns 9813645 (MN)", _nondet.PLANS[0][1], "ruling9"),
    # Regression arm — Dunn's milling_sy IS an FDR line (408,216 SY) and is stable today.
    ("Dunn Job 23388 (ND)", _nondet.PLANS[2][1], "regression"),
    # Defect 2 — AGGREGATE SURFACE COURSE CL 13, 170 TON, dropped from every bucket 7/10.
    ("Job 24133 Morton (ND)", _nondet.EXTENSION_PLANS[2][1], "cl13"),
]

# Fields recorded. The seven quantity buckets so a bucket-to-bucket move cannot hide, plus the
# milling companions because Dunn's milling is split SY/TON and a change to milling_sy prose can
# move a line between the two.
FIELDS = ["hot_mix_tons", "base_tons", "grading_quantity", "shoulder_tons",
          "milling_sy", "milling_tons", "milling_measured_unit",
          "crushing_tons", "stockpile_tons",
          "base_measured_unit", "base_unconverted",
          "shoulder_measured_unit", "shoulder_unconverted"]

# Fields whose model-stated reason/page are printed. Kept short so the report stays readable.
REASON_FIELDS = ["milling_sy", "shoulder_tons", "base_tons"]


def one_run(text: str, run_idx: int) -> dict:
    """One extraction over the held-constant input, capturing value + confidence + page + reason."""
    rec = {"run": run_idx, "status": None, "cells": None, "error": None}
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
        rec["status"] = "ERROR"
        rec["error"] = "model response did not parse (token-cap truncation, or malformed JSON)"
        return rec
    if not isinstance(data, dict):
        rec["status"] = "ERROR"
        rec["error"] = f"model returned a {type(data).__name__}, not a JSON object"
        return rec
    by_name = {f["name"]: f for f in schema.EXTRACT_FIELDS}
    cells = {}
    for name in FIELDS:
        f = by_name.get(name)
        if f is None:
            rec["status"] = "ERROR"
            rec["error"] = f"field {name!r} is not in schema.EXTRACT_FIELDS — harness is out of date"
            return rec
        cells[name] = s3_extract._coerce_cell(f, data.get(name))
    rec["status"] = "OK"
    rec["cells"] = cells
    return rec


def measure(n: int, out_path: Path, workers: int, only: str | None) -> int:
    field_set = {
        "commit": subprocess.run(["git", "-C", str(REPO), "rev-parse", "HEAD"],
                                 capture_output=True, text=True).stdout.strip(),
        "schema_dirty": bool(subprocess.run(
            ["git", "-C", str(REPO), "status", "--porcelain",
             "pipelines/plan_reader/01_pipeline/schema.py"],
            capture_output=True, text=True).stdout.strip()),
        "schema_sha": subprocess.run(["shasum", "-a", "256", str(_PIPE / "schema.py")],
                                     capture_output=True, text=True).stdout.split()[0],
        "n_extract_fields": len(schema.EXTRACT_FIELDS),
        "model": s3_extract.MODEL,
        "max_chars": s3_extract.MAX_CHARS,
        "extract_max_tokens": s3_extract.EXTRACT_MAX_TOKENS,
    }
    print(f"schema.py sha256 {field_set['schema_sha'][:16]}"
          f"{' (DIRTY vs git)' if field_set['schema_dirty'] else ''}, "
          f"{field_set['n_extract_fields']} extract fields, model {field_set['model']}\n")

    results = []
    for label, pdf, purpose in PLANS:
        if only and only not in purpose:
            continue
        print(f"=== {label}  [{purpose}]")
        built = build_input(pdf)
        if built["status"] != "OK":
            print(f"    BUILD_ERROR: {built['error']}")
            results.append({"plan": label, "purpose": purpose, "runs": [],
                            "input": {k: v for k, v in built.items() if k != "text"}})
            continue
        print(f"    {built['doc_type']}, {built['n_pages']}p, proposal {built['proposal_ranges']}, "
              f"{built['chars_sent']:,} chars sent"
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
                    runs[i] = {"run": i, "status": "ERROR", "cells": None,
                               "error": f"worker raised {type(e).__name__}: {e}"}
        n_err = sum(1 for r in runs if r["status"] != "OK")
        print(f"    {n - n_err}/{n} runs OK" + (f", {n_err} ERROR" if n_err else ""))
        for r in runs:
            if r["status"] != "OK":
                print(f"      run {r['run']}: {r['error']}")
        results.append({"plan": label, "purpose": purpose,
                        "input": {k: v for k, v in built.items() if k != "text"},
                        "runs": runs})

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps({"field_set": field_set, "n": n, "results": results}, indent=2))
    print(f"\nWrote {out_path}")
    return report(out_path)


def report(path: Path) -> int:
    blob = json.loads(path.read_text())
    fs = blob["field_set"]
    print(f"\nschema.py sha256 {fs['schema_sha'][:16]}, commit {fs['commit'][:8]}, "
          f"model {fs['model']}, temperature=0, N={blob['n']}\n")
    for res in blob["results"]:
        ok = [r for r in res["runs"] if r["status"] == "OK"]
        err = [r for r in res["runs"] if r["status"] != "OK"]
        print("=" * 100)
        print(f"{res['plan']}  [{res['purpose']}]   {len(ok)} OK / {len(err)} ERROR"
              + ("   <-- ERRORs are excluded, NOT counted as nulls" if err else ""))
        if not ok:
            print(f"  no OK runs — {res['input'].get('error', '')}\n")
            continue
        for name in FIELDS:
            vals = [r["cells"][name]["value"] for r in ok]
            counts = Counter("null" if v is None else str(v) for v in vals)
            detail = ", ".join(f"{k}×{c}" for k, c in counts.most_common())
            mark = "  " if len(counts) == 1 else " *"
            print(f" {mark}{name:<24} {detail}")
        for name in REASON_FIELDS:
            print(f"    -- {name} reasons:")
            seen = Counter()
            for r in ok:
                c = r["cells"][name]
                seen[f"p.{c['page']} | {c['value']} | {(c['reason'] or '')[:150]}"] += 1
            for k, c in seen.most_common():
                print(f"       ×{c}  {k}")
        print()
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=10)
    ap.add_argument("--arm", default="run", help="label for the output file (before / after / ...)")
    ap.add_argument("--out")
    ap.add_argument("--workers", type=int, default=5)
    ap.add_argument("--only", help="run only plans whose purpose contains this (ruling9/regression/cl13)")
    ap.add_argument("--report", help="read a results JSON and print the tables")
    args = ap.parse_args()
    here = Path(__file__).resolve().parent
    if args.report:
        p = Path(args.report)
        sys.exit(report(p if p.is_absolute() else here / args.report))
    out = Path(args.out) if args.out else here / "outputs" / f"2026-08-10_ruling9_{args.arm}.json"
    sys.exit(measure(args.n, out, args.workers, args.only))


if __name__ == "__main__":
    main()
