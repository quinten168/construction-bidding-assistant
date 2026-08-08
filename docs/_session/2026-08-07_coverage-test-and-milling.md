# Session report 3 — 2026-08-07 · publish blocked, coverage test, and a third six-figure mapping bug

Third report of the day. Companions: `2026-08-07_crosswalk-and-vision.md`, `2026-08-07_remap-run.md`.

---

## Lead: what did NOT happen

- **(c) republish to Postgres — BLOCKED, not skipped.** Missing credential, detail in §1. Nothing was
  published; `public.*` still holds the pre-remap snapshot.
- **(d) app confirmation — BLOCKED by (c).** Verified the app reads the published Postgres tables, so
  it cannot show the new numbers until (c) runs.
- **P1 (cache→DB migration), P2 (F2 rendering), P3 (extraction schema v2) — NOT STARTED.**
- **P4–P8 — NOT STARTED.**

## 1. (c) is blocked on the `postgres` role credential

`publish_to_supabase.py` refuses to run as anyone but `postgres`, and that refusal is **correct** —
it is the guard that stops a republish silently stripping the team's read access.

The mechanism, confirmed against live `pg_default_acl`:

```
('postgres','public','r', '{... csi_reader=r/postgres, csi_team=r/postgres}')
```

Grants do not survive `DROP TABLE`. What restores them is `ALTER DEFAULT PRIVILEGES`, and those are
scoped to **tables created by `postgres`**. Publishing as any other role produces correct data and
silently removes everyone's access. The script fails loudly before the first drop rather than
allowing that. **Good news: the "reapply grants after publish" step T asked for is already handled by
construction — provided it runs as `postgres`.**

**Verified by two independent methods** (per standing instruction), because this is an
"X does not exist" claim:

1. **Filesystem enumeration** — parsed all 8 `.env` files on disk plus shell environment. The only
   DSN present is `SUPABASE_TEAM_DB_URL`, role `csi_team`.
2. **Live database interrogation** — connected and asked the server:
   `current_user = 'csi_team'`, and `has_schema_privilege('csi_team','public','CREATE') = false`.
   So `csi_team` **cannot create tables in `public`** even if the pre-flight were bypassed.

The two methods agree. `pipelines/plan_reader/.env.example:9` documents `SUPABASE_DB_URL` as the
variable to set; no real value for it exists on this machine.

**To unblock:** set `SUPABASE_DB_URL` to the Supabase `postgres` login, then
`python pipelines/plan_reader/04_tools/publish_to_supabase.py` (dry-run first). Proof-of-grant should
be a real `csi_reader` SELECT, **not** `information_schema.role_table_grants` — that view only shows
grants visible to the querying role and produced a false negative on 2026-08-03.

### A stale doc that would mislead the next person

`publish_to_supabase.py`'s module docstring says *"The app does not read Supabase. Do not repoint it
here."* **That is now false.** P0-B repointed the app; `final_report.py:106,147,448` query
`public.gotchas` and `public.plans` via `ci_db`. Anyone trusting that docstring would conclude the
remap needs no publish. Worth a one-line correction when someone is next in the file.

## 2. P0 — the SPEC_MAP coverage test (built, and it found things immediately)

`pipelines/plan_reader/05_knowledge/test_quantity_crosswalk.py`. Four kinds of check, none of which
is a unit test of `spec_category`'s implementation:

1. **Dead keywords** — every `SPEC_MAP` entry must match ≥1 real corpus row.
2. **Wrong matches** — table-driven golden set of real pay items, including both of today's bugs
   pinned so they cannot regress, plus a general rule that *no removal may reach a placed bucket at
   any unit*.
