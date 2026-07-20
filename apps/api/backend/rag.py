"""
Agentic bid-intelligence assistant — the answer loop.

Claude is given a set of tools (see `tools.py`) and decides which to use per question:
  • search_plans       → plan CONTENTS (wages, phasing, gotchas, quantities…), cited by page
  • query_bid_history  → CSI's bidding RECORD (how many bid/won, win rates) from the master data
  • find_projects      → resolve a SPECIFIC named/located project, then drill into the others

The loop streams the answer token-by-token, runs any requested tools (off the event loop, so the
server stays responsive), feeds the results back, and continues until the model is done. Every turn
is traced (which tools, what args, latency) so the RAG behaviour is debuggable.
"""
from __future__ import annotations

import asyncio
import hashlib
import time
from typing import AsyncIterator, Optional, Tuple

from anthropic import AsyncAnthropic

from . import corrections, tools, trace
from .config import settings
from .observability import get_logger

log = get_logger("bid_assistant.rag")

_client = AsyncAnthropic(api_key=settings.anthropic_api_key, max_retries=3, timeout=60.0)
_MAX_STEPS = 4  # safety bound on tool-call rounds per question

_SYSTEM = (
    "You are Central Specialties' (CSI) bid-intelligence assistant for highway construction. You "
    "answer three kinds of questions and must pick the right tool:\n"
    "1. PLAN CONTENT (what a plan requires/contains) → call search_plans, then answer and cite "
    "each fact as [n] with its page.\n"
    "2. CSI's BIDDING RECORD (how many CSI bid/won, win rates, by state/year) → call "
    "query_bid_history and report the actual numbers it returns.\n"
    "3. A SPECIFIC NAMED/LOCATED PROJECT ('the Stearns CP-073 job', 'the Highway 23 project') → "
    "call find_projects to resolve it first. If several match, list them and ask which one. Once "
    "resolved, you can call search_plans (if it has a plan document) or query_bid_history for more.\n"
    "4. CSI's COMPETITORS (who CSI bids against, who beats CSI, by state) → call query_competitors.\n\n"
    "Rules:\n"
    "- Answer the question directly first, in a sentence or two; add detail only as needed. Keep it "
    "tight — do NOT dump large tables of raw DOT codes unless the user explicitly asks for a list.\n"
    "- Distinguish the STATE's open bid opportunities (letting advertisements in the plan corpus) "
    "from CSI's OWN bids (the bid-history data). If asked about CSI's bids, use query_bid_history.\n"
    "- If a tool returns nothing relevant, say so plainly. Never invent facts, numbers, or pages.\n"
    "- Explain DOT jargon in plain terms when you use it."
)

# A short, stable fingerprint of the system prompt. Stamped on every captured turn so the eval
# framework can segment "how is the model performing over time" by prompt version — when this string
# changes, you know a prompt edit is responsible for any metric shift.
_PROMPT_VERSION = hashlib.sha1(_SYSTEM.encode("utf-8")).hexdigest()[:8]


def _recent(history: list[dict]) -> list[dict]:
    return history[-settings.max_history_turns * 2:]


def _add_usage(acc: dict, usage) -> None:
    """Accumulate one step's token usage into the running per-turn totals. The Anthropic Usage
    object carries input/output + (when prompt caching is on) cache read/creation counts — all of
    which were previously computed and DISCARDED. Capturing them gives per-turn/session cost."""
    if usage is None:
        return
    acc["input_tokens"] += getattr(usage, "input_tokens", 0) or 0
    acc["output_tokens"] += getattr(usage, "output_tokens", 0) or 0
    acc["cache_read_tokens"] += getattr(usage, "cache_read_input_tokens", 0) or 0
    acc["cache_creation_tokens"] += getattr(usage, "cache_creation_input_tokens", 0) or 0


async def _execute_tool(name: str, args: dict) -> Tuple[str, list[dict], dict]:
    """Run one tool off the event loop, with tracing. Returns (text_for_model, source_hits, trace)
    where `trace` is the structured per-tool record captured on the turn (previously this data was
    only formatted into a stdout log line and lost). A tool failure becomes an error result the
    model can recover from (it can apologize / try another tool) rather than crashing the stream."""
    start = asyncio.get_event_loop().time()
    tool = tools.REGISTRY.get(name)
    if tool is None:
        log.warning("unknown tool requested: %s", name)
        tc = {"name": name, "args": args, "result_chars": 0, "n_sources": 0,
              "latency_ms": 0.0, "error": "unknown_tool"}
        return f"Unknown tool '{name}'.", [], tc
    try:
        text, hits = await asyncio.to_thread(tool.run, args)
    except Exception as e:                                   # noqa: BLE001 — surface, don't crash
        dt = (asyncio.get_event_loop().time() - start) * 1000
        log.exception("tool %s failed (args=%s)", name, args)
        tc = {"name": name, "args": args, "result_chars": 0, "n_sources": 0,
              "latency_ms": round(dt, 1), "error": type(e).__name__}
        return f"The {name} tool failed: {e}. Tell the user you couldn't retrieve that.", [], tc
    dt = (asyncio.get_event_loop().time() - start) * 1000
    log.info("tool %s args=%s → %d chars, %d sources, %.0f ms", name, args, len(text), len(hits), dt)
    tc = {"name": name, "args": args, "result_chars": len(text), "n_sources": len(hits),
          "latency_ms": round(dt, 1)}
    return text, hits, tc


