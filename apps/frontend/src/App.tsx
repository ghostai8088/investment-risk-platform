import type { ReactElement } from "react";

import { appInfo } from "./appInfo";

export function App(): ReactElement {
  const info = appInfo();
  return (
    <main>
      <h1>{info.name}</h1>
      <p>Scaffold shell — version {info.version}. No domain functionality yet.</p>
    </main>
  );
}
