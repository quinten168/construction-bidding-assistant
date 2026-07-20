"""
Project registry + name/location resolution.

The three data universes — the bid record (master CSV, 1,592 projects), the plan corpus (the
manifest's 117 ingested plans), and the v2 archetype — are only loosely linked by `contract_id`.
This module unifies them ONCE into a single registry (one row per project, enriched with archetype
+ whether a plan document exists) and exposes `find_projects(query)` to resolve a fuzzy
name / location / id to actual project(s).

Scoring is location-and-identifier-first, because those are what users actually anchor on:
  • LOCATION  — a county / city / state named in the query strongly boosts projects there.
  • CODE      — a route or SP/CP/PCN/contract number boosts projects whose ids/name contain it.
  • NAME      — token-set fuzzy match on the project name handles the descriptive remainder.
This ordering is deliberate: "Dunn County reconstruct" should rank Dunn projects above an Otter
Tail project that merely has the word "reconstruct" in its name.
"""
from __future__ import annotations

import re
from functools import lru_cache

import pandas as pd
from rapidfuzz import fuzz, process

from .config import MASTER_CSV, PLAN_READER

MANIFEST = PLAN_READER / "00_input" / "plans" / "plans_manifest.csv"
MAT = ["MIX_TN", "GRADE_CY", "BASE_TN", "SHLDR_TN", "MILL_SY", "CRUSH_TN", "STOCK_TN"]
TON_COLS = ["MIX_TN", "BASE_TN", "SHLDR_TN", "CRUSH_TN", "STOCK_TN"]
_MIX_SHARE_MIN, _MIX_ABS_MIN, _GRADE_MIN, _MILL_MIN = 0.15, 1000.0, 500.0, 1000.0

_STATE_FULL = {"minnesota", "north dakota", "south dakota", "iowa", "nebraska", "montana"}
_STATE_ABBR = {"mn": "minnesota", "nd": "north dakota", "sd": "south dakota",
               "ia": "iowa", "ne": "nebraska", "mt": "montana"}


def _to_num(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s.astype(str).str.replace(",", "", regex=False)
                         .str.replace("$", "", regex=False).str.strip().replace("", "nan"),
                         errors="coerce")


def _bare_county(s: pd.Series) -> pd.Series:
    return (s.fillna("").astype(str).str.lower()
            .str.replace(r"\s*county\s*$", "", regex=True).str.strip())


def _archetype(r) -> str:
    """v2 work-type from the 7 quantities (NaN-safe)."""
    g = lambda k: (float(r[k]) if k in r and pd.notna(r[k]) else 0.0)
    if not any(g(k) > 0 for k in MAT):
        return "Unknown/NoQty"
    total = sum(g(k) for k in TON_COLS)
    mix_share = g("MIX_TN") / total if total > 0 else 0.0
    paving = (mix_share >= _MIX_SHARE_MIN) or (g("MIX_TN") >= _MIX_ABS_MIN)
    grade, mill = g("GRADE_CY") >= _GRADE_MIN, g("MILL_SY") >= _MILL_MIN
    if paving:
        if grade: return "Reconstruct/Rebuild"
        if mill:  return "Mill & Overlay"
        return "HMA Overlay/Resurface"
    if grade: return "Grading/Earthwork"
    if g("BASE_TN") > 0 or g("SHLDR_TN") > 0: return "Aggregate/Base/Gravel"
    return "Other"


@lru_cache(maxsize=1)
def _registry() -> pd.DataFrame:
    # --- master projects (the bid record) -------------------------------------------------------
    df = pd.read_csv(MASTER_CSV, dtype=str, low_memory=False)
    for c in MAT:
        df[c] = _to_num(df[c])
    proj = df.sort_values("Contract_Id").drop_duplicates("Contract_Id").copy()
    proj["archetype"] = proj.apply(_archetype, axis=1)
    for c in ["Project_Name", "State", "County", "City"]:
        if c not in proj.columns:
            proj[c] = ""

    csi = df[df["Is_CSI"] == "TRUE"].copy()
    csi["_w"] = (csi["Is_Winner"] == "TRUE").astype(int)
    csi = (csi.sort_values("_w", ascending=False).drop_duplicates("Contract_Id")
              [["Contract_Id", "Is_Winner", "Margin_Pct"]]
              .rename(columns={"Is_Winner": "_won", "Margin_Pct": "csi_margin"}))
    proj = proj.merge(csi, on="Contract_Id", how="left")

    reg = pd.DataFrame({
        "project_name": proj["Project_Name"].fillna(""),
        "state": proj["State"].fillna(""),
        "county": proj["County"].fillna(""),
        "city": proj["City"].fillna(""),
        "contract_id": proj["Contract_Id"].fillna(""),
        "sp_number": "",
        "archetype": proj["archetype"],
        "csi_bid": proj["CSI_Participated"] == "TRUE",
        "csi_won": proj["_won"] == "TRUE",
        "csi_margin": proj["csi_margin"],
        "plan_id": pd.NA,
    })

    # --- plan-corpus projects (the ingested plans) ----------------------------------------------
    # Fold in every plan from the manifest. Where a plan's contract_id matches a master project we
    # attach the plan to that row; plans with no master match (e.g. NOBIDs CSI never bid) are added
    # as their own rows so they are still findable by name/location/SP.
    if MANIFEST.exists():
        man = pd.read_csv(MANIFEST, dtype=str).fillna("")
        cid_to_idx = {c: i for i, c in reg["contract_id"].items() if c}
        new_rows = []
        for _, p in man.iterrows():
            cid = p.get("contract_id", "")
            if cid and cid in cid_to_idx:
                i = cid_to_idx[cid]
                reg.at[i, "plan_id"] = p["plan_id"]
                if not reg.at[i, "sp_number"]:
                    reg.at[i, "sp_number"] = p.get("sp_number", "")
            else:
                state = _STATE_ABBR.get(str(p.get("state", "")).lower(), p.get("state", ""))
                outcome = p.get("outcome", "")
                new_rows.append({
                    "project_name": p["plan_id"], "state": state.title(),
                    "county": p.get("county", ""), "city": "", "contract_id": cid,
                    "sp_number": p.get("sp_number", ""), "archetype": "Unknown/NoQty",
                    "csi_bid": outcome in ("bid_won", "bid_lost"),
                    "csi_won": outcome == "bid_won", "csi_margin": pd.NA, "plan_id": p["plan_id"],
                })
        if new_rows:
            reg = pd.concat([reg, pd.DataFrame(new_rows)], ignore_index=True)

    reg["has_plan"] = reg["plan_id"].notna() & (reg["plan_id"].astype(str) != "")

    # --- matching columns -----------------------------------------------------------------------
    reg["county_bare"] = _bare_county(reg["county"])
    reg["city_l"] = reg["city"].fillna("").astype(str).str.lower().str.strip()
    reg["state_l"] = reg["state"].fillna("").astype(str).str.lower().str.strip()
    reg["name_l"] = reg["project_name"].fillna("").astype(str).str.lower()
    reg["id_blob"] = (reg[["sp_number", "contract_id", "project_name"]]
                      .fillna("").astype(str).agg(" ".join, axis=1).str.lower())
    return reg.reset_index(drop=True)


