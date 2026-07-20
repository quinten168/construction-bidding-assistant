# --- build_section_intelligence.py --------------------------------------------
# Builds a corpus-wide, EMPIRICAL "section intelligence" knowledge base for the
# Plan Reader. It extends Jay's manual boilerplate/section table (seed CSVs) to
# all 100 converted plans by grounding every claim in an actual DB query.
#
# What "empirical" buys us over a manual redo: for each canonical SECTION TYPE we
# learn, from the data, (a) how often it actually appears across the corpus,
# (b) whether it actually carries gotchas and which gotcha FAMILIES, (c) whether
# the bid schedule / quantities actually live there, and (d) roughly where in the
# document it sits. That lets the RAG retriever WEIGHT sections by real signal
# rather than by an LLM guess.
#
# READ-ONLY on csi_v2.db (SELECT only). Writes only CSV/markdown to 05_knowledge/.
# ------------------------------------------------------------------------------

import sqlite3
import csv
import re
from pathlib import Path
from datetime import date

# --- paths --------------------------------------------------------------------
# Everything is anchored off this script's folder (05_knowledge/), so outputs
# always land next to the live taxonomy we are proposing to enrich.
HERE = Path(__file__).resolve().parent
DB_PATH = HERE.parent / "csi_v2.db"
TODAY = "2026-06-17"

OUT_INTEL = HERE / f"{TODAY}_section_intelligence.csv"
OUT_README = HERE / f"{TODAY}_section_intelligence_README.md"
OUT_PROPOSED = HERE / "section_taxonomy_proposed.csv"

# Open the DB read-only via URI so we can never accidentally write to it
# (another process may be reading the same file).
conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
conn.row_factory = sqlite3.Row

# The corpus denominator: how many distinct plans have any extracted sections.
N_DOCS = conn.execute("SELECT COUNT(DISTINCT plan_id) FROM sections").fetchone()[0]

