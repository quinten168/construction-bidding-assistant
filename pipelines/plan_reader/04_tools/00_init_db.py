#!/usr/bin/env python3
"""
00_init_db.py  —  PHASE 0, STEP 1: create the CSI Plan Reader V2 SQLite store.

Output: pipelines/plan_reader/csi_v2.db

What this does, in plain terms:
  • Creates the full v2 schema — the 7 tables from the plan doc §2 (csi_v2_rag_pipeline_plan_v3.md).
    The store replaces v1's scatter of per-PDF CSV/JSON files so the corpus can scale to 100+ plans
    and two teams can work off ONE database.
  • Seeds the `section_taxonomy` table from the human-edited knowledge file
    (05_knowledge/section_taxonomy.csv) so the seed taxonomy lives in the DB. Jay's normalized
    taxonomy will later REPLACE these seed rows (source='jay_normalized').
  • Asserts the schema invariants the plan is explicit about (outcome nullable, plan_id is identity
    only, reserved columns exist, materials/gotchas are LONG) — so a later phase can't quietly
    violate them.

Idempotent: every table is CREATE TABLE IF NOT EXISTS and the seed re-inserts cleanly, so re-running
this script is safe and leaves the schema unchanged. It does NOT drop tables.

No Anthropic API calls (Phase 0 is the zero-API critical path).

Run:
    cd 01_Summer_2026
    python3 pipelines/plan_reader/04_tools/00_init_db.py
"""
import csv
import sqlite3
from pathlib import Path

# --- paths -------------------------------------------------------------------
# This script lives in .../plan_reader/04_tools/, so the module root is its parent's parent.
# The DB sits at the module root (gitignored — it's regenerable from the PDFs + knowledge files).
TOOLS_DIR   = Path(__file__).resolve().parent
MODULE_ROOT = TOOLS_DIR.parent                                  # .../plan_reader
DB_PATH     = MODULE_ROOT / "csi_v2.db"                         # the v2 store (defined ONCE here)
TAXONOMY_CSV = MODULE_ROOT / "05_knowledge" / "section_taxonomy.csv"  # the seed section taxonomy

# The 7 tables we expect to exist after init — used by the verification block to print row counts.
EXPECTED_TABLES = [
    "plans", "sections", "section_taxonomy", "field_registry",
    "materials", "gotchas", "plan_metrics",
    "conversations",   # bid_assistant runtime chat-turn capture (see backend/trace.py)
]


