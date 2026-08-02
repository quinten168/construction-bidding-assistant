"""
Shared Postgres access for the CI-data admin endpoints (bid results / pit list / competitor
registry). Talks to Supabase's `scratch` schema — see docs/DATA_ACCESS_SCRATCH.md.

This is the first place `apps/api` itself connects to Postgres; every other read in this backend
is a local CSV (see CLAUDE.md invariant #1/#2). Kept deliberately plain — a per-request connection,
no ORM, no pool — mirroring data/push_supabase_bid_data.py, which already proves this is enough for
this data's volume and this traffic's shape (low-volume interactive admin, not the chat hot path).
"""
from __future__ import annotations

import re
from contextlib import contextmanager
from typing import Iterator

import psycopg
from psycopg.rows import dict_row

from .config import settings


class ConfigError(RuntimeError):
    """SUPABASE_TEAM_DB_URL isn't set — surfaced as a clear error, not a psycopg traceback."""


@contextmanager
def get_conn() -> Iterator[psycopg.Connection]:
    if not settings.supabase_team_db_url:
        raise ConfigError(
            "SUPABASE_TEAM_DB_URL is not set. See docs/DATA_ACCESS_SCRATCH.md / apps/api/.env.example."
        )
    conn = psycopg.connect(settings.supabase_team_db_url, row_factory=dict_row)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def normalize(name: str | None) -> str:
    """Uppercase, whitespace-collapsed form used for exact-duplicate matching. Same normalization
    data/entity_resolution.py's apply_registry_mapping() applies to raw bidder names, kept in one
    place so the admin modules below don't each reimplement it."""
    if not name:
        return ""
    return re.sub(r"\s+", " ", name.strip().upper())
