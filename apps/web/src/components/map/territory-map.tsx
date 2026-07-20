"use client";

import { useState } from "react";
import {
  ComposableMap,
  Geographies,
  Geography,
  Marker,
  ZoomableGroup,
} from "react-simple-maps";
import { motion, AnimatePresence } from "motion/react";
import { Glass, Chip } from "@/components/kit";
import {
  PROJECTS,
  STATUS_COLOR,
  WORK_COLOR,
  STATE_NAMES,
  fmtUSD,
  type Project,
  type StateCode,
} from "@/lib/data";
import { cn } from "@/lib/utils";

// US states topojson — only MN/ND/SD are rendered (filtered by FIPS id).
const GEO_URL = "https://cdn.jsdelivr.net/npm/us-atlas@3/states-10m.json";
const TRI_STATE_FIPS = ["27", "38", "46"]; // MN · ND · SD

// Map a project's dollar value onto a bubble radius (4–14px).
const VALUE_MIN = 760_000;
const VALUE_MAX = 6_010_000;
function bubbleRadius(valueUSD: number): number {
  const t = (valueUSD - VALUE_MIN) / (VALUE_MAX - VALUE_MIN);
  const clamped = Math.max(0, Math.min(1, t));
  return 4 + clamped * 10;
}

const STATUS_LABEL: Record<Project["status"], string> = {
  won: "Won",
  lost: "Lost",
  no_bid: "No bid",
  open: "Open",
};

const STATUS_TONE: Record<Project["status"], "positive" | "negative" | "neutral" | "primary"> = {
  won: "positive",
  lost: "negative",
  no_bid: "neutral",
  open: "primary",
};

export default function TerritoryMap({ stateFilter }: { stateFilter: StateCode | "All" }) {
  // Track the hovered project + where the cursor is so we can float a tooltip.
  const [hovered, setHovered] = useState<Project | null>(null);
  const [cursor, setCursor] = useState<{ x: number; y: number }>({ x: 0, y: 0 });

  const visible =
    stateFilter === "All" ? PROJECTS : PROJECTS.filter((p) => p.state === stateFilter);

  return (
    <div
      className="relative h-full w-full"
      onMouseMove={(e) => {
        // Keep the tooltip anchored near the cursor, relative to this container.
        const rect = e.currentTarget.getBoundingClientRect();
        setCursor({ x: e.clientX - rect.left, y: e.clientY - rect.top });
      }}
    >
      <ComposableMap
        projection="geoAlbersUsa"
        width={820}
        height={560}
        style={{ width: "100%", height: "100%" }}
      >
        <ZoomableGroup center={[-100, 47]} zoom={3.6} minZoom={2.4} maxZoom={8}>
          <Geographies geography={GEO_URL}>
            {({ geographies }) =>
              geographies
                .filter((g) => TRI_STATE_FIPS.includes(g.id as string))
                .map((geo) => (
                  <Geography
                    key={geo.rsmKey}
                    geography={geo}
                    fill="var(--chart-1)"
                    fillOpacity={0.08}
                    stroke="var(--muted-foreground)"
                    strokeOpacity={0.35}
                    strokeWidth={0.5}
                    style={{
                      default: { outline: "none" },
                      hover: { outline: "none", fillOpacity: 0.14 },
                      pressed: { outline: "none" },
                    }}
                  />
                ))
            }
          </Geographies>

          {visible.map((p) => {
            const r = bubbleRadius(p.valueUSD);
            const color = STATUS_COLOR[p.status];
            const isOpen = p.status === "open";
            const active = hovered?.id === p.id;
            return (
              <Marker key={p.id} coordinates={[p.lon, p.lat]}>
                {/* Pulsing halo for live (open) opportunities */}
                {isOpen && (
                  <motion.circle
                    r={r}
                    fill="none"
                    stroke={color}
                    strokeWidth={1.2}
                    initial={{ opacity: 0.5, scale: 1 }}
                    animate={{ opacity: [0.5, 0], scale: [1, 2.4] }}
                    transition={{ duration: 2.2, repeat: Infinity, ease: "easeOut" }}
                    style={{ transformOrigin: "center" }}
                  />
                )}
                <circle
                  r={r}
                  fill={color}
                  fillOpacity={active ? 0.95 : 0.78}
                  stroke="white"
                  strokeWidth={active ? 1.6 : 1}
                  style={{ cursor: "pointer", transition: "fill-opacity 150ms" }}
                  onMouseEnter={() => setHovered(p)}
                  onMouseLeave={() => setHovered((h) => (h?.id === p.id ? null : h))}
                />
              </Marker>
            );
          })}
        </ZoomableGroup>
      </ComposableMap>

      {/* Floating glass tooltip for the hovered project */}
      <AnimatePresence>
        {hovered && (
          <motion.div
            key={hovered.id}
            initial={{ opacity: 0, y: 6, scale: 0.96 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 4, scale: 0.97 }}
            transition={{ type: "spring", stiffness: 320, damping: 26 }}
            className="pointer-events-none absolute z-30 w-60"
            style={{
              left: Math.min(cursor.x + 16, 560),
              top: Math.max(cursor.y - 12, 8),
            }}
          >
            <Glass className="glass-strong p-3">
              <div className="flex items-start justify-between gap-2">
                <p className="font-serif text-[13px] leading-tight tracking-tight">{hovered.name}</p>
                <Chip tone={STATUS_TONE[hovered.status]}>{STATUS_LABEL[hovered.status]}</Chip>
              </div>
              <p className="mt-0.5 text-[11px] text-muted-foreground">
                {hovered.county} County · {STATE_NAMES[hovered.state]}
              </p>
              <div className="mt-2 flex items-center gap-1.5 text-[11px]">
                <span
                  className="h-2 w-2 shrink-0 rounded-full"
                  style={{ background: WORK_COLOR[hovered.workType] }}
                />
                <span className="text-muted-foreground">{hovered.workType}</span>
              </div>
              <div className="mt-2 flex items-center justify-between border-t border-black/5 pt-2">
                <div>
                  <p className="text-[9px] uppercase tracking-wide text-muted-foreground">Value</p>
                  <p className="font-serif text-[15px] leading-none tnum">{fmtUSD(hovered.valueUSD)}</p>
                </div>
                <div className="text-right">
                  <p className="text-[9px] uppercase tracking-wide text-muted-foreground">Fit</p>
                  <p
                    className={cn(
                      "font-serif text-[15px] leading-none tnum",
                      hovered.fit >= 60 ? "text-[var(--positive)]" : "text-muted-foreground",
                    )}
                  >
                    {hovered.fit}
                  </p>
                </div>
              </div>
            </Glass>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
