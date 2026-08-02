"use client";

import { useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Check, Copy, FileText, RotateCcw, ThumbsDown, ThumbsUp } from "lucide-react";
import { type ChatMessage, type Citation } from "@/lib/chat-data";
import { Thinking, ReportNarration } from "./thinking";
import { ReportCard } from "./report-card";
import { cn } from "@/lib/utils";

// Markdown element styling — tuned to read like Claude: airy prose, real tables,
// soft inline code, tight lists. No typography plugin; explicit component map.
const MD = {
  p: (p: React.HTMLAttributes<HTMLParagraphElement>) => <p className="my-2 leading-relaxed first:mt-0 last:mb-0" {...p} />,
  ul: (p: React.HTMLAttributes<HTMLUListElement>) => <ul className="my-2 space-y-1.5 pl-1" {...p} />,
  ol: (p: React.HTMLAttributes<HTMLOListElement>) => <ol className="my-2 list-decimal space-y-1.5 pl-5" {...p} />,
  li: (p: React.HTMLAttributes<HTMLLIElement>) => (
    <li className="relative pl-4 leading-relaxed before:absolute before:left-0 before:text-primary before:content-['›'] [ol_&]:pl-0 [ol_&]:before:content-['']" {...p} />
  ),
  strong: (p: React.HTMLAttributes<HTMLElement>) => <strong className="font-semibold text-foreground" {...p} />,
  h3: (p: React.HTMLAttributes<HTMLHeadingElement>) => <h3 className="mb-1 mt-3 font-serif text-base" {...p} />,
  blockquote: (p: React.HTMLAttributes<HTMLQuoteElement>) => (
    <blockquote className="my-1.5 border-l-2 border-primary/40 pl-3 font-mono text-[12px] italic text-foreground/70" {...p} />
  ),
  code: (p: React.HTMLAttributes<HTMLElement>) => <code className="rounded bg-secondary px-1.5 py-0.5 font-mono text-[12px]" {...p} />,
  table: (p: React.HTMLAttributes<HTMLTableElement>) => (
    <div className="my-3 overflow-hidden rounded-xl border border-black/5">
      <table className="w-full text-sm" {...p} />
    </div>
  ),
  thead: (p: React.HTMLAttributes<HTMLTableSectionElement>) => <thead className="bg-secondary/60" {...p} />,
  th: (p: React.HTMLAttributes<HTMLTableCellElement>) => <th className="px-3 py-2 text-left text-xs font-medium text-muted-foreground" {...p} />,
  td: (p: React.HTMLAttributes<HTMLTableCellElement>) => <td className="border-t border-black/5 px-3 py-2 tnum" {...p} />,
  a: (p: React.AnchorHTMLAttributes<HTMLAnchorElement>) => <a className="text-primary underline-offset-2 hover:underline" {...p} />,
};

export function MessageBubble({ m }: { m: ChatMessage }) {
  if (m.role === "user") return <UserBubble m={m} />;
  return <AssistantBubble m={m} />;
}

function UserBubble({ m }: { m: ChatMessage }) {
  // A dropped plan renders as a FILE CHIP (ChatGPT-style), not a text bubble.
  if (m.planFile) {
    return (
      <motion.div initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} className="flex justify-end">
        <div className="flex items-center gap-2.5 rounded-2xl border border-black/10 bg-card py-2 pl-2 pr-3 elev-sm">
          <span className="grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-gradient-to-br from-[oklch(0.62_0.19_25)] to-[oklch(0.54_0.18_28)]">
            <FileText className="h-[18px] w-[18px] text-white" />
          </span>
          <span className="leading-tight">
            <span className="block max-w-[280px] truncate text-[13px] font-medium text-foreground">{m.planFile}</span>
            <span className="text-[11px] uppercase tracking-wide text-muted-foreground">PDF</span>
          </span>
        </div>
      </motion.div>
    );
  }
  return (
    <motion.div initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} className="flex justify-end">
      <div className="max-w-[80%] rounded-2xl rounded-br-md bg-primary px-4 py-2.5 text-[15px] text-primary-foreground shadow-sm">
        {m.content}
      </div>
    </motion.div>
  );
}