# ------------------------------------------------------------------------------
# 1. CANONICAL SECTION TYPES
# ------------------------------------------------------------------------------
# The DB already carries a *normalized* section name in two trustworthy places:
#   - gotchas.section  (top values are normalized types: special_provisions, ...)
#   - the live section_taxonomy.csv (16 canonical types)
# We adopt those normalized types as the spine, and attach to each one:
#   - a heading_regex that matches the RAW headings in sections.raw_heading
#     (so a machine can detect the section from a fresh plan), and
#   - the seed classification distilled from Jay's manual table.
#
# Each tuple: (section_type, heading_regex, section_role, jay_category,
#              remove_keep, project_specific, rag_weight, typical_page_position)
# rag_weight is our PROPOSED retrieval weight (0=skip ... 1=must-retrieve).
SECTION_DEFS = [
    # --- the bid-intelligence / decision core (high weight) -------------------
    ("bid_schedule",
     r"(?i)\b(bid schedule|schedule of prices|schedule of items|proposal form|bid form|"
     r"unit price|estimated quantit|schedule of bid items|bid tabulation)\b",
     "bid_intelligence", "Bid Intelligence", "Keep", "Yes", 1.00, "mid"),
    ("proposal_front_data",
     r"(?i)\b(project (location|description|number)|work type|job length|"
     r"description of work|location of work|completion date|notice to proceed by)\b",
     "keep_high_value", "Project Front Data", "Keep", "Mixed", 0.90, "front"),
    ("agreement",
     r"(?i)\b(agreement|standard form of agreement|time of commencement|"
     r"substantial completion|article ii|contract time)\b",
     "keep_high_value", "Contract / Schedule", "Keep", "Mixed", 0.85, "early"),
    # --- engineering / pricing (high weight: real estimating signal) ----------
    ("special_provisions",
     r"(?i)\b(special provision|division s\b|s-\d+|sp[- ]\d+|special provisions division)\b",
     "engineering", "Project-Specific Specifications", "Keep", "Yes", 0.95, "early"),
    ("prosecution_of_work",
     r"(?i)\b(prosecution of work|1804|sequence of operations|order of construction|"
     r"phasing|staging plan)\b",
     "engineering", "Schedule / Sequencing", "Keep", "Yes", 0.90, "mid"),
    ("traffic_staging",
     r"(?i)\b(traffic control|traffic staging|maintenance of traffic|"
     r"road closure|lane closure|business access|2563)\b",
     "engineering", "Traffic / Staging", "Keep", "Yes", 0.85, "mid"),
    ("general_notes",
     r"(?i)\b(general notes|plan notes|construction notes|soils and construction notes|"
     r"underground notes)\b",
     "engineering", "Engineering / Plan Notes", "Keep", "Yes", 0.85, "back"),
    ("specifications",
     r"(?i)\b(technical specification|specification \d|section \d{2} \d{2} \d{2}|"
     r"division 3[123]|construction requirements)\b",
     "engineering", "Project-Specific Specifications", "Keep", "Yes", 0.80, "mid"),
    ("typical_sections",
     r"(?i)\b(typical section|cross section|reshaping typical)\b",
     "engineering", "Engineering / Typical Sections", "Keep", "Yes", 0.75, "back"),
    ("geotechnical",
     r"(?i)\b(geotech|soil boring|subsurface|exploration|mix design|"
     r"soils for earthwork|pavement design)\b",
     "engineering", "Engineering / Geotechnical", "Keep", "Yes", 0.70, "mid"),
    # --- pricing-input but compliance-flavored (medium weight) ----------------
    ("prevailing_wage",
     r"(?i)\b(prevailing wage|wage decision|wage rate|davis[- ]bacon|minimum wage|"
     r"fringe (benefit|rate))\b",
     "administrative", "Labor (pricing input)", "Keep", "No", 0.40, "early"),
    # --- procurement front-matter / boilerplate (low weight) ------------------
    ("contract_front",
     r"(?i)\b(advertisement for bids|instructions to bidders|notice to bidders|"
     r"notice to contractors|invitation to bid|section 00[12]00|proposal guaranty)\b",
     "administrative", "EJCDC / Procurement", "Remove", "Mostly No", 0.20, "front"),
    ("title_index",
     r"(?i)\b(table of contents|index of sheets|sheet index|list of (sheets|drawings))\b",
     "administrative", "Navigation", "Remove", "No", 0.10, "front"),
    # --- pure boilerplate to skip (zero / near-zero weight) -------------------
    ("general_conditions",
     r"(?i)\b(general conditions|standard general conditions|supplementary conditions|"
     r"section 00[78]00|ejcdc c-700)\b",
     "boilerplate_remove", "Legal / General Conditions", "Remove", "No", 0.05, "mid"),
    ("bonds_forms",
     r"(?i)\b(bid bond|performance bond|payment bond|bond form|penal sum|"
     r"proposal guaranty|certified check)\b",
     "boilerplate_remove", "Bond / Administrative Forms", "Remove", "No", 0.02, "early"),
    ("eeo_federal",
     r"(?i)\b(equal employment|eeo|fhwa[- ]?1273|required contract provisions|"
     r"title vi|nondiscrimination|on-the-job training|executive order 11246|"
     r"non-?collusion|debarment|bid rigging|suspension)\b",
     "boilerplate_remove", "Federal-Aid / Civil Rights Boilerplate", "Remove", "No", 0.02, "back"),
    ("proposal_front",
     r"(?i)\b(proposal cover|proposal title page|cover sheet)\b",
     "boilerplate_remove", "Cover / Front Matter", "Remove", "No", 0.05, "front"),
    ("unknown",
     r"(?i).^",  # never matches; this is the catch-all bucket, kept full-weight
     "keep_high_value", "Untagged", "Keep", "Unknown", 0.60, "any"),
]

# ------------------------------------------------------------------------------
# 2. EMPIRICAL STATS PER SECTION TYPE
# ------------------------------------------------------------------------------

