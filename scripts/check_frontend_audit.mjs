#!/usr/bin/env node
// Runtime-dependency audit gate for the PRODUCTION frontend tree (TC-1 / OD-TC-1-D; tightened
// high->moderate at the Wave-1 close, OQ-W1C-4). Replaces a bare `npm audit --omit=dev
// --audit-level=moderate` with the SAME semantics PLUS a time-bound, reachability-justified
// allowlist (`audit-allowlist.json`): npm audit queries a LIVE advisory DB, so an unchanged tree
// can flip green->red when a new advisory publishes; a genuinely-unreachable advisory can be
// excepted with a written rationale and a review_by date. Governance guardrails:
//   - only advisories at/above `moderate` gate (parity with the old --audit-level);
//   - an EXPIRED exception (review_by < today) FAILS the gate — exceptions must be re-reviewed;
//   - any advisory NOT on the allowlist FAILS the gate (fail-closed);
//   - fails CLOSED if npm reports moderate+ vulns but the parser extracts none (JSON-format drift).
// Local run: `node scripts/check_frontend_audit.mjs` from the repo root.
//
// FE-M1 (OQ-FE-M1-3=A): the decision logic is split out of the CLI into the pure, exported
// `evaluateAudit(report, allowlist, today)` so it can be TESTED — see apps/frontend/audit-gate.test.ts.
// This gate is the reason the FE-M1 slice exists, it had no automated test of any kind, and FE-M1
// empties its allowlist, which puts the `exceptions: []` path into service having never once been
// exercised. A guard ships with its executed negative control (the Wave-12 close, OQ-W12C-3a);
// this one had been carrying a hand-run-once-in-a-past-session claim instead.
//
// Precisely what did and did not change: the four checks, their conditions, which of them FAIL the
// gate, and the exit code are all identical. The console OUTPUT is regrouped — messages were
// previously printed as each check ran (interleaved), and are now collected and printed as
// info -> warnings -> errors. Same lines, same text, different order. Saying "behaviour is
// unchanged" without that caveat would be the kind of overclaim this file's own slice exists to
// stop making.
import { execSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { argv, exit } from "node:process";
import { pathToFileURL } from "node:url";

export const LEVELS = { info: 0, low: 1, moderate: 2, high: 3, critical: 4 };
export const GATE = LEVELS.moderate;

/**
 * Collect the distinct advisories at/above the gate from an `npm audit --json` report.
 * @returns {Map<string, {severity: string, title: string, pkg: string}>} GHSA id -> detail
 */
export function collectAdvisories(report) {
  const advisories = new Map();
  for (const [pkg, v] of Object.entries(report.vulnerabilities ?? {})) {
    for (const via of v.via ?? []) {
      if (typeof via !== "object" || !via.url) continue; // string vias just name the parent pkg
      const m = via.url.match(/GHSA-[0-9a-z-]+/i);
      if (!m) continue;
      if ((LEVELS[via.severity] ?? 0) < GATE) continue;
      advisories.set(m[0], {
        severity: via.severity,
        title: via.title ?? "",
        pkg,
      });
    }
  }
  return advisories;
}

/**
 * The whole gate decision, as a pure function of its three inputs.
 * @param report   parsed `npm audit --omit=dev --json` output
 * @param allowlist parsed audit-allowlist.json
 * @param today    ISO yyyy-mm-dd string
 * @returns {{failed: boolean, errors: string[], warnings: string[], info: string[], summary: string}}
 */
export function evaluateAudit(report, allowlist, today) {
  const advisories = collectAdvisories(report);
  const allowById = new Map((allowlist.exceptions ?? []).map((e) => [e.id, e]));
  const errors = [];
  const warnings = [];
  const info = [];

  // (0) Wave-13 close fold — the exception SHAPE gate, closing a fail-OPEN in a fail-closed gate.
  //
  // Every date test here is a JS relational comparison against a string. If `review_by` is missing,
  // null, or not a string, EVERY such comparison is false — `undefined < "2026-07-29"` is false, and
  // so is `undefined >= "2026-07-29"`. The consequence in the code below was that a malformed
  // exception made its advisory fall through BOTH branches of (2): not expired (so (1) stays
  // silent), not allowlisted-and-current (so no info line), and `!e` is false (so no UNALLOWLISTED
  // error). A CRITICAL advisory was silently swallowed — no error, no warning, not even an info
  // line — by the gate whose entire purpose is to fail closed.
  //
  // An exception is a governance artifact: a written rationale plus a review date. One missing its
  // date is not a weaker exception, it is not an exception at all, so it fails rather than degrades.
  const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;
  const malformed = new Set();
  for (const [i, e] of (allowlist.exceptions ?? []).entries()) {
    const problems = [];
    if (typeof e?.id !== "string" || !e.id)
      problems.push("id must be a non-empty string");
    if (typeof e?.review_by !== "string" || !ISO_DATE.test(e.review_by)) {
      problems.push(
        `review_by must be a yyyy-mm-dd string (got ${JSON.stringify(e?.review_by)})`,
      );
    }
    if (typeof e?.reason !== "string" || !e.reason)
      problems.push("reason must be a non-empty string");
    if (problems.length) {
      if (typeof e?.id === "string") malformed.add(e.id);
      errors.push(
        `MALFORMED EXCEPTION at index ${i}${typeof e?.id === "string" ? ` (${e.id})` : ""}: ` +
          `${problems.join("; ")}. Refusing to pass — an exception without a valid review date ` +
          `cannot expire, so it would silence its advisory forever.`,
      );
    }
  }

  // (1) Expired exceptions fail — force a re-review.
  for (const e of allowlist.exceptions ?? []) {
    if (
      typeof e?.review_by === "string" &&
      ISO_DATE.test(e.review_by) &&
      e.review_by < today
    ) {
      errors.push(
        `EXCEPTION EXPIRED: ${e.id} (review_by ${e.review_by}) — re-review required.`,
      );
    }
  }

  // (2) Unallowlisted moderate+ advisories fail (fail-closed).
  for (const [id, a] of advisories) {
    const e = allowById.get(id);
    const usable = e && !malformed.has(id) && ISO_DATE.test(e.review_by ?? "");
    if (usable && e.review_by >= today) {
      info.push(`allowlisted (${a.severity}) ${id} [${a.pkg}] — ${e.reason}`);
    } else if (!e) {
      errors.push(
        `UNALLOWLISTED ${a.severity} advisory ${id} [${a.pkg}] — ${a.title}`,
      );
    } else if (!usable) {
      // The malformed-shape error above names the entry; this names the ADVISORY it was silently
      // covering, so the operator sees what is actually unguarded rather than only that a record
      // is untidy.
      errors.push(
        `UNGUARDED ${a.severity} advisory ${id} [${a.pkg}] — ${a.title} (its allowlist entry is ` +
          `malformed, so it grants nothing).`,
      );
    }
    // An allowlisted-but-EXPIRED advisory is already failed by (1); it is deliberately not
    // double-reported here.
  }

  // (3) Fail closed on JSON-format drift: npm reports moderate+ vulns but the parser found none.
  const meta = report.metadata?.vulnerabilities ?? {};
  const metaGatePlus =
    (meta.moderate ?? 0) + (meta.high ?? 0) + (meta.critical ?? 0);
  if (metaGatePlus > 0 && advisories.size === 0) {
    errors.push(
      `FAIL-CLOSED: npm reports ${metaGatePlus} moderate+ vulnerabilities but no advisory ids were ` +
        `parsed — npm audit JSON format may have drifted. Refusing to pass.`,
    );
  }

  // (4) Housekeeping note (does NOT fail): an allowlisted advisory no longer present (upstream fix).
  for (const e of allowlist.exceptions ?? []) {
    if (!advisories.has(e.id)) {
      warnings.push(
        `note: allowlisted ${e.id} no longer present — consider removing the exception.`,
      );
    }
  }

  return {
    failed: errors.length > 0,
    errors,
    warnings,
    info,
    summary: advisories.size
      ? "Frontend runtime-dependency audit passed (only reachability-justified allowlisted exceptions)."
      : "Frontend runtime-dependency audit passed (no moderate+ advisories).",
  };
}

function auditJson() {
  // npm audit exits non-zero when vulnerabilities exist; capture stdout either way.
  try {
    return execSync("npm audit --omit=dev --json", {
      encoding: "utf8",
      stdio: ["ignore", "pipe", "ignore"],
    });
  } catch (e) {
    if (e.stdout) return e.stdout;
    throw e;
  }
}

function main() {
  const report = JSON.parse(auditJson());
  const allowlist = JSON.parse(
    readFileSync(new URL("../audit-allowlist.json", import.meta.url), "utf8"),
  );
  const today = new Date().toISOString().slice(0, 10);
  const result = evaluateAudit(report, allowlist, today);

  for (const line of result.info) console.log(line);
  for (const line of result.warnings) console.warn(line);
  for (const line of result.errors) console.error(line);

  if (result.failed) {
    console.error("Frontend runtime-dependency audit FAILED.");
    exit(1);
  }
  console.log(result.summary);
}

// Run only when invoked directly, so the test can import the pure functions above.
if (argv[1] && import.meta.url === pathToFileURL(argv[1]).href) {
  main();
}
