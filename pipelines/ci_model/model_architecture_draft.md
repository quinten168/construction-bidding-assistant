# Competitor Intelligence System — Model 1 Architecture Reference

## Current Scope

This draft focuses only on **Model 1: Competitor Participation and Threat Assessment**.

Model 2, the client's multi-factor decision support, is intentionally out of scope for the current build. It should not be implemented until the Model 1 candidate filter, participation ranking, and threat evidence are stable and auditable.

Model 1 follows this sequence:

```text
Candidate filtering
-> Participation ranking
-> Threat / aggressiveness assessment for likely bidders
```

This separates two different questions:

1. Which competitors should be considered reasonable candidates for this project?
2. Among those candidates, which competitors are most likely to bid and most threatening if they appear?

---

## Open Questions and Planned Experiments

### Job Budget Definition

The model needs a consistent `job_budget` or `estimated_value` field. Potential definitions include:

- Lowest actual bid.
- Engineer's estimate, where available and reliable.
- the client's internal estimate, if available later.
- Quantity-based proxy from material quantities.

For historical backtesting, the lowest observed bid can be used as a practical proxy. This must be documented as a historical proxy, not as information that would always be known before a future bid.

### Candidate-Filter Rules

The first candidate filter should be transparent and rule-based. It should be evaluated before it is finalized.

Core evaluation questions:

- Does the filter retain actual bidders?
- Does it retain the winner?
- Does it retain near-low bidders?
- Does it keep the candidate set small enough to be useful?
- Does it capture region-specific and emerging competitors?

### Candidate Window Experiments

Recent activity windows are experiments, not fixed business facts. Do not include every window at once, because that will keep expanding the candidate pool.

Test separate filter versions:

- `Filter_v1_90d`
- `Filter_v2_180d`
- `Filter_v3_current_season`
- `Filter_v4_12m`
- `Filter_v5_24m`

For the first definition of current season, use:

```text
January 1 through the current bid date
```

Compare:

- Candidate recall.
- Winner recall.
- Near-low bidder recall.
- Recall@5.
- Recall@10.
- Average candidate count.
- Median candidate count.
- 90th percentile candidate count.
- Whether emerging competitors are captured.

The final configuration may show, for example, that 90 days is too short, 24 months is too broad, and current season + 12 months gives the best tradeoff.

### Pit Future Refinement

Pit and material-access data should remain a future refinement, not a Model 1 MVP dependency. The candidate filter and ranking model must run without pit data.

Future pit features may include:

- Distance to nearest eligible accessible pit or plant.
- Ownership and access rights.
- Material suitability.
- Traffic-level or specification compatibility.
- Local active-project or plant advantage.

Missing pit data should be represented as `unknown`, not as "no advantage."

---

## Competitor Entity Management

The modeling unit is the **competitor operating unit**, not the parent company and not a raw bidder-name string.

For example, Knife River Minnesota and Knife River North Dakota may share a parent company but should remain separate operating units if they:

- Bid from different offices or regions.
- Maintain separate workload and capacity.
- Follow different pricing behavior.
- Do not share operational capacity across divisions.

Core reference tables:

| Table | Purpose |
|---|---|
| `competitor_entities.csv` | Stable operating-unit registry |
| `competitor_aliases.csv` | Raw bidder name to `competitor_unit_id` mapping |
| `competitor_priority.csv` | Temporary or client-approved priority competitor list |
| `competitor_relationships.csv` | Future parent / acquisition / division relationships |
| `regional_competitors.csv` | Future region-specific competitor activation rules |

Pending mappings should stay marked as `pending_client_review`. Do not permanently merge ambiguous divisions, acquired companies, or DBA relationships before client confirmation.

---

## Model 1 Training Unit

Each row should represent:

```text
one project x one competitor operating unit
```

Core label columns:

| Column | Meaning |
|---|---|
| `did_bid` | 1 if the competitor bid on the project, otherwise 0 |
| `did_win` | 1 if the competitor was the winner / lowest bidder under the selected win rule |
| `bid_amount` | Actual bid amount when `did_bid = 1` |
| `gap_to_low` | `(bid_amount - low_bid_amount) / low_bid_amount` |
| `is_near_low` | 1 if `gap_to_low <= near_low_threshold` |
| `was_rule_candidate` | 1 if the competitor entered through the rule candidate filter |
| `candidate_source` | Rule path(s) that placed the competitor in the candidate set |

### Near-Low Definition

The MVP should use a fixed near-low threshold so evaluation metrics are stable:

```text
is_near_low = gap_to_low <= 0.05
```

Later sensitivity analysis should compare:

- 3%.
- 5%.
- 10%.

Tied-low bids need a clear rule. For the first backtest:

```text
did_win = 1 for all tied-low bidders
```

If the client later provides final awarded contractor data, `did_win` can be changed to reflect the awarded contractor instead of all tied-low bidders.

---

## Rule Candidate Set vs Training Panel Set

The architecture must distinguish between two sets.

