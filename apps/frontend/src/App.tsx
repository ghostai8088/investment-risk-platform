import { useState } from "react";
import type { ReactElement } from "react";
import { Navigate, Route, Routes } from "react-router-dom";

import { DevBanner } from "./components/DevBanner";
import { SessionForm } from "./components/SessionForm";
import { clearSession, loadSession, saveSession } from "./session";
import type { DevSession } from "./session";
import { RunDetail } from "./views/RunDetail";
import { RunsList } from "./views/RunsList";

export function App(): ReactElement {
  const [session, setSession] = useState<DevSession | null>(() => loadSession());

  return (
    <>
      <DevBanner />
      <main>
        <header className="app-header">
          <h1>Investment Risk Platform — risk runs (read-only)</h1>
          {session ? (
            <div className="session-info">
              <span className="mono">
                {session.userId} @ {session.tenantId}
              </span>
              <button
                onClick={() => {
                  clearSession();
                  setSession(null);
                }}
              >
                End session
              </button>
            </div>
          ) : null}
        </header>

        {session ? (
          <Routes>
            <Route path="/" element={<RunsList session={session} />} />
            <Route path="/runs/:family/:runId" element={<RunDetail session={session} />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        ) : (
          <SessionForm
            onStart={(s) => {
              saveSession(s);
              setSession(s);
            }}
          />
        )}
      </main>
    </>
  );
}
