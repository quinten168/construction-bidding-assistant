"""
Bridge to the existing Plan Reader RAG backend.

The Plan Reader already owns retrieval — a populated ChromaDB store (50k+ passages across the
plan corpus) and a `retriever` module that does nearest-k search + citation formatting. We REUSE
it here instead of duplicating that logic, so there is a single source of truth for "what does the
corpus say." This module just makes those functions importable from a clean namespace and caches
the collection (which loads the embedding model once).
"""
from __future__ import annotations

import sys
from functools import lru_cache

from .config import PIPELINE

# The Plan Reader's lib.py / retriever.py live in a sibling module that isn't a package; add it to
# the path so we can import them directly.
if str(PIPELINE) not in sys.path:
    sys.path.insert(0, str(PIPELINE))

import lib          # noqa: E402  — path is configured just above
import retriever    # noqa: E402


@lru_cache(maxsize=1)
def get_collection():
    """The Chroma collection, loaded once. The embedding model binds to the collection, so the
    first call pays the model-load cost and every later call is instant."""
    return lib.get_collection()


def retrieve(query: str, k: int, where: dict | None = None) -> list[dict]:
    """Nearest-k passages for a query. `where` is an optional metadata filter (e.g. one plan)."""
    return retriever.retrieve(get_collection(), query, k, where)


def build_context(hits: list[dict]) -> str:
    """Format retrieved passages into a citation-tagged context block for the prompt."""
    return retriever.build_context(hits)


@lru_cache(maxsize=1)
def indexed_plans() -> list[str]:
    """Distinct plan ids in the store (for an optional 'focus on one plan' scope control).
    Paginated — a single get() of all rows exceeds SQLite's variable limit on a large store."""
    col = get_collection()
    ids: set[str] = set()
    offset, page = 0, 1000
    while True:
        got = col.get(include=["metadatas"], limit=page, offset=offset)
        metas = got.get("metadatas") or []
        ids.update(m.get("doc_id") for m in metas if m.get("doc_id"))
        offset += page
        if len(metas) < page:
            break
    return sorted(ids)
