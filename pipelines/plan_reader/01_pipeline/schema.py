"""
schema.py — the Plan Reader's CANONICAL output schema, defined ONCE.

This is the interface contract between the Plan Reader and everything downstream (the
Competitor Intelligence module, an LLM, the eval). The extraction prompt, the per-PDF JSON
writer, the flattened review CSV, and the golden-comparison eval all read THIS file — change a
field here, not in four places.

Two artifacts come out of one schema:
  • per-PDF JSON  (the SOURCE OF TRUTH) — 00_input/plans/<plan_id>/<plan_id>.json. Each scalar field
    is an object {value, confidence, page}; gotchas/special_requirements are arrays of objects.
  • results.csv   (a flattened REVIEW VIEW for humans) — one upserted row per plan: clean value
    columns + compact citations/confidence columns + free-text gotchas for Alex to scan/edit.

Field `source`:
  • "extract" — pulled by the whole-document extractor (01_pipeline/s3_extract.py); these have a golden
    column and are AUTO-scored (quantities, location, prevailing wages, box).
  • "rag"     — pulled by structured retrieval (01_pipeline/s4_extract_rag.py) because they sit mid-document
    where smart_truncate drops them (traffic_level, construction dates, phasing, gotchas). Most
    have no golden ground truth yet → HUMAN-judged in the eval until Alex fills golden.
"""

CONFIDENCES = ("high", "medium", "low")


def _f(name, jtype, source, desc, golden=None, evalkind=None, group="other", doc="either"):
    """One scalar field spec. golden = the golden_dataset.csv column it maps to (for eval);
    evalkind = how eval compares it (num/bool/state/location/text/date) or None = human-judged;
    doc = which part of the package the field lives in (proposal | plan_set | either) — used to route
    extraction (proposal fields from the letter pages, plan-set fields from the map pages)."""
    return {"name": name, "type": jtype, "source": source, "desc": desc,
            "golden": golden, "evalkind": evalkind, "group": group, "doc": doc}


