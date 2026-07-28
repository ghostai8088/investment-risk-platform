/**
 * FE-M1 (OQ-FE-M1-4=D), fence 1 of 3 — `react-router-dom` cannot come back.
 *
 * react-router v8 REMOVED the `react-router-dom` re-export package; every symbol this app uses now
 * resolves at the root `react-router` entry. The reintroduction risk is not theoretical — it is
 * what the tooling actively recommends: `npm audit` on the pre-migration tree reported
 * `fixAvailable: { name: "react-router-dom", version: "7.11.0", isSemVerMajor: true }`, i.e. the
 * exact downgrade OPS-1's OQ-1=C was RATIFIED FOR AND THEN REFUTED IN BUILD, because 7.11.x
 * re-exposes six advisories including a High DoS and two reachable open-redirects.
 *
 * So the migration's most likely failure mode is not a bug — it is a well-meaning contributor
 * running `npm audit fix`. This test proves the lint fence actually fires, in both directions, and
 * it covers the specific hole the FE-M1 verifier pass found (V-3): the write fence's `writes.ts`
 * exemption used to switch the WHOLE `no-restricted-imports` rule off, which would have handed that
 * one file a free pass on this ban too.
 */
// @vitest-environment node

import { ESLint } from "eslint";
import { existsSync } from "node:fs";
import { dirname, join } from "node:path";
import { describe, expect, it } from "vitest";

/** Walk up from the working directory to the package dir holding the flat config (same pattern as
 * write-fence.test.ts — `import.meta.url` is an http:// URL under vitest, not a file one). */
function packageDir(): string {
  let dir = process.cwd();
  for (;;) {
    if (existsSync(join(dir, "eslint.config.js"))) return dir;
    const parent = dirname(dir);
    if (parent === dir) throw new Error("eslint.config.js not found walking up from cwd");
    dir = parent;
  }
}

const eslint = new ESLint({ cwd: packageDir() });

async function fenceMessages(code: string, filePath: string) {
  const [result] = await eslint.lintText(code, { filePath });
  return result.messages.filter((m) => m.ruleId === "no-restricted-imports");
}

/** Files at every depth, plus the two that sit OUTSIDE `src/` — the fence's file glob was widened
 * from `src/**` to `**\/*` at FE-M1 precisely so a root-level module could not route around it. */
const BANNED_SITES: Array<[label: string, file: string]> = [
  ["a src-root module", "src/probe.tsx"],
  ["a nested view", "src/views/ops/probe.tsx"],
  ["a deeply nested view", "src/views/a/b/c/probe.tsx"],
  ["the app entrypoint", "src/main.tsx"],
  ["a repo-root guard test", "probe.test.ts"],
  // V-3: the write-fence exemption must NOT extend to this ban.
  ["the write module itself (the V-3 hole)", "src/api/writes.ts"],
];

describe("the router fence: react-router-dom is unimportable anywhere", () => {
  it.each(BANNED_SITES)("blocks a react-router-dom import from %s", async (_label, file) => {
    const hits = await fenceMessages(
      `import { Link } from "react-router-dom";\nexport { Link };`,
      file,
    );
    expect(hits.length).toBeGreaterThan(0);
    expect(hits[0].message).toContain("react-router");
  });

  it("blocks it in a .jsx file — the EXTENSION axis of the fence-hole class", async () => {
    // FE-M1 review fold. Both fences were scoped to `.ts`/`.tsx`; a probe showed eslint reported
    // "File ignored because no matching configuration was supplied" for `.jsx` and exited 0, so a
    // single JSX component could route around both. The app is 100% TypeScript, but Vite compiles
    // `.jsx` regardless. Same class as the Wave-12 close HIGH (bypass shapes the ratifying probe
    // never enumerated), one axis over.
    const hits = await fenceMessages(
      `import { Link } from "react-router-dom";\nexport const X = () => <Link to="/" />;`,
      "src/probe.jsx",
    );
    expect(hits.length).toBeGreaterThan(0);
  });

  it("PERMITS react-router in a .jsx file (the extension fence is not a blanket ban)", async () => {
    const hits = await fenceMessages(
      `import { Link } from "react-router";\nexport const X = () => <Link to="/" />;`,
      "src/probe.jsx",
    );
    expect(hits).toEqual([]);
  });

  it("blocks a deep subpath import too (react-router-dom/server and friends)", async () => {
    const hits = await fenceMessages(
      `import { StaticRouter } from "react-router-dom/server";\nexport { StaticRouter };`,
      "src/probe.tsx",
    );
    expect(hits.length).toBeGreaterThan(0);
  });

  // ---- The positive controls. A fence that rejects everything proves nothing. ----

  it("PERMITS the replacement: `react-router` imports are unrestricted", async () => {
    const hits = await fenceMessages(
      `import { Link, useParams } from "react-router";\nexport { Link, useParams };`,
      "src/views/ops/probe.tsx",
    );
    expect(hits).toEqual([]);
  });

  it("PERMITS react-router in the write module, where the OTHER fence is relaxed", async () => {
    const hits = await fenceMessages(
      `import { Link } from "react-router";\nexport { Link };`,
      "src/api/writes.ts",
    );
    expect(hits).toEqual([]);
  });

  it("does not over-match a package whose name merely CONTAINS the banned one", async () => {
    const hits = await fenceMessages(
      `import x from "@scope/react-router-dom-utils";\nexport { x };`,
      "src/probe.tsx",
    );
    expect(hits).toEqual([]);
  });

  // ---- The V-3 regression pin, stated as its own assertion ----

  it("keeps BOTH fences live in src/api/writes.ts — only the write fence is relaxed there", async () => {
    // The write fence is relaxed here (that is the exemption's whole purpose)...
    const writeHits = await fenceMessages(
      `import { request } from "./client";\nexport { request };`,
      "src/api/writes.ts",
    );
    expect(writeHits).toEqual([]);
    // ...but the router fence is NOT. Before FE-M1 restructured the exemption from
    // `"no-restricted-imports": "off"` to a re-declaration, this assertion failed.
    const routerHits = await fenceMessages(
      `import { Link } from "react-router-dom";\nexport { Link };`,
      "src/api/writes.ts",
    );
    expect(routerHits.length).toBeGreaterThan(0);
  });
});
