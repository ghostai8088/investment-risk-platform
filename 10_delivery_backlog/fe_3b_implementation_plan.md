# FE-3b Implementation Plan — the SPA browser OIDC / PKCE login (Wave-10 slice 2)

Companion to `fe_3b_decision_record.md` (RATIFIED 2026-07-21; OQ-FE-3b-1 = A hand-roll PKCE; the rest
as recommended). One commit per step; each mirrors a shipped exemplar where one exists. **NO backend
LOGIC change** (`deps.py`/`auth.py`/`config.py` behavior untouched — the resource server is DONE); NO
migration; NO new governed number/code/permission/role/ENT; `audit/service.py` untouched; the GET-only
fence + the decimal-strings contract stay byte-behavior-identical; **NO new runtime dependency**
(`package.json` `dependencies` byte-identical). Demo counts UNCHANGED (17/20/35/101).

## Step 1 — The FE env convention (net-new) + the auth-mode gate scaffolding
- Add a typed `ImportMetaEnv` to `apps/frontend/src/vite-env.d.ts` (`VITE_AUTH_MODE: "dev_header"|"oidc"`, `VITE_OIDC_ISSUER`, `VITE_OIDC_CLIENT_ID`, `VITE_OIDC_REDIRECT_URI`) + a new `apps/frontend/.env.example` documenting them (default `VITE_AUTH_MODE=dev_header` so the demo runs unchanged locally). Add a small `apps/frontend/src/api/authConfig.ts` reading `import.meta.env` once.
- Verify: `make fe-check` typecheck/build green (no behavior change yet — the app still runs dev_header).

## Step 2 — The discriminated-union session (OD-FE-3b-B) + the 16-signature widening
- `session.ts`: `export type Session = DevSession | OidcSession`, `DevSession = { kind:"dev"; userId; tenantId }`, `OidcSession = { kind:"oidc"; accessToken; subject; expiresAt }` (subject = decoded `sub` for the identity chrome). Keep `load/save/clear` (now over `Session`); keep `isValidSessionId` for the dev arm.
- **Mechanically widen `session: DevSession` → `session: Session`** across the 16 non-test pass-through signatures (verifier CLAIM 3): `client.ts`, `useApiGet.ts`, `AppShell.tsx`, `RunsList.tsx`, `RunDetail.tsx`, `WalkStep.tsx`, the six walk step views, `useDemoPortfolio.ts`/`useModelIndex.ts`/`useModelValidations.ts`, `SessionForm.tsx`. Type-only; runtime pass-through unchanged.
- Verify: `make fe-check` typecheck green (the union now threads cleanly).

## Step 3 — `client.ts` identity branch (keep the GET-only fence)
- In `apiGet`, branch on `session.kind`: `"dev"` → the existing `X-User-Id`/`X-Tenant-Id`; `"oidc"` → `Authorization: Bearer ${session.accessToken}`. **`method:"GET"` stays hard-coded** (the fence is about the method, not the header). `AppShell.tsx:33` renders `session.kind==="dev" ? userId@tenantId : session.subject` (a decoded `sub`, never a raw token).
- Verify: FE tests over `apiGet` (extend the existing client test) assert the dev arm sends the two headers, the oidc arm sends `Authorization: Bearer` and NO dev headers, and neither opens a non-GET path.

