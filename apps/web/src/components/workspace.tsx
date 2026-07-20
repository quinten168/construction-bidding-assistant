"use client";

import { useState } from "react";
import { motion } from "motion/react";
import { FileText } from "lucide-react";
import { GoNoBidCard } from "./go-no-bid-card";
import { PlanViewer } from "./plan-viewer";
import { ReportPanel } from "./report/report-panel";
import { ProjectIdentity, ContractTimes } from "./blocks/plan-blocks";
import { PLAN, QUEUE, type Gotcha, type Field } from "@/lib/mock-plan";

type Selection = { page: number; evidence: string | null } | null;

export function Workspace() {
  const [sel, setSel] = useState<Selection>(null);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [reportOpen, setReportOpen] = useState(false);

  function selectGotcha(g: Gotcha) {
    setActiveId(g.id);
    setSel({ page: g.page, evidence: g.evidence });
  }
  function selectField(f: Field) {
    setActiveId(f.key);
    setSel({ page: f.page, evidence: null });
  }

  return (
    <div className="grid h-full grid-cols-[16rem_1fr_1fr] overflow-hidden">
      {/* ── Opportunity queue ─────────────────────────────── */}
      <aside className="flex flex-col border-r border-white/40 bg-white/25 backdrop-blur-xl">
        <div className="px-4 py-3">
          <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
            Opportunity queue
          </p>
        </div>
        <div className="space-y-1 px-2">
          {QUEUE.map((q) => (
            <button
              key={q.id}
              className={`flex w-full items-center justify-between rounded-lg px-3 py-2 text-left text-sm transition-colors ${
                q.active ? "bg-primary/10 text-foreground" : "hover:bg-secondary text-muted-foreground"
              }`}
            >
              <span className="flex items-center gap-2">
                <span className={q.active ? "text-primary" : "text-muted-foreground/50"}>
                  {q.active ? "●" : "○"}
                </span>
                <span className="truncate">{q.name}</span>
              </span>
              <span className="flex items-center gap-1 font-mono text-xs">
                {q.fit}
                <Trend dir={q.trend} />
              </span>
            </button>
          ))}
        </div>
        <button className="mx-2 mt-3 rounded-lg border border-dashed px-3 py-2 text-left text-sm text-muted-foreground transition-colors hover:border-primary hover:text-primary">
          + ingest plan
        </button>
      </aside>

      {/* ── Center: recommendation + gotchas + fields ─────── */}
      <main className="flex flex-col overflow-auto px-6 py-5">
        <div className="mb-1 flex items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <h1 className="font-serif text-2xl tracking-tight">{PLAN.title}</h1>
            <span className="rounded-full border px-2 py-0.5 font-mono text-[11px] text-muted-foreground">
              {PLAN.state} · {PLAN.outcome}
            </span>
          </div>
          <button
            onClick={() => setReportOpen(true)}
            className="flex shrink-0 items-center gap-1.5 rounded-xl bg-primary px-3 py-2 text-[13px] font-medium text-primary-foreground elev-sm transition-all hover:-translate-y-px hover:elev-md"
          >
            <FileText className="h-4 w-4" /> Generate report
          </button>
        </div>
        <p className="mb-4 text-sm text-muted-foreground">
          {PLAN.archetype} · {PLAN.state} · {PLAN.year} · {PLAN.pages} pages · structured extraction complete
        </p>

        <GoNoBidCard />

        {/* Clean output blocks (backlog #5) — full width so the table breathes */}
        <div className="mt-6 space-y-5">
          <ProjectIdentity />
          <ContractTimes />
        </div>

        {/* Extracted fields — each links to its source page */}
        <section className="mt-6">
          <SectionHead>Extracted fields</SectionHead>
          <div className="grid grid-cols-2 gap-2">
            {PLAN.fields.map((f) => (
              <button
                key={f.key}
                onClick={() => selectField(f)}
                className={`rounded-lg border p-3 text-left transition-colors ${
                  activeId === f.key ? "border-primary bg-primary/5" : "hover:bg-secondary"
                }`}
              >
                <div className="flex items-baseline justify-between">
                  <span className="text-xs text-muted-foreground">{f.label}</span>
                  <Conf v={f.confidence} />
                </div>
                <div className="mt-0.5 font-mono text-sm">
                  {f.value} {f.unit && <span className="text-muted-foreground">{f.unit}</span>}
                </div>
                {f.benchmark && <div className="mt-1 text-[11px] text-primary">▸ {f.benchmark}</div>}
                <div className="mt-1 font-mono text-[10px] text-muted-foreground">p.{f.page}</div>
              </button>
            ))}
          </div>
        </section>

        {/* Gotchas — the provenance list */}
        <section className="mt-6">
          <SectionHead>
            Gotchas <span className="text-muted-foreground">({PLAN.gotchas.length})</span>
          </SectionHead>
          <div className="space-y-2">
            {PLAN.gotchas.map((g, i) => (
              <motion.button
                key={g.id}
                initial={{ opacity: 0, y: 6 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: i * 0.05 }}
                onClick={() => selectGotcha(g)}
                className={`block w-full rounded-lg border p-3 text-left transition-colors ${
                  activeId === g.id ? "border-primary bg-primary/5" : "hover:bg-secondary"
                }`}
              >
                <div className="flex items-center justify-between">
                  <span className="flex items-center gap-2 text-sm font-medium">
                    <span className="text-amber-600">⚑</span> {g.title}
                  </span>
                  <span className="flex items-center gap-2">
                    <FamilyTag family={g.family} />
                    <Conf v={g.confidence} />
                  </span>
                </div>
                <p className="mt-1 text-xs text-muted-foreground">{g.explanation}</p>
                <p className="mt-2 border-l-2 border-primary/40 pl-2 font-mono text-[11px] italic leading-snug text-foreground/80">
                  “{g.evidence}”
                </p>
                <div className="mt-1.5 font-mono text-[10px] text-muted-foreground">
                  {g.section} · p.{g.page}
                </div>
              </motion.button>
            ))}
          </div>
        </section>
      </main>

      {/* ── Right: plan viewer ────────────────────────────── */}
      <section className="p-4">
        <PlanViewer page={sel?.page ?? null} evidence={sel?.evidence ?? null} />
      </section>

      {/* Standard Report artifact panel */}
      <ReportPanel open={reportOpen} onClose={() => setReportOpen(false)} />
    </div>
  );
}

function SectionHead({ children }: { children: React.ReactNode }) {
  return <h2 className="mb-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">{children}</h2>;
}

function Conf({ v }: { v: number }) {
  const pct = Math.round(v * 100);
  const tone = pct >= 90 ? "text-emerald-600" : pct >= 75 ? "text-amber-600" : "text-rose-600";
  return <span className={`font-mono text-[11px] ${tone}`}>{pct}%</span>;
}

function FamilyTag({ family }: { family: "go_no_go" | "pricing" }) {
  return (
    <span className="rounded-full border px-1.5 py-0.5 text-[10px] text-muted-foreground">
      {family === "go_no_go" ? "go/no-go" : "pricing"}
    </span>
  );
}

function Trend({ dir }: { dir: string }) {
  if (dir === "up") return <span className="text-emerald-600">▲</span>;
  if (dir === "down") return <span className="text-rose-600">▼</span>;
  return <span className="text-muted-foreground/40">—</span>;
}
