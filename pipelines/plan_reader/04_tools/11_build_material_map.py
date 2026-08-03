#!/usr/bin/env python3
"""
11_build_material_map.py — the SYSTEMATIC material map, generated as reviewable DATA.

WHY this exists (2026-07-30): the Stearns CP-073-123 test showed the line-item extraction is fine
(26/26 captured) but the description -> bucket mapping is wrong. Root cause is structural, not a
missing keyword: 05_knowledge/quantity_crosswalk.py is a FLAT first-match-wins keyword list, so the
material noun beats the action verb ("MILL BITUMINOUS SURFACE" hits BITUMINOUS -> hma before it can
reach milling). Corpus-wide that strands 1.2M SY of milling and 1.2M SY of reclamation.

WHAT this builds — NOT a new hardcoded mapping. T's constraint (2026-07-30) is explicit: we do not
bake in a mapping before testing it with CSI. So this emits a PROPOSAL as data:

  • 2026-07-30_material_map_PROPOSED.csv — one row per material FAMILY: the bucket we propose, the
    match rule, the real pay-item names we found, how many rows/plans/quantity ride on it, and a
    `status` of CONFIRMED (unambiguous, safe to wire) or NEEDS_CSI_RULING (a judgment call). The
    `csi_answer` / `csi_notes` columns are left BLANK for CSI to fill in the review meeting.
  • 2026-07-30_material_map_EVIDENCE.csv — every distinct pay-item name behind each family, so no
    family is a black box and CSI can see exactly what they are ruling on.

The family taxonomy is three layers, which is the actual fix for the structural bug:
    ACTION (mill / remove / place / salvage / saw / test)  ->  resolved FIRST
    MATERIAL (bituminous / aggregate / earth)              ->  resolved SECOND
    UNIT (TON / SY / CY)                                   ->  the existing bucket guard
An action verb can therefore never lose to a material noun, which is the class of bug that produced
the Stearns result.

Read-only against the DB. Writes two CSVs. No Claude calls, no DDL, no DML.

Run:
    python3 pipelines/plan_reader/04_tools/11_build_material_map.py
"""
import csv
import importlib.util
import re
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

# Reuse the Phase-0 noise filter instead of writing a second one. The `materials` table holds CAD
# sheet text as well as bid-schedule lines (plan legends, stationing runs like "60+00 61+00 62+00",
# sieve-analysis spec tables), and those strings DO match material keywords — the first version of
# this file offered "Horizontal Scale: 1\" = 200' ... Legend" as an example ASPHALT pay item. The
# rules for rejecting them are already written and auditable in 08_material_universe.py; that file
# is digit-prefixed so it cannot be imported by name.
_UNIVERSE = Path(__file__).resolve().parent / "08_material_universe.py"
_spec = importlib.util.spec_from_file_location("material_universe", _UNIVERSE)
_mu = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mu)
is_noise = _mu.is_noise

MODULE_ROOT = Path(__file__).resolve().parents[1]
DB_PATH     = MODULE_ROOT / "csi_v2.db"
OUT_DIR     = MODULE_ROOT / "05_knowledge" / "_markup"
DATE        = "2026-07-30"
MAP_CSV     = OUT_DIR / f"{DATE}_material_map_PROPOSED.csv"
EVID_CSV    = OUT_DIR / f"{DATE}_material_map_EVIDENCE.csv"
MASTER_MD   = OUT_DIR / f"{DATE}_material_map_MASTER.md"   # the one-glance table

# --- the six buckets CSI actually tracks (their spreadsheet column in parens) ------------------------
# These are the client's own numbers; we are only deciding what rolls INTO each one.
BUCKETS = {
    "ASPHALT":   "MIX TN — hot mix placed, tons",
    "BASE":      "BASE TN — aggregate base placed, tons",
    "SHOULDER":  "SHLDR TN — shoulder / surfacing gravel, tons",
    "GRADING":   "GRADE CY — earthwork, cubic yards",
    "MILLING":   "MILL SY — surface removal, square yards",
    "OTHER":     "not a CSI quantity — tracked as a scope flag only",
}

