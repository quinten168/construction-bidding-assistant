# Extraction Eval — Scorecard (2026-06-09)

Whole-doc extractor (`extraction_mvp.py`) scored against the golden dataset, across the
**11 plans that now have a local PDF**. Raw run log: `2026-06-09_extraction_eval_raw.txt`.
Re-run: `.venv/bin/python 02_modules/plan_reader/rag/scripts/2026-06-08_04_eval.py`.

> **How to read accuracy here:** a "miss" means the PDF and the golden answer *disagree* —
> it is a flag to adjudicate by hand, not proof the extractor is wrong. The golden values
> are still the unverified master-join baseline, and the 6 new 2023 plans have **blank**
> golden quantities (they need hand-verification), so they only contribute to `state`.

## Scorecard (per field)

| Field | Scored | Match | Accuracy | Read |
|---|--:|--:|--:|---|
| `state` | 11 | 11 | **100%** | solid |
| `project_location` | 5 | 5 | **100%** | solid (richer than golden — see below) |
| `prevailing_wages` | 5 | 2 | 40% | truncation bug — **doc-dependent** (see below) |
| `mix_tn` | 3 | 2 | 67% | quantity disagreements / truncation |
| `grade_cy` | 5 | 3 | 60% | quantity disagreements |
| `base_tn` | 3 | 1 | 33% | quantity disagreements |
| `box` | 2 | 2 | 100% | solid |
| `shldr_tn`/`mill_sy`/`crush_tn`/`stock_tn` | 0 | — | — | no golden values to score against yet |

## The key insight: `prevailing_wages` is now provably the truncation bug

It scored **0% before, 40% now** — and the pattern is diagnostic:
- ✅ Extracted correctly on **00 Prosoal** (280 pg) and **9804001** (252 pg) — the wage section
  fell inside the kept first-60%.
- ❌ Still `None` on **SAP 032**, **9758035**, **08MQ** — the wage determination sits in the
  dropped middle (`smart_truncate` keeps first 108k + last 72k chars).

So whether prevailing wages extracts is **luck of where it sits in the doc.** This is exactly
why the fix is to route prevailing wages through RAG (which retrieves it at distance 0.36
regardless of position) rather than blind truncation.

## The extractor already reads location *and* derives length

`project_location` scored 100% and is consistently **richer than the golden county**, e.g.:
- **9804001:** "Vermont Access Road NE … Miltona Township, Douglas County, MN; STA 00+00 to STA 115+61 **(2.190 miles)**"
- **00 Prosoal:** "… Watonwan County … approx. coordinates **43.877N, 94.688W**"
- **Yankton:** "SD Highway 52 … Begin Station 0+33.17 (approx. **Lat 42.9086, Long -97.5560**)"

The LLM is already extracting stationing-derived **length** and even **lat/long** when present —
supporting the "stationing → length/midpoint" next step and confirming we don't need a separate
geocoder for many plans.

## What the 6 new plans extracted (cached; golden not yet filled → not scored)

| Plan | Outcome | mix_tn | Notable gotchas found | Maps to taxonomy |
|---|---|--:|---|---|
| Dunn ND CP-13 | **WON** | 40,877 | Intelligent Compaction, High Friction Surface Treatment | `qc_inspection`, material spec |
| Yankton SD P-PH-0052 | **WON** | 59,745 | Lewis & Clark 4(f)/6(f), 180-day window, NLEB | `cultural_historic`, `seasonal_window`, `environmental_species` |
| Watonwan MN SP 8303-48 | lost | — | intermediate completion dates, 2-season duration, full Davis-Bacon | `tight_schedule`, `prevailing_wage` |
| Otter Tail MN CP 4069-304 | lost | 324 | no work after dark, no Sat after 3PM, no July 3 | `night_work`, `tight_schedule` |
| Walsh ND Hwy 9 | lost | 33,869 | millings hauled to owner pit 5mi W of Pisek at contractor cost; joint-density penalty | `incidental_scope`, `density_lot_failure` |
| Brookings SD surfacing | lost | 17,432 | pilot car at all times, flaggers at all intersections | `traffic_control` |

**Takeaways for the team:**
1. CSI's **wins are large-volume** jobs (40k–60k tons) — useful signal for the archetype work.
2. The gotchas these plans surface **validate the 20-type taxonomy** with fresh, real examples —
   good material for the Alex review.
3. To actually *score* these rows, a human needs to fill their golden quantities/gotchas
   (they have no master `contract_id` to auto-fill). That's the next golden-dataset task.
