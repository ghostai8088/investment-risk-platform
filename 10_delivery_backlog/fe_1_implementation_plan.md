# FE-1 Implementation Plan — Read-Only "Risk Runs & Results" View

> Build contract for the FE-1 slice. Decisions: `fe_1_decision_record.md` (OD-FE-1-A…H; implementation gated on
> the OQ-FE-1-1…8 ratification). READ-ONLY; ONE additive backend endpoint; NO migration; NO new
> permission/audit code. Planned against HEAD `ee3c581`.

## Step 1 — Backend: the list-runs endpoint (the slice's only backend change)
1. **`packages/shared-python/src/irp_shared/risk/queries.py`** (NEW, read-only):
   `RISK_RUN_TYPES = frozenset({RUN_TYPE_SENSITIVITY, RUN_TYPE_FACTOR_EXPOSURE, RUN_TYPE_COVARIANCE, RUN_TYPE_VAR})`
   (imported from the four services' constants — no string duplication) and
   `list_risk_runs(session, *, acting_tenant, run_type=None, status=None, limit=50, offset=0) -> list[CalculationRun]`:
   - refuse (raise `RiskRunQueryError`) an unknown `run_type` (outside the four) or unknown `status`
     (outside `RunStatus` values) — fail closed, never a silently-empty page;
   - clamp nothing silently: `limit` outside 1..200 or `offset < 0` also refuse;
   - `WHERE tenant_id = :acting_tenant AND run_type IN (...)` + optional filters,
     `ORDER BY created_at DESC, run_id`, `LIMIT/OFFSET`. (RLS is the enforcement; the tenant predicate is the
     belt-and-braces house pattern.)
2. **`apps/backend/src/irp_backend/api/risk.py`**: `GET /risk/runs` (placed BEFORE the per-family
   `…/runs/{run_id}` routes read it — FastAPI matches in registration order; verify no path shadowing) →
   `RiskRunListOut{items: list[RiskRunSummaryOut]}`; `RiskRunSummaryOut` = run_id, run_type, status,
   created_at, completed_at, initiated_by, input_snapshot_id, model_version_id, code_version, environment_id,
   failure_reason. Gate `_require_view` (`risk.view`); `RiskRunQueryError` → 422 via the existing
   `deps.map_refusal` wiring. NO audit emission (read).
3. **Tests** (`apps/backend` + shared suites, the existing files' pattern):
   - two-tenant separation (tenant A never sees B's runs — via the endpoint, both empty-filter and filtered);
   - the four-run_type fence (an exposure/MARKET_VALUE run in the table does NOT appear; `run_type=EXPOSURE…`
     query → 422);
   - unknown status 422; limit/offset bounds 422; pagination determinism (fixed created_at ties → run_id order);
   - 403 without `risk.view`; 401 without principal; `failure_reason` present on a FAILED run in the list.

## Step 2 — Frontend: session + client
4. **`apps/frontend/src/api/client.ts`**: `apiFetch(path, session)` — injects `X-User-Id`/`X-Tenant-Id`, maps
   401/403/422/5xx to typed errors. **`src/api/types.ts`**: hand-written interfaces for `RiskRunSummary`,
   `RiskRunList`, and the four per-family run-detail DTOs (rows embedded). All decimal fields typed `string`.
5. **Session handling**: `src/session.ts` — `{userId, tenantId}` in `sessionStorage`; a session form (plain
   inputs, "Start dev session" / "End session"); NO password field, NO "login" vocabulary.
6. **DEV banner**: permanent, non-dismissable, rendered above every view: "DEV SESSION — identity is unverified;
   not a security boundary until SSO (AD-007)".

## Step 3 — Frontend: the two screens
7. **Routing** (`react-router-dom`, the slice's single new runtime dep): `/` → runs list; `/runs/:runId` → run
   detail. Unknown routes → list.
8. **Runs list** (`src/views/RunsList.tsx`): fetch `GET /risk/runs` with run_type/status filter selects +
   prev/next offset paging; columns per OD-FE-1-B; `failure_reason` truncated with full text on the detail;
   row click → `/runs/{run_id}`; empty/loading/error states explicit.
9. **Run detail** (`src/views/RunDetail.tsx`): needs the family to pick the endpoint — the list row carries
   `run_type`; on deep-link WITHOUT state, resolve by trying the mapped endpoint from a
   `run_type → /risk/{family}/runs/{id}` map after first fetching the summary via `GET /risk/runs`…
   **Simpler v1 (do this):** deep-links carry the family in the path — route is `/runs/:family/:runId`
   (family ∈ sensitivities|factor-exposures|covariances|vars), so ONE fetch, no probing. Provenance block
   (verbatim ids, monospace); status badge; FAILED ⇒ `failure_reason` rendered prominently and verbatim;
   result-rows table per family (column sets hand-defined per DTO); decimal strings rendered VERBATIM.
10. **Styling**: minimal hand-written CSS (`src/styles.css`) — readable table, status badge colors, banner. No
    framework.

## Step 4 — Tests (frontend, vitest + mocked fetch)
11. RunsList: renders rows from a mocked page; filters change the query string; pagination offsets; error and
    empty states; a FAILED row shows truncated reason.
12. RunDetail ×2 families minimum (sensitivities + vars — the scalar-summary and multi-row shapes): provenance
    verbatim; FAILED prominence; decimal strings displayed EXACTLY as sent (assert e.g. `"123.400000"` survives
    untouched — the anti-`Number()` fence).
13. Session/banner: banner always present (with and without a session); no-session state renders the form and
    performs NO fetch; 403 renders the not-entitled state.
14. Client: header injection; error mapping.

## Step 5 — Docs + hygiene
15. `apps/frontend/README.md`: the dev run recipe (backend `uvicorn` + `npm run dev` + the proxy note + a seeded
    session example); the READ-ONLY + dev-shim posture stated.
16. `09_compliance_controls/control_matrix_skeleton.md`: no control changes (read-only slice) — verify, don't
    invent. `docs/project_memory/*` untouched until closeout.
17. Gates: `make check` (backend) + `npm ci && npm run -w apps/frontend lint/typecheck/test/build` + the full-PG
    pytest run (schema reset first) + `alembic check` (must be a no-op — NO migration in this slice) — then the
    independent adversarial review, fold, and HOLD for the Tier-2 commit approval.

## Out of scope (fenced in the decision record, Part 3)
UI mutations; exposure runs; charts/dashboards; other domain screens; SSO; CORS; codegen; state/UI-kit deps;
total-count pagination; lineage traversal UI.

## Definition of done
Both CI jobs green with the new content; the backend suite proves tenant separation + the run_type fence + 403;
the frontend suite proves the banner, FAILED rendering, and decimal-verbatim display; the two screens work
end-to-end against a locally seeded DB via the documented recipe.
