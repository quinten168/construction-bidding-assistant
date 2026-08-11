# Spec — frontend gap rendering (board item F2, UI half)

Date: 2026-08-10 · Branch: `2026-08-10-mapping-honesty` · Status: **SPEC ONLY — nothing built.
No `.tsx`, `.ts` or `.py` file was edited by this pass.**

> **This document is also the session report** (the task allowed folding the two together). §11 is
> the report half: what was verified, how, and which inherited claims were wrong.

Board item F2: *"If the UI has no branch for a gap state it must render visibly wrong, not blank."*
The backend now honours that (`payload_carry.py`, `final_report.py:702-703`, `:823-825`). The
frontend has **no branch at all** — its only two gap behaviours are *the row disappears* and *an em
dash*, which are precisely the two things F2 bans.

Read §2 (shape-independent — execute immediately), then §5 (shape-dependent — pick a branch first).

---

## 1. Verified state of the world

Every `file:line` below was re-read on 2026-08-10 at the head of `2026-08-10-mapping-honesty`.
Inherited-audit corrections are called out inline and collected in §11.2.

### 1.1 Frontend — the whole gap surface

| Fact | Location | Verified |
|---|---|---|
| `IDENTITY_LABELS` is a hardcoded 6-key list: `state`, `county`, `sp_number`, `location`, `traffic_level`, `construction_start` | `apps/web/src/components/chat/report-card.tsx:20-27` | ✅ as audited |
| `fmtVal` returns `"—"` for `null` / `undefined` / `""` | `report-card.tsx:34-38` | ✅ as audited |
| Empty identity rows are **filtered out** before render | `report-card.tsx:157` | ✅ as audited |
| The clipboard markdown builder repeats the loop **plus** an explicit non-empty skip | `report-card.tsx:74-76` (inside `reportToMarkdown`, `:71-87`); called from `copy` at `:148-152` | ✅ as audited |
| Quantities table renders `q.label` bare — no gloss, no footnote | `report-card.tsx:233-241` (the `<td>` is `:235`) | ✅ as audited |
| `identity` is typed `Record<string, string \| number \| boolean \| null>` and nothing reads a status key | `apps/web/src/lib/chat-data.ts:124` (`FinalReport`) and `:146` (`Extraction`) | ✅ as audited |
| Zero occurrences of `none_found` / `extraction_failed` / `never_matched` / `unconverted` anywhere in `apps/web` | — | ✅ (two methods, §11.1) |
| ⚠️ **Correction:** the audit said zero occurrences of `_status`. There is **one**: `mapping_status` at `apps/web/src/components/bid-results/use-bid-results-store.ts:33`, an unrelated bid-results column. No gap-status key is read anywhere. | | |

### 1.2 Backend — what is already on the wire

`final_report.assemble` passes `identity` through **whole**, with no key whitelist
(`final_report.py:493-499` builds the return dict from the same `identity` object bound at `:393`).
So every key below already reaches `apps/web` today and is being thrown away there.

Measured against **all 14** cached payloads in
`pipelines/plan_reader/00_input/_report_payload_cache/` (`python3` + `json`, every file parsed):

| identity key | Source | Values seen across the 14 payloads |
|---|---|---|
| `phasing_requirements` + `phasing_requirements_status` | `payload_carry.CARRIED_FIELDS` via `report.py:315` / `final_report.py:538-539` | `detected` 10, `none_found` 4 |
| `hot_mix_unconverted` / `base_unconverted` / `shoulder_unconverted` + each `_status` | same registry | `hot_mix_unconverted_status`: `detected` 2, `none_found` 12 |
| `milling_unit_status` (7 states) | `schema.milling_unit_status()` via `report.py:320` | `sy_only` 8, `not_present` 5, `sy_and_tons` 1 |
| `hot_mix_unit_status` / `base_unit_status` / `shoulder_unit_status` (6 states) | `schema.bucket_unit_status()` via `report.py:328-329` | base: `not_present` 6, `unconverted_only` 4, `tons_only` 3, `tons_and_unconverted` 1 · hot_mix: `tons_only` 9, `not_present` 3, `unconverted_only` 2 · shoulder: `not_present` 9, `tons_only` 3, `unconverted_only` 2 |

**Nine of the fourteen real payloads carry at least one `unconverted_only` or `tons_and_unconverted`
bucket.** This is not a hypothetical rendering branch; it is the majority of the demo corpus.

Status vocabularies (do not invent new ones):

- `payload_carry.py:39-41` — `detected` / `none_found` / `extraction_failed`, labels at `:45-48`.
- `schema.py:333-341` — `MILLING_UNIT_STATUSES`: `sy_only`, `tons_only`, `sy_and_tons`,
  `other_unit`, `not_present`, `unknown`, `inconsistent`.
- `schema.py:399-407` — `BUCKET_UNIT_STATUSES`: `tons_only`, `unconverted_only`,
  `tons_and_unconverted`, `not_present`, `unknown`, `inconsistent`.
