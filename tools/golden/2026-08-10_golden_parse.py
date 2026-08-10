"""Parse the corpus's machine-readable bid item lists into one normalised table.

Source of truth is the LOCAL MIRROR, not Box. Box's on-demand files list fine but
time out on read (verified 2026-08-10: 0 of 25 random files readable, 10 patient
retries over 206s all TimeoutError, while network was fine).

Three schema variants exist across the 8 `rtv-csv-for-Bid Item List*` files:
  V1  Category,Line,Item,Quantity                      -- Item is "2104.504 DESC (S Y)"
  V2  Category, Line, Number, Description, Unit, Quantity
  V3  Category,, Line, Number,, Description, Unit, Quantity   -- padded with blank cols

Failure and empty are kept distinguishable everywhere: every parse returns a
(rows, error) pair and `error is None` is the only success signal. A file that
legitimately holds zero item rows yields ([], None); a file that could not be read
or whose header matched no known variant yields ([], "<reason>").
"""

from __future__ import annotations

import csv
import glob
import io
import os
import re
import sys
from dataclasses import dataclass, asdict

MIRROR = (
    "/Users/t/Library/Mobile Documents/com~apple~CloudDocs/"
    "00 MSBA + Coding/00_summer 2026/00_CSI_ELP/CSI ELP 2026"
)

# "2104.504 REMOVE BITUMINOUS PAVEMENT (S Y)" -> number, description, unit
_V1_ITEM = re.compile(r"^\s*(?P<num>\d{4}\.\d{3})?\s*(?P<desc>.*?)\s*(?:\((?P<unit>[^()]*)\)\s*)?$")
# MnDOT item numbers appear in two forms and BOTH are valid:
#   base      2104.503
#   extended  2104.503/00315   (the /nnnnn suffix keys a specific variant)
# An earlier version of this regex accepted only the base form and silently
# dropped 8 of the 15 Marshall rows to "no item number" -- the same
# failure-looks-like-empty shape this project keeps hitting.
_SPEC_NUM = re.compile(r"^\d{4}\.\d{3}(/\d+)?$")


@dataclass
class GoldenRow:
    source_file: str          # path relative to the mirror root
    project_folder: str       # immediate parent folder name -- the join handle
    category: str
    line: str
    spec_item_number: str     # "" when the row carries none
    description: str
    unit: str
    quantity: float | None
    quantity_raw: str
    is_alternate: bool


def _norm(s: str) -> str:
    return (s or "").replace("\xa0", " ").strip()


def _num(raw: str):
    """Return (value, error). '' is a legitimate empty -> (None, None)."""
    t = _norm(raw).replace(",", "").replace("$", "")
    if t == "":
        return None, None
    try:
        return float(t), None
    except ValueError:
        return None, f"unparseable quantity {raw!r}"


def _is_alt(category: str) -> bool:
    c = _norm(category).upper()
    return "ALTERNATE" in c or c.startswith("ALT ")


def _detect(header: list[str]) -> str | None:
    h = [_norm(x).upper() for x in header if _norm(x)]
    if not h:
        return None
    if "ITEM" in h and "QUANTITY" in h and "DESCRIPTION" not in h:
        return "V1"
    if "NUMBER" in h and "DESCRIPTION" in h and "QUANTITY" in h:
        return "V2"  # V3 is V2 with blank padding columns; index-by-name handles both
    return None


