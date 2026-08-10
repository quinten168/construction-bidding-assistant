"""2026-08-10_rewarm_demo_cache.py — re-warm the demo plans' payload cache after the mapping fix.

WHY
---
The payload cache is keyed by PDF CONTENT HASH only (report.py::_payload_cache_path). It carries no
mapping or schema version, so the 2026-08-10 change to the seven quantity descriptions in schema.py
CANNOT invalidate it. Every cached entry predates that change, so a re-drop of a demo plan returns
pre-ruling numbers instantly and with no signal that they are stale. Stearns is the sharp case: the
cache holds MILL = 70,263 while the correct post-ruling value is 140,430 (the three MILL BITUMINOUS
lines plus 70,167 SY of FDR, which CSI ruled belongs in milling_sy).

This clears ONLY the named demo plans, re-runs the real live path once each, and writes the result
back through apply_verification() — the only function that writes the cache. Every other entry is
left alone, because a teammate is running the app live off this same cache.

The proper fix is a mapping version in the cache key: docs/_spec/2026-08-10-payload-cache-key-versioning.md.
That is specced and deliberately NOT built before the demo.

SAFETY
------
- Cleared entries are MOVED to a timestamped backup directory, never deleted.
- Chroma re-ingest is idempotent: s2_indexer uses deterministic ids ("{doc}:p{page}:c{idx}") and
  collection.upsert(), so re-running replaces chunks in place rather than duplicating them.
- Nothing is written to Postgres. No DDL. No bulk republish.
- A plan that fails to process is reported as FAILED and its backup is left in place; it is never
  recorded as "re-warmed with no quantities".

Usage:
    python tools/2026-08-10_rewarm_demo_cache.py --check     # report staleness, change nothing
    python tools/2026-08-10_rewarm_demo_cache.py --rewarm    # clear + re-run + verify
"""

import argparse
import datetime
import json
import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "apps" / "api"))

CORPUS = Path("/Users/t/Library/Mobile Documents/com~apple~CloudDocs/00 MSBA + Coding/"
              "00_summer 2026/00_CSI_ELP/CSI ELP 2026")

# The demo plans, with the value each MUST show after the re-warm. The expectation is the point of
# the script — a re-warm that produces a different number is a failure, not a new baseline.
DEMO_PLANS = [
    {"name": "Stearns CP 073-123-025 (MN)",
     "pdf": CORPUS / "2025 Bid year (9.1.24-8.31.25) - CURRENT" / "12 - AUGUST" / "Plans Proposals"
                   / "08.28.25 STEARNS CO MN CP 073-123-025 (CR 123) PAVEMENT RESURFACING AND REHAB"
                   / "9813645.pdf",
     "expect": {"MILL": 140430},
     "why": "ruling #9 folds 70,167 SY of FDR into milling_sy on top of the 70,263 SY of milling"},
    {"name": "Dunn Job 23388 (ND)",
     "pdf": CORPUS / "2026 JOBS" / "26051 DUNN COUNTY ND (ND 200)" / "Job 23388 Request for Proposal.pdf",
     "expect": {"MIX": 121421, "MILL": 408216, "BASE": 6506},
     "why": "state vocabulary fixes the 605x miss (was 200); FDR 408,216 SY; the 72,153 TON of "
            "REMOVE AGGREGATE BASE must NOT reach base_tons"},
]


def _mods():
    from backend import report as report_mod          # noqa: E402
    import s1_convert as convert                      # noqa: E402
    return report_mod, convert


def check():
    report_mod, convert = _mods()
    # The mapping change landed at this commit time; anything cached before it is pre-ruling.
    cutoff = datetime.datetime(2026, 8, 10, 13, 6, 13)
    cache_dir = report_mod._PAYLOAD_CACHE
    print(f"payload cache: {cache_dir}")
    entries = sorted(cache_dir.glob("*.json"))
    print(f"{len(entries)} cached payload(s); mapping changed {cutoff.isoformat()}\n")
    stale = 0
    for p in entries:
        mt = datetime.datetime.fromtimestamp(p.stat().st_mtime)
        j = json.loads(p.read_text())
        q = {x["label"]: x["value"] for x in (j.get("quantities") or [])}
        flag = "STALE" if mt < cutoff else "ok   "
        stale += mt < cutoff
        print(f"  {flag} {p.stem[:16]}  {mt:%Y-%m-%d %H:%M}  {str(j.get('plan_id'))[:32]:<33} {q}")
    print(f"\n{stale} of {len(entries)} predate the mapping fix.")

    print("\nDemo plans:")
    for d in DEMO_PLANS:
        if not d["pdf"].exists():
            print(f"  MISSING PDF  {d['name']}: {d['pdf']}")
            continue
        h = convert._hash(d["pdf"])
        path = report_mod._payload_cache_path(h)
        state = "cached" if path.exists() else "not cached (will run fresh)"
        print(f"  {d['name']}: hash={h} {state}; expect {d['expect']}")


def rewarm():
    report_mod, convert = _mods()
    stamp = datetime.datetime.now().strftime("%Y-%m-%d_%H%M%S")
    backup = report_mod._PAYLOAD_CACHE.parent / f"_report_payload_cache_backup_{stamp}"

    results = []
    for d in DEMO_PLANS:
        name = d["name"]
        if not d["pdf"].exists():
            # A missing source file is a FAILURE, never "re-warmed with nothing".
            results.append((name, "FAILED", "source PDF not found", {}))
            print(f"\n=== {name}: FAILED — source PDF not found at {d['pdf']}")
            continue

        print(f"\n=== {name}")
        h = convert._hash(d["pdf"])
        cached = report_mod._payload_cache_path(h)
        if cached.exists():
            backup.mkdir(parents=True, exist_ok=True)
            shutil.move(str(cached), str(backup / cached.name))
            print(f"  cleared {cached.name} -> {backup.name}/ (moved, not deleted)")
        else:
            print("  no cache entry; will run fresh")

        try:
            rep = report_mod.process_pdf(d["pdf"])
        except Exception as e:                                    # noqa: BLE001
            results.append((name, "FAILED", f"{e.__class__.__name__}: {e}", {}))
            print(f"  FAILED during process_pdf: {e.__class__.__name__}: {e}")
            continue

        if not rep.get("ok"):
            results.append((name, "FAILED", f"{rep.get('reason')}: {rep.get('message')}", {}))
            print(f"  FAILED: {rep.get('reason')} — {rep.get('message')}")
            continue

        # apply_verification with no edits: marks verified and writes the cache. This is the only
        # writer, so without it the re-run would produce a correct report and leave the cache stale.
        rep = report_mod.apply_verification(rep, {})
        got = {x["label"]: x["value"] for x in (rep.get("quantities") or [])}

        bad = {k: (v, got.get(k)) for k, v in d["expect"].items() if got.get(k) != v}
        status = "OK" if not bad else "MISMATCH"
        results.append((name, status, "" if not bad else f"expected vs got: {bad}", got))
        print(f"  quantities: {got}")
        print(f"  milling_unit_status: {(rep.get('identity') or {}).get('milling_unit_status')}")
        print(f"  {status}" + ("" if not bad else f" — {bad}"))

    print("\n" + "=" * 78)
    for name, status, note, got in results:
        print(f"  {status:<9} {name:<32} {note}")
    print("=" * 78)
    if backup.exists():
        print(f"Cleared entries backed up in: {backup}")
    return 0 if all(s == "OK" for _, s, _, _ in results) else 1


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--rewarm", action="store_true")
    a = ap.parse_args()
    if a.rewarm:
        sys.exit(rewarm())
    check()
