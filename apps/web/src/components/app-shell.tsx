"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { Command } from "cmdk";
import { motion } from "motion/react";
import {
  LayoutDashboard,
  Search,
  PanelLeft,
  Trophy,
  Mountain,
  Users,
  HardHat,
  SquarePen,
  MessageSquare,
  Trash2,
  ChevronDown,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { BRAND } from "@/lib/brand";
import { useChatStoreContext } from "@/components/chat/chat-store-context";

// Clean grouped IA, Claude/ChatGPT-style: icon + label only, no descriptor noise.
// "Overview" (the chat page) is deliberately NOT in this array any more (2026-08-11) -- it's
// rendered as the "New chat" action above Data instead, and Recents (below Data) is the way back
// to an existing conversation. Both need live store data / onClick handlers a static
// {href, label, icon} link can't carry, so they're hand-rendered in AppShell's JSX rather than
// data-driven like Data's items.
const NAV_GROUPS: {
  title?: string;
  items: { href: string; label: string; icon: typeof LayoutDashboard }[];
}[] = [
  {
    title: "Data",
    items: [
      { href: "/projects", label: "Projects", icon: HardHat },
      { href: "/bid-results", label: "Bid Results", icon: Trophy },
      { href: "/pit-list", label: "Pit List", icon: Mountain },
      { href: "/competitor-registry", label: "Competitors", icon: Users },
    ],
  },
];

const NAV = NAV_GROUPS.flatMap((g) => g.items);

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const store = useChatStoreContext();
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [collapsed, setCollapsed] = useState(false);
  // Independent of the whole-sidebar collapse above -- this just folds the Recents LIST closed
  // while keeping the rest of the sidebar (Data, the Recents label itself) visible, so a long
  // conversation history doesn't push everything else down/out of view. Starts open.
  const [recentsOpen, setRecentsOpen] = useState(true);
  const onChatPage = pathname === "/";
  const isEmptyChat = onChatPage && store.active.messages.length === 0;

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "k" && (e.metaKey || e.ctrlKey)) {
        e.preventDefault();
        setPaletteOpen((o) => !o);
      }
      if (e.key === "b" && (e.metaKey || e.ctrlKey)) {
        e.preventDefault();
        setCollapsed((c) => !c);
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, []);

  const go = (href: string) => {
    setPaletteOpen(false);
    router.push(href);
  };

  // "New chat" starts a fresh conversation and jumps to the chat page to show it. Disabled the
  // same way it was in chat-app.tsx's old rail: no-op (and greyed out) when already sitting on an
  // empty conversation, so clicking it there doesn't silently swap in an identical-looking empty
  // one with no visible change.
  const startNewChat = () => {
    if (isEmptyChat) return;
    store.newConversation();
    router.push("/");
  };

  const selectConversation = (id: string) => {
    store.selectConversation(id);
    router.push("/");
  };

  return (
    <div className="relative flex h-screen overflow-hidden">
      <div className="ambient-mesh" />

      {/* ── Sidebar (collapsible) ── */}
      <aside
        className={cn(
          "hidden shrink-0 flex-col border-r border-white/50 bg-white/35 backdrop-blur-2xl transition-[width] duration-300 ease-out md:flex",
          collapsed ? "w-[68px]" : "w-[244px]",
        )}
      >
        {/* Header: logo + collapse toggle */}
        <div className={cn("flex h-14 items-center px-3", collapsed ? "justify-center" : "justify-between")}>
          {!collapsed && (
            <Link href="/" className="flex items-center gap-2.5 px-1">
              <span className="grid h-8 w-8 place-items-center rounded-xl bg-primary text-[16px] text-primary-foreground elev-sm">◐</span>
              <span className="display text-[15px]">BidIntel</span>
            </Link>
          )}
          <button
            onClick={() => setCollapsed((c) => !c)}
            title="Toggle sidebar (⌘B)"
            className="grid h-8 w-8 place-items-center rounded-lg text-muted-foreground transition-colors hover:bg-black/[0.04] hover:text-foreground"
          >
            {collapsed ? <span className="text-[16px] text-primary">◐</span> : <PanelLeft className="h-[18px] w-[18px]" />}
          </button>
        </div>

        {/* Nav */}
        <nav className="flex flex-1 flex-col gap-5 overflow-y-auto px-3 py-3">
          {/* New chat — was "Overview" (a plain Link to "/"); now an action, since jumping to the
              chat page and starting a fresh conversation are the same click for every other entry
              point into chat (ChatGPT/Claude convention). Recents (below) is how you get back to
              an existing one instead. */}
          <button
            onClick={startNewChat}
            disabled={isEmptyChat}
            title={collapsed ? (isEmptyChat ? "Already on a new chat" : "New chat") : undefined}
            className={cn(
              "group relative flex items-center rounded-xl transition-colors",
              collapsed ? "h-10 w-10 justify-center self-center" : "gap-3 px-2.5 py-2",
              isEmptyChat
                ? "cursor-not-allowed text-muted-foreground/40"
                : "text-muted-foreground hover:text-foreground",
            )}
          >
            <SquarePen className="h-[18px] w-[18px] shrink-0" strokeWidth={2} />
            {!collapsed && <span className="text-[13.5px] font-medium">New chat</span>}
          </button>

          {NAV_GROUPS.map((group, gi) => (
            <div key={gi} className="flex flex-col gap-0.5">
              {group.title &&
                (collapsed ? (
                  <div className="mx-2 mb-1 h-px bg-black/[0.06]" />
                ) : (
                  <div className="px-2.5 pb-1 text-[10px] font-semibold uppercase tracking-[0.09em] text-muted-foreground/60">
                    {group.title}
                  </div>
                ))}
              {group.items.map((item) => {
                const active = item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
                const Icon = item.icon;
                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    title={collapsed ? item.label : undefined}
                    className={cn(
                      "group relative flex items-center rounded-xl transition-colors",
                      collapsed ? "h-10 w-10 justify-center self-center" : "gap-3 px-2.5 py-2",
                      active ? "text-foreground" : "text-muted-foreground hover:text-foreground",
                    )}
                  >
                    {active && (
                      <motion.span
                        layoutId="nav-active"
                        className="absolute inset-0 -z-10 rounded-xl border border-white/80 bg-white/85 elev-sm"
                        transition={{ type: "spring", stiffness: 380, damping: 32 }}
                      />
                    )}
                    <Icon className={cn("h-[18px] w-[18px] shrink-0", active && "text-primary")} strokeWidth={2} />
                    {!collapsed && <span className="text-[13.5px] font-medium">{item.label}</span>}
                  </Link>
                );
              })}
            </div>
          ))}

          {/* Chats / Recents — was ChatApp's own separate slide-out ConversationList, moved here
              2026-08-11 so it's reachable from every page, not just "/", and so there's one
              sidebar instead of two stacked ones when you ARE on the chat page. Collapsed mode
              hides the list body (a bare icon per conversation would be unreadable, unlike Data's
              small fixed set of static links) but keeps the group divider for consistency with
              how a titled NAV_GROUPS group collapses. */}
          <div className="flex flex-col gap-0.5">
            {collapsed ? (
              <div className="mx-2 mb-1 h-px bg-black/[0.06]" />
            ) : (
              <div className="px-2.5 pb-1 text-[10px] font-semibold uppercase tracking-[0.09em] text-muted-foreground/60">
                Chats
              </div>
            )}
            {!collapsed && (
              <>
                <button
                  onClick={() => setRecentsOpen((o) => !o)}
                  className="flex items-center gap-1 px-2.5 pb-1 text-[10px] font-medium text-muted-foreground/50 transition-colors hover:text-muted-foreground"
                >
                  <ChevronDown className={cn("h-3 w-3 transition-transform", !recentsOpen && "-rotate-90")} />
                  Recents
                </button>
                {recentsOpen && (
                <div className="flex flex-col gap-0.5">
                  {store.conversations.map((c) => {
                    const active = onChatPage && c.id === store.activeId;
                    return (
                      <div key={c.id} className="group/row relative">
                        <button
                          onClick={() => selectConversation(c.id)}
                          title={c.title}
                          className={cn(
                            "flex w-full items-center gap-3 rounded-xl px-2.5 py-2 pr-8 text-left transition-colors",
                            active ? "text-foreground" : "text-muted-foreground hover:text-foreground",
                          )}
                        >
                          {active && (
                            <motion.span
                              layoutId="nav-active"
                              className="absolute inset-0 -z-10 rounded-xl border border-white/80 bg-white/85 elev-sm"
                              transition={{ type: "spring", stiffness: 380, damping: 32 }}
                            />
                          )}
                          <MessageSquare className={cn("h-[16px] w-[16px] shrink-0", active && "text-primary")} strokeWidth={2} />
                          <span className="truncate text-[13px] font-medium">{c.title}</span>
                        </button>
                        {/* Delete — appears on hover, same convention the old ConversationList used */}
                        <button
                          onClick={(e) => { e.stopPropagation(); store.deleteConversation(c.id); }}
                          title="Delete chat"
                          className="absolute right-1.5 top-1/2 grid h-6 w-6 -translate-y-1/2 place-items-center rounded-md text-muted-foreground opacity-0 transition-all hover:bg-black/5 hover:text-[var(--negative)] focus:opacity-100 group-hover/row:opacity-100"
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                        </button>
                      </div>
                    );
                  })}
                </div>
                )}
              </>
            )}
          </div>
        </nav>

        {/* Footer: search + account */}
        <div className="flex flex-col gap-1 border-t border-black/[0.06] p-3">
          <button
            onClick={() => setPaletteOpen(true)}
            title="Search & ask (⌘K)"
            className={cn(
              "flex items-center rounded-xl text-muted-foreground transition-colors hover:bg-black/[0.04] hover:text-foreground",
              collapsed ? "h-9 w-9 justify-center self-center" : "justify-between px-2.5 py-2",
            )}
          >
            <span className="flex items-center gap-2 text-xs">
              <Search className="h-4 w-4" /> {!collapsed && "Search & ask"}
            </span>
            {!collapsed && <kbd className="rounded bg-secondary px-1.5 py-0.5 font-mono text-[10px]">⌘K</kbd>}
          </button>
          <div className={cn("flex items-center gap-2.5 rounded-xl px-2 py-1.5", collapsed && "justify-center px-0")}>
            <span className="grid h-7 w-7 shrink-0 place-items-center rounded-full bg-gradient-to-br from-primary to-[oklch(0.52_0.14_30)] text-xs text-primary-foreground elev-sm">
              {BRAND.user.initial}
            </span>
            {!collapsed && (
              <div className="leading-tight">
                <div className="text-[12px] font-medium">{BRAND.user.name}</div>
                <div className="text-[10px] text-muted-foreground">{BRAND.short}</div>
              </div>
            )}
          </div>
        </div>
      </aside>

      {/* ── Main column (fills the rest, scrolls internally) ── */}
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-14 shrink-0 items-center justify-between border-b border-white/50 bg-white/40 px-5 backdrop-blur-2xl">
          <div className="flex items-center gap-2.5">
            {/* "/" has no NAV_GROUPS entry any more (New chat/Recents replaced the old plain
                "Overview" link) -- show the active conversation's own title there instead of a
                static fallback string that no longer means anything. */}
            <span className="display text-[15px]">
              {onChatPage ? store.active.title : (NAV.find((n) => pathname.startsWith(n.href))?.label ?? "")}
            </span>
          </div>
          <button
            onClick={() => setPaletteOpen(true)}
            className="flex items-center gap-2 rounded-lg border border-black/5 bg-white/60 px-3 py-1.5 text-[12px] text-muted-foreground transition-colors hover:bg-white"
          >
            <Search className="h-3.5 w-3.5" /> Ask anything
            <kbd className="rounded bg-secondary px-1 font-mono text-[9px]">⌘K</kbd>
          </button>
        </header>

        <main className="min-h-0 flex-1 overflow-y-auto">{children}</main>
      </div>

      <CommandPalette open={paletteOpen} setOpen={setPaletteOpen} go={go} />
    </div>
  );
}

