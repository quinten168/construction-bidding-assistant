"""
Logging + lightweight tracing.

A RAG/agent backend is opaque without observability: when an answer is wrong you need to see what
the model searched for, which tool it called, what came back, and how long it took. This module
sets up structured stdout logging (which Railway/Docker capture automatically) and a tiny timing
context manager used to trace each tool call.
"""
from __future__ import annotations

import logging
import os
import sys
import time
from contextlib import contextmanager

_CONFIGURED = False


def configure(level: str | None = None) -> None:
    """Set up root logging once. Idempotent (safe to call from app startup and from scripts)."""
    global _CONFIGURED
    if _CONFIGURED:
        return
    # Log in UTC with a full date (not bare local time): captured turns are timestamped in UTC, so
    # the stdout trace and the stored records line up across machines/timezones.
    logging.Formatter.converter = time.gmtime
    logging.basicConfig(
        level=(level or os.environ.get("BID_LOG_LEVEL", "INFO")).upper(),
        format="%(asctime)s  %(levelname)-7s  %(name)s · %(message)s",
        datefmt="%Y-%m-%d %H:%M:%SZ",
        stream=sys.stdout,
    )
    # the embedding/vector libs are chatty at INFO — keep them at WARNING
    for noisy in ("httpx", "chromadb", "sentence_transformers", "urllib3"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    configure()
    return logging.getLogger(name)


@contextmanager
def timed(logger: logging.Logger, label: str):
    """Log how long a block took (and surface failures with their duration)."""
    start = time.perf_counter()
    try:
        yield
    except Exception:
        logger.exception("%s failed after %.0f ms", label, (time.perf_counter() - start) * 1000)
        raise
    else:
        logger.info("%s ok in %.0f ms", label, (time.perf_counter() - start) * 1000)
