"""
measure_bid_date.py — coverage measurement for the layer-1/layer-2 bid-date parser.

A parser that "works" on one file is not evidence. This walks a corpus root, finds every
standalone advertisement PDF, runs layer 1 on each, and reports a HIT RATE with the failures
characterised — and, where the containing folder is named `MM.DD.YY <COUNTY> ...` (the client's
consistent convention across three bid years), checks the parsed date against it.

    python pipelines/plan_reader/04_tools/bid_date/measure_bid_date.py <corpus-root> \
        --out docs/_session/2026-08-10-bid-date-layer1.csv
"""
from __future__ import annotations

import argparse
import csv
import re
import sys
from collections import Counter
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bid_date  # noqa: E402

FOLDER_DATE = re.compile(r"^(\d{2})\.(\d{2})\.(\d{2})\b")


def folder_date(p: Path):
    """the client names every project folder `MM.DD.YY <COUNTY> <STATE> - ...`. Walk up to find it."""
    for parent in [p.parent, *p.parents]:
        m = FOLDER_DATE.match(parent.name)
        if m:
            mo, d, y = (int(x) for x in m.groups())
            try:
                return date(2000 + y, mo, d).isoformat()
            except ValueError:
                return None
    return None


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("root")
    ap.add_argument("--out", default=None)
    ap.add_argument("--mode", choices=["ads", "plans"], default="ads",
                    help="ads: layer 1 over every standalone advertisement PDF under root. "
                         "plans: layer 2 over every plan-set PDF in root/<plan_id>/*.pdf.")
    args = ap.parse_args(argv)

    root = Path(args.root)
    if args.mode == "ads":
        cands = sorted(p for p in root.rglob("*.pdf")
                       if bid_date._AD_NAME.search(p.name) and not bid_date._NOT_AD.search(p.name))
        layer = bid_date.LAYER_ADVERTISEMENT_PDF
        label = "advertisement PDFs"
    else:
        cands = sorted(p for d in sorted(root.iterdir()) if d.is_dir()
                       for p in sorted(d.glob("*.pdf")))
        layer = bid_date.LAYER_PLAN_SET_PAGE
        label = "plan-set PDFs"

    rows, status = [], Counter()
    for p in cands:
        res = bid_date.extract_from_pdf(p, layer=layer)
        fd = folder_date(p)
        agree = ""
        if res.ok and fd:
            agree = "match" if res.bid_date == fd else "differs"
        status[res.status] += 1
        rows.append({
            "path": str(p.relative_to(root)), "status": res.status,
            "bid_date": res.bid_date or "", "bid_time": res.bid_time or "",
            "timezone": res.timezone or "", "page": res.page or "",
            "folder_date": fd or "", "agrees_with_folder": agree,
            "error": res.error or "", "raw": (res.raw or "")[:220],
        })

    n = len(rows)
    found = status[bid_date.STATUS_FOUND]
    with_time = sum(1 for r in rows if r["bid_time"])
    matched = sum(1 for r in rows if r["agrees_with_folder"] == "match")
    checkable = sum(1 for r in rows if r["agrees_with_folder"])

    print(f"{label} found : {n}")
    if n:
        print(f"  status=found           : {found}  ({found / n:.0%})")
        print(f"  status=not_found       : {status[bid_date.STATUS_NOT_FOUND]}")
        print(f"  status=error           : {status[bid_date.STATUS_ERROR]}")
        print(f"  found WITH a clock time: {with_time}  ({with_time / n:.0%} of all)")
    if checkable:
        print(f"  agrees with folder date: {matched}/{checkable}  ({matched / checkable:.0%})")
    print()
    for r in rows:
        if r["status"] != "found" or r["agrees_with_folder"] == "differs":
            print(f"  [{r['status']:9s}] {r['path']}")
            if r["error"]:
                print(f"      error : {r['error']}")
            if r["agrees_with_folder"] == "differs":
                print(f"      parsed {r['bid_date']} {r['bid_time']} vs folder {r['folder_date']}")
                print(f"      raw   : {r['raw'][:160]}")

    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()) if rows else ["path"])
            w.writeheader()
            w.writerows(rows)
        print(f"\nwrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