# ── Scalar fields (each carries {value, confidence, page} in the JSON) ──────────
SCALAR_FIELDS = [
    # identity
    _f("state", "str", "extract", "Two-letter state code (MN/ND/SD) inferred from the project location.",
       golden="state", evalkind="state", group="identity"),
    _f("county", "str", "extract",
       "County the project is in — ALWAYS extract it from the project location/address even if not "
       "separately labeled (e.g. location 'Miltona Township, Douglas County, MN' → 'Douglas').",
       golden="county", evalkind="location", group="identity"),
    _f("project_location", "str", "extract",
       "Physical location of the work (route/road name, county, termini, coordinates if present).",
       golden="project_location", evalkind="location", group="identity"),
    _f("sp_number", "str", "extract",
       "State project / contract number (e.g. 'SAP 021-600-023', 'SP 8303-48').",
       golden="sp_number", evalkind="text", group="identity"),
    _f("project_type", "str", "extract",
       "Project work-type: one of Reconstruct/Rebuild, Mill & Overlay, HMA Overlay/Resurface, "
       "Grading/Earthwork, Aggregate/Base/Gravel (see 05_knowledge/project_archetypes.csv).",
       golden=None, evalkind=None, group="identity"),
    # location — RAG despite being "identity": these live on the title sheet, which per
    # 05_knowledge/2026-06-17_field_locations_README.md can be a tabloid map page the whole-doc
    # pass never sees (s3_extract.py is fed only structure["proposal_pages"], report.py:110-111).
    _f("route_number", "str", "rag",
       "The route/highway number the project is on (e.g. '94' for TH 94 / I-94 / US-94) — digits "
       "only, without the route-type prefix letters (I-/US-/TH/SH). Return as written; null if not stated.",
       golden=None, evalkind=None, group="identity"),
    _f("begin_milepost", "str", "rag",
       "The project's OVERALL begin reference point (first SP/State-Project block if the plan has "
       "more than one). State DOTs call this different things — return the value exactly as written, "
       "do not convert format: MN 'REF. POINT' (station '71+00.444' or decimal '71.004'), ND/MT/NE "
       "'RP' (decimal, e.g. '4.3'), SD 'MRM' (e.g. '406.32+0.022'), IA 'MP' (decimal, e.g. '18.70'). "
       "Null if not stated.",
       golden=None, evalkind=None, group="identity"),
    _f("end_milepost", "str", "rag",
       "The project's OVERALL end reference point (last SP/State-Project block if more than one), "
       "same format/terminology as begin_milepost. Optional — null if not stated.",
       golden=None, evalkind=None, group="identity"),
    _f("total_gross_length", "num", "rag",
       "Total project length in miles: SUM the GROSS LENGTH row(s) yourself across EVERY SP/"
       "State-Project block on the title sheet (a plan with multiple SP blocks has one GROSS LENGTH "
       "line per block — add them all together). Return ONE plain number in miles, not a list. "
       "Null if no GROSS LENGTH value is stated anywhere.",
       golden=None, evalkind=None, group="identity"),
    # quantities (the bid-schedule numbers — all auto-scored vs golden, ±10%)
    #
    # THESE SEVEN DESCRIPTIONS ARE THE LIVE MATERIAL MAPPING. Treat them as a reviewable mapping,
    # not as prose. A newly dropped plan's quantities come from Claude being asked for these totals
    # directly — 05_knowledge/quantity_crosswalk.py is BATCH ONLY and is never loaded on this path
    # (verified three ways, docs/_session/2026-08-08_live-path-mapping.md §1).
    #
    # CSI's 2026-08-07 rulings (Alex's 11) were applied here on 2026-08-10. Each clause below cites
    # the ruling it encodes. Source of truth for the rulings themselves:
    # 05_knowledge/quantity_crosswalk.py::CSI_RULINGS_2026_08_07 (lines 185-202 are Alex's 11;
    # 218-225 are T's 8 — Mark's rule that pavement/base removal is grading work).
    # Design + open items: docs/_spec/2026-08-10-live-mapping-rulings.md.
    # No-regression proof: 03_evaluation/2026-08-10_mapping_regression.py.
    #
    # DO NOT edit a description without re-running that harness. The mapping is a prompt, so a
    # passing unit test proves nothing about it.
    _f("hot_mix_tons", "num", "extract",
       "Total tons of hot mix asphalt PLACED on this project. The three states write it differently "
       "and all three mean hot mix — count all of them: MN 'BITUMINOUS MIXTURE' / 'TYPE SP' (e.g. "
       "'SPWEA240B'), ND 'SUPERPAVE' (including 'RAP - SUPERPAVE FAA 43' — recycled hot mix, it "
       "counts), SD 'ASPHALT CONCRETE'. Count wearing course, non-wearing course, leveling and "
       "patching mixtures. Do NOT count milling or removal of existing bituminous — that is "
       "milling_sy. Do NOT count aggregate.",
       golden="mix_tn", evalkind="num", group="quantities"),
    # mix_sy_depth_items — raw per-item companion for hot_mix_tons, mirroring base_cy_items/
    # shoulder_cy_items below. IMPORTANT: unlike an earlier version of this field, the model is
    # NEVER asked to multiply or sum here — a live test on 2026-08-10 caught the model returning a
    # "value" that disagreed with its own "reason" text's arithmetic (reasoning correctly computed
    # 33,652; the returned value was 38,167). Multi-item multiply-then-sum is not reliable model
    # arithmetic even at temperature=0. So this field asks only for RAW per-item facts — reading a
    # printed number is what the model is actually reliable at — and material_tons_merge.py (code,
    # not the model) does every multiplication and every sum. See
    # docs/_spec/2026-08-10-aggregate-mix-tons-conversion.md.
    _f("mix_sy_depth_items", "items", "extract",
       "List every hot-mix-asphalt bid item that is measured in SQUARE YARDS (not tons) and whose "
       "OWN description states a thickness in inches (e.g. '2.0\" Type SP Wearing Course Mixture'). "
       "Do NOT list an item already counted in hot_mix_tons (a tons-measured item). Return a JSON "
       "array, one object per qualifying item: "
       "{\"quantity\": <the item's stated SY quantity>, \"unit\": \"SY\", "
       "\"depth_in\": <the thickness stated in that item's own description, in inches>, "
       "\"page\": <page number>, \"note\": <short citation, e.g. the pay item name>}. "
       "Only use a thickness printed in that exact item's own description — never borrow one from "
       "a different item, never assume one. Do NOT multiply, sum, or convert anything yourself — "
       "list each item's own stated numbers verbatim, one entry per item. Return an empty array "
       "[] (not null) if every mix item on this bid schedule is already measured in tons.",
       golden=None, evalkind=None, group="quantities"),
    _f("base_tons", "num", "extract",
       "Total tons of aggregate/granular base material PURCHASED AND PLACED — for example "
       "'AGGREGATE BASE CLASS 5 / 6 / 13', 'GRAVEL SURFACING', 'TRAFFIC SERVICE AGGREGATE'. Do NOT "
       "count 'REMOVE AGGREGATE BASE' or 'REMOVAL OF AGGREGATE BASE': that is demolition of "
       "existing material, not aggregate bought for this job. Do NOT count 'PORTLAND CEMENT' or "
       "'CEMENT STABILIZED SUBGRADE' — binder and additive, not aggregate. 'FULL DEPTH "
       "RECLAMATION' is base work, but its quantity belongs in milling_sy, not here.",
       golden="base_tn", evalkind="num", group="quantities"),
    # base_cy_items — raw per-item companion for base_tons, capturing CY-measured base items
    # instead of silently dropping them. Two source shapes can appear: an item already in CY, and
    # an SY item whose own description states a thickness. The model reports each item's OWN
    # stated numbers only — no multiplication, no summing, no unit conversion. material_tons_merge.py
    # (code, not the model) resolves each item to a CY contribution and sums them; the density step
    # (CY -> tons) happens there too, using a CSI-supplied constant. This field used to ask the
    # model to pre-compute a single CY total; a live test on 2026-08-10 caught the returned value
    # disagreeing with the arithmetic in its own reason text, so that was moved out of the prompt
    # entirely. See docs/_spec/2026-08-10-aggregate-mix-tons-conversion.md.
    _f("base_cy_items", "items", "extract",
       "List every aggregate/granular base bid item PURCHASED AND PLACED that is NOT already "
       "counted in base_tons (a tons-measured item) — i.e. every base item measured in CUBIC "
       "YARDS, or measured in SQUARE YARDS with its own description stating a thickness in inches. "
       "Do NOT count 'REMOVE AGGREGATE BASE'/'REMOVAL OF AGGREGATE BASE' (demolition, not "
       "aggregate bought for this job), 'PORTLAND CEMENT' or 'CEMENT STABILIZED SUBGRADE' (binder/"
       "additive), or grading/earthwork even if in CY (that belongs in grading_quantity). Do NOT "
       "list 'AGGREGATE SHOULDERING' or 'AGGREGATE SURFACING CLASS 1 / 2 / 5 / SPECIAL' items here "
       "even if they also mention 'base' or 'Class 5' in their name — those belong exclusively in "
       "shoulder_cy_items, matching the existing base_tons/shoulder_tons split. Every qualifying "
       "item belongs in EXACTLY ONE of base_cy_items or shoulder_cy_items, never both. Return a "
       "JSON array, one object per qualifying item: "
       "{\"quantity\": <the item's stated quantity>, \"unit\": \"CY\" or \"SY\", "
       "\"depth_in\": <the thickness stated in that item's own description, in inches — null if "
       "the item is already in CY or no thickness is stated>, \"page\": <page number>, "
       "\"note\": <short citation, e.g. the pay item name>}. Only use a thickness printed in that "
       "exact item's own description — never borrow one from a different item, never assume one. "
       "Do NOT multiply, sum, or convert anything yourself — list each item's own stated numbers "
       "verbatim, one entry per item. Return an empty array [] (not null) if every base item on "
       "this bid schedule is already measured in tons.",
       golden=None, evalkind=None, group="quantities"),
    _f("grading_quantity", "num", "extract",
       "Total cubic yards (CY) of grading / earthwork — common excavation, subgrade excavation, "
       "embankment, borrow. Also count 'SALVAGE AND REUSE EXISTING AGGREGATE' and 'CLEAN ROCK'. "
       "Pavement and base removal is grading work, so count it here WHEN the bid schedule measures "
       "it in cubic yards. When a removal is measured in square yards or tons, do NOT convert it "
       "and do NOT count it here — no verified depth or density factor exists. Such a removal is "
       "not discarded: bituminous milling/surface removal measured in square yards is reported in "
       "milling_sy, and measured in tons it is reported in milling_tons, both unconverted.",
       golden="grade_cy", evalkind="num", group="quantities"),
    _f("shoulder_tons", "num", "extract",
       "Total tons of shoulder aggregate, e.g. 'AGGREGATE SHOULDERING'. 'GRAVEL SURFACING' and "
       "'TRAFFIC SERVICE AGGREGATE' were moved to base_tons by CSI — do not count them here. "
       "'AGGREGATE SURFACING CLASS 1 / 2 / 5 / SPECIAL' is still counted here, pending a CSI ruling.",
       golden="shldr_tn", evalkind="num", group="quantities"),
    # shoulder_cy_items — same shape and rationale as base_cy_items above, scoped to the shoulder
    # bucket (e.g. '... Shouldering Aggregate Surfacing' items). Same no-arithmetic design.
    _f("shoulder_cy_items", "items", "extract",
       "List every shoulder-aggregate bid item that is NOT already counted in shoulder_tons (a "
       "tons-measured item) — i.e. every shoulder item measured in CUBIC YARDS, or measured in "
       "SQUARE YARDS with its own description stating a thickness in inches. This includes "
       "'AGGREGATE SHOULDERING' and 'AGGREGATE SURFACING CLASS 1 / 2 / 5 / SPECIAL' items, matching "
       "shoulder_tons's existing scope. Do NOT list 'GRAVEL SURFACING' or 'TRAFFIC SERVICE "
       "AGGREGATE' items here — those belong in base_cy_items. Every qualifying item belongs in "
       "EXACTLY ONE of base_cy_items or shoulder_cy_items, never both. Return a JSON array, one "
       "object per qualifying item: "
       "{\"quantity\": <the item's stated quantity>, \"unit\": \"CY\" or \"SY\", "
       "\"depth_in\": <the thickness stated in that item's own description, in inches — null if "
       "the item is already in CY or no thickness is stated>, \"page\": <page number>, "
       "\"note\": <short citation, e.g. the pay item name>}. Only use a thickness printed in that "
       "exact item's own description — never borrow one from a different item, never assume one. "
       "Do NOT multiply, sum, or convert anything yourself — list each item's own stated numbers "
       "verbatim, one entry per item. Return an empty array [] (not null) if every shoulder item on "
       "this bid schedule is already measured in tons.",
       golden=None, evalkind=None, group="quantities"),
    _f("milling_sy", "num", "extract",
       "Total square yards (SY) of milling and bituminous pavement removal: 'MILL BITUMINOUS "
       "SURFACE', 'REMOVE BITUMINOUS PAVEMENT', 'REMOVAL OF BITUMINOUS SURFACING', and 'FULL DEPTH "
       "RECLAMATION' (CSI ruled FDR is base work, but its quantity is reported here because it is "
       "measured in SY). Do NOT count 'REMOVE CONCRETE DRIVEWAY PAVEMENT' or 'REMOVE BITUMINOUS "
       "DRIVEWAY PAVEMENT'. Do NOT count concrete pavement removal — that is grading. Report square "
       "yards only; if the bid schedule measures milling in tons, report those tons in "
       "milling_tons instead and leave this field null rather than converting.",
       golden="mill_sy", evalkind="num", group="quantities"),
    # milling_tons / milling_measured_unit — capture the value AND its native unit, DO NOT CONVERT.
    # NDDOT pays milling by the ton (NDDOT spec §411.06, Pay Unit "Ton or Square Yard"), so on an ND
    # plan milling_sy is legitimately null while a real quantity exists. Dunn Job 23388 is the case:
    # 63,092 T MILLING PAVEMENT SURFACE + 3,915 T REMOVAL OF BITUMINOUS SURFACING = 67,007 T that
    # used to be dropped silently, alongside 408,216 SY of FDR that milling_sy correctly holds — so
    # a single (value, unit) pair could not describe this plan and the shape is per-unit subtotals.
    # No conversion is attempted anywhere: no verified milling depth factor exists (bucket_hierarchy's
    # 1.75 Ton/CY is unverified, and SDDOT's 1.50 tons/CY is salvaged granular material, a different
    # material and state). Design + the payload-assembly edit: docs/_spec/2026-08-10-milling-unit-capture.md.
    _f("milling_tons", "num", "extract",
       "Total quantity of milling / bituminous-surface-removal items that this bid schedule measures "
       "in TONS — e.g. ND 'MILLING PAVEMENT SURFACE' (TON), 'REMOVAL OF BITUMINOUS SURFACING' (TON). "
       "Report the tons EXACTLY as stated and DO NOT convert them to square yards. Include the "
       "TON-measured lines from BOTH kinds of pay item and ADD THEM TOGETHER: the milling items "
       "(e.g. 'MILLING PAVEMENT SURFACE') AND the removal-of-existing-bituminous items (e.g. "
       "'REMOVAL OF BITUMINOUS SURFACING', 'REMOVE BITUMINOUS PAVEMENT') — CSI classes both as the "
       "same work, and the two often sit in different sections of the schedule (a removal item in "
       "the 200-series section, a milling item in the 400-series). Sum only items whose unit is TON. "
       "Any pay item named in the milling_sy definition belongs HERE instead whenever its unit is "
       "TON — milling_sy takes the square-yard lines, this field takes the ton lines, and no line "
       "is left out of both. There is typically MORE THAN ONE such line and they sit many pages "
       "apart, so before answering scan the WHOLE bid schedule for every TON-measured milling or "
       "bituminous-removal line and add them; answering with only the largest single line is wrong. "
       "Where the same pay item is printed on more than one revision of the same proposal page, "
       "count it once. Null if this bid schedule measures no milling item in tons (the "
       "normal case for MN and SD, where milling is bid by the square yard and belongs in "
       "milling_sy).",
       golden=None, evalkind=None, group="quantities"),
    _f("milling_measured_unit", "str", "extract",
       "Which unit(s) this bid schedule measures milling / bituminous-surface-removal in. Answer "
       "with EXACTLY ONE of these tokens: 'SY' (every milling item is in square yards), 'TON' "
       "(every milling item is in tons), 'SY+TON' (both units appear — e.g. FULL DEPTH RECLAMATION "
       "in SY alongside MILLING PAVEMENT SURFACE in TON), 'OTHER' (a milling item is measured in "
       "some other unit such as CY, LF, LS or STA), or 'NONE' if this bid schedule contains no "
       "milling or bituminous-surface-removal item at all. 'NONE' is the answer for 'there is no "
       "such item' — do not use null for that.",
       golden=None, evalkind=None, group="quantities"),
    # crushing_tons / stockpile_tons DELIBERATELY UNCHANGED. CSI has not answered whether crushing
    # and stockpile stay excluded (quantity_crosswalk.py::CSI_OPEN_QUESTIONS_2026_08_07). Writing a
    # clause here would be inventing a ruling. Left as-is and recorded as open.
    _f("crushing_tons", "num", "extract", "Total tons of crushed aggregate to be produced.",
       golden="crush_tn", evalkind="num", group="quantities"),
    _f("stockpile_tons", "num", "extract", "Total tons of stockpile material.",
       golden="stock_tn", evalkind="num", group="quantities"),
    _f("box_culvert", "bool", "extract", "true if a box culvert is in scope, false if not.",
       golden="box", evalkind="bool", group="quantities"),
    # constraints / contract
    _f("prevailing_wages", "bool", "extract",
       "true if prevailing-wage / Davis-Bacon rates apply, false if not.",
       golden="prevailing_wages", evalkind="bool", group="constraints"),
    _f("construction_start", "date", "extract",
       "Required/earliest construction start date or notice-to-proceed (YYYY-MM-DD if given). Usually in the agreement near the front.",
       golden=None, evalkind=None, group="constraints"),
    _f("construction_end", "date", "extract",
       "Substantial-completion / final-completion date or contract-time deadline (YYYY-MM-DD if given). Usually in the agreement near the front.",
       golden="completion_date", evalkind="date", group="constraints"),
    _f("traffic_level", "str", "rag",
       "Aggregate traffic-level / mix spec that drives pit vs quarry. MN: a traffic-level code "
       "(e.g. '28S', '44', '58H'); ND/SD: a Superpave/Marshall class such as 'Superpave FAA 45' or "
       "'Class 41' (often a bid-schedule pay item). Return the code/class as written; null if not stated.",
       golden=None, evalkind=None, group="constraints", doc="either"),
    _f("phasing_requirements", "str", "rag",
       "Whether work must be built in defined phases/stages and a short summary of the sequence; null if none.",
       golden=None, evalkind=None, group="constraints"),
    # dates — routed through RAG because they're scattered (advertisement, agreement, special
    # provisions) and smart_truncate drops the middle where the completion clauses often sit.
    # This is the RAG FALLBACK, not the primary read. The deterministic 7th process_pdf stage
    # (backend/bid_date_bridge.py -> 04_tools/bid_date/) overwrites record["bid_deadline"] whenever
    # it finds one; this description only decides the plans where that stage returns not_found.
    # The "do NOT return" list is not padding — the deterministic parser had to be taught to reject
    # each of those, and they are exactly what a model handed five retrieved chunks reaches for.
    _f("bid_deadline", "str", "rag",
       "Bid opening / bid submission deadline — the date AND clock time (with time zone if given) "
       "that bids are due. Usually on the Advertisement for Bids page or the proposal cover, worded "
       "'bids will be received ... until <time> on <date>'. MnDOT/SDDOT proposal covers state it as "
       "two labelled fields instead: 'Letting Date: August 20, 2025' with 'Bids Close: 9:30 a.m. "
       "CST' — combine them. Do NOT return: a pre-bid conference date, a deadline for bidder "
       "questions or substitution requests (usually a week earlier), a plan-approval or "
       "certification date, or a substantial/final completion date. Return as written; null if not "
       "stated.",
       golden=None, evalkind=None, group="constraints", doc="either"),
    _f("substantial_completion", "str", "rag",
       "Substantial-completion date or deadline (the date the work must be usable). May be a calendar "
       "date or a working/calendar-day count. Return as written; null if not stated.",
       golden=None, evalkind=None, group="constraints", doc="either"),
    _f("final_completion", "str", "rag",
       "Final-completion date or deadline (all work incl. cleanup done). May be a calendar date or a "
       "working/calendar-day count. Return as written; null if not stated.",
       golden=None, evalkind=None, group="constraints", doc="either"),
]

