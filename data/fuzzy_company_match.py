#!/usr/bin/env python3
"""
Fuzzy company name matching for bidder deduplication candidates.

Reads:  data/cleaning_review/bidder_full_company_list.csv
Writes: data/cleaning_review/fuzzy_merge_candidates.csv

Does NOT modify the original dataset.

Steps:
  1. Strip legal entity suffixes (INC, LLC, CORP, CORPORATION, LTD, CO)
  2. Normalize DBA / D/B/A (drop the alias half)
  3. Compare every pair using token_sort_ratio
  4. Flag pairs above --threshold (default 70) for human review
"""

import re
import argparse
import pandas as pd
from itertools import combinations
from rapidfuzz import fuzz

INPUT  = "data/cleaning_review/bidder_full_company_list.csv"
OUTPUT = "data/cleaning_review/fuzzy_merge_candidates.csv"

# Legal entity suffixes — strip from end of string only
LEGAL_SUFFIXES = re.compile(
    r"\b(INCORPORATED|CORPORATION|CORP|INC|LLC|LTD|CO|LP)\b\.?$"
)

# Generic trade/industry words — strip from anywhere in the string.
# These appear in 10+ unrelated company names and inflate similarity scores
# without carrying identity signal.
TRADE_WORDS = re.compile(
    r"\b(CONSTRUCTION|CONTRACTING|CONTRACTORS|BUILDERS|COMPANY|COMPANIES|"
    r"EXCAVATING|EXCAVATION|PAVING|ASPHALT|CONCRETE|ELECTRIC|ELECTRICAL|"
    r"MATERIALS|GRAVEL|ENTERPRISES|SERVICES|UNDERGROUND|GRADING|UTILITIES|"
    r"UTILITY|DRILLING|LANDSCAPING|SITEWORKS|AGGREGATE?)\b"
)

# DBA variants — drop everything from DBA onward
DBA_PATTERN = re.compile(r"\s+(D/?B/?A|DBA)\s+.+$")

# Encoding artifacts (e.g. broken em-dash from Outlook → Â€")
ENCODING_ARTIFACTS = re.compile(r"[^\x00-\x7F]+")

# Noise tokens that add no identity signal
NOISE = re.compile(r"[-/,\.]+")

# Skip comparison if core name is too short after stripping (avoids "R R" matching everything)
MIN_CORE_LENGTH = 4


def normalize(name: str) -> str:
    name = name.upper().strip()
    name = ENCODING_ARTIFACTS.sub(" ", name)    # remove non-ASCII encoding artifacts
    name = DBA_PATTERN.sub("", name)            # drop DBA alias
    name = TRADE_WORDS.sub("", name)            # strip generic trade words (anywhere)
    name = LEGAL_SUFFIXES.sub("", name).strip()
    name = LEGAL_SUFFIXES.sub("", name).strip() # second pass catches residual "INC LLC"
    name = NOISE.sub(" ", name)                 # collapse punctuation to space
    name = re.sub(r"\s+", " ", name).strip()
    return name


def main(threshold: int):
    df = pd.read_csv(INPUT)
    df = df.dropna(subset=["company_name"])

    # Build lookup: company_name → bid_frequency
    bid_freq = df.set_index("company_name")["bid_frequency"].to_dict()

    names = df["company_name"].tolist()

    print(f"Loaded {len(names)} companies from {INPUT}")
    print(f"Running pairwise fuzzy match (token_sort_ratio ≥ {threshold}) …")

    rows = []
    pairs = list(combinations(range(len(names)), 2))
    total = len(pairs)

    for i, (a, b) in enumerate(pairs):
        if i % 50000 == 0 and i > 0:
            print(f"  {i:,} / {total:,} pairs checked …")

        norm_a = normalize(names[a])
        norm_b = normalize(names[b])

        if len(norm_a) < MIN_CORE_LENGTH or len(norm_b) < MIN_CORE_LENGTH:
            continue

        score = fuzz.token_sort_ratio(norm_a, norm_b)
        if score >= threshold:
            rows.append({
                "company_a":          names[a],
                "bids_a":             bid_freq.get(names[a], ""),
                "company_b":          names[b],
                "bids_b":             bid_freq.get(names[b], ""),
                "normalized_a":       norm_a,
                "normalized_b":       norm_b,
                "token_sort_ratio":   score,
                "decision":           "",   # blank for human review: merge / keep_separate
                "canonical_name":     "",   # name to keep if merging
            })

    out = pd.DataFrame(rows).sort_values("token_sort_ratio", ascending=False)
    out["combined_bids"] = out["bids_a"] + out["bids_b"]
    out.to_csv(OUTPUT, index=False)

    print(f"\nDone. {len(out)} candidate pairs written to {OUTPUT}")
    if len(out):
        print(f"  Score range: {out['token_sort_ratio'].min():.1f} – {out['token_sort_ratio'].max():.1f}")
        print(f"\nTop 10 matches:")
        print(out[["company_a", "bids_a", "company_b", "bids_b", "token_sort_ratio"]].head(10).to_string(index=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fuzzy company name deduplication")
    parser.add_argument("--threshold", type=int, default=70,
                        help="Minimum token_sort_ratio to flag a pair (default: 70)")
    args = parser.parse_args()
    main(args.threshold)