def find_projects(query: str, limit: int = 5) -> dict:
    """Resolve a name / location / id to candidate projects, best match first."""
    reg = _registry()
    qn = re.sub(r"[^a-z0-9 ]", " ", query.lower()).strip()

    # which locations does the query mention?
    counties = {c for c in reg["county_bare"].unique()
                if c and re.search(rf"\b{re.escape(c)}\b", qn)}
    cities = {c for c in reg["city_l"].unique()
              if c and len(c) > 2 and re.search(rf"\b{re.escape(c)}\b", qn)}
    states = {s for s in _STATE_FULL if s in qn}
    states |= {full for ab, full in _STATE_ABBR.items() if re.search(rf"\b{ab}\b", qn)}

    loc = (reg["county_bare"].isin(counties).astype(float) * 40
           + reg["city_l"].isin(cities).astype(float) * 25
           + reg["state_l"].isin(states).astype(float) * 10)

    # route / id codes in the query (tokens containing a digit) — longer = more specific
    codes = [t for t in re.findall(r"[a-z]*-?\d[a-z0-9()\-]*", query.lower()) if len(t) >= 2]
    code_boost = pd.Series(0.0, index=reg.index)
    for tok in codes:
        code_boost += reg["id_blob"].str.contains(re.escape(tok), regex=True).astype(float) \
            * (18 + min(len(tok), 6) * 5)

    fuzzy_pairs = process.extract(qn, reg["name_l"].to_dict(),
                                  scorer=fuzz.token_set_ratio, limit=len(reg))
    fuzzy = pd.Series({idx: sc for _, sc, idx in fuzzy_pairs}).reindex(reg.index).fillna(0)

    reg = reg.assign(_score=loc + code_boost + 0.4 * fuzzy)
    top = reg.sort_values("_score", ascending=False).head(limit)
    top = top[top["_score"] >= 25]

    matches = [{
        "project_name": r["project_name"], "state": r["state"], "county": r["county"],
        "contract_id": r["contract_id"] or None, "sp_number": r["sp_number"] or None,
        "archetype": r["archetype"],
        "csi_bid": bool(r["csi_bid"]), "csi_won": bool(r["csi_won"]),
        "csi_margin": (None if pd.isna(r["csi_margin"]) else r["csi_margin"]),
        "has_plan_document": bool(r["has_plan"]),
        "plan_id": (None if pd.isna(r["plan_id"]) else r["plan_id"]),
        "match_score": round(float(r["_score"]), 1),
    } for _, r in top.iterrows()]

    note = ("No project matched closely — try a county, route, SP/CP number, or part of the name."
            if not matches else
            "If several match, ask the user which one before drilling in. "
            "has_plan_document=true means you can also search_plans for its contents (filter by plan_id).")
    return {"query": query, "n_matches": len(matches), "matches": matches, "note": note}


TOOL_SCHEMA = {
    "name": "find_projects",
    "description": (
        "Resolve a project the user names or describes — by name, location (county/city/route), or "
        "an id like an SP/CP/PCN/contract number — to the actual project record(s). Use this when "
        "the user asks about a SPECIFIC project ('the Stearns CP-073 job', 'the Highway 23 project', "
        "'Dunn County reconstruct'). Returns matching projects with their archetype, whether CSI bid/"
        "won, and whether a plan document is ingested (so you can then search_plans for its contents, "
        "filtering by plan_id). If several match, present them and ask which one."),
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {"type": "string",
                      "description": "The project name, location, or id the user mentioned."},
        },
        "required": ["query"],
    },
}


def run(tool_input: dict) -> dict:
    return find_projects(tool_input["query"])
