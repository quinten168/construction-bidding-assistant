"""
lib.py — shared helpers + the SINGLE place every path in the Plan Reader module
is defined. Every 01_pipeline/, 03_evaluation/, and 04_tools/ script imports this so they agree on:

  • WHERE everything lives  (data, outputs, chroma, the .env key, the repo's 01_data)
  • WHICH embedding model + collection is used (retrieval breaks silently if these drift)
  • HOW to load a sibling step module (`load_step`, since step files start with digits)

Teaching note: a vector DB stores, for each chunk, an embedding (a list of
~384 floats for MiniLM). At query time we embed the *question* with the SAME
model and ask the DB for the chunks whose vectors are closest. "Closest" here
means cosine similarity (angle between vectors), which we set explicitly below.
"""
import importlib.util
from pathlib import Path

# ── 1. Locations — every path the module uses, defined ONCE ──────────────────
# lib.py lives in  .../plan_reader/01_pipeline/ , so the module root is its parent. The numbered
# folders read as the workflow: 00_input → 01_pipeline → 02_outputs → 03_evaluation → 04_tools →
# 05_knowledge → 06_chroma → 07_archive. CHANGE A PATH HERE, NOT PER-SCRIPT.
PIPELINE_DIR    = Path(__file__).resolve().parent      # .../plan_reader/01_pipeline  (the read-path scripts)
MODULE_ROOT     = PIPELINE_DIR.parent                  # .../plan_reader
TOOLS_DIR       = MODULE_ROOT / "04_tools"             # occasional utilities
EVAL_DIR        = MODULE_ROOT / "03_evaluation"        # golden + scoring + rag report
REPO_ROOT       = MODULE_ROOT.parents[1]               # .../01_Summer_2026  (plan_reader→02_modules→repo)

DATA_DIR     = MODULE_ROOT / "00_input"                # the corpus + ground truth
PLANS_DIR    = DATA_DIR / "plans"                      # corpus: one folder per project (PDFs gitignored)
MANIFEST     = PLANS_DIR / "plans_manifest.csv"        # per-plan provenance, source of truth
GOLDEN_CSV   = DATA_DIR / "golden_dataset.csv"         # extraction-eval ground truth
LEDGER_CSV   = DATA_DIR / "section_tag_ledger.csv"     # human-confirmed section-tag verdicts (optional)
SOURCE_DATA  = REPO_ROOT / "01_data"                   # crosswalk + master csv (READ-ONLY)

# ── The domain-knowledge home (the canonical, revisable taxonomies that DRIVE the code) ──
# Principle: domain knowledge is DATA, code is the engine. Adding a plan that reveals a new
# section/gotcha/archetype = add a row to a knowledge/ file + re-run, NOT a code edit.
# See knowledge/KNOWLEDGE.md for the index (each concept -> source file -> consuming code).
KNOWLEDGE_DIR   = MODULE_ROOT / "05_knowledge"
SECTION_TAXONOMY_CSV = KNOWLEDGE_DIR / "section_taxonomy.csv"  # (doc_type,section)->relevance,tier — the v2 two-axis map
GOTCHA_CSV      = KNOWLEDGE_DIR / "gotcha_taxonomy.csv"        # data twin of taxonomy.py (Alex marks this up)
ARCHETYPES_CSV  = KNOWLEDGE_DIR / "project_archetypes.csv"     # the 5 archetypes (lifted out of extract's prompt)
DISPOSITION_CSV = SECTION_TAXONOMY_CSV                         # back-compat alias (was data/section_disposition.csv)

OUTPUTS_DIR  = MODULE_ROOT / "02_outputs"              # all generated artifacts (date-prefixed)
# 02_outputs/ is organized into three subfolders by purpose (every writer references these, not literals):
OUT_PER_PLAN   = OUTPUTS_DIR / "per_plan"              # per-run inspection: briefs, ingest traces, retrieved chunks
OUT_SCORECARDS = OUTPUTS_DIR / "scorecards"            # extraction scorecard / eval diff + Claude extraction cache
OUT_DIAG       = OUTPUTS_DIR / "diagnostics"           # diagnostic reports (boilerplate scan, etc.)
RESULTS_CSV  = OUTPUTS_DIR / "results.csv"             # WIDE aggregator: one row per plan, upserted (see upsert_csv)
FLAGS_CSV    = OUTPUTS_DIR / "flags.csv"               # LONG aggregator: one row per flagged gotcha/item (see replace_rows)
CHROMA_DIR   = MODULE_ROOT / "06_chroma"               # persistent vector DB (gitignored)
ENV_PATH     = MODULE_ROOT / ".env"                    # Anthropic key (single-quoted, gitignored)
# Note: the readable per-plan Markdown + JSON are written NEXT TO each source PDF as
# input/plans/<plan_id>/<plan_id>.{md,json} (see convert.write_markdown / write_json) — not a central dir.


