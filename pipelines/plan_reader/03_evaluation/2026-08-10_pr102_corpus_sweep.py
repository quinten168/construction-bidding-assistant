"""2026-08-10_pr102_corpus_sweep.py — one #102 extraction per cached plan, to measure how much of
the demo corpus its CY/SY capture actually reaches (§3 capture-all). One run per plan, so this
measures COVERAGE, not stability — stability is 2026-08-10_pr102_stability.py's job."""
import importlib.util
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("h", str(HERE / "2026-08-10_pr102_stability.py"))
h = importlib.util.module_from_spec(spec)
spec.loader.exec_module(h)

sys.path.insert(0, str(HERE.parent / "01_pipeline"))
import schema        # noqa: E402
import s3_extract    # noqa: E402

out = {}
for md in sorted(h.MD_DIR.glob("*.json")):
    if md.name.endswith(".hybrid.json"):
        continue
    h.PLAN_HASH = md.stem
    try:
        text = s3_extract.smart_truncate(h.document_text(), s3_extract.MAX_CHARS)
    except Exception as e:                                   # noqa: BLE001
        out[md.stem] = {"status": "ERROR", "why": f"md unreadable: {e}"}
        print(md.stem, "ERROR md unreadable"); continue
    rec, meta = h.one_extraction(text, 6000)
    if rec is None:
        out[md.stem] = {"status": "ERROR", "why": meta.get("why"), "meta": meta}
        print(md.stem, "ERROR", meta.get("why")); continue
    s = h.summarise_run(rec)
    out[md.stem] = {"status": "OK", "meta": meta, "summary": s}
    counts = {k: ("null" if v is None else len(v)) for k, v in s["items"].items()}
    print(f"{md.stem} out_tok={meta['output_tokens']} counts={counts} "
          f"statuses={s['statuses']} merged={ {k: (round(v,2) if v else v) for k,v in s['merged'].items()} }")

Path("/tmp/pr102_sweep.json").write_text(json.dumps(out, indent=2))
print("\nwrote /tmp/pr102_sweep.json")
