"""
Tool 3 — generate_narrative

Two-layer approach:
  Layer A — Rule-based: synthesize cross-feature bullet points.
  Layer B — LLM polish: call Claude to turn bullet points into a fluent 2–3 sentence narrative.
             Skipped gracefully when no Anthropic client is provided.
"""
from __future__ import annotations

from pathlib import Path

_HERE = Path(__file__).resolve().parent.parent
_SYSTEM_PROMPT = (_HERE / "prompts" / "system_prompt.txt").read_text().strip()
_POLISH_PROMPT = (_HERE / "prompts" / "polish_prompt.txt").read_text()

_SCOPE_LABELS: dict[str, str] = {
    "paving_match":    "paving",
    "grading_match":   "grading",
    "base_match":      "base",
    "utility_match":   "utility",
    "structure_match": "structural",
    "drainage_match":  "drainage",
}


def _synthesize_bullets(
    feature_values: dict[str, float],
    win_stats: dict | None = None,
) -> str:
    """
    Build cross-feature synthesized bullet points.
    Groups related features into compound, insight-driven sentences
    rather than one sentence per feature.
    """
    bullets: list[str] = []

    # ── 2. Bid Rate (always shown) ────────────────────────────────────────────
    bid_rate = float(feature_values.get("prior_bid_rate", 0) or 0)
    if bid_rate > 0:
        if bid_rate < 0.15:
            rate_label = "highly selective (bids on fewer than 1 in 7 available projects — very targeted, does not pursue most opportunities)"
        elif bid_rate < 0.35:
            rate_label = "selective (bids on fewer than 1 in 3 available projects — does not chase every contract; focuses on preferred jobs)"
        elif bid_rate < 0.60:
            rate_label = "moderately active (bids on roughly 1 in 3 to 1 in 2 projects — regular market participant)"
        else:
            rate_label = "highly active (bids on more than half of available projects — broad market presence)"
        bullets.append(f"**Bid Rate (all locations, all types):** {bid_rate:.0%} historically — {rate_label}.")
    else:
        bullets.append("**Bid Rate (all locations, all types):** No historical bid rate data for this competitor.")

    # ── 3. Recency (always shown) ─────────────────────────────────────────────
    days_idle = float(feature_values.get("days_since_last_bid", 9999) or 9999)
    if days_idle < 9999:
        if days_idle < 30:
            recency = "actively bidding (last bid within 30 days)"
        elif days_idle < 90:
            recency = f"recently active (last bid {int(days_idle)} days ago)"
        elif days_idle < 365:
            recency = f"moderate recent activity (last bid {int(days_idle)} days ago)"
        else:
            recency = f"reduced activity — last bid was {int(days_idle)} days ago"
        bullets.append(f"**Recency:** {recency}.")
    else:
        bullets.append("**Recency:** No prior bid activity found in CSI data.")

    # ── 4. Capacity — season-based project wins + tons (all project types) ───
    if True:
        season_wins     = (win_stats or {}).get("season_wins")
        season_tons     = (win_stats or {}).get("season_tons")
        season_label    = (win_stats or {}).get("season_label", "current season")
        historical_avg  = (win_stats or {}).get("historical_avg_wins")
        historical_tons = (win_stats or {}).get("historical_avg_tons")
        historical_n    = (win_stats or {}).get("historical_seasons", 0)
        this_proj_tons  = float((win_stats or {}).get("mix_tons", 0) or 0)

        def _fmt_tons(t):
            return f"{t:,.0f} tons" if t and t > 0 else "—"

        if season_wins is None or historical_n == 0:
            bullets.append(
                "**Capacity (all project types):** Historical season baseline not available — "
                "insufficient prior bidding seasons on record."
            )
        else:
            sw_str      = f"{season_wins} project{'s' if season_wins != 1 else ''}"
            avg_win_str = f"{historical_avg:.1f}" if historical_avg is not None else "—"
            season_ton_str  = _fmt_tons(season_tons)
            avg_ton_str     = _fmt_tons(historical_tons)
            proj_ton_str    = _fmt_tons(this_proj_tons)

            if historical_avg and historical_avg > 0:
                pct = season_wins / historical_avg
                if pct < 0.40:
                    pace = "early in their typical season pace"
                elif pct < 0.80:
                    pace = "approaching their typical season pace"
                elif pct <= 1.20:
                    pace = "at or near their typical season pace"
                else:
                    pace = "above their typical season pace — capacity may be constrained"
                bullets.append(
                    f"**Capacity ({season_label}, all project types):** "
                    f"This project: {proj_ton_str}. "
                    f"Won {sw_str} ({season_ton_str}) so far this season — "
                    f"{pct:.0%} of typical pace ({avg_win_str} wins / {avg_ton_str} per season historically), {pace}."
                )
            else:
                bullets.append(
                    f"**Capacity ({season_label}, all project types):** "
                    f"This project: {proj_ton_str}. "
                    f"Won {sw_str} ({season_ton_str}) so far this season — "
                    f"no prior season baseline to compare."
                )

    # ── 5. Pit advantage (always shown for paving; shown only if private pit exists) ──
    has_private = int(feature_values.get("has_competitor_restricted_pit_within_25mi", 0) or 0)
    nearest_pvt = float(feature_values.get("nearest_owned_or_restricted_pit_miles", 9999) or 9999)
    pit_adv     = float(feature_values.get("competitor_pit_distance_advantage_vs_open", 0) or 0)
    has_clear   = int(feature_values.get("has_clear_pit_advantage", 0) or 0)
    if has_private:
        pvt_dist = f"{nearest_pvt:.1f} mi" if nearest_pvt < 9999 else "within 25 mi"
        adv_str  = f" — {pit_adv:.1f} mi closer than nearest public pit" if pit_adv > 0 else ""
        clear    = " (clear cost advantage)" if has_clear else ""
        bullets.append(
            f"**Pit Advantage:** Owns a private pit {pvt_dist} from this job site{adv_str}{clear}."
        )

    # ── 6. Experience (always shown) ──────────────────────────────────────────
    type_bids   = int(feature_values.get("same_project_type_bid_count",   0) or 0)
    if type_bids >= 3:
        bullets.append(f"**Experience:** {type_bids} prior bids on this exact project type.")
    elif type_bids > 0:
        bullets.append(f"**Experience:** {type_bids} prior bid{'s' if type_bids != 1 else ''} on this exact project type.")
    else:
        bullets.append(
            "**Experience:** No prior bids on this project type found in CSI data."
        )

    # ── 7. Win rates (always shown) ───────────────────────────────────────────
    if win_stats:
        county_name  = win_stats.get("county", "this county")
        county_b     = win_stats.get("county_bids", 0)
        county_w     = win_stats.get("county_wins", 0)
        type_b       = win_stats.get("type_bids",   0)
        type_w       = win_stats.get("type_wins",   0)
        proj_type    = win_stats.get("project_type", "")

        # Human-readable project type label
        _TYPE_LABELS = {
            "reconstruct_rebuild":   "Reconstruct/Rebuild",
            "mill_overlay":          "Mill & Overlay",
            "hma_resurface":         "HMA Resurface",
            "grading_earthwork":     "Grading/Earthwork",
            "aggregate_base_gravel": "Aggregate/Base",
            "other":                 "Other",
        }
        type_label = _TYPE_LABELS.get(proj_type, proj_type.replace("_", " ").title() if proj_type else "this project type")

        if type_b >= 3:
            wr = type_w / type_b
            bullets.append(
                f"**Win Rate — {type_label}, all locations:** {wr:.0%} "
                f"({type_w} win{'s' if type_w != 1 else ''} from {type_b} {type_label} bids)."
            )
        else:
            bullets.append(
                f"**Win Rate — {type_label}, all locations:** "
                f"Fewer than 3 {type_label} bids on record — insufficient data."
            )

        if county_b >= 3:
            wr = county_w / county_b
            bullets.append(
                f"**Win Rate — {county_name} (all types):** {wr:.0%} "
                f"({county_w} win{'s' if county_w != 1 else ''} from {county_b} bids in this county)."
            )
        else:
            bullets.append(
                f"**Win Rate — {county_name} (all types):** "
                f"Fewer than 3 bids in this county — insufficient data."
            )

    return "\n".join(f"- {b}" for b in bullets) if bullets else "- No significant signals found."