def load_step(filename, base=None):
    """Import a module by FILENAME from a given dir (default 01_pipeline/). The 2026-06-11 rename
    dropped the digit prefixes, so step modules now have importable names — scripts use plain
    `import convert` etc. This helper survives for the one path-robust caller (lib's own
    taxonomy load) and any ad-hoc cross-dir import; pass base=TOOLS_DIR for a tool."""
    path = (base or PIPELINE_DIR) / filename
    modname = "plr_" + path.stem.replace("-", "_")
    spec = importlib.util.spec_from_file_location(modname, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def plan_id_for(pdf_stem):
    """Map a PDF stem → its readable plan_id via the manifest (e.g. '9804001' →
    '2025_DOUGLAS-CO-MN_SAP-021-600-023_NOBID'). Falls back to the stem for ad-hoc PDFs not
    in the manifest. Lives in lib (not indexer.load_manifest) so `convert` can name files by
    plan without importing indexer — indexer imports convert, which would be circular. Cached."""
    import csv as _csv
    cache = getattr(plan_id_for, "_cache", None)
    if cache is None:
        cache = {}
        if MANIFEST.exists():
            for row in _csv.DictReader(open(MANIFEST)):
                pid = (row.get("plan_id") or "").strip()
                for col in ("source_file", "primary_pdf"):
                    fn = (row.get(col) or "").strip()
                    if fn and pid:
                        cache[Path(fn).stem] = pid
        plan_id_for._cache = cache
    return cache.get(pdf_stem, pdf_stem)


def upsert_csv(path, key, row, columns):
    """Upsert one row into a CSV keyed on `row[key]`, MERGING with any existing row — read the
    file, find the row whose key matches, and overwrite a column only when `row` supplies a
    non-empty value for it (else keep what's there). This is what makes results.csv a RUNNING
    table (one row per plan, never duplicated) that ACCUMULATES: a full `run.py inspect` fills
    fields + RAG answers + meta, while a later `extract`-only run updates just the fields it has
    without wiping the RAG/meta columns. `row` may carry extra keys; only `columns` are written."""
    import csv as _csv
    path = Path(path)
    rows = {}
    if path.exists():
        for r in _csv.DictReader(open(path)):
            rows[r.get(key, "")] = dict(r)
    kv = str(row.get(key, ""))
    merged = dict(rows.get(kv, {}))
    for c in columns:
        v = row.get(c)
        if v is not None and str(v) != "":
            merged[c] = v
        merged.setdefault(c, "")
    merged[key] = kv
    rows[kv] = merged
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="") as f:
        w = _csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
        w.writeheader()
        for r in rows.values():
            w.writerow({c: r.get(c, "") for c in columns})


def replace_rows(path, key, key_value, rows, columns):
    """Replace ALL rows where row[key]==key_value with `rows`, keeping every other row. The
    multi-row-per-plan analogue of upsert_csv — used for the long flags.csv (one row per gotcha):
    re-running a plan REPLACES its set of flags instead of duplicating them. `rows` is a list of dicts."""
    import csv as _csv
    path = Path(path)
    kept = []
    if path.exists():
        kept = [r for r in _csv.DictReader(open(path)) if r.get(key) != str(key_value)]
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="") as f:
        w = _csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
        w.writeheader()
        for r in kept:
            w.writerow({c: r.get(c, "") for c in columns})
        for r in rows:
            w.writerow({c: r.get(c, "") for c in columns})


def mark_processed(plan_id, date):
    """Record in the plans manifest that a plan was processed: set extracted=TRUE and
    last_processed=<date> on its row (adding the last_processed column if absent). This makes
    input/plans/plans_manifest.csv the live 'what have we processed' tracker. No-op if the manifest
    or the plan_id row is missing. Preserves all other columns/rows."""
    import csv as _csv
    if not MANIFEST.exists():
        return
    rows = list(_csv.DictReader(open(MANIFEST)))
    if not rows:
        return
    fields = list(rows[0].keys())
    if "last_processed" not in fields:
        fields.append("last_processed")
    hit = False
    for r in rows:
        if (r.get("plan_id") or "").strip() == plan_id:
            r["extracted"], r["last_processed"], hit = "TRUE", date, True
    if not hit:
        return
    with open(MANIFEST, "w", newline="") as f:
        w = _csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fields})


def page_section_map(collection, plan_id):
    """{page_number: section} for one plan, from the ingested chunk metadata — lets each extracted
    flag be tagged with WHERE it came from. First section seen per page wins (the page's opener)."""
    metas = collection.get(where={"doc_id": plan_id}, include=["metadatas"])["metadatas"]
    out = {}
    for m in metas:
        pg = m.get("page")
        if pg and pg not in out:
            out[pg] = m.get("section", "")
    return out


