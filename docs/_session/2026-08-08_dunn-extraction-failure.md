# Session report 7 — 2026-08-08 · the live path missed 121,221 tons of asphalt

Resolves the Dunn mix/milling gap by going to the source, as instructed. **This is the most serious
finding of the session and it is on the demo path.**

---

## Ground truth, from the bid schedule in the PDF

`2026_DUNN-CO-ND_JOB-23388` (NDDOT Job 23388, PCN-23388), proposal form pages 8 of 17:

| item | spec | unit | quantity |
|---|---|---|---:|
| **RAP - SUPERPAVE FAA 43** | 430-0143 | TON | **121,221** |
| **MILLING PAVEMENT SURFACE** | 411-0100 | TON | **63,092** |
| FULL DEPTH RECLAMATION | — | SY | 408,216 |
| PATCHING | 430-2000 | TON | 200 |
| REMOVE AGGREGATE BASE | — | TON | 72,153 |
| AGGREGATE BASE COURSE CL 5 | — | TON | 6,506 |

## The three-way comparison

| bucket | **source** | live LLM (demo) | crosswalk |
|---|---:|---:|---:|
| hot mix | **121,221 t** | **200 t** ❌ | 121,221 t ✅ |
| milling | **63,092 t** | *absent* | 408,216 SY (= FDR, not milling) |
| base | **6,506 t** | 6,506 t ✅ | 7,326 t |
| grading | — | 33,138 CY | 32,690 CY |

### The headline: the live path reported 200 tons of asphalt on a 121,221-ton job — off by 605×

It picked up `PATCHING | TON | 200` and **missed `RAP - SUPERPAVE FAA 43 | TON | 121,221` entirely.**
On the path the demo runs.

### Truncation was NOT the cause — hypothesis tested and rejected

`s3_extract` truncates to 180,000 chars (first 108,000 + last 72,000) of a 1,143,615-char document,
discarding the middle 963,615. That looked like the obvious culprit. It is not:

```
'RAP - SUPERPAVE FAA 43'    at offset  86,309  (7.5% in)  -> SENT to Claude
'MILLING PAVEMENT SURFACE'  at offset  86,229  (7.5% in)  -> SENT to Claude
```

Both were well inside the head window. **Claude saw the line and did not classify it as hot mix.**

### Most likely cause: a vocabulary gap in the seven-sentence prose mapping

`schema.py` asks for *"Total tons of hot mix asphalt (**HMA**) from the bid schedule."* NDDOT does not
write "HMA" or "hot mix" — it writes **`RAP - SUPERPAVE FAA 43`**. The model was asked for HMA, shown
Superpave, and returned the one line that did look like asphalt tonnage (`PATCHING`).

**This is exactly the state-vocabulary problem the spec books were just added to solve** — MN writes
BITUMINOUS, SD writes ASPHALT CONCRETE, ND writes SUPERPAVE. `SPEC_MAP` hand-orders around it and has
a `SUPERPAVE` keyword, which is why the crosswalk got this right and the prose mapping did not.

**UNVERIFIED:** this is the most plausible mechanism, not a proven one. Confirming it means one more
call with "SUPERPAVE" added to the field description and seeing whether 121,221 appears. That is the
cheapest possible next experiment and it should run before Wednesday.

### The milling absence is arguably CORRECT behaviour

`milling_sy` asks for *"Total **square yards** of milling."* The plan states milling in **TONS**
(63,092). The model declined to put tons into a square-yard field. That is the honest answer, and it
is open question #2 from the July pre-read — *"NDDOT measures milling in TONS while MN/SD measure SY.
Your MILL SY column cannot hold the ND tons."* The field name bakes in a unit the plan does not use.

The crosswalk's 408,216 is **not milling** — it is Full Depth Reclamation, routed to `milling_sy` by
Alex's ruling (category `base`, quantity stays where measurable). The crosswalk also drops the 63,092
TON of real milling, as `no_bucket_for_unit`. **So neither pipeline reports this plan's actual
milling.** Both are wrong, differently.

## What this changes

1. **Wednesday's risk is now specific and large.** A demo on an ND plan can under-report asphalt by
   orders of magnitude. Of CSI's bidding, **ND is 35.8%**.
2. **The crosswalk beat the LLM on the number that matters most here** — reversing the earlier
   read from Stearns/Walsh/Dunn-CP-13, where they agreed or the LLM was better. The two pipelines
   agree on easy plans and diverge on hard ones, which is the worst possible failure shape.
3. **The seven prose sentences are the highest-leverage thing to fix in the whole system.** They are
   ~40 words, they are the live mapping, and they encode neither CSI's rulings nor three states'
   vocabulary. Adding state vocabulary to them is hours, not days.
4. It strengthens the spec-book Tier 1 ticket: the books give the naming crosswalk directly.

## Recommended before Wednesday, in order

1. Add state vocabulary to the seven field descriptions (SUPERPAVE / ASPHALT CONCRETE / BITUMINOUS /
   RAP), re-drop Dunn, confirm 121,221 appears. ~1 hour, one API call to verify.
2. Decide what `milling_sy` does with ND tons — it is a real open question, not a bug.
3. Do not demo an ND plan until 1 is done.

## Side effects of this test, recorded

- The run wrote **558 chunks into Chroma under `doc_id = "Job 23388 Request for Proposal"`** — a
  stem-keyed id with blank provenance. Issue **#58** reproducing live from a single drop.
- No payload cache was written (`process_pdf` does not write it; only `apply_verification` does).
- **`.env`'s `ANTHROPIC_API_KEY` is a 10-character placeholder** (`sk-ant-...`). The first attempt
  died on a 401; the working key exists only in the shell environment. A fresh machine following the
  README gets a 401.
