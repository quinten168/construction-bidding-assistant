// Gap-state vocabulary and labels for the report card — a PORT of two Python sources:
//   apps/api/backend/payload_carry.py            (detected / none_found / extraction_failed)
//   pipelines/plan_reader/01_pipeline/schema.py  (MILLING_UNIT_STATUSES, BUCKET_UNIT_STATUSES)
//
// THE STANDING RULE, IN UI FORM: a failure and a legitimate empty answer must never share a
// rendering, and neither may render blank. Board item F2 — "if the UI has no branch for a gap
// state it must render visibly wrong, not blank" — is this file plus GapRow in report-card.tsx.
//
// This is a PORT, not a copy of convenience, and it is kept honest by
// tests/2026-08-10-status-label-parity.test.mjs, which reads both Python files as TEXT (no Python
// runtime, no cross-tree import) and asserts every status token has a counterpart BOTH ways. A
// ported table with no enforcement is exactly the four-competing-artifacts pattern this repo
// already suffers from: nothing fails when the two drift.
//
// Not date-prefixed: this is runtime source imported by name, and no file under apps/web/src is
// date-prefixed. The tests and docs this pass added are.

export type PresenceStatus = "detected" | "none_found" | "extraction_failed";

/** The full vocabulary, in payload_carry.py's order. The parity test asserts length 3. */
export const PRESENCE_STATUSES: readonly PresenceStatus[] = [
  "detected", "none_found", "extraction_failed",
] as const;

/** How a cell should LOOK, independent of what it says. Three tones, never two:
 *  value = a real answer · empty = a legitimate empty answer · failure = we never read it. */
export type GapTone = "value" | "empty" | "failure";

export type GapCell = { tone: GapTone; text: string };

// Wording deliberately echoes payload_carry._STATUS_LABEL ("None stated", "Not captured"). The
// backend strings are markdown (`_..._`, `⚠️ **...**`); these are the plain-text equivalents the
// React tree styles itself, so the parity test asserts the KEY PHRASES match, not the markup.
export const PRESENCE_CELL: Record<Exclude<PresenceStatus, "detected">, GapCell> = {
  none_found: { tone: "empty", text: "None stated in the plan" },
  extraction_failed: { tone: "failure", text: "Not captured — extraction did not return this field" },
};

const MAX_CHARS = 300; // same budget as payload_carry._MAX_CHARS

/** Presence of one carried field. A MISSING `_status` key is `extraction_failed`, never
 *  `none_found` — the same reading as payload_carry.render_value. Payloads cached before a field
 *  was plumbed through carry no status at all; treating that as "the plan has none" is the exact
 *  failure-vs-empty collapse this file exists to prevent. */
export function presenceOf(identity: Record<string, unknown>, field: string): PresenceStatus {
  const s = identity[`${field}_status`];
  if (s === "detected" || s === "none_found" || s === "extraction_failed") return s;
  return "extraction_failed";
}

/** The §① cell for one carried field. NEVER returns an empty string and never returns "—". */
export function carriedCell(identity: Record<string, unknown>, field: string): GapCell {
  const status = presenceOf(identity, field);
  if (status !== "detected") return PRESENCE_CELL[status];
  const raw = identity[field];
  // A schema cell is {value, confidence, page}; older artifacts store a bare scalar (payload_carry._unwrap).
  const unwrapped = raw && typeof raw === "object" && !Array.isArray(raw)
    ? (raw as Record<string, unknown>).value
    : raw;
  const text = String(unwrapped ?? "").replace(/\s+/g, " ").trim();
  // `detected` with nothing to show would render blank — say so rather than print a gap.
  if (!text) return PRESENCE_CELL.extraction_failed;
  return { tone: "value", text: text.length <= MAX_CHARS ? text : `${text.slice(0, MAX_CHARS).trimEnd()}…` };
}

/** Human labels for carried fields, copied VERBATIM from payload_carry._LABELS so the card and
 *  /export name the same field the same way. The parity test asserts the strings are identical. */