def write_json(pdf_path, record):
    """Write the per-PDF extraction record as JSON NEXT TO its PDF, named by plan_id:
    00_input/plans/<plan_id>/<plan_id>.json. This is the schema's SOURCE OF TRUTH (results.csv is a
    flattened view of it). Mirrors convert.write_markdown's colocate-and-name-by-plan convention."""
    import json as _json
    pdf_path = Path(pdf_path)
    out = pdf_path.parent / f"{plan_id_for(pdf_path.stem)}.json"
    out.write_text(_json.dumps(record, indent=2, ensure_ascii=False))
    return out


# ── 2. The embedding model ───────────────────────────────────────────────────
# all-MiniLM-L6-v2: 384-dim, ~80MB, fast, runs on CPU. The locked-stack default.
# Downloaded once to your HuggingFace cache on first use, then reused offline.
EMBED_MODEL = "all-MiniLM-L6-v2"
COLLECTION  = "csi_plans"


def get_collection():
    """Open (or create) the persistent ChromaDB collection with our embedding
    function attached. Because the embedding function is bound to the collection,
    Chroma auto-embeds documents on .add/.upsert AND questions on .query — so we
    never hand-roll vectors and ingest/query can't drift apart."""
    import chromadb
    from chromadb.utils import embedding_functions

    client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    ef = embedding_functions.SentenceTransformerEmbeddingFunction(model_name=EMBED_MODEL)
    # hnsw:space=cosine -> rank chunks by cosine similarity (standard for text).
    return client.get_or_create_collection(
        name=COLLECTION,
        embedding_function=ef,
        metadata={"hnsw:space": "cosine"},
    )


# ── 3. Chunking ──────────────────────────────────────────────────────────────
# WHY chunk at all? Two reasons:
#   (a) Embeddings compress meaning — a whole 200-page plan into one vector loses
#       everything. Small chunks keep each vector "about one thing," so retrieval
#       is precise.
#   (b) We only feed the top-k retrieved chunks to Claude, so chunks must be small
#       enough that a handful fit in the prompt.
#
# We target ~350 words (~500 tokens) per chunk with ~50 words of overlap. Overlap
# means a fact straddling a chunk boundary still lands wholly inside one chunk.
#
# "Sentence-aware": we never cut mid-sentence (a half-sentence embeds poorly), so
# we split into sentences first, then pack sentences into chunks.
import re

_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9])")


def split_sentences(text: str):
    """Lightweight sentence splitter (regex). nltk.sent_tokenize is a fancier
    alternative, but this avoids the punkt-data download and is plenty for plans."""
    # Collapse runs of whitespace/newlines first so word counts are honest.
    text = re.sub(r"[ \t]+", " ", text)
    # Split on hard line breaks too — plan docs are full of them.
    pieces = []
    for line in text.split("\n"):
        line = line.strip()
        if not line:
            continue
        pieces.extend(s.strip() for s in _SENT_SPLIT.split(line) if s.strip())
    return pieces


