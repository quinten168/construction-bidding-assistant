"""Coverage tests for the 2026-08-10 CY/SY -> tons conversion flag (PR #102, integration step 1).

The guarantee under test is NOT "the arithmetic is right" — PR #102's own validation already
proved that (docs/_session/2026-08-10-pr102-validation.md §1: 1,000 deterministic repeats, all
three of the client's hand-computed figures reproduced to the cent). The guarantee here is that **the
engine is dormant by default**, and that being dormant is a state a reader can see rather than a
null they cannot interpret.

Why this file exists as a coverage test and not a unit test: the thing that can go wrong is not a
wrong number, it is a wrong DEFAULT — a flag flipped on by an env var somebody exported months ago,
a config file that shipped, a `True` typed while debugging. So these tests assert the default
itself, and they assert it through the same import path production uses.

RED-BEFORE-GREEN, recorded: `test_flag_defaults_off` and `test_flag_off_derives_no_base_value` were
both run against `CONVERSION_ENABLED = True` before the flag existed in its computed form; both
FAILED (the second with base_tons == 3851.75, the exact value it must not produce). They pass now.
`test_flag_on_still_reproduces_csi_figures` is the inverse: it fails if the flag turned into a
no-op, i.e. if the engine was disabled by breaking it.

Plan 9786015 (Murray Co MN, CSAH 2 / Maryland Ave, md-cache hash a3171c2187e8af85) is the fixture.
Its six qualifying bid-schedule lines are transcribed from page 27 and are the same six the live
extractor returned identically on 6 of 6 runs (validation §2).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[3]
_PIPELINE = _REPO / "pipelines" / "plan_reader" / "01_pipeline"
if str(_PIPELINE) not in sys.path:
    sys.path.insert(0, str(_PIPELINE))

import material_tons_merge  # noqa: E402
import schema  # noqa: E402


def _cell(value):
    return {"value": value, "confidence": "high", "page": 27, "reason": ""}


def murray_9786015_record() -> dict:
    """Plan 9786015's extraction record, restricted to the fields this layer reads.

    Every quantity and depth below is printed on the plan's own bid schedule (page 27, items 40,
    41, 44-47). `base_tons` / `shoulder_tons` / `hot_mix_tons` are None because this plan states NO
    tonnage at all for those buckets — which is exactly what makes it the right fixture: with the
    flag off there is nothing for a derived value to hide behind.
    """
    return {
        "base_tons": _cell(None),
        "shoulder_tons": _cell(None),
        "hot_mix_tons": _cell(None),
        "base_cy_items": _cell([
            {"quantity": 2485.0, "unit": "CY", "depth_in": None, "page": 27,
             "note": "41 Class 5 Aggregate Base (CV)(P)"},
        ]),
        "shoulder_cy_items": _cell([
            {"quantity": 38.0, "unit": "SY", "depth_in": 8.0, "page": 27,
             "note": '40 8" Class 5 Alley & Shouldering Aggregate Surfacing'},
        ]),
        "mix_sy_depth_items": _cell([
            {"quantity": 5368.0, "unit": "SY", "depth_in": 2.0, "page": 27,
             "note": "44 Type SP 9.5 Wearing (CSAH 2)"},
            {"quantity": 5368.0, "unit": "SY", "depth_in": 3.0, "page": 27,
             "note": "45 Type SP 12.5 Non-Wearing (CSAH 2)"},
            {"quantity": 1703.0, "unit": "SY", "depth_in": 1.5, "page": 27,
             "note": "46 Type SP 9.5 Wearing (Maryland Ave)"},
            {"quantity": 1703.0, "unit": "SY", "depth_in": 2.5, "page": 27,
             "note": "47 Type SP 12.5 Wearing (Maryland Ave)"},
        ]),
    }


@pytest.fixture
def flag_on(monkeypatch):
    """Force the engine on for the one test that must prove it still works. Deliberately explicit
    and deliberately not reachable from an env var here — setting the env var would not flip the
    flag anyway, because G1 (nobody has signed the factors) and G2 (no recorded acceptance run)
    both still evaluate False. That is the point of the design and is asserted separately below."""
    monkeypatch.setattr(material_tons_merge, "CONVERSION_ENABLED", True)


# ── The default ───────────────────────────────────────────────────────────────

def test_flag_defaults_off():
    """The headline guarantee. If this ever fails, a derived tonnage is reaching a human."""
    assert material_tons_merge.CONVERSION_ENABLED is False


def test_the_default_is_computed_not_configured():
    """Off must be the consequence of three unmet gates, not of a literal somebody could edit.
    Checks each gate independently so a future change that satisfies one still leaves the flag off
    for a stated, findable reason rather than by luck."""
    assert material_tons_merge._g1_factors_blessed() is False, \
        "a factor row acquired a blessed_by/blessed_on — G1 now passes; this is a client sign-off " \
        "event and the flag's status must be re-decided deliberately, not drift on"
    assert material_tons_merge._g2_acceptance_recorded() is False
    assert not material_tons_merge.ACCEPTANCE_RECORD_PATH.exists(), \
        "the acceptance record file appeared; G2 is no longer structurally False"
    assert material_tons_merge._compute_conversion_enabled() is False


def test_unset_env_var_is_off_and_a_junk_value_is_off_loudly(monkeypatch, capsys):
    """Absence is off. A wrong value is ALSO off — but not silently, because a misconfigured
    operator who thinks the flag is on and sees pre-#102 numbers has no other way to find out."""
    monkeypatch.delenv(material_tons_merge.OPERATOR_OPT_IN_ENV, raising=False)
    assert material_tons_merge._g3_operator_opt_in() == (False, None)

    monkeypatch.setenv(material_tons_merge.OPERATOR_OPT_IN_ENV, "true")
    opted_in, complaint = material_tons_merge._g3_operator_opt_in()
    assert opted_in is False
    assert complaint and material_tons_merge.OPERATOR_OPT_IN_ENV in complaint

    # And even the correct token alone is not enough — G1/G2 still gate it.
    monkeypatch.setenv(material_tons_merge.OPERATOR_OPT_IN_ENV,
                       material_tons_merge.OPERATOR_OPT_IN_TOKEN)
    assert material_tons_merge._g3_operator_opt_in() == (True, None)
    assert material_tons_merge._compute_conversion_enabled() is False


