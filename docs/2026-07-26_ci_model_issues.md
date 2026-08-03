# ci_model: issues found, 2026-07-26

Findings from a full read of `pipelines/ci_model/` and `data/`. Every claim below was verified
against code on `origin/main` (post `5331d63`). Written for the CI workstream (Quinten, Wenyu).

Nothing here is a criticism of the modeling work. These are plumbing failures, and every one of
them fails **silently**, which is why they survived this long.

---

## AMENDMENT — 2026-08-03

**Substantially overtaken by events. Treat every finding below as "verified true on 2026-07-26",
not as current state.** Merged as a record of what was found and why, not as a live defect list.

Between 2026-07-26 and today `main` absorbed at least four commits aimed squarely at these
findings: `af9f8bc` "Fix 10 dead ranking features; rebuild scope-match on pure quantities",
`c7c8751` "Replace paving_match/grading_match/base_match with one match feature per material",
`f359c8d` "Swap CI model to interpretable 4-feature baseline (#44)", and `5381953`, which removed
`job_id` in favour of `project_natural_key` as the canonical identifier — the fix Issue 3
recommends.

Spot-checked on 2026-08-03, not exhaustively re-audited:

- **Issue 2** (`has_base` missing from `candidate_filter.py`) — the symbol no longer appears in
  that file at all; the surrounding code was restructured. Finding is stale in its stated form.
- **Issue 3** (`job_id` is a row ordinal) — `_project_identity` is now persisted and merged
  (`data/build_project_competitor_panel.py`), and `job_id` was dropped downstream. Largely
  addressed.
- **Issue 5** (missing becomes zero) — the `_pv()` / `.fillna(0)` pattern **still exists** at
  `pipelines/ci_model/02_features/build_ranking_features.py:237-238`. This is the root-cause
  finding and it appears to be the one still open. It is also the one that matters most.

**Do not use this document to open new tickets without re-verifying against current code first.**
The verification named in "Suggested order of fixing" still stands as the right test: at least one
of the ten formerly-dead features shows non-zero variance in a regenerated
`ranking_predictions.csv`.

---

## TL;DR

- **The model is advertised as 33 features. It is really 23.** Ten are hard zeros in production.
- **Every material quantity is one of the dead ten.** Tonnage never reaches the model.
- The cause is two lines in two scripts, not the modeling.
- **Issue #11 (materials to 2026 capacity) cannot be closed by connecting the two modules.** The
  CI side has to be fixed too.
- One bright spot: the client-facing **capacity number is computed outside the model** and is
  probably fixable much sooner.

---

## Issue 1 (critical): tonnage never reaches the model

**Ten of the 33 features are identically zero on every row in production:**

| dead feature | what it was supposed to carry |
|---|---|
| `log_mix_tons` | hot mix tonnage |
| `log_grading_yards` | grading volume |
| `log_base_tons` | base tonnage |
| `log_shldr_tons` | shoulder tonnage |
| `log_mill_sy` | milling area |
| `log_crush_tons` | crushing tonnage |
| `log_stock_tons` | stockpile tonnage |
| `project_size_proxy` | overall project size |
| `base_match` | competitor has done base work before |
| `project_location_missing` | coordinates were unavailable |

**Proven three independent ways:**

1. `03_training/outputs/ranking_predictions.csv`, all 237,346 rows: `std = 0`, `nunique = 1` for
   each of the ten.
2. `03_training/outputs/logistic_baseline_model.json`: `scaler_std = 1.000000` and
   `feature_weight = +0.0000` for exactly those ten. A std of 1.0 is scikit-learn's fallback when
   a column has zero variance.
3. `05_explainability/outputs/logistic_feature_importance.csv`: ranks 24 through 33 are labelled
   with the literal string `inactive (zero weight)`.

### The two scripts causing it

**`01_candidates/build_training_panel.py`, lines 118-130.** The merge only pulls five columns
across, and `mix_tons` and `grading_yards` are not among them:

```python
rule_candidates = rule_candidates.merge(
    actual[["job_id", "competitor_unit_id", "bid_amount", "bid_rank", "did_bid"]],
    on=["job_id", "competitor_unit_id"], how="left")
```

The quantity columns do appear in `ranking_training_panel.parquet`, but only on rows concatenated
in from the `missed_actual` frames, and line 189-194 then filters those rows back out. Result:
**`mix_tons` is null on 1581 of 1581 surviving rows. So is `grading_yards`.**

