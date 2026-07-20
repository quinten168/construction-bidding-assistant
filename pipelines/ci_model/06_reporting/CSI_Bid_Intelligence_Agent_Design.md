# CSI Bid Intelligence Agent — Architecture & Pipeline Design

> Adapted for CSI Competitor Bid Prediction System | Model: Logistic Regression | Last updated: 2026-06-21

---

## 1. Goal Hierarchy

| Level | Definition | CSI Application |
|---|---|---|
| **Mission** | Open-ended, evolving pursuit | Help CSI understand the competitive landscape before every bid, enabling smarter pricing and go/no-go decisions |
| **Objectives** | Scoped, measurable milestones | (1) Predict which competitors will bid on a given project, (2) Explain *why* in business language, (3) Generate a readable report for CSI decision-makers |
| **Tasks** | Atomic, tool-bound, executable steps | Run LR prediction → Calculate feature contributions → Translate to narrative → Assemble report → Export PDF/Word |

---

## 2. Agent Pattern Choice

### Pattern: Sequential Pipeline + Planner–Executor–Reflector (PER)

```
INPUT: New project data + competitor list + feature matrix
        ↓
┌─────────────────────────────────┐
│         PLANNER AGENT           │
│  - ALL Tier 1 competitors       │
│    (priority registry, no cap)  │
│  - Top N Tier 2 (discovery)     │
│  - Returns:                     │
│    {"tier1": [...],             │
│     "discovery": [...]}         │
└─────────────────────────────────┘
        ↓
┌─────────────────────────────────┐
│    EXECUTOR AGENT (ReAct Loop)  │
│                                 │
│  For each competitor:           │
│  Thought → Action → Observe     │
│                                 │
│  T: "Analyze Competitor A"      │
│  A: predict_and_explain()       │
│  O: probability + contributions │
│  T: "Translate to narrative"    │
│  A: generate_narrative()        │
│  O: narrative draft             │
│  → repeat for all competitors   │
└─────────────────────────────────┘
        ↓
┌─────────────────────────────────┐
│        REFLECTOR AGENT          │
│  - Check each narrative         │
│  - Validate logic consistency   │
│  - Flag or revise if needed     │
└─────────────────────────────────┘
        ↓
┌─────────────────────────────────┐
│         REPORTER AGENT          │
│  - Assemble Executive Summary   │
│  - Build Tier-Split Threat      │
│    Matrix:                      │
│    · Active / Watch  (≥ 0.40)   │
│    · Low Activity    (< 0.40)   │
│    · DISCOVERY — New Threats    │
│  - Export PDF / Word            │
└─────────────────────────────────┘
        ↓
OUTPUT: Bid Intelligence Report
```

**Why this pattern:**
- Task is multi-step but well-defined → Sequential Pipeline is simple, traceable, fail-fast
- Each competitor analysis has uncertainty → ReAct for Executor (grounded in live feature data)
- Report quality matters for client → Reflector adds self-critique before delivery

---

## 3. Reasoning Strategy: ReAct (Reason + Act)

Each competitor analysis follows a Thought → Action → Observation loop:

```
Thought:  "Competitor A has high same_county_prior_bid_count — need to check profile"
Action:   get_competitor_profile("Competitor_A")
Observe:  "8 bids in Hennepin County, 4 bids in last 3 months, active"

Thought:  "paving_match = 1 is a strong positive signal"
Action:   predict_and_explain("Competitor_A", project_id)
Observe:  probability=0.82, top contributions: county(+2.14), paving(+1.87), recency(+1.23)

Thought:  "Translate to business narrative"
Action:   generate_narrative(contributions, feature_values)
Observe:  Draft narrative generated → pass to Reflector
```

---

## 4. The Five Tools

### Tool 1 — `predict_and_explain(competitor_id, project_id)`

Runs LR prediction and computes per-feature contributions using coefficient × feature value.