# ── Array fields (lists of objects in the JSON; flattened to free-text in the CSV) ──
# special_requirements: [{text, page}] · gotchas: [{code, evidence, page, confidence}]
ARRAY_FIELDS = [
    {"name": "special_requirements", "source": "rag", "golden": "special_provisions",
     "desc": "Notable non-standard requirements that affect cost/scope (not the routine boilerplate)."},
    {"name": "gotchas", "source": "rag", "golden": "gotcha_types",
     "desc": "Cost/risk flags present in the plan, each tagged with a taxonomy code (see 01_pipeline/taxonomy.py)."},
]

SCALAR_NAMES = [f["name"] for f in SCALAR_FIELDS]
EXTRACT_FIELDS = [f for f in SCALAR_FIELDS if f["source"] == "extract"]   # whole-doc prompt
RAG_SCALAR_FIELDS = [f for f in SCALAR_FIELDS if f["source"] == "rag"]    # structured retrieval

# golden_col -> (schema_field_or_array_name, evalkind|"review") for 03_evaluation/eval_extraction.py.
# evalkind=None in the spec => "review" (human-judged side-by-side, not auto-scored).
GOLDEN_MAP = {}
for _f_ in SCALAR_FIELDS:
    if _f_["golden"]:
        GOLDEN_MAP[_f_["golden"]] = (_f_["name"], _f_["evalkind"] or "review")
