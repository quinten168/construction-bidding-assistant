// Coverage test for the competitor-name boundary in report-card.tsx (2026-08-10).
//
// `final.competitor.competitors` has arrived as `{ name, tier }` OBJECTS as well as plain strings.
// Rendering an object as a React child throws "Objects are not valid as a React child" and takes
// the whole report card down — demo-blocking. These tests render the REAL component (no mock, no
// shallow render) against the object shape that actually crashes, and assert on the rendered HTML,
// not on the input.
//
// Run:  cd apps/web && node --import ./tests/2026-08-10-register-loader.mjs \
//                          --test tests/2026-08-10-competitor-card.test.mjs
import test from "node:test";
import assert from "node:assert/strict";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

const { CompetitorSection } = await import("../src/components/chat/report-card.tsx");

const OBJECT_SHAPE = [
  { name: "KNIFE RIVER MATERIALS", tier: 1 },
  { name: "MAYO CONSTRUCTION", tier: 2 },
];

function comp(competitors, extra = {}) {
  return {
    project_id: "P", location: "Dunn, ND", county: "Dunn", state: "ND", bid_date: "2026-01-01",
    work_type: "Mill & Overlay", condition: "", materials: [], pits: {},
    summary: { analyzed: competitors.length, narrative: "" },
    competitors, attrs: {}, deep_dives: {}, stats: {}, source_file: "bid_report_TEST.md",
    _match: { confidence: "high", basis: "county+state+date", date_gap_days: 0 },
    ...extra,
  };
}

const render = (c) => renderToStaticMarkup(React.createElement(CompetitorSection, { comp: c }));

test("a competitor list of OBJECTS renders without throwing", () => {
  const html = render(comp(OBJECT_SHAPE));
  assert.match(html, /likely competitors/);
});

test("a name never renders as [object Object]", () => {
  const html = render(comp(OBJECT_SHAPE));
  assert.doesNotMatch(html, /\[object Object\]/);
  assert.match(html, /KNIFE RIVER MATERIALS/);
  assert.match(html, /MAYO CONSTRUCTION/);
  assert.doesNotMatch(html, /tier/i);
});

test("plain strings still render (the shape the backend emits today)", () => {
  const html = render(comp(["ASTECH CORP", "KNIFE RIVER MATERIALS"]));
  assert.match(html, /ASTECH CORP/);
  assert.match(html, /KNIFE RIVER MATERIALS/);
  assert.doesNotMatch(html, /\[object Object\]/);
});

test("mixed strings and objects both survive, in order", () => {
  const html = render(comp(["ASTECH CORP", { name: "KNIFE RIVER MATERIALS", tier: 1 }]));
  assert.ok(html.indexOf("ASTECH CORP") < html.indexOf("KNIFE RIVER MATERIALS"));
  assert.doesNotMatch(html, /\[object Object\]/);
});

test("object-shaped user_added still badges the right row", () => {
  const html = render(comp([...OBJECT_SHAPE, "ASTECH CORP"],
                           { user_added: [{ name: "ASTECH CORP" }] }));
  assert.match(html, /you added/i);
  assert.doesNotMatch(html, /\[object Object\]/);
});

test("an empty list reads as an empty answer, never as a failed lookup", () => {
  // The failed-lookup case is `competitor == null`, rendered by the caller as "No competitor-intel
  // report matched". An empty list must not be silently blank, or the two become the same thing.
  const html = render(comp([]));
  assert.match(html, /names no competitors/i);
  assert.doesNotMatch(html, /No competitor-intel report matched/);
});
