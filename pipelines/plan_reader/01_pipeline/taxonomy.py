"""
taxonomy.py — the codified the client gotcha taxonomy (single source of truth).

A "gotcha" is a plan requirement that raises a contractor's cost or risk and is easy
to miss on a fast read. Before this file there were THREE un-reconciled gotcha lists:
  (C) CLAUDE.md domain definition
  (A) the addendum's 13-type seed taxonomy
  (E) ~8 types we discovered empirically from 2 real plans (SAP 032 MN, 08MQ SD)
None was a superset. This module merges them into ONE canonical list, grouped into
five families, each typed with a one-line definition, trigger phrases, and provenance.

This is the input to few-shot gotcha extraction — NOT a trained classifier. The
`new_gotcha_types` escape hatch in the extractor lets the list keep growing; promote
recurring new types into this file after Alex/the team confirm them.

Provenance codes:  C = CLAUDE.md   A = addendum seed   E = empirically discovered
"""

# Each entry: type -> dict(family, definition, triggers[list], provenance[list], examples)
GOTCHA_TYPES = {
    # ── A. SCHEDULE & SEQUENCING ──────────────────────────────────────────────
    "phasing_staging": {
        "family": "Schedule & sequencing",
        "definition": "Work must be built in defined phases/stages or a mandated sequence of operations.",
        "triggers": ["Phase 1 / Phase 2", "stage construction", "sequence of operations",
                     "shall be completed before", "construction staging"],
        "provenance": ["C", "A", "E"],
        "examples": ["SAP 032: two-phase construction shown on plans"],
    },
    # Split out of phasing_staging on 2026-08-10. phasing_staging fired on 57 of 100 corpus plans
    # and collapsed three different things — a real break-and-resume, an in-season sequence of
    # operations, and traffic staging drawn on the plan. Only the first costs a remobilization, and
    # at a 57% base rate the combined flag told an estimator nothing. phasing_staging keeps its
    # definition (it is written by two batch tools); these two carry the parts that price
    # differently. See docs/_spec/2026-08-10-phasing-gotcha.md §2 and 01_pipeline/phasing.py.
    "phase_break_remobilization": {
        "family": "Schedule & sequencing",
        "definition": "Work stops and later resumes after a gap — most often overwinter, or gated "
                      "on another contract, ROW availability, or a preceding phase — forcing the "
                      "contractor to demobilize and remobilize.",
        "triggers": ["following construction season", "freeze thaw cycle", "left unpaved over a winter",
                     "Notice to Proceed will not be issued prior to",
                     "This Contract Contains Intermediate Completion Dates",
                     "Phase 2 may not begin until Phase 1 is complete",
                     "construction span crossing a winter (start and end in different seasons)"],
        "provenance": ["E"],
        "examples": [
            "Murray CSAH-2 (MN, 2025) p.181: 'Final bituminous wear course along CSAH 2 shall be "
            "placed during the following construction season. This will allow the non-wear course "
            "to be through a freeze thaw cycle.'",
            "Watonwan SP-8303-48 (MN, 2023) p.1: Starting Date 7/10/2023, Completion Date 6/1/2024 "
            "— 'This Contract Contains Intermediate Completion Dates'",
            "Brookings 8391182 (SD, 2023) p.45: substantially complete by October 15, 2023, but "
            "'the Notice to Proceed will not be issued prior to August 1, 2023'",
        ],
    },
    "interim_milestone_dates": {
        "family": "Schedule & sequencing",
        "definition": "The contract imposes intermediate/interim completion dates short of final "
                      "completion, so parts of the work carry their own deadlines and their own "
                      "liquidated-damages exposure.",
        "triggers": ["This Contract Contains Intermediate Completion Dates", "interim completion date",
                     "milestone date", "intermediate completion"],
        "provenance": ["A", "E"],
        # NOTE: a naive 'intermediate completion' grep hits 40 of 100 corpus plans and is dominated
        # by the EJCDC *definition* of Milestone, which imposes nothing. See phasing.py's
        # BOILERPLATE_PATTERNS before adding triggers here.
        "examples": ["Wilkin TH-75 (MN, 2023) p.1 and Watonwan SP-8303-48 p.1 both carry the "
                     "MnDOT proposal-cover declaration"],
    },
    "tight_schedule": {
        "family": "Schedule & sequencing",
        "definition": "Aggressive completion deadline, short working window, or interim milestone dates.",
        "triggers": ["completion date", "calendar days", "interim completion", "working days",
                     "substantial completion by"],
        "provenance": ["C", "A"],
        "examples": ["Watonwan: intermediate completion dates; duration spans two construction seasons (7/10/23-6/1/24)"],
    },
    "seasonal_window": {
        "family": "Schedule & sequencing",
        "definition": "Calendar-restricted work windows, often tied to species/weather/agency rules.",
        "triggers": ["April 15 to October 31", "in-water work window", "no work between",
                     "seasonal restriction"],
        "provenance": ["A", "E"],
        "examples": ["08MQ: NLEB seasonal restriction Apr 15-Oct 31 near structure",
                     "Yankton: Lewis & Clark Rec Area work must finish within 180 days"],
    },
    "night_work": {
        "family": "Schedule & sequencing",
        "definition": "Required night, weekend, or off-peak work hours.",
        "triggers": ["night work", "nighttime operations", "work between 9 PM and", "off-peak hours"],
        "provenance": ["C", "A"],
        "examples": ["Otter Tail: no work after dark (off highway before dark); no work after 3 PM Saturdays; no work July 3"],
    },

    # ── B. TRAFFIC & ACCESS ───────────────────────────────────────────────────
    "traffic_control": {
        "family": "Traffic & access",
        "definition": "Complex maintenance-of-traffic: detours, live adjacent traffic, lane closures, "
                      "urban/noise constraints.",
        "triggers": ["maintenance of traffic", "detour", "lane closure", "flagger",
                     "adjacent to live traffic", "noise ordinance"],
        "provenance": ["A"],
        "examples": ["Brookings: pilot car required at all times during mainline paving; flaggers at both ends + all intersections"],
    },

    # ── C. ENVIRONMENTAL & CULTURAL ───────────────────────────────────────────
    "environmental_species": {
        "family": "Environmental & cultural",
        "definition": "Endangered/protected species protections that constrain timing or methods.",
        "triggers": ["Northern Long-Eared Bat / NLEB", "whooping crane", "ESA", "roosting habitat",
                     "stop work if sighted"],
        "provenance": ["C", "A", "E"],
        "examples": ["08MQ: NLEB roosting + whooping-crane stoppage requirement",
                     "Yankton: NLEB restrictions on SD Hwy 52 project"],
    },
    "water_permit_dewatering": {
        "family": "Environmental & cultural",
        "definition": "Water-resource permitting and groundwater control: Section 404, SWPPP, dewatering, "
                      "invasive-species (AIS) decontamination.",
        "triggers": ["dewatering", "groundwater elevation", "Section 404", "SWPPP", "temporary discharge permit",
                     "AIS decontamination"],
        "provenance": ["A", "E"],
        "examples": ["08MQ: box-culvert dewatering (groundwater 1442.04), AIS hot-water wash + 7-day dry"],
    },
    "cultural_historic": {
        "family": "Environmental & cultural",
        "definition": "Cultural/historic-resource obligations that gate or constrain construction.",
        "triggers": ["Section 4(f)", "NRHP", "Memorandum of Agreement / MOA", "SHPO", "archaeological",
                     "adverse effect"],
        "provenance": ["E"],
        "examples": ["08MQ: NRHP-eligible historic bridge, MOA stipulations before construction",
                     "Yankton: Lewis & Clark Rec Area Section 4(f)/6(f), no staging in rec area"],
    },

    # ── D. SITE & SCOPE RISK ──────────────────────────────────────────────────
    "utility_conflict": {
        "family": "Site & scope risk",
        "definition": "Existing utilities in the work zone requiring avoidance, potholing, or relocation.",
        "triggers": ["high pressure gas line", "utility relocation", "potholing", "fiber optic",
                     "overhead power", "Gopher State One Call"],
        "provenance": ["A", "E"],
        "examples": ["SAP 032: Enterprise Products high-pressure gas line in project limits"],
    },
    "underground_work": {
        "family": "Site & scope risk",
        "definition": "New underground utility installation in scope — storm sewer, sanitary sewer, "
                      "watermain, or drainage pipe requiring trenching, bedding, or dewatering. (the client "
                      "self-performs pipe, so its presence + quantity is a scope/crew driver.)",
        "triggers": ["storm sewer", "sanitary sewer", "watermain", "RCP", "reinforced concrete pipe",
                     "pipe bedding", "trench excavation", "manhole", "catch basin", "storm drainage"],
        "provenance": ["C", "E"],
        "examples": ["8370470: storm sewer + watermain installation (self-perform pipe scope)"],
    },
    "structure_work": {
        "family": "Site & scope risk",
        "definition": "Box culverts, bridges, structure removal/replacement, or retaining/MSE walls in scope.",
        "triggers": ["box culvert", "bridge replacement", "structure removal", "MSE wall",
                     "thru-truss", "RCBC"],
        "provenance": ["C", "E"],
        "examples": ["SAP 032: box culvert at STA 62+68 (15° skew)",
                     "08MQ: steel thru-truss removal + new RCBC over Wolf Creek"],
    },
    "earthwork_imbalance": {
        "family": "Site & scope risk",
        "definition": "Large cut/fill imbalance or borrow/waste sourcing the contractor must resolve.",
        "triggers": ["excavation vs embankment", "borrow", "waste site", "surplus excavation",
                     "import fill"],
        "provenance": ["E"],
        "examples": ["SAP 032: 94,652 CY excavation vs 76,750 CY embankment"],
    },
    "missing_survey_data": {
        "family": "Site & scope risk",
        "definition": "Plans flag unknowns the contractor inherits: no survey data, do-not-disturb features.",
        "triggers": ["no survey data available", "do not disturb", "location approximate",
                     "field verify", "utilities not located"],
        "provenance": ["E"],
        "examples": ["SAP 032: judicial ditches & bridges with no survey data, do-not-disturb"],
    },
    "incidental_scope": {
        "family": "Site & scope risk",
        "definition": "Real work shifted onto the contractor with no direct pay item: 'incidental', "
                      "'by others' coordination, or owner-furnished material the contractor must place.",
        "triggers": ["incidental to the contract", "by others", "furnished by the County",
                     "placed by Contractor", "no separate payment"],
        "provenance": ["E"],
        "examples": ["SAP 032: county-supplied geogrid placed by contractor (incidental); 3,000 CY topsoil stockpile",
                     "Walsh: millings hauled to owner-designated pit 5 mi W of Pisek ND at contractor expense"],
    },
    "material_source": {
        "family": "Site & scope risk",
        "definition": "Aggregate-quality spec driving source choice (traffic level, pit vs quarry) or "
                      "owner-controlled material source.",
        "triggers": ["traffic level 4", "fractured faces", "crushed quarry rock", "aggregate from County pit",
                     "material source"],
        "provenance": ["A"],
        "examples": [],
    },

    # ── E. CONTRACT & COMPLIANCE ──────────────────────────────────────────────
    "prevailing_wage": {
        "family": "Contract & compliance",
        "definition": "Federal Davis-Bacon and/or state prevailing-wage rates apply (raises labor cost).",
        "triggers": ["Davis-Bacon", "prevailing wage", "wage determination", "certified payroll",
                     "minimum wage rate"],
        "provenance": ["A"],
        "examples": ["00 Prosoal: federal Davis-Bacon + MnDOT prevailing wage provisions"],
    },
    "dbe_goal": {
        "family": "Contract & compliance",
        "definition": "Disadvantaged/Women's Business Enterprise participation goal or good-faith effort.",
        "triggers": ["DBE goal", "good faith effort", "WBE", "disadvantaged business"],
        "provenance": ["C"],
        "examples": [],
    },
    "liquidated_damages": {
        "family": "Contract & compliance",
        "definition": "High liquidated-damages / disincentive rate for late completion.",
        "triggers": ["liquidated damages", "$ per calendar day", "disincentive", "road user costs"],
        "provenance": ["C", "A"],
        "examples": [],
    },
    "density_lot_failure": {
        "family": "Contract & compliance",
        "definition": "Compaction density-lot failure penalties / price-reduction or removal clauses.",
        "triggers": ["density lot", "lot will be rejected", "price reduction for density",
                     "remove and replace", "longitudinal joint density"],
        "provenance": ["C"],
        "examples": ["Walsh: longitudinal joint-density pay-adjustment penalty clause"],
    },
    "coordination": {
        "family": "Contract & compliance",
        "definition": "Mandatory coordination with other contractors, agencies, railroads, or landowners.",
        "triggers": ["coordinate with", "adjacent contract", "railroad flagger", "notify landowner",
                     "by separate contract"],
        "provenance": ["A", "E"],
        "examples": ["SAP 032: coordinate topsoil stockpile + geogrid with Jackson County"],
    },
    "tero_tribal_compliance": {
        "family": "Contract & compliance",
        "definition": "Project on tribal/reservation land triggering Tribal Employment Rights Ordinance "
                      "(TERO) hiring preference + fees, tribal jurisdiction, or Tribal Historic "
                      "Preservation review. Major bid/no-bid driver: added cost + tribal-hire obligations.",
        "triggers": ["TERO", "Tribal Employment Rights Ordinance", "tribal land", "reservation",
                     "MHA Nation", "Three Affiliated Tribes", "BIA", "Tribal Historic Preservation",
                     "tribal employment preference", "TERO fee"],
        "provenance": ["C", "A", "E"],
        "examples": ["8370470: MHA Nation TERO requirements — tribal employment rights + TERO fee on "
                     "reservation work"],
    },
    "railroad_coordination": {
        "family": "Contract & compliance",
        "definition": "Work at/near a railroad crossing or right-of-way requiring railroad coordination, "
                      "flagging, occupancy permit, railroad insurance, or a grade-crossing agreement "
                      "(schedule + insurance + cost risk).",
        "triggers": ["railroad right-of-way", "RR ROW", "railroad flagger", "railroad occupancy",
                     "grade crossing", "BNSF", "RCP&E", "railroad insurance", "railroad company",
                     "railroad protective liability"],
        "provenance": ["C", "A", "E"],
        "examples": ["Beadle SD: Schedule B includes Railroad R.O.W. Occupancy item (RCP&E)"],
    },
    "qc_inspection": {
        "family": "Contract & compliance",
        "definition": "Heightened QC / testing / certified-personnel or inspection hold-point burden.",
        "triggers": ["quality control plan", "certified technician", "inspection hold point",
                     "independent assurance", "required testing", "intelligent compaction"],
        "provenance": ["A"],
        "examples": ["Dunn: Intelligent Compaction required for HMA (SP-2); High Friction Surface Treatment provision"],
    },
}

