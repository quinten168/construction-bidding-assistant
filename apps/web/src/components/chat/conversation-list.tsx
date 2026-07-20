"use client";

import { motion } from "motion/react";
import { MessageSquare, Paperclip, Trash2 } from "lucide-react";
import { type Conversation } from "@/lib/chat-data";
import { NewChatButton } from "./composer";
import { Eyebrow } from "@/components/kit";
import { cn } from "@/lib/utils";

export function ConversationList({
  conversations,
  activeId,
  onSelect,
  onNew,
  onDelete,
}: {
  conversations: Conversation[];
  activeId: string;
  onSelect: (id: string) => void;
  onNew: () => void;
  onDelete: (id: string) => void;
}) {
  return (
    <div className="flex h-full flex-col gap-3 px-3 py-4">
      <NewChatButton onClick={onNew} />

      <div className="px-1">
        <Eyebrow>Chats</Eyebrow>
      </div>

      <div className="flex-1 space-y-0.5 overflow-y-auto">
        {conversations.map((c) => {
          const active = c.id === activeId;
          const last = c.messages.at(-1);
          return (
            <div
              key={c.id}
              role="button"
              tabIndex={0}
              onClick={() => onSelect(c.id)}
              onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && onSelect(c.id)}
              className={cn(
                "group relative flex w-full cursor-pointer flex-col gap-0.5 rounded-xl px-3 py-2 text-left transition-colors",
                active ? "text-foreground" : "text-muted-foreground hover:bg-white/40 hover:text-foreground",
              )}
            >
              {active && (
                <motion.span
                  layoutId="chat-active"
                  className="absolute inset-0 -z-10 rounded-xl bg-white/70 shadow-sm ring-1 ring-black/5"
                  transition={{ type: "spring", stiffness: 380, damping: 32 }}
                />
              )}
              <div className="flex items-center gap-2 pr-6">
                <MessageSquare className={cn("h-3.5 w-3.5 shrink-0", active && "text-primary")} />
                <span className="truncate text-[13px] font-medium">{c.title}</span>
              </div>
              <div className="flex items-center gap-2 pl-5.5 text-[11px] text-muted-foreground/70">
                <span className="truncate">
                  {last ? (last.role === "user" ? "You: " : "") + last.content.replace(/[*#>`|]/g, "").slice(0, 32) : "Empty chat"}
                </span>
              </div>
              <div className="flex items-center gap-2 pl-5.5 text-[10px] text-muted-foreground/60">
                <span>{c.updatedLabel}</span>
                {c.fileIds.length > 0 && (
                  <span className="inline-flex items-center gap-0.5">
                    <Paperclip className="h-2.5 w-2.5" /> {c.fileIds.length}
                  </span>
                )}
              </div>
              {/* Delete — appears on hover; stopPropagation so it doesn't also select the chat */}
              <button
                onClick={(e) => { e.stopPropagation(); onDelete(c.id); }}
                title="Delete chat"
                className="absolute right-2 top-2 grid h-6 w-6 place-items-center rounded-md text-muted-foreground opacity-0 transition-all hover:bg-black/5 hover:text-[var(--negative)] focus:opacity-100 group-hover:opacity-100"
              >
                <Trash2 className="h-3.5 w-3.5" />
              </button>
            </div>
          );
        })}
      </div>
    </div>
  );
}
