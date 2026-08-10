# Spec — the phasing gotcha and the key-date shape

Status: **proposed**, 2026-08-10. Board item P0 #5.
Owner of this spec: key-dates/phasing agent. `schema.py` edits are applied by the main session
(see §7 — exact text supplied, not applied here).

---

## 1. The decision this spec exists to settle

The board says phasing is "currently invisible to us." It is not literally absent — there is a
`phasing_requirements` field, a `phasing_staging` taxonomy code, and a `plan_metrics.has_phasing`
column. What is absent is **a shape an estimator can act on**.

The pattern that costs money is: *the project runs, then breaks, then the crew comes back weeks or
months later to finish.* Six weeks is typical; in this corpus the real instances are **overwinter**
— eight or nine months. The estimator prices a remobilization, a second setup, a second traffic
control mobilization, and the carrying cost of an open contract.

What we produce today for that case is either the string `null` or a paragraph of scheduling
boilerplate (§3). `has_phasing = 1` on 57 of 100 plans is not information; it is noise at a 57%
base rate.

**Decision: phasing is emitted as a structured, cited, interval-bearing object with an explicit
three-valued status. Never a boolean. Never a bare prose blob.**

---

## 2. Three distinct things that all currently collapse into "phasing"

Grounded in corpus evidence (`docs/_session/2026-08-10-key-dates-phasing.md` §4).

| Pattern | What it is | Estimator cost | Corpus example |
|---|---|---|---|
| **`break_and_resume`** | Work stops and restarts across a gap — overwinter, or gated on another contract/ROW. | **Remobilization.** This is the one that matters. | `2025_MURRAY-CO-MN_CSAH-2`: wear course "shall not be placed until the following construction season" |
| `sequenced_within_season` | Mandated order of operations inside one continuous mobilization. | Minor — crew sequencing, no second setup. | `2025_HAND-CO-SD_08MQ`: numbered sequence of operations |
| `staged_traffic` | Phase/stage limits drawn on the plan for traffic handling. | Traffic control cost, not remobilization. | `2025_JACKSON-CO-MN_SAP-032`: PHASE 1 / PHASE 2 construction limits |

Today all three land as `phasing_staging` and set `has_phasing = 1`. Collapsing them is why the
flag carries no signal. **The three are separate `pattern` values and only `break_and_resume` is a
pricing-relevant gotcha by default.**

---

## 3. Why the current field does not produce this (evidence, not inference)

`2023_WATONWAN-CO-MN_SP-8303-48` is the corpus's clearest break-and-resume: proposal cover page 1
reads `Starting Date: 7/10/2023  Completion Date: 6/1/2024` and, on the same line,
`This Contract Contains Intermediate Completion Dates`. The contract spans a winter.

Our extracted `phasing_requirements` for that plan is:

> "The contract requires work to be organized into defined phases and stages within the Work
> Breakdown Structure (WBS). The WBS includes Level 2: Construction, Level 3: Phase TBD, and
> Level 4: Stage TBD nodes…"

That is MnDOT's **schedule-software** provision. Retrieval matched the word "phase" in a section
about Primavera WBS coding and returned it as the project's phasing. The actual signal was on
page 1 in two date cells the whole-doc extractor already reads correctly.

**Conclusion the design rests on: the strongest break-and-resume signal in this corpus is
arithmetic on two fields we already fill, not a retrieval result.** Retrieval supplies the
narrative and the citation; it does not supply the detection.

---

## 4. Output shape

### 4.1 `DateExpr` — the unit every date is carried in

Applies to every key date (start, substantial, final, interim, phase boundaries). Solves the
"relative expressions must survive as written" requirement and the standing rule about failures
and empty answers sharing a value.

```json
{
  "raw":               "within thirty (30) calendar days of substantial completion",
  "kind":              "calendar" | "relative" | "duration" | "unparsed",
  "resolved":          "2026-05-15" | null,
  "anchor":            "substantial_completion" | "notice_to_proceed" | null,
  "offset_days":       30,
  "offset_basis":      "calendar" | "working" | null,
  "resolution_status": "resolved" | "unresolved_anchor_missing" | "unresolved_not_a_date" | "absent",
  "page":              47,
  "confidence":        "high" | "medium" | "low"
}
```

Rules, all load-bearing:

