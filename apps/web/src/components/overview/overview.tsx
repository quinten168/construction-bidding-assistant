"use client";

import Link from "next/link";
import { motion } from "motion/react";
import NumberFlow from "@number-flow/react";
import { ArrowRight, Clock, TrendingDown, FileUp, Target, Sparkles, LineChart } from "lucide-react";
import {
  PROJECTS, FUNNEL, KPIS, WORK_COLOR, STATUS_COLOR, STATE_NAMES,
  fmtUSD, fmtPct, type Project,
} from "@/lib/data";
import { Glass, Stat, SectionTitle, Eyebrow, Chip, Reveal } from "@/components/kit";
import { cn } from "@/lib/utils";
import { BRAND } from "@/lib/brand";

const open = PROJECTS.filter((p) => p.status === "open");
const pipelineValue = open.reduce((s, p) => s + p.valueUSD, 0);
const hot = [...open].sort((a, b) => b.fit - a.fit).slice(0, 6);

// pipeline by state for the mini bars
const byState = (["MN", "ND", "SD"] as const).map((st) => ({
  state: st,
  value: open.filter((p) => p.state === st).reduce((s, p) => s + p.valueUSD, 0),
  count: open.filter((p) => p.state === st).length,
}));
const maxStateVal = Math.max(...byState.map((s) => s.value));

export function Overview() {
  return (
    <div className="mx-auto max-w-[1440px] px-8 py-8">
      {/* Greeting */}
      <Reveal>
        <div className="mb-6 flex items-end justify-between">
          <div>
            <Eyebrow>Wednesday · June 18</Eyebrow>
            <h1 className="mt-1 font-serif text-3xl tracking-tight">Good morning, {BRAND.user.name}</h1>
            <p className="mt-1 text-sm text-muted-foreground">
              <span className="text-foreground">{open.length} live opportunities</span> in the pipe ·
              {" "}3 close this week · 1 flagged as a strong fit.
            </p>
          </div>
          <Link
            href="/ingest"
            className="hidden items-center gap-1.5 rounded-xl bg-primary px-3.5 py-2 text-sm text-primary-foreground shadow-sm transition-transform hover:-translate-y-0.5 sm:flex"
          >
            Ingest a plan <ArrowRight className="h-4 w-4" />
          </Link>
        </div>
      </Reveal>

      {/* Workflow rail — orient the user: the pre-award journey, each step a doorway */}
      <Reveal delay={0.04}>
        <div className="mb-4">
          <WorkflowRail />
        </div>
      </Reveal>

      {/* KPI row */}
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat label="Pipeline value" value={pipelineValue / 1_000_000} prefix="$" suffix="M" decimals={1} hint={`${open.length} open opportunities`} delay={0.02} />
        <Stat label="Win rate" value={KPIS.winRate * 100} suffix="%" decimals={1} hint="117 of 603 bids · canonical" delay={0.06} />
        <Stat label="Avg margin" value={KPIS.avgMarginPct * 100} suffix="%" decimals={1} delta={0.04} hint="realized, trailing 12mo" delay={0.1} />
        <Stat label="Bids this month" value={KPIS.bidsThisMonth} delta={KPIS.bidsTrendPct} hint="vs same period prior" delay={0.14} />
      </div>

      <div className="mt-4 grid grid-cols-1 gap-4 lg:grid-cols-3">
        {/* Pipeline funnel */}
        <Reveal delay={0.16} className="lg:col-span-2">
          <Glass className="p-5">
            <SectionTitle action={<Chip tone="primary">last 30 days</Chip>}>Pre-award funnel</SectionTitle>
            <Funnel />
          </Glass>
        </Reveal>

        {/* Left on the table insight */}
        <Reveal delay={0.2}>
          <Glass className="flex h-full flex-col p-5">
            <div className="flex items-center gap-2">
              <span className="grid h-8 w-8 place-items-center rounded-lg bg-[var(--negative)]/12 text-[var(--negative)]">
                <TrendingDown className="h-4 w-4" />
              </span>
              <Eyebrow>Opportunity cost</Eyebrow>
            </div>
            <div className="mt-3 font-serif text-4xl tracking-tight tnum">
              $<NumberFlow value={22.3} format={{ minimumFractionDigits: 1 }} />M
            </div>
            <p className="mt-1 text-sm text-muted-foreground">
              left on the table last cycle — overbidding on jobs ultimately won at too-low prices.
            </p>
            <div className="mt-auto pt-4">
              <p className="mb-1.5 text-[11px] text-muted-foreground">Recoverable with disciplined bid/no-bid</p>
              <div className="h-2 overflow-hidden rounded-full bg-secondary">
                <motion.div initial={{ width: 0 }} animate={{ width: "68%" }} transition={{ delay: 0.4, duration: 1 }} className="h-full rounded-full bg-[var(--negative)]" />
              </div>
            </div>
          </Glass>
        </Reveal>
      </div>

      <div className="mt-4 grid grid-cols-1 gap-4 lg:grid-cols-3">
        {/* Hot opportunities */}
        <Reveal delay={0.24} className="lg:col-span-2">
          <Glass className="p-5">
            <SectionTitle action={<Link href="/opportunities" className="text-xs text-primary hover:underline">View all →</Link>}>
              Hottest opportunities
            </SectionTitle>
            <div className="space-y-1.5">
              {hot.map((p, i) => <OppRow key={p.id} p={p} i={i} />)}
            </div>
          </Glass>
        </Reveal>

        {/* Pipeline by state */}
        <Reveal delay={0.28}>
          <Glass className="flex h-full flex-col p-5">
            <SectionTitle>By territory</SectionTitle>
            <div className="space-y-4">
              {byState.map((s) => (
                <div key={s.state}>
                  <div className="mb-1 flex items-baseline justify-between text-sm">
                    <span>{STATE_NAMES[s.state]}</span>
                    <span className="text-muted-foreground tnum">{fmtUSD(s.value)} · {s.count}</span>
                  </div>
                  <div className="h-2 overflow-hidden rounded-full bg-secondary">
                    <motion.div
                      initial={{ width: 0 }}
                      animate={{ width: `${(s.value / maxStateVal) * 100}%` }}
                      transition={{ delay: 0.4, duration: 0.9, ease: "easeOut" }}
                      className="h-full rounded-full bg-primary"
                    />
                  </div>
                </div>
              ))}
            </div>
            <Link href="/map" className="mt-auto pt-4 text-xs text-primary hover:underline">Open territory map →</Link>
          </Glass>
        </Reveal>
      </div>
    </div>
  );
}