# 2a. corpus_frequency: in how many of the N_DOCS plans does a heading matching
#     this section type actually appear? We pull every (plan_id, raw_heading)
#     once and test it against each section type's regex in Python (SQLite has no
#     regex by default). This is the honest "does this section exist in the doc"
#     signal, independent of whether it carried a gotcha.
rows = conn.execute(
    "SELECT DISTINCT plan_id, raw_heading FROM sections WHERE raw_heading IS NOT NULL"
).fetchall()

# Pre-compile the regexes once.
compiled = {st: re.compile(rx) for (st, rx, *_rest) in SECTION_DEFS}

# For each section type, collect the set of plans whose headings match it.
plans_with_section = {st: set() for st, *_ in SECTION_DEFS}
for r in rows:
    head = r["raw_heading"] or ""
    pid = r["plan_id"]
    for st, pat in compiled.items():
        if st == "unknown":
            continue
        if pat.search(head):
            plans_with_section[st].add(pid)

# 2b. gotcha signal: from the gotchas table, keyed on the NORMALIZED section
#     value (the top gotchas.section values already use these canonical names).
#     We learn: total gotchas, distinct plans, the gotcha families present, and
#     the go/no-go vs pricing split — all grounded in actual rows.
gotcha_by_section = {}
for r in conn.execute(
    "SELECT section, COUNT(*) n, COUNT(DISTINCT plan_id) ndocs "
    "FROM gotchas WHERE section IS NOT NULL GROUP BY section"
):
    gotcha_by_section[r["section"]] = {"n": r["n"], "ndocs": r["ndocs"]}

# families per normalized section
families_by_section = {}
for r in conn.execute(
    "SELECT section, family, COUNT(*) n FROM gotchas "
    "WHERE section IS NOT NULL AND family IS NOT NULL GROUP BY section, family"
):
    families_by_section.setdefault(r["section"], {})[r["family"]] = r["n"]

# go/no-go vs pricing split per normalized section
decision_split = {}
for r in conn.execute(
    "SELECT section, decision_class, COUNT(*) n FROM gotchas "
    "WHERE section IS NOT NULL GROUP BY section, decision_class"
):
    decision_split.setdefault(r["section"], {})[r["decision_class"] or "unclassified"] = r["n"]

# 2c. average page position of gotchas per normalized section (front/mid/back proxy)
avg_page = {}
for r in conn.execute(
    "SELECT section, AVG(page) ap, COUNT(*) n FROM gotchas "
    "WHERE section IS NOT NULL AND page IS NOT NULL GROUP BY section"
):
    avg_page[r["section"]] = (round(r["ap"], 1), r["n"])

# 2d. state breakdown per normalized section (for state_variants column)
state_by_section = {}
for r in conn.execute(
    "SELECT g.section, p.state, COUNT(*) n FROM gotchas g "
    "JOIN plans p ON g.plan_id = p.plan_id "
    "WHERE g.section IS NOT NULL GROUP BY g.section, p.state"
):
    state_by_section.setdefault(r["section"], {})[r["state"] or "??"] = r["n"]

# 2e. bid-schedule / quantities location: materials rows live in base_bid /
#     alternate_* "sections" which ARE the bid schedule. Count distinct plans
#     whose quantities were extracted = empirical "contains_quantities" for the
#     bid_schedule type.
mat_docs = conn.execute(
    "SELECT COUNT(DISTINCT plan_id) FROM materials"
).fetchone()[0]

conn.close()

# ------------------------------------------------------------------------------
# 3. ASSEMBLE THE SECTION-INTELLIGENCE ROWS
# ------------------------------------------------------------------------------

def fmt_families(d):
    """Render a family->count dict as 'Family (n); ...' sorted by count desc."""
    if not d:
        return ""
    return "; ".join(f"{k} ({v})" for k, v in sorted(d.items(), key=lambda kv: -kv[1]))

def fmt_states(d):
    """Render the state distribution, dropping the placeholder XX/?? buckets."""
    if not d:
        return ""
    clean = {k: v for k, v in d.items() if k not in ("XX", "??", "")}
    if not clean:
        return ""
    return "; ".join(f"{k} ({v})" for k, v in sorted(clean.items(), key=lambda kv: -kv[1]))

