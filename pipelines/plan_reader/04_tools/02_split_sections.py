#!/usr/bin/env python3
"""
02_split_sections.py  —  PHASE 0, STEP 3: split each plan's Markdown into the `sections` table.

This is the TRACK A / TRACK B handoff. We carve every converted plan's full_markdown into raw
sections (a heading + the text under it) and write one `sections` row each, leaving `section_type`
NULL. Jay's parallel track then NORMALIZES those raw headings into the canonical taxonomy — he only
needs `SELECT DISTINCT raw_heading FROM sections`, nothing from Track A's extraction logic.

How a header is detected (the lesson that shapes this):
  MN proposals come back from conversion with ENTIRE PARAGRAPHS in bold, so a naive "**bold** line is
  a header" rule would shatter the document. We instead reuse the guard philosophy from
  01_pipeline/lib.header_match — a line opens a section only if it is SHORT, is NOT a cross-reference
  ("...see the special provisions..."), and is structurally heading-like:
    • an ATX heading line ('#', '##', '### ...'),
    • an 'ARTICLE n – ...' line (the EJCDC contract format used by ND/SD county plans),
    • or an UPPERCASE-dominant short line ('STATE OF MINNESOTA', 'ADVERTISEMENT FOR BIDS').
  Long shouty paragraphs and mixed-case prose are rejected, which is what keeps MN from over-splitting.

Idempotent: a plan's existing `sections` rows are deleted before its new ones are written, so re-running
replaces rather than duplicates.

No Anthropic API calls (Phase 0 is the zero-API critical path).

Run:
    cd 01_Summer_2026
    python3 pipelines/plan_reader/04_tools/02_split_sections.py
"""
import re
import sys
import sqlite3
from collections import Counter
from pathlib import Path

# Reuse lib's cross-reference cue regex so we judge "is this a header?" the same way the read path does.
TOOLS_DIR    = Path(__file__).resolve().parent
MODULE_ROOT  = TOOLS_DIR.parent                                  # .../plan_reader
PIPELINE_DIR = MODULE_ROOT / "01_pipeline"
sys.path.insert(0, str(PIPELINE_DIR))
import lib            # noqa: E402  — for lib._CROSSREF_CUE

# --- paths -------------------------------------------------------------------
DB_PATH = MODULE_ROOT / "csi_v2.db"                             # the v2 store (created by 00_init_db.py)

# --- header detection --------------------------------------------------------
MAX_HEADING_CHARS = 80        # real headers are short; a longer line is prose (or a whole-para ATX)
MIN_HEADING_LETTERS = 3       # need ≥3 letters so bare project codes ('CP-13') aren't called headers
UPPER_DOMINANCE = 0.8         # ≥80% of the alphabetic chars uppercase ⇒ a shouted header line
MAX_HEADING_WORDS = 12        # an uppercase line longer than this is a shouted paragraph, not a header
MAX_HEADERS_PER_PAGE = 8       # a header-dense page is a *candidate* drawing — but ONLY if it's also
                              # letter-sparse (see below). Header count alone over-fires on dense PROSE.
# The fix (2026-06-15): the bare ">8 headers/page" rule wrongly pooled real proposal content — bid
# schedules, prevailing-wage tables, special provisions, spec TOCs — because their short uppercase
# spec/wage/bid-item codes ('SECTION 017005', '2360.504') trip the header test even though the page is
# letter-RICH prose. CAD label-soup is the opposite: header-dense AND letter-SPARSE (coordinate/station
# number soup). So the header rule now fires only when density is below this floor. Calibrated on the
# corpus: genuine prose pages sit at density >= 0.565 (bid schedule 0.69, wage tables 0.59-0.86, special
# provisions 0.79-0.90); genuine soup sits at <= 0.50 (Jackson plan-sheets 0.27, coordinate tables 0.34-0.46).
MAX_DRAWING_LETTER_DENSITY = 0.50  # below this AND header-dense ⇒ CAD soup; prose stays well above it

_PAGE_MARKER = re.compile(r"<!-- page (\d+) -->")               # the page boundaries s1_convert writes
_ATX = re.compile(r"^#{1,6}\s+")                                # Markdown ATX heading prefix
_ARTICLE = re.compile(r"^ARTICLE\s+[0-9IVXL]+\b", re.IGNORECASE)  # EJCDC 'ARTICLE 1 – ...'
_INTRO_HEADING = "(intro)"                                      # leading text before the first real header
# CAD/drawing pages (the 11x17 plan sheets) are number-soup: their all-caps labels ('MATCHLINE',
# 'SCALE IN FEET') aren't section headers but pass an uppercase test and would shatter the document
# into thousands of junk sections. We detect those pages with lib.is_drawing_page and pool them into
# ONE section per plan so their text is preserved but never pollutes the raw_heading handoff Jay reads.
_PLAN_SHEETS_HEADING = "(plan sheets / drawings)"


