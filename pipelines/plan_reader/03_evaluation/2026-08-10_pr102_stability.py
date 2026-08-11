"""
2026-08-10_pr102_stability.py — VALIDATION HARNESS for PR #102 (fix/aggregate-mix-tons-conversion).

Not a fix, not a feature. Answers three questions with measurements, on the real plan 9786015
(md_cache hash a3171c2187e8af85, Murray Co MN, CSAH 2 / Maryland Ave):

  A. Does #102's code reproduce base 3,851.75 t / shoulder 13.09 t / mix 1,901.34 t, with every
     multiplication and sum performed by material_tons_merge.py rather than by hand or by a doc?
  B. Is the CODE math deterministic across repeated calls? (--repeat-math)
  C. Is the MODEL's per-item BUCKET ASSIGNMENT stable across repeated extractions at temperature=0?
     (--runs N)  Arithmetic determinism and classification determinism are different claims; C is
     the one that matters for the drift we measured tonight.

Also records `stop_reason` and output-token usage on every call, so a truncated response is
distinguishable from a malformed one HERE even though call_json cannot tell them apart.

STANDING RULE, ENFORCED HERE: a failure and a legitimate empty answer never share a return value.
A run that errors is recorded status=ERROR with null buckets; a run whose model answer is a genuine
empty array is recorded status=OK with an empty list. They are never merged.

Usage:
    python 2026-08-10_pr102_stability.py --repeat-math 1000
    python 2026-08-10_pr102_stability.py --runs 6 --out /tmp/pr102_runs.json
    python 2026-08-10_pr102_stability.py --report /tmp/pr102_runs.json
"""

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

_PIPE = Path(__file__).resolve().parent.parent / "01_pipeline"
sys.path.insert(0, str(_PIPE))
import schema             # noqa: E402
import s3_extract         # noqa: E402
import material_tons_merge  # noqa: E402

# The md cache lives in the primary checkout (untracked; not copied into a worktree). READ ONLY.
MD_DIR = Path("/Users/t/dev/csi/csi-bid-intelligence/pipelines/plan_reader/00_input/_md_cache")
# a3171c2187e8af85 = plan 9786015 Murray MN (the plan #102 was built on)
# f19c9df671fd2fd7 = plan 9813645 Stearns MN (the MILL 140,430 / 70,263 drift case)
# 9ff5dc83b09d4079 = Crow Wing MN (the GRADE 7,707 / 15,876 drift case)
PLAN_HASH = "a3171c2187e8af85"

ITEM_FIELDS = ["base_cy_items", "shoulder_cy_items", "mix_sy_depth_items"]
SCALARS = ["base_tons", "shoulder_tons", "hot_mix_tons", "grading_quantity", "milling_sy"]

# The bid schedule's own placed-material lines (pages 27), transcribed from the document so a
# run's bucket assignment can be reported per REAL item rather than per model-invented entry.
GROUND_TRUTH = {
    2495: "39 Common Excavation (CV)(P) | CY",
    38:   '40 8" Class 5 Alley & Shouldering Aggregate Surfacing (CV)(P) | SY',
    2485: "41 Class 5 Aggregate Base (CV)(P) | CY",
    1566: '42 12" Cement Stabilized Subgrade (CV)(P) | SY',
    40:   "43 Cement Powder based on 5% | TON",
    5368: "44/45 2.0\" and 3.0\" Type SP Mixture (CSAH 2) | SY  [TWO items, same quantity]",
    1703: "46/47 1.5\" and 2.5\" Type SP Mixture (MARYLAND AVE) | SY  [TWO items, same quantity]",
}


def document_text():
    pages = json.load(open(MD_DIR / f"{PLAN_HASH}.json"))
    return "\n\n".join(f"[Page {p.get('page')}]\n{p.get('text', '')}" for p in pages
                       if (p.get("text") or "").strip())


# ── C: repeated live extraction ────────────────────────────────────────────────

