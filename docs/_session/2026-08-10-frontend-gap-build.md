# Session report — frontend gap rendering, shape-independent half (board item F2)

Date: 2026-08-10 · Branch: `2026-08-10-mapping-honesty` (PR #104) · Spec:
[`docs/_spec/2026-08-10-frontend-gap-rendering.md`](../_spec/2026-08-10-frontend-gap-rendering.md)

Commits: `454d17a` (RED — tests + ported table) → `f03d2b6` (GREEN — component).
Nothing pushed, no PR touched, no backend file edited, no `npm run build`.

Board item F2: *"If the UI has no branch for a gap state it must render visibly wrong, not blank."*
The backend honoured it; the frontend could not express it at all — its only two gap behaviours
were **the row disappears** and **an em dash**, precisely the two things F2 bans. 9 of the 14 cached
payloads carry a gap state, so this was the majority path through the demo corpus.

---

## 1. What was built — verified `file:line`

All line numbers re-read at `f03d2b6`.

### 1.1 NEW — `apps/web/src/lib/gap-status.ts`

Not date-prefixed: it is runtime source imported by name (the standing rule's stated exemption); no
file under `apps/web/src` is date-prefixed.

| Export | Line | What |
|---|---|---|
| `PresenceStatus` / `PRESENCE_STATUSES` | `:18`, `:21` | The three-token vocabulary, ported from `payload_carry.py:39-41` |
| `GapTone` / `GapCell` | `:27`, `:29` | `value` \| `empty` \| `failure` — how a cell LOOKS, separate from what it says |
| `PRESENCE_CELL` | `:34` | "None stated in the plan" (empty) vs "Not captured — extraction did not return this field" (failure) |
| `presenceOf` | `:45` | A **missing** `_status` key → `extraction_failed`, mirroring `payload_carry.presence_status` / `render_value:97` |
| `carriedCell` | `:52` | Unwraps the `{value, confidence, page}` cell, 300-char budget (`payload_carry._MAX_CHARS`), `detected`-but-empty → `extraction_failed`. **Never returns "" and never returns "—"** |
| `CARRIED_LABELS` | `:68` | Copied verbatim from `payload_carry._LABELS`; the parity test asserts byte equality |
| `MILLING_UNIT_CELL` | `:80` | All **7** `schema.MILLING_UNIT_STATUSES`, each with a branch |
| `millingCell` | `:93` | The suppression rule + the **unknown-status fallback**: a state the backend adds that this table has not learned renders LOUDLY (`Unrecognised milling unit status "x" — the UI has no branch for this`), not blank. That is F2 stated literally, in code. |
| `QUANTITY_LABEL` / `QUANTITY_NOTE` | `:113`, `:115` | The `MILL_TON` gloss |
| `BUCKET_UNIT_CELL` | `:127` | **Deliberately `undefined`** — the held half. See §4. |

### 1.2 EDIT — `apps/web/src/components/chat/report-card.tsx`

| Change | Line | Note |
|---|---|---|
| `AlertTriangle` added to the `lucide-react` import | `:5` | |
| `gap-status` import | `:8-9` | |
| `GAP_FIELDS` | `:42` | One entry today (`phasing_requirements`). The comment names exactly what the held half adds. |
| `copyReportMarkdown` (exported) | `:100` | Replaces the deleted `reportToMarkdown`. |
| `copy` handler | `:187` | `await`s it, surfaces the error string, never sets `copied` on failure |
| **The filter is gone** | `:211` | `const identityRows = IDENTITY_LABELS;` |
| `gapRows` | `:212-213` | Carried fields → `carriedCell`, never filtered, never em-dashed |
| milling row | `:214-215` | Appended as `"Milling measured in"` when `millingCell` returns non-null |
| `<dl>` guard widened | `:263` | `(identityRows.length > 0 \|\| gapRows.length > 0)` |
| `gapRows.map` → `<GapRow>` | `:273-275` | |
| `MILL_TON` label gloss + ⓘ | `:296-305` | Wire label untouched — comment says why |
| `MILL_TON` footnote | `:314-318` | Rendered only when a `MILL_TON` row exists |
| `GapRow` | `:462` | Emits `data-gap={cell.tone}` — the test surface |
| `GapText` | `:473` | Three renderings; the failure branch is amber + `AlertTriangle` |

### 1.3 EDIT — `apps/web/src/lib/chat-data.ts:124-131`

Comment only, no behavioural change: documents the gap keys `identity` carries that the type does
not enumerate, and says to read them through `lib/gap-status.ts` rather than with a bare truthiness
check. The type stays `Record<string, string | number | boolean | null>` — narrowing it would need
every producer typed.

### 1.4 The five requested items, mapped

1. **Stop filtering empty rows** — `:211`. Followed the spec exactly, *not* a blanket removal. The
   six `IDENTITY_LABELS` keys keep `fmtVal`'s em dash and the code comment argues why: the backend
   renders those same six with `or "—"` (`final_report.py:694-698`) and sends **no presence signal**
   for them, so printing a status we do not have would fabricate one. F2b is named in the comment.
2. **Real status instead of the em dash** — `GapRow`/`GapText`, three states, three independent
   channels (colour, icon, wording). Missing `_status` → `extraction_failed`.
3. **Clipboard divergence fixed** — `reportToMarkdown` deleted; `copyReportMarkdown` relays
   `/api/report/export` byte for byte and on **any** failure returns an error and copies nothing.
4. **`MILL_TON` glossed** — frontend done; the backend legend/alignment is handed over in §3.
5. **Shared status table ported, with the parity test** — §2, T8.

---

## 2. Red-before-green proof for T1–T10

Two runs, both recorded in git.

**Run 1 — at `454d17a`** (tests + `gap-status.ts` only, no component change).
`npm test` → **26 tests, 12 pass, 12 fail, 2 skip.**

| # | Test | Run 1 | Run 2 |
|---|---|---|---|
| T1 | `extraction_failed` renders "Not captured" instead of vanishing | **not ok** | ok |
| T2 | no gap cell is ever empty or a bare em dash | **not ok** | ok |
| T3 | "the plan says none" and "we never read it" never look the same | **not ok** | ok |
| T4 | a MISSING `_status` key reads as `extraction_failed`, never `none_found` | **not ok** | ok |
| T5 | `milling_unit_status: inconsistent` is loud, and `unknown` ≠ `not_present` | **not ok** | ok |
| T5b | the milling row is suppressed when there is no status and no MILL item | **not ok** | ok |
| T6 | `MILL_TON` glossed + footnoted; no footnote when absent | **not ok** | ok |
| T7 | **every** milling status in the table renders visible, non-blank, non-em-dash text | **not ok** | ok |
| T7b | every bucket status renders | SKIP (held) | SKIP (held) |
| T8 | parity — 7 assertions across two files | ok (5) / SKIP (1) | same |
| T9 | copy posts `fmt:"md"` and copies exactly what came back | **not ok** | ok |
| T9b | on a non-200 it errors and copies **nothing** | **not ok** | ok |
| T9c | transport failure and empty export each error, and copy nothing | **not ok** | ok |
| T10 | all 14 real cached payloads render with no blank gap cell | **not ok** | ok |

**Run 2 — at `f03d2b6`**: **26 tests, 24 pass, 0 fail, 2 skip.**

An earlier run, before `gap-status.ts` existed, was red at module resolution (`ERR_MODULE_NOT_FOUND`)
for both new files. That is a coarse red — no individual assertion executed — so `gap-status.ts`
was landed first specifically to get a **per-test** red on behaviour rather than on imports.

**Two tests were written to the "a negative result from a fixed set of checks is not proof of
absence" rule specifically:**

- **T7 iterates the whole vocabulary** (`for (const [status, cell] of Object.entries(MILLING_UNIT_CELL))`)
  rather than hand-listing states. Paired with `millingCell`'s loud fallback, a state added upstream
  with no UI branch fails here instead of on an estimator's screen.
- **T8 asserts both directions** — every Python token has a TS key *and* every TS key exists in the
  Python tuple, for `MILLING_UNIT_STATUSES`, `BUCKET_UNIT_STATUSES` and the three presence tokens.
  It reads both `.py` files as **text** (no Python runtime, no cross-tree import, no folder-boundary
  violation) and asserts *phrases* for wording (the backend strings are markdown) but *bytes* for
  the tokens.
- **T10 fails on zero fixtures rather than skipping.** Directory absent → `t.skip` (it is
  gitignored, so a fresh clone legitimately has none); directory present but empty → `assert.fail`.
  It also asserts at least one payload actually exercised a non-`value` tone, so the fixture set
  cannot go vacuous while still passing.

Static checks: `npx tsc --noEmit` clean, `npx eslint` clean on all three touched sources.
**`npm run build` deliberately not run** — a teammate has `next dev` live on this checkout.

---

## 3. HANDOVER — the exact `final_report.py` edit (NOT applied)

`apps/api/backend/final_report.py` is another agent's file this round. Line numbers verified at
`f03d2b6`; the ASCII-bar block is **`:713-718`** (`:710` is `qs = final["quantities"]`, `:719` is
the `else`).

**(a) Alignment bug, `:717`.** `MILL_TON` is 8 characters against a `:<6` field, so it *already*
misaligns the bar column of every export containing it.

```python
# before (:717)
            md.append(f"{q['label']:<6}{q['value']:>11,.0f} {q['unit']:<3} {_bar(q['value'], vmax)}")
# after
            md.append(f"{q['label']:<9}{q['value']:>11,.0f} {q['unit']:<3} {_bar(q['value'], vmax)}")
```

**(b) Legend.** Insert immediately after `:718` (`md.append("```")`), before the `else` at `:719`:

```python
        if any(q["label"] == "MILL_TON" for q in qs):
            md.append("")
            md.append("_MILL_TON — milling measured in TONS, carried unconverted. Where a plan "
                      "states both, MILL (SY) and MILL_TON are the same work in two units and are "
                      "not addable._")
```

**(c)** The non-ASCII branch (`:720`) should get the same conditional line appended, so a chat-mode
export is not the only place the caveat is missing.

**(d) The label itself must NOT change.** `MILL_TON` is the wire value: `bid_projects_record.py`
writes the label into the `mill_sy` column and `competitor_predict_live.py` maps `"MILL"` into
fitted competitor weights. Renaming it downstream would be a silent unit corruption. Only its
*presentation* is glossed — which is exactly what this pass did on the frontend.

---

## 4. Where the array-shape half plugs in

Three edits, no restructuring. The seams already exist and are commented in place.

1. **`gap-status.ts:127`** — replace
   `export const BUCKET_UNIT_CELL: Record<string, GapCell> | undefined = undefined;`
   with the real table (spec §5.1 for variant 2a's 6 states, §5.2 for #102's 8). **Both parity tests
   currently `t.skip` on `BUCKET_UNIT_CELL === undefined`** and go live the instant it is defined,
   so the half cannot land unenforced — that was the point of shipping it as an explicit `undefined`
   rather than omitting the export.
2. **`gap-status.ts:68`, `CARRIED_LABELS`** — add the three `*_unconverted` labels. Their exact
   `payload_carry._LABELS` wording is already quoted in the comment there, and the parity test
   asserts byte equality against the Python.
3. **`report-card.tsx:42`, `GAP_FIELDS`** — append the three tuples. Everything downstream
   (`gapRows` at `:212`, `GapRow`, `data-gap`, T2/T10's blank-cell assertions) already handles them
   with no change.

Plus the one genuinely new piece: a per-bucket **"Measured in"** sub-row keyed by
`BUCKET_STATUS_KEY`, rendered under its `BASE`/`SHLDR`/`MIX` quantities row, **and** as a §① row
when the bucket produced no quantity at all — 4 of the 14 payloads are `base: unconverted_only` with
no BASE row, and without the §① fallback that case is invisible, which is the original 9786015 bug
reintroduced one layer up.

**The key-name trap, restated because it is the sharpest edge:** 2a calls it `hot_mix_unit_status`,
#102 calls it **`mix_unit_status`**. Code written against one reads `undefined` on the other, and
under `presenceOf`'s default that renders "Not captured" for a bucket that was captured fine — a
fabricated failure. Whoever takes this must confirm the key name against the branch that actually
ships, not against the spec.

**If the value arrives as an ARRAY** (2a's per-item capture), `carriedCell:52` currently
`String()`s it, which would render `[object Object]` for object items — the same class of bug the
competitor-name test already guards. That is the one line the array half must change, and it should
land with a test in the shape of `2026-08-10-competitor-card.test.mjs`'s
`"a name never renders as [object Object]"`.

---

## 5. Not verified / deliberately not done

- **No browser click-through** — this sandbox has no headless browser (`CLAUDE.md` rough edge 7).
  The rendering is asserted through `react-dom/server` HTML, not through a real paint, so the
  amber/muted colour contrast is reasoned, not observed. The `data-gap` attribute and the wording
  are what the tests actually pin.
- **No live backend round-trip** for `copyReportMarkdown`'s `/api/report/export` call. T9 drives it
  with an injected `fetch`; the real proxy route was not exercised.
- **The Safari clipboard-gesture caveat** (spec §2.6) was **not** implemented. `writeText` after an
  `await` can lose the user-gesture context in Safari; the `ClipboardItem` workaround needs a real
  Safari to verify and this sandbox has none. `copyReportMarkdown` returns
  `"Couldn't write to the clipboard."` if `writeText` rejects, so the failure is visible rather than
  silent — but it is a **known unfixed** issue, not a handled one.
- **No backend edit applied** (§3 is text, not a diff). No `pipelines/` change. `never_matched`
  (spec §6) not shipped — it is unreachable in production today, and a UI branch for a value that
  never arrives is indistinguishable from one that works.
- **F2b** — giving the six base identity fields their own presence keys so their em dash can go too
  — is named in the code comment at `report-card.tsx:199-210` and not attempted.