for _a_ in ARRAY_FIELDS:
    if _a_["golden"]:
        GOLDEN_MAP[_a_["golden"]] = (_a_["name"], "review")


# ── Milling unit status (derived — no model call, no conversion) ───────────────
# The tenth instance of this repo's standing rule: a failure and a legitimate empty answer must
# never share a return value. Before this, `milling_sy = null` meant all three of "milling is
# measured in tons", "this plan has no milling item" and "extraction produced no answer".
#
# Derived rather than stored so the status can never drift from the values it describes.
# It NEVER converts and never infers a quantity — it only reports which of the six situations the
# record is in. Spec: docs/_spec/2026-08-10-milling-unit-capture.md.
MILLING_UNIT_TOKENS = ("SY", "TON", "SY+TON", "OTHER", "NONE")

MILLING_UNIT_STATUSES = (
    "sy_only",       # unit SY — milling_sy carries the whole quantity, nothing missing
    "tons_only",     # unit TON — CONVERSION_REQUIRED: milling_sy null BY DESIGN, milling_tons has it
    "sy_and_tons",   # unit SY+TON — both real; the two totals are NOT addable (Dunn Job 23388)
    "other_unit",    # a milling item in CY/LF/LS/STA — named rather than dropped
    "not_present",   # the model asserted there is no milling item. A legitimate empty answer.
    "unknown",       # no answer at all — extraction failure. NEVER reported as not_present.
    "inconsistent",  # the declared unit contradicts the quantities. Surfaced, not silently resolved.
)


