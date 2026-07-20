"""
09_build_material_crosswalk.py — Phase 1+2 of the material taxonomy: schema, seed, LLM classify.

WHAT this builds (design locked with T, 2026-07-03):
  • bucket_hierarchy   — the buckets & sub-buckets table. BUCKET is the Tuesday-meeting number
    (ASPHALT / AGGREGATE / GRADING / MILLING + the TOTAL TONS rollup); SUB-BUCKET is what we
    extract and back-test against CSI's spreadsheet columns (MIX_TN, BASE_TN, SHLDR_TN...).
    The removals rule lives here as DATA: removal tons divide by 1.75 (Ton/CY, from the Dunn
    County plan sheet) and roll into GRADING; they also sum into TOTAL TONS.
  • material_crosswalk — the learned dictionary: (normalized_description, state) → spec_category,
    with provenance (match_source: removal_rule | keyword | llm | human) and evidence counts.
    The crosswalk maps NAME → CATEGORY only; the (category, unit) → sub-bucket bridge stays
    per-line in quantity_crosswalk.py, because the same name can appear with different units.

WHY (state, description) is the key: pay-item vocabulary follows the state DOT spec book
(ND "Superpave", SD "Asphalt Concrete", MN "Bituminous") — see the 06-26 site-visit transcript.

Pipeline position: reads 02_outputs/2026-07-03_material_universe.csv (the Phase-0 cleaned
universe from 08_material_universe.py). Does NOT touch the live parser — rewiring
quantity_crosswalk to consult this table is Phase 3, gated by the HR12 diff.

Run:
    cd 01_Summer_2026
    python3 pipelines/plan_reader/04_tools/09_build_material_crosswalk.py           # schema + seed + export
    python3 pipelines/plan_reader/04_tools/09_build_material_crosswalk.py --llm     # classify the unknowns
"""
import csv
import json
import os
import re
import sqlite3
import sys
from collections import Counter
from pathlib import Path

# --- paths / imports (same conventions as 07_gotcha_extract) -----------------------------------------
TOOLS_DIR    = Path(__file__).resolve().parent
MODULE_ROOT  = TOOLS_DIR.parent
PIPELINE_DIR = MODULE_ROOT / "01_pipeline"
KNOW_DIR     = MODULE_ROOT / "05_knowledge"
sys.path.insert(0, str(PIPELINE_DIR))
sys.path.insert(0, str(KNOW_DIR))

import lib                                   # noqa: E402  (ENV_PATH, DB path conventions)
import quantity_crosswalk as qx              # noqa: E402  (the existing keyword SPEC_MAP)

DB_PATH      = MODULE_ROOT / "csi_v2.db"
UNIVERSE_CSV = MODULE_ROOT / "02_outputs" / "2026-07-03_material_universe.csv"
MIRROR_XWALK = KNOW_DIR / "material_crosswalk.csv"
MIRROR_HIER  = KNOW_DIR / "bucket_hierarchy.csv"

MODEL              = "claude-sonnet-4-6"     # same model as s4 / gotcha extraction
PRICE_PER_MTOK_IN  = 3.0
PRICE_PER_MTOK_OUT = 15.0
ITEMS_PER_CALL     = 60                      # ~3k tokens in / ~2k out per call — safe + resumable

# --- the bucket & sub-bucket hierarchy (locked with T; the client doc mirrors this) -------------------
# in_total_tons: summed into the TOTAL TONS "moves by truck" rollup.
# to_grading_factor: removal TONS ÷ 1.75 → CY added into GRADING (factor is data, adjustable).
HIERARCHY = [
    # sub_bucket        bucket       unit  historical_col  in_total  factor  note
    ("hot_mix_tons",    "ASPHALT",   "TON", "MIX_TN",      1, None, "placed hot mix only; tack/prime/binder excluded"),
    ("base_tons",       "AGGREGATE", "TON", "BASE_TN",     1, None, "aggregate base placed"),
    ("shoulder_tons",   "AGGREGATE", "TON", "SHLDR_TN",    1, None, "shoulder gravel / aggregate surfacing; CSI tracks separately (1,018 rows fill both)"),
    ("grading_quantity","GRADING",   "CY",  "GRADE_CY",    0, None, "earthwork native CY"),
    ("removal_tons",    "GRADING",   "TON", None,          1, 1.75, "removed pavement/base; ÷1.75 Ton/CY into GRADING (Dunn plan-sheet factor); own visible line"),
    ("milling_sy",      "MILLING",   "SY",  "MILL_SY",     0, None, "own bucket pending client Q1 (may fold under ASPHALT)"),
]

