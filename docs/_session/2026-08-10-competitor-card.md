# Competitor card crash — `{name, tier}` objects rendered as React children

**2026-08-10** · demo-blocking · fixed on local `main` (commits `0592490` backend, `8b8d67a` frontend).
Not pushed — the main session pushes.

---

## 1. The three consumers, real file:line

Line numbers are **pre-fix** (`git show HEAD~2:<path>` if they have since drifted):

| # | Consumer | Pre-fix location | What it did with an entry |
|---|---|---|---|
| 1 | `apps/web/src/components/chat/report-card.tsx` | `:437` `const names = comp.competitors ?? []`, rendered at `:478` `names.map((name) => <CompetitorRow name={name} …/>)` → `{name}` as a React child | threw **"Objects are not valid as a React child"**, taking the whole card down (the brief's "~479" was one line off) |
| 2 | `apps/api/backend/final_report.py` §④ | `:598` `names = comp.get("competitors", [])`, then `:615` `stats_map.get(name)` | **`TypeError: unhashable type: 'dict'`** — a dict can't be a dict key. The markdown/PDF/CSV export path, not just chat |
| 3 | `apps/web/src/lib/chat-data.ts` | `:76` `competitors: string[]` (and `:79` `user_added?: string[]`) | the type asserted a shape the wire does not guarantee, so TypeScript never flagged either consumer |

**A fourth, unlisted crash site found while fixing:** `final_report.py::assemble` `:355`
`existing_lower = {c.strip().lower() for c in comp.get("competitors", [])}` — the manual-competitor
dedup. With the object shape this raises `AttributeError: 'dict' object has no attribute 'strip'`
**before** §④ is ever reached, whenever an estimator types a name into the verify popup. Covered by
a test.

## 2. The flattening boundary

`competitors` is flattened to a plain ranked list of **names, no tiers** at three points — one per
path that can put a list in front of a human:

| Boundary | Why there |
|---|---|
| `final_report.py::predict_competitors()`, just before `return comp` | the single producer all cascade tiers flow through. `POST /api/report/{id}/predict-competitors` returns this list **straight to the verify-competitors popup** without passing through `assemble()`, so flattening only in `assemble()` would leave that popup broken |
| `final_report.py::assemble()`, immediately after `comp` is resolved | catches the path `predict_competitors` cannot: a **cached** prediction handed in by the endpoint (possibly written by an older build). Runs before the manual-name merge, so crash site #4 is fixed by the same line |
| `report-card.tsx::CompetitorSection`, first statement | defensive, per the coordinator's note — the frontend must survive the backend shape changing across the pending merge. Applied to `user_added` too |

Both implementations are named the same thing on purpose and cross-reference each other:
`final_report.py::competitor_names()` ↔ `chat-data.ts::competitorNames()`. Rules: order preserved,
duplicates dropped, `{name}`/`{display_name}` unwrapped, unnamed entries **dropped rather than
stringified** (never a dict repr / `[object Object]`).

The TS type now tells the truth instead of the intent:
`export type CompetitorEntry = string | { name?; display_name?; tier? }`, and
`competitors: CompetitorEntry[]`. The *rendered* list is still `string[]` — v3's no-tier intent is
enforced by the flattener, not by a type assertion nobody checks.

**Failure vs. empty** (standing rule): a failed/absent lookup is `competitor == null` and renders
"No competitor-intel report matched this project" (card) / the same sentence (markdown). A matched
report that names nobody now renders **"This report matched, but it names no competitors."** — it
used to render as blank space, i.e. indistinguishable from a card that had not loaded. Asserted in
both test suites.

## 3. Coverage tests, and that they fail before the fix

**Backend — `apps/api/tests/test_competitor_flatten.py`** (6 tests). Fixture is the object shape
that actually crashes: `[{"name": "KNIFE RIVER MATERIALS", "tier": 1}, {"name": "MAYO CONSTRUCTION", "tier": 2}]`.

- renders §④ without raising · no dict repr in the output (both `include_dives` modes) · mixed
  string+object entries survive · `assemble()` flattens before the manual-name merge · empty list
  and missing report do not render identically.
- **Before the fix: 6 failed** — 4× `TypeError: unhashable type: 'dict'`,
  1× `AttributeError: 'dict' object has no attribute 'strip'`, 1× empty-state assertion.
  After: 6 passed.

**Frontend — `apps/web/tests/2026-08-10-competitor-card.test.mjs`** (6 tests). Renders the **real**
`CompetitorSection` through `react-dom/server` and asserts on the emitted HTML, never on the input:

- objects render without throwing · **no `[object Object]` anywhere, and both names appear** ·
  plain strings still render · mixed list keeps its order · object-shaped `user_added` still badges
  the right row · empty list says so rather than going blank.
- **Before the fix: 5 failed, 1 passed** (the one that passed is the string case — exactly the
  worthless-fixture failure mode the brief warned about, kept deliberately as the regression guard
  for the shape the backend emits today). After: 6 passed.

`apps/web` had **no test runner** (verified two ways: `package.json` has no vitest/jest/mocha
dependency or script, and `node_modules/.bin` contains no test-runner binary — only `tsc` and
`playwright`). Rather than install one the week of the presentation, the tests run on `node --test`
with a 40-line ESM loader (`tests/2026-08-10-tsx-loader.mjs`) that resolves the `@/` alias and
transpiles `.tsx` with the already-installed `typescript`. Added `npm test` to `apps/web/package.json`.

Also clean: `npx tsc --noEmit`, `npx eslint`, `npm run build`, and the `apps/api` pytest suite
(33 passed, 1 failed — `test_midpoint_bridge.py`, the pre-existing rough-edge-6 MnDOT flake; three
test modules cannot be collected at all because `rapidfuzz` is not installed in this environment,
also pre-existing).

## 4. Things that contradict the board / need the owner's eye

1. **Nothing in this tree produces the `{name, tier}` shape.** Verified two ways: `grep -rn "tier"`
   across `apps/api/backend/` (only `final_report.py`'s own prose comments and `config.py:285`), and
   reading all three producers — `competitor_report.py:154`, `competitor_predict_live.py:205`, and
   `competitor_live.py` (which just parses the former) all build `names: list[str]`. The one place
   `tier` is a real field is `pipelines/ci_model/06_reporting/agent/executor.py:149`
   (`"tier": tier, # 1 = priority, 2 = discovery`), which is CI-owned and out of scope. So the
   object shape reaches the app either from a **cached prediction written by an older build** or
   from a CI-side change not in this tree. Worth confirming the provenance before the demo — the
   fix is shape-agnostic either way, but a stale cache would mean other v2-shaped fields are also
   in circulation.
2. **Upstream (`origin/main`, 9 commits ahead) has NOT already fixed this.** Checked
   `git show origin/main:apps/api/backend/final_report.py`: `:686` is still
   `names = comp.get("competitors", [])`, `:435` still `c.strip()`, and `origin/main`'s
   `report-card.tsx` still has `const names = comp.competitors ?? []`. #97 did **not** flatten
   anything — it added a top-5 cap (`TOP_N_COMPETITORS`) at the end of `predict_competitors()`.
   **The backend half of this fix is not redundant**; upstream is equally exposed.
3. **#97 did create the better boundary, and this fix already uses it.** Upstream's
   `predict_competitors()` is the single producer with a cap block at `:328`; my flatten sits at
   exactly that point in the local version, so after the merge the two collapse into adjacent lines
   in the same block — flatten first, then cap.

## 5. Expected merge conflicts (for whoever merges `origin/main`)

- `final_report.py::predict_competitors` — upstream rewrote the cascade (three tiers → two) and
  appended the top-5 cap. My flatten is the last statement before `return comp`. **Resolution: keep
  both, flatten before the cap** (capping a list of objects would truncate correctly but still
  crash downstream).
- `final_report.py::assemble` — my boundary block sits between `comp = predicted_competitors` and
  the `# --- manual competitors:` comment; upstream changed the `predict_competitors(...)` call
  signature two lines above (dropped `reports_dir`). Small textual conflict, keep both sides.
- `report-card.tsx::CompetitorSection` — upstream **deleted** the match-confidence chip block that
  sits directly above my two changed `const` lines, and rewrote `pit_access`. Keep the
  `competitorNames(...)` calls. Note upstream's `CompetitorSection` is **not exported**; the export
  is load-bearing for the frontend test and must survive the merge.
- `chat-data.ts` — upstream changed the `CompetitorStats.pit_access` shape (owned vs open pits);
  my change is confined to `Competitor.competitors` / `user_added` plus the new
  `CompetitorEntry`/`competitorNames` block. Should merge cleanly.

## 6. Files touched

Owned and edited: `apps/web/src/components/chat/report-card.tsx`,
`apps/web/src/lib/chat-data.ts`, `apps/api/backend/final_report.py` (§④ + the two flatten points +
the shared `competitor_names()` helper), `apps/web/package.json` (added `npm test`).
New: `apps/api/tests/test_competitor_flatten.py`, `apps/web/tests/2026-08-10-*.mjs` (3 files).

`final_report.py` was being edited concurrently by the payload-carry agent throughout; every edit
used `Edit` on a re-read file, and the backend commit was staged **hunk-by-hunk**
(`git apply --cached` on a filtered patch) so none of that agent's in-flight `payload_carry` work
was committed by me.

**Naming exemption:** `apps/api/tests/test_competitor_flatten.py` carries no date prefix — pytest
collects `test_*.py` and imports it as a module, and `2026-08-10-` is not a legal Python identifier.
Same runtime-module exemption the repo's other test files use. The three `apps/web` test files are
date-prefixed as required.
