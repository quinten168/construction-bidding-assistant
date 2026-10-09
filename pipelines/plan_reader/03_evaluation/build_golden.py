"""
build_golden.py  —  pre-fill the extraction-eval ground truth.

The golden dataset is ONE ROW PER PROJECT, hand-verified, and serves two jobs:
  1. EXTRACTION EVAL — diff the Plan Reader's output against these verified values.
  2. COMPARABLES — the trusted table the bid recommendation logic can query later.

The whole point of this script: a human shouldn't TYPE what a join can FILL. We
pull every field we can from the master bid table (joined on Contract_Id via the
crosswalk) and leave only the genuinely PDF-only fields blank for a human to read
off the plan. Output marks everything `verified=false` until a person signs off.

    crosswalk (box folder -> v4_contract_id)  ->  master (one row per bidder)  ->  golden row

This writes a REGENERABLE pre-fill to 02_outputs/golden_prefill.csv. The CANONICAL,
hand-verified golden lives at 00_input/golden_dataset.csv (lib.GOLDEN_CSV) — a human
consolidates the pre-fill into it, so re-running this never clobbers verified work.

Run:
    .venv/bin/python pipelines/plan_reader/03_evaluation/build_golden.py
"""
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / ".." / "01_pipeline"))  # 01_pipeline/ holds lib + step modules
import lib

REPO = lib.REPO_ROOT                          # .../01_Summer_2026
CROSSWALK = lib.SOURCE_DATA / "2026-06-08_crosswalk.csv"
MASTER    = lib.SOURCE_DATA / "2026-06-03_csi_bid_master.csv"
OUT       = lib.OUT_SCORECARDS / "golden_prefill.csv"   # regenerable; canonical = 00_input/golden_dataset.csv

# Local PDFs we've actually ingested, mapped to their Contract_Id, so the eval
# knows which golden rows have a document to extract from. Extend as you add PDFs.
LOCAL_PDF_BY_CID = {
    "1633": "SAP 032-629-048 Plan.pdf",     # Jackson MN, no-bid
    "1654": "08MQ_NonSection.pdf",           # Hand SD, no-bid
}

# Golden schema. AUTO = filled from the master join. MANUAL = read off the PDF.
COLUMNS = [
    # identifiers
    "contract_id", "project_name", "source_file",
    # AUTO from master
    "state", "county", "project_location", "date",
    "prevailing_wages", "price_of_diesel",
    "mix_tn", "grade_cy", "base_tn", "shldr_tn", "mill_sy", "crush_tn", "stock_tn", "box",
    "bid_outcome", "csi_bid_amount", "winning_bid_amount", "gross_margin",
    # MANUAL — only on the PDF, a human fills these
    "letting_number", "sp_number", "district", "time",
    "project_duration", "completion_date",
    "special_provisions", "gotcha_types", "gotcha_summary",
    # provenance / QA
    "qty_source", "verified", "manually_verified_by", "notes",
]


def load_master_by_cid():
    """Group master rows by Contract_Id."""
    rows = {}
    with open(MASTER, newline="") as f:
        for r in csv.DictReader(f):
            rows.setdefault(r["Contract_Id"], []).append(r)
    return rows


def derive_outcome(cid_rows):
    """Canonical the client outcome from the row set (see CLAUDE.md): the client won iff ITS OWN
    bid ranked 1st. Returns (outcome, csi_row_or_None)."""
    csi = next((r for r in cid_rows if r.get("Is_CSI", "").upper() == "TRUE"), None)
    if csi is None:
        return "no_bid", None
    return ("bid_won" if str(csi.get("Bid_Rank")) == "1" else "bid_lost"), csi


def build_row(cid, status, master_by_cid):
    cid_rows = master_by_cid.get(cid)
    if not cid_rows:
        return None  # crosswalk had a contract_id the master doesn't know
    any_row = cid_rows[0]                       # project-level fields are constant across bidders
    outcome, csi = derive_outcome(cid_rows)

    g = {c: "" for c in COLUMNS}
    g.update({
        "contract_id": cid,
        "project_name": any_row.get("Project_Name", ""),
        "source_file": LOCAL_PDF_BY_CID.get(cid, ""),
        # AUTO from master (project-level)
        "state": any_row.get("State", ""),
        "county": any_row.get("County", ""),
        "project_location": any_row.get("Location", ""),
        "date": any_row.get("Date", ""),
        "prevailing_wages": any_row.get("PREVAILING_WAGES", ""),
        "price_of_diesel": any_row.get("PRICE_OF_DIESEL", ""),
        "mix_tn": any_row.get("MIX_TN", ""),  "grade_cy": any_row.get("GRADE_CY", ""),
        "base_tn": any_row.get("BASE_TN", ""), "shldr_tn": any_row.get("SHLDR_TN", ""),
        "mill_sy": any_row.get("MILL_SY", ""), "crush_tn": any_row.get("CRUSH_TN", ""),
        "stock_tn": any_row.get("STOCK_TN", ""), "box": any_row.get("BOX", ""),
        "winning_bid_amount": any_row.get("Winner_Amount", ""),
        # AUTO the client-specific
        "bid_outcome": outcome,
        "csi_bid_amount": (csi or {}).get("Bid_Amount", ""),
        "gross_margin": (csi or {}).get("Margin_Pct", ""),
        # provenance: quantities came from the join, NOT yet eyeballed against the PDF
        "qty_source": "master_join",
        "verified": "false",
    })
    return g


def main():
    master_by_cid = load_master_by_cid()

    # Targets = crosswalk rows that actually carry a Contract_Id (only those join).
    targets = []
    with open(CROSSWALK, newline="") as f:
        for r in csv.DictReader(f):
            cid = (r.get("v4_contract_id") or "").strip()
            if cid:
                targets.append((cid, r.get("csi_status", "")))

    rows, missing = [], 0
    for cid, status in targets:
        g = build_row(cid, status, master_by_cid)
        if g is None:
            missing += 1
            continue
        rows.append(g)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        w.writeheader()
        w.writerows(rows)

    # Summary
    from collections import Counter
    oc = Counter(r["bid_outcome"] for r in rows)
    with_pdf = sum(1 for r in rows if r["source_file"])
    print(f"Wrote {OUT.relative_to(REPO)}")
    print(f"  {len(rows)} project rows pre-filled from the master join "
          f"({missing} crosswalk contract_ids not found in master)")
    print(f"  outcomes: {dict(oc)}")
    print(f"  rows with a LOCAL PDF to extract from: {with_pdf}  "
          f"({', '.join(r['source_file'] for r in rows if r['source_file'])})")
    print("\nNEXT (human-in-the-loop):")
    print("  • A person fills the MANUAL columns (letting_number, sp_number, district,")
    print("    project_duration, completion_date, special_provisions, gotcha_*) from the PDF.")
    print("  • Alex verifies quantities (mix_tn…) against the plan — the ~146 date+county")
    print("    key conflicts mean master quantities can be mis-attributed. Flip `verified`")
    print("    to true and set manually_verified_by as each row is checked.")


if __name__ == "__main__":
    main()