# ── Section detection ────────────────────────────────────────────────────────
# Plans are long but structured: a header like "SPECIAL PROVISIONS" introduces a
# block that runs for many pages until the next header. We tag each chunk with the
# section it falls under, for two payoffs:
#   • CITATIONS — "found in Special Provisions, p.112"
#   • SOFT FILTERING — optionally restrict a query to a section (a metadata `where`)
#
# IMPORTANT (the lesson): this is a *soft* signal, never a hard gate. State DOTs
# (MN/ND/SD) format differently and gotchas leak across sections — a phasing rule
# can live in General Notes. So we tag, and let the eval decide if filtering helps.
# It's heuristic v1: detect short, header-like LINES (not prose mentions), most
# specific patterns first.
#
# v2 (2026-06-09): added `contract_front` for the EJCDC/county procurement+contract
# front-matter that dominates ND county plans (Dunn, Walsh). Before this, those pages
# matched nothing, so `title_index` (from "TABLE OF CONTENTS") carried forward across
# the whole document — 42% of ND probes mislabeled. See 2026-06-09_field_location_map.md.
# NOTE: this does NOT help SD DOT *plan sets* (drawings) — they have almost no prose
# headers; sectioning those needs document-type detection, a separate task.
# v3 (2026-06-10): encode Alex (estimator) process. SPLIT the high-value few labels out of the
# coarse buckets so the two-axis taxonomy (knowledge/section_taxonomy.csv) can give each its own
# relevance (DECISION/PRICING/BOILERPLATE) + tier. Precedence (first match wins) is deliberate:
#   • the split labels (agreement/bonds_forms/eeo_federal/general_conditions) come BEFORE the
#     residual contract_front catch-all, so the Agreement (a DECISION source) no longer hides
#     inside down-weighted contract boilerplate.
#   • prevailing_wage stays FIRST so ND wage text physically inside the contract front is tagged
#     wages (PRICING, kept) before any contract section can claim — and before a DROP can apply.
#   • geotechnical/typical_sections peel off specifications; prosecution_of_work off special_provisions.
SECTION_PATTERNS = [
    ("prevailing_wage",  r"DAVIS[- ]BACON|PREVAILING WAGE|WAGE DETERMINATION|MINIMUM WAGE RATE"),
    ("traffic_staging",  r"TRAFFIC CONTROL|\bSTAGING\b|\bPHASING\b|CONSTRUCTION SEQUENC|TRANSPORTATION MANAGEMENT"),
    ("bid_schedule",     r"BID SCHEDULE|SCHEDULE OF PRICES|PAY ITEMS?|ESTIMATED QUANTITIES|PROPOSAL FORM|SCHEDULE OF ITEMS|\bBID FORM\b"),
    # Agreement — Alex: holds the substantial-completion date / contract time = "key piece of info".
    # Split from contract_front and ordered before it so the Agreement is a KEEP/DECISION section.
    # Match the Agreement-FORM language, NOT a bare "AGREEMENT" (which appears in running
    # headers/footers on every contract page and would re-tag the whole boilerplate block).
    ("agreement",        r"THIS AGREEMENT|AGREEMENT BETWEEN|SUBSTANTIAL COMPLETION|CONTRACT TIMES?\b"),
    # Provably-safe contract boilerplate Alex skips — split out so they're individually DROP-able.
    ("bonds_forms",      r"PERFORMANCE BOND|PAYMENT BOND|\bBID BOND\b|PENAL SUM"),
    ("eeo_federal",      r"EQUAL EMPLOYMENT|\bEEO\b|REQUIRED CONTRACT PROVISIONS|FEDERAL[- ]AID"),
    ("general_conditions", r"STANDARD GENERAL CONDITIONS|SUPPLEMENTARY CONDITIONS"),
    # The richest decision page (location, work type, job length, completion). Alex: state-agnostic
    # — the first couple of proposal pages carry it. (Content markers here; a POSITION rule in
    # page_sections() also tags the front pages of a proposal that lack these exact keywords.)
    # Ordered before special_provisions so a front page that *references* the SP tags as front, not SP.
    ("proposal_front_data", r"PROPOSAL FOR (HIGHWAY|ROAD) CONSTRUCTION|PROPOSAL OF \(NAME\)|CLASS OF WORK|"
                            r"FOR HIGHWAY CONSTRUCTION|TYPE OF WORK|LENGTH .{0,12}MILES"),
    # MnDOT 1804 "Prosecution and Progress" — where project phasing/staging lives (DECISION).
    ("prosecution_of_work", r"PROSECUTION (AND PROGRESS )?OF WORK|SEQUENCE OF OPERATIONS"),
    ("special_provisions", r"SPECIAL PROVISIONS?"),
    ("general_notes",    r"GENERAL NOTES?|STANDARD NOTES?"),
    # Pricing/construction detail Alex skips for the bid/no-bid call — split from specifications.
    ("geotechnical",     r"GEOTECHNICAL|SOILS? (REPORT|INVESTIGATION)|BORING LOG|SUBSURFACE"),
    ("typical_sections", r"TYPICAL SECTIONS?"),
    # Residual EJCDC / county procurement front-matter (after the splits above peel off).
    ("contract_front",   r"INSTRUCTIONS TO BIDDERS|NOTICE TO BIDDERS|ADVERTISEMENT FOR BIDS|"
                         r"CONSTRUCTION CONTRACT|NOTICE OF AWARD|NOTICE TO PROCEED|LEGAL AND PROCEDURAL"),
    ("specifications",   r"\bDIVISION \d|\bSECTION \d{4,5}\b|TECHNICAL SPECIFICATIONS?"),
    ("title_index",      r"TITLE SHEET|INDEX OF SHEETS|SHEET INDEX|TABLE OF CONTENTS"),
]
_SECTION_COMPILED = [(name, re.compile(pat)) for name, pat in SECTION_PATTERNS]

# Cross-reference cue words: a line that *points to* a section ("FOR SPECIAL PROVISIONS,
# SEE ATTACHED SHEETS") is a reference, not that section's header. We never let such a
# line open a section. This is what previously mis-tagged Otter Tail's cover page as
# special_provisions. (Word-boundaried so "SEE" doesn't match "SEED", etc.)
_CROSSREF_CUE = re.compile(r"\bSEE\b|ATTACHED|\bREFER\b|PURSUANT|IN ACCORDANCE|AS STATED|AS SHOWN")


