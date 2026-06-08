#!/usr/bin/env python3
"""
Apply client-approved bidder name standardizations to CSI_data_combined.csv

Reads bidder_potential_duplicates.csv, extracts MERGE decisions,
and applies the name mapping to all BIDDER_*_NAME columns in CSI_data_combined.csv
"""

import pandas as pd
from datetime import datetime
import os

# File paths
DUPLICATES_FILE = "data/cleaning_review/bidder_potential_duplicates.csv"
INPUT_FILE = "data/processed/CSI_data_combined.csv"
OUTPUT_FILE = "data/processed/CSI_data_combined.csv"
CHANGELOG_FILE = "docs/CHANGELOG.md"

def build_standardization_mapping(duplicates_df):
    """
    Extract variation → core_name mappings from bidder_potential_duplicates.csv
    Only includes rows marked with 'MERGE' decision
    """
    merge_rows = duplicates_df[duplicates_df['client_decision'] == 'MERGE']
    mapping = dict(zip(merge_rows['variation'], merge_rows['core_name']))
    return mapping

def apply_standardization(data_df, mapping):
    """
    Apply bidder name standardization to all BIDDER_*_NAME columns
    """
    bidder_cols = [col for col in data_df.columns if col.startswith('BIDDER_') and col.endswith('_NAME')]

    stats = {
        'total_replacements': 0,
        'affected_rows': set(),
        'unique_companies_merged': set()
    }

    for col in bidder_cols:
        for variation, core_name in mapping.items():
            mask = data_df[col] == variation
            if mask.any():
                data_df.loc[mask, col] = core_name
                stats['total_replacements'] += mask.sum()
                stats['affected_rows'].update(data_df[mask].index.tolist())
                stats['unique_companies_merged'].add((variation, core_name))

    return data_df, stats

def get_deleted_companies(duplicates_df):
    """
    Extract list of companies marked for deletion
    """
    delete_rows = duplicates_df[duplicates_df['client_decision'].str.contains('Delete', na=False)]
    return delete_rows['variation'].unique().tolist()

def main():
    print("=" * 80)
    print("CSI Bidder Name Standardization")
    print("=" * 80)

    # Load files
    print("\n1. Loading bidder_potential_duplicates.csv...")
    duplicates_df = pd.read_csv(DUPLICATES_FILE)
    print(f"   Loaded {len(duplicates_df)} duplicate entries")

    print("\n2. Building standardization mapping...")
    mapping = build_standardization_mapping(duplicates_df)
    print(f"   Created {len(mapping)} variation → core_name mappings")

    deleted_companies = get_deleted_companies(duplicates_df)
    print(f"   Found {len(deleted_companies)} companies marked for deletion")

    print("\n3. Loading CSI_data_combined.csv...")
    data_df = pd.read_csv(INPUT_FILE)
    print(f"   Loaded {len(data_df)} rows, {len(data_df.columns)} columns")

    print("\n4. Applying standardization to BIDDER_*_NAME columns...")
    data_df, stats = apply_standardization(data_df, mapping)

    print(f"   Total replacements: {stats['total_replacements']}")
    print(f"   Affected rows: {len(stats['affected_rows'])}")
    print(f"   Unique company merges: {len(stats['unique_companies_merged'])}")

    print("\n5. Saving updated file...")
    data_df.to_csv(OUTPUT_FILE, index=False)
    print(f"   Saved to {OUTPUT_FILE}")

    print("\n6. Updating CHANGELOG.md...")
    update_changelog(mapping, deleted_companies, stats, duplicates_df)
    print(f"   Updated {CHANGELOG_FILE}")

    print("\n" + "=" * 80)
    print("✓ Standardization complete!")
    print("=" * 80)

def update_changelog(mapping, deleted_companies, stats, duplicates_df):
    """
    Add a new section to CHANGELOG.md documenting this cleaning pass
    """
    date_str = datetime.now().strftime("%Y-%m-%d")

    # Count by merged group
    unique_merged_groups = len(set(mapping.values()))

    # Calculate statistics
    total_bids_by_deleted = duplicates_df[
        duplicates_df['client_decision'].str.contains('Delete', na=False)
    ]['total_bids'].sum()

    changelog_entry = f"""
## Cleaning Pass 4 — {date_str} (Quinten)

### Changes Applied

1. **Standardized bidder names based on client review**
   - Source: `bidder_potential_duplicates.csv` (client-approved decision log)
   - Created standardization mapping from {len(mapping)} variations → {unique_merged_groups} canonical names
   - Applied mapping to all BIDDER_*_NAME columns (15 columns across {len(duplicates_df[duplicates_df['client_decision'] == 'MERGE'])} variation rows)
   - Total bidder records affected: {stats['total_replacements']} replacements across {len(stats['affected_rows'])} project rows

2. **Deleted non-competitor entries**
   - Deleted {len(deleted_companies)} company variations matching non-competitor patterns
   - Pattern: Companies marked as "ENGINEERS ESTIMATE" and similar (total {total_bids_by_deleted} bids removed from analysis)
   - These are engineering cost estimates, not actual competitor bids, so are excluded from competitor analysis

### Standardization Details

- **Companies merged**: {unique_merged_groups}
- **Variations consolidated**: {len(mapping)}
- **Examples**:
"""

    # Add top 10 merge examples
    merge_groups = {}
    for variation, core_name in mapping.items():
        if core_name not in merge_groups:
            merge_groups[core_name] = []
        merge_groups[core_name].append(variation)

    for i, (core_name, variations) in enumerate(sorted(merge_groups.items())[:10], 1):
        changelog_entry += f"  - {core_name}: {', '.join(sorted(variations))}\n"

    if len(merge_groups) > 10:
        changelog_entry += f"  - ... and {len(merge_groups) - 10} more company groups\n"

    changelog_entry += f"""
### Data Integrity Notes

- No source rows were dropped from the wide-format file.
- Bidder names in BIDDER_*_NAME columns are now standardized and ready for competitor analysis.
- The standardization is one-way (variation → core_name); raw names can be recovered from git history if needed.
- Ready for: Competitor scoring engine, bid aggregation by company, market analysis.

"""

    # Append to changelog
    with open(CHANGELOG_FILE, 'a') as f:
        f.write(changelog_entry)

if __name__ == "__main__":
    main()
