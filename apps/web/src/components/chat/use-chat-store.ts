"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  SEED_CONVERSATIONS, SEED_FILES, estTextTokens, pagesToTokens,
  REPORT_NARRATION,
  type Conversation, type ChatMessage, type Citation, type Extraction, type FinalReport, type Usage,
  type UploadedFile,
} from "@/lib/chat-data";

// Respect the user's reduced-motion preference for the timed narration cadence.
const prefersReducedMotion = () =>
  typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;

// Globally-unique ids. A plain counter resets to its start on every page reload, but persisted
// conversations keep their old ids — so a counter collides after refresh (two "c-101"s → React
// duplicate-key bug). A random suffix is unique across reloads.
const rand = () =>
  typeof crypto !== "undefined" && crypto.randomUUID
    ? crypto.randomUUID().slice(0, 8)
    : Math.random().toString(36).slice(2, 10);
const nextId = (p: string) => `${p}-${rand()}`;

// ── Persistence (survive a page refresh) ────────────────────────────────────
// The chat lives in React state, so a reload would wipe it. We snapshot the
// durable parts to localStorage and rehydrate on mount. (The backend also
// captures every turn in SQLite — this is the fast client-side restore; a
// server-backed history load can replace it later for multi-device.)
const STORE_KEY = "csi-bidiq-chat-v1";

type Persisted = {
  conversations: Conversation[];
  activeId: string;
  files: UploadedFile[];
  activePlanId: string | null;
  sessionTokens: number;
};

// On reload, no answer is mid-flight — collapse any half-streamed message to a
// settled state so we never restore a frozen "thinking…" bubble. Also dedupe by
// id (cleans any storage corrupted by the old colliding-id bug).
function sanitize(convs: Conversation[]): Conversation[] {
  const seen = new Set<string>();
  return convs
    .filter((c) => (seen.has(c.id) ? false : (seen.add(c.id), true)))
    .map((c) => ({
    ...c,
    messages: c.messages.map((m) => {
      if (m.role === "assistant" && m.kind === "report" && !m.card && !m.final) {
        return { ...m, kind: "text" as const, status: "done" as const, content: "Report wasn’t saved — re-drop the plan to rebuild it." };
      }
      return m.status && m.status !== "done" ? { ...m, status: "done" as const } : m;
    }),
  }));
}

// ── Real backend streaming ──────────────────────────────────────────────────
// Talk to the same-origin proxy route (/api/chat), which forwards to the FastAPI
// bid-assistant and streams Server-Sent Events back. The event protocol is:
//   {type:"token", text}    incremental answer text (many)
//   {type:"turn",  turn_id} id of the captured turn (for thumbs feedback)
//   {type:"sources", sources:[…]} cited passages (once, near the end)
//   {type:"done"}           stream complete
//   {type:"error", message} something failed — show it instead of hanging
type StreamHandlers = {
  onToken: (text: string) => void;
  onTurn?: (turnId: string) => void;
  onSources?: (citations: Citation[]) => void;
  onUsage?: (usage: Usage) => void;
  onError: (message: string) => void;
};

type BackendSource = { source_file?: string; page?: string | number; section?: string; doc_id?: string; text?: string };