- `quantity_crosswalk.py:432-436` — `GAP_*`: `excluded_by_csi`, `untracked_category`,
  `no_bucket_for_unit`, `never_matched`. **Not on the wire — see §6.**

### 1.3 What the backend renders, which the UI must not contradict

- `final_report.py:699-703` — §① Plan Snapshot. The six base rows use `or "—"` (`:694-698`); the
  carried rows deliberately **do not**, and use `payload_carry.render_value` instead.
- `final_report.py:823-825` — CSV `detail` column carries the three-valued presence.
- `final_report.py:713-718` — ASCII bar block; `f"{q['label']:<6}"` at `:717`.

---

## 2. SHAPE-INDEPENDENT WORK — executable right now, on either branch

Five edits. None of them depends on the 2a-vs-#102 decision.

### 2.1 NEW FILE — `apps/web/src/lib/gap-status.ts`

Not date-prefixed: this is runtime source, and no file under `apps/web/src` is date-prefixed. The
date-prefix standing rule is applied to the docs and tests this pass creates.

```ts
// Gap-state vocabulary and labels, mirroring apps/api/backend/payload_carry.py and
// pipelines/plan_reader/01_pipeline/schema.py. THE STANDING RULE, IN UI FORM: a failure and a
// legitimate empty answer must never share a rendering, and neither may render blank.
// Kept honest by tests/2026-08-10-status-label-parity.test.mjs, which reads payload_carry.py.

export type PresenceStatus = "detected" | "none_found" | "extraction_failed";

export type GapTone = "value" | "empty" | "failure";

export type GapCell = { tone: GapTone; text: string };

// Wording deliberately echoes payload_carry._STATUS_LABEL ("None stated", "Not captured").
// The backend strings are markdown (`_..._`, `⚠️ **...**`); these are the plain-text equivalents
// the React tree styles itself. The parity test asserts the KEY PHRASES match, not the markup.
export const PRESENCE_CELL: Record<Exclude<PresenceStatus, "detected">, GapCell> = {
  none_found:        { tone: "empty",   text: "None stated in the plan" },
  extraction_failed: { tone: "failure", text: "Not captured — extraction did not return this field" },
};

/** Presence of one carried field. A MISSING `_status` key is `extraction_failed`, never
 *  `none_found` — same reading as payload_carry.render_value (payload_carry.py:97). 10 of the 14
 *  cached payloads predate some of these keys; treating that as "the plan has none" is the exact
 *  failure-vs-empty collapse this file exists to prevent. */
export function presenceOf(
  identity: Record<string, unknown>, field: string,
): PresenceStatus {
  const s = identity[`${field}_status`];
  if (s === "detected" || s === "none_found" || s === "extraction_failed") return s;
  return "extraction_failed";
}

/** The cell for one carried field. NEVER returns an empty string and never returns "—". */
export function carriedCell(identity: Record<string, unknown>, field: string): GapCell {
  const status = presenceOf(identity, field);
  if (status !== "detected") return PRESENCE_CELL[status];
  const raw = identity[field];
  const text = String(raw ?? "").replace(/\s+/g, " ").trim();
  // `detected` with nothing to show would render blank — say so rather than print a gap.
  if (!text) return PRESENCE_CELL.extraction_failed;
  return { tone: "value", text: text.length <= 300 ? text : `${text.slice(0, 300).trimEnd()}…` };
}

// schema.MILLING_UNIT_STATUSES (schema.py:333-341) — 7 states, all 7 present.
export const MILLING_UNIT_CELL: Record<string, GapCell> = {
  sy_only:      { tone: "value",   text: "Measured in square yards" },
  tons_only:    { tone: "empty",   text: "Measured in TONS — square yards not stated, nothing converted" },
  sy_and_tons:  { tone: "empty",   text: "Measured in BOTH square yards and tons — the two totals are not addable" },
  other_unit:   { tone: "empty",   text: "Measured in another unit (CY/LF/LS/STA) — not counted" },
  not_present:  { tone: "empty",   text: "No milling item in this bid schedule" },
  unknown:      { tone: "failure", text: "Not captured — extraction returned no milling unit" },
  inconsistent: { tone: "failure", text: "Inconsistent — the stated unit contradicts the quantities" },
};

// Human label for the quantities table. See §2.5.
export const QUANTITY_LABEL: Record<string, string> = { MILL_TON: "MILL (tons)" };
export const QUANTITY_NOTE: Record<string, string> = {
  MILL_TON:
    "Milling measured in TONS, carried unconverted. Where a plan states both, MILL (SY) and " +
    "MILL (tons) are the same work in two units and must not be added together.",
};
```

Bucket-status labels are **shape-dependent** and live in §5, appended to this same file.

### 2.2 EDIT — `report-card.tsx:157`, stop filtering

**Which keys.** Not a blanket removal. Two lists with two different contracts:

- **The six `IDENTITY_LABELS` keys** — always rendered, `fmtVal`'s `"—"` retained. This is
  deliberate and it is argued, not conceded: `final_report.py:694-698` renders exactly these six
  with `or "—"` in the export, and the UI diverging from the export is the bug §2.6 fixes, not a bug
  to introduce here. These six carry **no `_status` key from the backend**, so the UI genuinely
  cannot tell "the plan says nothing" from "extraction failed" for them — printing a status it does
  not have would be a fabrication. Follow-up **F2b** (not in this spec): extend
  `payload_carry.CARRIED_FIELDS`-style presence to the base identity fields, then delete the em dash
  here too.
- **The carried / gap keys** — never filtered, never `"—"`, always a `GapCell` (§2.1).

Before (`:157`):
```tsx
  const identityRows = IDENTITY_LABELS.filter(([k]) => final.identity[k] != null && final.identity[k] !== "");
```
After:
```tsx
  // F2: a gap must render visibly wrong, not blank. The six base fields keep the export's em dash
  // (final_report.py:694-698) because the backend sends no presence signal for them; the carried
  // fields below never render blank and never render an em dash.
  const identityRows = IDENTITY_LABELS;
  const gapRows = GAP_FIELDS.map(([k, label]) => [k, label, carriedCell(final.identity, k)] as const);
```

And `:205` — `{identityRows.length > 0 && (` becomes `{(identityRows.length > 0 || gapRows.length > 0) && (`;
the `<dl>` at `:206-215` gains, after the existing `.map`:

```tsx
              {gapRows.map(([k, label, cell]) => (
                <GapRow key={k} label={label} cell={cell} />
              ))}
```

`GAP_FIELDS` is the shape-dependent list — §5.

### 2.3 EDIT — new `GapRow` / `GapText` components in `report-card.tsx`

Insert after `Snapshot` (currently `report-card.tsx:372-379`):

```tsx
// One §① row whose value may be a gap state. THREE visually distinct outcomes, never a blank cell:
// a real value, a muted "None stated in the plan", and a loud amber "Not captured". The
// data-gap attribute is the test surface (tests/2026-08-10-report-card-gaps.test.mjs).
function GapRow({ label, cell }: { label: string; cell: GapCell }) {
  return (
    <div className="flex items-baseline justify-between gap-3 border-b border-black/[0.04] py-1.5">
      <dt className="shrink-0 text-[13px] text-muted-foreground">{label}</dt>
      <dd className="line-clamp-2 text-right text-[15px]" data-gap={cell.tone} title={cell.text}>
        <GapText cell={cell} />
      </dd>
    </div>
  );
}

function GapText({ cell }: { cell: GapCell }) {
  if (cell.tone === "value") return <span className="font-medium">{cell.text}</span>;
  if (cell.tone === "empty") return <span className="italic text-muted-foreground">{cell.text}</span>;
  return (
    <span className="inline-flex items-center gap-1 rounded-md bg-[var(--warn)]/12 px-1.5 py-0.5
                     text-[13px] font-medium text-[var(--warn)]">
      <AlertTriangle className="h-3.5 w-3.5 shrink-0" /> {cell.text}
    </span>
  );
}
```

`AlertTriangle` joins the `lucide-react` import at `report-card.tsx:5`.

**"We never read it" vs "the plan says none" is carried by three independent channels** — colour
(amber vs muted), an icon (present vs absent) and the wording ("Not captured" vs "None stated"). One
channel is enough for a test; three are enough for an estimator glancing at a screen.

### 2.4 EDIT — `chat-data.ts`, type the status keys

`chat-data.ts:124` and `:146` stay `Record<string, string | number | boolean | null>` — narrowing
them would need every producer typed and is not worth a breaking change this week. Instead, at the
end of the identity comment block above `:124`, add:

```ts
// Identity also carries GAP-STATE keys the backend already emits and this type does not enumerate:
//   <field>_status        detected | none_found | extraction_failed   (payload_carry.CARRIED_FIELDS)
//   milling_unit_status   schema.MILLING_UNIT_STATUSES (7)
//   <bucket>_unit_status  schema.BUCKET_UNIT_STATUSES (6)
// Read them through lib/gap-status.ts, never with a bare truthiness check — a falsy value here
// means one of three different things.
```

No behavioural change; this exists so the next reader does not re-derive §1.2.

### 2.5 EDIT — gloss `MILL_TON` (frontend + backend)

**Frontend**, `report-card.tsx:235`:

Before:
```tsx
                      <td className="px-4 py-2.5 font-medium">{q.label}</td>
```
After:
```tsx
                      <td className="px-4 py-2.5 font-medium">
                        {QUANTITY_LABEL[q.label] ?? q.label}
                        {QUANTITY_NOTE[q.label] && (
                          <span className="ml-1 cursor-help text-muted-foreground/70" title={QUANTITY_NOTE[q.label]}>ⓘ</span>
                        )}
                      </td>
```
and after the `</table>` (`report-card.tsx:243`), inside the same bordered box:
```tsx
              {final.quantities.some((q) => q.label === "MILL_TON") && (
                <p className="border-t border-black/[0.06] bg-secondary/20 px-4 py-2 text-[12px] text-muted-foreground">
                  {QUANTITY_NOTE.MILL_TON}
                </p>
              )}
```