def one_extraction(text, max_tokens):
    """One real extraction call. Returns (record_or_None, meta). meta always names WHY a failure
    happened (max_tokens vs malformed vs API error) — the distinction call_json itself loses."""
    import anthropic
    import re
    prompt = s3_extract.EXTRACTION_PROMPT.format(
        field_list=schema.extract_prompt_fields(),
        archetypes=s3_extract.archetype_choices(),
        document_text=text,
    )
    client = anthropic.Anthropic(api_key=s3_extract.API_KEY)
    try:
        resp = client.messages.create(model=s3_extract.MODEL, max_tokens=max_tokens,
                                      temperature=0,
                                      messages=[{"role": "user", "content": prompt}])
    except Exception as e:                                  # noqa: BLE001 — recorded, not swallowed
        return None, {"status": "ERROR", "why": f"api_error: {e.__class__.__name__}: {e}"}
    raw = resp.content[0].text.strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    meta = {"stop_reason": resp.stop_reason,
            "output_tokens": resp.usage.output_tokens,
            "input_tokens": resp.usage.input_tokens}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        meta["status"] = "ERROR"
        meta["why"] = ("truncated_at_max_tokens" if resp.stop_reason == "max_tokens"
                       else f"malformed_json: {e}")
        return None, meta
    meta["status"] = "OK"
    meta["why"] = ""
    record = {f["name"]: s3_extract._coerce_cell(f, data.get(f["name"]))
              for f in schema.EXTRACT_FIELDS}
    return record, meta


def summarise_run(record):
    """One extraction record -> the facts this validation compares across runs."""
    out = {"items": {}, "scalars": {}, "statuses": {}, "merged": {}}
    for f in ITEM_FIELDS:
        v = schema._cell_value(record, f)
        out["items"][f] = v            # None (no answer) and [] (asserted empty) stay distinct
    for f in SCALARS:
        out["scalars"][f] = schema._cell_value(record, f)
    out["statuses"] = {"base": schema.base_unit_status(record),
                       "shoulder": schema.shoulder_unit_status(record),
                       "mix": schema.mix_unit_status(record)}
    out["merged"] = material_tons_merge.merge_material_tons(record)
    return out


def run_many(n, max_tokens, out_path):
    text = s3_extract.smart_truncate(document_text(), s3_extract.MAX_CHARS)
    runs = []
    for i in range(n):
        record, meta = one_extraction(text, max_tokens)
        entry = {"run": i, "meta": meta}
        entry["summary"] = summarise_run(record) if record is not None else None
        runs.append(entry)
        m = entry["summary"]["merged"] if entry["summary"] else None
        print(f"run {i}: {meta['status']:5} stop={meta.get('stop_reason')} "
              f"out_tok={meta.get('output_tokens')} merged={m}")
    Path(out_path).write_text(json.dumps({"plan": PLAN_HASH,
                                          "max_tokens": max_tokens, "runs": runs}, indent=2))
    print(f"\nwrote {out_path}")
    return runs


# ── reporting ──────────────────────────────────────────────────────────────────

def _item_key(it):
    return (it.get("quantity"), it.get("unit"), it.get("depth_in"))


def report(path):
    blob = json.loads(Path(path).read_text())
    runs = blob["runs"]
    ok = [r for r in runs if r["summary"] is not None]
    print(f"\n=== {blob['plan']}  n={len(runs)} runs, {len(ok)} OK, "
          f"{len(runs) - len(ok)} ERROR (max_tokens={blob['max_tokens']}) ===\n")
    for r in runs:
        if r["summary"] is None:
            print(f"  run {r['run']}: ERROR — {r['meta'].get('why')}")

    print("\n-- merged bucket totals per run --")
    tot = defaultdict(list)
    for r in ok:
        for k, v in r["summary"]["merged"].items():
            tot[k].append(None if v is None else round(v, 2))
    for k, vals in tot.items():
        c = Counter(map(str, vals))
        print(f"  {k:14} {vals}   distinct={len(c)}  {'STABLE' if len(c) == 1 else 'DRIFT'}")

    print("\n-- pre-existing scalars per run (unrelated buckets, sanity) --")
    sc = defaultdict(list)
    for r in ok:
        for k, v in r["summary"]["scalars"].items():
            sc[k].append(v)
    for k, vals in sc.items():
        c = Counter(map(str, vals))
        print(f"  {k:18} {vals}   distinct={len(c)}  {'STABLE' if len(c) == 1 else 'DRIFT'}")

    print("\n-- derived unit statuses per run --")
    st = defaultdict(list)
    for r in ok:
        for k, v in r["summary"]["statuses"].items():
            st[k].append(v)
    for k, vals in st.items():
        c = Counter(vals)
        print(f"  {k:10} {vals}   distinct={len(c)}  {'STABLE' if len(c) == 1 else 'DRIFT'}")

    print("\n-- PER-ITEM BUCKET ASSIGNMENT (the key measurement) --")
    # item identity -> Counter of the bucket field it landed in, per run
    seen = defaultdict(Counter)
    per_run_sets = []
    for r in ok:
        assign = {}
        for field, items in r["summary"]["items"].items():
            for it in (items or []):
                assign.setdefault(_item_key(it), []).append(field)
        per_run_sets.append(assign)
        for key, fields in assign.items():
            seen[key]["+".join(sorted(fields))] += 1
    allkeys = sorted(seen, key=lambda k: (-(k[0] or 0)))
    for key in allkeys:
        qty, unit, depth = key
        counts = seen[key]
        appearances = sum(counts.values())
        gt = GROUND_TRUTH.get(int(qty) if qty is not None and float(qty).is_integer() else -1, "")
        verdict = "STABLE" if (len(counts) == 1 and appearances == len(ok)) else "UNSTABLE"
        print(f"  qty={qty} unit={unit} depth={depth}  seen in {appearances}/{len(ok)} runs  "
              f"-> {dict(counts)}  [{verdict}]")
        if gt:
            print(f"      plan item: {gt}")

    # item-count stability per bucket
    print("\n-- item COUNT per bucket per run --")
    cnt = defaultdict(list)
    for r in ok:
        for field, items in r["summary"]["items"].items():
            cnt[field].append("null" if items is None else len(items))
    for k, vals in cnt.items():
        c = Counter(map(str, vals))
        print(f"  {k:20} {vals}   distinct={len(c)}  {'STABLE' if len(c) == 1 else 'DRIFT'}")