```python
def predict_and_explain(competitor_id, project_id):
    X_row = get_feature_vector(competitor_id, project_id)
    prob = model.predict_proba(X_row)[0][1]

    contributions = {
        feature: model.coef_[0][i] * X_row[i]
        for i, feature in enumerate(feature_names)
    }

    top_reasons_to_bid = sorted(
        contributions.items(), key=lambda x: x[1], reverse=True
    )[:3]

    top_reasons_not_to_bid = sorted(
        contributions.items(), key=lambda x: x[1]
    )[:3]

    return {
        "competitor_id": competitor_id,
        "bid_probability": round(prob, 3),
        "top_reasons_to_bid": top_reasons_to_bid,
        "top_reasons_not_to_bid": top_reasons_not_to_bid,
        "raw_contributions": contributions
    }
```

**Key principle:** No SHAP needed. LR coefficients are inherently interpretable.
`contribution = coefficient × feature_value` → larger value = stronger push toward bidding.

**Example output:**
```json
{
  "competitor_id": "CENTRAL_SPECIALTIES",
  "bid_probability": 0.82,
  "top_reasons_to_bid": [
    ["same_county_prior_bid_count", 2.14],
    ["paving_match", 1.87],
    ["recent_3m_bid_count", 1.23]
  ],
  "top_reasons_not_to_bid": [
    ["days_since_last_bid", -0.94]
  ]
}
```

---

### Tool 2 — `get_competitor_profile(competitor_id)`

Returns historical summary for business context in the narrative.

```python
def get_competitor_profile(competitor_id):
    return {
        "total_bids": prior_bid_count,
        "overall_bid_rate": prior_bid_rate,
        "days_since_last_bid": days_since_last_bid,
        "recent_12m_activity": recent_12m_bid_count,
        "primary_scopes": [...],   # inferred from history
        "active_states": [...]
    }
```

---

### Tool 3 — `generate_narrative(contributions, competitor_profile, feature_values)`

Two-layer approach:

**Layer A — Rule-based template mapping (deterministic):**

```python
NARRATIVE_TEMPLATES = {
    # Activity features
    "prior_bid_count":
        "This competitor has submitted {value} bids historically, indicating {'high' if value > 20 else 'moderate' if value > 5 else 'limited'} overall market presence.",
    "prior_bid_rate":
        "Their historical bid rate is {value:.0%}, making them a {'selective' if value < 0.3 else 'moderately active' if value < 0.6 else 'highly active'} bidder.",
    "recent_3m_bid_count":
        "They submitted {value} bids in the past 3 months, indicating {'high' if value >= 3 else 'moderate' if value >= 1 else 'low'} recent activity.",
    "recent_6m_bid_count":
        "Over the past 6 months, they have bid {value} times.",
    "recent_12m_bid_count":
        "In the last 12 months, their bid count was {value}.",
    "days_since_last_bid":
        "{'Their last bid was {value} days ago, suggesting reduced recent activity.' if value < 9999 else 'No prior bid history found for this competitor.'}",

    # Geography features
    "same_state_prior_bid_count":
        "They have {value} prior bids in this state, giving them regional familiarity.",
    "same_county_prior_bid_count":
        "With {value} prior bids in this county, they have strong local market knowledge.",

    # Project type features
    "same_type_prior_bid_count":
        "They have bid on {value} projects of this exact type before.",
    "same_family_prior_bid_count":
        "They have experience with {value} projects in the same project family.",
    "same_primary_project_type":
        "{'This competitor has prior experience with this exact project type.' if value == 1 else 'This competitor has no prior experience with this project type.'}",

    # Scope match features
    "paving_match":
        "{'Their paving capability aligns with this project scope.' if value == 1 else ''}",
    "grading_match":
        "{'Their grading capability aligns with this project scope.' if value == 1 else ''}",
    "base_match":
        "{'Their base/aggregate capability aligns with this project scope.' if value == 1 else ''}",
    "utility_match":
        "{'Their utility work capability aligns with this project scope.' if value == 1 else ''}",
    "structure_match":
        "{'Their structure capability aligns with this project scope.' if value == 1 else ''}",
    "drainage_match":
        "{'Their drainage capability aligns with this project scope.' if value == 1 else ''}",

    # Project size features
    "log_mix_tons":
        "The asphalt tonnage on this project {'falls within their typical range.' if value > 2 else 'is smaller than their typical projects.'}",
    "project_size_proxy":
        "The combined paving and grading scope is {'large' if value > 6 else 'medium' if value > 3 else 'small'} relative to typical projects.",
}
```

**Layer B — LLM polish (for fluency):**