def _cell_value(record, name):
    """The value out of a record's cell, tolerating a bare scalar (some callers hold flat dicts)."""
    c = record.get(name)
    if isinstance(c, dict):
        return c.get("value")
    return c


def milling_unit_status(record) -> str:
    """One of MILLING_UNIT_STATUSES for this record. Pure; never mutates and never converts."""
    unit = _cell_value(record, "milling_measured_unit")
    unit = str(unit).strip().upper().replace(" ", "") if unit not in (None, "") else None
    sy = _cell_value(record, "milling_sy")
    tons = _cell_value(record, "milling_tons")
    has_sy = isinstance(sy, (int, float)) and sy > 0
    has_tons = isinstance(tons, (int, float)) and tons > 0

    if unit not in MILLING_UNIT_TOKENS:
        # No answer, or an answer outside the closed vocabulary. Either way we do not know what the
        # schedule measured — and "we do not know" is not "there was nothing there".
        return "unknown"
    if unit == "NONE":
        return "not_present" if not (has_sy or has_tons) else "inconsistent"
    if unit == "SY":
        # A declared unit with no quantity behind it is a contradiction, not a clean SY plan.
        return "sy_only" if (has_sy and not has_tons) else "inconsistent"
    if unit == "TON":
        return "tons_only" if (has_tons and not has_sy) else "inconsistent"
    if unit == "SY+TON":
        return "sy_and_tons" if (has_sy and has_tons) else "inconsistent"
    return "other_unit"


