"""
Reporter Agent

Assembles the final Bid Intelligence Report from all competitor analyses.
Sections:
  0. Project Introduction  (metadata)
  1. Executive Summary     (LLM-generated or static)
  2. Threat Matrix         (deterministic, no probability %)
  3. Competitor Deep Dives (HIGH/MEDIUM threats; narrative + signals)
  4. Strategic Recommendations (LLM-generated or static)
  5. Appendix              (full probability table — only place with %)
"""
from __future__ import annotations

import math
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

_HERE          = Path(__file__).resolve().parent.parent
_SYSTEM_PROMPT = (_HERE / "prompts" / "system_prompt.txt").read_text().strip()

_THREAT_ICON = {"HIGH": "🔴 HIGH", "MEDIUM": "🟡 MEDIUM", "LOW": "🟢 LOW"}

# Work type: label + plain-English condition description. Keyed on plan_reader's own `archetype`
# vocabulary (apps/api/backend/project_registry.py::_archetype) -- scratch.bid_projects.project_type
# was relabeled to match it (see data/build_project_competitor_panel.py), so a plan's own archetype
# and this historical classification finally share one format instead of three independently-
# maintained ones (the old DB slugs, this display table, and plan_reader's archetype).
# `project_info["project_type"]` (used below) is read from `ranking_predictions.csv` -- a separate,
# static training artifact this relabel does NOT regenerate (that needs a full model retrain,
# out of scope here) -- so it still carries the OLD slug format until that file is next rebuilt.
# Old keys are kept alongside the new ones so this lookup resolves either way in the meantime;
# safe to drop the old keys once `ranking_predictions.csv` is regenerated with the new format.
_WORK_TYPE: dict[str, tuple[str, str]] = {
    "Reconstruct/Rebuild":    ("Reconstruct / Rebuild",      "Regrade the roadbed and pave (grade ≥ 500 CY)"),
    "Mill & Overlay":         ("Mill & Overlay",             "Mill off old asphalt, lay new (grade < 500 CY, mill ≥ 1,000 SY)"),
    "HMA Overlay/Resurface":  ("HMA Overlay / Resurface",    "New asphalt over the surface — no mill, no regrade (grade < 500 CY, mill < 1,000 SY)"),
    "Grading/Earthwork":      ("Grading / Earthwork",        "Move/shape dirt — no real paving (grade ≥ 500 CY)"),
    "Aggregate/Base/Gravel":  ("Aggregate / Base / Gravel",  "Base/shoulder/gravel — no asphalt surface"),
    "Other":                  ("Other",                      "—"),
    # transitional: old ranking_predictions.csv slugs, until that file is regenerated
    "reconstruct_rebuild":    ("Reconstruct / Rebuild",      "Regrade the roadbed and pave (grade ≥ 500 CY)"),
    "mill_overlay":           ("Mill & Overlay",             "Mill off old asphalt, lay new (grade < 500 CY, mill ≥ 1,000 SY)"),
    "hma_resurface":          ("HMA Overlay / Resurface",    "New asphalt over the surface — no mill, no regrade (grade < 500 CY, mill < 1,000 SY)"),
    "grading_earthwork":      ("Grading / Earthwork",        "Move/shape dirt — no real paving (grade ≥ 500 CY)"),
    "aggregate_base_gravel":  ("Aggregate / Base / Gravel",  "Base/shoulder/gravel — no asphalt surface"),
    "other":                  ("Other",                      "—"),
}

_WORK_TYPE_TABLE = (
    "| Work Type | Condition | Rule / cut-offs |\n"
    "|---|---|---|\n"
    "| Reconstruct / Rebuild | Regrade the roadbed and pave | paving and GRADE_CY ≥ 500 |\n"
    "| Mill & Overlay | Mill off old asphalt, lay new (commodity) | paving, GRADE_CY < 500, MILL_SY ≥ 1,000 |\n"
    "| HMA Overlay / Resurface | New asphalt over the surface — no mill, no regrade | paving, GRADE_CY < 500, MILL_SY < 1,000 |\n"
    "| Grading / Earthwork | Move/shape dirt — no real paving | not paving, GRADE_CY ≥ 500 |\n"
    "| Aggregate / Base / Gravel | Base/shoulder/gravel — no asphalt surface | not paving, BASE_TN > 0 or SHLDR_TN > 0 |\n\n"
    "_paving = mix share ≥ 15% of total tonnage, or mix ≥ 1,000 tons regardless of share._"
)

