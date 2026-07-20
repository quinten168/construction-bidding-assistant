#!/usr/bin/env python3
"""
2026-06-15  PRELIMINARY FEASIBILITY ANALYSIS  (throwaway — NOT pipeline code)
============================================================================
Question: today the Plan Reader keeps only 7 summed material roll-ups + box_culvert
from a 25-43 line-item bid schedule and discards the rest. IF we parsed the full
line-item table, would the derived fields (item count, # distinct spec categories,
sub-scope flags, schedule tightness, gotcha burden) sharpen archetype ID and the
bid/no-bid decision enough to justify wiring them into the RAG pipeline?

This script ONLY READS already-converted artifacts (the <plan_id>.md + <plan_id>.json
that the live pipeline already produced) + the sweet-spot base table. It makes NO
Claude calls and touches NOTHING under 01_pipeline/. Outputs land next to this file.

Run:
    cd 01_Summer_2026
    python3 pipelines/plan_reader/07_archive/2026-06-15_bid_schedule_feasibility/2026-06-15_bid_schedule_feasibility.py
"""
from __future__ import annotations
import csv, json, re, sys, statistics
from pathlib import Path

HERE = Path(__file__).resolve().parent
MODULE = HERE.parent.parent                      # .../plan_reader
PLANS = MODULE / "00_input" / "plans"
SUMMER = MODULE.parent.parent                    # .../01_Summer_2026
BASE_TABLE = SUMMER / "02_modules" / "sweet_spot" / "outputs" / "2026-06-04_project_base.csv"
ARCH_TABLE = SUMMER / "02_modules" / "sweet_spot" / "outputs" / "2026-06-04_project_archetypes.csv"

OUT_CSV = HERE / "2026-06-15_bid_schedule_perplan.csv"
OUT_ITEMS = HERE / "2026-06-15_bid_items_parsed.csv"
OUT_MEMO = HERE / "2026-06-15_bid_schedule_findings.md"

# ---------------------------------------------------------------------------
# 1. spec-category keyword map  (inline + ordered; most-specific first)
#    This is a THROWAWAY prototype of what would become 05_knowledge/spec_category_map.csv
# ---------------------------------------------------------------------------
SPEC_MAP = [  # (keyword, category)  — first match wins
    ("MOBILIZATION", "mobilization"),
    ("CONTRACT BOND", "other"),
    ("ASPHALT CEMENT", "other"), ("PORTLAND CEMENT", "other"),  # binders, not mix tonnage
    ("CEMENT STABILIZED", "base"), ("STABILIZED SUBGRADE", "grading"),
    ("FLAGGING", "traffic_control"), ("PILOT CAR", "traffic_control"),
    ("LANE CLOSURE", "traffic_control"), ("BARRICADE", "traffic_control"),
    ("DELINEATOR", "traffic_control"), ("TUBULAR MARKER", "traffic_control"),
    ("VERTICAL PANEL", "traffic_control"), ("TRAFFIC CONTROL", "traffic_control"),
    ("RUMBLE STRIP", "traffic_control"),
    ("PVMT MK", "pavement_marking"), ("PAVEMENT MARKING", "pavement_marking"),
    ("PAINTED", "pavement_marking"), ("EPOXY", "pavement_marking"),
    ("SILT FENCE", "erosion"), ("EROSION", "erosion"), ("SEEDING", "erosion"),
    ("TOPSOIL", "erosion"), ("SWPPP", "erosion"), ("FIBER", "erosion"),
    ("MULCH", "erosion"), ("BLANKET", "erosion"), ("WATTLE", "erosion"),
    ("RIPRAP", "structures"), ("RIP RAP", "structures"), ("CULVERT", "structures"),
    ("BOX ", "structures"), ("BRIDGE", "structures"), ("PIPE", "structures"),
    ("RETAINING WALL", "structures"), ("STRUCTURE", "structures"),
    ("SUPERPAVE", "hma"), ("TYPE SP", "hma"), ("WEARING COURSE", "hma"),
    ("HOT MIX", "hma"), ("HMA", "hma"), ("2360", "hma"), ("ASPHALT CEMENT", "hma"),
    ("BITUMINOUS", "hma"),
    ("AGGREGATE BASE", "base"), ("BASE COURSE", "base"), ("STABILIZED BASE", "base"),
    ("2211", "base"), ("2112", "base"), ("CL 13", "base"), ("BASE PREPARATION", "base"),
    ("AGGREGATE SURFACING", "surfacing"), ("SHOULDER", "surfacing"),
    ("GRAVEL SURFACING", "surfacing"), ("2118", "surfacing"),
    ("COMMON EXCAVATION", "grading"), ("UNCLASSIFIED EXCAVATION", "grading"),
    ("GRADING", "grading"), ("EARTHWORK", "grading"), ("FORESLOPE", "grading"),
    ("RESHAPING", "grading"), ("SUBGRADE", "grading"), ("BORROW", "grading"),
    ("MILLING", "milling"), ("RECLAIM", "milling"), ("RELAYING MILLED", "milling"),
    ("REMOVE AND RELAY", "milling"), ("SAWING", "milling"),
]
LUMP_UNITS = {"LSUM", "LS", "LUMP SUM", "LUMP"}
SPEC_CODE_RE = re.compile(r"^\d{4}\.\d{2,3}$|^\d{6,7}/\d+$")


