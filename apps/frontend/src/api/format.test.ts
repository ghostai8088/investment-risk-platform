import { describe, expect, it } from "vitest";

import { shortId, verbatim } from "./format";

describe("verbatim", () => {
  it("renders a governed decimal string UNCHANGED (never re-parsed)", () => {
    // The exact 20-dp string from a covariance read must survive to the DOM byte-for-byte.
    const gov = "0.00000697448275862069";
    expect(verbatim(gov)).toBe(gov);
    expect(verbatim("3.322722")).toBe("3.322722");
    // A value that Number() would mangle (trailing zeros / precision) stays intact.
    expect(verbatim("100.00000000000000000000")).toBe("100.00000000000000000000");
  });

  it("renders null/undefined as an em dash and coerces non-strings with String()", () => {
    expect(verbatim(null)).toBe("—");
    expect(verbatim(undefined)).toBe("—");
    expect(verbatim(42)).toBe("42");
    expect(verbatim(true)).toBe("true");
  });
});

describe("shortId", () => {
  it("truncates long ids and leaves short ones", () => {
    expect(shortId("8475e693-daa6-4991-b28f-5d59c5dd722c")).toBe("8475e693…");
    expect(shortId("demo")).toBe("demo");
  });
});
