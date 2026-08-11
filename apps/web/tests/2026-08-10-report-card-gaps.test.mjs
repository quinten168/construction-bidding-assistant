// T1–T7, T9, T10 — COVERAGE FOR BOARD ITEM F2: "if the UI has no branch for a gap state it must
// render visibly wrong, not blank."
//
// Before this, `report-card.tsx` had exactly two gap behaviours and F2 bans both of them:
//   1. the row DISAPPEARS   (`IDENTITY_LABELS.filter(...)` — an absent field became an absent row)
//   2. an EM DASH           (`fmtVal` → "—" — a failure and a legitimate empty answer, identical)
// 9 of the 14 cached payloads carry at least one gap state, so this is the majority path through
// the demo corpus, not an edge case.
//
// Style follows tests/2026-08-10-competitor-card.test.mjs: render the REAL component through
// react-dom/server and assert on the emitted HTML, never on the input.
//
// Run:  cd apps/web && npm test
import test from "node:test";
import assert from "node:assert/strict";
import { readdir, readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

const { ReportCard, copyReportMarkdown } = await import("../src/components/chat/report-card.tsx");
const { MILLING_UNIT_CELL, BUCKET_UNIT_CELL } = await import("../src/lib/gap-status.ts");

// ── helpers ────────────────────────────────────────────────────────────────
function final(identity = {}, extra = {}) {
  return {
    plan_id: "TEST", title: "Test Plan", archetype: "Mill & Overlay", pages: 10,
    identity: { state: "ND", county: "Dunn", ...identity },
    tldr: "", quantities: [], gotchas: { go_no_go: [], pricing: [] }, competitor: null,
    ...extra,
  };
}
const render = (f) => renderToStaticMarkup(React.createElement(ReportCard, { final: f }));

/** Every `<dd …>…</dd>` that carries a data-gap attribute, as { tone, inner, text }. */
function gapCells(html) {
  return [...html.matchAll(/<dd\b([^>]*\bdata-gap="([^"]*)"[^>]*)>([\s\S]*?)<\/dd>/g)].map((m) => ({
    attrs: m[1],
    tone: m[2],
    inner: m[3],
    text: m[3].replace(/<[^>]*>/g, "").replace(/&#?[a-z0-9]+;/gi, " ").replace(/\s+/g, " ").trim(),
  }));
}
const strip = (html) => html.replace(/<[^>]*>/g, " ");

// ── T1 · the headline F2 case ──────────────────────────────────────────────
test("T1 — extraction_failed renders 'Not captured' instead of vanishing", () => {
  const html = render(final({ phasing_requirements: null, phasing_requirements_status: "extraction_failed" }));
  assert.match(strip(html), /Not captured/);
  assert.match(strip(html), /Phasing/);
});

// ── T2 · never blank, never a bare em dash ─────────────────────────────────
test("T2 — no gap cell is ever empty or a bare em dash", () => {
  const html = render(final({
    phasing_requirements: null, phasing_requirements_status: "extraction_failed",
    milling_unit_status: "unknown",
  }));
  const cells = gapCells(html);
  assert.ok(cells.length > 0, "expected at least one data-gap cell to exist at all");
  for (const c of cells) {
    assert.notEqual(c.inner.trim(), "", `an empty <dd data-gap="${c.tone}"> reached the DOM`);
    assert.notEqual(c.text, "—", `a bare em dash reached a <dd data-gap="${c.tone}">`);
    assert.ok(c.text.length > 3, `a gap cell rendered as good as blank: ${JSON.stringify(c.text)}`);
  }
});

// ── T3 · the standing rule, asserted directly ──────────────────────────────
test("T3 — 'the plan says none' and 'we never read it' never look the same", () => {
  const none = render(final({ phasing_requirements: null, phasing_requirements_status: "none_found" }));
  const failed = render(final({ phasing_requirements: null, phasing_requirements_status: "extraction_failed" }));

  const noneCell = gapCells(none).find((c) => c.text.length);
  const failedCell = gapCells(failed).find((c) => c.tone === "failure");
  assert.ok(noneCell, "none_found produced no gap cell");
  assert.ok(failedCell, "extraction_failed produced no failure-toned gap cell");

  assert.equal(noneCell.tone, "empty");
  assert.equal(failedCell.tone, "failure");
  assert.notEqual(noneCell.text, failedCell.text);
  assert.match(noneCell.text, /None stated/i);
  assert.match(failedCell.text, /Not captured/i);
});