# ── Aggregate/mix CY unit status (derived — no model call, no conversion) ──────
# Same standing rule as milling_unit_status above, applied to base_tons/shoulder_tons/hot_mix_tons:
# a null items list must stay distinguishable from "nothing to capture" and from "extraction did
# not answer". Unlike milling_unit_status, there is no model-asserted unit-summary field to read
# here at all — base_cy_items/shoulder_cy_items/mix_sy_depth_items are RAW per-item facts (see
# their field descriptions), so the status is derived entirely from the native tons field plus
# this function's own classification of each item — one fewer thing the model can get wrong.
# Spec: docs/_spec/2026-08-10-aggregate-mix-tons-conversion.md.
AGGREGATE_UNIT_STATUSES = (
    "tons_only",            # items list is empty and the native tons field has a real value
    "cy_only",              # every convertible item is already in CY (a direct read)
    "sy_converted_only",    # every convertible item came from an SY-with-stated-depth conversion
    "mixed",                # both a direct CY read and an SY-converted item are present
    "sy_no_depth_present",  # at least one item is SY with NO stated depth — seen but not
                             # convertible; named rather than silently excluded from the total
    "not_present",          # items list is empty and the native tons field also has no value
    "unknown",               # the items field itself is null — extraction produced no answer at
                             # all. NEVER reported as not_present, which is a real, asserted answer.
    "inconsistent",          # defensive: an item resolves to neither CY-direct nor SY-converted
                             # nor SY-no-depth (e.g. a garbled unit token) — surfaced, not guessed
)


def resolve_cy_item(item: dict):
    """One raw {quantity, unit, depth_in, ...} item -> CY contribution, or None if it cannot be
    converted without guessing (an SY item with no stated depth, or a garbled/unrecognised unit).
    Pure arithmetic, shared by material_tons_merge.py and the status functions below so the two
    can never disagree about what a given item resolves to. CY = SY * inches / 36 — pure geometry,
    no assumed density; the density step is a separate, later multiplication in
    material_tons_merge.py, never here. Used for base_cy_items/shoulder_cy_items ONLY — the mix
    bucket has no CY intermediate at all, see resolve_sy_depth_product below."""
    if not isinstance(item, dict):
        return None
    quantity = item.get("quantity")
    if not isinstance(quantity, (int, float)):
        return None
    unit = str(item.get("unit") or "").strip().upper()
    if unit == "CY":
        return quantity
    if unit == "SY":
        depth_in = item.get("depth_in")
        if isinstance(depth_in, (int, float)) and depth_in > 0:
            return quantity * depth_in / 36
        return None  # SY with no usable stated depth — a real item, just not convertible
    return None  # an unrecognised unit token