# --- schema ------------------------------------------------------------------
# Transcribed verbatim from the plan doc §2. Each statement is IF NOT EXISTS so re-running is a
# no-op on an already-built DB. The comments mirror the plan's intent so the schema reads on its own.
SCHEMA_SQL = """
-- 1 row per plan. plan_id is IDENTITY only — it does NOT encode the bid outcome.
CREATE TABLE IF NOT EXISTS plans (
  plan_id           TEXT PRIMARY KEY,
  source_file       TEXT,
  state             TEXT,
  county            TEXT,
  year              INTEGER,
  dot_project_id    TEXT,
  contract_id       TEXT,             -- join key to historical project_base when available
  doc_type          TEXT,            -- 'proposal'|'plan_set' (semantic, set in a later phase)
  archetype         TEXT,            -- = work_type (derived later). NOT the LLM value.
  project_type_llm  TEXT,            -- LLM's guess, CROSS-CHECK ONLY (later phase)
  outcome           TEXT,            -- NULLABLE: WON|LOST|NOBID or NULL in production
  source_pdf_path   TEXT,
  converted_md_path TEXT,
  full_markdown     TEXT,
  convert_status    TEXT,
  ingested_at       DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- 1 row per section (the TRACK A / TRACK B handoff). section_type stays NULL until Jay normalizes.
CREATE TABLE IF NOT EXISTS sections (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  plan_id       TEXT REFERENCES plans(plan_id),
  raw_heading   TEXT,
  page_start    INTEGER,
  page_end      INTEGER,
  raw_text      TEXT,
  section_type  TEXT,              -- filled later from Jay's normalized taxonomy
  classify_conf REAL,
  tier          TEXT,             -- KEEP|DOWN_WEIGHT|DROP (later)
  rag_treatment TEXT              -- index|down_weight|skip (later)
);

-- re-seedable section taxonomy; Jay's normalized output later REPLACES the seed rows.
CREATE TABLE IF NOT EXISTS section_taxonomy (
  section_type TEXT PRIMARY KEY,
  relevance    TEXT,
  tier         TEXT,
  note         TEXT,
  source       TEXT               -- 'seed'|'jay_normalized'
);

-- field registry (Mochen #1) — human-readable field definitions (populated in Phase 4).
CREATE TABLE IF NOT EXISTS field_registry (
  field_name  TEXT PRIMARY KEY,
  field_type  TEXT,
  group_name  TEXT,
  description TEXT,
  example     TEXT,
  source      TEXT,               -- 'crosswalk'|'extract'|'rag'|'derived'
  golden_col  TEXT,
  active      INTEGER DEFAULT 1
);

-- LONG: 1 row per bid-schedule line item (mirrors flags.csv shape; auditable). Filled in Phase 1.
CREATE TABLE IF NOT EXISTS materials (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  plan_id         TEXT REFERENCES plans(plan_id),
  source_file     TEXT,
  section         TEXT,            -- where found (usually bid_schedule)
  bid_item_no     TEXT,
  raw_description TEXT,            -- "SUPERPAVE FAA 45" — the original line
  csi_bucket      TEXT,           -- hot_mix_tons|base_tons|... or NULL if unmapped
  spec_category   TEXT,           -- mobilization|traffic_control|hma|... (state-relative for now)
  quantity        REAL,
  unit            TEXT,           -- TON|SY|CY...
  page            INTEGER,
  confidence      TEXT,           -- high|medium|low
  parse_method    TEXT            -- 'deterministic'|'llm_fallback'
);

-- LONG: 1 row per gotcha instance (EXACTLY flags.csv shape). Filled in Phase 2.
CREATE TABLE IF NOT EXISTS gotchas (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  plan_id     TEXT REFERENCES plans(plan_id),
  source_file TEXT,
  section     TEXT,               -- special_provisions|bid_schedule|agreement...
  flag_type   TEXT,               -- seasonal_window|tight_schedule|...|special_requirement
  family      TEXT,               -- Schedule & sequencing|Site & scope risk|...
  evidence    TEXT,               -- the excerpt (auditability)
  page        INTEGER,
  confidence  TEXT                -- high|medium|low
);

-- LONG: 1 row per CHAT TURN of the bid_assistant. NOT regenerable from PDFs — this is captured
-- runtime conversation traffic (the source data for conversation analysis + the eval framework).
-- The bid_assistant's backend/trace.py self-initializes this same table at runtime; it is mirrored
-- here so the canonical schema documents the whole DB. Keep the two definitions identical.
-- Top-level scalar columns = the queryable index; `payload` = the full TurnRecord JSON (the archive
-- is the per-day JSONL under bid_assistant/data/conversations/). See backend/trace.py.
CREATE TABLE IF NOT EXISTS conversations (
  turn_id               TEXT PRIMARY KEY,    -- uuid4 generated per turn in rag.py
  session_id            TEXT,                -- UI session (Chainlit/Next); groups a conversation
  user_id               TEXT,                -- reserved; NULL until auth exists
  ts                    TEXT,                -- ISO-8601 UTC, timezone-AWARE
  model_id              TEXT,                -- which model produced the turn (segment trends by this)
  prompt_version        TEXT,                -- system-prompt hash (segment trends by prompt change)
  schema_version        TEXT,                -- TurnRecord shape version
  question              TEXT,
  answer                TEXT,
  tool_names            TEXT,                -- comma-joined for quick filtering (detail in payload)
  n_tool_calls          INTEGER,
  n_sources             INTEGER,
  input_tokens          INTEGER,             -- from final.usage (was discarded before)
  output_tokens         INTEGER,
  cache_read_tokens     INTEGER,
  cache_creation_tokens INTEGER,
  latency_ms            REAL,
  n_steps               INTEGER,             -- agent loop rounds
  active_plan_id        TEXT,
  feedback_rating       INTEGER,             -- +1 / -1 / NULL (patched later via /api/feedback)
  feedback_reason       TEXT,
  error                 TEXT,                -- type name if the turn errored, else NULL
  payload               TEXT                 -- full TurnRecord JSON (tool_calls, sources, usage…)
);
CREATE INDEX IF NOT EXISTS idx_conversations_ts         ON conversations(ts);
CREATE INDEX IF NOT EXISTS idx_conversations_session    ON conversations(session_id);
CREATE INDEX IF NOT EXISTS idx_conversations_model      ON conversations(model_id);

-- WIDE: 1 row per plan — the analyst view the Master Agent reads. Filled in Phase 1/1.5/2.
CREATE TABLE IF NOT EXISTS plan_metrics (
  plan_id            TEXT PRIMARY KEY REFERENCES plans(plan_id),
  -- 7 material buckets (rollup from materials)
  hot_mix_tons       REAL,
  base_tons          REAL,
  grading_quantity   REAL,
  shoulder_tons      REAL,
  milling_sy         REAL,
  crushing_tons      REAL,
  stockpile_tons     REAL,
  box_culvert        INTEGER,
  prevailing_wages   INTEGER,
  has_quantity       INTEGER,
  -- Axis 1: work-type (derived, Phase 1.5)
  work_type          TEXT,
  -- Axis 3: size within work-type
  size_basis         TEXT,
  size_value         REAL,
  size_tier          TEXT,
  pctile_within_type REAL,
  -- Axis 2: messiness INPUTS (the 1-10 score is deferred — column reserved, stays NULL)
  n_spec_categories  INTEGER,
  bid_item_count     INTEGER,
  has_structures_work INTEGER,
  has_phasing        INTEGER,
  contract_duration_days INTEGER,
  messiness_score    REAL,        -- RESERVED; NULL until weights tuned with CSI
  -- Phase 2 parking lot (stays NULL for now)
  spatial_fragmentation REAL,     -- conversion-gated; Phase 2
  -- gotcha rollup
  gotcha_count       INTEGER,
  gotcha_burden_tier TEXT,
  -- provenance + cost
  parse_method       TEXT,
  unmapped_items     TEXT,        -- JSON array
  extraction_cost    REAL
);
"""


