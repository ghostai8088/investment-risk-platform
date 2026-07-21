/**
 * The FE-3 governance-narrative walk (OD-FE-3-A). The demo tenant's own lifecycle — capture →
 * exposures → governed numbers → backtest evidence → validation status → disclosed limitations —
 * is the product's spine, scoped to the single richest book (DEMO-GLOBAL). Each step is a route.
 */

export interface WalkStep {
  /** URL slug (`/walk/:slug`) and stable key. */
  slug: string;
  /** Short nav label (ordinal + name). */
  label: string;
  /** One-line description of what the step shows. */
  blurb: string;
}

export const WALK_STEPS: readonly WalkStep[] = [
  { slug: "capture", label: "1 · Capture", blurb: "The raw inputs: positions and marks." },
  { slug: "exposures", label: "2 · Exposures", blurb: "What the book is exposed to." },
  {
    slug: "numbers",
    label: "3 · Governed numbers",
    blurb: "Portfolio return, covariance, VaR — each traceable to its inputs.",
  },
  {
    slug: "backtest",
    label: "4 · Backtest evidence",
    blurb: "Did the risk numbers hold up against outcomes?",
  },
  {
    slug: "validation",
    label: "5 · Validation status",
    blurb: "Independent review: findings and evidence.",
  },
  {
    slug: "limitations",
    label: "6 · Disclosed limitations",
    blurb: "What each model deliberately cannot see.",
  },
];

/** The book the walk is scoped to (OD-FE-3-C, the focused vertical). */
export const DEMO_PORTFOLIO_CODE = "DEMO-GLOBAL";

/** Look up a step by slug (nav highlighting, route validation). */
export function walkStep(slug: string | undefined): WalkStep | undefined {
  return WALK_STEPS.find((s) => s.slug === slug);
}