3. **State distinguishability** — all four `bucket_gap_reason` values must be distinct, and
   `never_matched` must be reachable. ("Any enum where two states render identically is a bug
   waiting.")
4. **Contract** — `map_line` still returns a 2-tuple; `map_line_v2` never disagrees with it.

**Result: 11 of 78 `SPEC_MAP` keywords match zero corpus rows.**

| keyword | verdict |
|---|---|
| `2360`, `2211`, `2112`, `2118` | legitimately dead — the parser discards spec numbers (0/6,385 rows retain one) |
| `SWPPP`, `RETAINING WALL` | legitimately absent from these 66 plans |
| **`RECLAIM`** | **the bug that started all this. Still dead.** |
| `CRUSHING`, `CRUSHED AGGREGATE`, `CRUSH ` | **the entire `crushing` family is dead — `crushing_tons` can never be populated** |
| `STOCK PILE` | `STOCKPILE` (no space) matches; this variant never fires |

The five broken ones are pinned in a `strict=True` xfail so the list can only shrink deliberately.

**The `crushing` finding matters beyond the test.** CSI has an open question about whether
crushing/stockpile stay excluded. The answer today is that crushing is excluded *by accident* — no
keyword can reach it. That belongs in the batch document as a fact, not a question.

**The test also caught me.** My first draft of the milling fix added `MILL SURFACE` and `COLD PLANE`;
the coverage check rejected both as dead. I removed them rather than allow-listing them — the file's
own rule is that you do not add an entry to the exemption list to make the test pass.

## 3. A THIRD six-figure mapping bug — the original one, never actually fixed

The golden-item test failed red on a real corpus item:

```
MILL BITUMINOUS SURFACE (1.5")  ->  category 'mixed', expected 'mill'
```

First matching keyword: `BITUMINOUS` → `hma`. The milling keywords that would have caught it
(`MILLING`, `RECLAIM`) sit *below* `BITUMINOUS` in the first-match-wins list.

**This is the original Stearns bug.** The 2026-07-30 material pre-read names it exactly — *"MILL
BITUMINOUS SURFACE hits BITUMINOUS → hma before it can reach milling"* — and records it as **fixed**.
It was fixed in `04_tools/11_build_material_map.py`, the **pre-read generator**. It was never fixed in
`05_knowledge/quantity_crosswalk.py`, which is what runs.

**Measured impact: 1,346,886 SY across 18 plans**, categorised as hot mix. The unit guard prevented it
polluting `hot_mix_tons` (SY cannot enter a TON bucket), so it was counted **nowhere** rather than
counted wrong — which is precisely why nobody noticed for five weeks.

This is the third instance today of the same root cause, and the sharpest illustration of T's process
point: **a fix applied to the pre-read is not a fix.** The pre-read is a document; the crosswalk is
the product.

Fixed by adding `MILL BITUMINOUS`, `MILL TRANSITION`, `MILLING PAVEMENT` above the `hma` block, with
a comment recording that the pre-read's "fixed" claim was false for this file. Pinned by the golden
test.

## 4. Cumulative effect of one day on the corpus numbers

| bucket | start of day | now | change |
|---|---:|---:|---:|
| **`milling_sy`** | **542,262** | **2,826,995** | **+2,284,733 (+421%)** |
| `base_tons` | 1,008,322 | 808,944 | −199,378 |
| `grading_quantity` | 2,137,441 | 2,138,441 | +1,000 |
| `hot_mix_tons` | 1,150,328 | 1,146,413 | −3,915 |
| `shoulder_tons` | 47,211 | 45,871 | −1,340 |

Milling was under-reported by a factor of **5.2×**. Three independent defects contributed:
FDR (`RECLAIM` typo, 1,235,282 SY), `MILL BITUMINOUS` (noun-beats-verb, 1,346,886 SY), and Alex's
`REMOVE BITUMINOUS PAVEMENT` ruling (60,040 SY). The `base_tons` drop is demolition that was being
counted as purchased aggregate.

`integrity_check ok`; all four table row counts unchanged (plans 117, sections 37,261, materials
6,385, plan_metrics 100). Backup from earlier today is untouched.

**These numbers are in `csi_v2.db` only.** The app still shows the old ones until (c) runs.

## 5. Open for T

1. **The `postgres` DSN** — everything in (c)/(d) waits on it.
2. **The `crushing` family is dead**, so `crushing_tons` is structurally unreachable. Fix the
   keywords, or confirm with CSI that crushing is genuinely out of scope? This changes what the batch
   document asks.
3. **Left alone as instructed:** the two identical 64,750 TON `REMOVE AGGREGATE BASE & SURFACING`
   rows on `2026_BURKE-WARD-CO-ND_JOB-22484` (different item numbers, different pages). Needs an
   estimator's eye — flagged here for CSI.

## 6. Files changed this segment

| File | Change |
|---|---|
| `05_knowledge/quantity_crosswalk.py` | milling keywords above the hma block (the third bug) |
| `05_knowledge/test_quantity_crosswalk.py` | **new** — 32 coverage tests |
| `csi_v2.db` | re-mapped again to pick up the milling fix |

**67 passed, 1 xfailed.** Nothing committed.
