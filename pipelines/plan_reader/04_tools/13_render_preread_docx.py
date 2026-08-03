#!/usr/bin/env python3
"""
13_render_preread_docx.py — render the material pre-read as a styled .docx.

WHY not pandoc: the reference document (2026-06-17_gotcha_preread_final.docx) is styled with DIRECT
cell shading and run colours, not with named Word styles. `pandoc --reference-doc` only carries named
styles across, so it reproduces none of it. The palette below is read off that file verbatim so the
two documents sit together as one family.

Palette (from the gotcha pre-read):
    1F3A5F  navy      section headings, table header row
    1F6FB2  blue      group headings, accents
    C0392B  red       the "not counted" warnings
    EEF3F8  pale blue table header fill / group band
    F4F6F8  grey      zebra row fill
    FFF6DC  cream     callout blocks
    E3E7EB  border    all table borders
    808690  muted     sub-text
    Calibri           body font

Reads the SAME collected data as 12_build_material_preread.py — it imports that module rather than
parsing its markdown, so the two outputs cannot drift.

Run:
    python3 pipelines/plan_reader/04_tools/13_render_preread_docx.py
"""
import collections
import importlib.util
from pathlib import Path

import itertools

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement, parse_xml
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor

TOOLS_DIR = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("preread", TOOLS_DIR / "12_build_material_preread.py")
pre = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pre)

OUT_DOCX = pre.OUT_DIR / f"{pre.DATE}_material_preread_for_CSI.docx"

NAVY, BLUE, RED = "1F3A5F", "1F6FB2", "C0392B"
PALE, GREY, CREAM, BORDER, MUTED = "EEF3F8", "F4F6F8", "FFF6DC", "E3E7EB", "808690"
FONT = "Calibri"
CHECK = "☐"   # ☐


# --- low-level docx helpers (python-docx has no API for cell shading or table borders) ---------------
def shade(cell, hex_fill):
    el = OxmlElement("w:shd")
    el.set(qn("w:val"), "clear")
    el.set(qn("w:fill"), hex_fill)
    cell._tc.get_or_add_tcPr().append(el)


def table_borders(table, hex_color=BORDER):
    borders = OxmlElement("w:tblBorders")
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        e = OxmlElement(f"w:{edge}")
        e.set(qn("w:val"), "single")
        e.set(qn("w:sz"), "4")
        e.set(qn("w:space"), "0")
        e.set(qn("w:color"), hex_color)
        borders.append(e)
    table._tbl.tblPr.append(borders)


# --- clickable checkboxes ---------------------------------------------------------------------------
# T, 2026-08-03: the boxes have to be tickable in Word, not just a ☐ glyph to print and pen in.
#
# Word has two mechanisms and only one of them is right here:
#   legacy w:fldChar FORMCHECKBOX   clickable ONLY when the document is form-protected, which locks
#                                   the rest of the file — CSI could not then type in "Move to ___"
#                                   or write in the "anything missing" tables.
#   w:sdt + w14:checkbox            a content control; clicking toggles it during ordinary editing,
#                                   the rest of the document stays freely editable. This one.
#
# python-docx has no API for either, same as cell shading and table borders above, so it is raw OOXML.
# The w14 namespace is declared on the element itself rather than on the document root — python-docx
# builds document.xml from a fixed template we do not control, and Word accepts a local declaration.
_SDT_ID = itertools.count(90001)

_CHECKBOX_XML = (
    '<w:sdt xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
    'xmlns:w14="http://schemas.microsoft.com/office/word/2010/wordml">'
    '<w:sdtPr>'
    '<w:rPr><w:rFonts w:ascii="MS Gothic" w:eastAsia="MS Gothic" w:hAnsi="MS Gothic"/>'
    '<w:sz w:val="{half}"/></w:rPr>'
    '<w:id w:val="{sdt_id}"/>'
    '<w14:checkbox>'
    '<w14:checked w14:val="0"/>'
    '<w14:checkedState w14:val="2612" w14:font="MS Gothic"/>'
    '<w14:uncheckedState w14:val="2610" w14:font="MS Gothic"/>'
    '</w14:checkbox>'
    '</w:sdtPr>'
    '<w:sdtContent><w:r>'
    '<w:rPr><w:rFonts w:ascii="MS Gothic" w:eastAsia="MS Gothic" w:hAnsi="MS Gothic"/>'
    '<w:sz w:val="{half}"/></w:rPr><w:t>☐</w:t>'
    '</w:r></w:sdtContent></w:sdt>'
)


