# HANDOFF — read this first

Last updated: **2026-08-08**, end of the 2026-08-07 night session.
A fresh executor session starts here, then reads `TASKS.md` for the board.

Hard dates: **final presentation Wed Aug 12** · **handoff to CSI IT (Shane) Mon Aug 17** ·
**program ends Fri Aug 21**.

---

## 1. The one thing to know before Wednesday

**The live PDF-drop path under-reported asphalt by 605× on a real ND plan.**

On `2026_DUNN-CO-ND_JOB-23388` the bid schedule states `RAP - SUPERPAVE FAA 43 | TON | 121,221`.
The live path returned **200 tons** — it picked up `PATCHING | TON | 200` and missed the Superpave
line. Truncation was tested and ruled out (the line sits 7.5% into the document, inside the window
sent to Claude).

Most likely cause, **UNVERIFIED**: the live mapping asks for *"Total tons of hot mix asphalt
(**HMA**)"*, and NDDOT writes `SUPERPAVE`, not HMA. **ND is 35.8% of CSI's bidding.**

**Do not demo an ND plan until this is checked.** The fix is ~1 hour: add state vocabulary to seven
field descriptions and re-drop Dunn to confirm 121,221 appears. Full detail:
`docs/_session/2026-08-08_dunn-extraction-failure.md`.

## 2. The structural fact that explains most confusion in this repo

**There are TWO quantity pipelines and they have never shared a mapping.**

| | BATCH / corpus | LIVE / PDF drop (what the demo shows) |
|---|---|---|
| how quantities are derived | `05_parse_bid_schedule.py` → `05_knowledge/quantity_crosswalk.py` | **Claude is asked for the seven totals directly** |
| the mapping is | 78 ordered keywords + CSI's rulings | **seven prose sentences** in `01_pipeline/schema.py` field descriptions |
| lands in | `materials` → `plan_metrics` → `public.*` | payload cache → the report |

Verified three ways that the live path never loads `quantity_crosswalk.py` (grep of all six files in
the path; reverse-grep of importers; runtime `sys.modules` check after importing `report.py`).

**Consequence: fixing the crosswalk does not change what a customer sees.** All of 2026-08-07's
crosswalk work corrected the *archive*. Valuable — it is where CSI's rulings are written down and
what a benchmark measures against — but latent until the live path uses it.

**There are actually FOUR mapping artifacts**: `SPEC_MAP` (78 keywords, runs for batch),
`material_crosswalk.csv` (2,434 rows, **read by nothing at runtime**), `11_build_material_map.py`'s
`FAMILIES` (generates the CSI pre-read), and `schema.py`'s seven sentences (runs for the demo).
Alex marked up a document generated from the third. The design to converge them is
`docs/_spec/mapping_architecture.md`.

## 3. What changed on 2026-08-07 (all committed and pushed)

Four defects in `quantity_crosswalk.py`, all with one signature — **a matcher not recognising a value
and returning nothing, so a failure and a legitimate empty answer were indistinguishable**:

1. keyword `RECLAIM` never matched `FULL DEPTH RECLAMATION` (diverge at position 6) — 1.2M SY at zero
2. `MILL BITUMINOUS SURFACE` matched `BITUMINOUS`→hma first — the original Stearns bug, recorded as
   fixed on 2026-07-30 but fixed only in the *pre-read generator*, never in the file that runs
3. `spec_category`/`_csi_ruling` used bare `.upper()` while everything else normalises — 115 corpus
   rows carry `\xa0`, silently bypassing five of CSI's rulings incl. 168,834 SY
4. `_normalize_unit` did not recognise spelled-out `Square Yard` — another 179,016 SY dropped

Corpus effect: **`milling_sy` 542,262 → 3,021,338 (5.6×)**; `base_tons` 1,008,322 → 832,381
(demolition that was being counted as purchased aggregate).

