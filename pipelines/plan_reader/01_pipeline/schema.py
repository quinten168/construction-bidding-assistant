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
    _f("hot_mix_tons", "num", "extract", "Total tons of hot mix asphalt (HMA) from the bid schedule.",
       golden="mix_tn", evalkind="num", group="quantities"),
    _f("base_tons", "num", "extract", "Total tons of aggregate/granular base material.",
       golden="base_tn", evalkind="num", group="quantities"),
    _f("grading_quantity", "num", "extract", "Total cubic yards of grading / earthwork.",
       golden="grade_cy", evalkind="num", group="quantities"),
    _f("shoulder_tons", "num", "extract", "Total tons of shoulder gravel/aggregate.",
       golden="shldr_tn", evalkind="num", group="quantities"),
    _f("milling_sy", "num", "extract", "Total square yards of milling / pavement removal.",
       golden="mill_sy", evalkind="num", group="quantities"),
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
    _f("bid_deadline", "str", "rag",
       "Bid opening / bid submission deadline — the date (and time + time zone if given) bids are "
       "due. Usually on the advertisement or proposal cover. Return as written; null if not stated.",
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


# ── Record construction ────────────────────────────────────────────────────────

def cell(value=None, confidence="", page=None):
    """A scalar field's value-object: the unit of provenance in the JSON."""
    return {"value": value, "confidence": confidence, "page": page}


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
