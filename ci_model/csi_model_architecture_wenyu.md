# CSI Competitor Intelligence System — Model Architecture Reference

## Open Questions and Planned Experiments

This architecture should be treated as an MVP design plus a set of planned experiments. The first version should prioritize transparent candidate selection, clean labels, and auditable evidence before adding more complex predictive modeling.

### Job Budget Definition

The model needs a consistent `job_budget` or `estimated_value` field, but the current data may contain several possible proxies:

- Lowest actual bid.
- Engineer's estimate, where available and reliable.
- CSI's internal estimate, if available later.
- Project size proxy based on material quantities.

For the MVP, `estimated_value` can use the lowest observed bid in historical data as a practical proxy for completed bid events. This should be documented as a historical training proxy, not as information that would always be known before a future bid.

Planned comparison:

| Budget Definition | Use Case | Risk |
|---|---|---|
| Lowest actual bid | Historical backtesting proxy | Not available before future bid opening |
| Engineer's estimate | Future-facing estimate | Incomplete and may be contaminated in source data |
| CSI internal estimate | Best future-facing estimate | May not be available in current dataset |
| Quantity-based proxy | Available from project scope | Less direct financial signal |

### Candidate-Filter Rules

The candidate filter should be implemented as a transparent rule-based system first. Each rule should be evaluated before being treated as final.

The key open question is:

```text
Which rule set retains the actual bidders while keeping the candidate set small enough to be useful?
```

Evaluation should compare:

- Candidate recall.
- Recall@5.
- Recall@10.
- Winner recall.
- Near-low bidder recall.
- Number of candidates per project.
- Whether emerging competitors are captured.

### Candidate Window Experiments

Recent activity windows should be treated as hyperparameters / rule experiments, not business facts. The following windows should be tested:

- 90-day activity.
- 180-day activity.
- Current-season activity.
- 12-month activity.
- 24-month activity.

The final candidate-filter configuration may find, for example, that 90 days is too short, 24 months is too broad, and current season + 12 months gives the best tradeoff.

Evaluation should compare:

- Candidate recall.
- Recall@5.
- Recall@10.
- Number of candidates per project.
- Whether emerging competitors are captured.

### Pit Future Refinement

Pit and material-access features should be treated as future refinements, not MVP dependencies. The system should run without pit data. Once CSI provides a reliable pit / plant / access table, the model can add:

- Distance to nearest eligible pit or plant.
- Ownership and access rights.
- Material suitability.
- Traffic-level or specification compatibility.
- Local active-project or plant advantage.

---

## Overview

The system should be framed as **decision support**, not a pure binary classifier. The goal is to help CSI understand:

- Which competitors are likely to bid.
- Why those competitors are likely to bid.
- Which competitors may be aggressive or threatening.
- How CSI's own position, capacity, risk, and operational fit affect the bid decision.

The recommended structure is a **two-model pipeline**:

- **Model 1: Competitor Participation and Threat Assessment**
  - Candidate filtering.
  - Likely bidder ranking.
  - Competitor threat / aggressiveness assessment.
- **Model 2: CSI Multi-Factor Decision Support**
  - CSI competitive position.
  - Capacity and operational fit.
  - Risks.
  - Recommendation and explanation.

The final output may include a GO / REVIEW / NO-GO recommendation, but that recommendation should summarize an evidence-based assessment. It should not be presented as a direct conversion from a single win-probability score.

---

## Full Pipeline

```text
New Job Comes In
       |
       v
Project Feature Extraction
  - Location
  - Bid date / season
  - Project type
  - Material quantities
  - Estimated value / job budget proxy
       |
       v
Competitor Entity Resolution
  - Raw bidder name -> competitor_unit_id
  - Operating unit, not parent company, is the modeling unit
  - Parent company retained for reporting context
       |
       v
Model 1: Competitor Participation and Threat Assessment
  1. Candidate filtering
  2. Likely bidder ranking
  3. Competitor threat / aggressiveness output
       |
       v
Model 2: CSI Multi-Factor Decision Support
  1. CSI competitive position
  2. Capacity and operational fit
  3. Risks and uncertainty
  4. Recommendation and explanation
```

