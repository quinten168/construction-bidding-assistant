#!/usr/bin/env python3
"""
01_bulk_convert.py  —  PHASE 0, STEP 2: convert every plan PDF to Markdown and load `plans`.

For each <plan_id>/ folder under 00_input/plans/:
  • pick the source PDF (the manifest's primary_pdf, else the lone *.pdf in the folder),
  • convert it to Markdown by REUSING the existing read-path converter (01_pipeline/s1_convert.py —
    pymupdf4llm with a pdfplumber fallback for CAD/drawing pages, already cached to _md_cache/),
  • store full_markdown + the colocated readable .md path + convert_status on a `plans` row,
  • fill the plan's identity/metadata columns from the manifest (falling back to parsing the
    folder name if a plan has no manifest row).

Robustness (this is the path that must scale to 100+ plans):
  • IDEMPOTENT — a plan already converted (status='converted' + non-empty markdown) is skipped.
  • NON-FATAL failures — a PDF that converts empty/near-empty (pure plan-set / scanned) is logged
    to convert_failures.log, marked convert_status='failed: <reason>', and the batch CONTINUES.
    Every plan is wrapped in try/except so one crash can't kill the run.
  • RESUMABLE — because skips are based on DB state, re-running after a crash picks up where it left off.

No Anthropic API calls (Phase 0 is the zero-API critical path).

Run:
    cd 01_Summer_2026
    python3 pipelines/plan_reader/04_tools/01_bulk_convert.py --sample 5   # small test batch first
    python3 pipelines/plan_reader/04_tools/01_bulk_convert.py              # full batch
    python3 pipelines/plan_reader/04_tools/01_bulk_convert.py --force      # re-convert even if done
"""
import csv
import sys
import signal
import sqlite3
import traceback
from pathlib import Path

# A single pathological CAD PDF can send pymupdf4llm into a ~infinite 100%-CPU spin (no output).
# Guard the per-plan conversion with a hard wall-clock timeout so one bad PDF can't stall the whole
# 100+-plan batch — on timeout the plan is logged + marked failed and the run continues.
CONVERT_TIMEOUT_SECONDS = 300

class ConversionTimeout(Exception):
    pass

def _raise_timeout(signum, frame):
    raise ConversionTimeout()

# Reuse the existing read-path conversion logic. s1_convert + lib live in 01_pipeline/; putting that
# dir on sys.path lets us `import` them WITHOUT editing anything there (reuse, don't modify).
TOOLS_DIR    = Path(__file__).resolve().parent
MODULE_ROOT  = TOOLS_DIR.parent                                  # .../plan_reader
PIPELINE_DIR = MODULE_ROOT / "01_pipeline"
sys.path.insert(0, str(PIPELINE_DIR))
import lib            # noqa: E402  — shared paths + manifest helpers
import s1_convert     # noqa: E402  — convert_pages / pages_to_markdown / write_markdown

# --- paths -------------------------------------------------------------------
DB_PATH      = MODULE_ROOT / "csi_v2.db"                         # the v2 store (created by 00_init_db.py)
PLANS_DIR    = MODULE_ROOT / "00_input" / "plans"               # one folder per plan (PDFs gitignored)
MANIFEST_CSV = PLANS_DIR / "plans_manifest.csv"                  # richer metadata than the folder name
FAILURE_LOG  = TOOLS_DIR / "convert_failures.log"               # human-readable list of conversion failures

# A converted document shorter than this (after the pdfplumber fallback) is treated as a soft
# failure — almost always a pure plan-set/scanned PDF with no extractable proposal text. These are
# exactly the plans Phase 1's LLM fallback will target, so we log them rather than silently keep them.
MIN_MARKDOWN_CHARS = 500

# The `plans` columns THIS script owns. We upsert only these so a later phase's columns
# (doc_type, archetype, project_type_llm) are never clobbered by a re-run.
OWNED_COLUMNS = [
    "source_file", "state", "county", "year", "dot_project_id", "contract_id",
    "outcome", "source_pdf_path", "converted_md_path", "full_markdown", "convert_status",
]