# Brief explanations appended to ✗ (negative-contribution) signal lines
_NO_BID_REASON: dict[str, str] = {
    "recent_3m_bid_count":   "high recent volume suggests constrained capacity",
    "recent_6m_bid_count":   "high recent volume suggests constrained capacity",
    "recent_9m_bid_count":   "high recent volume suggests resource constraints",
    "recent_12m_bid_count":  "high recent volume may indicate resource constraints",
    "recent_24m_bid_count":  "elevated long-term activity reduces marginal bid probability",
    "prior_bid_count":       "high overall bid count may reflect broad but non-specialized activity",
    "prior_bid_rate":        "low historical bid rate signals selective bidding",
    "days_since_last_bid":   "extended inactivity reduces likelihood of re-entry",
    "same_state_prior_bid_count":  "limited in-state experience reduces regional fit",
    "same_county_prior_bid_count": "no prior county presence reduces local market fit",
    "same_type_prior_bid_count":   "limited experience with this project type",
    "same_primary_project_type":   "no match with this exact project type",
    "mix_tons_match":    "asphalt/paving scope mismatch reduces likelihood",
    "grading_yards_match": "grading scope mismatch reduces likelihood",
    "base_tons_match":   "base/aggregate scope mismatch",
    "shldr_tons_match":  "shoulder aggregate scope mismatch",
    "mill_sy_match":     "milling scope mismatch reduces likelihood",
    "crush_tons_match":  "crushing scope mismatch reduces likelihood",
    "stock_tons_match":  "stockpile scope mismatch reduces likelihood",
    "utility_match":   "utility scope mismatch reduces likelihood",
    "structure_match": "structural scope mismatch reduces likelihood",
    "drainage_match":  "drainage scope mismatch reduces likelihood",
    "log_mix_tons":    "project asphalt scope may exceed their typical contract size",
    "project_size_proxy": "project size outside their typical scale",
    "nearest_open_pit_miles": "distant pit access increases material cost risk",
    "open_pits_within_10mi": "limited nearby open-access pit options",
    "open_pits_within_25mi": "limited nearby pit access within 25 miles",
}

# Matches the duplicate header line generated by generate_narrative (no-LLM mode)
_DUPE_HEADER_RE = re.compile(r"^.+—\s+\d+%\s+likelihood\s+\(.+\)", re.IGNORECASE)


def _prob_delta(total_prob: float, contrib: float) -> float:
    """Convert a log-odds contribution to its probability-scale impact (leave-one-out delta)."""
    if total_prob <= 0.0 or total_prob >= 1.0:
        return 0.0
    logit = math.log(total_prob / (1.0 - total_prob))
    logit_without = max(-500.0, min(500.0, logit - contrib))
    p_without = 1.0 / (1.0 + math.exp(-logit_without))
    return total_prob - p_without


def _project_intro(project_info: dict, analyses: list[dict]) -> str:
    project_key = project_info.get("project_natural_key", "—")
    county    = project_info.get("county", "—")
    state     = project_info.get("state", "—")
    proj_type = project_info.get("project_type", "—")
    bid_date  = project_info.get("bid_date", "—")
    lat       = project_info.get("lat")
    lon       = project_info.get("lon")
    coords    = f"{lat:.6f}, {lon:.6f}" if (lat is not None and lon is not None) else "—"

    type_label, _ = _WORK_TYPE.get(
        proj_type,
        (proj_type.replace("_", " ").title(), "—"),
    )

    # Public pit counts are project-level — pull from any analysis row (per-band, not cumulative)
    pit_line = "No public-access pits found within 50 miles of this site."
    if analyses:
        fv = analyses[0].get("feature_values", {})
        b10     = int(fv.get("open_pits_lt_10mi",  0) or 0)
        b25     = int(fv.get("open_pits_10_25mi",  0) or 0)
        b50     = int(fv.get("open_pits_25_50mi",  0) or 0)
        nearest = float(fv.get("nearest_open_pit_miles", 9999) or 9999)
        if b10 + b25 + b50 > 0:
            pit_line = (
                f"{b10} within 10 mi, {b25} within 10–25 mi, {b50} within 25–50 mi"
                + (f" (nearest: {nearest:.1f} mi)" if nearest < 9999 else "")
            )
        elif nearest < 9999:
            pit_line = f"nearest accessible pit: {nearest:.1f} mi"

    # Check if any competitor has a private pit
    any_private = any(
        a.get("feature_values", {}).get("has_competitor_restricted_pit_within_25mi", 0) == 1
        for a in analyses
    )
    private_note = (
        "At least one competitor in this analysis has a private pit within 25 miles — see deep dives."
        if any_private
        else "No competitors in this analysis have a private pit within 25 miles."
    )

    lines = (
        f"**Project:**          {project_key} — {county}, {state}\n"
        f"**Work Type:**        {type_label}\n"
        f"**Location:**         {county}, {state}\n"
        f"**Coordinates:**      {coords}\n"
        f"**Bid Date:**         {bid_date}\n\n"
        f"**Work Type Reference:**\n{_WORK_TYPE_TABLE}\n\n"
        f"**Public-access pits near site:** {pit_line}\n"
        f"**Private pits:**     {private_note}"
    )
    return lines


