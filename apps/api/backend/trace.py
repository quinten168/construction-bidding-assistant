"""
Conversation capture — the durable record of every chat turn.

Why this exists: before this module, a turn produced only streamed text held in an in-memory
Chainlit session (gone on timeout); tool traces went to stdout; token usage was computed by the
API and discarded. Nothing survived to analyse. This module captures ONE structured `TurnRecord`
per turn and fans it out to two sinks:

  • a per-day JSONL archive  (data/conversations/YYYY-MM-DD.jsonl) — append-only, crash-safe, the
    raw record an analyst / the eval harness reads with pandas.read_json(lines=True);
  • Supabase Postgres (table `scratch.conversations`) — top-level scalar columns for fast
    filtering + a `payload` JSONB column holding the full record. Moved off the local
    plan_reader/csi_v2.db SQLite file on 2026-08-03 (#50).

The capture is deliberately:
  • framework-agnostic — it lives in the backend, called from the agent loop (rag.py), so it works
    identically under Chainlit today and the Next.js frontend tomorrow;
  • non-blocking — the JSONL append + Postgres write run via asyncio.to_thread so a slow disk or
    a slow network doesn't stall the event loop / other users;
  • fail-safe — a capture error is logged and swallowed; it must NEVER break a chat turn.

The data is SEMI-STRUCTURED (stable ids/usage/timestamps + variable-length tool_calls/sources +
free text), which is exactly why the storage shape is "a few indexed columns + one JSON blob". The
move to Postgres took the `payload` column to real `JSONB`, which is what the SQLite version always
said it was heading for.

RETIREMENT NOTE: this module used to CREATE csi_v2.db on first use if it was absent. That is what
manufactured the decoy database `config.corpus_state` exists to detect — a file holding only a
`conversations` table, against which an `.exists()` guard passed while the report rendered a
confident, wrong "zero gotchas". It no longer touches the filesystem for storage, so that decoy
can no longer be created by this process at all.
"""
from __future__ import annotations

import asyncio
import datetime as _dt
import json
import uuid
from pathlib import Path
from typing import Any, Optional

from psycopg.types.json import Json

from . import ci_db
from .config import CSI_DB, settings
from .observability import get_logger

log = get_logger("bid_assistant.trace")

SCHEMA_VERSION = "1"          # bump when the TurnRecord shape changes

# --- where captured turns live -----------------------------------------------------------------
# JSONL archive (the raw, append-only record) lives under the module; the queryable index is now
# scratch.conversations in Supabase Postgres.
#
# Why `scratch` and not `public`: `public` holds the PUBLISHED plan-reader corpus and the app's role
# (csi_team) has USAGE but not CREATE on it, so the self-initializing DDL below cannot run there.
# That privilege split matches the intent — this is runtime data the app owns, not published corpus
# data, and `scratch` is where the app already reads and writes. The original reason this table
# shared csi_v2.db with plans/materials/gotchas was so conversation rows could join them; that still
# works, because `scratch.conversations` ⨝ `public.plans` is an ordinary cross-schema join in
# Postgres. Nothing is lost by the move.
CONV_DIR = Path(__file__).resolve().parent.parent / "data" / "conversations"
# Retained but UNUSED, so the retirement stays greppable and no stale import breaks. Nothing in
# this module opens it any more — see the RETIREMENT NOTE above for why that specifically matters.
DB_PATH = CSI_DB

# The conversations table, Postgres dialect. Still self-initializing at runtime (idempotent), which
# is why the assistant works against a fresh database with no migration step — the same property
# the SQLite version had. 04_tools/00_init_db.py still documents the legacy SQLite shape.
# `payload` is JSONB here, not TEXT: this module's docstring always named that as the destination
# and there is no other reader of this table to break (verified — the only other reference in the
# tree is 00_init_db.py's SQLite DDL; apps/web's `conversations` is unrelated local UI state).
_SCHEMA_STATEMENTS = (
    """
    create table if not exists scratch.conversations (
      turn_id               text primary key,
      session_id            text,
      user_id               text,
      ts                    text,
      model_id              text,
      prompt_version        text,
      schema_version        text,
      question              text,
      answer                text,
      tool_names            text,
      n_tool_calls          integer,
      n_sources             integer,
      input_tokens          integer,
      output_tokens         integer,
      cache_read_tokens     integer,
      cache_creation_tokens integer,
      latency_ms            double precision,
      n_steps               integer,
      active_plan_id        text,
      feedback_rating       integer,
      feedback_reason       text,
      error                 text,
      payload               jsonb
    )
    """,
    "create index if not exists idx_conversations_ts      on scratch.conversations(ts)",
    "create index if not exists idx_conversations_session on scratch.conversations(session_id)",
    "create index if not exists idx_conversations_model   on scratch.conversations(model_id)",
)

