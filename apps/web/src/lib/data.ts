// ────────────────────────────────────────────────────────────────────────────
// Mock corpus for the BidIntel console. One source of truth for every dashboard,
// chart, and map. Grounded in the real client domain: MN/ND/SD counties, the
// two-axis archetype model (work-type × messiness × size), and bid outcomes.
// Deterministic (no Date/random at module load) so SSR + client hydrate identically.
// ────────────────────────────────────────────────────────────────────────────

export type WorkType =
  | "Reconstruct/Rebuild"
  | "Mill & Overlay"
  | "HMA Overlay"
  | "Grading/Earthwork"
  | "Aggregate/Base";

export type Status = "won" | "lost" | "no_bid" | "open";
export type StateCode = "MN" | "ND" | "SD";

export type Project = {
  id: string;
  name: string;
  county: string;
  state: StateCode;
  lat: number;
  lon: number;
  workType: WorkType;
  messiness: number; // 1 (clean) .. 10 (messy) — the client's #1 edge driver
  sizeTons: number; // native size (placed tons)
  valueUSD: number;
  fit: number; // 0..100 model fit score
  status: Status;
  marginPct: number | null; // realized margin for historicals; projected for open
  edge: "high" | "med" | "low";
  deadlineDays?: number; // for open opportunities
};

// Edge by work-type, per the client's archetype model (Reconstruct = highest).
const EDGE: Record<WorkType, "high" | "med" | "low"> = {
  "Reconstruct/Rebuild": "high",
  "Grading/Earthwork": "med",
  "HMA Overlay": "med",
  "Aggregate/Base": "low",
  "Mill & Overlay": "low",
};

function mk(
  id: string,
  name: string,
  county: string,
  state: StateCode,
  lat: number,
  lon: number,
  workType: WorkType,
  messiness: number,
  sizeTons: number,
  valueUSD: number,
  fit: number,
  status: Status,
  marginPct: number | null,
  deadlineDays?: number,
): Project {
  return { id, name, county, state, lat, lon, workType, messiness, sizeTons, valueUSD, fit, status, marginPct, edge: EDGE[workType], deadlineDays };
}

