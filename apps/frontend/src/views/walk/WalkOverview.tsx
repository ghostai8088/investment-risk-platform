import type { ReactElement } from "react";
import { Link } from "react-router-dom";

import { DEMO_PORTFOLIO_CODE, WALK_STEPS } from "../../walk/steps";

/**
 * The walk landing (FE-3, OD-FE-3-A). A STATIC overview — it fetches nothing until you enter a
 * step — that frames the product as the governance story: every governed number carries its
 * provenance, validation, and disclosed limitations, walked end to end on one book.
 */
export function WalkOverview(): ReactElement {
  return (
    <section className="walk-overview">
      <h2>How you can trust a governed number</h2>
      <p className="lede">
        This walk follows one book — <strong>{DEMO_PORTFOLIO_CODE}</strong> — from its raw inputs to
        its risk numbers, the evidence they held up, the independent review that signed them off,
        and the limitations each model discloses. Every number traces to its inputs and reproduces
        on demand; nothing is asserted without its provenance.
      </p>
      <ol className="walk-cards">
        {WALK_STEPS.map((step) => (
          <li key={step.slug} className="walk-card">
            <Link to={`/walk/${step.slug}`}>
              <span className="walk-card-label">{step.label}</span>
              <span className="walk-card-blurb">{step.blurb}</span>
            </Link>
          </li>
        ))}
      </ol>
    </section>
  );
}
