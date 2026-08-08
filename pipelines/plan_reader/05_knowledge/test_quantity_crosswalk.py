"""Coverage tests for the crosswalk — the class of test that would have caught RECLAIM on day one.

WHY THIS FILE EXISTS (2026-08-07). In a single day the flat `SPEC_MAP` keyword list produced two
silent, six-figure data errors, and 36 passing unit tests caught neither:

  1. `RECLAIM` never matched `FULL DEPTH RECLAMATION` (the substrings diverge at position 6), so
     1,235,282 SY reported as ZERO for months.
  2. `AGGREGATE BASE` matched `REMOVE AGGREGATE BASE`, so 202,031 TON of demolition was reported to
     CSI as purchased aggregate base.

Both are invisible to per-function unit tests, because the function did exactly what it was written
to do. They are only visible by asking questions ABOUT THE TABLE as a whole:

  - does every entry actually match something?           (catches bug 1)
  - does any entry match something it must not?          (catches bug 2)
  - can two different outcomes be told apart downstream? (catches the blank-cell problem)

That is what this file tests. It is deliberately NOT a test of `spec_category`'s implementation.
"""
import os
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import quantity_crosswalk as xwalk  # noqa: E402

MODULE_ROOT = Path(__file__).resolve().parents[1]
DB_PATH = MODULE_ROOT / "csi_v2.db"


# --------------------------------------------------------------------------------------------------
# 1. DEAD KEYWORDS — an entry that matches nothing is either a typo or a rule for work we have never
#    seen, and the two must not be indistinguishable. RECLAIM sat here for months looking like the
#    second while being the first.
# --------------------------------------------------------------------------------------------------

# Keywords that legitimately match zero corpus rows, each with the REASON it is allowed to.
# Adding an entry here is a deliberate act: you are asserting you checked and it is fine.
# Do NOT add a keyword here to make the test pass. If it should match and does not, fix the keyword.
KNOWN_DEAD_KEYWORDS = {
    # MnDOT spec numbers. The bid-schedule parser stores line numbers rather than the `Mat No.`
    # column, so 0 of 6,385 corpus rows retain a spec number at all. These keywords cannot fire
    # until that parser change lands. Documented in the material pre-read's "Known weaknesses".
    "2360": "spec numbers are discarded by the parser (0/6385 rows retain one)",
    "2211": "spec numbers are discarded by the parser",
    "2112": "spec numbers are discarded by the parser",
    "2118": "spec numbers are discarded by the parser",
    # Genuinely absent vocabulary in this corpus, not typos — verified by searching the corpus for
    # the underlying concept, not just the keyword.
    "SWPPP": "corpus writes 'EROSION CONTROL' / 'STORM WATER'; no SWPPP line item present",
    "RETAINING WALL": "no retaining-wall pay item in the 66 plans that have materials",
}

# Keywords that are dead AND should not be. Kept as an explicit xfail list rather than being
# silently tolerated, so they stay visible until someone fixes or removes them.
DEAD_AND_SHOULD_NOT_BE = {
    "RECLAIM": "does not match FULL DEPTH RECLAMATION — the bug that started this file. The CSI "
               "ruling layer now matches the item explicitly, so no quantity is lost, but this "
               "keyword is still wrong and would mislead the next reader.",
    "CRUSHING": "the whole `crushing` family is dead, so crushing_tons can never be populated",
    "CRUSHED AGGREGATE": "same family",
    "CRUSH ": "same family",
    "STOCK PILE": "'STOCKPILE' (no space) matches; this spaced variant never fires",
}


def _corpus_descriptions():
    """Every real (non-noise) pay-item description in the corpus, uppercased."""
    if not DB_PATH.exists():
        pytest.skip("csi_v2.db not present (gitignored, 167 MB) — corpus coverage cannot be checked")
    import importlib.util
    universe = MODULE_ROOT / "04_tools" / "08_material_universe.py"
    spec = importlib.util.spec_from_file_location("material_universe", universe)
    mu = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mu)
    conn = sqlite3.connect(os.path.realpath(DB_PATH))
    rows = conn.execute("select raw_description, unit from materials").fetchall()
    conn.close()
    return [(d or "").upper() for d, u in rows if not mu.is_noise(d, u)[0]]


