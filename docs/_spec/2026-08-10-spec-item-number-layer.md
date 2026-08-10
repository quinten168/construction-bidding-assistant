# Spec — the coded item number beats the keyword heuristic

Date: 2026-08-10 · Status: **spec only, do not build** · Task board P0 #3, second half

## The argument in one paragraph

State bid schedules carry the spec item number on every row: `2211.509 AGGREGATE BASE CLASS 5 (TON)`,
`2104.504 REMOVE BITUMINOUS PAVEMENT (S Y)`. That number is the state's own classification of the
pay item, it keys directly into the spec books now sitting in `05_knowledge/`, and it is stable in a
way a description never is. We have spent this project hand-building a fuzzy keyword classifier to
decide whether `REMOVE AGGREGATE BASE` is base or demolition, and the state answered that question
when it assigned the item a number. **Where the number exists it should win outright and the keyword
heuristic should get no vote.**

Two independent confirmations that the number is available and currently thrown away:

1. `CSI ELP 2026/**/rtv-csv-for-Bid Item List*.csv` — 38 machine-readable bid schedules, item number
   in the `Item` column on every row (`docs/_session/2026-08-08-corpus-findings.md` §1).
2. `05_knowledge/_markup/2026-08-03_material_preread_HANDOFF.md`, "Known weaknesses": *"MnDOT bid
   schedules carry a `Mat No.` column (`2232.504` milling, `2360.509` hot mix, `2215.504` FDR). The
   parser stores line numbers instead (0 of 6,385 rows retain one)."*

So the number is on the page, and our parser drops it. That is the change.

---

## Proposed layer order

```
L0  CODED ITEM NUMBER        deterministic lookup, state-keyed. Wins outright where present.
L1  LLM READ                 the seven schema.py descriptions. Handles freeform descriptions.
L2  KEYWORD HEURISTIC        SPEC_MAP, last resort only, and it must announce itself.
--  never_matched            an explicit terminal state. NOT a zero, NOT a null.
```

Each layer records **which layer answered** on the row. That provenance column is the whole point:
today a number in `base_tons` carries no indication of whether the state said so, a model said so,
or an ordered substring list said so, and those are not the same claim.

### Why the keyword heuristic goes last rather than being deleted

It is the only layer with no dependency and no cost, and it is the fallback when both a number and a
usable description are absent. But it is also where every one of the eight defects on this project
lived. Demoting it to last with a loud terminal state converts it from the primary classifier into
the thing that runs when nothing better is available, which is what it should always have been.

### Why the LLM sits between them and not first

The model reads meaning, so it handles the freeform municipal descriptions L0 cannot. It is also
non-deterministic and unauditable per-row. Where the state has already coded the item, preferring a
model read over the state's own classification is strictly worse and costs money to do.

---

## What this does NOT cover — say it plainly, do not oversell

**Item numbers only appear on state-form bid schedules.** Municipal and consultant-let projects
routinely write freeform descriptions with no number at all. Those go to L1 and the LLM path stays
load-bearing forever. Anyone presenting this as "we replaced the classifier with a lookup" is
overstating it.

The honest framing: **L0 makes the state-let majority deterministic and auditable, and shrinks the
surface the heuristic is trusted on.** The coverage number for L0 is an output of the build, not an
assumption — it is measured, per state, before anyone quotes it.

Second uncovered case: an item number present in the plan but absent from our lookup table. That is
`never_matched` with `reason=unknown_item_number`, and it must be distinguishable from
`reason=no_item_number_on_row`. One is a gap in our table and is fixable; the other is a property of
the document and is not.

---

## Open questions that gate the build

**1. Is the numbering scheme shared across states, or per-state?**
MnDOT uses `2xxx.xxx`. Whether NDDOT and SDDOT use the same scheme, their own, or none is
**UNVERIFIED here** and is being answered by the Tier 1 spec-book sweep
(`docs/_session/2026-08-10-spec-books-tier1.md`, in flight). This decides whether the lookup is one
table or is keyed `(state, item_number)`.

**Design defensively: key on `(state, item_number)` regardless.** If the schemes turn out to be
shared it costs one redundant column; if they collide and we keyed on the number alone, an ND item
would silently resolve to an MN definition. That is the same failure shape as everything else on
this project and it is cheap to prevent.

**2. Where does the number come from at extraction time?**
Two sources, and they are not equivalent:
- The **rtv-csv golden files** — 38 projects, already machine-readable. Free, but historical only.
- The **plan set / QUANITIES.pdf bid schedule** — every project, but the parser currently discards
  the column. This is the parser change and it is the real work.

The lookup table itself is built from the spec books and does not depend on either.

**3. What is the authority when L0 and CSI's rulings disagree?**
CSI's rulings win. `2215.504 FULL DEPTH RECLAMATION` will have a spec definition; CSI has ruled FDR
is base work with the quantity staying in `milling_sy`. The spec book describes what the state pays
for, not which of CSI's buckets a contractor tracks it in. **The ruling layer sits above L0**, which
makes the real order `CSI ruling → L0 → L1 → L2`. Flagged because it is easy to build L0 as the top
layer by accident and quietly overwrite the client's decisions.

**4. 2025 spec books against 2023-24 plans.** Item numbers drift between editions. A number that
resolves under the 2025 book may have meant something else on a 2023 plan. Needs an `edition` column
and a decision on what to do when a plan predates the book. Not blocking, but it must not be
discovered later.

---

## Data shape

`05_knowledge/2026-08-10-spec_item_lookup.csv` (being produced by the Tier 1 sweep):

```
state, item_number, item_name, unit, spec_section, includes, excludes, source_pdf, page
```

Every row carries a page number so a human can check it against the book. No page, no row.

The resolver returns a record, never a bare bucket:

```python
{
  "bucket":       "base_tons" | ... | None,
  "layer":        "csi_ruling" | "L0_item_number" | "L1_llm" | "L2_keyword" | "never_matched",
  "reason":       None | "no_item_number_on_row" | "unknown_item_number" | "no_keyword_match",
  "item_number":  "2211.509" | None,
  "confidence":   ...,
}
```

**`bucket=None` and a raised exception must never be the same thing, and `never_matched` must never
render as zero.** Nine instances of that bug on this project; this is the layer where it would be
cheapest to introduce a tenth.

---

## How it gets proved

Coverage tests, not unit tests, matching the pattern in
`05_knowledge/test_quantity_crosswalk.py`:

1. **Every item number in the lookup table matches at least one real corpus row.** A row that
   matches nothing is either a typo or an item that does not occur; the test forces us to know which.
2. **Every corpus row carrying an item number resolves through L0**, or is explicitly listed as a
   known gap with a reason.
3. **L0 and the keyword heuristic are compared on the rows where both fire.** Every disagreement is
   listed and reviewed by hand. That list is the actual value of this work — it is the set of places
   the heuristic has been quietly wrong.
4. **The 38 golden bid item lists are the measurement**, joined per
   `docs/_spec/2026-08-10-benchmark-table.md`.

## Recommendation on sequencing

Do not start this before Wednesday. The rulings are now in the live mapping and that was the
Wednesday-blocking half. This layer needs the spec-book lookup finished, the parser change to retain
the item-number column, and a corpus re-run — none of which fit before the presentation, and all of
which are cheaper once the benchmark table exists to measure them against.
