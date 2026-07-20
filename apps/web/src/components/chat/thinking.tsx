"use client";

import { useEffect, useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import { Check } from "lucide-react";
import { THINKING_STEPS } from "@/lib/chat-data";

// Construction-flavored "thinking" state — a surveyor's transit line sweeping while
// it cycles plain-language build phrases. Calm and deliberate, never frantic.
export function Thinking() {
  const [i, setI] = useState(0);
  useEffect(() => {
    const t = setInterval(() => setI((x) => (x + 1) % THINKING_STEPS.length), 1100);
    return () => clearInterval(t);
  }, []);

  return (
    <div className="flex items-center gap-2.5 text-sm text-muted-foreground">
      <span className="relative flex h-4 w-4 items-center justify-center">
        <motion.span
          className="absolute inset-0 rounded-full border-2 border-primary/30 border-t-primary"
          animate={{ rotate: 360 }}
          transition={{ repeat: Infinity, duration: 1.1, ease: "linear" }}
        />
      </span>
      <AnimatePresence mode="wait">
        <motion.span
          key={i}
          initial={{ opacity: 0, y: 4 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -4 }}
          transition={{ duration: 0.25 }}
          className="font-medium"
        >
          {THINKING_STEPS[i]}
        </motion.span>
      </AnimatePresence>
      <motion.span
        className="ml-0.5 inline-flex gap-0.5"
        initial="hidden"
        animate="visible"
      >
        {[0, 1, 2].map((d) => (
          <motion.span
            key={d}
            className="h-1 w-1 rounded-full bg-muted-foreground/60"
            animate={{ opacity: [0.2, 1, 0.2] }}
            transition={{ repeat: Infinity, duration: 1.2, delay: d * 0.18 }}
          />
        ))}
      </motion.span>
    </div>
  );
}

// Claude-Code-style processing log for the PDF→report flow: completed steps stay
// checked, the live step shows a spinner. The store streams `step` upward.
export function ReportNarration({ steps, step }: { steps: string[]; step: number }) {
  const visible = steps.slice(0, step + 1);
  return (
    <div className="space-y-2.5">
      {visible.map((s, i) => {
        const done = i < step;
        return (
          <motion.div
            key={s}
            initial={{ opacity: 0, x: -4 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.3 }}
            className="flex items-center gap-2.5 text-[15px]"
          >
            <span className="grid h-4 w-4 shrink-0 place-items-center">
              {done ? (
                <Check className="h-3.5 w-3.5 text-[var(--positive)]" />
              ) : (
                <motion.span
                  className="block h-3.5 w-3.5 rounded-full border-2 border-primary/30 border-t-primary"
                  animate={{ rotate: 360 }}
                  transition={{ repeat: Infinity, duration: 1, ease: "linear" }}
                />
              )}
            </span>
            <span className={done ? "text-muted-foreground" : "font-medium text-foreground"}>{s}</span>
          </motion.div>
        );
      })}
    </div>
  );
}