def test_every_spec_map_keyword_matches_at_least_one_corpus_row():
    """A keyword that fires on nothing is a keyword nobody has verified.

    This is THE test that would have caught RECLAIM the day it was written.
    """
    descriptions = _corpus_descriptions()
    dead = [kw for kw, _cat in xwalk.SPEC_MAP
            if not any(kw in d for d in descriptions)]
    unexplained = [kw for kw in dead
                   if kw not in KNOWN_DEAD_KEYWORDS and kw not in DEAD_AND_SHOULD_NOT_BE]
    assert not unexplained, (
        "SPEC_MAP keywords match zero corpus rows and are not documented as knowingly dead:\n  "
        + "\n  ".join(repr(k) for k in unexplained)
        + "\n\nEither the keyword is wrong (fix it) or it is legitimately absent from this corpus "
          "(add it to KNOWN_DEAD_KEYWORDS with the reason you verified)."
    )


@pytest.mark.xfail(strict=True, reason="known-broken keywords, tracked in issue #83")
def test_known_broken_keywords_are_still_broken():
    """Pins the keywords we know are wrong but have not removed.

    strict=True, so this FAILS if someone fixes one without updating the list — which is the point:
    the list must shrink deliberately, not drift.
    """
    descriptions = _corpus_descriptions()
    still_dead = [kw for kw in DEAD_AND_SHOULD_NOT_BE
                  if not any(kw in d for d in descriptions)]
    assert not still_dead, f"still dead: {still_dead}"


# --------------------------------------------------------------------------------------------------
# 2. WRONG MATCHES — the converse failure. A keyword that fires on something it must not.
#    `AGGREGATE BASE` matching `REMOVE AGGREGATE BASE` is this bug, and it cost 202,031 TON.
# --------------------------------------------------------------------------------------------------

# (description, unit, expected_csi_category, expected_csi_bucket)
# Every row here is a REAL pay item from the corpus, not a synthetic example.
GOLDEN_ITEMS = [
    # --- the two bugs of 2026-08-07, pinned so they cannot regress ---------------------------------
    ("FULL DEPTH RECLAMATION", "SY", "base", "milling_sy"),
    ("FULL DEPTH RECLAMATION (P)", "SY", "base", "milling_sy"),
    ("REMOVE AGGREGATE BASE", "TON", "grading", None),
    ("REMOVE AGGREGATE BASE & SURFACING", "TON", "grading", None),
    # --- ordinary placed materials must be unaffected by the ruling layer --------------------------
    ("SUPERPAVE FAA 45", "TON", "mixed", "hot_mix_tons"),
    ("TYPE SP 12.5 WEARING COURSE MIXTURE (3,C)", "TON", "mixed", "hot_mix_tons"),
    ("AGGREGATE BASE COURSE CL 5", "TON", "base", "base_tons"),
    ("COMMON EXCAVATION", "CY", "grading", "grading_quantity"),
    ("MILL BITUMINOUS SURFACE (1.5\")", "SY", "mill", "milling_sy"),
    # --- CSI's 2026-08-07 rulings ------------------------------------------------------------------
    ("GRAVEL SURFACING", "TON", "base", "base_tons"),
    ("TRAFFIC SERVICE AGGREGATE", "TON", "base", "base_tons"),
    ("REMOVE BITUMINOUS PAVEMENT", "SY", "mill", "milling_sy"),
    ("PORTLAND CEMENT", "TON", "excluded", None),
    ("CEMENT STABILIZED SUBGRADE - 12 INCH", "SY", "excluded", None),
    ("REMOVE CONCRETE DRIVEWAY PAVEMENT", "SY", "excluded", None),
    ("REMOVE BITUMINOUS DRIVEWAY PAVEMENT", "SY", "excluded", None),
    ("SALVAGE AND REUSE EXISTING AGGREGATE", "CY", "grading", "grading_quantity"),
]


