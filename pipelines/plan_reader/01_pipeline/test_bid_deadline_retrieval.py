"""
test_bid_deadline_retrieval.py — COVERAGE tests for the bid_deadline retrieval query.

Spec: docs/_spec/2026-08-10-bid-date-query-split.md. Diagnosis: docs/_session/2026-08-10-bid-date.md §2.

The point of this file is NOT to prove `retriever.retrieve` returns k results. It is to assert that
the RIGHT chunk — the one that actually STATES the bid deadline — is inside the top-5 that
`fill_rag_fields` hands to Claude, and to go red the day that stops being true.

The anchor case is the one that started the whole track: 2025_MURRAY-CO-MN_CSAH-2_NOBID (Fulda CSAH 2,
466 pages, 521 chunks), page 9, "until Thursday, August 7, 2025, at 11:00am local time". Under the
old shared query — one entry serving bid_deadline + substantial_completion + final_completion — that
chunk ranked 40th and s4_extract_rag pulls k=5, so Claude never saw it. Under the split query it
ranks 3rd.

The corpus tests SKIP (never silently pass) when 06_chroma/ is absent — it is gitignored and 1.5 GB,
see pipelines/plan_reader/README.md. A fresh clone must not get a false green here.

    .venv/bin/python -m pytest pipelines/plan_reader/01_pipeline/test_bid_deadline_retrieval.py -q
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lib          # noqa: E402
import retriever    # noqa: E402
import s4_extract_rag as s4  # noqa: E402

CHROMA = lib.CHROMA_DIR
needs_chroma = pytest.mark.skipif(
    not (CHROMA / "chroma.sqlite3").exists(),
    reason="06_chroma/ not present (gitignored, 1.5 GB — see pipelines/plan_reader/README.md)")

MURRAY = "2025_MURRAY-CO-MN_CSAH-2_NOBID"
MURRAY_PAGE = 9
MURRAY_DEADLINE = "August 7, 2025"

# What s4 actually pulls. If this ever diverges from fill_rag_fields the tests below are measuring
# something the pipeline does not do, so it is asserted rather than hardcoded twice.
K = 5

_MONTH = ("January|February|March|April|May|June|July|August|September|October|November|December")
_DATE = (r"(?:\*{0,2}\s*(?:" + _MONTH + r")\s+\d{1,2}(?:st|nd|rd|th)?,?\s*\*{0,2}\s*20\d\d"
         r"|\d{1,2}/\d{1,2}/20\d\d)")

# STRICT ground truth: a chunk counts only if it STATES the deadline. A chunk that merely says
# "Advertisement for Bids" (a table of contents, a cross-reference in the Instructions to Bidders)
# does not — scoring those as hits is how a retrieval test flatters itself.
BID_TRUTH = re.compile(
    r"(?:bids?[^.]{0,300}?received[^.]{0,400}?until[^.]{0,200}?" + _DATE + r")"
    r"|(?:letting\s*date\s*[:\-]?\s*" + _DATE + r")"
    r"|(?:bid\s*opening[^.]{0,120}?" + _DATE + r")", re.I | re.S)

# Measured 2026-08-10 over the 33 plans in the store that state a bid deadline in a retrievable
# chunk. Old shared query: 12. Split query: 21. Asserted as a FLOOR below the measured value so a
# re-ingest that shifts chunk boundaries does not fail the suite, but a collapse does.
HIT5_FLOOR = 18
OLD_QUERY_HIT5 = 12       # what we are beating; recorded so the improvement is not folklore


def _query_for(field_name: str) -> str:
    """The retrieval query s4 will actually use for a field — read out of SCALAR_QUERIES so the test
    cannot drift away from the shipped configuration."""
    matches = [q for names, q in s4.SCALAR_QUERIES if field_name in names]
    assert len(matches) == 1, f"{field_name} is served by {len(matches)} SCALAR_QUERIES entries"
    return matches[0]


@pytest.fixture(scope="module")
def col():
    return lib.get_collection()


def _chunks(col, doc_id):
    g = col.get(where={"doc_id": doc_id}, include=["documents", "metadatas"])
    return list(zip(g["ids"], g["documents"], g["metadatas"]))


def _truth_keys(chunks, rx):
    return {(m.get("page"), d[:60]) for _i, d, m in chunks if rx.search(d)}


def _rank(col, doc_id, query, keys, kmax=100):
    """1-based rank of the first ground-truth chunk, or None if it is not in the top `kmax`.
    None means 'not retrieved' and is only ever returned for a query that RAN — a Chroma failure
    raises out of retriever.retrieve rather than arriving here as an empty list."""
    hits = retriever.retrieve(col, query, kmax, where={"doc_id": doc_id})
    for n, h in enumerate(hits, 1):
        if (h["meta"].get("page"), h["text"][:60]) in keys:
            return n
    return None


# ── 1. The configuration itself ────────────────────────────────────────────────

def test_bid_deadline_has_its_own_query():
    """The whole fix. If someone re-merges bid_deadline into the completion entry, this goes red
    before anyone has to notice a wrong bid date on a report."""
    entry = [names for names, _q in s4.SCALAR_QUERIES if "bid_deadline" in names]
    assert entry == [["bid_deadline"]], f"bid_deadline is grouped with {entry}"


def test_the_completion_query_is_unchanged():
    """substantial_completion / final_completion keep the EXACT string they had when they shared the
    entry with bid_deadline. Same text, same k, same filter => identical context => they cannot have
    regressed. That is the no-regression guarantee, and it only holds while this string holds."""
    assert _query_for("substantial_completion") == _query_for("final_completion")
    assert _query_for("substantial_completion") == (
        "bid opening date bids due proposal deadline letting date substantial completion final "
        "completion contract time working days calendar days notice to proceed completion deadline "
        "liquidated damages complete the work by")


def test_the_bid_query_does_not_carry_completion_vocabulary():
    """The dilution that caused the bug: 'substantial completion', 'final completion', 'liquidated
    damages' and 'working days' pulling a 466-page proposal's contract boilerplate over the one
    advertisement page."""
    q = _query_for("bid_deadline").lower()
    for banned in ("substantial completion", "final completion", "liquidated damages",
                   "working days", "calendar days", "notice to proceed"):
        assert banned not in q, f"{banned!r} is back in the bid_deadline query"


# ── 2. The acceptance measurement — the Murray advertisement page, within k=5 ───

@needs_chroma
def test_the_murray_advertisement_chunk_is_in_the_store_at_all(col):
    """Rules out 'the converter or the boilerplate filter lost it' as an explanation for any miss
    below. The chunk is DOWN_WEIGHT, not DROP."""
    page9 = [(i, d, m) for i, d, m in _chunks(col, MURRAY) if m.get("page") == MURRAY_PAGE]
    stating = [i for i, d, _m in page9 if MURRAY_DEADLINE in d]
    assert stating == [f"{MURRAY}:p9:c0"], f"page 9 chunks stating the deadline: {stating}"


@needs_chroma
def test_murray_bid_deadline_page_is_retrieved_within_k5(col):
    """THE acceptance test. k is s4's own k, not a number chosen to make this pass."""
    chunks = _chunks(col, MURRAY)
    keys = _truth_keys(chunks, BID_TRUTH)
    assert keys, "ground-truth regex matched no Murray chunk — the fixture, not the query, is broken"
    rank = _rank(col, MURRAY, _query_for("bid_deadline"), keys)
    assert rank is not None, "the advertisement page was not retrieved at all in the top 100"
    assert rank <= K, (
        f"Murray p.{MURRAY_PAGE} ranks {rank}; s4_extract_rag pulls k={K}, so Claude never sees it")


