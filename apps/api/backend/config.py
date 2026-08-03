"""
Central configuration for the Bid Assistant.

Everything that differs between local development and a deployed container lives here as an
environment variable with a sensible default — so the app is 12-factor / deploy-ready without
touching code. On Railway you'd set these in the dashboard; locally they fall back to defaults
and the project's existing `.env` convention.
"""
from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass
from pathlib import Path

# Load .env BEFORE any os.environ.get() below runs. Without this, apps/api/.env is an inert file:
# nothing in this backend read it, so a teammate who filled in SUPABASE_TEAM_DB_URL there got the
# "not set" warning anyway and had no way to tell why. Existing env vars always win, so an export
# or a Railway dashboard value still overrides the file.
#
# Search order is nearest-first: apps/api/.env, then the repo-root .env that
# ci_model/06_reporting/agent/orchestrator.py already loads, so one root file can serve both.
try:
    from dotenv import load_dotenv as _load_dotenv
    _DOTENV_AVAILABLE = True
except ImportError:                                   # optional dep; absent means env-vars-only
    _DOTENV_AVAILABLE = False

    def _load_dotenv(*_a, **_k):
        return False

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
ROAD_MIDPOINT_DIR = PLAN_READER / "04_tools" / "road_midpoint"   # importable: road_midpoint.py
REVERSE_GEOCODE_DIR = PLAN_READER / "04_tools" / "reverse_geocode"  # importable: reverse_geocode.py
# The single source of truth for the master bid CSV. Previously duplicated verbatim across
# bid_data.py, competitors.py and project_registry.py — so a path change fixed one and broke
# three, which is the most confusing failure mode available. They now import this.
MASTER_CSV = REPO / "data" / "reference" / "2026-06-03_csi_bid_master.csv"
# The Plan Reader's SQLite database. Shared on purpose: backend/trace.py writes conversation rows
# here so they can join plans/materials/gotchas (see the comment at the top of that file).
CSI_DB = PLAN_READER / "csi_v2.db"

# --- is the plan corpus actually loaded? ---------------------------------------------------------
CORPUS_OK = "ok"
CORPUS_NO_FILE = "no_file"
CORPUS_NO_TABLE = "no_table"
CORPUS_EMPTY = "empty"

CORPUS_MESSAGES = {
    CORPUS_NO_FILE: "database file not found",
    CORPUS_NO_TABLE: "database has no `plans` table",
    CORPUS_EMPTY: "`plans` table is empty",
}


def corpus_state(db_path: Path = CSI_DB) -> str:
    """Answer "is the plan corpus loaded", not "does a file exist". Returns one of CORPUS_*.

    File existence is not a usable proxy. backend/trace.py deliberately creates csi_v2.db on the
    first chat turn so the assistant works even if 00_init_db.py was never run, which means the
    path can exist while holding nothing but a `conversations` table. A guard on `.exists()` passes
    against that decoy and the caller then renders a confident, wrong "zero gotchas". Issue #13 will
    make process_pdf write here on every run, at which point the file always exists and a
    path-existence guard is permanently useless.

    Checks three states in order: file absent, no `plans` table, `plans` table with zero rows.

    Deliberately not cached. trace.py can create the file mid-process, so an answer computed once at
    import time would be wrong for the remaining life of the worker.
    """
    if not db_path.exists():
        return CORPUS_NO_FILE
    try:
        # Read-only: a plain connect() on a missing path CREATES it, so a careless probe here would
        # manufacture the very decoy this function exists to detect.
        con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    except sqlite3.Error:
        return CORPUS_NO_FILE
    try:
        found = con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='plans'").fetchone()
        if found is None:
            return CORPUS_NO_TABLE
        (n_plans,) = con.execute("SELECT count(*) FROM plans").fetchone()
    except sqlite3.Error:
        return CORPUS_NO_TABLE
    finally:
        con.close()
    return CORPUS_OK if n_plans else CORPUS_EMPTY
# Competitor Intelligence reports (Quentin/Wenyu's pipeline output). The final report parses +
# matches these `bid_report_<project_natural_key>.md` files to a plan. They can be pre-generated
# (static) OR generated LIVE by invoking the CI team's agent (see CI_MODEL_REPO below) when a plan
# maps to a corpus project.
COMPETITOR_REPORTS = REPO / "pipelines" / "ci_model" / "reports"

# --- live competitor generation (the CI model, now in-repo) -------------------------------------
# Their agent (`06_reporting/agent/orchestrator.py::run_report`) generates a fresh report for any
# project_natural_key already in their pre-computed corpus in ~1s (--skip-llm) / ~5-15s (with LLM).
# We invoke it as a subprocess and drop the output into COMPETITOR_REPORTS so the matcher picks up
# the fresh file.
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
# Swapped from logistic_baseline_model.json (36 features) to the 4-feature simple-rule baseline:
# evaluation showed only a ~4pt winner-hit-rate@10 gap (61.7% vs 57.4% on the full test split) for
# a model that's far more interpretable and easier to explain to an estimator. See
# docs/adr (or KTD) for the full comparison against the other baselines tried (xgboost, decision
# tree, SVM) -- none of them beat simple-rule by enough to justify the added complexity, so none of
# them are wired in here; they stay evaluation-only artifacts in 03_training/outputs + 04_evaluation.
CI_MODEL_JSON = REPO / "pipelines" / "ci_model" / "03_training" / "outputs" / "simple_rule_baseline_weights.json"
CI_REGISTRY_CSV = (REPO / "pipelines" / "ci_model" / "01_candidates" / "outputs"
                   / "competitor_name_registry - name_variants.csv")