# ── Flag OFF: no derived value, on the plan that would produce the biggest one ─

def test_flag_off_derives_no_base_value():
    """Plan 9786015's base is 2,485 CY and NOTHING in tons. With conversion on that is 3,851.75 t.
    With the flag off it must be None — not 0, not 3851.75, not a partial."""
    merged = material_tons_merge.merge_material_tons(murray_9786015_record())
    assert merged["base_tons"] is None
    assert merged["base_tons"] != pytest.approx(3851.75)


def test_flag_off_derives_nothing_for_any_of_the_three_buckets():
    merged = material_tons_merge.merge_material_tons(murray_9786015_record())
    assert merged == {"base_tons": None, "shoulder_tons": None, "hot_mix_tons": None}


def test_flag_off_leaves_a_stated_tonnage_exactly_as_stated():
    """The other half of 'exactly the pre-#102 behaviour': a bucket the plan DOES state in tons is
    passed through untouched and, critically, is not blended with a convertible CY item."""
    record = murray_9786015_record()
    record["base_tons"] = _cell(500.0)
    merged = material_tons_merge.merge_material_tons(record)
    assert merged["base_tons"] == 500.0, "a CY item leaked into a stated tonnage with the flag off"


# ── Flag OFF is a STATE, not a silence ────────────────────────────────────────

def test_withheld_is_distinguishable_from_nothing_to_convert():
    """The standing rule, applied to the flag itself. Three records that all produce base_tons is
    None must NOT all look the same to a reader."""
    withheld = material_tons_merge.conversion_report(murray_9786015_record())

    empty = murray_9786015_record()
    empty["base_cy_items"] = _cell([])            # the model asserted: nothing qualifies
    unanswered = murray_9786015_record()
    unanswered["base_cy_items"] = _cell(None)     # the model answered nothing at all

    nothing_usable = murray_9786015_record()      # a real item, but not convertible
    nothing_usable["base_cy_items"] = _cell(
        [{"quantity": 999.0, "unit": "SY", "depth_in": None, "page": 27, "note": "no depth"}])

    statuses = {
        withheld["base_tons"]["status"],
        material_tons_merge.conversion_report(empty)["base_tons"]["status"],
        material_tons_merge.conversion_report(unanswered)["base_tons"]["status"],
        material_tons_merge.conversion_report(nothing_usable)["base_tons"]["status"],
    }
    assert len(statuses) == 4, f"four distinct situations collapsed into {statuses}"
    assert withheld["base_tons"]["status"] == "disabled_withheld"
    assert withheld["base_tons"]["convertible_item_count"] == 1
    assert material_tons_merge.conversion_report(empty)["base_tons"]["status"] \
        == "disabled_not_applicable"
    assert material_tons_merge.conversion_report(unanswered)["base_tons"]["status"] \
        == "disabled_unknown_input"
    assert material_tons_merge.conversion_report(nothing_usable)["base_tons"]["status"] \
        == "disabled_nothing_convertible"