def header_match(text: str):
    """Scan a page for the first line that *opens* a recognizable section.
    Returns (section_name, matched_line) or (None, None). `detect_section` wraps this;
    the suspect-tag flagger reuses it so it judges headers exactly as the tagger does.

    A line qualifies as a header only if it is SHORT, is NOT a cross-reference, and the
    matched keyword DOMINATES the line (a real header is ~just the section name, not a
    sentence that mentions it)."""
    for raw in text.splitlines():
        s = raw.strip()
        if not s or len(s) > 60:                 # headers are short lines
            continue
        up = s.upper()
        if _CROSSREF_CUE.search(up):             # a pointer to a section, not a header
            continue
        for name, pat in _SECTION_COMPILED:
            m = pat.search(up)
            if not m:
                continue
            # Keyword must dominate the line: either it's most of the characters, or only
            # a few extra words trail it. Filters "...see the special provisions and..." prose.
            dominates = (len(m.group(0)) / len(up) >= 0.55) or \
                        (len(up.split()) - len(m.group(0).split()) <= 3)
            if dominates:
                return name, s
    return None, None


def detect_section(text: str):
    """Return a section label if this page *opens* a recognizable section, else None.
    We only treat SHORT, non-cross-reference, keyword-dominant lines as headers so a
    passing prose mention of 'prevailing wage' doesn't flip the section."""
    return header_match(text)[0]


# Position rule for proposal front-matter (Alex: the front couple of pages carry
# location/work-type/length/completion — his richest DECISION source — and they're NOT
# always keyword-detectable, especially on non-MnDOT proposals). So for a PROPOSAL doc, the
# first few prose pages that haven't hit a real header yet are tagged proposal_front_data.
FRONT_MATTER_PAGES = 3        # how many leading pages the position rule may claim
FRONT_MIN_CHARS    = 300      # skip near-blank cover/divider pages (no decision signal)
# Sections the position rule is allowed to OVERRIDE (else carry-forward keeps a stale tag):
# a title sheet or a yet-untagged page on page 1-3 of a proposal is really the data front-matter.
_FRONT_OVERRIDABLE = {"unknown", "title_index", "proposal_front", "proposal_front_data"}


def page_sections(page_texts, doc_type="proposal"):
    """Assign a section label to EVERY page: header detection with carry-forward, PLUS the
    proposal front-matter position rule. Returns a list[str] aligned to page_texts. Both
    ingest and demo_brief use this so the two can't drift on how a page is sectioned.
    (Header detection is still the primary signal; the position rule only fires on the first
    few pages of a proposal that header detection left at an overridable label.)"""
    out, current = [], "unknown"
    for idx, text in enumerate(page_texts):
        text = text or ""
        sec = detect_section(text)
        if sec:
            current = sec
        elif (doc_type == "proposal" and idx < FRONT_MATTER_PAGES
              and current in _FRONT_OVERRIDABLE and len(text.strip()) >= FRONT_MIN_CHARS):
            current = "proposal_front_data"
        out.append(current)
    return out


# ── Gotcha guard (never DROP a page that carries a real decision gotcha) ─────
# Section-level DROP is a blunt instrument. Before honoring a DROP we check the page for any
# gotcha trigger phrase (built from taxonomy.py); a hit downgrades the DROP to a keep so the
# "tier, don't delete a gotcha" invariant holds even for boilerplate sections. Mirrors the
# protect list in 04_tools/boilerplate_scan.py (the paragraph-level scanner).
def _gotcha_re():
    cache = getattr(_gotcha_re, "_cache", None)
    if cache is not None:
        return cache
    tax = load_step("taxonomy.py")
    phrases = []
    for t in tax.GOTCHA_TYPES.values():
        phrases += [re.escape(p) for p in t.get("triggers", []) if p]
    phrases += ["prevailing wage", "davis-bacon", "dbe", "liquidated damages",
                "density", "disincentive", "good faith effort"]
    rx = re.compile("|".join(phrases), re.I) if phrases else re.compile(r"(?!x)x")
    _gotcha_re._cache = rx
    return rx


def page_has_gotcha(text: str) -> bool:
    """True if the page text contains any gotcha trigger phrase — used to spare a DROP-section
    page that nonetheless carries a decision gotcha."""
    return bool(_gotcha_re().search(text or ""))


