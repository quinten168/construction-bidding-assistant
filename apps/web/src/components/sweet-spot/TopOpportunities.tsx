"use client";

import { Star, ArrowUpRight } from "lucide-react";
import { Glass, Chip, Reveal } from "@/components/kit";
import { WORK_COLOR, fmtUSD, type WorkType } from "@/lib/data";
import { SCORED, FIT_LINE } from "./helpers";

// Open opportunities only, ranked by sweet-spot score (fit × margin) desc.
const OPEN = SCORED.filter((p) => p.status === "open").sort((a, b) => b.score - a.score);
const MAX_FIT = 100;

export function TopOpportunities() {
  return (
    <div className="space-y-2">
      {OPEN.map((p, i) => (
        <Reveal key={p.id} delay={0.04 * i}>
          <Glass interactive className="flex items-center gap-4 p-3.5">
            {/* work-type dot */}
            <span
              className="size-2.5 shrink-0 rounded-full"
              style={{ background: WORK_COLOR[p.workType as WorkType] }}
              title={p.workType}
            />

            {/* name + meta */}
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2">
                <p className="truncate text-sm font-medium">{p.name}</p>
                {p.inSweetSpot && (
                  <Chip tone="primary">
                    <Star className="size-2.5 fill-current" /> sweet spot
                  </Chip>
                )}
              </div>
              <div className="mt-1 flex items-center gap-2 text-[11px] text-muted-foreground">
                <Chip>{p.state}</Chip>
                <span>{p.workType}</span>
                {p.deadlineDays != null && <span>· {p.deadlineDays}d left</span>}
              </div>
            </div>

            {/* fit mini-bar */}
            <div className="hidden w-28 sm:block">
              <div className="flex items-center justify-between text-[10px] text-muted-foreground">
                <span>fit</span>
                <span className="tnum font-medium text-[color:var(--foreground)]">{p.fit}</span>
              </div>
              <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-border/60">
                <div
                  className="h-full rounded-full"
                  style={{
                    width: `${(p.fit / MAX_FIT) * 100}%`,
                    background: p.fit >= FIT_LINE ? "var(--primary)" : "var(--muted-foreground)",
                  }}
                />
              </div>
            </div>

            {/* margin */}
            <div className="hidden w-16 text-right sm:block">
              <p className="text-[10px] text-muted-foreground">margin</p>
              <p className="tnum text-sm font-medium">{p.marginVal.toFixed(1)}%</p>
            </div>

            {/* value */}
            <div className="w-16 text-right">
              <p className="text-[10px] text-muted-foreground">value</p>
              <p className="tnum text-sm font-medium">{fmtUSD(p.valueUSD)}</p>
            </div>

            <ArrowUpRight className="size-4 shrink-0 text-muted-foreground" />
          </Glass>
        </Reveal>
      ))}
    </div>
  );
}