def parse_file(path: str) -> tuple[list[GoldenRow], str | None]:
    """Return (rows, error). error is None on success -- including a genuine 0 rows."""
    rel = os.path.relpath(path, MIRROR)
    folder = os.path.basename(os.path.dirname(path))
    try:
        if path.lower().endswith((".xlsx", ".xlsm")):
            recs, err = _read_xlsx(path)
        else:
            with open(path, "rb") as fh:
                raw = fh.read()
            recs = list(csv.reader(io.StringIO(raw.decode("utf-8-sig", "replace"))))
            err = None
        if err:
            return [], err
    except Exception as exc:  # noqa: BLE001 -- must not be confused with empty
        return [], f"read failed: {type(exc).__name__}: {exc}"

    recs = [r for r in recs if any(_norm(c) for c in r)]
    if not recs:
        return [], "file has no non-empty rows"

    header = recs[0]
    variant = _detect(header)
    if variant is None:
        return [], f"unrecognised header: {header!r}"

    idx = {}
    for i, name in enumerate(header):
        key = _norm(name).upper()
        if key and key not in idx:
            idx[key] = i

    def cell(row, key):
        i = idx.get(key)
        return _norm(row[i]) if i is not None and i < len(row) else ""

    out: list[GoldenRow] = []
    for row in recs[1:]:
        category = cell(row, "CATEGORY")
        line = cell(row, "LINE")
        qty_raw = cell(row, "QUANTITY")

        if variant == "V1":
            item = cell(row, "ITEM")
            m = _V1_ITEM.match(item)
            num = _norm(m.group("num") or "") if m else ""
            desc = _norm(m.group("desc") or "") if m else item
            unit = _norm(m.group("unit") or "") if m else ""
        else:
            num = cell(row, "NUMBER")
            desc = cell(row, "DESCRIPTION")
            unit = cell(row, "UNIT")

        if not (num or desc):
            continue  # blank filler row, not a failure

        qty, _qerr = _num(qty_raw)
        out.append(
            GoldenRow(
                source_file=rel,
                project_folder=folder,
                category=category,
                line=line,
                spec_item_number=num if _SPEC_NUM.match(num) else "",
                description=desc,
                unit=unit,
                quantity=qty,
                quantity_raw=qty_raw,
                is_alternate=_is_alt(category),
            )
        )
    return out, None


def _read_xlsx(path: str) -> tuple[list[list[str]], str | None]:
    try:
        import openpyxl
    except ImportError:
        return [], "openpyxl not installed"
    try:
        wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
        ws = wb[wb.sheetnames[0]]
        rows = [["" if c is None else str(c) for c in r] for r in ws.iter_rows(values_only=True)]
        wb.close()
        return rows, None
    except Exception as exc:  # noqa: BLE001
        return [], f"xlsx read failed: {type(exc).__name__}: {exc}"


def find_bid_item_lists() -> list[str]:
    return sorted(glob.glob(os.path.join(MIRROR, "**", "rtv-csv-for-Bid Item List*"), recursive=True))


def main() -> int:
    files = find_bid_item_lists()
    if not files:
        print("ERROR: glob matched zero Bid Item List files -- check MIRROR path", file=sys.stderr)
        return 2

    all_rows: list[GoldenRow] = []
    failures: list[tuple[str, str]] = []
    for f in files:
        rows, err = parse_file(f)
        rel = os.path.relpath(f, MIRROR)
        if err is not None:
            failures.append((rel, err))
            print(f"FAIL  {rel}\n      {err}")
            continue
        all_rows.extend(rows)
        print(f"ok    {len(rows):4d} rows  {rel}")

    out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)))
    out_csv = os.path.join(out_dir, "2026-08-10_golden_rows.csv")
    with open(out_csv, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(asdict(all_rows[0]).keys()) if all_rows else [])
        if all_rows:
            w.writeheader()
            for r in all_rows:
                w.writerow(asdict(r))

    print(f"\nfiles={len(files)} parsed={len(files) - len(failures)} failed={len(failures)} rows={len(all_rows)}")
    print(f"wrote {out_csv}")

    # --- coverage assertions: a zero here is a real defect, not a quiet pass ---
    problems = []
    if failures:
        problems.append(f"{len(failures)} file(s) failed to parse")
    if not all_rows:
        problems.append("zero golden rows extracted from a non-empty file set")
    with_num = sum(1 for r in all_rows if r.spec_item_number)
    if all_rows and with_num == 0:
        problems.append("no row carried a spec item number -- parser regression")
    if all_rows and not any(r.unit for r in all_rows):
        problems.append("no row carried a unit -- parser regression")
    if problems:
        print("\nCOVERAGE PROBLEMS:")
        for p in problems:
            print("  -", p)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
