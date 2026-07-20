"use client";

import { motion } from "motion/react";
import { PLAN } from "@/lib/mock-plan";
import { Eyebrow } from "@/components/kit";

// Clean, scannable output blocks (backlog #5) — Project Identity as a two-column
// table, Contract times & phasing as compact cards. Matches the reference design.

export function ProjectIdentity() {
  return (
    <div>
      <Eyebrow>Project identity</Eyebrow>
      <div className="mt-2 overflow-hidden rounded-2xl border border-black/[0.07] bg-card/70 elev-sm">
        {PLAN.identity.map((row, i) => (
          <div
            key={row.label}
            className={`flex items-start gap-4 px-4 py-2.5 text-[13px] ${i > 0 ? "border-t border-black/[0.05]" : ""}`}
          >
            <span className="w-36 shrink-0 text-muted-foreground">{row.label}</span>
            <span className="font-medium leading-snug">{row.value}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

export function ContractTimes() {
  return (
    <div>
      <Eyebrow>Contract times &amp; phasing</Eyebrow>
      <div className="mt-2 grid grid-cols-1 gap-2.5 sm:grid-cols-3">
        {PLAN.contractTimes.map((c, i) => (
          <motion.div
            key={c.label}
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.05 * i }}
            className="rounded-2xl border border-black/[0.07] bg-card/70 p-3.5 elev-sm"
          >
            <div className="text-[11px] text-muted-foreground">{c.label}</div>
            <div className="mt-1 font-serif text-[18px] tracking-tight tnum">{c.date}</div>
            {c.note && <div className="mt-0.5 text-[11px] leading-snug text-muted-foreground">{c.note}</div>}
          </motion.div>
        ))}
      </div>
    </div>
  );
}
