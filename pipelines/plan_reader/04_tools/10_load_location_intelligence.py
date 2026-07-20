"""
10_load_location_intelligence.py  —  build + populate the `location_intelligence` table.

The `location_intelligence` table is the TARGET-LEVEL detail layer (sibling to `section_intelligence`,
the section-level rollup). One row per (target, section): where an extraction target lives, the keyword
that signals it, and — when it appears in many places — which occurrence is authoritative.

This loader UNIONS two sources into one table shape:
  (a) GOTCHA rows — derived FREE from the existing `gotchas` table: one row per (flag_type, section)
      with n_docs + family. target_kind='gotcha'. (No re-derivation by hand — materialized from data.)
  (b) FIELD rows — read from 05_knowledge/2026-06-17_field_locations.csv (the empirical field scan).

Guardrails honored:
  * READ-ONLY on every EXISTING table (gotchas/materials/sections/plans). We only SELECT from gotchas.
  * We CREATE + DELETE/INSERT into the NEW `location_intelligence` table ONLY.
  * Idempotent: DELETE-then-insert, so re-running replaces rather than duplicates.

Run:  python3 pipelines/plan_reader/04_tools/10_load_location_intelligence.py
"""
import sqlite3
import csv
import re
from pathlib import Path

# --- paths -------------------------------------------------------------------------------------------
HERE = Path(__file__).resolve()
MODULE = HERE.parents[1]                       # pipelines/plan_reader
DB = MODULE / "csi_v2.db"
FIELD_CSV = MODULE / "05_knowledge" / "2026-06-17_field_locations.csv"

# --- canonical section types (mirror of section_intelligence.section_type) ---------------------------
# Used to (a) recognize which gotcha `section` values are already canonical, and (b) map the long tail
# of raw-heading gotcha sections back onto a canonical type so the gotcha view aligns with the field
# view on the SAME section vocabulary. Unmapped raw headings are kept verbatim (never dropped).
CANONICAL = {
    "bid_schedule", "special_provisions", "prosecution_of_work", "proposal_front_data",
    "traffic_staging", "agreement", "general_notes", "specifications", "typical_sections",
    "geotechnical", "prevailing_wage", "contract_front", "title_index", "general_conditions",
    "bonds_forms", "eeo_federal", "proposal_front", "unknown",
}

# Same heading_regex set as the section spine — to fold a raw heading onto a canonical type.
SECTION_REGEX = {
    "bid_schedule": r"(bid schedule|schedule of prices|schedule of items|proposal form|bid form|unit price|estimated quantit|schedule of bid items|bid tabulation|measurement and payment|basis of payment)",
    "prosecution_of_work": r"(prosecution of work|1804|sequence of operations|order of construction|phasing|staging plan|determination .* contract time|failure to complete|1806|1807|time of completion|work restriction|hours of operation|work hours|night limitation)",
    "traffic_staging": r"(traffic control|traffic staging|maintenance of traffic|road closure|lane closure|business access|2563|maintaining access)",
    "agreement": r"(agreement|standard form of agreement|time of commencement|substantial completion|article ii|contract time|final payment|application for payment)",
    "geotechnical": r"(geotech|soil boring|subsurface|exploration|mix design|soils for earthwork|pavement design|subsurface and physical)",
    "prevailing_wage": r"(prevailing wage|wage decision|wage rate|davis[- ]bacon|minimum wage|fringe (benefit|rate)|labor; working|unpaid wages)",
    "contract_front": r"(advertisement for bids|instructions to bidders|notice to bidders|notice to contractors|invitation to bid|section 00[12]00|proposal guaranty)",
    "eeo_federal": r"(equal employment|\beeo\b|fhwa[- ]?1273|required contract provisions|title vi|nondiscrimination|on-the-job training|minority and women|civil rights)",
    "specifications": r"(technical specification|specification \d|section \d{2} \d{2} \d{2}|division 3[123]|construction requirements|tack coat|relaying milled|remove and relay|anti-skid|preservatives|graded aggregate|approach paving|rap incorporated|cold inplace)",
    "general_notes": r"(general notes|plan notes|construction notes|soils and construction notes|underground notes|earthwork balance|grading operations|subsurface utility)",
    "special_provisions": r"(special provision|division s\b|s-\d+|sp[- ]\d+|special provisions division|protection of fish|protection of bats|laws to be observed|utility property|air, land|railroad highway|intent of contract|restrictions on movement)",
    "geotechnical_env": None,
}


def fold_section(section):
    """Map a gotcha `section` string onto a canonical section type. Already-canonical values pass
    through; raw headings are matched against the spine regexes; otherwise kept verbatim (lowercased
    placeholder 'other_heading' is NOT used — we keep the real text so nothing is lost)."""
    if not section:
        return "unknown"
    s = section.strip()
    if s in CANONICAL:
        return s
    for st, pat in SECTION_REGEX.items():
        if pat and re.search(pat, s, re.I):
            return st
    return s  # keep the raw heading verbatim (a long-tail micro-section)


# --- DDL ---------------------------------------------------------------------------------------------
DDL = """
CREATE TABLE IF NOT EXISTS location_intelligence (
  id               INTEGER PRIMARY KEY AUTOINCREMENT,
  target_kind      TEXT,    -- gotcha | material | numeric | spec
  target_name      TEXT,    -- flag_type or field name
  section_type     TEXT,    -- where it appears (FK -> section_intelligence.section_type)
  family           TEXT,    -- gotcha family (NULL for fields)
  label_keywords   TEXT,    -- the keyword/label that signals it
  unit             TEXT,    -- TON|SY|CY|STA|MILE|NULL
  n_docs           INTEGER, -- empirical: # distinct plans
  frequency_pct    REAL,    -- n_docs / docs_scanned
  is_authoritative INTEGER, -- 1 = this occurrence is "law"
  precedence_rank  INTEGER, -- 1 = authoritative; 2,3... = decoy occurrences by prevalence
  confidence       TEXT,    -- high|medium|low
  low_sample_flag  TEXT,    -- 'Y' if n_docs < 3
  notes            TEXT
);
"""

