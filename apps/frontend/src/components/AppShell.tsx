import type { ReactElement } from "react";
import { NavLink, Outlet, useLocation } from "react-router";

import type { Session } from "../session";
import { DEMO_PORTFOLIO_CODE, WALK_STEPS } from "../walk/steps";

/** The identity label in the header chrome: the dev shim shows `userId @ tenantId`; a verified
 * OIDC session shows the decoded `sub` (never the raw token). */
function sessionLabel(session: Session): string {
  return session.kind === "oidc" ? session.subject : `${session.userId} @ ${session.tenantId}`;
}

/**
 * The application shell (FE-3, OD-FE-3-B; IA re-ordered at OPS-1, OQ-6=A).
 *
 * A header + a left nav, with the routed content in the outlet. **Operations is the first group.**
 * FE-3 made the governance walk the front door because there was nothing operational to do yet —
 * the platform could explain itself but not be worked. With a live breach queue and an approval
 * queue, the daily user is an operator and the walk becomes the explainer, so it moves below.
 */
export function AppShell({
  session,
  onEndSession,
}: {
  session: Session;
  onEndSession: () => void;
}): ReactElement {
  // The book chip describes the WALK's scope only. The operations surfaces are tenant-wide across
  // every portfolio, so showing a single book alongside them would be a false claim about what is
  // on screen (OPS-1 verifier fold).
  const { pathname } = useLocation();
  const showBookChip = pathname === "/" || pathname.startsWith("/walk");

  return (
    <div className="shell">
      <a className="skip-link" href="#walk-main">
        Skip to main content
      </a>
      <header className="app-header">
        <div className="app-title">
          <h1>Investment Risk Platform</h1>
          {showBookChip ? (
            <span className="book-chip" title="The walk is scoped to this book">
              {DEMO_PORTFOLIO_CODE}
            </span>
          ) : null}
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
        <nav className="walk-nav" aria-label="Main">
          {/* OQ-6=A: operations first — the daily surface outranks the explainer. */}
          <p className="nav-heading">Operations</p>
          <NavLink
            to="/ops/breaches"
            className={({ isActive }) => (isActive ? "nav-link active" : "nav-link")}
          >
            Breach queue
          </NavLink>
          <NavLink
            to="/ops/limits"
            className={({ isActive }) => (isActive ? "nav-link active" : "nav-link")}
          >
            Limits &amp; approvals
          </NavLink>
          {/* RPT-2: governed reports, regenerated (and re-proven) on every read. */}
          <NavLink
            to="/ops/reports"
            className={({ isActive }) => (isActive ? "nav-link active" : "nav-link")}
          >
            Reports
          </NavLink>

          {/* ALERT-1: is the reproduction alarm channel actually working? */}
          <NavLink
            to="/ops/alerting"
            className={({ isActive }) => (isActive ? "nav-link active" : "nav-link")}
          >
            Alerting
          </NavLink>

          {/* REPRO-2: is the nightly reproduction check running, and what did it find? */}
          <NavLink
            to="/ops/reproduction"
            className={({ isActive }) => (isActive ? "nav-link active" : "nav-link")}
          >
            Reproduction
          </NavLink>

          {/* ONBOARD-1b: tenant self-administration. The link is shown to everyone — the FE holds
              no permission knowledge, and a non-admin opening it sees the server's own refusal in
              plain language (the OPS-1 convention). */}
          <p className="nav-heading">Administration</p>
          <NavLink
            to="/admin/users"
            className={({ isActive }) => (isActive ? "nav-link active" : "nav-link")}
          >
            Users &amp; roles
          </NavLink>

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