# --- the spec_category taxonomy the LLM classifies into ----------------------------------------------
# Existing categories (from qx.SPEC_MAP) + the new ones the Phase-0 universe demanded. One line each —
# these definitions go verbatim into the prompt, so keep them tight and contrastive.
CATEGORIES = {
    "hma":              "hot mix asphalt PLACED (Superpave, Asphalt Concrete, Bituminous, wearing course)",
    "asphalt_binder":   "asphalt binder/coat lines priced separately: tack coat, prime coat, PG asphalt cement, fog seal",
    "base":             "aggregate base PLACED under pavement (base course, salvaged base, stabilized base)",
    "surfacing":        "shoulder gravel / aggregate surfacing placed on shoulders or gravel roads",
    "grading":          "earthwork: excavation, embankment, borrow, topsoil, subgrade prep, muck/rock/shale excavation",
    "removal":          "removal or salvage of EXISTING pavement, base, curb, structures (the item is a removal, not placement)",
    "milling":          "milling / cold planing / reclaiming existing asphalt surface",
    "mobilization":     "mobilization, bonds, insurance lump sums",
    "traffic_control":  "temporary traffic control: flagging, pilot car, barricades, drums, message boards, detours",
    "pavement_marking": "permanent striping and markings: paint, epoxy, tape, wet-reflective lines, markers",
    "erosion":          "erosion & sediment control and turf: silt fence, seeding, mulch, blankets, wattles, inlet protection, SWPPP",
    "structures":       "bridges, culverts, pipe (storm/culvert), riprap, retaining walls, box culverts",
    "concrete":         "concrete flatwork/pavement: curb & gutter, sidewalk, driveway, PCC pavement, truncated domes, portland cement",
    "signing":          "permanent signs: flat sheet signs, sign posts, delineators (permanent), object markers",
    "guardrail":        "guardrail, end terminals, cable barrier, crash cushions",
    "utilities_pipe":   "water main, sanitary sewer, utility conduit/casing, hydrants, valves (municipal utilities)",
    "water_dust":       "water for compaction/dust control, dust palliative, calcium chloride, blotter material",
    "lighting_signals": "roadway lighting, traffic signals, luminaires, electrical service",
    "fencing":          "right-of-way fence, gates, cattle guards",
    "testing_qc":       "QC/QA and lab items: contractor's laboratory, cored samples, aggregate laboratory, density testing",
    "admin":            "administrative/contract lines: e-ticketing, field office, project documentation, training",
    "other":            "a real pay item that fits none of the above",
}

# Removal disambiguation, checked BEFORE the keyword map: "REMOVE AND RELAY" is milling-family work
# (the existing SPEC_MAP handles it); everything else containing REMOV* is a removal item.
RE_REMOVAL = re.compile(r"\bREMOV", re.I)
RE_RELAY   = re.compile(r"RELAY|RE-LAY", re.I)


def seed_category(desc):
    """Deterministic seed: removal rule first, then the existing keyword SPEC_MAP.
    Returns (category, source) — ('other', None) means 'unknown, send to the LLM'."""
    if RE_REMOVAL.search(desc) and not RE_RELAY.search(desc):
        return "removal", "removal_rule"
    cat = qx.spec_category(desc)
    if cat != "other":
        return cat, "keyword"
    return "other", None                      # unknown — LLM target