1. **`raw` is never discarded.** A relative expression is stored verbatim and `kind = "relative"`.
   It is never coerced to `null` and never to a guessed calendar date.
2. `resolved` is populated **only** when an anchor date is itself known. Otherwise it is `null`
   **and `resolution_status` says which kind of null it is.** `"absent"` (the plan does not state
   it) and `"unresolved_anchor_missing"` (the plan states it, we could not compute it) are
   different values and must render differently. This is standing-rule instance #10.
3. A working-day count is `kind = "duration"`, `offset_basis = "working"`, `resolved = null`. We do
   not own a state holiday calendar; guessing one is exactly the failure this project keeps making.
4. `"unparsed"` means the extractor returned text it could not classify — visible, not silent.

### 4.2 `schedule_phasing` — the gotcha object

```json
{
  "status": "detected" | "none_found" | "extraction_failed",
  "pattern": "break_and_resume" | "sequenced_within_season" | "staged_traffic" | null,
  "signals": ["multi_season_span", "intermediate_completion_declared"],
  "segments": [
    {"label": "Phase 1", "start": <DateExpr>, "end": <DateExpr>, "page": 34, "quote": "…"},
    {"label": "Phase 2", "start": <DateExpr>, "end": <DateExpr>, "page": 34, "quote": "…"}
  ],
  "break": {
    "after":            <DateExpr>,
    "resumes":          <DateExpr>,
    "interval_days":    195,
    "interval_stated":  "the following construction season",
    "interval_source":  "computed" | "stated" | null,
    "page":             34
  },
  "evidence": [{"quote": "…", "page": 34, "signal": "wear_course_next_season"}],
  "confidence": "high" | "medium" | "low",
  "summary": "Phase 1 complete by 2025-11-01; Phase 2 begins 2026-05-15 (≈195 day break). Plan set p.34."
}
```

Rules:

1. **`status` is three-valued and is the only field a consumer may branch on for presence.**
   `none_found` means we looked and the plan has no phasing. `extraction_failed` means retrieval or
   the LLM call errored, or returned unparseable output. **These must never share a value**, and
   `extraction_failed` must never be rendered to an estimator as "no phasing."
2. **`status = "detected"` requires at least one entry in `evidence` with a non-null `page`.**
   A detection with no citation is not shippable — an estimator cannot verify it. If a signal fires
   but no citation can be attached, the object is `detected` with `confidence = "low"` and the
   signal named; it is never emitted as a bare true.
3. `interval_days` is populated when both ends are `resolved`; `interval_stated` carries the plan's
   own words ("the following construction season") whenever they exist, **and both may be present.**
   `interval_source` says which one the number came from. Where neither exists, both are `null` and
   `pattern` still stands on the signal — a stated break with no stated interval is still a break.
4. `summary` is the one line that reaches the report. It must name a date or an interval and a page.
   It is generated from the structure, not by an LLM, so it cannot disagree with the fields.

### 4.3 Relationship to the existing surfaces — additive, nothing deleted

- `phasing_requirements` (prose) **stays** and stays as-is. It becomes the narrative slot; the new
  object is the actionable one. Deleting it would lose the only phrasing an estimator can read.
- `taxonomy.py`'s `phasing_staging` code **stays** with its current definition. Two new sibling
  codes are proposed in §7.3 so the three patterns of §2 stop colliding.
- `plan_metrics.has_phasing` **stays** (it is written by two batch tools). It is redefined in
  documentation as "any of the three patterns", i.e. explicitly *not* the pricing signal.

---

## 5. Detection — layered, cheapest and most deterministic first

Layer order is deliberate: the deterministic layers are the ones that fire on Watonwan, where
retrieval failed.

| # | Layer | Signal | Cost | Fires on (corpus) |
|---|---|---|---|---|
| 1 | **Multi-season span** | `construction_start` and `construction_end` resolve to dates in different construction seasons (end month ≤ 6 of a later year, or span crosses a Dec 1 – Mar 31 window) | free — arithmetic on two fields already filled | Watonwan SP-8303-48 (7/10/23→6/1/24); Watonwan WATLINE-TRAIL (9/15/25→6/15/26) |
| 2 | **Declared interim completion** | literal `This Contract Contains Intermediate Completion Dates` (MnDOT proposal cover) | free — regex on page 1 | 2 plans |
| 3 | **Overwinter-work phrases** | `following/next construction season`, `freeze thaw cycle` + `wear course`, `left unpaved over a winter` | free — regex over sections | Murray CSAH-2 |
| 4 | **Gated start** | `Notice to Proceed will not be issued prior to <date>`, `not … available until <date>` | free — regex | Brookings (×2 plans) |
| 5 | **Retrieval + LLM** | the existing `phasing_requirements` query, re-prompted for the §4.2 shape | ~1 Claude call | narrative + citations |

