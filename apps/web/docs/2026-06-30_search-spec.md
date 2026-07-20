# Search — feature spec (CSI Bidding Intelligence)

Status: proposed · 2026-06-30 · owner: T
Context: we removed the Search + Pin rail icons (no functionality yet). This specs the
Search icon so it can be built as a real feature. Pin is deferred separately.

## Goal
Let Adam find things fast from one entry point (the ⌘K palette + the rail Search icon):
1. **His conversations** — "that Dunn County plan I reviewed last week".
2. **The plan corpus** — "which plans flagged a railroad crossing?" (semantic, across all
   indexed plans, not just this chat).

## Scope — two tiers, ship in order

### Tier 1 — Conversation search (client-only, ~1–2 hrs) ← build first
Search the user's own chat history. No backend. Instant.
- Data source: the `conversations` already in `useChatStore` / localStorage
  (`csi-bidiq-chat-v1`). Each has `title` + `messages[].content`.
- UI: a command palette (reuse `cmdk`, already a dependency — see the old
  `app-shell.tsx CommandPalette`). Open on ⌘K and on the rail Search icon.
- Match: case-insensitive substring over `title` + every message `content`
  (assistant + user). Rank: title hit > message hit; recent > old.
- Result row: conversation title + a snippet with the match highlighted + relative date.
  Enter / click → `selectConversation(id)` and (optional) scroll to the matched message.
- Empty state: "No chats match '<q>'."
- Wire-up: add `searchConversations(query)` to `useChatStore` returning
  `{ convId, title, snippet, msgId }[]`; palette calls it on each keystroke (debounced 120ms).

### Tier 2 — Corpus / plan search (backend, ~half day)
Search across ALL indexed plans (185+), not the current chat. This is the real
differentiator — "find me every ND mill-&-overlay with a tight schedule".
- Backend already has the retrieval: the agent's `search_plans` tool hits ChromaDB
  (`csi_plans`, metadata-filterable) + the master CSV. Two options:
  - (a) **Reuse the agent** — send the query through `/api/chat` with a hint to call
    `search_plans`; render the cited plans. Cheapest; no new endpoint.
  - (b) **New `GET /api/plans/search?q=&state=&work_type=`** — thin wrapper over
    `retriever.retrieve` + SQLite `plan_metrics`, returns structured hits
    `{ plan_id, title, state, county, work_type, n_gotchas, snippet, page }`. Better for a
    non-chat results grid + filters. **Recommended** once Tier 1 ships.
- Filters that map to existing chunk metadata / SQLite columns: `state`, `work_type`
  (archetype), `has_railroad`/gotcha type, year, county.
- UI: same palette, a "Search plans" tab/section under "Your chats"; each hit opens the
  plan (Tier-3 dependency below) or drops it into a new review thread.

## Dependencies / open
- Tier 2 result → "open plan" needs the **Plan Library** reopen path (parked next-phase:
  `GET /api/plans` + reopen without re-dropping). Until then, a corpus hit can only
  "ask about it" via chat, not reopen a saved report card.
- Keep Pin out until search lands; pinning is a separate, smaller feature (a `pinned:boolean`
  on Conversation + sort-to-top).

## Definition of done (Tier 1)
- ⌘K and the rail Search icon open the palette.
- Typing filters the user's conversations live; Enter opens the chat.
- No backend calls; works offline; respects the existing localStorage store.