# --- helpers -----------------------------------------------------------------
def create_schema(conn):
    """Run the full schema script — creates any of the 7 tables that don't already exist."""
    conn.executescript(SCHEMA_SQL)
    conn.commit()


def seed_section_taxonomy(conn):
    """Load the seed section taxonomy from the knowledge CSV into the DB.

    The CSV columns are (doc_type, section, relevance, tier, note). Every seed row has doc_type='*'
    (a wildcard — the seed taxonomy isn't state-specific), so we map `section` -> the table's
    `section_type` primary key and drop doc_type. We INSERT OR REPLACE keyed on section_type so a
    re-run refreshes the seed in place rather than duplicating it. source is stamped 'seed' so Jay's
    later normalized rows can be told apart (and can overwrite these)."""
    if not TAXONOMY_CSV.exists():
        print(f"  ! seed taxonomy CSV not found: {TAXONOMY_CSV} — skipping seed")
        return 0

    rows = list(csv.DictReader(open(TAXONOMY_CSV)))
    for r in rows:
        conn.execute(
            "INSERT OR REPLACE INTO section_taxonomy (section_type, relevance, tier, note, source) "
            "VALUES (?, ?, ?, ?, 'seed')",
            (
                (r.get("section") or "").strip(),
                (r.get("relevance") or "").strip(),
                (r.get("tier") or "").strip(),
                (r.get("note") or "").strip(),
            ),
        )
    conn.commit()
    return len(rows)


