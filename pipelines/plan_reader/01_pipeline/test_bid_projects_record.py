"""Tests for the plan_reader -> scratch.bid_projects row assembly (issue #36).

Pure unit tests, no database — build_record() takes a plan_payload dict and returns a plain dict.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from bid_projects_record import (  # noqa: E402
    CITY_SENTINEL,
    UNPARSED_BID_DATE,
    build_project_natural_key,
    build_record,
    mapped_columns,
)


def _payload(**identity_overrides) -> dict:
    identity = {
        "state": "MN", "county": "Stearns", "location": "TH 23, Melrose",
        "sp_number": "SP 7305-45", "latitude": 45.67, "longitude": -94.81,
        "bid_deadline": "2023-08-03", "geocoded_city": "Melrose",
        "geocoded_county": "Stearns County", "geocoded_state": "MN", "geocoded_zip": "56352",
        "coordinate_provenance": "midpoint", "geocode_provenance": "google",
        "prevailing_wages": True, "traffic_level": "moderate",
    }
    identity.update(identity_overrides)
    return {
        "plan_id": "test-plan-1",
        "identity": identity,
        "quantities": [
            {"label": "MIX", "value": 12000.0, "unit": "t"},
            {"label": "GRADE", "value": 800.0, "unit": "CY"},
        ],
        "gotchas": [{"code": "prevailing_wage"}],
        "archetype": "Mill & Overlay",
    }


class BuildProjectNaturalKeyTest(unittest.TestCase):
    def test_fully_resolved_key_has_no_suffix(self):
        key, provisional, reason = build_project_natural_key(
            "MN", "STEARNS CO", "Melrose", "2023-08-03", plan_uid="abc123")
        self.assertEqual(key, "MN_STEARNS_CO_MELROSE_2023-08-03")
        self.assertFalse(provisional)
        self.assertIsNone(reason)

    def test_sentinel_components_get_hash_suffix_and_flagged_provisional(self):
        key, provisional, reason = build_project_natural_key(
            None, None, None, None, plan_uid="e9ae6f091234abcd")
        self.assertEqual(key, f"UNKNOWN_{CITY_SENTINEL}_{CITY_SENTINEL}_{UNPARSED_BID_DATE}_e9ae6f09")
        self.assertTrue(provisional)
        self.assertIn("sentinel:", reason)

    def test_two_different_projects_with_same_sentinels_get_different_keys(self):
        """The exact bug build_project_natural_key exists to prevent: two ND plans with no
        extractable county/date must not collapse onto the same key and overwrite each other."""
        key1, _, _ = build_project_natural_key(None, None, None, None, plan_uid="e9ae6f091234")
        key2, _, _ = build_project_natural_key(None, None, None, None, plan_uid="2c83fa4e5678")
        self.assertNotEqual(key1, key2)


class BuildRecordTest(unittest.TestCase):
    def test_well_formed_payload_produces_a_complete_non_provisional_row(self):
        row = build_record(_payload(), content_hash="abc123def456", source_file="test-plan-1")
        self.assertEqual(row["project_natural_key"], "MN_STEARNS_CO_MELROSE_2023-08-03")
        self.assertFalse(row["key_provisional"])
        self.assertEqual(row["row_status"], "complete")
        self.assertIsNone(row["missing_fields"])
        self.assertEqual(row["state"], "MN")
        self.assertEqual(row["county"], "STEARNS CO")
        self.assertEqual(row["plan_uid"], "abc123def456")
        self.assertEqual(row["row_source"], "plan_reader")
        self.assertFalse(row["duplicate_flag"])

    def test_quantities_map_onto_material_columns_with_units(self):
        row = build_record(_payload(), content_hash="abc123")
        self.assertEqual(row["mix_tons"], 12000.0)
        self.assertEqual(row["mix_unit"], "t")
        self.assertEqual(row["grading_yards"], 800.0)
        self.assertEqual(row["grading_unit"], "CY")
        self.assertIsNone(row["base_tons"])   # not present in this payload -> NULL, not 0
        self.assertIsNone(row["base_unit"])
        self.assertEqual(row["unit_source"], "observed")

    def test_missing_required_fields_are_named_not_defaulted(self):
        row = build_record(_payload(sp_number=None, bid_deadline=None), content_hash="abc123")
        self.assertEqual(row["row_status"], "partial")
        self.assertIn("source_project_id", row["missing_fields"])
        self.assertIn("bid_date", row["missing_fields"])
        self.assertTrue(row["key_provisional"])

    def test_unparseable_bid_date_writes_sentinel_not_none(self):
        row = build_record(_payload(bid_deadline="whenever, probably"), content_hash="abc123")
        self.assertEqual(row["bid_date"], UNPARSED_BID_DATE)
        self.assertTrue(row["bid_date_unparsed"])

    def test_archetype_and_gotcha_count_carry_through(self):
        row = build_record(_payload(), content_hash="abc123")
        self.assertEqual(row["plan_reader_archetype"], "Mill & Overlay")
        self.assertEqual(row["gotcha_count"], 1)


class MappedColumnsTest(unittest.TestCase):
    def test_includes_direct_new_and_unpopulated_columns(self):
        cols = mapped_columns()
        for expected in ("state", "county", "mix_tons",          # direct
                         "plan_uid", "join_key", "row_source",    # new_columns
                         "project_natural_key", "bid_date"):      # unpopulated (not db_default)
            self.assertIn(expected, cols)


if __name__ == "__main__":
    unittest.main()
