"use client";

import {
  ResponsiveContainer,
  ScatterChart,
  Scatter,
  XAxis,
  YAxis,
  CartesianGrid,
  Cell,
  Tooltip,
  ReferenceLine,
} from "recharts";
import { PROJECTS, WORK_COLOR, type Project, type WorkType } from "@/lib/data";

// Only projects with a realized/projected margin — messiness is the X signal.
const DATA = PROJECTS.filter((p) => p.marginPct != null).map((p) => ({
  ...p,
  marginVal: p.marginPct as number,
}));

const AXIS_TICK = { fontSize: 11, fill: "var(--muted-foreground)" } as const;

// Least-squares trend line over messiness → margin (the "edge rises" story).
function trend() {
  const xs = DATA.map((d) => d.messiness);
  const ys = DATA.map((d) => d.marginVal);
  const n = xs.length;
  const mx = xs.reduce((a, b) => a + b, 0) / n;
  const my = ys.reduce((a, b) => a + b, 0) / n;
  let num = 0;
  let den = 0;
  for (let i = 0; i < n; i++) {
    num += (xs[i] - mx) * (ys[i] - my);
    den += (xs[i] - mx) ** 2;
  }
  const slope = num / den;
  const intercept = my - slope * mx;
  return [
    { messiness: 1, marginVal: slope * 1 + intercept },
    { messiness: 10, marginVal: slope * 10 + intercept },
  ];
}
const TREND = trend();

function TipCard({ active, payload }: { active?: boolean; payload?: { payload: Project & { marginVal: number } }[] }) {
  if (!active || !payload?.length) return null;
  const p = payload[0].payload;
  return (
    <div className="glass-strong rounded-xl px-3 py-2 text-xs shadow-xl">
      <p className="font-medium">{p.name}</p>
      <p className="mt-0.5 text-muted-foreground tnum">
        messiness {p.messiness}/10 · {p.marginVal.toFixed(1)}% margin
      </p>
    </div>
  );
}

export function MessinessInsight() {
  return (
    <div className="h-[230px] w-full">
      <ResponsiveContainer width="100%" height="100%">
        <ScatterChart margin={{ top: 12, right: 20, bottom: 22, left: 4 }}>
          <CartesianGrid stroke="var(--border)" strokeOpacity={0.5} strokeDasharray="3 3" />
          <XAxis
            type="number"
            dataKey="messiness"
            domain={[0, 11]}
            ticks={[2, 4, 6, 8, 10]}
            tick={AXIS_TICK}
            tickLine={false}
            axisLine={{ stroke: "var(--border)" }}
            label={{ value: "messiness (clean → messy) →", position: "insideBottom", offset: -12, fontSize: 11, fill: "var(--muted-foreground)" }}
          />
          <YAxis
            type="number"
            dataKey="marginVal"
            domain={[0, 20]}
            tick={AXIS_TICK}
            tickLine={false}
            axisLine={{ stroke: "var(--border)" }}
            tickFormatter={(v: number) => `${v}%`}
          />
          <Tooltip content={<TipCard />} cursor={{ strokeDasharray: "3 3", stroke: "var(--muted-foreground)", strokeOpacity: 0.3 }} />

          {/* Trend line: margin climbs with messiness. */}
          <ReferenceLine
            segment={[
              { x: TREND[0].messiness, y: TREND[0].marginVal },
              { x: TREND[1].messiness, y: TREND[1].marginVal },
            ]}
            stroke="var(--primary)"
            strokeWidth={2}
            strokeDasharray="5 4"
            ifOverflow="extendDomain"
          />

          <Scatter data={DATA} fillOpacity={0.85}>
            {DATA.map((p) => (
              <Cell key={p.id} fill={WORK_COLOR[p.workType as WorkType]} r={5} />
            ))}
          </Scatter>
        </ScatterChart>
      </ResponsiveContainer>
    </div>
  );
}
