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
      VENDOR/competitor name normalization (the client / Knife River spelling variants), not a
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
    # --- ADDED 2026-08-07. THE ORIGINAL STEARNS BUG WAS NEVER FIXED HERE. -------------------------
    # The 2026-07-30 material pre-read records "MILL BITUMINOUS SURFACE hits BITUMINOUS -> hma before
    # it can reach milling" as the root cause, and records it as FIXED. It was fixed in
    # 04_tools/11_build_material_map.py — the PRE-READ GENERATOR — and never in this file, which is
    # what actually runs. The unit guard stopped it polluting hot_mix_tons (SY into a TON bucket),
    # so it was counted NOWHERE rather than counted wrong, which is why nobody saw it.
    #
    # Magnitude, stated precisely because a looser figure caused a disagreement on 2026-08-07:
    #   1,218,210 SY / 17 plans  — rows whose description contains "MILL BITUMINOUS" (after
    #                              normalize_description; 168,834 of it hides behind \xa0)
    #   2,122,223 SY / 36 plans  — the wider "any MILL or COLD PLANE" set, which also includes
    #                              MILLING PAVEMENT and MILL TRANSITION
    # An earlier comment here said "1,346,886 SY across 18 plans", which was the wider set measured
    # mid-fix and matches neither definition. Quote one of the two above, with its definition.
    #
    # These must stay ABOVE the BITUMINOUS/hma block below. The list is first-match-wins and the
    # action verb has to beat the material noun. Covered by test_golden_items_map_as_intended.
    # Only keywords with an actual corpus hit are listed. "MILL SURFACE" and "COLD PLANE" were in
    # the first draft of this fix and the coverage test rejected them as dead — add them back when a
    # real pay item needs them, with the row that proves it.
    ("MILL BITUMINOUS", "milling"), ("MILL TRANSITION", "milling"), ("MILLING PAVEMENT", "milling"),
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


# --- 4. the client's rulings, 2026-08-07 (the "Alex layer") ------------------------------------------------
# Provenance: the client (Alex) returned the marked-up material pre-read on 2026-08-07 with nine rulings.
# These are the CLIENT'S decisions and they OUTRANK SPEC_MAP above. They are applied first.
#
# WHY a separate item-level layer instead of editing SPEC_MAP: the rulings split items that share a
# SPEC_MAP keyword. "REMOVE BITUMINOUS PAVEMENT" becomes milling while "REMOVE BITUMINOUS DRIVEWAY
# PAVEMENT" becomes nothing at all — one keyword cannot express that, so the override has to be
# per-item and ordered, with the narrower pattern first.
#
# WHY this layer never looks at the unit: see CATEGORY vs BUCKET below.
CROSSWALK_VERSION = 2          # 1 = pre-Alex (everything above). 2 = with the rulings below.
                               # Stamped onto every mapped row so the two are distinguishable in the
                               # DATA, not just in git history.

# ---------------------------------------------------------------------------------------------------
# CATEGORY vs BUCKET — the distinction this layer introduces, and the reason it exists.
#
# A bucket name like `base_tons` or `milling_sy` bakes a UNIT into a CATEGORY. That conflation is a
# real defect, and it produced a real near-miss: the client ruled that Full Depth Reclamation is BASE work.
# Read as a bucket move that ruling says "put 1.2M SQUARE YARDS into a TONS column", the unit guard
# then drops every row, and FDR silently returns to counting as zero — which is the exact bug the
# whole mapping exercise was convened to fix. the client answered a category question; the unit error was
# ours, not theirs.
#
# So the two are now recorded separately:
#   csi_category — WHAT KIND of work this is. Unit-independent. This is what the client rules on.
#   csi_bucket   — WHICH TOTAL the quantity is summed into. Still unit-guarded, still safe.
# For FDR they deliberately DISAGREE: category "base" (the client's ruling, honoured) with the quantity
# still counted in milling_sy (where it is measurable). Both are surfaced. Nothing is converted and
# nothing is lost. Unit conversion is a LATER layer with a documented, the client-verified factor table —
# it does not belong here. Decision by T, 2026-08-07.
# ---------------------------------------------------------------------------------------------------