const FLOW = [
  { href: "/ingest", icon: FileUp, step: "01", title: "Ingest", desc: "Drop a plan set — it parses in seconds" },
  { href: "/opportunities", icon: Target, step: "02", title: "Read & decide", desc: "Gotchas, quantities, bid/no-bid" },
  { href: "/sweet-spot", icon: Sparkles, step: "03", title: "Find the fit", desc: "Where your edge and margin line up" },
  { href: "/pricing", icon: LineChart, step: "04", title: "Price it", desc: "Unit costs from public bid tabs" },
];

function WorkflowRail() {
  return (
    <div className="grid grid-cols-2 gap-2.5 lg:grid-cols-4">
      {FLOW.map((s, i) => {
        const Icon = s.icon;
        return (
          <motion.div key={s.href} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.06 + i * 0.05 }}>
            <Link href={s.href} className="group relative block">
              <Glass interactive className="h-full p-3.5">
                <div className="flex items-center justify-between">
                  <span className="grid h-8 w-8 place-items-center rounded-lg bg-primary/12 text-primary transition-colors group-hover:bg-primary group-hover:text-primary-foreground">
                    <Icon className="h-4 w-4" />
                  </span>
                  <span className="font-mono text-[11px] text-muted-foreground/50">{s.step}</span>
                </div>
                <div className="mt-2.5 text-sm font-medium">{s.title}</div>
                <div className="mt-0.5 text-[11px] leading-snug text-muted-foreground">{s.desc}</div>
              </Glass>
              {/* connector arrow between steps */}
              {i < FLOW.length - 1 && (
                <span className="absolute -right-2 top-1/2 z-10 hidden -translate-y-1/2 text-muted-foreground/30 lg:block">›</span>
              )}
            </Link>
          </motion.div>
        );
      })}
    </div>
  );
}

