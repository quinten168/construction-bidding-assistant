// ── Pure helpers for the Pricing page ──────────────────────────
// Kept framework-free so both the list and the detail panel share one source of
// truth for formatting + YoY math.

import type { PriceItem } from "@/lib/data";

// Total % change across the 4-yr trend (first → last). Big LS items and cheap
// per-SY items both flow through the same formula.
export function totalChangePct(trend: PriceItem["trend"]): number {
  if (trend.length < 2) return 0;
  const first = trend[0].price;
  const last = trend[trend.length - 1].price;
  if (first === 0) return 0;
  return ((last - first) / first) * 100;
}

// Year-over-year change = last vs second-to-last point (the most recent step).
export function yoyPct(trend: PriceItem["trend"]): number {
  if (trend.length < 2) return 0;
  const prev = trend[trend.length - 2].price;
  const last = trend[trend.length - 1].price;
  if (prev === 0) return 0;
  return ((last - prev) / prev) * 100;
}

// Format a unit price. Large lump-sum dollars get $K compaction; small per-unit
// prices keep cents-grade precision so $2.40/SY doesn't collapse to $2.
export function fmtPrice(n: number): string {
  if (n >= 1000) return `$${(n / 1000).toFixed(0)}K`;
  if (n >= 100) return `$${n.toFixed(0)}`;
  return `$${n.toFixed(2)}`;
}

// Where the avg sits between low and high, clamped to [0,1] for the gauge marker.
export function avgPosition(low: number, avg: number, high: number): number {
  if (high <= low) return 0.5;
  return Math.min(1, Math.max(0, (avg - low) / (high - low)));
}