EXCLUDED = "excluded"   # the client ruled this out ON PURPOSE. Distinct from "other" (not a tracked
                        # bucket) and from None (we never matched it) — three different facts that
                        # must not collapse into one, or a report cannot tell "the plan has none of
                        # this" from "we failed to read it".

# (pattern, csi_category, csi_bucket_override_or_None, note)
# Matched against the UPPERCASED description. FIRST MATCH WINS, so narrower patterns come first.
# csi_bucket_override of None means "leave the bucket to the normal (category, unit) bridge".
CSI_RULINGS_2026_08_07 = [
    # --- NOW EXCLUDED (were mapped) -- driveway rules MUST precede the mainline removal rules -----
    ("REMOVE CONCRETE DRIVEWAY PAVEMENT", EXCLUDED, EXCLUDED, "the client 08-07: do not count"),
    ("REMOVE BITUMINOUS DRIVEWAY PAVEMENT", EXCLUDED, EXCLUDED, "the client 08-07: do not count"),
    ("CEMENT STABILIZED SUBGRADE", EXCLUDED, EXCLUDED, "the client 08-07: do not count"),
    ("PORTLAND CEMENT", EXCLUDED, EXCLUDED, "the client 08-07: binder/additive, not aggregate base"),

    # --- MOVES ------------------------------------------------------------------------------------
    ("REMOVE BITUMINOUS PAVEMENT", "mill", None, "the client 08-07: grading -> milling"),
    ("REMOVAL OF BITUMINOUS SURFACING", "mill", None, "the client 08-07: grading -> milling"),
    ("GRAVEL SURFACING", "base", None, "the client 08-07: shoulder -> base"),
    ("TRAFFIC SERVICE AGGREGATE", "base", None, "the client 08-07: shoulder -> base"),
    # FDR: category moves to base, quantity DELIBERATELY stays in milling_sy. See the block above.
    # Do not "fix" this into a bucket move — that zeroes 1.2M SY. It is the point of this layer.
    ("FULL DEPTH RECLAMATION", "base", "milling_sy",
     "the client 08-07: base WORK; qty stays SY in milling_sy pending a verified conversion factor"),

    # --- PREVIOUSLY UNASSIGNED, resolved ----------------------------------------------------------
    ("SALVAGE AND REUSE EXISTING AGGREGATE", "grading", None, "the client 08-07: unassigned -> grading"),
    ("CLEAN ROCK", "grading", None, "the client 08-07: unassigned -> grading"),
    # The other two of the four assigned rows on the unassigned table. They were filed in
    # CSI_DO_NOT_COUNT_2026_08_07 until 2026-08-11, which asserted the client had ruled them OUT when the
    # returned .docx ticks a BUCKET for each — worse than a miss, because it launders our
    # transcription error as the client's decision. THE FINGERPRINT that proves it was ours: that
    # list held 13 entries = the 11 genuinely-unassigned rows PLUS these 2, i.e. all 15 unassigned
    # rows were swept into "do not count" and only 2 of the 4 assigned ones were then rescued.
    # Marks decoded from w14:checkbox XML and cross-checked against the visible glyph — two methods,
    # agreeing. docs/_session/2026-08-11-alex-conformance-encoding.md §2, rulings #2 and #3.
    ("FULL DEPTH BITUMINOUS STREET REPAIR", "mixed", None, "the client 08-07: unassigned -> Mixed_tons"),
    ("GRANULAR BEDDING", "grading", None, "the client 08-07: unassigned -> grading"),

    # --- REMOVALS: the FDR treatment applied to the same shape (T, 2026-08-07) --------------------
    # Mark's standing rule is that pavement/base removal "is considered grading work". That is a
    # CATEGORY statement, and it collides with a unit the same way FDR did: removal is measured in SY
    # (30 of 41 corpus rows) or TON (7 rows), while grading_yards is CY. Depth — which any SY->CY
    # conversion needs — is stated on ZERO of the 41 rows.
    #
    # So: record the category, and let the quantity stay where it is counted, which for most of these
    # is NOWHERE. That is deliberate and it is the honest answer. `bucket_gap_reason` below reports it
    # as `no_bucket_for_unit` rather than letting it look like a plan with no removals. Do NOT invent
    # a conversion here — the 1.75 Ton/CY factor the client supplied has never been checked against a plan
    # and does not distinguish bituminous from aggregate base.
    #
    # These sit AFTER the driveway exclusions and the two bituminous-removal rulings above, so the client's
    # explicit decisions keep winning over this general rule.
    ("REMOVAL OF AGGREGATE BASE", "grading", None, "T 08-07: removal = grading work (Mark's rule)"),
    ("REMOVE AGGREGATE BASE", "grading", None, "T 08-07: removal = grading work (Mark's rule)"),
    ("REMOVE CONCRETE PAVEMENT", "grading", None, "T 08-07: removal = grading work (Mark's rule)"),
    ("REMOVAL OF CONCRETE PAVEMENT", "grading", None, "T 08-07: removal = grading work (Mark's rule)"),
    ("REMOVE DRIVEWAY PAVEMENT", "grading", None, "T 08-07: removal = grading work (Mark's rule)"),
    ("PAVEMENT REMOVAL", "grading", None, "T 08-07: removal = grading work (Mark's rule)"),
    ("REMOVAL OF PAVEMENT", "grading", None, "T 08-07: removal = grading work (Mark's rule)"),
    ("REMOVE PAVEMENT", "grading", None, "T 08-07: removal = grading work (Mark's rule)"),
]