Layers 1–4 set `pattern` and `signals`. Layer 5 supplies `segments`, `quote`s, and `interval_stated`.
**A layer-1 hit with no layer-5 narrative is still `status = "detected"`** — the dates are the
evidence and page 1 is the citation.

### 5.1 Boilerplate exclusion is mandatory, and it is measured

Naive keywords are overwhelmingly boilerplate in this corpus. Measured on 37,261 sections:

- `intermediate completion` → 72 matches across 40 plans, of which the large majority are the
  **EJCDC definition** ("*Milestone* —A principal event … by an intermediate completion date").
- `suspension of work` → 315 matches / 57 plans, dominated by **EJCDC Article 16**.
- `carryover` → 40 matches / 11 plans, all **FHWA on-the-job-training** trainee carryover.
- `suspend operations for the winter` → 15 plans, all the identical **MnDOT 1803.4** sentence.

Every one of those is a contract-form clause that says nothing about *this* project. The detector
therefore carries an explicit deny-list of boilerplate fingerprints, and layer 3/4 phrases must
co-occur with a project-specific token (a date, a station, a route, or a named work item) to count.

**The deny-list is a coverage-tested artifact, not a comment:** a test asserts each denied phrase
still appears in the corpus (so a dead entry is caught) and that the detector returns
`none_found` on the plans where only boilerplate matched.

---

## 6. Tests — coverage, not units

Per the working rule, the tests that matter are the ones that fail when the extractor stops
matching real plans.

1. **`test_multi_season_detector_fires_on_known_plans`** — asserts `break_and_resume` on
   `2023_WATONWAN-CO-MN_SP-8303-48` (7/10/23→6/1/24) and `2025_WATONWAN-CO-MN_WATLINE-TRAIL`
   (9/15/25→6/15/26). Fails loudly if the detector matches zero plans.
2. **`test_overwinter_phrases_match_real_corpus_text`** — every phrase pattern must match at least
   one real section in `csi_v2.db`. A pattern matching nothing is a dead pattern and fails.
3. **`test_boilerplate_is_not_detected`** — the EJCDC/FHWA/MnDOT-1803.4 fingerprints of §5.1 must
   produce `none_found`, not `detected`.
4. **`test_relative_expression_survives_verbatim`** — `"within thirty (30) calendar days of
   substantial completion"` (real, `2b2438a4eaaa0e79` p.47) round-trips with `raw` intact,
   `kind = "relative"`, `resolved = null`, `resolution_status = "unresolved_anchor_missing"`.
5. **`test_failure_and_empty_do_not_share_a_value`** — a raising retrieval yields
   `extraction_failed`; a clean empty plan yields `none_found`. Asserted to be `!=`.

---

## 7. Exact text for the main session to apply (`schema.py` — not applied here)

### 7.1 Replace the `phasing_requirements` description

Current:

```
    _f("phasing_requirements", "str", "rag",
       "Whether work must be built in defined phases/stages and a short summary of the sequence; null if none.",
       golden=None, evalkind=None, group="constraints"),
```

Proposed:

```
    _f("phasing_requirements", "str", "rag",
       "The PROJECT'S OWN phasing/staging requirement: whether the work must be built in defined "
       "phases or stages, and a short summary of the sequence, quoting the plan's words. Include any "
       "stated break between phases (e.g. 'wear course not placed until the following construction "
       "season', 'Phase 2 shall not begin until Phase 1 is complete') and the stated interval if one "
       "is given. IGNORE contract-form boilerplate that defines phasing without imposing it — "
       "schedule-software / Work Breakdown Structure provisions, EJCDC 'Milestone' definitions, "
       "EJCDC Article 16 'Owner May Suspend Work', and MnDOT 1803.4 'Temporary Suspensions' are NOT "
       "project phasing. Null if the plan states none.",
       golden=None, evalkind=None, group="constraints"),
```

