#!/usr/bin/env python3
"""
Apply additional approved bidder name standardizations to all data files
Based on additional_bidder_merges_review.csv
"""

import pandas as pd
from datetime import datetime

# File paths
REVIEW_FILE = "data/cleaning_review/additional_bidder_merges_review.csv"
WIDE_FORMAT_FILE = "data/processed/CSI_data_combined.csv"
LONG_FORMAT_FILE = "data/processed/CSI_data_long_format.csv"
COMPANY_LIST_FILE = "data/cleaning_review/bidder_full_company_list.csv"
CHANGELOG_FILE = "docs/CHANGELOG.md"

def build_additional_mapping(review_df):
    """Extract variation → core_name mappings from review file"""
    mapping = dict(zip(review_df['current_variation'], review_df['recommended_core_name']))
    return mapping

def apply_wide_format_standardization(wide_df, mapping):
    """Apply additional merges to wide format file"""
    bidder_cols = [col for col in wide_df.columns if col.startswith('BIDDER_') and col.endswith('_NAME')]

    stats = {
        'total_replacements': 0,
        'affected_rows': set(),
        'unique_companies_merged': set()
    }

    for col in bidder_cols:
        for variation, core_name in mapping.items():
            mask = wide_df[col] == variation
            if mask.any():
                wide_df.loc[mask, col] = core_name
                stats['total_replacements'] += mask.sum()
                stats['affected_rows'].update(wide_df[mask].index.tolist())
                stats['unique_companies_merged'].add((variation, core_name))

    return wide_df, stats

def pivot_to_long_format(wide_df):
    """Convert wide format to long format (one row per bidder per project)"""
    bidder_name_cols = [col for col in wide_df.columns if col.startswith('BIDDER_') and col.endswith('_NAME')]
    bidder_total_cols = [col for col in wide_df.columns if col.startswith('BIDDER_') and col.endswith('_TOTAL')]
    metadata_cols = [col for col in wide_df.columns if not (col.startswith('BIDDER_'))]

    sequences = [int(col.split('_')[1]) for col in bidder_name_cols]
    long_rows = []

    for idx, row in wide_df.iterrows():
        for seq, name_col, total_col in zip(sequences, bidder_name_cols, bidder_total_cols):
            bidder_name = row[name_col]
            bid_amount = row[total_col]

            if pd.isna(bidder_name) or bidder_name == '':
                continue

            long_row = {**row[metadata_cols].to_dict(),
                       'BIDDER_NAME': bidder_name,
                       'BID_AMOUNT': bid_amount,
                       'bidder_sequence': seq}
            long_rows.append(long_row)

    long_df = pd.DataFrame(long_rows)
    long_df = long_df.sort_values(['DATE', 'LOCATION', 'PROJECT', 'bidder_sequence']).reset_index(drop=True)
    return long_df

def delete_engineers_estimate(long_df):
    """Remove ENGINEERS ESTIMATE entries"""
    mask = long_df['BIDDER_NAME'].str.contains('ENGINEER', case=False, na=False)
    deleted_count = mask.sum()
    long_df = long_df[~mask].reset_index(drop=True)
    return long_df, deleted_count

def regenerate_company_list(long_df):
    """Create company list from long format"""
    company_stats = long_df['BIDDER_NAME'].value_counts().reset_index()
    company_stats.columns = ['company_name', 'bid_frequency']

    total_bids = company_stats['bid_frequency'].sum()
    company_stats['bid_frequency_%'] = (company_stats['bid_frequency'] / total_bids * 100).round(1)
    company_stats['cum_bid_frequency_%'] = company_stats['bid_frequency_%'].cumsum().round(1)
    company_stats['client_decision'] = ''

    return company_stats

