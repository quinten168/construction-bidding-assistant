#!/usr/bin/env python3
"""
12_build_material_preread.py — the CSI-facing material pre-read, in the gotcha-preread shape.

WHY a second file next to 11_build_material_map.py: 11 emits the ENGINEERING artifact — 33 families
with keyword lists and match rules. That is the right shape for us and the wrong shape for CSI. They
cannot react to a keyword list; they can only react to "does Aggregate Surfacing Class 5 belong in
shldr_tons or base_tons?". So this file re-cuts the SAME matcher output with:

  • one row per SPEC'D MATERIAL as printed in the plan, not per family
  • CSI's own bucket names (Mixed_tons / base_tons / shldr_tons / grading_yards / mill_sy)
  • a hard split between WHAT WE TRACK and WHAT WE DO NOT TRACK, because "not tracked" is itself a
    decision we need them to sign off on
  • a TODAY column, so they can see which materials currently count as nothing
  • a Keep / Move / Drop checkbox per row, mirroring 2026-06-17_gotcha_preread_final.docx

Ordered by HOW OFTEN a material appears (number of plans), not by quantity — T's call: the review
should start with what CSI sees on every job, not with whichever plan happened to be biggest.

Variants are collapsed: MILL BITUMINOUS SURFACE (1.0") / (1.5") / (4.0") is ONE row with the depths
listed, because CSI is ruling on the material, not on each depth.

NOT DONE HERE: state-by-state vocabulary differences. Every row lists which states it was seen in,
but comparing MN vs ND vs SD naming is a separate analysis (T, 2026-07-30).

Read-only. Writes one markdown file. No Claude calls.

Run:
    python3 pipelines/plan_reader/04_tools/12_build_material_preread.py
"""
import collections
import importlib.util
import re
import sqlite3
import sys
from pathlib import Path

TOOLS_DIR   = Path(__file__).resolve().parent
MODULE_ROOT = TOOLS_DIR.parents[0]
DB_PATH     = MODULE_ROOT / "csi_v2.db"
OUT_DIR     = MODULE_ROOT / "05_knowledge" / "_markup"
DATE        = "2026-07-30"
OUT_MD      = OUT_DIR / f"{DATE}_material_preread_for_CSI.md"

# Reuse the matcher + the noise filter rather than re-deriving either.
_spec = importlib.util.spec_from_file_location("mmap", TOOLS_DIR / "11_build_material_map.py")
mmap = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mmap)
sys.path.insert(0, str(MODULE_ROOT / "05_knowledge"))
import quantity_crosswalk as qx   # noqa: E402 — the LIVE mapping, for the "Today" column

# --- CSI's own column names. These are the labels on their spreadsheet; use theirs, not ours. --------
CSI_BUCKET = {
    "ASPHALT":  "Mixed_tons",
    "BASE":     "base_tons",
    "SHOULDER": "shldr_tons",
    "GRADING":  "grading_yards",
    "MILLING":  "mill_sy",
}
TRACKED_ORDER = ["ASPHALT", "BASE", "SHOULDER", "GRADING", "MILLING"]
BUCKET_BLURB = {
    "ASPHALT":  "Hot mix asphalt placed, in TONS.",
    "BASE":     "Aggregate base placed under the pavement, in TONS.",
    "SHOULDER": "Shoulder gravel and aggregate surfacing, in TONS.",
    "GRADING":  "Earthwork moved, in CUBIC YARDS.",
    "MILLING":  "Existing surface ground off, in SQUARE YARDS.",
}
# what the live pipeline's internal bucket names map to, for the "Today" column
LIVE_TO_CSI = {"hot_mix_tons": "Mixed_tons", "base_tons": "base_tons",
               "shoulder_tons": "shldr_tons", "grading_quantity": "grading_yards",
               "milling_sy": "mill_sy"}