async function streamChat(
  body: { question: string; history: { role: string; content: string }[]; active_plan_id?: string },
  h: StreamHandlers,
  signal: AbortSignal,
): Promise<void> {
  let res: Response;
  try {
    res = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal,
    });
  } catch {
    h.onError("Network error talking to the assistant.");
    return;
  }
  if (!res.ok || !res.body) {
    h.onError(`Assistant request failed (${res.status}).`);
    return;
  }

  // Parse the SSE byte stream: accumulate into a buffer, split on the blank-line
  // frame delimiter, and dispatch each `data: {…}` payload as it arrives.
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const frames = buffer.split("\n\n");
    buffer = frames.pop() ?? ""; // keep the last, possibly-incomplete frame
    for (const frame of frames) {
      const line = frame.trim();
      if (!line.startsWith("data:")) continue;
      let evt: {
        type: string; text?: string; turn_id?: string; sources?: BackendSource[]; message?: string;
        input_tokens?: number; output_tokens?: number; cache_read_tokens?: number;
        cache_creation_tokens?: number; model?: string;
      };
      try {
        evt = JSON.parse(line.slice(5).trim());
      } catch {
        continue; // ignore a malformed frame rather than killing the stream
      }
      if (evt.type === "token" && evt.text) h.onToken(evt.text);
      else if (evt.type === "turn" && evt.turn_id) h.onTurn?.(evt.turn_id);
      else if (evt.type === "sources") h.onSources?.(mapSources(evt.sources ?? []));
      else if (evt.type === "usage") h.onUsage?.({
        input_tokens: evt.input_tokens ?? 0, output_tokens: evt.output_tokens ?? 0,
        cache_read_tokens: evt.cache_read_tokens, cache_creation_tokens: evt.cache_creation_tokens,
        model: evt.model,
      });
      else if (evt.type === "error") h.onError(evt.message ?? "Unknown error.");
    }
  }
}

// A client-side request failure is NOT evidence the backend is down (2026-08-10). Ask
// /api/backend-health before saying so; the two cases must never render identically.
// `stage` is what the user was doing, so the sentence reads right in both branches.
async function explainClientFailure(stage: "reading the plan" | "finishing the report"): Promise<string> {
  try {
    const probe = await fetch("/api/backend-health", { cache: "no-store" });
    const health = (await probe.json()) as { reachable?: boolean; status?: string; detail?: string };
    if (health?.reachable) {
      return (
        `The browser lost the connection while ${stage}, but the backend is UP ` +
        `(${health.detail ?? "health check passed"}). The run is most likely still going — a large ` +
        `plan set takes several minutes. Wait for it to finish, then re-drop the same PDF: the ` +
        `finished run is cached by content hash and comes back immediately.`
      );
    }
    return (
      `Cannot reach the bid-assistant backend (${health?.detail ?? "health check failed"}). ` +
      `Is uvicorn running on :8010?`
    );
  } catch {
    // The health probe itself could not run — that means this Next.js server, not the
    // Python backend. Say that, rather than blaming uvicorn on no evidence.
    return `Lost the connection to this app while ${stage}, and the health check could not run either. Reload the page and check that both the Next.js dev server and uvicorn are up.`;
  }
}

// Upload a dropped PDF to the report endpoint (multipart) — phase ① of the verify gate: extraction
// only. A new plan takes 2–5+ min (convert → index → 2 Claude passes). Usually resolves with
// `extraction` (unverified — the caller shows the verify gate next); a re-drop of previously
// VERIFIED content resolves with `final` directly instead (backend content-hash cache, post-gate).
// NOTE: no AbortController/timeout on purpose — the browser must be allowed to wait out a real
// multi-minute run. The server route (api/report/route.ts) owns the only deadline (30 min).
async function uploadReport(
  file: File,
): Promise<{ ok: boolean; final?: FinalReport; extraction?: Extraction; message?: string }> {
  const form = new FormData();
  form.append("file", file, file.name);
  try {
    const res = await fetch("/api/report", { method: "POST", body: form });
    if (!res.ok) return { ok: false, message: `Report request failed (${res.status}).` };
    return await res.json();
  } catch {
    return { ok: false, message: await explainClientFailure("reading the plan") };
  }
}

