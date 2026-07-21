# Session Log: 21-07-2026 12:44 - SSO-1 & FE-3 (identity + product UI)

## Quick Reference (for AI scanning)
**Confidence keywords:** SSO-1, OIDC, AD-007, resource-server, PyJWT, JWKS, RS256, dev_header, auth_mode, validate_auth_config, lifespan-guard, RLS-canonicalization, tenant_id::text, set_tenant_context, external_subject, demo-auditor, OD-048, Keycloak, FE-3, governance-walk, GovernedValue, Pane, ValidationBadge, useApiGet, useModelIndex, useModelValidations, verbatim, decimal-contract, OnlyCountsAreNumbers, API-1b, partial-entitlement, WCAG, 4-finder-review, PR#86, CI#466, fe-3, Wave-9
**Projects:** investment-risk-platform (nested at ~/Projects/investment_risk_platform/investment-risk-platform)
**Outcome:** SSO-1 (real OIDC identity) fully closed + merged (PR #86, CI #466); the entire FE-3 product UI (six-step governance-narrative walk) built, 4-finder-reviewed (zero HIGH), and pushed on branch `fe-3` awaiting user merge + closeout.

## Decisions Made

### SSO-1 (Wave-9 slice 3) — ratified OQ-SSO-1-1..4 (all as recommended)
- **Verification model:** the API is an OAuth2 **resource server** — validates `Authorization: Bearer <JWT>` against the issuer JWKS (stateless). Rejected BFF session cookies.
- **Local/test IdP:** locally-signed RSA test keys now (no CI container); Keycloak realm documented + docker-compose-wired (closes OD-048). Rejected Keycloak-in-CI.
- **Tenant resolution:** verified tenant claim cross-checked against the `app_user` record via `(tenant, external_subject)` lookup. Rejected subject-only lookup (external_subject is unique only per-tenant).
- **FE scope:** backend-only; the SPA OIDC auth-code+PKCE login deferred to FE-3b.
- Config guard is a **standalone `validate_auth_config` called from the FastAPI lifespan, NEVER at import** — the `settings = Settings()` singleton is built at import, so an import-time validator would explode CI at collection.
- `Principal.user_id` MUST be `app_user.id` (what `has_permission` joins), NOT the raw `sub`.
- NO migration (the `external_subject` column pre-existed); no new governed number/code/permission/role; `audit/service.py` FROZEN + never imported.

### FE-3 (Wave-9 slice 4) — ratified OQ-FE-3-1..3 (all as recommended)
- **IA spine:** the **governance-narrative walk** — the demo tenant's own lifecycle (capture → exposures → governed numbers → backtest evidence → validation status → disclosed limitations), with provenance/validation/limitations first-class on every number ("verifiability as the product"). Rejected: portfolio-first workspace; enhanced run browser.
- **Auth:** build on the preserved `dev_header` client path; defer the browser OIDC PKCE login to a bounded **FE-3b**.
- **Depth:** focused vertical on `DEMO-GLOBAL`, full depth (not broad-shallow).
- **Step-0 finding → scope adjustment:** no demo principal could READ the whole walk (registrar/validator are SoD-split for WRITE duties; even `auditor_3l` template lacks snapshot/position/valuation.view). Added a read-only 3L **`demo-auditor`** viewer (`external_subject="demo-auditor"`, `_AUDITOR_PERMS`) to the demo seed — reusing existing `*.view` codes only. So FE-3 = FE + one additive demo-seed change; NO migration/new-code.
- **Class-C VaR gap:** VaR/active-risk have no "latest for portfolio P" read (deferred to API-1b, needs `calculation_run.scope_portfolio_id`). FE-3 shows VaR as the real seeded run SERIES with the gap stated honestly — never a faked resolver.
- Register item (NOT FE-3's fix): the shared `auditor_3l` ROLE_TEMPLATE lacks snapshot/position/valuation.view — an arguable governance gap (an auditor can't verify a snapshot), flagged for the Wave-9 close register.

## Key Learnings
- **RLS canonicalization (the SSO-1 HIGH, generalizable):** any code path that arms a Postgres RLS tenant GUC from an EXTERNALLY-controlled string must canonicalize it first (`str(uuid.UUID(...))`). The `tenant_isolation` policy compares `tenant_id::text` (PG renders uuid lowercase-hyphenated) against the RAW `app.current_tenant` GUC — a valid but non-canonical UUID claim (uppercase/.NET GUID) is RLS-HIDDEN → a legitimate user gets a false-deny 401. `_principal_from_token` is the FIRST caller ever to feed `set_tenant_context` a raw external string; every prior caller sourced tenant from a DB round-trip (always canonical). SQLite CANNOT catch this class (RLS is a no-op there) → a PG-tier regression test under a constrained `irp_app` role is required.
- **Adding a `Header`/`Depends` param to a shared FastAPI dependency drifts the WHOLE committed OpenAPI schema** — `get_principal`'s new `authorization` Header stamped 231 param blocks into `openapi.json`, breaking FE-2's own `api-type-drift` CI job. Always regenerate (`make gen-api`).
- **Exhaustive compile-time guards must extend as new decimal DTOs get wired** (the FE-2 lesson, recurring at the capture tier): FE-3 is the first slice to render `PositionOut`/`ValuationOut` decimals, so they had to join `OnlyCountsAreNumbers` (with `record_version`, a bitemporal version int, added to `CountKey`).
- **On a verifiability UI, no-fabricated-data is existential:** never a fake "✓ reproduces" mark, never a fabricated domain-gated verdict, never a synthetic "latest" from a real series. The FE structurally prevents all three (the verify mark is unreachable — no step passes `snapshotVerified`/`snapshotId`).
- **The demo pipeline uses the worker/tenant-context path (`run_in_tenant`), not the HTTP `require_permission` gate** — so a missing demo-principal HTTP grant is invisible to the full-PG battery. The FE calls HTTP reads AS a principal → needs the grants (found via Step-0 verifier: booted the backend + curled every read).
- **Route restructuring breaks old absolute links:** moving RunsList from `/` to `/runs` left RunDetail's "back to runs" `/` links pointing at the new walk overview.
- Pydantic `BaseSettings` singleton is built at import; test autouse `conftest.py` can mutate `settings.auth_mode` (not frozen). `.at(-1)` needs es2022 lib (use `arr[arr.length-1]`); zsh does NOT word-split unquoted vars (curl `-H` must be inline, not via `$H`).

## Solutions & Fixes

### SSO-1 (2 HIGH + 4 MED + LOWs, ALL folded from the 4-finder review)
- **HIGH-1 RLS false-deny:** canonicalize `str(uuid.UUID(claims.tenant))` in `_principal_from_token` before `set_tenant_context` + the WHERE; NEW `test_oidc_tenant_canonicalization_pg.py` under constrained `irp_app` + a CI step.
- **HIGH-2 CI drift:** regenerated + committed `openapi.json` + FE types.
- **MED:** require `OIDC_AUDIENCE` in oidc mode (confused-deputy); `_check_mfa` filters `amr` to hashable str (nested-list 500→deny); `validate_auth_config` rejects `require_mfa` without `acr_values` (fail-fast at boot); the RLS coverage gap.
- **LOW:** dev_header per-request `app_env=='local'` backstop; clock-skew `leeway=60s` (OD-A claimed it, was 0 — expiry tests moved beyond leeway); JWKS/discovery outage → 503 not 500; tests for lifespan/build_verifier/discovery/amr/demo-seed.

### FE-3 (2 MED + 6 LOW folded from the 4-finder review; ZERO HIGH)
- **MED:** RunDetail "back to runs" `/`→`/runs`; `useModelValidations` `.find`→latest-validated-version (`filter` + `[len-1]`).
- **LOW:** extend the exhaustive decimal guard to `PositionOut`/`ValuationOut`; WCAG 2.4.7 skip-link focus ring (`main.shell-content:focus-visible`, not `outline:none`); limitation lists index keys; 3 honesty label nits (numbers blurb said "ES" — it's in Backtest; VaR note now says "across all books"; WalkStep stale placeholder comment).

### Commands / gates that worked
- Local PG: reset `DROP SCHEMA public CASCADE; CREATE SCHEMA public; GRANT USAGE ON SCHEMA public TO PUBLIC; GRANT CREATE ON SCHEMA public TO PUBLIC;` → `DATABASE_URL=postgresql+psycopg://irp:irp@localhost:5432/irp .venv/bin/alembic upgrade head` → `IRP_TEST_DATABASE_URL=...` `pytest packages/shared-python/tests -k "_pg"`. Container `irp_pg_local`, creds irp/irp/irp.
- Boot backend for FE verification: `AUTH_MODE=dev_header APP_ENV=local DATABASE_URL=... .venv/bin/uvicorn irp_backend.main:app --port 8137`; curl reads with `-H "X-User-Id: <app_user.id>" -H "X-Tenant-Id: 8c3193a6-1c9c-5353-bbe1-ab8716e986a9"`.
- `make check` (Python, ~1778 pass), `make fe-check` (97 FE tests + build), `make gen-api-check` (openapi drift), `make gen-api` (regenerate).
- DEMO_TENANT_ID = `8c3193a6-1c9c-5353-bbe1-ab8716e986a9`; demo principals: demo-validator (model.validate+model.inventory.view), demo-registrar (risk.run/view+perf.run/view), demo-auditor (the 11-code read-only viewer).

## Files Modified & Pending

### SSO-1 (merged, PR #86 = `422c164`, CI green #466)
- `apps/backend/src/irp_backend/config.py`: `auth_mode` + oidc fields + `validate_auth_config` (audience + mfa-pairing + dev_header-local guards).
- `apps/backend/src/irp_backend/main.py`: lifespan calling the guard.
- `apps/backend/src/irp_backend/auth.py` (NEW): `TokenVerifier` (PyJWT/JWKS, RS256-only, leeway, MFA), `build_verifier`/`get_verifier`, `_discover_jwks_uri`.
- `apps/backend/src/irp_backend/deps.py`: `get_principal` dispatcher + `_principal_from_headers`/`_principal_from_token` (canonicalization, 503-on-discovery).
- `apps/backend/tests/`: `conftest.py` (autouse dev_header), `test_auth_config.py`, `test_auth_verifier.py`, `test_oidc_auth.py`, `test_lifespan_guard.py`.
- `packages/shared-python/tests/`: `test_oidc_tenant_canonicalization_pg.py`, `test_demo_external_subject.py`.
- `packages/shared-python/src/irp_shared/demo/campaign.py`: `external_subject` on demo principals + the `demo-auditor` viewer (`_AUDITOR_PERMS`).
- `apps/backend/pyproject.toml` + `requirements-dev.txt`: pyjwt 2.13.0 + cryptography 49.0.0.
- `infra/keycloak/` (NEW): `irp-local-realm.json` + `README.md`; `docker-compose.yml` keycloak service (profile `oidc`); `.env.example` OIDC keys.
- Docs: `sso_1_decision_record.md` (CLOSED) + `_implementation_plan.md`; AD-007/OD-048 in `foundational_adrs.md`; DR-P1A0-3 cutover in `p1a0_decision_record.md`; roadmap DONE row; `current_state.md` banner.

### FE-3 (pushed on `fe-3`, 11 commits, tip `49ed1e4`; NOT yet merged)
- `apps/frontend/src/`: NEW `walk/{steps,useDemoPortfolio,useModelIndex,useModelValidations}.ts`, `components/{AppShell,Pane,GovernedValue,ValidationBadge}.tsx`, `api/{format,useApiGet}.ts`, `views/walk/{WalkOverview,WalkStep,CaptureStep,ExposuresStep,NumbersStep,BacktestStep,ValidationStep,LimitationsStep}.tsx` (+ tests). MODIFIED `App.tsx` (nested routes: walk at `/`, run browser at `/runs`), `api/types.ts` (10 generated-DTO aliases), `api/decimal-contract.ts` (guard + CountKey), `views/RunDetail.tsx` (verbatim dedup + link fix), `vite.config.ts` (proxy prefixes), `styles.css`.
- `packages/shared-python/src/irp_shared/demo/campaign.py` (the demo-auditor — the one backend touch).
- Docs: `fe_3_decision_record.md` (Part 6 = review outcome) + `_implementation_plan.md`.

### Memory updated
`sso-1-planning-state.md` (NEW), `ui-read-surface-state.md` (F1-F4 all discharged), `delivery-roadmap-state.md`, `MEMORY.md`. (FE-3 memory NOT yet written — do at closeout.)

## Pending Tasks
1. **User merges `sso-1-closeout`** (if not done) then **`fe-3`**; wait for CI green.
2. **FE-3 closeout** (after merge + CI): roadmap SSO-1... wait, FE-3 row → DONE with PR#/CI#; `current_state.md` banner; `fe_3_decision_record.md` → CLOSED; write `fe-3-planning-state.md` memory + update `MEMORY.md`/`ui-read-surface-state`/`delivery-roadmap-state`. This CLOSES Wave 9.
3. **Wave-9 close review** (mandatory rule-2 re-baseline across API-1 → FE-2 → SSO-1 → FE-3). Close-register carry-ins: FE-2 `@redocly` dev-tree advisory; SSO-1 pyjwt/cryptography advisory surface (candidate pip-audit gate); BT-3 D-F4 reword; the FE-3 `auditor_3l`-template read-gap.
4. Named fast-follows: **API-1b** (Class-C VaR/active-risk reads + `scope_portfolio_id`); **FE-3b** (the SPA OIDC PKCE login).

## Quick Resume Context
SSO-1 is fully closed and merged (real OIDC identity boundary; PR #86, CI #466). FE-3 (the entire six-step governance-narrative product walk over DEMO-GLOBAL) is built, 4-finder-reviewed with zero HIGH (2 MED + 6 LOW folded), all gates green, and pushed on branch `fe-3` (tip `49ed1e4`) awaiting the user's merge. The immediate next step after merge + CI-green is the mechanical FE-3 closeout (roadmap DONE, current_state, decision-record CLOSED, memory), which closes Wave 9 and tees up the mandatory Wave-9 close review.

---

## Raw Session Log (condensed narrative)

This session continued from a `/compress` + `/compact` of the prior API-1/FE-2 session. It executed two full Wave-9 slices end-to-end under the standing autonomy grant (plan → OQ-ratify → one-commit-per-step → make-check/fe-check gate → 4-finder adversarial review → fold → push; USER opens/merges PRs).

**SSO-1 arc:** User said "proceed" → scouted the dev-header shim (single chokepoint `deps.py:get_principal`, everything behind it real). Surfaced 4 forks via AskUserQuestion; user ratified all as recommended. Wrote decision record + plan; ran a Step-0 verifier subagent (V1-V5 confirmed: `Principal.user_id`=app_user.id; RLS visibility mechanics; no test overrides get_principal; no Python audit gate exists; the import-time-explosion flag → lifespan guard). Implemented steps 1-6 (config guard, verifier, dispatcher+conftest, oidc tests, Keycloak realm + demo external_subject, doc stamps), each committed with make-check green. Ran `make check` (1778) + full-PG battery (demo 101 runs). 4-finder review (2×Opus + Sonnet + Fable) found 2 HIGH (RLS canonicalization false-deny — live-reproduced on PG; OpenAPI drift from the new authorization header) + 4 MED + LOWs, all folded. Full-PG battery re-run green; pushed `sso-1`; user merged (PR #86); monitored CI #466 to green (fought a zsh `read-only variable: status` monitor-script bug + used jq); ran the closeout on `sso-1-closeout` (roadmap DONE, current_state, decision-record CLOSED, memory). Confirmed `fe-2-closeout` had been merged (PR #85) and `sso-1` (PR #86) merged cleanly on top.

**FE-3 arc:** User "proceed" (opus[1m]) → scouted the FE + API-1 read surface + demo data + auth story. Surfaced 3 forks (IA spine with ASCII previews, auth scope, depth) via AskUserQuestion; user ratified all as recommended (governance walk / defer OIDC to FE-3b / DEMO-GLOBAL vertical). Wrote decision record + plan on branch `fe-3` (from origin/main). Step-0 verifier (done by hand): reset+seeded the demo, booted the backend on dev_header, curled every walk read — all return real DEMO-GLOBAL data, decimals are strings. **Decisive finding:** no principal can READ the whole walk → added the read-only `demo-auditor` viewer to the demo seed (Step 0.5), folded into the decision record scope. Then built the walk over 6 committed steps: (1) shell + nav + routes + vite proxy; (2) primitives GovernedValue/Pane/ValidationBadge/useApiGet/verbatim; (3) Capture + Exposures; (4) Governed numbers — the star, with useModelIndex powering inline validation/limitations and VaR shown as the honest run series; (5) Backtest + Validation (useModelValidations chained reads → findings+evidence) + Limitations; (6) WCAG skip-link + a11y. Each step: `make fe-check` green (67→84→88→90→96→97 tests). Pushed `fe-3`; ran all gates (fe-check 97, make check, gen-api-check clean). 4-finder review (2×Opus decimal+honesty, 2×Sonnet degradation+correctness/a11y): ZERO HIGH — the decimal contract and the three existential honesty defects proven clean/prevented; 2 MED (RunDetail links, first-vs-latest validated version) + 6 LOW folded. Pushed. FE-3 awaiting user merge + closeout.

**Environment:** repo nested at `investment-risk-platform/`, git origin HTTPS (plain push works), `gh` not installed (use REST API), local PG container `irp_pg_local`. Standing rules honored: last sentence of each reply = model+effort rec; plain-language gate briefings; concise prose; clickable PR links; fixtures economically plausible.
