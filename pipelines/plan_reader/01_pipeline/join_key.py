"""The join key that crosses the plan_reader → ci_model seam.

Specified in `docs/2026-07-26_architecture_recommendation.md` §3. This module is the SINGLE
implementation of that rule: the live path reaches it through `plan_reader_bridge` (which puts
`01_pipeline/` on sys.path) and the batch path through the same sys.path insertion its `04_tools`
scripts already do. Do not add a second copy on either side. §3 is explicit about why:

    Both sides must implement this identically or the join silently returns zero matches.

Pure functions only. No I/O, no database, no PDF, no network.
"""
from __future__ import annotations

import re

SEPARATOR = "~"

# The only `unkeyable_reason` this module emits today. §3 defines exactly one condition under which
# a key cannot be formed. See issue #35: the rule under-flags badly, catching 1 row of the 117-plan
# corpus where a further 15 hold a road name that passes the digit test and yields a well-formed key
# matching nothing. Widening it here would diverge from the contract the CI side builds against, so
# it stays literal until #35 settles the shape of the fix.
NO_DIGITS = "sp_number_has_no_digits"


def normalize_state(state):
    """`upper(trim(x))` per §3."""
    return (state or "").strip().upper()


def normalize_county(county):
    """`lower(trim(x))`, collapse whitespace and hyphens to one space, then strip a trailing "county".

    The order is load-bearing and §3 now states it explicitly. Stripping first would leave
    `Otter-Tail-County` untouched, since its trailing token is hyphen-joined rather than
    space-joined, and the two sides would key the same county differently.
    """
    text = (county or "").strip().lower()
    text = re.sub(r"[\s-]+", " ", text).strip()
    return re.sub(r"\s+county$", "", text).strip()


def normalize_sp_number(sp_number):
    """`upper(x)`, remove every non-alphanumeric character."""
    return re.sub(r"[^A-Z0-9]", "", (sp_number or "").upper())


def normalize_join_key(state, county, sp_number):
    """Return `(join_key, unkeyable_reason)` for one plan's identity.

    On success the reason is None. When no key can be formed the key is None and the reason says
    why, so a null key is never indistinguishable from an absent one (contract §5).
    """
    sp = normalize_sp_number(sp_number)
    if not any(char.isdigit() for char in sp):
        return (None, NO_DIGITS)
    return (
        SEPARATOR.join((normalize_state(state), normalize_county(county), sp)),
        None,
    )
