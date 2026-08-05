// ────────────────────────────────────────────────────────────────────────────
// Chat domain model: conversations, messages, uploaded plan files, token
// accounting, and a mock "estimator copilot" response engine. Built to be
// swapped for the Vercel AI SDK useChat() later — the message/streaming shape
// mirrors it. Token math is domain-true: plan sets are huge, so the context
// meter is a real signal, not decoration.
// ────────────────────────────────────────────────────────────────────────────

import { PLAN } from "./mock-plan";
import { PRICE_ITEMS, COMPETITORS, fmtUSD } from "./data";

export type Role = "user" | "assistant";

export type Citation = { label: string; page: number; passage?: string };

// Real per-turn token usage from the backend (the honest context/usage signal).
// input_tokens = the true context size for that answer (system + tools + retrieved
// chunks + recent history) — NOT a whole-document estimate.
export type Usage = {
  input_tokens: number;
  output_tokens: number;
  cache_read_tokens?: number;
  cache_creation_tokens?: number;
  model?: string;
};

// ── Real assembled report (the shape returned by FastAPI POST /api/report → final) ──
// Mirrors backend/final_report.py::assemble. Scalar identity fields + bid-schedule
// quantities + gotchas split go/no-go vs pricing. (No recommendation/per-field
// confidence yet — the backend doesn't produce those.)
export type FinalGotcha = {
  code: string;
  family?: string | null;
  evidence?: string;
  page?: number | string | null;
  page_count?: number | null;
  confidence?: string | null;
};
// ── Competitive landscape (§④) — mirrors backend/competitor_report.py::parse_report (v3 schema).
// The Competitor Intel team's model output, matched to this plan on county+state+date. As of v3
// this is a single flat top-N ranking (no Priority/Discovery tiers — CSI's tracked-list membership
// never drove the ranking, only a display grouping that's now gone) + structured per-competitor
// attributes — NO numeric threat scores. An estimator can also type in names they personally expect
// to bid (the verify-competitors popup); genuinely new ones are appended to the same flat list and
// analyzed alongside the model's picks, duplicates of an existing name are not re-added.

// A rate scoped one way (state, county, or project_type) — raw counts alongside the percentage,
// never just the percentage alone (a lone "37%" hides whether that's 3/8 or 300/800).
export type ScopedRate = { wins?: number; bids?: number; total?: number; pct: number | null };
export type CompetitorStats = {
  win_rate: { state: ScopedRate; county: ScopedRate; project_type: ScopedRate } | null;
  bid_rate: { state: ScopedRate; county: ScopedRate; project_type: ScopedRate } | null;
  capacity: {
    typical_capacity: number | null; ytd_won: number; capacity_pct: number | null;
    last_year_total: number | null;
  } | null;
  pit_access: {
    nearest_pit: { name: string; distance_miles: number; quality: number | null } | null;
    pits_within_25mi_count: number;
    pits_within_25mi_avg_quality: number | null;
  } | null;
};

export type Competitor = {
  project_id: string;
  location: string;
  county: string;
  state: string;
  bid_date: string;
  work_type: string;
  condition: string;
  materials: string[];
  pits: { public?: string; private?: string };
  summary: { analyzed: number; narrative: string };
  // rank-ordered names, best match first (estimator-added names appended at the end)
  competitors: string[];
  // subset of `competitors` the estimator typed in themselves (the verify-competitors popup),
  // vs. model-predicted — UI-badge purposes only, not a separate list or ranking
  user_added?: string[];
  // names the estimator typed into the verify-competitors popup that were already on the list
  // (predicted, or an earlier name in the same submission) — not re-added, surfaced back so the
  // UI can tell them rather than silently dropping the name
  duplicate_names?: string[];
  // name → { "Bid Rate": "...", "Recency": "...", "Experience": "...", "Local Win Rate ...": "..." }
  attrs: Record<string, Record<string, string>>;
  deep_dives: Record<string, string[]>;
  source_file: string;
  // name → live-retrieved win/bid rate, capacity, pit access — same retrieval for every competitor
  // on the report regardless of tier (predicted or estimator-added).
  stats?: Record<string, CompetitorStats>;
  // how confident the county+state(+date) join is — surface it so a wrong match is visible
  _match?: { confidence: "high" | "medium" | "low" | string; basis: string; date_gap_days: number | null };
};
export type FinalReport = {
  plan_id: string;
  title: string;
  archetype: string;
  pages?: number | null; // real page count from the backend (structure.n_pages)
  identity: Record<string, string | number | boolean | null>;
  tldr: string;
  quantities: { label: string; value: number | string; unit: string }[];
  gotchas: { go_no_go: FinalGotcha[]; pricing: FinalGotcha[] };
  gotcha_source?: string;
  competitor?: Competitor | null;
};

