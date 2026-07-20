"""
boilerplate_scan.py — Task C evidence: which content is BOILERPLATE vs project-specific?

T's question: "What sections to skip — is this a consistent pattern we can detect every
time? Would a 'toss-out' taxonomy make sense?"  Answer: yes, and you don't hand-maintain
a regex list — you detect boilerplate EMPIRICALLY by cross-plan repetition.

THE IDEA
  Standard-specification / contract / procurement language is, by definition, copied
  near-verbatim across many plans (only the project number / county changes). Project-
  specific content (this road's quantities, this site's gotchas) appears in ONE plan.
  So: normalize each paragraph (strip digits/punctuation), and count in how many DISTINCT
  plans it appears. High cross-plan document-frequency (DF) ⇒ boilerplate ⇒ safe to drop /
  down-weight. DF == 1 ⇒ unique to this project ⇒ PRESERVE.

  Rolled up by SECTION, this says what fraction of each section is boilerplate, which is
  exactly the input to the section-disposition tiers (KEEP / DOWN_WEIGHT / DROP).

GUARDRAIL (the pushback that shaped the plan)
  A paragraph that is repetitive BUT carries a gotcha-taxonomy trigger phrase
  (prevailing wage, DBE, liquidated damages, density-lot failure, …) is NOT droppable —
  those Family-E gotchas live inside contract/legal boilerplate. We mark such paragraphs
  "protected" and report them separately so disposition never drops a section that hides them.

Read-only. Reads the convert Markdown cache (warm it first).

Run:
    python3 pipelines/plan_reader/04_tools/boilerplate_scan.py
Writes:
    02_outputs/<DATE>_boilerplate_scan.md       (readable: section boilerplate profile)
    02_outputs/<DATE>_section_boilerplate.csv   (per doc_type×section: boilerplate %, protected count)
"""
import sys
import csv
import re
import json
from pathlib import Path
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "01_pipeline"))  # 01_pipeline/ holds lib + step modules
import lib

import taxonomy
import s1_convert as convert
import s2_indexer as indexer

DATE = "2026-06-10"
OUT = lib.OUT_DIAG
CACHE = lib.DATA_DIR / "_md_cache"

# A paragraph must have at least this many alpha-normalized chars to count (skip noise).
MIN_NORM_LEN = 60
# Boilerplate = the same normalized paragraph appears in >= this many DISTINCT plans.
BOILERPLATE_MIN_PLANS = 3


def _gotcha_trigger_re():
    """Build one regex of all gotcha trigger phrases from taxonomy.py — the protect list."""
    phrases = []
    for t in taxonomy.GOTCHA_TYPES.values():
        phrases += [re.escape(p) for p in t.get("triggers", []) if p]
    # Always protect the Family-E compliance keywords even if triggers list is sparse.
    phrases += ["prevailing wage", "davis-bacon", "dbe", "liquidated damages",
                "density", "disincentive", "good faith effort"]
    return re.compile("|".join(phrases), re.I) if phrases else re.compile(r"(?!x)x")


GOTCHA_RE = _gotcha_trigger_re()


normalize = lib.normalize_paragraph   # shared with ingest so keys can't drift


def paragraphs(md: str):
    """Split a page's Markdown into paragraph blocks (blank-line separated)."""
    for block in re.split(r"\n\s*\n", md):
        b = block.strip()
        if b:
            yield b


def load_corpus():
    """Return list of (plan_id, state, [(page_no, section, paragraph_text), ...]).
    Reads each plan through convert.convert_pages (the same hybrid Markdown ingest uses),
    so the scan sees exactly what ingest will chunk."""
    manifest = indexer.load_manifest()
    out = []
    for pdf in sorted(lib.PLANS_DIR.rglob("*.pdf")):
        rec = manifest.get(pdf.stem, {})
        plan_id = rec.get("plan_id") or pdf.stem
        state = rec.get("state") or "?"
        current = "unknown"
        items = []
        for p in convert.convert_pages(pdf):
            sec = lib.detect_section(p["text"])
            if sec:
                current = sec
            for para in paragraphs(p["text"]):
                items.append((p["page"], current, para))
        out.append((plan_id, state, items))
    return out