// Phase ② of the verify gate: bake the human's confirmed/edited fields into the extraction payload
// and assemble the final report (this is where competitor-intel generation actually runs).
async function finalizeReport(
  planId: string,
  extraction: Extraction,
  edits: Record<string, string>,
  manualCompetitors: string[] = [],
): Promise<{ ok: boolean; final?: FinalReport; message?: string }> {
  try {
    const res = await fetch(`/api/report/${encodeURIComponent(planId)}/finalize`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ extraction, edits, manual_competitors: manualCompetitors }),
    });
    if (!res.ok) return { ok: false, message: `Finalize request failed (${res.status}).` };
    return await res.json();
  } catch {
    return { ok: false, message: await explainClientFailure("finishing the report") };
  }
}

// Between the two verify-gate popups: run the competitor-prediction cascade right after extraction
// is confirmed/skipped, so the "expected competitors" popup can show what the model actually
// predicted instead of an empty list. Fails open (empty list) — this step never blocks the flow.
async function predictCompetitors(
  planId: string,
  extraction: Extraction,
  edits: Record<string, string>,
): Promise<{ ok: boolean; competitors: string[] }> {
  try {
    const res = await fetch(`/api/report/${encodeURIComponent(planId)}/predict-competitors`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ extraction, edits }),
    });
    if (!res.ok) return { ok: false, competitors: [] };
    const data = await res.json();
    return { ok: !!data.ok, competitors: data.competitors ?? [] };
  } catch {
    return { ok: false, competitors: [] };
  }
}

// Map the backend's retrieved passages onto the UI's Citation shape, de-duping
// repeats of the same file+page and dropping any without a usable page number.
function mapSources(sources: BackendSource[]): Citation[] {
  const seen = new Set<string>();
  const out: Citation[] = [];
  for (const s of sources) {
    const page = Number(s.page);
    const label = (s.source_file ?? s.doc_id ?? "source").replace(/\.pdf$/i, "");
    const key = `${label}#${page}`;
    if (!Number.isFinite(page) || seen.has(key)) continue;
    seen.add(key);
    out.push({ label, page, passage: (s.text ?? "").trim() || undefined });
  }
  return out;
}

