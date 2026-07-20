"use client";

// ── Master list: selectable PRICE_ITEMS rows ───────────────────
// Each row is a glass strip showing the item, its code/unit, the current avg in
// a big tabular number, and a tiny YoY chip computed from the trend endpoints.
// The selected row gets a clay ring + lifted surface.

import { motion } from "motion/react";
import { ArrowDownRight, ArrowUpRight } from "lucide-react";
import type { PriceItem } from "@/lib/data";
import { cn } from "@/lib/utils";
import { yoyPct, fmtPrice } from "./pricing-utils";

export function ItemList({
  items,
  selected,
  onSelect,
}: {
  items: PriceItem[];
  selected: string;
  onSelect: (code: string) => void;
}) {
  return (
    <div className="flex flex-col gap-2">
      {items.map((it, i) => {
        const yoy = yoyPct(it.trend);
        const up = yoy >= 0;
        const active = it.code === selected;
        return (
          <motion.button
            key={it.code}
            type="button"
            onClick={() => onSelect(it.code)}
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.04 * i, type: "spring", stiffness: 200, damping: 24 }}
            className={cn(
              "glass sheen group w-full rounded-2xl px-4 py-3 text-left transition-all duration-300",
              active
                ? "shadow-lg ring-2 ring-primary/50 -translate-y-0.5"
                : "hover:-translate-y-0.5 hover:shadow-md ring-1 ring-transparent",
            )}
          >
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <p
                  className={cn(
                    "truncate text-sm font-medium",
                    active ? "text-foreground" : "text-foreground/90",
                  )}
                >
                  {it.item}
                </p>
                <p className="mt-0.5 text-[11px] text-muted-foreground tnum">
                  {it.code} · per {it.unit}
                </p>
              </div>
              <div className="shrink-0 text-right">
                <p className="font-serif text-lg leading-none tracking-tight tnum">
                  {fmtPrice(it.avg)}
                </p>
                <span
                  className={cn(
                    "mt-1 inline-flex items-center gap-0.5 rounded-full px-1.5 py-0.5 text-[10px] font-medium tnum",
                    up
                      ? "bg-[var(--positive)]/12 text-[var(--positive)]"
                      : "bg-[var(--negative)]/12 text-[var(--negative)]",
                  )}
                >
                  {up ? <ArrowUpRight className="h-2.5 w-2.5" /> : <ArrowDownRight className="h-2.5 w-2.5" />}
                  {Math.abs(yoy).toFixed(1)}%
                </span>
              </div>
            </div>
          </motion.button>
        );
      })}
    </div>
  );
}
