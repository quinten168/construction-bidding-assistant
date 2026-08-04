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
    """Load their projects table once (project_natural_key, bid_date, state, county). pandas is
    already a dep."""
    import pandas as pd
    df = pd.read_csv(CI_PROJECTS_CSV,
                     usecols=["project_natural_key", "bid_date", "state", "county"],
                     dtype=str).fillna("")
    df["_county"] = df["county"].map(cr.norm_county)
    df["_state"] = df["state"].map(cr.norm_state)
    return df


def _date_gap_days(a: str, b: str) -> int:
    import datetime as dt
    try:
        return abs((dt.date.fromisoformat(a[:10]) - dt.date.fromisoformat(b[:10])).days)
    except Exception:
        return 10_000


def find_project_key(county: str, state: str, bid_date: str | None) -> tuple[str, int] | None:
    """Reverse-lookup a plan's (county, state, [bid_date]) to the CI corpus project_natural_key.
    Returns (project_natural_key, date_gap_days) for the county+state match nearest in date, or
    None if no county+state hit exists (we do NOT fall back to state-only here — a wrong project
    would generate a wrong report)."""
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


def live_report(county: str, state: str, bid_date: str | None) -> dict | None:
    """Full live path: reverse-lookup → generate → parse. Returns a parsed report dict with a
    `_match` block tagged basis='live-generated', or None so the caller falls back to static match."""
    if not (settings.ci_live_enabled and available()):
        return None
    ensure_fresh_local_data()
    found = find_project_key(county, state, bid_date)
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
    # a live report generated FOR this project is a high-confidence match (we looked it up by identity)
    conf = "high" if (bid_date is None or gap <= 45) else "medium"
    parsed["_match"] = {"confidence": conf, "basis": "live-generated", "date_gap_days": gap}
    log.info("ci live: generated fresh report for %s (project %s, gap %sd)", county, project_key, gap)
    return parsed