// ── Unverified extraction (POST /api/report, phase ①) — mirrors backend/report.py::process_pdf's
// return shape BEFORE final_report.assemble runs. Same identity/quantities grain as FinalReport,
// plus field_confidence (real 3-level confidence — "high"|"medium"|"low", not a percentage — and
// the source page, per field) for the verify gate to flag what needs a human look. content_hash +
// verified round-trip back to POST /api/report/{plan_id}/finalize unchanged.
export type FieldMeta = { confidence: "high" | "medium" | "low" | null; page: number | null };
export type Extraction = {
  plan_id: string;
  archetype: string;
  identity: Record<string, string | number | boolean | null>;
  quantities: { label: string; value: number | string; unit: string }[];
  gotchas: FinalGotcha[];
  field_confidence: Record<string, FieldMeta>;
  content_hash: string;
  verified: false;
};

export type ChatMessage = {
  id: string;
  role: Role;
  content: string; // markdown for assistant
  citations?: Citation[];
  status?: "thinking" | "streaming" | "done";
  tokens: number;
  attachedFileIds?: string[];
  turnId?: string; // backend turn id (for thumbs feedback → POST /api/feedback)
  final?: FinalReport; // real assembled report from POST /api/report/{id}/finalize (phase ②)
  reportError?: string; // set when /api/report failed (e.g. drawings-only plan set)
  // ── signature PDF→report flow ──
  // When set, this assistant turn renders the inline plan REPORT CARD instead of
  // (or after) prose. `narration` drives the Claude-Code-style processing steps;
  // `narrationStep` is the live index; `card` flips on once narration completes.
  kind?: "text" | "report";
  narration?: string[];
  narrationStep?: number;
  card?: boolean; // render the report card body
  planFile?: string; // the dropped file name, for the card header
  // Human-in-the-loop verify gate, between extraction (phase ①) and assembly (phase ②).
  // `verifying` true = extraction landed and is waiting on the human before finalize() runs;
  // `extraction` is that phase-① payload, seeding the verify modal.
  verifying?: boolean;
  extraction?: Extraction;
  // Optional 2nd popup, between the verify-extraction gate and finalize: the estimator can type in
  // competitors they personally expect to bid. `pendingEdits` carries phase-①'s edits through this
  // extra step so finalize still gets them once this step completes (skip or submit).
  awaitingCompetitors?: boolean;
  pendingEdits?: Record<string, string>;
};

export type UploadedFile = {
  id: string;
  name: string;
  pages: number;
  tokens: number;
  status: "parsing" | "ready";
  kind: "plan" | "bidtab" | "spec";
};

export type Conversation = {
  id: string;
  title: string;
  messages: ChatMessage[];
  fileIds: string[];
  updatedLabel: string;
};

// ── Token accounting (Claude 1M context) ──
export const CONTEXT_BUDGET = 1_000_000;
export const SYSTEM_TOKENS = 4_200; // system prompt + tools + taxonomy
export const TOKENS_PER_PAGE = 1_800; // dense civil plan page
export const estTextTokens = (s: string) => Math.max(1, Math.round(s.length / 4));
export const pagesToTokens = (pages: number) => pages * TOKENS_PER_PAGE;

// ── Seed uploaded files ──
// Empty: a real session starts with no files in context. Files appear only when
// the user attaches a plan (which runs the real pipeline). The mock pre-loaded
// corpus (Dunn/MnDOT/letting) was prototype scaffolding — removed.
export const SEED_FILES: UploadedFile[] = [];

// ── Construction-flavored "thinking" phrases (rotate while generating) ──
export const THINKING_STEPS = [
  "Surveying the plan set",
  "Staking out the quantities",
  "Grading the line items",
  "Pulling the spec book",
  "Checking prevailing wage",
  "Running the bid tabs",
  "Squaring the corners",
  "Backfilling the rationale",
  "Pouring the recommendation",
];

