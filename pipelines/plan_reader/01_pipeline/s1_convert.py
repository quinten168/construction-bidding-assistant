"""
s1_convert.py  —  STEP 0: turn a plan PDF into structure-preserving Markdown.

    PDF  ->  Markdown (headings, tables, lists kept)  ->  cached on disk

WHY this step exists (the lesson):
  The old ingest fed pdfplumber's `.extract_text()` — a FLAT wall of text — straight
  into the vector DB. Two things got lost that matter most for bid extraction:
    • TABLES. The bid schedule (quantities: MIX_TN, GRADE_CY, …) and the special
      provisions are tables. Flattened, a quantity table becomes "number-soup": rows
      and headers smeared together, so a chunk for "estimated quantities" can't be
      matched or read back cleanly.
    • HEADINGS. Section headers ("SPECIAL PROVISIONS") are the anchors `detect_section`
      keys on. Markdown keeps them as `#`-prefixed lines, giving the tagger cleaner hits.

  pymupdf4llm (PyMuPDF's Markdown writer) is the locked OSS choice: fast, CPU-only,
  emits real Markdown tables and ATX headings, and can chunk page-by-page so we keep
  the exact `page` number every downstream citation needs. MarkItDown is reserved for
  the *non-PDF* corpus (Excel pricing sheets, Word); docling/LlamaParse are the
  OCR-capable fallback for scanned plans — see the module README.

PERFORMANCE (why caching exists — measured 2026-06-10):
  Conversion costs ~1.2s/PAGE on graphics-dense CAD plans (a 139-pp / 42 MB plan
  takes ~2.5 min; the 619-pp Watonwan ~12 min); light text PDFs are fast (Otter Tail,
  34 pp / 1.4 MB → 4.4s). Measured surprise: the cost is pymupdf4llm's per-page
  layout/word extraction, NOT table detection — `table_strategy=None` ran the SAME
  46s and still found the SAME 18 tables on a 40-page slice. So there is no cheap
  "turn tables off to go fast" lever. The fix is to convert ONCE and CACHE:
    • Converted Markdown is cached on disk (keyed on PDF path + mtime). Ingest /
      scorecard / demo all reuse it — a 2nd call is instant (0.000s).
    • `table_strategy` stays exposed (a valid pymupdf4llm kwarg) for experimentation,
      but it is NOT a performance knob — leave it at the default to keep bid-schedule
      tables, which convert cleanly (the quantity rows survive as real Markdown tables).

Run:
    python3 pipelines/plan_reader/01_pipeline/s1_convert.py <plan.pdf>            # write cache + readable .md, print stats
    python3 .../01_pipeline/s1_convert.py <plan.pdf> --print                      # also dump the Markdown to stdout
    python3 .../01_pipeline/s1_convert.py <plan.pdf> --no-md                       # skip the readable .md (cache only)
    python3 .../01_pipeline/s1_convert.py pipelines/plan_reader/00_input/plans       # convert whole corpus (warm the cache)

INSPECTABILITY (2026-06-11): besides the machine-readable JSON cache (00_input/_md_cache/,
which keeps per-page n_tables/n_images/source that downstream steps need), every run now
also writes a HUMAN-READABLE Markdown file NEXT TO the source PDF, named by plan:
00_input/plans/<plan_id>/<plan_id>.md (see write_markdown + lib.plan_id_for) — open it to SEE the
converted plan with tables, headings, and <!-- page N --> markers intact. The .md is derived
from the same pages as the cache, so they can't drift.
"""
import sys
import hashlib
import json
import time
from functools import lru_cache
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # so `import lib` works
import lib

# Converted Markdown is cached here (gitignored — it's regenerable from the PDFs).
CACHE_DIR = lib.DATA_DIR / "_md_cache"
# Default: keep tables (right for proposals/bid schedules). "lines_strict" is
# pymupdf4llm's default; we name it so callers can override or disable (None).
DEFAULT_TABLE_STRATEGY = "lines_strict"


# Pages whose Markdown comes back shorter than this are treated as "pymupdf gave up"
# (pure CAD/drawing pages) and back-filled from pdfplumber. Measured need: on image/
# drawing-heavy SD plans pymupdf4llm returns EMPTY markdown for most pages, while
# pdfplumber still recovers the (messy but real) title-block / stationing / note text —
# e.g. Yankton, a CSI win, loses 124/144 pages without this fallback.
HYBRID_MIN_CHARS = 100


