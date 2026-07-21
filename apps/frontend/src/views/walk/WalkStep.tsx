import type { ReactElement } from "react";
import { Link, Navigate, useParams } from "react-router-dom";

import { WALK_STEPS, walkStep } from "../../walk/steps";

/**
 * A single walk step (FE-3, OD-FE-3-A). Renders the step chrome — a progress stepper and
 * prev/next navigation — around the step body. The bodies (capture / exposures / numbers /
 * backtest / validation / limitations) are filled in by later FE-3 steps; here they are
 * placeholders so the shell and routing are testable first (the session prop arrives with the
 * data steps).
 */
export function WalkStep(): ReactElement {
  const { step: slug } = useParams();
  const step = walkStep(slug);
  if (!step) return <Navigate to="/walk" replace />;

  const index = WALK_STEPS.findIndex((s) => s.slug === step.slug);
  const prev = index > 0 ? WALK_STEPS[index - 1] : undefined;
  const next = index < WALK_STEPS.length - 1 ? WALK_STEPS[index + 1] : undefined;

  return (
    <section className="walk-step" aria-labelledby="walk-step-heading">
      <ol className="stepper" aria-label={`Step ${index + 1} of ${WALK_STEPS.length}`}>
        {WALK_STEPS.map((s, i) => (
          <li
            key={s.slug}
            className={s.slug === step.slug ? "stepper-dot current" : "stepper-dot"}
            aria-current={s.slug === step.slug ? "step" : undefined}
          >
            <Link to={`/walk/${s.slug}`}>
              <span className="stepper-num">{i + 1}</span>
              <span className="stepper-name">{s.label.replace(/^\d+ · /, "")}</span>
            </Link>
          </li>
        ))}
      </ol>

      <h2 id="walk-step-heading">{step.label}</h2>
      <p className="lede">{step.blurb}</p>

      <StepBody slug={step.slug} />

      <nav className="step-nav" aria-label="Walk navigation">
        {prev ? (
          <Link to={`/walk/${prev.slug}`} className="step-prev">
            ← {prev.label}
          </Link>
        ) : (
          <span />
        )}
        {next ? (
          <Link to={`/walk/${next.slug}`} className="step-next">
            {next.label} →
          </Link>
        ) : (
          <Link to="/walk" className="step-next">
            Back to overview
          </Link>
        )}
      </nav>
    </section>
  );
}

/** The per-step content. Placeholders until FE-3 steps 3–5 fill each in. */
function StepBody({ slug }: { slug: string }): ReactElement {
  return (
    <p className="placeholder" data-step={slug}>
      This step is being built. It will read {slug} for the demo book directly from the governed
      API, with each governed number carrying its provenance, validation status, and disclosed
      limitations.
    </p>
  );
}