# ── Document-type detection ──────────────────────────────────────────────────
# WHY (the lesson): the corpus mixes two structurally different document kinds, and
# they need different handling — both for SECTIONING and for PERFORMANCE:
#   • PROPOSAL  — text-dense procurement docs: bid schedule, special provisions,
#     instructions to bidders. Prose headers → detect_section works well (MN, most ND).
#   • PLAN_SET  — engineering DRAWINGS: stationing, sheet grids, typical sections, very
#     little prose. detect_section finds almost nothing (the SD ~42% no-section problem).
# A single per-plan PDF is usually a COMBINED doc (proposal pages up front, drawings at
# the back), so we report the DOMINANT type plus a page-level drawing flag the section
# disposition (Task C) uses to down-weight number-soup drawing pages.
#
# Heuristic, source-agnostic: works on pdfplumber text OR convert Markdown.
_DOCTYPE_BID    = re.compile(r"BID SCHEDULE|ESTIMATED QUANTITIES|SCHEDULE OF PRICES|QUANITIES|PAY ITEMS?")
_DOCTYPE_PROC   = re.compile(r"INSTRUCTIONS TO BIDDERS|NOTICE TO BIDDERS|ADVERTISEMENT FOR BIDS|PROPOSAL FOR")
_DOCTYPE_SPEC   = re.compile(r"SPECIAL PROVISIONS?|TECHNICAL SPECIFICATIONS?")
_DOCTYPE_FORMS  = re.compile(r"PERFORMANCE BOND|PAYMENT BOND|\bAGREEMENT\b|NOTICE TO PROCEED|PENAL SUM")
_DOCTYPE_ADD    = re.compile(r"\bADDENDUM\b|\bADDENDA\b")
_DOCTYPE_DRAW   = re.compile(r"\bSTA\b|\d+\+\d{2}\b|TYPICAL SECTION|PLAN AND PROFILE|SHEET \d|\bPROFILE\b")


def text_density(text: str) -> float:
    """Fraction of non-space characters that are LETTERS. Low (<~0.5) ⇒ number/symbol
    'soup' — a CAD drawing page (coordinate grids, station numbers) rather than prose.
    Used to spot drawing pages that embed poorly (nothing semantic to match)."""
    chars = [c for c in text if not c.isspace()]
    if not chars:
        return 0.0
    return sum(c.isalpha() for c in chars) / len(chars)


def is_drawing_page(text: str) -> bool:
    """True if a page looks like an engineering DRAWING rather than prose: little text,
    or low letter-density with drawing markers (stationing, sheet/profile). Soft signal —
    the disposition layer down-weights these, never hard-deletes (a note can sit on a drawing)."""
    body = text.strip()
    if len(body) < 300:                       # near-empty page (pure graphics)
        return True
    if text_density(text) < 0.55 and _DOCTYPE_DRAW.search(text.upper()):
        return True
    return False