# --- the family taxonomy ------------------------------------------------------------------------------
# (family, bucket, status, action, unit, [match keywords], question_for_csi)
#
# status CONFIRMED       = unambiguous; the only reason it is wrong today is the flat-list bug.
# status NEEDS_CSI_RULING = a real judgment call. We ship a PROPOSED bucket so CSI has something to
#                           react to, but nothing is wired until they rule. This is the whole point
#                           of the file.
#
# Keywords are matched against a whitespace-normalized UPPERCASE description (see normalize()).
#
# ORDER IS LOAD-BEARING. Every ACTION family (mill / saw / remove / salvage) is declared BEFORE the
# PLACE families, because a pay item names the action and the material in one string and the action
# is what decides the bucket. This is not stylistic — the first draft of this file declared
# hot_mix_placed first and immediately reproduced the original bug: "COLD MILLING ASPHALT CONCRETE"
# (75,664 SY, SDDOT) matched the ASPHALT CONCRETE keyword and was read as hot mix. Do not reorder
# these two blocks.
FAMILIES = [
    # ================= ACTION FAMILIES — must stay above the PLACE families =================
    # ---------------- MILLING ----------------
    ("cold_milling", "MILLING", "CONFIRMED", "mill", "SY",
     ["MILL BITUMINOUS", "COLD MILLING", "MILLING PAVEMENT", "MILL TRANSITION", "COLD PLANE",
      "MILLING ASPHALT", "MILL SURFACE", "2232"],
     "Category is unambiguous, but the UNIT is not: NDDOT measures 'Milling Pavement Surface' in "
     "TONS (230,625 T in our corpus) while MN/SD measure SY. Your MILL SY column cannot hold the "
     "ND tons. Do you want a second milling-tons line, or a conversion?"),
    ("full_depth_reclamation", "MILLING", "NEEDS_CSI_RULING", "mill", "SY",
     ["FULL DEPTH RECLAMATION", "RECLAMATION", "RECLAIM"],
     "THE BIGGEST OPEN ITEM: ~1,199,000 SY across the corpus, currently reported as ZERO. FDR "
     "grinds the asphalt AND the base below it into a new base layer. Is that MILL SY, is it "
     "GRADE CY (you are rebuilding the roadbed), or does it need its own number?"),
    ("cold_recycle", "MILLING", "NEEDS_CSI_RULING", "mill", "SY|TON",
     ["COLD RECYCLED", "COLD IN PLACE", "CIR ", "RECYCLING AGENT"],
     "Cold in-place recycling / cold recycled plant mix: same question as FDR — milling family, or "
     "its own thing?"),
    ("sawing", "OTHER", "NEEDS_CSI_RULING", "saw", "LF",
     ["SAWING", "SAW CUT", "SAWCUT"],
     "Sawing is LF and is currently mis-filed as milling. Propose: incidental, flag only. Confirm?"),

    # ---------------- REMOVAL / SALVAGE ----------------
    ("removal_pavement", "GRADING", "NEEDS_CSI_RULING", "remove", "SY|TON",
     ["REMOVE BITUMINOUS", "REMOVAL OF BITUMINOUS", "REMOVE AND DISPOSE OF BITUMINOUS",
      "REMOVE CONCRETE PAVEMENT", "REMOVE CONCRETE DRIVEWAY", "REMOVAL OF CONCRETE",
      "PAVEMENT REMOVAL", "REMOVAL OF PAVEMENT", "REMOVE PAVEMENT",
      "REMOVAL OF AGGREGATE BASE", "REMOVE AGGREGATE BASE"],
     "Mark said pavement removal 'is considered grading work' and converts to CY. (a) Confirm the "
     "rule applies ONLY to pavement/base removal, not to REMOVE SILT FENCE / REMOVE SIGN / REMOVE "
     "PIPE. (b) Is 1.75 Ton/CY your standard factor, or does it vary by material?"),
    ("salvaged_base", "BASE", "NEEDS_CSI_RULING", "salvage", "TON|SY",
     ["SALVAGED BASE", "BASE COURSE, SALVAGED", "REMOVE AND RELAY", "RECYCLED PAVEMENT",
      "SALVAGED AGGREGATE", "SALVAGE AND STOCKPILE"],
     "Salvaged / remove-and-relay base: the material is re-used, not purchased. Does it count "
     "toward BASE TN (it still has to be moved and placed), or is it excluded because you are not "
     "buying aggregate?"),
    ("removal_other", "OTHER", "CONFIRMED", "remove", "*",
     ["REMOVE SILT FENCE", "REMOVE FIBER ROLL", "REMOVE SIGN", "SALVAGE SIGN", "REMOVAL OF PIPE",
      "REMOVE PIPE", "REMOVE CULVERT", "REMOVAL OF CULVERT", "REMOVE FENCE", "REMOVE CURB",
      "REMOVE SEDIMENT", "REMOVE WATTLE", "REMOVE GATE", "REMOVAL OF END SECTION",
      "REMOVE CONCRETE WALK", "REMOVE EXISTING FENCE", "REMOVE FLOTATION"],
     ""),

    # ================= PLACE FAMILIES =================
    # ---------------- ASPHALT ----------------
    # These three sit ABOVE hot_mix_placed for the same action-before-noun reason as the block above.
    # They are things that MENTION asphalt without being placed tonnage, and each one was caught in a
    # real corpus row landing in Mixed_tons:
    #   "INSTALL SIGN TYPE SPECIAL"  -> matched "TYPE SP"  (MnDOT's mix designation) -> read as hot mix
    #   "HMA INTELLIGENT COMPACTION" -> matched "HMA"                                -> read as hot mix
    #   "BITUMINOUS LABORATORY"      -> matched "BITUMINOUS"                         -> read as hot mix
    ("signing", "OTHER", "CONFIRMED", "place", "*",
     ["SIGN TYPE", "SIGN PANEL", "SIGN POST", "INSTALL SIGN", "DELINEATOR", "OBJECT MARKER",
      "TRAFFIC BARRIER"],
     ""),
    ("asphalt_qc", "OTHER", "CONFIRMED", "test", "*",
     ["BITUMINOUS LABORATORY", "INTELLIGENT COMPACTION", "E TICKETING", "E-TICKETING",
      "QUALITY MANAGEMENT", "BITUMINOUS MATERIALS"],
     ""),
    ("asphalt_binder", "OTHER", "NEEDS_CSI_RULING", "place", "TON|GAL",
     ["ASPHALT CEMENT", "TACK COAT", "PRIME COAT", "FOG SEAL", "EMULSIFIED ASPHALT",
      "ASPHALT FOR TACK", "ASPHALT BINDER PG", "SS-1H", "CSS-1H", "BITUMINOUS MATERIAL FOR"],
     "PG binder / tack / prime are priced as separate TON lines. We propose EXCLUDING them from "
     "MIX TN so mix tonnage is not double-counted (the binder is already inside the mix). Confirm?"),
    ("hot_mix_placed", "ASPHALT", "CONFIRMED", "place", "TON",
     ["SUPERPAVE", "TYPE SP", "WEARING COURSE", "WEAR COURSE", "NON WEAR", "HOT MIX ASPHALT",
      "HMA", "ASPHALT CONCRETE PAVEMENT", "ASPHALT CONCRETE", "BITUMINOUS WEAR",
      "BITUMINOUS NON WEAR", "PLANT MIX SURF", "2360"],
     ""),
    ("asphalt_patching", "ASPHALT", "NEEDS_CSI_RULING", "place", "TON|SY",
     ["PATCHING", "PATCH"],
     "Patching appears as TON and as SY, and is priced as its own line. Does patch tonnage belong "
     "in your MIX TN number, or do you price it separately from mainline paving?"),
    ("seal_coat", "OTHER", "NEEDS_CSI_RULING", "place", "TON|SY",
     ["SEAL COAT", "CHIP SEAL", "FLUSH SEAL", "BLOTTER"],
     "Seal coat / chip seal / blotter: is this work CSI bids, and does it belong in ASPHALT or is it "
     "a different line of business?"),

    # ---------------- BASE ----------------
    ("aggregate_base_placed", "BASE", "CONFIRMED", "place", "TON",
     ["AGGREGATE BASE", "BASE COURSE", "SUBBASE", "CLASS 5 AGGREGATE", "2211"],
     ""),
    ("stabilized_base", "BASE", "NEEDS_CSI_RULING", "place", "SY|TON",
     ["CEMENT STABILIZED", "STABILIZED BASE", "STABILIZED SUBGRADE", "SOIL STABILIZATION",
      "LIQUID BASE STABILIZER", "CEMENT TREATED", "PORTLAND CEMENT"],
     "Cement/soil stabilization is measured in SY at a stated depth, not tons, so it cannot enter "
     "BASE TN as written. Do you self-perform stabilization, and do you want it as a quantity or a "
     "scope flag?"),
    ("geosynthetic", "OTHER", "NEEDS_CSI_RULING", "place", "SY",
     ["GEOSYNTHETIC", "GEOGRID", "GEOTEXTILE", "SEPARATION FABRIC", "DRAINAGE FABRIC"],
     "Fabric / geogrid is SY and is not aggregate. Propose: scope flag only, never a tonnage. "
     "Is fabric a cost driver you want surfaced on the report?"),

    # ---------------- SHOULDER ----------------
    ("shoulder_aggregate", "SHOULDER", "CONFIRMED", "place", "TON",
     ["SHOULDER BASE AGGREGATE", "SHOULDER GRAVEL", "SHOULDER AGGREGATE"],
     ""),
    ("aggregate_surfacing", "SHOULDER", "NEEDS_CSI_RULING", "place", "TON",
     ["AGGREGATE SURFACING", "AGGREGATE SURACING", "AGGREGATE SURFACE COURSE", "GRAVEL SURFACING",
      "TRAFFIC SERVICE AGGREGATE", "ACCESS GRAVEL", "GRANULAR MATERIAL", "GRAUNULAR MATERIAL",
      "SHOT ROCK", "2118"],
     "Aggregate Surfacing comes in Class 1, Class 5 and Special. We currently put ALL of it in "
     "SHLDR TN. Is Class 5 surfacing actually base material to you, with only Class 1 / Special "
     "being shoulder gravel?"),

    # ---------------- GRADING ----------------
    # NOTE: the special_* excavations are declared BEFORE plain earthwork so "EXCAVATION - MUCK"
    # cannot be swallowed by the generic EXCAVATION keyword. Same action-before-noun principle.
    ("special_excavation", "GRADING", "NEEDS_CSI_RULING", "move", "CY",
     ["ROCK EXCAVATION", "EXCAVATION - ROCK", "EXCAVATION ROCK",
      "MUCK EXCAVATION", "EXCAVATION - MUCK", "EXCAVATION MUCK",
      "SHALE EXCAVATION", "EXCAVATION - SHALE", "UNDERCUTTING", "SUBCUT",
      "SUBGRADE REPAIR", "EXCAVATION - SUBGRADE"],
     "Rock / muck / shale excavation and undercutting are priced far above common excavation. Do "
     "they belong inside your GRADE CY number, or do you want them called out separately because "
     "they change the price per yard?"),
    # topsoil BEFORE earthwork: "COMMON TOPSOIL BORROW" would otherwise be swallowed by the BORROW
    # keyword, silently answering a question CSI has not been asked yet.
    ("topsoil", "GRADING", "NEEDS_CSI_RULING", "move", "CY",
     ["TOPSOIL", "LOAM TOPSOIL"],
     "Topsoil strip / salvage / borrow / place is ~475,000 CY across our corpus and is currently "
     "filed as erosion control, so it is invisible in GRADE CY. Is topsoil handling part of your "
     "grading number or is it turf-establishment work?"),
    ("earthwork", "GRADING", "CONFIRMED", "move", "CY",
     ["COMMON EXCAVATION", "EXCAVATION - COMMON", "EXCAVATION COMMON", "EXCAVATION AND EMBANKMENT",
      "UNCLASSIFIED EXCAVATION", "COMMON EMBANKMENT", "EMBANKMENT", "BORROW", "FOUNDATION FILL",
      "RESHAPING FORESLOPE", "EXCAVATION"],
     ""),
    ("subgrade_prep", "GRADING", "NEEDS_CSI_RULING", "move", "SY|RDST",
     ["SUBGRADE PREPARATION", "SUBGRADE PREP"],
     "Subgrade preparation is measured three different ways (RDST road-stations in MN, SY in SD, "
     "CY in ND). It is grading work but not a cubic-yard quantity. Flag only, or convert?"),
    ("clearing", "OTHER", "NEEDS_CSI_RULING", "remove", "ACRE|EA",
     ["CLEARING", "GRUBBING"],
     "Clearing & grubbing: scope flag, or part of the grading number?"),
    # ---------------- OTHER (scope flags, never a CSI quantity) ----------------
    ("equipment_rental", "OTHER", "CONFIRMED", "rent", "HOUR",
     ["MOTOR GRADER", "CU YD TRUCK", "FRONT END LOADER", "SKID LOADER", "DOZER", "BACKHOE",
      "EQUIPMENT RENTAL", "2123"],
     ""),
    ("traffic_control", "OTHER", "CONFIRMED", "place", "*",
     ["TRAFFIC CONTROL", "FLAGGING", "PILOT CAR", "BARRICADE", "LANE CLOSURE", "DRUM",
      "MESSAGE BOARD", "DETOUR", "SHOULDER CLOSED", "SHOULDER DROP-OFF", "RUMBLE STRIP"],
     ""),
    ("pavement_marking", "OTHER", "CONFIRMED", "place", "*",
     ["PAVEMENT MARKING", "PVMT MK", "PAINTED", "EPOXY", "STRIPING"],
     ""),
    ("erosion_turf", "OTHER", "CONFIRMED", "place", "*",
     ["SILT FENCE", "EROSION", "SEEDING", "SEED ", "MULCH", "BLANKET", "WATTLE", "FERTILIZER",
      "FIBER MATRIX", "SWPPP", "INLET PROTECTION", "ECB TYPE"],
     ""),
    ("structures", "OTHER", "CONFIRMED", "place", "*",
     ["RIPRAP", "RIP RAP", "CULVERT", "BRIDGE", "PIPE", "RETAINING WALL", "BOX ", "END SECTION"],
     ""),
    ("concrete", "OTHER", "NEEDS_CSI_RULING", "place", "*",
     ["CURB AND GUTTER", "CURB & GUTTER", "SIDEWALK", "CONCRETE PAVEMENT", "CONCRETE WALK",
      "TRUNCATED DOME", "PORTLAND CEMENT CONCRETE"],
     "Does CSI ever self-perform concrete flatwork (curb, gutter, sidewalk, PCC), or is it always "
     "subbed? If always subbed we track it as a flag and never as a CSI quantity."),
    ("guardrail", "OTHER", "CONFIRMED", "place", "*",
     ["GUARDRAIL", "END TERMINAL", "CABLE BARRIER", "CRASH CUSHION"],
     ""),
    ("utilities", "OTHER", "CONFIRMED", "place", "*",
     ["WATER MAIN", "SANITARY SEWER", "HYDRANT", "CONDUIT", "CASING", "VALVE"],
     ""),
    ("water_dust", "OTHER", "CONFIRMED", "place", "*",
     ["DUST CONTROL", "DUST PALLIATIVE", "CALCIUM CHLORIDE", "WATER FOR"],
     ""),
    ("mobilization_admin", "OTHER", "CONFIRMED", "admin", "LS",
     ["MOBILIZATION", "CONTRACT BOND", "FIELD OFFICE", "AS BUILT", "HAUL ROADS"],
     ""),
]