# ── B: code-math determinism ───────────────────────────────────────────────────

FIXED_RECORD = {
    "base_tons": schema.cell(None, "", None, ""),
    "shoulder_tons": schema.cell(None, "", None, ""),
    "hot_mix_tons": schema.cell(None, "", None, ""),
    "base_cy_items": schema.cell([{"quantity": 2485.0, "unit": "CY", "depth_in": None,
                                   "page": 27, "note": "41 Class 5 Aggregate Base (CV)(P)"}],
                                 "high", 27, ""),
    "shoulder_cy_items": schema.cell([{"quantity": 38.0, "unit": "SY", "depth_in": 8.0,
                                       "page": 27, "note": "40 8\" Class 5 Alley & Shouldering"}],
                                     "high", 27, ""),
    "mix_sy_depth_items": schema.cell([
        {"quantity": 5368.0, "unit": "SY", "depth_in": 2.0, "page": 27, "note": "44"},
        {"quantity": 5368.0, "unit": "SY", "depth_in": 3.0, "page": 27, "note": "45"},
        {"quantity": 1703.0, "unit": "SY", "depth_in": 1.5, "page": 27, "note": "46"},
        {"quantity": 1703.0, "unit": "SY", "depth_in": 2.5, "page": 27, "note": "47"},
    ], "high", 27, ""),
}

EXPECTED = {"base_tons": 3851.75, "shoulder_tons": 13.09, "hot_mix_tons": 1901.34}


def repeat_math(n):
    results = set()
    for _ in range(n):
        m = material_tons_merge.merge_material_tons(FIXED_RECORD)
        results.add(tuple(sorted((k, repr(v)) for k, v in m.items())))
    m = material_tons_merge.merge_material_tons(FIXED_RECORD)
    print(f"merge_material_tons() x{n}: {len(results)} distinct result(s) "
          f"-> {'DETERMINISTIC' if len(results) == 1 else 'NON-DETERMINISTIC'}")
    print("  full precision:", m)
    for k, want in EXPECTED.items():
        got = round(m[k], 2)
        print(f"  {k:14} code={got}  expected={want}  {'MATCH' if got == want else 'MISMATCH'}")
    # show the arithmetic chain, all in code
    print("\n  chain (code, not by hand):")
    print("    base   :", schema.resolve_cy_item(FIXED_RECORD["base_cy_items"]["value"][0]),
          "CY x", material_tons_merge.AGGREGATE_TON_PER_CY)
    print("    shldr  :", schema.resolve_cy_item(FIXED_RECORD["shoulder_cy_items"]["value"][0]),
          "CY x", material_tons_merge.AGGREGATE_TON_PER_CY)
    prods = [schema.resolve_sy_depth_product(i)
             for i in FIXED_RECORD["mix_sy_depth_items"]["value"]]
    print("    mix    :", prods, "sum =", sum(prods), "SY-in x",
          material_tons_merge.MIX_TON_PER_SY_INCH)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=0)
    ap.add_argument("--max-tokens", type=int, default=6000)
    ap.add_argument("--out", default="/tmp/pr102_runs.json")
    ap.add_argument("--report")
    ap.add_argument("--repeat-math", type=int, default=0)
    ap.add_argument("--plan", default=PLAN_HASH)
    a = ap.parse_args()
    PLAN_HASH = a.plan
    if a.repeat_math:
        repeat_math(a.repeat_math)
    if a.runs:
        run_many(a.runs, a.max_tokens, a.out)
    if a.report:
        report(a.report)
