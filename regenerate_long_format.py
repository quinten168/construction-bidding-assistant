#!/usr/bin/env python3
"""
Regenerate CSI_data_long_format.csv from updated CSI_data_combined.csv

Pivots wide format (one row per project, 15 bidders) to long format
(one row per bidder per project) with standardized company names.
"""

import pandas as pd
import numpy as np
from datetime import datetime

# File paths
WIDE_FORMAT_FILE = "data/processed/CSI_data_combined.csv"
LONG_FORMAT_OUTPUT = "data/processed/CSI_data_long_format.csv"
CHANGELOG_FILE = "docs/CHANGELOG.md"

def pivot_to_long_format(wide_df):
    """
    Convert wide format (one row per project) to long format (one row per bidder per project)
    """
    # Identify bidder columns
    bidder_name_cols = [col for col in wide_df.columns if col.startswith('BIDDER_') and col.endswith('_NAME')]
    bidder_total_cols = [col for col in wide_df.columns if col.startswith('BIDDER_') and col.endswith('_TOTAL')]

    # Non-bidder columns (project metadata)
    metadata_cols = [col for col in wide_df.columns if not (col.startswith('BIDDER_'))]

    # Extract bidder sequence numbers
    sequences = [int(col.split('_')[1]) for col in bidder_name_cols]

    # Create list to collect long format rows
    long_rows = []

    for idx, row in wide_df.iterrows():
        for seq, name_col, total_col in zip(sequences, bidder_name_cols, bidder_total_cols):
            bidder_name = row[name_col]
            bid_amount = row[total_col]

            # Skip null bidders
            if pd.isna(bidder_name) or bidder_name == '':
                continue

            # Create row with metadata + bidder info
            long_row = {**row[metadata_cols].to_dict(),
                       'BIDDER_NAME': bidder_name,
                       'BID_AMOUNT': bid_amount,
                       'bidder_sequence': seq}
            long_rows.append(long_row)

    long_df = pd.DataFrame(long_rows)

    # Sort by date, location, project, bidder sequence
    long_df = long_df.sort_values(['DATE', 'LOCATION', 'PROJECT', 'bidder_sequence']).reset_index(drop=True)

    return long_df

def delete_engineers_estimate(long_df):
    """
    Remove rows matching ENGINEERS ESTIMATE patterns
    """
    mask = long_df['BIDDER_NAME'].str.contains('ENGINEER', case=False, na=False)
    deleted_count = mask.sum()
    long_df = long_df[~mask].reset_index(drop=True)
    return long_df, deleted_count

def main():
    print("=" * 80)
    print("CSI Long Format Regeneration with Standardized Names")
    print("=" * 80)

    print("\n1. Loading CSI_data_combined.csv (updated wide format)...")
    wide_df = pd.read_csv(WIDE_FORMAT_FILE)
    print(f"   Loaded {len(wide_df)} rows, {len(wide_df.columns)} columns")

    print("\n2. Pivoting to long format (one row per bidder per project)...")
    long_df = pivot_to_long_format(wide_df)
    print(f"   Created {len(long_df)} bidder records")

    print("\n3. Removing ENGINEERS ESTIMATE entries...")
    long_df, deleted_count = delete_engineers_estimate(long_df)
    print(f"   Deleted {deleted_count} ENGINEERS ESTIMATE entries")
    print(f"   Final long format: {len(long_df)} rows")

    print("\n4. Saving updated long format...")
    long_df.to_csv(LONG_FORMAT_OUTPUT, index=False)
    print(f"   Saved to {LONG_FORMAT_OUTPUT}")

    # Count unique competitors
    unique_competitors = long_df['BIDDER_NAME'].nunique()
    print(f"   Unique competitors: {unique_competitors}")

    print("\n5. Updating CHANGELOG.md...")
    update_changelog(len(long_df), unique_competitors, deleted_count)
    print(f"   Updated {CHANGELOG_FILE}")

    print("\n" + "=" * 80)
    print("✓ Long format regeneration complete!")
    print("=" * 80)

def update_changelog(long_format_rows, unique_competitors, deleted_engineers):
    """
    Add note to CHANGELOG documenting the long format regeneration
    """
    date_str = datetime.now().strftime("%Y-%m-%d")

    changelog_entry = f"""
## Long Format Regeneration — {date_str}

### Purpose
Updated `CSI_data_long_format.csv` to reflect standardized bidder names from Cleaning Pass 4.

### Changes Applied

1. **Re-pivoted from updated wide format**
   - Source: `CSI_data_combined.csv` (with Cleaning Pass 4 standardized names)
   - Output: `CSI_data_long_format.csv` ({long_format_rows} rows)
   - One row per bidder per project (from 1,661 projects with up to 15 bidders each)

2. **Removed non-competitor entries**
   - Deleted {deleted_engineers} ENGINEERS ESTIMATE entries (same pattern as prior pass)

3. **Results**
   - Total bidder records: {long_format_rows}
   - Unique competitors: {unique_competitors}
   - Ready for: Competitor scoring engine (similarity, distance, capacity analysis)

### Data Integrity Notes
- All standardized company names from Cleaning Pass 4 are now reflected in long format.
- Original wide format preserved for auditability.
- Bidder sequence (1-15) preserved to track bid ranking within each project.
- No rows lost; consolidation only.

"""

    with open(CHANGELOG_FILE, 'a') as f:
        f.write(changelog_entry)

if __name__ == "__main__":
    main()