# --- how NOT-TRACKED material is grouped for review --------------------------------------------------
# Families are rolled into plain-English groups; CSI should not have to read our family names.
NOT_TRACKED_GROUPS = {
    "asphalt_binder":   "Binder & coatings (tack, prime, PG cement)",
    "seal_coat":        "Seal coat / chip seal / blotter",
    "asphalt_qc":       "Testing & quality management",
    "geosynthetic":     "Fabric, geogrid, geotextile",
    "concrete":         "Concrete flatwork (curb, gutter, sidewalk, PCC)",
    "structures":       "Structures (culvert, bridge, pipe, riprap)",
    "erosion_turf":     "Erosion control & turf",
    "traffic_control":  "Traffic control",
    "pavement_marking": "Pavement marking",
    "signing":          "Signing",
    "guardrail":        "Guardrail",
    "utilities":        "Utilities",
    "equipment_rental": "Equipment rental (hourly)",
    "removal_other":    "Removals that are not pavement or base",
    "sawing":           "Sawing",
    "clearing":         "Clearing & grubbing",
    "water_dust":       "Water & dust control",
    "mobilization_admin": "Mobilization & contract admin",
}

CHECKBOX = "☐ Keep ☐ Move to ______ ☐ Drop<br>Notes:"


def spec_name(description):
    """Collapse a pay-item name to the MATERIAL being reviewed, dropping the depth/size/class detail
    that makes three rows out of one decision. 'MILL BITUMINOUS SURFACE (1.0")' -> 'MILL BITUMINOUS
    SURFACE'. The dropped detail is preserved separately and shown in a 'variants' note, so nothing
    is hidden — CSI still sees that the item comes in several depths."""
    s = mmap.normalize(description)
    s = re.sub(r"\([^)]*\)", " ", s)                       # (2,B) (P) (CV) (1.0")
    s = re.sub(r'\b\d+(\.\d+)?\s*(IN|INCH|INCHES|")', " ", s)
    s = re.sub(r"[-–]\s*\d+.*$", " ", s)                   # trailing "- 6\" DEPTH"
    # Strip the qualifier words the depth/size removal leaves stranded. Without this,
    # "TYPE SP 12.5 WEARING COURSE MIXTURE 3\" THICKNESS" collapses to "... MIXTURE THICKNESS" and
    # becomes a SEPARATE row from plain "... MIXTURE" — splitting one CSI decision across three rows.
    s = re.sub(r"\b(THICK|THICKNESS|DEPTH|SPEC|SPECIAL THICKNESS|MOD|WIDTH|LIFT)\b\s*$", " ", s)
    s = re.sub(r"^\s*(DEPTH|THICKNESS)\b", " ", s)         # leading leftover of '2.0" DEPTH TYPE SP…'
    # Fold spelling variants of the SAME material. MnDOT plans write the same mix as "Type SP 12.5
    # Wearing Course Mixture", "... Wear Course Mix", and "... Non-Wearing Course Mixture" — that is
    # ONE decision for CSI, but it was producing ten separate rows to initial and sign off on. The
    # mix designation itself (12.5 vs 9.5) is NOT folded: those are different mixes.
    s = re.sub(r"\bMIXTURE\b", "MIX", s)
    s = re.sub(r"\bWEARING\b", "WEAR", s)
    s = re.sub(r"\bNON[\s-]*WEAR\b", "NON-WEAR", s)
    s = re.sub(r"\bCOURSES\b", "COURSE", s)
    s = re.sub(r"\s+", " ", s).strip(" ,-.")
    return s or mmap.normalize(description)