export const PROJECTS: Project[] = [
  // ── Open pipeline (live opportunities) ──
  mk("p-dunn", "Dunn County · CP-13 Reconstruction", "Dunn", "ND", 47.36, -102.6, "Reconstruct/Rebuild", 8, 10414, 4_820_000, 82, "open", 14.2, 9),
  mk("p-yankton", "Yankton · 4th St Resurface", "Yankton", "SD", 42.87, -97.39, "Mill & Overlay", 3, 3120, 1_240_000, 64, "open", 6.1, 5),
  mk("p-olmsted", "Olmsted County · TH-52 Overlay", "Olmsted", "MN", 44.0, -92.46, "HMA Overlay", 4, 5400, 2_310_000, 41, "open", 8.4, 21),
  mk("p-cass-nd", "Cass County · 32nd Ave Widening", "Cass", "ND", 46.87, -96.79, "Reconstruct/Rebuild", 7, 8800, 3_960_000, 58, "open", 12.0, 12),
  mk("p-stearns", "Stearns County · CSAH-75 Recon", "Stearns", "MN", 45.55, -94.6, "Reconstruct/Rebuild", 9, 12200, 5_640_000, 76, "open", 15.1, 18),
  mk("p-ward", "Ward County · US-83 Grading", "Ward", "ND", 48.23, -101.3, "Grading/Earthwork", 6, 0, 2_870_000, 52, "open", 9.7, 7),
  mk("p-minnehaha", "Minnehaha · I-229 Mill & Fill", "Minnehaha", "SD", 43.55, -96.7, "Mill & Overlay", 4, 6100, 2_540_000, 38, "open", 5.4, 3),
  mk("p-ottertail", "Otter Tail · CSAH-1 Base/Shldr", "Otter Tail", "MN", 46.4, -95.6, "Aggregate/Base", 2, 4200, 980_000, 47, "open", 7.0, 26),

  // ── Historical wins ──
  mk("p-blueearth", "Blue Earth · TH-22 Reconstruct", "Blue Earth", "MN", 44.16, -94.0, "Reconstruct/Rebuild", 8, 9600, 4_450_000, 88, "won", 17.3),
  mk("p-stark", "Stark County · I-94 Recon", "Stark", "ND", 46.88, -102.79, "Reconstruct/Rebuild", 7, 11200, 5_120_000, 84, "won", 16.0),
  mk("p-brookings", "Brookings · Main Ave Rebuild", "Brookings", "SD", 44.31, -96.8, "Reconstruct/Rebuild", 6, 7400, 3_380_000, 79, "won", 14.6),
  mk("p-burleigh", "Burleigh · 43rd Ave Grading", "Burleigh", "ND", 46.8, -100.78, "Grading/Earthwork", 5, 0, 2_120_000, 71, "won", 11.2),
  mk("p-clay", "Clay County · CSAH-11 Overlay", "Clay", "MN", 46.87, -96.78, "HMA Overlay", 3, 5200, 2_010_000, 68, "won", 10.1),
  mk("p-grandforks", "Grand Forks · Gateway Recon", "Grand Forks", "ND", 47.92, -97.03, "Reconstruct/Rebuild", 9, 13400, 6_010_000, 81, "won", 18.4),
  mk("p-polk", "Polk County · US-2 Base", "Polk", "MN", 47.77, -96.6, "Aggregate/Base", 2, 3800, 870_000, 62, "won", 9.0),

  // ── Historical losses (underbid / lost on price) ──
  mk("p-hennepin", "Hennepin · I-394 Mill & Overlay", "Hennepin", "MN", 44.97, -93.27, "Mill & Overlay", 5, 8200, 3_640_000, 44, "lost", 3.1),
  mk("p-pennington", "Pennington · US-16 Overlay", "Pennington", "SD", 44.08, -103.23, "HMA Overlay", 4, 6800, 2_720_000, 49, "lost", 4.4),
  mk("p-williams", "Williams · US-2 Reconstruct", "Williams", "ND", 48.15, -103.6, "Reconstruct/Rebuild", 8, 10100, 4_680_000, 66, "lost", 6.8),
  mk("p-stlouis", "St. Louis · TH-53 Mill & Fill", "St. Louis", "MN", 46.78, -92.1, "Mill & Overlay", 6, 7600, 3_210_000, 40, "lost", 2.2),
  mk("p-brown", "Brown County · US-12 Overlay", "Brown", "SD", 45.46, -98.49, "HMA Overlay", 3, 4900, 1_880_000, 45, "lost", 5.0),

  // ── No-bid (passed) ──
  mk("p-beltrami", "Beltrami · CSAH-7 Mill", "Beltrami", "MN", 47.47, -94.88, "Mill & Overlay", 4, 5600, 2_150_000, 28, "no_bid", null),
  mk("p-cass-mn", "Cass County MN · TH-371 Base", "Cass", "MN", 46.9, -94.3, "Aggregate/Base", 3, 3300, 760_000, 31, "no_bid", null),
];

// ── Pipeline funnel (Stage-1 intake → award) ──
export const FUNNEL = [
  { stage: "Ads scraped", count: 312, note: "DOT lettings + portals, 30d" },
  { stage: "Auto-triaged", count: 168, note: "matched capability profile" },
  { stage: "Plans read", count: 74, note: "extraction complete" },
  { stage: "Go decision", count: 31, note: "fit ≥ 60" },
  { stage: "Bid submitted", count: 22, note: "estimate approved" },
  { stage: "Won", count: 8, note: "lowest responsive" },
];

// ── Headline KPIs ──
export const KPIS = {
  pipelineValueUSD: 31_270_000, // sum of open opportunities (display)
  openOpps: 24,
  winRate: 0.194, // 117/603 — the canonical client figure
  avgMarginPct: 0.121,
  leftOnTableUSD: 22_300_000, // Fall 2025 finding
  bidsThisMonth: 22,
  bidsTrendPct: 0.31, // vs same period prior
  hoursSaved: 1840, // estimator hours reclaimed (cumulative)
};

// ── Unit-price intelligence (the public bid-tab moat) ──
export type PriceItem = {
  code: string;
  item: string;
  unit: string;
  avg: number;
  low: number;
  high: number;
  byState: { state: StateCode; avg: number }[];
  trend: { year: string; price: number }[]; // 4-yr
};

