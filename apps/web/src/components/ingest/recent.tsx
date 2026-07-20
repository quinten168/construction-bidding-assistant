"use client";

// ─────────────────────────────────────────────────────────────────────────────
// A small "Recently ingested" strip — a few PROJECTS shown as compact glass
// cards (name + state chip + fit). Light social proof that the queue is alive.
// ─────────────────────────────────────────────────────────────────────────────

import { PROJECTS } from "@/lib/data";
import { Glass, Chip, Eyebrow } from "@/components/kit";
import { cn } from "@/lib/utils";

// Pull a handful of recently "ingested" plans to show under the hero.
const RECENT = PROJECTS.filter((p) => p.status === "open").slice(0, 4);

export function RecentlyIngested() {
  return (
    <div>
      <Eyebrow>Recently ingested</Eyebrow>
      <div className="mt-2.5 grid grid-cols-1 gap-2.5 sm:grid-cols-2">
        {RECENT.map((p) => (
          <Glass key={p.id} interactive className="flex items-center justify-between gap-3 p-3.5">
            <div className="min-w-0">
              <p className="truncate text-[13px] font-medium tracking-tight">{p.name}</p>
              <p className="text-[11px] text-muted-foreground">{p.workType}</p>
            </div>
            <div className="flex shrink-0 items-center gap-2">
              <Chip tone="neutral">{p.state}</Chip>
              <span
                className={cn(
                  "rounded-full px-2 py-0.5 text-[10.5px] font-medium tnum",
                  p.fit >= 60
                    ? "bg-[var(--positive)]/12 text-[var(--positive)]"
                    : p.fit >= 45
                      ? "bg-[var(--warn)]/12 text-[var(--warn)]"
                      : "bg-black/[0.05] text-muted-foreground",
                )}
              >
                fit {p.fit}
              </span>
            </div>
          </Glass>
        ))}
      </div>
    </div>
  );
}