export const CARRIED_LABELS: Record<string, string> = {
  phasing_requirements: "Phasing",
  // The three `*_unconverted` labels are deliberately NOT here yet — they are the shape-dependent
  // half (see GAP_FIELDS in report-card.tsx). Their payload_carry._LABELS wording is
  // "Hot mix not counted (unit is not tons)" etc., ready to paste in when the capture shape lands.
};

// ── schema.MILLING_UNIT_STATUSES — 7 states, all 7 have a branch ───────────────────────────────
// Shape-independent: neither capture-shape variant touches milling_unit_status.
// `unknown` (we never read it) and `not_present` (the plan has no milling item) are the two that
// currently collapse to one blank cell; `inconsistent` is OUR reading contradicting the plan and
// must look like a problem, not like an absence.
export const MILLING_UNIT_CELL: Record<string, GapCell> = {
  sy_only: { tone: "value", text: "Measured in square yards" },
  tons_only: { tone: "empty", text: "Measured in TONS — square yards not stated, nothing converted" },
  sy_and_tons: { tone: "empty", text: "Measured in BOTH square yards and tons — the two totals are not addable" },
  other_unit: { tone: "empty", text: "Measured in another unit (CY/LF/LS/STA) — not counted" },
  not_present: { tone: "empty", text: "No milling item in this bid schedule" },
  unknown: { tone: "failure", text: "Not captured — extraction returned no milling unit" },
  inconsistent: { tone: "failure", text: "Inconsistent — the stated unit contradicts the quantities" },
};

/** The milling cell, or null when the row should not render at all. A plan that never had milling
 *  must not gain a row saying "Not captured" about a field nobody asked for — "always render
 *  everything" is the failure mode on the other side of F2. */
export function millingCell(
  identity: Record<string, unknown>,
  quantityLabels: string[],
): GapCell | null {
  const status = identity.milling_unit_status;
  if (typeof status === "string" && status) {
    return MILLING_UNIT_CELL[status]
      // A status the backend added and this table has not learned yet renders LOUDLY rather than
      // blank — that is board item F2 stated literally.
      ?? { tone: "failure", text: `Unrecognised milling unit status "${status}" — the UI has no branch for this` };
  }
  if (quantityLabels.some((l) => l.toUpperCase().startsWith("MILL"))) return MILLING_UNIT_CELL.unknown;
  return null;
}

// ── Quantity-label glosses ─────────────────────────────────────────────────────────────────────
// MILL_TON is tons of milling carried UNCONVERTED alongside MILL in square yards. The WIRE LABEL
// MUST STAY `MILL_TON`: bid_projects_record.py writes the label into the `mill_sy` column and
// competitor_predict_live.py maps "MILL" into fitted competitor weights, so renaming it downstream
// would be a silent unit corruption. Only its PRESENTATION is glossed.
export const QUANTITY_LABEL: Record<string, string> = { MILL_TON: "MILL (tons)" };

export const QUANTITY_NOTE: Record<string, string> = {
  MILL_TON:
    "Milling measured in TONS, carried unconverted. Where a plan states both, MILL (SY) and " +
    "MILL (tons) are the same work in two units and must not be added together.",
};

// ── HELD: the shape-dependent half ─────────────────────────────────────────────────────────────
// `BUCKET_UNIT_CELL` (schema.BUCKET_UNIT_STATUSES under variant 2a, or the 8-state vocabulary
// under #102) belongs here, exported with the same `Record<string, GapCell>` type. Until the
// capture shape is settled it is deliberately absent, and BOTH parity tests skip on
// `BUCKET_UNIT_CELL === undefined` rather than passing vacuously — so the half cannot land
// unenforced. Spec: docs/_spec/2026-08-10-frontend-gap-rendering.md §5.
export const BUCKET_UNIT_CELL: Record<string, GapCell> | undefined = undefined;
