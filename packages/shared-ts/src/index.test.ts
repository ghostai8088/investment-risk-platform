import { describe, expect, it } from "vitest";

import { SHARED_LIB_VERSION } from "./index";

describe("shared-ts", () => {
  it("exposes a semver-like version", () => {
    expect(SHARED_LIB_VERSION).toMatch(/\d+\.\d+\.\d+/);
  });
});