@needs_chroma
def test_the_old_shared_query_still_fails_the_same_case(col):
    """Guards the diagnosis, not the fix. If this ever passes, the store changed underneath us and
    every 'before' number in the spec and the session report is stale — which is worth knowing
    loudly, because it would mean the improvement above is being credited to the wrong change."""
    old = ("bid opening date bids due proposal deadline letting date substantial completion final "
           "completion contract time working days calendar days notice to proceed completion "
           "deadline liquidated damages complete the work by")
    keys = _truth_keys(_chunks(col, MURRAY), BID_TRUTH)
    assert (_rank(col, MURRAY, old, keys) or 999) > K, \
        "the OLD diluted query now surfaces Murray p.9 within k=5 — re-measure everything"


# ── 3. Corpus-wide floor ───────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def bid_deadline_plans(col):
    """Every plan in the store that states a bid deadline in a retrievable chunk. Discovered from
    the store rather than hardcoded, so a re-ingest widens the test instead of stranding it."""
    import sqlite3
    con = sqlite3.connect(f"file:{CHROMA / 'chroma.sqlite3'}?mode=ro", uri=True)
    doc_ids = [r[0] for r in con.execute(
        "select string_value, count(*) c from embedding_metadata where key='doc_id' "
        "group by 1 having c >= 100 order by c desc")]
    con.close()
    out = []
    for d in doc_ids:
        if not (d[:4].isdigit() and "_" in d):       # canonical plan ids only; skips the duplicates
            continue                                  # filed under a bare numeric stem or a uuid
        keys = _truth_keys(_chunks(col, d), BID_TRUTH)
        if 1 <= len(keys) <= 3:
            out.append((d, keys))
    return out


