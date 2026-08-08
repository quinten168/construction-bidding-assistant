# Spec — four-layer material mapping with provenance

Status: **SPEC ONLY. Nothing built. Nothing restructured.** For T to grill.
Date: 2026-08-07. Every number below was measured today against the live corpus; the method is
stated per number.

---

## 0. The finding that should change the design before you read the rest

T's thesis — *"a 78-keyword heuristic is doing the job of a 2,434-row lookup table that already
exists"* — is **correct about the structure and half-correct about the remedy.**

I tested the lookup table against today's three six-figure bugs:

| bug | what `material_crosswalk.csv` says | verdict |
|---|---|---|
| `FULL DEPTH RECLAMATION` | `milling`, source **`llm`**, confidence high | ✅ **would have caught it** |
| `REMOVE AGGREGATE BASE` | `removal`, source **`removal_rule`**, high | ✅ **would have caught it** |
| `MILL BITUMINOUS SURFACE (1.5")` | `hma`, source **`keyword`**, high | ❌ **wrong, identically** |

**681 of the 2,434 lookup rows have `match_source = 'keyword'`** — they were seeded from `SPEC_MAP`
and inherited its bugs. Breakdown: `llm` 1,608 · `keyword` 681 · `removal_rule` 145.

So a naive "L1 first, it's authoritative" design would fix two bugs and **entrench the third**,
converting a wrong heuristic guess into a high-confidence lookup hit that nothing ever re-examines.
That is worse than today, because today the heuristic is at least visibly a heuristic.

**Consequence for the design: `match_source` is not decoration, it is a trust tier.** The layer
order must be `human > llm > removal_rule > keyword`, and keyword-sourced rows must be treated as
**provisional** — re-derivable, and re-derived whenever `SPEC_MAP` changes. Detail in §4.

---

## 1. Is `material_crosswalk.csv` wired into anything? **No. Confirmed by two methods.**

**Method 1 — repo-wide grep** for `material_crosswalk` and `bucket_hierarchy` across `*.py`,
`*.ts`, `*.tsx` (excluding `node_modules`, `.venv`). Every hit is one of:

| file | role |
|---|---|
| `04_tools/09_build_material_crosswalk.py` | **the builder** — creates, seeds, LLM-classifies, mirrors to CSV |
| `04_tools/publish_to_supabase.py` | publishes both as Postgres tables |
| `04_tools/inspect_supabase.py`, `audit_types_for_postgres.py` | inspection/审计 tooling |

**Method 2 — read the consumers directly.** `05_knowledge/quantity_crosswalk.py`,
`04_tools/05_parse_bid_schedule.py`, `04_tools/10_remap_buckets.py`,
`04_tools/11_build_material_map.py`, and everything under `apps/api/backend/` were read: none opens
either file, and none imports anything that does.

**So both tables are built, mirrored to CSV, and published to Postgres — and read by nothing at
runtime.** The mapping decisions in `material_crosswalk.csv` have never affected a single reported
number.

`bucket_hierarchy.csv` is in the same state, and it is the more consequential of the two (§3).

## 2. Coverage: L1 vs L2

Measured against the 4,125 real pay items (6,385 `materials` rows minus 2,260 rejected by
`08_material_universe.is_noise`):

| layer | coverage | note |
|---|---:|---|
| **L1** exact lookup | **4,125 / 4,125 — 100.0%** | ⚠️ see caveat |
| **L2** `SPEC_MAP` keyword | **1,677 / 4,125 — 40.7%** | the other 59.3% resolve to `other` |
| neither | 0 | |

**The 100% caveat, stated plainly: `material_crosswalk.csv` was BUILT FROM THIS CORPUS on
2026-07-03.** Every description in it is a description it has already seen, so 100% is
tautological — it measures *recall on the training set*, not generalisation. The honest reading is:

- L1 is a **perfect cache of decisions already made** about 2,290 distinct descriptions.
- Its coverage of a **new, unseen plan is unmeasured**, and cannot be measured from this corpus.
- L2's 40.7% is the honest generalisation number, and it is the number that matters for new plans.

