"""
Live competitor-report generation.

The Competitor Intel team's agent (`06_reporting/agent/orchestrator.py`) generates a fresh
`bid_report_<project_natural_key>.md` for any project already in their pre-computed corpus — ~1s
with `--skip-llm`, ~5-15s with the LLM narrative. This module is the seam that lets a *dropped
plan* trigger that generation live, instead of matching a stale static report:

  1. `find_project_key(county, state, bid_date)` — reverse-lookup a plan's identity to their
     `project_natural_key` (their `projects.csv` has no shared key with our data, but it DOES
     carry county+state+bid_date). Deliberately not job_id: that's CSI's local CSV row id,
     renumbered by row-sort-position on every regeneration of their pipeline, so a report cached
     under an old job_id number could silently correspond to a *different* project after a
     regeneration. project_natural_key (state_county_city_date[_N]) is stable across runs.
  2. `generate(project_key)` — invoke their orchestrator as a subprocess, writing the fresh report
     into our `COMPETITOR_REPORTS` dir so the existing matcher/parser picks it up.
  3. `live_report(county, state, bid_date)` — do both, parse the fresh file, and return the parsed
     dict with a `_match` block tagged `live`. Returns None (caller falls back to static match) if
     the plan isn't in the corpus, the repo isn't present, or generation fails/times out.

Fail-safe by design: any error returns None so a PDF drop never breaks on the competitor step.
"""
from __future__ import annotations

import os
import subprocess
import sys
from functools import lru_cache
from pathlib import Path

from . import competitor_report as cr
from .config import (CI_BIDDER_RESULTS, CI_MODEL_JSON, CI_MODEL_REPO, CI_ORCHESTRATOR,
                     CI_PREDICTIONS_CSV, CI_PROJECTS_CSV, CI_REGISTRY_CSV, COMPETITOR_REPORTS,
                     PULL_SCRATCH_SCRIPT, settings)
from .observability import get_logger, timed

log = get_logger("bid_assistant.competitor_live")


def ensure_fresh_local_data() -> None:
    """Refresh data/processed/*.csv + the registry from Supabase's `scratch.*` before a live
    report reads them, so admin-UI edits (bid-results entry, pit-list CRUD, competitor-registry
    CRUD) actually reach a report instead of being stranded in Supabase (see
    docs/ARCHITECTURE.md §9's "no path back" gap). Fail-safe by design, same as the rest of this
    module: any error here just means the report uses whatever local data already exists on
    disk, identical to today's behavior. Never raises."""
    if not settings.supabase_team_db_url:
        return
    try:
        check = subprocess.run([sys.executable, str(PULL_SCRATCH_SCRIPT), "--check-only"],
                               capture_output=True, timeout=5)
        if check.returncode == 0:
            return  # already fresh
        subprocess.run([sys.executable, str(PULL_SCRATCH_SCRIPT), "--all"],
                       capture_output=True, timeout=30, check=True)
        _projects.cache_clear()
    except Exception as e:                                   # noqa: BLE001 — must never block a report
        log.warning("scratch data refresh failed, using existing local data: %s", e)


def available() -> bool:
    """True when the CI model repo + orchestrator + projects table are all present on disk."""
    return CI_ORCHESTRATOR.exists() and CI_PROJECTS_CSV.exists()


@lru_cache(maxsize=1)
def _projects():
    """Load their projects table once (project_natural_key, bid_date, state, county, project_type).
    pandas is already a dep. project_type uses the same six labels as the plan pipeline's archetype
    (verified 2026-08-09: `project_registry._archetype()`'s outputs match projects.csv's
    project_type values exactly), which is what makes find_project_key's type gate a direct
    comparison instead of a mapping problem."""
    import pandas as pd
    df = pd.read_csv(CI_PROJECTS_CSV,
                     usecols=["project_natural_key", "bid_date", "state", "county", "project_type"],
                     dtype=str).fillna("")
    df["_county"] = df["county"].map(cr.norm_county)
    df["_state"] = df["state"].map(cr.norm_state)
    df["_work_type"] = df["project_type"].map(cr.norm_work_type)
    return df


