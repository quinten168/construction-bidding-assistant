# Advisor Handoff — 2026-08-08

For the next Cowork session acting as T's advisor on the CSI project. Supersedes every earlier version.

---

## Setup

Connect these folders. Folder access is per-session and does not carry over.

1. `/Users/t/dev/csi/csi-bid-intelligence` — code, plus `docs/_session/` and `docs/_spec/`
2. `.../00_CSI_ELP/01_Summer_2026` — plans, knowledge, modules
3. `.../00_CSI_ELP/CSI ELP 2026` — **CSI's own working corpus.** New. This is where the golden datasets are

Then read `docs/_session/HANDOFF.md`, `docs/_session/TASKS.md`, `docs/_session/latest_report.md`.

## Key locations

| Path | What |
|---|---|
| `docs/_session/latest_report.md` | Executor's most recent report. Read it, don't ask T to paste |
| `docs/_spec/` | Specs awaiting T's review |
| `pipelines/plan_reader/01_pipeline/schema.py` | **The live mapping.** Seven prose field descriptions |
| `.../05_knowledge/quantity_crosswalk.py` | SPEC_MAP, 78 keywords. Batch only |
| `05_knowledge/bucket_hierarchy.csv` | Parent buckets, the 1.75 removal factor |
| `05_knowledge/2026-08-08-*specifications*.pdf` | MN, ND, SD spec books, ~3,000 pages |
| `CSI ELP 2026/**/rtv-csv-for-Bid Item List*.csv` | **38 machine-readable bid schedules. The golden dataset** |
| `CSI ELP 2026/**/BID RESULTS*.msg` | 909 bid-result emails, date and time in the filename |
| `CSI ELP 2026/Daily Ads/` | 174 daily bid-advertisement digests |
| `CSI ELP 2026/No Bid/` | 150 projects CSI declined. Negative class |

---

## The working model

Everything funnels through the advisor. T pastes, or the advisor reads `docs/_session/latest_report.md`. Advisor gives a read and drafts the prompt back. T sends it. **The advisor never talks to the executor directly.**

The tasks-deployment doc is *ours*, regenerated each turn and delivered as a file. `docs/_session/` is the executor's memory. Different things.

---

## Where things stand

Two of three project goals are done. Postgres is live, SQLite is out of the runtime, plan-reader output writes to `bid_projects`.

**Scope was deliberately narrowed on Aug 8 evening.** T's call, and it is the right one: core quality, core dependencies, solid data practices, features on the backlog. Five P0s and nothing competes with them. See the tasks doc.

**The finding that still frames the mapping work:** there are four material-mapping artifacts and only one runs. It is seven prose sentences in `schema.py`. Alex's rulings went into the batch layer, not the product. The product is unreviewed, not broken — Walsh 4/4, Dunn 3/3, Stearns milling exact to the square yard.

**The finding that reframes validation:** 38 machine-readable bid item lists already exist in CSI's corpus, with state spec item numbers on every row. Extraction has never been validated against a source document and the plan for doing it was manual transcription. It is now a join. The item numbers also mean we have been hand-building a fuzzy classifier for a field the state already coded.

**Eight defects found, all one shape:** a value obviously right to a human, unrecognised by a matcher, silently returning zero instead of an error. Milling went 542,262 to 3,021,338 SY as a result.

---

## Settled — do not re-litigate

Demote the cache, don't remove it. `removal_tons` at 1.75 Ton/CY. Verb-before-noun rejected as a general rule, narrow form only. No more bulk rewrites of `csi_v2.db`. Vector store local for handoff, hosted only as a disposable bridge deleted Aug 17. Project identity keys on state project number, then `{state}_{county}_{bid_date}`; reverse geocode for display only. Document type is a five-way classification. Estimation checklist export and Notes & Quotes are backlog, not pre-Wednesday.

## Unverified — do not inherit as fact

Whether the Supabase account transfers to CSI after Aug 21. Whether `chromadb` 1.5.9 embeds client-side against a hosted server. Railway's default volume-backup schedule. The estimator-hours figure, which T is asking CSI and nobody should invent. Whether the Advertisement for Bids page survives into Chroma as a chunk.

---

## Method

Spec before code for anything with a decision in it. T grills the spec. TDD at the seams. **Coverage tests over unit tests** — 36 passing unit tests missed two keywords matching the wrong thing. Adversarial verification on absence claims: "X does not exist" needs two methods, both named.

**Every file gets a `YYYY-MM-DD` prefix.** No exceptions.

**The standing rule, earned nine times: never let a failure and a legitimate empty answer share a return value.**

Suggest parallel subagents where work is genuinely independent. Research sweeps over the corpus are the obvious case.

---

## Style

No em dashes. Direct and casual. Recommendations, not menus. He uses voice-to-text so messages garble, read through it. Jargon explained plainly.

He is right often enough that pushback deserves real consideration. He corrected the advisor on the Box blocker, on hosting, on the strategy for historical rows, and on scope discipline for this final week. When he says something is a feature and not a foundation, he is usually right about that too.

He also asks to be tested with before things get built. Give the read, get agreement, then produce.

---

## Watch for

The executor is excellent and has been confidently wrong several times, always by asserting something does not exist from a partial view. It self-corrects well and reports honestly. Trust it, verify absence claims.

Watch the advisor's own version of the same failure. Several corrections in this project came from T pointing at a file and the advisor discovering its own claim was stale.

And watch scope. This project's characteristic failure is a session producing excellent analysis and no software. The bar is working code on main that the team can run.
