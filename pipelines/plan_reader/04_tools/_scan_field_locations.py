"""
_scan_field_locations.py  —  EMPIRICAL field-location scan (READ-ONLY on csi_v2.db).

What it does, step by step:
  1. For each numeric/material/spec FIELD CSI extracts, define the LABEL keyword(s) that signal it.
  2. Scan every plan's `plans.full_markdown` (100 docs). For each occurrence of a label, look BACK
     to the nearest governing heading and tag which SECTION TYPE that occurrence falls under, using
     the same heading_regex set as `05_knowledge/2026-06-17_section_intelligence.csv`.
  3. Tally, per (field, section_type): how many DOCS hit it (n_docs) + the label keywords seen.
  4. Apply the PRECEDENCE design (materials -> bid_schedule; stationing/length/traffic -> title sheet)
     to mark is_authoritative / precedence_rank and flag the decoys.
  5. Materials are grounded a SECOND way against the parsed `materials` table (priced quantities live
     in the bid schedule) so the material rows are not regex-only guesses.

Writes 05_knowledge/2026-06-17_field_locations.csv (the location_intelligence row shape).
NEVER writes to the DB — that is the loader's job (10_load_location_intelligence.py).
"""
import sqlite3
import re
import csv
from pathlib import Path
from datetime import date

# --- paths -------------------------------------------------------------------------------------------
HERE = Path(__file__).resolve()
MODULE = HERE.parents[1]                       # pipelines/plan_reader
DB = MODULE / "csi_v2.db"
KNOW = MODULE / "05_knowledge"
OUT_CSV = KNOW / "2026-06-17_field_locations.csv"

# --- 1. the section spine: heading_regex per section type (from section_intelligence) ----------------
# We re-list the regexes here so the scan is self-contained and grounded in the SAME taxonomy. These
# are the "governing heading" detectors: when we find a field label, we walk back to the most recent
# heading line and classify it with these patterns -> the section type that occurrence sits under.
SECTION_REGEX = {
    "bid_schedule": r"(bid schedule|schedule of prices|schedule of items|proposal form|bid form|unit price|estimated quantit|schedule of bid items|bid tabulation)",
    "special_provisions": r"(special provision|division s\b|s-\d+|sp[- ]\d+|special provisions division)",
    "prosecution_of_work": r"(prosecution of work|1804|sequence of operations|order of construction|phasing|staging plan)",
    "proposal_front_data": r"(project (location|description|number)|work type|job length|description of work|location of work|completion date|notice to proceed by)",
    "traffic_staging": r"(traffic control|traffic staging|maintenance of traffic|road closure|lane closure|business access|2563)",
    "agreement": r"(agreement|standard form of agreement|time of commencement|substantial completion|article ii|contract time)",
    "general_notes": r"(general notes|plan notes|construction notes|soils and construction notes|underground notes)",
    "specifications": r"(technical specification|specification \d|section \d{2} \d{2} \d{2}|division 3[123]|construction requirements)",
    "typical_sections": r"(typical section|cross section|reshaping typical)",
    "geotechnical": r"(geotech|soil boring|subsurface|exploration|mix design|soils for earthwork|pavement design)",
    "prevailing_wage": r"(prevailing wage|wage decision|wage rate|davis[- ]bacon|minimum wage|fringe (benefit|rate))",
    "contract_front": r"(advertisement for bids|instructions to bidders|notice to bidders|notice to contractors|invitation to bid|section 00[12]00|proposal guaranty)",
    "title_index": r"(table of contents|index of sheets|sheet index|list of (sheets|drawings)|title sheet|estimated quantities|statement of estimated)",
    "general_conditions": r"(general conditions|standard general conditions|supplementary conditions|section 00[78]00|ejcdc c-700)",
    "bonds_forms": r"(bid bond|performance bond|payment bond|bond form|penal sum|proposal guaranty|certified check)",
    "eeo_federal": r"(equal employment|eeo|fhwa[- ]?1273|required contract provisions|title vi|nondiscrimination|on-the-job training)",
}
SECTION_PAT = {st: re.compile(p, re.I) for st, p in SECTION_REGEX.items()}