def assert_invariants(conn):
    """Verify the schema invariants the plan is explicit about, printing PASS/FAIL for each.
    These are guardrails — if a later phase edits the schema and breaks one, this surfaces it."""
    # Read the live column definitions for the two tables the invariants concern.
    plans_cols   = {c[1]: c for c in conn.execute("PRAGMA table_info(plans)").fetchall()}
    metrics_cols = {c[1]: c for c in conn.execute("PRAGMA table_info(plan_metrics)").fetchall()}
    materials_cols = {c[1]: c for c in conn.execute("PRAGMA table_info(materials)").fetchall()}
    gotchas_cols   = {c[1]: c for c in conn.execute("PRAGMA table_info(gotchas)").fetchall()}

    # PRAGMA table_info columns: (cid, name, type, notnull, dflt_value, pk).
    checks = []

    # 1. outcome must be NULLABLE (notnull flag == 0) so the workflow runs without a bid outcome.
    outcome = plans_cols.get("outcome")
    checks.append(("plans.outcome is nullable", outcome is not None and outcome[3] == 0))

    # 2. plan_id is the primary key and the ONLY required identity column (it must not be derived
    #    from outcome — we can't assert intent, but we assert it's the PK and outcome is not).
    plan_id = plans_cols.get("plan_id")
    checks.append(("plans.plan_id is PRIMARY KEY", plan_id is not None and plan_id[5] == 1))
    checks.append(("plans.outcome is NOT part of the key", outcome is not None and outcome[5] == 0))

    # 3. The two reserved columns must EXIST (so later phases have a home) and we keep them NULL now.
    checks.append(("plan_metrics.messiness_score exists (reserved)", "messiness_score" in metrics_cols))
    checks.append(("plan_metrics.spatial_fragmentation exists (reserved)", "spatial_fragmentation" in metrics_cols))

    # 4. materials + gotchas are LONG tables: an autoincrement integer id PK, NOT keyed on plan_id.
    checks.append(("materials.id is the PK (LONG table)", materials_cols.get("id", (0, 0, 0, 0, 0, 0))[5] == 1))
    checks.append(("gotchas.id is the PK (LONG table)", gotchas_cols.get("id", (0, 0, 0, 0, 0, 0))[5] == 1))

    print("\n-- Schema invariants --")
    all_ok = True
    for label, ok in checks:
        print(f"  [{'PASS' if ok else 'FAIL'}]  {label}")
        all_ok = all_ok and ok
    return all_ok


def print_row_counts(conn):
    """Print the row count of every expected table — the at-a-glance state of the store."""
    print("\n-- Table row counts --")
    for t in EXPECTED_TABLES:
        n = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        print(f"  {t:18s}: {n:,}")


# --- main --------------------------------------------------------------------
def main():
    print(f"Initializing CSI Plan Reader V2 store at:\n  {DB_PATH}\n")

    conn = sqlite3.connect(DB_PATH)
    try:
        # Step 1: create the schema (idempotent — existing tables are left untouched).
        create_schema(conn)
        print("  ✓ schema created (7 tables, CREATE TABLE IF NOT EXISTS)")

        # Step 2: seed the section taxonomy from the knowledge CSV.
        n_seed = seed_section_taxonomy(conn)
        print(f"  ✓ section_taxonomy seeded from CSV: {n_seed} rows (source='seed')")

        # Step 3: verify the invariants the plan is explicit about.
        ok = assert_invariants(conn)

        # Step 4: report the state of every table.
        print_row_counts(conn)

        print(f"\nDone. Invariants: {'all PASS' if ok else 'SOME FAILED — see above'}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
