# TC-1 Implementation Plan — FE Toolchain Bump

> Build contract for TC-1 (decisions: `tc_1_decision_record.md`, OD-TC-1-A…F; gated on OQ-TC-1-1…5).
> Dev-toolchain only: NO runtime deps, NO app behavior, NO Python, NO migration. Planned against `63a1bb8`.

## Steps
1. **Bump** (workspace `apps/frontend`): `vite@^8`, `vitest@^4`, `@vitejs/plugin-react@^6` (devDependencies).
   Lockfile regenerates; diff audited (registry hosts, install scripts) by finder 1.
2. **Config/test fixes only as required by the majors** — expected small or zero (ESM config already; stable core
   vitest API). Every required edit is listed in the review log. If the majors force semantic changes to tests,
   STOP and re-plan (that contradicts the Part 2 expectation).
3. **ci.yml (frontend job only):** `node-version: "20"` → `"24"`; NEW step `npm audit --omit=dev
   --audit-level=high` (blocking); NEW step `npm run -w apps/frontend format:check`.
4. **Verify the advisory close:** `npm audit` (full tree) recorded in the review log — expected clean; if any
   dev-tree advisory remains, record it honestly with disposition.
5. **Validation gates (unreduced):** full frontend set (lint / typecheck / format:check / test ×37 / build) +
   shared-ts test + `make check` (proves the Python side untouched incl. docs/secret scans) + a `git diff --stat`
   fence proving the diff is confined to `apps/frontend/package.json`, `package-lock.json`,
   `apps/frontend/vite.config.ts`(if required), test files (only if required by step 2), and `.github/workflows/ci.yml`.
6. **Proportionate 3-finder review** (OD-TC-1-F) → fold → HOLD Tier-2 commit approval → push → CI green →
   Tier-0 closeout (roadmap amendment log NOT needed — this IS the sequence).

## Definition of done
All 37 frontend tests + build green on vite 8/vitest 4; CI green on Node 24 with the two new steps; `npm audit
--omit=dev` clean and blocking in CI; the five scaffold-era advisories gone (or honestly dispositioned); zero
runtime-dependency and zero Python changes.
