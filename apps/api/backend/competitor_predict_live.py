"""
Live candidate prediction for a genuinely new project — one with no row of its own in the CI
corpus's training panel (pipelines/ci_model/03_training/outputs/ranking_predictions.csv), so
competitor_live.py's live-generation and competitor_report.py's static match both have nothing to
key off (both require an EXISTING project_natural_key). This module is the live-inference analogue
of pipelines/ci_model/03_training/train_simple_rule_baseline.py for exactly one ad-hoc project:
same 4 features (county/type/state win counts + size_fit), and the SAME already-fitted weights
(03_training/outputs/simple_rule_baseline_weights.json) — applied fresh against live Postgres data
instead of matching a precomputed training-panel row.

The candidate pool (_candidate_pool()) is a manually maintained MIRROR of
pipelines/ci_model/01_candidates/candidate_filter.py::build_v3_candidate_set() — 6 of its 10 signal
sources, ported to live SQL/Python since apps/ cannot import pipelines/ (CLAUDE.md invariant 1).
See that function's docstring for exactly which signals, why 4 were dropped, and the offline
consistency test (apps/api/tests/test_candidate_pool_consistency.py) that catches the two
implementations drifting apart.

The weights are read, never refit, here. Refitting needs a label (did_bid — did this candidate
actually bid), which does not exist for a project that has not been let yet; there is nothing to
fit against for a single new project. What CAN legitimately change over time is the whole model
being periodically retrained on the growing historical corpus (train_simple_rule_baseline.py, run
again as a batch job) — a separate, offline concern from this module, which only ever scores with
whatever weights that job last produced.

Score → probability: _score_candidates() ranks by the same raw-feature-space linear score as
before (unchanged ordering), and now also attaches a calibrated win probability
(sigmoid(score + decision_offset), see _decision_offset()) wherever the weights file has a real
fitted logistic model behind it (fit: true) — a pure algebraic read of numbers already in that
JSON, not a new model.

Fail-open like every other *_live.py module in this tree (capacity_live.py, competitor_stats_live.py):
any error, or an empty/unloadable weights file, returns None, so a genuinely new plan without a
prediction still gets the rest of its report rather than a broken one.
"""
from __future__ import annotations

import datetime
import json
from math import exp, log1p

from . import ci_db
from . import competitor_report as cr
from .config import CI_MODEL_JSON
from .observability import get_logger

log = get_logger("bid_assistant.competitor_predict_live")

MIN_MATERIAL_BIDS = 3

# Mirrors pipelines/ci_model/shared/config.py's V3_* constants (as of commit 51935b84, 2026-08-02)
# -- see _candidate_pool()'s docstring for why these are copied, not shared/imported.
V3_RECENT_WINDOW_DAYS = 90
V3_FALLBACK_LOOKBACK_DAYS = 730
V3_RECURRING_REGIONAL_MIN_BIDS = 3
V3_FALLBACK_SCORE_THRESHOLD = 1.5
V3_PRIORITY_WEIGHT = 3.0
V3_HISTORICAL_WINNER_WEIGHT = 2.0
V3_RECURRING_REGIONAL_WEIGHT = 1.5

# Empirically (2026-08-09, 143 real worst-case probes -- exhaustive MT+NE plus the rarest county in
# every state) _candidate_pool() never returned fewer than 25, because the registry's
# `top_competitors_tag = '1'` rows (currently 25) always clear the fallback-score gate regardless of
# state/county/type (V3_PRIORITY_WEIGHT=3.0 >= V3_FALLBACK_SCORE_THRESHOLD=1.5). That floor is DATA-
# dependent, not code-guaranteed -- if the registry's priority tags were ever cleared, or a query
# silently returned fewer rows, this function would return a tiny pool with nothing signaling that
# anything had changed. MIN_POOL_SIZE turns that implicit guarantee into an explicit one: below it,
# _candidate_pool() logs loudly and widens defensively rather than silently serving too few
# candidates. Set well under the observed 25-candidate floor so normal rare-county queries never
# trip it -- this is an anomaly guard, not a normal-operation branch.
MIN_POOL_SIZE = 10

