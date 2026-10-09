"""
test_material_vocabulary_coverage.py — COVERAGE tests for the live material mapping's VOCABULARY.

Spec: docs/_spec/2026-08-10-live-mapping-rulings.md · report: docs/_session/2026-08-10-ruling9-and-cl13.md

WHY THIS FILE IS A COVERAGE TEST AND NOT A UNIT TEST
-----------------------------------------------------
The live material mapping is seven prose field descriptions in `schema.py`, read by a model. A unit
test cannot assert what the model does with them. What a test CAN assert — and what this project
learned the hard way when 36 passing unit tests missed two keywords that matched the wrong thing —
is that every pay-item name those descriptions tell the model to look for **is a string that
actually appears on a real bid schedule in the corpus**. A description that names an item nobody
writes is dead vocabulary, and dead vocabulary is invisible: it neither fails nor fires.

So every phrase asserted here is matched against `00_input/_md_cache/*.json` — the real converted
page markdown of real corpus plans. No synthetic fixtures. A phrase that matches zero corpus lines
fails.

The two defects this file was written for (2026-08-10):
  • `AGGREGATE SURFACE COURSE CL 13` (ND, Job 24133, 170 TON) was named by NO field description, so
    7 runs in 10 dropped it out of every bucket — a silent capture failure.
  • the client ruling #9 (FDR's quantity is reported in `milling_sy`) did not fire on Stearns 9813645,
    where the FDR line is printed as `FULL DEPTH RECLAMATION ... 70167` and summarised elsewhere in
    the same document under a DIFFERENT name, `Bituminous Pavement Reclamation 70,167 SY`.

The corpus cache is gitignored, so these tests SKIP (never silently pass) when it is absent — a
fresh clone must not get a false green.

    .venv/bin/python -m pytest pipelines/plan_reader/01_pipeline/test_material_vocabulary_coverage.py -q
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import corpus_match  # noqa: E402
import schema  # noqa: E402

MD_CACHE = Path(__file__).resolve().parents[1] / "00_input" / "_md_cache"
needs_md = pytest.mark.skipif(
    not MD_CACHE.is_dir() or not any(MD_CACHE.glob("*.json")),
    reason="00_input/_md_cache is absent (gitignored; see pipelines/plan_reader/README.md)")


def _desc(name: str) -> str:
    for f in schema.SCALAR_FIELDS:
        if f["name"] == name:
            return f["desc"]
    raise AssertionError(f"{name!r} is not in schema.SCALAR_FIELDS — the schema moved under this test")


@pytest.fixture(scope="module")
def corpus_lines():
    """Every non-blank line of every cached corpus page, as (file, page, line).

    Loading failure is NOT the same as an empty corpus: a cache file that will not parse raises
    here rather than silently shrinking the corpus these assertions are made against.
    """
    out = []
    files = [p for p in sorted(MD_CACHE.glob("*.json")) if not p.name.endswith(".hybrid.json")]
    assert files, "no non-hybrid md_cache files — the corpus fixture itself is broken"
    for p in files:
        pages = json.loads(p.read_text())          # a parse error must surface, not be swallowed
        for pg in pages:
            text = pg.get("md") or pg.get("text") or ""
            for line in text.splitlines():
                line = line.strip()
                if line:
                    out.append((p.name, pg.get("page"), line))
    assert len(out) > 10_000, f"corpus is implausibly small ({len(out)} lines) — check the cache"
    return out


def _matches(corpus_lines, phrase: str):
    """Corpus lines containing `phrase`, ignoring case and any markdown noise BETWEEN the words.

    2026-08-11 — THIS FUNCTION USED TO UNDER-REPORT, AND A COVERAGE TEST THAT UNDER-REPORTS IS
    WORSE THAN NONE. It joined the words with a tolerant separator of up to 12 non-alphanumeric
    characters and matched against the RAW line. Stearns 9813645 p77 prints 15 characters of
    converter markup between CONCRETE and DRIVEWAY, so both of the client's driveway-removal rulings
    matched ZERO lines here and in the conformance inventory that inherited this matcher — while
    both are priced bid items (44 SY and 326 SY). Verified before the fix: 0 hits old, 1 hit new,
    for each of the two phrases.

    The single implementation now lives in `corpus_match.py`, which STRIPS the markup before
    matching rather than widening the tolerance (widening only moves the cliff). It is shared with
    03_evaluation/2026-08-11_alex_conformance_behavior.py so there is one matcher, not three.
    """
    pat = corpus_match.phrase_pattern(phrase)
    return [(f, pg, ln) for f, pg, ln in corpus_lines if pat.search(corpus_match.denoise(ln))]


# ── 1. The CL 13 gap: the added vocabulary must be IN the description AND in the corpus ─────────
# RED BEFORE GREEN: on 2026-08-10 both halves of this test failed — no description named
# "AGGREGATE SURFACE COURSE", so `test_..._is_named_by_the_shoulder_description` failed on the
# schema side while the corpus side already held the row. That is the exact shape of a silent
# capture failure: real document, no vocabulary.

CL13_ROW = "AGGREGATE SURFACE COURSE CL 13"


@needs_md
def test_aggregate_surface_course_cl13_is_a_real_corpus_row(corpus_lines):
    """The phrase is a REAL printed bid line — 170 TON on Job 24133 (Morton Co ND), not a fixture."""
    hits = _matches(corpus_lines, CL13_ROW)
    assert hits, (f"{CL13_ROW!r} matches no corpus line — either the cache changed or the phrase "
                  f"is wrong. Vocabulary that matches nothing is worse than none.")
    # The specific row the defect was measured on: quantity 170, unit TON, in the same table cell.
    with_qty = [h for h in hits if re.search(r"TON", h[2], re.I) and "170" in h[2]]
    assert with_qty, (f"found {len(hits)} corpus line(s) for {CL13_ROW!r} but none carrying the "
                      f"measured 170 TON quantity: {hits[:3]}")


@needs_md
def test_aggregate_surface_course_is_named_by_the_shoulder_description(corpus_lines):
    """The bucket description must NAME the item, or the model has no way to place it.

    ASSUMPTION, labelled in the description itself: the client has NOT ruled on aggregate surfacing (the
    open questions are riprap and crushing/stockpile). Bucketing to shoulder_tons follows the
    existing `AGGREGATE SURFACING CLASS 1/2/5/SPECIAL` clause, which is itself labelled "pending a
    the client ruling". This test asserts the vocabulary exists and is attributed — not that the client agreed.
    """
    d = _desc("shoulder_tons")
    assert "AGGREGATE SURFACE COURSE" in d.upper(), (
        "shoulder_tons does not name ND's 'AGGREGATE SURFACE COURSE CL __' — the 2026-08-10 CL 13 "
        "capture failure is back")
    assert "ASSUMPTION" in d.upper(), (
        "the aggregate-surfacing bucketing is an assumption, not the client ruling, and the description "
        "must say so out loud")


@needs_md
def test_nd_base_and_surface_course_are_distinguished_in_the_prose(corpus_lines):
    """ND writes BOTH `Aggregate Base Course Cl__` and `Aggregate Surface Course Cl__` under §302,
    distinguished ONLY by the words Base/Surface (spec-book sweep,
    05_knowledge/2026-08-10-spec_item_lookup.csv rows 36-37). Both strings are in the corpus, so the
    prose has to tell them apart or one bucket eats the other."""
    assert _matches(corpus_lines, "AGGREGATE BASE COURSE CL"), \
        "no corpus line for 'AGGREGATE BASE COURSE CL' — check the cache"
    assert _matches(corpus_lines, "AGGREGATE SURFACE COURSE CL"), \
        "no corpus line for 'AGGREGATE SURFACE COURSE CL' — check the cache"
    base_d, shldr_d = _desc("base_tons").upper(), _desc("shoulder_tons").upper()
    assert "SURFACE COURSE" in base_d, \
        "base_tons must say that 'AGGREGATE SURFACE COURSE' is NOT base, or ND surfacing lands here"
    assert "AGGREGATE SURFACE COURSE" in shldr_d


# ── 2. Ruling #9: every name the corpus uses for reclamation must be in the FDR prose ───────────
# The Stearns document prints the SAME 70,167 SY under two different names on two different pages.
# Naming only one of them is how ruling #9 failed to fire at 0/10.
#
# 2026-08-11 — THE FIELD THESE ASSERT AGAINST MOVED, on Alex's own mark (`Move to __base____`).
# FDR's QUANTITY now belongs to base; it is measured in SY and base_tons is TON, so it is reported
# verbatim in `base_unconverted` and is explicitly NOT counted in milling_sy. Both halves are
# asserted below, because "the phrase appears in the description" was too weak a test to notice the
# difference: milling_sy still CONTAINS every reclamation name, in a `Do NOT count` clause. A
# vocabulary test has to know which side of the sentence a phrase is on.

RECLAMATION_NAMES = [
    "FULL DEPTH RECLAMATION",             # Stearns bid schedule p.77; Dunn p.13 (408,216 SY)
    "BITUMINOUS PAVEMENT RECLAMATION",    # Stearns "Approximate Major Quantities" summary, p.79
]


@needs_md
@pytest.mark.parametrize("phrase", RECLAMATION_NAMES)
def test_reclamation_name_is_a_real_corpus_row(corpus_lines, phrase):
    assert _matches(corpus_lines, phrase), (
        f"{phrase!r} matches no corpus line — a clause naming it would be dead vocabulary")


@needs_md
@pytest.mark.parametrize("phrase", RECLAMATION_NAMES)
def test_reclamation_name_is_named_by_the_base_unconverted_description(corpus_lines, phrase):
    """the client put FDR's quantity in BASE. base_tons is tons and FDR is square yards, so the field that
    has to name it is the one that carries an off-unit base item verbatim."""
    assert phrase in _desc("base_unconverted").upper(), (
        f"base_unconverted does not name {phrase!r}. Alex ruled FDR's quantity is base, and the "
        f"corpus writes that item under more than one name.")


@needs_md
def test_milling_sy_now_pushes_reclamation_away_rather_than_counting_it(corpus_lines):
    """The reversal, asserted as a direction and not merely as a mention.

    Before 2026-08-11 milling_sy called FDR 'kind (b)' and added it. It must now (a) still name the
    item — an item nobody names is an item nobody can place — and (b) name it in an exclusion that
    says where the quantity went, or the 408,216 SY on Dunn silently vanishes.
    """
    d = _desc("milling_sy").upper()
    assert "FULL DEPTH RECLAMATION" in d, \
        "milling_sy no longer mentions FDR at all — a model with no clause will guess"
    assert "DO NOT COUNT FULL DEPTH RECLAMATION" in d, \
        "milling_sy must EXCLUDE reclamation explicitly, not merely fail to list it"
    assert "BASE_UNCONVERTED" in d, \
        "the exclusion must say where FDR's quantity goes; a bare 'do not count' is a silent drop"
    assert "KIND (B)" not in d, "the removed kind-(b) reclamation addend is back in milling_sy"


@needs_md
def test_the_two_measured_fdr_quantities_are_in_the_corpus(corpus_lines):
    """The two numbers the ruling-#9 firing rate is measured against, asserted against the source
    text so a future cache change cannot quietly move the target: Stearns 70,167 SY and Dunn
    408,216 SY."""
    for qty in ("70167", "408,216"):
        hits = [h for h in corpus_lines
                if qty in h[2] and re.search(r"RECLAMATION", h[2], re.I)]
        assert hits, f"no corpus reclamation line carrying {qty} — the measurement target moved"


# ── 3. The 2026-08-11 conformance vocabulary — every phrase Alex's marks added ───────────────────
# Each of these is a phrase a description now tells the model to look for (or to exclude). The rule
# this file enforces applies to all of them: vocabulary that matches nothing in the corpus is dead,
# and dead vocabulary neither fails nor fires.

# (phrase, the field whose description must name it)
CONFORMANCE_VOCABULARY = [
    ("SALVAGED BASE COURSE", "base_tons"),                  # BA5, Alex: Agree -> base_tons
    ("TACK COAT", "hot_mix_tons"),                          # P1 binder/coatings, flag only
    ("PRIME COAT", "hot_mix_tons"),
    ("ASPHALT CEMENT", "hot_mix_tons"),
    ("CLEAN ROCK", "grading_quantity"),                     # already named; now reachable via CY guard
    ("GRANULAR BEDDING", "grading_quantity"),               # 6-box pick -> grading
    ("TOPSOIL", "grading_quantity"),                        # GR2/GR7/GR15/GR17/GR20, ~539,000 CY
    ("COMMON TOPSOIL BORROW", "grading_quantity"),
    ("SUBGRADE PREPARATION", "grading_unconverted"),        # SY grading item, off-unit capture
]


@needs_md
@pytest.mark.parametrize("phrase,field", CONFORMANCE_VOCABULARY)
def test_conformance_phrase_is_named_by_its_field(corpus_lines, phrase, field):
    assert phrase in _desc(field).upper(), f"{field} does not name {phrase!r}"


@needs_md
@pytest.mark.parametrize("phrase,field", CONFORMANCE_VOCABULARY)
def test_conformance_phrase_is_a_real_corpus_row(corpus_lines, phrase, field):
    assert _matches(corpus_lines, phrase), (
        f"{phrase!r} (added to {field} on 2026-08-11) matches no corpus line — dead vocabulary")


@needs_md
def test_full_depth_bituminous_street_repair_is_RULED_BUT_ABSENT_and_that_is_recorded(corpus_lines):
    """The one 2026-08-11 addition that IS dead vocabulary, asserted as such rather than hidden.

    Alex ticked `Mixed_tons` for FULL DEPTH BITUMINOUS STREET REPAIR (a six-box pick), so it is
    encoded in hot_mix_tons — but the phrase matches ZERO lines in all 18 cached plans, under the
    exact spelling and under every alias the conformance inventory tried. That is a legitimate
    result, not a gap: it is a client decision about an item this corpus does not exercise. The
    honest thing is to say so out loud, so that a future coverage sweep does not either delete a
    real ruling as dead weight OR quietly treat "0 hits" as proof the ruling works.

    If this test ever FAILS, that is good news: a plan carrying the item entered the corpus, and the
    ruling can finally be measured instead of asserted.
    """
    phrase = "FULL DEPTH BITUMINOUS STREET REPAIR"
    assert phrase in _desc("hot_mix_tons").upper(), "Alex's Mixed_tons pick is not encoded"
    assert not _matches(corpus_lines, phrase), (
        f"{phrase!r} now appears in the corpus — MEASURE the ruling and delete this test's "
        f"untested-no-plan caveat from docs/_session/2026-08-11-conformance-fixes.md")


# ── 4. The matcher itself: the two rulings a fixed 12-char tolerance reported as absent ──────────

@needs_md
@pytest.mark.parametrize("phrase", ["REMOVE CONCRETE DRIVEWAY PAVEMENT",
                                    "REMOVE BITUMINOUS DRIVEWAY PAVEMENT"])
def test_driveway_removal_rulings_are_real_priced_corpus_rows(corpus_lines, phrase):
    """RED BEFORE GREEN, and the red was measured: with the previous raw-line 12-char matcher both
    of these returned 0 hits; with corpus_match.denoise both return 1. They are priced bid items —
    Stearns 9813645 p77 `REMOVE CONCRETE DRIVEWAY PAVEMENT | S Y | 44` and Crow Wing p220
    `REMOVE BITUMINOUS DRIVEWAY PAVEMENT | S Y | 326` — and the client ruled both DO NOT COUNT, so a
    matcher that cannot see them cannot check that the exclusions have anything to exclude."""
    hits = _matches(corpus_lines, phrase)
    assert hits, (f"{phrase!r} matches no corpus line — the 12-character-tolerance regression is "
                  f"back; see corpus_match.py")
    assert phrase in _desc("milling_sy").upper(), \
        f"milling_sy no longer excludes {phrase!r} — the client ruled it does not count"