// ── T4 · the stale-cache case ──────────────────────────────────────────────
test("T4 — a MISSING _status key reads as extraction_failed, never as none_found", () => {
  // No `phasing_requirements_status` at all: a payload cached before the field was plumbed
  // through. Reporting that as "this plan has no phasing" is the exact failure-vs-empty collapse
  // the whole feature exists to prevent (mirrors payload_carry.render_value).
  const html = render(final({ phasing_requirements: null }));
  const text = strip(html);
  assert.match(text, /Not captured/);
  assert.doesNotMatch(text, /None stated/);
  assert.ok(gapCells(html).some((c) => c.tone === "failure"));
});

// ── T5 · milling unit status (spec §4 / §7) ────────────────────────────────
test("T5 — milling_unit_status: inconsistent is loud, and unknown ≠ not_present", () => {
  const inconsistent = render(final({ milling_unit_status: "inconsistent" }));
  assert.ok(gapCells(inconsistent).some((c) => c.tone === "failure" && /Inconsistent/i.test(c.text)),
    "an 'inconsistent' milling unit — our reading contradicting the plan — rendered without a failure tone");

  const unknown = gapCells(render(final({ milling_unit_status: "unknown" })));
  const notPresent = gapCells(render(final({ milling_unit_status: "not_present" })));
  const u = unknown.find((c) => /milling|captured/i.test(c.text) || c.tone === "failure");
  const n = notPresent.find((c) => /milling/i.test(c.text));
  assert.ok(u && n, "expected a milling row for both unknown and not_present");
  assert.notEqual(u.text, n.text, "'we never read it' and 'there is no milling item' render identically");
  assert.equal(u.tone, "failure");
  assert.equal(n.tone, "empty");
});

test("T5b — the milling row is suppressed when there is no status and no MILL item", () => {
  // "Always render everything" is the failure mode on the OTHER side of F2: a plan that never had
  // milling must not gain a row saying "Not captured" about a field nobody asked for.
  const html = render(final({}, { quantities: [{ label: "GRADE", value: 100, unit: "CY" }] }));
  assert.doesNotMatch(strip(html), /Milling measured in/);
  // …but a MILL quantity with no status key DOES surface the row.
  const withMill = render(final({}, { quantities: [{ label: "MILL", value: 100, unit: "SY" }] }));
  assert.match(strip(withMill), /Milling measured in/);
});

// ── T6 · MILL_TON gloss ────────────────────────────────────────────────────
test("T6 — MILL_TON is glossed and footnoted, and the wire label is unchanged elsewhere", () => {
  const html = render(final({}, { quantities: [{ label: "MILL_TON", value: 4200, unit: "TON" }] }));
  const text = strip(html);
  assert.match(text, /MILL \(tons\)/, "MILL_TON still reads as a typo to an estimator");
  assert.match(text, /not be added together|not addable/i, "the not-addable footnote is missing");

  const without = strip(render(final({}, { quantities: [{ label: "MILL", value: 9, unit: "SY" }] })));
  assert.doesNotMatch(without, /not be added together|not addable/i,
    "the MILL_TON footnote rendered on a payload that has no MILL_TON row");
});

// ── T7 · iterate the WHOLE vocabulary, not a hand-listed subset ────────────
// "A negative result from a fixed set of checks is not proof of absence" (CLAUDE.md). Hand-listing
// the states we happen to remember proves nothing about a NEW backend state; iterating the table
// means a state added upstream with no UI branch fails here instead of on an estimator's screen.
test("T7 — every milling status in the table renders visible, non-blank, non-em-dash text", () => {
  for (const [status, cell] of Object.entries(MILLING_UNIT_CELL)) {
    const html = render(final({ milling_unit_status: status }));
    const cells = gapCells(html);
    const hit = cells.find((c) => c.text === cell.text.trim());
    assert.ok(hit, `milling status "${status}" did not render its cell text`);
    assert.notEqual(hit.text, "—", `milling status "${status}" rendered a bare em dash`);
    assert.ok(hit.text.length > 3, `milling status "${status}" rendered as good as blank`);
    assert.equal(hit.tone, cell.tone);
  }
});

