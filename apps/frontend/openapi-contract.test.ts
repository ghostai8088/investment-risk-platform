/**
 * OPS-1: pin the parts of the API contract the operations UI hand-models.
 *
 * `gen-api-check` protects SCHEMAS (it regenerates types and fails on a diff), but two things the
 * ops UI depends on are not schema:
 *
 *   1. the **409 refusal causes** — three unrelated governed refusals share status 409 and the UI
 *      discriminates on the `detail` prose, so if the declared description stops enumerating them
 *      the hand-modelled classifier in `src/api/writes.ts` has silently drifted from the server;
 *   2. the **`seq` token** on `BreachOut` — the optimistic-concurrency precondition is only usable
 *      because the breach carries its own timeline head (OPS-1 fold H3). If that field disappears,
 *      every write would quietly fall back to the fail-OPEN unconditioned default.
 *
 * This file lives at the package root, next to `api-prefixes.test.ts`, because it reads files and
 * the typechecked `src` tree has no node types.
 */

import { existsSync, readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { describe, expect, it } from "vitest";

function repoFile(relative: string): string {
  let dir = process.cwd();
  for (;;) {
    const candidate = resolve(dir, relative);
    if (existsSync(candidate)) return candidate;
    const parent = dirname(dir);
    if (parent === dir) throw new Error(`could not locate ${relative} above ${process.cwd()}`);
    dir = parent;
  }
}

interface OpenApiDoc {
  paths: Record<
    string,
    Record<string, { responses?: Record<string, { description?: string }> }>
  >;
  components: { schemas: Record<string, { properties?: Record<string, unknown> }> };
}

function spec(): OpenApiDoc {
  return JSON.parse(readFileSync(repoFile("apps/frontend/openapi.json"), "utf8")) as OpenApiDoc;
}

describe("the committed OpenAPI contract", () => {
  it("declares the three distinct 409 causes on a breach write verb", () => {
    const conflict =
      spec().paths["/breaches/{breach_id}/respond"]?.post?.responses?.["409"]?.description ?? "";
    expect(conflict).toContain("separation-of-duties");
    expect(conflict).toContain("expected_seq");
    expect(conflict).toContain("illegal transition");
  });

  it("declares the refusal statuses the UI renders (403/409/503)", () => {
    const responses = spec().paths["/breaches/{breach_id}/review"]?.post?.responses ?? {};
    for (const code of ["403", "409", "503"]) {
      expect(Object.keys(responses)).toContain(code);
    }
  });

  it("exposes `seq` on BreachOut so expected_seq is obtainable", () => {
    const props = spec().components.schemas.BreachOut?.properties ?? {};
    expect(Object.keys(props)).toContain("seq");
  });

  it("still refuses to serialize the frozen Breach.status column (D6)", () => {
    // `state` is the recency-derived truth; the frozen column reads DETECTED forever. Leaking it
    // would give the UI a plausible-looking field that is always wrong.
    const props = spec().components.schemas.BreachOut?.properties ?? {};
    expect(Object.keys(props)).toContain("state");
    expect(Object.keys(props)).not.toContain("status");
  });
});