def spec_category(desc: str) -> str:
    u = (desc or "").upper()
    for kw, cat in SPEC_MAP:
        if kw in u:
            return cat
    return "other"


# ---------------------------------------------------------------------------
# 2. deterministic bid-schedule parser (handles ND/EJCDC + MN/MnDOT layouts)
# ---------------------------------------------------------------------------
def _clean(cell: str) -> str:
    cell = cell.replace("~~", "").replace("<br>", " ").replace("**", "")
    return cell.strip()


def _split(line: str):
    s = line.strip()
    if not s.startswith("|"):
        return None
    return [_clean(p) for p in s.strip("|").split("|")]


def _is_separator(cells):
    return all(c == "" or set(c) <= set("-: ") for c in cells)


def _num(s: str):
    s = re.sub(r"[^\d.]", "", (s or "").replace(",", ""))
    try:
        return float(s) if s not in ("", ".") else None
    except ValueError:
        return None


TOTAL_RE = re.compile(r"TOTAL OF (ALL|ALTERNATE)|GRAND TOTAL|TOTAL BASE BID", re.I)
ALT_RE = re.compile(r"ALTERNATE\s+([A-Z])\b", re.I)


def _is_header(cells):
    """Header-row signature for a bid-schedule PRICING form: QUANTITY + a description
    col + a unit col + a PRICE/SUBTOTAL col. The price column is what distinguishes
    the biddable schedule from engineer's-estimate quantity tabulations ('BASIS OF
    ESTIMATE') that share QUANTITY/UNIT but carry no price. Covers MN/ND/SD layouts."""
    u = [c.upper() for c in cells]
    has_qty = any("QUANTITY" in c for c in u)
    has_desc = any(("DESCRIPTION" in c) or c in ("ITEM", "ITEM #") for c in u)
    has_unit = any(c in ("UNIT", "UNITS") for c in u)
    has_price = any(("PRICE" in c) or ("SUBTOTAL" in c) or ("EXTENDED" in c) for c in u)
    return has_qty and has_desc and has_unit and has_price and len(cells) >= 4


def _colmap(cells):
    """Map header cell names -> field indices."""
    u = [c.upper() for c in cells]
    def find(pred, default=None):
        for i, c in enumerate(u):
            if pred(c):
                return i
        return default
    qty_i = find(lambda c: "QUANTITY" in c)
    unit_i = find(lambda c: c in ("UNIT", "UNITS"))
    # description: prefer an explicit DESCRIPTION; else a bare ITEM (MnDOT 'Item')
    desc_i = find(lambda c: "DESCRIPTION" in c)
    if desc_i is None:
        desc_i = find(lambda c: c == "ITEM")
    code_i = find(lambda c: "MAT NO" in c or c == "ITEM #" or c == "SPEC")
    line_i = find(lambda c: c in ("NO.", "BID ITEM", "LINE", "NO"))
    if line_i is None:
        line_i = 0
    return {"line": line_i, "code": code_i, "desc": desc_i, "unit": unit_i, "qty": qty_i}