---

## Competitor Entity Management

The participation and workload models should use **competitor operating units**, not standardized company names or ultimate parent companies.

For example, Knife River Minnesota and Knife River North Dakota may share the same parent company but should be modeled separately if they:

- Bid from different offices or regions.
- Maintain separate workload and capacity.
- Follow different pricing behavior.
- Do not share operational capacity across divisions.

Company names should not be used as permanent IDs. Each operating unit should have a stable `competitor_unit_id`, with raw historical names mapped through an alias table.

Core reference tables:

| Table | Purpose |
|---|---|
| `competitor_entities.csv` | Stable operating-unit registry |
| `competitor_aliases.csv` | Raw bidder name to `competitor_unit_id` mapping |
| `competitor_priority.csv` | Temporary or client-approved priority competitor list |
| `competitor_relationships.csv` | Future parent / acquisition / division relationships |
| `regional_competitors.csv` | Future region-specific competitor activation rules |

Pending mappings should remain explicitly marked as `pending_client_review`. Do not permanently merge Knife River divisions, acquired companies, or ambiguous DBA relationships before client confirmation.

---

## Model 1: Competitor Participation and Threat Assessment

### Purpose

Model 1 answers two linked questions:

1. Which competitor operating units are likely to bid on this project?
2. Among those likely bidders, which competitors appear most threatening or aggressive?

The first MVP should begin with rule-based candidate filtering and simple ranking baselines before adding more complex models.

### Training Unit

Each training row should represent:

```text
one project x one competitor operating unit
```

Core label columns:

| Column | Meaning |
|---|---|
| `did_bid` | 1 if the competitor bid on the project, otherwise 0 |
| `did_win` | 1 if the competitor submitted the lowest bid / won |
| `bid_amount` | Actual bid amount when `did_bid = 1` |
| `gap_to_low` | `(bid_amount - low_bid_amount) / low_bid_amount` |

Actual bidders must always be included during training, even if the candidate filter would have missed them. This allows candidate-filter recall to be measured instead of hidden.

---

### Initial Candidate-Filtering Logic

The first candidate filter should be implemented as a transparent rule-based system and evaluated before being finalized.

A competitor may enter the candidate set through any of the following paths:

```text
Candidate Set =
historically relevant competitors
+ temporary priority competitors
+ region-specific competitors
+ recently active / emerging competitors
+ actual bidders during training
```

The candidate filter should be evaluated separately from the ranking model. If the filter drops the true bidder, the ranking model cannot recover that competitor later.

#### 1. Historically Relevant Competitors

**Definition**

An operating unit is historically relevant if, before the current project's bid date, it has demonstrated bidding activity in a market, project type, or project profile similar to the current project.

Historical relevance may include prior bids in:

- The same state.
- The same county.
- The same normalized project type.
- Projects with similar size.
- Projects with a similar material profile.

**First MVP Rule**

Start with the simplest version:

```text
same state OR same county OR same normalized project type
```

All calculations must use only bid records before the current project's bid date.

**Later Refinement**

After basic candidate recall is evaluated, add:

- Similar project size.
- Similar material quantities.
- Similar paving / grading / mixed work profile.
- Prior near-low behavior on similar projects.

**Caution**

Historical relevance should not become a pure frequency filter. A competitor with low total bid count may still be important in a specific region or project type.

#### 2. Temporary Priority Competitors

**Definition**

Temporary priority competitors are operating units that should be reviewed on each project until CSI provides a final priority competitor list.

**First MVP Rule**

Use the 10-12 operating units with the highest historical bid counts as a temporary priority list.

**How the Flag Should Be Used**

Priority status should:

