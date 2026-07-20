"use client";

// ── Range gauge: low — avg — high ──────────────────────────────
// A styled track with a clay marker positioned at the avg between low and high.
// This is the literal spread an estimator prices within, so the labels read as
// the floor and ceiling of plausible unit price.

import { motion } from "motion/react";
import { avgPosition, fmtPrice } from "./pricing-utils";

export function RangeBar({ low, avg, high }: { low: number; avg: number; high: number }) {
  const pos = avgPosition(low, avg, high);
  return (
    <div className="w-full">
      <div className="mb-2 flex items-center justify-between text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
        <span>Low</span>
        <span>Estimator spread</span>
        <span>High</span>
      </div>

      {/* The track: a soft warm gradient from floor to ceiling. */}
      <div className="relative h-3 w-full rounded-full bg-[linear-gradient(90deg,color-mix(in_oklch,var(--chart-3)_30%,transparent),color-mix(in_oklch,var(--chart-1)_40%,transparent))] ring-1 ring-black/5">
        {/* The avg marker — springs to its position when the item changes. */}
        <motion.div
          className="absolute top-1/2 z-10"
          initial={false}
          animate={{ left: `${pos * 100}%` }}
          transition={{ type: "spring", stiffness: 240, damping: 26 }}
          style={{ transform: "translate(-50%, -50%)" }}
        >
          <div className="h-5 w-5 rounded-full border-2 border-white bg-primary shadow-md" />
        </motion.div>
      </div>

      <div className="mt-2 flex items-center justify-between tnum">
        <span className="text-sm font-semibold text-foreground">{fmtPrice(low)}</span>
        <span className="font-serif text-sm text-primary">avg {fmtPrice(avg)}</span>
        <span className="text-sm font-semibold text-foreground">{fmtPrice(high)}</span>
      </div>
    </div>
  );
}