# Convenience: the plain list of type keys, for prompt injection.
GOTCHA_TYPE_KEYS = list(GOTCHA_TYPES.keys())

# ── Relevance: bid/no-bid DECISION driver vs PRICING input (Alex reconciliation) ──
# Alex distinguishes what drives the bid/no-bid DECISION from what's only needed to PRICE the
# work. Prevailing wage is the canonical example: "crucial for pricing… won't influence our
# decision." So we tag each gotcha. The bid/no-bid Master Agent surfaces only decision_driver
# gotchas; extract still captures ALL 20 (pricing needs them). Each entry gets a "relevance"
# key from this one editable map.
#   material_source is FLAGGED for Alex: traffic level → whether a quarry is needed is arguably a
#   capability/fit question (decision), not pure pricing. Listed as pricing_input pending his call.
PRICING_INPUT = {"prevailing_wage", "dbe_goal", "material_source"}
for _k, _v in GOTCHA_TYPES.items():
    _v["relevance"] = "pricing_input" if _k in PRICING_INPUT else "decision_driver"


def decision_gotchas():
    """Type keys that drive the bid/no-bid decision (what the Master Agent should surface)."""
    return [k for k, v in GOTCHA_TYPES.items() if v["relevance"] == "decision_driver"]


def pricing_gotchas():
    """Type keys that are pricing inputs only (captured by the extractor, not decision drivers)."""
    return [k for k, v in GOTCHA_TYPES.items() if v["relevance"] == "pricing_input"]


