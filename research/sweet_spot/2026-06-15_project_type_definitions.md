# CSI project-type definitions — the canonical rule

*Reference of record. Updated 2026-06-17 to the share-gated **v2** rule. Read this before any
archetype analysis. The story of how it was decided is in `README.md`.*

A project's **work-type** = *what kind of job it is*, read from the quantities in its bid schedule.
We use only the **7 plan-knowable roll-up quantities** — the same fields whether they come from CSI's
historical data or the Plan Reader's extraction of a new RFP, so the rule **runs forward on new plans**:

```
MIX_TN   GRADE_CY   BASE_TN   SHLDR_TN   MILL_SY   CRUSH_TN   STOCK_TN
```

The single organizing question: **does the job lay real pavement, and if so does it also regrade the
roadbed or mill the surface?**

---

## The rule (two layers)

**Layer 1 — is it genuinely a paving job?**
A job is *paving* if its hot-mix is a real share **or** a real absolute amount of the work:

```
paving  =  (mix_share ≥ 0.15)  OR  (MIX_TN ≥ 1000)
   where  mix_share = MIX_TN / (MIX_TN + BASE_TN + SHLDR_TN + CRUSH_TN + STOCK_TN)
```

**Layer 2 — route the job.** Each trigger is **gated by a magnitude floor** so a token amount can't
flip the label:

| | Condition | → Work-type | CSI edge |
|---|---|---|---|
| **paving** + real grading (`GRADE_CY ≥ 500`) | regrade **and** pave | **Reconstruct / Rebuild** | **High** |
| **paving** + real milling (`MILL_SY ≥ 1000`), no grading | mill off old surface, repave (commodity) | **Mill & Overlay** | **Low** |
| **paving**, no grading, no milling | lay new asphalt over the surface | **HMA Overlay / Resurface** | Medium |
| **not paving** + real grading | move/shape dirt, no real pavement | **Grading / Earthwork** | Medium |
| **not paving** + base/shoulder present | base / shoulder / gravel, no surface | **Aggregate / Base / Gravel** | Low–Med |
| no quantities at all | data-coverage gap, **not a real type** | **Unknown / NoQty** | N/A |
| has quantities but none of the above | rare residual | **Other** | N/A |

**Priority (first match wins):** Reconstruct → Mill & Overlay → HMA Overlay → Grading → Aggregate → Other.

### The four thresholds (and why they sit there)
Each was read off the material distributions of the 1,592-project history (see `README.md` for the charts):

| Threshold | Value | Why |
|---|---|---|
| `MIX_SHARE_MIN` | **0.15** | Real paving jobs sit at mix-share p25 ≈ 0.18–0.26; the token-mix jobs we want to demote sit below ~0.20. 0.15 is conservative. |
| `MIX_ABS_MIN` | **1,000 t** | The OR-floor. A 39,000-t mill-and-overlay that *also* carries more aggregate dips below 15% share but is obviously paving. Real paving jobs sit at mix p25 ≈ 1,300 t; token jobs have <100 t. |
| `GRADE_MIN_CY` | **500 CY** | Reconstruct grading sits at p10/p25 = 200/668 CY; <500 CY is approach- / driveway-scale, not a roadbed regrade. |
| `MILL_MIN_SY` | **1,000 SY** | Mill & Overlay milling sits at p25 ≈ 1,664 SY; ~19% sit <1,000 SY (edge mills), which shouldn't define the job. |

---

## Why this rule (the design choices)

- **Shares, not raw magnitude.** Across the data, the *amounts* of MIX/BASE overlap heavily between
  types — they don't separate. The **share** of mix-vs-aggregate cleanly draws the paving / non-paving
  line, and the **presence of grading vs milling** splits the paving types. (Evidence: the distribution
  and tonnage-share analyses cited in `README.md`.)
- **Magnitude gates kill "trivial triggers."** The earlier binary-presence rule labeled a job
  "Reconstruct" on as little as 30 CY of grading, or "Mill & Overlay" on 237 SY of edge milling. That
  over-labeled **Reconstruct by ~25%** (615 → 461 projects). The floors fix it.
- **Grade-vs-surface is CSI's own distinction** (rebuild vs resurface) and the most cost-meaningful split
  (earthwork crews vs paving crews). It makes the types mutually exclusive.
- **BASE is deliberately *not* a routing trigger.** It is present in 85–95% of every paving type, so it
  separates nothing; and base *intensity* was tested as a CSI-edge signal and **rejected** (no predictive
  relationship — see `scripts/2026-06-17_base_intensity_edge_validation.py`).
- **MILL is deliberately *not* used in the non-paving branch.** The "Aggregate jobs that carry milling"
  are a data artifact (levee / landfill / grading jobs with blank MIX & GRADE and a mis-loaded MILL_SY),
  not a real reclaim type.

---

## Known limits (what the 7 quantities can't see)

- **Full Depth Reclamation (FDR) / reclaim-and-pave** is invisible here — there is no reclamation column
  in the historical data, so an FDR job (e.g. Stearns Co CP-073-123) classifies as **Mill & Overlay**
  even though it is reconstruct-class work. Recovering FDR needs the Plan Reader's **bid-schedule SPEC
  codes** (spec 2215), not the 7 roll-ups. Same wall for a clean **Reclaim / Cement-Stabilization** split.
- **Size** (Large/Small) and **messiness** (1–10) are **separate axes**, derived *within* each work-type —
  they are **not** types. Size lives in `scripts/2026-06-15_size_within_archetype.py`; messiness is a
  post–Plan-Reader signal.

---

## Where the rule lives (keep in sync)

The rule is duplicated in **three** places that must stay identical (same thresholds, same logic):

1. `02_modules/dashboard/utils/data.py` → `_rule_archetype()`
2. `02_modules/sweet_spot/scripts/2026-06-04_02_archetypes.py` → `rule_archetype()`
3. `02_modules/sweet_spot/scripts/2026-06-15_size_within_archetype.py` → `work_type()`

`scripts/2026-06-17_archetype_rule_v2.py` is the **reference implementation + the v1→v2 diff tool** —
run it to re-derive the label-migration table or sanity-check a future change against the baseline.
