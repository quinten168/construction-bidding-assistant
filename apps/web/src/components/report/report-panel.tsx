"use client";

import { useEffect, useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { FileText, FileDown, X, Check, Loader2, Sparkles, Copy } from "lucide-react";
import { buildReport, reportMarkdown, reportCSV, downloadText, downloadPDF } from "@/lib/report";
import { PLAN } from "@/lib/mock-plan";
import { cn } from "@/lib/utils";

// Markdown styling for the report body (compact, document-like).
const MD = {
  p: (p: React.HTMLAttributes<HTMLParagraphElement>) => <p className="my-1.5 text-[13px] leading-relaxed" {...p} />,
  ul: (p: React.HTMLAttributes<HTMLUListElement>) => <ul className="my-1.5 space-y-1" {...p} />,
  li: (p: React.HTMLAttributes<HTMLLIElement>) => <li className="relative pl-4 text-[13px] leading-snug before:absolute before:left-0 before:text-primary before:content-['›']" {...p} />,
  strong: (p: React.HTMLAttributes<HTMLElement>) => <strong className="font-semibold" {...p} />,
  blockquote: (p: React.HTMLAttributes<HTMLQuoteElement>) => <blockquote className="my-1 border-l-2 border-primary/40 pl-2.5 font-mono text-[11px] italic text-foreground/70" {...p} />,
  table: (p: React.HTMLAttributes<HTMLTableElement>) => <div className="my-2 overflow-hidden rounded-lg border border-black/5"><table className="w-full text-[12px]" {...p} /></div>,
  thead: (p: React.HTMLAttributes<HTMLTableSectionElement>) => <thead className="bg-secondary/60" {...p} />,
  th: (p: React.HTMLAttributes<HTMLTableCellElement>) => <th className="px-2.5 py-1.5 text-left text-[11px] font-medium text-muted-foreground" {...p} />,
  td: (p: React.HTMLAttributes<HTMLTableCellElement>) => <td className="border-t border-black/5 px-2.5 py-1.5 tnum" {...p} />,
};

export function ReportPanel({ open, onClose }: { open: boolean; onClose: () => void }) {
  const sections = buildReport(PLAN);
  const [built, setBuilt] = useState(0); // how many sections have "generated"
  const [copied, setCopied] = useState(false);
  const done = built >= sections.length;

  const copyAll = () => {
    navigator.clipboard?.writeText(reportMarkdown(PLAN));
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };

  // On open, stream the sections in one at a time (Claude-Code-style artifact build).
  useEffect(() => {
    if (!open) { setBuilt(0); return; }
    if (built >= sections.length) return;
    const t = setTimeout(() => setBuilt((b) => b + 1), built === 0 ? 350 : 520);
    return () => clearTimeout(t);
  }, [open, built, sections.length]);

  return (
    <AnimatePresence>
      {open && (
        <>
          {/* dim only on small screens */}
          <motion.div
            initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
            onClick={onClose}
            className="fixed inset-0 z-40 bg-black/20 backdrop-blur-[2px] lg:hidden"
          />
          <motion.aside
            initial={{ x: "100%" }}
            animate={{ x: 0 }}
            exit={{ x: "100%" }}
            transition={{ type: "spring", stiffness: 260, damping: 32 }}
            className="glass-strong fixed right-0 top-0 z-50 flex h-screen w-full max-w-[500px] flex-col border-l border-white/50"
          >
            {/* Header */}
            <div className="flex items-center justify-between border-b border-black/5 px-4 py-3">
              <div className="flex items-center gap-2">
                <span className="grid h-7 w-7 place-items-center rounded-lg bg-primary/12 text-primary">
                  <FileText className="h-4 w-4" />
                </span>
                <div className="leading-tight">
                  <div className="font-serif text-[14px]">Standard Report</div>
                  <div className="text-[10px] text-muted-foreground">{PLAN.title}</div>
                </div>
              </div>
              <button onClick={onClose} className="grid h-7 w-7 place-items-center rounded-lg text-muted-foreground hover:bg-secondary hover:text-foreground">
                <X className="h-4 w-4" />
              </button>
            </div>

            {/* Build status / export bar */}
            <div className="flex items-center justify-between gap-2 border-b border-black/5 bg-white/30 px-4 py-2">
              {!done ? (
                <span className="flex items-center gap-2 text-[12px] text-muted-foreground">
                  <Sparkles className="h-3.5 w-3.5 text-primary" /> Assembling report… {built}/{sections.length}
                </span>
              ) : (
                <span className="flex items-center gap-1.5 text-[12px] text-[var(--positive)]">
                  <Check className="h-3.5 w-3.5" /> Ready · {sections.length} sections
                </span>
              )}
              <div className="flex items-center gap-1">
                <button
                  onClick={copyAll}
                  disabled={!done}
                  className={cn(
                    "flex items-center gap-1 rounded-lg border px-2 py-1 text-[11px] font-medium transition-all",
                    !done ? "cursor-not-allowed border-black/5 text-muted-foreground/40" : "border-black/10 text-muted-foreground hover:border-primary/30 hover:text-primary",
                  )}
                >
                  {copied ? <Check className="h-3 w-3 text-[var(--positive)]" /> : <Copy className="h-3 w-3" />} {copied ? "Copied" : "Copy"}
                </button>
                <ExportBtn label="PDF" disabled={!done} onClick={() => downloadPDF(PLAN)} />
                <ExportBtn label="MD" disabled={!done} onClick={() => downloadText(`${PLAN.id}_report.md`, reportMarkdown(PLAN), "text/markdown")} />
                <ExportBtn label="CSV" disabled={!done} onClick={() => downloadText(`${PLAN.id}_report.csv`, reportCSV(PLAN), "text/csv")} />
              </div>
            </div>

            {/* Body */}
            <div className="flex-1 overflow-y-auto px-5 py-4">
              <div className="space-y-4">
                {sections.slice(0, built).map((s, i) => (
                  <motion.section
                    key={s.id}
                    initial={{ opacity: 0, y: 8 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.3 }}
                    className="border-b border-black/5 pb-4 last:border-0"
                  >
                    <h3 className="mb-1.5 flex items-center gap-1.5 font-serif text-[13px] text-primary">
                      <span className="font-mono text-[10px] text-muted-foreground/50">{String(i + 1).padStart(2, "0")}</span>
                      {s.title}
                    </h3>
                    <ReactMarkdown remarkPlugins={[remarkGfm]} components={MD}>{s.body}</ReactMarkdown>
                  </motion.section>
                ))}
                {!done && (
                  <div className="flex items-center gap-2 py-2 text-[12px] text-muted-foreground">
                    <Loader2 className="h-3.5 w-3.5 animate-spin text-primary" /> writing next section…
                  </div>
                )}
              </div>
            </div>

            <div className="border-t border-black/5 px-4 py-2 text-center text-[10px] text-muted-foreground/70">
              Generated by BidIntel · every figure cited to its source page · decision support, not final pricing
            </div>
          </motion.aside>
        </>
      )}
    </AnimatePresence>
  );
}

function ExportBtn({ label, onClick, disabled }: { label: string; onClick: () => void; disabled: boolean }) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className={cn(
        "flex items-center gap-1 rounded-lg border px-2 py-1 text-[11px] font-medium transition-all",
        disabled
          ? "cursor-not-allowed border-black/5 text-muted-foreground/40"
          : "border-primary/30 text-primary hover:bg-primary hover:text-primary-foreground",
      )}
    >
      <FileDown className="h-3 w-3" /> {label}
    </button>
  );
}
