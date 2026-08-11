"""Run plan 9786015 through the material-tons merge BOTH ways and print the numbers side by side.

The point is to DEMONSTRATE the flag rather than describe it: same record, same code, one boolean
apart. No network, no Chroma, no database, no PDF re-conversion — this reads nothing and writes
nothing, so it is safe to run while the app is live.

    python3 pipelines/plan_reader/03_evaluation/2026-08-10_conversion_flag_demo.py

The fixture is plan 9786015 (Murray Co MN, CSAH 2 / Maryland Ave, md-cache a3171c2187e8af85),
bid-schedule page 27, items 40/41/44-47. It is the only validated arithmetic oracle on this project:
CSI hand-computed 3,851.75 / 13.09 / 1,901.34 for it, so the ON column can be checked against a
human's answer rather than against our own code's.

Forcing the flag on here is a deliberate, visible assignment to the module global. It is NOT how
production turns it on — production cannot, because two of the three gates (a CSI signature on the
factor table, a recorded acceptance run) are not satisfiable by anything in this file.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "01_pipeline"))

import material_tons_merge  # noqa: E402

CSI_HAND_COMPUTED = {"base_tons": 3851.75, "shoulder_tons": 13.09, "hot_mix_tons": 1901.34}


def _cell(value):
    return {"value": value, "confidence": "high", "page": 27, "reason": ""}


RECORD = {
    # This plan states NO tonnage for any of the three buckets. Every figure below is SY or CY.
    "base_tons": _cell(None),
    "shoulder_tons": _cell(None),
    "hot_mix_tons": _cell(None),
    "base_cy_items": _cell([
        {"quantity": 2485.0, "unit": "CY", "depth_in": None, "page": 27,
         "note": "41 Class 5 Aggregate Base (CV)(P)"}]),
    "shoulder_cy_items": _cell([
        {"quantity": 38.0, "unit": "SY", "depth_in": 8.0, "page": 27,
         "note": '40 8" Class 5 Alley & Shouldering Aggregate Surfacing'}]),
    "mix_sy_depth_items": _cell([
        {"quantity": 5368.0, "unit": "SY", "depth_in": 2.0, "page": 27,
         "note": "44 Type SP 9.5 Wearing (CSAH 2)"},
        {"quantity": 5368.0, "unit": "SY", "depth_in": 3.0, "page": 27,
         "note": "45 Type SP 12.5 Non-Wearing (CSAH 2)"},
        {"quantity": 1703.0, "unit": "SY", "depth_in": 1.5, "page": 27,
         "note": "46 Type SP 9.5 Wearing (Maryland Ave)"},
        {"quantity": 1703.0, "unit": "SY", "depth_in": 2.5, "page": 27,
         "note": "47 Type SP 12.5 Wearing (Maryland Ave)"}]),
}


def run(enabled: bool):
    original = material_tons_merge.CONVERSION_ENABLED
    material_tons_merge.CONVERSION_ENABLED = enabled
    try:
        return (material_tons_merge.merge_material_tons(RECORD),
                material_tons_merge.conversion_report(RECORD))
    finally:
        material_tons_merge.CONVERSION_ENABLED = original


def fmt(value):
    return "None" if value is None else f"{value:,.2f}"


def main():
    print(f"CONVERSION_ENABLED at import = {material_tons_merge.CONVERSION_ENABLED}")
    print(f"  G1 factors blessed      : {material_tons_merge._g1_factors_blessed()}")
    print(f"  G2 acceptance recorded  : {material_tons_merge._g2_acceptance_recorded()} "
          f"(record file exists: {material_tons_merge.ACCEPTANCE_RECORD_PATH.exists()})")
    print(f"  G3 operator opt-in      : {material_tons_merge._g3_operator_opt_in()[0]} "
          f"(${material_tons_merge.OPERATOR_OPT_IN_ENV})")
    print()

    off_tons, off_status = run(False)
    on_tons, on_status = run(True)

    print(f"{'bucket':<14} {'OFF (default)':>14} {'ON':>12} {'CSI by hand':>12}   status OFF / ON")
    print("-" * 92)
    for bucket in ("base_tons", "shoulder_tons", "hot_mix_tons"):
        print(f"{bucket:<14} {fmt(off_tons[bucket]):>14} {fmt(on_tons[bucket]):>12} "
              f"{CSI_HAND_COMPUTED[bucket]:>12,.2f}   "
              f"{off_status[bucket]['status']} / {on_status[bucket]['status']}")
    print()

    ok = all(round(on_tons[b], 2) == CSI_HAND_COMPUTED[b] for b in CSI_HAND_COMPUTED)
    print(f"ON reproduces all three CSI figures : {'YES' if ok else 'NO'}")
    print(f"OFF derives nothing                 : "
          f"{'YES' if all(off_tons[b] is None for b in CSI_HAND_COMPUTED) else 'NO'}")
    print("OFF is not a silence                : every bucket reports "
          f"{off_status['base_tons']['status']!r} with a convertible-item count, not a null")


if __name__ == "__main__":
    main()
