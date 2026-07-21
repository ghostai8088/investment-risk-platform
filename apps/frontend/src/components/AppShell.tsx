import type { ReactElement } from "react";
import { NavLink, Outlet } from "react-router-dom";

import type { Session } from "../session";
import { DEMO_PORTFOLIO_CODE, WALK_STEPS } from "../walk/steps";

/** The identity label in the header chrome: the dev shim shows `userId @ tenantId`; a verified
 * OIDC session shows the decoded `sub` (never the raw token). */
function sessionLabel(session: Session): string {
  return session.kind === "oidc" ? session.subject : `${session.userId} @ ${session.tenantId}`;
}

/**
 * The application shell (FE-3, OD-FE-3-B): a header + a left nav listing the six-step governance
 * walk and the (kept) run browser, with the routed content in the outlet. The walk is the front
 * door; the run browser stays reachable but secondary.
 */
export function AppShell({
  session,
  onEndSession,
}: {
  session: Session;
  onEndSession: () => void;
}): ReactElement {
  return (
    <div className="shell">
      <a className="skip-link" href="#walk-main">
        Skip to main content
      </a>
      <header className="app-header">
        <div className="app-title">
          <h1>Investment Risk Platform</h1>
          <span className="book-chip" title="The walk is scoped to this book">
            {DEMO_PORTFOLIO_CODE}
          </span>
        </div>
        <div className="session-info">
          <span className="mono" aria-label="active session">
            {sessionLabel(session)}
          </span>
          <button type="button" onClick={onEndSession}>
            {session.kind === "oidc" ? "Sign out" : "End session"}
          </button>
        </div>
      </header>

      <div className="shell-body">
        <nav className="walk-nav" aria-label="Governance walk">
          <p className="nav-heading">The walk</p>
          <ol className="nav-steps">
            {WALK_STEPS.map((step) => (
              <li key={step.slug}>
                <NavLink
                  to={`/walk/${step.slug}`}
                  className={({ isActive }) => (isActive ? "nav-link active" : "nav-link")}
                >
                  {step.label}
                </NavLink>
              </li>
            ))}
          </ol>
          <p className="nav-heading">Browse</p>
          <NavLink
            to="/runs"
            className={({ isActive }) => (isActive ? "nav-link active" : "nav-link")}
          >
            Runs (all calculations)
          </NavLink>
        </nav>

        <main id="walk-main" className="shell-content" tabIndex={-1}>
          <Outlet />
        </main>
      </div>
    </div>
  );
}