# --- metadata helpers --------------------------------------------------------
def load_manifest():
    """Return {plan_id: row_dict} from plans_manifest.csv (empty if absent). The manifest is the
    PRIMARY source of plan metadata — it's hand-curated and cleaner than parsing the folder name."""
    if not MANIFEST_CSV.exists():
        return {}
    return {(r.get("plan_id") or "").strip(): r for r in csv.DictReader(open(MANIFEST_CSV))}


def normalize_outcome(value):
    """Map any outcome spelling to the canonical WON|LOST|NOBID, or None if not derivable.
    Outcome is NULLABLE by design — production plans have no outcome yet, and the workflow must
    run without one. The manifest uses 'bid_won'/'bid_lost'/'no_bid'; folder suffixes use
    'WON'/'LOST'/'NOBID' — we normalize all of them (the leading 'BID_' is stripped first)."""
    v = (value or "").strip().upper().replace("-", "_")
    if v.startswith("BID_"):                              # 'BID_WON' -> 'WON', 'BID_LOST' -> 'LOST'
        v = v[len("BID_"):]
    if v in ("WON", "WIN"):
        return "WON"
    if v in ("LOST", "LOSS"):
        return "LOST"
    if v in ("NOBID", "NO_BID"):
        return "NOBID"
    return None


def metadata_from_folder(plan_id):
    """Fallback metadata by parsing the folder name, e.g.
    '2023_DUNN-CO-ND_CP-13_WON' -> year 2023, county DUNN, state ND, dot_project_id CP-13, outcome WON.
    Used ONLY when a plan has no manifest row. Best-effort — missing pieces stay None."""
    parts = plan_id.split("_")
    meta = {"year": None, "state": None, "county": None, "dot_project_id": None, "outcome": None}
    if parts and parts[0].isdigit():
        meta["year"] = int(parts[0])
    # The second token looks like 'DUNN-CO-ND' (county-CO-state) — pull county + state from it.
    if len(parts) >= 2 and "-CO-" in parts[1]:
        county, _, state = parts[1].partition("-CO-")
        meta["county"] = county.title()
        meta["state"] = state
    # A trailing WON/LOST/NOBID token is the outcome; the token(s) before it are the project id.
    if len(parts) >= 3:
        last = normalize_outcome(parts[-1])
        meta["outcome"] = last
        id_tokens = parts[2:-1] if last else parts[2:]
        meta["dot_project_id"] = "-".join(id_tokens) or None
    return meta


def plan_metadata(plan_id, manifest):
    """Resolve a plan's identity/metadata columns: manifest first, folder-name parse as fallback.
    Returns a dict of the metadata subset of OWNED_COLUMNS (the PDF-path/markdown/status columns
    are filled later, after conversion)."""
    row = manifest.get(plan_id)
    if row:
        return {
            "state":          (row.get("state") or "").strip() or None,
            "county":         (row.get("county") or "").strip() or None,
            "year":           int(row["year"]) if (row.get("year") or "").strip().isdigit() else None,
            "dot_project_id": (row.get("sp_number") or "").strip() or None,   # sp_number is the DOT id
            "contract_id":    (row.get("contract_id") or "").strip() or None,
            "outcome":        normalize_outcome(row.get("outcome")),
            "source_file":    (row.get("source_file") or row.get("primary_pdf") or "").strip() or None,
        }
    # No manifest row — parse what we can from the folder name.
    fb = metadata_from_folder(plan_id)
    return {
        "state": fb["state"], "county": fb["county"], "year": fb["year"],
        "dot_project_id": fb["dot_project_id"], "contract_id": None,
        "outcome": fb["outcome"], "source_file": None,
    }


