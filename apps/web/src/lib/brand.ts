// CSI Bid Assistant — single-tenant, chatbot-only MVP for Central Specialties Inc.
// This is NOT the multi-tenant platform (that's Plumb). It's CSI's internal copilot:
// ask about plans, gotchas, quantities, bid history, competitors — cited to the source.
export const BRAND = {
  name: "CSI Bidding Intelligence",
  short: "CSI",
  tagline: "Ask the plans.",
  mark: "◆",
  company: "Central Specialties Inc.",
  blurb: "Your estimating copilot — reads the plan set, flags the gotchas, cites every figure.",
  // The signed-in estimator (single-tenant MVP → hardcoded for now; driven by login later).
  user: { name: "Adam", initial: "A" },
};