def resolve_sy_depth_product(item: dict):
    """One raw mix_sy_depth_items entry -> its SY*inches product, or None if unconvertible.
    Deliberately NOT resolve_cy_item: mix skips the /36 CY-volume step entirely — its density
    constant (MIX_TON_PER_SY_INCH) already operates on the raw SY*inches product, per the
    CSI-supplied formula. Using resolve_cy_item here was a real bug caught in testing: it silently
    divided the mix product by 36, undercounting mix tons by 36x. Kept as its own function, not a
    branch inside resolve_cy_item, so the two can never be conflated again."""
    if not isinstance(item, dict):
        return None
    quantity = item.get("quantity")
    depth_in = item.get("depth_in")
    if not isinstance(quantity, (int, float)):
        return None
    if str(item.get("unit") or "").strip().upper() != "SY":
        return None
    if not (isinstance(depth_in, (int, float)) and depth_in > 0):
        return None  # SY with no usable stated depth — a real item, just not convertible
    return quantity * depth_in


def _aggregate_unit_status(record, tons_field: str, items_field: str, resolver=resolve_cy_item) -> str:
    """Shared logic behind base_unit_status/shoulder_unit_status/mix_unit_status. Pure; never
    mutates and never converts — classifies each item with `resolver` rather than trusting a
    separate model-asserted summary field. `resolver` defaults to resolve_cy_item (base/shoulder);
    mix_unit_status passes resolve_sy_depth_product instead."""
    tons = _cell_value(record, tons_field)
    has_tons = isinstance(tons, (int, float)) and tons > 0
    items = _cell_value(record, items_field)

    if items is None:
        return "unknown"
    if not isinstance(items, list):
        return "inconsistent"
    if not items:
        return "tons_only" if has_tons else "not_present"

    has_cy_direct = False
    has_sy_converted = False
    has_unconvertible = False
    for item in items:
        contribution = resolver(item)
        if contribution is None:
            has_unconvertible = True
            continue
        unit = str((item or {}).get("unit") or "").strip().upper()
        if unit == "CY":
            has_cy_direct = True
        elif unit == "SY":
            has_sy_converted = True

    if has_unconvertible:
        return "sy_no_depth_present"
    if has_cy_direct and has_sy_converted:
        return "mixed"
    if has_cy_direct:
        return "cy_only"
    if has_sy_converted:
        return "sy_converted_only"
    return "inconsistent"  # non-empty list but nothing classified as anything — a garbled response


def base_unit_status(record) -> str:
    """One of AGGREGATE_UNIT_STATUSES for this record's base bucket."""
    return _aggregate_unit_status(record, "base_tons", "base_cy_items")


def shoulder_unit_status(record) -> str:
    """One of AGGREGATE_UNIT_STATUSES for this record's shoulder bucket."""
    return _aggregate_unit_status(record, "shoulder_tons", "shoulder_cy_items")


def mix_unit_status(record) -> str:
    """One of AGGREGATE_UNIT_STATUSES for this record's mix bucket (hot_mix_tons /
    mix_sy_depth_items). Uses resolve_sy_depth_product, NOT resolve_cy_item — mix has no CY
    intermediate, see that function's docstring."""
    return _aggregate_unit_status(record, "hot_mix_tons", "mix_sy_depth_items",
                                  resolver=resolve_sy_depth_product)


# ── Record construction ────────────────────────────────────────────────────────

def cell(value=None, confidence="", page=None, reason=""):
    """A scalar field's value-object: the unit of provenance in the JSON. `reason` is the model's
    own short justification — a quoted/paraphrased line for "high", or why it's unsure for "low"."""
    return {"value": value, "confidence": confidence, "page": page, "reason": reason}


def blank_record(plan_id, source_file, run_date):
    """A fully-formed empty record (all scalars null cells, arrays empty). Extractors fill it.
    `document_structure` (page-size doc classification: type + where the maps live) is filled by
    run.py from lib.detect_structure."""
    rec = {"plan_id": plan_id, "source_file": source_file, "run_date": run_date,
           "document_structure": {}}
    for f in SCALAR_FIELDS:
        rec[f["name"]] = cell()
    for a in ARRAY_FIELDS:
        rec[a["name"]] = []
    return rec


# ── CSV flattening (the review view) ────────────────────────────────────────────
# doc_type/proposal_pages/map_pages come from the record's document_structure (page-size detection).
META_COLS = ["plan_id", "source_file", "outcome", "doc_type", "proposal_pages", "map_pages",
             "pages", "n_chunks", "run_date"]
ARRAY_COLS = ["special_requirements", "gotchas", "gotchas_evidence"]
PROV_COLS = ["citations", "confidence"]
# value columns first (the scannable block), then array text, then compact provenance.
CSV_COLUMNS = META_COLS + SCALAR_NAMES + ARRAY_COLS + PROV_COLS


