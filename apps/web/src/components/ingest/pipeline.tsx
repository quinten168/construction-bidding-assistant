"use client";

// ─────────────────────────────────────────────────────────────────────────────
// The streaming extraction pipeline — a vertical stepper that lights up stage by
// stage. Pure client-side simulation (setTimeout) so the demo "feels alive"
// without a backend. Each stage owns a label, an icon, a set of streamed log
// lines, and a live counter that ticks up with NumberFlow.
// ─────────────────────────────────────────────────────────────────────────────

import { useEffect, useRef, useState } from "react";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import NumberFlow from "@number-flow/react";
import { FileText, Boxes, ScanLine, ShieldAlert, Check, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";
import { Glass } from "@/components/kit";

// Each stage runs ~900–1400ms, streams a couple of log lines, and lands on a
// final counter value (pages parsed, sections indexed, fields, gotchas).
type Stage = {
  id: string;
  label: string;
  icon: React.ComponentType<{ className?: string; strokeWidth?: number }>;
  counterLabel: string;
  target: number;
  durationMs: number;
  logs: string[];
};

const STAGES: Stage[] = [
  {
    id: "convert",
    label: "Converting PDF → Markdown",
    icon: FileText,
    counterLabel: "pages parsed",
    target: 214,
    durationMs: 1300,
    logs: ["pymupdf4llm · 214 pages", "recovered 1,160 bid tables", "doc-type: proposal (8.5×11)"],
  },
  {
    id: "index",
    label: "Indexing sections (ChromaDB)",
    icon: Boxes,
    counterLabel: "sections indexed",
    target: 47,
    durationMs: 1100,
    logs: ["MiniLM embeddings · 3,744 chunks", "section taxonomy matched 97%", "page 47 · traffic control"],
  },
  {
    id: "extract",
    label: "Extracting fields & quantities",
    icon: ScanLine,
    counterLabel: "fields extracted",
    target: 28,
    durationMs: 1200,
    logs: ["found: 6,296 TON hot mix · pg 12", "found: 9,840 TON base aggregate", "prevailing wage: Yes (federal) · pg 53"],
  },
  {
    id: "gotchas",
    label: "Scanning 20-type gotcha taxonomy",
    icon: ShieldAlert,
    counterLabel: "gotchas found",
    target: 6,
    durationMs: 1400,
    logs: ["found: liquidated damages $1,200/day", "found: seasonal cutoff Oct 1", "found: enhanced SWPPP · Missouri River"],
  },
];

export type PipelineStatus = "idle" | "running" | "done";

export function Pipeline({ onComplete }: { onComplete: () => void }) {
  const reduce = useReducedMotion();
  // Which stage index is currently active (-1 = not started, STAGES.length = done).
  const [active, setActive] = useState(0);
  // Per-stage progress 0..1 for the progress bars.
  const [progress, setProgress] = useState<number[]>(() => STAGES.map(() => 0));
  // Per-stage live counter values that tick up to `target`.
  const [counts, setCounts] = useState<number[]>(() => STAGES.map(() => 0));
  // How many log lines are visible per stage (revealed one at a time).
  const [logsShown, setLogsShown] = useState<number[]>(() => STAGES.map(() => 0));

  // Guard so the timer chain only ever spins up once.
  const startedRef = useRef(false);

  useEffect(() => {
    if (startedRef.current) return;
    startedRef.current = true;

    const timers: ReturnType<typeof setTimeout>[] = [];

    // Walk the stages sequentially; each schedules its own sub-animations and
    // then kicks off the next stage when it finishes.
    const runStage = (i: number) => {
      if (i >= STAGES.length) {
        setActive(STAGES.length);
        timers.push(setTimeout(onComplete, 450));
        return;
      }
      setActive(i);
      const stage = STAGES[i];
      const steps = 24;
      const tick = stage.durationMs / steps;

      // Animate the progress bar + counter for this stage step by step.
      for (let s = 1; s <= steps; s++) {
        timers.push(
          setTimeout(() => {
            const frac = s / steps;
            setProgress((p) => p.map((v, idx) => (idx === i ? frac : v)));
            setCounts((c) => c.map((v, idx) => (idx === i ? Math.round(frac * stage.target) : v)));
          }, tick * s),
        );
      }

      // Reveal the streamed log lines spread across the stage's duration.
      stage.logs.forEach((_, li) => {
        timers.push(
          setTimeout(() => {
            setLogsShown((l) => l.map((v, idx) => (idx === i ? li + 1 : v)));
          }, (stage.durationMs / (stage.logs.length + 1)) * (li + 1)),
        );
      });

      // When the stage finishes, advance to the next one.
      timers.push(setTimeout(() => runStage(i + 1), stage.durationMs + 220));
    };

    runStage(0);
    return () => timers.forEach(clearTimeout);
  }, [onComplete]);

  return (
    <Glass className="p-6 sm:p-8">
      <div className="mb-5 flex items-center gap-2.5">
        <span className="relative grid h-9 w-9 place-items-center rounded-xl bg-primary/12 text-primary">
          {active < STAGES.length ? (
            <Loader2 className={cn("h-4 w-4", !reduce && "animate-spin")} strokeWidth={2.5} />
          ) : (
            <Check className="h-4 w-4" strokeWidth={2.5} />
          )}
        </span>
        <div className="leading-tight">
          <p className="font-serif text-[17px] tracking-tight">
            {active < STAGES.length ? "Reading the plan set…" : "Extraction complete"}
          </p>
          <p className="text-[12px] text-muted-foreground">2023_DUNN-CO-ND_CP-13.pdf · 18.4 MB</p>
        </div>
      </div>

      <ol className="flex flex-col gap-2.5">
        {STAGES.map((stage, i) => {
          const state: "pending" | "running" | "done" = active > i ? "done" : active === i ? "running" : "pending";
          const Icon = stage.icon;
          return (
            <li key={stage.id}>
              <motion.div
                initial={false}
                animate={{ opacity: state === "pending" ? 0.45 : 1 }}
                transition={{ duration: 0.3 }}
                className={cn(
                  "hairline rounded-xl border px-4 py-3 transition-colors",
                  state === "running" ? "border-primary/30 bg-primary/[0.04]" : "border-border/60 bg-white/30",
                )}
              >
                <div className="flex items-center gap-3">
                  <span
                    className={cn(
                      "grid h-7 w-7 shrink-0 place-items-center rounded-lg transition-colors",
                      state === "done"
                        ? "bg-[var(--positive)]/12 text-[var(--positive)]"
                        : state === "running"
                          ? "bg-primary/12 text-primary"
                          : "bg-black/[0.04] text-muted-foreground",
                    )}
                  >
                    {state === "done" ? (
                      <Check className="h-3.5 w-3.5" strokeWidth={3} />
                    ) : state === "running" ? (
                      <Loader2 className={cn("h-3.5 w-3.5", !reduce && "animate-spin")} strokeWidth={2.5} />
                    ) : (
                      <Icon className="h-3.5 w-3.5" strokeWidth={2} />
                    )}
                  </span>

                  <span className="min-w-0 flex-1 text-[13.5px] font-medium tracking-tight">{stage.label}</span>

                  <span className="shrink-0 text-right tnum">
                    <span className="font-serif text-[16px] tracking-tight text-foreground">
                      <NumberFlow value={counts[i]} transformTiming={{ duration: 500, easing: "ease-out" }} />
                    </span>
                    <span className="ml-1 text-[10.5px] text-muted-foreground">{stage.counterLabel}</span>
                  </span>
                </div>

                {/* Per-stage progress bar */}
                <div className="mt-2.5 h-1 overflow-hidden rounded-full bg-black/[0.06]">
                  <motion.div
                    className={cn("h-full rounded-full", state === "done" ? "bg-[var(--positive)]" : "bg-primary")}
                    animate={{ width: `${Math.round((progress[i] ?? 0) * 100)}%` }}
                    transition={{ duration: 0.2, ease: "easeOut" }}
                  />
                </div>

                {/* Streamed log lines (only while running, persisted once done) */}
                <AnimatePresence initial={false}>
                  {state !== "pending" && (
                    <div className="mt-2 flex flex-col gap-0.5">
                      {stage.logs.slice(0, state === "done" ? stage.logs.length : logsShown[i]).map((log, li) => (
                        <motion.p
                          key={li}
                          initial={{ opacity: 0, x: -4 }}
                          animate={{ opacity: 1, x: 0 }}
                          transition={{ duration: 0.25 }}
                          className="flex items-center gap-1.5 font-mono text-[10.5px] text-muted-foreground"
                        >
                          <span className="text-primary/70">›</span>
                          {log}
                        </motion.p>
                      ))}
                    </div>
                  )}
                </AnimatePresence>
              </motion.div>
            </li>
          );
        })}
      </ol>
    </Glass>
  );
}
