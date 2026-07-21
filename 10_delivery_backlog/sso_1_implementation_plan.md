# SSO-1 Implementation Plan — real identity (OIDC / AD-007), Wave-9 slice 3

Companion to `sso_1_decision_record.md` (RATIFIED 2026-07-21, OQ-SSO-1-1..4). One commit per step; `make check` green at each; the 4-finder adversarial review after the last impl step; closeout after CI-green + user merge. **NO migration, NO new governed number/code/permission/role, NO `audit/service.py` touch.**

## Step 0 — Verifier pass (V1–V5) — RAN 2026-07-21, folded (see decision record Part 5)
All five confirmed. Load-bearing folds now baked in below: **(V2)** the resolve flow sets tenant context to the claimed tenant before the `app_user` lookup; `get_principal` takes a per-request-cached `get_db`. **(V4)** no Python audit gate exists — pin only, don't add one. **(V5)** the guard is a **standalone function at app STARTUP (lifespan), never at import** — a constructor/import-time validator would explode CI at collection. *(No commit — reconnaissance.)*

## Step 1 — Config surface + the fail-closed guard  (`config.py` + `main.py` lifespan)
Add the OIDC fields (OD-B): `auth_mode` (default `"oidc"`), `oidc_issuer/audience/jwks_uri/algorithms`, `oidc_tenant_claim`/`oidc_subject_claim`, `oidc_require_mfa`/`oidc_acr_values`. Add a **standalone `validate_auth_config(settings)` function** (NOT a `model_validator`, NOT at import — V5) enforcing: `dev_header` ⇒ `app_env == "local"` (else raise), `oidc` ⇒ `oidc_issuer` set (else raise). Call it from a **FastAPI lifespan** added to `main.py` (fires on a real `uvicorn` boot; plain-`TestClient` tests never trigger it) + a `WARNING` log when `dev_header` is active. Update `.env.example` (documented keys, no secrets). Unit-test `validate_auth_config` directly (both rejection branches + both happy paths — they fire on no existing config, V5).
**Commit:** `SSO-1 step 1: OIDC config surface + fail-closed auth_mode guard (lifespan)`

## Step 2 — The resource-server verifier  (new `apps/backend/src/irp_backend/auth.py`)
Add `pyjwt` + `cryptography`: a `>=` floor in `apps/backend/pyproject.toml` AND an exact `==` pin in `requirements-dev.txt` (V4 — both places, matching fastapi/pydantic). A `TokenVerifier` with a swappable signing-key source (`PyJWKClient` in prod; an injected public key in tests): `verify(token) -> Claims` doing signature + **explicit `algorithms=["RS256"]` allow-list (never `alg=none`, never HS/RS confusion)** + `iss`/`aud`/`exp`/`nbf` + required-claim checks + the optional MFA (`acr`/`amr`) check (OD-G); raising a typed `TokenError` on any failure; fail-closed on JWKS fetch error (never fail-open). Pure, no DB. Full unit battery (valid round-trip; tampered sig; `alg=none` rejected; wrong `iss`; wrong `aud`; expired; missing `sub`/tenant claim; MFA-required-but-absent) with locally-signed RS256 keys (OD-D).
**Commit:** `SSO-1 step 2: OAuth2 resource-server JWT verifier (PyJWT, locally-signed test keys)`

## Step 3 — Wire the verifier into `get_principal` (the dispatcher + claim→app_user resolution)  (`deps.py`)
`get_principal` dispatches on `settings.auth_mode`: `dev_header` → the existing header read (verbatim, OD-E); `oidc` → verify the bearer token, set `app.current_tenant` to the claimed tenant, look up `AppUser` by `(tenant, external_subject=sub, is_active)` (OD-C), build `Principal(user_id=app_user.id, tenant_id=app_user.tenant_id)`; 401 on any verify failure or unknown/inactive subject or tenant mismatch. Update the module docstring (the shim is now one branch behind a guard). A `WARNING` log on `dev_header` startup.
**Commit:** `SSO-1 step 3: get_principal OIDC dispatcher + verified claim→app_user resolution`

## Step 4 — Test-suite migration (shared `conftest.py` + new OIDC endpoint tests)
Add `apps/backend/tests/conftest.py`: an autouse fixture pinning the suite to `auth_mode="dev_header"` (so the ~42 header-based files pass unchanged, OD-E) + a shared `bearer_headers(principal, key)` helper. NEW `test_oidc_auth.py`: end-to-end through the app in `oidc` mode with a locally-signed token — allow-200, tampered/expired/wrong-iss/wrong-aud → 401, unknown-`sub` → 401, tenant-mismatch → 401, `require_permission` still 403 for a real-but-unentitled user. Rework the two shim-behaviour files (`test_entitlement_dependency.py`, `test_tenant_session.py`) to assert both modes explicitly.
**Commit:** `SSO-1 step 4: shared auth conftest + OIDC-mode endpoint test battery`

## Step 5 — Documented Keycloak realm + demo external_subject seed (closes OD-048)
Add a `docker-compose` Keycloak service + a committed realm export (issuer/client/a demo user whose `sub` matches a seeded `external_subject`); a short `docs/` runbook (dev login against Keycloak). Set `external_subject` on the demo user(s) in the seed so the documented `sub` resolves (OD-F — a column set, **no new run, counts UNCHANGED**). Verify the full-PG demo suite stays green. **Not a CI dependency** (CI stays on locally-signed keys).
**Commit:** `SSO-1 step 5: documented Keycloak dev realm + demo external_subject seed (closes OD-048)`

## Step 6 — Docs & status stamps
`foundational_adrs.md` AD-007 — mark the OIDC resource-server realized at SSO-1 (OD-048 closed); `p1a0_decision_record.md` DR-P1A0-3 — the shim cutover note (now guarded, `dev_header`+local only); `03_architecture`/`06_security` OD-024 pointer as applicable; `delivery_roadmap.md` SSO-1 row → DONE; `current_state.md` banner; the decision record → CLOSED.
**Commit:** `SSO-1 step 6: doc status stamps (AD-007 realized, DR-P1A0-3 cutover, roadmap DONE)`

## Step 7 — `make check` + full-PG + push, then the 4-finder review
`make check` green; the full-PG demo battery green (external_subject seeded); push `sso-1-impl`; hand the compare link to the USER. Then the **4-finder adversarial review** (doctrine / security / correctness-CI / a Fable numeric-or-logic lens) — security lens weighted here (it IS the auth boundary): confirm no auth bypass (no route reachable without a verified principal in `oidc` mode), the `dev_header` guard cannot be tricked, the tenant cross-check can't be spoofed, PyJWT is used with an explicit algorithm allow-list (no `alg=none`, no HS/RS confusion), the production audit is clean, and all six hard invariants hold. Fold, re-run gates, closeout.

## Risks / watch-items (seeded for the finders)
- **`alg` confusion / `alg=none`** — the verifier MUST pin `oidc_algorithms` (RS256) and never accept a symmetric or `none` alg. Explicit finder target.
- **RLS visibility of `app_user` at resolution time (V2)** — get the "set claimed-tenant context, then look up" ordering right, or the lookup false-denies (hidden row) / the fix must not open a cross-tenant read.
- **`auth_mode` default leakage (V5)** — a deployment or CI step that leaves `dev_header` reachable is a security hole; the guard + a test must make it impossible.
- **New production runtime dep (PyJWT/cryptography)** — first non-dev advisory surface since FE-2; pin + audit + close-register note.
- **JWKS network fetch in prod** — cache + timeout + a clear failure mode (fail-closed 401/503, never fail-open).