test("T7b — every bucket status in the table renders (skips while the table is held)", (t) => {
  if (BUCKET_UNIT_CELL === undefined) {
    t.skip("BUCKET_UNIT_CELL not yet ported — held pending the capture-shape decision (spec §5)");
    return;
  }
  for (const [status, cell] of Object.entries(BUCKET_UNIT_CELL)) {
    assert.ok(cell.text.trim().length > 3, `bucket status "${status}" is blank in the table`);
  }
});

// ── T9 · the clipboard must not silently produce a SHORTER report ──────────
test("T9 — copy posts to /api/report/export with fmt:md and copies exactly what came back", async () => {
  const calls = [];
  const written = [];
  const f = final({ phasing_requirements_status: "extraction_failed" });
  const err = await copyReportMarkdown(f, {
    fetch: async (url, init) => {
      calls.push({ url, init });
      return new Response("# Real export\n- **Phasing:** ⚠️ **Not captured**\n", { status: 200 });
    },
    writeText: async (t2) => { written.push(t2); },
  });
  assert.equal(err, null);
  assert.equal(calls.length, 1);
  assert.equal(calls[0].url, "/api/report/export");
  assert.equal(JSON.parse(calls[0].init.body).fmt, "md");
  assert.deepEqual(JSON.parse(calls[0].init.body).final, JSON.parse(JSON.stringify(f)));
  assert.deepEqual(written, ["# Real export\n- **Phasing:** ⚠️ **Not captured**\n"]);
});

test("T9b — on a non-200 it errors and copies NOTHING (never a shorter report)", async () => {
  const written = [];
  const err = await copyReportMarkdown(final(), {
    fetch: async () => new Response("nope", { status: 500 }),
    writeText: async (t2) => { written.push(t2); },
  });
  assert.ok(err, "a failed export returned no error");
  assert.match(err, /500|fail/i);
  assert.deepEqual(written, [], "a failed export still wrote something to the clipboard");
});

test("T9c — a transport failure and an empty export each error, and copy nothing", async () => {
  for (const stub of [
    async () => { throw new Error("network down"); },
    async () => new Response("   ", { status: 200 }),
  ]) {
    const written = [];
    const err = await copyReportMarkdown(final(), { fetch: stub, writeText: async (t2) => written.push(t2) });
    assert.ok(err, "expected an error string");
    assert.deepEqual(written, []);
  }
});

// ── T10 · the REAL corpus, not invented payloads ───────────────────────────
const CACHE = fileURLToPath(new URL("../../../pipelines/plan_reader/00_input/_report_payload_cache/", import.meta.url));

test("T10 — every cached payload renders with no blank gap cell", async (t) => {
  // The cache is gitignored, so a fresh clone has no directory at all — that skips. A directory
  // that EXISTS and is EMPTY must fail: a fixture test that passes with zero fixtures is the
  // "success signal at the wrong layer" this repo keeps hitting (CLAUDE.md).
  let names;
  try {
    names = (await readdir(CACHE)).filter((n) => n.endsWith(".json"));
  } catch {
    t.skip("payload cache absent — regenerate per pipelines/plan_reader/README.md");
    return;
  }
  assert.ok(names.length > 0, `${CACHE} exists but holds no payloads — refusing to pass on zero fixtures`);

  let sawGap = 0;
  for (const name of names) {
    const p = JSON.parse(await readFile(CACHE + name, "utf8"));
    const html = render(final(p.identity ?? {}, {
      plan_id: p.plan_id ?? name, quantities: p.quantities ?? [],
    }));
    const cells = gapCells(html);
    assert.ok(cells.length > 0, `${name} rendered no gap cell at all`);
    for (const c of cells) {
      assert.notEqual(c.inner.trim(), "", `${name}: empty <dd data-gap="${c.tone}">`);
      assert.notEqual(c.text, "—", `${name}: bare em dash in a gap cell`);
    }
    if (cells.some((c) => c.tone !== "value")) sawGap += 1;
  }
  // The corpus is 9-of-14 gap-bearing; if this ever drops to zero the fixtures stopped exercising
  // the branch and the test above became vacuous.
  assert.ok(sawGap > 0, "no cached payload exercised a gap state — the fixture set went vacuous");
});
