"use client";

import { motion } from "motion/react";
import { PLAN } from "@/lib/mock-plan";

// The generative-UI hero card: a streamed-in bid recommendation with rationale
// + confidence. In production this is what the model returns as a component.
export function GoNoBidCard() {
  const verdict = PLAN.recommendation;
  const pct = Math.round(PLAN.confidence * 100);

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ type: "spring", stiffness: 220, damping: 26 }}
      className="glass sheen rounded-2xl p-5"
    >
      <div className="flex items-baseline justify-between">
        <div className="flex items-center gap-2">
          <span className="text-primary">◆</span>
          <span className="font-serif text-lg font-medium tracking-tight">
            Recommend: {verdict === "BID" ? "Bid" : verdict === "NO_BID" ? "No-Bid" : "Review"}
          </span>
        </div>
        <ConfidenceMeter pct={pct} />
      </div>

      <div className="mt-4 grid gap-3 sm:grid-cols-2">
        <div>
          <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Why bid</p>
          <ul className="mt-1.5 space-y-1.5">
            {PLAN.rationale.map((r, i) => (
              <motion.li
                key={i}
                initial={{ opacity: 0, x: -6 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: 0.15 + i * 0.08 }}
                className="text-sm leading-snug"
              >
                <span className="text-primary">›</span> {r}
              </motion.li>
            ))}
          </ul>
        </div>
        <div>
          <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Risks to price in</p>
          <ul className="mt-1.5 space-y-1.5">
            {PLAN.risks.map((r, i) => (
              <motion.li
                key={i}
                initial={{ opacity: 0, x: -6 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: 0.3 + i * 0.08 }}
                className="text-sm leading-snug text-muted-foreground"
              >
                <span className="text-amber-600">⚑</span> {r}
              </motion.li>
            ))}
          </ul>
        </div>
      </div>
    </motion.div>
  );
}

function ConfidenceMeter({ pct }: { pct: number }) {
  return (
    <div className="flex items-center gap-2">
      <div className="h-1.5 w-20 overflow-hidden rounded-full bg-secondary">
        <motion.div
          className="h-full bg-primary"
          initial={{ width: 0 }}
          animate={{ width: `${pct}%` }}
          transition={{ delay: 0.2, duration: 0.8, ease: "easeOut" }}
        />
      </div>
      <span className="font-mono text-sm tabular-nums text-muted-foreground">{pct}%</span>
    </div>
  );
}