### 1. `rule_candidate_set`

This is the real candidate pool that would be available at prediction time. It must be generated using only information known before the current project's bid date.

It may include competitors from:

- Historical relevance rules.
- Temporary priority rules.
- Region-specific rules.
- Recent activity / emerging competitor rules.

This set is used to:

- Simulate future prediction.
- Evaluate candidate recall.
- Provide the real input universe to the participation ranking model.

### 2. `training_panel_set`

This is the panel used for training and diagnostic analysis:

```text
training_panel_set = rule_candidate_set + actual bidders
```

Actual bidders are added only so positive examples do not disappear from the training data and so missed bidders can be audited.

This does **not** mean the filter succeeded. Use:

```text
was_rule_candidate = 0
```

for actual bidders that were missed by the rule filter.

Example:

| Project | Competitor | did_bid | was_rule_candidate |
|---|---|---:|---:|
| A | Knife River MN | 1 | 1 |
| A | Local Contractor X | 1 | 0 |
| A | Competitor Y | 0 | 1 |

This allows the team to report:

```text
Candidate filter missed Local Contractor X.
```

---

## Initial Candidate-Filtering Logic

A competitor may enter the `rule_candidate_set` through any of these paths:

```text
rule_candidate_set =
historically relevant competitors
+ temporary priority competitors
+ region-specific competitors
+ recently active / emerging competitors
```

During training only:

```text
training_panel_set =
rule_candidate_set
+ actual bidders missed by the rules
```

The candidate filter should be evaluated separately from the ranking model. If the rule filter misses a true bidder, the ranking model cannot recover that competitor at prediction time.

### 1. Historically Relevant Competitors

#### Definition

An operating unit is historically relevant if, before the current project's bid date, it has demonstrated bidding activity in a market, project type, or project profile similar to the current project.

Possible relevance signals:

- Same state.
- Same county.
- Same normalized project type.
- Similar project size.
- Similar material profile.

#### Candidate Rules to Backtest

The first draft rule:

```text
same state OR same county OR same normalized project type
```

is too broad. `same county` is already contained within `same state`, and `same normalized project type` alone may pull in remote competitors from unrelated markets.

Backtest multiple rule versions:

```text
Rule A:
same state

Rule B:
same county

Rule C:
same state AND same normalized project type

Rule D:
same county
OR (same state AND same normalized project type)

Rule E:
same county
OR (same state AND same normalized project type)
OR recent activity
```

The most promising first test is:

```text
same county
OR (same state AND same normalized project type)
```

This is narrower than the broad OR rule while still allowing state-level project-type relevance.

#### Later Refinement

After basic candidate recall is evaluated, test:

- Similar project size.
- Similar material quantities.
- Similar paving / grading / mixed work profile.
- Prior near-low behavior on similar projects.

#### Caution

Historical relevance should not become a pure total-frequency filter. A competitor with low overall bid count may still be important in a specific region or project type.

### 2. Temporary Priority Competitors

#### Definition

Temporary priority competitors are operating units that should be reviewed on each project until the client provides a final priority competitor list.

#### First MVP Rule

Use the 10-12 operating units with the highest historical bid counts as the temporary priority list.

#### How the Flag Should Be Used

Priority status should:

- Force the competitor to be reviewed.
- Make the competitor eligible for detailed reporting.
- Support separate priority-competitor recall metrics.

Priority status should **not** directly increase predicted participation probability.

Priority competitors should also not automatically occupy the model Top 5 / Top 10. Separate the output into:

```text
Model-ranked likely bidders
```

and:

```text
Additional priority competitors reviewed
```

Example:

| Competitor | Predicted Likelihood | Why Shown |
|---|---:|---|
| Knife River MN | High | Model Top 5 |
| Competitor X | Low | client priority review |

#### Later Refinement

Replace the temporary top-count list with the client-approved priority list when available.

### 3. Region-Specific Competitors

#### Definition

An operating unit is region-specific if it has meaningful historical concentration in the project's local market, even if it is not frequent across the full dataset.

This captures contractors that may not appear in the overall Top 10 but are important in specific counties or market areas.

#### Initial Rules

Region-specific logic must use both count and concentration to avoid small-sample false positives.

Do not rely only on regional share. Example failure:

```text
A competitor has only one historical bid.
That one bid is in the county.
Regional share = 100%.
```

This should not automatically make it an important regional competitor.

Initial rule options:

```text
regional_bid_count >= 2 or 3
AND
regional_bid_share >= threshold
```

or:

```text
same_county_bid_count >= 2
OR nearby_region_bid_count >= 3
```

Specific thresholds should be selected through backtesting.

#### Nearby Region Definition

`nearby county` is not yet defined. For the first MVP, use one of:

- Same county only.
- Fixed client market region, if available.
- Client-provided regional competitor designation.

Do not build county adjacency logic until the required geography table is ready.

#### Caution

Region-specific status should activate candidate inclusion and review. It should not automatically imply high predicted participation probability.

