"""
Coverage test — a tons bucket the bid schedule measured in some OTHER unit must surface the item,
its value and its unit, with a reason. It must never come back as a bare null.

THE DEFECT THIS GUARDS (the client live test, plan 9786015 — CSAH 2 / Maryland Ave, Murray Co MN)
------------------------------------------------------------------------------------------
`hot_mix_tons` / `base_tons` / `shoulder_tons` are TONS by name and by destination column
(bid_projects.mix_tn / base_tn / shldr_tn). 9786015 measures ALL THREE in something else —
2,485 CY of Class 5 aggregate base, 14,142 SY of Type SP mixture, 38 SY of shouldering aggregate —
so all three came back null and the report was indistinguishable from a plan with no paving in it.
Eleventh instance of the standing rule: a failure and a legitimate empty answer must never share a
return value.

WHY THE ASSERTIONS BELOW ARE NOT "A PLAN WITH NO BASE RETURNS NULL"
-------------------------------------------------------------------
A test that passes on a plan with no base at all proves nothing — null is the right answer there.
The test that matters is a plan whose base EXISTS and is CY-measured, and it is asserted here
against a REAL extraction run over the real document, recorded red-and-green:

    03_evaluation/outputs/2026-08-10_tons_unit_capture_9786015_old.json   (before: three bare nulls)
    03_evaluation/outputs/2026-08-10_tons_unit_capture_9786015_new.json   (after:  three items named)

Both were produced by 03_evaluation/2026-08-10_tons_unit_capture_run.py at temperature=0 against
00_input/_md_cache/a3171c2187e8af85.json. The mapping is a prompt, so re-running the model is the
only way to re-derive them; the artifacts are committed so this test can assert on the evidence
without an API call. Regenerate with the runner if the descriptions change.

NOTHING HERE CONVERTS ANYTHING. Spec: docs/_spec/2026-08-10-tons-bucket-unit-capture.md.
"""
import json
from pathlib import Path

import pytest

import schema

OUTPUTS = Path(__file__).resolve().parents[1] / "03_evaluation" / "outputs"
RED = OUTPUTS / "2026-08-10_tons_unit_capture_9786015_old.json"
GREEN = OUTPUTS / "2026-08-10_tons_unit_capture_9786015_new.json"


def _load(path):
    assert path.exists(), (
        f"{path.name} is missing — it is COMMITTED EVIDENCE of a real extraction run, not a "
        "regenerable cache. Re-derive it with 03_evaluation/2026-08-10_tons_unit_capture_run.py."
    )
    runs = json.loads(path.read_text())
    assert len(runs) == 1, f"{path.name} should hold exactly one document"
    run = runs[0]
    # A run that ERRORED and a run that legitimately found nothing must not be read as the same
    # thing — the harness keeps them apart and so does this test.
    assert run["status"] == "OK", f"{path.name} recorded status={run['status']}: {run['error']}"
    return run


# ── The three states, on the real document ──────────────────────────────────────────────────────

def test_9786015_cy_base_used_to_be_a_bare_null_the_red_half():
    """BEFORE: the shipped field set could not say anything about the 2,485 CY base."""
    red = _load(RED)
    assert red["totals"]["base_tons"] is None
    assert red["capture"] is None, "the old arm has no field to record an off-unit item in"
    # And the derived status can only be `unknown` — which is the honest reading: we did not ask.
    assert red["statuses"]["base_tons"] == "unknown"
    # The same silent drop hit all three tons buckets on this one plan, not just base.
    assert set(red["statuses"].values()) == {"unknown"}


def test_9786015_cy_base_is_now_surfaced_with_its_value_its_unit_and_a_reason():
    """AFTER: the item, the number, the unit, and why it was not counted."""
    green = _load(GREEN)

    # base_tons stays null — correct, the schedule does not state tons. That null is no longer the
    # only thing we say about the base.
    assert green["totals"]["base_tons"] is None

    cap = green["capture"]
    assert cap["base_measured_unit"] == "OTHER"          # the reason, in the closed vocabulary
    line = cap["base_unconverted"]
    assert line, "the CY base item must be recorded, not dropped"
    assert "2485" in line.replace(",", ""), f"the stated quantity must survive verbatim: {line!r}"
    assert "CY" in line.upper(), f"the native unit must survive verbatim: {line!r}"
    assert "AGGREGATE BASE" in line.upper(), f"the item itself must be named: {line!r}"

    # The reason, derived and machine-readable: found, and not convertible with what we know.
    assert green["statuses"]["base_tons"] == "unconverted_only"

    # NOTHING WAS CONVERTED. 2,485 CY must not have become a tonnage anywhere in the record.
    assert green["totals"]["base_tons"] is None
    assert green["totals"]["shoulder_tons"] is None
    assert green["totals"]["hot_mix_tons"] is None


def test_9786015_hot_mix_and_shoulder_were_dropped_the_same_way_and_are_now_surfaced_too():
    """The plan the client tested drops all three tons buckets, not just base. All three are covered."""
    green = _load(GREEN)
    cap = green["capture"]
    for bucket in ("hot_mix", "shoulder"):
        assert cap[f"{bucket}_measured_unit"] == "OTHER"
        assert cap[f"{bucket}_unconverted"], f"{bucket}: the off-unit item(s) must be recorded"
        assert "SY" in cap[f"{bucket}_unconverted"].upper()
    assert green["statuses"]["hot_mix_tons"] == "unconverted_only"
    assert green["statuses"]["shoulder_tons"] == "unconverted_only"


