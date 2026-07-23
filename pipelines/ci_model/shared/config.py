from __future__ import annotations

from pathlib import Path

DEFAULT_CANDIDATE_RULE = "v3_90d_warmup_targeted_fallback"

# Candidate Pool V3. These values are deliberately centralized so the audit,
# training panel, and future inference path cannot silently use different rules.
V3_RECENT_WINDOW_DAYS = 90
V3_WARMUP_HISTORY_DAYS = 365
V3_WARMUP_RECENT_DAYS = 365
V3_FALLBACK_LOOKBACK_DAYS = 730
V3_RECURRING_REGIONAL_MIN_BIDS = 3
V3_FALLBACK_SCORE_THRESHOLD = 1.5
V3_PRIORITY_WEIGHT = 3.0
V3_HISTORICAL_WINNER_WEIGHT = 2.0
V3_RECURRING_REGIONAL_WEIGHT = 1.5

# Client company IDs — never appear as predicted competitors (the tool is used BY these companies).
# Add more IDs here if the client operates under multiple entities.
# competitor_unit_id is now the competitor_name_registry's comp_name (see
# data/entity_resolution.py apply_registry_mapping) — "CENTRAL SPECIALTIES" is
# where the client's raw bidder-name variants resolve to today. One variant,
# "BRADFORD BAY CENTRAL SPECIALTIES", is still needs_review in the registry
# and isn't merged in here — confirm in the registry before adding it.
CLIENT_UNIT_IDS: frozenset[str] = frozenset({
    "CENTRAL SPECIALTIES",
})

# Tiered competitor set
TIER_COL = "tier"
PRIORITY_TIER = 1   # top competitors — always included, ranking quality is primary
DISCOVERY_TIER = 2  # rule-discovered — surfacing relevant newcomers is primary

_REGISTRY_FILENAME = "competitor_name_registry - name_variants.csv"
COMPETITOR_REGISTRY_PATH = (
    Path(__file__).resolve().parent.parent
    / "01_candidates"
    / "outputs"
    / _REGISTRY_FILENAME
)

TRAIN_END_DATE = "2025-01-01"
VALIDATION_END_DATE = "2025-05-01"

TOP_K_VALUES = [5, 10, 20]

PIT_RANKING_FEATURE_COLUMNS = [
    "pit_applicable",          # 1 = MN project (pit data available), 0 = other state (zeroed out)
    "project_location_missing",
    # Open pits — marginal (non-cumulative) bands
    "nearest_open_pit_miles",
    "open_pits_lt_10mi",
    "open_pits_10_25mi",
    "open_pits_25_50mi",
    "best_open_pit_rating_within_25mi",
    "avg_open_pit_rating_within_25mi",
    # Unknown-access pits
    "nearest_unknown_access_pit_miles",
    "unknown_access_pits_within_25mi",
    # Owned/restricted pits
    "nearest_owned_or_restricted_pit_miles",
    "owned_or_restricted_pits_within_25mi",
    "best_owned_or_restricted_pit_rating_within_25mi",
    "has_competitor_restricted_pit_within_25mi",
    # Competitive advantage — distance vs nearest open pit only
    "competitor_pit_distance_advantage_vs_open",
]

RANKING_FEATURE_COLUMNS = [
    # Activity (kept: overall rate + recency; dropped 6 nested cumulative window counts)
    "prior_bid_rate",
    "mix_ton_capacity_ratio",
    "days_since_last_bid",
    # Geography
    "same_state_prior_bid_count",
    "same_county_prior_bid_count",
    # Project type match
    "same_project_type_bid_count",
    "ever_bid_same_project_type",
    # Scope match (quantity-backed only: mix_tons, grading_yards, base_tons/shldr_tons)
    "paving_match",
    "grading_match",
    "base_match",
    # Project size
    "log_mix_tons",
    "log_grading_yards",
    "log_base_tons",
    "log_shldr_tons",
    "log_mill_sy",
    "log_crush_tons",
    "log_stock_tons",
    "project_size_proxy",
    # Pit geography (project_location_pit_county_centroid dropped: perfect mirror of project_location_missing)
    *PIT_RANKING_FEATURE_COLUMNS,
]

PROJECT_FLAG_COLUMNS = [
    "has_paving",
    "has_grading",
    "has_base",
    "has_utility",
    "has_structure",
    "has_drainage",
    "has_reclamation",
    "has_trail",
]