**`02_features/build_ranking_features.py`, lines 229-239.** It reads the quantities off the panel
row, and a missing value becomes zero without a warning:

```python
def _pv(key: str) -> float:
    return float(pd.to_numeric(pd.Series([project.get(key, 0)]),
                 errors="coerce").fillna(0).iloc[0])

base["log_mix_tons"] = np.log1p(max(_pv("mix_tons"), 0))
```

`.get(key, 0)` on a null gives NaN, `fillna(0)` makes it 0, `log1p(0)` is 0. No error, no log line.

**These are separable failures and both are real.** Feeding the same function a panel that does
carry `mix_tons` produces `log_mix_tons` with mean 4.68 and max 11.61, while `log_base_tons` and
`log_mill_sy` stay at exactly 0.0, because those five columns are never selected in the first
place (`build_training_panel.py:75-85` lists only `mix_tons` and `grading_yards`).

### Where tonnage does still survive

- **`mix_ton_capacity_ratio`** (`build_ranking_features.py:252-273`) works, because it reads
  `mix_tons` straight from `projects.csv` and bypasses the panel. But its coefficient is
  **-0.016**, rank 20 of 33. It is alive and nearly inert.
- **The season capacity number in the report** (`06_reporting/agent/executor.py:48-53, 63-112`,
  fed by `orchestrator.py:171-187`) also reads `projects.csv` directly. It sums `mix_tons` for won
  projects over a Sept 1 to Apr 30 season. **This is the client-facing capacity figure, and it
  does not depend on the model at all.** Likely the fastest path to something the client can see.

---

## Issue 2: `base_match` is dead for a different reason

Two copies of the same column list disagree:

| file | entries | includes `has_base`? |
|---|---|---|
| `data/build_project_competitor_panel.py:29-46` | 16 | yes |
| `01_candidates/candidate_filter.py:101-117` | 15 | **no** |

So `has_base` never reaches `rule_candidate_set`, and `base_match` is always 0. One missing string
in a list. `shared/config.py:93-102` also lists `has_base`, so `candidate_filter.py` is the outlier.

---

## Issue 3: `job_id` is a row number, not an identifier

`data/build_project_competitor_panel.py:249-275`:

```python
projects.insert(0, "job_id", [f"P{i:06d}" for i in range(1, len(projects) + 1)])
```

It is a 1-based ordinal assigned **after** sorting by `(bid_date, _project_identity)`.

- Insert one project with an earlier bid date and **every subsequent `job_id` shifts by one**.
- There is no persisted mapping and no idempotency check.
- Everything downstream is keyed on it: `bidder_results.csv`, all five `model1/*.parquet`,
  `ranking_predictions.csv`, and the 40 committed `bid_report_P######.md` files, whose filenames
  encode it (`orchestrator.py:261`).
- The stable key already exists as `_project_identity`
  (`build_project_competitor_panel.py:209-218`), but it is dropped before every parquet write.

**Recommendation: persist `_project_identity` alongside `job_id`.** It costs one column.

---

## Issue 4: there is no way to add one project

Exactly one line writes `projects.csv` (`build_project_competitor_panel.py:579`) and it is a full
regeneration. To add a project you must append to `data/raw/CSI_data_2025.csv` and re-run the
entire chain, which triggers Issue 3.

This matters because the whole point of connecting the modules is that a **new, unseen** plan
arrives and gets a report. There is no code path for that today. The live path
(`apps/api/backend/competitor_live.py:60-72`) reverse-looks-up an **existing** `job_id` by county
and state, and refuses if there is no hit.

---

## Issue 5 (root cause): missing data becomes zero, silently

This pattern is why Issues 1 and 2 went unnoticed for months. It appears in at least three places:

| file:line | pattern | effect |
|---|---|---|
| `02_features/build_ranking_features.py:229-239` | `.get(key, 0)` then `fillna(0)` | missing tonnage becomes `log1p(0) = 0` |
| `06_reporting/agent/predict_and_explain.py:68,72` | `row.get(f, 0.0)` over the 33 features | a missing feature scores as 0 at predict time |
| `data/build_project_competitor_panel.py:247` | `available_cols = [c for c in project_cols if c in bids.columns]` | a renamed or typo'd header **drops the column with no error** |

**A missing value and a genuine zero are indistinguishable everywhere in this pipeline.** The
single highest-value change in this document is to make a missing required field raise instead of
default.

---

## Issue 6: there is no project-number column

