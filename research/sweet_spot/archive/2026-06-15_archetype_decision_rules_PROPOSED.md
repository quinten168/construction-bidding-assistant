# CSI project classification — PROPOSED model (to test with the client)
*2026-06-15 · sweet_spot · a discussion artifact, NOT a code change. The live `10_000` rule is unchanged.*

This rewrites the earlier "fix the 10k cut-off" note. Working through it with CSI's kickoff
transcripts (`04_meeting_notes/05-22`, `05-28`) showed the real problem wasn't the *number* — it was
the *structure*. "Large" was a **size**, sitting in a list of **work-types**. Below is the corrected
model and the questions for CSI.

## The headline: a project has THREE axes, not one label

CSI doesn't think in five flat archetypes. From their own words, a job is:

1. **Work-type** — *what kind of job* (read off the bid schedule).
2. **Messiness** — *how messy* (phasing + #scopes + spread-out); their #1 edge ("got our name on it").
3. **Size** — *how big*, judged **relative to its own work-type** ("fewer, larger jobs").

…and the thing they actually want to know is **profit** by (work-type × size × messiness) — their
"sweet spot." *"We don't know if we're bidding grading too high, paving too cheap, pipe…"* (Ross).

---

## Axis 1 — Work-type archetype (from the bid schedule)

Objectively separable **today** by which scopes are present in the 7 quantities (validated on 1,376
quantity-complete projects):

Refined (split on **grading = rebuild vs resurface**; drops the earlier "Mixed Paving" catch-all):

| Work-type | Distinguishing rule (first match wins) | n | CSI edge (win + margin) |
|---|---|---|---|
| **Reconstruct / Rebuild** | GRADE **and** MIX present | 615 | **High** — multi-scope, self-perform |
| **Mill & Overlay** | MIX, no GRADE, MILL present | 321 | **Low — "gross", avoid** |
| **Grading / Earthwork** | GRADE, no MIX | 212 | Medium |
| **HMA Overlay / Resurface** | MIX, no GRADE, no MILL | 109 | Medium |
| **Aggregate / Base / Gravel** | BASE/SHLDR, no MIX, no GRADE | 84 | Low–Med |
| *Other / Unknown* | residual / no quantities | 35 / 215 | N/A |

Full definitions: `2026-06-15_project_type_definitions.md`. *Needs the Plan Reader's bid-schedule SPEC
codes to add:* a **Reclaim/Stabilization** type, and a finer **Mill & Overlay vs HMA Resurface** split.

**"CSI edge" = their win + margin advantage on that type** — evidence-backed (below), not asserted.

---

## Axis 2 — Messiness (1–10, clean ↔ messy)  *— mostly a Plan-Reader deliverable*

NOT a work-type — a **score that composes with Axis 1**. *"Messy/Complex"* = a high-messiness job,
**concentrated in Reconstructs but possible on any type** (e.g., spread-out ¼-mile turn lanes over a
200-mile resurface). CSI asked for exactly this 1–10 scale.

Variables, in priority (★ = available now, ☆ = needs Plan Reader / RAG):
1. ☆ **# distinct SPEC categories** in the bid schedule — the backbone (objective).
2. ☆ **Phasing** severity — *already partly extracted* (`phasing_requirements`).
3. ☆ **Spatial fragmentation** — many small location items / stationing spread.
4. ☆ **Subbed-scope presence** — bridge / concrete / structures (CSI subs these).
5. ☆ **Schedule tightness**, 6. ☆ **urban**.
- ★ **Interim proxy today** = `n_mat_types` (+ `BOX`). Weak — flagged, not shipped as the real score.

**Ask CSI:** *"Does a 1–10 messiness score built from #scopes + phasing + spread-out + subbed work
match how you decide 'this one's got our name on it'? What weights?"*

---

## Axis 3 — Size, derived WITHIN each work-type (statistical, plan-knowable)

"Large" is a **tier inside each work-type**, in that type's **native unit** (never summing across
units; never using auction $). Cut derived from the type's own log-size distribution (GMM 2-mode seam,
else median):

| Work-type | Size basis | "Large ≥" | back-test ρ vs $ |
|---|---|---|---|
| Reconstruct / Rebuild | placed tons (MIX+BASE+SHLDR) | ~7,190 t | **0.64** |
| Mill & Overlay | MIX tons | ~2,780 t | 0.41 |
| HMA Overlay / Resurface | MIX tons | ~1,560 t | 0.37 |
| Grading / Earthwork | GRADE cubic yards | ~4,340 CY | 0.43 |
| Aggregate / Base / Gravel | BASE+SHLDR tons | ~2,600 t | 0.40 |

*(exact cuts: `outputs/2026-06-15_worktype_size_thresholds.csv`)*

*Why per-type, not one number:* MIX/GRADE/BASE are **independent, non-overlapping** size drivers
(VIF 1.2; MIX–GRADE corr ≈ −0.01) — distinct layers in distinct units — so no single pooled measure
works. Each type's size tracks realized $ (ρ 0.37–0.66) **without using $ as an input** (leakage-safe).

**Ask CSI:** *"Within each job type, does this small/large line match your gut? And do you want a
state-relative version (ND jobs run smaller than SD)?"*

---

## The sweet spot — profit by work-type × size  (the answer to "where do we make money")

Median CSI margin by cell (full table: `outputs/2026-06-15_archetype_size_profit.csv`). The pattern is
striking and **matches the transcript** (*"small all-self-performed ≈ 45%; big subbed ≈ 30%"*):

- **Smaller jobs within a type carry higher margin** — Reconstruct **Small 16% vs Large 8%**; Mixed
  Paving **Small 16% vs Large 10%** (large jobs lean on subs → lower self-perform → thinner margin).
- **Grading is the margin standout** — Small ~26%, Large ~24% (highly self-performed dirt work).
- **Mill & Overlay is the floor** — ~10% margin, commodity, many bidders → confirms "avoid."
- **Reconstruct-Large wins most** (26% win, 19% win-well) but at thin margin — a *volume/keep-crews-busy*
  play, not a *margin* play. The distinction CSI wanted to see.

**Ask CSI:** *"Does this map to your experience — small self-performed jobs are your margin sweet
spot, big reconstructs keep crews busy at thin margin, mill-and-overlay is to be avoided?"*

---

## Migration from the old 5 archetypes
Complex/Messy → **Axis 2** (messiness) · Large Volume → **Axis 3** (size) · Standard Paving → **Mill &
Overlay + HMA Resurface** · Earthwork Heavy → **Grading** · Shoulder/Base → **Aggregate/Base**.

## Honesty / guardrails
- **Buildable + back-testable today:** Axis 1 (work-type), Axis 3 (size), and the margin sweet-spot —
  all from the 7 plan-knowable quantities.
- **Needs the Plan Reader:** the real Axis 2 (scope count, phasing, fragmentation) and the
  Reclaim / Mill-vs-Resurface refinements. Today's messiness is a flagged proxy.
- **Leakage-safe (HR10):** `Project_Size_Dollars` is the post-auction winning bid → **never a live
  input**; used only to back-test the size tiers (ρ above). **No bid-price model (HR9).**
- **Profit target:** `CSI_Margin_Pct` now; swap in the **2023–25 gross-profit reports** (5-digit job
  number link) when CSI provides them.

*Backing: `scripts/2026-06-15_size_within_archetype.py` + its notebook/Rmd twins; data lineage and the
full reasoning in the project plan.*
