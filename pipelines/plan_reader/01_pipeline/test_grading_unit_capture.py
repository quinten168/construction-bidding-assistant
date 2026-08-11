"""
Coverage test — a GRADING item the bid schedule measured in some other unit than cubic yards must
surface the item, its value and its unit, with a reason. It must never vanish.

NOT DATE-PREFIXED, deliberately: pytest collects `test_*.py` / `*_test.py`, so a `2026-08-11_`
prefix would make this file silently uncollected — a test that never runs is worse than no test.
Same exemption the four sibling `test_*.py` files in this directory already take.

THE DEFECT THIS GUARDS (Dunn Job 23388, measured 2026-08-11)
------------------------------------------------------------
CSI (Alex) assigned `CLEAN ROCK` to grading. `grading_quantity` named it — and then, two sentences
later, forbade tons-measured items, because no verified TON->CY factor exists. Dunn prices clean
rock at `| CLEAN ROCK | TON | 758 |`. Measured at N=13 across two arms the ruling fired **0 times**,
and the model said exactly why in its own stated reason:

    "CLEAN ROCK (Item 045) is listed under grading definition but is measured in TON not CY so not
     counted here."

A self-contradiction inside one shipped field description. The contrast that proves the diagnosis:
`SALVAGE AND REUSE EXISTING AGGREGATE` — the OTHER unassigned pick, ruled into the same bucket —
fires 3/3, because the plan that carries it prices it in CY. The two picks differ only in the unit
the state happened to use.

The unit guard is NOT the bug and is not removed here. What was missing is a place to put an
off-unit grading item, which `hot_mix_tons` / `base_tons` / `shoulder_tons` have each had since
2026-08-10. Twelfth instance of the standing rule.

NOTHING HERE CONVERTS ANYTHING. Spec: docs/_spec/2026-08-11-grading-unit-capture.md.
"""
from __future__ import annotations

import json
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
    raise AssertionError(f"{name!r} is not in schema.SCALAR_FIELDS")


# ── 1. The status function: six states, six values, and the two that must never collapse ────────

def test_found_but_unconvertible_absent_and_failed_are_three_distinct_values():
    """The rule this whole change is an instance of, asserted directly.

    A grading item priced in TONS, a plan with no grading at all, and an extraction that returned
    nothing are three different facts. Before this field pair they were one null.
    """
    found_unconvertible = schema.grading_unit_status(
        {"grading_measured_unit": "OTHER", "grading_quantity": None,
         "grading_unconverted": "CLEAN ROCK | 758 | TON"})
    genuinely_absent = schema.grading_unit_status(
        {"grading_measured_unit": "NONE", "grading_quantity": None, "grading_unconverted": None})
    extraction_failed = schema.grading_unit_status({})

    assert found_unconvertible == "unconverted_only"
    assert genuinely_absent == "not_present"
    assert extraction_failed == "unknown"
    assert len({found_unconvertible, genuinely_absent, extraction_failed}) == 3


def test_no_answer_is_never_reported_as_the_plan_having_no_grading():
    """`unknown` vs `not_present` is the whole point. A missing/blank/garbage unit is `unknown`."""
    for unit in (None, "", "  ", "CUBIC YARDS", "TON", "SY", "cy+ton"):
        rec = {"grading_measured_unit": unit, "grading_quantity": None, "grading_unconverted": None}
        assert schema.grading_unit_status(rec) == "unknown", f"unit={unit!r}"


def test_the_six_statuses_are_all_reachable_and_none_is_dead():
    """Every token in GRADING_UNIT_STATUSES must be producible, or the vocabulary is lying."""
    cases = {
        "cy_only": {"grading_measured_unit": "CY", "grading_quantity": 38535,
                    "grading_unconverted": None},
        "unconverted_only": {"grading_measured_unit": "OTHER", "grading_quantity": None,
                             "grading_unconverted": "CLEAN ROCK | 758 | TON"},
        "cy_and_unconverted": {"grading_measured_unit": "CY+OTHER", "grading_quantity": 38535,
                               "grading_unconverted": "CLEAN ROCK | 758 | TON"},
        "not_present": {"grading_measured_unit": "NONE", "grading_quantity": None,
                        "grading_unconverted": None},
        "unknown": {},
        # A declared CY with an off-unit line behind it contradicts itself. Surfaced, not resolved.
        "inconsistent": {"grading_measured_unit": "CY", "grading_quantity": 38535,
                         "grading_unconverted": "CLEAN ROCK | 758 | TON"},
    }
    assert set(cases) == set(schema.GRADING_UNIT_STATUSES), \
        "a status is unreachable or untested — check GRADING_UNIT_STATUSES"
    for want, rec in cases.items():
        assert schema.grading_unit_status(rec) == want, f"{want}: {rec}"