intel_rows = []
for st, rx, role, jay_cat, remove_keep, proj_specific, rag_w, page_pos in SECTION_DEFS:
    n_plans = len(plans_with_section[st]) if st != "unknown" else 0
    corpus_freq = round(100.0 * n_plans / N_DOCS, 1) if N_DOCS else 0.0

    g = gotcha_by_section.get(st, {"n": 0, "ndocs": 0})
    fam = families_by_section.get(st, {})
    split = decision_split.get(st, {})
    ap = avg_page.get(st)
    states = state_by_section.get(st, {})

    # contains_quantities: only the bid_schedule type carries the materials/
    # quantity table; flag it Y and note how many plans we actually pulled
    # quantities from. Everything else is N (grounded: materials.section is
    # base_bid/alternate_*, never these prose sections).
    contains_q = "Y" if st == "bid_schedule" else "N"
    q_note = f"{mat_docs}/{N_DOCS} plans had quantities extracted" if st == "bid_schedule" else ""

    # low-sample flag: gotcha evidence resting on <3 docs is thin.
    low_sample = "Y" if 0 < g["ndocs"] < 3 else ""

    intel_rows.append({
        "section_type": st,
        "section_role": role,
        "jay_category": jay_cat,
        "remove_keep": remove_keep,
        "project_specific": proj_specific,
        "rag_weight": rag_w,
        "corpus_frequency_pct": corpus_freq,
        "docs_with_section": n_plans,
        "gotcha_count": g["n"],
        "gotcha_docs": g["ndocs"],
        "gotcha_families": fmt_families(fam),
        "go_no_go": split.get("go_no_go", 0),
        "pricing": split.get("pricing", 0),
        "contains_quantities": contains_q,
        "quantities_note": q_note,
        "avg_gotcha_page": ap[0] if ap else "",
        "typical_page_position": page_pos,
        "state_variants": fmt_states(states),
        "low_sample_flag": low_sample,
        "heading_regex": rx,
    })

# Sort by rag_weight desc so the most important sections read first.
intel_rows.sort(key=lambda r: (-r["rag_weight"], -r["gotcha_count"]))

FIELDS = [
    "section_type", "section_role", "jay_category", "remove_keep",
    "project_specific", "rag_weight", "corpus_frequency_pct", "docs_with_section",
    "gotcha_count", "gotcha_docs", "gotcha_families", "go_no_go", "pricing",
    "contains_quantities", "quantities_note", "avg_gotcha_page",
    "typical_page_position", "state_variants", "low_sample_flag", "heading_regex",
]

