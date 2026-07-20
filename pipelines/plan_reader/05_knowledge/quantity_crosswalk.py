"""
quantity_crosswalk.py  —  the SINGLE canonical crosswalk for bid-schedule line items.

Two jobs, both deterministic (no Claude calls):
  1. map a raw bid-item DESCRIPTION  -> a spec_category  (mobilization / hma / base / ...)
  2. map a (spec_category, UNIT)      -> a csi_bucket     (one of the 7 quantity buckets)

WHY this file exists (consolidation, 2026-06-16): the mapping had drifted across three places.
Rather than pick one, we consolidate here in priority order so the parser has ONE source of truth
going forward (the v2 plan treats the crosswalk as a maintainable artifact — Mochen's field-registry
concern). Provenance is noted per block so we know where each rule came from as the dict grows:

  PRIORITY 1 — the validated feasibility keyword map
      (07_archive/2026-06-15_bid_schedule_feasibility/). Highest trust: it produced the verified
      Dunn = 39-item result. It is reproduced VERBATIM as SPEC_MAP below; where anything conflicts,
      this map wins.
  PRIORITY 2 — the Fall-2025 `NAME_MAPPING` (130+ rules). INSPECTED and EXCLUDED: it turned out to be
      VENDOR/competitor name normalization (CSI / Knife River spelling variants), not a
      material-description crosswalk — nothing to fold in here. (The context pack referenced it only
      as a structural *pattern*, not as material content.)
  PRIORITY 3 — the 2026-06-12 context-pack crosswalk. It contained no dict, only an illustrative Dunn
      table (SUPERPAVE FAA 45 -> hot_mix_tons, AGGREGATE BASE COURSE CL 13 -> base_tons,
      MILLING PAVEMENT SURFACE -> milling_sy). Those examples are already covered by SPEC_MAP; they
      live on as the GROWTH/test anchors at the bottom of this file.

GROWTH: descriptions the parser can't categorize land in `plan_metrics.unmapped_items`. Those are the
candidate additions — add a (keyword, category) row to SPEC_MAP (most-specific first) and re-run. This
is the home for that growth, alongside the other knowledge taxonomies in 05_knowledge/.
"""
import re

# --- 1. description -> spec_category (PRIORITY 1: verbatim from the validated feasibility map) -------
# Ordered list, FIRST MATCH WINS, so the most-specific keywords come first. spec_category is the broad
# work-category used for n_spec_categories + the scope flags; it is also the first half of the
# (spec_category, unit) -> csi_bucket bridge below.
SPEC_MAP = [  # (keyword, category)
    ("MOBILIZATION", "mobilization"),
    ("CONTRACT BOND", "other"),
    ("ASPHALT CEMENT", "other"), ("PORTLAND CEMENT", "other"),  # binders, not mix tonnage
    ("CEMENT STABILIZED", "base"), ("STABILIZED SUBGRADE", "grading"),
    ("FLAGGING", "traffic_control"), ("PILOT CAR", "traffic_control"),
    ("LANE CLOSURE", "traffic_control"), ("BARRICADE", "traffic_control"),
    ("DELINEATOR", "traffic_control"), ("TUBULAR MARKER", "traffic_control"),
    ("VERTICAL PANEL", "traffic_control"), ("TRAFFIC CONTROL", "traffic_control"),
    ("RUMBLE STRIP", "traffic_control"),
    ("PVMT MK", "pavement_marking"), ("PAVEMENT MARKING", "pavement_marking"),
    ("PAINTED", "pavement_marking"), ("EPOXY", "pavement_marking"),
    ("SILT FENCE", "erosion"), ("EROSION", "erosion"), ("SEEDING", "erosion"),
    ("TOPSOIL", "erosion"), ("SWPPP", "erosion"), ("FIBER", "erosion"),
    ("MULCH", "erosion"), ("BLANKET", "erosion"), ("WATTLE", "erosion"),
    ("RIPRAP", "structures"), ("RIP RAP", "structures"), ("CULVERT", "structures"),
    ("BOX ", "structures"), ("BRIDGE", "structures"), ("PIPE", "structures"),
    ("RETAINING WALL", "structures"), ("STRUCTURE", "structures"),
    # --- ADDED 2026-06-17 (Brookings SD regression fix) — milling DISAMBIGUATION must come BEFORE the
    #     ASPHALT CONCRETE hma keyword below, because SD writes its milling line as
    #     "Cold Milling Asphalt Concrete" (a removal, SqYd) — that is milling, not mix tonnage.
    ("COLD MILLING", "milling"), ("MILLING ASPHALT", "milling"),
    ("SUPERPAVE", "hma"), ("TYPE SP", "hma"), ("WEARING COURSE", "hma"),
    ("HOT MIX", "hma"), ("HMA", "hma"), ("2360", "hma"), ("ASPHALT CEMENT", "hma"),
    ("BITUMINOUS", "hma"),
    # --- ADDED 2026-06-17 (Brookings SD regression fix) — SD DOT names its hot-mix pay item
    #     "Asphalt Concrete Pavement" / "Asphalt Concrete" (the MN/ND "BITUMINOUS"/"SUPERPAVE" analogue).
    #     17,432.3 t of Brookings hot mix was silently dropped because this term was unmapped (→ "other").
    #     Placed AFTER the milling disambiguation above so "Cold Milling Asphalt Concrete" stays milling.
    ("ASPHALT CONCRETE", "hma"),
    ("AGGREGATE BASE", "base"), ("BASE COURSE", "base"), ("STABILIZED BASE", "base"),
    ("2211", "base"), ("2112", "base"), ("CL 13", "base"), ("BASE PREPARATION", "base"),
    ("AGGREGATE SURFACING", "surfacing"), ("SHOULDER", "surfacing"),
    ("GRAVEL SURFACING", "surfacing"), ("2118", "surfacing"),
    ("COMMON EXCAVATION", "grading"), ("UNCLASSIFIED EXCAVATION", "grading"),
    ("GRADING", "grading"), ("EARTHWORK", "grading"), ("FORESLOPE", "grading"),
    ("RESHAPING", "grading"), ("SUBGRADE", "grading"), ("BORROW", "grading"),
    # --- ADDED 2026-06-22 (LLM-fallback recall fix) — the biggest earthwork items were landing in
    #     "other" (so grading_quantity stayed empty on ~MN plans). MnDOT writes the pay item
    #     "EXCAVATION - COMMON" (word order reversed from "COMMON EXCAVATION" above, sometimes with a
    #     non-breaking space) and "COMMON EMBANKMENT (CV)" — neither substring-matched. These two bare
    #     keywords are unambiguously mainline earthwork (CY). Placed AFTER the structures block above,
    #     so "BOX CULVERT EXCAVATION" / "Bridge End Embankment" still read as structures (first match wins).
    ("EXCAVATION", "grading"), ("EMBANKMENT", "grading"),
    ("MILLING", "milling"), ("RECLAIM", "milling"), ("RELAYING MILLED", "milling"),
    ("REMOVE AND RELAY", "milling"), ("SAWING", "milling"),
    # --- ADDED 2026-06-16 (Phase 1) — the schema has crushing_tons / stockpile_tons buckets but the
    #     feasibility map had no keyword for them, so a crushed/stockpiled line could never reach those
    #     buckets. Placed AFTER base/surfacing so "CRUSHED AGGREGATE BASE" still reads as base.
    ("CRUSHING", "crushing"), ("CRUSHED AGGREGATE", "crushing"), ("CRUSH ", "crushing"),
    ("STOCKPILE", "stockpile"), ("STOCK PILE", "stockpile"),
]

