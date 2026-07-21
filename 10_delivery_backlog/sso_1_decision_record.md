# SSO-1 Decision Record — real identity (OIDC / AD-007), Wave-9 slice 3

| | |
|---|---|
| **Status** | **RATIFIED 2026-07-21 (OQ-SSO-1-1/2/3/4, user answers). Implementation follows.** Wave-9 slice 3 (roadmap Part 2.12), following API-1 + FE-2 (both DONE 2026-07-21). The last of the four read-surface findings (F4). The four forks decided **as recommended**: **(1)** the API becomes an OAuth2 **resource server** validating `Authorization: Bearer <JWT>` against the issuer JWKS (stateless — matches AD-007's "short-lived signed tokens", no server session store); **(2)** local-dev/test uses a **locally-signed RSA keypair** (no running IdP required in CI) with a containerized Keycloak realm wired + documented (closing OD-048) — validation ships now, the container is documented not CI-required; **(3)** tenant resolves from a **verified tenant claim cross-checked against the `app_user` record** (`(tenant, external_subject)` lookup — deny on any mismatch); **(4)** **backend-only** — the SPA OIDC auth-code+PKCE login flow is deferred to FE-3. **NO migration** (`app_user.external_subject` already exists, `models.py:31`); **NO new governed number/code/permission/role** (hard invariant — the enforcement behind the shim is untouched); **NO change to `audit/service.py`** (FROZEN). Bounded identity-swap at ONE chokepoint (`deps.py:50-56`). |
| **Premise** | Read-surface assessment F4 (`ui_read_surface_assessment.md`, roadmap Part 2.12 F4): identity is the self-labeled **DEV PLACEHOLDER header shim** — `get_principal` (`deps.py:50-56`) reads `X-User-Id` / `X-Tenant-Id` with **zero verification**; the tenant claim is "unverified and not a security boundary until SSO" (deps.py:6-7, DR-P1A0-3). Everything *behind* the shim is already real: `has_permission` deny-by-default RBAC (`entitlement/service.py:37`), the `app.current_tenant` → FORCE-RLS tenant fence (`db/tenant.py:34`), and — decisively — `app_user.external_subject` (`models.py:31`) is **already the OIDC-subject binding slot** (unique `(tenant_id, external_subject)`, `models.py:27`). AD-007 (`03_architecture/foundational_adrs.md:80-89`) governs: OIDC primary, MFA enforced, short-lived signed tokens, containerized local-dev IdP; DR-P1A0-3 (`p1a0_decision_record.md:67-80`) authorized the shim "until real SSO in P9 — production must use OIDC/SAML verified tenant claims before external users or client data." SSO-1 is that swap: **prove identity for real, feed the proven identity into the enforcement that already works.** |

## Part 1 — Grounding (the chokepoint + the receiving surface, file:line)

The reconnaissance (2026-07-21) confirmed the swap is localized to **one function**; every downstream consumer is already built to receive a real principal.

### 1.1 Where identity enters today (the single chokepoint)

- `get_principal(x_user_id, x_tenant_id)` — **`apps/backend/src/irp_backend/deps.py:50-56`**. FastAPI `Header(default=None)` maps to `X-User-Id`/`X-Tenant-Id`; raises 401 only if a header is *absent*; **no signature, no issuer, no expiry — the caller simply asserts its identity**. This is the `get_current_user`-equivalent and the ONLY thing SSO-1 replaces.
- `get_tenant_session(principal, db)` — **deps.py:59-75**. Depends on `get_principal`, then `set_tenant_context(db, principal.tenant_id)` (the RLS bind). Unchanged by SSO-1.
- `require_permission(code)` — **deps.py:78-91**. The deny-by-default gate; runs under `get_tenant_session`, `has_permission(...) → 403`. Unchanged.
- `main.py` — **no auth middleware, no global dependency**; auth is per-router `Depends(require_permission(...))`. Health/system probes deliberately exempt. Unchanged.

### 1.2 The receiving surface — already built for a real identity

| Consumer | Location | What it expects | SSO-1 impact |
|---|---|---|---|
| `Principal(user_id, tenant_id)` dataclass | `entitlement/service.py:28-34` | an authenticated subject; docstring: "real identity arrives via SSO (AD-007)" | **unchanged** — SSO-1 builds the SAME `Principal`, from verified claims |
| `has_permission(...)` | `entitlement/service.py:37-66` | `principal.user_id` joins `UserRole.user_id` (an **`app_user.id`**, a UUID — FK `user_role.user_id → app_user.id`, `models.py:71`) | **unchanged** — but note: `user_id` MUST be the `app_user.id`, not the OIDC `sub` (see OD-C) |
| `set_tenant_context` / `app.current_tenant` RLS | `db/tenant.py:34-43`; policies in every domain migration (`USING (tenant_id::text = current_setting('app.current_tenant', true))`) | `principal.tenant_id` sets the GUC the RLS policy reads | **unchanged** — the identity→tenant→RLS chain's only mutable hop is the first (header → claim) |
| `app_user.external_subject` | `entitlement/models.py:31` (`String(255)`, nullable, unique `(tenant_id, external_subject)`) | "OIDC subject placeholder" | **the binding column** — the token `sub` maps HERE; already exists → **NO migration** |
| `Settings` | `config.py:12-17` (`BaseSettings`, `env_file=".env"`, `extra="ignore"`) | env-only, no secrets in source (BR-10) | new OIDC fields drop straight in (OD-B) |

### 1.3 The tests that authenticate (what changes, and what does NOT)

~42 backend test files send raw `X-User-Id`/`X-Tenant-Id` headers via a per-file `_headers(principal)` helper (e.g. `test_lineage_endpoint.py:70-71`); there is **no shared `conftest.py`**. Two files assert the shim's own behavior: `test_entitlement_dependency.py` (allow-200 / missing-headers-401 / unknown-user-403, `:64-86`) and `test_tenant_session.py` (RLS bind). **The minimal-churn insight (OD-E):** the header path is PRESERVED as an explicit `dev_header` auth mode, valid only under `app_env == local`. Existing tests run in `dev_header` mode and need **no per-file change** — a single new autouse `conftest.py` fixture pins the suite to `dev_header`; the OIDC path gets NEW dedicated tests that opt into `oidc` mode with locally-signed tokens.

## Part 2 — Design decisions

### OD-SSO-1-A — The verification model: OAuth2 resource-server bearer JWT (OQ-SSO-1-1, ratified)
The API becomes an OAuth2 **resource server**. A new verifier reads `Authorization: Bearer <JWT>`, validates **signature** (against the issuer JWKS, cached), **`iss`** (== configured issuer), **`aud`** (== configured audience), **`exp`/`nbf`** (with small leeway), and the **required claims** (`sub`, the tenant claim). Stateless — no server session store — matching AD-007's "short-lived signed tokens with rotation." The FE (FE-3) obtains the access token from the IdP and sends it; SSO-1 only *verifies*. **Rejected:** a BFF session-cookie model (a server-side session store + more moving parts; stronger against browser token theft but heavier and unneeded for a read-only viewer whose tokens are already short-lived).

### OD-SSO-1-B — Config surface + the fail-closed default (OD lands in `config.py`)
New `Settings` fields (env-only, BR-10 — **no secrets in source**; client secrets are the IdP's/FE's concern, the resource server needs none):
- `auth_mode: Literal["oidc", "dev_header"] = "oidc"` — **default `oidc` (fail-closed / safe-by-default)**.
- `oidc_issuer: str | None`, `oidc_audience: str | None`, `oidc_jwks_uri: str | None` (if unset, discovered from `{issuer}/.well-known/openid-configuration`), `oidc_algorithms: list[str] = ["RS256"]`.
- `oidc_tenant_claim: str = "tenant_id"` (the claim carrying the tenant UUID — configurable, since IdPs namespace claims differently), `oidc_subject_claim: str = "sub"`.
- `oidc_require_mfa: bool = False` + `oidc_acr_values`/`amr` check (OD-G).
- **Startup/validation guard:** `auth_mode == "dev_header"` is **rejected unless `app_env == "local"`** (a `model_validator` or an explicit `settings.validate_auth()` called at app construction). `auth_mode == "oidc"` with no `oidc_issuer` also fails fast. This is the cutover's teeth — the shim **cannot** run in a deployed env.

### OD-SSO-1-C — Tenant resolution: verified claim, cross-checked against the record (OQ-SSO-1-3, ratified)
The verified token carries `sub` (OIDC subject) and a tenant claim. Resolution:
1. Verify the token (OD-A) → extract `sub` and `tenant_claim`.
2. Look up **`AppUser` by `(tenant_id == tenant_claim, external_subject == sub, is_active == True)`** — a single query enforcing the cross-check by construction (the `(tenant_id, external_subject)` unique constraint guarantees ≤1 row).
3. On **no active match → 401** ("unknown identity" — deny-by-default; no JIT provisioning, OD-F). On match, build **`Principal(user_id=app_user.id, tenant_id=app_user.tenant_id)`** — note `user_id` is the **`app_user.id`** (the FK `has_permission` joins), NOT the raw `sub`. This is the one semantic difference from the dev shim, which passed `app_user.id` directly as `X-User-Id`.

**Why not subject-only lookup (the rejected alternative):** `external_subject` is unique only *per-tenant* (`uq_app_user_tenant_id` on `(tenant_id, external_subject)`), so a bare `sub` lookup is ambiguous across tenants and would need a global-uniqueness guarantee the schema does not give. The claim-cross-check is explicit, auditable, and honours the existing constraint.

**Note — this lookup runs OUTSIDE the tenant RLS session:** `app_user`/`role`/`user_role` are themselves tenant-RLS tables. Resolution happens on a plain `get_db` session with `app.current_tenant` set to the claimed tenant *first* (so the lookup can see the row), mirroring how `get_tenant_session` already arms RLS before `has_permission` reads `user_role`. The verifier sets the tenant context to the *claimed* tenant, then the lookup either finds the (tenant-scoped) active user or denies — an attacker asserting tenant B's id cannot read tenant A's users, and cannot forge a token (signature check).

### OD-SSO-1-D — Local-dev / test: locally-signed keys now, Keycloak documented (OQ-SSO-1-2, ratified)
Ship **full JWKS validation**; the local/test path uses a **locally-generated RSA keypair** — a test helper mints RS256 tokens signed by the test private key, and the verifier's JWKS source is pointed at the test public key (no network, no container in CI). A containerized **Keycloak** realm (issuer, client, a demo user whose `sub` matches a seeded `external_subject`) is **wired into `docker-compose` + documented** as the intended dev IdP, **closing OD-048** (foundational_adrs.md:161, "confirm local-dev OIDC provider choice") — but it is **not a CI dependency** (CI validates with locally-signed keys, keeping the pipeline hermetic). **Rejected:** requiring a live Keycloak in CI (realm seeding + service orchestration inside an M-sized slice, and a network dependency in the hermetic test suite).

### OD-SSO-1-E — Dev-shim cutover: gate, don't delete (the safety posture)
`get_principal` becomes a dispatcher on `settings.auth_mode`: `oidc` → the verifier (OD-A/C); `dev_header` → the existing header read (preserved verbatim). The startup guard (OD-B) makes `dev_header` **impossible outside `app_env == local`**. Keeping the shim (behind the guard) preserves ~42 tests unchanged and the local dev loop, while the guard guarantees a deployed env fails fast if misconfigured. **Rejected:** deleting the shim outright (would force a live IdP for every local run and rewrite 42 test files for no security gain — the guard already makes the shim unreachable in prod). A LOW-noise `WARNING` log on every `dev_header` startup keeps it visible.

### OD-SSO-1-F — Provisioning: pre-provisioned only, NO JIT (entitlement doctrine)
An `app_user` with `external_subject == sub` **must already exist** (created by onboarding / the demo seed) before a token authenticates; an unknown `sub` → **401**. **No just-in-time provisioning** (no auto-create-user, no auto-role-grant) — JIT would grant access without the maker-checker/SoD action the entitlement framework requires (BR-11/BR-17; `grant_role` audits `ENTITLEMENT.GRANT`), and would be a de-facto new role assignment path outside the governed mint. SSO-1 adds **no new permission, role, or audit code** (hard invariant). Setting `external_subject` on an existing `app_user` is a tenant-scoped data update (the demo seed does it for the demo user so the documented Keycloak `sub` resolves — a column set, **no new run, counts UNCHANGED**).

### OD-SSO-1-G — MFA posture (AD-007 "MFA enforced")
MFA is **enforced at the IdP**, not the resource server (AD-007 — the IdP owns the auth ceremony). The resource server MAY assert it was performed: if `oidc_require_mfa == True`, verify an `acr`/`amr` claim indicating MFA (deny otherwise). Ships **off by default** (`False`) with the check implemented and documented, so a deployment enables it against its IdP's `acr` vocabulary without code change. This records SSO-1's honest boundary: we verify the *assertion* of MFA, the IdP performs it.

### OD-SSO-1-H — Dependency: PyJWT (+ cryptography) (OD-I)
Adopt **PyJWT** with its `PyJWKClient` for JWKS fetch/cache + `cryptography` for RS256 — the most standard, minimal, actively-maintained option; no framework lock-in (vs `authlib`, heavier; `python-jose`, less-maintained). This is a **new production runtime dependency** (unlike FE-2's dev-only `openapi-typescript`) — pinned, and the production `pip-audit`/`npm`-equivalent audit must stay clean (flagged for the review's security lens + the Wave-9 close register). The verifier abstracts its signing-key source so tests inject the local public key without a network call.

### OD-SSO-1-I — Scope fence
SSO-1 = the resource-server verifier module + the `config.py` OIDC fields & guard (OD-B) + the `get_principal` dispatcher (OD-E) + the claim→`app_user` resolution (OD-C) + the shared-test `conftest.py` (`dev_header` autouse) + NEW oidc-path tests (locally-signed) + the documented+composed Keycloak realm (OD-D, closes OD-048) + demo `external_subject` seeding (OD-F) + docs (AD-007 status, DR-P1A0-3 cutover note). **NO FE login flow (FE-3), NO migration, NO new governed number/code/permission/role, NO `audit/service.py` change, NO change to `has_permission`/RLS/`require_permission`.** The entire enforcement layer stays byte-behaviour-identical; only *how the `Principal` is minted* changes.

### OD-SSO-1-J — What SSO-1 does NOT do (honest boundaries)
- No token *issuance* (the IdP's job); no refresh/rotation logic in the resource server (short-lived tokens + FE silent-refresh is FE-3).
- No SAML (AD-007 lists it "supported"; OIDC is primary and the only Wave-9 target).
- No admin UI for provisioning users/subjects (onboarding tooling is later; SSO-1 uses the seed + direct data).
- No per-request IdP introspection (stateless JWKS validation only; revocation relies on short token lifetimes per AD-007).

## Part 3 — Open decisions (OQ-SSO-1-1…4) — ALL RATIFIED 2026-07-21

- **OQ-SSO-1-1 — Verification model** → **Resource-server bearer JWT** (OD-A). *Ratified.* Rejected: BFF session cookies.
- **OQ-SSO-1-2 — Local-dev / test IdP** → **Locally-signed test keys now, Keycloak wired+documented** (OD-D, closes OD-048). *Ratified.* Rejected: Keycloak-in-CI.
- **OQ-SSO-1-3 — Tenant resolution** → **Verified tenant claim cross-checked against the `app_user` record** (OD-C). *Ratified.* Rejected: subject-only lookup.
- **OQ-SSO-1-4 — FE scope** → **Backend-only; SPA OIDC login deferred to FE-3** (OD-I/J). *Ratified.* Rejected: bundling the PKCE login flow.

## Part 4 — Invariants & gates (unchanged, re-affirmed)

- **Hard invariants:** `audit/service.py` FROZEN (never imported by SSO-1 — no audit-code change); no BYPASSRLS/hybrid beyond the closed 5-table set; **no new audit code, permission, or role** (SSO-1 adds none — it re-mints the existing `Principal` from verified claims); no secrets in source (BR-10 — the resource server holds no client secret); the app DB role stays non-superuser / non-BYPASSRLS (DR-P1A0-1).
- **Gates (never waived):** `make check` green; full-PG validation (the demo suite green with `external_subject` seeded); CI-watch-to-green; the OIDC verifier covered by reproduction-grade tests (a real signed token round-trips; tampered signature / wrong `iss` / wrong `aud` / expired / unknown-`sub` / tenant-mismatch each deny with the correct status).
- **Counts UNCHANGED** (17 numbers / 20 codes / 35 records / 101 runs; migration head `0045`) — SSO-1 mints no governed number, code, or run and adds no migration.

## Part 5 — Verifier pass (pre-ratification) — to RUN before implementation

Per the standing cadence, a pre-ratification verifier pass runs against this record before the first impl commit, checking specifically: **(V1)** that `Principal.user_id` truly must be `app_user.id` not `sub` (confirm the `user_role.user_id → app_user.id` FK and the `has_permission` join — OD-C's correctness hinges on it); **(V2)** that the claim→`app_user` lookup under RLS actually sees the row when `app.current_tenant` is set to the claimed tenant (the OD-C "resolve outside/around the tenant session" mechanics); **(V3)** that no existing test asserts `get_principal` behaviour in a way the `auth_mode` dispatcher breaks (beyond the two shim-behaviour files already identified); **(V4)** that PyJWT + `cryptography` land clean in the production dependency audit; **(V5)** that `app_env`/`auth_mode` defaults don't silently open `dev_header` anywhere CI or a deployment would run. Findings fold into the plan before Step 1.
