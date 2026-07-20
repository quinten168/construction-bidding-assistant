# Sweet-Spot module — find which projects CSI should chase

**Start here.** This module answers one business question: **where is CSI's competitive sweet spot —
which kinds of projects should we bid on?**

It does that in two moves:

1. **Label every project by work-type** (Reconstruct, Mill & Overlay, HMA Overlay, Grading, Aggregate)
   using only the quantities in the bid schedule.
2. **Measure CSI's performance inside each type** — how often we bid, how often we win, and how often we
   win *well* vs. overpay ("bomb").

If you only read one other file, read **`2026-06-15_project_type_definitions.md`** — that's the rule of
record for how a project gets its type.

---

## How we decided the archetype rule (the short story)

We didn't guess the types. We worked up to them from the data — CSI's 1,592-project bid history, using
the 7 quantity fields every project has. Four analyses, in order:

1. **Looked at the raw material distributions per type.**
   *Finding:* the **amounts** of asphalt/base/etc. overlap heavily between types — magnitude alone can't
   tell a Reconstruct from a Mill & Overlay.
   *Script:* `scripts/2026-06-17_material_distributions_by_archetype.py`

2. **Switched to material *shares* (each material as a % of total tons).**
   *Finding:* shares separate the types cleanly — the **share of hot-mix** draws the paving / non-paving
   line, and **whether the job grades or mills** splits the paving jobs apart.
   *Script:* `scripts/2026-06-17_tonnage_shares_by_archetype.py`

3. **Tested whether "how much base" predicts CSI's profit margin** (a tempting idea).
   *Finding:* **no** — base intensity has no real relationship with CSI's edge. So base stays *out* of the
   rule. (Good to know what *doesn't* work.)
   *Script:* `scripts/2026-06-17_base_intensity_edge_validation.py`

4. **Built the new rule and checked it against the old one, job by job.**
   *Finding:* the old rule labeled jobs "Reconstruct" on as little as 30 cubic yards of grading. The new
   rule adds size floors so a *token* amount can't flip the label. Net effect: **Reconstruct shrank ~25%**
   (615 → 461 projects) — those were never really reconstructs.
   *Script:* `scripts/2026-06-17_archetype_rule_v2.py` (also prints the before/after migration table)

The result is the **share-gated rule** written up in `2026-06-15_project_type_definitions.md`.

---

## The rule in one breath

A project is a **paving job** if hot-mix is a real share (≥15% of tons) **or** a real amount (≥1,000 t).
Then:

- paving **+ real grading** → **Reconstruct / Rebuild** (high CSI edge)
- paving **+ real milling**, no grading → **Mill & Overlay** (low edge — commodity)
- paving, no grading, no milling → **HMA Overlay / Resurface**
- not paving **+ grading** → **Grading / Earthwork**
- not paving **+ base/shoulder** → **Aggregate / Base / Gravel**

"Real" means above a size floor (grading ≥ 500 CY, milling ≥ 1,000 SY) so tiny amounts don't count. Full
detail and the *why* behind each number is in `2026-06-15_project_type_definitions.md`.

---

## How to run it

From the repo root (`01_Summer_2026/`), with a Python that has pandas, numpy, scikit-learn, matplotlib:

```bash
# 1. build the one-row-per-project table
python3 02_modules/sweet_spot/scripts/2026-06-04_01_build_base_table.py
# 2. label every project by work-type (this is where the rule runs)
python3 02_modules/sweet_spot/scripts/2026-06-04_02_archetypes.py
# 3-5. bid model, win model, the sweet-spot map
python3 02_modules/sweet_spot/scripts/2026-06-04_03_bid_model.py
python3 02_modules/sweet_spot/scripts/2026-06-04_04_win_model.py
python3 02_modules/sweet_spot/scripts/2026-06-04_05_sweetspot.py
# 6. size (Large/Small) within each type — feeds the dashboard's Archetype page
python3 02_modules/sweet_spot/scripts/2026-06-15_size_within_archetype.py
```

Run them **in order** — each reads the previous step's CSV from `outputs/`. The dashboard reads the
outputs of steps 2 and 6.

---

## What's where

```
sweet_spot/
├── README.md                                  ← you are here
├── 2026-06-15_project_type_definitions.md     ← THE RULE (reference of record)
├── 2026-06-04_00_METHODOLOGY.md               ← why the bid/win models are built this way
├── 2026-06-15_large_project_threshold_findings.md  ← the size (Large/Small) analysis
├── scripts/        the pipeline (01-05) + the size step + the 2026-06-17 analyses that set the rule
├── outputs/        every generated CSV + chart (regenerable by re-running the scripts)
├── notebooks/      annotated, runnable twins of the scripts
└── archive/        superseded docs (old archetype rule) — see archive/README.md
```

### Key scripts at a glance

| Script | What it does | Load-bearing? |
|---|---|---|
| `2026-06-04_01_build_base_table.py` | Collapse the bid data to one row per project | Yes — feeds everything |
| `2026-06-04_02_archetypes.py` | **Apply the work-type rule** + discover clusters | Yes — dashboard reads its output |
| `2026-06-04_03/04/05_*.py` | Bid model, win model, sweet-spot map | Diagnostic |
| `2026-06-15_size_within_archetype.py` | Large/Small size **within** each type | Yes — dashboard Archetype page |
| `2026-06-15_large_project_threshold_analysis.py` | Where the "Large" size cut sits | Yes — dashboard Archetype page |
| `2026-06-17_archetype_rule_v2.py` | The rule's reference implementation + v1→v2 diff | Reference / QA |
| `2026-06-17_material_distributions_by_archetype.py` | Evidence: amounts overlap | Reference |
| `2026-06-17_tonnage_shares_by_archetype.py` | Evidence: shares separate | Reference |
| `2026-06-17_base_intensity_edge_validation.py` | Evidence: base ≠ edge (rejected) | Reference |

---

## Two things to know before you change anything

1. **The rule lives in 3 places that must stay identical** (same thresholds, same logic):
   `dashboard/utils/data.py`, `scripts/2026-06-04_02_archetypes.py`, and
   `scripts/2026-06-15_size_within_archetype.py`. If you change one, change all three, then re-run
   `2026-06-17_archetype_rule_v2.py` to confirm the labels still make sense.

2. **The 7 quantities can't see Full Depth Reclamation (FDR).** An FDR "reclaim-and-pave" job looks like a
   Mill & Overlay to this rule, because the historical data has no reclamation field. Picking those up
   needs the Plan Reader reading the bid-schedule SPEC codes (spec 2215). It's a known gap, not a bug.

---

## Status (2026-06-17)

The share-gated rule is **live and validated**:
- Propagated into all 3 functions; all downstream outputs regenerated; dashboard self-test passing.
- **Validated against the golden set** — v2 gives the same label from hand-verified plan quantities as
  from the master CSV (100%, 36/36); the Stearns FDR limitation is confirmed.
- **Win/loss refreshed on v2 labels** — see `2026-06-17_sweetspot_findings_v2.md`. Headline: CSI's edge
  is in win *quality* (Reconstruct + Grading are healthy; HMA Overlay + Aggregate carry the pricing leak,
  61–63% bomb-share of wins).
