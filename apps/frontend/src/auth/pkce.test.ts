import { describe, expect, it } from "vitest";

import { base64UrlEncode, codeChallengeS256, randomCodeVerifier } from "./pkce";

describe("pkce", () => {
  it("base64url-encodes without padding or +/", () => {
    // 0xFB 0xFF → base64 "+/8=" → base64url "-_8"
    expect(base64UrlEncode(new Uint8Array([0xfb, 0xff]))).toBe("-_8");
    expect(base64UrlEncode(new Uint8Array([]))).toBe("");
  });

  it("generates a 43-char base64url verifier from 32 random bytes", () => {
    const v = randomCodeVerifier();
    expect(v).toHaveLength(43);
    expect(v).toMatch(/^[A-Za-z0-9\-_]+$/);
    expect(randomCodeVerifier()).not.toBe(v); // random each call
  });

  it("computes the S256 challenge — the RFC 7636 Appendix-B known-answer vector", async () => {
    // RFC 7636 §B: verifier → SHA-256 → base64url challenge (the canonical PKCE test vector).
    const verifier = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk";
    const challenge = await codeChallengeS256(verifier);
    expect(challenge).toBe("E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM");
  });
});
