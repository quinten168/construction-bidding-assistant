"""Merge native-tons extraction with converted CY/SY-depth items into one final tons total.

Pure, no I/O — same shape as `bid_projects_record.py` and `join_key.py` next door: everything here
is testable from a dict, and this function is never given, and never reads, the database. That is
what makes it idempotent by construction: re-running it on the same extraction record always
produces the same answer, because nothing about the current `scratch.bid_projects` state feeds in.

WHY THIS EXISTS
----------------
`base_tons`/`shoulder_tons`/`hot_mix_tons` only ever captured TON-denominated bid items. A CY-
measured base item (no depth stated) or an SY-measured aggregate/mix item that states its own
thickness (e.g. '8" Class 5 ... Surfacing') was extracted for nothing and silently dropped — no
field, no field_confidence entry, no citation. `schema.py` now captures those separately
(`base_cy_items`/`shoulder_cy_items`/`mix_sy_depth_items`, each a RAW per-item list — quantity, unit,
stated depth — with NO arithmetic performed at extraction time; see schema.py's field descriptions
and `resolve_cy_item()`). This module does the two remaining steps: sum each item's CY (or
SY*inches) contribution, then apply the CSI-supplied density constant.

ALL ARITHMETIC IS CODE-ONLY, NEVER THE MODEL'S
--------------------------------------------------
An earlier version of this feature asked the model to pre-compute the per-bucket CY/SY*inches total
itself. A live test on 2026-08-10 caught the model returning a "value" that disagreed with its own
"reason" text's arithmetic (Murray Co/Fulda: reasoning correctly computed a mix total of 33,652; the
returned value was 38,167 — a ~13% silent error that would have gone straight into a live,
DB-persisted, model-feeding total). Multi-item multiply-then-sum is not reliable model arithmetic
even at temperature=0, so the schema no longer asks for it at all — the model only ever reports
numbers it read directly off the page (a quantity, a stated thickness), and every multiplication and
every sum, geometric or density, happens here, in auditable, testable Python.

CONSTANT PROVENANCE
--------------------
`AGGREGATE_TON_PER_CY` and `MIX_TON_PER_SY_INCH` are CSI-supplied (MnDOT reference conversion
table), confirmed 2026-08-10. This is a DIFFERENT, more authoritative source than
`bucket_hierarchy.csv`'s `1.75 Ton/CY`, which every existing reference to it flags as unverified and
never checked against a plan (`schema.py`'s milling_tons comment, `docs/_spec/2026-08-10-milling-
unit-capture.md:44-49,269-271`). See `docs/_spec/2026-08-10-aggregate-mix-tons-conversion.md` for the
full writeup of why this constant is trusted where that one deliberately wasn't.

NO PER-STATE OR PER-MATERIAL LOOKUP TABLE
--------------------------------------------
Both constants are fixed, MnDOT-sourced numbers, not a configurable table — explicitly deferred if
this ever needs to expand past MnDOT projects.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import schema

AGGREGATE_TON_PER_CY = 1.55    # CSI-supplied (MnDOT), confirmed 2026-08-10 — distinct from and
                                 # supersedes bucket_hierarchy.csv's unverified 1.75 for this use.
MIX_TON_PER_SY_INCH = 0.0565   # CSI-supplied (MnDOT), confirmed 2026-08-10.


# ── The conversion flag: computed at import, NEVER configured ─────────────────
#
# Added 2026-08-10 as the integration step for PR #102. The engine above is correct and validated
# (it reproduces CSI's own hand-computed 3,851.75 / 13.09 / 1,901.34 on plan 9786015 to the cent),
# but it is NOT yet allowed to change a number a human reads. Three things are still missing —
# per-value provenance, the two internal failure/empty collapses, and a reconciled status
# vocabulary — and until they land, a converted tonnage is indistinguishable from a stated one on
# screen and in scratch.bid_projects. So the engine ships present and dormant.
#
# THE DESIGN PROPERTY THAT MATTERS, per docs/_spec/2026-08-10-placed-material-conversion.md §9.2:
# the flag is not a boolean anybody sets. It is COMPUTED at import from three independent gates,
# and every way of doing nothing evaluates to False:
#
#   G1 (blessed)   — every factor row carries a non-empty blessed_by + blessed_on. Nobody has
#                    signed, so FACTOR_TABLE's blessing fields are empty strings, so G1 is False.
#                    Forgetting to get a signature leaves the flag off; there is no separate
#                    "remember to turn it off" step to forget.
#   G2 (reproduces)— the acceptance run's recorded result exists on disk and says it passed. The
#                    file does not exist in this tree. A MISSING FILE IS FALSE — never "assume it
#                    passed", never "assume it is fine because the tests are green".
#   G3 (opt-in)    — an operator env var set to the one explicit token. UNSET IS FALSE. Anything
#                    other than the exact token is False and says so loudly rather than falling
#                    back silently.
#
# A fresh clone therefore has conversion OFF with no action taken, and `git grep` for a config file
# to fix will find nothing, because there isn't one. Turning it on takes three deliberate positive
# acts by three different kinds of authority (CSI, a recorded test run, an operator).
#
# WITH THE FLAG OFF, `merge_material_tons` returns the native TON extraction and nothing else — the
# exact pre-#102 numbers. The three items fields are still EXTRACTED and still carried in
# field_confidence, which is what makes `conversion_report()` below able to say "we saw convertible
# items and withheld them" rather than emitting a null. See CONVERSION_STATUSES.

OPERATOR_OPT_IN_ENV = "PLAN_READER_MATERIAL_CONVERSION"
OPERATOR_OPT_IN_TOKEN = "on"     # the ONE accepted value; compared case-insensitively, stripped

# The factor table. `blessed_by`/`blessed_on` are G1, and they are deliberately empty: no factor in
# this table has been signed off by CSI in writing. The numbers themselves are the data-validated
# assumption (they reproduce CSI's own arithmetic exactly, §10.1 of the placed-material spec), which
# is why they are recorded here with their basis rather than left blank — but a reproduction is
# evidence that these are the factors CSI *used*, not that they are the factors CSI *endorses*.
FACTOR_TABLE = {
    "F1": {"material": "Bituminous mixture, placed (MN Type SP / ND Superpave / SD Asphalt Concrete)",
           "factor": MIX_TON_PER_SY_INCH, "units": "ton per SY per inch of compacted depth",
           "basis": "113 lb/SY-in / 2000 — MnDOT reference conversion table (CSI-supplied "
                    "2026-08-10); ASSUMPTION, not traced to a printed state spec-book page",
           "blessed_by": "", "blessed_on": ""},
    "F2": {"material": "Class 5 aggregate base / shoulder aggregate, purchased and placed",
           "factor": AGGREGATE_TON_PER_CY, "units": "ton per CY",
           "basis": "3,100 lb/CY / 2000 — MnDOT reference conversion table (CSI-supplied "
                    "2026-08-10); ASSUMPTION, not traced to a printed state spec-book page",
           "blessed_by": "", "blessed_on": ""},
}

# G2's record. Deliberately a path that does not exist: the acceptance run has not been recorded.
ACCEPTANCE_RECORD_PATH = (Path(__file__).resolve().parents[1]
                          / "03_evaluation" / "outputs"
                          / "2026-08-10_conversion_acceptance.json")


def _g1_factors_blessed() -> bool:
    """Every factor row carries a non-empty blessed_by AND blessed_on. An empty table is NOT
    vacuously blessed — an empty table means there is nothing to convert with."""
    if not FACTOR_TABLE:
        return False
    return all(str(row.get("blessed_by") or "").strip()
               and str(row.get("blessed_on") or "").strip()
               for row in FACTOR_TABLE.values())


def _g2_acceptance_recorded() -> bool:
    """The acceptance run's recorded result exists and says it passed. A missing file, an
    unreadable file, or a file that does not explicitly say `"passed": true` is all False —
    absence is never taken as success (the repo's standing 'a success signal at the wrong layer is
    not evidence' rule: a file we cannot read is not a passing test)."""
    try:
        record = json.loads(ACCEPTANCE_RECORD_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return record.get("passed") is True


def _g3_operator_opt_in() -> tuple[bool, str | None]:
    """(opted_in, complaint). Unset -> (False, None): the ordinary, expected, silent case. Set to
    anything other than the exact token -> (False, <complaint>): a misconfiguration a human should
    hear about, NOT a silent fallback to off. Returning the complaint rather than logging here
    keeps this module pure/importable; the caller emits it once at import."""
    raw = os.environ.get(OPERATOR_OPT_IN_ENV)
    if raw is None:
        return False, None
    if raw.strip().lower() == OPERATOR_OPT_IN_TOKEN:
        return True, None
    return False, (f"{OPERATOR_OPT_IN_ENV}={raw!r} is not the accepted token "
                   f"{OPERATOR_OPT_IN_TOKEN!r} — material conversion stays OFF")


def _compute_conversion_enabled() -> bool:
    opted_in, complaint = _g3_operator_opt_in()
    if complaint:
        print(f"  WARNING: {complaint}")
    return _g1_factors_blessed() and _g2_acceptance_recorded() and opted_in


#: Evaluated once, at import. Module-level rather than re-read per call so that the answer cannot
#: change mid-report; read through the module global inside the functions below so a test can
#: exercise the ON path by setting `material_tons_merge.CONVERSION_ENABLED = True` explicitly —
#: which is a deliberate, visible act in a test, not a supported production switch.
CONVERSION_ENABLED = _compute_conversion_enabled()


# ── Conversion status: OFF is a state, never a silence ────────────────────────
#
# Standing rule: never let a failure and a legitimate empty answer share a return value. Applied
# here to the flag itself — "we did not try" must not look like "we tried and there was nothing".
# Each bucket gets exactly one of these, always, in every code path.
CONVERSION_STATUSES = (
    # ── flag OFF ──
    "disabled_withheld",            # the flag is off AND at least one item WOULD have converted.
                                    # This is the one that must never be silent: a real tonnage
                                    # exists on this plan and we are deliberately not showing it.
    "disabled_nothing_convertible",  # off, items were captured, none of them was convertible
                                    # anyway (e.g. SY with no stated depth) — turning the flag on
                                    # would change nothing for this bucket.
    "disabled_not_applicable",      # off, and the model asserted an empty items list: there is
                                    # genuinely nothing here to convert. A real answer.
    "disabled_unknown_input",       # off, and the items field is null — extraction gave no answer
                                    # at all, so we cannot even say whether anything was withheld.
    # ── flag ON ──
    "all_converted",                # every captured item converted
    "partly_converted",             # some converted, some could not. THE BUCKET TOTAL IS
                                    # INCOMPLETE and must render as incomplete.
    "none_converted",               # items exist, none was convertible
    "not_applicable",               # empty items list — nothing to convert, and that is an answer
    "unknown",                      # items field null — extraction produced no answer
)

_BUCKETS = (
    # (tons field, items field, resolver, density factor)
    ("base_tons", "base_cy_items", schema.resolve_cy_item, AGGREGATE_TON_PER_CY),
    ("shoulder_tons", "shoulder_cy_items", schema.resolve_cy_item, AGGREGATE_TON_PER_CY),
    ("hot_mix_tons", "mix_sy_depth_items", schema.resolve_sy_depth_product, MIX_TON_PER_SY_INCH),
)


def _sum_items(items, resolver) -> float | None:
    """A raw items list -> total, summing only the items `resolver` can actually convert. Returns
    None for a null/empty/all-unconvertible list — never a bare 0 standing in for 'we don't know'
    (the null-vs-zero discipline `bid_projects_record.py::_quantity` already documents). An item
    the resolver can't convert (SY with no stated depth) is simply excluded from the sum here;
    `schema.base_unit_status` (etc.) is what surfaces that as `sy_no_depth_present` rather than
    letting it disappear silently.

    `resolver` MUST be `schema.resolve_cy_item` for base/shoulder (CY = SY * inches / 36) or
    `schema.resolve_sy_depth_product` for mix (SY * inches, no /36 — mix has no CY intermediate).
    Passing the wrong one is a real, previously-shipped bug: it silently divided the mix total by
    36, undercounting mix tons 36x. Never default this parameter — every caller must choose
    explicitly."""
    if not items:
        return None
    total = None
    for item in items:
        contribution = resolver(item)
        if contribution is not None:
            total = (total or 0) + contribution
    return total


def _combine(native, cy_total, factor) -> float | None:
    """native (already tons) + cy_total * factor -> tons, or None if both components are absent."""
    native_val = native if isinstance(native, (int, float)) else None
    if native_val is None and cy_total is None:
        return None
    return (native_val or 0) + (cy_total or 0) * factor


def merge_material_tons(record: dict) -> dict:
    """record -> {'base_tons': ..., 'shoulder_tons': ..., 'hot_mix_tons': ...}.

    WITH `CONVERSION_ENABLED` (the default, and the only state a fresh clone can be in): each value
    is the native TON extraction and NOTHING ELSE — byte-identical to the pre-#102 behaviour, so no
    derived tonnage reaches `quantities`, the archetype rule, or scratch.bid_projects. The captured
    CY/SY items are not summed, not multiplied, not consulted.

    WITH IT ON: each value is the native TON extraction plus its converted CY/SY-depth items summed
    and density-multiplied (or None if the plan has neither).

    Either way this is a pure function of `record` — never touches the database, so calling it
    twice on the same record always yields the same three numbers.

    This function answers "how many tons", and only that. It deliberately does NOT signal whether
    conversion ran, because a number cannot carry that without becoming ambiguous — that is
    `conversion_report()`'s job, and every caller that renders these numbers must read it too.
    """
    enabled = CONVERSION_ENABLED
    merged = {}
    for tons_field, items_field, resolver, factor in _BUCKETS:
        native = schema._cell_value(record, tons_field)
        converted = (_sum_items(schema._cell_value(record, items_field), resolver)
                     if enabled else None)
        merged[tons_field] = _combine(native, converted, factor)
    return merged


def sum_milling_sy_items(record: dict) -> float | None:
    """record -> the code-computed milling_sy total, summing milling_sy_items — or None if the
    model reported no items (null) or an empty list, so the caller (report.py) can fall back to
    the model's own milling_sy scalar.

    Deliberately NOT wired into merge_material_tons/_BUCKETS above: those three buckets convert a
    DIFFERENT unit into tons using an unverified, CSI-gated density factor (CONVERSION_ENABLED).
    milling_sy_items needs no conversion and no gate — every entry is already in SY, milling_sy's
    own native unit, so this is plain same-unit addition, not an unverified constant, and ships
    unconditionally regardless of CONVERSION_ENABLED.

    Added 2026-08-11 after a live, 4-for-4 reproducible case (Grant Co MN, SP 2680-44): the
    model's own milling_sy VALUE (83,777) disagreed with its own REASON text's arithmetic (which
    correctly computed 8,346 + 7,250 + 76,527 = 92,123) on every run — the same
    value-disagrees-with-its-own-reason failure class the mix bucket hit before this file existed.
    """
    items = schema._cell_value(record, "milling_sy_items")
    return _sum_items(items, schema.resolve_milling_sy_item)


def conversion_report(record: dict) -> dict:
    """record -> {'base_tons': {...}, 'shoulder_tons': {...}, 'hot_mix_tons': {...}}, one entry per
    bucket, each holding a `status` from CONVERSION_STATUSES plus the item counts behind it.

    THIS IS THE ANTI-SILENCE MECHANISM. With the flag off, a plan whose base is CY-measured is not
    "no base" — it is `disabled_withheld` with `convertible_item_count >= 1`, which a reader can
    tell apart from `disabled_not_applicable` (the model asserted there is nothing) and from
    `disabled_unknown_input` (extraction did not answer). Twelve prior instances on this project
    collapsed exactly this distinction into a null; this one does not.

    What is deliberately NOT here: the withheld tonnage itself. Carrying the number the flag exists
    to withhold would hand any consumer a way to render it by accident, which is the whole failure
    the flag is preventing. The count says a number exists; the count does not leak it.
    """
    enabled = CONVERSION_ENABLED
    report = {}
    for tons_field, items_field, resolver, _factor in _BUCKETS:
        items = schema._cell_value(record, items_field)
        if items is None or not isinstance(items, list):
            # None: the model gave no answer. Non-list: a malformed answer. Neither is "empty",
            # and neither lets us claim anything was or was not withheld.
            report[tons_field] = {
                "status": "disabled_unknown_input" if not enabled else "unknown",
                "captured_item_count": None, "convertible_item_count": None,
                "conversion_enabled": enabled,
            }
            continue
        convertible = sum(1 for item in items if resolver(item) is not None)
        captured = len(items)
        if not enabled:
            if convertible:
                status = "disabled_withheld"
            elif captured:
                status = "disabled_nothing_convertible"
            else:
                status = "disabled_not_applicable"
        elif not captured:
            status = "not_applicable"
        elif convertible == captured:
            status = "all_converted"
        elif convertible:
            status = "partly_converted"
        else:
            status = "none_converted"
        report[tons_field] = {"status": status, "captured_item_count": captured,
                              "convertible_item_count": convertible,
                              "conversion_enabled": enabled}
    return report