# The scalar columns we promote out of the payload into their own Postgres columns (the queryable
# index). Everything is also kept in `payload` so the JSONL and the row never disagree.
_COLS = [
    "turn_id", "session_id", "user_id", "ts", "model_id", "prompt_version", "schema_version",
    "question", "answer", "tool_names", "n_tool_calls", "n_sources", "input_tokens",
    "output_tokens", "cache_read_tokens", "cache_creation_tokens", "latency_ms", "n_steps",
    "active_plan_id", "feedback_rating", "feedback_reason", "error", "payload",
]


def new_turn_id() -> str:
    """A stable id for one turn — generated at the START of the turn so the UI can reference it
    (e.g. to attach feedback) before the answer has finished streaming."""
    return uuid.uuid4().hex


def utc_now_iso() -> str:
    """Timezone-AWARE UTC timestamp (fixes the old local-time/no-tz bug). Sorts + compares cleanly
    across machines and is what every downstream analysis should key time on."""
    return _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")


def make_record(
    *,
    turn_id: str,
    question: str,
    answer: str,
    tool_calls: list[dict],
    sources: list[dict],
    usage: dict,
    latency_ms: float,
    n_steps: int,
    model_id: str,
    prompt_version: str,
    session_id: Optional[str] = None,
    user_id: Optional[str] = None,
    active_plan_id: Optional[str] = None,
    corrections_applied: Optional[list[str]] = None,
    error: Optional[str] = None,
) -> dict:
    """Assemble the canonical TurnRecord (one dict, JSON-serialisable). Keeping construction here
    (not in rag.py) means the schema has a single home and the eval harness can build the same
    shape when it replays the golden set."""
    return {
        "turn_id": turn_id,
        "session_id": session_id,
        "user_id": user_id,
        "ts": utc_now_iso(),
        "model_id": model_id,
        "prompt_version": prompt_version,
        "schema_version": SCHEMA_VERSION,
        "question": question,
        "answer": answer,
        "tool_calls": tool_calls,                  # [{name, args, result_chars, n_sources, latency_ms, error?}]
        "sources": sources,                        # [{doc_id, source_file, page, section, distance, ...}]
        "usage": usage,                            # {input_tokens, output_tokens, cache_read_tokens, cache_creation_tokens}
        "latency_ms": round(latency_ms, 1),
        "n_steps": n_steps,
        "active_plan_id": active_plan_id,
        "corrections_applied": corrections_applied or [],
        "feedback": {"rating": None, "reason": None},  # patched later via update_feedback()
        "error": error,
    }


# --- the two sinks (sync; called via to_thread) ------------------------------------------------
def _row_from_record(rec: dict) -> dict:
    """Flatten the nested TurnRecord into the scalar columns the Postgres index needs."""
    usage = rec.get("usage") or {}
    fb = rec.get("feedback") or {}
    tool_calls = rec.get("tool_calls") or []
    return {
        "turn_id": rec["turn_id"],
        "session_id": rec.get("session_id"),
        "user_id": rec.get("user_id"),
        "ts": rec.get("ts"),
        "model_id": rec.get("model_id"),
        "prompt_version": rec.get("prompt_version"),
        "schema_version": rec.get("schema_version"),
        "question": rec.get("question"),
        "answer": rec.get("answer"),
        "tool_names": ",".join(tc.get("name", "") for tc in tool_calls),
        "n_tool_calls": len(tool_calls),
        "n_sources": len(rec.get("sources") or []),
        "input_tokens": usage.get("input_tokens"),
        "output_tokens": usage.get("output_tokens"),
        "cache_read_tokens": usage.get("cache_read_tokens"),
        "cache_creation_tokens": usage.get("cache_creation_tokens"),
        "latency_ms": rec.get("latency_ms"),
        "n_steps": rec.get("n_steps"),
        "active_plan_id": rec.get("active_plan_id"),
        "feedback_rating": fb.get("rating"),
        "feedback_reason": fb.get("reason"),
        "error": rec.get("error"),
        # Json() adapts the dict straight to JSONB. default=str keeps non-serialisable values
        # (datetimes, Paths) from failing the write, exactly as the old json.dumps did.
        "payload": Json(rec, dumps=lambda o: json.dumps(o, default=str, ensure_ascii=False)),
    }


def _append_jsonl(obj: dict) -> None:
    """Append one JSON object as a line to today's (UTC) archive file."""
    CONV_DIR.mkdir(parents=True, exist_ok=True)
    day = (obj.get("ts") or utc_now_iso())[:10]              # YYYY-MM-DD from the ISO timestamp
    path = CONV_DIR / f"{day}.jsonl"
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(obj, default=str, ensure_ascii=False) + "\n")


