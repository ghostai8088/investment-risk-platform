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
import { execSync } from "node:child_process";
import { readFileSync } from "node:fs";

const LEVELS = { info: 0, low: 1, moderate: 2, high: 3, critical: 4 };
const GATE = LEVELS.moderate;

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

const report = JSON.parse(auditJson());
const allowlist = JSON.parse(
  readFileSync(new URL("../audit-allowlist.json", import.meta.url), "utf8"),
);
const today = new Date().toISOString().slice(0, 10);

// Collect distinct advisories at/above the gate: GHSA id -> {severity, title, pkg}.
const advisories = new Map();
for (const [pkg, v] of Object.entries(report.vulnerabilities ?? {})) {
  for (const via of v.via ?? []) {
    if (typeof via !== "object" || !via.url) continue; // string vias just name the parent pkg
    const m = via.url.match(/GHSA-[0-9a-z-]+/i);
    if (!m) continue;
    if ((LEVELS[via.severity] ?? 0) < GATE) continue;
    advisories.set(m[0], { severity: via.severity, title: via.title ?? "", pkg });
  }
}

const allowById = new Map((allowlist.exceptions ?? []).map((e) => [e.id, e]));
let failed = false;

// (1) Expired exceptions fail — force a re-review.
for (const e of allowlist.exceptions ?? []) {
  if (e.review_by < today) {
    console.error(`EXCEPTION EXPIRED: ${e.id} (review_by ${e.review_by}) — re-review required.`);
    failed = true;
  }
}

// (2) Unallowlisted moderate+ advisories fail (fail-closed).
for (const [id, a] of advisories) {
  const e = allowById.get(id);
  if (e && e.review_by >= today) {
    console.log(`allowlisted (${a.severity}) ${id} [${a.pkg}] — ${e.reason}`);
  } else if (!e) {
    console.error(`UNALLOWLISTED ${a.severity} advisory ${id} [${a.pkg}] — ${a.title}`);
    failed = true;
  }
}

// (3) Fail closed on JSON-format drift: npm reports moderate+ vulns but the parser found none.
const meta = report.metadata?.vulnerabilities ?? {};
const metaGatePlus = (meta.moderate ?? 0) + (meta.high ?? 0) + (meta.critical ?? 0);
if (metaGatePlus > 0 && advisories.size === 0) {
  console.error(
    `FAIL-CLOSED: npm reports ${metaGatePlus} moderate+ vulnerabilities but no advisory ids were ` +
      `parsed — npm audit JSON format may have drifted. Refusing to pass.`,
  );
  failed = true;
}

// (4) Housekeeping note (does NOT fail): an allowlisted advisory no longer present (upstream fix).
for (const e of allowlist.exceptions ?? []) {
  if (!advisories.has(e.id)) {
    console.warn(`note: allowlisted ${e.id} no longer present — consider removing the exception.`);
  }
}

if (failed) {
  console.error("Frontend runtime-dependency audit FAILED.");
  process.exit(1);
}
console.log(
  advisories.size
    ? "Frontend runtime-dependency audit passed (only reachability-justified allowlisted exceptions)."
    : "Frontend runtime-dependency audit passed (no moderate+ advisories).",
);