function Funnel() {
  const max = FUNNEL[0].count;
  return (
    <div className="space-y-2">
      {FUNNEL.map((stage, i) => {
        const pct = (stage.count / max) * 100;
        const conv = i > 0 ? Math.round((stage.count / FUNNEL[i - 1].count) * 100) : 100;
        return (
          <motion.div
            key={stage.stage}
            initial={{ opacity: 0, x: -8 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ delay: 0.2 + i * 0.06 }}
            className="flex items-center gap-3"
          >
            <div className="w-28 shrink-0 text-right text-xs text-muted-foreground">{stage.stage}</div>
            <div className="relative h-9 flex-1 overflow-hidden rounded-lg bg-secondary/60">
              <motion.div
                initial={{ width: 0 }}
                animate={{ width: `${pct}%` }}
                transition={{ delay: 0.25 + i * 0.06, duration: 0.7, ease: "easeOut" }}
                className="flex h-full items-center justify-between rounded-lg px-3"
                style={{ background: `color-mix(in oklch, var(--chart-1) ${90 - i * 12}%, white)` }}
              >
                <span className="text-sm font-medium text-white tnum">
                  <NumberFlow value={stage.count} />
                </span>
              </motion.div>
              <span className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-[11px] text-muted-foreground">
                {stage.note}
              </span>
            </div>
            <div className="w-10 shrink-0 text-xs tnum text-muted-foreground">{i > 0 ? `${conv}%` : ""}</div>
          </motion.div>
        );
      })}
    </div>
  );
}

function OppRow({ p, i }: { p: Project; i: number }) {
  const suggest = p.fit >= 70 ? "BID" : p.fit >= 50 ? "REVIEW" : "NO-BID";
  const tone = p.fit >= 70 ? "positive" : p.fit >= 50 ? "warn" : "negative";
  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: 0.28 + i * 0.05 }}
    >
      <Link
        href="/opportunities"
        className="group flex items-center gap-3 rounded-xl px-2 py-2 transition-colors hover:bg-white/50"
      >
        <FitRing fit={p.fit} />
        <span className="h-7 w-1 rounded-full" style={{ background: WORK_COLOR[p.workType] }} />
        <div className="min-w-0 flex-1">
          <div className="truncate text-sm font-medium">{p.name}</div>
          <div className="text-[11px] text-muted-foreground">{p.workType} · {p.state}</div>
        </div>
        {p.deadlineDays !== undefined && (
          <Chip tone={p.deadlineDays <= 7 ? "negative" : "neutral"}>
            <Clock className="h-3 w-3" /> {p.deadlineDays}d
          </Chip>
        )}
        <div className="w-16 text-right text-sm tnum">{fmtUSD(p.valueUSD)}</div>
        <Chip tone={tone as "positive" | "warn" | "negative"}>{suggest}</Chip>
      </Link>
    </motion.div>
  );
}

function FitRing({ fit }: { fit: number }) {
  const r = 13, c = 2 * Math.PI * r;
  const color = fit >= 70 ? "var(--positive)" : fit >= 50 ? "var(--warn)" : "var(--negative)";
  return (
    <div className="relative grid h-8 w-8 place-items-center">
      <svg className="h-8 w-8 -rotate-90" viewBox="0 0 32 32">
        <circle cx="16" cy="16" r={r} fill="none" stroke="var(--secondary)" strokeWidth="3" />
        <motion.circle
          cx="16" cy="16" r={r} fill="none" stroke={color} strokeWidth="3" strokeLinecap="round"
          strokeDasharray={c}
          initial={{ strokeDashoffset: c }}
          animate={{ strokeDashoffset: c - (fit / 100) * c }}
          transition={{ delay: 0.4, duration: 0.9, ease: "easeOut" }}
        />
      </svg>
      <span className="absolute text-[10px] font-medium tnum">{fit}</span>
    </div>
  );
}
