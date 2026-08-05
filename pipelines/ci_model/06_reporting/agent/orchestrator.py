#!/usr/bin/env python3
"""
CSI Bid Intelligence Agent — Orchestrator

Sequential pipeline: Planner → Executor → Reflector → Reporter → Export

Identified by project_natural_key (e.g. MN_STEARNS_CO_MELROSE_2023-08-03). There used to also be
a job_id column (CSI's local CSV row id, renumbered by row-sort-position on every regeneration of
projects.csv/ranking_predictions.csv, not stable across pipeline runs) -- removed entirely.
project_natural_key is deterministic (state_county_city_date[_N]) and stays the same across
regenerations, which is what the live app's report cache (apps/api/backend/competitor_live.py)
depends on.

Usage:
    # From the repo root
    python pipelines/ci_model/06_reporting/agent/orchestrator.py --project-key MN_STEARNS_CO_MELROSE_2023-08-03

    # Skip LLM calls (deterministic output only, no API key needed)
    python pipelines/ci_model/06_reporting/agent/orchestrator.py --project-key MN_STEARNS_CO_MELROSE_2023-08-03 --skip-llm

    # Top 15 competitors, docx export
    python pipelines/ci_model/06_reporting/agent/orchestrator.py \\
        --project-key MN_STEARNS_CO_MELROSE_2023-08-03 --top-n 15 --format docx
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import pandas as pd

# ── Path setup ────────────────────────────────────────────────────────────────
_REPORTING_DIR = Path(__file__).resolve().parent.parent   # …/06_reporting/
_REPO_ROOT     = _REPORTING_DIR.parent.parent.parent      # …/csi-bid-intelligence/
sys.path.insert(0, str(_REPORTING_DIR))

# ── Defaults ──────────────────────────────────────────────────────────────────
_DEFAULT_PREDICTIONS = str(
    _REPO_ROOT / "ci_model/competitor_prediction_model/03_training/outputs/ranking_predictions.csv"
)
_DEFAULT_MODEL = str(
    _REPO_ROOT / "ci_model/competitor_prediction_model/03_training/outputs/simple_rule_baseline_weights.json"
)
_DEFAULT_REGISTRY = str(
    _REPO_ROOT / "ci_model/competitor_prediction_model/01_candidates/outputs/competitor_name_registry - name_variants.csv"
)
_DEFAULT_BIDDER_RESULTS = str(
    _REPO_ROOT / "data/processed/bidder_results.csv"
)
_DEFAULT_PROJECTS = str(
    _REPO_ROOT / "data/processed/projects.csv"
)
_DEFAULT_OUTPUT_DIR = str(_REPORTING_DIR / "outputs/reports")
_LLM_MODEL = "claude-sonnet-4-6"


def _build_name_lookup(registry_path: str, bidder_results_path: str) -> dict[str, str]:
    """Build {competitor_unit_id: comp_name} using registry comp_name as the canonical label."""
    try:
        registry = pd.read_csv(registry_path)
        bidder_results = pd.read_csv(
            bidder_results_path, usecols=["competitor_unit_id", "raw_bidder_name"]
        )
        name_map = (
            registry[["raw_name_variant", "comp_name"]]
            .dropna(subset=["comp_name"])
            .assign(raw_name_variant=lambda df: df["raw_name_variant"].str.upper())
            .drop_duplicates("raw_name_variant")
            .set_index("raw_name_variant")["comp_name"]
            .to_dict()
        )
        lookup: dict[str, str] = {}
        for uid, grp in bidder_results.groupby("competitor_unit_id"):
            for raw in grp["raw_bidder_name"].dropna().str.upper():
                if raw in name_map:
                    lookup[str(uid)] = name_map[raw]
                    break
        return lookup
    except Exception:
        return {}


def _resolve_tiers(
    project_rows: pd.DataFrame,
    registry_path: str,
    bidder_results_path: str,
) -> pd.DataFrame:
    """
    Add a 'tier' column to project_rows: 1 = priority (Top Competitors Tag = 1), 2 = discovery.
    Uses the same logic as evaluate_ranking.py.
    """
    import numpy as np

    try:
        registry = pd.read_csv(registry_path)
        top_variants = set(
            registry[registry["Top Competitors Tag"].astype(str) == "1"]["raw_name_variant"]
            .dropna().str.upper()
        )
        bidder_results = pd.read_csv(bidder_results_path, usecols=["competitor_unit_id", "raw_bidder_name"])
        priority_ids = set(
            bidder_results[bidder_results["raw_bidder_name"].str.upper().isin(top_variants)]
            ["competitor_unit_id"].dropna().astype(str)
        )
        project_rows = project_rows.copy()
        project_rows["tier"] = np.where(
            project_rows["competitor_unit_id"].isin(priority_ids), 1, 2
        )
    except Exception as e:
        print(f"  [warn] Could not resolve tiers ({e}); treating all as discovery.")
        project_rows = project_rows.copy()
        project_rows["tier"] = 2

    return project_rows


def _load_client(skip_llm: bool):
    if skip_llm:
        return None
    try:
        from dotenv import load_dotenv
        load_dotenv(dotenv_path=_REPO_ROOT / ".env")
    except ImportError:
        pass

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("  [warn] ANTHROPIC_API_KEY not set — running without LLM (--skip-llm mode).")
        return None

    import anthropic
    return anthropic.Anthropic(api_key=api_key)


def run_report(
    project_key: str,
    predictions_path: str = _DEFAULT_PREDICTIONS,
    model_path: str = _DEFAULT_MODEL,
    registry_path: str = _DEFAULT_REGISTRY,
    bidder_results_path: str = _DEFAULT_BIDDER_RESULTS,
    output_dir: str = _DEFAULT_OUTPUT_DIR,
    top_n: int = 5,
    skip_llm: bool = False,
    fmt: str = "md",
    verbose: bool = True,
) -> Path:
    """
    Run the full Bid Intelligence pipeline for one project.

    project_key is a project_natural_key (see module docstring) -- stable across pipeline
    regenerations.

    Returns the path to the generated report file.
    """
    from agent.planner   import plan
    from agent.executor  import execute_all
    from agent.reflector import reflect
    from agent.reporter  import build_report
    from tools.export_report import export_report

    # ── Load data ─────────────────────────────────────────────────────────────
    if verbose:
        print(f"\n{'='*60}")
        print(f"  CSI Bid Intelligence Agent")
        print(f"  Project: {project_key}")
        print(f"{'='*60}")

    predictions = pd.read_csv(predictions_path)
    project_rows = predictions[predictions["project_natural_key"] == project_key].copy()

    if project_rows.empty:
        raise ValueError(f"No rows found for project_natural_key='{project_key}' in {predictions_path}")

    # Merge project-level mix_tons + coordinates from projects.csv; build tons_lookup for capacity
    _lat, _lon = None, None
    _tons_lookup: dict[str, float] = {}
    try:
        projects_df = pd.read_csv(
            _DEFAULT_PROJECTS,
            usecols=["project_natural_key", "mix_tons", "project_latitude", "project_longitude"],
        )
        proj_row = projects_df[projects_df["project_natural_key"] == project_key].iloc[0]
        mix_tons_val = proj_row["mix_tons"]
        project_rows["mix_tons"] = float(mix_tons_val) if not pd.isna(mix_tons_val) else 0.0
        import math
        lat_raw = proj_row.get("project_latitude")
        lon_raw = proj_row.get("project_longitude")
        _lat = None if (lat_raw is None or (isinstance(lat_raw, float) and math.isnan(lat_raw))) else float(lat_raw)
        _lon = None if (lon_raw is None or (isinstance(lon_raw, float) and math.isnan(lon_raw))) else float(lon_raw)
        # Build {project_natural_key: mix_tons} lookup for all projects (capacity season-tons calc)
        _tons_lookup = {
            str(r["project_natural_key"]): float(r["mix_tons"]) if not pd.isna(r["mix_tons"]) else 0.0
            for _, r in projects_df.iterrows()
        }
    except Exception:
        project_rows["mix_tons"] = 0.0

    # ── Tier resolution (priority vs discovery) ───────────────────────────────
    project_rows = _resolve_tiers(project_rows, registry_path, bidder_results_path)
    name_lookup  = _build_name_lookup(registry_path, bidder_results_path)
    tier1_count = int((project_rows["tier"] == 1).sum())
    if verbose:
        print(f"  Tier 1 (priority): {tier1_count}  |  Tier 2 (discovery): {len(project_rows) - tier1_count}")

    model = json.loads(Path(model_path).read_text())

    first_row = project_rows.iloc[0]
    # "state"/"county" on project_rows hold the simple-rule model's numeric input features, not
    # the project's actual state/county abbreviation -- see train_simple_rule_baseline.py's
    # project_state/project_county comment for why. Read the preserved identity columns instead.
    project_info = {
        "project_natural_key": project_key,
        "state":        str(first_row.get("project_state", "—")),
        "county":       str(first_row.get("project_county", "—")),
        "project_type": str(first_row.get("project_type", "—")),
        "bid_date":     str(first_row.get("bid_date", "—")),
        "lat":          _lat,
        "lon":          _lon,
    }

    if verbose:
        print(f"  Location:  {project_info['county']}, {project_info['state']}")
        print(f"  Type:      {project_info['project_type']}")
        print(f"  Bid date:  {project_info['bid_date']}")
        print(f"  Candidates in pool: {len(project_rows)}")

    client = _load_client(skip_llm)
    if verbose:
        mode = "LLM-enhanced" if client else "deterministic (no LLM)"
        print(f"  Mode:      {mode}")

    # ── Planner ───────────────────────────────────────────────────────────────
    if verbose:
        print(f"\n[1/4] Planner — selecting top {top_n} competitors...")
    competitor_ids = plan(project_rows, top_n=top_n)
    if verbose:
        print(f"  Total selected: {len(competitor_ids)}")

    # ── Live capacity (one batched query for the whole shortlist, not one per competitor) ──────
    # Fail-open: any connection/query error falls back to the local ranking_predictions.csv +
    # tons_lookup computation executor.py already had -- see tools/capacity_live.py's docstring.
    from tools import capacity_live
    live_capacity_df = None
    try:
        with capacity_live.connect() as conn:
            live_capacity_df = capacity_live.fetch_capacity_history(
                competitor_ids, str(project_info["bid_date"]), conn,
            )
        if verbose:
            print(f"  Live capacity: fetched {len(live_capacity_df)} historical bid row(s) "
                  f"from Supabase for {len(competitor_ids)} competitor(s)")
    except Exception as e:
        if verbose:
            print(f"  [warn] live capacity fetch failed, using local fallback: {e}")

    # ── Executor ──────────────────────────────────────────────────────────────
    if verbose:
        print(f"\n[2/4] Executor — running predictions and narratives...")
    analyses = execute_all(
        competitor_ids, project_rows, model, client, _LLM_MODEL,
        verbose=verbose, name_lookup=name_lookup, all_predictions=predictions,
        tons_lookup=_tons_lookup, live_capacity_df=live_capacity_df,
    )
    if verbose:
        print(f"  Completed: {len(analyses)} analyses")

    # ── Reflector ─────────────────────────────────────────────────────────────
    if verbose:
        print(f"\n[3/4] Reflector — quality checking narratives...")
    for i, analysis in enumerate(analyses):
        analyses[i] = reflect(analysis, client, _LLM_MODEL, verbose=verbose)
    flagged = sum(1 for a in analyses if a.get("reflection_passed") is False)
    if verbose and flagged:
        print(f"  {flagged} narrative(s) flagged for human review.")

    # ── Reporter ──────────────────────────────────────────────────────────────
    if verbose:
        print(f"\n[4/4] Reporter — assembling report...")
    report_text = build_report(
        project_info = project_info,
        analyses     = analyses,
        model_meta   = model,
        client       = client,
        llm_model    = _LLM_MODEL,
    )

    # ── Export ────────────────────────────────────────────────────────────────
    out_path = Path(output_dir) / f"bid_report_{project_key}"
    out_file = export_report(report_text, out_path, fmt=fmt)

    if verbose:
        print(f"\n{'='*60}")
        print(f"  Report saved: {out_file}")
        print(f"{'='*60}\n")

    return out_file


def main() -> None:
    parser = argparse.ArgumentParser(
        description="CSI Bid Intelligence Agent — generate a competitor report for a project."
    )
    parser.add_argument(
        "--project-key", required=True,
        help="project_natural_key to analyze (e.g. MN_STEARNS_CO_MELROSE_2023-08-03)"
    )
    parser.add_argument(
        "--predictions", default=_DEFAULT_PREDICTIONS,
        help="Path to ranking_predictions.csv"
    )
    parser.add_argument(
        "--model", default=_DEFAULT_MODEL,
        help="Path to logistic_baseline_model.json"
    )
    parser.add_argument(
        "--registry", default=_DEFAULT_REGISTRY,
        help="Path to competitor_name_registry CSV (for tier resolution)"
    )
    parser.add_argument(
        "--bidder-results", default=_DEFAULT_BIDDER_RESULTS,
        help="Path to bidder_results.csv (for tier resolution)"
    )
    parser.add_argument(
        "--output-dir", default=_DEFAULT_OUTPUT_DIR,
        help="Directory for output reports"
    )
    parser.add_argument(
        "--top-n", type=int, default=5,
        help="Number of competitors to include (default: 5)"
    )
    parser.add_argument(
        "--skip-llm", action="store_true",
        help="Skip all LLM calls; produce deterministic output only"
    )
    parser.add_argument(
        "--format", choices=["md", "docx"], default="md", dest="fmt",
        help="Output format: md (default) or docx"
    )
    parser.add_argument(
        "--quiet", action="store_true",
        help="Suppress progress output"
    )
    args = parser.parse_args()

    run_report(
        project_key          = args.project_key,
        predictions_path     = args.predictions,
        model_path           = args.model,
        registry_path        = args.registry,
        bidder_results_path  = args.bidder_results,
        output_dir           = args.output_dir,
        top_n                = args.top_n,
        skip_llm             = args.skip_llm,
        fmt                  = args.fmt,
        verbose              = not args.quiet,
    )


if __name__ == "__main__":
    main()