@needs_chroma
def test_bid_deadline_hit_rate_at_k5_does_not_regress(col, bid_deadline_plans):
    """A per-plan test would pass on the 12 plans the old query already got. This is the number that
    moved: how many plans put the chunk that STATES the deadline inside the k=5 Claude actually sees."""
    assert len(bid_deadline_plans) >= 25, \
        f"only {len(bid_deadline_plans)} plans in the fixture — the corpus, not the query, is thin"
    q = _query_for("bid_deadline")
    hits = [d for d, keys in bid_deadline_plans if (_rank(col, d, q, keys) or 999) <= K]
    assert len(hits) >= HIT5_FLOOR, (
        f"hit@{K} fell to {len(hits)}/{len(bid_deadline_plans)} (floor {HIT5_FLOOR}; the old shared "
        f"query scored {OLD_QUERY_HIT5}). The split query has stopped working.")


# ── 4. A retrieval that finds nothing must not look like one that failed ───────

@needs_chroma
def test_a_plan_with_no_bid_deadline_returns_an_empty_hit_not_an_error(col):
    """The standing rule, on this path. A doc_id that exists but has no advertisement chunk yields a
    populated hit list whose ranks are all misses — NOT an exception, and not an empty list that
    could be confused with a dead collection."""
    hits = retriever.retrieve(col, _query_for("bid_deadline"), K, where={"doc_id": MURRAY})
    assert len(hits) == K and all(h["text"] for h in hits)
    missing = _rank(col, MURRAY, _query_for("bid_deadline"), keys=set())
    assert missing is None                      # "no ground truth matched" is a clean, distinct None


def test_a_nonexistent_doc_id_does_not_silently_look_like_a_miss(col=None):
    """Retrieval scoped to a doc_id that is not in the store returns zero hits. Zero hits and 'five
    hits, none of them the answer' are different facts and _rank must not flatten them: the first is
    len(hits)==0, the second is len(hits)==K with rank None."""
    if not (CHROMA / "chroma.sqlite3").exists():
        pytest.skip("06_chroma/ not present")
    c = lib.get_collection()
    hits = retriever.retrieve(c, _query_for("bid_deadline"), K,
                              where={"doc_id": "NO-SUCH-PLAN-2026"})
    assert hits == [], "a doc_id that does not exist returned hits — the where filter is not applied"


# ── 5. The parse-failure hole in fill_rag_fields ──────────────────────────────

def test_a_json_parse_failure_is_not_written_as_a_clean_null(monkeypatch):
    """extract.call_json returns None on a JSON parse failure. Before 2026-08-10 fill_rag_fields did
    `or {}`, so every field in the group was written as a null cell — byte-identical to 'the plan
    states no value'. It must now be named."""
    import schema
    rec = schema.blank_record("PLAN", "f.pdf", "2026-08-10")
    monkeypatch.setattr(s4.extract, "call_json", lambda *a, **k: None)
    monkeypatch.setattr(s4, "_context", lambda *a, **k: ("ctx", []))
    monkeypatch.setattr(s4, "detect_gotchas", lambda *a, **k: [])
    s4.fill_rag_fields(rec, col=None, plan_id="PLAN")
    assert "bid_deadline" in rec.get("rag_scalar_parse_failures", []), \
        "a parse failure produced an unexplained null bid_deadline"
    assert rec["bid_deadline"]["value"] is None


def test_a_real_null_is_not_reported_as_a_parse_failure(monkeypatch):
    """The other half of the same rule: a model that read the excerpts and honestly found nothing
    must NOT be flagged as a failure."""
    import schema
    rec = schema.blank_record("PLAN", "f.pdf", "2026-08-10")
    monkeypatch.setattr(s4.extract, "call_json",
                        lambda *a, **k: {"bid_deadline": {"value": None, "confidence": "", "page": None}})
    monkeypatch.setattr(s4, "_context", lambda *a, **k: ("ctx", []))
    monkeypatch.setattr(s4, "detect_gotchas", lambda *a, **k: [])
    s4.fill_rag_fields(rec, col=None, plan_id="PLAN")
    assert rec.get("rag_scalar_parse_failures", []) == []
    assert rec["bid_deadline"]["value"] is None
