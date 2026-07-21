import { useState } from "react";
import type { ReactElement } from "react";
import { Navigate, Route, Routes } from "react-router-dom";

import { AppShell } from "./components/AppShell";
import { DevBanner } from "./components/DevBanner";
import { SessionForm } from "./components/SessionForm";
import { clearSession, loadSession, saveSession } from "./session";
import type { DevSession } from "./session";
import { RunDetail } from "./views/RunDetail";
import { RunsList } from "./views/RunsList";
import { WalkOverview } from "./views/walk/WalkOverview";
import { WalkStep } from "./views/walk/WalkStep";

export function App(): ReactElement {
  const [session, setSession] = useState<DevSession | null>(() => loadSession());

  if (!session) {
    return (
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

  return (
    <>
      <DevBanner />
      <Routes>
        <Route
          element={
            <AppShell
              session={session}
              onEndSession={() => {
                clearSession();
                setSession(null);
              }}
            />
          }
        >
          {/* The governance walk is the front door; the run browser stays reachable at /runs. */}
          <Route index element={<WalkOverview />} />
          <Route path="walk" element={<WalkOverview />} />
          <Route path="walk/:step" element={<WalkStep />} />
          <Route path="runs" element={<RunsList session={session} />} />
          <Route path="runs/:family/:runId" element={<RunDetail session={session} />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </>
  );
}
