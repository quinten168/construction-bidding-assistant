"use client";

import { motion } from "motion/react";
import NumberFlow from "@number-flow/react";
import { FileText, Database, BookOpen, Trash2, Loader2 } from "lucide-react";
import { type UploadedFile, type Usage } from "@/lib/chat-data";
import { Eyebrow } from "@/components/kit";

const KIND_ICON = { plan: FileText, spec: BookOpen, bidtab: Database } as const;
const fmtTok = (n: number) => (n >= 1000 ? `${(n / 1000).toFixed(n >= 100_000 ? 0 : 1)}K` : `${n}`);

// Friendly model label from the backend's model id (e.g. "claude-sonnet-4-6" → "Sonnet 4.6").
function modelLabel(id?: string): string {
  if (!id) return "Sonnet 4.6";
  const m = id.match(/(opus|sonnet|haiku)-(\d+)-(\d+)/i);
  if (m) return `${m[1][0].toUpperCase()}${m[1].slice(1)} ${m[2]}.${m[3]}`;
  return id;
}

export function ContextPanel({
  files,
  onDetach,
  usage,
  sessionTokens,
}: {
  files: UploadedFile[];
  onDetach: (id: string) => void;
  usage: Usage | null;
  sessionTokens: number;
}) {
  const lastTotal = usage ? usage.input_tokens + usage.output_tokens : 0;

  return (
    <div className="flex h-full flex-col gap-5 overflow-y-auto px-4 py-5">
      {/* Real per-turn usage — the honest signal. RAG retrieves only the relevant chunks, so the
          input tokens here are the TRUE context size for an answer, not a whole-document estimate. */}
      <div>
        <div className="flex items-center justify-between">
          <Eyebrow>Usage</Eyebrow>
          <span className="font-mono text-[10px] text-muted-foreground">{modelLabel(usage?.model)}</span>
        </div>

        {usage ? (
          <>
            <div className="mt-2 flex items-baseline gap-1.5">
              <span className="font-serif text-2xl tracking-tight tnum">
                <NumberFlow value={lastTotal} format={{ maximumFractionDigits: 0 }} />
              </span>
              <span className="text-sm text-muted-foreground">tokens · last answer</span>
            </div>

            <div className="mt-3 space-y-1">
              <UsageRow label="Input (context)" value={usage.input_tokens} color="var(--chart-1)" />
              <UsageRow label="Output" value={usage.output_tokens} color="var(--chart-3)" />
              {!!usage.cache_read_tokens && (
                <UsageRow label="Cached" value={usage.cache_read_tokens} color="var(--muted-foreground)" />
              )}
              <div className="flex items-center justify-between border-t border-black/5 pt-1 text-[11px]">
                <span className="text-muted-foreground">Session total</span>
                <span className="font-mono tnum text-foreground/70">{fmtTok(sessionTokens)}</span>
              </div>
            </div>
          </>
        ) : (
          <p className="mt-2 rounded-xl border border-dashed border-black/10 px-3 py-4 text-center text-[11px] text-muted-foreground">
            No answers yet. Token usage for each answer will appear here.
          </p>
        )}
      </div>

      {/* Attached plans — these are INDEXED into retrieval, not loaded whole into context. */}
      <div className="flex-1">
        <div className="mb-2 flex items-center justify-between">
          <Eyebrow>Attached plans</Eyebrow>
          <span className="rounded-full bg-secondary px-1.5 py-0.5 font-mono text-[10px] text-muted-foreground">{files.length}</span>
        </div>

        <div className="space-y-1.5">
          {files.length === 0 && (
            <p className="rounded-xl border border-dashed border-black/10 px-3 py-4 text-center text-[11px] text-muted-foreground">
              No plans attached. Drop a plan set into the composer and I&apos;ll read it.
            </p>
          )}
          {files.map((f) => {
            const Icon = KIND_ICON[f.kind];
            return (
              <motion.div
                key={f.id}
                initial={{ opacity: 0, x: 8 }}
                animate={{ opacity: 1, x: 0 }}
                className="group flex items-center gap-2.5 rounded-xl border border-black/5 bg-white/40 px-2.5 py-2"
              >
                <span className="grid h-7 w-7 shrink-0 place-items-center rounded-lg bg-primary/10 text-primary">
                  {f.status === "parsing" ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Icon className="h-3.5 w-3.5" />}
                </span>
                <div className="min-w-0 flex-1">
                  <div className="truncate text-[12px] font-medium">{f.name}</div>
                  <div className="font-mono text-[10px] text-muted-foreground">
                    {f.status === "parsing" ? "reading…" : `${f.pages} pp · indexed`}
                  </div>
                </div>
                <button
                  onClick={() => onDetach(f.id)}
                  className="grid h-6 w-6 shrink-0 place-items-center rounded-md text-muted-foreground opacity-0 transition-all hover:bg-secondary hover:text-[var(--negative)] group-hover:opacity-100"
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </button>
              </motion.div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

function UsageRow({ label, value, color }: { label: string; value: number; color: string }) {
  return (
    <div className="flex items-center justify-between text-[11px]">
      <span className="flex items-center gap-1.5 text-muted-foreground">
        <span className="h-2 w-2 rounded-full" style={{ background: color }} /> {label}
      </span>
      <span className="font-mono tnum text-foreground/70">{fmtTok(value)}</span>
    </div>
  );
}
