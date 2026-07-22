"""
Tests for the plan-corpus presence check (issue #25).

The bug these guard against: the three SQLite readers in final_report.py used `DB_PATH.exists()`
as a proxy for "the corpus is loaded". backend/trace.py legitimately creates that same file on the
first chat turn with only a `conversations` table in it, so the guard passed against a database
holding no plans and the report rendered a confident "zero gotchas".

These build real SQLite files in tmp_path rather than mocking, because the decoy case is precisely
about what is inside the file, which a mock of `.exists()` cannot express.

Run from the apps/api/ directory:   ../../.venv/bin/python3 -m pytest -q
"""
import sqlite3

import pytest

from backend import config, final_report, trace


def _make_db(path, tables=(), plan_rows=0):
    """Build a SQLite file with the named tables, optionally seeding `plans` with N rows."""
    con = sqlite3.connect(path)
    if "conversations" in tables:
        con.execute("CREATE TABLE conversations (turn_id TEXT PRIMARY KEY, session_id TEXT)")
    if "plans" in tables:
        con.execute("CREATE TABLE plans (plan_id TEXT PRIMARY KEY, source_file TEXT)")
        for i in range(plan_rows):
            con.execute("INSERT INTO plans VALUES (?, ?)", (f"plan-{i}", f"{i}.pdf"))
    con.commit()
    con.close()
    return path


# --- the shared path constant ---------------------------------------------------------------------
def test_trace_and_final_report_share_one_db_path():
    """The reader and the writer must never drift apart: divergent paths are how a guard ends up
    checking a different file from the one a sibling module creates, which is the root of #25."""
    assert trace.DB_PATH == final_report.DB_PATH == config.CSI_DB


# --- corpus_state, the three failure states -----------------------------------------------------
def test_absent_file_is_no_file(tmp_path):
    assert config.corpus_state(tmp_path / "nope.db") == config.CORPUS_NO_FILE


def test_probe_does_not_create_the_file(tmp_path):
    """A plain sqlite3.connect() would CREATE the missing file, manufacturing the decoy."""
    db = tmp_path / "nope.db"
    config.corpus_state(db)
    assert not db.exists()


def test_trace_created_decoy_is_no_table(tmp_path):
    """The exact #25 failure: trace.py's file exists but has no `plans` table."""
    db = _make_db(tmp_path / "csi_v2.db", tables=("conversations",))
    assert config.corpus_state(db) == config.CORPUS_NO_TABLE


def test_initialised_but_unpopulated_is_empty(tmp_path):
    """00_init_db.py creates `plans` empty, so schema alone is not a loaded corpus."""
    db = _make_db(tmp_path / "csi_v2.db", tables=("conversations", "plans"), plan_rows=0)
    assert config.corpus_state(db) == config.CORPUS_EMPTY


def test_populated_corpus_is_ok(tmp_path):
    db = _make_db(tmp_path / "csi_v2.db", tables=("conversations", "plans"), plan_rows=8)
    assert config.corpus_state(db) == config.CORPUS_OK


def test_state_is_not_cached_across_calls(tmp_path):
    """trace.py can create the file mid-process, so a cached answer would go stale."""
    db = tmp_path / "csi_v2.db"
    assert config.corpus_state(db) == config.CORPUS_NO_FILE
    _make_db(db, tables=("plans",), plan_rows=1)
    assert config.corpus_state(db) == config.CORPUS_OK


# --- the three readers ---------------------------------------------------------------------------
@pytest.fixture
def db_at(tmp_path, monkeypatch):
    """Point final_report's DB_PATH at a throwaway database."""
    def _point(**kw):
        db = tmp_path / "csi_v2.db"
        if kw:
            _make_db(db, **kw)
        monkeypatch.setattr(final_report, "DB_PATH", db)
        return db
    return _point


@pytest.mark.parametrize("state", [
    {},                                                          # file absent
    {"tables": ("conversations",)},                              # trace decoy
    {"tables": ("conversations", "plans"), "plan_rows": 0},      # schema only
])
def test_readers_return_none_without_a_corpus(db_at, caplog, state):
    db_at(**state)
    with caplog.at_level("WARNING"):
        assert final_report._gotchas_from_db("any-plan") is None
        assert final_report._work_type_from_db("any-plan") is None
        assert final_report._resolve_corpus_plan_id({"sp_number": "SAP 021-600-023"}) is None
    assert "_gotchas_from_db" in caplog.text
    assert "_work_type_from_db" in caplog.text
    assert "_resolve_corpus_plan_id" in caplog.text


def test_no_corpus_and_corpus_miss_log_differently(db_at, caplog):
    """A setup problem must be distinguishable from an ordinary miss without opening the DB."""
    db_at(tables=("conversations",))
    with caplog.at_level("INFO"):
        final_report._resolve_corpus_plan_id({"sp_number": "SAP 021-600-023"})
    assert "setup problem" in caplog.text
    caplog.clear()

    # Corpus present, plan simply not in it.
    db = db_at(tables=("plans",), plan_rows=1)
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE gotchas (plan_id TEXT, flag_type TEXT)")
    con.commit()
    con.close()
    with caplog.at_level("INFO"):
        final_report._resolve_corpus_plan_id({"sp_number": "SAP 021-600-023"})
    assert "ordinary corpus miss" in caplog.text
    assert "setup problem" not in caplog.text


def test_populated_corpus_reads_normally(db_at):
    """No regression: with a real corpus the readers return data, not None."""
    db = db_at(tables=("plans",), plan_rows=1)
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE gotchas (id INTEGER PRIMARY KEY, plan_id TEXT, source_file TEXT, "
                "flag_type TEXT, family TEXT, decision_class TEXT, evidence TEXT, page INTEGER, "
                "page_count INTEGER, confidence TEXT)")
    con.execute("INSERT INTO gotchas (plan_id, flag_type, family, decision_class, evidence, page, "
                "page_count, confidence) VALUES (?,?,?,?,?,?,?,?)",
                ("021-600-023", "LIQUIDATED_DAMAGES", "schedule", "go_no_go", "LDs of $1,200/day",
                 4, 1, "high"))
    con.execute("CREATE TABLE plan_metrics (plan_id TEXT PRIMARY KEY, work_type TEXT)")
    con.execute("INSERT INTO plan_metrics VALUES (?, ?)", ("021-600-023", "Overlay"))
    con.commit()
    con.close()

    assert final_report._resolve_corpus_plan_id({"sp_number": "SAP 021-600-023"}) == "021-600-023"
    assert final_report._work_type_from_db("021-600-023") == "Overlay"
    got = final_report._gotchas_from_db("021-600-023")
    assert got["go_no_go"][0]["code"] == "LIQUIDATED_DAMAGES"


# --- startup warnings -----------------------------------------------------------------------------
def test_warnings_distinguishes_missing_file_from_empty_corpus(tmp_path, monkeypatch):
    missing = tmp_path / "gone.db"
    monkeypatch.setattr(config, "CSI_DB", missing)
    assert any("not found" in w for w in config.settings.warnings())

    decoy = _make_db(tmp_path / "csi_v2.db", tables=("conversations",))
    monkeypatch.setattr(config, "CSI_DB", decoy)
    msgs = [w for w in config.settings.warnings() if "corpus" in w.lower()]
    assert msgs and "exists but holds no plans" in msgs[0]
