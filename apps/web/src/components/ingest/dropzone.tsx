"use client";

// ─────────────────────────────────────────────────────────────────────────────
// The hero drag-and-drop zone. A large frosted-glass panel with a dashed border
// that glows clay-coral on drag-over (animated border + a soft radial glow).
// Dropping any file — or clicking "Try a sample plan" — starts the pipeline.
// ─────────────────────────────────────────────────────────────────────────────

import { useCallback } from "react";
import { useDropzone } from "react-dropzone";
import { motion, useReducedMotion } from "motion/react";
import { UploadCloud, FileText, Sparkles } from "lucide-react";
import { cn } from "@/lib/utils";

export function DropZone({ onFile }: { onFile: () => void }) {
  const reduce = useReducedMotion();

  // Any dropped file (we don't actually parse it — this is a demo) starts the run.
  const onDrop = useCallback(() => onFile(), [onFile]);

  const { getRootProps, getInputProps, isDragActive, open } = useDropzone({
    onDrop,
    accept: { "application/pdf": [".pdf"] },
    multiple: false,
    noClick: false,
    noKeyboard: false,
  });

  return (
    <div className="flex flex-col items-center gap-4">
      <motion.div
        {...(getRootProps() as object)}
        initial={false}
        animate={{ scale: isDragActive && !reduce ? 1.012 : 1 }}
        transition={{ type: "spring", stiffness: 300, damping: 22 }}
        className={cn(
          "glass sheen group relative w-full cursor-pointer overflow-hidden rounded-2xl border-2 border-dashed p-10 text-center transition-colors sm:p-14",
          isDragActive ? "border-primary" : "border-border hover:border-primary/50",
        )}
      >
        <input {...getInputProps()} />

        {/* Soft radial glow that blooms on drag-over */}
        <motion.div
          aria-hidden
          initial={false}
          animate={{ opacity: isDragActive ? 1 : 0 }}
          transition={{ duration: 0.35 }}
          className="pointer-events-none absolute inset-0"
          style={{
            background:
              "radial-gradient(circle at 50% 42%, color-mix(in oklab, var(--primary) 22%, transparent), transparent 62%)",
          }}
        />

        <div className="relative flex flex-col items-center gap-4">
          <motion.span
            animate={
              reduce ? undefined : { y: isDragActive ? -4 : 0 }
            }
            transition={{ type: "spring", stiffness: 260, damping: 18 }}
            className={cn(
              "grid h-16 w-16 place-items-center rounded-2xl transition-colors",
              isDragActive ? "bg-primary text-primary-foreground" : "bg-primary/10 text-primary",
            )}
          >
            <UploadCloud className="h-7 w-7" strokeWidth={1.8} />
          </motion.span>

          <div className="space-y-1.5">
            <p className="font-serif text-[22px] tracking-tight">
              {isDragActive ? "Release to ingest" : "Drop a plan set"}
            </p>
            <p className="text-[13.5px] text-muted-foreground">
              PDF or CAD · drag here, or{" "}
              <span className="font-medium text-primary underline-offset-2 group-hover:underline">browse</span>
            </p>
          </div>

          <div className="mt-1 flex items-center gap-2 text-[11px] text-muted-foreground">
            <FileText className="h-3.5 w-3.5" />
            up to 280 pages · MN · ND · SD DOT formats
          </div>
        </div>
      </motion.div>

      {/* Sample-plan shortcut: clicking it also opens the file picker chooser is
          separate — this injects the Dunn County demo plan directly. */}
      <div className="flex items-center gap-3 text-[12px] text-muted-foreground">
        <button
          onClick={onFile}
          className="inline-flex items-center gap-1.5 rounded-full border border-primary/30 bg-primary/8 px-3 py-1.5 font-medium text-primary transition-colors hover:bg-primary/14"
        >
          <Sparkles className="h-3.5 w-3.5" /> Try a sample plan
        </button>
        <button onClick={open} className="underline-offset-2 transition-colors hover:text-foreground hover:underline">
          or choose a file
        </button>
      </div>
    </div>
  );
}
