"""plan_reader payload → one `scratch.bid_projects` row. Pure assembly, no I/O. (#36)

This is the whole of the record-building half of the seam. It reads `bid_projects_mapping.yaml`
and applies it literally: **a payload field that is not listed there is not written.** That is
deliberate (mapping doc §"THIS FILE IS THE MAPPING") — a rename can then never silently drop data,
because the field simply stops appearing rather than quietly landing in the wrong column.

Pure functions only, like `join_key.py` next door: no database, no network, no PDF, no clock except
the `processed_at` the caller passes in. Everything here is testable from a dict.

WHAT THIS DOES NOT DO
---------------------
It does not write. It does not decide whether a row is a duplicate of an existing one — it computes
the *inputs* to that decision (`join_key`, `plan_uid`) and the writer (#37) owns the comparison.
And it never DELETEs anything, because nothing in this seam ever does (settled decision 4).

THE COUNTY CONVENTION — READ THIS BEFORE CHANGING `_county_for_column`
---------------------------------------------------------------------
`bid_projects_mapping.yaml` says `county` takes `transform: strip_county_suffix`, i.e.
`join_key.normalize_county`, which yields `'stearns'`. **The live table does not look like that.**
All ~1,591 existing rows hold an uppercase, `' CO'`-suffixed value: `'STEARNS CO'`, `'MILLE LACS CO'`,
`'CASS CO & CLAY CO'`. Following the YAML literally would put `'stearns'` into a column where every
other row says `'STEARNS CO'`, and would produce a `project_natural_key` that does not resemble the
existing `MN_STEARNS_CO_MELROSE_2023-08-03` shape.

Resolved 2026-08-03 by the owner, explicitly: **match the existing convention, do not invent a
cleaner one.** Consistency with 1,591 rows of real data beats internal tidiness on a key we have
already agreed to recompute table-wide later. The YAML is the thing that is wrong here, and it is
flagged in `docs/2026-08-03_bid_projects_mapping.md` rather than silently diverged from.

`join_key.normalize_county` is still used, unchanged, for `join_key` — that key belongs to the
plan_reader↔ci_model contract (§3) and is a different key with different rules. The two are
deliberately not unified.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Optional

import yaml

import join_key

MAPPING_PATH = Path(__file__).with_name("bid_projects_mapping.yaml")

# Settled decisions, 2026-08-03. Named constants rather than inline literals so a future reader can
# grep for them and find this comment.
CITY_SENTINEL = "UNKNOWN"          # decision 2 — uppercase, matching the key's casing. Never "".
UNPARSED_BID_DATE = "1900-01-01"   # decision 3 — never reject the row; write an obviously-fake date
ROW_SOURCE = "plan_reader"         # decision 1 — the safety column the CI upsert guards on

# Contract §5: which fields must be present for a row to call itself complete. Anything absent here
# is NAMED in missing_fields rather than defaulted, so a consumer substituting a value is choosing
# to rather than doing it by accident.
REQUIRED_FIELDS = ("state", "county", "source_project_id", "bid_date")


class MappingError(RuntimeError):
    """The mapping file and the payload disagree in a way that must not be papered over."""


def load_mapping(path: Path = MAPPING_PATH) -> dict:
    """Parse the YAML. Kept separate so tests can inject a mapping without touching the file."""
    with open(path, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


# --- normalisation helpers ------------------------------------------------------------------------
def _upper_trim(value) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip().upper()
    return text or None


_COUNTY_SUFFIX_RE = re.compile(r"\s+(COUNTY|CO)\.?$", re.IGNORECASE)


def _county_for_column(county) -> Optional[str]:
    """Match the live convention: uppercase, single-spaced, exactly one trailing ' CO'.

    Accepts any of 'Stearns', 'Stearns County', 'STEARNS CO', 'McKenzie County' (what the reverse
    geocoder returns) and produces 'STEARNS CO' / 'MCKENZIE CO'. Normalising the suffix off first
    and re-adding it is what makes the function idempotent — running it twice must not yield
    'STEARNS CO CO'.

    Multi-county values ('CASS CO & CLAY CO') are passed through with each part normalised, because
    the live table already contains them and collapsing them would destroy the very ambiguity the
    mapping doc wants visible for the 10 '?'/two-county rows.
    """
    if county is None:
        return None
    text = re.sub(r"[\s-]+", " ", str(county).strip()).strip()
    if not text:
        return None
    if "&" in text:
        parts = [p.strip() for p in text.split("&") if p.strip()]
        return " & ".join(_county_for_column(p) or "" for p in parts) or None
    text = _COUNTY_SUFFIX_RE.sub("", text).strip()
    if not text:
        return None
    return f"{text.upper()} CO"


def _slug(value) -> Optional[str]:
    """The key-component slug. Uppercase, spaces → underscores.

    Owner's decision, 2026-08-03: match the existing convention rather than invent a cleaner one.
    This makes the key unparseable — 'MN_STEARNS_CO_MELROSE_2023-08-03' cannot be split back into
    its components, because the county itself contains an underscore. That is already true of all
    1,591 existing rows; it is a known defect, and consistency beats cleanliness on a key we have
    agreed to recompute table-wide once its composition is settled.
    """
    if value is None:
        return None
    text = re.sub(r"[\s-]+", " ", str(value).strip()).strip()
    if not text:
        return None
    return re.sub(r"\s+", "_", text.upper())


def parse_bid_date(raw) -> tuple[Optional[str], bool]:
    """(iso_date_or_None, was_parsed). Free text in, ISO date out.

    `bid_deadline` is genuinely free text — '09:30AM Central Time on August 15, 2025', '11/15/2025',
    or None. Returns None (not the sentinel) when it cannot parse; substituting the sentinel is the
    CALLER's decision, and keeping that split here means `bid_date` and `project_natural_key` can
    make it differently. `bid_deadline_raw` always retains the original either way.
    """
    if raw is None:
        return None, False
    text = str(raw).strip()
    if not text:
        return None, False

    months = ("january february march april may june july august september october november december"
              ).split()
    month_alt = "|".join(m[:3] for m in months)

    # ISO first — it is unambiguous, and construction_start/end already arrive in this shape.
    if m := re.search(r"\b(\d{4})-(\d{2})-(\d{2})\b", text):
        y, mo, d = m.groups()
        return _valid(y, mo, d)
    # 'August 15, 2025' / 'Aug 15 2025'
    if m := re.search(rf"\b({month_alt})[a-z]*\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?,?\s+(\d{{4}})\b",
                      text, re.IGNORECASE):
        name, d, y = m.groups()
        mo = months.index(next(x for x in months if x.startswith(name.lower()[:3]))) + 1
        return _valid(y, f"{mo:02d}", d)
    # '15 August 2025'
    if m := re.search(rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+({month_alt})[a-z]*\.?,?\s+(\d{{4}})\b",
                      text, re.IGNORECASE):
        d, name, y = m.groups()
        mo = months.index(next(x for x in months if x.startswith(name.lower()[:3]))) + 1
        return _valid(y, f"{mo:02d}", d)
    # '11/15/2025' — US order, which is what every DOT in the six operating states writes.
    if m := re.search(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b", text):
        mo, d, y = m.groups()
        return _valid(y, mo, d)
    return None, False


def _valid(y, mo, d) -> tuple[Optional[str], bool]:
    """Reject an impossible date rather than emit a plausible-looking wrong one."""
    try:
        import datetime
        iso = datetime.date(int(y), int(mo), int(d)).isoformat()
    except (ValueError, TypeError):
        return None, False
    return iso, True


def _quantity_unit(payload: dict, label: str) -> Optional[str]:
    """The unit as the plan itself stated it, per quantity (settled decision 5).

    Eight columns rather than one global `unit_source`, because one global column cannot say WHICH
    quantity's unit was assumed, and that distinction is not recoverable after the fact.
    """
    for item in payload.get("quantities") or []:
        if (item or {}).get("label") == label:
            return item.get("unit")
    return None


def _quantity(payload: dict, label: str):
    """payload.quantities is a LIST of {label, value, unit}, and report.py has already dropped any
    entry whose value is None/''/0. So an absent quantity and a genuine zero are indistinguishable
    here, and we write NULL rather than 0 — contract §5, and the exact failure that left ten CI
    features hard zeros for months."""
    for item in payload.get("quantities") or []:
        if (item or {}).get("label") == label:
            return item.get("value")
    return None


def build_project_natural_key(state, county_col, city, bid_date_iso) -> str:
    """`{state}_{county}_{city}_{bid_date}`, slugged, with sentinels for the two soft spots.

    `county_col` is expected in the live column convention already ('STEARNS CO'), so the key
    matches the existing MN_STEARNS_CO_MELROSE_2023-08-03 shape.
    """
    return "_".join((
        _slug(state) or CITY_SENTINEL,
        _slug(county_col) or CITY_SENTINEL,
        _slug(city) or CITY_SENTINEL,
        bid_date_iso or UNPARSED_BID_DATE,
    ))


# --- the assembly ---------------------------------------------------------------------------------
def build_record(payload: dict, *, content_hash: str = None, source_file: str = None,
                 processed_at: str = None, mapping: dict = None) -> dict:
    """One payload → one dict of column → value, ready for the writer. Never raises on missing data.

    `content_hash` / `source_file` / `processed_at` are passed in rather than dug out of the payload
    because older cached payloads predate those keys entirely (all 7 fixtures have no `content_hash`
    field at all — the cache FILENAME carries it). Making them explicit parameters means the caller
    states where they came from instead of this function guessing.
    """
    mapping = mapping or load_mapping()
    identity = payload.get("identity") or {}

    state = _upper_trim(identity.get("state"))
    county_col = _county_for_column(identity.get("county"))

    bid_date, date_parsed = parse_bid_date(identity.get("bid_deadline"))
    # Decision 3: never reject the row. The sentinel goes in the column AND the key, and
    # bid_date_unparsed marks it so it is findable without string-matching a magic date.
    bid_date_col = bid_date or UNPARSED_BID_DATE

    # The city component comes ONLY from the reverse geocoder — plan_reader cannot extract a city,
    # which is the entire reason the geocode stage exists.
    city = identity.get("geocoded_city")

    jkey, unkeyable = join_key.normalize_join_key(
        identity.get("state"), identity.get("county"), identity.get("sp_number"))

    row: dict[str, Any] = {
        # --- case 1: existing columns ---
        "state": state,
        "county": county_col,
        "project_location": identity.get("location"),
        "source_project_id": identity.get("sp_number"),
        "project_latitude": identity.get("latitude"),
        "project_longitude": identity.get("longitude"),
        "mix_tons": _quantity(payload, "MIX"),
        "grading_yards": _quantity(payload, "GRADE"),
        "base_tons": _quantity(payload, "BASE"),
        "shldr_tons": _quantity(payload, "SHLDR"),
        "mill_sy": _quantity(payload, "MILL"),
        "crush_tons": _quantity(payload, "CRUSH"),
        "stock_tons": _quantity(payload, "STOCK"),
        # Units, one per quantity (decision 5). Null where the quantity itself is null.
        "mix_unit": _quantity_unit(payload, "MIX"),
        "grading_unit": _quantity_unit(payload, "GRADE"),
        "base_unit": _quantity_unit(payload, "BASE"),
        "shldr_unit": _quantity_unit(payload, "SHLDR"),
        "mill_unit": _quantity_unit(payload, "MILL"),
        "crush_unit": _quantity_unit(payload, "CRUSH"),
        "stock_unit": _quantity_unit(payload, "STOCK"),
        # 'observed' only when the plan actually yielded a quantity to observe a unit on. A row with
        # no quantities gets NULL, not a confident-looking 'observed' about nothing.
        "unit_source": ("observed" if (payload.get("quantities") or []) else None),
        # --- case 3: assembled / derived ---
        "project_natural_key": build_project_natural_key(state, county_col, city, bid_date),
        "bid_date": bid_date_col,
        "bid_year": int(bid_date[:4]) if bid_date else None,
        "project_name": None,      # null_always — no equivalent anywhere in schema.py
        "project_type": None,      # null_always — CI's vocabulary; ours goes to plan_reader_archetype
        # --- case 2: new columns ---
        "plan_uid": content_hash,
        "join_key": jkey,
        "unkeyable_reason": unkeyable,
        "processed_at": processed_at,
        "source_file": source_file or payload.get("source_file"),
        "mapping_version": mapping.get("version"),
        "row_source": ROW_SOURCE,
        "geocoded_city": identity.get("geocoded_city"),
        "geocoded_county": identity.get("geocoded_county"),
        "geocoded_state": identity.get("geocoded_state"),
        "geocoded_zip": identity.get("geocoded_zip"),
        "coordinate_provenance": identity.get("coordinate_provenance"),
        "geocode_provenance": identity.get("geocode_provenance"),
        "plan_reader_archetype": payload.get("archetype"),
        "bid_deadline_raw": identity.get("bid_deadline"),
        "construction_start_raw": identity.get("construction_start"),
        "construction_end_raw": identity.get("construction_end"),
        "prevailing_wages": identity.get("prevailing_wages"),
        "traffic_level": identity.get("traffic_level"),
        "gotcha_count": len(payload.get("gotchas") or []),
        "bid_date_unparsed": (not date_parsed),
        "duplicate_flag": False,       # the writer owns this; assembled false so the shape is whole
        "duplicate_reason": None,
    }

    missing = [f for f in REQUIRED_FIELDS
               if row.get(f) in (None, "") or (f == "bid_date" and not date_parsed)]
    row["row_status"] = "complete" if not missing else "partial"
    row["missing_fields"] = ",".join(missing) or None
    return row


def mapped_columns(mapping: dict = None) -> list[str]:
    """Every column the mapping declares, in file order. The writer uses this to build its INSERT,
    so a column that is not in the YAML is not written — the no-fuzzy-match rule, enforced rather
    than merely documented."""
    mapping = mapping or load_mapping()
    cols = [e["target"] for e in mapping.get("direct") or []]
    cols += [e["target"] for e in mapping.get("new_columns") or []]
    cols += [e["target"] for e in mapping.get("unpopulated") or []
             if e.get("resolution") != "db_default"]
    return cols
