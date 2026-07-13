#!/usr/bin/env python3
"""
Competitor Name Registry Updater

Scans raw bid data and pit access names for new company name variants not yet
in the competitor_name_registry. Auto-confirms 100%-certain matches (exact
normalized form), and queues ambiguous ones for client review with a fuzzy
suggestion. Writes all new rows directly to the registry.

Also backfills a 'source' column (bid_data / pit_list / both / unknown) for
every row without touching any other existing values, and prints a pit-name
match report showing which pit operators are linked to historical bidders.

Usage:
    python update_name_registry.py

Inputs:
    data/processed/CSI_data_combined.csv              (wide format; BIDDER_1..15_NAME columns)
    data/processed/MN_pit_list_cleaned.csv            (Access column)
    ci_model/.../competitor_name_registry - name_variants.csv

Output:
    Same competitor_name_registry file, with new rows appended and 'source'
    column added. No existing cell values are changed.
"""

import re
import pandas as pd
from rapidfuzz import fuzz

REGISTRY_FILE = (
    "ci_model/competitor_prediction_model/01_candidates/outputs/"
    "competitor_name_registry - name_variants.csv"
)
COMBINED_FILE = "data/processed/CSI_data_combined.csv"
PIT_FILE      = "data/processed/MN_pit_list_cleaned.csv"

BIDDER_NAME_COLS = [f"BIDDER_{i}_NAME" for i in range(1, 16)]
FUZZY_THRESHOLD  = 80


def norm(s) -> str:
    if pd.isna(s):
        return ""
    return re.sub(r"\s+", " ", str(s).strip().upper())


def load_raw_names() -> dict[str, str]:
    """Return {name: source} where source is 'bid_data', 'pit_list', or 'both'."""
    available_cols = [
        c for c in BIDDER_NAME_COLS
        if c in pd.read_csv(COMBINED_FILE, nrows=0).columns
    ]
    combined = pd.read_csv(COMBINED_FILE, usecols=available_cols or BIDDER_NAME_COLS, dtype=str)
    bid_names: set[str] = set(
        pd.melt(combined, value_vars=available_cols or BIDDER_NAME_COLS)["value"]
        .dropna().str.strip()
        .pipe(lambda s: s[s != ""])
    )

    pit = pd.read_csv(PIT_FILE, usecols=["Access"], dtype=str)
    pit_names: set[str] = set(pit["Access"].dropna().str.strip().pipe(lambda s: s[s != ""]))

    result: dict[str, str] = {}
    for n in bid_names | pit_names:
        if n in bid_names and n in pit_names:
            result[n] = "both"
        elif n in bid_names:
            result[n] = "bid_data"
        else:
            result[n] = "pit_list"
    return result


def find_new_names(source_map: dict[str, str], registry: pd.DataFrame) -> list[str]:
    known = set(registry["raw_name_variant"].dropna().str.strip())
    return sorted(source_map.keys() - known)


def auto_confirm(name: str, known_comp_names) -> str | None:
    norm_name = norm(name)
    for comp in known_comp_names:
        if norm(comp) == norm_name:
            return comp
    return None


def suggest_comp(name: str, known_comp_names) -> str:
    best_score, best_comp = 0, ""
    for comp in known_comp_names:
        score = fuzz.token_sort_ratio(norm(name), norm(comp))
        if score > best_score:
            best_score, best_comp = score, comp
    return best_comp if best_score >= FUZZY_THRESHOLD else ""


def backfill_source(registry: pd.DataFrame, source_map: dict[str, str]) -> pd.DataFrame:
    """Insert 'source' column after 'raw_name_variant'; only fills rows where source is blank."""
    if "source" not in registry.columns:
        # Insert as 3rd column (after comp_name, raw_name_variant)
        insert_pos = registry.columns.get_loc("raw_name_variant") + 1
        registry.insert(insert_pos, "source", "")

    for idx, row in registry.iterrows():
        existing = str(row.get("source", "")).strip()
        if existing:  # respect any value the user has already set
            continue
        raw = str(row.get("raw_name_variant", "")).strip()
        registry.at[idx, "source"] = source_map.get(raw, "unknown")

    return registry