# Designators that must NEVER be collapsed away. T, 2026-07-30: "we should keep these FAA 45 class
# special ... these are all really important". They are right, and the reason is domain, not taste:
#   FAA 42 / 43 / 45   fine aggregate angularity — decides quarried rock vs pit gravel, i.e. SOURCE
#   CL 5 / CL 13 / Class 1 / Class Special   gradation — decides base vs shoulder material
#   SP 12.5 / SP 9.5   mix design
#   PG 58S-28 / 58H-34 binder grade
# These drive cost and sourcing, and in several cases the designator is what decides the BUCKET (open
# question 5 is literally "is Aggregate Surfacing Class 5 base rather than shoulder?" — collapsing the
# class would make that question impossible to ask). So base_name() is used ONLY to GROUP rows for
# review; every spec'd variant stays its own visible, separately-rulable line underneath.
def base_name(description):
    """The common material name, used as a GROUPING HEADER only — never as a replacement for the
    printed name. Strips the class/grade designator so the nine spellings of Aggregate Surfacing sit
    under one heading, while each class remains its own row."""
    s = spec_name(description)
    s = re.sub(r"\b(CLASS|CL|TYPE|GRADE|DESIGN|FAA|PG)\s*[A-Z0-9.\-]*", " ", s)
    s = re.sub(r"\b\d+(\.\d+)?\b", " ", s)
    s = re.sub(r"\b(SPECIAL|MOD|SP|CV|LV|RAP|MODIFIED)\b", " ", s)
    # word-order + dropped-noun folding: "COMMON EXCAVATION" and "EXCAVATION - COMMON" are the same
    # MnDOT item; "AGGREGATE BASE COURSE" and "AGGREGATE BASE" are the same material. Matching on the
    # SET of words rather than the string collapses both without touching any designator.
    words = [w for w in re.split(r"[^A-Z]+", s) if w and w not in ("COURSE", "SURFACE", "PAVEMENT")]
    return " ".join(sorted(set(words))) or spec_name(description)


def base_label(names):
    """Human-readable heading for a base-name group. Takes the shortest printed variant and strips
    the class designator FROM THE HEADING ONLY — the heading should read 'Aggregate Surfacing', while
    the rows underneath keep Class 1 / Class 5 / Class Special intact for CSI to rule on each."""
    s = min(names, key=lambda n: (len(n), n))
    # Strip designators ANYWHERE in the heading, not just at the end. "TYPE SP 9.5 WEAR COURSE MIX"
    # as a heading over a group that also contains SP 12.5 is an actively wrong label — the heading
    # must be the family ("Type SP Wear Course Mix") and the sizes live in the rows.
    s = re.sub(r"\b(CLASS|CL|GRADE|FAA|PG)\s*[A-Z0-9.\-]*", " ", s)
    s = re.sub(r"\b(SP)\s+\d+(\.\d+)?", r"\1", s)          # TYPE SP 12.5 -> TYPE SP
    s = re.sub(r"\bMOD\s*\d*\b", " ", s)
    s = re.sub(r"[,\s]+", " ", s).strip(" ,-")
    return (s or min(names, key=len)).title()


def collect():
    """One pass over the corpus -> per (bucket, spec_name) evidence, keyed for both report halves."""
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("""
        SELECT m.raw_description, m.unit, m.quantity, p.state, m.plan_id
        FROM materials m JOIN plans p USING (plan_id)
    """).fetchall()

    agg = collections.defaultdict(lambda: {
        "rows": 0, "qty": collections.defaultdict(float), "states": set(), "units": set(),
        "plans": set(), "today": set(), "variants": set(), "family": set(), "base": None})
    for desc, unit, qty, state, plan_id in rows:
        if mmap.is_noise(desc, unit)[0]:
            continue
        family, bucket, _status, _action = mmap.match_family(desc)
        bucket = bucket or "(UNPLACED)"
        u = mmap.norm_unit(unit)
        e = agg[(bucket, spec_name(desc))]
        e["base"] = base_name(desc)
        e["rows"] += 1
        e["states"].add(state or "?")
        e["plans"].add(plan_id)
        e["family"].add(family)
        if u in ("TON", "SY", "CY"):
            e["units"].add(u)
            if qty:
                e["qty"][u] += qty
        # what the LIVE pipeline does with this line today — the honest before-picture
        e["today"].add(LIVE_TO_CSI.get(qx.csi_bucket(desc, unit) or "", "not counted"))
        full = mmap.normalize(desc)
        if full != spec_name(desc):
            e["variants"].add(full)
    return agg


def fmt_qty(e):
    return "; ".join(f"{v:,.0f} {u}" for u, v in sorted(e["qty"].items())) or "—"