@pytest.mark.parametrize("desc,unit,want_cat,want_bucket", GOLDEN_ITEMS)
def test_golden_items_map_as_intended(desc, unit, want_cat, want_bucket):
    assert xwalk.csi_category(desc) == want_cat, f"{desc!r} category"
    assert xwalk.csi_bucket(desc, unit) == want_bucket, f"{desc!r} bucket"


@pytest.mark.parametrize("desc", [
    "REMOVE AGGREGATE BASE",
    "REMOVE AGGREGATE BASE & SURFACING",
    "REMOVAL OF AGGREGATE BASE",
])
def test_removals_never_count_as_placed_material(desc):
    """A removal must never land in a PLACED-material bucket, whatever its unit.

    This is the general form of the 202,031 TON bug: the check is not "does REMOVE AGGREGATE BASE
    map correctly" but "can any removal reach a placed bucket at all".
    """
    placed = {"hot_mix_tons", "base_tons", "shoulder_tons"}
    for unit in ("TON", "SY", "CY"):
        assert xwalk.csi_bucket(desc, unit) not in placed, f"{desc!r} @ {unit} reached a placed bucket"


# --------------------------------------------------------------------------------------------------
# 3. STATES THAT MUST NOT RENDER ALIKE — "any enum where two states render identically is a bug
#    waiting" (T, 2026-08-07). All four gap reasons reach a report as an empty quantity cell; the
#    report has to be able to tell them apart, or `never_matched` hides inside `excluded`.
# --------------------------------------------------------------------------------------------------

GAP_CASES = [
    ("SUPERPAVE FAA 45", "TON", None),                          # reached a bucket
    ("PORTLAND CEMENT", "TON", xwalk.GAP_EXCLUDED_BY_CSI),      # CSI ruled it out
    ("TRAFFIC CONTROL", "LS", xwalk.GAP_UNTRACKED_CATEGORY),    # real work, untracked
    ("MILLING PAVEMENT SURFACE", "TON", xwalk.GAP_NO_BUCKET_FOR_UNIT),   # known cat, homeless unit
    ("ZORBLAT FLANGE WIDGET", "EA", xwalk.GAP_NEVER_MATCHED),   # READER FAILURE
]


@pytest.mark.parametrize("desc,unit,want", GAP_CASES)
def test_bucket_gap_reason(desc, unit, want):
    assert xwalk.bucket_gap_reason(desc, unit) == want


def test_all_gap_states_are_distinct():
    """The four reasons must be four distinct values. If any two collapse, the report cannot
    distinguish 'this plan has no milling' from 'we could not read the milling' — opposite facts."""
    observed = {xwalk.bucket_gap_reason(d, u) for d, u, _ in GAP_CASES}
    assert len(observed) == len(GAP_CASES), f"gap states collapsed: {observed}"


def test_never_matched_is_reachable_and_means_reader_failure():
    """`never_matched` is the state that would have surfaced RECLAIM. It must be reachable.

    An unreachable failure state is worse than no failure state, because it reads as an all-clear.
    """
    assert xwalk.bucket_gap_reason("ZORBLAT FLANGE WIDGET", "EA") == xwalk.GAP_NEVER_MATCHED
    # and it must NOT fire for something we genuinely categorised
    assert xwalk.bucket_gap_reason("TRAFFIC CONTROL", "LS") != xwalk.GAP_NEVER_MATCHED


# --------------------------------------------------------------------------------------------------
# 4. CONTRACT — two callers depend on map_line's 2-tuple shape.
# --------------------------------------------------------------------------------------------------

def test_map_line_returns_a_two_tuple():
    """`04_tools/05_parse_bid_schedule.py` and `10_remap_buckets.py` both unpack this as
    `bucket, cat = ...`. Changing the shape breaks them silently at import-free runtime."""
    result = xwalk.map_line("SUPERPAVE FAA 45", "TON")
    assert isinstance(result, tuple) and len(result) == 2
    assert result == ("hot_mix_tons", "hma")