# Ruled "do not count" explicitly. These match nothing in SPEC_MAP today, so they move no number —
# but recording them converts "we never matched it" into "the client decided", which is the distinction the
# report needs in order to show an honest empty bucket.
CSI_DO_NOT_COUNT_2026_08_07 = [
    "CONCRETE DRIVEWAY PAVEMENT", "PENETRATING WATER REPELLENT TREATMENT", "REINFORCEMENT FABRIC",
    "CONTROLLED DENSITY FILL", "CONCRETE VALLEY GUTTER", "STRUCTURAL CONCRETE",
    "NON-REINF CONCRETE PVMT CL AE-DOWELED", "NON REINF CONCRETE PVMT CL AE-DOWELED",
    "CONCRETE PENETRATING SEALER", "CONCRETE MEDIAN PAVING", "RAPID STABILIZATION METHOD 4",
    # 2026-08-11: `FULL DEPTH BITUMINOUS STREET REPAIR` and `GRANULAR BEDDING` were REMOVED from
    # this list and moved into CSI_RULINGS_2026_08_07 above — Alex assigned each a bucket, so
    # recording them here inverted his decision. 11 entries, which is exactly the number of
    # genuinely-unassigned rows on the form.
]

# STILL UNANSWERED by the client as of 2026-08-07 — flagged, NOT assumed. Do not add rulings for these
# without an answer: (1) the riprap confirmation, (2) whether crushing/stockpile stay excluded.
CSI_OPEN_QUESTIONS_2026_08_07 = ["riprap classification", "crushing/stockpile exclusion"]

# spec_category (the SPEC_MAP vocabulary) -> csi_category (the client-facing vocabulary).
_SPEC_TO_CSI_CATEGORY = {
    "hma": "mixed", "base": "base", "surfacing": "shldr", "grading": "grading",
    "milling": "mill", "crushing": "crushing", "stockpile": "stockpile",
}