def pick_pdf(plan_dir, manifest_row):
    """Choose the source PDF for a plan: the manifest's primary_pdf if it exists in the folder,
    else the single *.pdf present. Returns a Path or None (None ⇒ a plan folder with no PDF —
    expected for the plan-set-only plans whose proposal PDF hasn't been pulled from Box yet)."""
    if manifest_row:
        primary = (manifest_row.get("primary_pdf") or "").strip()
        if primary and (plan_dir / primary).exists():
            return plan_dir / primary
    pdfs = sorted(plan_dir.glob("*.pdf"))
    return pdfs[0] if len(pdfs) >= 1 else None


# --- DB helpers --------------------------------------------------------------
def already_converted(conn, plan_id):
    """True if this plan already has a 'converted' row with non-empty markdown — the skip signal
    that makes the batch idempotent and resumable."""
    row = conn.execute(
        "SELECT convert_status, LENGTH(COALESCE(full_markdown, '')) FROM plans WHERE plan_id = ?",
        (plan_id,),
    ).fetchone()
    return bool(row) and row[0] == "converted" and row[1] > 0


def upsert_plan(conn, plan_id, values):
    """Insert or update a plans row, writing ONLY the columns this script owns. ON CONFLICT updates
    in place so later-phase columns (doc_type, archetype, project_type_llm) survive a re-run."""
    cols = ["plan_id"] + OWNED_COLUMNS
    placeholders = ", ".join("?" for _ in cols)
    updates = ", ".join(f"{c} = excluded.{c}" for c in OWNED_COLUMNS)
    sql = (
        f"INSERT INTO plans ({', '.join(cols)}) VALUES ({placeholders}) "
        f"ON CONFLICT(plan_id) DO UPDATE SET {updates}"
    )
    conn.execute(sql, [plan_id] + [values.get(c) for c in OWNED_COLUMNS])
    conn.commit()


def log_failure(plan_id, reason):
    """Append a one-line failure record to convert_failures.log (created on first failure)."""
    with open(FAILURE_LOG, "a") as f:
        f.write(f"{plan_id}\t{reason}\n")


# --- conversion --------------------------------------------------------------
def convert_one(conn, plan_dir, manifest):
    """Convert a single plan folder and upsert its row. Returns a status string:
    'converted' | 'skipped' | 'failed: <reason>'. Never raises — caller relies on that to keep going."""
    plan_id = plan_dir.name

    # Idempotency: don't re-do a plan that's already converted.
    if already_converted(conn, plan_id):
        return "skipped"

    manifest_row = manifest.get(plan_id)
    pdf = pick_pdf(plan_dir, manifest_row)
    meta = plan_metadata(plan_id, manifest)

    # A plan folder with no PDF can't be converted — record it as a failure and move on.
    if pdf is None:
        values = dict(meta, source_pdf_path=None, converted_md_path=None,
                      full_markdown=None, convert_status="failed: no PDF in folder")
        upsert_plan(conn, plan_id, values)
        log_failure(plan_id, "no PDF in folder")
        return "failed: no PDF in folder"

    # Convert (reusing s1_convert's cached hybrid path) and build the whole-document markdown.
    # Wrapped in a wall-clock timeout: a pathological PDF that spins forever is marked failed,
    # not allowed to stall the batch. (signal.alarm is safe here — main() is single-threaded.)
    signal.signal(signal.SIGALRM, _raise_timeout)
    signal.alarm(CONVERT_TIMEOUT_SECONDS)
    try:
        pages = s1_convert.convert_pages(pdf)                 # cached pymupdf4llm + pdfplumber fallback
        full_markdown = s1_convert.pages_to_markdown(pages)   # one string with <!-- page N --> markers
        md_path = s1_convert.write_markdown(pdf, pages)       # colocated readable .md (named by plan_id)
    except ConversionTimeout:
        reason = f"conversion timeout (>{CONVERT_TIMEOUT_SECONDS}s; pathological PDF)"
        values = dict(meta, source_pdf_path=str(pdf), converted_md_path=None,
                      full_markdown=None, convert_status=f"failed: {reason}")
        upsert_plan(conn, plan_id, values)
        log_failure(plan_id, reason)
        return f"failed: {reason}"
    finally:
        signal.alarm(0)   # always clear the alarm

    # A near-empty conversion means a plan-set/scanned PDF with no proposal text — soft failure.
    if len(full_markdown) < MIN_MARKDOWN_CHARS:
        reason = f"empty/near-empty conversion ({len(full_markdown)} chars; likely plan-set/scanned)"
        values = dict(meta, source_pdf_path=str(pdf), converted_md_path=str(md_path),
                      full_markdown=full_markdown or None, convert_status=f"failed: {reason}")
        upsert_plan(conn, plan_id, values)
        log_failure(plan_id, reason)
        return f"failed: {reason}"

    values = dict(meta, source_pdf_path=str(pdf), converted_md_path=str(md_path),
                  full_markdown=full_markdown, convert_status="converted")
    upsert_plan(conn, plan_id, values)
    n_pages = len(pages)
    n_fallback = sum(1 for p in pages if p.get("source") == "pdfplumber")
    fb_note = f", {n_fallback} pdfplumber-fallback pages" if n_fallback else ""
    print(f"  ✓ {plan_id}: {n_pages} pages, {len(full_markdown):,} chars{fb_note}")
    return "converted"