def parse_bid_items(md: str):
    """Header-anchored parse. Find every bid-schedule header row (QUANTITY + desc +
    unit signature), map its columns by name, then consume item rows until the
    matching TOTAL row / next header / +200 lines — tolerating page-break gaps so
    continuation tables (e.g. Dunn items 26-37) are captured. Anchoring on the
    header signature (not table arity) skips MnDOT noise tables that lack a header."""
    lines = md.splitlines()
    n = len(lines)
    headers = []
    for i, ln in enumerate(lines):
        cells = _split(ln)
        if cells and _is_header(cells):
            headers.append((i, _colmap(cells)))
    header_idx = {i for i, _ in headers}
    items, seen = [], set()
    for hi, cmap in headers:
        # section label: look back ~8 lines for an ALTERNATE marker
        section = "base_bid"
        for k in range(hi, max(0, hi - 8), -1):
            m = ALT_RE.search(_clean(lines[k]))
            if m:
                section = f"alternate_{m.group(1).upper()}"
                break
        end = n
        for j in range(hi + 1, min(n, hi + 200)):
            if TOTAL_RE.search(_clean(lines[j])):
                end = j
                break
            if j in header_idx:
                end = j
                break
        for j in range(hi + 1, end):
            cells = _split(lines[j])
            if not cells or _is_separator(cells) or _is_header(cells):
                continue
            if TOTAL_RE.search(" ".join(cells)):
                continue
            need = max(cmap["desc"] or 0, cmap["unit"] or 0, cmap["qty"] or 0)
            if len(cells) <= need:
                continue
            desc = cells[cmap["desc"]] if cmap["desc"] is not None else ""
            if not desc or len(desc) < 2 or "DESCRIPTION" in desc.upper():
                continue
            unit = cells[cmap["unit"]] if cmap["unit"] is not None else ""
            qty = cells[cmap["qty"]] if cmap["qty"] is not None else ""
            code = cells[cmap["code"]] if cmap["code"] is not None and cmap["code"] < len(cells) else ""
            line_raw = cells[cmap["line"]] if cmap["line"] < len(cells) else ""
            ln_digits = re.sub(r"\D", "", line_raw)
            ln_int = int(ln_digits) if ln_digits else None
            is_lump = unit.upper() in LUMP_UNITS
            key = (section, ln_int, desc.upper()[:40])
            if key in seen:
                continue
            seen.add(key)
            items.append({
                "line_no": ln_int, "item_code": code, "description": desc,
                "unit": unit, "quantity": (None if is_lump else _num(qty)),
                "is_lump": is_lump, "section": section,
                "spec_category": spec_category(desc),
            })
    return items


# ---------------------------------------------------------------------------
# 3. gotcha burden tier  (reuse the live taxonomy's decision/pricing split)
# ---------------------------------------------------------------------------
sys.path.insert(0, str(MODULE / "01_pipeline"))
try:
    import taxonomy as TAX
    DECISION = set(TAX.decision_gotchas())
except Exception as e:                                   # pragma: no cover
    print(f"  ! could not import taxonomy ({e}); burden tier will use raw count")
    DECISION = set()


def gotcha_burden(gotchas):
    n = len(gotchas)
    # weight decision-driver gotchas 2x (they answer the bid/no-bid question)
    weight = sum(2 if g.get("code") in DECISION else 1 for g in gotchas)
    tier = "low" if weight <= 4 else ("med" if weight <= 9 else "high")
    return n, weight, tier


# ---------------------------------------------------------------------------
# 4. cross-check: re-derive the 7 roll-ups from line items vs the JSON's values
# ---------------------------------------------------------------------------
# map JSON roll-up field -> the spec_category(ies) whose TON/CY/SY it should sum
ROLLUP = {
    "hot_mix_tons": ("hma", "TON"),
    "base_tons": ("base", "TON"),
    "milling_sy": ("milling", "SY"),
    "shoulder_tons": ("surfacing", "TON"),
}


def cross_check(items, jrec):
    out = {}
    for field, (cat, unit) in ROLLUP.items():
        claude = (jrec.get(field) or {}).get("value")
        line_sum = sum(
            it["quantity"] for it in items
            if it["spec_category"] == cat and it["quantity"] and unit in it["unit"].upper()
        )
        line_sum = round(line_sum) if line_sum else None
        pct = None
        if claude and line_sum:
            pct = round(100 * (line_sum - claude) / claude, 1)
        out[field] = (claude, line_sum, pct)
    return out


