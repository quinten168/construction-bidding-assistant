"""
Central configuration for the Bid Assistant.

Everything that differs between local development and a deployed container lives here as an
environment variable with a sensible default — so the app is 12-factor / deploy-ready without
touching code. On Railway you'd set these in the dashboard; locally they fall back to defaults
and the project's existing `.env` convention.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

# --- where things live --------------------------------------------------------------------------
# We reuse the existing Plan Reader RAG backend (Chroma store + retriever) rather than rebuild it,
# so we need to know where that module is on disk.
HERE = Path(__file__).resolve()


def _find_repo_root(start: Path) -> Path:
    """Walk up to the directory containing `.git`.

    Was `HERE.parents[3]`, which silently resolved to the wrong directory whenever this
    file changed depth — and the comment still said `.../01_Summer_2026`, from before the
    module was ported out of the personal repo. Depth-counting survived the apps/ move by
    coincidence, not design; a marker makes it move-proof.
    """
    for candidate in (start, *start.parents):
        if (candidate / ".git").exists():
            return candidate
    return start.parents[3]  # last-resort fallback: preserves the historical behaviour


REPO = _find_repo_root(HERE)
PLAN_READER = REPO / "pipelines" / "plan_reader"
PIPELINE = PLAN_READER / "01_pipeline"                  # importable: lib.py, retriever.py
# The single source of truth for the master bid CSV. Previously duplicated verbatim across
# bid_data.py, competitors.py and project_registry.py — so a path change fixed one and broke
# three, which is the most confusing failure mode available. They now import this.
MASTER_CSV = REPO / "data" / "reference" / "2026-06-03_csi_bid_master.csv"
# Competitor Intelligence reports (Quentin/Wenyu's pipeline output). The final report parses +
# matches these `bid_report_P*.md` files to a plan. They can be pre-generated (static) OR generated
# LIVE by invoking the CI team's agent (see CI_MODEL_REPO below) when a plan maps to a corpus job.
COMPETITOR_REPORTS = REPO / "pipelines" / "ci_model" / "reports"

# --- live competitor generation (the CI model, now in-repo) -------------------------------------
# Their agent (`06_reporting/agent/orchestrator.py::run_report`) generates a fresh report for any
# job_id already in their pre-computed corpus in ~1s (--skip-llm) / ~5-15s (with LLM). We invoke it
# as a subprocess and drop the output into COMPETITOR_REPORTS so the matcher picks up the fresh file.
#
# This used to shell out to a separate clone at ~/dev/csi-ci-model — an undeclared runtime
# dependency on a directory outside the repo, pinned to a 2026-06-30 checkout. Now that ci_model
# lives at pipelines/ci_model, the *code* resolves in-repo.
#
# A fresh clone still needs ONE artifact that git does not carry:
# 03_training/outputs/ranking_predictions.csv (~94 MB, gitignored as a regenerable training
# output). Without it the orchestrator fails and live_report() returns None, so apps/api falls
# back to a stale static report — the UI renders and nothing appears broken. See
# pipelines/ci_model/README.md for how to regenerate or recover it.
#
# Note the path is one level shorter than before. The external clone nested everything under
# `ci_model/competitor_prediction_model/`; in-repo the layout is flat (`ci_model/06_reporting/...`).
# Verified at repoint: orchestrator.py byte-identical across the two; 5 dependency files differ
# (reporter, narrative templates/tools, shared/config) — both trees internally self-consistent.
CI_MODEL_REPO = Path(os.environ.get("CI_MODEL_REPO", str(REPO)))
# Full-path override, because the external clone's internal layout differs — pointing CI_MODEL_REPO
# at it is not enough on its own.
CI_ORCHESTRATOR = Path(os.environ.get(
    "CI_ORCHESTRATOR",
    str(REPO / "pipelines" / "ci_model" / "06_reporting" / "agent" / "orchestrator.py")))
# These stay in data/processed/ — a tracked, coherent 13-file directory. An earlier pass moved
# just these two to data/reference/, which split the directory and broke the orchestrator: it
# resolves _REPO_ROOT/"data/processed/projects.csv" internally and has no --projects flag to
# override. The concern behind that move was "don't let runtime inputs land somewhere gitignored";
# data/processed/ is tracked and always has been, so leaving them here satisfies it in full.
CI_PROJECTS_CSV = REPO / "data" / "processed" / "projects.csv"
# The orchestrator's own --model/--registry defaults point at the old external-clone layout
# (`ci_model/competitor_prediction_model/…`), which has never existed here. competitor_live.py
# passes these explicitly so we fix the paths without editing CI-team code.
CI_PREDICTIONS_CSV = REPO / "pipelines" / "ci_model" / "03_training" / "outputs" / "ranking_predictions.csv"
CI_MODEL_JSON = REPO / "pipelines" / "ci_model" / "03_training" / "outputs" / "logistic_baseline_model.json"
CI_REGISTRY_CSV = (REPO / "pipelines" / "ci_model" / "01_candidates" / "outputs"
                   / "competitor_name_registry - name_variants.csv")
# Authoritative bidder × project outcomes (every bidder, county, win) — backs the competitor_record
# chat tool. Broader than the CSI-centric master CSV (which only covers projects CSI also bid on).
CI_BIDDER_RESULTS = REPO / "data" / "processed" / "bidder_results.csv"


def _load_api_key() -> str:
    """Anthropic key resolution, in priority order:
    1. the ANTHROPIC_API_KEY env var (how you'd set it on Railway), else
    2. the project's existing single-quoted `.env` file in plan_reader (local convention).
    """
    if key := os.environ.get("ANTHROPIC_API_KEY"):
        return key
    env_file = PLAN_READER / ".env"
    if env_file.exists():
        # the project stores the key as ANTHROPIC_API_KEY='sk-...'; split on the quote.
        return env_file.read_text().split("'")[1]
    return ""


@dataclass(frozen=True)
class Settings:
    """Immutable, env-driven settings. Read once at import time."""
    anthropic_api_key: str = _load_api_key()

    # Models — Sonnet for both the answer and the (cheap) query-rewrite step. Override per-env.
    chat_model: str = os.environ.get("BID_CHAT_MODEL", "claude-sonnet-4-6")
    rewrite_model: str = os.environ.get("BID_REWRITE_MODEL", "claude-sonnet-4-6")

    # Retrieval + conversation knobs.
    retrieve_k: int = int(os.environ.get("BID_RETRIEVE_K", "6"))        # passages per question
    max_history_turns: int = int(os.environ.get("BID_MAX_HISTORY", "8"))  # turns kept in memory
    answer_max_tokens: int = int(os.environ.get("BID_ANSWER_MAX_TOKENS", "900"))

    # Live competitor generation. When a dropped plan maps to a job in the CI corpus, invoke their
    # agent live for a FRESH report instead of matching a stale static one. Default skip_llm=True →
    # ~1s, deterministic, free, and produces the same structured tiers + attributes we render.
    # (The CI team's LLM-narrative path currently crashes in reflector.py — an unescaped `{}` in the
    # reflection prompt template throws KeyError — so we don't call it by default; set CI_LIVE_SKIP_LLM=0
    # once they fix it to get the polished narrative.) On timeout/failure we fall back to the static
    # matched report, so this can't break a PDF drop.
    ci_live_enabled: bool = os.environ.get("CI_LIVE_ENABLED", "1") not in ("0", "false", "False")
    ci_live_skip_llm: bool = os.environ.get("CI_LIVE_SKIP_LLM", "1") not in ("0", "false", "False")
    ci_live_timeout: int = int(os.environ.get("CI_LIVE_TIMEOUT", "120"))

    # Conversation capture (see backend/trace.py). Empty = use the local SQLite csi_v2.db + JSONL.
    # Set CONVERSATION_DB_URL to a Postgres DSN when we deploy multi-user (same schema → JSONB);
    # the per-day JSONL archive is written in both worlds.
    conversation_db_url: str = os.environ.get("CONVERSATION_DB_URL", "")

    def warnings(self) -> list[str]:
        """Config problems worth surfacing at startup (non-fatal, but the app won't fully work)."""
        issues = []
        if not self.anthropic_api_key:
            issues.append("No Anthropic API key found (set ANTHROPIC_API_KEY or plan_reader/.env) "
                          "— the chat cannot answer.")
        master = MASTER_CSV
        if not master.exists():
            issues.append(f"Master bid CSV not found at {master} — bid-history/project tools will fail.")
        return issues


settings = Settings()
