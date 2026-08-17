"use client";

import { useMemo, useState } from "react";
import { motion } from "motion/react";
import { Check, MapPin, AlertTriangle, Pencil, ArrowRight, ShieldCheck } from "lucide-react";
import { type Extraction } from "@/lib/chat-data";
import { Glass, Eyebrow, Chip } from "@/components/kit";
import { cn } from "@/lib/utils";

// Human-in-the-loop verification: the estimator confirms or corrects what the model read BEFORE
// the rest of the report (competitor-intel generation, the slow part) runs — not as an afterthought
// once a full report already exists. Low-confidence fields are flagged for review but stay
// non-blocking; location (which plans rarely state as lat/long) gets its own dedicated block and —
// per 2026-08-05 decision, reversing the prior 2026-07-31 one — must be explicitly confirmed before
// the estimator can continue, since haul-distance and competitor scoring depend on it downstream.

// Mirrors report.py::process_pdf's `identity_fields` dict 1:1 — every key that carries
// field_confidence — with a friendly label. bid_deadline leads (right after the lat/long block
// above) since it's required, same tier as location; everything else follows in the old order.
const FIELD_LABELS: [string, string][] = [
  ["bid_deadline", "Bid deadline"],
  ["state", "State"],
  ["county", "County"],
  ["sp_number", "Project no."],
  ["location", "Location"],
  ["traffic_level", "Traffic level"],
  ["prevailing_wages", "Prevailing wage"],
  ["construction_start", "Construction start"],
  ["construction_end", "Construction end"],
  ["substantial_completion", "Substantial completion"],
  ["final_completion", "Final completion"],
];

// Required, like location: if the model didn't find these, they still get a row (not silently
// dropped) and the estimator has to type a value before it counts as confirmed — a blank bid
// deadline is a bid the firm can miss entirely, so "not detected" can't just disappear.
const REQUIRED_KEYS = new Set(["bid_deadline"]);

type VerifyField = {
  key: string;
  label: string;
  value: string;
  unit?: string;
  confidence: "high" | "medium" | "low" | null;
  page: number | null;
  reason: string | null;
  required: boolean;
};

function buildFields(extraction: Extraction): VerifyField[] {
  const out: VerifyField[] = [];
  for (const [key, label] of FIELD_LABELS) {
    const raw = extraction.identity[key];
    const required = REQUIRED_KEYS.has(key);
    if (!required && (raw == null || raw === "")) continue; // nothing extracted — nothing to verify here
    const meta = extraction.field_confidence[key];
    out.push({
      key, label, value: raw == null ? "" : String(raw),
      confidence: meta?.confidence ?? null, page: meta?.page ?? null, reason: meta?.reason ?? null,
      required,
    });
  }
  for (const q of extraction.quantities) {
    const meta = extraction.field_confidence[q.label];
    out.push({
      key: q.label, label: q.label, value: String(q.value), unit: q.unit,
      confidence: meta?.confidence ?? null, page: meta?.page ?? null, reason: meta?.reason ?? null,
      required: false,
    });
  }
  return out;
}

// bid_date_bridge.py's engine (04_tools/bid_date/bid_date.py) already reads a wide range of
// free-text date formats and writes identity.bid_deadline starting with a proper 'YYYY-MM-DD'
// (optionally followed by 'THH:MM timezone') -- but the downstream reader that scopes competitor
// capacity to "as of this date" is a SEPARATE, narrower parser (bid_projects_record.parse_bid_date,
// see final_report.py::_resolve_bid_date), and it has already been wrong once (2026-08-10: choked
// on the 'T11:00 local' suffix, silently fell back to a completion date 10 months later, reported
// zero capacity for every competitor). A human glancing at "2025-08-07" and clicking confirm
// cannot tell that the machine-readable half a different code path will actually key off of might
// not agree with what's on screen. Rather than trust that every future date-shaped string this
// pipeline ever produces stays parseable downstream, require the ISO prefix to be visibly right
// AT THE HUMAN CHECKPOINT -- the one place a mismatch is cheap to catch.
const ISO_DATE_PREFIX = /^\d{4}-\d{2}-\d{2}/;
const isBidDeadlineFormatOk = (key: string, value: string) =>
  key !== "bid_deadline" || !value || ISO_DATE_PREFIX.test(value.trim());

