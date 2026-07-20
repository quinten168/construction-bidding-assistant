"use client";

import {
  ResponsiveContainer,
  ScatterChart,
  Scatter,
  XAxis,
  YAxis,
  ZAxis,
  CartesianGrid,
  ReferenceLine,
  ReferenceArea,
  Cell,
  Tooltip,
} from "recharts";
import { WORK_COLOR, fmtUSD, type WorkType } from "@/lib/data";
import { SCORED, FIT_LINE, MARGIN_LINE, type ScoredProject } from "./helpers";

const AXIS_TICK = { fontSize: 11, fill: "var(--muted-foreground)" } as const;
const GRID_STROKE = "var(--border)";

function TipCard({ active, payload }: { active?: boolean; payload?: { payload: ScoredProject }[] }) {
  if (!active || !payload?.length) return null;
  const p = payload[0].payload;
  return (
    <div className="glass-strong rounded-xl px-3 py-2 text-xs shadow-xl">
      <p className="font-serif text-[13px] tracking-tight">{p.name}</p>
      <div className="mt-1.5 flex items-center gap-1.5 text-muted-foreground">
        <span className="inline-block size-2 rounded-full" style={{ background: WORK_COLOR[p.workType] }} />
        {p.workType} · {p.state}
      </div>
      <div className="mt-1.5 grid grid-cols-3 gap-x-3 gap-y-0.5 tnum">
        <span className="text-muted-foreground">Fit</span>
        <span className="text-muted-foreground">Margin</span>
        <span className="text-muted-foreground">Value</span>
        <span className="font-medium">{p.fit}</span>
        <span className="font-medium">{p.marginVal.toFixed(1)}%</span>
        <span className="font-medium">{fmtUSD(p.valueUSD)}</span>
      </div>
    </div>
  );
}

export function QuadrantScatter() {
  return (
    <div className="h-[420px] w-full">
      <ResponsiveContainer width="100%" height="100%">
        <ScatterChart margin={{ top: 16, right: 24, bottom: 28, left: 8 }}>
          <CartesianGrid stroke={GRID_STROKE} strokeOpacity={0.5} strokeDasharray="3 3" />

          {/* Shade the top-right "chase" quadrant in faint clay. */}
          <ReferenceArea
            x1={FIT_LINE}
            x2={100}
            y1={MARGIN_LINE}
            y2={22}
            fill="var(--primary)"
            fillOpacity={0.07}
            stroke="var(--primary)"
            strokeOpacity={0.18}
            label={{ value: "SWEET SPOT", position: "insideTopRight", fontSize: 11, fill: "var(--primary)", fontWeight: 600, dy: 6, dx: -6 }}
          />

          {/* Quadrant guide lines. */}
          <ReferenceLine x={FIT_LINE} stroke="var(--muted-foreground)" strokeOpacity={0.4} strokeDasharray="4 4" />
          <ReferenceLine y={MARGIN_LINE} stroke="var(--muted-foreground)" strokeOpacity={0.4} strokeDasharray="4 4" />

          <XAxis
            type="number"
            dataKey="fit"
            name="Fit"
            domain={[20, 100]}
            tick={AXIS_TICK}
            tickLine={false}
            axisLine={{ stroke: GRID_STROKE }}
            label={{ value: "Model fit →", position: "insideBottom", offset: -14, fontSize: 11, fill: "var(--muted-foreground)" }}
          />
          <YAxis
            type="number"
            dataKey="marginVal"
            name="Margin"
            domain={[0, 20]}
            tick={AXIS_TICK}
            tickLine={false}
            axisLine={{ stroke: GRID_STROKE }}
            tickFormatter={(v: number) => `${v}%`}
            label={{ value: "Margin →", angle: -90, position: "insideLeft", offset: 16, fontSize: 11, fill: "var(--muted-foreground)" }}
          />
          <ZAxis type="number" dataKey="valueUSD" range={[80, 700]} name="Value" />

          <Tooltip content={<TipCard />} cursor={{ strokeDasharray: "3 3", stroke: "var(--muted-foreground)", strokeOpacity: 0.3 }} />

          <Scatter data={SCORED} fillOpacity={0.85}>
            {SCORED.map((p) => (
              <Cell
                key={p.id}
                fill={WORK_COLOR[p.workType as WorkType]}
                stroke={p.inSweetSpot ? "var(--primary)" : "transparent"}
                strokeWidth={p.inSweetSpot ? 2 : 0}
              />
            ))}
          </Scatter>
        </ScatterChart>
      </ResponsiveContainer>
    </div>
  );
}