- Force the competitor to be reviewed.
- Make the competitor eligible for detailed reporting.
- Support separate priority-competitor recall metrics.

Priority status should **not** directly increase the model's predicted participation probability.

**Later Refinement**

Replace the temporary top-count list with CSI's client-approved priority competitor list once available.

**Caution**

The priority list is not the full competitor universe. It is a reporting and review mechanism, not a participation label.

#### 3. Region-Specific Competitors

**Definition**

An operating unit is region-specific if it has meaningful historical concentration in the project's local market, even if it is not a frequent competitor across the full dataset.

This captures contractors that may not appear in the overall Top 10 but are important in specific counties, corridors, or local markets.

**Initial Rules**

An operating unit may be region-specific if it has:

- A minimum number of bids in the same county or nearby counties.
- A high share of its own historical bids occurring in that region.
- A client-provided regional competitor designation.

**Later Refinement**

Regional definitions can be refined using:

- County clusters.
- State DOT districts.
- CSI-defined market areas.
- Distance bands from project location.
- Region-specific project-type patterns.

**Caution**

Region-specific status should activate review and candidate inclusion. It should not automatically imply a high participation probability.

#### 4. Recently Active or Emerging Competitors

**Definition**

A recently active or emerging competitor is an operating unit that may not have enough long-term history to satisfy the historical-relevance rules but has shown recent activity or has been identified by CSI as newly relevant.

**Initial Signals**

Signals may include:

- One or more bids during the current bidding season.
- Multiple bids during the past 90 or 180 days.
- A recent first appearance in the historical data.
- Client identification as a new or emerging competitor.

**Window Experiments**

The exact activity window should be selected through historical backtesting, not assumed as a business fact. Test:

- 90-day activity.
- 180-day activity.
- Current-season activity.
- 12-month activity.
- 24-month activity.

Compare:

- Candidate recall.
- Recall@5.
- Recall@10.
- Number of candidates per project.
- Whether emerging competitors are captured.

**Caution**

Recent activity alone is not the same as project-specific relevance. A recently active competitor may still be unlikely to bid if the project is outside its region, size range, or work type.

---

### Participation Ranking

After candidate filtering, Model 1 ranks the candidate competitors by likely participation.

The MVP ranking should compare:

1. Historical frequency baseline.
2. Rule-based score.
3. Logistic regression or shallow decision tree.
4. Random Forest / boosting only as a benchmark if simpler methods are insufficient.

The ranking model should be evaluated with ranking metrics, not only accuracy or AUC.

Recommended metrics:

| Metric | Purpose |
|---|---|
| `candidate_recall` | Whether actual bidders survived candidate filtering |
| `recall@5` | Actual bidders captured in the top 5 ranked competitors |
| `recall@10` | Actual bidders captured in the top 10 ranked competitors |
| `winner_recall@K` | Whether the actual winner appears in top K |
| `near_low_bidder_recall@K` | Whether near-low bidders appear in top K |
| `average_candidates_per_project` | Candidate-set size and usability |

### Threat / Aggressiveness Output

Model 1 should also produce a competitor threat / aggressiveness assessment for the top ranked competitors.

This can start as a transparent rule-based output:

```text
Threat / Aggressiveness =
  participation likelihood
+ historical near-low behavior
+ recent win shortage
+ low observed workload
+ project-type and size fit
+ regional presence
+ optional pit / material advantage
+ optional nearby active work
```

Low observed workload should not automatically mean a competitor is aggressive. It becomes stronger evidence only when paired with recent bidding activity and historically aggressive behavior.

Example output:

| Competitor Unit | Bid Likelihood | Threat Level | Evidence |
|---|---:|---|---|
| KR_MN | High | High | Strong regional history; recent activity; low observed mix workload |
| MARK_SG | Medium | Medium | Regional relevance; similar paving work |
| STRATA_ND | Low | Medium | Historical activity, but operating-unit status pending review |