# A "heading" line in the converted Markdown: a markdown header (#...), an ALL-CAPS short line, or a
# numbered/spec-coded line. We classify each candidate heading with SECTION_PAT.
HEADING_LINE = re.compile(r"^(#{1,6}\s+.+|[A-Z0-9][A-Z0-9 ,.()/&\-]{6,80})\s*$")


def classify_heading(line):
    """Return the section_type a heading line belongs to, or None if it matches no known pattern."""
    for st, pat in SECTION_PAT.items():
        if pat.search(line):
            return st
    return None


def governing_section(lines, idx, last_heading_type, window=60):
    """The section type governing line `idx`: the most recent classifiable heading at or above it.
    `last_heading_type` is the running section as we stream down the doc (cheap + matches how a reader
    experiences the document); we also look back a small window for a closer un-streamed heading."""
    # look back up to `window` lines for the nearest classifiable heading
    for j in range(idx, max(idx - window, -1), -1):
        ln = lines[j].strip()
        if HEADING_LINE.match(ln):
            st = classify_heading(ln)
            if st:
                return st
    return last_heading_type


# --- 2. the FIELDS to locate: label keywords + unit + target_kind + precedence design ----------------
# Each field = a list of (label_keyword_regex) that signal it in the prose. For materials we ALSO cross
# the parsed `materials` table so the rows are empirically grounded, not regex-only.
FIELDS = [
    # name, target_kind, unit, [label regexes], authoritative_section, decoy_note
    ("MIX_TN", "material", "TON",
     [r"TYPE\s+SP\s*\d", r"SUPERPAVE", r"WEARING COURSE", r"PLANT MIX(?:ED)? (?:ASPHALT|BITUMINOUS)",
      r"HOT MIX", r"\bHMA\b", r"ASPHALT CONCRETE PAVEMENT", r"BITUMINOUS"],
     "bid_schedule", "title-sheet quantity summary + estimate sheets repeat the tonnage — decoy"),
    ("GRADE_CY", "material", "CY",
     [r"COMMON EXCAVATION", r"UNCLASSIFIED EXCAVATION", r"SUBGRADE EXCAVATION", r"EARTHWORK",
      r"EXCAVATION AND EMBANKMENT", r"\bBORROW\b"],
     "bid_schedule", "title-sheet earthwork summary repeats CY — decoy"),
    ("BASE_TN", "material", "TON",
     [r"AGGREGATE BASE", r"BASE COURSE", r"\bCL 13\b", r"BASE PREPARATION"],
     "bid_schedule", "typical-section / title summary repeat base tons — decoy"),
    ("SHLDR_TN", "material", "TON",
     [r"SHOULDER", r"AGGREGATE SURFACING", r"GRAVEL SURFACING"],
     "bid_schedule", "typical-section shoulder callout — decoy"),
    ("MILL_SY", "material", "SY",
     [r"COLD MILLING", r"MILL BITUMINOUS", r"MILLING (?:PAVEMENT|ASPHALT|BITUMINOUS)", r"MILL(?:ING)? SURFACE"],
     "bid_schedule", "plan notes mention milling SY — decoy"),
    ("CRUSH_TN", "material", "TON",
     [r"CRUSHING", r"CRUSHED AGGREGATE", r"\bCRUSH\b"],
     "bid_schedule", None),
    ("STOCK_TN", "material", "TON",
     [r"STOCKPILE", r"STOCK PILE", r"BLEND, HAUL, AND STOCKPILE"],
     "bid_schedule", None),
    # numeric — stationing + length live on the TITLE SHEET (proposal_front_data / title_index)
    ("project_stationing", "numeric", "STA",
     [r"BEGIN\s+(?:PROJECT|CONSTRUCTION).{0,40}STA", r"END\s+(?:PROJECT|CONSTRUCTION).{0,40}STA",
      r"\bSTA\.?\s*\d+\+\d{2}\b"],
     "proposal_front_data", "stationing is repeated in special_provisions calendar-day clauses & plan sheets — decoy"),
    ("project_length", "numeric", "MILE",
     [r"PROJECT\s+LENGTH\s*[:\-]?\s*\d", r"GROSS\s+LENGTH", r"NET\s+LENGTH",
      r"LENGTH\s+OF\s+(?:PROJECT|ROAD)", r"\d+\.\d+\s*MILES?\b"],
     "proposal_front_data", "bare 'X.XXX MILES' recurs in prose (sampling, mobilization) — only the title-sheet PROJECT LENGTH line is law"),
    # spec — traffic / mixture design level
    ("traffic_level", "spec", None,
     [r"DESIGN\s+(?:DATA|TRAFFIC|ESAL)", r"\bA?ADT\b", r"\bESAL\b", r"SP\s*\d+\.?\d*\s*\(\s*\d",
      r"TYPE\s+SP\s*\d+\.?\d*\s*\("],
     "proposal_front_data", "SP mixture level also printed in the bid-schedule item description & typical sections — design-data block on the title sheet is authoritative"),
]