function AssistantBubble({ m }: { m: ChatMessage }) {
  const [copied, setCopied] = useState(false);
  const [vote, setVote] = useState<"up" | "down" | null>(null);
  const copy = () => {
    navigator.clipboard?.writeText(m.content);
    setCopied(true);
    setTimeout(() => setCopied(false), 1400);
  };

  const isReport = m.kind === "report";
  // While a report turn is processing, show the narration log in place of prose.
  const showNarration = isReport && !m.card;

  return (
    <motion.div initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} className="group flex gap-3">
      <span className="mt-0.5 grid h-7 w-7 shrink-0 place-items-center rounded-lg bg-primary/12 text-primary">◐</span>
      <div className="min-w-0 flex-1">
        {showNarration ? (
          <div className="py-1.5">
            <ReportNarration steps={m.narration ?? []} step={m.narrationStep ?? 0} />
          </div>
        ) : m.status === "thinking" ? (
          <div className="py-1.5">
            <Thinking />
          </div>
        ) : (
          <>
            {m.content && (
              <div className="text-[17px] leading-[1.72] text-foreground">
                <ReactMarkdown remarkPlugins={[remarkGfm]} components={MD}>
                  {m.content}
                </ReactMarkdown>
                {m.status === "streaming" && (
                  <span className="ml-0.5 inline-block h-4 w-[2px] -translate-y-px animate-pulse bg-primary align-middle" />
                )}
              </div>
            )}

            {/* Inline report card (the signature artifact). Breaks out of the avatar
                indent (-ml-10) so it uses the FULL thread width — big and easy to read. */}
            {isReport && m.card && (
              <div className="mt-3 -ml-10">
                <ReportCard final={m.final} />
              </div>
            )}

            {/* Citations — grouped by source doc, page passage on click */}
            {m.status === "done" && m.citations && m.citations.length > 0 && <Citations citations={m.citations} />}

            {/* Hover actions */}
            {m.status === "done" && (
              <div className="mt-2 flex items-center gap-0.5 opacity-0 transition-opacity group-focus-within:opacity-100 group-hover:opacity-100">
                <Action onClick={copy} label="Copy">
                  {copied ? <Check className="h-3.5 w-3.5 text-[var(--positive)]" /> : <Copy className="h-3.5 w-3.5" />}
                </Action>
                <Action label="Good" onClick={() => setVote((v) => (v === "up" ? null : "up"))}>
                  <ThumbsUp className={cn("h-3.5 w-3.5", vote === "up" && "text-[var(--positive)]")} />
                </Action>
                <Action label="Bad" onClick={() => setVote((v) => (v === "down" ? null : "down"))}>
                  <ThumbsDown className={cn("h-3.5 w-3.5", vote === "down" && "text-[var(--negative)]")} />
                </Action>
                <Action label="Retry"><RotateCcw className="h-3.5 w-3.5" /></Action>
                <span className="ml-1 font-mono text-[10px] text-muted-foreground/60">{m.tokens} tok</span>
              </div>
            )}
          </>
        )}
      </div>
    </motion.div>
  );
}

// Citations grouped by source doc; click a page chip to reveal the cited passage.
function Citations({ citations }: { citations: Citation[] }) {
  const [openKey, setOpenKey] = useState<string | null>(null);
  return (
    <div className="mt-3">
      <div className="mb-1.5 flex items-center gap-1.5 text-[11px] text-muted-foreground">
        <FileText className="h-3 w-3" />
        <span className="font-medium">Cited to source</span>
        <span className="text-muted-foreground/60">· every figure pinned to its page</span>
      </div>
      <div className="flex flex-wrap gap-1.5">
        {citations.map((c, i) => {
          const key = `${c.label}-${c.page}-${i}`;
          const passage = c.passage; // the REAL retrieved passage from the backend
          const open = openKey === key;
          return (
            <div key={key} className="relative">
              <button
                onClick={() => setOpenKey(open ? null : key)}
                className={cn(
                  "inline-flex items-center gap-1.5 rounded-lg border bg-white/50 px-2 py-1 text-[11px] transition-colors",
                  open ? "border-primary/40 text-primary" : "border-black/5 text-muted-foreground hover:border-primary/30 hover:text-primary",
                )}
                title={passage ? "Show the cited passage" : "Source page"}
              >
                <FileText className="h-3 w-3" />
                <span className="max-w-[200px] truncate">{c.label}</span>
                <span className="rounded bg-secondary px-1 font-mono text-[10px]">p.{c.page}</span>
              </button>
              <AnimatePresence>
                {open && passage && (
                  <motion.div
                    initial={{ opacity: 0, y: -4, scale: 0.98 }}
                    animate={{ opacity: 1, y: 0, scale: 1 }}
                    exit={{ opacity: 0, y: -4, scale: 0.98 }}
                    transition={{ duration: 0.16 }}
                    className="glass-strong absolute left-0 top-full z-20 mt-1.5 w-[340px] max-w-[80vw] rounded-xl border border-black/[0.06] p-3 elev-md"
                  >
                    <div className="mb-1 flex items-center justify-between text-[10px] text-muted-foreground">
                      <span className="font-medium">{c.label}</span>
                      <span className="font-mono">p.{c.page}</span>
                    </div>
                    <pre className="whitespace-pre-wrap font-mono text-[11px] leading-relaxed text-foreground/80">{passage}</pre>
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function Action({ children, label, onClick }: { children: React.ReactNode; label: string; onClick?: () => void }) {
  return (
    <button
      onClick={onClick}
      title={label}
      className={cn("grid h-7 w-7 place-items-center rounded-md text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground")}
    >
      {children}
    </button>
  );
}