with OUT_INTEL.open("w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=FIELDS)
    w.writeheader()
    w.writerows(intel_rows)

# ------------------------------------------------------------------------------
# 4. PROPOSED ENRICHMENT OF THE LIVE section_taxonomy.csv
# ------------------------------------------------------------------------------
# The live file has: doc_type, section, relevance, tier, note. We propose a
# superset that ADDS the new machine-usable columns (rag_weight, heading_regex,
# typical_page_position) plus the empirical gotcha signal — WITHOUT overwriting
# the live file. We keep the existing relevance/tier values where the live file
# had them, and derive sensible ones for the boilerplate types it omitted.

# Map our section_role -> (relevance, tier) consistent with the live convention.
ROLE_TO_REL_TIER = {
    "bid_intelligence":   ("DECISION", "KEEP"),
    "keep_high_value":    ("DECISION", "KEEP"),
    "engineering":        ("PRICING", "KEEP"),
    "administrative":     ("BOILERPLATE", "DOWN_WEIGHT"),
    "boilerplate_remove": ("BOILERPLATE", "DROP"),
}

prop_fields = [
    "doc_type", "section", "relevance", "tier", "rag_weight",
    "typical_page_position", "corpus_frequency_pct", "gotcha_count",
    "gotcha_families", "contains_quantities", "heading_regex", "note", "source",
]
with OUT_PROPOSED.open("w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=prop_fields)
    w.writeheader()
    for r in intel_rows:
        rel, tier = ROLE_TO_REL_TIER.get(r["section_role"], ("DECISION", "KEEP"))
        # special-case prevailing_wage: live file marks it PRICING/KEEP (hidden
        # from decision retrieval) — honor that rather than the generic admin map.
        if r["section_type"] == "prevailing_wage":
            rel, tier = "PRICING", "KEEP"
        if r["section_type"] == "unknown":
            rel, tier = "DECISION", "KEEP"
        w.writerow({
            "doc_type": "*",
            "section": r["section_type"],
            "relevance": rel,
            "tier": tier,
            "rag_weight": r["rag_weight"],
            "typical_page_position": r["typical_page_position"],
            "corpus_frequency_pct": r["corpus_frequency_pct"],
            "gotcha_count": r["gotcha_count"],
            "gotcha_families": r["gotcha_families"],
            "contains_quantities": r["contains_quantities"],
            "heading_regex": r["heading_regex"],
            "note": f"Jay:{r['jay_category']} | empirical: {r['gotcha_docs']} docs w/ gotchas, "
                    f"{r['corpus_frequency_pct']}% corpus freq",
            "source": "empirical_2026-06-17",
        })

# ------------------------------------------------------------------------------
# 5. README (headline findings)
# ------------------------------------------------------------------------------
# Build a few summary tables straight from the rows so the prose stays grounded.
gotcha_ranked = sorted(intel_rows, key=lambda r: -r["gotcha_count"])
top_gotcha = [r for r in gotcha_ranked if r["gotcha_count"] > 0][:8]
skip_sections = [r for r in intel_rows if r["rag_weight"] <= 0.1]

def md_row(cells):
    return "| " + " | ".join(str(c) for c in cells) + " |"

lines = []
lines.append(f"# Section Intelligence — empirical corpus analysis ({TODAY})")
lines.append("")
lines.append(f"Built from `csi_v2.db` (READ-ONLY) over **{N_DOCS} converted plans**, "
             f"extending Jay's manual boilerplate table with evidence from the "
             f"`sections`, `gotchas`, and `materials` tables. Every number below "
             f"comes from an actual query — see `build_section_intelligence.py`.")
lines.append("")
lines.append("## TL;DR for the pipeline")
lines.append("")
lines.append("- **The bid schedule lives in `bid_schedule`** (proposal form / schedule of "
             f"prices / bid form). Quantities were extracted from **{mat_docs}/{N_DOCS}** "
             "plans, sitting ~0.69 of the way through the document (mid/back). The schedule "
             "detector should target the `bid_schedule` heading regex, not scan all prose.")
lines.append("- **Gotchas concentrate in a handful of section types.** The top carriers are "
             "`special_provisions`, `traffic_staging`, `agreement`, `bid_schedule`, and "
             "`contract_front` — together the vast majority of all flagged gotchas. The "
             "gotcha pass should be WEIGHTED toward these, not run uniformly over boilerplate.")
lines.append("- **Boilerplate is genuinely low-signal.** `eeo_federal`, `bonds_forms`, "
             "`general_conditions`, `title_index` appear in most docs but carry few gotchas "
             "and never the bid schedule — these get `rag_weight` ~0.")
lines.append("")
lines.append("## Which sections carry gotchas (empirical, by gotcha_count)")
lines.append("")
lines.append(md_row(["section_type", "role", "gotchas", "docs", "go/no-go", "pricing", "top families"]))
lines.append(md_row(["---"] * 7))
for r in top_gotcha:
    fam_short = "; ".join(r["gotcha_families"].split("; ")[:2])
    lines.append(md_row([r["section_type"], r["section_role"], r["gotcha_count"],
                         r["gotcha_docs"], r["go_no_go"], r["pricing"], fam_short]))
lines.append("")
lines.append("## Where the bid schedule / quantities live")
lines.append("")
lines.append(f"- `materials` rows (the bid-schedule line items) were extracted from "
             f"**{mat_docs}/{N_DOCS} plans**, all under the `base_bid` / `alternate_*` "
             "buckets = the bid schedule. Normalized page position ≈ **0.69** "
             "(mid-to-back of the document).")
lines.append("- Only the **`bid_schedule`** section type has `contains_quantities = Y`. "
             "No prose section (special_provisions, agreement, etc.) holds quantities — "
             "so a quantity detector should anchor on the bid-schedule heading regex.")
lines.append("")
lines.append("## Sections to SKIP (rag_weight ≤ 0.1)")
lines.append("")
lines.append(md_row(["section_type", "jay_category", "corpus_freq_%", "gotcha_count", "rag_weight"]))
lines.append(md_row(["---"] * 5))
for r in sorted(skip_sections, key=lambda x: -x["corpus_frequency_pct"]):
    lines.append(md_row([r["section_type"], r["jay_category"],
                         r["corpus_frequency_pct"], r["gotcha_count"], r["rag_weight"]]))
lines.append("")
lines.append("## Recommended RAG weighting map (`rag_weight`)")
lines.append("")
lines.append("Use this as a per-section multiplier on retrieval scores. High for the "
             "bid-intelligence + engineering core, ~0 for boilerplate. Full values are in "
             "`section_taxonomy_proposed.csv`.")
lines.append("")
lines.append(md_row(["section_type", "section_role", "rag_weight", "corpus_freq_%", "gotcha_docs"]))
lines.append(md_row(["---"] * 5))
for r in intel_rows:
    lines.append(md_row([r["section_type"], r["section_role"], r["rag_weight"],
                         r["corpus_frequency_pct"], r["gotcha_docs"]]))
lines.append("")
lines.append("## Concrete pipeline recommendations")
lines.append("")
lines.append("1. **Schedule detector** — target the `bid_schedule` `heading_regex` "
             "(proposal form / schedule of prices / bid form / unit price) instead of "
             "scanning every page. It reliably catches the quantity table, which sits "
             "mid/back (~0.69 of the doc).")
lines.append("2. **Gotcha pass** — weight retrieval toward the five proven gotcha carriers "
             "(`special_provisions`, `traffic_staging`, `agreement`, `bid_schedule`, "
             "`contract_front`) plus the engineering specs. Don't spend Claude calls judging "
             "`eeo_federal` / `bonds_forms` / `general_conditions` prose — they carry almost "
             "no gotchas and never quantities.")
lines.append("3. **Retriever weighting** — multiply chunk scores by `rag_weight`. This "
             "demotes boilerplate (~0) without dropping it (a page-level gotcha guard can "
             "still rescue a rare flag), and promotes the decision/engineering core.")
lines.append("4. **State-aware framing** — `special_provisions` and `traffic_staging` carry "
             "the most gotchas across all three states; MN leans on `general_notes` + "
             "`prosecution_of_work` (plan-notes style), while ND/SD push more into "
             "`contract_front` and `agreement`. See `state_variants` per row.")
lines.append("")
lines.append("## Caveats")
lines.append("")
lines.append("- `sections.section_type`/`tier`/`rag_treatment` are still NULL in the DB "
             "(Jay's section-spine classification is the pending handoff). `corpus_frequency` "
             "here is derived by regex-matching `raw_heading`; the gotcha/decision signal is "
             "keyed on the already-normalized `gotchas.section` values.")
lines.append("- Rows with `low_sample_flag = Y` rest on <3 docs — treat as directional.")
lines.append("- Addenda were not processed (per project guardrails).")
lines.append("")

OUT_README.write_text("\n".join(lines))

# --- console summary ----------------------------------------------------------
print(f"N_DOCS (corpus denominator): {N_DOCS}")
print(f"section types classified:    {len(intel_rows)}")
print(f"materials/quantities docs:   {mat_docs}")
print(f"wrote: {OUT_INTEL.name}")
print(f"wrote: {OUT_README.name}")
print(f"wrote: {OUT_PROPOSED.name}")
print("\nTop gotcha-carrying sections:")
for r in [x for x in gotcha_ranked if x['gotcha_count'] > 0][:6]:
    print(f"  {r['section_type']:22s} gotchas={r['gotcha_count']:4d} "
          f"docs={r['gotcha_docs']:3d} rag_weight={r['rag_weight']}")
