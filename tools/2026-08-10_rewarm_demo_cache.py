"""2026-08-10_rewarm_demo_cache.py — re-warm the demo plans' payload cache after the mapping fix.

WHY
---
The payload cache is keyed by PDF CONTENT HASH only (report.py::_payload_cache_path). It carries no
mapping or schema version, so the 2026-08-10 change to the seven quantity descriptions in schema.py
CANNOT invalidate it. Every cached entry predates that change, so a re-drop of a demo plan returns
pre-ruling numbers instantly and with no signal that they are stale. Stearns is the sharp case: the
cache holds MILL = 70,263 while the correct post-ruling value is 140,430 (the three MILL BITUMINOUS
lines plus 70,167 SY of FDR, which CSI ruled belongs in milling_sy).

2026-08-10, LATER — WHY STEARNS' MILL IS NO LONGER A PINNED EXPECTATION.
140,430 is still the CORRECT number and is what a re-warm should show. It is not pinned because it
does not reproduce every time: measured N=10 on the live extractor input
(03_evaluation/2026-08-10_ruling9_cl13_measurement.py, arm `after4`), milling_sy came back
140,430 on 8 runs and ~208,4xx — the milling subtotal double-counted — on 2. Pinning a value that
reproduces 8 times in 10 turns a 20%-likely model arithmetic slip into a script that reports
FAILED on a correct run, and this repo has already been burned by a check whose green and red both
meant something other than what they said. What IS pinned is the four Stearns fields that were
unanimous across 20 runs (two arms of 10). MILL is printed on every re-warm and is checked by a
human against 140,430; if it differs, re-run before concluding anything.
Full before/after distributions: docs/_session/2026-08-10-ruling9-and-cl13.md.

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
     # MILL is deliberately NOT here — see the docstring. Expected value 140,430, reproduces 8/10.
     # These four were unanimous across both N=10 arms (before and after the 2026-08-10 prose fix).
     "expect": {"MIX": 14480, "BASE": 270, "GRADE": 200, "SHLDR": 460},
     "why": ("MILL is NOT pinned: the correct post-ruling value is 140,430 (70,263 SY of MILL "
             "BITUMINOUS SURFACE + 70,167 SY of FULL DEPTH RECLAMATION, CSI ruling #9), and it "
             "reproduces 8 times in 10 — the other 2 double-count the milling subtotal to "
             "~208,4xx. CHECK THE PRINTED MILL BY HAND against 140,430; if it is 70,263 the "
             "ruling stopped firing, if it is ~208,4xx it is the known arithmetic slip, and "
             "either way re-run before concluding. The four pinned fields were 20/20 stable.")},
    {"name": "Dunn Job 23388 (ND)",
     "pdf": CORPUS / "2026 JOBS" / "26051 DUNN COUNTY ND (ND 200)" / "Job 23388 Request for Proposal.pdf",
     "expect": {"MIX": 121421, "MILL": 408216, "BASE": 6506},
     "why": "state vocabulary fixes the 605x miss (was 200); FDR 408,216 SY; the 72,153 TON of "
            "REMOVE AGGREGATE BASE must NOT reach base_tons"},
]


# Plans with no cache entry yet that still belong on the re-warm set. 9786015 is the plan the CSI
# team tested on 2026-08-10 (CSAH 2 / Maryland Ave, Murray County MN) — the source of the
# found-but-unconvertible finding — and it had never been through the live path here.
EXTRA_PLANS = [
    CORPUS / "2025 Bid year (9.1.24-8.31.25) - CURRENT" / "12 - AUGUST" / "Plans Proposals"
           / "08.07.25 MURRAY CO MN, FULDA PROJ 254021 (CSAH 2) INFRASTRUCTURE IMPS" / "9786015.pdf",
]


def _mods():
    from backend import report as report_mod          # noqa: E402
    import s1_convert as convert                      # noqa: E402
    return report_mod, convert


def discover_sources(report_mod, convert):
    """cache hash -> source PDF, resolved by plan_id and CONFIRMED by re-hashing the file.

    The payload does not record where it came from, so the mapping is rebuilt: index the corpus by
    filename stem, look up each payload's plan_id, and accept a candidate only when its content hash
    equals the cache key. `_hash` is an md5 of the file BYTES (s1_convert._content_key), so the same
    file matches from either mirror.

    A hash that resolves to no file is returned in `unresolved` and is never silently skipped — an
    unresolvable entry is a gap in the re-warm, not a plan that needed no work.
    """
    by_stem = {}
    for f in CORPUS.rglob("*.pdf"):
        by_stem.setdefault(f.stem, []).append(f)
    found, unresolved = {}, []
    for p in sorted(report_mod._PAYLOAD_CACHE.glob("*.json")):
        pid = json.loads(p.read_text()).get("plan_id")
        hit = None
        for c in by_stem.get(str(pid), []):
            try:
                if convert._hash(c) == p.stem:
                    hit = c
                    break
            except OSError:
                continue
        if hit:
            found[p.stem] = hit
        else:
            unresolved.append((p.stem, pid, len(by_stem.get(str(pid), []))))
    return found, unresolved, len(by_stem)


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


def _moved(before, after):
    """Labels whose value changed. `before is None` (no prior cache entry) yields {} — a plan that
    was never cached has not "moved", and conflating the two would invent movement that never
    happened. An unreadable prior entry is reported as its own state, never as unchanged."""
    if before is None:
        return {}
    if before == "UNREADABLE":
        return {"(prior cache entry)": ("UNREADABLE", "rebuilt")}
    return {k: (before.get(k), after.get(k))
            for k in set(before) | set(after) if before.get(k) != after.get(k)}


def rewarm(all_stale=False):
    report_mod, convert = _mods()
    stamp = datetime.datetime.now().strftime("%Y-%m-%d_%H%M%S")
    backup = report_mod._PAYLOAD_CACHE.parent / f"_report_payload_cache_backup_{stamp}"

    plans = list(DEMO_PLANS)
    if all_stale:
        cutoff = datetime.datetime(2026, 8, 10, 13, 6, 13)
        found, unresolved, n_stems = discover_sources(report_mod, convert)
        print(f"discovery: {len(found)} of {len(found) + len(unresolved)} cache entries resolved to a "
              f"source PDF (corpus indexed by {n_stems} stems)")
        for h, pid, n in unresolved:
            # Never silently skipped: an unresolved entry stays stale and must be reported as such.
            print(f"  UNRESOLVED {h} plan_id={pid!r} ({n} stem candidates) — stays stale")
        known = {d["pdf"] for d in plans}
        for h, pdf in sorted(found.items(), key=lambda kv: str(kv[1])):
            if pdf in known:
                continue
            mt = datetime.datetime.fromtimestamp(report_mod._payload_cache_path(h).stat().st_mtime)
            if mt < cutoff:
                plans.append({"name": f"{pdf.stem} (stale {mt:%m-%d %H:%M})", "pdf": pdf,
                              "expect": {}, "why": "re-warm only; no pinned expectation"})
        for pdf in EXTRA_PLANS:
            if pdf not in {p["pdf"] for p in plans}:
                plans.append({"name": f"{pdf.stem} (CSI test plan, never cached)", "pdf": pdf,
                              "expect": {}, "why": "CSI tested this one on 2026-08-10"})
        print(f"re-warming {len(plans)} plan(s)\n")

    results = []
    for d in plans:
        name = d["name"]
        if not d["pdf"].exists():
            # A missing source file is a FAILURE, never "re-warmed with nothing".
            results.append((name, "FAILED", "source PDF not found", {}, None, {}))
            print(f"\n=== {name}: FAILED — source PDF not found at {d['pdf']}")
            continue

        print(f"\n=== {name}")
        # The `why` carries what a pinned equality check cannot: which fields are NOT pinned, what
        # their correct value is, and what a deviation means. Printing it is the difference between
        # an operator seeing an unpinned MILL and knowing what to compare it against.
        if d.get("why"):
            print(f"  note: {d['why']}")
        h = convert._hash(d["pdf"])
        cached = report_mod._payload_cache_path(h)
        before = None
        if cached.exists():
            # Read the OLD quantities before clearing, so "which plans moved" is a measurement
            # rather than a guess. None means there was no prior entry, which is distinct from {}
            # (an entry that legitimately held no quantities).
            try:
                before = {x["label"]: x["value"]
                          for x in (json.loads(cached.read_text()).get("quantities") or [])}
            except (OSError, json.JSONDecodeError):
                before = "UNREADABLE"
            backup.mkdir(parents=True, exist_ok=True)
            shutil.move(str(cached), str(backup / cached.name))
            print(f"  cleared {cached.name} -> {backup.name}/ (moved, not deleted)")
            print(f"  before: {before}")
        else:
            print("  no cache entry; will run fresh")

        try:
            rep = report_mod.process_pdf(d["pdf"])
        except Exception as e:                                    # noqa: BLE001
            results.append((name, "FAILED", f"{e.__class__.__name__}: {e}", {}, before, {}))
            print(f"  FAILED during process_pdf: {e.__class__.__name__}: {e}")
            continue

        if not rep.get("ok"):
            results.append((name, "FAILED", f"{rep.get('reason')}: {rep.get('message')}", {}, before, {}))
            print(f"  FAILED: {rep.get('reason')} — {rep.get('message')}")
            continue

        # apply_verification with no edits: marks verified and writes the cache. This is the only
        # writer, so without it the re-run would produce a correct report and leave the cache stale.
        rep = report_mod.apply_verification(rep, {})
        got = {x["label"]: x["value"] for x in (rep.get("quantities") or [])}

        bad = {k: (v, got.get(k)) for k, v in d["expect"].items() if got.get(k) != v}
        status = "OK" if not bad else "MISMATCH"
        moved = _moved(before, got)
        results.append((name, status, "" if not bad else f"expected vs got: {bad}", got, before, moved))
        print(f"  after : {got}")
        if moved:
            print(f"  MOVED : {moved}")
        print(f"  milling_unit_status: {(rep.get('identity') or {}).get('milling_unit_status')}")
        print(f"  {status}" + ("" if not bad else f" — {bad}"))

    print("\n" + "=" * 78)
    for name, status, note, got, before, moved in results:
        print(f"  {status:<9} {name:<44} {note}")
    print("-" * 78)
    print("  PLANS WHOSE NUMBERS MOVED (old -> new):")
    any_moved = False
    for name, status, note, got, before, moved in results:
        if moved:
            any_moved = True
            for label, (o, n) in sorted(moved.items()):
                print(f"    {name[:40]:<42} {label:<10} {str(o):>12} -> {str(n):>12}")
    if not any_moved:
        print("    (none)")
    print("=" * 78)
    if backup.exists():
        print(f"Cleared entries backed up in: {backup}")
    return 0 if all(r[1] == "OK" for r in results) else 1


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--rewarm", action="store_true")
    ap.add_argument("--all-stale", action="store_true",
                    help="re-warm every cache entry that predates the mapping fix, not just the "
                         "two pinned demo plans")
    a = ap.parse_args()
    if a.rewarm or a.all_stale:
        sys.exit(rewarm(all_stale=a.all_stale))
    check()