Also added: CSI's 2026-08-07 rulings as an explicit override layer; `csi_category` (what kind of work,
unit-independent — what CSI rules on) separated from `csi_bucket` (which total, still unit-guarded),
deliberately allowed to disagree so FDR can be *base work* whose quantity stays in `milling_sy`;
`bucket_gap_reason` with four states; and **coverage tests** (92 passing) that assert every keyword
matches a real corpus row and that no removal can reach a placed-material bucket.

## 4. State of the stores

| store | state |
|---|---|
| `csi_v2.db` (SQLite, 167 MB, symlink→iCloud) | remapped, `crosswalk_version=2` on all 6,385 rows. Backup: `/Users/t/Desktop/csi_v2_backup_2026-08-07.db` (integrity ok, row counts verified) |
| Supabase `public.*` | **republished 2026-08-08, zero divergence** from SQLite on all six buckets. `csi_reader` SELECT verified via `has_table_privilege` |
| Supabase `scratch.bid_projects` | 1,598 rows; 11 from `plan_reader`. **Fed by the LLM path via `_QMAP`, not the crosswalk** |
| Chroma `06_chroma/` (1.6 GB, 75,080 chunks) | one laptop. ~42% duplicated (#58), ~15% noise (#85) |

**No more bulk rewrites of `csi_v2.db`** (owner decision 2026-08-08). Historical rows are an archive
with a version stamp; nothing reads them. Validation moves to a benchmark table.

## 5. Traps that have each cost real time

- **A clean `--dry-run` is evidence about the numbers, not about the SQL.** `10_remap_buckets.py
  --dry-run` passed and the real run died instantly on `no such column`. The dry run skips the write.
- **`information_schema.role_table_grants` lies** — it only shows grants visible to the querying role.
  Use `pg_class.relacl` or `has_table_privilege`.
- **`is_noise(description, unit)` returns a TUPLE**, not a bool. `if is_noise(...)` is always true and
  silently filters your entire corpus.
- **`.env`'s `ANTHROPIC_API_KEY` is a 10-char placeholder.** The real key is only in the shell. A
  fresh machine following the README gets a 401.
- **Two `00_input` directories** — the runtime resolves to the one with 1 PDF. See **#88**, a handoff
  blocker.
- **`publish_to_supabase` requires the `postgres` role**, not `csi_team`. That guard is correct: it is
  what keeps `csi_reader`'s grants alive across drop-and-recreate.
- Reports read **gotchas from Postgres** but **quantities from the payload cache**. A republish
  changes the first and not the second.

## 6. Where things live

| | |
|---|---|
| session reports | `docs/_session/` — `latest_report.md` is always current (the faculty advisor reads it directly); dated slug files are the permanent record |
| the board | `docs/_session/TASKS.md` |
| open issues, offline-readable | `docs/_session/issues.md` (53 issues, triaged) |
| specs awaiting approval | `docs/_spec/mapping_architecture.md`, `cache_to_db_migration.md`, `vector_hosting.md`, `vector_hosting_setup.md` |
| identity design | `docs/2026-08-07_identity_design.md` |

## 7. Decisions already made — do not re-litigate

- **Vector hosting: Chroma stays local** (`PersistentClient`) on CSI's server. $0. Railway is a
  disposable 10-day bridge (~$5/mo Hobby, not free after trial), **deleted Aug 17**. If hosted is
  ever needed, Fly over Railway — Railway is the only candidate with no automatic volume backups.
- **FDR is base work** (CSI, 2026-08-07), quantity stays in `milling_sy`. No unit conversion in the
  mapping layer; conversion is a later layer with a CSI-verified factor table.
- **`removal_tons`** exists in `bucket_hierarchy.csv` with a sourced 1.75 Ton/CY factor — adopt it.
- **Verb-before-noun as a general rule: rejected** (tested; breaks 8 real cases). The narrow form —
  process verbs beating pavement-material nouns only — catches all three historic bugs and breaks none.
- **`crushing_tons`: delete.** Holds 0, keywords match nothing, absent from `bucket_hierarchy.csv`,
  and DOTs do not write crushing as a pay item. Not a correction to send CSI.
- Pinecone rejected; the pgvector evaluation in #22 is closed unless Supabase billing transfers.
