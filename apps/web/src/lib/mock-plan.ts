// Mock data shaped to the real Plan Reader schema: every field/gotcha carries a
// verbatim quote snapped to a source page + a confidence. This is the provenance
// contract that makes the UI trustworthy — "here's the gotcha, here's the proof."

export type Family = "go_no_go" | "pricing";

export type Gotcha = {
  id: string;
  flag_type: string; // taxonomy code
  family: Family;
  title: string; // plain-language label
  explanation: string; // separate plain-language gloss
  evidence: string; // VERBATIM quote from the plan
  section: string;
  page: number;
  confidence: number; // 0..1
};

export type Field = {
  key: string;
  label: string;
  value: string;
  unit?: string;
  confidence: number;
  page: number;
  benchmark?: string; // bid-tab comparable
};

export type Plan = {
  id: string;
  title: string;
  state: "MN" | "ND" | "SD";
  county: string;
  outcome: "WON" | "LOST" | "NO_BID";
  pages: number;
  fit: number; // 0..100
  recommendation: "BID" | "NO_BID" | "REVIEW";
  confidence: number;
  rationale: string[];
  risks: string[];
  fields: Field[];
  gotchas: Gotcha[];
  // ── readable-title + structured output blocks (backlog #1, #5) ──
  year: string;
  archetype: string;
  identity: { label: string; value: string }[];
  contractTimes: { label: string; date: string; note?: string }[];
};

// A handful of "PDF pages" rendered as plan-like prose so the viewer has something
// to highlight. The evidence strings below appear verbatim inside these pages.
export const PAGE_TEXT: Record<number, string> = {
  12: `BID SCHEDULE — DIVISION 2310 PLANT MIXED ASPHALT\n\nItem 2360.509  Type SP 9.5 Wearing Course Mixture (3,B)\nQuantity: 6,296 TON   Unit: TON\n\nItem 2360.509  Type SP 12.5 Non Wearing Course Mixture (3,B)\nQuantity: 4,118 TON   Unit: TON\n\nAll bituminous quantities are final-pay based on the bid schedule\nand shall govern over any quantity referenced elsewhere in the plan.`,
  31: `SECTION 1804 — PROGRESS AND COMPLETION\n\nThe Contractor shall complete Stage 1 paving operations prior to\nopening any portion of the roadway to unrestricted public traffic.\nStaging shall be conducted in three sequential phases as shown on\nthe traffic control plans, sheets 44 through 51.`,
  47: `SECTION 2105 — TRAFFIC CONTROL & SEASONAL LIMITATIONS\n\nNo bituminous wearing course shall be placed after October 1 of the\ncalendar year. Liquidated damages in the amount of $1,200 per\ncalendar day shall be assessed for each day the work remains\nincomplete beyond the contract completion date.`,
  53: `SECTION 1717 — FEDERAL LABOR PROVISIONS\n\nThis project is subject to the prevailing wage determination issued\nby the U.S. Department of Labor. A Disadvantaged Business Enterprise\n(DBE) goal of 6.0% has been established for this contract.`,
  68: `SECTION 2573 — STORM WATER MANAGEMENT\n\nThe Contractor shall obtain coverage under the NPDES/SDS\nConstruction Storm Water General Permit. A SWPPP exceeding the\nstandard Special Provisions is required due to proximity to the\nMissouri River drainage; impaired-water buffer requirements apply.`,
};

