// T8 — STATUS-LABEL PARITY between the frontend table and the backend vocabularies.
//
// `src/lib/gap-status.ts` is a PORT of two Python sources:
//   apps/api/backend/payload_carry.py            (detected / none_found / extraction_failed)
//   pipelines/plan_reader/01_pipeline/schema.py  (MILLING_UNIT_STATUSES, BUCKET_UNIT_STATUSES)
// A ported table with no enforcement is exactly the four-competing-artifacts pattern this repo
// already suffers from (CLAUDE.md, mapping artifacts): nothing fails when the two drift, and the
// estimator is the one who finds out. This test reads the Python as TEXT — no Python runtime, no
// cross-language import, no folder-boundary violation — and fails when they disagree.
//
// It asserts PHRASES for the wording (the backend strings are markdown, `_..._` / `⚠️ **...**`,
// and the UI strings are not, so a byte comparison would either force markdown into a React tree
// or be permanently red) and BYTES for the vocabulary tokens, which must match exactly.
//
// Run:  cd apps/web && npm test
import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

const {
  PRESENCE_CELL, PRESENCE_STATUSES, MILLING_UNIT_CELL, BUCKET_UNIT_CELL,
} = await import("../src/lib/gap-status.ts");

const read = (rel) => readFile(new URL(rel, import.meta.url), "utf8");
const PAYLOAD_CARRY = await read("../../../apps/api/backend/payload_carry.py");
const SCHEMA = await read("../../../pipelines/plan_reader/01_pipeline/schema.py");

/** The quoted tokens inside a named Python tuple literal, e.g. MILLING_UNIT_STATUSES = ( ... ). */
function pyTuple(src, name) {
  const m = src.match(new RegExp(`^${name}\\s*(?::[^=]+)?=\\s*\\(([\\s\\S]*?)^\\)`, "m"));
  assert.ok(m, `${name} not found in the Python source — did it get renamed?`);
  return [...m[1].matchAll(/"([a-z_]+)"/g)].map((x) => x[1]);
}

test("the three presence tokens are byte-identical to payload_carry.py", () => {
  for (const [constant, token] of [
    ["DETECTED", "detected"],
    ["NONE_FOUND", "none_found"],
    ["EXTRACTION_FAILED", "extraction_failed"],
  ]) {
    assert.match(
      PAYLOAD_CARRY,
      new RegExp(`^${constant}\\s*=\\s*"${token}"`, "m"),
      `payload_carry.${constant} is no longer "${token}"`,
    );
    assert.ok(PRESENCE_STATUSES.includes(token), `gap-status.ts is missing "${token}"`);
  }
  // …and no EXTRA token on the TS side that the backend never emits.
  assert.equal(PRESENCE_STATUSES.length, 3);
});

test("the UI wording says what payload_carry._STATUS_LABEL says", () => {
  const label = (constant) => {
    const m = PAYLOAD_CARRY.match(new RegExp(`${constant}:\\s*"([^"]+)"`));
    assert.ok(m, `_STATUS_LABEL[${constant}] not found`);
    return m[1];
  };
  assert.match(label("NONE_FOUND"), /None stated/i);
  assert.match(PRESENCE_CELL.none_found.text, /None stated/i);
  assert.match(label("EXTRACTION_FAILED"), /Not captured/i);
  assert.match(PRESENCE_CELL.extraction_failed.text, /Not captured/i);
});

test("a legitimate empty answer and a failure never share a tone or a wording", () => {
  assert.notEqual(PRESENCE_CELL.none_found.tone, PRESENCE_CELL.extraction_failed.tone);
  assert.notEqual(PRESENCE_CELL.none_found.text, PRESENCE_CELL.extraction_failed.text);
  assert.equal(PRESENCE_CELL.extraction_failed.tone, "failure");
  assert.equal(PRESENCE_CELL.none_found.tone, "empty");
});

test("every MILLING_UNIT_STATUSES state has a UI branch, and vice versa", () => {
  const py = pyTuple(SCHEMA, "MILLING_UNIT_STATUSES");
  assert.ok(py.length >= 7, `expected the 7-state milling vocabulary, got ${py.length}`);
  for (const s of py) {
    assert.ok(MILLING_UNIT_CELL[s], `schema.py emits milling status "${s}" and the UI has no branch`);
  }
  for (const s of Object.keys(MILLING_UNIT_CELL)) {
    assert.ok(py.includes(s), `gap-status.ts has milling status "${s}" that schema.py never emits`);
  }
});

// BUCKET_UNIT_CELL is the SHAPE-DEPENDENT half (spec §5): it lands with the 2a-vs-#102 decision.
// This test is written now so that half cannot land unenforced — it self-skips while the table is
// deliberately absent, and goes live the moment someone adds it.
test("every BUCKET_UNIT_STATUSES state has a UI branch, and vice versa", (t) => {
  if (BUCKET_UNIT_CELL === undefined) {
    t.skip("BUCKET_UNIT_CELL not yet ported — held pending the capture-shape decision (spec §5)");
    return;
  }
  const py = pyTuple(SCHEMA, "BUCKET_UNIT_STATUSES");
  for (const s of py) {
    assert.ok(BUCKET_UNIT_CELL[s], `schema.py emits bucket status "${s}" and the UI has no branch`);
  }
  for (const s of Object.keys(BUCKET_UNIT_CELL)) {
    assert.ok(py.includes(s), `gap-status.ts has bucket status "${s}" that schema.py never emits`);
  }
});

test("no gap cell anywhere renders blank or a bare em dash", () => {
  const tables = [PRESENCE_CELL, MILLING_UNIT_CELL, BUCKET_UNIT_CELL ?? {}];
  for (const table of tables) {
    for (const [k, cell] of Object.entries(table)) {
      assert.ok(cell.text.trim().length > 3, `${k} renders as good as blank: ${JSON.stringify(cell.text)}`);
      assert.notEqual(cell.text.trim(), "—", `${k} renders a bare em dash`);
      assert.ok(["value", "empty", "failure"].includes(cell.tone), `${k} has tone ${cell.tone}`);
    }
  }
});

test("the carried-field labels match payload_carry._LABELS", async () => {
  const { CARRIED_LABELS } = await import("../src/lib/gap-status.ts");
  for (const [field, label] of Object.entries(CARRIED_LABELS)) {
    const m = PAYLOAD_CARRY.match(new RegExp(`"${field}":\\s*"([^"]+)"`));
    assert.ok(m, `payload_carry._LABELS has no entry for "${field}"`);
    assert.equal(label, m[1], `the card and /export name "${field}" differently`);
  }
});
