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

  it("blocks `request` in a .jsx file too (FE-M1 fold: the EXTENSION axis)", async () => {
    // This fence was scoped to `src/**/*.ts(x)`, so a `.jsx` component was linted by nothing at all
    // — eslint reported "File ignored because no matching configuration was supplied" and exited 0,
    // leaving an unaudited route to `client.ts::request`. Found while widening the fence set at
    // FE-M1; it is the Wave-12 close HIGH's own class along a different axis, so it is pinned here
    // rather than left for a fourth audit to rediscover.
    const hits = await fenceMessages(
      `import { request } from "./api/client";\nexport const X = request;`,
      "src/probe.jsx",
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

  it("blocks `request` from a .mts file (Wave-13 close: the TS half of the extension axis)", async () => {
    // FE-M1's R-1 closed the extension axis for the JS family (.js/.jsx/.mjs/.cjs) but left the
    // TypeScript family's own module-signalling extensions out of every fence glob. Both `tsc` and
    // Vite compile them, so the hole R-1 was raised to close was still open one letter over.
    const hits = await fenceMessages(
      `import { request } from "./client";\nexport const X = request;`,
      "src/api/probe.mts",
    );
    expect(hits.length).toBeGreaterThan(0);
  });
});

/**
 * Wave-13 close fold — the SYNTAX axis, this fence class's THIRD un-enumerated bypass (after
 * specifier spelling at the Wave-12 close and file extension at FE-M1 R-1).
 *
 * `no-restricted-imports` registers visitors for `ImportDeclaration` and friends and has NO
 * `ImportExpression` visitor, so `await import("../api/client")` was invisible to it. The router
 * half of the same axis is closed by a different control (`dependency-fence.test.ts` pins the
 * package absent from the lockfile, so a bare specifier cannot resolve at all) — but `../api/client`
 * is a LOCAL module that resolves through `import()` perfectly well, so the write half was open.
 */
describe("the dynamic-import fence (Wave-13 close): import() cannot reach request() either", () => {
  async function syntaxMessages(code: string, filePath: string) {
    const [result] = await eslint.lintText(code, { filePath });
    return result.messages.filter((m) => m.ruleId === "no-restricted-syntax");
  }

  it.each([
    ["../api/client", "src/views/probe.ts"],
    ["./api/client", "src/probe.ts"],
    ["./client", "src/api/probe.ts"],
    ["../../../api/client", "src/views/deep/deeper/probe.ts"],
  ])("blocks a dynamic import of %s from %s", async (spec, file) => {
    const hits = await syntaxMessages(
      `export async function s() { return await import("${spec}"); }`,
      file,
    );
    expect(hits.length).toBeGreaterThan(0);
  });

  it("blocks a dynamic import of react-router-dom", async () => {
    const hits = await syntaxMessages(
      `export async function s() { return await import("react-router-dom"); }`,
      "src/views/probe.ts",
    );
    expect(hits.length).toBeGreaterThan(0);
  });

  it("POSITIVE CONTROL: an unrelated dynamic import is untouched", async () => {
    // Without this, a fence that matched EVERY ImportExpression would pass the negatives above
    // while breaking legitimate code splitting — the by-absence trap R-4 was raised about.
    const hits = await syntaxMessages(
      `export async function s() { return await import("../session"); }`,
      "src/views/probe.ts",
    );
    expect(hits).toEqual([]);
  });

  it("POSITIVE CONTROL: writes.ts keeps its exemption for the client clause only", async () => {
    const allowed = await syntaxMessages(
      `export async function s() { return await import("./client"); }`,
      "src/api/writes.ts",
    );
    expect(allowed).toEqual([]);
    // ...but the router clause is still enforced there — the V-3 lesson: an exemption must stay
    // scoped to the thing it exempts, never switch the whole rule off.
    const stillFenced = await syntaxMessages(
      `export async function s() { return await import("react-router-dom"); }`,
      "src/api/writes.ts",
    );
    expect(stillFenced.length).toBeGreaterThan(0);
  });
});