def add_checkbox(paragraph, *, size=8.5):
    """Append one clickable checkbox control to a paragraph. w:sz is in HALF-points."""
    paragraph._p.append(parse_xml(_CHECKBOX_XML.format(half=int(round(size * 2)),
                                                       sdt_id=next(_SDT_ID))))


def _label_run(paragraph, text, *, size, bold=False, color=None):
    run = paragraph.add_run(text)
    run.font.name = FONT
    run.font.size = Pt(size)
    run.font.bold = bold
    if color:
        run.font.color.rgb = RGBColor.from_string(color)
    return run


def checkbox_line(paragraph, options, *, size=8.5, sep="   "):
    """Render 'checkbox + label' pairs into an existing paragraph, in order."""
    for i, label in enumerate(options):
        if i:
            _label_run(paragraph, sep, size=size)
        add_checkbox(paragraph, size=size)
        _label_run(paragraph, " " + label, size=size)
    return paragraph


def cell_checkboxes(cell, options, *, size=8.5):
    """Replace a table cell's contents with a row of clickable checkboxes."""
    cell.text = ""
    p = cell.paragraphs[0]
    p.paragraph_format.space_before = Pt(1)
    p.paragraph_format.space_after = Pt(1)
    return checkbox_line(p, options, size=size)


def cell_text(cell, text, *, bold=False, size=8.5, color=None, align=None):
    cell.text = ""
    p = cell.paragraphs[0]
    p.paragraph_format.space_before = Pt(1)
    p.paragraph_format.space_after = Pt(1)
    if align:
        p.alignment = align
    run = p.add_run(text)
    run.font.name = FONT
    run.font.size = Pt(size)
    run.font.bold = bold
    if color:
        run.font.color.rgb = RGBColor.from_string(color)
    return run


def para(doc, text="", *, size=10, bold=False, color=None, space_after=6, align=None, italic=False):
    p = doc.add_paragraph()
    p.paragraph_format.space_after = Pt(space_after)
    if align:
        p.alignment = align
    run = p.add_run(text)
    run.font.name = FONT
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.italic = italic
    if color:
        run.font.color.rgb = RGBColor.from_string(color)
    return p


def rich(doc, chunks, *, size=10, space_after=6):
    """A paragraph built from (text, bold, color) chunks, so a sentence can carry emphasis inline."""
    p = doc.add_paragraph()
    p.paragraph_format.space_after = Pt(space_after)
    for text, bold, color in chunks:
        run = p.add_run(text)
        run.font.name = FONT
        run.font.size = Pt(size)
        run.font.bold = bold
        if color:
            run.font.color.rgb = RGBColor.from_string(color)
    return p


def heading(doc, text, *, level=1):
    sizes = {1: 16, 2: 13, 3: 11}
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(16 if level == 1 else 12)
    p.paragraph_format.space_after = Pt(6)
    run = p.add_run(text)
    run.font.name = FONT
    run.font.size = Pt(sizes[level])
    run.font.bold = True
    run.font.color.rgb = RGBColor.from_string(NAVY if level == 1 else BLUE)
    if level == 1:                              # navy rule under section headings
        pbdr = OxmlElement("w:pBdr")
        bottom = OxmlElement("w:bottom")
        bottom.set(qn("w:val"), "single")
        bottom.set(qn("w:sz"), "8")
        bottom.set(qn("w:space"), "2")
        bottom.set(qn("w:color"), NAVY)
        pbdr.append(bottom)
        p._p.get_or_add_pPr().append(pbdr)
    return p


def callout(doc, lines, fill=CREAM):
    """A single-cell shaded block — used for the framing notes, same as the reference doc."""
    t = doc.add_table(rows=1, cols=1)
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    table_borders(t)
    c = t.rows[0].cells[0]
    shade(c, fill)
    c.text = ""
    for i, (text, bold) in enumerate(lines):
        p = c.paragraphs[0] if i == 0 else c.add_paragraph()
        p.paragraph_format.space_after = Pt(2)
        if isinstance(text, list):             # a list of labels means clickable checkboxes
            checkbox_line(p, text, size=9.5)
            continue
        run = p.add_run(text)
        run.font.name = FONT
        run.font.size = Pt(9.5)
        run.font.bold = bold
    doc.add_paragraph().paragraph_format.space_after = Pt(4)