That does not weaken the case for L1 — a perfect cache is exactly what you want in front of a 41%
heuristic — but it does mean **L3 is not optional**. The unseen-item rate on a genuinely new plan is
the thing L3 exists to absorb, and we have no estimate of it. Getting one is a prerequisite, not a
follow-up: hold out the 5 most recently added plans, rebuild the lookup without them, and measure L1
hit rate on those. Until that runs, any claim about L1's real-world coverage is unfounded.

## 3. `bucket_hierarchy.csv` and `removal_tons`

The file has 6 sub-buckets. The code has 7. **They are not the same 6.**

| `bucket_hierarchy.csv` | in code's `CSI_BUCKETS`? |
|---|---|
| `base_tons` → AGGREGATE | yes |
| `shoulder_tons` → AGGREGATE | yes |
| `hot_mix_tons` → ASPHALT | yes |
| `grading_quantity` → GRADING | yes |
| **`removal_tons` → GRADING, TON, factor 1.75** | **NO — the code has no such bucket** |
| `milling_sy` → MILLING | yes |
| — | `crushing_tons` (invented) |
| — | `stockpile_tons` (invented) |

### Does adopting `removal_tons` resolve REMOVE AGGREGATE BASE? **Yes, and T is right that I got it wrong.**

I excluded those 4 rows (202,031 TON) to no bucket this evening on the grounds that no conversion
was defensible. **The conversion was already defensible and already recorded** — the hierarchy's own
note says *"removed pavement/base; ÷1.75 Ton/CY into GRADING (Dunn plan-sheet factor); own visible
line."* The factor is sourced to a real plan sheet. I did not read this file before deciding, and
that is the same "check more than one place" failure as the others.

### What else moves if we adopt it — measured

Rows whose lookup `spec_category = 'removal'`: **248 rows across 42 plans.** By unit:

| unit | quantity | disposition under the hierarchy |
|---|---:|---|
| **TON** | **208,440** | → `removal_tons`, ÷1.75 → **119,109 CY** into GRADING, shown as its own line |
| SY | 68,954 | **no factor in the hierarchy — still homeless** |
| LF / LINFT / FT / LNFT | 302,534 | fence, sign, pipe, culvert — must NOT enter a tonnage bucket |
| SQFT / SF | 54,416 | ÷9 → SY, then same problem as SY |
| CY | 21,407 | already GRADING's native unit |
| EA / EACH / HOUR / LS | ~630 | never a quantity bucket |

**Critical design point: `spec_category='removal'` is NOT the same as the `removal_tons` bucket.**
The pre-read already warned that "158 removal item types are mostly fence/sign/pipe". The unit guard
must survive this change — `removal` + TON → `removal_tons`; `removal` + LF → nothing. Adopting the
hierarchy does not let us drop the (category, unit) bridge; it adds a row to it.

**Still unresolved after adoption:** removal measured in SY (68,954) has no factor and depth is
stated on 0 of 41 corpus rows. That stays a CSI question, unchanged.

**One data-quality flag found while measuring:** a row with unit
`WILLIAMSCOUNTYNDSTATOREMOVALSCOUNTYROADRECONSTRUCTION` and quantity 209,003,763,060 passed the
noise filter. A CAD legend that slipped through. It is excluded from every total above, but
`is_noise` should catch it.

### Should `crushing_tons` / `stockpile_tons` be deleted?

**`crushing_tons`: yes, delete.** It holds 0. Its three keywords match nothing. The hierarchy never
had it. The only corpus row containing "CRUSH" is `Crushed | Crushed |` — a mis-split table cell
with no quantity. Three independent signals agree it does not exist as a pay item.