export const PLAN: Plan = {
  id: "2023_DUNN-CO-ND_CP-13",
  title: "Dunn County ND · CP-13 Reconstruction",
  state: "ND",
  county: "Dunn",
  outcome: "WON",
  pages: 214,
  fit: 82,
  recommendation: "BID",
  confidence: 0.82,
  year: "2023",
  archetype: "Reconstruct/Rebuild",
  identity: [
    { label: "Owner", value: "Dunn County Highway Dept, ND" },
    { label: "Engineer", value: "KLJ Engineering" },
    { label: "Project", value: "CP-13 — TH-22 Reconstruction & Overlay" },
    { label: "Project no.", value: "SP 045-613-008 / eBidDoc 8451120" },
    { label: "Bid platform", value: "Bid Express — electronic only" },
    { label: "Bid deadline", value: "March 14, 2023, 11:00 a.m. local" },
    { label: "Bid security", value: "5% of bidder's maximum price" },
    { label: "Bid acceptance period", value: "60 days after opening" },
    { label: "Contract form", value: "NDDOT Std. Specifications 2020" },
  ],
  contractTimes: [
    { label: "Milestone 1", date: "Jun 30, 2023", note: "grading & aggregate base complete" },
    { label: "Substantial completion", date: "Sep 29, 2023", note: "paving incl. wearing course" },
    { label: "Final payment ready", date: "Oct 31, 2023" },
  ],
  rationale: [
    "You've won 7 of 9 earthwork-heavy projects in the ND turf over 3 years.",
    "Reconstruct/Rebuild archetype — your highest-margin work type.",
    "Current backlog suggests open capacity in Q4.",
  ],
  risks: [
    "SWPPP requirements here exceed your typical scope (Missouri River buffer).",
    "Seasonal paving cutoff (Oct 1) compresses the schedule.",
  ],
  fields: [
    { key: "mix_tn", label: "Hot Mix Asphalt", value: "6,296", unit: "TON", confidence: 0.98, page: 12, benchmark: "bid-tab avg $54–61/ton" },
    { key: "base_tn", label: "Base Aggregate", value: "9,840", unit: "TON", confidence: 0.94, page: 12, benchmark: "bid-tab avg $11–16/ton" },
    { key: "traffic_level", label: "Traffic Level", value: "SP 9.5 (3,B)", confidence: 0.71, page: 47 },
    { key: "prevailing_wage", label: "Prevailing Wage", value: "Yes (federal)", confidence: 0.96, page: 53 },
  ],
  gotchas: [
    {
      id: "g1",
      flag_type: "PHASING_SEQUENCED",
      family: "go_no_go",
      title: "Three-stage sequenced phasing",
      explanation: "Roadway must be staged in 3 phases; Stage 1 paving must finish before opening to traffic. Drives crew scheduling and mobilization cost.",
      evidence: "The Contractor shall complete Stage 1 paving operations prior to opening any portion of the roadway to unrestricted public traffic.",
      section: "1804 — Progress and Completion",
      page: 31,
      confidence: 0.94,
    },
    {
      id: "g2",
      flag_type: "SEASONAL_WINDOW",
      family: "go_no_go",
      title: "Seasonal paving cutoff — Oct 1",
      explanation: "No wearing course after October 1. Compresses the schedule and raises the risk of liquidated damages if work slips.",
      evidence: "No bituminous wearing course shall be placed after October 1 of the calendar year.",
      section: "2105 — Traffic Control",
      page: 47,
      confidence: 0.91,
    },
    {
      id: "g3",
      flag_type: "LIQUIDATED_DAMAGES",
      family: "pricing",
      title: "Liquidated damages $1,200/day",
      explanation: "Per-day penalty for late completion. Feeds the risk premium in the bid margin.",
      evidence: "Liquidated damages in the amount of $1,200 per calendar day shall be assessed for each day the work remains incomplete beyond the contract completion date.",
      section: "2105 — Traffic Control",
      page: 47,
      confidence: 0.97,
    },
    {
      id: "g4",
      flag_type: "PREVAILING_WAGE",
      family: "pricing",
      title: "Federal prevailing wage",
      explanation: "Davis-Bacon wage determination applies — raises labor cost vs. private work.",
      evidence: "This project is subject to the prevailing wage determination issued by the U.S. Department of Labor.",
      section: "1717 — Federal Labor",
      page: 53,
      confidence: 0.96,
    },
    {
      id: "g5",
      flag_type: "DBE_GOAL",
      family: "go_no_go",
      title: "DBE goal 6.0%",
      explanation: "Disadvantaged Business Enterprise participation target — requires sub sourcing and documentation.",
      evidence: "A Disadvantaged Business Enterprise (DBE) goal of 6.0% has been established for this contract.",
      section: "1717 — Federal Labor",
      page: 53,
      confidence: 0.9,
    },
    {
      id: "g6",
      flag_type: "SWPPP_ENHANCED",
      family: "go_no_go",
      title: "Enhanced SWPPP — impaired water",
      explanation: "Storm-water plan exceeds standard scope due to Missouri River proximity. Extra scope your estimate must absorb.",
      evidence: "A SWPPP exceeding the standard Special Provisions is required due to proximity to the Missouri River drainage; impaired-water buffer requirements apply.",
      section: "2573 — Storm Water",
      page: 68,
      confidence: 0.88,
    },
  ],
};

export const QUEUE = [
  { id: "2023_DUNN-CO-ND_CP-13", name: "Dunn County ND · CP-13", state: "ND", fit: 82, trend: "up", active: true },
  { id: "2023_YANKTON-SD", name: "Yankton SD · Resurface", state: "SD", fit: 64, trend: "flat", active: false },
  { id: "2024_OLMSTED-MN", name: "Olmsted County MN · Overlay", state: "MN", fit: 41, trend: "down", active: false },
  { id: "2024_CASS-ND", name: "Cass County ND · Widening", state: "ND", fit: 58, trend: "up", active: false },
];
