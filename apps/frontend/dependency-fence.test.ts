/**
 * FE-M1 (OQ-FE-M1-4=D), fences 2 and 3 of 3 — the two things the lint fence structurally cannot see.
 *
 * Fence 1 (`router-fence.test.ts`) bans the `react-router-dom` IMPORT SPECIFIER. ESLint reads
 * source files, so it can never see:
 *
 *   (2) the MANIFEST. `npm install react-router-dom` with no import yet written passes lint clean,
 *       reinstates the vulnerable transitive `react-router@7`, and re-arms GHSA-qwww-vcr4-c8h2. The
 *       reintroduction is actively recommended by tooling: `npm audit` on the pre-migration tree
 *       reported `fixAvailable: { name: "react-router-dom", version: "7.11.0" }`.
 *
 *   (3) the RESOLVED TREE. react-router@8 requires react >= 19.2.7, and `@testing-library/react`
 *       peers on `^18 || ^19`. During FE-M1's dry run, a plain `npm install` over the old lockfile
 *       left testing-library holding a stale react@18.3.1 while the app resolved 19.2.8 — TWO React
 *       copies. `npm dedupe` is what collapses them, and it is a separate command a future
 *       contributor will not know to run.
 *
 * On fence 3, honestly: this is a DIAGNOSTIC, not the detector. The duplicate state was measured
 * during FE-M1 planning and it fails 73 of 150 tests loudly — but with cryptic hook-call errors
 * that read as "the migration broke everything" rather than "npm hoisted two Reacts". It is also
 * the one shape `tsc --noEmit` and `vite build` BOTH pass (measured), so any future pipeline that
 * builds without testing would ship it. The claim that "the suite cannot see this" would have been
 * false, and is not made here.
 */
// @vitest-environment node

import { existsSync, readFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { describe, expect, it } from "vitest";

/** Walk up from the working directory to the repo root (the dir holding package-lock.json). Same
 * pattern as api-prefixes.test.ts — `import.meta.url` is an http:// URL under vitest. */
function repoRoot(): string {
  let dir = process.cwd();
  for (;;) {
    if (existsSync(join(dir, "package-lock.json"))) return dir;
    const parent = dirname(dir);
    if (parent === dir) throw new Error("package-lock.json not found walking up from cwd");
    dir = parent;
  }
}

function readJson(path: string): Record<string, unknown> {
  return JSON.parse(readFileSync(path, "utf8")) as Record<string, unknown>;
}

const ROOT = repoRoot();
const frontendPkg = readJson(resolve(ROOT, "apps/frontend/package.json"));
const lock = readJson(resolve(ROOT, "package-lock.json")) as {
  packages: Record<string, { version?: string }>;
};

const declaredDeps = {
  ...((frontendPkg.dependencies as Record<string, string>) ?? {}),
  ...((frontendPkg.devDependencies as Record<string, string>) ?? {}),
};

/** Every resolved copy of a package in the lockfile, as `path -> version`. A workspace tree can
 * legitimately hold several copies of most packages; for React it cannot. */
function resolvedCopies(name: string): Array<[string, string]> {
  return Object.entries(lock.packages)
    .filter(([path]) => path.endsWith(`node_modules/${name}`))
    .map(([path, entry]) => [path, entry.version ?? "?"]);
}

describe("fence 2: react-router-dom is absent from the dependency manifests", () => {
  it("is not a declared dependency of the frontend", () => {
    expect(Object.keys(declaredDeps)).not.toContain("react-router-dom");
  });

  it("declares react-router instead, at the patched major", () => {
    // The advisory's affected range is >=7.12.0 <8.3.0, so anything below 8 re-arms it.
    const spec = (frontendPkg.dependencies as Record<string, string>)["react-router"];
    expect(spec).toBeDefined();
    expect(spec).toMatch(/^\^?8\./);
  });

  it("has no resolved copy anywhere in the lockfile (not even transitively)", () => {
    expect(resolvedCopies("react-router-dom")).toEqual([]);
  });

  it("resolves react-router at >= 8.3.0 — the version that PATCHES GHSA-qwww-vcr4-c8h2", () => {
    const copies = resolvedCopies("react-router");
    expect(copies.length).toBeGreaterThan(0);
    for (const [, version] of copies) {
      const [major, minor] = version.split(".").map(Number);
      expect(major).toBeGreaterThanOrEqual(8);
      if (major === 8) expect(minor).toBeGreaterThanOrEqual(3);
    }
  });
});

describe("fence 3: exactly one React", () => {
  // If this fails, the fix is `npm dedupe` — see the message below, which exists so the next
  // person does not spend an afternoon debugging 73 cryptic hook-call failures.
  const DEDUPE_HINT =
    "Run `npm install && npm dedupe` from the repo root. A plain `npm install` can leave " +
    "@testing-library/react holding its own react@18 alongside the app's react@19 — two React " +
    "copies, which breaks hooks at runtime and in tests (but passes tsc AND vite build).";

  it.each(["react", "react-dom"])("resolves exactly one copy of %s", (name) => {
    const copies = resolvedCopies(name);
    expect(copies.length, `${name}: found ${JSON.stringify(copies)}. ${DEDUPE_HINT}`).toBe(1);
  });

  it("resolves React at the major react-router@8 requires (peer floor >= 19.2.7)", () => {
    for (const name of ["react", "react-dom"]) {
      const [[, version]] = resolvedCopies(name);
      const [major, minor, patch] = version.split(".").map(Number);
      expect(major, `${name} is ${version}`).toBeGreaterThanOrEqual(19);
      if (major === 19) {
        expect(
          minor * 1000 + patch,
          `${name} is ${version}, below the 19.2.7 peer floor`,
        ).toBeGreaterThanOrEqual(2 * 1000 + 7);
      }
    }
  });

  it("keeps react and react-dom on the SAME version (they are released as a pair)", () => {
    const [[, react]] = resolvedCopies("react");
    const [[, reactDom]] = resolvedCopies("react-dom");
    expect(reactDom).toBe(react);
  });
});