```python
POLISH_PROMPT = """
You are a bid intelligence analyst writing for a non-technical audience.

Competitor: {competitor_id}
Bid Probability: {probability:.0%}
Key signals (bullet points): {bullet_points}

Write 2-3 sentences explaining why this competitor is likely/unlikely to bid.
Rules:
- Use plain business language only. No ML or statistics terms.
- Ground every claim in the signals provided. Do not add information.
- Be direct and specific.
"""
```

---

### Tool 4 — `generate_report_section(section_type, data)`

Modular section generators — each can be tested and iterated independently.

```python
SECTIONS = {
    "executive_summary":      generate_exec_summary,
    "threat_matrix":          generate_threat_matrix,
    "competitor_deep_dive":   generate_deep_dive,
    "strategic_recommendations": generate_recommendations,
    "appendix":               generate_appendix
}

def generate_report_section(section_type, data):
    return SECTIONS[section_type](data)
```

**Threat classification:**
```python
def classify_threat(probability):
    if probability >= 0.70:
        return "HIGH"
    elif probability >= 0.40:
        return "MEDIUM"
    else:
        return "LOW"
```

---

### Tool 5 — `export_report(sections, format)`

```python
def export_report(sections, format="pdf"):
    if format == "pdf":
        return render_pdf(sections)
    elif format == "docx":
        return render_docx(sections)
```

---

### Agent–Tool Mapping

Which agent is allowed to call which tool:

| Tool | Planner | Executor | Reflector | Reporter |
|---|:---:|:---:|:---:|:---:|
| `predict_and_explain()` | | ✓ | | |
| `get_competitor_profile()` | | ✓ | | |
| `generate_narrative()` | | ✓ | | |
| `generate_report_section()` | | | | ✓ |
| `export_report()` | | | | ✓ |

**Notes:**
- **Planner** calls no tools directly — it reads the incoming project data and competitor list to initialize the session plan.
- **Executor** owns the ReAct loop per competitor: calls `get_competitor_profile()` for context, `predict_and_explain()` for probability + contributions, then `generate_narrative()` to produce a draft.
- **Reflector** calls no tools — it receives the Executor's narrative output and runs a self-critique prompt against it, returning a revised narrative if any check fails.
- **Reporter** takes all validated narratives and calls `generate_report_section()` for each section, then `export_report()` for the final PDF/Word output.

This matches the **Limit tool exposure** principle (Section 11): each agent has access only to the tools it needs.

---

## 5. Production Prompt Design

```
┌─────────────────────────────────────────────────────────────┐
│ LAYER 1: Role & Identity (Static — never changes at runtime) │
├─────────────────────────────────────────────────────────────┤
│ "You are a bid intelligence analyst for CSI, a highway      │
│ construction company. Your job is to analyze competitor      │
│ bid behavior and explain predictions in clear business       │
│ language. Never use ML or statistics jargon."               │
└─────────────────────────────────────────────────────────────┘
┌─────────────────────────────────────────────────────────────┐
│ LAYER 2: Task Instructions + Output Format (Behavioral)     │
├─────────────────────────────────────────────────────────────┤
│ "For each competitor:                                        │
│   Step 1: Review their feature contribution values          │
│   Step 2: Identify top 3 reasons to bid / not to bid        │
│   Step 3: Write a 2-3 sentence business narrative           │
│   Step 4: Assign threat level (HIGH / MEDIUM / LOW)         │
│                                                             │
│  Output JSON: {competitor_id, probability, threat_level,    │
│  narrative, top_signals}"                                   │
└─────────────────────────────────────────────────────────────┘
┌─────────────────────────────────────────────────────────────┐
│ LAYER 3: Constraints & Guardrails + Tools (Safety)          │
├─────────────────────────────────────────────────────────────┤
│ - Never fabricate historical data                           │
│ - If confidence < 0.40, flag as LOW and note uncertainty    │
│ - Always ground explanation in actual feature values        │
│ - If days_since_last_bid = 9999, state no history found     │
│                                                             │
│ Tools: predict_and_explain() | get_competitor_profile()     │
│        generate_narrative()  | export_report()              │
└─────────────────────────────────────────────────────────────┘
┌─────────────────────────────────────────────────────────────┐
│ LAYER 4: Retrieved Context (Dynamic — injected per query)   │
├─────────────────────────────────────────────────────────────┤
│ Project info: {project_id, location, type, scope flags}     │
│ LR model coefficients: {feature: coefficient}               │
│ Feature values for this competitor × project: {matrix}      │
└─────────────────────────────────────────────────────────────┘
┌─────────────────────────────────────────────────────────────┐
│ LAYER 5: Few-Shot Examples (Calibration)                    │
├─────────────────────────────────────────────────────────────┤
│ Input:  same_county_prior_bid_count=8, paving_match=1,      │
│         recent_3m_bid_count=4, probability=0.82             │
│ Output: "Central Specialties has a strong presence in this  │
│         county with 8 prior bids. Their paving capability   │
│         aligns with this project's scope, and recent high   │
│         activity suggests active pursuit. Threat: HIGH"     │
└─────────────────────────────────────────────────────────────┘
┌─────────────────────────────────────────────────────────────┐
│ LAYER 6: Conversation History (Short-term memory)           │
├─────────────────────────────────────────────────────────────┤
│ Prior competitor analyses from this session                 │
│ (truncate oldest if approaching token limit)                │
└─────────────────────────────────────────────────────────────┘
┌─────────────────────────────────────────────────────────────┐
│ LAYER 7: User Input (Trigger — the only part user controls) │
├─────────────────────────────────────────────────────────────┤
│ Project: {project_info}                                     │
│ Competitors to analyze: {competitor_list}                   │
│ Feature matrix: {feature_matrix}                            │
└─────────────────────────────────────────────────────────────┘
```