export function useChatStore() {
  const [conversations, setConversations] = useState<Conversation[]>(SEED_CONVERSATIONS);
  const [files, setFiles] = useState<UploadedFile[]>(SEED_FILES);
  const [activeId, setActiveId] = useState<string>(SEED_CONVERSATIONS[0].id);
  const [busy, setBusy] = useState(false);
  const [activePlanId, setActivePlanId] = useState<string | null>(null); // scopes chat to a dropped plan
  const [lastUsage, setLastUsage] = useState<Usage | null>(null);        // real tokens for the last answer
  const [sessionTokens, setSessionTokens] = useState(0);                 // running input+output this session
  const [hydrated, setHydrated] = useState(false); // true once localStorage has been read
  const timers = useRef<ReturnType<typeof setTimeout>[]>([]);
  const aborters = useRef<AbortController[]>([]); // in-flight chat streams (for cleanup/cancel)

  const active = conversations.find((c) => c.id === activeId) ?? conversations[0];

  // Rehydrate from localStorage once on mount (client-only → no SSR mismatch).
  useEffect(() => {
    try {
      const raw = localStorage.getItem(STORE_KEY);
      if (raw) {
        const s = JSON.parse(raw) as Persisted;
        if (s.conversations?.length) {
          const convs = sanitize(s.conversations);
          setConversations(convs);
          setActiveId(convs.some((c) => c.id === s.activeId) ? s.activeId : convs[0].id);
          // Dedupe by id — stale localStorage (from the old counter-id scheme) can hold two files
          // with the same id (e.g. "f-101"), which trips React's duplicate-key guard on render.
          if (s.files) {
            const seen = new Set<string>();
            setFiles(s.files.filter((f) => (seen.has(f.id) ? false : (seen.add(f.id), true))));
          }
          if (s.activePlanId) setActivePlanId(s.activePlanId);
          if (typeof s.sessionTokens === "number") setSessionTokens(s.sessionTokens);
        }
      }
    } catch {
      /* corrupt storage → start fresh */
    }
    setHydrated(true);
  }, []);

  // Persist on change — but only after hydration, so first render's seed can't
  // clobber saved state.
  useEffect(() => {
    if (!hydrated) return;
    try {
      const snapshot: Persisted = { conversations, activeId, files, activePlanId, sessionTokens };
      localStorage.setItem(STORE_KEY, JSON.stringify(snapshot));
    } catch {
      /* quota / private mode → skip persistence silently */
    }
  }, [hydrated, conversations, activeId, files, activePlanId, sessionTokens]);

  // Patch a single message inside a conversation (functional → no stale closures).
  const patchMessage = useCallback((convId: string, msgId: string, patch: Partial<ChatMessage>) => {
    setConversations((prev) =>
      prev.map((c) =>
        c.id !== convId ? c : { ...c, messages: c.messages.map((m) => (m.id === msgId ? { ...m, ...patch } : m)) },
      ),
    );
  }, []);

  const newConversation = useCallback(() => {
    const id = nextId("c");
    setConversations((prev) => [
      { id, title: "New chat", messages: [], fileIds: [], updatedLabel: "now" },
      ...prev,
    ]);
    setActiveId(id);
    setActivePlanId(null); // a fresh thread starts with no plan in context
    return id;
  }, []);

  const selectConversation = useCallback((id: string) => setActiveId(id), []);

  // Delete a conversation. If it was active, fall back to the top remaining one; if it was the
  // last conversation, replace it with a fresh empty chat so the app always has one.
  const deleteConversation = useCallback(
    (id: string) => {
      const remaining = conversations.filter((c) => c.id !== id);
      if (remaining.length === 0) {
        const fresh: Conversation = { id: nextId("c"), title: "New chat", messages: [], fileIds: [], updatedLabel: "now" };
        setConversations([fresh]);
        setActiveId(fresh.id);
        setActivePlanId(null);
      } else {
        setConversations(remaining);
        if (activeId === id) {
          setActiveId(remaining[0].id);
          setActivePlanId(null);
        }
      }
    },
    [conversations, activeId],
  );

  const send = useCallback(
    (text: string) => {
      if (!text.trim() || busy) return;
      const convId = activeId;
      const conv = conversations.find((c) => c.id === convId);

      // Replay prior turns to the stateless backend (it owns retrieval, not history).
      const history = (conv?.messages ?? [])
        .filter((m) => m.content && (m.role === "user" || m.status === "done"))
        .map((m) => ({ role: m.role, content: m.content }));

      const userMsg: ChatMessage = { id: nextId("m"), role: "user", content: text, tokens: estTextTokens(text) };
      const asstId = nextId("m");
      const asstMsg: ChatMessage = { id: asstId, role: "assistant", content: "", status: "thinking", tokens: 0 };

      // Append both; auto-title the conversation from the first user turn.
      setConversations((prev) =>
        prev.map((c) =>
          c.id !== convId
            ? c
            : {
                ...c,
                title: c.messages.length === 0 ? text.slice(0, 38) : c.title,
                updatedLabel: "now",
                messages: [...c.messages, userMsg, asstMsg],
              },
        ),
      );
      setBusy(true);

      // Stream the real answer. The first token flips "thinking" → "streaming";
      // we accumulate content locally and patch the running text each token.
      let acc = "";
      let started = false;
      const controller = new AbortController();
      aborters.current.push(controller);

      streamChat(
        { question: text, history, active_plan_id: activePlanId ?? undefined },
        {
          onToken: (chunk) => {
            acc += chunk;
            if (!started) {
              started = true;
              patchMessage(convId, asstId, { status: "streaming" });
            }
            patchMessage(convId, asstId, { content: acc });
          },
          onSources: (citations) => patchMessage(convId, asstId, { citations }),
          onTurn: (turnId) => patchMessage(convId, asstId, { turnId }),
          onUsage: (u) => {
            setLastUsage(u);
            setSessionTokens((s) => s + (u.input_tokens || 0) + (u.output_tokens || 0));
          },
          onError: (message) => {
            patchMessage(convId, asstId, {
              status: "done",
              content: acc || `⚠️ ${message}`,
              tokens: estTextTokens(acc),
            });
            setBusy(false);
          },
        },
        controller.signal,
      ).then(() => {
        // Stream ended cleanly (the backend sent {type:"done"}).
        patchMessage(convId, asstId, { status: "done", content: acc, tokens: estTextTokens(acc) });
        setBusy(false);
      });
    },
    [activeId, busy, conversations, patchMessage, activePlanId],
  );

  // ── Signature flow: drop a PDF → narrate processing → render the report card ──
  // Creates a "report" assistant turn, advances the narration step-by-step, then
  // flips the card on. Scoped to whichever file was dropped (header label).
  // Shared by processPlan's cache-hit branch (re-drop of already-verified content, final arrives
  // immediately) and confirmVerification (the normal path, final arrives after the verify gate) —
  // both end the same way: render the card, scope the chat to the plan, rename the conversation.
  const applyFinalReport = useCallback(
    (convId: string, asstId: string, fileName: string, final: FinalReport) => {
      setActivePlanId(final.plan_id);
      // Replace the placeholder page count with the REAL one from the backend, and mark ready.
      const realPages = final.pages;
      setFiles((prev) => prev.map((x) =>
        x.name === fileName && x.kind === "plan"
          ? { ...x, status: "ready", ...(realPages ? { pages: realPages, tokens: pagesToTokens(realPages) } : {}) }
          : x));
      // Rename the conversation to the clean project name (e.g. "Chippewa Co, MN").
      const projectName = final.title;
      setConversations((prev) =>
        prev.map((c) => (c.id === convId && projectName ? { ...c, title: projectName } : c)),
      );
      // Any manually-typed competitor names that duplicated an existing one (predicted, or an
      // earlier name in the same submission) were not re-added — tell the estimator why the
      // report's count didn't go up by however many they typed.
      const dupes = final.competitor?.duplicate_names ?? [];
      const dupeNote = dupes.length
        ? ` (${dupes.map((n) => `"${n}"`).join(", ")} ${dupes.length === 1 ? "was" : "were"} already in the report — not added again.)`
        : "";
      patchMessage(convId, asstId, {
        status: "done", card: true, final, verifying: false, extraction: undefined,
        awaitingCompetitors: false, pendingEdits: undefined,
        content: `I read **${fileName}** end to end. Here's the full report — every figure pinned to its source page.${dupeNote}`,
        tokens: 90,
      });
      setBusy(false);
    },
    [patchMessage],
  );

  // Phase ② trigger, now deferred behind the optional "expected competitors" popup: the verify
  // modal's Confirm/Skip no longer finalize directly — they stash the edits and hand off to that
  // second, optional step. `submitCompetitors`/`skipCompetitors` (below) are what actually calls
  // finalizeReport(), once that step completes (with or without any names).
  //
  // The popup opens immediately in a loading state, then predictCompetitors() runs the same
  // cascade finalize would otherwise run blind, so the estimator sees the model's predicted names
  // before deciding whether to add anyone — instead of typing into what looks like an empty list.
  const confirmVerification = useCallback(
    (messageId: string, edits: Record<string, string>) => {
      const convId = conversations.find((c) => c.messages.some((m) => m.id === messageId))?.id ?? activeId;
      const msg = conversations.find((c) => c.id === convId)?.messages.find((m) => m.id === messageId);
      patchMessage(convId, messageId, {
        verifying: false, awaitingCompetitors: true, competitorsPredicting: true, pendingEdits: edits,
      });
      if (!msg?.extraction) return;
      predictCompetitors(msg.extraction.plan_id, msg.extraction, edits).then((res) => {
        patchMessage(convId, messageId, {
          competitorsPredicting: false,
          predictedCompetitors: res.competitors,
        });
      });
    },
    [conversations, activeId, patchMessage],
  );

  // The actual finalize call, shared by submitCompetitors/skipCompetitors below (the only
  // difference between them is whether `manualCompetitors` is empty).
  const runFinalize = useCallback(
    async (messageId: string, manualCompetitors: string[]) => {
      const conv = conversations.find((c) => c.messages.some((m) => m.id === messageId));
      const msg = conv?.messages.find((m) => m.id === messageId);
      if (!conv || !msg?.extraction) return;
      setBusy(true);
      const res = await finalizeReport(msg.extraction.plan_id, msg.extraction, msg.pendingEdits ?? {}, manualCompetitors);
      if (!res.ok || !res.final) {
        patchMessage(conv.id, messageId, {
          status: "done", awaitingCompetitors: false, card: false, kind: "text",
          content: `⚠️ ${res.message || "Could not finish building the report."}`,
          reportError: res.message, tokens: 24,
        });
        setBusy(false);
        return;
      }
      applyFinalReport(conv.id, messageId, msg.planFile ?? "the plan", res.final);
    },
    [conversations, patchMessage, applyFinalReport],
  );

  const submitCompetitors = useCallback(
    (messageId: string, names: string[]) => runFinalize(messageId, names),
    [runFinalize],
  );

  const skipCompetitors = useCallback(
    (messageId: string) => runFinalize(messageId, []),
    [runFinalize],
  );

  const processPlan = useCallback(
    (file: File, targetConvId?: string) => {
      // No busy-guard: dropping a plan is an explicit intent. (The composer is
      // disabled while busy, so two concurrent flows can't be user-initiated.)
      const fileName = file.name;
      const convId = targetConvId ?? activeId;
      // The user "turn" for a dropped plan is the file itself — rendered as a chip in the
      // thread (ChatGPT-style), NOT a text line. Empty content keeps it out of chat history.
      const userMsg: ChatMessage = {
        id: nextId("m"), role: "user", content: "", planFile: fileName, tokens: 12,
      };
      const asstId = nextId("m");
      const asstMsg: ChatMessage = {
        id: asstId, role: "assistant", content: "", status: "thinking", tokens: 0,
        kind: "report", narration: REPORT_NARRATION, narrationStep: 0, card: false, planFile: fileName,
      };
      setConversations((prev) =>
        prev.map((c) =>
          c.id !== convId ? c : {
            ...c,
            title: c.messages.length === 0 ? `Plan review · ${fileName.replace(/\.pdf$/i, "")}` : c.title,
            updatedLabel: "now",
            messages: [...c.messages, userMsg, asstMsg],
          },
        ),
      );
      setBusy(true);

      // Kick off the REAL extraction immediately; narrate while we wait. The
      // narration advances through its steps and HOLDS on the last one until the
      // backend responds (a new plan is ~2 min; a cached re-drop returns in ~0s).
      const reportPromise = uploadReport(file);
      const reduced = prefersReducedMotion();
      // Per-step dwell (ms). Heavier passes (bid schedule, gotcha scan, cross-check,
      // final build) linger longer so it reads like a person actually working through
      // the document — not a fixed metronome blowing through 8 lines in 5 seconds. A
      // little variety per step + a slower overall cadence sells the "real work" feel.
      const STEP_MS = [1500, 2200, 3400, 2400, 2200, 3200, 2800, 3000];
      const dwell = (i: number) => (reduced ? 160 : STEP_MS[i] ?? 2200);
      const advance = (i: number) => {
        const last = REPORT_NARRATION.length - 1;
        patchMessage(convId, asstId, { narrationStep: Math.min(i, last) });
        if (i < last) {
          const t = setTimeout(() => advance(i + 1), dwell(i));
          timers.current.push(t);
        }
      };
      const first = setTimeout(() => advance(0), reduced ? 120 : 500);
      timers.current.push(first);

      reportPromise.then((res) => {
        if (!res.ok || (!res.final && !res.extraction)) {
          patchMessage(convId, asstId, {
            status: "done", card: false, kind: "text",
            content: `⚠️ ${res.message || "I couldn't read that plan."}`,
            reportError: res.message, tokens: 24,
          });
          setBusy(false);
          return;
        }
        if (res.final) {
          // Re-drop of content that was already verified before — skip the gate entirely, same
          // instant-return feel as the old single-phase cache hit.
          applyFinalReport(convId, asstId, fileName, res.final);
          return;
        }
        // Normal path: extraction landed, unverified — hold here and let the verify modal (opened
        // by chat-app.tsx off this message's `verifying` flag) drive what happens next.
        patchMessage(convId, asstId, {
          status: "done", card: false, verifying: true, extraction: res.extraction,
          content: `I read **${fileName}**. Before I pull competitor intel, take a look at what I extracted.`,
          tokens: 40,
        });
        setBusy(false);
      });
    },
    [activeId, patchMessage, applyFinalReport],
  );

  const attachFiles = useCallback(
    (incoming: File[]) => {
      // A dropped PDF is treated as "read this plan" → triggers the report flow,
      // not a silent attach. (CSVs/specs still just attach as context.)
      const pdfs = incoming.filter((f) => /\.pdf$/i.test(f.name));
      const others = incoming.filter((f) => !/\.pdf$/i.test(f.name));

      // One plan = one review thread. If a NEW plan lands in a conversation that already has
      // a plan/messages, start a FRESH thread so the new proposal gets a CLEAN context (the old
      // plan no longer lingers in the composer/sources). An empty chat is reused in place.
      const current = conversations.find((c) => c.id === activeId);
      const currentHasContent = !!current && (current.messages.length > 0 || current.fileIds.length > 0);
      const convId = pdfs.length > 0 && currentHasContent ? newConversation() : activeId;

      const created: UploadedFile[] = incoming.map((f) => {
        const isPdf = /\.pdf$/i.test(f.name);
        const pages = isPdf ? 214 : 38 + Math.floor(Math.random() * 30);
        return {
          id: nextId("f"), name: f.name, pages, tokens: pagesToTokens(pages),
          status: "parsing", kind: isPdf ? "plan" : /\.csv$/i.test(f.name) ? "bidtab" : "spec",
        };
      });
      setFiles((prev) => [...prev, ...created]);
      setConversations((prev) =>
        prev.map((c) => (c.id === convId ? { ...c, fileIds: [...c.fileIds, ...created.map((f) => f.id)] } : c)),
      );
      // Mark non-PDF context files ready (they aren't run through the pipeline).
      created.forEach((f, idx) => {
        const t = setTimeout(() => {
          setFiles((prev) => prev.map((x) => (x.id === f.id ? { ...x, status: "ready" } : x)));
        }, 1400 + idx * 700);
        timers.current.push(t);
      });

      // Kick off the real report flow for the first dropped PDF, in the target thread.
      if (pdfs.length > 0) {
        const t = setTimeout(() => processPlan(pdfs[0], convId), others.length ? 200 : 100);
        timers.current.push(t);
      }
    },
    [activeId, conversations, newConversation, processPlan],
  );

  const detachFile = useCallback(
    (fileId: string) => {
      const convId = activeId;
      setConversations((prev) => prev.map((c) => (c.id === convId ? { ...c, fileIds: c.fileIds.filter((id) => id !== fileId) } : c)));
    },
    [activeId],
  );

  return {
    conversations, files, active, activeId, busy, lastUsage, sessionTokens,
    newConversation, selectConversation, deleteConversation, send, attachFiles, detachFile, processPlan,
    confirmVerification, submitCompetitors, skipCompetitors,
  };
}

export type ChatStore = ReturnType<typeof useChatStore>;
