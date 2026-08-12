"use client";

import { useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import { PanelRightClose, PanelRightOpen, Gauge } from "lucide-react";
import { useChatStoreContext } from "./chat-store-context";
import { Thread } from "./thread";
import { Composer } from "./composer";
import { ContextPanel } from "./context-panel";
import { VerifyExtraction } from "@/components/verify/verify-extraction";
import { VerifyCompetitors } from "@/components/verify/verify-competitors";
import { BRAND } from "@/lib/brand";
import { cn } from "@/lib/utils";

export function ChatApp() {
  // Shared with AppShell's sidebar (New chat button, Recents list) via context -- one store
  // instance, not two that could drift. See chat-store-context.tsx.
  const store = useChatStoreContext();
  // Right usage panel starts CLOSED (Claude/ChatGPT keep the canvas clean — no
  // permanent right column). It opens on demand from the usage pill.
  const [panelOpen, setPanelOpen] = useState(false);
  // Verify gate auto-opens off message state (set by processPlan once extraction lands) rather
  // than a manual trigger — it's a required checkpoint between extraction and report generation,
  // not an optional follow-up the user has to remember to click into.
  const verifyingMsg = store.active.messages.filter((m) => m.verifying && m.extraction).at(-1);
  // Optional 2nd popup, gated the same way as the first — auto-opens off message state once the
  // verify-extraction gate hands off to it (see use-chat-store.ts's confirmVerification).
  const awaitingCompetitorsMsg = store.active.messages.filter((m) => m.awaitingCompetitors).at(-1);

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
      {/* The icon rail (chat toggle / new chat / account) and the slide-out conversation list
          that used to live here are GONE (2026-08-11) -- AppShell's persistent left sidebar now
          owns "New chat" and the Recents list for every page, not just this one, so having a
          second, separate copy of the same controls in here was the exact redundancy that
          prompted the change. See app-shell.tsx. */}

      {/* Center: single top bar + thread + composer */}
      <div className="flex min-w-0 flex-1 flex-col">
        {/* One merged top bar: brand + active title (left) · usage + account (right) */}
        <div className="flex h-[52px] shrink-0 items-center justify-between border-b border-border bg-card/70 px-3 backdrop-blur-xl">
          {/* Title itself is NOT repeated here — AppShell's own header (the bar directly above
              this one) already shows store.active.title, and a second copy right underneath it
              read as two stacked "New chat" labels. This bar keeps only what AppShell's header
              doesn't have: the source-file count. */}
          <div className="flex min-w-0 items-center gap-2 text-sm">
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
              <Thread messages={store.active.messages} onSend={store.send} />
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

      {/* Verify-extraction gate — auto-opens once a plan's extraction lands (verifyingMsg above),
          before the rest of the report (competitor-intel generation) runs. No backdrop/X dismiss:
          Confirm or Skip are the only ways through, since either one actually finalizes the report
          via the store — an accidental dismiss would leave the message stuck waiting forever. */}
      <AnimatePresence>
        {verifyingMsg && (
          <>
            <motion.div
              initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
              className="fixed inset-0 z-50 bg-black/25 backdrop-blur-[2px]"
            />
            <motion.div
              initial={{ opacity: 0, y: 16, scale: 0.98 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: 16, scale: 0.98 }}
              transition={{ type: "spring", stiffness: 280, damping: 30 }}
              className="glass-strong fixed left-1/2 top-1/2 z-50 max-h-[88vh] w-full max-w-2xl -translate-x-1/2 -translate-y-1/2 overflow-y-auto rounded-2xl border border-white/50 p-5"
            >
              <VerifyExtraction
                extraction={verifyingMsg.extraction!}
                onConfirm={(edits) => store.confirmVerification(verifyingMsg.id, edits)}
              />
            </motion.div>
          </>
        )}
      </AnimatePresence>

      {/* Expected-competitors gate — optional 2nd popup, same no-backdrop-dismiss treatment as the
          verify-extraction gate above. Skip/Add are the only exits, both of which actually finalize
          the report via the store. */}
      <AnimatePresence>
        {awaitingCompetitorsMsg && (
          <>
            <motion.div
              initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
              className="fixed inset-0 z-50 bg-black/25 backdrop-blur-[2px]"
            />
            <motion.div
              initial={{ opacity: 0, y: 16, scale: 0.98 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: 16, scale: 0.98 }}
              transition={{ type: "spring", stiffness: 280, damping: 30 }}
              className="glass-strong fixed left-1/2 top-1/2 z-50 max-h-[88vh] w-full max-w-2xl -translate-x-1/2 -translate-y-1/2 overflow-y-auto rounded-2xl border border-white/50 p-5"
            >
              <VerifyCompetitors
                predicted={awaitingCompetitorsMsg.predictedCompetitors ?? []}
                loading={!!awaitingCompetitorsMsg.competitorsPredicting}
                onSubmit={(names) => store.submitCompetitors(awaitingCompetitorsMsg.id, names)}
                onSkip={() => store.skipCompetitors(awaitingCompetitorsMsg.id)}
              />
            </motion.div>
          </>
        )}
      </AnimatePresence>
    </div>
  );
}
