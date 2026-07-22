"""
Conversation capture — the durable record of every chat turn.

Why this exists: before this module, a turn produced only streamed text held in an in-memory
Chainlit session (gone on timeout); tool traces went to stdout; token usage was computed by the
API and discarded. Nothing survived to analyse. This module captures ONE structured `TurnRecord`
per turn and fans it out to two sinks:

  • a per-day JSONL archive  (data/conversations/YYYY-MM-DD.jsonl) — append-only, crash-safe, the
    raw record an analyst / the eval harness reads with pandas.read_json(lines=True);
  • the existing SQLite store (plan_reader/csi_v2.db, table `conversations`) — top-level scalar
    columns for fast filtering + a `payload` JSON column holding the full record.

The capture is deliberately:
  • framework-agnostic — it lives in the backend, called from the agent loop (rag.py), so it works
    identically under Chainlit today and the Next.js frontend tomorrow;
  • non-blocking — the JSONL append + SQLite write run via asyncio.to_thread so a slow disk doesn't
    stall the event loop / other users;
  • fail-safe — a capture error is logged and swallowed; it must NEVER break a chat turn.

The data is SEMI-STRUCTURED (stable ids/usage/timestamps + variable-length tool_calls/sources +
free text), which is exactly why the storage shape is "a few indexed columns + one JSON blob". That
same shape ports to Postgres `JSONB` unchanged when we outgrow SQLite (set CONVERSATION_DB_URL).
"""
from __future__ import annotations

import asyncio
import datetime as _dt
import json
import sqlite3
import uuid
from pathlib import Path
from typing import Any, Optional

from .config import CSI_DB, settings
from .observability import get_logger

log = get_logger("bid_assistant.trace")

SCHEMA_VERSION = "1"          # bump when the TurnRecord shape changes

# --- where captured turns live -----------------------------------------------------------------
# JSONL archive (the raw, append-only record) lives under the module; SQLite index reuses the
# Plan Reader's csi_v2.db so conversation rows can join the plans/materials/gotchas tables.
CONV_DIR = Path(__file__).resolve().parent.parent / "data" / "conversations"
DB_PATH = CSI_DB          # one definition, shared with final_report.py, so the two cannot drift

# The conversations table — kept IDENTICAL to 04_tools/00_init_db.py (that file documents the whole
# DB; this one self-initializes at runtime so the assistant works even if init_db was never run).
_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS conversations (
  turn_id               TEXT PRIMARY KEY,
  session_id            TEXT,
  user_id               TEXT,
  ts                    TEXT,
  model_id              TEXT,
  prompt_version        TEXT,
  schema_version        TEXT,
  question              TEXT,
  answer                TEXT,
  tool_names            TEXT,
  n_tool_calls          INTEGER,
  n_sources             INTEGER,
  input_tokens          INTEGER,
  output_tokens         INTEGER,
  cache_read_tokens     INTEGER,
  cache_creation_tokens INTEGER,
  latency_ms            REAL,
  n_steps               INTEGER,
  active_plan_id        TEXT,
  feedback_rating       INTEGER,
  feedback_reason       TEXT,
  error                 TEXT,
  payload               TEXT
);
CREATE INDEX IF NOT EXISTS idx_conversations_ts      ON conversations(ts);
CREATE INDEX IF NOT EXISTS idx_conversations_session ON conversations(session_id);
CREATE INDEX IF NOT EXISTS idx_conversations_model   ON conversations(model_id);
"""

# The scalar columns we promote out of the payload into their own SQLite columns (the queryable
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
    """Flatten the nested TurnRecord into the scalar columns the SQLite index needs."""
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
        "payload": json.dumps(rec, default=str, ensure_ascii=False),
    }


def _append_jsonl(obj: dict) -> None:
    """Append one JSON object as a line to today's (UTC) archive file."""
    CONV_DIR.mkdir(parents=True, exist_ok=True)
    day = (obj.get("ts") or utc_now_iso())[:10]              # YYYY-MM-DD from the ISO timestamp
    path = CONV_DIR / f"{day}.jsonl"
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(obj, default=str, ensure_ascii=False) + "\n")


def _connect() -> sqlite3.Connection:
    # WAL keeps the assistant's writes from blocking the dashboard's reads of the same csi_v2.db.
    conn = sqlite3.connect(DB_PATH, timeout=10.0)
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _upsert_sqlite(rec: dict) -> None:
    """Insert (or, on the rare id clash, refresh) the row — but never clobber feedback that a later
    /api/feedback call may already have written for this turn_id."""
    row = _row_from_record(rec)
    placeholders = ", ".join("?" for _ in _COLS)
    # On conflict, update everything EXCEPT the feedback columns (those are owned by update_feedback).
    updatable = [c for c in _COLS if c not in ("turn_id", "feedback_rating", "feedback_reason")]
    set_clause = ", ".join(f"{c}=excluded.{c}" for c in updatable)
    sql = (
        f"INSERT INTO conversations ({', '.join(_COLS)}) VALUES ({placeholders}) "
        f"ON CONFLICT(turn_id) DO UPDATE SET {set_clause}"
    )
    conn = _connect()
    try:
        conn.executescript(_SCHEMA_SQL)                      # idempotent; self-initialize on first use
        conn.execute(sql, [row[c] for c in _COLS])
        conn.commit()
    finally:
        conn.close()


def _write_sync(rec: dict) -> None:
    """Both sinks, fail-safe per sink so one failing doesn't lose the other."""
    try:
        _append_jsonl(rec)
    except Exception:                                        # noqa: BLE001
        log.exception("trace: JSONL append failed (turn_id=%s)", rec.get("turn_id"))
    try:
        _upsert_sqlite(rec)
    except Exception:                                        # noqa: BLE001
        log.exception("trace: SQLite write failed (turn_id=%s)", rec.get("turn_id"))


# --- public async API (what rag.py / app.py call) ----------------------------------------------
async def record(rec: dict) -> None:
    """Persist a TurnRecord. Non-blocking + fail-safe: a capture failure is logged, never raised,
    so it cannot break the chat turn it is recording."""
    try:
        await asyncio.to_thread(_write_sync, rec)
    except Exception:                                        # noqa: BLE001 — capture must not crash chat
        log.exception("trace: record failed (turn_id=%s)", rec.get("turn_id"))


def _update_feedback_sync(turn_id: str, rating: Optional[int], reason: Optional[str]) -> bool:
    # Patch the SQLite columns…
    conn = _connect()
    try:
        conn.executescript(_SCHEMA_SQL)
        cur = conn.execute("SELECT payload FROM conversations WHERE turn_id=?", (turn_id,))
        found = cur.fetchone()
        conn.execute(
            "UPDATE conversations SET feedback_rating=?, feedback_reason=? WHERE turn_id=?",
            (rating, reason, turn_id),
        )
        # …and keep the payload's nested feedback in sync so the row never disagrees with itself.
        if found and found[0]:
            try:
                payload = json.loads(found[0])
                payload["feedback"] = {"rating": rating, "reason": reason}
                conn.execute("UPDATE conversations SET payload=? WHERE turn_id=?",
                             (json.dumps(payload, default=str, ensure_ascii=False), turn_id))
            except Exception:                                # noqa: BLE001
                pass
        conn.commit()
        n = conn.execute("SELECT changes()").fetchone()[0]
    finally:
        conn.close()
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
