import type { ReactElement } from "react";
import { Link, Navigate, useParams } from "react-router-dom";

import { Pane } from "../../components/Pane";
import type { DevSession } from "../../session";
import { WALK_STEPS, walkStep } from "../../walk/steps";
import { useDemoPortfolio } from "../../walk/useDemoPortfolio";
import type { DemoPortfolio } from "../../walk/useDemoPortfolio";
import { CaptureStep } from "./CaptureStep";
import { ExposuresStep } from "./ExposuresStep";

/**
 * A single walk step (FE-3, OD-FE-3-A). Renders the step chrome — a progress stepper and prev/next
 * navigation — around the step body, resolving the demo book once for the data steps. Capture and
 * Exposures are live; numbers / backtest / validation / limitations are placeholders until FE-3
 * steps 4–5.
 */
export function WalkStep({ session }: { session: DevSession }): ReactElement {
  const { step: slug } = useParams();
  const demo = useDemoPortfolio(session);
  const step = walkStep(slug);
  if (!step) return <Navigate to="/walk" replace />;

  const index = WALK_STEPS.findIndex((s) => s.slug === step.slug);
  const prev = index > 0 ? WALK_STEPS[index - 1] : undefined;
  const next = index < WALK_STEPS.length - 1 ? WALK_STEPS[index + 1] : undefined;

  return (
    <section className="walk-step" aria-labelledby="walk-step-heading">
      <ol className="stepper" aria-label={`Step ${String(index + 1)} of ${String(WALK_STEPS.length)}`}>
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

      <StepBody slug={step.slug} session={session} demo={demo} />

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

/** Dispatch to the live step or a placeholder. The book-scoped steps render inside a Pane over the
 * portfolio resolution so a missing `portfolio.view` grant degrades gracefully (OD-E). */
function StepBody({
  slug,
  session,
  demo,
}: {
  slug: string;
  session: DevSession;
  demo: DemoPortfolio;
}): ReactElement {
  if (slug === "capture" || slug === "exposures") {
    return (
      <Pane state={demo.state} requires="portfolio.view">
        {() =>
          demo.portfolio ? (
            slug === "capture" ? (
              <CaptureStep session={session} portfolioId={demo.portfolio.id} />
            ) : (
              <ExposuresStep session={session} portfolioId={demo.portfolio.id} />
            )
          ) : (
            <p className="state">The demo book “DEMO-GLOBAL” was not found for this tenant.</p>
          )
        }
      </Pane>
    );
  }
  return (
    <p className="placeholder" data-step={slug}>
      This step is being built. It will read {slug} for the demo book directly from the governed
      API, with each governed number carrying its provenance, validation status, and disclosed
      limitations.
    </p>
  );
}