---

## 6. Reflector Agent — Quality Checkpoint

Self-critique prompt runs after every narrative is generated:

```python
REFLECTION_PROMPT = """
Review this competitor analysis narrative:
"{narrative}"

Check all of the following:
1. Is the threat level ({threat_level}) consistent with the probability ({probability:.0%})?
2. Are all claims grounded in actual feature values? No invented data?
3. Is the language clear for a non-technical business reader?
4. Are there any logical contradictions?
5. Is every scope match claim (paving/grading/base etc.) supported by feature values?

If any check fails, rewrite the narrative.
Output JSON only:
{{
  "passed": true or false,
  "issues_found": ["..."],
  "revised_narrative": "..."
}}
"""
```

---

## 7. Failure Modes & Guardrails

| Failure Mode | Risk in CSI Agent | Guardrail |
|---|---|---|
| **Hallucination** | LLM invents competitor history | All narratives must be grounded in actual feature values. LLM only polishes language, never generates facts. |
| **Cascade Failure** | Bad prediction → bad narrative → bad report | Each tool validates its output before passing downstream. Confidence < 0.4 triggers a LOW flag and stops deep analysis. |
| **Goal Drift** | Agent starts writing generic analysis instead of explaining predictions | Reflector checks: does every sentence cite a specific feature value? |
| **Sycophancy** | LLM agrees with expected outcome instead of following data | Temperature = 0.0 for all prediction and narrative steps. |
| **Infinite Loop** | Reflector keeps revising forever | Max 2 revision cycles per competitor. If still failing, flag for human review. |
| **Tool Misuse** | Agent calls wrong data source | Constrain tool access — each agent role has explicit tool allowlist only. |

**Temperature discipline:**
```
prediction / classification   → temperature = 0.0
narrative generation          → temperature = 0.3
executive summary / polish    → temperature = 0.5
```

---

## 8. Report Output Structure

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Bid Intelligence Report
Project: #{project_id} | {location} | {project_type}
Bid Date: {bid_date} | Generated: {timestamp}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

SECTION 1: EXECUTIVE SUMMARY
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Predicted bidders: N competitors
Competition intensity: LOW / MEDIUM / HIGH
Top threats: Competitor A (82%), Competitor B (74%)

SECTION 2: THREAT MATRIX
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  ── Priority Competitors — Active / Watch ──   (score ≥ 0.40)
  🔴 HIGH     Competitor A    82%
  🔴 HIGH     Competitor B    74%
  🟡 MEDIUM   Competitor C    55%

  ── Priority Competitors — Low Activity ──     (score < 0.40)
  🟢 LOW      Competitor D    23%
  🟢 LOW      Competitor E    15%

  ── DISCOVERY — New Threats ──
  🟡 MEDIUM   Competitor F    48%
  🟢 LOW      Competitor G    31%

