"""Tests for the plan_reader ↔ ci_model join key (issue #34).

Every expected value here comes from the contract, `docs/2026-07-26_architecture_recommendation.md`
§3, not from re-running the implementation's own logic. §3 is the independent source of truth: it is
what the CI side builds against, and if these tests and that document disagree, the document wins.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from join_key import (  # noqa: E402
    NO_DIGITS,
    normalize_county,
    normalize_join_key,
    normalize_sp_number,
    normalize_state,
)


class JoinKeyTest(unittest.TestCase):
    def test_contract_worked_example(self):
        """§3's own example: the three components normalize and join with '~'."""
        key, reason = normalize_join_key("MN", "Otter Tail County", "SP 8303-48")
        self.assertEqual(key, "MN~otter tail~SP830348")
        self.assertIsNone(reason)

    def test_digitless_sp_number_is_unkeyable(self):
        """§3: no digits in the normalized sp_number means no key, and a stated reason.

        `UNKNOWN` is the real value this catches: it is the sp_number of
        2025_MINNEHAHA-CO-SD_UNKNOWN_NOBID, the single row in the 117-plan corpus the rule nulls.
        """
        key, reason = normalize_join_key("SD", "Minnehaha", "UNKNOWN")
        self.assertIsNone(key)
        self.assertTrue(reason, "an unkeyable row must say why, never a bare None")

    def test_sp_number_worked_examples(self):
        """All three sp_number examples §3 spells out, verbatim."""
        for raw, expected in [
            ("SP 8303-48", "SP830348"),
            ("CP-13(23)01", "CP132301"),
            ("SAP 021-600-023", "SAP021600023"),
        ]:
            with self.subTest(sp_number=raw):
                self.assertEqual(normalize_sp_number(raw), expected)

    def test_county_spellings_collapse_to_one_token(self):
        """A county written three ways must key identically, or the join silently drops rows."""
        for raw in ["Otter Tail County", "otter tail", "Otter-Tail", "  OTTER   TAIL  "]:
            with self.subTest(county=raw):
                self.assertEqual(normalize_county(raw), "otter tail")

    def test_county_steps_run_in_the_order_the_contract_states(self):
        """§3: collapse separators BEFORE stripping a trailing "county".

        The reverse order leaves `Otter-Tail-County` untouched, because its trailing token is joined
        by a hyphen rather than a space, so the two orders produce different keys for the same
        county. No value in the corpus is order-sensitive as of 2026-07-26, so this is insurance
        rather than a live divergence. It is pinned here because the CI side implements §3
        independently, and a disagreement returns zero matches while saying nothing.
        """
        self.assertEqual(normalize_county("Otter-Tail-County"), "otter tail")

    def test_state_is_upper_and_trimmed(self):
        for raw in ["MN", "mn", " Mn "]:
            with self.subTest(state=raw):
                self.assertEqual(normalize_state(raw), "MN")

    def test_missing_components_do_not_raise(self):
        """None is a real input here: §4.1 types state, county and sp_number all nullable."""
        key, reason = normalize_join_key(None, None, None)
        self.assertIsNone(key)
        self.assertEqual(reason, NO_DIGITS)


if __name__ == "__main__":
    unittest.main()
