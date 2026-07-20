"use client";

// ── Detail panel for the selected PRICE_ITEM ───────────────────
// Headline (NumberFlow avg) → range gauge → 4-yr escalation area chart →
// by-state bar comparison. The whole panel cross-fades + slides when the
// selection changes (keyed motion).

import { AnimatePresence, motion } from "motion/react";
import NumberFlow from "@number-flow/react";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { TrendingUp } from "lucide-react";
import type { PriceItem } from "@/lib/data";
import { STATE_NAMES } from "@/lib/data";
import { Chip, Eyebrow, Glass, SectionTitle } from "@/components/kit";
import { axisTick, GRID, GlassTooltip } from "./chart-bits";
import { RangeBar } from "./range-bar";
import { fmtPrice, totalChangePct } from "./pricing-utils";

// State → chart color so MN/ND/SD read consistently across the page.
const STATE_COLOR: Record<string, string> = {
  MN: "var(--chart-1)",
  ND: "var(--chart-3)",
  SD: "var(--chart-4)",
};

export function DetailPanel({ item }: { item: PriceItem }) {
  const change = totalChangePct(item.trend);
  const up = change >= 0;

  // Find the hot / cheap state for the plain-language note under the bars.
  const sorted = [...item.byState].sort((a, b) => b.avg - a.avg);
  const hot = sorted[0];
  const cheap = sorted[sorted.length - 1];

  // Reference line = overall avg, drawn across the by-state bars.
  const overallAvg = item.avg;

  return (
    <AnimatePresence mode="wait">
      <motion.div
        key={item.code}
        initial={{ opacity: 0, x: 16 }}
        animate={{ opacity: 1, x: 0 }}
        exit={{ opacity: 0, x: -16 }}
        transition={{ type: "spring", stiffness: 220, damping: 26 }}
        className="flex flex-col gap-5"
      >
        {/* a. Headline ─────────────────────────────────────── */}
        <Glass className="p-6">
          <div className="flex flex-wrap items-end justify-between gap-4">
            <div>
              <Eyebrow>{item.code} · public DOT bid tabs</Eyebrow>
              <h2 className="mt-1 font-serif text-2xl tracking-tight">{item.item}</h2>
            </div>
            <Chip tone={up ? "negative" : "positive"}>
              <TrendingUp className="h-3 w-3" />
              {up ? "+" : ""}
              {change.toFixed(1)}% since {item.trend[0].year}
            </Chip>
          </div>

          <div className="mt-4 flex items-baseline gap-2">
            <span className="font-serif text-5xl leading-none tracking-tight tnum text-primary">
              <NumberFlow
                value={item.avg}
                prefix="$"
                format={{
                  maximumFractionDigits: item.avg >= 100 ? 0 : 2,
                  minimumFractionDigits: item.avg >= 100 ? 0 : 2,
                }}
                transformTiming={{ duration: 900, easing: "ease-out" }}
              />
            </span>
            <span className="text-lg text-muted-foreground">/ {item.unit}</span>
          </div>
          <p className="mt-1 text-sm text-muted-foreground">
            Statewide average across MN, ND &amp; SD lettings — the number to price against.
          </p>
        </Glass>

        {/* b. Range gauge ──────────────────────────────────── */}
        <Glass className="p-6">
          <SectionTitle>Price range</SectionTitle>
          <RangeBar low={item.low} avg={item.avg} high={item.high} />
        </Glass>

        <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
          {/* c. 4-yr escalation ────────────────────────────── */}
          <Glass className="p-6">
            <SectionTitle
              action={
                <span
                  className="tnum text-xs font-medium"
                  style={{ color: up ? "var(--negative)" : "var(--positive)" }}
                >
                  {up ? "+" : ""}
                  {change.toFixed(1)}% total
                </span>
              }
            >
              4-year escalation
            </SectionTitle>
            <div className="h-52 w-full">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={item.trend} margin={{ top: 8, right: 8, left: -8, bottom: 0 }}>
                  <defs>
                    <linearGradient id={`grad-${item.code}`} x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="var(--chart-1)" stopOpacity={0.35} />
                      <stop offset="100%" stopColor="var(--chart-1)" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid stroke={GRID} vertical={false} />
                  <XAxis dataKey="year" tick={axisTick} tickLine={false} axisLine={false} />
                  <YAxis
                    tick={axisTick}
                    tickLine={false}
                    axisLine={false}
                    width={48}
                    domain={["auto", "auto"]}
                    tickFormatter={(v: number) => fmtPrice(v)}
                  />
                  <Tooltip
                    cursor={{ stroke: GRID }}
                    content={<GlassTooltip fmt={fmtPrice} valueLabel="Unit price" />}
                  />
                  <Area
                    type="monotone"
                    dataKey="price"
                    stroke="var(--chart-1)"
                    strokeWidth={2.5}
                    fill={`url(#grad-${item.code})`}
                    dot={{ r: 3, fill: "var(--chart-1)", strokeWidth: 0 }}
                    activeDot={{ r: 5, fill: "var(--chart-1)", stroke: "white", strokeWidth: 2 }}
                  />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          </Glass>

          {/* d. By-state comparison ────────────────────────── */}
          <Glass className="p-6">
            <SectionTitle>By state</SectionTitle>
            <div className="h-52 w-full">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={item.byState} margin={{ top: 8, right: 8, left: -8, bottom: 0 }}>
                  <CartesianGrid stroke={GRID} vertical={false} />
                  <XAxis dataKey="state" tick={axisTick} tickLine={false} axisLine={false} />
                  <YAxis
                    tick={axisTick}
                    tickLine={false}
                    axisLine={false}
                    width={48}
                    domain={[0, "auto"]}
                    tickFormatter={(v: number) => fmtPrice(v)}
                  />
                  <Tooltip
                    cursor={{ fill: "color-mix(in oklch, var(--muted-foreground) 8%, transparent)" }}
                    content={<GlassTooltip fmt={fmtPrice} valueLabel="Avg" />}
                  />
                  <ReferenceLine
                    y={overallAvg}
                    stroke="var(--muted-foreground)"
                    strokeDasharray="4 4"
                    strokeOpacity={0.6}
                  />
                  <Bar dataKey="avg" radius={[6, 6, 0, 0]} maxBarSize={56}>
                    {item.byState.map((s) => (
                      <Cell key={s.state} fill={STATE_COLOR[s.state] ?? "var(--chart-2)"} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
            <p className="mt-3 text-xs text-muted-foreground">
              <span className="font-medium text-foreground">{STATE_NAMES[hot.state]}</span> runs
              hottest at {fmtPrice(hot.avg)}, while{" "}
              <span className="font-medium text-foreground">{STATE_NAMES[cheap.state]}</span> is the
              cheapest at {fmtPrice(cheap.avg)} — a{" "}
              <span className="tnum">
                {(((hot.avg - cheap.avg) / cheap.avg) * 100).toFixed(0)}%
              </span>{" "}
              spread across the border. Dashed line = statewide avg.
            </p>
          </Glass>
        </div>
      </motion.div>
    </AnimatePresence>
  );
}