def test_map_line_v2_agrees_with_map_line():
    """The rich API must not drift from the tuple API — they are the same decision, twice."""
    for desc, unit, _cat, _bucket in GOLDEN_ITEMS:
        assert xwalk.map_line_v2(desc, unit)["csi_bucket"] == xwalk.map_line(desc, unit)[0]


# --------------------------------------------------------------------------------------------------
# 5. TYPOGRAPHY — the gap that silently bypassed five CSI rulings.
#    115 real corpus rows contain a non-breaking space. `spec_category`/`_csi_ruling` used a bare
#    `.upper()` while the lookup table used a normalizing form, so a description with \xa0 or a
#    double space missed every ruling. Found 2026-08-07; these are the REAL corpus strings.
# --------------------------------------------------------------------------------------------------

TYPOGRAPHIC_CASES = [
    ('Mill\xa0Bituminous\xa0Surfacing\xa01.5" (P)', "SY", "mill", "milling_sy"),   # 168,834 SY
    ("REMOVE BITUMINOUS  PAVEMENT", "SY", "mill", "milling_sy"),                   # double space
    ("REMOVE BITUMINOUS  DRIVEWAY\xa0PAVEMENT", "SY", "excluded", None),
    ("Full\xa0Depth\xa0Reclamation (P)", "SY", "base", "milling_sy"),
    ('8"\xa0Concrete Valley Gutter', "SY", "excluded", None),
    ("AGGREGATE\xa0BASE\xa0COURSE\xa0CL\xa05", "TON", "base", "base_tons"),        # the 2026-06 case
]


@pytest.mark.parametrize("desc,unit,want_cat,want_bucket", TYPOGRAPHIC_CASES)
def test_typographic_variants_still_hit_their_ruling(desc, unit, want_cat, want_bucket):
    assert xwalk.csi_category(desc) == want_cat, repr(desc)
    assert xwalk.csi_bucket(desc, unit) == want_bucket, repr(desc)


def test_normalization_is_idempotent_and_matches_the_material_universe_form():
    """All three artifacts must agree on what a description IS before arguing what it MEANS.

    `08_material_universe.normalize` is what the 2,434-row lookup table was built with; this
    crosswalk must fold the same characters or the two can never be compared."""
    import importlib.util
    universe = MODULE_ROOT / "04_tools" / "08_material_universe.py"
    spec = importlib.util.spec_from_file_location("material_universe", universe)
    mu = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mu)
    for raw in [d for d, _u, _c, _b in TYPOGRAPHIC_CASES]:
        ours = xwalk.normalize_description(raw)
        assert ours == xwalk.normalize_description(ours), "not idempotent"
        assert ours == mu.normalize(raw).upper(), (
            f"crosswalk and material_universe disagree on {raw!r}: "
            f"{ours!r} vs {mu.normalize(raw).upper()!r}")


@pytest.mark.parametrize("raw,want", [
    # every spelling below appears in the real corpus
    ("SY", "SY"), ("S Y", "SY"), ("SQ YD", "SY"), ("SQYD", "SY"),
    ("Square Yard", "SY"), ("Square\xa0Yard", "SY"),      # 179,016 SY was lost to this one
    ("CY", "CY"), ("CU YD", "CY"), ("Cubic Yard", "CY"),
    ("TON", "TON"), ("Ton", "TON"), ("Tons", "TON"), ("T", "TON"),
    # things that must NOT be coerced into a bucket unit
    ("LF", "LF"), ("EA", "EA"), ("GAL", "GAL"), ("MILE", "MILE"), ("STA", "STA"),
])
def test_unit_normalization(raw, want):
    """A unit spelling a human reads instantly must not silently produce a zero.

    Three separate defects on 2026-08-07 had this shape (keyword typo, \\xa0 in a description,
    spelled-out unit). The bucket bridge drops anything it cannot name, and dropping is invisible."""
    assert xwalk._normalize_unit(raw) == want


def test_csi_category_never_returns_none():
    """A caller must not have to distinguish 'no category' from 'no answer'."""
    for desc in ["SUPERPAVE FAA 45", "ZORBLAT FLANGE WIDGET", "", None]:
        assert xwalk.csi_category(desc) is not None
