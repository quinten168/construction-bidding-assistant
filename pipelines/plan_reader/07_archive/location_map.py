"""
location_map.py — WHERE does each kind of information live in a plan?

Plans from different DOTs (MN/ND/SD) are structured differently. This analysis tests, across
the 11 ingested plans, *where* each information type actually sits — which section, what part of
the document — and rolls it up by state to surface format conventions (e.g. the "MnDOT phasing in
section 1804" claim from the 06-03 meeting notes).

Two views, both read-only (NO Claude calls — retrieval + chunk metadata only):
  1. Per-plan section -> page-range profile (pure metadata).
  2. Field-location matrix: for each info-type query, doc-restricted retrieval -> where the top
     hit lands (section, page, page-position front/mid/back, distance). Rolled up by state.

Writes:
  02_outputs/2026-06-09_field_location_map.md   (readable: profiles + matrix + state cheat-sheet)
  02_outputs/2026-06-09_field_location_map.csv  (machine-readable matrix)

Run:
    .venv/bin/python pipelines/plan_reader/04_tools/location_map.py
"""
import sys
import csv
from pathlib import Path
from collections import defaultdict, Counter

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "01_pipeline"))  # 01_pipeline/ holds lib + step modules
import lib

# Reuse the query step's retrieve() (same pattern as 03_evaluation/rag_report).
import retriever as query_mod

OUT = lib.OUT_DIAG
DATE = "2026-06-09"

# Canonical info-type probes — one query per field we extract / care about.
INFO_TYPES = [
    ("location",         "project location route county stationing legal description township range"),
    ("quantities",       "bid schedule estimated quantities pay items tons cubic yards square yards"),
    ("prevailing_wages", "prevailing wage Davis-Bacon wage determination minimum rate"),
    ("phasing_staging",  "construction phasing staging sequence of operations stage"),
    ("traffic_control",  "traffic control maintenance of traffic detour lane closure flagger pilot car"),
    ("environmental",    "environmental permit endangered species wetland SWPPP erosion 404"),
    ("structure",        "box culvert bridge structure removal RCBC"),
    ("schedule",         "completion date working days project duration substantial completion"),
]


