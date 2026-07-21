import { useEffect, useRef, useState } from "react";
import type { ReactElement } from "react";
import { Navigate, Route, Routes, useLocation, useNavigate } from "react-router-dom";

import { authMode } from "./api/authConfig";
import { AppShell } from "./components/AppShell";
import { DevBanner } from "./components/DevBanner";
import { SessionForm } from "./components/SessionForm";
import { beginLogin, completeLogin, logout } from "./auth/oidc";
import { clearSession, loadSession, saveSession } from "./session";
import type { Session } from "./session";
import { RunDetail } from "./views/RunDetail";
import { RunsList } from "./views/RunsList";
import { WalkOverview } from "./views/walk/WalkOverview";
import { WalkStep } from "./views/walk/WalkStep";

/** The OIDC redirect lands here pre-auth (above the session gate). Runs the code exchange ONCE
 * (StrictMode-safe via the ref) and, on success, sets the session + navigates into the app. */
function OidcCallback({ onSession }: { onSession: (s: Session) => void }): ReactElement {
  const navigate = useNavigate();
  const ran = useRef(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (ran.current) return; // StrictMode double-invoke / re-render guard: exchange the code once
    ran.current = true;
    const search = new URLSearchParams(window.location.search); // captured before completeLogin strips it
    void completeLogin(search)
      .then((s) => {
        onSession(s);
        navigate("/", { replace: true });
      })
      .catch((e: unknown) => {
        setError(e instanceof Error ? e.message : "sign-in failed");
      });
  }, [navigate, onSession]);

  return (
    <main className="session-gate">
      <h1>Investment Risk Platform</h1>
      {error ? (
        <>
          <p className="state error" role="alert">
            Sign-in did not complete: {error}
          </p>
          <button type="button" onClick={() => void beginLogin()}>
            Try signing in again
          </button>
        </>
      ) : (
        <p className="state">Completing sign-in…</p>
      )}
    </main>
  );
}

/** The logged-out sign-in screen for oidc mode (no DevBanner — a verified session is a real
 * security boundary, so nothing here may claim "unverified"). */
function SignIn(): ReactElement {
  return (
    <main className="session-gate">
      <h1>Investment Risk Platform</h1>
      <p>Sign in with your organization account to continue.</p>
      <button type="button" onClick={() => void beginLogin()}>
        Sign in
      </button>
    </main>
  );
}

export function App(): ReactElement {
  const [session, setSession] = useState<Session | null>(() => loadSession());
  const location = useLocation();

  // The /callback route must be reachable WITHOUT a session (it lands pre-auth) — handle it above
  // the session gate. Only meaningful in oidc mode.
  if (authMode === "oidc" && location.pathname === "/callback") {
    return <OidcCallback onSession={setSession} />;
  }

  if (!session) {
    // dev_header: the DevBanner + the unverified header form. oidc: the Sign-in button, NO banner.
    return authMode === "oidc" ? (
      <SignIn />
    ) : (
      <>
        <DevBanner />
        <main className="session-gate">
          <h1>Investment Risk Platform</h1>
          <SessionForm
            onStart={(s) => {
              saveSession(s);
              setSession(s);
            }}
          />
        </main>
      </>
    );
  }

  const endSession = () => {
    if (session.kind === "oidc") {
      logout(); // a real OIDC logout (redirects to the IdP end-session endpoint)
    } else {
      clearSession();
      setSession(null);
    }
  };

  return (
    <>
      {/* The DevBanner renders ONLY over an unverified dev session — never over a verified OIDC one. */}
      {session.kind === "dev" ? <DevBanner /> : null}
      <Routes>
        <Route element={<AppShell session={session} onEndSession={endSession} />}>
          {/* The governance walk is the front door; the run browser stays reachable at /runs. */}
          <Route index element={<WalkOverview />} />
          <Route path="walk" element={<WalkOverview />} />
          <Route path="walk/:step" element={<WalkStep session={session} />} />
          <Route path="runs" element={<RunsList session={session} />} />
          <Route path="runs/:family/:runId" element={<RunDetail session={session} />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </>
  );
}
