"""
08_material_universe.py — Phase 0 of the material taxonomy: clean + dedupe the raw pay-item universe.

WHY this exists: the `materials` table holds 6,385 rows / 3,806 distinct raw descriptions, but ~73%
land in spec_category='other' — and a big slice of that is TABLE-PARSE NOISE (markdown column headers
like "Col4", project numbers repeated down a column, boilerplate sentences), not real pay items.
Building the crosswalk dictionary straight from the raw list would bake that noise in. So step 0 is:
separate signal from noise, normalize the survivors, and export ONE clean unique list
(normalized_description, state, unit, evidence) that Phases 1-2 seed the crosswalk from.

Read-only: reads csi_v2.db, writes two dated CSVs to 02_outputs/. Never touches the DB.

Run:
    cd 01_Summer_2026
    python3 pipelines/plan_reader/04_tools/08_material_universe.py
"""
import csv
import re
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

# --- paths (mirror lib.py conventions: everything hangs off the module root) -------------------------
MODULE_ROOT = Path(__file__).resolve().parents[1]
DB_PATH     = MODULE_ROOT / "csi_v2.db"
OUT_DIR     = MODULE_ROOT / "02_outputs"
DATE        = "2026-07-03"
CLEAN_CSV   = OUT_DIR / f"{DATE}_material_universe.csv"
NOISE_CSV   = OUT_DIR / f"{DATE}_material_universe_noise.csv"

# --- noise-filter rules -------------------------------------------------------------------------------
# Each rule is (name, test). A description is NOISE if ANY rule fires. The rule NAME is written to the
# noise CSV so every rejection is auditable — if a real pay item gets caught, we can see which rule
# to loosen. These defaults came from eyeballing the top-40 'other' rows; T tunes them here.

# markdown table artifacts: pymupdf4llm emits placeholder headers when a table has unnamed columns
RE_COL_ARTIFACT = re.compile(r"^Col\d+$", re.I)
# project / contract numbers repeated down a column: "FXP-0716(080)", "CP-3823(023)", "22-2-23A",
# "BRO 8052(00)23-1" — mostly digits/dashes/parens, few letters, no material words
RE_PROJECT_NUM  = re.compile(r"^[A-Z]{0,4}[\s-]*\d[\d\-().,& ]*[A-Z]?$")
# stationing / elevations / offsets: "(-) 0.688'", "EL:", "16.0"
RE_MEASUREMENT  = re.compile(r"^\(?[-+]?\)?\s*\d*\.?\d+'?\"?$|^EL:?$|^STA[\s.]", re.I)
# generic header words that leak out of table headers
HEADER_WORDS = {
    "PROJECT NUMBER", "SECTION NAME", "ITEM", "DESCRIPTION", "UNIT", "QUANTITY", "TOTAL",
    "SHEET NO", "SHEET", "PAGE", "STATE OF SOUTH DAKOTA", "S T A T E O F SOUTH DAKOTA",
    "STATE OF NORTH DAKOTA", "STATE OF MINNESOTA", "ESTIMATE", "BID ITEM", "ITEM NO",
    "PAY ITEM", "SPEC", "NO", "N/A", "00",
}


def is_noise(description, unit):
    """Return (True, rule_name) if this row is table-parse noise, (False, None) if it's a real
    (or at least plausible) pay item. Order: cheapest / most-certain rules first."""
    d = (description or "").strip()
    u = (unit or "").strip()

    # 1-2 character cells carry no information ("OS", "TO" — stationing fragments)
    if len(d) <= 2:
        return True, "empty"
    # markdown column placeholders ("Col4") — pure artifact, in description OR unit position
    if RE_COL_ARTIFACT.match(d):
        return True, "col_artifact"
    # NOTE on desc==unit rows: first version rejected them wholesale ("desc_eq_unit") and that
    # killed REAL items (WATER, ROCK/SHALE/MUCK EXCAVATION) whose table row mis-split so the same
    # text landed in both cells. Now main() blanks the unit instead and the description is judged
    # on its own merits — prose legends still die on prose_sentence below, real items survive.
    # a unit cell that is a STATION ("271+70") marks a stationing table row, not a pay item
    if re.match(r"^\d+\+\d+$", u):
        return True, "station_row"
    # known header words leaking through
    if d.upper().rstrip(".:") in HEADER_WORDS:
        return True, "header_word"
    # project/contract numbers: digit-heavy, no letters beyond a short prefix
    if RE_PROJECT_NUM.match(d.upper()) and not re.search(r"[A-Z]{5,}", d.upper()):
        return True, "project_number"
    # stationing / elevation / bare measurements
    if RE_MEASUREMENT.match(d):
        return True, "measurement"
    # sentence-length boilerplate: real pay items are short noun phrases; instructions are prose.
    # 120 chars OR >15 words is far beyond any real item name we have seen.
    if len(d) > 120 or len(d.split()) > 15:
        return True, "prose_sentence"
    # ALL-punctuation / no letters at all
    if not re.search(r"[A-Za-z]", d):
        return True, "no_letters"
    return False, None