def test_a_declared_unit_with_nothing_behind_it_is_inconsistent_not_a_clean_answer():
    """`OTHER` means 'the item exists and is off-unit'. `OTHER` with nothing listed has lost the
    very item it claims exists — that is a contradiction, not an empty plan."""
    assert schema.grading_unit_status(
        {"grading_measured_unit": "OTHER", "grading_quantity": None,
         "grading_unconverted": None}) == "inconsistent"
    assert schema.grading_unit_status(
        {"grading_measured_unit": "CY", "grading_quantity": None,
         "grading_unconverted": None}) == "inconsistent"
    assert schema.grading_unit_status(
        {"grading_measured_unit": "NONE", "grading_quantity": 100,
         "grading_unconverted": None}) == "inconsistent"


def test_it_tolerates_a_schema_cell_as_well_as_a_bare_scalar():
    """Records reach this from two shapes: {value, confidence, page} cells and flat dicts."""
    assert schema.grading_unit_status({
        "grading_measured_unit": {"value": "CY+OTHER", "confidence": "high", "page": 13},
        "grading_quantity": {"value": 38535, "confidence": "high", "page": 13},
        "grading_unconverted": {"value": "CLEAN ROCK | 758 | TON", "confidence": "high",
                                "page": 13}}) == "cy_and_unconverted"


def test_nothing_in_this_module_converts_a_unit():
    """A tons figure must never become a CY figure. The status function is pure and reports only."""
    rec = {"grading_measured_unit": "OTHER", "grading_quantity": None,
           "grading_unconverted": "CLEAN ROCK | 758 | TON"}
    before = json.dumps(rec, sort_keys=True)
    schema.grading_unit_status(rec)
    assert json.dumps(rec, sort_keys=True) == before, "grading_unit_status mutated its input"


# ── 2. The vocabulary is grounded in a real priced corpus row, not a fixture ─────────────────────

@pytest.fixture(scope="module")
def corpus_lines():
    out = []
    files = [p for p in sorted(MD_CACHE.glob("*.json")) if not p.name.endswith(".hybrid.json")]
    assert files, "no non-hybrid md_cache files — the corpus fixture itself is broken"
    for p in files:
        for pg in json.loads(p.read_text()):
            for line in (pg.get("md") or pg.get("text") or "").splitlines():
                line = line.strip()
                if line:
                    out.append((p.name, pg.get("page"), line))
    assert len(out) > 10_000, f"corpus is implausibly small ({len(out)} lines)"
    return out


@needs_md
def test_clean_rock_is_a_real_priced_ton_row_which_is_why_this_field_pair_exists(corpus_lines):
    """Dunn Job 23388 p13 `|**045**|**302**|**2000**|**CLEAN ROCK**|**TON**|**758.**|`.

    Asserted against the source text so a future cache change cannot quietly move the target: the
    item is priced, it is priced in TONS, and the CY bucket therefore cannot hold it.
    """
    hits = [h for h in corpus_lines if corpus_match.matches("CLEAN ROCK", h[2])]
    assert hits, "'CLEAN ROCK' matches no corpus line — the measurement target moved"
    priced = [h for h in hits if "758" in h[2] and "TON" in h[2].upper()]
    assert priced, (f"no CLEAN ROCK line carrying the measured 758 TON: {[h[2][:120] for h in hits[:3]]}")


@needs_md
def test_the_grading_prose_names_the_item_AND_gives_it_somewhere_to_go(corpus_lines):
    """Naming an item and then forbidding its unit, with no third field, is what fired 0/13."""
    g = _desc("grading_quantity").upper()
    assert "CLEAN ROCK" in g, "grading_quantity no longer names Alex's CLEAN ROCK ruling"
    assert "GRADING_UNCONVERTED" in g, (
        "grading_quantity forbids off-unit items without saying where they go — that is the "
        "self-contradiction this field pair was added to resolve, restored")
    u = _desc("grading_unconverted").upper()
    assert "CLEAN ROCK" in u
    assert "DO NOT CONVERT" in u, "the capture field must forbid conversion in its own words"


@needs_md
def test_the_cy_native_tokens_are_not_the_tons_bucket_tokens(corpus_lines):
    """grading is CUBIC-YARD native. If it ever answers 'TON' the closed vocabulary is lying, and
    that lie would propagate into bid_projects.grade_cy."""
    assert schema.GRADING_UNIT_TOKENS == ("CY", "CY+OTHER", "OTHER", "NONE")
    assert "TON" not in schema.GRADING_UNIT_TOKENS
    d = _desc("grading_measured_unit").upper()
    for token in schema.GRADING_UNIT_TOKENS:
        assert f"'{token}'" in d, f"the prose does not offer the token {token!r}"
    # The four unit-free statuses are spelled identically to the tons vocabulary on purpose.
    shared = set(schema.GRADING_UNIT_STATUSES) & set(schema.BUCKET_UNIT_STATUSES)
    assert shared == {"unconverted_only", "not_present", "unknown", "inconsistent"}


def test_grading_is_not_a_tons_bucket():
    """It must not have been folded into TONS_BUCKETS — see the spec §2.2 for why."""
    assert "grading_quantity" not in schema.TONS_BUCKETS
    with pytest.raises(ValueError):
        schema.bucket_unit_status({}, "grading_quantity")
