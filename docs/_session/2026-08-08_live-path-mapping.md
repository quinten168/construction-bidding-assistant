# Session report 6 — 2026-08-08 · how a newly dropped plan actually gets bucketed

Answers the owner's 🔴 stop question. **You were right and I was wrong** about what the crosswalk fixes
are worth.

---

## 1. The answer: seven prose sentences

A newly dropped plan's quantities come from **Claude being asked for the seven bucket totals
directly**, and the entire mapping is the field descriptions in
`pipelines/plan_reader/01_pipeline/schema.py`:

| field | the complete mapping rule |
|---|---|
| `hot_mix_tons` | *"Total tons of hot mix asphalt (HMA) from the bid schedule."* |
| `base_tons` | *"Total tons of aggregate/granular base material."* |
| `grading_quantity` | *"Total cubic yards of grading / earthwork."* |
| `shoulder_tons` | *"Total tons of shoulder gravel/aggregate."* |
| `milling_sy` | *"Total square yards of milling / **pavement removal**."* |
| `crushing_tons` | *"Total tons of crushed aggregate to be produced."* |
| `stockpile_tons` | *"Total tons of stockpile material."* |

`s3_extract.py:52` adds the only other instruction: *"Sum the bid-schedule line items if needed."*

**That is the fourth mapping artifact**, alongside `SPEC_MAP` (78 keywords),
`material_crosswalk.csv` (2,434 rows), and `11_build_material_map.py`'s `FAMILIES`. It is the only
one that runs for the demo, and it is the only one nobody knew was a mapping.

**Is the crosswalk reachable from ANY live path? No — batch only.** Its importers are
`05_parse_bid_schedule.py`, `10_remap_buckets.py`, `09_build_material_crosswalk.py`,
`12_build_material_preread.py`, and its test. Confirmed earlier three ways including a runtime
`sys.modules` check.

## 2. Your reframe is correct

I called the crosswalk "a code deliverable whose value is on new plans." **That was wrong.** New plans
do not touch it. Today's four fixes correct the *archive*, and the archive has no confirmed reader.

The crosswalk is not worthless — it is the only artifact where CSI's rulings are written down, and it
is what a benchmark would measure against. But its value is **latent until the live path uses it**,
and that is now the highest-leverage change on the board.

## 3. Does the live path have its own version of the six defects?

Checked the three you named. The answer differs by defect, and two of them are genuinely **better**.

| defect class | live LLM path | why |
|---|---|---|
| **non-breaking space** (`Mill\xa0Bituminous`) | **not susceptible** | there is no matcher to fail. An LLM reads `\xa0` as a space. This whole class exists only where a substring comparison decides. |
| **unit spelling** (`Square Yard` → dropped) | **not susceptible in the same way** | the model is asked for "total square yards" and does the unit reasoning itself. Different risk: a silent *wrong* conversion instead of a silent zero — wrong beats missing for visibility, but is harder to detect. |
| **removal landing in a placed bucket** | ⚠️ **STRUCTURALLY POSSIBLE AND UNTESTED** | `base_tons` is defined as *"Total tons of aggregate/granular base material"* — **no "placed" qualifier**. Nothing in the prompt tells the model that `REMOVE AGGREGATE BASE` (208,440 TON corpus-wide) is demolition. The crosswalk had exactly this bug for months. |

And a fourth, which you did not ask about but is larger:

**None of CSI's 2026-08-07 rulings are encoded in the live path.** Not one. The prompt has no
knowledge that Portland Cement is excluded, that Cement Stabilized Subgrade is excluded, that
driveway removals are excluded, that Gravel Surfacing moved to base, or that FDR is base work. Alex's
markup changed the batch tooling and left the product untouched.

Worse, the prompt contains a mapping decision that **contradicts** the other artifacts:
`milling_sy` = *"milling / pavement removal"* folds removal into milling, while
`bucket_hierarchy.csv` routes removal to GRADING at 1.75 Ton/CY and Mark's rule says grading. Three
artifacts, three answers, and the one that ships was never reviewed.

## 4. Which numbers does the demo show? The LLM's — and they are mostly good

Measured across every cached payload that matches a corpus plan:

| plan | bucket | LLM (demo) | crosswalk | note |
|---|---|---:|---:|---|
| `2023_WALSH-CO-ND_8376434` | MIX / BASE / GRADE / MILL | 33,869 / 2,671 / 1,643 / 154,218 | identical | **4/4 exact** |
| `2023_DUNN-CO-ND_CP-13` | MIX / BASE / MILL | 40,877 / 19,689 / 51,929 | identical | **3/3 exact** |
| `2025_SHERBURNE-CO-MN_9747843` | MILL | 31,500 | 34,500 | LLM 3,000 short |
| `2025_SHERBURNE-CO-MN_9747843` | GRADE | — | 100 | LLM missed |
| `2025_KANDIYOHI-CO-MN_9749930` | BASE / GRADE | 313 / 389 | — / — | **LLM found what the crosswalk missed** |

Plus the Stearns case from earlier: LLM `MILL = 70,263`, which is the three `MILL BITUMINOUS` lines
to the square yard, correctly excluding FDR.

**Read honestly: the live path is broadly accurate and occasionally better than the crosswalk.** It
is not obviously broken. But it is unreviewed, its mapping is undocumented, it encodes none of the
client's decisions, and it has one structural hole nobody has tested.

## 5. Wednesday's real risk, stated plainly

Not the historical rows. **The demo runs on a mapping that has never been reviewed, and CSI's own
rulings are not in it.** If Alex asks on Wednesday "did you apply what I sent back?", the honest
answer today is *"to the analysis, yes; to the thing on screen, no."*

**The one test I would run before Wednesday** (cannot be answered from cache — no cached payload
overlaps a plan containing `REMOVE AGGREGATE BASE`): drop `2026_DUNN-CO-ND_JOB-23388` or
`2026_BURKE-WARD-CO-ND_JOB-22484` through the live path and check whether its 72,153 / 129,500 TON of
`REMOVE AGGREGATE BASE` lands in `base_tons`. That is one PDF, ~$0.20, and it either confirms the
live path is clean or finds the seventh defect.

## 6. What this changes about the plan

- **The archive strategy stands** — unchanged, and better supported. Nothing reads the historical
  rows.
- **The crosswalk's value is latent.** Making the live path use it (or porting the rulings into the
  prompt) is now the highest-leverage change, and it is what the mapping spec's L1/L2/L3 design is
  for. Not tonight.
- **F2 four-state is confirmed out of reach tonight**, for exactly this reason: the gap states are
  computed in code the live path never calls. Two-state is the right call.
- **The extraction schema is a mapping artifact**, so schema v2 should treat those seven descriptions
  as a reviewable mapping and not as prose.

## 7. Open

1. Run the one `REMOVE AGGREGATE BASE` drop before Wednesday?
2. Port CSI's 11 rulings into the extraction prompt as a stopgap, or wait for the L1/L2/L3 work?
   A stopgap is a fifth place the mapping lives, which is how we got here.
