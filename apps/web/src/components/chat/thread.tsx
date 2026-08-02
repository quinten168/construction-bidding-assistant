"use client";

import { useEffect, useRef } from "react";
import { motion } from "motion/react";
import { type ChatMessage } from "@/lib/chat-data";
import { BRAND } from "@/lib/brand";
import { MessageBubble } from "./message-bubble";

export function Thread({
  messages,
  onSend,
}: {
  messages: ChatMessage[];
  onSend: (text: string) => void;
}) {
  const endRef = useRef<HTMLDivElement>(null);
  const reportRef = useRef<HTMLDivElement>(null);
  const last = messages.at(-1);
  // Track both length and live content/step so autoscroll follows streaming and
  // the step-by-step narration. prefers-reduced-motion → instant, no smooth jump.
  const lastContent = last?.content;
  const lastStep = last?.narrationStep;
  const lastCard = last?.card;

  useEffect(() => {
    const reduce = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    // When a report card lands, jump to the TOP of the report (a bid report is read
    // top-down); for normal chat/narration, follow the stream to the bottom.
    if (lastCard && reportRef.current) {
      reportRef.current.scrollIntoView({ behavior: reduce ? "auto" : "smooth", block: "start" });
    } else {
      endRef.current?.scrollIntoView({ behavior: reduce ? "auto" : "smooth", block: "end" });
    }
  }, [messages.length, lastContent, lastStep, lastCard]);

  if (messages.length === 0) return <EmptyState />;

  return (
    <div className="mx-auto flex w-full max-w-[760px] flex-col gap-6 px-4 py-8">
      {messages.map((m) => {
        const isReportCard = m.kind === "report" && m.card;
        return (
          <div key={m.id} ref={isReportCard ? reportRef : undefined} className="scroll-mt-4">
            <MessageBubble m={m} />
          </div>
        );
      })}
      <div ref={endRef} className="h-2" />
    </div>
  );
}

function EmptyState() {
  return (
    <div className="mx-auto flex h-full max-w-2xl flex-col items-center justify-center px-4 py-10 text-center">
      <motion.div
        initial={{ opacity: 0, scale: 0.9 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ type: "spring", stiffness: 200, damping: 20 }}
        className="grid h-14 w-14 place-items-center rounded-2xl bg-primary/12 text-2xl text-primary shadow-sm"
      >
        ◐
      </motion.div>
      <motion.h1
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.05 }}
        className="mt-5 font-serif text-3xl tracking-tight"
      >
        Welcome back, {BRAND.user.name}.
      </motion.h1>
      <motion.p
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.1 }}
        className="mt-2 max-w-md text-sm text-muted-foreground"
      >
        <span className="font-medium text-foreground">Drop a plan and let&apos;s get started!</span> I&apos;ll read it
        end to end — quantities, gotchas, contract times — or ask about pricing, competitors, and your bid history.
        Every figure is cited to the page it came from.
      </motion.p>
    </div>
  );
}