---

## Model 2: CSI Multi-Factor Decision Support

### Purpose

Model 2 translates the competitive environment into an evidence-based CSI decision-support assessment.

It should not be framed as:

```text
win_probability -> GO / NO-GO
```

Win probability is useful, but it is not the same as bid attractiveness. CSI may bid a lower-probability job for strategic reasons, or decline a high-probability job due to margin, schedule, capacity, risk, or operational fit.

### CSI Competitive Position

Model 2 should summarize CSI's position relative to the expected competitor field:

- Expected number of bidders.
- Number of strong competitors.
- Most threatening competitors.
- CSI's historical performance on similar projects.
- CSI's relative position by geography, project type, size, and work profile.

### Capacity and Operational Fit

Capacity should be treated as a workload proxy unless CSI provides verified physical capacity denominators.

Initial workload logic:

| Contractor / Work Type | Preferred MVP Proxy |
|---|---|
| Paving-heavy work | Hot mix tons awarded before bid date vs historical annual mix-ton benchmark |
| Grading-heavy work | Awarded revenue before bid date vs historical annual revenue benchmark |
| Mixed work | Report both signals where available |

Output should use business-facing categories:

| Workload Status | Interpretation |
|---|---|
| Low observed workload | May have available capacity |
| Moderate observed workload | Near recent workload level |
| High observed workload | May be more selective |
| Insufficient data | Capacity signal uncertain |

### Risks

Model 2 should explicitly surface risks and missing-data limitations:

- Candidate filter uncertainty.
- Pending operating-unit mappings.
- Incomplete project type or budget definition.
- Incomplete construction-window information.
- Pit and material-access data not yet included in the MVP.
- Workload proxy uncertainty.

### Recommendation and Explanation

The output should be a structured assessment, not only a score.

Example:

```text
Competitive attractiveness: Medium
CSI operational fit: High
Capacity fit: Moderate
Estimated win competitiveness: Medium
Risk level: Medium
Recommendation: Review / consider bidding
Confidence: Medium

Positive evidence:
- Only two high-likelihood competitors are expected.
- CSI has strong historical performance on similar work.
- Current workload proxy does not indicate severe overextension.

Risks:
- One expected competitor has strong near-low history.
- Job budget definition is still based on a historical proxy.
- Pit and material-access advantages are not included in MVP 1.
```

---

## Future Refinement: Pit and Material Access

Pit and material-access features should be added after CSI provides a reliable pit / plant / access table.

Future pit features may include:

- `distance_to_nearest_eligible_accessible_pit`
- `pit_access_status`
- `material_suitability_status`
- `traffic_level_compatibility`
- `plant_or_active_project_advantage`

Pit distance alone should not be treated as a complete advantage feature. Eligibility depends on material requirement, ownership/access rights, traffic level, project date, and whether the pit or plant is actually available.

Missing pit data should be represented as `unknown`, not as "no advantage."

---

## Data Leakage Rules

All historical statistics must be computed using only information available before the current project's bid date.

This applies to:

- Candidate-filter membership.
- Historical state / county / type bid counts.
- Recent activity windows.
- Near-low rates.
- Win shortage.
- Workload proxies.
- CSI historical performance metrics.

The candidate filter, ranking model, and threat assessment should all be backtested point-in-time. The model should never use future bids to decide whether a competitor should have been a candidate for an earlier project.

---

## Implementation Notes

Current build order:

1. Build competitor entity registry.
2. Apply raw bidder-name to operating-unit mapping.
3. Build project x competitor panel.
4. Evaluate candidate-filter rules.
5. Build point-in-time historical features.
6. Train / compare ranking baselines and simple models.
7. Add competitor threat assessment.
8. Add CSI multi-factor decision-support output.
9. Add pit and material-access features as future refinement.

The architecture should remain modular so the candidate-filter logic, window experiments, workload proxies, and pit features can be revised independently.
