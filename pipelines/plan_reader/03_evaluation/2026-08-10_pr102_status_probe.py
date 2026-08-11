"""2026-08-10_pr102_status_probe.py — behaviour probes on #102's derived statuses and merge, for
the cases the golden says are real: one bucket carrying TWO units at once, and an SY item with no
stated depth sitting beside a convertible one. No network, no I/O."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "01_pipeline"))
import schema                # noqa: E402
import material_tons_merge   # noqa: E402


def rec(tons, items):
    return {"base_tons": schema.cell(tons, "high" if tons else "", 27, "native"),
            "base_cy_items": schema.cell(items, "high", 27, "items"),
            "shoulder_tons": schema.cell(None, "", None, ""),
            "shoulder_cy_items": schema.cell([], "high", None, ""),
            "hot_mix_tons": schema.cell(None, "", None, ""),
            "mix_sy_depth_items": schema.cell([], "high", None, "")}


CASES = {
    "TON only": rec(500, []),
    "TON + CY (both units, the golden's real case)": rec(500, [
        {"quantity": 100.0, "unit": "CY", "depth_in": None, "page": 1, "note": ""}]),
    "TON + SY-with-depth": rec(500, [
        {"quantity": 360.0, "unit": "SY", "depth_in": 6.0, "page": 1, "note": ""}]),
    "CY + SY-with-depth (no tons)": rec(None, [
        {"quantity": 100.0, "unit": "CY", "depth_in": None, "page": 1, "note": ""},
        {"quantity": 360.0, "unit": "SY", "depth_in": 6.0, "page": 1, "note": ""}]),
    "CY + SY-NO-depth (one convertible, one not)": rec(None, [
        {"quantity": 100.0, "unit": "CY", "depth_in": None, "page": 1, "note": ""},
        {"quantity": 999.0, "unit": "SY", "depth_in": None, "page": 1, "note": ""}]),
    "GAL item only (a unit the resolver does not know)": rec(None, [
        {"quantity": 4200.0, "unit": "GAL", "depth_in": None, "page": 1, "note": ""}]),
    "items field null (extraction produced no answer)": rec(500, None),
}

for name, r in CASES.items():
    print(f"{name}")
    print(f"    base_unit_status = {schema.base_unit_status(r)!r}")
    print(f"    merged base_tons = {material_tons_merge.merge_material_tons(r)['base_tons']}")