## Step 4 — The hand-rolled PKCE flow (OD-FE-3b-C; zero-dep, Web Crypto)
- New `apps/frontend/src/auth/pkce.ts`: `randomVerifier()` (`crypto.getRandomValues`→base64url), `challenge(verifier)` (`crypto.subtle.digest("SHA-256")`→base64url), `base64url()` helper. Pure, unit-tested.
- New `apps/frontend/src/auth/oidc.ts`: `beginLogin()` (build the `/authorize` URL with `code_challenge_method=S256` + a random `state`; stash `{verifier, state}` in `sessionStorage`; `window.location.assign`); `completeLogin(searchParams)` (validate `state` FIRST; **strip the `?code` from the URL synchronously via `history.replaceState` before any subresource load**; exchange the code at the token endpoint via `fetch` POST form-encoded — public client, no secret; **delete the single-use `verifier`+`state` from `sessionStorage`**; return the `OidcSession` with decoded `sub`+`exp`); `logout()` (clear + redirect to the Keycloak `end_session_endpoint`). Decode the JWT payload for `sub`/`exp` with a tiny base64url-JSON parse (no verification — the backend verifies; the FE only reads `sub` for display + `exp` for re-auth).
- Verify: unit tests for `pkce.ts` (verifier length/charset; challenge is the S256 of the verifier, cross-checked against a known vector) + `oidc.ts` state-mismatch rejection + the URL-strip.

## Step 5 — `App.tsx`: the `/callback` route above the gate + the auth-mode split (OD-FE-3b-F)
- Handle `/callback` BEFORE the session gate (it lands pre-auth): a `window.location.pathname==="/callback"` branch (or a tiny always-mounted `<Routes>`) that runs `completeLogin`, sets the session, and navigates to `/`.
- The logged-out gate splits on `VITE_AUTH_MODE`: `"dev_header"` → `SessionForm` + `DevBanner` UNCHANGED; `"oidc"` → a "Sign in" button (`beginLogin`) and **NO `DevBanner`** (the honesty invariant — a verified session is a security boundary). "End session" → `logout()` (OIDC) or `clearSession()` (dev).
- Verify: FE tests — dev_header mode renders `SessionForm`+`DevBanner`; oidc mode renders "Sign in" and NOT `DevBanner`; the `/callback` path is reachable logged-out.

## Step 6 — The realm + compose oidc-profile wiring (OD-FE-3b-G; OQ-FE-3b-3=A)
- `infra/keycloak/irp-local-realm.json`: add the **`demo-auditor`** user (username `demo-auditor` → `sub`; `tenant_id` attr = `8c3193a6-1c9c-5353-bbe1-ab8716e986a9` = `DEMO_TENANT_ID`; `enabled:true`) + BR-10-marked local password credentials on the demo users (clearly-fake, env-overridable, never a real secret; the docker-compose `admin/admin` precedent).
- `docker-compose.yml` `backend` service (oidc profile): `AUTH_MODE=oidc`, `OIDC_ISSUER=http://localhost:8080/realms/irp-local`, `OIDC_AUDIENCE=irp-backend`, **`OIDC_JWKS_URI=http://keycloak:8080/realms/irp-local/protocol/openid-connect/certs`** (the verifier CLAIM-2 fix — without it every login 503s), + the frontend build-arg `VITE_AUTH_MODE=oidc` etc. Add `infra/keycloak/README.md` runbook: the issuer-consistency explanation + `docker compose --profile oidc up` steps + the demo-auditor login.
- Verify: manual/documented — `docker compose --profile oidc up`, log in as `demo-auditor`, the walk renders (this is the demonstrable-login acceptance). NOT a CI dependency (CI keeps its locally-signed RS256 keys; SSO-1 precedent).

## Step 7 — Full gate + review
- `make fe-check` (typecheck/lint/format/tests/build — the FE suite + the new pkce/oidc/client/App tests); `make check` (Python — a no-op, NO backend change); `make gen-api-check` clean (NO new endpoint); `package.json` `dependencies` byte-identical (the OD-FE-1-F gate); `npm audit --omit=dev` still 0.
- 4-finder adversarial review (a security-sensitive auth flow): PKCE/state-CSRF correctness + no token-in-URL/history leak; the token→backend contract (demo-auditor resolves); the DevBanner-honesty gate; the GET-only fence intact; the issuer-consistency wiring actually works (`OIDC_JWKS_URI` present).
- Closeout: **stamp THIS record CLOSED** (the API-1b closure-check now ENFORCES it — a DONE roadmap row + a DRAFT Status cell fails CI), roadmap Part 2.13 slice-2 → DONE with PR#/CI#, `current_state` banner, memory.
