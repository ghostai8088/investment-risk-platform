/**
 * Wave-12 close fold (re-proving the OPS-1 M-4 write fence): the eslint `no-restricted-imports`
 * rule IS the fence around `client.ts::request` — there is no secondary guard — so it must be
 * unit-tested against the ACTUAL bypass forms, not proven once by hand with a single probe. The
 * shipped OPS-1 rule enumerated literal specifiers for depths 2-3 only; the close audit showed the
 * natural src-root form (`./api/client`) and every depth-4+ form passed clean. This test runs the
 * real resolved config through the ESLint API for every relative spelling at every depth (there
 * are no tsconfig/vite aliases, so relative specifiers are the only route to the module), plus the
 * namespace form, and pins the two intended pass-throughs: the `writes.ts` exemption and `apiGet`.
 */
// @vitest-environment node

import { ESLint } from "eslint";
import { existsSync } from "node:fs";
import { dirname, join } from "node:path";
import { describe, expect, it } from "vitest";

/** Walk up from the working directory to the package dir holding the flat config (same pattern as
 * api-prefixes.test.ts — `import.meta.url` is an http:// URL under vitest, not a file one). */
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

/** Every relative spelling of the client module, from every depth a file can sit at. The first
 * two rows are the exact bypass forms the shipped OPS-1 enumeration missed (the close audit's
 * empirical probes) — they are the negative controls that make this pin non-vacuous. */
const BYPASS_FORMS: Array<[spec: string, file: string]> = [
  ["./api/client", "src/probe.ts"], // src-root form — passed CLEAN before this fold
  ["../../../api/client", "src/views/deep/deeper/probe.ts"], // depth-4 form — also CLEAN before
  ["./client", "src/api/probe.ts"],
  ["../api/client", "src/views/probe.ts"],
  ["../../api/client", "src/views/ops/probe.ts"],
  ["../../../../api/client", "src/a/b/c/d/probe.ts"],
];

describe("the write fence (OQ-2=A): request() is importable ONLY in src/api/writes.ts", () => {
  it.each(BYPASS_FORMS)("blocks `request` via %s from %s", async (spec, file) => {
    const hits = await fenceMessages(
      `import { request } from "${spec}";\nexport { request };`,
      file,
    );
    expect(hits.length).toBeGreaterThan(0);
  });

  it("blocks the namespace form too (a `* as` import reaches request)", async () => {
    const hits = await fenceMessages(
      `import * as c from "../api/client";\nexport const r = c.request;`,
      "src/views/probe.ts",
    );
    expect(hits.length).toBeGreaterThan(0);
  });

  it("exempts src/api/writes.ts — the single audited write surface", async () => {
    const hits = await fenceMessages(
      `import { request } from "./client";\nexport { request };`,
      "src/api/writes.ts",
    );
    expect(hits).toEqual([]);
  });

  it("leaves the read path alone: `apiGet` imports are unrestricted", async () => {
    const hits = await fenceMessages(
      `import { apiGet } from "../api/client";\nexport { apiGet };`,
      "src/views/probe.ts",
    );
    expect(hits).toEqual([]);
  });
});