### 4. Recently Active or Emerging Competitors

#### Definition

A recently active or emerging competitor is an operating unit that may not have enough long-term history to satisfy historical relevance rules but has shown recent activity or has been identified by the client as newly relevant.

#### Initial Signals

Signals may include:

- One or more bids during the current bidding season.
- Multiple bids during the past 90 or 180 days.
- A recent first appearance in the historical data.
- Client identification as a new or emerging competitor.

#### Window Experiments

Do not apply every activity window at once. Treat each window as a candidate-filter version:

```text
Filter_v1_90d
Filter_v2_180d
Filter_v3_current_season
Filter_v4_12m
Filter_v5_24m
```

Compare:

- Candidate recall.
- Winner recall.
- Near-low bidder recall.
- Recall@5.
- Recall@10.
- Average candidate count.
- Median candidate count.
- 90th percentile candidate count.
- Whether emerging competitors are captured.

Current season should first be defined simply as:

```text
January 1 through the current bid date
```

#### Caution

Recent activity alone is not the same as project-specific relevance. A recently active competitor may still be unlikely to bid if the project is outside its region, size range, or work type.

---

## Negative Sample Definition

Negative rows should not be generated from:

```text
every project x every historical competitor
```

That creates many trivial negatives, such as a Minnesota local contractor paired with a remote North Dakota project. These rows can make the model look accurate while teaching little beyond geography.

Training rows should include:

```text
rule candidates
+ actual bidders missed by rules
```

If extra negative sampling is needed later, draw only from a reasonable competitor universe, such as operating units that:

- Have activity in the same state.
- Have activity in nearby years.
- Have bid on the same normalized project type.

---

## Participation Ranking

After candidate filtering, Model 1 ranks competitors in the `rule_candidate_set` by likely participation.

The first implementation should compare:

1. **Baseline 1:** historical bid frequency.
2. **Baseline 2:** weighted rule score.
3. **Model 3:** logistic regression.

A shallow decision tree can be added as an interpretability comparison. Random Forest or boosting should be held for later benchmarking after simple methods are tested.

Initial features may include:

- Same county bid count.
- Same state bid count.
- Same normalized project-type bid count.
- Days since last bid.
- Current-season bids.
- Historical bid rate.
- Similar-size bid count.

All features must be calculated point-in-time using only records before the current project's bid date.

### Ranking Metrics

Evaluate ranking with:

- Candidate recall.
- Recall@5.
- Recall@10.
- Winner recall.
- Near-low bidder recall.
- Average candidate count.
- Median candidate count.
- 90th percentile candidate count.

Do not judge Model 1 primarily by accuracy, because most candidate rows are negatives.

---

## Threat / Aggressiveness Assessment

Model 1 should output two separate concepts:

```text
Bid likelihood
Pricing threat
```

Do not immediately combine them into a single threat score.

Example:

| Competitor | Bid Likelihood | Pricing Threat | Interpretation |
|---|---|---|---|
| Competitor A | High | Medium | Likely to bid, but historically not often near-low |
| Competitor B | Medium | High | Less certain to bid, but dangerous if present |

### Bid Likelihood Evidence

Bid likelihood can use:

- Historical state / county / type participation.
- Recent activity.
- Region-specific relevance.
- Temporary priority review flag, reported separately.
- Project size and work-profile fit.

### Pricing Threat Evidence

Pricing threat can use:

- Historical near-low rate.
- Frequency of bids within 5% of low.
- Prior wins on similar projects.
- Recent win shortage.
- Low observed workload, only when paired with active bidding behavior.

Low observed workload should not automatically mean a competitor is aggressive. It may also mean the competitor is leaving a market or not pursuing that type of work.

The first threat assessment can be rule-based. It does not need to be trained as a supervised model in the first Model 1 iteration.

---

## Model 1 Implementation Flow

```text
Step 1
Resolve competitor entities at operating-unit level

Step 2
Build clean project and bidder tables

Step 3
For each historical project:
use only earlier records to calculate features

Step 4
Generate rule_candidate_set

Step 5
Add missed actual bidders only to training_panel_set

Step 6
Evaluate candidate filter separately

Step 7
Choose one candidate-filter configuration

Step 8
Train participation ranking model

Step 9
Evaluate Recall@5, Recall@10, winner recall, and near-low recall

Step 10
Generate rule-based threat evidence for top-ranked competitors
```

---

## Model 2 Placeholder

Model 2 should remain out of scope until Model 1 is stable.

Later, Model 2 can use Model 1 outputs to support the client's decision-making:

- The client's competitive position.
- Capacity and operational fit.
- Risk flags.
- Recommendation and explanation.

No Model 2 logic should be built until the candidate filter, participation ranking, and threat evidence are validated.

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
- The client's historical performance metrics used later by Model 2.

The candidate filter, participation ranking model, and threat assessment should all be backtested point-in-time. The model should never use future bids to decide whether a competitor should have been a candidate for an earlier project.