// ── PDF→report processing narration (Claude-Code-style, estimator language) ──
// Streamed one line at a time with a spinner before the report card renders.
export const REPORT_NARRATION = [
  "Reading the plan set…",
  "Detecting document structure (proposal vs. plan-set pages)…",
  "Extracting the bid schedule — quantities, units, item codes…",
  "Pulling project identity — owner, engineer, deadline, bid security…",
  "Reading contract times & phasing milestones…",
  "Scanning the 20-type gotcha taxonomy…",
  "Cross-checking unit prices against the ND bid-tab history…",
  "Building the extraction — pinning every figure to its page…",
];

// ── Suggested starter prompts ──
export const STARTERS = [
  { icon: "◆", title: "Should we bid Dunn County?", sub: "A grounded go / no-go with rationale" },
  { icon: "⚑", title: "What gotchas are in this plan?", sub: "Every flag, quoted verbatim with its page" },
  { icon: "$", title: "What's HMA running in ND?", sub: "Unit price vs. the bid-tab history" },
  { icon: "◎", title: "Who beats us in South Dakota?", sub: "Likely competitors and their turf" },
  { icon: "▦", title: "How did we do on bids last year?", sub: "Win rate, margin, where we left money" },
  { icon: "⛏", title: "What are the headline quantities?", sub: "Tonnage straight off the bid schedule" },
];

// ── Mock response engine ──────────────────────────────────────────────
// Returns markdown + citations for a user message. Keyword-routed, grounded in
// the Dunn County plan + pricing/competitor data. Swap for a real model call later.
export type MockReply = { content: string; citations: Citation[] };

