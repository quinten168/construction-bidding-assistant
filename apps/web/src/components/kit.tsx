"use client";

import { motion } from "motion/react";
import NumberFlow from "@number-flow/react";
import { cn } from "@/lib/utils";

// ── Glass surface ──────────────────────────────────────────────
export function Glass({
  className,
  children,
  interactive,
  ...rest
}: React.HTMLAttributes<HTMLDivElement> & { interactive?: boolean }) {
  return (
    <div
      className={cn(
        "glass sheen rounded-2xl",
        interactive && "transition-all duration-300 hover:-translate-y-0.5 hover:elev-lg",
        className,
      )}
      {...rest}
    >
      {children}
    </div>
  );
}

// ── Animated KPI stat ──────────────────────────────────────────
export function Stat({
  label,
  value,
  prefix,
  suffix,
  decimals = 0,
  delta,
  hint,
  delay = 0,
}: {
  label: string;
  value: number;
  prefix?: string;
  suffix?: string;
  decimals?: number;
  delta?: number; // signed fraction, e.g. +0.31
  hint?: string;
  delay?: number;
}) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay, type: "spring", stiffness: 200, damping: 24 }}
    >
      <Glass interactive className="p-4">
        <p className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">{label}</p>
        <div className="mt-1.5 flex items-baseline gap-1.5">
          <span className="font-serif text-[26px] leading-none tracking-tight tnum">
            {prefix}
            <NumberFlow
              value={value}
              format={{ maximumFractionDigits: decimals, minimumFractionDigits: decimals }}
              transformTiming={{ duration: 900, easing: "ease-out" }}
            />
            {suffix}
          </span>
          {delta !== undefined && (
            <span
              className={cn(
                "rounded-full px-1.5 py-0.5 text-[10px] font-medium tnum",
                delta >= 0 ? "bg-[var(--positive)]/12 text-[var(--positive)]" : "bg-[var(--negative)]/12 text-[var(--negative)]",
              )}
            >
              {delta >= 0 ? "▲" : "▼"} {Math.abs(delta * 100).toFixed(0)}%
            </span>
          )}
        </div>
        {hint && <p className="mt-1 text-[11px] text-muted-foreground">{hint}</p>}
      </Glass>
    </motion.div>
  );
}

// ── Section header ─────────────────────────────────────────────
export function SectionTitle({ children, action }: { children: React.ReactNode; action?: React.ReactNode }) {
  return (
    <div className="mb-3 flex items-center justify-between">
      <h2 className="font-serif text-lg tracking-tight">{children}</h2>
      {action}
    </div>
  );
}

export function Eyebrow({ children }: { children: React.ReactNode }) {
  return <p className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">{children}</p>;
}

// ── Pill / chip ────────────────────────────────────────────────
export function Chip({
  children,
  tone = "neutral",
  className,
}: {
  children: React.ReactNode;
  tone?: "neutral" | "positive" | "negative" | "warn" | "primary";
  className?: string;
}) {
  const tones: Record<string, string> = {
    neutral: "border-border text-muted-foreground",
    positive: "border-[var(--positive)]/30 text-[var(--positive)] bg-[var(--positive)]/8",
    negative: "border-[var(--negative)]/30 text-[var(--negative)] bg-[var(--negative)]/8",
    warn: "border-[var(--warn)]/30 text-[var(--warn)] bg-[var(--warn)]/8",
    primary: "border-primary/30 text-primary bg-primary/8",
  };
  return (
    <span className={cn("inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] font-medium", tones[tone], className)}>
      {children}
    </span>
  );
}

// ── Reveal wrapper (stagger-friendly) ──────────────────────────
export function Reveal({ children, delay = 0, className }: { children: React.ReactNode; delay?: number; className?: string }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay, type: "spring", stiffness: 180, damping: 22 }}
      className={className}
    >
      {children}
    </motion.div>
  );
}
