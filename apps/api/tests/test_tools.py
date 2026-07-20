"""
Unit/integration tests for the data tools (no LLM calls — fast, deterministic).

These guard the two structured tools against regressions: the bid-history lookup and the
project resolver. They read the real data files, so they double as a smoke test that the
data is wired correctly.

Run from the bid_assistant/ directory:   ../../.venv/bin/python3 -m pytest -q
"""
from backend import bid_data, project_registry, tools


# --- bid history --------------------------------------------------------------------------------
def test_bid_history_south_dakota_has_bids():
    r = bid_data.query_bid_history(state="South Dakota")
    assert r["n_bids"] > 0
    assert 0 <= r["win_rate_pct"] <= 100
    assert set(r["by_year"]).issubset({"2023", "2024", "2025"})


def test_bid_history_accepts_abbreviation():
    full = bid_data.query_bid_history(state="South Dakota")
    abbr = bid_data.query_bid_history(state="SD")
    assert full["n_bids"] == abbr["n_bids"]          # "SD" resolves to "South Dakota"


def test_bid_history_empty_slice_reports_options():
    r = bid_data.query_bid_history(state="Nowhere")
    assert r["n_bids"] == 0
    assert r["available_states"]                      # tells the model what *is* available


# --- project resolution -------------------------------------------------------------------------
def test_registry_unions_master_and_plans():
    reg = project_registry._registry()
    assert len(reg) > 1600                            # ~1592 master + plan-only rows
    assert reg["has_plan"].sum() >= 100               # the ingested plans are folded in


def test_find_resolves_named_plan_project():
    r = project_registry.find_projects("Stearns CP-073")
    top = r["matches"][0]
    assert "073" in (top["plan_id"] or "") + top["project_name"]
    assert top["has_plan_document"] is True


def test_find_location_beats_descriptive_word():
    # "Dunn County reconstruct" must rank Dunn projects above an unrelated "reconstruct" name
    r = project_registry.find_projects("Dunn County reconstruct")
    assert r["matches"], "expected at least one match"
    assert "dunn" in r["matches"][0]["county"].lower()


# --- tool registry ------------------------------------------------------------------------------
def test_registry_exposes_all_tools():
    assert set(tools.REGISTRY) == {"search_plans", "query_bid_history", "find_projects",
                                   "query_competitors", "competitor_record", "record_correction"}
    assert len(tools.SCHEMAS) == 6
    for schema in tools.SCHEMAS:
        assert "name" in schema and "input_schema" in schema


def test_correction_roundtrips_and_canonicalizes():
    from backend import corrections
    corrections.save_correction("__test_plan__", "lat/long", "45.62,-95.05")
    corrections.save_correction("__test_plan__", "mix", "5200")
    cv = corrections.corrected_values("__test_plan__")
    assert cv["lat_long"] == "45.62,-95.05"          # alias → canonical
    assert cv["hot_mix_tons"] == "5200"              # alias → canonical


def test_competitors_south_dakota():
    from backend import competitors
    r = competitors.query_competitors(state="South Dakota")
    assert r["n_competitors"] > 0
    assert all(0 <= c["beat_csi_pct"] <= 100 for c in r["competitors"])
