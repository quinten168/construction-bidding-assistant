"""
Tool registry — the uniform interface the agent reasons over.

Every tool exposes the same shape: an Anthropic tool `schema` (what the model sees) and a `run`
function that takes the model's arguments and returns `(text_for_model, source_hits)`. Adding a
capability is now a single entry here — the agent loop discovers tools from this registry instead
of hard-coding an if/elif ladder.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Callable, List, Tuple

from . import (bid_data, competitors, competitor_record, corrections,
               plan_reader_bridge as pr, project_registry)
from .config import settings

# (text the model receives, source passages for the UI)
ToolResult = Tuple[str, List[dict]]


@dataclass(frozen=True)
class Tool:
    name: str
    schema: dict
    run: Callable[[dict], ToolResult]


# --- the plan-search tool (schema lives here; the retrieval is in the bridge) --------------------
_SEARCH_PLANS_SCHEMA = {
    "name": "search_plans",
    "description": (
        "Search the ingested highway bid-plan documents for passages relevant to a query. Use this "
        "for questions about what a plan REQUIRES or CONTAINS — prevailing wages, phasing/staging, "
        "liquidated damages, environmental/ESA restrictions, traffic control, quantities, special "
        "provisions, etc. Returns excerpts with citation tags you must cite as [n] with the page. "
        "Note: the corpus also contains state DOT *letting advertisements* (lists of UPCOMING bid "
        "OPPORTUNITIES) — those are the state's open solicitations, NOT CSI's own bids. Pass plan_id "
        "to restrict the search to a single plan."),
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "What to search the plans for."},
            "plan_id": {"type": "string",
                        "description": "Optional: restrict to one plan id (from find_projects)."},
        },
        "required": ["query"],
    },
}


def _run_search_plans(args: dict) -> ToolResult:
    where = {"doc_id": args["plan_id"]} if args.get("plan_id") else None
    hits = pr.retrieve(args["query"], settings.retrieve_k, where=where)
    return pr.build_context(hits), hits


def _run_query_bid_history(args: dict) -> ToolResult:
    return json.dumps(bid_data.run(args), default=str), []


def _run_find_projects(args: dict) -> ToolResult:
    return json.dumps(project_registry.run(args), default=str), []


def _run_query_competitors(args: dict) -> ToolResult:
    return json.dumps(competitors.run(args), default=str), []


def _run_competitor_record(args: dict) -> ToolResult:
    return json.dumps(competitor_record.run(args), default=str), []


def _run_record_correction(args: dict) -> ToolResult:
    return json.dumps(corrections.run(args), default=str), []


_ALL = [
    Tool("search_plans", _SEARCH_PLANS_SCHEMA, _run_search_plans),
    Tool("query_bid_history", bid_data.TOOL_SCHEMA, _run_query_bid_history),
    Tool("find_projects", project_registry.TOOL_SCHEMA, _run_find_projects),
    Tool("query_competitors", competitors.TOOL_SCHEMA, _run_query_competitors),
    Tool("competitor_record", competitor_record.TOOL_SCHEMA, _run_competitor_record),
    Tool("record_correction", corrections.TOOL_SCHEMA, _run_record_correction),
]

REGISTRY = {t.name: t for t in _ALL}
SCHEMAS = [t.schema for t in _ALL]   # passed to the Anthropic API as the `tools` argument