def clean_heading(raw_line):
    """Strip Markdown decoration (ATX '#', bold '**', underscores) to get the human heading text."""
    text = _ATX.sub("", raw_line.strip())
    text = re.sub(r"\*\*", "", text)            # drop bold markers
    return text.strip().strip("*_").strip()


def header_text(raw_line):
    """Return the cleaned heading IF this line opens a section, else None.
    Order matters: the length + cross-reference guards run FIRST so long TOC/dot-leader lines and
    'see ...' pointers are rejected before any accept rule can fire."""
    line = raw_line.strip()
    if not line:
        return None
    is_atx = bool(_ATX.match(line))
    text = clean_heading(line)

    # Guards (shared by every header kind): short, real, and not a pointer to another section.
    if not text or len(text) > MAX_HEADING_CHARS:
        return None
    if lib._CROSSREF_CUE.search(text.upper()):
        return None

    # Accept rules, most specific first.
    if _ARTICLE.match(text):                     # 'ARTICLE 4 – Site and Other Areas'
        return text
    if is_atx:                                   # any short ATX heading line
        return text
    # An uppercase-dominant short line: 'SPECIAL PROVISIONS', 'NOTICE TO BIDDERS'.
    letters = [c for c in text if c.isalpha()]
    if (len(letters) >= MIN_HEADING_LETTERS
            and sum(c.isupper() for c in letters) / len(letters) >= UPPER_DOMINANCE
            and len(text.split()) <= MAX_HEADING_WORDS):
        return text
    return None


# --- splitting ---------------------------------------------------------------
def pages_from_markdown(full_markdown):
    """Yield (page_number, page_text) by splitting on the '<!-- page N -->' markers s1_convert emits.
    Text before the first marker (the 'converted from ...' file header) is ignored."""
    parts = _PAGE_MARKER.split(full_markdown)
    # parts = [preamble, page_no, text, page_no, text, ...] — walk it two at a time after the preamble.
    for i in range(1, len(parts), 2):
        page_no = int(parts[i])
        text = parts[i + 1] if i + 1 < len(parts) else ""
        yield page_no, text


def is_drawing_page(page_no, page_text, map_pages, line_headings):
    """Decide whether a page is a CAD/plan-sheet rather than a prose page. Two PRIMARY signals
    (either is enough), strongest first, then a guarded fallback:
      • page_no is a tabloid (11x17) MAP page from lib.detect_structure — the robust page-SIZE signal;
      • lib.is_drawing_page — near-empty or low letter-density drawing page;
      • FALLBACK for letter-sized plan sheets the size signal misses: header-dense AND letter-sparse.
        CAD label-soup is both (dozens of all-caps fragments over coordinate/station number soup); a
        dense PROSE page (bid schedule, wage table, spec/TOC) is header-dense but letter-RICH, so the
        letter-density guard keeps it from pooling. Header count ALONE must not pool — that was the bug."""
    if page_no in map_pages:
        return True
    if lib.is_drawing_page(page_text):
        return True
    n_headers = sum(1 for h in line_headings if h is not None)
    return n_headers > MAX_HEADERS_PER_PAGE and lib.text_density(page_text) < MAX_DRAWING_LETTER_DENSITY


def split_into_sections(full_markdown, map_pages=frozenset()):
    """Carve a plan's markdown into sections. Returns a list of dicts:
        {raw_heading, raw_text, page_start, page_end}
    A section runs from its heading line until the next heading (text carries forward across page
    boundaries). Text before the first heading becomes a leading '(intro)' section so nothing is lost.
    `map_pages` is the set of tabloid drawing pages from lib.detect_structure (pooled, not sectioned)."""
    sections = []
    current = None

    def open_section(heading, page_no, first_line):
        # Start a fresh section; the heading line is kept in raw_text too so the body is complete.
        return {"raw_heading": heading, "lines": [first_line],
                "page_start": page_no, "page_end": page_no}

    for page_no, page_text in pages_from_markdown(full_markdown):
        lines = page_text.splitlines()
        line_headings = [header_text(l) for l in lines]      # detect once; reused below

        # CAD/drawing page: don't scan it for headers. Pool its text into one running
        # '(plan sheets / drawings)' section so the content is kept but the headings stay clean.
        if is_drawing_page(page_no, page_text, map_pages, line_headings):
            if current is None or current["raw_heading"] != _PLAN_SHEETS_HEADING:
                if current is not None:
                    sections.append(current)
                current = open_section(_PLAN_SHEETS_HEADING, page_no, page_text)
            else:
                current["lines"].append(page_text)
            current["page_end"] = page_no
            continue

        for raw_line, heading in zip(lines, line_headings):
            if heading is not None:
                # A new heading closes the section in progress and opens the next.
                if current is not None:
                    sections.append(current)
                current = open_section(heading, page_no, raw_line)
            else:
                # Body text — start an intro section if we haven't seen any heading yet.
                if current is None:
                    current = open_section(_INTRO_HEADING, page_no, raw_line)
                else:
                    current["lines"].append(raw_line)
                current["page_end"] = page_no

    if current is not None:
        sections.append(current)

    # Materialize raw_text and drop sections that ended up with no real content.
    out = []
    for s in sections:
        raw_text = "\n".join(s["lines"]).strip()
        if not raw_text:
            continue
        out.append({"raw_heading": s["raw_heading"], "raw_text": raw_text,
                    "page_start": s["page_start"], "page_end": s["page_end"]})
    return out