def main():
    corpus = load_corpus()
    if not corpus:
        print("No cached Markdown found — run 01_pipeline/s1_convert.py 00_input/plans first.")
        sys.exit(1)
    n_plans = len(corpus)
    print(f"Scanning {n_plans} plans for cross-plan repetition…")

    # DF: normalized-paragraph -> set(plan_id)
    df = defaultdict(set)
    for plan_id, state, items in corpus:
        for _, _, para in items:
            key = normalize(para)
            if len(key) >= MIN_NORM_LEN:
                df[key].add(plan_id)

    # Per (doc_type, section): tally paragraphs, boilerplate paragraphs, protected ones.
    # doc_type is per-plan (all "proposal" here, but kept general).
    sec_stats = defaultdict(lambda: {"paras": 0, "boiler": 0, "protected": 0,
                                     "boiler_chars": 0, "total_chars": 0})
    for plan_id, state, items in corpus:
        doc_type, _ = lib.detect_doc_type([p for _, _, p in items] or [""])
        for page, section, para in items:
            key = normalize(para)
            if len(key) < MIN_NORM_LEN:
                continue
            st = sec_stats[(doc_type, section)]
            st["paras"] += 1
            st["total_chars"] += len(para)
            n_in = len(df[key])
            protected = bool(GOTCHA_RE.search(para))
            if n_in >= BOILERPLATE_MIN_PLANS:
                st["boiler"] += 1
                st["boiler_chars"] += len(para)
                if protected:
                    st["protected"] += 1

    # ── CSV ──
    OUT.mkdir(parents=True, exist_ok=True)
    csv_path = OUT / f"{DATE}_section_boilerplate.csv"
    with open(csv_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["doc_type", "section", "paragraphs", "boilerplate_paras",
                    "boilerplate_pct", "boilerplate_char_pct", "protected_paras",
                    "suggested_tier"])
        rows = []
        for (dt, sec), st in sorted(sec_stats.items(), key=lambda kv: -kv[1]["boiler_chars"]):
            bp = st["boiler"] / st["paras"] if st["paras"] else 0
            bcp = st["boiler_chars"] / st["total_chars"] if st["total_chars"] else 0
            # Suggested tier: high boilerplate + no protected gotchas -> DROP;
            # high boilerplate but protected -> DOWN_WEIGHT; otherwise KEEP.
            if bcp >= 0.75 and st["protected"] == 0:
                tier = "DROP"
            elif bcp >= 0.5:
                tier = "DOWN_WEIGHT"
            else:
                tier = "KEEP"
            rows.append((dt, sec, st["paras"], st["boiler"], round(bp, 2),
                         round(bcp, 2), st["protected"], tier))
            w.writerow(rows[-1])

    # ── Markdown report ──
    L = [f"# Boilerplate scan — cross-plan repetition ({DATE})\n",
         f"Corpus: **{n_plans} plans**. Boilerplate = a normalized paragraph that appears in "
         f"**≥{BOILERPLATE_MIN_PLANS} distinct plans**. `protected` = boilerplate paragraphs that "
         f"carry a gotcha trigger (prevailing wage, DBE, liquidated damages, density…) — these "
         f"are NEVER dropped.\n",
         "## Section boilerplate profile (sorted by boilerplate volume)\n",
         "| doc_type | section | paras | boiler % | boiler char % | protected | suggested tier |",
         "|---|---|--:|--:|--:|--:|:--:|"]
    for (dt, sec, paras, boiler, bp, bcp, prot, tier) in rows:
        L.append(f"| {dt} | {sec} | {paras} | {int(bp*100)}% | {int(bcp*100)}% | {prot} | {tier} |")
    L.append("")
    # Most-repeated paragraphs (the literal boilerplate), for a human gut-check.
    top = sorted(((len(plans), key) for key, plans in df.items() if len(plans) >= BOILERPLATE_MIN_PLANS),
                 reverse=True)[:15]
    # map a normalized key back to a sample raw paragraph
    sample = {}
    for plan_id, state, items in corpus:
        for _, _, para in items:
            k = normalize(para)
            if k not in sample and len(k) >= MIN_NORM_LEN:
                sample[k] = para
    L.append("## Top cross-plan repeated paragraphs (the literal boilerplate)\n")
    for cnt, key in top:
        snippet = re.sub(r"\s+", " ", sample.get(key, ""))[:160]
        prot = "  🔒protected" if GOTCHA_RE.search(sample.get(key, "")) else ""
        L.append(f"- **in {cnt}/{n_plans} plans**{prot}: {snippet}…")
    L.append("")
    L.append("## How this feeds the disposition (Task C)\n")
    L.append("- **DROP** tier = section is ≥75% boilerplate char-volume AND holds no protected "
             "gotcha — safe to skip at ingest (signature/forms/standard-condition prose).")
    L.append("- **DOWN_WEIGHT** = ≥50% boilerplate but mixed with real content or protected "
             "gotchas — keep in the store, de-prioritize at retrieval.")
    L.append("- **KEEP** = mostly project-specific — the bid schedule, real special provisions, gotchas.")
    L.append("- These suggestions inform `knowledge/section_taxonomy.csv` (the editable two-axis "
             "taxonomy); ingest reads that, not this report.")

    # ── Fingerprints file: the PRECISE toss-out list ingest applies ──
    # A normalized-paragraph key qualifies as droppable boilerplate iff it appears in
    # >= BOILERPLATE_MIN_PLANS plans AND its sample text carries NO gotcha trigger (the
    # guardrail — never drop a paragraph that hides a Family-E gotcha). This is the
    # paragraph-level "toss-out taxonomy": data-derived, not hand-maintained regex.
    fingerprints = [key for key, plans in df.items()
                    if len(plans) >= BOILERPLATE_MIN_PLANS
                    and not GOTCHA_RE.search(sample.get(key, ""))]
    fp_path = lib.DATA_DIR / "boilerplate_fingerprints.json"
    fp_path.write_text(json.dumps({
        "generated": DATE,
        "min_plans": BOILERPLATE_MIN_PLANS,
        "min_norm_len": MIN_NORM_LEN,
        "n_plans_scanned": n_plans,
        "keys": sorted(fingerprints),
    }))

    md_path = OUT / f"{DATE}_boilerplate_scan.md"
    md_path.write_text("\n".join(L) + "\n")
    print(f"\nWrote:\n  {md_path}\n  {csv_path}\n  {fp_path}  ({len(fingerprints)} drop fingerprints)")
    print("\nSuggested tiers:")
    for r in rows:
        print(f"  {r[0]:<10} {r[1]:<20} boiler_char={int(r[5]*100):>3}%  protected={r[6]:<3} -> {r[7]}")


if __name__ == "__main__":
    main()