def flatten_row(record, meta=None):
    """Flatten a JSON record into one flat dict for results.csv: clean value columns (left,
    for scanning) + free-text special_requirements/gotchas + compact citations/confidence
    columns carrying the per-field provenance. `meta` supplies the run context (outcome,
    pages, n_chunks) that isn't part of the extraction schema."""
    meta = meta or {}
    ds = record.get("document_structure") or {}
    row = {"plan_id": record.get("plan_id", ""), "source_file": record.get("source_file", ""),
           "run_date": record.get("run_date", ""),
           "doc_type": ds.get("type", ""), "proposal_pages": ds.get("proposal_ranges", ""),
           "map_pages": ds.get("map_ranges", ""),
           **{k: meta.get(k, "") for k in ("outcome", "pages", "n_chunks")}}
    cites, confs = [], []
    for name in SCALAR_NAMES:
        c = record.get(name) or {}
        row[name] = c.get("value")
        if c.get("page"):
            cites.append(f"{name}=p.{c['page']}")
        conf = c.get("confidence")
        if conf and conf != "high":
            confs.append(f"{name}={conf}")
    sr = record.get("special_requirements") or []
    row["special_requirements"] = "; ".join(
        f"{x.get('text', '')} (p.{x.get('page')})" if x.get("page") else x.get("text", "") for x in sr)
    g = record.get("gotchas") or []
    row["gotchas"] = "; ".join(
        f"{x.get('code', '')} (p.{x.get('page')})" if x.get("page") else x.get("code", "") for x in g)
    row["gotchas_evidence"] = " | ".join(f"{x.get('code', '')}: {x.get('evidence', '')}" for x in g)
    row["citations"] = "; ".join(cites)
    row["confidence"] = "; ".join(confs)
    return row


# ── Long/tidy flags table (02_outputs/flags.csv): one row per flagged item ─────────
# Complements results.csv (one WIDE row per plan). This is one row per flag — every taxonomy gotcha
# plus the field-flags (traffic_level, phasing, each special_requirement) — so the client can review
# gotcha-by-gotcha and we can grow the taxonomy. flag_type = the specific taxonomy code (for gotchas)
# or the field name (for field-flags); family = the 5-family group.
FLAG_COLUMNS = ["plan_id", "source_file", "outcome", "doc_type", "state", "section",
                "flag_type", "family", "evidence", "page", "confidence"]
# Family for the non-gotcha field-flags (gotcha families come from taxonomy.py, passed in).
FLAG_FIELD_FAMILY = {
    "traffic_level": "Site & scope risk",
    "phasing_requirements": "Schedule & sequencing",
    "special_requirement": "Contract & compliance",
}


def flag_rows(record, meta=None, page_section=None, gotcha_family=None):
    """Explode a record into long/tidy flag rows (one per flagged item) for 02_outputs/flags.csv.
    `page_section` maps a page number → its section tag (so we can say WHERE the flag came from);
    `gotcha_family` maps a taxonomy code → its family. Both are passed in to keep schema.py
    dependency-light (the caller builds them from the collection + taxonomy.py)."""
    meta = meta or {}
    page_section = page_section or {}
    gotcha_family = gotcha_family or {}
    ds = record.get("document_structure") or {}
    base = {"plan_id": record.get("plan_id", ""), "source_file": record.get("source_file", ""),
            "outcome": meta.get("outcome", ""), "doc_type": ds.get("type", ""),
            "state": (record.get("state") or {}).get("value", "")}

    def _row(page, flag_type, family, evidence, confidence):
        return {**base, "section": page_section.get(page, ""), "flag_type": flag_type,
                "family": family, "evidence": evidence, "page": page if page else "",
                "confidence": confidence or ""}

    rows = []
    for gch in record.get("gotchas") or []:
        rows.append(_row(gch.get("page"), gch.get("code", ""), gotcha_family.get(gch.get("code"), ""),
                         gch.get("evidence", ""), gch.get("confidence", "")))
    for fname in ("traffic_level", "phasing_requirements"):
        c = record.get(fname) or {}
        if c.get("value"):
            rows.append(_row(c.get("page"), fname, FLAG_FIELD_FAMILY.get(fname, ""),
                             c.get("value"), c.get("confidence", "")))
    for x in record.get("special_requirements") or []:
        if x.get("text"):
            rows.append(_row(x.get("page"), "special_requirement",
                             FLAG_FIELD_FAMILY["special_requirement"], x.get("text"), ""))
    return rows


# ── Prompt helpers ──────────────────────────────────────────────────────────────

def field_lines(fields):
    """Bullet list of `- name (type): desc` for a set of field specs — keeps every prompt in
    sync with the schema (both the whole-doc extractor and the structured RAG step use this)."""
    return "\n".join(f"- {f['name']} ({f['type']}): {f['desc']}" for f in fields)


def extract_prompt_fields():
    """Field list for the whole-doc extraction prompt (source=='extract' fields)."""
    return field_lines(EXTRACT_FIELDS)