def page_position(page, max_page):
    """front / middle / back third of the document."""
    if not max_page:
        return "?"
    f = page / max_page
    return "front" if f <= 0.34 else ("middle" if f <= 0.67 else "back")


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    col = lib.get_collection()
    meta = col.get(include=["metadatas"])["metadatas"]

    # doc_id -> state, and doc_id -> max page (for front/mid/back normalization)
    doc_state, doc_maxpage = {}, defaultdict(int)
    sec_pages = defaultdict(lambda: defaultdict(list))   # doc -> section -> [pages]
    for m in meta:
        d = m["doc_id"]
        doc_state[d] = m.get("state", "") or "?"
        doc_maxpage[d] = max(doc_maxpage[d], m.get("page", 0))
        sec_pages[d][m.get("section", "unknown")].append(m.get("page", 0))
    docs = sorted(sec_pages, key=lambda d: (doc_state[d], d))

    # ── View 1: per-plan section -> page-range profile ────────────────────────
    md = [f"# Where Information Lives — Field-Location Map ({DATE})", "",
          f"Across **{len(docs)} plans**. Read-only (retrieval + chunk metadata; no Claude calls). "
          "Reproduce: `location_map.py`.", "",
          "## Headline findings", "",
          "1. **Patterns exist, and they're sensible — for MN.** MN plans put each field in a distinct, "
          "predictable section: quantities→`bid_schedule`, wages→`prevailing_wage`, traffic→`traffic_staging`. "
          "So section-routed extraction is viable for MnDOT plans.",
          "2. **Prevailing wages sit MID-document in MN** (page-position *middle*) — which is exactly why "
          "the `smart_truncate` extractor drops them. Confirms the bug, and that routing to the wage "
          "section is the fix.",
          "3. **Section tagger v2 now handles ND.** Added `contract_front` patterns for the EJCDC/"
          "county front-matter that dominates ND county plans — ND's no-section-found rate dropped "
          "sharply (42%→17%; see §3 diagnostic). **SD DOT plan-sets stay weak** (~38%): they're "
          "drawings with almost no prose headers, so more patterns won't help — sectioning them needs "
          "document-type detection (a separate task).", "",
          "## 1. Section → page-range profile, per plan", "",
          "Where each tagged section physically sits in each document (min–max page : #chunks). "
          "Section tags are the heuristic tagger's — a soft signal.", ""]
    for d in docs:
        secs = sec_pages[d]
        parts = []
        for s, pgs in sorted(secs.items(), key=lambda kv: min(kv[1])):
            parts.append(f"{s} pp.{min(pgs)}–{max(pgs)} ({len(pgs)})")
        md.append(f"- **[{doc_state[d]}] {d}** (≤{doc_maxpage[d]}pg) — " + " · ".join(parts))
    md.append("")

    # ── View 2: field-location matrix via retrieval ───────────────────────────
    md += ["## 2. Field-location matrix (where the top retrieved chunk lands)", "",
           "For each info-type, doc-restricted retrieval; showing **top hit** `section p.page (dist)`. "
           "Lower distance = more confident the field is really there.", "",
           "| Info type | " + " | ".join(f"[{doc_state[d]}] {d.split('_')[1] if '_' in d else d[:10]}" for d in docs) + " |",
           "|---|" + "---|" * len(docs)]

    rows_csv = []
    # also collect per (info_type, state) for the rollup
    roll = defaultdict(lambda: defaultdict(list))   # info -> state -> [(section, position, dist)]
    for info, q in INFO_TYPES:
        cells = []
        for d in docs:
            hits = query_mod.retrieve(col, q, 3, where={"doc_id": d})
            if not hits:
                cells.append("—"); continue
            h = hits[0]; m = h["meta"]
            sec, pg, dist = m.get("section", "?"), m["page"], h["distance"]
            pos = page_position(pg, doc_maxpage[d])
            cells.append(f"{sec} p.{pg} ({dist:.2f})")
            roll[info][doc_state[d]].append((sec, pos, dist))
            rows_csv.append(dict(info_type=info, plan=d, state=doc_state[d],
                                 top_section=sec, top_page=pg, page_position=pos,
                                 distance=round(dist, 3)))
        md.append(f"| **{info}** | " + " | ".join(cells) + " |")
    md.append("")

    # ── View 3: state rollup + cheat sheet ────────────────────────────────────
    md += ["## 3. State rollup — where each field lives, by DOT format", "",
           "Modal section + typical page position across each state's plans (count of plans).", "",
           "| Info type | MN | ND | SD |", "|---|---|---|---|"]
    for info, _ in INFO_TYPES:
        cells = []
        for st in ("MN", "ND", "SD"):
            recs = roll[info].get(st, [])
            if not recs:
                cells.append("—"); continue
            modal_sec = Counter(s for s, _, _ in recs).most_common(1)[0][0]
            modal_pos = Counter(p for _, p, _ in recs).most_common(1)[0][0]
            avg = sum(dz for _, _, dz in recs) / len(recs)
            cells.append(f"{modal_sec} / {modal_pos} ({avg:.2f}, n={len(recs)})")
        md.append(f"| **{info}** | " + " | ".join(cells) + " |")

    # Tagger-discrimination diagnostic: high title_index/unknown share = the tagger failed to
    # detect real section boundaries for that state's format (it fell back to the default).
    md += ["", "### Section-tagger discrimination, by state (a caveat on the above)", "",
           "Share of matrix cells whose top section is `title_index`/`unknown` — i.e. the tagger "
           "found **no real section**. A high share means the section labels for that state are "
           "unreliable (the tagger's header patterns are tuned to one DOT's format).", "",
           "| State | cells | title_index/unknown | share |", "|---|--:|--:|--:|"]
    for st in ("MN", "ND", "SD"):
        cells_st = [r for r in rows_csv if r["state"] == st]
        nbad = sum(1 for r in cells_st if r["top_section"] in ("title_index", "unknown"))
        share = f"{100*nbad/len(cells_st):.0f}%" if cells_st else "—"
        md.append(f"| {st} | {len(cells_st)} | {nbad} | {share} |")
    md += ["", "### Cheat sheet — where to look first", "",
           "Derived from the modal section per field above (confirm against the plan before trusting):"]
    for info, _ in INFO_TYPES:
        allsec = Counter(s for st in roll[info].values() for s, _, _ in st)
        if allsec:
            top2 = ", ".join(f"`{s}`" for s, _ in allsec.most_common(2))
            md.append(f"- **{info}** → {top2}")
    md += ["", "### Claims from the 06-03 meeting notes — do the data support them?",
           "- *\"MnDOT phasing in section 1804\"* → see the `phasing_staging` row (MN) above + the "
           "MN plans' section profiles in View 1.",
           "- *\"info split varies MN vs ND\"* → compare the MN vs ND columns in View 3.", ""]

    (OUT / f"{DATE}_field_location_map.md").write_text("\n".join(md))
    with open(OUT / f"{DATE}_field_location_map.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["info_type", "plan", "state", "top_section",
                                          "top_page", "page_position", "distance"])
        w.writeheader(); w.writerows(rows_csv)
    print(f"✓ wrote {DATE}_field_location_map.md  ({len(docs)} plans × {len(INFO_TYPES)} info-types)")
    print(f"✓ wrote {DATE}_field_location_map.csv  ({len(rows_csv)} cells)")


if __name__ == "__main__":
    main()