async def agentic_answer(history: list[dict], question: str,
                         active_plan_id: str | None = None,
                         session_id: Optional[str] = None,
                         user_id: Optional[str] = None) -> AsyncIterator[Tuple[str, object]]:
    """Yield ('token', str) as the answer streams, then ('turn', turn_id) and ('sources', list[hit])
    at the end. Every turn is assembled into one structured TurnRecord and persisted via trace.record
    (JSONL archive + SQLite index) — capture lives HERE in the backend, not the UI, so it is identical
    under Chainlit and the Next.js frontend, and feeds the eval framework.

    `active_plan_id` (a just-uploaded plan the user is viewing) scopes vague follow-ups to it.
    `session_id`/`user_id` come from the UI and group turns into conversations / users."""
    turn_id = trace.new_turn_id()
    t0 = time.perf_counter()
    log.info("Q: %s%s", question, f"  [active plan: {active_plan_id}]" if active_plan_id else "")

    system = _SYSTEM
    corrections_applied: list[str] = []
    if active_plan_id:
        system += (f"\n\nCONTEXT: the user just uploaded and is viewing plan '{active_plan_id}'. "
                   f"If they say 'this plan'/'it' or ask about the plan without naming another, call "
                   f"search_plans with plan_id='{active_plan_id}'. When the user states a value to "
                   f"CONFIRM, CORRECT, or ADD (a quantity, lat/long coordinates, prevailing wages, a "
                   f"date, etc.), call record_correction with plan_id='{active_plan_id}', then confirm.")
        cv = corrections.corrected_values(active_plan_id)
        if cv:
            system += ("\nUser-confirmed values for this plan (PREFER these over the extraction): "
                       + ", ".join(f"{k}={v}" for k, v in cv.items()) + ".")
            corrections_applied = list(cv.keys())
    messages = _recent(history) + [{"role": "user", "content": question}]

    # per-turn capture accumulators
    sources: list[dict] = []
    tool_calls: list[dict] = []
    usage = {"input_tokens": 0, "output_tokens": 0, "cache_read_tokens": 0, "cache_creation_tokens": 0}
    answer_parts: list[str] = []
    n_steps = 0
    err: Optional[str] = None

    try:
        for step in range(_MAX_STEPS):
            n_steps = step + 1
            async with _client.messages.stream(
                model=settings.chat_model,
                max_tokens=settings.answer_max_tokens,
                system=system,
                tools=tools.SCHEMAS,
                messages=messages,
            ) as stream:
                async for text in stream.text_stream:
                    answer_parts.append(text)
                    yield ("token", text)
                final = await stream.get_final_message()
            _add_usage(usage, getattr(final, "usage", None))

            if final.stop_reason != "tool_use":
                break

            # run every tool the model asked for, then feed the results back
            messages.append({"role": "assistant", "content": final.content})
            results = []
            for block in final.content:
                if block.type == "tool_use":
                    out, hits, tc = await _execute_tool(block.name, block.input)
                    sources.extend(hits)
                    tool_calls.append(tc)
                    results.append({"type": "tool_result", "tool_use_id": block.id, "content": out})
            messages.append({"role": "user", "content": results})
        else:
            log.warning("hit _MAX_STEPS (%d) tool rounds without a final answer", _MAX_STEPS)
    except Exception as e:                                   # noqa: BLE001
        err = type(e).__name__
        log.exception("agentic_answer failed")
        msg = (f"\n\n⚠️ Something went wrong answering that ({err}). Please try again.")
        answer_parts.append(msg)
        yield ("token", msg)

    # assemble + persist the turn (trace.record is itself fail-safe — capture never breaks the chat)
    rec = trace.make_record(
        turn_id=turn_id, question=question, answer="".join(answer_parts),
        tool_calls=tool_calls, sources=sources, usage=usage,
        latency_ms=(time.perf_counter() - t0) * 1000, n_steps=n_steps,
        model_id=settings.chat_model, prompt_version=_PROMPT_VERSION,
        session_id=session_id, user_id=user_id, active_plan_id=active_plan_id,
        corrections_applied=corrections_applied, error=err,
    )
    await trace.record(rec)

    yield ("turn", turn_id)
    yield ("sources", sources)
    # Real per-turn token usage (the honest context/usage signal for the UI). RAG sends only the
    # system prompt + tools + the handful of retrieved chunks + recent history — so `input_tokens`
    # is the true context size for this answer, not a whole-document estimate.
    yield ("usage", {**usage, "model": settings.chat_model})
