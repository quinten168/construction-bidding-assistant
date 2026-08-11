"use client";

import { createContext, useContext } from "react";
import { useChatStore, type ChatStore } from "./use-chat-store";

// Single shared instance of useChatStore(), lifted out of ChatApp so AppShell's persistent
// sidebar (New chat button, Recents list) and the chat page itself read/write the exact same
// state — two independent useChatStore() calls would each own their own useState and silently
// diverge (a click in one place wouldn't be reflected in the other without a reload).
const ChatStoreContext = createContext<ChatStore | null>(null);

export function ChatStoreProvider({ children }: { children: React.ReactNode }) {
  const store = useChatStore();
  return <ChatStoreContext.Provider value={store}>{children}</ChatStoreContext.Provider>;
}

export function useChatStoreContext(): ChatStore {
  const ctx = useContext(ChatStoreContext);
  if (!ctx) throw new Error("useChatStoreContext() called outside <ChatStoreProvider>");
  return ctx;
}
