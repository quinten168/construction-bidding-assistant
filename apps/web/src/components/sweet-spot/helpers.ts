import { PROJECTS, WORK_TYPES, type Project, type WorkType } from "@/lib/data";

// ── Sweet-spot thresholds (the quadrant lines) ───────────────────
// A project lands in the "sweet spot" when model fit is strong AND the
// projected/realized margin clears the client's healthy-margin floor.
export const FIT_LINE = 60; // fit ≥ 60 = a "go" candidate
export const MARGIN_LINE = 10; // marginPct ≥ 10% = healthy work

// marginPct in the data is stored as whole-number percent (e.g. 14.2),
// so every calc here works in that same unit for consistency.
export type ScoredProject = Project & { marginVal: number; score: number; inSweetSpot: boolean };

// Treat a missing margin (no-bid passes) as 0 so they never look attractive.
const marginOf = (p: Project) => p.marginPct ?? 0;

// Simple, legible sweet-spot score: reward fit and margin together.
const scoreOf = (p: Project) => (p.fit / 100) * marginOf(p);

export function scoreProject(p: Project): ScoredProject {
  const marginVal = marginOf(p);
  return {
    ...p,
    marginVal,
    score: scoreOf(p),
    inSweetSpot: p.fit >= FIT_LINE && marginVal >= MARGIN_LINE,
  };
}

export const SCORED: ScoredProject[] = PROJECTS.map(scoreProject);

// ── Avg margin by work-type (drives the edge-ranking bar chart) ──
export type WorkTypeAgg = { workType: WorkType; avgMargin: number; n: number; edge: "high" | "med" | "low" };

export function avgMarginByWorkType(): WorkTypeAgg[] {
  return WORK_TYPES.map((wt) => {
    // Only count projects that actually have a margin (skip no-bid passes).
    const rows = PROJECTS.filter((p) => p.workType === wt && p.marginPct != null);
    const avg = rows.length ? rows.reduce((s, p) => s + (p.marginPct ?? 0), 0) / rows.length : 0;
    return { workType: wt, avgMargin: avg, n: rows.length, edge: rows[0]?.edge ?? "low" };
  }).sort((a, b) => b.avgMargin - a.avgMargin);
}

// Map edge tier → Chip tone for consistent coloring across the page.
export const EDGE_TONE: Record<"high" | "med" | "low", "primary" | "warn" | "neutral"> = {
  high: "primary",
  med: "warn",
  low: "neutral",
};