# --- 2. (spec_category, unit) -> csi_bucket  (the 7 quantity buckets) --------------------------------
# WHY a (category, unit) pair and not category alone: a "base" line measured in TON is base_tons, but
# the same work measured in SY (e.g. "STABILIZED BASE COURSE - 6\" DEPTH | SY") is an area, NOT a
# tonnage bucket — so unit guards against summing incompatible units into a bucket. This extends the
# feasibility cross-check ROLLUP (which covered only hma/base/milling/surfacing) to all 7 buckets.
# A category/unit pair not listed here -> csi_bucket = None (a real line, but not one of the 7 buckets:
# mobilization, traffic_control, erosion, structures, pavement_marking, "other" all fall through).
BUCKET_RULES = {
    ("hma", "TON"):        "hot_mix_tons",
    ("base", "TON"):       "base_tons",
    ("surfacing", "TON"):  "shoulder_tons",     # shoulder gravel / aggregate surfacing tonnage
    ("milling", "SY"):     "milling_sy",
    ("grading", "CY"):     "grading_quantity",
    ("crushing", "TON"):   "crushing_tons",
    ("stockpile", "TON"):  "stockpile_tons",
}

# --- 3. readable-bucket -> legacy historical column (the _num suffix) --------------------------------
# Used ONLY by the later back-test (Phase 1.5) to line our buckets up against the historical master.
# Live code uses the readable names above; this isolates the legacy names so we never rename a bucket.
BUCKET_TO_HISTORICAL = {
    "hot_mix_tons": "MIX_TN_num", "base_tons": "BASE_TN_num",
    "grading_quantity": "GRADE_CY_num", "shoulder_tons": "SHLDR_TN_num",
    "milling_sy": "MILL_SY_num", "crushing_tons": "CRUSH_TN_num",
    "stockpile_tons": "STOCK_TN_num",
}

# The 7 canonical buckets, in schema order — handy for callers building the plan_metrics rollup.
CSI_BUCKETS = ["hot_mix_tons", "base_tons", "grading_quantity", "shoulder_tons",
               "milling_sy", "crushing_tons", "stockpile_tons"]


def spec_category(description):
    """Map a raw bid-item description to its broad work category (first keyword match wins)."""
    upper = (description or "").upper()
    for keyword, category in SPEC_MAP:
        if keyword in upper:
            return category
    return "other"


def _normalize_unit(unit):
    """Collapse a raw unit cell to a canonical token (TON / SY / CY / LF / EA / LSUM / ...).
    DOTs write the same unit many ways ('TONS', 'TON', 'T'; 'SQ YD', 'S.Y.', 'SY') — we only need the
    coarse family for the bucket bridge, so we key on the leading letters."""
    u = re.sub(r"[^A-Z]", "", (unit or "").upper())
    if u.startswith("TON") or u == "T":
        return "TON"
    if u in ("SY", "SQYD", "SYD") or u.startswith("SQYD"):
        return "SY"
    if u in ("CY", "CUYD", "CYD") or u.startswith("CUYD"):
        return "CY"
    return u  # LF / EA / LSUM / MILE / GAL / ACRE ... — never a tracked bucket


def csi_bucket(description, unit):
    """Map a (description, unit) to one of the 7 csi_buckets, or None if the line isn't a tracked
    quantity bucket. Deterministic: category from the keyword map, then the (category, unit) bridge."""
    return BUCKET_RULES.get((spec_category(description), _normalize_unit(unit)))


def map_line(description, unit):
    """Convenience: return (csi_bucket_or_None, spec_category) for one bid-item line — the single call
    the parser makes per row."""
    cat = spec_category(description)
    bucket = BUCKET_RULES.get((cat, _normalize_unit(unit)))
    return bucket, cat