### 7.2 Replace the `construction_start` description

Current text says only "Required/earliest construction start date or notice-to-proceed
(YYYY-MM-DD if given)". It fills at 3/8 in the corpus and 4/12 live, and it silently drops relative
expressions, which the board calls out explicitly.

```
    _f("construction_start", "date", "extract",
       "Required or earliest construction start date / notice-to-proceed. Prefer YYYY-MM-DD when the "
       "plan states a calendar date. If the plan expresses it RELATIVE to something else (e.g. 'within "
       "10 days of Notice to Proceed', 'on or after September 15th', 'not issued prior to August 1, "
       "2023'), return the expression EXACTLY AS WRITTEN rather than null and rather than a guessed "
       "date. Usually in the agreement near the front or on the MnDOT proposal cover 'Starting Date'.",
       golden=None, evalkind=None, group="constraints"),
```

### 7.3 Add two interim/phase-date fields (new, `rag`)

```
    _f("interim_completion_dates", "str", "rag",
       "Any INTERIM / intermediate / milestone completion dates the contract imposes short of final "
       "completion — including phase or stage deadlines. Return every one as written, semicolon-"
       "separated, each with the phase or work it applies to (e.g. 'Phase 1 grading complete by "
       "2025-11-01; wear course by 2026-06-15'). MnDOT proposal covers declare their presence with "
       "the literal line 'This Contract Contains Intermediate Completion Dates' — when that line is "
       "present, the dates themselves are elsewhere in the proposal, so keep looking. Null if none.",
       golden=None, evalkind=None, group="constraints", doc="either"),
    _f("phase_break_interval", "str", "rag",
       "If the work stops and later resumes (a phase gap — most often overwinter), the plan's OWN "
       "words for the gap and its length (e.g. 'the following construction season', 'not before "
       "August 1, 2023', 'six weeks after Phase 1'). Return as written. This is the remobilization "
       "signal, so do NOT return generic suspension boilerplate here. Null if work is continuous.",
       golden=None, evalkind=None, group="constraints", doc="either"),
```

### 7.4 Add the phasing gotcha to `FLAG_FIELD_FAMILY` and `flag_rows`

In `FLAG_FIELD_FAMILY`, add:

```
    "phase_break_interval": "Schedule & sequencing",
    "interim_completion_dates": "Schedule & sequencing",
```

and in `flag_rows`, extend the field-flag loop:

```
    for fname in ("traffic_level", "phasing_requirements",
                  "interim_completion_dates", "phase_break_interval"):
```

### 7.5 `taxonomy.py` — split the collided code (this agent's file, applied here)

`phasing_staging` keeps its definition. Two siblings are added so §2's three patterns stop sharing
one code:

- **`phase_break_remobilization`** — "Work stops and resumes after a gap (most often overwinter or
  gated on another contract), requiring the contractor to demobilize and remobilize." Triggers:
  `following construction season`, `freeze thaw cycle`, `left unpaved over a winter`,
  `Notice to Proceed will not be issued prior to`, `This Contract Contains Intermediate Completion
  Dates`, a construction span crossing a winter. Relevance: **decision_driver**.
- **`interim_milestone_dates`** — "Contract imposes intermediate completion dates short of final
  completion." Relevance: decision_driver.

---

## 8. Where this meets the other two agents

- **Task 4 (bid date), other owner.** `bid_deadline` stays entirely theirs. This spec reads it and
  never writes it. The seam is `DateExpr` (§4.1): if their parser emits `{raw, kind, resolved,
  resolution_status}` for `bid_deadline`, every key date on the report shares one shape and one
  null-vs-failure convention. If they emit a bare string, this spec still works — the phasing
  detector does not depend on `bid_deadline` at all. **No file is edited by both.**
- **Main session (`schema.py`).** §7.1–7.4 is the entire ask. Nothing here edits that file.

---

## 9. Open, needs a human

1. Is a **six-week** in-season break priced differently from an **overwinter** break, or is it the
   same remobilization line? The board says six weeks is typical; the corpus's real instances are
   overwinter. Ask Alex. Until answered, both are `break_and_resume` and the interval is reported
   so the estimator can tell them apart himself.
2. Confidence thresholds are undefined project-wide (board, "Confidence levels — open"). This spec
   inherits whatever that resolves to and does not invent one.