# CSI's own bid entity, resolved through the registry to this canonical competitor_unit_id -- must
# never be predicted as a competitor to itself. Mirrors pipelines/ci_model/shared/config.py's
# CLIENT_UNIT_IDS (duplicated, not imported -- apps/ cannot import pipelines/, invariant 1; same
# convention as this file's V3_* constants above). That offline pipeline excludes it when building
# the training panel / ranking_predictions.csv, which is why tier 1 (fresh CI-generated reports)
# has never shown it -- verified live 2026-08-10 against a real corpus project. This live path
# (tier 3) was NOT excluding it -- an omission from porting the V3 signals on 2026-08-09, found
# live the same way: CSI itself (606 historical bids, the single most active bidder in the
# dataset -- see CLAUDE.md) was appearing in its own predicted-competitor lists. If the client ever
# operates under an additional entity, add its resolved comp_name here AND to CLIENT_UNIT_IDS --
# two places, not shared code, same drift risk as every other apps/pipelines mirror in this file.
CLIENT_UNIT_IDS: frozenset[str] = frozenset({"CENTRAL SPECIALTIES"})

# quantities keys this module understands — the same 7 columns train_simple_rule_baseline.py's
# MATERIALS list and project_admin.py's MATERIAL_FIELDS both use. A fixed whitelist, not
# caller-supplied strings, because these get interpolated into a SQL column list below.
_MATERIAL_COLS = ("mix_tons", "grading_yards", "base_tons", "shldr_tons",
                   "mill_sy", "crush_tons", "stock_tons")
# final_report.py's `quantities` list uses these short display labels, not the DB column names.
LABEL_TO_MATERIAL_COL = {
    "MIX": "mix_tons", "GRADE": "grading_yards", "BASE": "base_tons",
    "SHLDR": "shldr_tons", "MILL": "mill_sy", "CRUSH": "crush_tons", "STOCK": "stock_tons",
}


def _sigmoid(x: float) -> float:
    if x >= 0:
        z = exp(-x)
        return 1.0 / (1.0 + z)
    z = exp(x)
    return z / (1.0 + z)


def _decision_offset(data: dict) -> float | None:
    """`_score_candidates()` already computes a raw-feature-space score
    `raw_score = Σ weights[f] * x_f`, where `weights[f] == feature_weights[f] / scaler_std[f]`
    (verified against the JSON: e.g. county 0.287264/0.136673 = 2.1018, matching `weights.county`
    exactly — this is train_simple_rule_baseline.py::fit_primary_weights()'s documented
    un-standardizing step, not a coincidence). Expanding sklearn's standardized decision function
    `Σ coef_i * (x_i - mean_i)/std_i + intercept` in terms of that same raw score gives
    `decision = raw_score + offset`, where `offset = intercept - Σ(feature_weights_i * mean_i / std_i)`
    is a single constant — it does not depend on any candidate's features. So
    `sigmoid(raw_score + offset)` is EXACTLY the calibrated probability sklearn's
    `predict_proba` would give (not an approximation), and because it's a strictly monotonic
    function of `raw_score`, attaching it never changes the ranking `_score_candidates()` already
    produces — see conversation notes; verified numerically against this repo's actual
    03_training/outputs/simple_rule_baseline_weights.json before shipping (offset ≈ 0.19)."""
    feature_weights = data.get("feature_weights")
    scaler_mean = data.get("scaler_mean")
    scaler_std = data.get("scaler_std")
    feature_columns = data.get("feature_columns")
    intercept = data.get("intercept")
    if not (feature_weights and scaler_mean and scaler_std and feature_columns) or intercept is None:
        return None
    try:
        centered = sum(feature_weights[f] * m / s
                       for f, m, s in zip(feature_columns, scaler_mean, scaler_std))
        return intercept - centered
    except (KeyError, ZeroDivisionError, TypeError):
        return None


def _load_weights() -> tuple[dict[str, float], float | None] | None:
    """Returns (weights, decision_offset). `decision_offset` is None when the weights file is the
    hand-picked FALLBACK_WEIGHTS (fit: false) — there is no fitted logistic model to calibrate a
    probability from in that case, so callers must treat a None offset as "score only, no
    probability", never fabricate one."""
    try:
        data = json.loads(CI_MODEL_JSON.read_text())
    except Exception as e:                                    # noqa: BLE001 — missing/corrupt file
        log.warning("could not load fitted weights from %s: %s", CI_MODEL_JSON, e)
        return None
    weights = data.get("weights")
    if not weights:
        return None
    if not data.get("fit"):
        # fit: false means train_simple_rule_baseline.py fell back to the hand-picked constants
        # (see that module's FALLBACK_WEIGHTS) — still usable for ranking, just not for a probability.
        return (weights, None)
    return (weights, _decision_offset(data))