`grep` finds **no `sp_number` field anywhere** in `data/` or `pipelines/ci_model/`. The state
project number is embedded in free text inside `source_project_id`, mixed with other ID schemes,
sometimes several in one cell:

```
'P 0079(88)133, NH 0212(202)38 (PCN 06G1, 06G2)'    <- two IDs, one cell
'SAP 007-611-015'   'CP 17-002'   'PROJ #9774'   'CALL 161 76-0151-006'   '23636'
```

1264 of 1591 non-null, 13 duplicates, no normalization. This blocks joining to plan_reader on the
agreed key, which is normalized `(state, county, sp_number)`.

---

## Issue 7: the location fallback has never run

- `data/processed/projects.csv` has **zero null coordinates**, 1591 of 1591.
- So the county-centroid fallback in `01_candidates/build_pit_features.py:275-320` never fires,
  and `project_location_missing` is a constant 0 (one of the dead ten).
- What the code calls a "county centroid" is the **mean of pit coordinates in that county**
  (`build_pit_features.py:216-225`), not a civil centroid.
- The explicit `--county-centroids` file defaults to `None` (`:603`), so the medium-confidence
  path is unreachable today.

This is an **untested code path** that would run for the first time on a plan_reader-sourced
project, which has no coordinates. Worth a test before it matters.

Separately: pit features are zeroed outright for every non-MN project
(`build_pit_features.py:571-583`), roughly 40% of rows. `MN_pit_list_cleaned.csv` is 100% MN.

---

## Issue 8: smaller things worth knowing

- **`competitor_unit_id` is null on 10 rows** of `bidder_results.csv`.
- **`project_family` has no writer.** It exists in the branch's `projects.csv` and three parquets,
  is documented in `README.md:127-137` with 7 values, and `grep -rl project_family --include=*.py`
  returns **zero hits**. It was removed on `origin/main`. Unknown provenance.
- **`mix_ton_capacity_ratio` emits `RuntimeWarning: divide by zero` on every group**
  (`build_ranking_features.py:269` computes the quotient before `np.where` masks it).
- **`contract_id` is 3.7% populated** (62 of 1661). Unusable as a key.
- **`csi_job_id` is typed float64**, so it renders as `12345.0`.
- **The `Rating` scale on `MN_pit_list_cleaned.csv` is undocumented.** Integers 1 to 11.
  `best_*_rating` uses `MAX`, implying higher is better, but that is written down nowhere.
- **`Access` is free text with duplicates that differ only by whitespace**: `"Knife River"` and
  `"Knife River "` are separate values.
- **State codes can be minted from garbage.** `build_project_competitor_panel.py:187` falls back
  to `value[:2]`. Three rows carry `CO`, which is not one of the six operating states.

---

## Issue 9: the module's own docs are stale

Do not build against these without checking the code:

| file | claim | actual |
|---|---|---|
| `PIPELINE.md:117` | "~60 features" | 33 declared, 23 effective |
| `PIPELINE.md:82` | "28 pit features" | 29 defined, 15 reach the model |
| `PIPELINE.md:38,78` | inputs include `reference/competitor_priority.csv`, `competitor_entities.csv` | both deleted in `5331d63` |
| `README.md:139-150` | 10-value `project_type` vocabulary (`mill_and_overlay`, `reconstruction`, …) | code emits 6 values (`mill_overlay`, `reconstruct_rebuild`, …) |

---

## Suggested order of fixing

| # | Fix | File | Effort | Unblocks |
|---|---|---|---|---|
| 1 | Add the quantity columns to the panel merge | `build_training_panel.py:118-130` | small | 8 dead features |
| 2 | Raise instead of defaulting to 0 | `build_ranking_features.py:229-239` | small | prevents the next silent failure |
| 3 | Add `has_base` to the column list | `candidate_filter.py:101-117` | one line | `base_match` |
| 4 | Persist `_project_identity` next to `job_id` | `build_project_competitor_panel.py:275` | small | stable keys, incremental adds |
| 5 | Add a normalized project-number column | `build_project_competitor_panel.py` | medium | joining to plan_reader |
| 6 | Retrain and confirm the dead features now have non-zero weight | `train_logistic_baseline.py` | rerun | proves 1 to 3 worked |

**Verification for the whole set:** at least one of the ten dead features shows non-zero variance
in a regenerated `ranking_predictions.csv`. Until that is true, tonnage is not reaching the model,
no matter what the plan_reader side delivers.