**`stockpile_tons`: no, do not delete — but it is not a hierarchy bucket either.** It currently holds
4,548 TON from real items (`Salvage and Stockpile Asphalt Mix and Granular Base Material`, `Blend,
Haul, and Stockpile Granular Material`), and the lookup has a `stockpile` spec_category. So the work
exists; what is missing is a decision about where it belongs. Recommend: keep the category, drop the
*bucket*, and let those rows report as `no_bucket_for_unit` until CSI rules — which is exactly the
FDR treatment. **Do not silently delete a bucket that holds a real number.**

Both belong in the batch document as *findings*, not questions: "crushing does not appear as a pay
item in 117 plans" is an answer, not an ask.

## 4. The four layers

```
        ┌─────────────────────────────────────────────────────────────┐
raw ──▶ │ normalize()  — the ONE normalizer, shared by all layers      │
        └─────────────────────────────────────────────────────────────┘
                │
    L1 ─────────▼──────────  exact lookup (normalized_description, state)
                │              trust tier by match_source:
                │                human       → authoritative, never re-derived
                │                llm         → authoritative until contradicted
                │                removal_rule→ authoritative
                │                keyword     → PROVISIONAL — re-derive on SPEC_MAP change
                │  miss, or hit is provisional-and-stale
    L2 ─────────▼──────────  SPEC_MAP keyword heuristic
                │              writes back as match_source='keyword' (provisional)
                │  no keyword fires
    L3 ─────────▼──────────  LLM classifier, one short call
                │              context: 6 bucket defs + CSI's rulings + 3–4 nearest L1 neighbours
                │              writes back as match_source='llm' + confidence
                │
    L4 ─────────▼──────────  confidence gate → existing human verify step
                               triggers on: low confidence, OR quantity ≥ 100,000 units,
                               OR L3 disagreed with L2, OR gap_reason='never_matched'
```

**Provenance stamped on every mapped row** (extends the `crosswalk_version` column added today):
`mapping_layer` (L1/L2/L3), `match_source`, `match_confidence`, `crosswalk_version`.

### The provisional-row rule — this is what makes it self-correcting rather than self-entrenching

A `keyword`-sourced L1 row is a **cached heuristic answer, not a decision**. It carries the
`spec_map_version` that produced it. When `SPEC_MAP` changes, every provisional row whose version is
stale is re-derived. Without this, tonight's `MILL BITUMINOUS` fix would never reach the 681
keyword-seeded rows, and the lookup would permanently disagree with the heuristic that produced it.

This also answers "does the heuristic shrink over time?" — yes, but only for `llm`/`human` rows.
Keyword rows are not shrinkage, they are a cache.

### L3 cost and latency

Grounded in today's measured vision call ($0.0339 for 5,225 input / 312 output tokens on Opus 5) and
the measured chat average (10,701 input / 446 output per turn).

An L3 call is much smaller than either: ~6 bucket definitions + ~11 CSI rulings + 4 neighbour
examples + one description ≈ **600–900 input tokens, ~80 output**.

| model | per item | per plan (est. 5 unseen items) | full 4,125-item corpus |
|---|---:|---:|---:|
| Haiku 4.5 | ~$0.0009 | ~$0.005 | ~$3.70 |
| Sonnet 5 | ~$0.0035 | ~$0.018 | ~$14.40 |

**Latency: ~1–2 s per item, but it is off the critical path** — L3 only fires on genuinely unseen
descriptions, and every answer is written back, so the same item never costs twice. A plan with 40
line items where 35 hit L1 costs 5 calls, batchable into one. **These are ESTIMATES**: the token
counts are reasoned from the prompt shape, not measured, because L3 does not exist. The $0.0339
anchor is real; the extrapolation is not.

**Recommendation: Haiku for L3.** This is a constrained classification into 6 buckets with examples
supplied — the easiest possible LLM task — and L4 catches the uncertain ones anyway.

## 5. The round trip: merging Alex's `.docx` answers back into `PROPOSED.csv`

**Current state, measured:** `2026-07-30_material_map_PROPOSED.csv` has 33 rows,
`csi_answer` filled on **0 of 33**, `csi_notes` on 0. Status split: 17 CONFIRMED, 16
NEEDS_CSI_RULING. The file was purpose-built for this round trip and was bypassed — Alex marked up
the `.docx` because that is what he was sent.

