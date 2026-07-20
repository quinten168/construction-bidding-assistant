"use client";

import {
  ResponsiveContainer,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Cell,
  Tooltip,
} from "recharts";
import { WORK_COLOR, type WorkType } from "@/lib/data";
import { Chip } from "@/components/kit";
import { avgMarginByWorkType, EDGE_TONE, type WorkTypeAgg } from "./helpers";

const DATA = avgMarginByWorkType();
const AXIS_TICK = { fontSize: 11, fill: "var(--muted-foreground)" } as const;

function TipCard({ active, payload }: { active?: boolean; payload?: { payload: WorkTypeAgg }[] }) {
  if (!active || !payload?.length) return null;
  const d = payload[0].payload;
  return (
    <div className="glass-strong rounded-xl px-3 py-2 text-xs shadow-xl">
      <p className="font-medium">{d.workType}</p>
      <p className="mt-0.5 text-muted-foreground tnum">
        {d.avgMargin.toFixed(1)}% avg margin · {d.n} projects · {d.edge} edge
      </p>
    </div>
  );
}

export function EdgeRanking() {
  return (
    <div className="space-y-3">
      <div className="h-[210px] w-full">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={DATA} layout="vertical" margin={{ top: 4, right: 20, bottom: 4, left: 8 }} barCategoryGap="28%">
            <CartesianGrid horizontal={false} stroke="var(--border)" strokeOpacity={0.5} strokeDasharray="3 3" />
            <XAxis
              type="number"
              domain={[0, "dataMax + 2"]}
              tick={AXIS_TICK}
              tickLine={false}
              axisLine={{ stroke: "var(--border)" }}
              tickFormatter={(v: number) => `${v}%`}
            />
            <YAxis
              type="category"
              dataKey="workType"
              tick={AXIS_TICK}
              tickLine={false}
              axisLine={false}
              width={130}
            />
            <Tooltip content={<TipCard />} cursor={{ fill: "var(--primary)", fillOpacity: 0.05 }} />
            <Bar dataKey="avgMargin" radius={[0, 6, 6, 0]}>
              {DATA.map((d) => (
                <Cell key={d.workType} fill={WORK_COLOR[d.workType as WorkType]} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>

      {/* Edge-tier legend, sorted to match the bars. */}
      <div className="flex flex-wrap gap-2">
        {DATA.map((d) => (
          <div key={d.workType} className="flex items-center gap-1.5">
            <span className="inline-block size-2 rounded-full" style={{ background: WORK_COLOR[d.workType as WorkType] }} />
            <span className="text-[11px] text-muted-foreground">{d.workType}</span>
            <Chip tone={EDGE_TONE[d.edge]}>{d.edge} edge</Chip>
          </div>
        ))}
      </div>
    </div>
  );
}