def scan():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    plans = con.execute(
        "SELECT plan_id, state, full_markdown FROM plans "
        "WHERE full_markdown IS NOT NULL AND length(full_markdown) > 100"
    ).fetchall()
    total_docs = len(plans)

    # accumulator: (field, target_kind, unit) -> section_type -> set(plan_id), Counter(keyword)
    from collections import defaultdict, Counter
    acc = defaultdict(lambda: defaultdict(set))           # [(fld)][section] = {plan_ids}
    kw_seen = defaultdict(lambda: defaultdict(Counter))    # [(fld)][section] = Counter(matched label)
    field_state = defaultdict(lambda: defaultdict(Counter))  # [(fld)][section] = Counter(state)

    field_pats = {f[0]: [re.compile(p, re.I) for p in f[3]] for f in FIELDS}
    field_meta = {f[0]: (f[1], f[2], f[4], f[5]) for f in FIELDS}

    for row in plans:
        pid, state, md = row["plan_id"], row["state"], row["full_markdown"]
        lines = md.splitlines()
        # stream down, tracking the running governing section
        running = None
        for i, raw in enumerate(lines):
            ln = raw.strip()
            if HEADING_LINE.match(ln):
                st = classify_heading(ln)
                if st:
                    running = st
            if not ln:
                continue
            U = ln.upper()
            for fname, pats in field_pats.items():
                for pat in pats:
                    m = pat.search(ln)
                    if m:
                        sect = governing_section(lines, i, running) or "unknown"
                        acc[fname][sect].add(pid)
                        kw_seen[fname][sect][m.group(0).strip()[:40]] += 1
                        field_state[fname][sect][state] += 1
                        break  # one hit per field per line is enough

    # --- materials cross-grounding from the parsed materials table (priced quantities = bid_schedule)
    # This is the EMPIRICAL anchor: every material we parsed came out of the bid schedule (base_bid /
    # alternate_*). We record that as the authoritative material location so the rows aren't regex-only.
    mat_docs = {}
    for bucket, fld in [("hot_mix_tons", "MIX_TN"), ("grading_quantity", "GRADE_CY"),
                        ("base_tons", "BASE_TN"), ("shoulder_tons", "SHLDR_TN"),
                        ("milling_sy", "MILL_SY"), ("crushing_tons", "CRUSH_TN"),
                        ("stockpile_tons", "STOCK_TN")]:
        d = con.execute(
            "SELECT COUNT(DISTINCT plan_id) FROM materials WHERE csi_bucket=?", (bucket,)
        ).fetchone()[0]
        mat_docs[fld] = d
    con.close()

    # The title sheet maps to BOTH proposal_front_data (MN front-data block) and title_index (the ND/SD
    # "TITLE SHEET / ESTIMATED QUANTITIES" sheet). For the title-sheet fields, BOTH are authoritative
    # (rank 1) — they are the same physical sheet under two DOT heading conventions.
    TITLE_SHEET_SECTIONS = {"proposal_front_data", "title_index"}

    # --- assemble location_intelligence rows -------------------------------------------------------
    rows_out = []
    for fname, pats in field_pats.items():
        kind, unit, auth_sect, decoy = field_meta[fname]
        sect_docs = acc[fname]
        title_sheet_field = kind in ("numeric", "spec")
        # precedence: authoritative section gets rank 1; everything else ranks by n_docs desc
        ordered = sorted(sect_docs.items(), key=lambda kv: (-len(kv[1]), kv[0]))
        rank = 2  # rank 1 is reserved for the authoritative section; decoys start at 2
        for sect, pids in ordered:
            n = len(pids)
            # materials: the parsed materials table is the EMPIRICAL truth for the bid-schedule count
            # (the markdown bid-schedule TABLE often has no nearby classifiable heading, so regex
            #  undercounts it). Override the bid_schedule material count with the parsed-table count.
            if kind == "material" and sect == auth_sect and mat_docs.get(fname, 0) > n:
                n = mat_docs[fname]
            is_auth = 1 if (sect == auth_sect or (title_sheet_field and sect in TITLE_SHEET_SECTIONS)) else 0
            # keyword list (top 3 by freq)
            kws = "; ".join(k for k, _ in kw_seen[fname][sect].most_common(3))
            if kind == "material" and sect == auth_sect:
                kws = (kws + "; (priced line items, parsed materials table)").strip("; ")
            states = "; ".join(f"{s}({c})" for s, c in field_state[fname][sect].most_common())
            note_parts = []
            if is_auth:
                note_parts.append("AUTHORITATIVE")
                if title_sheet_field and sect in TITLE_SHEET_SECTIONS:
                    note_parts.append("title sheet (one physical sheet under two DOT heading names)")
            elif sect == "unknown":
                note_parts.append("no classifiable governing heading (often title/front sheet pre-section)")
            else:
                note_parts.append("decoy occurrence" + (f" — {decoy}" if decoy else ""))
            note_parts.append(f"states: {states}")
            conf = "high" if n >= 10 else ("medium" if n >= 3 else "low")
            low_sample = n < 3
            rows_out.append({
                "target_kind": kind, "target_name": fname, "section_type": sect,
                "label_keywords": kws, "unit": unit or "", "n_docs": n,
                "frequency_pct": round(100.0 * n / total_docs, 1),
                "is_authoritative": is_auth,
                "precedence_rank": 1 if is_auth else rank,
                "confidence": conf,
                "low_sample_flag": "Y" if low_sample else "",
                "notes": " | ".join(note_parts),
            })
            if not is_auth:
                rank += 1
        # if the authoritative section never showed a regex hit but the materials table proves it,
        # add the empirically-anchored authoritative row (materials only)
        if kind == "material" and auth_sect not in sect_docs:
            n = mat_docs.get(fname, 0)
            rows_out.append({
                "target_kind": kind, "target_name": fname, "section_type": auth_sect,
                "label_keywords": "(parsed priced line items)", "unit": unit or "", "n_docs": n,
                "frequency_pct": round(100.0 * n / total_docs, 1),
                "is_authoritative": 1, "precedence_rank": 1,
                "confidence": "high" if n >= 10 else ("medium" if n >= 3 else "low"),
                "low_sample_flag": "Y" if n < 3 else "",
                "notes": "AUTHORITATIVE | grounded in parsed materials table (priced quantities)",
            })

    return rows_out, total_docs, mat_docs


def main():
    rows, total_docs, mat_docs = scan()
    cols = ["target_kind", "target_name", "section_type", "label_keywords", "unit", "n_docs",
            "frequency_pct", "is_authoritative", "precedence_rank", "confidence",
            "low_sample_flag", "notes"]
    with OUT_CSV.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)
    print(f"scanned {total_docs} docs -> {len(rows)} field-location rows")
    print(f"wrote {OUT_CSV}")
    print("\nauthoritative section per field:")
    for r in rows:
        if r["is_authoritative"]:
            print(f"  {r['target_name']:20s} -> {r['section_type']:22s} "
                  f"n_docs={r['n_docs']:3d}  {'(LOW SAMPLE)' if r['low_sample_flag'] else ''}")
    print("\nmaterials table grounding (priced-quantity docs):", mat_docs)


if __name__ == "__main__":
    main()
