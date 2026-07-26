/**
 * OPS-1: pin the REFUSAL contract the operations UI depends on.
 *
 * Three different governed refusals arrive as HTTP 409 and demand OPPOSITE remedies, so the UI
 * discriminates on the server's `detail` text (see `writes.ts::classifyRefusal`). That makes those
 * strings a real contract — but they live in the backend's `_ERROR_MAP`, and `gen-api-check` cannot
 * protect them because a `detail` value is data, not schema. A well-meaning backend reword would
 * silently degrade every SoD and stale-seq explanation to a generic "conflict" with no test failing.
 *
 * So this test pins the classifier against the EXACT detail strings the backend ships. The
 * companion assertion — that the OpenAPI 409 description still enumerates all three causes — lives
 * in `openapi-contract.test.ts` at the package root, alongside the other file-reading contract
 * tests (the typechecked `src` tree has no node types). It is the FE-2 lesson applied to prose:
 * a contract you hand-model must be pinned.
 */

import { describe, expect, it } from "vitest";

import { classifyRefusal } from "./writes";

/** The exact details the backend's `_ERROR_MAP` ships today (apps/backend/.../api/breaches.py). */
const BACKEND_DETAILS = {
  sod: "separation of duties: the actor responded to this breach",
  stale: "the breach changed while you were reading it; reload and retry",
  illegal: "illegal transition from the current breach state",
  assignee: "assignee must resolve to an active user in the tenant",
} as const;

describe("the refusal contract", () => {
  it("classifies each backend refusal detail distinctly", () => {
    expect(classifyRefusal(BACKEND_DETAILS.sod)).toBe("separation-of-duties");
    expect(classifyRefusal(BACKEND_DETAILS.stale)).toBe("stale");
    expect(classifyRefusal(BACKEND_DETAILS.illegal)).toBe("illegal-transition");
  });

  it("does not confuse the two conflict causes with each other", () => {
    // The regression this guards: before OPS-1 the stale-seq refusal REUSED the illegal-transition
    // detail verbatim, so the UI told operators "that move is not legal" when the truthful message
    // was "reload — the tick moved this underneath you". They are not interchangeable.
    expect(classifyRefusal(BACKEND_DETAILS.stale)).not.toBe(
      classifyRefusal(BACKEND_DETAILS.illegal),
    );
    expect(classifyRefusal(BACKEND_DETAILS.sod)).not.toBe(classifyRefusal(BACKEND_DETAILS.illegal));
  });

  it("falls back to 'other' for an unrecognised detail rather than guessing", () => {
    expect(classifyRefusal("some future refusal")).toBe("other");
    expect(classifyRefusal("")).toBe("other");
    // An assignee 422 is NOT a conflict cause — it must not be mistaken for one.
    expect(classifyRefusal(BACKEND_DETAILS.assignee)).toBe("other");
  });
});