export function generateReply(userText: string): MockReply {
  const t = userText.toLowerCase();

  if (/(bid|no-?go|no-?bid|should we|recommend|pursue|chase)/.test(t)) {
    return {
      content: `**Recommendation: Bid** — confidence **82%**.

The **${PLAN.title}** is a *Reconstruct/Rebuild* set (GRADE + MIX present), which is your highest-margin work type. Three reasons it fits:

- You've won **7 of 9** earthwork-heavy jobs in the ND turf over three years.
- Backlog suggests open capacity in **Q4**.
- Projected margin **14.2%**, above your trailing-12 average of 12.1%.

**Two risks to price in:**

1. **Enhanced SWPPP** — Missouri River buffer pushes storm-water scope past your norm.
2. **Seasonal cutoff** — no wearing course after **Oct 1**, which compresses the schedule against the liquidated-damages clause.

Net: a bid, but carry a risk premium for the SWPPP and the weather window.`,
      citations: [
        { label: "§1804 Progress & Completion", page: 31 },
        { label: "§2573 Storm Water", page: 68 },
        { label: "§2105 Seasonal Limits", page: 47 },
      ],
    };
  }

  if (/(gotcha|risk|flag|catch|watch out|special)/.test(t)) {
    const lines = PLAN.gotchas
      .map((g) => `- **${g.title}** (${g.family === "go_no_go" ? "go/no-go" : "pricing"}) — ${g.explanation}\n  > “${g.evidence}” — *p.${g.page}*`)
      .join("\n");
    return {
      content: `I found **${PLAN.gotchas.length} gotchas** in this set — ${PLAN.gotchas.filter((g) => g.family === "go_no_go").length} go/no-go signals and ${PLAN.gotchas.filter((g) => g.family === "pricing").length} pricing inputs. Each is quoted verbatim from the plan:

${lines}

Want me to fold these into the estimate as cost adjustments?`,
      citations: PLAN.gotchas.slice(0, 4).map((g) => ({ label: g.section, page: g.page })),
    };
  }

  if (/(price|cost|unit|hma|asphalt|rate|\$|ton|aggregate|mill)/.test(t)) {
    const hma = PRICE_ITEMS[0];
    const nd = hma.byState.find((b) => b.state === "ND");
    return {
      content: `From the public bid tabs, **${hma.item}** (item ${hma.code}) is running:

- **ND average: $${nd?.avg.toFixed(2)}/ton** — vs $${hma.byState.find((b) => b.state === "MN")?.avg.toFixed(2)} in MN.
- Cross-state range **$${hma.low}–$${hma.high}/ton**.
- Up from $${hma.trend[0].price.toFixed(2)} in ${hma.trend[0].year} → **+${(((hma.trend.at(-1)!.price - hma.trend[0].price) / hma.trend[0].price) * 100).toFixed(0)}%** over four years.

For the Dunn set's **6,296 tons**, that's roughly **${fmtUSD(6296 * (nd?.avg ?? 55))}** of HMA at the running average — price slightly under to stay competitive on the low-bid wins.`,
      citations: [{ label: "Bid schedule §2360", page: 12 }],
    };
  }

  if (/(competitor|who else|who beats|turf|rival|against|bidder|beat us)/.test(t)) {
    // Read the state out of the question; default to ND (the active Dunn set).
    const stateAsked = /south dakota|\bsd\b/.test(t) ? "SD" : /minnesota|\bmn\b/.test(t) ? "MN" : "ND";
    const stateName = stateAsked === "SD" ? "South Dakota" : stateAsked === "MN" ? "Minnesota" : "North Dakota";
    const list = COMPETITORS.filter((c) => c.turf === stateAsked).sort((a, b) => b.bids - a.bids);
    const lines = list
      .map((c) => `- **${c.name}** — ${c.bids} bids, ${(c.winRate * 100).toFixed(0)}% win rate, ${(c.capacityUsedPct * 100).toFixed(0)}% capacity ${c.capacityUsedPct > 0.8 ? "*(at capacity — may bid soft)*" : c.capacityUsedPct < 0.55 ? "*(hungry — likely aggressive)*" : ""}`)
      .join("\n");
    const top = list[0];
    const hungry = list.find((c) => c.capacityUsedPct < 0.55);
    return {
      content: `In **${stateName}**, expect these likely bidders by turf:

${lines}

**${top?.name}** is the one to beat — most active on this turf${top && top.capacityUsedPct > 0.8 ? " and near capacity, so they may not price as sharp" : ""}.${hungry ? ` **${hungry.name}** is hungry and could undercut.` : ""} This is decision support — your estimators apply the local read on top.`,
      citations: [{ label: `Bid participation · ${stateAsked}`, page: 1 }],
    };
  }

  if (/(last year|how did we|win rate|track record|history|left on|margin|overpay)/.test(t)) {
    return {
      content: `Here's the read on last season's bids:

- **Win rate: 19.4%** — you won **117 of 603** projects you bid. That's a row-derived number (your bid ranked 1st), not the old 70% figure that was really a row count.
- **Average margin: 12.1%** on the work you took.
- **Money left on the table: ~$22.3M** — mostly overbidding on jobs you *did* win, where a sharper number still wins and keeps more.

Where you're strongest: **Reconstruct/Rebuild** sets (GRADE + MIX) — your highest-margin work type. Where you bleed: commodity **Mill & Overlay**, where you're one of eight bidders and price is the only lever. The pattern says chase messy reconstructs, pass on clean resurfaces.`,
      citations: [{ label: "CSI bid history 2023–24", page: 1 }],
    };
  }

  if (/(quantit|takeoff|tonnage|how much|excavat)/.test(t)) {
    return {
      content: `Headline quantities pulled from the bid schedule (the authoritative source — ignoring the ~17 places these numbers are *referenced* elsewhere in prose):

| Item | Quantity | Unit |
|---|---|---|
| HMA Type SP 9.5 Wearing | **6,296** | TON |
| HMA Type SP 12.5 Non-wear | 4,118 | TON |
| Aggregate Base Class 5 | 9,840 | TON |

The bid schedule governs over any quantity referenced elsewhere in the plan. Confidence on the HMA figure is 98% — it landed within ~1% of CSI's hand-keyed value in the validation harness.`,
      citations: [{ label: "Bid schedule §2360.509", page: 12 }],
    };
  }

  return {
    content: `I'm your estimating copilot for this plan set. I've read **${PLAN.title}** (${PLAN.pages} pages) and have the MnDOT spec book and ND bid-tab history loaded.

Ask me things like:

- *"Should we bid this?"* — a grounded go/no-go with rationale
- *"What are the gotchas?"* — every flag, quoted verbatim with its page
- *"What's HMA running in ND?"* — unit pricing from the public bid tabs
- *"Who else will bid?"* — likely competitors and their turf

Everything I tell you is cited back to the page it came from.`,
    citations: [],
  };
}

// Initial seed conversations so the multi-chat sidebar isn't empty.
// A real session opens to a single empty chat (the store inits activeId from [0]).
// The mock demo conversations (Dunn review / HMA pricing / Yankton) were prototype
// scaffolding — removed so the workspace starts clean.
export const SEED_CONVERSATIONS: Conversation[] = [
  {
    id: "c-1",
    title: "New chat",
    fileIds: [],
    updatedLabel: "now",
    messages: [],
  },
];
