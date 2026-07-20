"use client";

// ─────────────────────────────────────────────────────────────────────────────
// The reveal: once extraction finishes, animate in a summary built from the mock
// PLAN. Title, a row of Stats, a compact preview of the first gotchas (with the
// verbatim quote as the provenance proof), and a CTA into Opportunities.
// ─────────────────────────────────────────────────────────────────────────────

import Link from "next/link";
import { motion } from "motion/react";
import { ArrowRight, CheckCircle2, RotateCcw, MapPin } from "lucide-react";
import { PLAN } from "@/lib/mock-plan";
import { fmtUSD, PROJECTS } from "@/lib/data";
import { Glass, Stat, Chip, Reveal, SectionTitle } from "@/components/kit";

// The plan's headline est. value — pull from the matching open project if present.
const PLAN_VALUE = PROJECTS.find((p) => p.id === "p-dunn")?.valueUSD ?? 4_820_000;

export function Result({ onReset }: { onReset: () => void }) {
  const topGotchas = PLAN.gotchas.slice(0, 4);

  return (
    <div className="flex flex-col gap-5">
      {/* ── Header card ── */}
      <Reveal>
        <Glass className="relative overflow-hidden p-6 sm:p-7">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div className="min-w-0">
              <div className="mb-1.5 flex items-center gap-2">
                <Chip tone="positive">
                  <CheckCircle2 className="h-3 w-3" /> Extracted
                </Chip>
                <Chip tone="primary">{PLAN.state}</Chip>
                <Chip tone="neutral">
                  <MapPin className="h-3 w-3" /> {PLAN.county} County
                </Chip>
              </div>
              <h2 className="font-serif text-[24px] leading-tight tracking-tight">{PLAN.title}</h2>
              <p className="mt-1 text-[12.5px] text-muted-foreground">
                Reconstruct/Rebuild · recommendation{" "}
                <span className="font-medium text-primary">{PLAN.recommendation}</span> · fit {PLAN.fit}/100
              </p>
            </div>
            <Chip tone="positive" className="shrink-0 px-2.5 py-1 text-[11px]">
              89.5% verbatim confidence
            </Chip>
          </div>

          {/* ── Stat row ── */}
          <div className="mt-5 grid grid-cols-2 gap-3 sm:grid-cols-4">
            <Stat label="Pages read" value={PLAN.pages} delay={0.05} />
            <Stat label="Fields extracted" value={28} delay={0.1} />
            <Stat label="Gotchas found" value={PLAN.gotchas.length} delay={0.15} />
            <Stat label="Est. value" value={PLAN_VALUE / 1_000_000} prefix="$" suffix="M" decimals={1} delay={0.2} />
          </div>
        </Glass>
      </Reveal>

      {/* ── Gotcha preview ── */}
      <Reveal delay={0.1}>
        <Glass className="p-6 sm:p-7">
          <SectionTitle action={<Chip tone="warn">{PLAN.gotchas.length} flags · 20-type taxonomy</Chip>}>
            Gotchas, with the proof
          </SectionTitle>
          <ul className="flex flex-col gap-2.5">
            {topGotchas.map((g, i) => (
              <motion.li
                key={g.id}
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.15 + i * 0.06, type: "spring", stiffness: 200, damping: 24 }}
                className="hairline rounded-xl border border-border/60 bg-white/30 p-3.5"
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="text-[13.5px] font-medium tracking-tight">{g.title}</span>
                  <div className="flex shrink-0 items-center gap-1.5">
                    <Chip tone={g.family === "pricing" ? "primary" : "warn"}>
                      {g.family === "pricing" ? "pricing" : "go / no-go"}
                    </Chip>
                    <span className="text-[10.5px] text-muted-foreground tnum">pg {g.page}</span>
                  </div>
                </div>
                <p className="mt-1.5 border-l-2 border-primary/30 pl-2.5 font-mono text-[11px] italic leading-relaxed text-muted-foreground">
                  “{g.evidence}”
                </p>
              </motion.li>
            ))}
          </ul>
        </Glass>
      </Reveal>

      {/* ── CTA row ── */}
      <Reveal delay={0.18}>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <button
            onClick={onReset}
            className="inline-flex items-center gap-1.5 rounded-xl border border-border bg-white/40 px-3.5 py-2.5 text-[13px] font-medium text-muted-foreground transition-colors hover:text-foreground"
          >
            <RotateCcw className="h-3.5 w-3.5" /> Ingest another
          </button>
          <Link
            href="/opportunities"
            className="group inline-flex items-center gap-2 rounded-xl bg-primary px-4 py-2.5 text-[13.5px] font-medium text-primary-foreground shadow-sm transition-all hover:-translate-y-0.5 hover:shadow-lg"
          >
            Open in Opportunities
            <ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-0.5" />
          </Link>
        </div>
      </Reveal>
    </div>
  );
}