# --- normalization ------------------------------------------------------------------------------------
def normalize(description):
    """Collapse a raw description to its dictionary key: uppercase, single-spaced, straight quotes,
    trailing punctuation dropped. Deliberately DOES NOT strip sizes/types ('CL 13', '4IN') — those
    distinguish real items; collapsing them is a Phase-2 decision, not a Phase-0 one."""
    d = (description or "").upper()
    d = d.replace("’", "'").replace("“", '"').replace("”", '"')
    d = re.sub(r"\s+", " ", d).strip().rstrip(".,;:")
    return d


def main():
    if not DB_PATH.exists():
        sys.exit(f"DB not found: {DB_PATH}")
    conn = sqlite3.connect(DB_PATH)

    # pull every material row with its plan's state — state is half the crosswalk key
    rows = conn.execute("""
        SELECT m.raw_description, m.unit, m.spec_category, m.csi_bucket,
               p.state, m.plan_id, m.quantity
        FROM materials m JOIN plans p USING (plan_id)
    """).fetchall()
    print(f"materials rows: {len(rows)}")

    # --- pass 1: split signal vs noise, row by row ----------------------------------------------------
    clean = defaultdict(lambda: {"count": 0, "states": set(), "units": set(), "plans": set(),
                                 "spec_categories": set(), "buckets": set(), "example_qty": None})
    noise = defaultdict(lambda: {"count": 0, "rule": None, "example_unit": None})

    for desc, unit, cat, bucket, state, plan_id, qty in rows:
        # mis-split table row: same text in both cells means the unit was never captured.
        # Blank it so the description gets judged alone (see NOTE in is_noise).
        if (desc or "").strip() == (unit or "").strip():
            unit = ""
        bad, rule = is_noise(desc, unit)
        if bad:
            k = normalize(desc)[:120]
            noise[k]["count"] += 1
            noise[k]["rule"] = rule
            noise[k]["example_unit"] = unit
            continue
        # key on (normalized description, state): the same name can mean different things per state,
        # and per-state evidence counts are what the crosswalk seeding needs
        key = (normalize(desc), state or "XX")
        e = clean[key]
        e["count"] += 1
        e["states"].add(state or "XX")
        e["units"].add((unit or "").strip().upper())
        e["plans"].add(plan_id)
        if cat:
            e["spec_categories"].add(cat)
        if bucket:
            e["buckets"].add(bucket)
        if e["example_qty"] is None and qty:
            e["example_qty"] = qty

    # --- write the clean universe ---------------------------------------------------------------------
    OUT_DIR.mkdir(exist_ok=True)
    with open(CLEAN_CSV, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["normalized_description", "state", "row_count", "n_plans", "units",
                    "current_spec_category", "current_csi_bucket", "example_quantity"])
        for (desc, state), e in sorted(clean.items(), key=lambda kv: -kv[1]["count"]):
            w.writerow([desc, state, e["count"], len(e["plans"]),
                        "|".join(sorted(u for u in e["units"] if u)),
                        "|".join(sorted(e["spec_categories"])),
                        "|".join(sorted(e["buckets"])),
                        e["example_qty"]])

    # --- write the noise audit (every rejection + which rule fired) -----------------------------------
    with open(NOISE_CSV, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["rejected_description", "rule", "row_count", "example_unit"])
        for k, e in sorted(noise.items(), key=lambda kv: -kv[1]["count"]):
            w.writerow([k, e["rule"], e["count"], e["example_unit"]])

    # --- summary: the before/after picture ------------------------------------------------------------
    n_clean_rows = sum(e["count"] for e in clean.values())
    n_noise_rows = sum(e["count"] for e in noise.values())
    uniq_desc = len({d for (d, s) in clean})
    print(f"\nclean rows:  {n_clean_rows}  -> {len(clean)} unique (desc, state) keys "
          f"({uniq_desc} unique descriptions)")
    print(f"noise rows:  {n_noise_rows}  -> {len(noise)} unique rejected strings")
    by_rule = defaultdict(int)
    for e in noise.values():
        by_rule[e["rule"]] += e["count"]
    print("noise by rule:", dict(sorted(by_rule.items(), key=lambda kv: -kv[1])))
    # how much of the old 'other' bucket was actually noise vs real unmapped material?
    other_clean = sum(e["count"] for e in clean.values()
                      if e["spec_categories"] == {"other"})
    print(f"'other' rows that SURVIVE the filter (real unmapped material): {other_clean}")
    print(f"\nwrote {CLEAN_CSV.name} + {NOISE_CSV.name} to 02_outputs/")


if __name__ == "__main__":
    main()