function CommandPalette({
  open,
  setOpen,
  go,
}: {
  open: boolean;
  setOpen: (o: boolean) => void;
  go: (href: string) => void;
}) {
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center pt-[18vh]" onClick={() => setOpen(false)}>
      <div className="absolute inset-0 bg-black/20 backdrop-blur-sm" />
      <motion.div
        initial={{ opacity: 0, scale: 0.97, y: -8 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        transition={{ type: "spring", stiffness: 300, damping: 26 }}
        className="glass-strong relative w-full max-w-lg overflow-hidden rounded-2xl shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <Command className="[&_[cmdk-input]]:outline-none">
          <div className="flex items-center gap-2 border-b border-black/5 px-4">
            <Search className="h-4 w-4 text-muted-foreground" />
            <Command.Input
              autoFocus
              placeholder="Jump to… or ask BidIntel"
              className="h-12 w-full bg-transparent text-sm outline-none placeholder:text-muted-foreground"
            />
          </div>
          <Command.List className="max-h-80 overflow-auto p-2">
            <Command.Empty className="px-3 py-6 text-center text-sm text-muted-foreground">No results.</Command.Empty>
            <Command.Group heading="Navigate" className="px-1 text-[11px] uppercase tracking-wide text-muted-foreground [&_[cmdk-group-heading]]:px-2 [&_[cmdk-group-heading]]:py-1.5">
              {NAV.map((n) => {
                const Icon = n.icon;
                return (
                  <Command.Item
                    key={n.href}
                    onSelect={() => go(n.href)}
                    className="flex cursor-pointer items-center gap-2.5 rounded-lg px-2.5 py-2 text-sm text-foreground data-[selected=true]:bg-primary/10"
                  >
                    <Icon className="h-4 w-4 text-muted-foreground" /> {n.label}
                  </Command.Item>
                );
              })}
            </Command.Group>
          </Command.List>
        </Command>
      </motion.div>
    </div>
  );
}