// The model's reason text for a quantity is one run-on paragraph enumerating every bid-schedule
// line item that fed the total ("Item 0250 ... = 16,060 TON; Item 0255 ... = 5,386 TON; ... Total
// = ... = 32,098 TON.") — reads as a wall of text. An earlier version of this split before
// specific keywords ("Item"/"line", "Total"/"total"), which kept breaking every time a different
// report phrased the same kind of clause differently (this prose is model-generated, not a fixed
// template — there is no finite keyword list that covers every wording it might use). Split on
// PUNCTUATION instead — any ';' or '.' followed by whitespace — since every clause boundary in
// this prose is marked that way regardless of what words the clause itself uses. This is why it's
// safe to split unconditionally rather than only before a recognized keyword: a decimal number
// like "12.5" has no space after its period, so it's never mistaken for a clause boundary, and a
// mid-clause abbreviation with a trailing space (rare in this domain's text) just costs an extra,
// harmless line break rather than silently failing to split at all. Frontend-only formatting of
// free text, not a structured field.
const splitReasonLines = (reason: string): string[] =>
  reason
    .split(/(?<=[;.])\s+/)
    .map((s) => s.trim())
    .filter(Boolean);

// Coordinate validation — added 2026-08-15 after a teammate caught this: the location inputs
// accepted any string ("abc" satisfied the old !loc.lat/!loc.lon non-empty check and enabled
// Confirm), which apply_verification()'s float(value) parse then silently fell back to storing
// as a raw string on failure — no crash, no error, just a report that quietly can't compute
// haul-distance/competitor scoring downstream. isValidCoord rejects that at the source: not just
// "is this text present" but "does this parse as a real latitude/longitude".
const isValidCoord = (value: string, min: number, max: number): boolean => {
  if (value.trim() === "") return false;
  const n = Number(value);
  return Number.isFinite(n) && n >= min && n <= max;
};

const needsReview = (f: Pick<VerifyField, "key" | "confidence" | "required" | "value">) =>
  f.confidence === "low" || f.confidence === "medium" || (f.required && !f.value) ||
  !isBidDeadlineFormatOk(f.key, f.value);

type FieldState = { value: string; verified: boolean; edited: boolean };