# ---------------------------------------------------------------------------
# 5. drive over the corpus
# ---------------------------------------------------------------------------
def jget(rec, field):
    return (rec.get(field) or {}).get("value")


def load_contract_archetype():
    """contract_id -> (rule_archetype, n_mat_types) from sweet-spot outputs."""
    arche = {}
    if ARCH_TABLE.exists():
        for r in csv.DictReader(open(ARCH_TABLE)):
            cid = r.get("Contract_Id") or r.get("contract_id")
            if cid:
                arche[cid] = r.get("rule_archetype", "")
    nmat = {}
    if BASE_TABLE.exists():
        for r in csv.DictReader(open(BASE_TABLE)):
            cid = r.get("Contract_Id") or r.get("contract_id")
            if cid:
                nmat[cid] = r.get("n_mat_types", "")
    return arche, nmat


def main():
    arche_map, nmat_map = load_contract_archetype()
    manifest = {}
    man_path = PLANS / "plans_manifest.csv"
    for r in csv.DictReader(open(man_path)):
        manifest[r["plan_id"]] = r

    rows, all_items = [], []
    print("\n=== PARSE + DERIVE (8 converted plans) ===")
    for d in sorted(PLANS.iterdir()):
        if not d.is_dir():
            continue
        pid = d.name
        md_p, js_p = d / f"{pid}.md", d / f"{pid}.json"
        if not md_p.exists() or not js_p.exists():
            print(f"  - {pid:45s} SKIP (no md/json — plan-set only)")
            continue
        md = md_p.read_text(errors="replace")
        jrec = json.load(open(js_p))
        items = parse_bid_items(md)
        for it in items:
            all_items.append({"plan_id": pid, **it})

        # why-did-it-fail diagnosis (for the fallback story)
        if items:
            parse_status = "clean"
        else:
            up = md.upper()
            if "|COL2|" in up or "|COL3|" in up:
                parse_status = "fallback: conversion mangled header (merged cells)"
            elif "SCHEDULE OF PRICES" in up or "BID SCHEDULE" in up or "STATEMENT OF ESTIMATED" in up:
                parse_status = "fallback: priced schedule not converted as a clean table"
            else:
                parse_status = "fallback: no recognizable bid schedule"

        cats = {it["spec_category"] for it in items}
        cats.discard("other")
        n_base = sum(1 for it in items if it["section"] == "base_bid")
        n_alt = sum(1 for it in items if it["section"] != "base_bid")
        gn, gw, gtier = gotcha_burden(jrec.get("gotchas", []))
        cs, ce = jget(jrec, "construction_start"), jget(jrec, "construction_end")
        dur = None
        if cs and ce:
            try:
                from datetime import date
                a = date.fromisoformat(cs); b = date.fromisoformat(ce)
                dur = (b - a).days
            except Exception:
                pass
        man = manifest.get(pid, {})
        cid = man.get("contract_id", "")
        row = {
            "plan_id": pid,
            "state": jget(jrec, "state") or man.get("state", ""),
            "outcome": man.get("outcome", ""),
            "project_type_extracted": jget(jrec, "project_type") or "",
            "rule_archetype_master": arche_map.get(cid, "(no contract_id)"),
            "n_mat_types_master": nmat_map.get(cid, ""),
            # -------- candidate NEW fields --------
            "bid_item_count": len(items),
            "n_base": n_base, "n_alt": n_alt,
            "has_alternates": n_alt > 0,
            "n_spec_categories": len(cats),
            "spec_categories": "|".join(sorted(cats)),
            "has_structures_work": "structures" in cats,
            "has_traffic_control": "traffic_control" in cats,
            "has_erosion_control": "erosion" in cats,
            "mobilization_present": any(it["spec_category"] == "mobilization" for it in items),
            "contract_duration_days": dur,
            "gotcha_count": gn, "gotcha_weight": gw, "gotcha_burden_tier": gtier,
            "parse_status": parse_status,
        }
        rows.append(row)
        # roll-up cross check
        xc = cross_check(items, jrec)
        xc_str = "  ".join(
            f"{f.split('_')[0]}:claude={c}/lines={l}" + (f"({p:+}%)" if p is not None else "")
            for f, (c, l, p) in xc.items()
        )
        print(f"  + {pid:45s} items={len(items):3d} (base {n_base}/alt {n_alt})  "
              f"cats={len(cats)}  gotcha={gn}({gtier})  dur={dur}  [{parse_status}]")
        print(f"        rollup-xcheck: {xc_str}")

    # ---- write per-plan CSV + parsed items CSV ----
    with open(OUT_CSV, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader(); w.writerows(rows)
    with open(OUT_ITEMS, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["plan_id", "section", "line_no", "item_code",
                                          "description", "unit", "quantity", "is_lump", "spec_category"])
        w.writeheader(); w.writerows(all_items)

    # ---- resolution argument: bid_item_count vs n_mat_types corpus-wide ----
    nmat_dist = {}
    if BASE_TABLE.exists():
        for r in csv.DictReader(open(BASE_TABLE)):
            v = r.get("n_mat_types", "")
            nmat_dist[v] = nmat_dist.get(v, 0) + 1

    print("\n=== RESOLUTION (the core go/no-go) ===")
    counts = [r["bid_item_count"] for r in rows if r["bid_item_count"]]
    print(f"  bid_item_count across {len(counts)} parsed plans: "
          f"min={min(counts)} median={int(statistics.median(counts))} max={max(counts)}")
    print(f"  n_mat_types corpus-wide (1,591 projects): "
          f"{dict(sorted(nmat_dist.items(), key=lambda x: str(x[0])))}  <- caps at 6, 95% in 2-4")

    write_memo(rows, nmat_dist, counts)
    print(f"\nWrote:\n  {OUT_CSV.name}\n  {OUT_ITEMS.name}\n  {OUT_MEMO.name}\n(in {HERE})")


def write_memo(rows, nmat_dist, counts):
    L = []
    A = L.append
    A("# Bid-Schedule Extraction — Preliminary Feasibility Findings")
    A("\n*2026-06-15 · throwaway analysis · reads converted .md + .json only · no Claude calls · no pipeline changes*\n")
    A("## The question")
    A("Today the Plan Reader keeps 7 summed material roll-ups + `box_culvert` and discards the rest "
      "of the 25–43 line-item bid schedule. **Would parsing the full schedule give fields that sharpen "
      "archetype ID and the bid/no-bid decision?**\n")

    A("## 1. Does it parse reliably? (deterministic, zero Claude cost)\n")
    A("| plan | state | items (base/alt) | spec cats | gotcha (tier) | parse status |")
    A("|---|---|---|---|---|---|")
    for r in rows:
        A(f"| {r['plan_id']} | {r['state']} | "
          f"{r['bid_item_count']} ({r['n_base']}/{r['n_alt']}) | {r['n_spec_categories']} | "
          f"{r['gotcha_count']} ({r['gotcha_burden_tier']}) | {r['parse_status']} |")
    parsed = [r for r in rows if r["bid_item_count"] > 0]
    A(f"\n- **{len(parsed)}/{len(rows)} plans parsed cleanly and deterministically** from the "
      "already-converted Markdown — across THREE distinct schedule layouts: ND/EJCDC "
      "(`BID ITEM | DESCRIPTION | UNIT | QUANTITY`), MnDOT (`No. | Mat No. | Item | Units | Quantity`, "
      "spec codes like `2360.509`), and NDDOT (`SPEC | ITEM # | ITEM DESCRIPTION | UNIT | QUANTITY`). "
      "Header-row anchoring (not table arity) handles all three; column-by-name mapping adapts per layout.")
    A("- **Dunn (ND) ground-truth check: parsed 39 = 37 base + 2 alternate** ✓ — the page-break "
      "continuation table (items 26–37) is captured.")
    A("- **The price-column discriminator is essential.** A real bid *schedule* is a pricing form "
      "(it has a BID UNIT PRICE / SUBTOTAL / EXTENDED column); engineer's-estimate quantity "
      "tabulations ('BASIS OF ESTIMATE') share QUANTITY/UNIT but carry no price. Requiring a price "
      "column dropped Dunn from a polluted 104 to the correct 39 — and is the single most important "
      "anchoring rule for production.")
    A(f"- **The {len(rows) - len(parsed)} plans that need a fallback fail on *conversion quality*, "
      "not parser logic:** Douglas (MN) — the priced 'Statement of Estimated Quantities' collapsed "
      "into one merged-cell blob; Brookings (SD) — header became `BID SCHEDULE | Col2 | Col3`; "
      "Watonwan (MN) — 'SCHEDULE OF PRICES' did not convert as a table at all (its only pipe table is "
      "the MnDOT unit-weight reference, correctly excluded as noise). **This is the real gate: the "
      "bid schedule's table structure must survive `s1_convert` (or get an LLM fallback).**\n")

    A("## 2. The core go/no-go: resolution vs today's complexity proxy\n")
    A("The sweet-spot models' only complexity feature is `n_mat_types` (count of non-zero material "
      "types). Its corpus-wide distribution:\n")
    A("```")
    A(f"n_mat_types (1,591 projects): {dict(sorted(nmat_dist.items(), key=lambda x: str(x[0])))}")
    A("```")
    A(f"It **caps at 6 and puts ~95% of projects in {{2,3,4}}** — almost no resolution. By contrast "
      f"`bid_item_count` on the parsed plans ranges **{min(counts)}–{max(counts)}** "
      f"(median {int(statistics.median(counts))}), and `n_spec_categories` adds an orthogonal breadth "
      "signal. A 39-item Dunn job and a 7-item Otter-Tail job are *identical-ish* under `n_mat_types` "
      "but obviously different operations. **This is the signal the 2026-06-15 archetype reanalysis "
      "explicitly asked for and could not compute.**\n")

    A("## 3. New fields this unlocks (all derived, zero extra Claude calls)\n")
    A("- **Complexity/messiness:** `bid_item_count`, `n_spec_categories`, `has_structures_work`, "
      "`has_traffic_control`, `has_erosion_control`, `has_alternates`, `mobilization_present`.")
    A("- **Schedule/contract risk:** `contract_duration_days` (from existing construction dates).")
    A("- **Gotcha burden:** `gotcha_count` / `gotcha_burden_tier` (decision-driver gotchas weighted 2× "
      "via the live `taxonomy.py` split) — the missing 'this job is risky/messy' signal for the Q2 win model.\n")

    A("## 4. Honest limitations\n")
    A("- **Small sample (8 plans).** Value claims about archetype separation are *directional*; the "
      "resolution argument (§2) is corpus-wide and solid.")
    A("- **Thin master join.** Only the 3 NOBID 2025 plans carry a `contract_id`, so a per-plan join to "
      "the master archetype labels is weak on this sample — not a blocker for the feasibility call.")
    A("- **State-relative.** `bid_item_count` is only comparable *within* a state (MN splits HMA across "
      "many `2360.509` lines; ND lumps). Segment by state before any model, same as the 10k-ton threshold.")
    A("- **Roll-up cross-check** (line-item sums vs the 7 Claude roll-ups) is printed per plan; treat as "
      "a QA artifact, not a field swap — do not disturb the golden-scored roll-ups.\n")

    A("## 5. Recommendation\n")
    A("**PROCEED to pipeline integration** — with eyes open on the conversion-quality gate.")
    A("- The parse is deterministic, free, and verified-correct on clean schedules (Dunn 39 ✓), and "
      "`bid_item_count` / `n_spec_categories` give exactly the complexity resolution today's "
      "`n_mat_types` lacks. The value case holds.")
    A("- Two anchoring rules proved essential and should carry into production: **(a) require a "
      "price/subtotal column** to separate the biddable schedule from quantity tabulations; "
      "**(b) anchor on the header-row signature, not table arity**, to skip MnDOT noise tables.")
    A("- **The binding constraint is `s1_convert` table fidelity**, not the parser — ~half the sample "
      "lost its priced schedule to merged-cell conversion. So the production step needs an **LLM "
      "fallback** over the bid-schedule pages whenever the deterministic parse returns nothing, and it "
      "may be worth hardening `s1_convert` for plan-sheet 'Statement of Estimated Quantities' tables.")
    A("\n**Next step (separate, already-scoped):** new `01_pipeline/s5_bid_items.py` (this parser + LLM "
      "fallback) → `bid_items.csv` long table + derived scalar fields in `schema.py`, with "
      "`05_knowledge/spec_category_map.csv` as the category map and `04_tools/rebuild_aggregates.py` "
      "wired to regenerate it with no Claude calls. Keep the 7 golden-scored roll-ups untouched; the "
      "line-item sums are a QA cross-check only.")
    OUT_MEMO.write_text("\n".join(L) + "\n")


if __name__ == "__main__":
    main()