def _exec_summary_llm(
    project_info: dict,
    analyses: list[dict],
    client,
    llm_model: str,
) -> str:
    high   = [a for a in analyses if a["threat_level"] == "HIGH"]
    medium = [a for a in analyses if a["threat_level"] == "MEDIUM"]
    low    = [a for a in analyses if a["threat_level"] == "LOW"]

    top3_names = [
        a["display_name"]
        for a in sorted(analyses, key=lambda x: x["bid_probability"], reverse=True)[:3]
    ]

    prompt = (
        f"Project: {project_info.get('project_natural_key')} | "
        f"{project_info.get('county', '')} County, {project_info.get('state', '')} | "
        f"{project_info.get('project_type', '')}\n"
        f"Competitors analyzed: {len(analyses)}\n"
        f"HIGH threats: {len(high)}, MEDIUM: {len(medium)}, LOW: {len(low)}\n"
        f"Top 3 competitors (by model score): {', '.join(top3_names)}\n\n"
        "Write a 4–5 sentence executive summary for the client's decision-maker. Include:\n"
        "1. One sentence on project context (type and location).\n"
        "2. One sentence assessing overall competition level with brief rationale.\n"
        "3. Name the top 3 competitors and each one's primary risk signal "
        "(do NOT include probability percentages).\n"
        "4. One-line recommended posture (e.g. 'Price competitively; confirm utility scope coverage').\n"
        "Use plain business language only. Do not include percentage figures."
    )

    response = client.messages.create(
        model=llm_model,
        max_tokens=400,
        temperature=0.5,
        system=_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text.strip()


def _exec_summary_static(project_info: dict, analyses: list[dict]) -> str:
    county = project_info.get("county", "—")
    state  = project_info.get("state", "—")
    proj_type = project_info.get("project_type", "—")
    type_label, _ = _WORK_TYPE.get(proj_type, (proj_type.replace("_", " ").title(), ""))

    ranked = sorted(analyses, key=lambda x: x["bid_probability"], reverse=True)

    lines = []

    # Competitors with strong county win rate
    strong_county = [
        a for a in ranked
        if a.get("feature_values", {}).get("same_county_prior_bid_count", 0) >= 5
    ]
    if strong_county:
        names = ", ".join(a["display_name"] for a in strong_county[:3])
        lines.append(f"Strong county presence: {names}.")

    # Any competitor with private pit advantage
    pit_advantage = [
        a for a in ranked
        if a.get("feature_values", {}).get("has_competitor_restricted_pit_within_25mi", 0) == 1
    ]
    if pit_advantage:
        names = ", ".join(a["display_name"] for a in pit_advantage[:2])
        lines.append(f"Private pit advantage within 25 miles: {names}.")

    # Competition breadth
    high_prob = [a for a in ranked if a["bid_probability"] >= 0.70]
    if len(high_prob) >= 5:
        lines.append(f"{len(high_prob)} competitors with ≥70% bid likelihood — expect a competitive field.")
    elif len(high_prob) >= 2:
        lines.append(f"{len(high_prob)} competitors with ≥70% bid likelihood.")

    return "\n".join(lines) if lines else f"{type_label} project in {county}, {state}."


def _recommendations_llm(
    project_info: dict,
    analyses: list[dict],
    client,
    llm_model: str,
) -> str:
    high_names = [a["display_name"] for a in analyses if a["threat_level"] == "HIGH"]
    summary = (
        f"Project: {project_info.get('project_natural_key')} | "
        f"{project_info.get('county', '')} County, {project_info.get('state', '')} | "
        f"{project_info.get('project_type', '')}\n"
        f"High-threat competitors: {', '.join(high_names) if high_names else 'None'}\n"
        "Provide 2–3 concise strategic recommendations for the client's bid strategy. "
        "Focus on pricing positioning and competitive response. "
        "Use plain business language."
    )
    response = client.messages.create(
        model=llm_model,
        max_tokens=300,
        temperature=0.5,
        system=_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": summary}],
    )
    return response.content[0].text.strip()


def _recommendations_static(analyses: list[dict]) -> str:
    top3 = sorted(analyses, key=lambda x: x["bid_probability"], reverse=True)[:3]
    if not top3:
        return "No competitors identified. The client may have pricing flexibility on this project."
    return (
        f"Watch closely: {', '.join(a['display_name'] for a in top3)} "
        "are the most likely bidders. Price competitively and confirm scope alignment."
    )


def _format_contributions(top_bid: list, top_no_bid: list, probability: float) -> str:
    lines = []
    for feat, contrib in top_bid:
        delta = _prob_delta(probability, contrib)
        sign = "+" if delta >= 0 else ""
        lines.append(f"  ✓ {feat:<40} ({sign}{delta:.0%})")
    for feat, contrib in top_no_bid:
        delta = _prob_delta(probability, contrib)
        sign = "+" if delta >= 0 else ""
        reason = _NO_BID_REASON.get(feat, "signal reduces bid likelihood")
        lines.append(f"  ✗ {feat:<40} ({sign}{delta:.0%})  ({reason})")
    return "\n".join(lines)


def _strip_dupe_header(narrative: str) -> str:
    """Remove the first line if it repeats the H3 heading (no-LLM narrative mode)."""
    first, _, rest = narrative.partition("\n")
    if _DUPE_HEADER_RE.match(first.strip()):
        return rest.lstrip("\n")
    return narrative


def build_report(
    project_info: dict,
    analyses: list[dict],
    model_meta: dict | None = None,
    client=None,
    llm_model: str = "claude-sonnet-4-6",
) -> str:
    """
    Assemble the full Bid Intelligence Report as a markdown string.

    Args:
        project_info: {project_natural_key, state, county,
                       project_type, bid_date, lat (optional), lon (optional),
                       materials (optional)}
        analyses:     list of dicts from executor + reflector
        model_meta:   loaded model JSON (for appendix metadata)
        client:       anthropic.Anthropic client (None → static summaries)
        llm_model:    Claude model ID

    Returns:
        Full report as a string.
    """
    now         = datetime.now().strftime("%Y-%m-%d %H:%M")
    project_key = project_info.get("project_natural_key", "—")
    state    = project_info.get("state", "—")
    county   = project_info.get("county", "—")
    bid_date = project_info.get("bid_date", "—")

    sections: list[str] = []

    # ── Header ────────────────────────────────────────────────────────────────
    sections.append(
        f"# Bid Intelligence Report\n"
        f"Project: {project_key} | {county}, {state}\n"
        f"Bid Date: {bid_date} | Generated: {now}"
    )

    # ── Project Introduction ──────────────────────────────────────────────────
    sections.append("## PROJECT INTRODUCTION\n\n" + _project_intro(project_info, analyses))

    # ── Competitor List ───────────────────────────────────────────────────────
    # A single flat ranking by bid_probability (== planner.py's simple_rule_score order) --
    # no priority/discovery split. That tier field never drove this ordering (planner.py's plan()
    # sorts purely by score); it only drove this display grouping, so removing the grouping changes
    # nothing about which competitors are here or in what order.
    sorted_analyses = sorted(analyses, key=lambda x: x["bid_probability"], reverse=True)

    matrix_rows = []
    for a in sorted_analyses:
        flag = " ⚠ needs review" if a.get("reflection_passed") is False else ""
        matrix_rows.append(f"  {a['display_name']}{flag}")

    sections.append("## COMPETITOR LIST\n\n" + "\n".join(matrix_rows))

    # ── Competitor Deep Dives ─────────────────────────────────────────────────
    # Every analyzed competitor gets a full deep dive -- with the list already capped to top_n by
    # the planner, gating further by threat_level (as the old tiered version did) would just hide
    # some of the 5 the reader asked to see in detail.
    blocks = []
    for a in sorted_analyses:
        narrative = _strip_dupe_header(a["narrative"])
        flag = "\n  ⚠ Flagged for human review." if a.get("reflection_passed") is False else ""
        blocks.append(f"### {a['display_name']}\n{narrative}{flag}")

    if blocks:
        sections.append("## COMPETITOR DEEP DIVES\n\n" + "\n\n".join(blocks))

    return "\n\n".join(sections) + "\n"