# Typographic characters DOT PDFs emit that break naive matching. Every one was found in this
# corpus, not guessed. Kept in sync with 04_tools/11_build_material_map.py::TYPOGRAPHIC and
# 04_tools/08_material_universe.py::normalize — all three must agree on what a description IS
# before they can argue about what it MEANS.
_TYPOGRAPHIC = {"\xa0": " ", "‐": "-", "‑": "-", "–": "-", "—": "-",
                "‘": "'", "’": "'", "“": '"', "”": '"'}


def normalize_description(text):
    """Fold typographic characters, collapse whitespace, uppercase.

    THIS IS A DEFECT FIX, NOT COSMETICS — and it is the second time this exact gap has cost six
    figures. `spec_category` and `_csi_ruling` previously did a bare `.upper()` while the rest of
    the system (the material lookup table, the material map) used a normalizing form. 115 real
    corpus rows contain a non-breaking space, and the mismatch silently bypassed FIVE of the client's
    2026-08-07 rulings:

        'Mill\\xa0Bituminous\\xa0Surfacing\\xa01.5" (P)'  168,834 SY -> read as HOT MIX, not milling
        'REMOVE BITUMINOUS  PAVEMENT'  (double space)      15,067 SY -> read as HOT MIX
        'REMOVE BITUMINOUS  DRIVEWAY\\xa0PAVEMENT'                   -> not excluded as the client ruled
        'Full\\xa0Depth\\xa0Reclamation (P)'                10,182 SY -> missed the FDR ruling
        '8"\\xa0Concrete Valley Gutter'                               -> not excluded as the client ruled

    Same failure class as the Stearns MILL BITUMINOUS bug (a removal/mill item landing in `hma`),
    reintroduced through a text gap instead of a keyword-ordering gap. Found 2026-08-07 by the
    mapping pressure-test; 11 rows change category once this is applied."""
    t = text or ""
    for bad, good in _TYPOGRAPHIC.items():
        t = t.replace(bad, good)
    return re.sub(r"\s+", " ", t).upper().strip()


def _csi_ruling(description):
    """Return (csi_category, bucket_override, note) if the client ruled on this item, else (None, None, None)."""
    upper = normalize_description(description)
    for pattern, category, bucket_override, note in CSI_RULINGS_2026_08_07:
        if pattern in upper:
            return category, bucket_override, note
    for pattern in CSI_DO_NOT_COUNT_2026_08_07:
        if pattern in upper:
            return EXCLUDED, EXCLUDED, "the client 08-07: do not count"
    return None, None, None


def spec_category(description):
    """Map a raw bid-item description to its broad work category (first keyword match wins).

    the client's 2026-08-07 rulings are applied FIRST and outrank the keyword list — they are the client's
    decisions about their own numbers, not another heuristic."""
    csi_cat, _bucket, _note = _csi_ruling(description)
    if csi_cat is not None:
        # translate the client vocabulary back into the SPEC_MAP vocabulary this function returns
        return {"mixed": "hma", "base": "base", "shldr": "surfacing", "grading": "grading",
                "mill": "milling", EXCLUDED: "other"}[csi_cat]
    upper = normalize_description(description)
    for keyword, category in SPEC_MAP:
        if keyword in upper:
            return category
    return "other"


def csi_category(description):
    """The the client-facing work category — WHAT KIND of work, independent of how it is measured.

    Returns one of: mixed / base / shldr / grading / mill / crushing / stockpile / excluded / other.
    `excluded` means the client ruled it out deliberately; `other` means it is simply not a tracked bucket.
    Never returns None, so a caller cannot confuse "no category" with "no answer"."""
    csi_cat, _bucket, _note = _csi_ruling(description)
    if csi_cat is not None:
        return csi_cat
    return _SPEC_TO_CSI_CATEGORY.get(spec_category(description), "other")


