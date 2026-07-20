"use client";

import { useMemo, useState } from "react";
import { motion } from "motion/react";
import { Check, MapPin, AlertTriangle, Pencil, ArrowRight, ShieldCheck } from "lucide-react";
import { PLAN } from "@/lib/mock-plan";
import { Glass, Eyebrow, Chip } from "@/components/kit";
import { cn } from "@/lib/utils";

// Human-in-the-loop verification: the estimator confirms or corrects what the
// model read before it's trusted downstream. Low-confidence fields are flagged
// for review; location (which plans rarely state as lat/long) must be confirmed.
// This is the trust gate — the research says it drives adoption in this industry.

const REVIEW_THRESHOLD = 0.85;

type FieldState = { value: string; verified: boolean; edited: boolean };

export function VerifyExtraction({ onConfirm, onSkip }: { onConfirm: () => void; onSkip?: () => void }) {
  // Seed editable state from the extraction. High-confidence fields are pre-accepted.
  const [fields, setFields] = useState<Record<string, FieldState>>(() =>
    Object.fromEntries(
      PLAN.fields.map((f) => [f.key, { value: f.value, verified: f.confidence >= REVIEW_THRESHOLD, edited: false }]),
    ),
  );
  const [editing, setEditing] = useState<string | null>(null);
  const [loc, setLoc] = useState({ lat: "", lon: "", confirmed: false });

  const setField = (k: string, patch: Partial<FieldState>) => setFields((p) => ({ ...p, [k]: { ...p[k], ...patch } }));

  const fieldsDone = PLAN.fields.filter((f) => fields[f.key].verified).length;
  const total = PLAN.fields.length + 1; // + location
  const done = fieldsDone + (loc.confirmed ? 1 : 0);
  const allClear = done === total;

  const lowConf = useMemo(() => PLAN.fields.filter((f) => f.confidence < REVIEW_THRESHOLD).length, []);

  return (
    <div>
      {/* Header */}
      <div className="mb-4 flex items-start justify-between gap-3">
        <div>
          <Eyebrow>Step 2 · Human-in-the-loop</Eyebrow>
          <h2 className="mt-1 font-serif text-[22px] tracking-tight">Review &amp; confirm the read</h2>
          <p className="mt-1 max-w-lg text-[13px] text-muted-foreground">
            Your eyes on the AI&apos;s extraction before it&apos;s trusted. {lowConf} field{lowConf === 1 ? "" : "s"} flagged
            for review and the location needs confirming — everything else is high-confidence.
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
            <Chip tone="warn"><AlertTriangle className="h-3 w-3" /> not detected in plan</Chip>
          )}
        </div>
        <p className="mt-1 text-[12px] text-muted-foreground">
          {PLAN.county} County, {PLAN.state}. The plan shows a location map but no coordinates — enter the lat/long
          (or paste a Google Maps pin) so haul-distance and competitor scoring can run.
        </p>
        <div className="mt-2.5 flex flex-wrap items-center gap-2">
          <CoordInput label="Latitude" placeholder="47.3600" value={loc.lat} onChange={(v) => setLoc((p) => ({ ...p, lat: v, confirmed: false }))} />
          <CoordInput label="Longitude" placeholder="-102.6000" value={loc.lon} onChange={(v) => setLoc((p) => ({ ...p, lon: v, confirmed: false }))} />
          <button
            onClick={() => setLoc((p) => ({ ...p, lat: p.lat || "47.3600", lon: p.lon || "-102.6000", confirmed: true }))}
            className="ml-auto flex items-center gap-1.5 rounded-lg bg-primary px-3 py-2 text-[12px] font-medium text-primary-foreground transition-all hover:-translate-y-px"
          >
            <Check className="h-3.5 w-3.5" /> Confirm location
          </button>
        </div>
      </Glass>

      {/* Fields */}
      <div className="space-y-2">
        {PLAN.fields.map((f) => {
          const st = fields[f.key];
          const needsReview = f.confidence < REVIEW_THRESHOLD;
          const isEditing = editing === f.key;
          return (
            <Glass
              key={f.key}
              className={cn("p-3", needsReview && !st.verified && "ring-1 ring-[var(--warn)]/40")}
            >
              <div className="flex items-center gap-3">
                {/* confirm toggle */}
                <button
                  onClick={() => setField(f.key, { verified: !st.verified })}
                  className={cn(
                    "grid h-6 w-6 shrink-0 place-items-center rounded-md border transition-colors",
                    st.verified ? "border-[var(--positive)] bg-[var(--positive)] text-white" : "border-black/15 text-transparent hover:border-primary",
                  )}
                >
                  <Check className="h-3.5 w-3.5" />
                </button>

                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <span className="text-[12px] text-muted-foreground">{f.label}</span>
                    {needsReview ? (
                      <Chip tone="warn">review · {Math.round(f.confidence * 100)}%</Chip>
                    ) : (
                      <span className="font-mono text-[10px] text-[var(--positive)]">{Math.round(f.confidence * 100)}%</span>
                    )}
                    {st.edited && <Chip tone="primary">edited</Chip>}
                    <span className="ml-auto font-mono text-[10px] text-muted-foreground/60">p.{f.page}</span>
                  </div>
                  {isEditing ? (
                    <div className="mt-1 flex items-center gap-2">
                      <input
                        autoFocus
                        defaultValue={st.value}
                        onKeyDown={(e) => {
                          if (e.key === "Enter") {
                            const v = (e.target as HTMLInputElement).value;
                            setField(f.key, { value: v, edited: v !== f.value, verified: true });
                            setEditing(null);
                          }
                        }}
                        onBlur={(e) => {
                          const v = e.target.value;
                          setField(f.key, { value: v, edited: v !== f.value, verified: true });
                          setEditing(null);
                        }}
                        className="w-40 rounded-lg border border-primary/40 bg-white/70 px-2 py-1 font-mono text-sm outline-none"
                      />
                      {f.unit && <span className="text-xs text-muted-foreground">{f.unit}</span>}
                      <span className="text-[10px] text-muted-foreground">↵ to save</span>
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
          {allClear ? "All fields confirmed — extraction is trusted." : `${total - done} item${total - done === 1 ? "" : "s"} still need a human check.`}
        </span>
        <div className="flex items-center gap-2">
          {onSkip && (
            <button
              onClick={onSkip}
              className="rounded-xl px-3 py-2.5 text-[13px] font-medium text-muted-foreground transition-colors hover:text-foreground"
            >
              Skip for now
            </button>
          )}
          <button
            onClick={onConfirm}
            className={cn(
              "flex items-center gap-1.5 rounded-xl px-4 py-2.5 text-[13px] font-medium transition-all",
              allClear ? "bg-primary text-primary-foreground elev-sm hover:-translate-y-px hover:elev-md" : "bg-secondary text-foreground hover:bg-secondary/70",
            )}
          >
            {allClear ? "Confirm & save" : "Save anyway"} <ArrowRight className="h-4 w-4" />
          </button>
        </div>
      </motion.div>
    </div>
  );
}

function CoordInput({ label, placeholder, value, onChange }: { label: string; placeholder: string; value: string; onChange: (v: string) => void }) {
  return (
    <label className="flex flex-col gap-0.5">
      <span className="text-[10px] uppercase tracking-wide text-muted-foreground">{label}</span>
      <input
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className="w-32 rounded-lg border border-black/10 bg-white/70 px-2 py-1.5 font-mono text-[13px] outline-none focus:border-primary/50"
      />
    </label>
  );
}
