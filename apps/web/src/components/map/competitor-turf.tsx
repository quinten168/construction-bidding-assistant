"use client";

import { Glass, Chip } from "@/components/kit";
import { COMPETITORS, STATE_NAMES, fmtUSD, fmtPct, type StateCode } from "@/lib/data";
import { cn } from "@/lib/utils";

// Translate a 0..1 capacity-used figure into CSI's plain-language label.
// <0.55 = hungry (sage), >0.8 = at capacity (rose), else steady.
function capacityLabel(used: number): { text: string; tone: "positive" | "negative" | "neutral"; bar: string } {
  if (used < 0.55) return { text: "hungry", tone: "positive", bar: "var(--positive)" };
  if (used > 0.8) return { text: "at capacity", tone: "negative", bar: "var(--negative)" };
  return { text: "steady", tone: "neutral", bar: "var(--chart-2)" };
}

export function CompetitorTurf({ stateFilter }: { stateFilter: StateCode | "All" }) {
  // Show competitors whose home turf matches the selected state (or all), busiest first.
  const rows = COMPETITORS.filter((c) => stateFilter === "All" || c.turf === stateFilter).sort(
    (a, b) => b.bids - a.bids,
  );

  return (
    <Glass className="p-4">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="font-serif text-lg tracking-tight">Competitor turf</h2>
        <Chip tone="neutral">
          {stateFilter === "All" ? "Tri-state" : STATE_NAMES[stateFilter]}
        </Chip>
      </div>

      {rows.length === 0 ? (
        <p className="py-6 text-center text-sm text-muted-foreground">No tracked rivals on this turf.</p>
      ) : (
        <div className="flex flex-col gap-3">
          {rows.map((c) => {
            const cap = capacityLabel(c.capacityUsedPct);
            return (
              <div key={c.name} className="rounded-xl border border-black/5 bg-white/30 p-3">
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <p className="truncate text-[13px] font-medium">{c.name}</p>
                    <p className="text-[11px] text-muted-foreground">{c.bids} bids tracked</p>
                  </div>
                  <Chip tone="primary">{c.turf}</Chip>
                </div>

                {/* Capacity bar — how full their book is this season */}
                <div className="mt-2.5">
                  <div className="mb-1 flex items-center justify-between text-[10px]">
                    <span className="uppercase tracking-wide text-muted-foreground">Capacity</span>
                    <span className={cn("font-medium tnum")} style={{ color: cap.bar }}>
                      {fmtPct(c.capacityUsedPct)} · {cap.text}
                    </span>
                  </div>
                  <div className="h-1.5 w-full overflow-hidden rounded-full bg-black/8">
                    <div
                      className="h-full rounded-full transition-all"
                      style={{ width: `${Math.round(c.capacityUsedPct * 100)}%`, background: cap.bar }}
                    />
                  </div>
                </div>

                <div className="mt-2.5 flex items-center justify-between text-[11px] text-muted-foreground">
                  <span>
                    Win rate <span className="tnum font-medium text-foreground">{fmtPct(c.winRate)}</span>
                  </span>
                  <span>
                    Avg <span className="tnum font-medium text-foreground">{fmtUSD(c.avgProjectUSD)}</span>
                  </span>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </Glass>
  );
}
