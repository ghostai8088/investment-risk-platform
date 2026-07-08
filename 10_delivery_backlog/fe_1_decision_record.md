# FE-1 Decision Record — Read-Only Frontend "Risk Runs & Results" View (the first visible slice)

| Field | Value |
|---|---|
| Status | **PLANNING RATIFIED** — OQ-FE-1-1…8 approved by the user at the commit gate (2026-07-07, after a plain-language decision briefing); implementation is a SEPARATE approval |
| Date | 2026-07-07 |
| Basis | User direction 2026-07-07: the read-only frontend view chosen as the next slice on the walking-skeleton / thin-vertical-slice recommendation (integrate end-to-end early; the API surface has never had an external consumer). Sits OUTSIDE the P3 number-sequence (a cross-cutting UI slice; the P3 roadmap — P3-6/P3-7/roadmap VaR methods — is unchanged). |
| Grounding | Verified against shipped HEAD `ee3c581` (CI #106): `apps/frontend` is a React 18 + Vite 5 + TypeScript 5.5 scaffold (vitest/eslint/prettier; CI job runs lint/typecheck/test/build; `App.tsx` is a placeholder shell); the `/risk` router exposes per-family `GET …/runs/{run_id}` (run + embedded result rows + `failure_reason`) and `GET …/{row_id}` but **NO list endpoint**; `get_principal` is the documented DEV header shim (`X-User-Id`/`X-Tenant-Id` — "unverified and not a security boundary until SSO", DR-P1A0-3); no CORS middleware exists; all result DTOs already serialize decimal values as exact strings; `calculation_run` carries `run_type/status/created_at/completed_at/failure_reason` + full provenance columns. |
| Sign-off | **OQ-FE-1-1…8 — APPROVED / RATIFIED by the user (2026-07-07: "Proceed" on the full package, all eight as recommended, after the simplified decision-point briefing).** |

---

## Part 1 — Decisions at a glance

| ID | Topic | Decision |
|---|---|---|
| **OD-FE-1-A** | slice character | The **first frontend slice**: READ-ONLY. NO new governed number, NO new entity/canonical id, NO new permission, NO new audit code, **NO migration**. Exactly ONE additive backend change: the read-only list-runs endpoint (OD-FE-1-C). Everything else is frontend-only. |
| **OD-FE-1-B** | screens | TWO screens, nothing more: **(1) Runs list** — the four RISK run families (SENSITIVITY / FACTOR_EXPOSURE / COVARIANCE / VAR), columns run_type, status, created_at, completed_at, initiated_by, failure_reason (truncated), run_id; filterable by run_type and status; paginated. **(2) Run detail** — full provenance (input_snapshot_id, model_version_id, code_version, environment_id, initiated_by, status, failure_reason verbatim) + the family-specific result-rows table via the EXISTING per-family `GET /risk/…/runs/{run_id}`. A FAILED run renders its persisted `failure_reason` prominently (the P3-C1 column's first consumer). NO dashboards, NO charts, NO run triggering, NO editing, NO other domains (portfolios/market data/exposure screens are out). |
| **OD-FE-1-C** | the ONE backend addition | **`GET /risk/runs`** — tenant-scoped (RLS session), gated by the EXISTING `risk.view`, restricted to the four RISK `run_type`s (a `run_type` outside the four and any unknown `status` are 422 refusals — fail closed, never silently empty); optional `run_type`/`status` filters; `limit` (default 50, max 200) + `offset`, ordered `created_at DESC, run_id` (deterministic pagination); NO total count in v1 (no COUNT(*) cost; the UI pages by offset). Read-only ⇒ NO audit event (the standing GET precedent). Service home: a new read-only `irp_shared/risk/queries.py` (thin router, service-side query — the house pattern). Exposure-family runs are EXCLUDED (different permission family, `exposure.view`) — a recorded follow-up, not silently mixed in. |
| **OD-FE-1-D** | auth posture | The UI uses the EXISTING dev header shim and says so loudly: a session form (user id + tenant id, kept in `sessionStorage`, sent as `X-User-Id`/`X-Tenant-Id` on every request) plus a **permanent, non-dismissable "DEV SESSION — identity is unverified; not a security boundary until SSO (AD-007)" banner**. Server-side entitlement (`risk.view`, deny-by-default) and RLS remain the ONLY enforcement — the UI adds none and claims none. 401/403 render as honest states ("no session" / "not entitled"), never masked. Real SSO stays P6+ (AD-007/DR-P1A0-3), UNCHANGED by this slice. |
| **OD-FE-1-E** | dev wiring | **Vite dev proxy** (`server.proxy: {"/risk": "http://localhost:8000"}`) — the backend gains NO CORS middleware (no production-shaped config for a dev concern). The run recipe (uvicorn + vite + a seeded local DB) is documented in `apps/frontend/README.md`. |
| **OD-FE-1-F** | dependencies | Exactly ONE new runtime dependency: **`react-router-dom`** — run-detail URLs (`/runs/{run_id}`) must be deep-linkable/bookmarkable (an audit-oriented platform wants shareable evidence links; hand-rolled routing is false economy). NO state library, NO component/CSS framework, NO codegen toolchain — plain fetch + hand-written types + minimal CSS. Any further dependency is a decision, not a drive-by. |
| **OD-FE-1-G** | API client + types | A thin hand-written typed client (`src/api/`): one fetch wrapper injecting the two dev headers + TS interfaces mirroring the run/row DTOs. NO OpenAPI codegen in v1 (the consumed surface is 5 endpoints; a codegen toolchain is not yet paying rent — revisit when the surface grows). **Decimal values remain strings end-to-end** — displayed verbatim, NEVER `parseFloat`/`Number()` (the PreciseDecimal contract extends into the display layer). |
| **OD-FE-1-H** | testing | Frontend: vitest component tests over a mocked fetch — list rendering + filters, FAILED-run `failure_reason` display, decimal-string verbatim rendering, dev-banner presence, 401/403/error states, run_type→detail-endpoint routing. Backend: endpoint tests for `GET /risk/runs` — tenant scoping (two-tenant separation), the four-run_type restriction, filter refusals (422), pagination caps/determinism, 403 without `risk.view`, and PG coverage via the existing suites' pattern. CI already runs both jobs; no new CI step. |

## Part 2 — Rationale highlights

### OD-FE-1-C — why one generic list endpoint and not four per-family ones
The four families share ONE `calculation_run` table with a `run_type` discriminator, and the screen is one list.
Four parallel list endpoints would quadruple surface for zero information. The four-run_type restriction keeps the
endpoint inside the `risk.view` permission's honest scope; exposure runs would smuggle a different permission
family into a risk-gated endpoint.

### OD-FE-1-D — why the dev shim is acceptable here and what makes it honest
Enforcement never moves client-side: the backend already 401s a missing principal, 403s a missing `risk.view`,
and RLS scopes every row. The UI is a viewer over an already-enforced API. What would be DISHONEST is a
login-looking screen implying verified identity — hence the permanent banner and the "session", not "login",
vocabulary. This slice must not create pressure to soften that.

### OD-FE-1-F/G — why so few dependencies
The first UI slice sets the frontend's cost baseline. Every runtime dependency is supply-chain surface the secret
scan and review process must carry forever (BR-10 discipline). Two screens need routing (real value: deep links)
and nothing else. Codegen, state managers, and UI kits can each be added later WHEN a slice demonstrates the need.

### What this slice deliberately proves (the walking-skeleton payoff)
First external consumer of the API: surfaces auth-session ergonomics, DTO display-fitness, and the list-endpoint
gap (already found in planning); freezes the consumed contract with CI running a real consumer against the types;
establishes the run recipe a demo needs.

## Part 3 — Explicitly OUT of scope (recorded)
- Any POST/mutation from the UI (run triggering is a later, separately-planned slice).
- Exposure-family runs in the list (permission family differs; recorded follow-up).
- Dashboards/charts/aggregation views; market-data/portfolio/reference screens; result export/download.
- Real SSO/OIDC (P6+, AD-007); any client-side entitlement logic.
- Backend CORS configuration; production frontend hosting/deployment topology.
- OpenAPI codegen; state-management/UI-kit dependencies; a total-count/last-page pagination affordance.

## Part 4 — Open decisions (OQ-FE-1-1…8) — **APPROVED / RATIFIED by the user (2026-07-07, the plan-commit gate)**
**Status: RATIFIED.** The eight defaults below are fixed inputs to the FE-1 implementation. *(The original recommendations are retained verbatim.)*
- **OQ-FE-1-1 — recommend APPROVE.** Slice scope = the two read-only screens + the one additive list endpoint; no migration; no new permission/audit code. (OD-FE-1-A/B.)
- **OQ-FE-1-2 — recommend APPROVE.** `GET /risk/runs` as specified (four RISK run_types; `risk.view`; fail-closed filters; capped deterministic pagination; no audit event on reads; exposure runs excluded as a recorded follow-up). (OD-FE-1-C.)
- **OQ-FE-1-3 — recommend APPROVE.** The dev-session posture: header-shim session form + permanent DEV banner; enforcement stays server-side; SSO unchanged at P6+. (OD-FE-1-D.)
- **OQ-FE-1-4 — recommend APPROVE.** Vite dev proxy; NO backend CORS change. (OD-FE-1-E.)
- **OQ-FE-1-5 — recommend APPROVE.** `react-router-dom` as the single new runtime dependency (deep-linkable run URLs). (OD-FE-1-F.)
- **OQ-FE-1-6 — recommend APPROVE.** Hand-written typed client; no codegen toolchain in v1. (OD-FE-1-G.)
- **OQ-FE-1-7 — recommend APPROVE.** Decimal values displayed as exact strings verbatim — never converted to floats anywhere in the frontend. (OD-FE-1-G.)
- **OQ-FE-1-8 — recommend APPROVE.** The test bar of OD-FE-1-H (frontend component tests + backend list-endpoint tests incl. tenant separation and 403) as the slice's definition of done, inside the existing CI jobs.

## Part 5 — Planning review (single-pass, 8-lens)

| Lens | Conclusion |
|---|---|
| Chief-Architect | The slice is correctly thin: one read endpoint + a viewer. The riskiest surface is scope creep toward "just one chart" — Part 3 fences it. **Folded:** deterministic pagination tie-break (`created_at DESC, run_id`). |
| Security/Tenancy | No new enforcement surface; the UI must not LOOK like one — the banner + "session" vocabulary folded into OD-FE-1-D; `sessionStorage` (not `localStorage`) so a closed tab drops the dev identity. 401/403 rendered honestly. |
| Governance/Audit | Reads stay unaudited (the standing GET precedent) — no new audit code; `risk.view` reused; zero permission mints. The FAILED-run screen is the `failure_reason` column's designed first consumer. |
| Data-Contract | Decimal-as-string end-to-end pinned as an OQ (the PreciseDecimal contract would be silently destroyed by one `Number()`); DTO types hand-mirrored and CONSUMED by CI. |
| Lineage/DQ | Run detail shows provenance ids verbatim (snapshot/model/code/environment) — display-only; no lineage traversal UI in v1 (a later slice if wanted). |
| Ops/CI | No new CI job; both existing jobs gain real content. The dev proxy keeps prod-shaped config out of the backend. |
| Test-Quality | The list endpoint gets the same two-tenant separation + 403 proofs every read surface has; frontend tests assert the banner and the FAILED rendering so the honesty affordances can't silently vanish. |
| Simplicity | One dependency added, justified; codegen/state/UI kits refused with revisit criteria. The endpoint returns items-only (no COUNT) — the cheapest honest pagination. |

## Part 6 — FE-1 implementation readiness gate
Implementation-ready once OQ-FE-1-1…8 are ratified. Build contract = `fe_1_implementation_plan.md`.
**FE-1 planning implements nothing.**