# Authoritative bidder × project outcomes (every bidder, county, win) — backs the competitor_record
# chat tool. Broader than the CSI-centric master CSV (which only covers projects CSI also bid on).
CI_BIDDER_RESULTS = REPO / "data" / "processed" / "bidder_results.csv"
# Pulls admin-UI edits (bid-results entry, pit-list CRUD, competitor-registry CRUD — see
# backend/ci_db.py) back from Supabase `scratch.*` into the CSVs above, before a live report reads
# them. See competitor_live.py::ensure_fresh_local_data.
PULL_SCRATCH_SCRIPT = REPO / "data" / "pull_scratch_updates.py"

_ENV_FILES_FOUND = [f for f in (REPO / "apps" / "api" / ".env", REPO / ".env") if f.exists()]
for _env_file in _ENV_FILES_FOUND:
    _load_dotenv(_env_file, override=False)


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

    # Automated route/milepost → lat/long lookup (04_tools/road_midpoint/road_midpoint.py), the
    # 5th process_pdf stage (report.py). Calls up to 6 state DOT GIS REST endpoints (MN/ND/SD/NE/
    # IA/MT) — the first non-Anthropic outbound calls on the live report path. Fails safe:
    # midpoint_bridge.compute_midpoint never raises, leaves latitude/longitude null on any error,
    # and a human can always fill them in via record_correction regardless of this setting.
    midpoint_lookup_enabled: bool = os.environ.get("MIDPOINT_LOOKUP_ENABLED", "1") not in ("0", "false", "False")

    # 6th process_pdf stage: coordinates -> city/county/state/zip, for project_natural_key's city
    # component. Off when GOOGLE_GEOCODING_API_KEY is absent, so a teammate without the key gets a
    # null city rather than a stack trace. That key is SERVER-SIDE and must not be the same value as
    # NEXT_PUBLIC_GOOGLE_MAPS_API_KEY, which the pit-list page ships to the browser.
    reverse_geocode_enabled: bool = (
        os.environ.get("REVERSE_GEOCODE_ENABLED", "1") not in ("0", "false", "False")
        and bool(os.environ.get("GOOGLE_GEOCODING_API_KEY", "").strip())
    )
    reverse_geocode_timeout: int = int(os.environ.get("REVERSE_GEOCODE_TIMEOUT", "20"))
    midpoint_lookup_timeout: int = int(os.environ.get("MIDPOINT_LOOKUP_TIMEOUT", "90"))

    # Conversation capture (see backend/trace.py). Empty = use the local SQLite csi_v2.db + JSONL.
    # Set CONVERSATION_DB_URL to a Postgres DSN when we deploy multi-user (same schema → JSONB);
    # the per-day JSONL archive is written in both worlds.
    conversation_db_url: str = os.environ.get("CONVERSATION_DB_URL", "")

    # The CI-data admin endpoints (bid results / pit list / competitor registry — see
    # backend/ci_db.py): read/write access to Supabase's scratch schema, docs/DATA_ACCESS_SCRATCH.md.
    # Same DSN data/push_supabase_bid_data.py already uses (the csi_team login: read/write on
    # scratch, read-only on public) — reused rather than provisioning a separate app role.
    supabase_team_db_url: str = os.environ.get("SUPABASE_TEAM_DB_URL", "")

    def warnings(self) -> list[str]:
        """Config problems worth surfacing at startup (non-fatal, but the app won't fully work)."""
        issues = []
        # A .env that is never read is worse than no .env: the operator believes it is configured.
        if _ENV_FILES_FOUND and not _DOTENV_AVAILABLE:
            issues.append(
                f"Found {', '.join(str(f) for f in _ENV_FILES_FOUND)} but python-dotenv is not "
                "installed, so NOTHING in those files was loaded. Either `pip install python-dotenv` "
                "(it is in apps/api/requirements.txt) or export the variables directly.")
        if not self.anthropic_api_key:
            issues.append("No Anthropic API key found (set ANTHROPIC_API_KEY or plan_reader/.env) "
                          "— the chat cannot answer.")
        master = MASTER_CSV
        if not master.exists():
            issues.append(f"Master bid CSV not found at {master} — bid-history/project tools will fail.")
        # The two corpus failures need different fixes, so they get different messages. "File not
        # found" is the obvious one; "file present but no plan corpus" is the confusing one, because
        # trace.py creates that file and everything downstream looks healthy while the final report
        # quietly reports zero gotchas for every plan.
        # Passed explicitly, not left to the default argument: the default binds CSI_DB once at
        # definition time, so a test or a caller that repoints the module global would be ignored.
        state = corpus_state(CSI_DB)
        if state == CORPUS_NO_FILE:
            issues.append(
                f"Plan corpus database not found at {CSI_DB}. The final report will show zero "
                "gotchas for every plan. Run pipelines/plan_reader/04_tools/00_init_db.py, then "
                "ingest the plans.")
        elif state != CORPUS_OK:
            issues.append(
                f"Plan corpus database at {CSI_DB} exists but holds no plans "
                f"({CORPUS_MESSAGES[state]}). The final report will show zero gotchas for every "
                "plan. The file alone is not evidence the corpus loaded: the conversation tracer "
                "creates it on the first chat turn. Ingest the plans.")
        if not self.supabase_team_db_url:
            issues.append(
                "SUPABASE_TEAM_DB_URL is not set — the bid-results/pit-list/competitor-registry "
                "admin endpoints will fail on first write. See docs/DATA_ACCESS_SCRATCH.md.")
        return issues


settings = Settings()