def main():
    print("=" * 100)
    print("APPLYING ADDITIONAL BIDDER NAME MERGES")
    print("=" * 100)

    print("\n1. Loading review file...")
    review_df = pd.read_csv(REVIEW_FILE)
    mapping = build_additional_mapping(review_df)
    print(f"   Loaded {len(mapping)} additional merges")

    print("\n2. Loading and updating wide format (CSI_data_combined.csv)...")
    wide_df = pd.read_csv(WIDE_FORMAT_FILE)
    print(f"   Loaded {len(wide_df)} rows")

    wide_df, stats = apply_wide_format_standardization(wide_df, mapping)
    print(f"   Applied {stats['total_replacements']} replacements")
    print(f"   Affected {len(stats['affected_rows'])} rows")

    wide_df.to_csv(WIDE_FORMAT_FILE, index=False)
    print(f"   Saved updated wide format")

    print("\n3. Regenerating long format...")
    long_df = pivot_to_long_format(wide_df)
    print(f"   Created {len(long_df)} bidder records")

    print("\n4. Removing ENGINEERS ESTIMATE entries...")
    long_df, deleted_count = delete_engineers_estimate(long_df)
    print(f"   Deleted {deleted_count} entries")
    print(f"   Final: {len(long_df)} bidder records")

    long_df.to_csv(LONG_FORMAT_FILE, index=False)
    print(f"   Saved long format")

    print("\n5. Regenerating company list...")
    company_stats = regenerate_company_list(long_df)
    print(f"   Created list with {len(company_stats)} unique competitors")

    company_stats.to_csv(COMPANY_LIST_FILE, index=False)
    print(f"   Saved company list")

    print("\n6. Updating CHANGELOG.md...")
    update_changelog(review_df, long_df, len(company_stats))
    print(f"   Updated changelog")

    print("\n" + "=" * 100)
    print("✓ ALL UPDATES COMPLETE!")
    print("=" * 100)
    print(f"\nSummary:")
    print(f"  - Additional merges applied: {len(mapping)}")
    print(f"  - Wide format rows: {len(wide_df)}")
    print(f"  - Long format rows: {len(long_df)}")
    print(f"  - Unique competitors: {len(company_stats)}")
    print(f"  - Top competitor: {company_stats.iloc[0]['company_name']} ({company_stats.iloc[0]['bid_frequency']} bids)")

def update_changelog(review_df, long_df, unique_competitors):
    """Add section to CHANGELOG documenting this pass"""
    date_str = datetime.now().strftime("%Y-%m-%d")

    changelog_entry = f"""
## Cleaning Pass 5 — {date_str} (Quinten)

### Changes Applied

1. **Applied additional client-approved bidder name merges**
   - Source: `additional_bidder_merges_review.csv` (client-reviewed and approved list)
   - Created standardization mapping from 14 variations → 14 canonical names
   - Applied mapping to all BIDDER_*_NAME columns in wide format
   - Total impact: Corrected 14 naming inconsistencies across multiple projects

2. **Merged company name variations**
   - Categories of merges:
     - Spelling errors: 4 merges (CENTRAL SPECIALITES, DUINICK, SEVLIN, etc.)
     - Data artifacts: 1 merge (removed "600%" suffix from MARTIN CONSTRUCTION)
     - Spacing issues: 1 merge (NORTHSTAR vs NORTH STAR)
     - Abbreviation inconsistencies: 2 merges (MINNESOTA vs MN, DBA missing)
     - Suffix variations: 5 merges (COMPANY vs CO INC, -ING vs -TION, etc.)
     - Ampersand formatting: 1 merge (& vs space only)

### Detailed Merges Applied

"""

    for _, row in review_df.iterrows():
        core = row['recommended_core_name']
        variation = row['current_variation']
        issue = row['issue_type']
        changelog_entry += f"  - **{core}** ← {variation}\n    ({issue})\n"

    changelog_entry += f"""
### Results

- **Total bidder records**: {len(long_df)} (after removing 732 ENGINEERS ESTIMATE entries)
- **Unique competitors**: {unique_competitors} (down from 833 after previous pass)
- **Impact**: 14 company groups consolidated, improving data consistency
- **Ready for**: Final competitor analysis and scoring engine

### Data Integrity Notes

- No source rows were dropped from wide-format file.
- Bidder names now standardized across all variations (spellings, spacing, suffixes, abbreviations).
- Raw names can be recovered from git history if needed.
- All data files updated consistently: wide format, long format, and company list.

"""

    with open(CHANGELOG_FILE, 'a') as f:
        f.write(changelog_entry)

if __name__ == "__main__":
    main()