def _normalize_unit(unit):
    """Collapse a raw unit cell to a canonical token (TON / SY / CY / LF / EA / LSUM / ...).
    DOTs write the same unit many ways ('TONS', 'TON', 'T'; 'SQ YD', 'S.Y.', 'SY') — we only need the
    coarse family for the bucket bridge, so we key on the leading letters."""
    u = re.sub(r"[^A-Z]", "", (unit or "").upper())
    if u.startswith("TON") or u == "T":
        return "TON"
    # SPELLED-OUT forms added 2026-08-07. `Square Yard` collapsed to "SQUAREYARD", which matched
    # none of the SQYD/SY/SYD forms, so 179,016 SY of correctly-categorised milling was dropped by
    # the bucket bridge. Third instance in one day of the same defect class — a value that is
    # obviously right to a human and unrecognised by a matcher, silently producing a zero. The
    # SQUARE/CUBIC prefixes are checked before the abbreviations because they are unambiguous.
    if u.startswith("SQUAREYARD") or u in ("SY", "SQYD", "SYD") or u.startswith("SQYD"):
        return "SY"
    if u.startswith("CUBICYARD") or u in ("CY", "CUYD", "CYD") or u.startswith("CUYD"):
        return "CY"
    return u  # LF / EA / LSUM / MILE / GAL / ACRE ... — never a tracked bucket


def csi_bucket(description, unit):
    """Map a (description, unit) to one of the 7 csi_buckets, or None if the line isn't a tracked
    quantity bucket. Deterministic: category from the keyword map, then the (category, unit) bridge.

    A the client bucket_override wins over the bridge. That is not a special case bolted on — it is how a
    ruling like FDR's ("base work, but the quantity is square yards") is expressed without either
    inventing a conversion or dropping the number. Without this branch the bridge would look up
    ("base", "SY"), find nothing, and silently zero 1.2M SY."""
    _cat, bucket_override, _note = _csi_ruling(description)
    if bucket_override is not None:
        return None if bucket_override is EXCLUDED else bucket_override
    return BUCKET_RULES.get((spec_category(description), _normalize_unit(unit)))


def map_line(description, unit):
    """Convenience: return (csi_bucket_or_None, spec_category) for one bid-item line — the single call
    the parser makes per row. Contract unchanged (2-tuple) — 05_parse_bid_schedule.py and
    10_remap_buckets.py both depend on this shape."""
    return csi_bucket(description, unit), spec_category(description)


#: Columns the crosswalk stamps onto every row it maps. Owned here rather than by either writer,
#: because both `05_parse_bid_schedule.py` (fresh parse) and `10_remap_buckets.py` (re-map of stored
#: rows) write them and they must not drift apart.
STAMP_COLUMNS = [("csi_category", "TEXT"), ("crosswalk_version", "INTEGER")]


def ensure_stamp_columns(conn):
    """Add the stamp columns to `materials` if absent. Expand-only and idempotent — safe to call on
    every run, never drops or rewrites anything.

    WHY this exists: `csi_bucket` is computed at write time and frozen into the row, so when the
    crosswalk changes, old rows keep a stale bucket with nothing recording which mapping produced it.
    Stamping the version makes pre-the client-ruling and post-the client-ruling rows distinguishable IN THE DATA,
    not just in git history — which is what you need to answer "why is this number different from
    last week's" without a bisect."""
    have = {r[1] for r in conn.execute("PRAGMA table_info(materials)")}
    for name, decl in STAMP_COLUMNS:
        if name not in have:
            conn.execute(f"ALTER TABLE materials ADD COLUMN {name} {decl}")
    conn.commit()