def fmt_today(e):
    """Collapse the set of live-mapping outcomes. 'partly counted' is deliberate: some depths of the
    same material map and others do not, which is itself worth showing CSI."""
    t = e["today"]
    if t == {"not counted"}:
        return "**not counted**"
    if len(t) == 1:
        return next(iter(t))
    return "partly counted (" + ", ".join(sorted(x for x in t if x != "not counted")) + ")"


def main():
    agg = collect()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = []
    w = out.append

    w("# Material Roll-Up — Pre-Read")
    w("Quick calibration for the CSI bidding & estimating team  ·  July 30, 2026\n")
    w("## What we need from you\n")
    w("We pulled every priced line item out of the bid schedules in 117 plans (MN / ND / SD) and "
      "sorted each material into the five quantity columns you already track. **We have not turned "
      "any of this on yet.** Before we do, we need you to tell us whether the roll-ups are right.\n")
    w("For each material: **Keep** it where we put it, **Move** it to a different column, or "
      "**Drop** it if it should not be counted at all.\n")
    w("Materials are listed **most-frequent first** — the ones you see on the most jobs are at the "
      "top of each table.\n")

    w("## Why we are asking\n")
    w("We tested on **Stearns County CP 073-123-025** (CR 123 resurfacing, let 08.28.25). We read "
      "all 26 line items off the bid schedule correctly, but the roll-up put them in the wrong "
      "columns:\n")
    w("| Line item on the Stearns bid schedule | Quantity | What we reported |")
    w("|---|---|---|")
    w("| Mill Bituminous Surface (1.0\", 1.5\", 4.0\") | 70,263 SY | counted as asphalt, then dropped |")
    w("| Full Depth Reclamation | 70,167 SY | not counted at all |")
    w("| Remove Concrete Driveway Pavement | 44 SY | not counted at all |")
    w("| Motor Grader / Truck / Loaders | hourly | not counted at all |")
    w("")
    w("So the job reported **zero milling** on a project that is almost entirely milling and "
      "reclamation. Across all 117 plans the same fault leaves **1.6M SY of milling** and **1.2M SY "
      "of reclamation** uncounted. We have fixed the mechanism. What we cannot decide for you is "
      "which column each material belongs in — that is this document.\n")
    w("A note on the tables: **\"Today\"** is what the current system does with that material. Where "
      "it says *not counted*, that quantity is invisible on the report right now.\n")
    w("---\n")

    # ---------------- PART 1: what we track ----------------
    w("# Part 1 — What we ARE tracking\n")
    w("Five columns, matching your spreadsheet.\n")
    for bucket in TRACKED_ORDER:
        col = CSI_BUCKET[bucket]
        all_items = [(k[1], v) for k, v in agg.items() if k[0] == bucket]
        # Only materials that actually carry a quantity somewhere belong in a QUANTITY roll-up review.
        # A name we have only ever seen without a number (a lump-sum or a mis-parsed row) cannot move
        # this column, so listing it just spends CSI's attention. The count is disclosed below.
        items = [(n, e) for n, e in all_items if e["qty"]]
        no_qty = [n for n, e in all_items if not e["qty"]]
        # most-frequent first: how many PLANS the material shows up in
        items.sort(key=lambda kv: (-len(kv[1]["plans"]), -sum(kv[1]["qty"].values())))
        # Group the spec'd names under their common base material. The GROUP is the heading; every
        # spec/class variant stays its own row, because the designator (FAA 45, CL 5, Class Special)
        # is real cost and sourcing information — and sometimes decides the bucket itself.
        groups = collections.defaultdict(list)
        for name, e in items:
            groups[e["base"]].append((name, e))
        ordered = sorted(groups.items(),
                         key=lambda kv: (-len({p for _n, e in kv[1] for p in e["plans"]}),
                                         -sum(sum(e["qty"].values()) for _n, e in kv[1])))
        w(f"## `{col}` — {BUCKET_BLURB[bucket]}\n")
        w(f"**{len(ordered)} materials** ({len(items)} spec'd variants) roll into this column.\n")
        for gi, (_key, members) in enumerate(ordered, 1):
            members.sort(key=lambda kv: (-len(kv[1]["plans"]), -sum(kv[1]["qty"].values())))
            gplans = {p for _n, e in members for p in e["plans"]}
            gqty = collections.defaultdict(float)
            for _n, e in members:
                for u, v in e["qty"].items():
                    gqty[u] += v
            label = base_label([n for n, _e in members])
            total = "; ".join(f"{v:,.0f} {u}" for u, v in sorted(gqty.items()))
            ref = f"{bucket[:2].upper()}{gi}"
            w(f"**{ref}. {label}** — seen in {len(gplans)} plans · {total}\n")
            w("| Spec / class as printed | Seen in | States | Unit | Today | Qty | Right column? |")
            w("|---|---|---|---|---|---|---|")
            for name, e in members:
                w(f"| {name.title()} | {len(e['plans'])} | "
                  f"{','.join(sorted(s for s in e['states'] if s and s != '?'))} | "
                  f"{','.join(sorted(e['units'])) or '—'} | {fmt_today(e)} | {fmt_qty(e)} | "
                  f"{CHECKBOX} |")
            w("")
        if no_qty:
            w(f"<sub>{len(no_qty)} further item name(s) matched this column but never carried a "
              f"quantity in any plan (lump-sum lines, or rows our parser did not read a number from). "
              f"They cannot affect the total, so they are left out of the table above: "
              f"{', '.join(n.title() for n in sorted(no_qty)[:6])}"
              f"{'…' if len(no_qty) > 6 else ''}</sub>\n")
        w(f"**Anything missing from `{col}`?**\n")
        w("| Material we did not list | Why it belongs here |")
        w("|---|---|")
        w("|  |  |")
        w("|  |  |")
        w("")

    # ---------------- PART 2: what we do not track ----------------
    w("---\n")
    w("# Part 2 — What we are NOT tracking\n")
    w("These are real pay items we read off the bid schedule but do **not** roll into any of your "
      "five columns. We carry them as a yes/no flag on the report instead (\"this job has concrete "
      "work\"), not as a quantity.\n")
    w("**The question for each group: should any of these actually be counted?**\n")
    groups = collections.defaultdict(lambda: {"plans": set(), "names": [], "qty": collections.defaultdict(float)})
    for (bucket, name), e in agg.items():
        if bucket != "OTHER":
            continue
        fam = next(iter(e["family"]), None)
        label = NOT_TRACKED_GROUPS.get(fam, "Other")
        g = groups[label]
        g["plans"] |= e["plans"]
        g["names"].append((name, len(e["plans"])))
        for u, v in e["qty"].items():
            g["qty"][u] += v
    w("| Group | Seen in | Example materials | Quantity we are ignoring | Should we count it? |")
    w("|---|---|---|---|---|")
    for label, g in sorted(groups.items(), key=lambda kv: -len(kv[1]["plans"])):
        ex = "; ".join(n.title() for n, _c in sorted(g["names"], key=lambda x: -x[1])[:3])
        qty = "; ".join(f"{v:,.0f} {u}" for u, v in sorted(g["qty"].items())) or "—"
        w(f"| **{label}** | {len(g['plans'])} plans | {ex} | {qty} | ☐ Keep as flag ☐ Count it as ______ |")
    w("")
    w("Two we want to call out specifically:\n")
    w("- **Crushing and stockpile.** Your spreadsheet has columns for both, but they are filled on "
      "under 5% of historical rows, and in 117 plans we found 1 with stockpile and 0 with crushing. "
      "We treat them as internal sourcing decisions rather than plan quantities. Correct?")
    w("- **Riprap** sits under structures, not asphalt — it is quarried rock slope protection at "
      "culvert ends and on slopes, measured in CY/TON. Flagging it because an early draft of our "
      "asphalt list had it in the wrong place.\n")

    # ---------------- PART 3: we do not know ----------------
    unplaced = [(k[1], v) for k, v in agg.items() if k[0] == "(UNPLACED)" and v["qty"]]
    unplaced.sort(key=lambda kv: (-len(kv[1]["plans"]), -sum(kv[1]["qty"].values())))
    w("---\n")
    w("# Part 3 — Materials we could not place\n")
    w(f"{len(unplaced)} priced materials carrying a real quantity that we could not confidently "
      "assign to any column. These are the ones most likely to be wrong, so they are worth your "
      "eyes even though the quantities are smaller.\n")
    w("| Material | Seen in | States | Unit | Total qty | Which column? |")
    w("|---|---|---|---|---|---|")
    for name, e in unplaced[:40]:
        w(f"| {name.title()} | {len(e['plans'])} plans | "
          f"{','.join(sorted(s for s in e['states'] if s and s != '?'))} | "
          f"{','.join(sorted(e['units'])) or '—'} | {fmt_qty(e)} | ☐ Mixed_tons ☐ base_tons "
          "☐ shldr_tons ☐ grading_yards ☐ mill_sy ☐ Do not count |")
    w("")

    # ---------------- closing questions ----------------
    w("---\n")
    w("# The judgment calls we could not make for you\n")
    w("These are the ones where our best guess could go either way. Ordered by how much quantity "
      "rides on the answer.\n")
    w("1. **Full Depth Reclamation — 1,166,000 SY, 14 plans, currently counted as nothing.** FDR "
      "grinds the asphalt *and* the base below it into a new base layer. Is that `mill_sy`, is it "
      "`grading_yards` because you are rebuilding the roadbed, or does it need its own column?")
    w("2. **Milling is measured in TONS in North Dakota — 230,625 T.** MN and SD measure it in SY. "
      "`mill_sy` cannot hold both. Separate tons line, or a conversion?")
    w("3. **Topsoil — 539,000 CY.** Strip, salvage, borrow and place. Currently filed as erosion "
      "control, so it never reaches `grading_yards`. Is topsoil part of your grading number?")
    w("4. **Pavement removal.** Mark said pavement removal \"is considered grading work\" and "
      "converts to CY. (a) Does that apply only to pavement and base removal? We have 158 removal "
      "item types and most are *remove silt fence*, *remove sign*, *remove pipe*. (b) Is 1.75 "
      "Ton/CY your standard factor?")
    w("5. **Aggregate Surfacing Class 1 vs Class 5 vs Special — 67,000 T.** We put all of it in "
      "`shldr_tons`. Is Class 5 really base material to you?")
    w("6. **Salvaged / remove-and-relay base.** The material is re-used, not bought. Does it count "
      "toward `base_tons` because you still move and place it?")
    w("7. **PG binder, tack and prime — 56,029 T.** We propose excluding these from `Mixed_tons` so "
      "mix tonnage is not double-counted (the binder is already inside the mix). Confirm?")
    w("")
    w("---\n")
    w("### Two more things\n")
    w("**Where do you read quantities?** Some projects have a priced bid schedule in the proposal "
      "*and* quantity sheets in the plan set (Basis of Estimate / Estimate of Quantities). When they "
      "disagree, which do you trust, and which do you read first?\n")
    w("**Does the letting agency change the wording?** Do pay-item names shift between a state DOT "
      "job and a county / city / township / SAP-CSAH job, or does everyone in a state use that "
      "state's spec book? *(We can see the vocabulary differs by state — MN says \"Type SP\", ND "
      "says \"Superpave\", SD says \"Asphalt Concrete\". A state-by-state comparison is a separate "
      "piece of work we have not done yet.)*\n")

    OUT_MD.write_text("\n".join(out))
    n_tracked = sum(1 for k in agg if k[0] in TRACKED_ORDER)
    print(f"tracked materials: {n_tracked}   not-tracked groups: {len(groups)}   "
          f"unplaced: {len(unplaced)}")
    print(f"wrote {OUT_MD.relative_to(MODULE_ROOT)}")


if __name__ == "__main__":
    main()
