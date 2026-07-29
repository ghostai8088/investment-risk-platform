/**
 * FE-M1 (OQ-FE-M1-3=A): the first automated test of `scripts/check_frontend_audit.mjs`.
 *
 * This gate is the reason the FE-M1 slice exists — it is what fails CI when the react-router
 * advisory's time-bound exception expires — and until now it had NO test. Its three failure paths
 * were proven by hand once, in the session that wrote it, and that proof was never committed; what
 * remained was a claim in a decision record, which is not evidence (the standing Wave-12 close rule:
 * a shipped guard carries its EXECUTED negative control).
 *
 * FE-M1 makes that gap acute. Retiring `GHSA-qwww-vcr4-c8h2` empties the allowlist, so the
 * `exceptions: []` path — never once exercised — becomes the gate's PRIMARY path. A gate that
 * fails open on an empty allowlist would be silently useless from the moment this slice merges.
 *
 * Every fixture below is shaped from the REAL `npm audit --omit=dev --json` output measured on this
 * tree during FE-M1 recon (the react-router advisory), not from an invented schema — a fixture
 * derived from a guess cannot test a parser (the SR-1 lesson).
 */

import { describe, expect, it } from "vitest";

import { collectAdvisories, evaluateAudit } from "../../scripts/check_frontend_audit.mjs";

const TODAY = "2026-07-28";

/** The real advisory this slice retires, in the exact shape npm emits. */
function reportWithReactRouterAdvisory() {
  return {
    vulnerabilities: {
      "react-router": {
        name: "react-router",
        severity: "high",
        isDirect: false,
        via: [
          {
            source: 1124282,
            name: "react-router",
            dependency: "react-router",
            title: "React Router: RSC Mode CSRF Bypass Allows Action Execution Before 400 Response",
            url: "https://github.com/advisories/GHSA-qwww-vcr4-c8h2",
            severity: "high",
            cwe: ["CWE-352"],
            range: ">=7.12.0 <8.3.0",
          },
        ],
        range: "7.12.0 - 8.2.0",
      },
      "react-router-dom": {
        name: "react-router-dom",
        severity: "high",
        isDirect: true,
        via: ["react-router"], // a STRING via just names the parent package — must not parse as an advisory
        range: ">=7.12.0-pre.0",
      },
    },
    metadata: { vulnerabilities: { info: 0, low: 0, moderate: 0, high: 2, critical: 0, total: 2 } },
  };
}

/** The post-migration state this slice ships: nothing to report. */
function cleanReport() {
  return {
    vulnerabilities: {},
    metadata: { vulnerabilities: { info: 0, low: 0, moderate: 0, high: 0, critical: 0, total: 0 } },
  };
}

const LIVE_EXCEPTION = {
  id: "GHSA-qwww-vcr4-c8h2",
  package: "react-router",
  severity: "high",
  reason: "NOT REACHABLE in this app: client-only SPA, no RSC and no data-router server actions.",
  introduced: "2026-07-24",
  review_by: "2026-10-24",
};