def generate_narrative(
    contributions: dict[str, float],
    feature_values: dict[str, float],
    competitor_name: str,
    probability: float,
    threat_level: str,
    win_stats: dict | None = None,
    client=None,
    model: str = "claude-sonnet-4-6",
    temperature: float = 0.3,
) -> str:
    """
    Generate a 2–3 sentence business narrative for one competitor.

    Args:
        contributions:   feature → log-odds contribution (from predict_and_explain)
        feature_values:  feature → raw value
        competitor_name: display name (e.g. "Duininck Inc")
        probability:     bid probability (0–1)
        threat_level:    "HIGH" | "MEDIUM" | "LOW"
        win_stats:       optional dict with county/state/type win counts from runtime aggregation
        client:          anthropic.Anthropic client (None → Layer A only)
        model:           Claude model ID
        temperature:     LLM temperature for Layer B

    Returns:
        Polished narrative string.
    """
    bullet_text = _synthesize_bullets(feature_values, win_stats)

    if client is None:
        return (
            f"{competitor_name} — {probability:.0%} likelihood ({threat_level})\n"
            + bullet_text
        )

    # Layer B — LLM polish
    user_msg = _POLISH_PROMPT.format(
        competitor_name=competitor_name,
        probability=probability,
        threat_level=threat_level,
        bullet_points=bullet_text,
    )

    response = client.messages.create(
        model=model,
        max_tokens=256,
        temperature=temperature,
        system=_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_msg}],
    )
    return response.content[0].text.strip()
