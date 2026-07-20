# First-Principles Single-Factor Rules — Control Experiment

Requested by Mochen: instead of making the model more complex, hand-write
single-factor rules from first principles and see whether any of them alone
reproduce the client's intuition ("3-5 known real competitors, winner is one
of them ~90% of the time"), **without any candidate pre-filtering** — ranking
directly over the full ~700+ competitor universe. This mirrors the setup
already used for the teammate's composite "Simple Rule-Based" baseline, but
isolates each factor instead of combining them.

## Rules tested

| Rule | Definition | Coverage caveat |
|---|---|---|
| `distance` | Top-K = nearest self-owned MN pit to the project site. Nothing else. | Pit ownership data is MN-only and only 20/727 companies own a pit — everyone else ties at "no computable distance" and ranks last. |
| `capacity_size_fit` | Company's historical average material quantity vs. this project's required quantity — log-gap based fit score, compared only on materials the project actually needs (qty > 0). Requires >=3 prior bids with qty>0 on a material to count it. | Only compares project-relevant materials — see "Bug fix" note below for why. |
| `capacity_volume` | log(total historical bid dollar volume) as of bid_date. Pure scale, no project-fit. | — |
| `historical_winrate_state` | Candidate pool restricted to companies with prior bid history **in the same state only** (no cross-state), scored by win rate for this project_type in-state (falls back to overall in-state win rate). | — |

All scores are as-of safe (only use data strictly before the project's
`bid_date`). Test set = same split as the existing pipeline
(`bid_date >= 2025-05-01`, `shared/config.py` `VALIDATION_END_DATE`), 243
projects, 224 with a resolvable winner in the full universe.

## Results — Winner Hit Rate @K

Run `python run_experiment.py` to regenerate; see `outputs/summary.csv` and
`outputs/per_project_<rule>.csv`.

| Method | @5 | @10 | @20 |
|---|---|---|---|
| Logistic Regression (filtered pool, reference) | 45.2% | 61.1% | 76.4% |
| Existing Rule Heuristic (filtered pool, reference) | 29.8% | 38.0% | 55.3% |
| **capacity_volume** | 17.9% | 25.0% | 29.9% |
| **distance** | 14.7% | 15.2% | 15.2% |
| **historical_winrate_state** | 1.4% | 1.8% | 3.2% |
| **capacity_size_fit** | 0.0% | 1.3% | 5.8% |

("filtered pool" reference rows run on the existing pre-filtered candidate
panel, not the full universe — not apples-to-apples pool size, kept only for
context. Analytical random baseline for the full universe was ~0.7%/1.4%/2.9%
at @5/@10/@20, computed as `K / candidate_count` averaged over projects —
useful for sanity-checking the rules above but not carried as its own row.)

## Bug fix: `capacity_size_fit` was scoring worse than random

The first pass at `capacity_size_fit` compared every candidate against **all**
material columns unconditionally, treating "this project doesn't need this
material" as a target quantity of `0`. Two problems fell out of that:

1. **NaN bug**: `float(project_row.get(col, 0) or 0)` treats `NaN` as truthy
   (Python's `or` only falls through on `0`/`False`/`None`), so a project's
   genuinely-missing material column stayed `NaN` instead of becoming `0`. That
   NaN propagated into the cohort-wide fallback mean, which then silently
   scored most of the ~700-company candidate pool as `NaN` — an almost
   arbitrary ranking.
2. **Deeper design flaw**: even after fixing the NaN, scoring against
   irrelevant materials systematically penalized larger/more diversified
   companies (they have historical activity in materials this project doesn't
   need, which reads as a large "gap"). A 60-project sample showed the winner's
   average rank percentile was **0.63 — worse than random (0.5)**.

Fix: only compare materials the project actually needs (`qty > 0`). Re-running
the same sample dropped the winner's average rank percentile to **0.37**
(better than random). Full-set Hit Rate went from 0.4%/0.9%/0.9% to
0.0%/1.3%/5.8% at @5/@10/@20.

## Takeaway

No single factor comes close to the composite rule (county+type+state+size-fit,
~38-55% hit rate) or the ML models, let alone the client's claimed ~90%.
`capacity_volume` (raw historical scale) is the strongest single factor,
followed by `distance`, which plateaus fast because only 20 companies have a
computable distance at all. `historical_winrate_state` and `capacity_size_fit`
are the weakest of the four, even after fixing the bug above — matching a
project's material scale to a company's historical average is a materially
weaker "who wins" signal than raw company scale or geographic proximity. This
suggests the client's mental model is not reducible to one dominant signal —
it's the *combination* of geography + project-type history + recency that does
the work, consistent with why the composite rule (and ML) outperform every
individual factor here.