def _candidate_pool(conn, county: str, state: str, project_type: str | None, before_date: str) -> set[str]:
    """Live analogue of pipelines/ci_model/01_candidates/candidate_filter.py::build_v3_candidate_set
    (as of commit 51935b84, 2026-08-02 — re-check this function against that commit/whatever is
    current before trusting it, and update the pin above when you do) for exactly one ad-hoc
    project instead of a full historical panel. Ports 6 of its 10 signal sources, using the SAME
    thresholds as pipelines/ci_model/shared/config.py's V3_* constants (copied at the top of this
    file): same_county, same_type (both same-state, unbounded lookback — matches the source's
    `prior` frame having no time filter), recent_90d, historical_winner_24m, recurring_regional_24m
    (>=3 wins... no, >=3 bids in the 24m window, matching V3_RECURRING_REGIONAL_MIN_BIDS), and
    priority (registry tag). A candidate qualifies if it hits one of the first three "default"
    signals directly, OR if its weighted combination of {priority, historical_winner, recurring}
    reaches V3_FALLBACK_SCORE_THRESHOLD — same two-tier gate as the source, not just a flat union.

    Deliberately drops 2 of the 10 source flags: `source_warmup_12m_same_state` only fires while
    the *historical training panel itself* is left-censored (`history_days_available < 365`,
    i.e. only for projects near the very start of the historical corpus) — a live plan scored
    against today's full corpus is never in that state, so porting it here would be dead code.
    `source_active_entity`/`source_regional`'s active-entity filter has no equivalent table in
    `scratch.*` today (same constraint the other *_live.py modules in this file already document).

    THIS IS A MANUALLY MAINTAINED MIRROR, NOT SHARED CODE — apps/ cannot import pipelines/ (CLAUDE.md
    invariant 1), so there is no way to make this "just call the real function." It WILL drift
    silently if candidate_filter.py's rule or pipelines/ci_model/shared/config.py's V3_* constants
    change without a matching edit here. `apps/api/tests/test_candidate_pool_consistency.py` diffs
    this function's output against `data/processed/model1/rule_candidate_set.parquet` (the
    materialized ground truth build_v3_candidate_set already writes) on a sample of real historical
    projects — skipped like the other Supabase-backed tests unless SUPABASE_TEAM_DB_URL is set,
    since this needs a live scratch.bid_results/bid_projects to score against. Run it after any
    change to either side of this mirror."""
    target_county = cr.norm_county(county)
    target_type = (project_type or "").strip().upper() or None
    before = datetime.date.fromisoformat(before_date[:10])
    recent_cutoff = before - datetime.timedelta(days=V3_RECENT_WINDOW_DAYS)
    lookback_cutoff = before - datetime.timedelta(days=V3_FALLBACK_LOOKBACK_DAYS)

    with conn.cursor() as cur:
        cur.execute(
            "select br.competitor_unit_id, br.did_win, bp.county, bp.project_type, bp.bid_date "
            "from scratch.bid_results br join scratch.bid_projects bp using (project_natural_key) "
            "where upper(bp.state) = upper(%(state)s) and bp.bid_date < %(before_date)s "
            "and bp.deleted_at is null",
            {"state": state, "before_date": before_date},
        )
        rows = cur.fetchall()

        # '1' is the only true value -- confirmed against build_candidate_panels.py:84
        # (`registry["Top Competitors Tag"] == "1"`) and live data on 2026-08-09: the naive
        # "is not null and != ''" this replaced also matched the string '0' (889/897 registry rows)
        # and a literal 'Top Competitors Tag' header value sitting in the data as a row, both of
        # which are not tags -- that bug pre-dates this rewrite and was caught by
        # test_candidate_pool_consistency.py showing near-total pool drift.
        cur.execute(
            "select distinct comp_name from scratch.competitor_name_registry "
            "where top_competitors_tag = '1'"
        )
        priority_ids = {r["comp_name"] for r in cur.fetchall() if r["comp_name"]}

    same_county_ids, same_type_ids, recent_90d_ids, winner_ids = set(), set(), set(), set()
    regional_counts: dict[str, int] = {}
    for r in rows:
        cid = r["competitor_unit_id"]
        bid_date = r["bid_date"]
        if target_county and cr.norm_county(r["county"]) == target_county:
            same_county_ids.add(cid)
        if target_type and (r["project_type"] or "").strip().upper() == target_type:
            same_type_ids.add(cid)
        if bid_date is None:
            continue
        if bid_date >= recent_cutoff:
            recent_90d_ids.add(cid)
        if bid_date >= lookback_cutoff:
            regional_counts[cid] = regional_counts.get(cid, 0) + 1
            if r["did_win"]:
                winner_ids.add(cid)

    recurring_ids = {cid for cid, n in regional_counts.items() if n >= V3_RECURRING_REGIONAL_MIN_BIDS}
    in_default_90d = same_county_ids | same_type_ids | recent_90d_ids

    pool = set(in_default_90d)
    for cid in (winner_ids | recurring_ids | priority_ids) - in_default_90d:
        fallback_score = (
            (V3_PRIORITY_WEIGHT if cid in priority_ids else 0.0)
            + (V3_HISTORICAL_WINNER_WEIGHT if cid in winner_ids else 0.0)
            + (V3_RECURRING_REGIONAL_WEIGHT if cid in recurring_ids else 0.0)
        )
        if fallback_score >= V3_FALLBACK_SCORE_THRESHOLD:
            pool.add(cid)

    pool -= CLIENT_UNIT_IDS                              # never predict CSI as its own competitor

    log.info("live candidate pool: %d (default_90d=%d, fallback=%d) for %s/%s before %s",
             len(pool), len(in_default_90d), len(pool) - len(in_default_90d), county, state, before_date)

    if len(pool) < MIN_POOL_SIZE:
        widened = _widen_pool_fallback(conn, state, before_date)
        log.warning(
            "live candidate pool too small (%d < MIN_POOL_SIZE=%d) for %s/%s before %s -- the "
            "registry's priority-tag floor (see MIN_POOL_SIZE's docstring) may have eroded. "
            "Widening to the state-wide bidder pool (%d candidates) as a safety net.",
            len(pool), MIN_POOL_SIZE, county, state, before_date, len(widened),
        )
        pool |= widened

    return pool