describe("check_frontend_audit gate", () => {
  // ---- The path FE-M1 puts into service, which had never been exercised ----

  it("PASSES on an empty allowlist when the tree is clean (the state FE-M1 ships)", () => {
    const r = evaluateAudit(cleanReport(), { exceptions: [] }, TODAY);
    expect(r.failed).toBe(false);
    expect(r.errors).toEqual([]);
    expect(r.summary).toContain("no moderate+ advisories");
  });

  it("FAILS CLOSED on an empty allowlist when an advisory is present", () => {
    // The negative control for the test above. An empty allowlist must mean "nothing is excused",
    // never "nothing is checked" — if these two shared an outcome the gate would be decorative.
    const r = evaluateAudit(reportWithReactRouterAdvisory(), { exceptions: [] }, TODAY);
    expect(r.failed).toBe(true);
    expect(r.errors.join("\n")).toContain("UNALLOWLISTED high advisory GHSA-qwww-vcr4-c8h2");
  });

  it("FAILS CLOSED when the allowlist key is absent entirely, not just empty", () => {
    const r = evaluateAudit(reportWithReactRouterAdvisory(), {}, TODAY);
    expect(r.failed).toBe(true);
  });

  // ---- The time-bound exception mechanism (the whole point of the allowlist) ----

  it("PASSES an unexpired, reachability-justified exception and echoes its rationale", () => {
    const r = evaluateAudit(
      reportWithReactRouterAdvisory(),
      { exceptions: [LIVE_EXCEPTION] },
      TODAY,
    );
    expect(r.failed).toBe(false);
    expect(r.info.join("\n")).toContain("allowlisted (high) GHSA-qwww-vcr4-c8h2");
    expect(r.info.join("\n")).toContain("NOT REACHABLE");
  });

  it("FAILS on an EXPIRED exception — the 2026-10-24 cliff this slice exists to beat", () => {
    const expired = { ...LIVE_EXCEPTION, review_by: "2026-07-27" }; // yesterday
    const r = evaluateAudit(reportWithReactRouterAdvisory(), { exceptions: [expired] }, TODAY);
    expect(r.failed).toBe(true);
    expect(r.errors.join("\n")).toContain("EXCEPTION EXPIRED: GHSA-qwww-vcr4-c8h2");
  });

  it("treats review_by === today as still valid (the boundary is inclusive, not off-by-one)", () => {
    const boundary = { ...LIVE_EXCEPTION, review_by: TODAY };
    const r = evaluateAudit(reportWithReactRouterAdvisory(), { exceptions: [boundary] }, TODAY);
    expect(r.failed).toBe(false);
  });

  it("FAILS an expired exception even when its advisory has since been fixed upstream", () => {
    // Expiry means "re-review this decision", and the decision record is stale whether or not the
    // advisory happens to be gone. This is also exactly the state a half-done FE-M1 would leave.
    const expired = { ...LIVE_EXCEPTION, review_by: "2026-07-27" };
    const r = evaluateAudit(cleanReport(), { exceptions: [expired] }, TODAY);
    expect(r.failed).toBe(true);
    expect(r.errors.join("\n")).toContain("EXCEPTION EXPIRED");
  });

  // ---- The JSON-drift fail-closed guard ----

  it("FAILS CLOSED when npm counts moderate+ vulns but no advisory ids parse (format drift)", () => {
    const drifted = {
      vulnerabilities: { "some-pkg": { name: "some-pkg", severity: "high", via: ["other-pkg"] } },
      metadata: { vulnerabilities: { moderate: 0, high: 3, critical: 0 } },
    };
    const r = evaluateAudit(drifted, { exceptions: [] }, TODAY);
    expect(r.failed).toBe(true);
    expect(r.errors.join("\n")).toContain("FAIL-CLOSED");
  });

  it("does NOT fire the drift guard when npm genuinely reports zero moderate+ vulns", () => {
    // The negative control for the guard above: silence must not be read as drift.
    const r = evaluateAudit(cleanReport(), { exceptions: [] }, TODAY);
    expect(r.errors.join("\n")).not.toContain("FAIL-CLOSED");
  });

  // ---- The moderate gate boundary ----

  it("ignores advisories BELOW the moderate gate", () => {
    const low = {
      vulnerabilities: {
        "tiny-pkg": {
          name: "tiny-pkg",
          severity: "low",
          via: [
            {
              title: "a cosmetic issue",
              url: "https://github.com/advisories/GHSA-0000-0000-0001",
              severity: "low",
            },
          ],
        },
      },
      metadata: { vulnerabilities: { low: 1, moderate: 0, high: 0, critical: 0 } },
    };
    const r = evaluateAudit(low, { exceptions: [] }, TODAY);
    expect(r.failed).toBe(false);
    expect(collectAdvisories(low).size).toBe(0);
  });

  it("gates a MODERATE advisory (the Wave-1-close tightening is real, not documentation)", () => {
    const moderate = {
      vulnerabilities: {
        "mid-pkg": {
          name: "mid-pkg",
          severity: "moderate",
          via: [
            {
              title: "a moderate issue",
              url: "https://github.com/advisories/GHSA-0000-0000-0002",
              severity: "moderate",
            },
          ],
        },
      },
      metadata: { vulnerabilities: { low: 0, moderate: 1, high: 0, critical: 0 } },
    };
    const r = evaluateAudit(moderate, { exceptions: [] }, TODAY);
    expect(r.failed).toBe(true);
  });

  // ---- Parsing ----

  it("counts one advisory per GHSA id, not one per affected package", () => {
    // `react-router-dom`'s via is the STRING "react-router" — the same advisory reached through a
    // parent, not a second finding. Double-counting here would make the reports unreadable.
    expect([...collectAdvisories(reportWithReactRouterAdvisory()).keys()]).toEqual([
      "GHSA-qwww-vcr4-c8h2",
    ]);
  });

  // ---- Housekeeping (must NOT fail the gate) ----

  it("warns without failing when an allowlisted advisory is gone (FE-M1's own transition)", () => {
    // The exact state on the FE-M1 branch between the dependency bump and emptying the allowlist.
    const r = evaluateAudit(cleanReport(), { exceptions: [LIVE_EXCEPTION] }, TODAY);
    expect(r.failed).toBe(false);
    expect(r.warnings.join("\n")).toContain("no longer present");
  });

  // ---- Exception SHAPE (Wave-13 close: a fail-OPEN inside the fail-closed gate) ----

  // Every date test in the gate is a JS relational comparison against a string, and EVERY relational
  // comparison with `undefined` is false. So an exception missing `review_by` was simultaneously
  // "not expired" (rule 1 silent), "not current" (no info line), and present (so `!e` was false and
  // no UNALLOWLISTED error fired) — the advisory fell through every branch and vanished. These cases
  // pin the failure DIRECTION: a malformed governance record must fail, never degrade to silence.
  it.each([
    ["missing review_by", { id: "GHSA-qwww-vcr4-c8h2", reason: "r" }],
    ["null review_by", { id: "GHSA-qwww-vcr4-c8h2", reason: "r", review_by: null }],
    ["non-string review_by", { id: "GHSA-qwww-vcr4-c8h2", reason: "r", review_by: 20261024 }],
    ["non-ISO review_by", { id: "GHSA-qwww-vcr4-c8h2", reason: "r", review_by: "24/10/2026" }],
    ["missing reason", { id: "GHSA-qwww-vcr4-c8h2", review_by: "2026-10-24" }],
  ])("FAILS closed on a %s exception instead of swallowing the advisory", (_label, exception) => {
    const r = evaluateAudit(reportWithReactRouterAdvisory(), { exceptions: [exception] }, TODAY);
    expect(r.failed).toBe(true);
    // Both halves matter: the record is named AND the advisory it was covering is named, so the
    // operator sees what is actually unguarded rather than merely that a file is untidy.
    expect(r.errors.join("\n")).toContain("MALFORMED EXCEPTION");
    expect(r.errors.join("\n")).toContain("GHSA-qwww-vcr4-c8h2");
  });

  it("POSITIVE CONTROL: a well-formed, unexpired exception still allowlists its advisory", () => {
    // Without this, a shape gate that rejected EVERY exception would pass all five cases above
    // while breaking the mechanism entirely — the by-absence trap R-4 was raised about.
    const r = evaluateAudit(
      reportWithReactRouterAdvisory(),
      { exceptions: [LIVE_EXCEPTION] },
      TODAY,
    );
    expect(r.failed).toBe(false);
    expect(r.info.join("\n")).toContain("allowlisted");
  });
});
