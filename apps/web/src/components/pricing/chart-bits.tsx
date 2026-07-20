"use client";

// ── Shared recharts chrome for the Pricing page ────────────────
// Glass-styled tooltip + faint warm gridline/axis defaults so every chart on
// the page reads from the same visual vocabulary (no chart junk).

import type { ReactNode } from "react";

// Axis tick styling — small + muted, reused on every <XAxis/YAxis>.
export const axisTick = { fontSize: 11, fill: "var(--muted-foreground)" } as const;

// Faint warm gridline color (the bone canvas pushed a touch darker).
export const GRID = "color-mix(in oklch, var(--muted-foreground) 18%, transparent)";

// A glass-frosted tooltip card. Recharts hands us the active payload; we render
// a tiny label + a formatted value row. `fmt` lets each chart format its own number.
export function GlassTooltip({
  active,
  payload,
  label,
  fmt,
  valueLabel = "Avg",
}: {
  active?: boolean;
  payload?: { value?: number | string; payload?: Record<string, unknown> }[];
  label?: ReactNode;
  fmt: (n: number) => string;
  valueLabel?: string;
}) {
  if (!active || !payload || payload.length === 0) return null;
  const raw = payload[0]?.value;
  const value = typeof raw === "number" ? fmt(raw) : String(raw ?? "");
  return (
    <div className="glass-strong rounded-xl px-3 py-2 text-xs shadow-lg">
      {label !== undefined && (
        <p className="mb-0.5 font-medium text-foreground">{label}</p>
      )}
      <p className="tnum text-muted-foreground">
        {valueLabel}: <span className="font-semibold text-foreground">{value}</span>
      </p>
    </div>
  );
}