def _widen_pool_fallback(conn, state: str, before_date: str) -> set[str]:
    """Emergency-only widening for when _candidate_pool()'s 6-signal result comes back
    suspiciously small (see MIN_POOL_SIZE) -- "everyone who has bid in this state," the same broad
    query the pre-2026-08-09 version of _candidate_pool() always used unconditionally. Deliberately
    NOT the default path anymore (see rough edge 10 in CLAUDE.md for why that was too crude to serve
    as the normal candidate pool) -- this exists purely so a data problem elsewhere (e.g. the
    registry's priority tags being cleared) degrades to "too many candidates" instead of "too few to
    be useful," while still logging loudly so the real cause gets noticed and fixed."""
    with conn.cursor() as cur:
        cur.execute(
            "select distinct br.competitor_unit_id "
            "from scratch.bid_results br join scratch.bid_projects bp using (project_natural_key) "
            "where upper(bp.state) = upper(%(state)s) and bp.bid_date < %(before_date)s "
            "and bp.deleted_at is null",
            {"state": state, "before_date": before_date},
        )
        return {r["competitor_unit_id"] for r in cur.fetchall()} - CLIENT_UNIT_IDS


def _score_candidates(
    conn, candidates: set[str], county: str, state: str, project_type: str | None,
    before_date: str, quantities: dict[str, float], weights: dict[str, float],
    decision_offset: float | None = None,
) -> list[tuple[str, float, float | None]]:
    """One query for every candidate's win history, then the same log1p(win_count)-weighted linear
    combination train_simple_rule_baseline.py::build_simple_rule_score() computes for historical
    projects — just scored against this one ad-hoc project's own county/state/type/quantities
    instead of a training-panel row's. County matching uses competitor_report.norm_county() (an
    exact match on the normalized token — NOT a substring/LIKE match, which produces real false
    positives on this data; see #77's "Clark" -> "CLARKE CO" class of bug)."""
    if not candidates:
        return []
    target_county = cr.norm_county(county)
    target_state = (state or "").strip().upper()
    target_type = (project_type or "").strip().upper() or None
    material_cols = [c for c in _MATERIAL_COLS if quantities.get(c, 0) > 0]

    select_cols = ", ".join(f"bp.{c}" for c in material_cols) if material_cols else "null as _unused"
    with conn.cursor() as cur:
        cur.execute(
            f"select br.competitor_unit_id, br.did_win, bp.county, bp.state, bp.project_type, "
            f"{select_cols} "
            "from scratch.bid_results br join scratch.bid_projects bp using (project_natural_key) "
            "where br.competitor_unit_id = any(%(ids)s) and bp.bid_date < %(before_date)s "
            "and bp.deleted_at is null",
            {"ids": list(candidates), "before_date": before_date},
        )
        rows = cur.fetchall()

    win_county: dict[str, int] = {}
    win_type: dict[str, int] = {}
    win_state: dict[str, int] = {}
    # cid -> material -> [log1p(qty), ...] over this candidate's WON projects with that material present
    material_logs: dict[str, dict[str, list[float]]] = {}

    for r in rows:
        if not r["did_win"]:
            continue
        cid = r["competitor_unit_id"]
        if (r["state"] or "").strip().upper() == target_state:
            win_state[cid] = win_state.get(cid, 0) + 1
        if cr.norm_county(r["county"]) == target_county:
            win_county[cid] = win_county.get(cid, 0) + 1
        if target_type and (r["project_type"] or "").strip().upper() == target_type:
            win_type[cid] = win_type.get(cid, 0) + 1
        for m in material_cols:
            qty = r.get(m)
            if qty and qty > 0:
                material_logs.setdefault(cid, {}).setdefault(m, []).append(log1p(float(qty)))

    # size_fit: this project's active materials vs. each candidate's own historical average
    # (>= MIN_MATERIAL_BIDS qualifying won projects with that material present). Leakage-safe
    # neutral fallback for candidates without enough material history — the population mean of the
    # OTHER candidates' real fit values, same rationale as train_simple_rule_baseline.py's: 0 would
    # be this metric's best possible value, so defaulting to it would silently reward missing data.
    per_cid_fit: dict[str, float] = {}
    for cid in candidates:
        fits = []
        for m in material_cols:
            vals = material_logs.get(cid, {}).get(m, [])
            if len(vals) >= MIN_MATERIAL_BIDS:
                fits.append(-abs(log1p(quantities[m]) - (sum(vals) / len(vals))))
        if fits:
            per_cid_fit[cid] = sum(fits) / len(fits)
    fallback_fit = (sum(per_cid_fit.values()) / len(per_cid_fit)) if per_cid_fit else 0.0

    scored = []
    for cid in candidates:
        score = (
            weights.get("county", 0) * log1p(win_county.get(cid, 0))
            + weights.get("type", 0) * log1p(win_type.get(cid, 0))
            + weights.get("state", 0) * log1p(win_state.get(cid, 0))
            + weights.get("size_fit", 0) * per_cid_fit.get(cid, fallback_fit)
        )
        # sigmoid(score + offset) is a strictly monotonic function of score (see
        # _decision_offset()'s docstring) -- adding it here never changes the sort below.
        prob = _sigmoid(score + decision_offset) if decision_offset is not None else None
        scored.append((cid, score, prob))

    scored.sort(key=lambda t: t[1], reverse=True)
    return scored


