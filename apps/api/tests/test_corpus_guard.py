"""
Tests for the plan-corpus presence check (issue #25), moved to Postgres by #50.

The bug these guard against has NOT changed: the three readers in final_report.py must not treat
"I cannot see a corpus" as "this plan has no gotchas", because that renders a confident, wrong
"zero gotchas" in the report. Only the storage engine changed.

What DID change is how the failure is reproduced. Under SQLite these tests built real database
files in tmp_path, because the decoy case was about what was *inside* a file that trace.py had
created. Postgres cannot manufacture that decoy — there is no file to bring into being — so the
equivalent states are now produced by stubbing `ci_db.get_conn`:

    no corpus reachable  -> get_conn raises ConfigError (no DSN) or any connection error
    no `plans` table     -> the count query raises (undefined table / no privilege)
    corpus empty         -> the count query returns 0
    corpus ok            -> the count query returns N > 0

GUARANTEE MAP (SQLite version -> this version). Recorded because rewriting a test file is exactly
where guarantees quietly weaken, and this needs to stay auditable later:

  OLD test                                    GUARANTEE                        NEW test
  ------------------------------------------  -------------------------------  ----------------------------------------
  test_absent_file_is_no_file                 unreachable corpus is detected   test_unreachable_corpus_is_no_file
  test_trace_created_decoy_is_no_table        reachable but no corpus table    test_missing_plans_table_is_no_table
  test_initialised_but_unpopulated_is_empty   schema alone is not a corpus     test_present_but_unpopulated_is_empty
  test_populated_corpus_is_ok                 the happy path still passes      test_populated_corpus_is_ok
  test_state_is_not_cached_across_calls       state is re-read every call      test_state_is_not_cached_across_calls
  test_readers_return_none_without_a_corpus   all 3 readers degrade + log      test_readers_return_none_without_a_corpus
  test_no_corpus_and_corpus_miss_log_differ.  setup problem != ordinary miss   test_no_corpus_and_corpus_miss_log_differently
  test_populated_corpus_reads_normally        no regression on the happy path  test_populated_corpus_reads_normally
  test_warnings_distinguishes_missing_file…   startup warning distinguishes    test_warnings_distinguishes_unreachable_from_empty_corpus
                                              unreachable from empty

  test_probe_does_not_create_the_file         DROPPED, and deliberately: it asserted that probing
                                              must not CREATE the SQLite file, which is the decoy
                                              mechanism itself. Postgres has no file to create, so
                                              the guarantee is now structural rather than tested.
                                              trace.py's own commit (226f897) verifies the property
                                              end-to-end by moving csi_v2.db away and confirming
                                              nothing recreates it.
  test_trace_and_final_report_share_one_db…   DROPPED: asserted trace.DB_PATH == final_report.DB_PATH
                                              == config.CSI_DB so reader and writer could not drift
                                              onto different files. Both now go through ci_db.get_conn
                                              and a single DSN, so divergence is not expressible.

TWO NEW CASES, covering states SQLite could not express:

  test_connection_failure_is_no_file_not_an_exception
      A dead network / auth failure mid-call must return CORPUS_NO_FILE, never raise into the
      report. Under SQLite the only failure was a local file being absent, which cannot throw a
      connection error; Postgres adds a whole class of transport failures on the read path.

  test_a_query_failure_degrades_rather_than_raising
      The corpus is present and healthy, but the gotchas/plan_metrics query itself fails mid-read
      (e.g. the server closes the connection). The readers must return None, not propagate. SQLite
      had no equivalent — a local file that opened successfully did not then fail mid-statement.

  test_db_path_argument_is_accepted_and_ignored
      corpus_state still takes db_path for signature compatibility and must ignore it. Guards
      against someone "fixing" the unused parameter by reintroducing a file check.

Run from the apps/api/ directory:   ../../.venv/bin/python3 -m pytest -q
"""
from contextlib import contextmanager

import pytest

from backend import ci_db, config, final_report


# --- fake connection plumbing --------------------------------------------------------------------
class _FakeCursor:
    """Answers the handful of queries the corpus readers issue, by substring match.

    Deliberately not a general SQL engine: matching on a fragment keeps each test's intent visible
    at the call site, and an unrecognised query raises rather than silently returning [].
    """

    def __init__(self, responses):
        self._responses = responses
        self._rows = []

    def execute(self, sql, params=None):
        for fragment, value in self._responses.items():
            if fragment in sql:
                if isinstance(value, Exception):
                    raise value
                self._rows = value
                return self
        raise AssertionError(f"unstubbed query: {sql!r}")

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return self._rows

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class _FakeConn:
    def __init__(self, responses):
        self._responses = responses

    def cursor(self):
        return _FakeCursor(self._responses)

    def rollback(self):
        pass


def _stub_conn(monkeypatch, responses, *, raises=None):
    """Point ci_db.get_conn at a fake connection. `raises` makes get_conn itself blow up."""
    @contextmanager
    def fake_get_conn():
        if raises is not None:
            raise raises
        yield _FakeConn(responses)
    monkeypatch.setattr(ci_db, "get_conn", fake_get_conn)


PLANS = "from public.plans"
GOTCHAS = "from public.gotchas"
METRICS = "from public.plan_metrics"


def _corpus(n_plans):
    return {PLANS: [{"n": n_plans}]}


# --- corpus_state, the four states ---------------------------------------------------------------
def test_unreachable_corpus_is_no_file(monkeypatch):
    """No DSN configured. CORPUS_NO_FILE keeps its name for callers; it now means 'unreachable'."""
    _stub_conn(monkeypatch, {}, raises=ci_db.ConfigError("SUPABASE_TEAM_DB_URL is not set"))
    assert config.corpus_state() == config.CORPUS_NO_FILE