def _date_gap_days(a: str, b: str) -> int:
    import datetime as dt
    try:
        return abs((dt.date.fromisoformat(a[:10]) - dt.date.fromisoformat(b[:10])).days)
    except Exception:
        return 10_000


def find_project_key(county: str, state: str, bid_date: str | None,
                     project_type: str | None = None,
                     plan_id: str | None = None) -> tuple[str, int] | None:
    """Reverse-lookup a plan's (county, state, [bid_date]) to the CI corpus project_natural_key.
    Returns (project_natural_key, date_gap_days) for the county+state match nearest in date, or
    None if no county+state hit exists (we do NOT fall back to state-only here — a wrong project
    would generate a wrong report).

    `project_type` (the plan's archetype) + `plan_id` (for the log line) feed the work-type gate:
    if candidates exist within MATCH_REVIEW_GAP_DAYS but NONE of them shares the plan's work type,
    the match is a likely wrong project — same-county same-week lettings are routinely DIFFERENT
    projects (CLAUDE.md rough edge 11: 169 exact same-day collisions, 63% differing in type, ~80%
    median material-quantity difference; human sampling of the collision cases confirmed genuine
    mismatches, not archetype-extraction errors, which is why 'enforce' hard-refuses rather than
    soft-warns). Behavior per settings.type_gate_mode: 'off' = no detection; 'log_only' (default) =
    log would_reject + return the match unchanged; 'enforce' = return None so the cascade falls
    through to live prediction. This gate is an INDEPENDENT detector from live_report's
    needs_review (that one catches "too far in time", this one "near but nothing looks like this
    plan") — keep them separately toggleable and separately countable. It never fires when the
    type is unknown/'Other' (norm_work_type -> ''), when bid_date is missing, or when no candidate
    is within the window (the FAR-ONLY bucket keeps its needs_review path instead)."""
    if not available():
        return None
    nc, ns = cr.norm_county(county), cr.norm_state(state)
    if not nc or not ns:
        return None
    df = _projects()
    hits = df[(df["_state"] == ns) & (df["_county"] == nc)]
    if hits.empty:
        return None
    if bid_date:
        gaps = hits["bid_date"].map(lambda d: _date_gap_days(d, bid_date))
        mode = settings.type_gate_mode
        nt = cr.norm_work_type(project_type or "") if mode in ("log_only", "enforce") else ""
        if nt:
            near = hits[gaps <= cr.MATCH_REVIEW_GAP_DAYS]
            if not near.empty and not (near["_work_type"] == nt).any():
                log.warning(
                    "type gate (%s): plan=%s reason=type_all_excluded layer=1-live %d corpus "
                    "project(s) within %dd of %s/%s (%s) but none matches work type %r "
                    "(rejected: %s, types: %s)",
                    "reject" if mode == "enforce" else "would_reject", plan_id,
                    len(near), cr.MATCH_REVIEW_GAP_DAYS, county, state, bid_date, project_type,
                    sorted(near["project_natural_key"]), sorted(set(near["project_type"])))
                if mode == "enforce":
                    return None
        i = gaps.idxmin()
        return (df.loc[i, "project_natural_key"], int(gaps.loc[i]))
    return (hits.iloc[0]["project_natural_key"], 10_000)