def predict_report(
    county: str, state: str, project_type: str | None, bid_date: str,
    quantities: dict[str, float], source_id: str, top_n: int = 5,
) -> dict | None:
    """Live-inference analogue of the CI corpus lookup, for a project with no history of its own —
    builds its own candidate pool and scores it from live Postgres data instead of matching an
    existing ranking_predictions.csv row. Returns the SAME dict shape
    competitor_live.live_report() does (every key present, just
    empty except `competitors`/`summary`), so every downstream consumer — the manual-competitor
    merge, competitor_stats_live.compute_stats(), render_markdown(), report-card.tsx — works
    completely unmodified; they cannot tell a predicted list from a matched one.

    None (never raises) if state is blank, the weights file is missing/unfit, or any query fails.
    """
    if not state:
        return None
    loaded = _load_weights()
    if not loaded:
        return None
    weights, decision_offset = loaded
    # A genuinely new plan often has no extracted construction_start/end yet -- this is exactly the
    # case this module exists for, so a blank bid_date must not be fatal. `before_date` only exists
    # to keep the candidate pool leakage-safe (no future bid data); "today" is the correct neutral
    # cutoff when the actual letting date isn't known yet. Passing "" straight into the Postgres
    # date comparisons below raised "invalid input syntax for type date" and was silently swallowed
    # by the except below, so a missing date looked identical to "no candidates found."
    before_date = bid_date or datetime.date.today().isoformat()
    try:
        with ci_db.get_conn() as conn:
            candidates = _candidate_pool(conn, county, state, project_type, before_date)
            scored = _score_candidates(conn, candidates, county, state, project_type, before_date,
                                       quantities, weights, decision_offset)
    except Exception as e:                                    # noqa: BLE001 — must never break assembly
        log.warning("predict_report: query failed, no live prediction: %s", e)
        return None

    top = scored[:top_n]
    names = [cid for cid, _, _ in top]
    attrs = {cid: {"Predicted probability": f"{prob:.0%}"} for cid, _, prob in top if prob is not None}
    location = ", ".join(p for p in (county, state) if p)
    return {
        "project_id": source_id, "location": location, "county": county, "state": state,
        "bid_date": bid_date, "work_type": project_type or "", "condition": "", "materials": [],
        "pits": {}, "summary": {"analyzed": len(names), "narrative": ""},
        "competitors": names, "attrs": attrs, "deep_dives": {}, "source_file": "",
        "_match": {"confidence": "predicted",
                   "basis": "live candidate model, no CI corpus match", "date_gap_days": None},
    }
