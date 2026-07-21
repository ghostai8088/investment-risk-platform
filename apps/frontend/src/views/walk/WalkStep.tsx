import type { ReactElement } from "react";
import { Link, Navigate, useParams } from "react-router-dom";

import { Pane } from "../../components/Pane";
import type { DevSession } from "../../session";
import { WALK_STEPS, walkStep } from "../../walk/steps";
import { useDemoPortfolio } from "../../walk/useDemoPortfolio";
import type { DemoPortfolio } from "../../walk/useDemoPortfolio";
import { BacktestStep } from "./BacktestStep";
import { CaptureStep } from "./CaptureStep";
import { ExposuresStep } from "./ExposuresStep";
import { LimitationsStep } from "./LimitationsStep";
import { NumbersStep } from "./NumbersStep";
import { ValidationStep } from "./ValidationStep";

/**
 * A single walk step (FE-3, OD-FE-3-A). Renders the step chrome — a progress stepper and prev/next
 * navigation — around the step body, resolving the demo book once for the book-scoped steps. All
 * six step bodies (capture / exposures / numbers / backtest / validation / limitations) are live.
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
  // Book-scoped steps read by portfolio_id, so they resolve the demo book first.
  if (slug === "capture" || slug === "exposures" || slug === "numbers" || slug === "backtest") {
    return (
      <Pane state={demo.state} requires="portfolio.view">
        {() => {
          if (!demo.portfolio) {
            return <p className="state">The demo book “DEMO-GLOBAL” was not found for this tenant.</p>;
          }
          const pid = demo.portfolio.id;
          if (slug === "capture") return <CaptureStep session={session} portfolioId={pid} />;
          if (slug === "exposures") return <ExposuresStep session={session} portfolioId={pid} />;
          if (slug === "numbers") return <NumbersStep session={session} portfolioId={pid} />;
          return <BacktestStep session={session} portfolioId={pid} />;
        }}
      </Pane>
    );
  }
  // Model-scoped steps (no portfolio needed).
  if (slug === "validation") return <ValidationStep session={session} />;
  return <LimitationsStep session={session} />;
}