def test_connection_failure_is_no_file_not_an_exception(monkeypatch):
    """A dead network must degrade the report, never raise into it."""
    _stub_conn(monkeypatch, {}, raises=OSError("connection refused"))
    assert config.corpus_state() == config.CORPUS_NO_FILE


def test_missing_plans_table_is_no_table(monkeypatch):
    """The Postgres analogue of the old trace.py decoy: reachable, but no corpus in it."""
    _stub_conn(monkeypatch, {PLANS: RuntimeError('relation "public.plans" does not exist')})
    assert config.corpus_state() == config.CORPUS_NO_TABLE


def test_present_but_unpopulated_is_empty(monkeypatch):
    """Schema alone is not a loaded corpus — the failure most likely to look like success."""
    _stub_conn(monkeypatch, _corpus(0))
    assert config.corpus_state() == config.CORPUS_EMPTY


def test_populated_corpus_is_ok(monkeypatch):
    _stub_conn(monkeypatch, _corpus(117))
    assert config.corpus_state() == config.CORPUS_OK


def test_state_is_not_cached_across_calls(monkeypatch):
    """Another process can load the corpus mid-run, so a cached answer would go stale.

    Same guarantee as the SQLite version, which guarded against trace.py creating the file
    mid-process.
    """
    _stub_conn(monkeypatch, _corpus(0))
    assert config.corpus_state() == config.CORPUS_EMPTY
    _stub_conn(monkeypatch, _corpus(5))
    assert config.corpus_state() == config.CORPUS_OK


def test_db_path_argument_is_accepted_and_ignored(monkeypatch):
    """Signature compatibility: callers still pass a path; it must not change the answer."""
    _stub_conn(monkeypatch, _corpus(117))
    assert config.corpus_state(config.CSI_DB) == config.CORPUS_OK
    assert config.corpus_state(config.PLAN_READER / "does-not-exist.db") == config.CORPUS_OK


# --- the three readers ---------------------------------------------------------------------------
@pytest.mark.parametrize("responses,raises", [
    ({}, ci_db.ConfigError("no DSN")),                                    # unreachable
    ({PLANS: RuntimeError("undefined table")}, None),                     # no plans table
    (_corpus(0), None),                                                   # empty corpus
])
def test_readers_return_none_without_a_corpus(monkeypatch, caplog, responses, raises):
    _stub_conn(monkeypatch, responses, raises=raises)
    with caplog.at_level("WARNING"):
        assert final_report._gotchas_from_db("any-plan") is None
        assert final_report._work_type_from_db("any-plan") is None
        assert final_report._resolve_corpus_plan_id({"sp_number": "SAP 021-600-023"}) is None
    assert "_gotchas_from_db" in caplog.text
    assert "_work_type_from_db" in caplog.text
    assert "_resolve_corpus_plan_id" in caplog.text


def test_no_corpus_and_corpus_miss_log_differently(monkeypatch, caplog):
    """A setup problem must be distinguishable from an ordinary miss without opening the DB."""
    _stub_conn(monkeypatch, _corpus(0))
    with caplog.at_level("INFO"):
        final_report._resolve_corpus_plan_id({"sp_number": "SAP 021-600-023"})
    assert "setup problem" in caplog.text
    caplog.clear()

    # Corpus present, plan simply not in it.
    _stub_conn(monkeypatch, {**_corpus(117), GOTCHAS: []})
    with caplog.at_level("INFO"):
        final_report._resolve_corpus_plan_id({"sp_number": "SAP 021-600-023"})
    assert "ordinary corpus miss" in caplog.text
    assert "setup problem" not in caplog.text


def test_populated_corpus_reads_normally(monkeypatch):
    """No regression: with a real corpus the readers return data, not None."""
    _stub_conn(monkeypatch, {
        **_corpus(117),
        GOTCHAS: [{"plan_id": "021-600-023", "flag_type": "LIQUIDATED_DAMAGES",
                   "family": "schedule", "decision_class": "go_no_go",
                   "evidence": "LDs of $1,200/day", "page": 4, "page_count": 1,
                   "confidence": "high"}],
        METRICS: [{"work_type": "Overlay"}],
    })
    assert final_report._resolve_corpus_plan_id({"sp_number": "SAP 021-600-023"}) == "021-600-023"
    assert final_report._work_type_from_db("021-600-023") == "Overlay"
    got = final_report._gotchas_from_db("021-600-023")
    assert got["go_no_go"][0]["code"] == "LIQUIDATED_DAMAGES"


def test_a_query_failure_degrades_rather_than_raising(monkeypatch):
    """The corpus is loaded but the query itself blows up mid-read. The report must survive."""
    _stub_conn(monkeypatch, {**_corpus(117), GOTCHAS: RuntimeError("server closed the connection"),
                             METRICS: RuntimeError("server closed the connection")})
    assert final_report._gotchas_from_db("021-600-023") is None
    assert final_report._work_type_from_db("021-600-023") is None


# --- startup warnings -----------------------------------------------------------------------------
def test_warnings_distinguishes_unreachable_from_empty_corpus(monkeypatch):
    _stub_conn(monkeypatch, {}, raises=ci_db.ConfigError("no DSN"))
    assert any("corpus" in w.lower() for w in config.settings.warnings())

    _stub_conn(monkeypatch, _corpus(0))
    msgs = [w for w in config.settings.warnings() if "corpus" in w.lower()]
    assert msgs and "holds no plans" in msgs[0]
