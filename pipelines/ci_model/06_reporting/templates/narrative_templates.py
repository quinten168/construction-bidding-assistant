"""
Rule-based feature → business-language mapping.
Each entry is a callable: (value: float) -> str.
Returns an empty string when the feature has no meaningful narrative for that value.
"""

NARRATIVE_TEMPLATES: dict[str, callable] = {
    # ── Activity ────────────────────────────────────────────────────────────────
    "prior_bid_count": lambda v: (
        f"This competitor has submitted {int(v)} bids historically, indicating "
        f"{'high' if v > 20 else 'moderate' if v > 5 else 'limited'} overall market presence."
    ),
    "prior_bid_rate": lambda v: (
        f"Their historical bid rate is {v:.0%}, making them a "
        f"{'selective' if v < 0.3 else 'moderately active' if v < 0.6 else 'highly active'} bidder."
    ),
    "recent_3m_bid_count": lambda v: (
        f"They submitted {int(v)} bid{'s' if v != 1 else ''} in the past 3 months, indicating "
        f"{'high' if v >= 3 else 'moderate' if v >= 1 else 'low'} recent activity."
    ),
    "recent_6m_bid_count": lambda v: (
        f"Over the past 6 months they have bid {int(v)} time{'s' if v != 1 else ''}."
    ),
    "recent_9m_bid_count": lambda v: (
        f"Over the past 9 months they have submitted {int(v)} bid{'s' if v != 1 else ''}."
    ),
    "recent_12m_bid_count": lambda v: (
        f"In the last 12 months their bid count was {int(v)}."
    ),
    "recent_24m_bid_count": lambda v: (
        f"In the last 24 months their bid count was {int(v)}."
    ),
    "days_since_last_bid": lambda v: (
        f"Their last bid was {int(v)} days ago, suggesting {'recent' if v < 30 else 'moderate' if v < 90 else 'reduced'} activity."
        if v < 9999 else "No prior bid history found for this competitor."
    ),

    # ── Geography ───────────────────────────────────────────────────────────────
    "same_state_prior_bid_count": lambda v: (
        f"They have {int(v)} prior bid{'s' if v != 1 else ''} in this state, giving them regional familiarity."
    ),
    "same_county_prior_bid_count": lambda v: (
        f"With {int(v)} prior bid{'s' if v != 1 else ''} in this county, they have "
        f"{'strong' if v >= 5 else 'some' if v >= 1 else 'no'} local market knowledge."
    ),

    # ── Project type ────────────────────────────────────────────────────────────
    "same_type_prior_bid_count": lambda v: (
        f"They have bid on {int(v)} project{'s' if v != 1 else ''} of this exact type before."
    ),
    "same_primary_project_type": lambda v: (
        "This competitor has prior experience with this exact project type."
        if v == 1 else ""
    ),

    # ── Scope match (one per bid-schedule quantity) ───────────────────────────────
    "mix_tons_match": lambda v: (
        "Their asphalt/paving capability aligns with this project's scope." if v == 1 else ""
    ),
    "grading_yards_match": lambda v: (
        "Their grading capability aligns with this project's scope." if v == 1 else ""
    ),
    "base_tons_match": lambda v: (
        "Their base/aggregate capability aligns with this project's scope." if v == 1 else ""
    ),
    "shldr_tons_match": lambda v: (
        "Their shoulder-aggregate capability aligns with this project's scope." if v == 1 else ""
    ),
    "mill_sy_match": lambda v: (
        "Their milling capability aligns with this project's scope." if v == 1 else ""
    ),
    "crush_tons_match": lambda v: (
        "Their crushing capability aligns with this project's scope." if v == 1 else ""
    ),
    "stock_tons_match": lambda v: (
        "Their stockpile-material capability aligns with this project's scope." if v == 1 else ""
    ),
    "utility_match": lambda v: (
        "Their utility work capability aligns with this project's scope." if v == 1 else ""
    ),
    "structure_match": lambda v: (
        "Their structural capability aligns with this project's scope." if v == 1 else ""
    ),
    "drainage_match": lambda v: (
        "Their drainage capability aligns with this project's scope." if v == 1 else ""
    ),

    # ── Project scope flags (project-level — negative weights narrow the field) ─
    "has_paving": lambda v: (
        "This project includes paving work, which narrows the eligible competitor pool."
        if v == 1 else ""
    ),
    "has_grading": lambda v: (
        "This project includes grading work." if v == 1 else ""
    ),
    "has_base": lambda v: (
        "This project includes base/aggregate work." if v == 1 else ""
    ),
    "has_utility": lambda v: (
        "This project includes utility work, which narrows the eligible competitor pool."
        if v == 1 else ""
    ),
    "has_structure": lambda v: (
        "This project includes structural work, which narrows the eligible competitor pool."
        if v == 1 else ""
    ),
    "has_drainage": lambda v: (
        "This project includes drainage work." if v == 1 else ""
    ),
    "has_reclamation": lambda v: (
        "This project includes reclamation work, which narrows the eligible competitor pool."
        if v == 1 else ""
    ),
    "has_trail": lambda v: (
        "This project includes trail work." if v == 1 else ""
    ),

    # ── Project classification ───────────────────────────────────────────────────
    "is_reconstruction": lambda v: (
        "This is a reconstruction project, which may attract competitors with rehabilitation experience."
        if v == 1 else ""
    ),
    "is_structure_replacement": lambda v: (
        "This is a structure replacement project." if v == 1 else ""
    ),

    # ── Project size (zero-weighted in current model) ────────────────────────────
    "log_mix_tons": lambda v: (
        f"The asphalt tonnage on this project is {'large' if v > 4 else 'moderate' if v > 2 else 'small'}."
        if v > 0 else ""
    ),
    "log_grading_yards": lambda v: (
        f"The grading volume on this project is {'large' if v > 4 else 'moderate' if v > 2 else 'small'}."
        if v > 0 else ""
    ),
    "log_base_tons": lambda v: (
        f"The base tonnage on this project is {'large' if v > 4 else 'moderate' if v > 2 else 'small'}."
        if v > 0 else ""
    ),
    "log_shldr_tons": lambda v: "",
    "log_mill_sy":    lambda v: "",
    "log_crush_tons": lambda v: "",
    "log_stock_tons": lambda v: "",
    "project_size_proxy": lambda v: (
        f"The combined paving and grading scope is {'large' if v > 6 else 'medium' if v > 3 else 'small'} "
        "relative to typical projects." if v > 0 else ""
    ),

    # ── Pit access (zero-weighted in current model; templates ready for future) ──
    "project_location_missing": lambda v: "",
    "project_location_pit_county_centroid": lambda v: "",
    "nearest_open_pit_miles": lambda v: (
        f"The nearest open-access pit is {v:.1f} miles from this project."
        if 0 < v < 9999 else ""
    ),
    "open_pits_within_10mi": lambda v: (
        f"There {'is' if v == 1 else 'are'} {int(v)} open-access pit{'s' if v != 1 else ''} within 10 miles."
        if v > 0 else ""
    ),
    "open_pits_within_25mi": lambda v: (
        f"There {'is' if v == 1 else 'are'} {int(v)} open-access pit{'s' if v != 1 else ''} within 25 miles."
        if v > 0 else ""
    ),
    "open_pits_within_50mi": lambda v: "",
    "best_open_pit_rating_within_25mi": lambda v: "",
    "avg_open_pit_rating_within_25mi": lambda v: "",
    "nearest_unknown_access_pit_miles": lambda v: "",
    "unknown_access_pits_within_25mi": lambda v: "",
    "has_unknown_access_pit_within_25mi": lambda v: "",
    "nearest_accessible_pit_miles": lambda v: (
        f"The nearest accessible pit is {v:.1f} miles away."
        if 0 < v < 9999 else ""
    ),
    "accessible_pits_within_10mi": lambda v: (
        f"There {'is' if v == 1 else 'are'} {int(v)} accessible pit{'s' if v != 1 else ''} within 10 miles."
        if v > 0 else ""
    ),
    "accessible_pits_within_25mi": lambda v: (
        f"There {'is' if v == 1 else 'are'} {int(v)} accessible pit{'s' if v != 1 else ''} within 25 miles."
        if v > 0 else ""
    ),
    "accessible_pits_within_50mi": lambda v: "",
    "best_accessible_pit_rating_within_25mi": lambda v: "",
    "avg_accessible_pit_rating_within_25mi": lambda v: "",
    "nearest_owned_or_restricted_pit_miles": lambda v: "",
    "owned_or_restricted_pits_within_10mi": lambda v: "",
    "owned_or_restricted_pits_within_25mi": lambda v: "",
    "owned_or_restricted_pits_within_50mi": lambda v: "",
    "best_owned_or_restricted_pit_rating_within_25mi": lambda v: "",
    "has_competitor_restricted_pit_within_25mi": lambda v: (
        "This competitor has a restricted pit within 25 miles, giving them a potential material cost advantage."
        if v == 1 else ""
    ),
    "nearest_knife_river_pending_pit_miles": lambda v: "",
    "knife_river_pending_pits_within_25mi": lambda v: "",
    "competitor_pit_distance_advantage_vs_open": lambda v: (
        f"This competitor is {v:.1f} miles closer to the project than the nearest open-access pit."
        if v > 0 else ""
    ),
    "competitor_pit_distance_advantage_vs_market_median": lambda v: (
        f"This competitor sits {v:.1f} miles closer than the median competitor pit proximity."
        if v > 0 else ""
    ),
    "has_clear_pit_advantage": lambda v: (
        "This competitor has a clear pit distance advantage over the open market."
        if v == 1 else ""
    ),
}


def render_template(feature: str, value: float) -> str:
    """Return the business-language sentence for a feature value, or '' if not applicable."""
    fn = NARRATIVE_TEMPLATES.get(feature)
    if fn is None:
        return ""
    try:
        return fn(value)
    except Exception:
        return ""
