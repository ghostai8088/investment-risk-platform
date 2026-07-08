# TC-1 Decision Record — FE Toolchain Bump (Wave-1 slice 1)

| Field | Value |
|---|---|
| Status | **IMPLEMENTED and CLOSED** — plan `76c7942` (CI #111 green); implementation `c34b346` (CI **#112** green — the first run OF the upgraded pipeline itself: Node 24 + the audit and format gates all executed); OQ-TC-1-1…5 ratified 2026-07-08; Tier-2 commit separately user-approved after the Part 6 review was folded |
| Date | 2026-07-08 |
| Basis | `delivery_roadmap.md` Wave 1, slice 1 (the FE-1 recorded follow-up: the scaffold-era vite5/vitest2 dev-only advisory chain; the keep-Vite/Vitest decision was accepted by the user 2026-07-08 — switching tools does not escape the advisory class). |
| Grounding | Verified 2026-07-08 against HEAD `63a1bb8` (CI #110): installed vite **5.4.21** / vitest **2.1.9** (the audit-flagged chain: 3 moderate + 1 high + 1 critical, ALL dev-server/test-runner surfaces; the critical requires the uninstalled Vitest UI). Targets: **vite 8.1.3** (engines `^20.19 \|\| >=22.12`), **vitest 4.1.10** (peer `vite ^6\|\|^7\|\|^8`), **@vitejs/plugin-react 6.0.3** (peer `vite ^8`). jsdom 29.1.1 + @testing-library/react 16.3.2 remain current. CI's frontend/shared-ts job runs **Node 20 — END-OF-LIFE since 2026-04**; local dev is Node 24.16. CI does NOT currently run the frontend `format:check`. Runtime deps (react/react-dom/react-router-dom) are UNTOUCHED by this slice. |
| Sign-off | **OQ-TC-1-1…5 — APPROVED / RATIFIED by the user (2026-07-08: "Proceed" on the full package, all five as recommended).** |

---

## Part 1 — Decisions at a glance

| ID | Topic | Decision |
|---|---|---|
| **OD-TC-1-A** | slice character | **Dev-toolchain only.** NO runtime-dependency change, NO application-code behavior change, NO backend/Python change, NO migration. Source edits only where a toolchain major REQUIRES them (config/test-API syntax), each noted in the review. |
| **OD-TC-1-B** | the bump | vite 5.4.21 → **8.x**, vitest 2.1.9 → **4.x**, @vitejs/plugin-react 4.x → **6.x** (the vite-8 peer). jsdom/@testing-library/react stay (current). All five audit findings resolve; `npm audit` expected clean afterward (verified at implementation). |
| **OD-TC-1-C** | CI Node | The frontend/shared-ts CI job moves **Node 20 → Node 24** (20 is EOL since 2026-04; 24 is the active LTS and matches local dev v24.16). The Python jobs are untouched. |
| **OD-TC-1-D** | the audit gate | NEW blocking CI step in the frontend job: **`npm audit --omit=dev --audit-level=high`** — a high/critical advisory in the RUNTIME dependency tree (react/react-dom/react-router-dom, currently 3 packages) turns CI red on its own. **Dev-tree advisories deliberately do NOT block CI** (they appear spontaneously and would fail unrelated PRs — a known flaky-CI source). **The wave-close review covers ALL sub-high advisories — runtime AND dev** *(wording widened at the implementation review, Part 6 finding 1: moderate runtime advisories previously fell under neither the CI gate nor the review cadence; tightening the CI gate to `moderate` for the tiny runtime tree is a recorded wave-close consideration)*. |
| **OD-TC-1-E** | format gate | Add the missing **`format:check`** (prettier) step to the frontend CI job — the script exists and passes locally but CI never ran it, so format drift could land silently. |
| **OD-TC-1-F** | proportionate review | A **3-finder** adversarial review instead of 6 (the diff is deps/config/CI only): (1) lockfile/supply-chain provenance scan; (2) CI-workflow correctness; (3) behavior-parity (test semantics unchanged under vitest 4 — same 37 tests, same assertions actually exercised, build output sane). The full validation gates are NOT reduced. |

## Part 2 — Rationale
The advisories are dev-only (no shipped code contains vite/vitest), so the risk being closed is the local
dev-server/test-runner attack surface — real but narrow; the ancillary wins (EOL Node off CI, an automated runtime
supply-chain gate, the missing format gate) make the slice worth its size. The version story is unusually clean:
plugin-react 6 pins vite 8; our vite config is already ESM; our vitest usage is the stable core API
(describe/it/expect/vi.fn/stubGlobal) — the majors' breaking changes concentrate in features we don't use
(workspaces, coverage providers, the UI). If implementation contradicts that expectation, the escape hatch is
vite 7/vitest 3 (also advisory-clean) with the delta recorded.

## Part 3 — Out of scope (fenced)
Runtime deps; any app-code refactor; OpenAPI codegen/state/UI libraries; gitleaks (OD-049) and branch protection
(OD-050) — separate recorded items; Python/backend/CI-migration-job changes; the dev header shim.

## Part 4 — Open decisions (OQ-TC-1-1…5) — **APPROVED / RATIFIED by the user (2026-07-08, the plan-commit gate)**
**Status: RATIFIED.** The five defaults below are fixed inputs to the TC-1 implementation.
- **OQ-TC-1-1 — recommend APPROVE.** The bump set: vite 8.x + vitest 4.x + plugin-react 6.x; jsdom/testing-library unchanged; runtime deps untouched. (OD-TC-1-B.)
- **OQ-TC-1-2 — recommend APPROVE.** CI frontend/shared-ts job Node 20 (EOL) → Node 24 LTS. (OD-TC-1-C.)
- **OQ-TC-1-3 — recommend APPROVE.** The blocking production-deps audit step; dev-tree advisories handled at wave closes, not in CI. (OD-TC-1-D.)
- **OQ-TC-1-4 — recommend APPROVE.** Add `format:check` to the frontend CI job. (OD-TC-1-E.)
- **OQ-TC-1-5 — recommend APPROVE.** The proportionate 3-finder review for a deps/config-only diff; validation gates unreduced. (OD-TC-1-F.)

## Part 5 — TC-1 implementation readiness gate
Implementation-ready once OQ-TC-1-1…5 are ratified. Build contract = `tc_1_implementation_plan.md`.
**TC-1 planning implements nothing.**

---

## Part 6 — Implementation adversarial review log (2026-07-08, independent-context, 3-finder per OD-TC-1-F)

> **CLOSEOUT STAMP (2026-07-08):** TC-1 **IMPLEMENTED and CLOSED** — plan `76c7942` (CI **#111**); implementation
> `c34b346` (CI **#112** green, user-confirmed + watcher-verified — the new frontend job's own first execution).
> `npm audit`: 0 vulnerabilities full-tree. Wave-1 slice 1 done; next per the roadmap: **VAR-HS-1**.

Findings: **1 folded, 1 dispositioned-with-evidence, 0 code changes.** The build itself needed ZERO source edits
(the Part 2 expectation held); `npm audit` = 0 vulnerabilities full-tree; the diff fence held at exactly 4 files.

- **Finder 1 (lockfile/supply-chain): CLEAN.** Runtime closure byte-identical (versions + integrity); 100%
  registry.npmjs.org; sha512 everywhere; NO new install scripts (esbuild's went away — the new tree has fewer);
  all 41 additions verified as the vite-8/rolldown/vitest-4 ecosystem (the one odd name, `obug`, individually
  verified against the live registry); the five scaffold-era advisories confirmed present at HEAD and absent
  after.
- **Finder 2 (CI workflow): 2 findings.** (1) **Moderate RUNTIME advisories were covered by neither the CI gate
  (high+ only) nor the wave-close wording (dev-tree only)** → FOLDED: OD-TC-1-D wording widened to "all sub-high
  advisories, runtime and dev" at wave closes; tightening the CI gate to `moderate` recorded as a wave-close
  consideration. (2) One unexplained `vitest run` exit-1 in 9 attempts (no output captured) → **dispositioned:
  12/12 subsequent SERIAL runs green; the failure occurred while two finders ran the suite concurrently on the
  same machine (resource contention); not reproduced; CI observation is the ongoing monitor — if the frontend job
  flakes on unrelated pushes, reopen as a vitest-4 worker-teardown suspect.** Everything else verified
  empirically: workspace audit coverage proven (the root-level `npm audit --omit=dev` audits the full lockfile
  incl. workspace runtime deps — 14 prod packages enumerated), Node 24 satisfies every engines range, `npm ci
  --dry-run` clean (no EUSAGE on CI), the ci.yml diff confined to the frontend job.
- **Finder 3 (behavior parity): CLEAN, with teeth proven.** All three mutation probes (encodeURIComponent
  removal / staleness-guard removal / Number() decimal corruption) were killed by EXACTLY the tests built to
  catch them (1+1+4 failures respectively) and each restore returned 37/37 green; every vitest API in use
  verified semantically unchanged 2→4; zero deprecation warnings; vite-8 bundle sane (~2% size delta); final
  tree check = only the 4 intended files.

*(Process note: the first run of finders 2+3 completed their work — incl. probe restoration, independently
verified — but died before reporting; both were re-run fresh on user direction and delivered the results above.)*

Post-fold validation: frontend lint/typecheck/format/test(37)/build green; shared-ts green; `make check` green
(917 passed — Python untouched); `npm audit` 0 vulnerabilities; `npm audit --omit=dev --audit-level=high` exit 0.
