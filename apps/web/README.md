# BidIntel — frontend sandbox

A glass, seamless, data-rich console for an AI-native **bid intelligence platform** for civil/highway
contractors. This is a **clean-room frontend prototype** (no client code) — the demo that doubles as the YC
artifact and the Anthropic-FDE artifact. Backend is mocked; another track owns the real pipeline.

## Run

```bash
npm run dev      # http://localhost:3000
npm run build    # production build
npx tsc --noEmit # typecheck
```

## Stack

- **Next.js 16** (App Router, RSC, TypeScript, `src/`)
- **Tailwind v4** + **shadcn/ui** primitives
- **Vercel AI SDK** (`ai`, `@ai-sdk/anthropic`) — for live Claude streaming (next slice)
- **motion** (Framer Motion), **recharts** (charts), **react-simple-maps** (territory map),
  **cmdk** (command palette), **@number-flow/react** (animated counters), **react-dropzone**

## Design system

Anthropic-grade "bone/clay" aesthetic, defined once in `src/app/globals.css`:

- **Palette** — bone canvas `#F0EEE6`, clay-coral accent `#D97757`, warm chart palette (clay · gold ·
  sage · slate · plum) as `--chart-1..5`; semantic `--positive / --negative / --warn`.
- **Type** — Fraunces serif display (`font-serif`) + Geist sans body.
- **Glass** — `.glass` / `.glass-strong` frosted panels, `.sheen` top-light, `.ambient-mesh` drifting
  gradient backdrop, `.shimmer` skeletons, thin custom scrollbars. Reduced-motion safe.
- **Shared primitives** — `src/components/kit.tsx`: `Glass`, `Stat` (NumberFlow KPI), `SectionTitle`,
  `Eyebrow`, `Chip`, `Reveal`. Every page composes these for coherence.
- **Mock data** — `src/lib/data.ts` is the single source of truth (projects w/ MN/ND/SD coords,
  work-type archetypes, pipeline funnel, bid-tab pricing, competitors). `src/lib/mock-plan.ts` holds the
  provenance plan (gotchas w/ verbatim evidence + page) shaped to the real `schema.py`.

## Routes

| Route | Surface |
|---|---|
| `/` | **Overview** — KPIs, pre-award funnel, hottest opportunities, $22.3M-on-the-table insight, by-territory |
| `/chat` | **Ask BidIntel** — Claude-grade estimator copilot: multi-conversation rail, construction-flavored "thinking", drag-to-attach plan sets, **live context-window meter** (1M, segmented by system/docs/chat), per-source token weights, cited answers, markdown/tables, message actions |
| `/ingest` | **Plan ingestion** — glass drag-drop → 4-stage streaming extraction → result reveal |
| `/opportunities` | **Workspace** — go/no-bid card + gotchas ↔ plan viewer w/ verbatim source highlight (provenance) |
| `/sweet-spot` | **Sweet Spot** — fit×margin quadrant scatter, work-type edge ranking, messiness insight, ranked opps |
| `/map` | **Territory** — react-simple-maps tri-state map, value-scaled opportunity bubbles, competitor turf |
| `/pricing` | **Pricing intelligence** — bid-tab unit prices, ranges, 4-yr trends, by-state comparison (the moat) |

Global shell (`src/components/app-shell.tsx`): glass sidebar + topbar + ⌘K command palette.

## Not yet wired (next slices)

- Live Claude streaming via an AI SDK route handler (needs `ANTHROPIC_API_KEY`) — stream the go/no-bid
  card as real generative UI.
- Real PDF render (react-pdf) in the plan viewer — the selection contract (`page + evidence`) is ready.
- FastAPI bridge to the real Plan Reader pipeline (the other track) → swap mock data for `schema.py` JSON.