def build_table(doc, headers, rows, widths):
    """Header row in navy-on-pale, zebra body rows, thin grey borders."""
    t = doc.add_table(rows=1, cols=len(headers))
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    table_borders(t)
    for i, h in enumerate(headers):
        c = t.rows[0].cells[i]
        shade(c, PALE)
        cell_text(c, h, bold=True, size=8.5, color=NAVY)
    for r_i, row in enumerate(rows):
        cells = t.add_row().cells
        for i, val in enumerate(row):
            if r_i % 2 == 1:
                shade(cells[i], GREY)
            if isinstance(val, list):          # a list of labels means clickable checkboxes
                cell_checkboxes(cells[i], val)
                continue
            text, color, bold = val if isinstance(val, tuple) else (val, None, False)
            cell_text(cells[i], text, size=8.5, color=color, bold=bold)
    for row in t.rows:
        for i, wdt in enumerate(widths):
            row.cells[i].width = Inches(wdt)
    doc.add_paragraph().paragraph_format.space_after = Pt(2)
    return t


def today_cell(e):
    """The 'Today' value, in red when the material currently counts as nothing — that colour is the
    whole argument of the document, so it should be visible at a glance."""
    t = pre.fmt_today(e).replace("**", "")
    return (t, RED, True) if t == "not counted" else (t, None, False)