def detect_doc_type(pages):
    """Classify a document from its list of page texts. Returns (doc_type, signals).
    doc_type ∈ {proposal, plan_set, contract_forms, addendum}. `signals` is a dict for
    transparency (page count, median chars/page, drawing-page fraction, which markers hit).
    Accepts pdfplumber text or Markdown — it only reads words."""
    pages = [p or "" for p in pages]
    n = len(pages) or 1
    upper = "\n".join(pages).upper()
    char_counts = sorted(len(p) for p in pages)
    median_chars = char_counts[len(char_counts) // 2] if char_counts else 0
    draw_frac = sum(1 for p in pages if is_drawing_page(p)) / n

    sig = {
        "n_pages": len(pages),
        "median_chars_per_page": median_chars,
        "drawing_page_fraction": round(draw_frac, 2),
        "has_bid_schedule": bool(_DOCTYPE_BID.search(upper)),
        "has_procurement_front": bool(_DOCTYPE_PROC.search(upper)),
        "has_special_provisions": bool(_DOCTYPE_SPEC.search(upper)),
        "has_contract_forms": bool(_DOCTYPE_FORMS.search(upper)),
    }

    # Addendum only if it announces itself early AND is short (we don't ingest addenda,
    # but flagging the type lets the caller honor Hard Rule 11).
    early = "\n".join(pages[:3]).upper()
    if _DOCTYPE_ADD.search(early) and len(pages) < 40:
        doc_type = "addendum"
    elif draw_frac >= 0.6 and not sig["has_special_provisions"]:
        doc_type = "plan_set"          # drawing-dominated (SD plan-sets)
    elif sig["has_bid_schedule"] or sig["has_procurement_front"] or sig["has_special_provisions"]:
        doc_type = "proposal"          # the normal combined proposal+plan
    elif sig["has_contract_forms"]:
        doc_type = "contract_forms"
    else:
        doc_type = "proposal"          # safe default — extraction still tries

    sig["doc_type"] = doc_type
    return doc_type, sig


# ── Document structure by PAGE SIZE (the robust proposal vs plan-set signal) ─────
# A bid package = a PROPOSAL (text, 8.5x11 letter) + a PLAN SET (CAD/maps, 11x17 tabloid). They may be
# combined in one PDF or separate. Page DIMENSIONS separate them cleanly (verified on the corpus: Dunn =
# 126 letter + 45 tabloid, boundary exactly at 127; 08MQ = all tabloid → plan-set-only). This replaces
# the text-heuristic detect_doc_type (which mislabeled every corpus PDF "proposal"). The map page ranges
# are the "where the maps live" highlight the estimator asked for.
MAP_LONG_SIDE_IN = 15.5   # long side ≥ 15.5in ⇒ tabloid/ledger (11x17+) MAP page; else letter proposal page


def page_dimensions(pdf_path):
    """[(width_in, height_in)] per page — cheap pdfplumber geometry pass (no text extraction)."""
    import pdfplumber
    with pdfplumber.open(pdf_path) as pdf:
        return [(round(p.width / 72.0, 1), round(p.height / 72.0, 1)) for p in pdf.pages]


def _is_map_page(w_in, h_in):
    return max(w_in, h_in) >= MAP_LONG_SIDE_IN


def compress_ranges(nums):
    """Compress sorted 1-based page numbers into a 'a-b, c, d-e' string (for human-readable ranges)."""
    nums = sorted(nums)
    if not nums:
        return ""
    out, start, prev = [], nums[0], nums[0]
    for n in nums[1:]:
        if n == prev + 1:
            prev = n
        else:
            out.append(f"{start}-{prev}" if start != prev else f"{start}")
            start = prev = n
    out.append(f"{start}-{prev}" if start != prev else f"{start}")
    return ", ".join(out)


def detect_structure(pdf_path):
    """Classify a bid-package PDF by page size. Returns a dict:
        type           — 'proposal' (no map pages) | 'plan_set' (all map pages) | 'combined' (mix)
        n_pages
        map_pages      — 1-based page numbers that are tabloid/ledger (the maps/plan set)
        map_ranges     — those compressed, e.g. '127-171' — WHERE THE MAPS LIVE
        proposal_pages / proposal_ranges — the letter (8.5x11) pages
        boundary_page  — first map page IF the maps are a contiguous tail (combined like Dunn), else None
    Callers: run.py skips type=='plan_set', extracts proposal fields from proposal_pages, and routes
    plan-set fields (traffic_level) to map_pages."""
    dims = page_dimensions(pdf_path)
    n = len(dims)
    map_pages = [i + 1 for i, (w, h) in enumerate(dims) if _is_map_page(w, h)]
    map_set = set(map_pages)
    proposal_pages = [p for p in range(1, n + 1) if p not in map_set]
    dtype = "proposal" if not map_pages else ("plan_set" if not proposal_pages else "combined")
    boundary = map_pages[0] if (map_pages and map_pages == list(range(map_pages[0], n + 1))) else None
    return {
        "type": dtype, "n_pages": n,
        "map_pages": map_pages, "map_ranges": compress_ranges(map_pages),
        "proposal_pages": proposal_pages, "proposal_ranges": compress_ranges(proposal_pages),
        "boundary_page": boundary,
    }


# ── Section taxonomy: the TWO-AXIS "toss-out" map (v2, encodes Alex's process) ──
# knowledge/section_taxonomy.csv maps (doc_type, section) -> (relevance, tier).
#
#   RELEVANCE — Alex's mental model; the primary, client-facing axis:
#     DECISION    — drives the bid/no-bid call (bid schedule, agreement/schedule, plan notes,
#                   proposal front-matter, phasing). The bid/no-bid agent reads these.
#     PRICING     — needed to PRICE the work but not to decide (prevailing wage, geotech, most
#                   special provisions). The extractor reads these; the decision agent can skip.
#     BOILERPLATE — standard contract language Alex has "seen many times" (general conditions,
#                   bonds, EEO/federal provisions).
#
#   TIER — what INGEST does in the vector store (derived from relevance, but explicit so it's
#   editable): KEEP (weight 1.0) · DOWN_WEIGHT (weight 0.3, kept but de-prioritized) · DROP
#   (skipped at ingest — only true boilerplate, and still spared per-page by page_has_gotcha).
#   DECISION/PRICING default to KEEP; the relevance tag (not the weight) is what lets a future
#   decision-only retrieval hide PRICING. BOILERPLATE -> DROP/DOWN_WEIGHT.
TIERS = ("KEEP", "DOWN_WEIGHT", "DROP")
RELEVANCES = ("DECISION", "PRICING", "BOILERPLATE")


def _load_taxonomy_rows():
    """Return {(doc_type, section): {"tier": ..., "relevance": ...}} from the CSV.
    doc_type '*' is a wildcard. Cached on the function object (read disk once per run)."""
    import csv as _csv
    cache = getattr(_load_taxonomy_rows, "_cache", None)
    if cache is not None:
        return cache
    out = {}
    if SECTION_TAXONOMY_CSV.exists():
        for row in _csv.DictReader(open(SECTION_TAXONOMY_CSV)):
            dt = (row.get("doc_type") or "*").strip() or "*"
            sec = (row.get("section") or "").strip()
            if not sec:
                continue
            tier = (row.get("tier") or "KEEP").strip().upper()
            rel = (row.get("relevance") or "").strip().upper()
            out[(dt, sec)] = {
                "tier": tier if tier in TIERS else "KEEP",
                "relevance": rel if rel in RELEVANCES else "",
            }
    _load_taxonomy_rows._cache = out
    return out


def load_disposition():
    """Return {(doc_type, section): tier} — the back-compat shape ingest/demo already use.
    Missing file / missing key ⇒ KEEP (we never silently drop without an explicit rule)."""
    return {k: v["tier"] for k, v in _load_taxonomy_rows().items()}


def disposition_for(section, doc_type="proposal", table=None):
    """Tier for a (doc_type, section). Tries the exact doc_type, then the '*' wildcard,
    then defaults to KEEP. Pass a preloaded `table` (from load_disposition) to avoid
    re-reading the CSV per chunk."""
    table = load_disposition() if table is None else table
    return table.get((doc_type, section)) or table.get(("*", section)) or "KEEP"


def relevance_for(section, doc_type="proposal"):
    """Relevance (DECISION / PRICING / BOILERPLATE) for a (doc_type, section). Mirrors
    disposition_for: exact doc_type, then '*' wildcard. Defaults to DECISION for an unlisted
    section (unknown content is kept full-weight AND visible to the decision agent — safe)."""
    rows = _load_taxonomy_rows()
    hit = rows.get((doc_type, section)) or rows.get(("*", section))
    return (hit or {}).get("relevance") or "DECISION"


# ── Paragraph-level boilerplate removal (the precise toss-out) ───────────────
# 04_tools/boilerplate_scan.py finds paragraphs repeated across many plans that carry NO
# gotcha trigger, and writes their normalized keys to 00_input/boilerplate_fingerprints.json.
# Ingest drops any paragraph whose key matches — a data-derived, gotcha-safe filter that
# strips EJCDC/standard-contract boilerplate without touching project-specific content.
BOILERPLATE_FP = DATA_DIR / "boilerplate_fingerprints.json"


def normalize_paragraph(text: str) -> str:
    """Canonical key for a paragraph: lowercase letters only (digits/punctuation/space
    stripped) so the same boilerplate with different project numbers collapses to one key.
    Shared by the scanner and ingest so the two can't drift."""
    return re.sub(r"[^a-z]", "", text.lower())


def load_boilerplate_fingerprints():
    """Return the set of normalized boilerplate keys (empty if the file is absent —
    ingest then keeps everything). Cached on the function object so we read disk once."""
    import json
    cache = getattr(load_boilerplate_fingerprints, "_cache", None)
    if cache is not None:
        return cache
    keys = set()
    if BOILERPLATE_FP.exists():
        keys = set(json.loads(BOILERPLATE_FP.read_text()).get("keys", []))
    load_boilerplate_fingerprints._cache = keys
    return keys


def strip_boilerplate_paragraphs(page_text: str, fingerprints, min_norm_len: int = 60):
    """Remove blank-line-separated paragraphs whose normalized key is a known boilerplate
    fingerprint. Returns (kept_text, n_dropped). Paragraphs shorter than min_norm_len are
    always kept (too short to fingerprint reliably)."""
    if not fingerprints:
        return page_text, 0
    out, dropped = [], 0
    for block in re.split(r"\n\s*\n", page_text):
        key = normalize_paragraph(block)
        if len(key) >= min_norm_len and key in fingerprints:
            dropped += 1
            continue
        out.append(block)
    return "\n\n".join(out), dropped


def chunk_text(text: str, target_words: int = 350, overlap_words: int = 50):
    """Pack sentences into ~target_words chunks with overlap_words carried over
    between consecutive chunks. Returns a list of chunk strings."""
    sentences = split_sentences(text)
    chunks, cur, cur_words = [], [], 0
    for sent in sentences:
        w = len(sent.split())
        if cur_words + w > target_words and cur:
            chunks.append(" ".join(cur))
            # Start the next chunk with a tail of the previous one (overlap).
            tail, tw = [], 0
            for s in reversed(cur):
                tw += len(s.split())
                tail.insert(0, s)
                if tw >= overlap_words:
                    break
            cur, cur_words = tail[:], tw
        cur.append(sent)
        cur_words += w
    if cur:
        chunks.append(" ".join(cur))
    return chunks
