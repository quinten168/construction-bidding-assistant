"use client";

import { useId, useRef, useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import { ArrowUp, FileText, Loader2, Plus, X } from "lucide-react";
import { type UploadedFile } from "@/lib/chat-data";
import { cn } from "@/lib/utils";

export function Composer({
  onSend,
  onAttach,
  onDetach,
  attached,
  busy,
  placeholder = "Ask about this plan set — quantities, gotchas, pricing, competitors…",
  hint = true,
}: {
  onSend: (text: string) => void;
  onAttach: (files: File[]) => void;
  onDetach: (id: string) => void;
  attached: UploadedFile[];
  busy: boolean;
  placeholder?: string;
  hint?: boolean;
}) {
  const [text, setText] = useState("");
  const taRef = useRef<HTMLTextAreaElement>(null);
  // The "+" button owns this native file input directly. We deliberately do NOT use
  // react-dropzone here: its root wraps the composer and intercepts the programmatic
  // .click() that bubbles up from the input, so the OS picker never opened. Native input
  // + native drag handlers below = nothing in the click path to swallow the dialog.
  const fileRef = useRef<HTMLInputElement>(null);
  const fileInputId = useId(); // unique per composer instance → label htmlFor binds correctly
  const [isDragActive, setDragActive] = useState(false);

  const submit = () => {
    if (!text.trim() || busy) return;
    onSend(text);
    setText("");
    if (taRef.current) taRef.current.style.height = "auto";
  };

  const pickFiles = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files ?? []);
    if (files.length) onAttach(files);
    e.target.value = ""; // reset so re-picking the same file fires change again
  };

  // Native drag-and-drop (replaces react-dropzone). Only react to files being dragged in.
  const onDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragActive(false);
    const files = Array.from(e.dataTransfer.files ?? []).filter((f) => /\.(pdf|csv)$/i.test(f.name));
    if (files.length) onAttach(files);
  };
  const onDragOver = (e: React.DragEvent) => {
    if (e.dataTransfer.types.includes("Files")) {
      e.preventDefault();
      setDragActive(true);
    }
  };
  const onDragLeave = (e: React.DragEvent) => {
    // Only clear when the pointer actually leaves the composer (not on child boundaries).
    if (!e.currentTarget.contains(e.relatedTarget as Node)) setDragActive(false);
  };

  const grow = (el: HTMLTextAreaElement) => {
    el.style.height = "auto";
    el.style.height = Math.min(el.scrollHeight, 200) + "px";
  };

  return (
    <div className="px-4 pb-4 pt-1">
      <div
        onDrop={onDrop}
        onDragOver={onDragOver}
        onDragLeave={onDragLeave}
        className={cn(
          "glass-strong relative mx-auto max-w-[768px] rounded-3xl p-2.5 transition-all duration-200",
          isDragActive && "ring-2 ring-primary/50",
        )}
      >
        {/* Drag overlay */}
        <AnimatePresence>
          {isDragActive && (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="absolute inset-0 z-10 grid place-items-center rounded-3xl bg-primary/8 text-sm font-medium text-primary backdrop-blur-sm"
            >
              Drop a plan set — I&apos;ll read it and build the extraction
            </motion.div>
          )}
        </AnimatePresence>

        {/* Attached file chips — ChatGPT-style card: a PDF tile (spinner ring while
            reading) + filename + type/status, with a remove button. */}
        {attached.length > 0 && (
          <div className="flex flex-wrap gap-2 px-2 pb-2 pt-1.5">
            {attached.map((f) => {
              const parsing = f.status === "parsing";
              const kindLabel = /\.pdf$/i.test(f.name) ? "PDF" : /\.csv$/i.test(f.name) ? "CSV" : "File";
              return (
                <motion.div
                  key={f.id}
                  initial={{ opacity: 0, scale: 0.95, y: 4 }}
                  animate={{ opacity: 1, scale: 1, y: 0 }}
                  className="group relative flex w-[248px] items-center gap-2.5 rounded-2xl border border-black/10 bg-card py-2 pl-2 pr-8 elev-sm"
                >
                  {/* PDF icon tile — coral/red like a document app; shows a spinner ring while reading */}
                  <span className="relative grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-gradient-to-br from-[oklch(0.62_0.19_25)] to-[oklch(0.54_0.18_28)] text-primary-foreground">
                    {parsing ? (
                      <Loader2 className="h-4 w-4 animate-spin text-white/90" />
                    ) : (
                      <FileText className="h-[18px] w-[18px] text-white" />
                    )}
                  </span>
                  <span className="min-w-0 flex-1 leading-tight">
                    <span className="block truncate text-[13px] font-medium text-foreground">{f.name}</span>
                    <span className="mt-0.5 flex items-center gap-1.5 text-[11px] text-muted-foreground">
                      {parsing ? (
                        <span className="text-primary">Reading…</span>
                      ) : (
                        <span className="inline-flex items-center gap-1">
                          <span className="h-1.5 w-1.5 rounded-full bg-[var(--positive)]" /> {kindLabel}
                        </span>
                      )}
                      <span className="text-muted-foreground/50">·</span>
                      <span className="font-mono">{(f.tokens / 1000).toFixed(0)}K</span>
                    </span>
                  </span>
                  <button
                    onClick={() => onDetach(f.id)}
                    title="Remove"
                    className="absolute right-2 top-2 grid h-5 w-5 place-items-center rounded-full bg-secondary text-muted-foreground transition-colors hover:bg-foreground hover:text-background"
                  >
                    <X className="h-3 w-3" />
                  </button>
                </motion.div>
              );
            })}
          </div>
        )}

        <div className="flex items-end gap-1.5">
          {/* Pure-HTML file trigger: the "+" is a <label> bound to the input by id, so clicking
              it opens the OS picker NATIVELY — no JS .click(), nothing to intercept or block.
              This is the most robust possible attach control. sr-only (not display:none) keeps
              the input in the render tree so the label association works everywhere. */}
          <input
            id={fileInputId}
            ref={fileRef}
            type="file"
            accept=".pdf,.csv"
            multiple
            className="sr-only"
            tabIndex={-1}
            onChange={pickFiles}
          />
          <label
            htmlFor={fileInputId}
            title="Attach plan set"
            aria-label="Attach plan set"
            className="mb-0.5 grid h-9 w-9 shrink-0 cursor-pointer place-items-center rounded-xl text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
          >
            <Plus className="h-5 w-5" />
          </label>

          <textarea
            ref={taRef}
            value={text}
            rows={1}
            onChange={(e) => {
              setText(e.target.value);
              grow(e.target);
            }}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                submit();
              }
            }}
            placeholder={placeholder}
            className="max-h-[220px] min-h-[40px] flex-1 resize-none bg-transparent px-1 py-2 text-[16px] outline-none placeholder:text-muted-foreground"
          />

          <button
            onClick={submit}
            disabled={!text.trim() || busy}
            className={cn(
              "mb-0.5 grid h-9 w-9 shrink-0 place-items-center rounded-xl transition-all",
              text.trim() && !busy
                ? "bg-primary text-primary-foreground shadow-sm hover:-translate-y-0.5"
                : "bg-secondary text-muted-foreground",
            )}
          >
            {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <ArrowUp className="h-4 w-4" />}
          </button>
        </div>
      </div>
      {hint && (
        <p className="mt-2 text-center text-[11px] text-muted-foreground/70">
          CSI Bid Assistant cites every figure to its source page · decision support, not final pricing
        </p>
      )}
    </div>
  );
}
