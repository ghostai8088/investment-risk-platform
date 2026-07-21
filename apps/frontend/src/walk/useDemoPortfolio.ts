import type { AsyncState } from "../api/useApiGet";
import { useApiGet } from "../api/useApiGet";
import type { PortfolioSummary } from "../api/types";
import type { DevSession } from "../session";
import { DEMO_PORTFOLIO_CODE } from "./steps";

export interface DemoPortfolio {
  /** The resolved portfolio, or null while loading / on error / if the code is absent. */
  portfolio: PortfolioSummary | null;
  /** The underlying /portfolios read state (drives the loading / 403 / error Pane). */
  state: AsyncState<PortfolioSummary[]>;
}

/**
 * Resolve the demo book (DEMO-GLOBAL) the walk is scoped to. The `/portfolios` list is tenant-RLS
 * scoped and gated `portfolio.view`; the walk finds the fixed code by value (ids are per-seed, not
 * stable). Steps chain their data reads on `portfolio?.id` (passing `null` to `useApiGet` until it
 * resolves).
 */
export function useDemoPortfolio(session: DevSession): DemoPortfolio {
  const state = useApiGet<PortfolioSummary[]>("/portfolios", session);
  const portfolio = state.data?.find((p) => p.code === DEMO_PORTFOLIO_CODE) ?? null;
  return { portfolio, state };
}
