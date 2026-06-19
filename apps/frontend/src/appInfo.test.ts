import { describe, expect, it } from "vitest";

import { appInfo } from "./appInfo";

describe("appInfo", () => {
  it("returns the app name and a semver-like version", () => {
    const info = appInfo();
    expect(info.name).toBe("Investment Risk Platform");
    expect(info.version).toMatch(/\d+\.\d+\.\d+/);
  });
});