def main():
    agg = pre.collect()
    doc = Document()
    style = doc.styles["Normal"]
    style.font.name = FONT
    style.font.size = Pt(10)
    for s in doc.sections:
        s.left_margin = s.right_margin = Inches(0.6)
        s.top_margin = s.bottom_margin = Inches(0.6)

    # ---------------- masthead ----------------
    para(doc, "Material Roll-Up — Pre-Read", size=22, bold=True, color=NAVY, space_after=2)
    para(doc, "Quick calibration for the CSI bidding & estimating team  ·  July 30, 2026",
         size=10, color=MUTED, space_after=12)

    callout(doc, [
        ("What we need from you", True),
        ("We pulled every priced line item out of the bid schedules in 117 plans (MN / ND / SD) and "
         "sorted each material into the five quantity columns you already track. We have not turned "
         "any of this on yet — before we do, we need you to tell us whether the roll-ups are right.", False),
        ("For each material: Keep it where we put it, Move it to a different column, or Drop it if "
         "it should not be counted at all. Materials are listed most-frequent first.", False),
    ])

    heading(doc, "Why we are asking")
    rich(doc, [("We tested on ", False, None),
               ("Stearns County CP 073-123-025", True, None),
               (" (CR 123 resurfacing, let 08.28.25). We read all 26 line items off the bid schedule "
                "correctly, but the roll-up put them in the wrong columns:", False, None)])
    build_table(doc,
                ["Line item on the Stearns bid schedule", "Quantity", "What we reported"],
                [['Mill Bituminous Surface (1.0", 1.5", 4.0")', "70,263 SY",
                  ("counted as asphalt, then dropped", RED, True)],
                 ["Full Depth Reclamation", "70,167 SY", ("not counted at all", RED, True)],
                 ["Remove Concrete Driveway Pavement", "44 SY", ("not counted at all", RED, True)],
                 ["Motor Grader / Truck / Loaders", "hourly", ("not counted at all", RED, True)]],
                [4.2, 1.4, 3.0])
    rich(doc, [("So the job reported ", False, None), ("zero milling", True, RED),
               (" on a project that is almost entirely milling and reclamation. Across all 117 plans "
                "the same fault leaves ", False, None),
               ("1.6M SY of milling", True, None), (" and ", False, None),
               ("1.2M SY of reclamation", True, None),
               (" uncounted. We have fixed the mechanism. What we cannot decide for you is which "
                "column each material belongs in — that is this document.", False, None)])
    rich(doc, [("A note on the tables: ", False, None), ("“Today”", True, None),
               (" is what the current system does with that material. Where it says ", False, None),
               ("not counted", True, RED),
               (", that quantity is invisible on the report right now.", False, None)])

    # ---------------- Part 1 ----------------
    heading(doc, "Part 1 — What we ARE tracking")
    para(doc, "Five columns, matching your spreadsheet. Materials are grouped by their common name; "
              "each spec / class is its own line, because the class is what drives the material "
              "source and the price.", size=10, color=MUTED, space_after=10)

    for bucket in pre.TRACKED_ORDER:
        col = pre.CSI_BUCKET[bucket]
        all_items = [(k[1], v) for k, v in agg.items() if k[0] == bucket]
        items = [(n, e) for n, e in all_items if e["qty"]]
        no_qty = [n for n, e in all_items if not e["qty"]]
        groups = collections.defaultdict(list)
        for name, e in items:
            groups[e["base"]].append((name, e))
        ordered = sorted(groups.items(),
                         key=lambda kv: (-len({p for _n, e in kv[1] for p in e["plans"]}),
                                         -sum(sum(e["qty"].values()) for _n, e in kv[1])))

        heading(doc, f"{col}  —  {pre.BUCKET_BLURB[bucket]}", level=2)
        para(doc, f"{len(ordered)} materials ({len(items)} spec'd variants) roll into this column.",
             size=9.5, color=MUTED, space_after=8)

        for gi, (_key, members) in enumerate(ordered, 1):
            members.sort(key=lambda kv: (-len(kv[1]["plans"]), -sum(kv[1]["qty"].values())))
            gplans = {p for _n, e in members for p in e["plans"]}
            gqty = collections.defaultdict(float)
            for _n, e in members:
                for u, v in e["qty"].items():
                    gqty[u] += v
            label = pre.base_label([n for n, _e in members])
            total = "; ".join(f"{v:,.0f} {u}" for u, v in sorted(gqty.items()))
            rich(doc, [(f"{bucket[:2].upper()}{gi}.  {label}", True, BLUE),
                       (f"   seen in {len(gplans)} plans  ·  {total}", False, MUTED)],
                 size=10, space_after=3)
            build_table(doc,
                        ["Spec / class as printed", "Plans", "States", "Unit", "Today", "Quantity",
                         "Right column?"],
                        [[n.title(), str(len(e["plans"])),
                          ",".join(sorted(s for s in e["states"] if s and s != "?")),
                          ",".join(sorted(e["units"])) or "—",
                          today_cell(e), pre.fmt_qty(e),
                          f"{CHECK} Keep   {CHECK} Move to ______   {CHECK} Drop"]
                         for n, e in members],
                        [2.5, 0.5, 0.6, 0.6, 1.2, 1.3, 1.9])
        if no_qty:
            para(doc, f"{len(no_qty)} further item name(s) matched this column but never carried a "
                      f"quantity in any plan, so they cannot affect the total and are left out above: "
                      f"{', '.join(n.title() for n in sorted(no_qty)[:6])}"
                      f"{'…' if len(no_qty) > 6 else ''}",
                 size=8.5, color=MUTED, italic=True, space_after=6)
        para(doc, f"Anything missing from {col}?", size=9.5, bold=True, space_after=3)
        build_table(doc, ["Material we did not list", "Why it belongs here"],
                    [["", ""], ["", ""]], [4.3, 4.3])

    # ---------------- Part 2 ----------------
    doc.add_page_break()
    heading(doc, "Part 2 — What we are NOT tracking")
    para(doc, "These are real pay items we read off the bid schedule but do not roll into any of "
              "your five columns. We carry them as a yes/no flag on the report (“this job has "
              "concrete work”), not as a quantity.", space_after=4)
    para(doc, "The question for each group: should any of these actually be counted?",
         bold=True, space_after=8)

    groups = collections.defaultdict(lambda: {"plans": set(), "names": [],
                                              "qty": collections.defaultdict(float)})
    for (bucket, name), e in agg.items():
        if bucket != "OTHER":
            continue
        label = pre.NOT_TRACKED_GROUPS.get(next(iter(e["family"]), None), "Other")
        g = groups[label]
        g["plans"] |= e["plans"]
        g["names"].append((name, len(e["plans"])))
        for u, v in e["qty"].items():
            g["qty"][u] += v
    build_table(doc,
                ["Group", "Plans", "Example materials", "Quantity we are ignoring",
                 "Should we count it?"],
                [[(label, None, True), str(len(g["plans"])),
                  "; ".join(n.title() for n, _c in sorted(g["names"], key=lambda x: -x[1])[:3]),
                  "; ".join(f"{v:,.0f} {u}" for u, v in sorted(g["qty"].items())) or "—",
                  f"{CHECK} Keep as flag   {CHECK} Count it as ______"]
                 for label, g in sorted(groups.items(), key=lambda kv: -len(kv[1]["plans"]))],
                [2.2, 0.5, 2.6, 1.6, 1.9])
    callout(doc, [
        ("Two we want to call out specifically", True),
        ("Crushing and stockpile — your spreadsheet has columns for both, but they are filled on "
         "under 5% of historical rows, and in 117 plans we found 1 with stockpile and 0 with "
         "crushing. We treat them as internal sourcing decisions rather than plan quantities. "
         "Correct?", False),
        ("Riprap sits under structures, not asphalt — it is quarried rock slope protection at "
         "culvert ends and on slopes, measured in CY/TON.", False),
    ])

    # ---------------- Part 3 ----------------
    doc.add_page_break()
    heading(doc, "Part 3 — Materials we could not place")
    unplaced = [(k[1], v) for k, v in agg.items() if k[0] == "(UNPLACED)" and v["qty"]]
    unplaced.sort(key=lambda kv: (-len(kv[1]["plans"]), -sum(kv[1]["qty"].values())))
    para(doc, f"{len(unplaced)} priced materials carrying a real quantity that we could not "
              "confidently assign to any column. These are the ones most likely to be wrong, so they "
              "are worth your eyes even though the quantities are smaller.", space_after=8)
    build_table(doc,
                ["Material", "Plans", "States", "Unit", "Quantity", "Which column?"],
                [[n.title(), str(len(e["plans"])),
                  ",".join(sorted(s for s in e["states"] if s and s != "?")),
                  ",".join(sorted(e["units"])) or "—", pre.fmt_qty(e),
                  f"{CHECK} Mixed_tons  {CHECK} base_tons  {CHECK} shldr_tons  "
                  f"{CHECK} grading_yards  {CHECK} mill_sy  {CHECK} Do not count"]
                 for n, e in unplaced[:40]],
                [2.3, 0.5, 0.6, 0.6, 1.2, 3.4])

    # ---------------- closing ----------------
    doc.add_page_break()
    heading(doc, "The judgment calls we could not make for you")
    para(doc, "Ordered by how much quantity rides on the answer.", size=9.5, color=MUTED,
         space_after=8)
    for i, (title, body) in enumerate([
        ("Full Depth Reclamation — 1,166,000 SY, 14 plans, currently counted as nothing.",
         "FDR grinds the asphalt and the base below it into a new base layer. Is that mill_sy, is it "
         "grading_yards because you are rebuilding the roadbed, or does it need its own column?"),
        ("Milling is measured in TONS in North Dakota — 230,625 T.",
         "MN and SD measure it in SY. mill_sy cannot hold both. Separate tons line, or a conversion?"),
        ("Topsoil — 539,000 CY.",
         "Strip, salvage, borrow and place. Currently filed as erosion control, so it never reaches "
         "grading_yards. Is topsoil part of your grading number?"),
        ("Pavement removal.",
         "Mark said pavement removal “is considered grading work” and converts to CY. (a) Does that "
         "apply only to pavement and base removal? We have 158 removal item types and most are "
         "remove silt fence, remove sign, remove pipe. (b) Is 1.75 Ton/CY your standard factor?"),
        ("Aggregate Surfacing Class 1 vs Class 5 vs Special — 67,000 T.",
         "We put all of it in shldr_tons. Is Class 5 really base material to you?"),
        ("Salvaged / remove-and-relay base.",
         "The material is re-used, not bought. Does it count toward base_tons because you still move "
         "and place it?"),
        ("PG binder, tack and prime — 56,029 T.",
         "We propose excluding these from Mixed_tons so mix tonnage is not double-counted (the binder "
         "is already inside the mix). Confirm?"),
    ], 1):
        rich(doc, [(f"{i}.  ", True, BLUE), (title, True, None), ("  " + body, False, None)],
             space_after=6)

    heading(doc, "Two more things")
    rich(doc, [("Where do you read quantities?  ", True, None),
               ("Some projects have a priced bid schedule in the proposal and quantity sheets in the "
                "plan set (Basis of Estimate / Estimate of Quantities). When they disagree, which do "
                "you trust, and which do you read first?", False, None)])
    rich(doc, [("Does the letting agency change the wording?  ", True, None),
               ("Do pay-item names shift between a state DOT job and a county / city / township / "
                "SAP-CSAH job, or does everyone in a state use that state's spec book? We can see the "
                "vocabulary differs by state — MN says “Type SP”, ND says “Superpave”, SD says "
                "“Asphalt Concrete”. A state-by-state comparison is separate work we have not done "
                "yet.", False, None)])

    doc.save(OUT_DOCX)
    print(f"wrote {OUT_DOCX.relative_to(pre.MODULE_ROOT)}")


if __name__ == "__main__":
    main()