**This is the root of the "signed off on a fiction" problem, and it has a second half nobody has
named:** `PROPOSED.csv` is generated from `11_build_material_map.py`'s `FAMILIES`, which is *also*
not what runs. So even a perfectly executed round trip would have recorded CSI's answers against the
wrong artifact. Note the proof, found today: `PROPOSED.csv`'s `cold_milling` row lists
`MILL BITUMINOUS / COLD MILLING / MILLING PAVEMENT / MILL TRANSITION / COLD PLANE / MILL SURFACE`
as its keywords — **the pre-read had the correct milling keywords all along**, while the live
crosswalk had none of them. The document was right and the product was wrong, for five weeks.

**Recommended fix, in order:**

1. **Generate `PROPOSED.csv` from the live mapping**, not from `FAMILIES`. One generator, sourced
   from `quantity_crosswalk.py` + `material_crosswalk.csv` + `bucket_hierarchy.csv`. This makes the
   document a view of production *by construction*, so the drift cannot recur.
2. **Back-fill Alex's 9 rulings into `csi_answer` now**, by hand, with `csi_notes = "from
   2026-08-07 .docx markup"`. It is 9 rows. This reconstructs the audit trail that the `.docx`
   detour destroyed, and it is the evidence base for F3's trust export.
3. **Send the CSV alongside the `.docx` next time**, and treat the `.docx` as the *rendering* of the
   CSV rather than an independent artifact — same relationship the pre-read already has to its
   generator.
4. Retire the hand-authored `FAMILIES` list once (1) lands, or demote it to test fixtures. It is a
   third mapping and there should be one.

## 6. Should `PROPOSED.csv` become a table?

**Yes — but it is the third-most urgent of the three, and the reason matters.**

`material_crosswalk` and `bucket_hierarchy` are already Postgres tables and the code reads neither.
**Promoting a third file to a table nobody reads does not help.** The problem is not storage, it is
that no runtime path consults any of them.

Recommended order:
1. **Wire `bucket_hierarchy` into the code first.** Smallest file (6 rows), biggest correctness win
   (`removal_tons` + deleting `crushing_tons`), and it removes two invented buckets. It should be
   the definition of `CSI_BUCKETS`, not a mirror of it.
2. **Wire `material_crosswalk` as L1**, with the trust tiers from §0.
3. **Then** promote `PROPOSED.csv` — as the CSI-decision-of-record table, keyed by family, with
   `csi_answer`, `csi_notes`, `answered_at`, `answered_by`. At that point it stops being a document
   and becomes the thing L1's `human` tier is populated from, which is the only reason to make it a
   table at all.

## 7. Open questions for T

1. **`match_source='keyword'` provisional-row rule** — do you accept that 681 lookup rows are a
   cache rather than decisions, and should be re-derived on `SPEC_MAP` change? This is the crux; if
   they are treated as authoritative, L1-first makes things worse.
2. **The held-out generalisation test** — do you want it before building, or do we build on the
   100%-on-training-set number and measure after? I would not ship without it.
3. **`removal_tons` for the SY removals** (68,954 SY, no depth on any row) — batch to CSI, or FDR
   treatment (category recorded, quantity homeless, visible)?
4. **`stockpile_tons`** — keep the bucket, or FDR-treat it like I propose in §3?
5. Should I back-fill Alex's 9 rulings into `csi_answer` now, or is that part of the build?

## 8. What this spec does NOT cover

- Any code. Nothing was restructured tonight, per instruction.
- The unseen-item rate on new plans (§2) — unmeasured, and it gates L3 sizing.
- Whether `state` should be part of the L1 key. The table is keyed `(normalized_description, state)`
  and 2,434 rows collapse to 2,290 distinct descriptions, so only 144 rows differ by state — I have
  not checked whether those are real state differences or duplicates.