# --- caching: keyed by PDF CONTENT HASH, not filename ------------------------------------------
# WHY (2026-06-25): the cache used to key on the PDF's filename stem + mtime. But the chat UI saves
# every upload under a fresh random UUID, so the SAME plan dropped twice never hit the cache and got
# fully re-converted (~2.5 min on a 252-pp plan). Keying on the file's content hash makes a re-drop
# of any previously-seen PDF instant regardless of its upload name, and is immune to mtime drift.
# Legacy stem-keyed caches are still honored on read and migrated forward (see _read_cache).
@lru_cache(maxsize=128)
def _content_key(path_str: str, size: int, mtime: float) -> str:
    """md5 of the file bytes (first 16 hex). Memoized on (path, size, mtime) so we hash each file
    at most once per process; ~50ms for a 21 MB PDF."""
    h = hashlib.md5()
    with open(path_str, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def _hash(pdf_path: Path) -> str:
    st = pdf_path.stat()
    return _content_key(str(pdf_path), st.st_size, st.st_mtime)


def _cache_path(pdf_path: Path) -> Path:
    return CACHE_DIR / (_hash(pdf_path) + ".json")            # raw pymupdf pages


def _hybrid_cache_path(pdf_path: Path) -> Path:
    return CACHE_DIR / (_hash(pdf_path) + ".hybrid.json")     # pymupdf + pdfplumber fallback


def _read_cache(pdf_path: Path, suffix: str):
    """Return cached pages or None. A content-hash hit is ALWAYS valid (content can't change without
    the hash changing). On miss, fall back to a legacy stem-keyed cache (newer than the PDF) and
    migrate it forward to the hash key, so the 192 pre-existing caches keep working and become
    reusable under any upload filename."""
    hp = CACHE_DIR / (_hash(pdf_path) + suffix)
    if hp.exists():
        return json.loads(hp.read_text())
    legacy = CACHE_DIR / (pdf_path.stem + suffix)
    if legacy.exists() and legacy.stat().st_mtime >= pdf_path.stat().st_mtime:
        data = json.loads(legacy.read_text())
        try:
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            hp.write_text(json.dumps(data))                  # migrate stem → hash for future drops
        except Exception:
            pass
        return data
    return None


def _write_cache(pdf_path: Path, suffix: str, data) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    (CACHE_DIR / (_hash(pdf_path) + suffix)).write_text(json.dumps(data))


def _pymupdf_pages(pdf_path, table_strategy, use_cache):
    """The raw pymupdf4llm Markdown pages (the slow step), cached on disk by content hash."""
    if use_cache and (cached := _read_cache(pdf_path, ".json")) is not None:
        return cached
    import pymupdf4llm
    kwargs = dict(page_chunks=True, show_progress=False)
    if table_strategy is not None:
        kwargs["table_strategy"] = table_strategy
    raw = pymupdf4llm.to_markdown(str(pdf_path), **kwargs)
    pages = [{
        "page": i,
        "text": pg.get("text") or "",
        "n_tables": len(pg.get("tables") or []),
        "n_images": len(pg.get("images") or []),
        "source": "markdown",
    } for i, pg in enumerate(raw, start=1)]
    _write_cache(pdf_path, ".json", pages)
    return pages


def _apply_pdfplumber_fallback(pdf_path, pages):
    """For pages where pymupdf produced almost no text, substitute pdfplumber's raw text
    (which recovers fragmented CAD-drawing text pymupdf drops). Only opens the empty pages,
    so it's cheap. Returns the merged pages and the count back-filled."""
    weak = [p for p in pages if len(p["text"].strip()) < HYBRID_MIN_CHARS]
    if not weak:
        return pages, 0
    import pdfplumber
    filled = 0
    with pdfplumber.open(pdf_path) as pdf:
        for p in weak:
            idx = p["page"] - 1
            if 0 <= idx < len(pdf.pages):
                txt = pdf.pages[idx].extract_text() or ""
                if len(txt.strip()) >= HYBRID_MIN_CHARS:
                    p["text"] = txt
                    p["source"] = "pdfplumber"
                    filled += 1
    return pages, filled


def convert_pages(pdf_path, table_strategy=DEFAULT_TABLE_STRATEGY, use_cache=True, hybrid=True):
    """Convert a PDF to per-page text. Returns a list of page dicts:
        {"page": 1-based int, "text": str, "n_tables": int, "n_images": int, "source": str}

    By default uses the HYBRID path: pymupdf4llm Markdown (tables/headings) with a
    pdfplumber fallback for pages pymupdf leaves empty (CAD drawings). Mirrors
    indexer.extract_pages so ingest can consume it. Cached to disk; pass
    hybrid=False for the pure-pymupdf output, use_cache=False to force rebuild."""
    pdf_path = Path(pdf_path)
    if not hybrid:
        return _pymupdf_pages(pdf_path, table_strategy, use_cache)

    if use_cache and (cached := _read_cache(pdf_path, ".hybrid.json")) is not None:
        return cached
    pages = _pymupdf_pages(pdf_path, table_strategy, use_cache)
    pages, _ = _apply_pdfplumber_fallback(pdf_path, pages)
    _write_cache(pdf_path, ".hybrid.json", pages)
    return pages


def convert_pages_iter(pdf_path, **kw):
    """Yield (page_number, markdown_text) — the drop-in shape ingest consumes."""
    for pg in convert_pages(pdf_path, **kw):
        yield pg["page"], pg["text"]


def pages_to_markdown(pages) -> str:
    """Join already-converted page dicts into one Markdown string with page markers.
    Split out from to_markdown so callers that already hold `pages` (main, write_markdown)
    don't re-read the cache."""
    parts = []
    for pg in pages:
        if pg["text"].strip():
            parts.append(f"\n\n<!-- page {pg['page']} -->\n\n{pg['text']}")
    return "".join(parts).strip()


def to_markdown(pdf_path, **kw) -> str:
    """Whole document as one Markdown string with page markers (mirrors extract's
    page-tagged text, but Markdown). Used by the demo brief and ad-hoc inspection."""
    return pages_to_markdown(convert_pages(pdf_path, **kw))


def write_markdown(pdf_path, pages) -> Path:
    """Write the human-readable Markdown NEXT TO its source PDF, named by plan_id:
    00_input/plans/<plan_id>/<plan_id>.md (e.g. .../2025_DOUGLAS-CO-MN_SAP-021-600-023_NOBID.md).
    This is the INSPECTION artifact: openable, with tables/headings/page markers, unlike the
    JSON cache. Named by plan (via lib.plan_id_for) so you know which plan it is at a glance;
    falls back to the PDF stem for ad-hoc PDFs not in the manifest. Returns the path."""
    pdf_path = Path(pdf_path)
    name = lib.plan_id_for(pdf_path.stem)              # plan_id, or the stem if unknown
    out = pdf_path.parent / f"{name}.md"               # colocated with the PDF
    header = f"<!-- converted from {pdf_path.name} — {len(pages)} pages -->\n"
    out.write_text(header + pages_to_markdown(pages))
    return out


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    do_print = "--print" in sys.argv[1:]
    no_cache = "--no-cache" in sys.argv[1:]
    no_md = "--no-md" in sys.argv[1:]
    if not args:
        print(__doc__)
        sys.exit(1)

    # Accept a dir (convert the whole corpus to warm the cache) or single PDFs.
    pdfs = []
    for a in args:
        p = Path(a)
        pdfs.extend(sorted(p.rglob("*.pdf")) if p.is_dir() else [p])

    for pdf in pdfs:
        # check cache existence BEFORE converting (convert writes it, so a post-check is useless)
        was_cached = (not no_cache) and _read_cache(pdf, ".hybrid.json") is not None
        t0 = time.time()
        pages = convert_pages(pdf, use_cache=not no_cache)
        secs = time.time() - t0
        chars = sum(len(p["text"]) for p in pages)
        tables = sum(p["n_tables"] for p in pages)
        fb = sum(1 for p in pages if p.get("source") == "pdfplumber")
        cached = "cached" if was_cached else "built"
        fb_note = f", {fb} pdfplumber-fallback pages" if fb else ""
        print(f"  ✓ {pdf.name}: {len(pages)} pages, {tables} tables, "
              f"{chars:,} chars{fb_note} ({cached}, {secs:.1f}s)")
        if not no_md:
            md_path = write_markdown(pdf, pages)
            print(f"      ↳ readable markdown: {md_path}")
        if do_print:
            print("\n" + pages_to_markdown(pages))


if __name__ == "__main__":
    main()