def print_pit_match_report(registry: pd.DataFrame) -> None:
    """Print which pit_list names are/aren't matched to a historical bidder comp_name."""
    bid_comp_names: set[str] = set(
        registry.loc[
            registry["source"].isin(["bid_data", "both"]),
            "comp_name",
        ]
        .dropna().str.strip()
        .pipe(lambda s: s[s != ""])
    )

    pit_rows = registry[registry["source"].isin(["pit_list", "both"])]

    matched: list[tuple[str, str]] = []
    unmatched: list[tuple[str, str]] = []
    not_in_list: list[str] = []

    for _, row in pit_rows.iterrows():
        raw  = str(row.get("raw_name_variant", "")).strip()
        comp = str(row.get("comp_name", "")).strip()
        if comp.lower() in ("", "nan"):
            comp = ""
        if not comp:
            not_in_list.append(raw)
        elif comp in bid_comp_names:
            matched.append((raw, comp))
        else:
            unmatched.append((raw, comp))

    print("\n" + "=" * 60)
    print("  Pit Name Match Report")
    print("=" * 60)

    if matched:
        print(f"\nMATCHED ({len(matched)}) — comp_name exists in bid data:")
        for raw, comp in sorted(matched):
            print(f"  {raw:<42} → {comp}")

    if unmatched:
        print(f"\nUNMATCHED ({len(unmatched)}) — comp_name not found in bid data:  ← review")
        for raw, comp in sorted(unmatched):
            print(f"  {raw:<42} → {comp}")

    if not_in_list:
        print(f"\nNOT_IN_BIDDER_LIST ({len(not_in_list)}) — no comp_name set:")
        for raw in sorted(not_in_list):
            print(f"  {raw}")

    print()


def main():
    registry   = pd.read_csv(REGISTRY_FILE, dtype=str)
    source_map = load_raw_names()
    new_names  = find_new_names(source_map, registry)

    # ── Append new name variants ───────────────────────────────────────────────
    if new_names:
        print(f"Found {len(new_names)} new name variant(s):\n")
        known_comp_names = registry["comp_name"].dropna().unique()
        new_rows = []

        for name in new_names:
            comp = auto_confirm(name, known_comp_names)
            src  = source_map.get(name, "unknown")
            if comp:
                tag = registry.loc[registry["comp_name"] == comp, "Top Competitors Tag"].iloc[0]
                new_rows.append({
                    "comp_name":           comp,
                    "raw_name_variant":    name,
                    "source":              src,
                    "Top Competitors Tag": tag,
                })
                print(f"  [auto-confirmed]      {name}  →  {comp}")
            else:
                hint = suggest_comp(name, known_comp_names)
                new_rows.append({
                    "comp_name":           "",
                    "raw_name_variant":    name,
                    "source":              src,
                    "Top Competitors Tag": "",
                    "suggested_comp":      hint,
                })
                hint_str = f"suggested: {hint}" if hint else "no suggestion"
                print(f"  [needs client review] {name}  ({hint_str})")

        registry = pd.concat([registry, pd.DataFrame(new_rows)], ignore_index=True)

        auto_count   = sum(1 for r in new_rows if r["comp_name"])
        review_count = sum(1 for r in new_rows if not r["comp_name"])
        print(f"\n{len(new_rows)} new rows added.  Auto-confirmed: {auto_count}  "
              f"Needs review: {review_count}")
    else:
        print("No new name variants found — registry is up to date.")

    # ── Backfill source column (never overwrites user-set values) ─────────────
    registry = backfill_source(registry, source_map)

    # ── Save (column order: comp_name, raw_name_variant, source, ...) ─────────
    registry.to_csv(REGISTRY_FILE, index=False)
    print(f"Registry saved → {REGISTRY_FILE}")

    # ── Pit name match report (console only) ──────────────────────────────────
    print_pit_match_report(registry)


if __name__ == "__main__":
    main()