def generate(project_key: str, skip_llm: bool | None = None, timeout: int | None = None) -> Path | None:
    """Invoke the CI orchestrator as a subprocess to (re)generate `bid_report_<project_key>.md`
    into our COMPETITOR_REPORTS dir. Returns the path on success, None on failure/timeout."""
    if not available():
        return None
    skip = settings.ci_live_skip_llm if skip_llm is None else skip_llm
    tmo = settings.ci_live_timeout if timeout is None else timeout
    COMPETITOR_REPORTS.mkdir(parents=True, exist_ok=True)
    out = COMPETITOR_REPORTS / f"bid_report_{project_key}.md"

    # --predictions / --model / --registry / --bidder-results look redundant (the orchestrator
    # defines defaults for all four) but are load-bearing — do not "clean up". Its defaults resolve to
    # `ci_model/competitor_prediction_model/…`, the layout of the old standalone csi-ci-model clone.
    # That path has never existed in this repo, where ci_model is flat under pipelines/. Passing the
    # real paths from here fixes it without editing CI-team code, which would only create conflicts
    # for the update_data_pipeline rebase. Delete these flags and live generation fails silently:
    # the caller falls back to a stale static report, so the UI still renders and nothing looks wrong.
    cmd = [sys.executable, str(CI_ORCHESTRATOR), "--project-key", project_key,
           "--predictions", str(CI_PREDICTIONS_CSV),
           "--model", str(CI_MODEL_JSON),
           "--registry", str(CI_REGISTRY_CSV),
           "--bidder-results", str(CI_BIDDER_RESULTS),
           "--output-dir", str(COMPETITOR_REPORTS), "--quiet"]
    if skip:
        cmd.append("--skip-llm")
    env = dict(os.environ)
    if settings.anthropic_api_key and "ANTHROPIC_API_KEY" not in env:
        env["ANTHROPIC_API_KEY"] = settings.anthropic_api_key
    try:
        with timed(log, f"ci live-generate {project_key} (skip_llm={skip})"):
            # cwd = this repo's root: the orchestrator still resolves some paths relative to _REPO_ROOT
            subprocess.run(cmd, cwd=str(CI_MODEL_REPO), env=env, check=True,
                           capture_output=True, timeout=tmo)
    except subprocess.TimeoutExpired:
        log.warning("ci live-generate %s timed out after %ds", project_key, tmo)
        return None
    except subprocess.CalledProcessError as e:
        log.warning("ci live-generate %s failed: %s", project_key, (e.stderr or b"")[:400])
        return None
    except Exception as e:                                   # noqa: BLE001
        log.warning("ci live-generate %s error: %s", project_key, e)
        return None
    return out if out.exists() else None


# A match this far apart in time, or with no date to disambiguate at all (find_project_key's
# gap=10_000 sentinel when bid_date is None), is not safe to auto-trust: 59% of (state, county)
# pairs in data/processed/projects.csv have more than one historical project, and county+state+date
# alone is NOT a unique identifier -- see CLAUDE.md rough edge 11 for the collision statistics that
# justified this threshold (169 exact same-day, same-county collisions between genuinely different
# projects, out of 1591 total; 28% of same-county project pairs sit within 7 days of each other).
MATCH_REVIEW_GAP_DAYS = 45


def live_report(county: str, state: str, bid_date: str | None,
                project_type: str | None = None, plan_id: str | None = None) -> dict | None:
    """Full live path: reverse-lookup → generate → parse. Returns a parsed report dict with a
    `_match` block tagged basis='live-generated', or None so the caller falls back to static match.
    `project_type`/`plan_id` feed find_project_key's work-type gate (see its docstring)."""
    if not (settings.ci_live_enabled and available()):
        return None
    ensure_fresh_local_data()
    found = find_project_key(county, state, bid_date, project_type=project_type, plan_id=plan_id)
    if not found:
        log.info("ci live: no corpus project for %s/%s (%s) — falling back to static", county, state, bid_date)
        return None
    project_key, gap = found
    path = generate(project_key)
    if not path:
        return None
    try:
        parsed = cr.parse_report(path)
    except Exception as e:                                   # noqa: BLE001
        log.warning("ci live: parse failed for %s: %s", project_key, e)
        return None
    # Was: `"high" if (bid_date is None or gap <= 45) else "medium"` -- that treated "we have no
    # date at all to disambiguate this county" as HIGHER confidence than "we have a date and it's
    # close," which is backwards. gap is find_project_key's 10_000 sentinel when bid_date is None,
    # so this single comparison now handles both cases correctly without a special case.
    needs_review = gap > MATCH_REVIEW_GAP_DAYS
    conf = "medium" if needs_review else "high"
    parsed["_match"] = {"confidence": conf, "basis": "live-generated", "date_gap_days": gap,
                        "needs_review": needs_review}
    if needs_review:
        log.warning("ci live: match for %s/%s needs review — nearest corpus project %s is %sd away "
                   "(county+state alone is not a unique identifier, see CLAUDE.md rough edge 11)",
                   county, state, project_key, gap)
    log.info("ci live: generated fresh report for %s (project %s, gap %sd)", county, project_key, gap)
    return parsed
