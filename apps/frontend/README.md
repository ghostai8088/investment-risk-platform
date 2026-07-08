# Frontend (`@irp/frontend`)

TypeScript + React + Vite (AD-003). **FE-1: the read-only "risk runs & results" view** — a runs
list (the four risk families: sensitivities, factor exposures, covariances, VaR) and a
deep-linkable run detail (provenance + result rows + the persisted `failure_reason` on FAILED
runs). READ-ONLY: the UI performs no mutation of any kind. No calculation logic lives in the UI
(ARCH-P-04); it only renders governed results from the backend. Accessibility target is WCAG 2.1
AA.

## Dev-session posture (READ BEFORE DEMOING)

The UI authenticates with the backend's **development header shim** (`X-User-Id` /
`X-Tenant-Id`, DR-P1A0-3): the identity is **unverified and not a security boundary** — a
permanent banner says so on every screen. Enforcement (entitlement `risk.view`, deny-by-default,
plus PostgreSQL RLS) is entirely server-side. Real SSO/OIDC is AD-007 (a later phase). The
session lives in `sessionStorage` (closing the tab drops it).

## Running locally

```bash
# 0. Database at head (fresh/reset DBs only; the local irp_pg_local container):
DATABASE_URL=postgresql+psycopg://irp:irp@localhost:5432/irp .venv/bin/alembic upgrade head

# 1. Backend (from repo root; needs DATABASE_URL pointing at the local PG):
DATABASE_URL=postgresql+psycopg://irp:irp@localhost:5432/irp \
  .venv/bin/uvicorn irp_backend.main:app --app-dir apps/backend/src --port 8000

# 2. Frontend dev server (proxies /risk to :8000 — see vite.config.ts; no backend CORS):
npm run -w apps/frontend dev
```

Then open the printed URL and start a dev session with a user id that holds `risk.view` in its
tenant. To mint one (verified recipe — prints the two ids to paste into the session form):

```bash
DATABASE_URL=postgresql+psycopg://irp:irp@localhost:5432/irp .venv/bin/python - <<'PY'
import os, uuid
from irp_shared.db.session import make_engine, make_session_factory
from irp_shared.db.tenant import set_tenant_context
from irp_shared.entitlement.models import AppUser, Permission, Role, RolePermission, UserRole

db = make_session_factory(make_engine(os.environ["DATABASE_URL"]))()
tenant = str(uuid.uuid4())
set_tenant_context(db, tenant)  # transaction-local tenant GUC (AD-016) so RLS admits the writes
user = AppUser(tenant_id=tenant, display_name="Demo viewer")
role = Role(tenant_id=tenant, code="demo-viewer", name="Demo viewer")
db.add_all([user, role])
db.flush()
perm = db.query(Permission).filter_by(code="risk.view").one_or_none()
if perm is None:
    perm = Permission(code="risk.view", description="view risk results")
    db.add(perm)
    db.flush()
db.add(RolePermission(role_id=role.id, permission_id=perm.id))
db.add(UserRole(tenant_id=tenant, user_id=user.id, role_id=role.id))
db.commit()
print("X-User-Id:  ", user.id)
print("X-Tenant-Id:", tenant)
PY
```

A fresh tenant has zero runs — the list will honestly say so; runs appear once the governed
risk endpoints have been exercised for that tenant.

## Commands

```bash
npm install                 # from repo root (workspaces)
npm run -w apps/frontend dev        # local dev server (with the /risk proxy)
npm run -w apps/frontend lint       # eslint
npm run -w apps/frontend typecheck  # tsc --noEmit
npm run -w apps/frontend test       # vitest (jsdom + Testing Library)
npm run -w apps/frontend build      # type-check + vite build
npm run -w apps/frontend format:check  # prettier
```

## Dependency discipline (OD-FE-1-F)

Runtime deps are `react`, `react-dom`, `react-router-dom` — nothing else without a decision
record. Test tooling (`vitest`, `jsdom`, `@testing-library/react`) is dev-only. Decimal values
from the API are exact strings and are rendered **verbatim** — never `Number()`/`parseFloat`
(OQ-FE-1-7; there is a test that fails if this regresses).