# --- main --------------------------------------------------------------------
def main():
    force  = "--force" in sys.argv[1:]
    sample = None
    if "--sample" in sys.argv[1:]:
        i = sys.argv.index("--sample")
        sample = int(sys.argv[i + 1])

    # Discover plan folders (skip the manifest CSV + README that live alongside them).
    plan_dirs = sorted(d for d in PLANS_DIR.iterdir() if d.is_dir())
    if sample is not None:
        plan_dirs = plan_dirs[:sample]
        print(f"SAMPLE MODE: first {len(plan_dirs)} plan(s) only\n")

    manifest = load_manifest()
    conn = sqlite3.connect(DB_PATH)

    # If --force, clear the status so already_converted() returns False and every plan re-converts.
    if force:
        conn.execute("UPDATE plans SET convert_status = NULL, full_markdown = NULL")
        conn.commit()
        print("FORCE MODE: cleared convert_status — re-converting all plans\n")

    # Convert each plan independently; one plan's crash must not abort the batch.
    counts = {"converted": 0, "skipped": 0, "failed": 0}
    failures = []
    for plan_dir in plan_dirs:
        try:
            status = convert_one(conn, plan_dir, manifest)
        except Exception as e:                            # never let one bad PDF kill the run
            status = f"failed: {type(e).__name__}: {e}"
            log_failure(plan_dir.name, status)
            # Record the failure on the row too, so the DB reflects what happened.
            try:
                upsert_plan(conn, plan_dir.name, dict(plan_metadata(plan_dir.name, manifest),
                            source_pdf_path=None, converted_md_path=None,
                            full_markdown=None, convert_status=status))
            except Exception:
                pass
            print(f"  ✗ {plan_dir.name}: {status}")
            traceback.print_exc()

        if status == "converted":
            counts["converted"] += 1
        elif status == "skipped":
            counts["skipped"] += 1
            print(f"  – {plan_dir.name}: skipped (already converted)")
        else:
            counts["failed"] += 1
            failures.append((plan_dir.name, status))

    # -- Verification --
    print("\n-- Verification --")
    print(f"  plan folders discovered : {len(plan_dirs)}")
    print(f"  converted               : {counts['converted']}")
    print(f"  skipped (already done)  : {counts['skipped']}")
    print(f"  failed                  : {counts['failed']}")
    total_rows = conn.execute("SELECT COUNT(*) FROM plans").fetchone()[0]
    print(f"  plans rows in DB        : {total_rows}")
    if failures:
        print("\n  Failures (these are the CAD/scanned/plan-set PDFs for Phase 1's LLM fallback):")
        for plan_id, reason in failures:
            print(f"    - {plan_id}: {reason}")
        print(f"\n  Full log: {FAILURE_LOG}")

    conn.close()


if __name__ == "__main__":
    main()