**Backend** (spec'd, deliberately not applied — `final_report.py` is another agent's file this
round), `final_report.py:713-718`:

- `:717` — the format string is `f"{q['label']:<6}"`. `MILL_TON` is 8 characters, so it already
  **breaks the column alignment of every export that contains it**. Widen to `:<9`.
- After `:718` (`md.append("```")`), add:
  ```python
      if any(q["label"] == "MILL_TON" for q in qs):
          md.append("")
          md.append("_MILL_TON — milling measured in TONS, carried unconverted. Where a plan states "
                    "both, MILL (SY) and MILL_TON are the same work in two units and are not addable._")
  ```
- The non-ASCII branch at `:720` gets the same conditional line appended.
- The label itself must **not** change: `report.py:293-296` documents that `bid_projects_record.py`
  writes the label into the column `mill_sy` and `competitor_predict_live.py` maps `"MILL"` into
  fitted weights. `MILL_TON` is the wire value; only its *presentation* is glossed.

### 2.6 EDIT — kill the clipboard divergence (`report-card.tsx:71-87`, `:148-152`)

The hand-built markdown will drift from `/export` again the moment either side changes; it already
has (`:75` skips empty identity values, `/export` prints all six plus the carried rows). **Do not
fix the loop — delete the builder and copy what the backend produced.**

Delete `reportToMarkdown` entirely (`:71-87`). Replace `copy` (`:148-152`) with:

```tsx
  // Copy the EXPORT's markdown, byte for byte. A locally rebuilt markdown is a second renderer
  // that silently drifts from /export — it already had (the old builder skipped empty identity
  // rows, so a copied report was shorter than a downloaded one). On failure this surfaces an
  // error; it never falls back to a shorter report, because a partial copy and a good copy must
  // not look the same.
  const copy = async () => {
    setDlError(null);
    try {
      const res = await fetch("/api/report/export", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ final, fmt: "md" }),
      });
      if (!res.ok) throw new Error(`Export failed (${res.status}).`);
      const text = await res.text();
      if (!text.trim()) throw new Error("The export came back empty.");
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch (e) {
      setDlError(e instanceof Error ? e.message : "Couldn't copy the report.");
    }
  };
```

**Safari note.** `navigator.clipboard.writeText` after an `await` loses the user-gesture context in
Safari. If QA hits it, wrap with `ClipboardItem` when available — the promise form keeps the
gesture:
```tsx
      if (typeof ClipboardItem !== "undefined" && navigator.clipboard.write) {
        await navigator.clipboard.write([new ClipboardItem({ "text/plain": blobPromise })]);
      }
```
where `blobPromise` is created **before** the `await`. Spec'd as a conditional because it needs a
real Safari to verify and this sandbox has none — do not claim it works until someone clicks it.

---

## 3. RECOMMENDATION — one status-label table, enforced by a test, not by convention

**Agreed with the brief, with one amendment: port the table *and* add a parity test, because a
ported table with no enforcement is exactly the four-competing-artifacts pattern.**

Why not the alternatives:

| Option | Verdict |
|---|---|
| Two hand-synced copies (`payload_carry._STATUS_LABEL` + a TS literal) | **No.** This repo has four competing material-mapping artifacts from precisely this. Nothing fails when they drift. |
| Backend emits a pre-rendered `{field}_status_label` on identity | **No.** It bakes markdown (`_..._`, `⚠️ **...**`) into a React tree, invalidates all 14 payload caches, and makes the UI unable to style the three tones differently — which is the requirement. |
| Import a shared JSON from `apps/api/` into `apps/web/` | **No.** It crosses the folder-responsibility boundary in `CLAUDE.md` and Next's module root. |
| **Port the table into `gap-status.ts` + a node test that reads `payload_carry.py` as text and asserts the key phrases match** | **Yes.** One canonical wording, divergence fails a test rather than shipping, and no cross-language runtime coupling. |

The test asserts **phrases, not bytes** — the backend string is markdown and the UI string is not,
so a byte comparison would either force markdown into the UI or be permanently red:

`apps/web/tests/2026-08-10-status-label-parity.test.mjs`
```js
// Reads apps/api/backend/payload_carry.py as TEXT (no Python runtime) and asserts the UI wording
// and the export wording say the same thing. If someone reworks the backend label, this goes red
// instead of the two quietly disagreeing on an estimator's screen.
const py = await readFile(new URL("../../../apps/api/backend/payload_carry.py", import.meta.url), "utf8");
const label = (k) => py.match(new RegExp(`${k}:\\s*"([^"]+)"`))[1];
assert.match(label("NONE_FOUND"), /None stated/i);
assert.match(PRESENCE_CELL.none_found.text, /None stated/i);
assert.match(label("EXTRACTION_FAILED"), /Not captured/i);
assert.match(PRESENCE_CELL.extraction_failed.text, /Not captured/i);
// and the vocabulary itself, which MUST be byte-identical:
for (const k of ["detected", "none_found", "extraction_failed"]) assert.ok(py.includes(`"${k}"`));
```

The 6-state / 7-state unit vocabularies get the same treatment against
`pipelines/plan_reader/01_pipeline/schema.py`'s `MILLING_UNIT_STATUSES` / `BUCKET_UNIT_STATUSES`
tuples: assert every TS key exists in the Python tuple **and** every Python state has a TS key. A
new backend state with no UI branch is exactly the F2 failure, and this makes it loud.

---

## 4. Rendering the milling unit status (shape-independent — same in both variants)

Neither 2a nor #102 touches `milling_unit_status`; #102's spec §8 says milling was not touched, and
`report.py:320` is byte-identical on both branches (verified with `git show`).

Add to `GAP_FIELDS`-adjacent rendering, as a §① row labelled **"Milling measured in"**, using
`MILLING_UNIT_CELL` (§2.1). All 7 states have a branch, including the two the audit called out as
computed-and-discarded:

- **`inconsistent`** — tone `failure`. A declared unit contradicting the quantities is *our* problem
  surfacing, not the plan's, and must look like one.
- **`unknown`** — tone `failure`, distinct wording from `not_present` (tone `empty`). These are the
  two that currently collapse to one blank cell.

Suppression rule: render the row only when `identity.milling_unit_status` is present **or** any
quantity label starts with `MILL`. A plan with no milling and no key would otherwise gain a row
saying "Not captured" about a field nobody asked for — worth stating because "always render
everything" is the failure mode on the other side of F2.

---

## 5. SHAPE-DEPENDENT WORK — pick a branch first

The undecided piece is **how a tons bucket measured in another unit reaches the payload**. Both
variants are implemented in code today; only one can ship.

### 5.0 The wire difference, in one table

| | **2a** (`2026-08-10-mapping-honesty`, this branch) | **#102** (`fix/aggregate-mix-tons-conversion`) |
|---|---|---|
| Philosophy | Capture verbatim, **convert nothing** | Capture **and merge** into the tons total |
| `payload_carry.CARRIED_FIELDS` | `phasing_requirements`, `hot_mix_unconverted`, `base_unconverted`, `shoulder_unconverted` (`payload_carry.py:24-37`) | `phasing_requirements` **only** (verified via `git show`) |
| identity gap keys | `hot_mix_unit_status`, `base_unit_status`, `shoulder_unit_status` (`report.py:328-329`) | `base_unit_status`, `shoulder_unit_status`, **`mix_unit_status`** (`report.py:346-348` on that branch) |
| Vocabulary | 6 states (`schema.BUCKET_UNIT_STATUSES`) | **8** states (`base_unit_status()` / `shoulder_unit_status()` / `mix_unit_status()`, spec §5) |
| `quantities` rows | `BASE`/`SHLDR`/`MIX` are TON-only; the off-unit items are text on identity | `BASE`/`SHLDR`/`MIX` hold the **merged** number; raw items appear only in `field_confidence["base_cy_items" \| "shoulder_cy_items" \| "mix_sy_depth_items"]` (that branch's `report.py:322-323`) |
| Key-name trap | `hot_mix_unit_status` | **`mix_unit_status`** — a different key for the same bucket. Code written for one is silently wrong on the other, because a missing key reads as "no status", which is the collapse this whole spec is about. |

Everything in §2 and §4 is identical under both.

### 5.1 VARIANT A — 2a (`*_unconverted` + 6-state `bucket_unit_status`)

Append to `gap-status.ts`:
```ts
// schema.BUCKET_UNIT_STATUSES (schema.py:399-407) — 6 states, all 6 present.
export const BUCKET_UNIT_CELL: Record<string, GapCell> = {
  tons_only:            { tone: "value",   text: "Measured in tons" },
  unconverted_only:     { tone: "empty",   text: "Measured in another unit — NOT included in the tons total" },
  tons_and_unconverted: { tone: "empty",   text: "Partly in tons, partly in another unit — the remainder is not included" },
  not_present:          { tone: "empty",   text: "No item of this material in the bid schedule" },
  unknown:              { tone: "failure", text: "Not captured — extraction returned no unit for this material" },
  inconsistent:         { tone: "failure", text: "Inconsistent — the stated unit contradicts the quantities" },
};
```

`GAP_FIELDS` in `report-card.tsx` (new constant beside `IDENTITY_LABELS` at `:20-27`):
```tsx
const GAP_FIELDS: [string, string][] = [
  ["phasing_requirements", "Phasing"],
  ["hot_mix_unconverted", "Hot mix not counted (unit is not tons)"],
  ["base_unconverted", "Base not counted (unit is not tons)"],
  ["shoulder_unconverted", "Shoulder not counted (unit is not tons)"],
];
```
Labels are copied verbatim from `payload_carry._LABELS` (`payload_carry.py:112-119`) so the card and
`/export` name the same field the same way; the parity test (§3) covers these too.

Plus a **"Measured in"** sub-row per bucket, rendered *underneath* its `BASE`/`SHLDR`/`MIX`
quantities row and suppressed when the status is `tons_only` (the uninteresting case) — a small
`<tr>` spanning all three columns:

```tsx
const BUCKET_STATUS_KEY: Record<string, string> = { MIX: "hot_mix_unit_status", BASE: "base_unit_status", SHLDR: "shoulder_unit_status" };
```
…and, because a bucket can be `unconverted_only` with **no quantities row at all** (4 of the 14
payloads have exactly that for `base`), the three statuses must **also** be rendered as §① rows when
their bucket produced no quantity. Without that, `base_unconverted_only` on a plan with no BASE row
is invisible — which is the original 9786015 bug, reintroduced one layer up.

Suppression rule, stated exactly: render a bucket-status row iff
`status !== "tons_only" && status !== "not_present"`, **or** `status === "not_present"` and the
plan produced no quantities at all. Everything else is noise.

### 5.2 VARIANT B — #102 (merged totals + 8-state statuses)

Append to `gap-status.ts` instead:
```ts
// #102's base_unit_status/shoulder_unit_status/mix_unit_status — 8 states.
export const BUCKET_UNIT_CELL: Record<string, GapCell> = {
  tons_only:           { tone: "value",   text: "Measured in tons" },
  cy_only:             { tone: "value",   text: "Measured in cubic yards, converted to tons" },
  sy_converted_only:   { tone: "value",   text: "Measured in square yards with a stated depth, converted to tons" },
  mixed:               { tone: "value",   text: "Mixed units — cubic yards and depth-converted square yards, both included" },
  sy_no_depth_present: { tone: "failure", text: "An item is in square yards with NO stated depth — seen, not convertible, NOT in the total" },
  not_present:         { tone: "empty",   text: "No item of this material in the bid schedule" },
  unknown:             { tone: "failure", text: "Not captured — extraction returned no items list" },
  inconsistent:        { tone: "failure", text: "Inconsistent — the items list could not be classified" },
};
```
`GAP_FIELDS` shrinks to `[["phasing_requirements", "Phasing"]]`, and the key map becomes:
```tsx
const BUCKET_STATUS_KEY: Record<string, string> = { MIX: "mix_unit_status", BASE: "base_unit_status", SHLDR: "shoulder_unit_status" };
```

Three variant-B-only rendering obligations:

1. **A converted total must be visibly converted.** Under #102 a `BASE` row can be a computed number
   (`quantity × 1.55 ton/CY`), rendered identically to a number printed in the bid schedule. That is
   a new failure-vs-value collapse, in the opposite direction from the one this spec fixes: an
   estimator cannot tell a plan figure from our arithmetic. **Required:** any bucket whose status is
   `cy_only` / `sy_converted_only` / `mixed` renders a "converted" marker on the quantity cell with
   the factor in the `title`. Non-negotiable under B, and it does not exist in the branch today.
2. **`sy_no_depth_present` is a loud state, not a footnote** — it means a real item was seen and
   excluded from the total. Tone `failure`.
3. `field_confidence["base_cy_items" | "shoulder_cy_items" | "mix_sy_depth_items"]` carries the
   per-item citation. Optional, but it is the only place the raw items survive to the UI under B —
   a disclosure under the converted row, showing each `{quantity, unit, depth_in, page}`.

### 5.3 If the decision slips

§2 and §4 ship without it. `gap-status.ts` gains `BUCKET_UNIT_CELL` and `report-card.tsx` gains
`BUCKET_STATUS_KEY` only when a branch is chosen. Nothing in §2 imports either.

---

## 6. `never_matched` — spec'd, and NOT shipping

`quantity_crosswalk.bucket_gap_reason` (`quantity_crosswalk.py:439-457`) is the only thing that can
produce `never_matched` — "we could not categorise this line at all", i.e. a **reader failure**, as
distinct from `excluded_by_csi` / `untracked_category` / `no_bucket_for_unit`, which are correct
outcomes. Rendering all four the same is, in that file's own words, how the FDR typo hid for months.

**It is unreachable in production today.** Two independent verifications:

1. **Call-graph.** `bucket_gap_reason` is emitted only by `map_line_v2`
   (`quantity_crosswalk.py:414`). A repo-wide grep for `map_line_v2` returns exactly two hits
   outside the definition, both in `pipelines/plan_reader/05_knowledge/test_quantity_crosswalk.py`
   (`:218-221`). Every production caller uses `map_line` —
   `04_tools/05_parse_bid_schedule.py:216` and `:423`, `04_tools/10_remap_buckets.py:53` — and
   `map_line` (`:356-360`) returns a **2-tuple** `(csi_bucket, spec_category)` with no reason in it.
2. **The data.** All 14 cached payloads were parsed; **zero** contain any key matching
   `gap`/`reason`/`never_matched`, in `identity` or in `quantities`. Nothing on the wire could
   render it even with a UI branch.

**Do not present this as shipping.** The rendering below is dead code until the pipeline is
separately changed to carry the reason (`map_line` → `map_line_v2` at the two parser call sites,
a `bucket_gap_reason` column on the row, and a `gaps` array on the payload — a `pipelines/` change,
out of scope here and not attempted).

Spec'd rendering, for when it lands — a §② sub-table "Items not counted", grouped by reason:

```ts
export const GAP_REASON_CELL: Record<string, GapCell> = {
  excluded_by_csi:     { tone: "empty",   text: "Excluded by CSI ruling — deliberately not counted" },
  untracked_category:  { tone: "empty",   text: "Real work, not one of the tracked materials" },
  no_bucket_for_unit:  { tone: "empty",   text: "Category known, but this unit has no bucket — not counted" },
  never_matched:       { tone: "failure", text: "NOT READ — we could not categorise this line at all" },
};
```
`never_matched` is the only `failure` tone of the four, and it must sort to the top of the group.
Ship this **with** the pipeline change, in the same commit, or not at all — a UI branch for a value
that never arrives is indistinguishable from a UI branch that works.

---

## 7. Also produced-but-never-rendered (called out in the brief)

- **`schema.milling_unit_status()` — `inconsistent`.** Computed (`schema.py:352-374`), written to
  identity (`report.py:320`), present in all 14 payloads, read by nothing in `apps/web`. §4 gives it
  a `failure`-toned branch. This is the state where *a declared unit contradicts the quantities* —
  the plan and our reading disagree — and it currently renders as nothing at all.
- **`schema.bucket_unit_status()` — the reason half.** The `*_unconverted` fields carry the *item*;
  this function carries *why it was not counted* (`report.py:321-329`'s comment says exactly that).
  Under variant A, §5.1 renders the value and the reason together; rendering only the `_unconverted`
  text (which is what a naive fix would do, since it is the only human-readable string) would show
  an estimator a list of items with no explanation of why they are listed. **The pairing is the
  requirement, not the value.**

---

## 8. Test plan — red before green, on the real component

Runner: the one added 2026-08-10 — `npm test` →
`node --import ./tests/2026-08-10-register-loader.mjs --test tests/*.test.mjs`
(`apps/web/package.json:10`), with `tests/2026-08-10-tsx-loader.mjs` resolving `@/…` and transpiling
`.tsx` through the installed `typescript`. Style: render the real component via
`react-dom/server`, assert on HTML (`tests/2026-08-10-competitor-card.test.mjs`).

**Verified this pass:** `ReportCard` itself (not just `CompetitorSection`) renders under
`renderToStaticMarkup` through that loader — `motion/react` and `lucide-react` both SSR cleanly. A
throwaway probe was run and deleted; no test file was added by this pass. So the tests below can
target the whole card, not an extracted helper.

New file: `apps/web/tests/2026-08-10-report-card-gaps.test.mjs`.

| # | Assertion | Today | Why |
|---|---|---|---|
| T1 | `phasing_requirements_status: "extraction_failed"` → HTML contains `Not captured` | **RED** — row is filtered at `:157` | The headline F2 case |
| T2 | Same payload → HTML contains **no** `<dd …></dd>` with empty content, and no `<dd>` whose text is exactly `—`, for any `data-gap` cell | **RED** | "never a blank cell or a bare em dash" |
| T3 | `none_found` and `extraction_failed` render **different** strings, and the `extraction_failed` one carries `data-gap="failure"` while `none_found` carries `data-gap="empty"` | **RED** | The standing rule, asserted directly |
| T4 | Identity with the field **and no `_status` key at all** renders `Not captured`, never `None stated` | **RED** | The stale-cache case; `presenceOf`'s default |
| T5 | `milling_unit_status: "inconsistent"` → visible, `data-gap="failure"`; `"unknown"` and `"not_present"` render different text | **RED** | §4, §7 |
| T6 | A `MILL_TON` quantity row renders `MILL (tons)` and the note text contains `not addable`; a payload without it renders no note | **RED** | §2.5 |
| T7 | Every key of `MILLING_UNIT_CELL` / `BUCKET_UNIT_CELL` renders non-empty, non-`—` text — a `for…of` over the table, not a hand-listed subset | **RED** | "A negative result from a fixed set of checks is not proof of absence": iterate the vocabulary so a **new** backend state fails loudly |
| T8 | Parity test (§3): backend `NONE_FOUND` label contains `None stated`, `EXTRACTION_FAILED` contains `Not captured`; every Python status token has a TS key **and** vice versa | **RED** (file does not exist) | Stops the two tables drifting |
| T9 | `copy()` posts to `/api/report/export` with `fmt:"md"` and writes exactly the returned text; on a non-200 it sets an error and writes **nothing** to the clipboard | **RED** | §2.6 — a partial copy must not look like a good copy |
| T10 | Fixture test: render every JSON in `pipelines/plan_reader/00_input/_report_payload_cache/` through `assemble`-shaped minimal wrapping; assert no `data-gap` cell is empty | **RED** | Real payloads, not invented ones |

**T9 mechanics.** Stub `globalThis.fetch` and `globalThis.navigator = { clipboard: { writeText } }`
before importing, and drive `copy` by rendering `ReportCard` and invoking the handler — or, if
reaching the handler through static markup proves awkward, export `copyReportMarkdown(final, setters)`
as a plain async function from `report-card.tsx` and test it directly. **Prefer the exported
function**: it is the same trick the existing test used (`export function CompetitorSection`) and it
does not need a DOM.

**T10 caveat, stated rather than hidden.** The payload cache is gitignored, so on a fresh clone this
test finds zero files. It must **fail** on zero files, not skip — a fixture test that silently
passes with no fixtures is the exact "success signal at the wrong layer" this repo keeps hitting.
Guard it as: if the directory is absent → `t.skip("payload cache absent — regenerate per README")`;
if the directory exists but is empty → `assert.fail`.

Run: `cd apps/web && npm test`. **Never `npm run build`** — a teammate is running `next dev` on this
checkout and a build writes `.next`.

---

## 9. Execution order

1. §2.1 `gap-status.ts` + §3 parity test (T8) — no component change, goes green alone.
2. §2.2–2.3 filter + `GapRow`/`GapText` — turns T1–T4 green.
3. §4 milling row — T5.
4. §2.5 `MILL_TON` gloss, frontend — T6. Backend gloss in a **separate** commit (different file
   owner, different tree; cleanup and behaviour stay apart).
5. §2.6 clipboard — T9.
6. **STOP.** §5 waits on the 2a/#102 decision.
7. §6 only alongside the `pipelines/` change that makes `never_matched` reachable.

---

## 10. Out of scope, deliberately

- No `pipelines/` change; `map_line` keeps its 2-tuple contract (§6).
- No backend edit applied — the `final_report.py` gloss in §2.5 is spec'd text, not a diff.
- No golden edits, no merge or checkout of #102 (read via `git show origin/…` only), no 2a layering.
- No `next build`, no push, no PR, no DDL, no Supabase, no `pipelines/ci_model/`, no
  `road_midpoint.py`.
- **F2b** (base identity fields get presence keys so their em dash can go too) is named in §2.2 and
  not attempted.

---

## 11. Report half — verification record

### 11.1 Claims of absence, two methods each

| Claim | Method 1 | Method 2 |
|---|---|---|
| No `none_found` / `extraction_failed` / `never_matched` / `unconverted` anywhere in `apps/web` | `grep -rnoE` over `apps/web/src/**/*.{ts,tsx}` → 0 hits for all four | `git grep -n -E` over the same pathspec → 0 hits |
| `never_matched` cannot reach production | Call-graph: `map_line_v2` has 2 non-definition hits, both in `test_quantity_crosswalk.py:218-221`; production callers (`05_parse_bid_schedule.py:216,423`, `10_remap_buckets.py:53`) use `map_line`, whose body (`:356-360`) returns a 2-tuple | Data: all 14 cached payloads parsed; zero keys matching `gap`/`reason`/`never_matched` |
| `identity` reaches the frontend unfiltered | Read `final_report.py:393` (bind) → `:493-499` (return) — same object, no whitelist | 14 payload caches inspected: every `_status` / `_unit_status` key present in the persisted `identity` |

### 11.2 Inherited claims corrected

- **"Zero occurrences of `_status` in any `.ts`/`.tsx`"** — there is one, `mapping_status`
  (`use-bid-results-store.ts:33`), unrelated to gap state. The *substantive* claim (nothing reads a
  gap status) holds.
- **`final_report.py:710-719`** for the ASCII bars — the actual block is **`:713-718`**; `:710` is
  `qs = final["quantities"]` and `:719` is the `else`. The format string is at **`:717`**.
- Every other cited line (`report-card.tsx:20-27`, `:34-38`, `:74-76`, `:157`, `:233-236`;
  `chat-data.ts:124`; `final_report.py:702-703`, `:823-825`) was **exact**.
- **New, not in the audit:** `MILL_TON` is 8 characters against `final_report.py:717`'s `:<6` field
  width, so it already misaligns every export containing it (§2.5).
- **New, not in the audit:** 9 of 14 cached payloads carry at least one `unconverted_only` /
  `tons_and_unconverted` bucket — the un-rendered branch is the majority of the demo corpus, not an
  edge case.
- **New, not in the audit:** #102 renames the hot-mix status key `hot_mix_unit_status` →
  **`mix_unit_status`**. Frontend code written against one reads `undefined` on the other and, under
  `presenceOf`'s default, would silently report "Not captured" for a bucket that was captured fine.
  Called out in §5.0 because it is the single sharpest edge between the two variants.

### 11.3 Not verified

- No browser click-through — this sandbox has no headless browser (`CLAUDE.md` rough edge 7). The
  Safari clipboard-gesture note in §2.6 is reasoning, not observation.
- No live backend round-trip for §2.6's `/api/report/export` copy path.
- `git show` was the only contact with #102; it was neither checked out nor merged.