def map_line_v2(description, unit):
    """The full mapped record for one bid-item line, for callers that need to show their work.

    Returns a dict rather than a tuple because the interesting cases need more than two facts:
    F3's audit export has to show the raw quantity, the bucket it landed in, and WHY — including
    "the client excluded this on purpose", which no bucket value can express.

    Keys:
      csi_bucket        which total the quantity is summed into (None = no tracked bucket)
      csi_category      what kind of work it is, unit-independent (never None; may be `excluded`)
      spec_category     the legacy SPEC_MAP vocabulary, for back-compat with existing rows
      unit_normalized   TON / SY / CY / LF / ... as the bridge sees it
      unit_matches_bucket  False when the quantity is held in a bucket whose name implies another
                        unit (FDR). Surfacing this is the whole reason the FDR ruling is safe.
      crosswalk_version stamped so pre-Alex (1) and post-Alex (2) rows are distinguishable in the data
      ruling_source     'CSI_2026-08-07' when a client ruling decided this, else 'SPEC_MAP'
      ruling_note       the human-readable reason, when there is one
    """
    csi_cat, bucket_override, note = _csi_ruling(description)
    bucket = csi_bucket(description, unit)
    cat = csi_category(description)
    u = _normalize_unit(unit)
    expected = BUCKET_UNIT.get(bucket)
    return {
        "csi_bucket": bucket,
        "csi_category": cat,
        "spec_category": spec_category(description),
        "unit_normalized": u,
        "unit_matches_bucket": (expected is None) or (u == expected),
        "bucket_gap_reason": bucket_gap_reason(description, unit),
        "crosswalk_version": CROSSWALK_VERSION,
        "ruling_source": "CSI_2026-08-07" if csi_cat is not None else "SPEC_MAP",
        "ruling_note": note or "",
        "excluded_by_csi": cat == EXCLUDED,
    }


#: The unit each bucket is denominated in. The whole category/bucket split exists because these
#: names conflate the two; keeping the mapping explicit is what lets us DETECT the conflation.
BUCKET_UNIT = {"hot_mix_tons": "TON", "base_tons": "TON", "shoulder_tons": "TON",
               "grading_quantity": "CY", "milling_sy": "SY", "crushing_tons": "TON",
               "stockpile_tons": "TON"}

# The reasons a line carries a real quantity but lands in no bucket. These are NOT interchangeable,
# and rendering them identically is the defect F2 exists to fix — it is also exactly how the FDR
# typo hid for months, because "keyword never matched" and "deliberately not counted" both showed up
# as an empty cell.
GAP_NOT_APPLICABLE = None                 # it did land in a bucket
GAP_EXCLUDED_BY_CSI = "excluded_by_csi"   # the client ruled it out on purpose
GAP_UNTRACKED_CATEGORY = "untracked_category"   # real work, but not one of the tracked buckets
GAP_NO_BUCKET_FOR_UNIT = "no_bucket_for_unit"   # we KNOW the category; the unit has nowhere to go
GAP_NEVER_MATCHED = "never_matched"       # we could not categorise it at all — a READER failure


def bucket_gap_reason(description, unit):
    """Why this line reached no bucket. Returns None when it did reach one.

    Distinguishing `never_matched` from the other three is the point: the first is OUR failure and
    should be visible as one, while the rest are correct outcomes. A report that renders all four as
    a blank cell cannot tell an estimator "this plan has no milling" from "we could not read the
    milling", and those are opposite facts."""
    if csi_bucket(description, unit) is not None:
        return GAP_NOT_APPLICABLE
    cat = csi_category(description)
    if cat == EXCLUDED:
        return GAP_EXCLUDED_BY_CSI
    if cat == "other":
        # `other` from a genuine SPEC_MAP hit (traffic control, erosion...) is untracked work;
        # `other` because nothing matched at all is a reader failure. Same value, different meaning.
        return (GAP_UNTRACKED_CATEGORY
                if spec_category(description) != "other" or _matched_any_keyword(description)
                else GAP_NEVER_MATCHED)
    return GAP_NO_BUCKET_FOR_UNIT


def _matched_any_keyword(description):
    """True if any SPEC_MAP keyword fired. Separates a deliberate `other` from a total miss."""
    upper = normalize_description(description)
    return any(kw in upper for kw, _c in SPEC_MAP)
