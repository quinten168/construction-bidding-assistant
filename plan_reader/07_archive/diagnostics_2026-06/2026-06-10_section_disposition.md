# Section disposition — the "toss-out taxonomy" (2026-06-10)

Answers T's Q1: *What sections do we skip, and how? Is boilerplate a consistent
pattern we can detect every time? Does a toss-out taxonomy make sense?*

## TL;DR

A toss-out taxonomy makes sense, but **not as aggressive section deletion**. The data
says:

1. **Exact cross-plan boilerplate is real but modest and format-specific.** The literal
   repeated text is EJCDC standard-contract language ("Work Change Directive",
   "Certificate of Substantial Completion", "Progress Schedule will be acceptable to
   Engineer") — and it only appears in the 4 EJCDC-format plans (ND county + SD). MnDOT
   plans use a different format, so there is **no single boilerplate pattern across all
   states**. Even the most boilerplate-heavy section (`proposal_front`) is only ~48% by
   character volume; nothing approaches "mostly boilerplate."
2. **Boilerplate is interleaved with gotchas in the same sections.** `contract_front`
   is 34% boilerplate but holds **33 protected paragraphs** carrying Family-E gotchas
   (prevailing wage, DBE, liquidated damages, bonds). Dropping the section would drop
   those. This is exactly the risk flagged at planning time.

So we use **two precise levers** instead of a blunt section delete:

| Lever | What it does | Why it's safe |
|---|---|---|
| **Paragraph fingerprints** (`data/boilerplate_fingerprints.json`, 738 keys) | Ingest drops individual paragraphs that recur in ≥3 plans **and carry no gotcha trigger** | Data-derived, gotcha-guarded — removes EJCDC boilerplate paragraph-by-paragraph without touching project-specific or gotcha-bearing text |
| **Section tiers** (`data/section_disposition.csv`) | DOWN_WEIGHT procedural front-matter; KEEP everything else; **DROP nothing** | Down-weighting de-prioritizes low-signal sections at retrieval while keeping them searchable (gotchas stay reachable) |

## The tiers (and why)

- **KEEP** — `bid_schedule`, `special_provisions`, `prevailing_wage`, `traffic_staging`,
  `general_notes`, `specifications`, `unknown`. Project-specific, ≤2% boilerplate.
- **DOWN_WEIGHT** — `proposal_front` (blank-form cover, 48% boilerplate),
  `contract_front` (EJCDC conditions + bonds, 34% boilerplate but 33 protected gotchas),
  `title_index` (navigation; also over-carries-forward, so unreliable to drop).
- **DROP (section-level)** — **none.** The evidence doesn't justify deleting any whole
  section; the paragraph fingerprints do the safe cutting.

## "Consistent pattern we can detect every time?"

Partly. Within a **document format** (EJCDC), boilerplate is highly consistent and
fingerprintable. **Across formats** (MnDOT vs EJCDC) it is not — which is why detection
is empirical (cross-plan repetition) rather than a hand-maintained regex list, and why
the fingerprint set will grow/shift as more plans of each format are added. Re-run
`tools/boilerplate_scan.py` whenever the corpus changes to refresh the fingerprints.

## How to tune
- Edit `data/section_disposition.csv` to move a section between KEEP / DOWN_WEIGHT / DROP.
- Lower `BOILERPLATE_MIN_PLANS` in `tools/boilerplate_scan.py` to catch more (riskier);
  raise it to be more conservative.
- The gotcha guardrail is automatic: any paragraph matching a `taxonomy.py` trigger is
  never added to the fingerprint drop-list.

## Evidence
- `outputs/2026-06-10_boilerplate_scan.md` — section boilerplate profile + the literal
  top repeated paragraphs.
- `outputs/2026-06-10_section_boilerplate.csv` — per-section boilerplate %, protected count.