# Typographic characters DOT PDFs emit that break naive keyword matching. Every one of these was
# found in the corpus, not guessed:
#   \xa0  non-breaking space  — 'AGGREGATE\xa0BASE\xa0COURSE\xa0CL\xa05'  (21,107 TON lost)
#   ‐ ‑ – —  hyphen / non-breaking hyphen / en / em dash — 'EXCAVATION ‐COMMON'
#   ‘ ’ “ ”  smart quotes — 'Asphalt Patching – 4” HBP'
TYPOGRAPHIC = {"\xa0": " ", "‐": "-", "‑": "-", "–": "-", "—": "-",
               "‘": "'", "’": "'", "“": '"', "”": '"'}


def normalize(text):
    """Fold typographic characters, uppercase, collapse whitespace. This is a real defect fix, not
    cosmetics: 34,739 TON of aggregate was silently lost corpus-wide purely because the PDF used
    non-breaking spaces and the keyword used ordinary ones."""
    t = text or ""
    for bad, good in TYPOGRAPHIC.items():
        t = t.replace(bad, good)
    return re.sub(r"\s+", " ", t).upper().strip()


def match_family(description):
    """Return the first family whose keyword appears in the description.

    Families are evaluated in FAMILIES order, and that order encodes the fix for the structural bug:
    action-verb families (mill / remove / saw / salvage) are declared before the material-noun family
    they would otherwise collide with, so 'MILL BITUMINOUS SURFACE' can no longer be read as hot mix.
    """
    d = normalize(description)
    for family, bucket, status, action, unit, keywords, _q in FAMILIES:
        for kw in keywords:
            if kw in d:
                return family, bucket, status, action
    return None, None, None, None