# --- schema -------------------------------------------------------------------------------------------
def ensure_schema(conn):
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS bucket_hierarchy (
      sub_bucket        TEXT PRIMARY KEY,
      bucket            TEXT NOT NULL,
      unit              TEXT NOT NULL,
      historical_col    TEXT,
      in_total_tons     INTEGER DEFAULT 0,
      to_grading_factor REAL,
      note              TEXT
    );
    CREATE TABLE IF NOT EXISTS material_crosswalk (
      normalized_description TEXT NOT NULL,
      state         TEXT NOT NULL,
      spec_category TEXT,
      match_source  TEXT,
      confidence    TEXT,
      row_count     INTEGER,
      n_plans       INTEGER,
      units         TEXT,
      notes         TEXT,
      created_at    DATETIME DEFAULT CURRENT_TIMESTAMP,
      PRIMARY KEY (normalized_description, state)
    );
    """)
    # hierarchy is small + canonical: rewrite it wholesale so edits here are the source of truth
    conn.execute("DELETE FROM bucket_hierarchy")
    conn.executemany(
        "INSERT INTO bucket_hierarchy VALUES (?,?,?,?,?,?,?)", HIERARCHY)
    conn.commit()


# --- seed pass ----------------------------------------------------------------------------------------
def seed(conn):
    """Load the Phase-0 clean universe and upsert every key with its deterministic category.
    Unknowns are stored with spec_category=NULL so the LLM pass (and the review queue) can find them."""
    if not UNIVERSE_CSV.exists():
        sys.exit(f"Run 08_material_universe.py first — missing {UNIVERSE_CSV}")
    rows = list(csv.DictReader(open(UNIVERSE_CSV)))
    stats = Counter()
    for r in rows:
        desc, state = r["normalized_description"], r["state"]
        cat, source = seed_category(desc)
        if source is None:
            cat, conf = None, None            # unknown → LLM target
        else:
            conf = "high"                     # deterministic rules are high-confidence by definition
        stats[source or "unknown"] += 1
        conn.execute("""
            INSERT INTO material_crosswalk
              (normalized_description, state, spec_category, match_source, confidence,
               row_count, n_plans, units, notes)
            VALUES (?,?,?,?,?,?,?,?,NULL)
            ON CONFLICT(normalized_description, state) DO UPDATE SET
              row_count=excluded.row_count, n_plans=excluded.n_plans, units=excluded.units,
              -- a deterministic re-seed only overwrites rows the LLM/human hasn't touched
              spec_category = CASE WHEN material_crosswalk.match_source IN ('llm','human')
                                   THEN material_crosswalk.spec_category ELSE excluded.spec_category END,
              match_source  = CASE WHEN material_crosswalk.match_source IN ('llm','human')
                                   THEN material_crosswalk.match_source ELSE excluded.match_source END,
              confidence    = CASE WHEN material_crosswalk.match_source IN ('llm','human')
                                   THEN material_crosswalk.confidence ELSE excluded.confidence END
        """, (desc, state, cat, source, conf, r["row_count"], r["n_plans"], r["units"]))
    conn.commit()
    print(f"seeded {len(rows)} keys → {dict(stats)}")


# --- LLM pass -----------------------------------------------------------------------------------------
def llm_classify(conn):
    """Classify every spec_category IS NULL key with Claude, ITEMS_PER_CALL at a time.
    Resumable: each call's results commit immediately, so a crash only loses the in-flight chunk."""
    import anthropic
    api_key = os.environ.get("ANTHROPIC_API_KEY") or lib.ENV_PATH.read_text().split("'")[1]
    client = anthropic.Anthropic(api_key=api_key)

    todo = conn.execute("""
        SELECT normalized_description, state, units FROM material_crosswalk
        WHERE spec_category IS NULL ORDER BY row_count DESC
    """).fetchall()
    print(f"LLM targets: {len(todo)} unknown keys → ~{(len(todo)-1)//ITEMS_PER_CALL+1} calls")

    cat_block = "\n".join(f"- {k}: {v}" for k, v in CATEGORIES.items())
    system = (
        "You classify highway-construction bid pay items (MN/ND/SD DOT vocabulary) into exactly one "
        "spec category. Items were extracted from bid schedules and estimate sheets; some strings are "
        "garbled table fragments — if a string is clearly not a real pay item, use category 'noise'.\n\n"
        f"Categories:\n{cat_block}\n- noise: not a real pay item (table fragment, heading, garble)\n\n"
        "Return ONLY a JSON array, one object per input item, same order: "
        '{"i": <index>, "cat": "<category>", "conf": "high|medium|low"}'
    )

    tok_in = tok_out = 0
    for start in range(0, len(todo), ITEMS_PER_CALL):
        chunk = todo[start:start + ITEMS_PER_CALL]
        lines = "\n".join(f'{i}. [{s}] {d}  (units: {u or "?"})'
                          for i, (d, s, u) in enumerate(chunk))
        resp = client.messages.create(
            model=MODEL, max_tokens=4096, temperature=0,
            system=system,
            messages=[{"role": "user", "content": f"Classify these {len(chunk)} items:\n{lines}"}],
        )
        tok_in += resp.usage.input_tokens
        tok_out += resp.usage.output_tokens
        text = resp.content[0].text.strip()
        m = re.search(r"\[.*\]", text, re.S)   # tolerate prose around the array
        try:
            results = json.loads(m.group(0) if m else text)
        except json.JSONDecodeError:
            print(f"  ! chunk @{start}: unparseable response — skipped (re-run to retry)")
            continue
        for r in results:
            i = r.get("i")
            if i is None or not (0 <= i < len(chunk)):
                continue
            cat = r.get("cat")
            if cat not in CATEGORIES and cat != "noise":
                cat = "other"                 # never let the model invent a category
            desc, state, _ = chunk[i]
            conn.execute("""
                UPDATE material_crosswalk
                SET spec_category=?, match_source='llm', confidence=?
                WHERE normalized_description=? AND state=? AND spec_category IS NULL
            """, (cat, r.get("conf", "low"), desc, state))
        conn.commit()
        done = min(start + ITEMS_PER_CALL, len(todo))
        print(f"  {done}/{len(todo)}  (in={tok_in:,} out={tok_out:,} "
              f"~${tok_in/1e6*PRICE_PER_MTOK_IN + tok_out/1e6*PRICE_PER_MTOK_OUT:.2f})")
    print(f"LLM pass done: {tok_in:,} in / {tok_out:,} out ≈ "
          f"${tok_in/1e6*PRICE_PER_MTOK_IN + tok_out/1e6*PRICE_PER_MTOK_OUT:.2f}")


# --- mirrors (KNOWLEDGE.md principle: the DB is live state; 05_knowledge CSVs are the reviewable twin) -
def export_mirrors(conn):
    for path, table, order in [(MIRROR_XWALK, "material_crosswalk", "state, spec_category, normalized_description"),
                               (MIRROR_HIER,  "bucket_hierarchy",   "bucket, sub_bucket")]:
        cur = conn.execute(f"SELECT * FROM {table} ORDER BY {order}")
        with open(path, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow([c[0] for c in cur.description])
            w.writerows(cur)
        print(f"mirror → {path.relative_to(MODULE_ROOT)}")


def report(conn):
    print("\n-- crosswalk state --")
    for src, cat, n in conn.execute("""
        SELECT COALESCE(match_source,'UNKNOWN'), COALESCE(spec_category,'(null)'), count(*)
        FROM material_crosswalk GROUP BY 1,2 ORDER BY 1,3 DESC"""):
        print(f"  {src:14s} {cat:18s} {n}")


def main():
    conn = sqlite3.connect(DB_PATH)
    ensure_schema(conn)
    seed(conn)
    if "--llm" in sys.argv:
        llm_classify(conn)
    export_mirrors(conn)
    report(conn)


if __name__ == "__main__":
    main()