def _ensure_schema(cur) -> None:
    """Idempotent; self-initializes on first use so the assistant works against a fresh database
    with no migration step. Same property the SQLite version had, minus the ability to create a
    decoy — see the RETIREMENT NOTE in the module docstring."""
    for stmt in _SCHEMA_STATEMENTS:
        cur.execute(stmt)


def _upsert_row(rec: dict) -> None:
    """Insert (or, on the rare id clash, refresh) the row — but never clobber feedback that a later
    /api/feedback call may already have written for this turn_id."""
    row = _row_from_record(rec)
    placeholders = ", ".join("%s" for _ in _COLS)
    # On conflict, update everything EXCEPT the feedback columns (those are owned by update_feedback).
    updatable = [c for c in _COLS if c not in ("turn_id", "feedback_rating", "feedback_reason")]
    set_clause = ", ".join(f"{c} = excluded.{c}" for c in updatable)
    sql = (
        f"insert into scratch.conversations ({', '.join(_COLS)}) values ({placeholders}) "
        f"on conflict (turn_id) do update set {set_clause}"
    )
    with ci_db.get_conn() as conn, conn.cursor() as cur:
        _ensure_schema(cur)
        cur.execute(sql, [row[c] for c in _COLS])


def _write_sync(rec: dict) -> None:
    """Both sinks, fail-safe per sink so one failing doesn't lose the other."""
    try:
        _append_jsonl(rec)
    except Exception:                                        # noqa: BLE001
        log.exception("trace: JSONL append failed (turn_id=%s)", rec.get("turn_id"))
    try:
        _upsert_row(rec)
    except Exception:                                        # noqa: BLE001
        log.exception("trace: Postgres write failed (turn_id=%s)", rec.get("turn_id"))


# --- public async API (what rag.py / app.py call) ----------------------------------------------
async def record(rec: dict) -> None:
    """Persist a TurnRecord. Non-blocking + fail-safe: a capture failure is logged, never raised,
    so it cannot break the chat turn it is recording."""
    try:
        await asyncio.to_thread(_write_sync, rec)
    except Exception:                                        # noqa: BLE001 — capture must not crash chat
        log.exception("trace: record failed (turn_id=%s)", rec.get("turn_id"))


def _update_feedback_sync(turn_id: str, rating: Optional[int], reason: Optional[str]) -> bool:
    # Patch the promoted columns…
    with ci_db.get_conn() as conn, conn.cursor() as cur:
        _ensure_schema(cur)
        cur.execute("select payload from scratch.conversations where turn_id = %s", (turn_id,))
        found = cur.fetchone()
        cur.execute(
            "update scratch.conversations set feedback_rating = %s, feedback_reason = %s "
            "where turn_id = %s",
            (rating, reason, turn_id),
        )
        n = cur.rowcount                                     # psycopg's equivalent of changes()
        # …and keep the payload's nested feedback in sync so the row never disagrees with itself.
        payload = (found or {}).get("payload")
        if payload:
            try:
                # JSONB comes back already decoded; tolerate a str in case an older TEXT-column row
                # survived a migration.
                if isinstance(payload, str):
                    payload = json.loads(payload)
                payload["feedback"] = {"rating": rating, "reason": reason}
                cur.execute("update scratch.conversations set payload = %s where turn_id = %s",
                            (Json(payload), turn_id))
            except Exception:                                # noqa: BLE001
                pass
    # JSONL is append-only, so feedback is recorded as its own event line (keeps the archive whole).
    try:
        _append_jsonl({"type": "feedback", "turn_id": turn_id, "rating": rating,
                       "reason": reason, "ts": utc_now_iso()})
    except Exception:                                        # noqa: BLE001
        log.exception("trace: feedback JSONL append failed (turn_id=%s)", turn_id)
    return bool(n)


async def update_feedback(turn_id: str, rating: Optional[int], reason: Optional[str] = None) -> bool:
    """Attach a thumbs rating (+1/-1) and optional reason to an already-recorded turn. Returns True
    if the turn was found. The cheapest, highest-signal label for the eval framework."""
    try:
        return await asyncio.to_thread(_update_feedback_sync, turn_id, rating, reason)
    except Exception:                                        # noqa: BLE001
        log.exception("trace: update_feedback failed (turn_id=%s)", turn_id)
        return False


# Reserved for the Postgres switch: when settings.conversation_db_url is set we'll route _upsert
# there (same columns, payload as JSONB). JSONL stays the raw archive in both worlds.
def using_external_db() -> bool:
    return bool(getattr(settings, "conversation_db_url", ""))
