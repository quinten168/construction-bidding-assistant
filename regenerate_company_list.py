#!/usr/bin/env python3
"""
Regenerate bidder_full_company_list.csv with updated company names and bid frequencies
after standardization merges have been applied.
"""

import pandas as pd

# File paths
LONG_FORMAT_FILE = "data/processed/CSI_data_long_format.csv"
OUTPUT_FILE = "data/cleaning_review/bidder_full_company_list.csv"

def main():
    print("=" * 80)
    print("Regenerating Bidder Full Company List")
    print("=" * 80)

    print("\n1. Loading CSI_data_long_format.csv...")
    df = pd.read_csv(LONG_FORMAT_FILE)
    print(f"   Loaded {len(df)} bidder records")

    print("\n2. Computing bid frequency by standardized company name...")
    company_stats = df['BIDDER_NAME'].value_counts().reset_index()
    company_stats.columns = ['company_name', 'bid_frequency']

    print("\n3. Calculating percentages and cumulative percentages...")
    total_bids = company_stats['bid_frequency'].sum()
    company_stats['bid_frequency_%'] = (company_stats['bid_frequency'] / total_bids * 100).round(1)
    company_stats['cum_bid_frequency_%'] = company_stats['bid_frequency_%'].cumsum().round(1)

    print("\n4. Adding client_decision column (empty for future use)...")
    company_stats['client_decision'] = ''

    print("\n5. Saving to file...")
    company_stats.to_csv(OUTPUT_FILE, index=False)
    print(f"   Saved to {OUTPUT_FILE}")

    print("\n" + "=" * 80)
    print("Summary Statistics:")
    print("=" * 80)
    print(f"Total unique competitors: {len(company_stats)}")
    print(f"Total bidder records: {total_bids}")
    print(f"\nTop 10 competitors by bid frequency:")
    print(company_stats.head(10).to_string(index=False))

    print("\n" + "=" * 80)
    print("✓ Bidder list regeneration complete!")
    print("=" * 80)

if __name__ == "__main__":
    main()