export function VerifyExtraction({
  extraction,
  onConfirm,
}: {
  extraction: Extraction;
  onConfirm: (edits: Record<string, string>) => void;
}) {
  const allFields = useMemo(() => buildFields(extraction), [extraction]);

  const [fields, setFields] = useState<Record<string, FieldState>>(() =>
    Object.fromEntries(
      allFields.map((f) => [f.key, { value: f.value, verified: !needsReview(f), edited: false }]),
    ),
  );
  const [editing, setEditing] = useState<string | null>(null);

  const origLat = extraction.identity.latitude;
  const origLon = extraction.identity.longitude;
  const [loc, setLoc] = useState({
    lat: origLat != null ? String(origLat) : "",
    lon: origLon != null ? String(origLon) : "",
    confirmed: origLat != null && origLon != null,
  });

  const setField = (k: string, patch: Partial<FieldState>) => setFields((p) => ({ ...p, [k]: { ...p[k], ...patch } }));

  const fieldsDone = allFields.filter((f) => fields[f.key]?.verified).length;
  const total = allFields.length + 1; // + location
  const done = fieldsDone + (loc.confirmed ? 1 : 0);
  const allClear = done === total;

  const lowConf = useMemo(() => allFields.filter((f) => needsReview(f)).length, [allFields]);
  const missingRequired = useMemo(() => allFields.filter((f) => f.required && !f.value).length, [allFields]);
  const anyRequiredMissing = allFields.some((f) => f.required && !fields[f.key]?.value);

  const buildEdits = (): Record<string, string> => {
    const edits: Record<string, string> = {};
    for (const f of allFields) {
      const st = fields[f.key];
      if (st?.edited) edits[f.key] = st.value;
    }
    if (loc.lat && loc.lon && (loc.lat !== (origLat != null ? String(origLat) : "") || loc.lon !== (origLon != null ? String(origLon) : ""))) {
      edits.latitude = loc.lat;
      edits.longitude = loc.lon;
    }
    return edits;
  };

  return (
    <div>
      {/* Header */}
      <div className="mb-4 flex items-start justify-between gap-3">
        <div>
          <Eyebrow>Step 2 · Human-in-the-loop</Eyebrow>
          <h2 className="mt-1 font-serif text-[22px] tracking-tight">Review &amp; confirm the read</h2>
          <p className="mt-1 max-w-lg text-[13px] text-muted-foreground">
            Your eyes on the extraction before I pull competitor intel and build the rest of the
            report. {lowConf} field{lowConf === 1 ? "" : "s"} flagged for review
            {missingRequired > 0
              ? `, ${missingRequired} required field${missingRequired === 1 ? "" : "s"} missing`
              : ""}
            {extraction.identity.latitude == null ? " and the location isn't detected" : ""} —
            everything else is high-confidence.
          </p>
        </div>
        <div className="shrink-0 text-right">
          <div className="font-serif text-2xl tnum">{done}/{total}</div>
          <div className="text-[11px] text-muted-foreground">confirmed</div>
        </div>
      </div>

      {/* Location — the domain-critical one (plans rarely state lat/long) */}
      <Glass className={cn("mb-3 p-4", !loc.confirmed && "ring-1 ring-[var(--warn)]/40")}>
        <div className="flex items-center justify-between">
          <span className="flex items-center gap-2 text-sm font-medium">
            <MapPin className="h-4 w-4 text-primary" /> Project location
          </span>
          {loc.confirmed ? (
            <Chip tone="positive"><Check className="h-3 w-3" /> confirmed</Chip>
          ) : (
            <Chip tone="warn"><AlertTriangle className="h-3 w-3" /> not detected</Chip>
          )}
        </div>
        <p className="mt-1 text-[12px] text-muted-foreground">
          {[extraction.identity.county, extraction.identity.state].filter(Boolean).join(", ") || "This plan"}.
          {loc.confirmed
            ? " Auto-computed from the route/milepost fields — confirm it or correct it below."
            : " No coordinates could be computed automatically — enter the lat/long (or paste a Google Maps pin) so haul-distance and competitor scoring can run."}
        </p>
        <div className="mt-2.5 flex flex-wrap items-center gap-2">
          <CoordInput
            label="Latitude" placeholder="47.3600" value={loc.lat}
            invalid={loc.lat.trim() !== "" && !isValidCoord(loc.lat, -90, 90)}
            onChange={(v) => setLoc((p) => ({ ...p, lat: v, confirmed: false }))}
          />
          <CoordInput
            label="Longitude" placeholder="-102.6000" value={loc.lon}
            invalid={loc.lon.trim() !== "" && !isValidCoord(loc.lon, -180, 180)}
            onChange={(v) => setLoc((p) => ({ ...p, lon: v, confirmed: false }))}
          />
          <button
            onClick={() => setLoc((p) => ({
              ...p, confirmed: isValidCoord(p.lat, -90, 90) && isValidCoord(p.lon, -180, 180),
            }))}
            disabled={!isValidCoord(loc.lat, -90, 90) || !isValidCoord(loc.lon, -180, 180)}
            className="ml-auto flex items-center gap-1.5 rounded-lg bg-primary px-3 py-2 text-[12px] font-medium text-primary-foreground transition-all hover:-translate-y-px disabled:opacity-40"
          >
            <Check className="h-3.5 w-3.5" /> Confirm location
          </button>
        </div>
        {((loc.lat.trim() !== "" && !isValidCoord(loc.lat, -90, 90))
          || (loc.lon.trim() !== "" && !isValidCoord(loc.lon, -180, 180))) && (
          <p className="mt-1.5 text-[11px] leading-snug text-[var(--warn)]">
            Latitude must be a number between -90 and 90, longitude between -180 and 180.
          </p>
        )}
      </Glass>

      {/* Fields */}
      <div className="space-y-2">
        {allFields.map((f) => {
          const st = fields[f.key];
          const missingRequired = f.required && !st.value;
          const review = needsReview({ key: f.key, confidence: f.confidence, required: f.required, value: st.value });
          const badDeadlineFormat = !isBidDeadlineFormatOk(f.key, st.value);
          // blank required field OR a bid_deadline not shaped like yyyy-mm-dd: always editable,
          // never silently skippable via a bare checkbox click (see isBidDeadlineFormatOk's
          // comment for why the format specifically, not just presence, has to be human-checked).
          const isEditing = editing === f.key || missingRequired || badDeadlineFormat;
          return (
            <Glass key={f.key} className={cn("p-3", review && !st.verified && "ring-1 ring-[var(--warn)]/40")}>
              <div className="flex items-center gap-3">
                {/* confirm toggle */}
                <button
                  onClick={() => setField(f.key, { verified: !st.verified })}
                  disabled={missingRequired || badDeadlineFormat}
                  title={missingRequired ? "Enter a value first" : badDeadlineFormat ? "Fix the date format first" : undefined}
                  className={cn(
                    "grid h-6 w-6 shrink-0 place-items-center rounded-md border transition-colors disabled:cursor-not-allowed disabled:opacity-40",
                    st.verified ? "border-[var(--positive)] bg-[var(--positive)] text-white" : "border-black/15 text-transparent hover:border-primary",
                  )}
                >
                  <Check className="h-3.5 w-3.5" />
                </button>

                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <span className="text-[12px] text-muted-foreground">{f.label}</span>
                    {missingRequired ? (
                      <Chip tone="warn"><AlertTriangle className="h-3 w-3" /> required — not detected</Chip>
                    ) : f.confidence ? (
                      review ? (
                        <Chip tone="warn">{f.confidence} confidence</Chip>
                      ) : (
                        <span className="font-mono text-[10px] text-[var(--positive)]">{f.confidence} confidence</span>
                      )
                    ) : null}
                    {st.edited && <Chip tone="primary">edited</Chip>}
                    {f.page != null && <span className="ml-auto font-mono text-[10px] text-muted-foreground/60">p.{f.page}</span>}
                  </div>
                  {isEditing ? (
                    <div>
                      <div className="mt-1 flex items-center gap-2">
                        <input
                          autoFocus={editing === f.key}
                          defaultValue={st.value}
                          placeholder={
                            missingRequired
                              ? f.key === "bid_deadline" ? "yyyy-mm-dd" : "Required — type it in"
                              : undefined
                          }
                          onKeyDown={(e) => {
                            if (e.key === "Enter") {
                              const v = (e.target as HTMLInputElement).value;
                              const formatOk = isBidDeadlineFormatOk(f.key, v);
                              setField(f.key, { value: v, edited: v !== f.value, verified: v !== "" && formatOk });
                              if (formatOk) setEditing(null); // bad format: stay open until it's fixed
                            }
                          }}
                          onBlur={(e) => {
                            const v = e.target.value;
                            const formatOk = isBidDeadlineFormatOk(f.key, v);
                            setField(f.key, { value: v, edited: v !== f.value, verified: v !== "" && formatOk });
                            if (v !== "" && formatOk) setEditing(null);
                          }}
                          className={cn(
                            "w-40 rounded-lg border bg-white/70 px-2 py-1 font-mono text-sm outline-none",
                            missingRequired || badDeadlineFormat ? "border-[var(--warn)]/50" : "border-primary/40",
                          )}
                        />
                        {f.unit && <span className="text-xs text-muted-foreground">{f.unit}</span>}
                        {!missingRequired && <span className="text-[10px] text-muted-foreground">↵ to save</span>}
                      </div>
                      {missingRequired && f.key === "bid_deadline" && (
                        <p className="mt-1 text-[11px] leading-snug text-muted-foreground">
                          Not stated anywhere in the plan — enter the bid opening / letting date
                          (yyyy-mm-dd). This is what scopes the competitor capacity numbers to
                          &quot;as of&quot; this date.
                        </p>
                      )}
                      {!missingRequired && badDeadlineFormat && (
                        <p className="mt-1 text-[11px] leading-snug text-[var(--warn)]">
                          Enter as yyyy-mm-dd — competitor capacity is scoped &quot;as of&quot; this
                          date by a different reader than the one that extracted it, and a format it
                          doesn&apos;t recognize silently falls back to a completion date instead.
                        </p>
                      )}
                    </div>
                  ) : (
                    <div className="mt-0.5 flex items-center gap-2">
                      <span className="font-mono text-sm">{st.value}{f.unit && <span className="text-muted-foreground"> {f.unit}</span>}</span>
                      <button
                        onClick={() => setEditing(f.key)}
                        className="text-muted-foreground transition-colors hover:text-primary"
                        title="Edit value"
                      >
                        <Pencil className="h-3 w-3" />
                      </button>
                    </div>
                  )}
                  {f.reason && (
                    <div className="mt-1 space-y-0.5">
                      {splitReasonLines(f.reason).map((line, i) => (
                        <p key={i} className="text-[11px] italic leading-snug text-muted-foreground/80">
                          {line}
                        </p>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            </Glass>
          );
        })}
      </div>

      {/* Footer action */}
      <motion.div layout className="mt-5 flex items-center justify-between gap-3 rounded-2xl border border-black/5 bg-white/40 p-3">
        <span className="flex items-center gap-2 text-[13px] text-muted-foreground">
          <ShieldCheck className={cn("h-4 w-4", allClear ? "text-[var(--positive)]" : "text-muted-foreground")} />
          {allClear
            ? "All fields confirmed — extraction is trusted."
            : anyRequiredMissing
              ? "Enter the required field(s) above to continue."
              : !loc.confirmed && done === total - 1
                ? "Confirm the project location to continue."
                : `${total - done} item${total - done === 1 ? "" : "s"} still need a human check.`}
        </span>
        <div className="flex items-center gap-2">
          <button
            onClick={() => onConfirm(buildEdits())}
            disabled={!loc.confirmed || anyRequiredMissing}
            className={cn(
              "flex items-center gap-1.5 rounded-xl px-4 py-2.5 text-[13px] font-medium transition-all disabled:opacity-40",
              allClear ? "bg-primary text-primary-foreground elev-sm hover:-translate-y-px hover:elev-md" : "bg-secondary text-foreground hover:bg-secondary/70",
            )}
          >
            {allClear ? "Confirm & continue" : "Save & continue"} <ArrowRight className="h-4 w-4" />
          </button>
        </div>
      </motion.div>
    </div>
  );
}

// A partial-number pattern (not the FULL isValidCoord check upstream — this only needs to allow
// everything a real number could still become mid-typing, e.g. "-", "47.", so keystrokes aren't
// rejected while the user is still in the middle of typing a valid value) — rejects letters and
// stray punctuation at the keystroke level, which is the "force the user to input a number" half
// of the fix; isValidCoord (range + finite check) upstream is the "and it has to be a real
// coordinate" half.
const PARTIAL_NUMBER = /^-?\d*\.?\d*$/;

function CoordInput({ label, placeholder, value, onChange, invalid }: {
  label: string; placeholder: string; value: string; onChange: (v: string) => void; invalid?: boolean;
}) {
  return (
    <label className="flex flex-col gap-0.5">
      <span className="text-[10px] uppercase tracking-wide text-muted-foreground">{label}</span>
      <input
        value={value}
        onChange={(e) => {
          const v = e.target.value;
          if (v === "" || PARTIAL_NUMBER.test(v)) onChange(v);
        }}
        inputMode="decimal"
        placeholder={placeholder}
        className={cn(
          "w-32 rounded-lg border bg-white/70 px-2 py-1.5 font-mono text-[13px] outline-none focus:border-primary/50",
          invalid ? "border-[var(--warn)]/60" : "border-black/10",
        )}
      />
    </label>
  );
}