def norm_unit(unit):
    u = re.sub(r"[^A-Z]", "", normalize(unit))
    if u.startswith("TON") or u == "T":
        return "TON"
    if u.startswith("SQYD") or u in ("SY", "SYD"):
        return "SY"
    if u.startswith("CUYD") or u in ("CY", "CYD"):
        return "CY"
    return u or "?"


def main():
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("""
        SELECT m.raw_description, m.unit, m.quantity, p.state, m.plan_id
        FROM materials m JOIN plans p USING (plan_id)
    """).fetchall()

    # --- attribute every corpus line to a family, keeping the evidence -------------------------------
    ev = defaultdict(lambda: {"rows": 0, "plans": set(), "states": set(),
                              "names": defaultdict(lambda: [0, 0.0, set(), set()]), "qty": defaultdict(float)})
    unmatched = defaultdict(lambda: [0, 0.0, set()])
    n_noise = 0
    for desc, unit, qty, state, plan_id in rows:
        # Drop CAD/table noise BEFORE matching. A legend or stationing string that happens to contain
        # "BITUMINOUS" is not a pay item, and letting it through inflates every count in this file.
        bad, _rule = is_noise(desc, "" if (desc or "").strip() == (unit or "").strip() else unit)
        if bad:
            n_noise += 1
            continue
        fam, bucket, status, action = match_family(desc)
        u = norm_unit(unit)
        if fam is None:
            k = normalize(desc)[:70]
            unmatched[k][0] += 1
            unmatched[k][1] += qty or 0
            unmatched[k][2].add(state)
            continue
        e = ev[fam]
        e["rows"] += 1
        e["plans"].add(plan_id)
        e["states"].add(state or "?")
        n = e["names"][normalize(desc)[:70]]
        n[0] += 1
        n[1] += qty or 0
        n[2].add(state or "?")
        n[3].add(u)
        if u in ("TON", "SY", "CY") and qty:
            e["qty"][u] += qty

    # --- the proposal sheet ---------------------------------------------------------------------------
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(MAP_CSV, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["bucket", "bucket_meaning", "family", "status", "action", "expected_unit",
                    "match_keywords", "corpus_rows", "corpus_plans", "states",
                    "corpus_quantity", "example_pay_items",
                    "question_for_csi", "csi_answer", "csi_notes"])
        for family, bucket, status, action, unit, keywords, question in FAMILIES:
            e = ev.get(family)
            if e:
                top = sorted(e["names"].items(), key=lambda kv: (-kv[1][1], -kv[1][0]))[:4]
                examples = " | ".join(f"{name} [{','.join(sorted(v[2]))}]" for name, v in top)
                qty = "; ".join(f"{u} {v:,.0f}" for u, v in sorted(e["qty"].items()))
                nrows, nplans = e["rows"], len(e["plans"])
                states = ",".join(sorted(s for s in e["states"] if s))
            else:
                examples = qty = states = ""
                nrows = nplans = 0
            w.writerow([bucket, BUCKETS[bucket], family, status, action, unit,
                        " / ".join(keywords), nrows, nplans, states, qty, examples,
                        question, "", ""])

    # --- the evidence sheet: every distinct name behind every family ---------------------------------
    with open(EVID_CSV, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["family", "bucket", "status", "pay_item_name", "states", "units",
                    "rows", "quantity"])
        for family, bucket, status, action, unit, keywords, question in FAMILIES:
            e = ev.get(family)
            if not e:
                continue
            for name, (n, q, states, units) in sorted(e["names"].items(), key=lambda kv: -kv[1][1]):
                w.writerow([family, bucket, status, name, ",".join(sorted(states)),
                            ",".join(sorted(units)), n, round(q, 1) if q else ""])
        # everything the proposal does NOT yet cover — the growth queue, kept visible on purpose
        for name, (n, q, states) in sorted(unmatched.items(), key=lambda kv: -kv[1][1])[:200]:
            w.writerow(["(UNMATCHED)", "", "NEEDS_REVIEW", name,
                        ",".join(sorted(s or "?" for s in states)), "", n, round(q, 1) if q else ""])

    # --- the master table: the whole mapping on one page, generated so it cannot drift -------------
    # Grouped by bucket rather than by FAMILIES order, because the reader wants "what counts as
    # ASPHALT", not "what does the matcher check first". The matcher's order is a separate concern
    # and is documented at the FAMILIES definition.
    with open(MASTER_MD, "w") as f:
        f.write(f"# Material map — master table\n\nGenerated {DATE} by "
                f"`04_tools/11_build_material_map.py` from the {len(rows):,}-line corpus. "
                f"Do not hand-edit — edit `FAMILIES` in the script and re-run.\n\n"
                "`CONFIRMED` = safe to wire. `NEEDS_CSI_RULING` = a judgment call, not wired until "
                "CSI answers (see `2026-07-30_material_mapping_for_CSI.md`).\n\n")
        for bucket, meaning in BUCKETS.items():
            fams = [x for x in FAMILIES if x[1] == bucket]
            f.write(f"## {bucket} — {meaning}\n\n")
            f.write("| Family | Status | Unit | Matches on | Example pay items (corpus) | Plans | Quantity |\n")
            f.write("|---|---|---|---|---|---|---|\n")
            for family, _b, status, action, unit, keywords, _q in fams:
                e = ev.get(family)
                if e:
                    top = sorted(e["names"].items(), key=lambda kv: (-kv[1][1], -kv[1][0]))[:3]
                    examples = "; ".join(name.title() for name, _v in top) or "—"
                    qty = "; ".join(f"{u} {v:,.0f}" for u, v in sorted(e["qty"].items())) or "—"
                    nplans = len(e["plans"])
                else:
                    examples, qty, nplans = "—", "—", 0
                mark = "" if status == "CONFIRMED" else " ⚠"
                kw = ", ".join(keywords[:5]) + ("…" if len(keywords) > 5 else "")
                f.write(f"| `{family}` | {status}{mark} | {unit} | {kw} | {examples} | {nplans} | {qty} |\n")
            f.write("\n")
        n_open = sum(1 for x in FAMILIES if x[2] == "NEEDS_CSI_RULING")
        f.write(f"---\n\n**{n_open} of {len(FAMILIES)} families still need a CSI ruling.** "
                "Full per-item evidence: `2026-07-30_material_map_EVIDENCE.csv`.\n")

    # --- console summary -----------------------------------------------------------------------------
    # Report coverage TWO ways. Raw row coverage looks bad and is misleading: most unmatched rows are
    # table-parse noise (QC spec tables, sieve-analysis rows, column headers) with no quantity at all.
    # The number that actually matters is coverage of rows carrying a real TON/SY/CY quantity, because
    # that is the only thing that can move a CSI bucket.
    matched = sum(e["rows"] for e in ev.values())
    real = len(rows) - n_noise
    qty_rows = [r for r in rows if r[2] and norm_unit(r[1]) in ("TON", "SY", "CY")
                and not is_noise(r[0], r[1])[0]]
    qty_unmatched = [r for r in qty_rows if match_family(r[0])[0] is None]
    lost = sum(r[2] for r in qty_unmatched)
    print(f"corpus rows: {len(rows)}   CAD/table noise dropped: {n_noise}   real pay items: {real}")
    print(f"matched to a family: {matched} of {real} ({matched/real*100:.1f}%)")
    print(f"quantity-bearing rows (TON/SY/CY): {len(qty_rows)}   "
          f"matched: {len(qty_rows)-len(qty_unmatched)} "
          f"({(len(qty_rows)-len(qty_unmatched))/len(qty_rows)*100:.1f}%)   "
          f"unmatched: {len(qty_unmatched)} carrying {lost:,.0f} units")
    print(f"\n{'BUCKET':10s} {'FAMILY':26s} {'STATUS':18s} {'ROWS':>5s} {'PLANS':>6s}  QUANTITY")
    for family, bucket, status, action, unit, keywords, question in FAMILIES:
        e = ev.get(family)
        if not e:
            print(f"{bucket:10s} {family:26s} {status:18s} {'-':>5s} {'-':>6s}  (no corpus evidence)")
            continue
        qty = "; ".join(f"{u} {v:,.0f}" for u, v in sorted(e['qty'].items()))
        print(f"{bucket:10s} {family:26s} {status:18s} {e['rows']:>5} {len(e['plans']):>6}  {qty}")
    n_open = sum(1 for f in FAMILIES if f[2] == "NEEDS_CSI_RULING")
    print(f"\nopen questions for CSI: {n_open} of {len(FAMILIES)} families")
    print(f"wrote {MAP_CSV.name} + {EVID_CSV.name} + {MASTER_MD.name} to 05_knowledge/_markup/")


if __name__ == "__main__":
    main()