def test_every_emitted_status_is_in_the_closed_vocabulary():
    report = material_tons_merge.conversion_report(murray_9786015_record())
    assert set(report) == {"base_tons", "shoulder_tons", "hot_mix_tons"}
    for bucket in report.values():
        assert bucket["status"] in material_tons_merge.CONVERSION_STATUSES


def test_the_status_never_leaks_the_withheld_tonnage():
    """A consumer must not be able to render the number the flag exists to withhold by reading the
    status object. Counts yes, tons no."""
    report = material_tons_merge.conversion_report(murray_9786015_record())
    flat = repr(report)
    for forbidden in ("3851.75", "1901.3", "13.08"):
        assert forbidden not in flat


# ── Flag ON: disabled without being broken ────────────────────────────────────

def test_flag_on_still_reproduces_csi_figures(flag_on):
    """Proves the flag disables the engine rather than damaging it. These three numbers are the client's
    own hand computation for plan 9786015."""
    merged = material_tons_merge.merge_material_tons(murray_9786015_record())
    assert round(merged["base_tons"], 2) == 3851.75
    assert round(merged["shoulder_tons"], 2) == 13.09
    assert round(merged["hot_mix_tons"], 2) == 1901.34


def test_flag_on_reports_all_converted(flag_on):
    report = material_tons_merge.conversion_report(murray_9786015_record())
    assert report["base_tons"]["status"] == "all_converted"
    assert report["hot_mix_tons"]["status"] == "all_converted"
    assert report["hot_mix_tons"]["captured_item_count"] == 4


# ── The golden must not have moved ────────────────────────────────────────────

GOLDEN = _REPO / "pipelines" / "plan_reader" / "00_input" / "golden_dataset.csv"


def test_golden_dataset_untouched_by_this_change():
    """This change must not have edited the ground truth it would be scored against. Two
    independent methods, both named, per the standing absence rule: (1) the file's own bytes hash
    to the value git has for the committed blob, and (2) git reports no working-tree modification
    for that path."""
    import subprocess
    blob = subprocess.run(["git", "hash-object", str(GOLDEN)], cwd=_REPO,
                          capture_output=True, text=True, check=True).stdout.strip()
    committed = subprocess.run(["git", "rev-parse", "HEAD:pipelines/plan_reader/00_input/golden_dataset.csv"],
                               cwd=_REPO, capture_output=True, text=True, check=True).stdout.strip()
    assert blob == committed, "golden_dataset.csv differs from the committed blob"

    status = subprocess.run(["git", "status", "--porcelain", "--",
                             "pipelines/plan_reader/00_input/golden_dataset.csv"],
                            cwd=_REPO, capture_output=True, text=True, check=True).stdout
    assert status.strip() == "", f"git reports the golden as modified: {status!r}"


# ── The eleven client rulings must have survived the merge ───────────────────────

RULING_TOKENS = [
    "SUPERPAVE",
    "ASPHALT CONCRETE",
    "REMOVE AGGREGATE BASE",
    "PORTLAND CEMENT",
    "CEMENT STABILIZED SUBGRADE",
    "GRAVEL SURFACING",
    "TRAFFIC SERVICE AGGREGATE",
    "SALVAGE AND REUSE EXISTING AGGREGATE",
    "CLEAN ROCK",
    "FULL DEPTH RECLAMATION",
]


def test_csi_ruling_tokens_survived_the_merge():
    """PR #102 inserts three new field descriptions into schema.py's SCALAR_FIELDS. It must not
    have disturbed the eleven client rulings encoded in the seven pre-existing quantity descriptions.
    Checked against the live SCALAR_FIELDS objects, not the file text, so a token that survived in
    a comment but fell out of a prompt would still fail."""
    prompt_text = " ".join(f["desc"].upper()
                           for f in schema.SCALAR_FIELDS if f.get("group") == "quantities")
    missing = [t for t in RULING_TOKENS if t not in prompt_text]
    assert not missing, f"the client ruling tokens lost from the extraction prompt: {missing}"


def test_both_driveway_exclusions_survived_the_merge():
    """The two driveway exclusions are the eleventh ruling and are phrased, not tokenised, so they
    get their own check rather than being folded into the token list above."""
    prompt_text = " ".join(f["desc"].upper()
                           for f in schema.SCALAR_FIELDS if f.get("group") == "quantities")
    assert prompt_text.count("DRIVEWAY") >= 2, \
        "fewer than two DRIVEWAY exclusions remain in the quantity descriptions"