SECTION 3A: PRIORITY COMPETITORS — Deep Dives
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
*(Known top competitors tracked by CSI — HIGH and MEDIUM threats)*

SECTION 3B: DISCOVERY COMPETITORS — Deep Dives
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
*(Rule-discovered competitors — watch for emerging threats)*
【Competitor A — 82%】
[2-3 sentence narrative]

Top signals driving this prediction:
  ✓ same_county_prior_bid_count = 8   (contribution: +2.14)
  ✓ paving_match = 1                  (contribution: +1.87)
  ✓ recent_3m_bid_count = 4           (contribution: +1.23)
  ✗ days_since_last_bid = 45          (contribution: -0.94)

SECTION 4: STRATEGIC RECOMMENDATIONS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[LLM-generated recommendations based on threat landscape]

SECTION 5: APPENDIX
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Full probability table for all competitors analyzed
Model: Logistic Regression | Feature count: 40
```

---

## 9. Folder Structure

```
ci_model/
└── model_1_wenyu/
    ├── 01_candidates/
    ├── 02_features/
    ├── 03_training/
    ├── 04_evaluation/
    ├── 05_explainability/
    │   └── outputs/
    │       ├── logistic_feature_importance.csv   ← agent reads this
    │       └── logistic_feature_importance.txt
    └── 06_reporting/                              ← NEW
        ├── agent/
        │   ├── orchestrator.py      # main pipeline runner
        │   ├── planner.py           # decides competitor list + order
        │   ├── executor.py          # ReAct loop per competitor
        │   ├── reflector.py         # quality checkpoint
        │   └── reporter.py          # assembles + exports report
        ├── tools/
        │   ├── predict_and_explain.py
        │   ├── get_competitor_profile.py
        │   ├── generate_narrative.py
        │   └── export_report.py
        ├── templates/
        │   └── narrative_templates.py   # 40-feature white-language mapping
        ├── prompts/
        │   ├── system_prompt.txt        # Layers 1-3 (static)
        │   ├── reflection_prompt.txt
        │   └── polish_prompt.txt
        ├── outputs/
        │   └── reports/                 # generated PDFs and Word docs
        └── README.md
```

---

## 10. Implementation Status

All components are complete as of 2026-06-21. The pipeline has been run end-to-end and a sample report has been generated.

| Component | Status | Location |
|---|---|---|
| `predict_and_explain()` | ✓ Done | `tools/predict_and_explain.py` |
| `get_competitor_profile()` | ✓ Done | `tools/get_competitor_profile.py` |
| `generate_narrative()` | ✓ Done | `tools/generate_narrative.py` |
| `generate_report_section()` + `export_report()` | ✓ Done | `tools/export_report.py` |
| `narrative_templates.py` (40-feature mapping) | ✓ Done | `templates/narrative_templates.py` |
| Planner, Executor, Reflector, Reporter agents | ✓ Done | `agent/*.py` |
| Orchestrator (full pipeline runner) | ✓ Done | `agent/orchestrator.py` |
| System, reflection, and polish prompts | ✓ Done | `prompts/*.txt` |
| Sample report output | ✓ Generated | `outputs/reports/bid_report_P001529.md` |

---

## 11. Key Design Principles


1. **Not every step needs an LLM.** Rule-based templates handle feature → narrative translation. LLM only polishes language and generates the executive summary and recommendations.
2. **Never let LLMs do the math.** LR prediction and contribution calculations are fully deterministic Python. LLM receives the computed numbers, never calculates them.
3. **Audit trail is essential.** Every report records: model version, feature values used, contributions computed, narrative draft, reflection result, final output. Timestamped.
4. **Limit tool exposure.** Each agent role (Planner, Executor, Reflector, Reporter) has access only to the tools it needs. No open-ended access.
5. **Autonomy is a progression.** Start with human review on every report. Earn trust. Scale to automated delivery.

---

*Document owner: Quinten (Hsin Kuei Chang)*
*Project: CSI ELP — Bid Intelligence System*
*Model: Logistic Regression (model_1_wenyu)*