export const PRICE_ITEMS: PriceItem[] = [
  {
    code: "2360.509", item: "HMA Type SP 9.5 Wearing", unit: "ton", avg: 57.4, low: 51, high: 64,
    byState: [{ state: "MN", avg: 59.1 }, { state: "ND", avg: 55.2 }, { state: "SD", avg: 56.8 }],
    trend: [{ year: "2021", price: 48.2 }, { year: "2022", price: 52.6 }, { year: "2023", price: 55.9 }, { year: "2024", price: 57.4 }],
  },
  {
    code: "2211.507", item: "Aggregate Base Class 5", unit: "ton", avg: 13.8, low: 11, high: 16,
    byState: [{ state: "MN", avg: 14.2 }, { state: "ND", avg: 12.9 }, { state: "SD", avg: 14.0 }],
    trend: [{ year: "2021", price: 10.9 }, { year: "2022", price: 12.1 }, { year: "2023", price: 13.2 }, { year: "2024", price: 13.8 }],
  },
  {
    code: "2105.507", item: "Common Excavation", unit: "CY", avg: 9.6, low: 7, high: 13,
    byState: [{ state: "MN", avg: 10.1 }, { state: "ND", avg: 8.7 }, { state: "SD", avg: 9.4 }],
    trend: [{ year: "2021", price: 7.8 }, { year: "2022", price: 8.4 }, { year: "2023", price: 9.1 }, { year: "2024", price: 9.6 }],
  },
  {
    code: "2232.501", item: "Mill Bituminous Surface", unit: "SY", avg: 2.4, low: 1.8, high: 3.4,
    byState: [{ state: "MN", avg: 2.6 }, { state: "ND", avg: 2.1 }, { state: "SD", avg: 2.3 }],
    trend: [{ year: "2021", price: 1.9 }, { year: "2022", price: 2.1 }, { year: "2023", price: 2.3 }, { year: "2024", price: 2.4 }],
  },
  {
    code: "2563.601", item: "Traffic Control (lump)", unit: "LS", avg: 84_000, low: 42_000, high: 160_000,
    byState: [{ state: "MN", avg: 92_000 }, { state: "ND", avg: 78_000 }, { state: "SD", avg: 81_000 }],
    trend: [{ year: "2021", price: 61_000 }, { year: "2022", price: 70_000 }, { year: "2023", price: 79_000 }, { year: "2024", price: 84_000 }],
  },
];

// ── Competitor intelligence (turf + capacity) ──
export type Competitor = {
  name: string;
  turf: StateCode;
  bids: number;
  winRate: number;
  avgProjectUSD: number;
  capacityUsedPct: number; // 0..1; near 1 = "full", low = "hungry"
};

export const COMPETITORS: Competitor[] = [
  { name: "Knife River", turf: "ND", bids: 64, winRate: 0.34, avgProjectUSD: 4_100_000, capacityUsedPct: 0.86 },
  { name: "Mark Sand & Gravel", turf: "MN", bids: 41, winRate: 0.27, avgProjectUSD: 2_700_000, capacityUsedPct: 0.62 },
  { name: "Border States Paving", turf: "ND", bids: 38, winRate: 0.31, avgProjectUSD: 3_500_000, capacityUsedPct: 0.74 },
  { name: "Bituminous Paving", turf: "ND", bids: 29, winRate: 0.22, avgProjectUSD: 2_200_000, capacityUsedPct: 0.48 },
  { name: "Duininck", turf: "MN", bids: 33, winRate: 0.25, avgProjectUSD: 3_000_000, capacityUsedPct: 0.69 },
  { name: "BX Civil & Construction", turf: "SD", bids: 26, winRate: 0.29, avgProjectUSD: 2_600_000, capacityUsedPct: 0.55 },
];

// ── Helpers ──
export const fmtUSD = (n: number) =>
  n >= 1_000_000 ? `$${(n / 1_000_000).toFixed(1)}M` : n >= 1_000 ? `$${(n / 1_000).toFixed(0)}K` : `$${n}`;
export const fmtPct = (n: number) => `${(n * 100).toFixed(n * 100 < 10 ? 1 : 0)}%`;

export const WORK_TYPES: WorkType[] = [
  "Reconstruct/Rebuild", "Grading/Earthwork", "HMA Overlay", "Aggregate/Base", "Mill & Overlay",
];

// Chart color per work-type (matches --chart tokens)
export const WORK_COLOR: Record<WorkType, string> = {
  "Reconstruct/Rebuild": "var(--chart-1)",
  "Grading/Earthwork": "var(--chart-3)",
  "HMA Overlay": "var(--chart-2)",
  "Aggregate/Base": "var(--chart-4)",
  "Mill & Overlay": "var(--chart-5)",
};

export const STATUS_COLOR: Record<Status, string> = {
  won: "var(--positive)",
  lost: "var(--negative)",
  no_bid: "var(--muted-foreground)",
  open: "var(--chart-1)",
};

export const STATE_NAMES: Record<StateCode, string> = { MN: "Minnesota", ND: "North Dakota", SD: "South Dakota" };