def test_red_and_green_are_the_same_document_and_the_same_seven_totals():
    """The only thing that moved is the capture. If a bucket total moved, this change regressed the
    mapping — the exact risk of adding fields to a prompt."""
    red, green = _load(RED), _load(GREEN)
    assert red["hash"] == green["hash"] == "a3171c2187e8af85"
    assert red["totals"] == green["totals"], (
        "the seven quantity totals moved between arms — the six new fields perturbed the mapping")


# ── The status function: three states must be three values, exhaustively ────────────────────────

@pytest.mark.parametrize("bucket", sorted(schema.TONS_BUCKETS))
def test_found_but_unconvertible_absent_and_failed_are_three_distinct_values(bucket):
    """The rule this whole change is an instance of, asserted directly and per bucket."""
    unit_field, unconv_field = schema.TONS_BUCKETS[bucket]

    found_unconvertible = schema.bucket_unit_status(
        {unit_field: "OTHER", bucket: None, unconv_field: "AGGREGATE BASE CLASS 5 | 2485 | CY"},
        bucket)
    genuinely_absent = schema.bucket_unit_status(
        {unit_field: "NONE", bucket: None, unconv_field: None}, bucket)
    extraction_failed = schema.bucket_unit_status({}, bucket)

    assert found_unconvertible == "unconverted_only"
    assert genuinely_absent == "not_present"
    assert extraction_failed == "unknown"
    assert len({found_unconvertible, genuinely_absent, extraction_failed}) == 3


@pytest.mark.parametrize("bucket", sorted(schema.TONS_BUCKETS))
def test_a_null_unit_is_never_read_as_absence(bucket):
    """`null` is reserved for 'extraction produced no answer'. A model that returns nothing must not
    be reported as a model that asserted there is no such item."""
    unit_field, unconv_field = schema.TONS_BUCKETS[bucket]
    for empty in (None, "", "  ", "n/a", "NOT STATED"):
        assert schema.bucket_unit_status(
            {unit_field: empty, bucket: None, unconv_field: None}, bucket) == "unknown"


@pytest.mark.parametrize("bucket", sorted(schema.TONS_BUCKETS))
def test_every_declared_unit_maps_to_a_status_and_contradictions_are_surfaced(bucket):
    """Exhaustive over the closed vocabulary x (tons present?) x (unconverted present?). A declared
    unit that contradicts the values is `inconsistent` — never silently resolved toward either."""
    unit_field, unconv_field = schema.TONS_BUCKETS[bucket]
    expected = {
        # (unit,        has_tons, has_unconverted): status
        ("TON",         True,  False): "tons_only",
        ("TON",         False, False): "inconsistent",   # declared tons, no quantity behind it
        ("TON",         True,  True):  "inconsistent",   # declared tons, yet an off-unit line
        ("TON",         False, True):  "inconsistent",
        ("OTHER",       False, True):  "unconverted_only",
        ("OTHER",       False, False): "inconsistent",   # claims an item exists, names none
        ("OTHER",       True,  True):  "inconsistent",
        ("OTHER",       True,  False): "inconsistent",
        ("TON+OTHER",   True,  True):  "tons_and_unconverted",
        ("TON+OTHER",   True,  False): "inconsistent",
        ("TON+OTHER",   False, True):  "inconsistent",
        ("TON+OTHER",   False, False): "inconsistent",
        ("NONE",        False, False): "not_present",
        ("NONE",        True,  False): "inconsistent",   # "no such item" with a quantity
        ("NONE",        False, True):  "inconsistent",
        ("NONE",        True,  True):  "inconsistent",
    }
    for (unit, has_tons, has_unconv), want in expected.items():
        rec = {unit_field: unit,
               bucket: 1234.0 if has_tons else None,
               unconv_field: "ITEM | 1 | CY" if has_unconv else None}
        got = schema.bucket_unit_status(rec, bucket)
        assert got == want, f"{bucket} {unit} tons={has_tons} unconv={has_unconv}: {got} != {want}"
        assert got in schema.BUCKET_UNIT_STATUSES

    # Every token in the closed vocabulary is reachable and none falls through to a default.
    assert set(schema.BUCKET_UNIT_TOKENS) == {u for u, _, _ in expected}


def test_it_accepts_both_a_cell_record_and_a_flat_dict():
    """Callers hold either shape: report.py passes the {value, confidence, page} cells straight from
    the extractor; the eval harnesses hold flat dicts."""
    cells = {"base_measured_unit": {"value": "OTHER", "confidence": "high", "page": 27},
             "base_tons": {"value": None, "confidence": "", "page": None},
             "base_unconverted": {"value": "Class 5 Aggregate Base (CV) (P) | 2485 | CY",
                                  "confidence": "high", "page": 27}}
    assert schema.bucket_unit_status(cells, "base_tons") == "unconverted_only"


def test_a_bucket_that_is_not_a_tons_bucket_raises_rather_than_answering():
    """`milling_sy` has its own status function with its own vocabulary. Asking this one about it
    must fail loudly rather than return a plausible-looking status."""
    with pytest.raises(ValueError):
        schema.bucket_unit_status({}, "milling_sy")


def test_a_zero_tonnage_is_not_treated_as_a_quantity():
    """0 tons is not evidence that the bucket is tons-measured — the same rule report.py's quantity
    loop already applies when it skips a 0 value."""
    assert schema.bucket_unit_status(
        {"base_measured_unit": "OTHER", "base_tons": 0, "base_unconverted": "X | 1 | CY"},
        "base_tons") == "unconverted_only"