# docs scanned for the gotcha frequency denominator (the 100-plan converted corpus the gotcha pass ran on)
GOTCHA_DOC_DENOM = 100


def load():
    con = sqlite3.connect(DB)
    cur = con.cursor()
    cur.executescript(DDL)
    # idempotent: clear and rebuild
    cur.execute("DELETE FROM location_intelligence")

    # --- (a) GOTCHA rows — free from gotchas, one row per (flag_type, folded section) --------------
    # READ-ONLY select. Fold raw-heading sections onto canonical types, then aggregate.
    raw = cur.execute(
        "SELECT plan_id, flag_type, section, family FROM gotchas "
        "WHERE flag_type IS NOT NULL AND flag_type != ''"
    ).fetchall()
    from collections import defaultdict, Counter
    g_docs = defaultdict(set)       # (flag_type, section) -> {plan_id}
    g_family = defaultdict(Counter)  # (flag_type, section) -> Counter(family)
    for plan_id, flag_type, section, family in raw:
        sect = fold_section(section)
        key = (flag_type, sect)
        g_docs[key].add(plan_id)
        if family:
            g_family[key][family] += 1

    # for each flag_type, the section with the most docs is the authoritative (modal) location
    by_flag = defaultdict(list)
    for (flag_type, sect), pids in g_docs.items():
        by_flag[flag_type].append((sect, len(pids)))

    gotcha_rows = 0
    for flag_type, secs in by_flag.items():
        secs.sort(key=lambda x: (-x[1], x[0]))
        for rank, (sect, n) in enumerate(secs, start=1):
            fam = g_family[(flag_type, sect)].most_common(1)
            fam = fam[0][0] if fam else None
            is_auth = 1 if rank == 1 else 0
            conf = "high" if n >= 10 else ("medium" if n >= 3 else "low")
            note = ("modal gotcha section (authoritative)" if is_auth
                    else "secondary location for this gotcha type")
            cur.execute(
                "INSERT INTO location_intelligence "
                "(target_kind,target_name,section_type,family,label_keywords,unit,n_docs,"
                " frequency_pct,is_authoritative,precedence_rank,confidence,low_sample_flag,notes) "
                "VALUES ('gotcha',?,?,?,?,NULL,?,?,?,?,?,?,?)",
                (flag_type, sect, fam, flag_type.replace("_", " "), n,
                 round(100.0 * n / GOTCHA_DOC_DENOM, 1), is_auth, rank, conf,
                 "Y" if n < 3 else "", note),
            )
            gotcha_rows += 1

    # --- (b) FIELD rows — from the field-location CSV ---------------------------------------------
    field_rows = 0
    with FIELD_CSV.open() as fh:
        for r in csv.DictReader(fh):
            cur.execute(
                "INSERT INTO location_intelligence "
                "(target_kind,target_name,section_type,family,label_keywords,unit,n_docs,"
                " frequency_pct,is_authoritative,precedence_rank,confidence,low_sample_flag,notes) "
                "VALUES (?,?,?,NULL,?,?,?,?,?,?,?,?,?)",
                (r["target_kind"], r["target_name"], r["section_type"], r["label_keywords"],
                 r["unit"] or None, int(r["n_docs"]), float(r["frequency_pct"]),
                 int(r["is_authoritative"]), int(r["precedence_rank"]), r["confidence"],
                 r["low_sample_flag"], r["notes"]),
            )
            field_rows += 1

    con.commit()

    # --- summary ----------------------------------------------------------------------------------
    print("location_intelligence populated (idempotent DELETE-then-insert).\n")
    print("rows by target_kind:")
    for kind, c in cur.execute(
        "SELECT target_kind, COUNT(*) FROM location_intelligence GROUP BY target_kind ORDER BY 2 DESC"
    ):
        print(f"  {kind:10s} {c}")
    total = cur.execute("SELECT COUNT(*) FROM location_intelligence").fetchone()[0]
    print(f"  {'TOTAL':10s} {total}\n")

    print("authoritative section per FIELD (target_kind in material/numeric/spec):")
    for name, sect, n, low in cur.execute(
        "SELECT target_name, section_type, n_docs, low_sample_flag FROM location_intelligence "
        "WHERE is_authoritative=1 AND target_kind IN ('material','numeric','spec') "
        "ORDER BY target_kind, target_name, n_docs DESC"
    ):
        print(f"  {name:20s} -> {sect:20s} n_docs={n:3d} {'(LOW SAMPLE)' if low else ''}")

    print("\nDECOYS flagged (top non-authoritative section per field, by prevalence):")
    for name, sect, n in cur.execute(
        "SELECT target_name, section_type, MAX(n_docs) FROM location_intelligence "
        "WHERE is_authoritative=0 AND target_kind IN ('material','numeric','spec') "
        "GROUP BY target_name ORDER BY 3 DESC"
    ):
        print(f"  {name:20s} loudest decoy: {sect:20s} n_docs={n}")

    print(f"\ngotcha rows: {gotcha_rows} | field rows: {field_rows}")
    con.close()


if __name__ == "__main__":
    load()
