# Local OIDC provider (Keycloak) — SSO-1 / AD-007

This closes **OD-048** ("confirm the local-dev OIDC provider choice"): the local-dev identity
provider is **Keycloak**, run as an opt-in `docker compose` service that imports the realm in
[`irp-local-realm.json`](irp-local-realm.json).

> **Scope note (honest boundary).** The backend's token verification is covered by CI with
> **locally-signed RS256 keys** (`apps/backend/tests/test_auth_verifier.py`,
> `test_oidc_auth.py`) — **Keycloak is NOT a CI dependency**. This realm + compose service is a
> **developer convenience** for exercising a real end-to-end OIDC flow locally. The realm export
> is provided as a starting point; the Keycloak admin console at <http://localhost:8080/admin> is
> the authoritative place to adjust it. MFA (AD-007) is enforced at the IdP and is out of scope
> for this local realm.

## The binding that must hold

The backend resolves identity as: verified token `sub` → `app_user.external_subject`, within the
token's `tenant_id` claim (see `apps/backend/src/irp_backend/deps.py`, OD-SSO-1-C). So a token is
accepted **only if** an active `app_user` exists with:

| Token claim | Must equal |
|---|---|
| `sub` | an `app_user.external_subject` |
| `tenant_id` | that same row's `app_user.tenant_id` |
| `aud` | `OIDC_AUDIENCE` (if set on the backend) — the realm maps `irp-backend` |
| `iss` | `OIDC_ISSUER` (`http://localhost:8080/realms/irp-local`) |

The demo seed (`irp_shared.demo.campaign._seed_principals`) creates two demo principals in the
demo tenant `8c3193a6-1c9c-5353-bbe1-ab8716e986a9`:

| `external_subject` | display name |
|---|---|
| `demo-validator` | Andrew Cox |
| `demo-registrar` | MG-1 demo registrar |

The realm's two users (`demo-validator`, `demo-registrar`) carry the matching `username` and a
`tenant_id` user-attribute of that tenant. A **`sub-from-username` protocol mapper** makes the
token's `sub` equal the username (Keycloak's native `sub` is the internal user UUID), and a
**`tenant_id` attribute mapper** emits the tenant claim. If you instead let `sub` default to the
Keycloak UUID, set `external_subject` to that UUID.

## Run it

```bash
# 1. Start Keycloak (opt-in profile; imports the realm on first boot).
docker compose --profile oidc up keycloak

# 2. The three demo users (demo-validator / demo-registrar / demo-auditor) ship with the local-only
#    placeholder password "demo" (FE-3b — a clearly-fake dev credential, the admin/admin precedent,
#    BR-10; never a real secret). Change it in the admin console if you like.

# 3. Point the backend at the realm (in .env):
#    AUTH_MODE=oidc
#    OIDC_ISSUER=http://localhost:8080/realms/irp-local
#    OIDC_AUDIENCE=irp-backend

# 4. Obtain an access token (direct-access grant is enabled for the demo client):
curl -s http://localhost:8080/realms/irp-local/protocol/openid-connect/token \
  -d grant_type=password -d client_id=irp-frontend \
  -d username=demo-auditor -d password=demo | python -c 'import sys,json;print(json.load(sys.stdin)["access_token"])'

# 5. Call the API with it:
curl -H "Authorization: Bearer <token>" http://localhost:8000/<endpoint>
```

## The full SPA login demo (FE-3b) — `docker compose --profile oidc up`

FE-3b ships the browser auth-code + PKCE login. The one non-obvious piece is a **Keycloak-in-Docker
issuer-consistency** gotcha: the browser reaches Keycloak at `localhost:8080`, so the token's `iss`
is `http://localhost:8080/realms/irp-local` — and the backend's `OIDC_ISSUER` must be that exact
string. But the backend runs *inside* the compose network, where `localhost:8080` is the backend
container, not Keycloak — so JWKS *auto-discovery* to the issuer host fails and every login 503s.

**Fix (already wired in `.env.example`):** keep `OIDC_ISSUER=localhost` (to match the token) and set
`OIDC_JWKS_URI=http://keycloak:8080/realms/irp-local/protocol/openid-connect/certs` — the keys are
fetched via the compose *service* name, and the certs endpoint embeds no issuer, so the cross-host
fetch is sound.

```bash
# 1. In .env, uncomment the FE-3b block (AUTH_MODE=oidc + the OIDC_* incl. OIDC_JWKS_URI + the VITE_*
#    front-end vars — VITE_* are inlined at the frontend image BUILD, so a rebuild is required).
# 2. Build + run the whole stack (the oidc profile adds Keycloak; the rest always start):
docker compose --profile oidc up --build
# 3. Open http://localhost:5173 → "Sign in" → Keycloak → log in as demo-auditor / demo →
#    the governance walk renders (demo-auditor holds exactly the walk's read permissions).
```

The `irp-frontend` client is a **public** client (PKCE S256, no secret); the token carries `sub`
(=username=the app_user's `external_subject`), the `tenant_id` claim (=`DEMO_TENANT_ID`), and the
`irp-backend` audience — everything `_principal_from_token` needs.