# --- DB helpers --------------------------------------------------------------
def converted_plans(conn):
    """(plan_id, source_pdf_path, full_markdown) for every plan that converted with usable markdown."""
    return conn.execute(
        "SELECT plan_id, source_pdf_path, full_markdown FROM plans "
        "WHERE convert_status = 'converted' AND COALESCE(full_markdown, '') <> ''"
    ).fetchall()


def map_pages_for(pdf_path):
    """Set of 1-based tabloid (11x17) drawing page numbers via lib.detect_structure — the robust
    page-SIZE signal for 'this is a plan sheet, not prose'. Empty set if the PDF isn't on disk
    (PDFs are gitignored) — the per-page text signals still catch drawing pages without it."""
    if not pdf_path or not Path(pdf_path).exists():
        return frozenset()
    try:
        return frozenset(lib.detect_structure(pdf_path)["map_pages"])
    except Exception:
        return frozenset()


def write_sections(conn, plan_id, sections):
    """Replace this plan's sections with the freshly split set (idempotent per plan). section_type and
    the other downstream columns are left NULL — that's Jay's normalization job, a later phase."""
    conn.execute("DELETE FROM sections WHERE plan_id = ?", (plan_id,))
    conn.executemany(
        "INSERT INTO sections (plan_id, raw_heading, page_start, page_end, raw_text) "
        "VALUES (?, ?, ?, ?, ?)",
        [(plan_id, s["raw_heading"], s["page_start"], s["page_end"], s["raw_text"]) for s in sections],
    )
    conn.commit()


# --- main --------------------------------------------------------------------
def main():
    conn = sqlite3.connect(DB_PATH)
    plans = converted_plans(conn)

    per_plan_counts = []
    for plan_id, source_pdf_path, full_markdown in plans:
        map_pages = map_pages_for(source_pdf_path)               # tabloid drawing pages to pool, not section
        sections = split_into_sections(full_markdown or "", map_pages)
        write_sections(conn, plan_id, sections)
        per_plan_counts.append((plan_id, len(sections)))
        print(f"  ✓ {plan_id}: {len(sections)} sections  ({len(map_pages)} drawing pages pooled)")

    # -- Verification --
    print("\n-- Verification --")
    total = conn.execute("SELECT COUNT(*) FROM sections").fetchone()[0]
    n_null_type = conn.execute("SELECT COUNT(*) FROM sections WHERE section_type IS NULL").fetchone()[0]
    n_with_heading = conn.execute(
        "SELECT COUNT(*) FROM sections WHERE COALESCE(raw_heading,'') <> '' AND COALESCE(raw_text,'') <> ''"
    ).fetchone()[0]
    print(f"  plans split            : {len(plans)}")
    print(f"  total sections         : {total}")
    print(f"  rows with heading+text : {n_with_heading}")
    print(f"  section_type IS NULL   : {n_null_type}  (expect = total — Jay fills these)")

    print("\n  Per-plan section counts:")
    for plan_id, n in sorted(per_plan_counts):
        print(f"    {plan_id:42s}: {n}")

    # The 20 most common raw headings — the sanity check that headings are real (Jay's starting point).
    print("\n  20 most common raw_heading values (the Track-B handoff view):")
    headings = [r[0] for r in conn.execute(
        "SELECT raw_heading FROM sections WHERE raw_heading <> ?", (_INTRO_HEADING,)).fetchall()]
    for heading, n in Counter(headings).most_common(20):
        print(f"    {n:4d}  {heading}")

    conn.close()


if __name__ == "__main__":
    main()
