"use client";

import { useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import { PanelRightClose, PanelRightOpen, PanelLeft, Gauge, X, SquarePen, MessageSquare } from "lucide-react";
import { useChatStore } from "./use-chat-store";
import { ConversationList } from "./conversation-list";
import { Thread } from "./thread";
import { Composer } from "./composer";
import { ContextPanel } from "./context-panel";
import { VerifyExtraction } from "@/components/verify/verify-extraction";
import { BRAND } from "@/lib/brand";
import { cn } from "@/lib/utils";

export function ChatApp() {
  const store = useChatStore();
  // Right usage panel starts CLOSED (Claude/ChatGPT keep the canvas clean — no
  // permanent right column). It opens on demand from the usage pill.
  const [panelOpen, setPanelOpen] = useState(false);
  // First open = clean canvas: conversation rail collapsed too (open on demand).
  const [railOpen, setRailOpen] = useState(false);
  const [verifyOpen, setVerifyOpen] = useState(false);

  const activeFiles = store.files.filter((f) => store.active.fileIds.includes(f.id));
  // Composer only shows files that are still being read, or non-plan context (CSV/spec). A
  // finished plan does NOT linger in the composer — it lives in the thread as a file chip +
  // the header source count (ChatGPT-style: the attachment moves up, the composer stays clean).
  const composerFiles = activeFiles.filter((f) => f.status === "parsing" || f.kind !== "plan");
  // Empty thread → ChatGPT-style centered hero; once a turn lands, drop to the bottom composer.
  const isEmpty = store.active.messages.length === 0;
  // Real signal for the topbar pill: tokens used by the last answer (0 until one lands).
  const lastTotal = store.lastUsage ? store.lastUsage.input_tokens + store.lastUsage.output_tokens : 0;

  return (
    <div className="flex min-h-0 flex-1 overflow-hidden">
      {/* Thin icon rail (always visible, ChatGPT-style) — quick actions + account */}
      <div className="hidden w-14 shrink-0 flex-col items-center border-r border-border bg-[oklch(0.952_0.009_83)] py-3 md:flex">
        <RailIcon icon={PanelLeft} label="Toggle chats" active={railOpen} onClick={() => setRailOpen((o) => !o)} />
        <div className="mt-1 flex flex-col items-center gap-1">
          <RailIcon icon={SquarePen} label="New chat" onClick={store.newConversation} />
          <RailIcon icon={MessageSquare} label="Chats" onClick={() => setRailOpen(true)} />
        </div>
        <div className="flex-1" />
        <button
          title={`${BRAND.user.name} · ${BRAND.company}`}
          className="grid h-8 w-8 shrink-0 place-items-center rounded-full bg-gradient-to-br from-primary to-[oklch(0.5_0.15_30)] text-[13px] text-primary-foreground elev-sm"
        >
          {BRAND.user.initial}
        </button>
      </div>

      {/* Conversation rail (collapsible) — solid cream surface, not hazy glass */}
      <AnimatePresence initial={false}>
        {railOpen && (
          <motion.div
            initial={{ width: 0, opacity: 0 }}
            animate={{ width: 248, opacity: 1 }}
            exit={{ width: 0, opacity: 0 }}
            transition={{ type: "spring", stiffness: 260, damping: 30 }}
            className="hidden shrink-0 overflow-hidden border-r border-border bg-[oklch(0.955_0.009_83)] lg:block"
          >
            <div className="h-full w-[248px]">
              <ConversationList
                conversations={store.conversations}
                activeId={store.activeId}
                onSelect={store.selectConversation}
                onNew={store.newConversation}
                onDelete={store.deleteConversation}
              />
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Center: single top bar + thread + composer */}
      <div className="flex min-w-0 flex-1 flex-col">
        {/* One merged top bar: brand + active title (left) · usage + account (right) */}
        <div className="flex h-[52px] shrink-0 items-center justify-between border-b border-border bg-card/70 px-3 backdrop-blur-xl">
          <div className="flex min-w-0 items-center gap-2 text-sm">
            <span className="grid h-7 w-7 shrink-0 place-items-center rounded-lg bg-primary text-[13px] text-primary-foreground elev-sm">{BRAND.mark}</span>
            <span className="truncate font-serif tracking-tight text-foreground">{store.active.title}</span>
            {activeFiles.length > 0 && (
              <span className="shrink-0 rounded-full bg-secondary px-2 py-0.5 font-mono text-[10px] text-muted-foreground">
                {activeFiles.length} {activeFiles.length === 1 ? "source" : "sources"}
              </span>
            )}
          </div>
          <div className="flex shrink-0 items-center gap-2">
            <button
              onClick={() => setPanelOpen((o) => !o)}
              title="Usage & sources"
              className="flex items-center gap-1.5 rounded-lg border border-border bg-card px-2.5 py-1.5 text-[11px] text-muted-foreground transition-colors hover:text-foreground"
            >
              <Gauge className="h-3.5 w-3.5" />
              <span className="tnum">{lastTotal ? `${(lastTotal / 1000).toFixed(1)}K tokens` : "usage"}</span>
              {panelOpen ? <PanelRightClose className="h-3.5 w-3.5" /> : <PanelRightOpen className="h-3.5 w-3.5" />}
            </button>
          </div>
        </div>

        {isEmpty ? (
          /* ChatGPT-style hero: headline + composer vertically centered on the canvas */
          <div className="flex min-h-0 flex-1 flex-col items-center justify-center overflow-y-auto px-4 pb-[8vh]">
            <div className="w-full max-w-3xl">
              <motion.div
                initial={{ opacity: 0, scale: 0.9 }}
                animate={{ opacity: 1, scale: 1 }}
                transition={{ type: "spring", stiffness: 200, damping: 20 }}
                className="mx-auto grid h-14 w-14 place-items-center rounded-2xl bg-primary/12 text-2xl text-primary shadow-sm"
              >
                {BRAND.mark}
              </motion.div>
              <motion.h1
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.05 }}
                className="mt-5 text-center font-serif text-[38px] leading-tight tracking-tight"
              >
                What are we bidding on today?
              </motion.h1>
              <motion.p
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.1 }}
                className="mx-auto mt-3 max-w-lg text-center text-[15px] text-muted-foreground"
              >
                Drop in a plan and I&apos;ll read it end to end — quantities, gotchas, contract times —
                or ask about pricing, competitors, and your bid history.
              </motion.p>
              <motion.div
                initial={{ opacity: 0, y: 12 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.14 }}
                className="mt-5"
              >
                <Composer
                  onSend={store.send}
                  onAttach={store.attachFiles}
                  onDetach={store.detachFile}
                  attached={composerFiles}
                  busy={store.busy}
                  placeholder="Drop in a plan to get started…"
                />
              </motion.div>
            </div>
          </div>
        ) : (
          <>
            <div className="min-h-0 flex-1 overflow-y-auto">
              <Thread messages={store.active.messages} onSend={store.send} onVerify={() => setVerifyOpen(true)} />
            </div>

            <Composer
              onSend={store.send}
              onAttach={store.attachFiles}
              onDetach={store.detachFile}
              attached={composerFiles}
              busy={store.busy}
            />
          </>
        )}
      </div>

      {/* Right: context panel */}
      <AnimatePresence initial={false}>
        {panelOpen && (
          <motion.div
            initial={{ width: 0, opacity: 0 }}
            animate={{ width: 304, opacity: 1 }}
            exit={{ width: 0, opacity: 0 }}
            transition={{ type: "spring", stiffness: 260, damping: 30 }}
            className={cn("hidden shrink-0 overflow-hidden border-l border-border bg-[oklch(0.955_0.009_83)] md:block")}
          >
            <div className="h-full w-[304px]">
              <ContextPanel files={activeFiles} usage={store.lastUsage} sessionTokens={store.sessionTokens} onDetach={store.detachFile} />
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Verify-extraction modal (the trust gate, opened from the report card) */}
      <AnimatePresence>
        {verifyOpen && (
          <>
            <motion.div
              initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
              onClick={() => setVerifyOpen(false)}
              className="fixed inset-0 z-50 bg-black/25 backdrop-blur-[2px]"
            />
            <motion.div
              initial={{ opacity: 0, y: 16, scale: 0.98 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: 16, scale: 0.98 }}
              transition={{ type: "spring", stiffness: 280, damping: 30 }}
              className="glass-strong fixed left-1/2 top-1/2 z-50 max-h-[88vh] w-full max-w-2xl -translate-x-1/2 -translate-y-1/2 overflow-y-auto rounded-2xl border border-white/50 p-5"
            >
              <button
                onClick={() => setVerifyOpen(false)}
                className="absolute right-3 top-3 grid h-7 w-7 place-items-center rounded-lg text-muted-foreground hover:bg-secondary hover:text-foreground"
              >
                <X className="h-4 w-4" />
              </button>
              <VerifyExtraction onConfirm={() => setVerifyOpen(false)} onSkip={() => setVerifyOpen(false)} />
            </motion.div>
          </>
        )}
      </AnimatePresence>
    </div>
  );
}

// A single icon button in the thin left rail. `active` gets a subtle filled pill.
function RailIcon({
  icon: Icon,
  label,
  active,
  onClick,
}: {
  icon: typeof PanelLeft;
  label: string;
  active?: boolean;
  onClick?: () => void;
}) {
  return (
    <button
      onClick={onClick}
      title={label}
      aria-label={label}
      className={cn(
        "grid h-9 w-9 place-items-center rounded-xl transition-colors",
        active
          ? "bg-card text-foreground elev-sm"
          : "text-muted-foreground hover:bg-card hover:text-foreground",
      )}
    >
      <Icon className="h-[18px] w-[18px]" strokeWidth={2} />
    </button>
  );
}
