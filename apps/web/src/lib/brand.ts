// Construction Bidding Assistant — single-tenant, chatbot-only MVP for a highway construction contractor.
// This is NOT the multi-tenant platform (that's Plumb). It's the client's internal copilot:
// ask about plans, gotchas, quantities, bid history, competitors — cited to the source.
export const BRAND = {
  name: "Construction Bidding Assistant",
  short: "Bidding Assistant",
  tagline: "Ask the plans.",
  mark: "◆",
  company: "a highway construction contractor",
  blurb: "Your estimating copilot — reads the plan set, flags the gotchas, cites every figure.",
  // The signed-in estimator (single-tenant MVP → hardcoded for now; driven by login later).
  user: { name: "Adam", initial: "A" },
};