FAMILIES = [
    "Schedule & sequencing",
    "Traffic & access",
    "Environmental & cultural",
    "Site & scope risk",
    "Contract & compliance",
]


def prompt_block() -> str:
    """Render the taxonomy as a compact few-shot block for the extraction prompt."""
    lines = []
    for fam in FAMILIES:
        lines.append(f"  {fam}:")
        for k, v in GOTCHA_TYPES.items():
            if v["family"] == fam:
                lines.append(f"    - {k}: {v['definition']}")
    return "\n".join(lines)


def dump_csv(path=None):
    """Write the data twin of this taxonomy to knowledge/gotcha_taxonomy.csv — the CSV Alex
    marks up (one row per type: family, relevance, definition, triggers, examples, provenance).
    taxonomy.py stays the code source of truth; this CSV mirrors it for human review."""
    import csv as _csv
    import importlib.util as _ilu
    if path is None:
        # Resolve knowledge/ via lib without a hard import cycle.
        spec = _ilu.spec_from_file_location("plr_lib", str(__import__("pathlib").Path(__file__).with_name("lib.py")))
        _lib = _ilu.module_from_spec(spec); spec.loader.exec_module(_lib)
        path = _lib.GOTCHA_CSV
    path.parent.mkdir(parents=True, exist_ok=True)
    cols = ["gotcha_type", "family", "relevance", "definition", "triggers", "examples", "provenance"]
    with open(path, "w", newline="") as f:
        w = _csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for k, v in GOTCHA_TYPES.items():
            w.writerow({
                "gotcha_type": k,
                "family": v["family"],
                "relevance": v["relevance"],
                "definition": v["definition"],
                "triggers": " | ".join(v.get("triggers", [])),
                "examples": " | ".join(v.get("examples", [])),
                "provenance": "".join(v.get("provenance", [])),
            })
    return path


if __name__ == "__main__":
    import sys
    if "--dump-csv" in sys.argv[1:]:
        print("Wrote", dump_csv())
    else:
        print(f"{len(GOTCHA_TYPES)} canonical gotcha types across {len(FAMILIES)} families "
              f"({len(decision_gotchas())} decision-driver, {len(pricing_gotchas())} pricing-input):\n")
        print(prompt_block())
