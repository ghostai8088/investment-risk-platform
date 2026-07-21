"""FastAPI dependencies wiring the foundation frameworks into the API.

- ``get_db`` yields a SQLAlchemy session (configured from ``DATABASE_URL``).
- ``get_principal`` resolves the caller per ``settings.auth_mode`` (SSO-1, AD-007). In ``oidc``
  mode (the default) it verifies the ``Authorization: Bearer`` JWT and resolves the ``sub`` claim
  to an active ``app_user`` in the token's tenant. In ``dev_header`` mode it reads the unverified
  ``X-User-Id`` / ``X-Tenant-Id`` shim — a **development-only** path, permitted only when
  ``app_env == "local"`` (fail-closed at startup via ``validate_auth_config``); the header tenant
  is **unverified and not a security boundary** in that mode (DR-P1A0-3).
- ``get_tenant_session`` yields a session with ``app.current_tenant`` set for the principal's
  tenant (AD-016) so PostgreSQL RLS admits the principal's rows. **All entitled/data paths use
  this**, not ``get_db`` directly.
- ``require_permission`` is a deny-by-default entitlement gate (BR-11, BR-17) running under the
  tenant session (so RLS does not hide the principal's own ``role``/``user_role`` rows).

**Deployment security requirement (DR-P1A0-1):** the application database role must be
**non-superuser and must NOT have BYPASSRLS** — PostgreSQL superusers / BYPASSRLS roles bypass
row-level security entirely (even under ``FORCE ROW LEVEL SECURITY``), so RLS only protects when
the app connects as a constrained role. BYPASSRLS is reserved for the dedicated ops role (audit
verification); normal request paths never use it.
"""

from __future__ import annotations

from collections.abc import Iterator
from functools import lru_cache

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from irp_backend.auth import TokenError, get_verifier
from irp_backend.config import settings
from irp_shared.db.session import make_engine, make_session_factory
from irp_shared.db.tenant import set_tenant_context
from irp_shared.entitlement.models import AppUser
from irp_shared.entitlement.service import Principal, has_permission


@lru_cache(maxsize=1)
def _session_factory() -> sessionmaker[Session]:
    if not settings.database_url:
        raise RuntimeError("DATABASE_URL is not configured")
    return make_session_factory(make_engine(settings.database_url))


def get_db() -> Iterator[Session]:
    db = _session_factory()()
    try:
        yield db
    finally:
        db.close()


def get_principal(
    db: Session = Depends(get_db),
    x_user_id: str | None = Header(default=None),
    x_tenant_id: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
) -> Principal:
    """Resolve the caller's identity per ``settings.auth_mode`` (SSO-1, AD-007).

    - ``oidc`` (default): verify the ``Authorization: Bearer`` JWT and resolve its ``sub`` claim to
      an active ``app_user`` in the token's tenant (see :func:`_principal_from_token`).
    - ``dev_header``: the unverified ``X-User-Id`` / ``X-Tenant-Id`` shim — permitted only when
      ``app_env == "local"`` (enforced fail-closed at startup by ``validate_auth_config``).
    """
    if settings.auth_mode == "dev_header":
        return _principal_from_headers(x_user_id, x_tenant_id)
    return _principal_from_token(authorization, db)


def _principal_from_headers(x_user_id: str | None, x_tenant_id: str | None) -> Principal:
    """The DEV shim: trust the caller's asserted identity headers (local only)."""
    if not x_user_id or not x_tenant_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="missing principal")
    return Principal(user_id=x_user_id, tenant_id=x_tenant_id)


def _principal_from_token(authorization: str | None, db: Session) -> Principal:
    """Verify a Bearer JWT and resolve ``(tenant_claim, sub)`` → an active ``app_user`` row.

    The token's ``sub`` binds to ``app_user.external_subject``; the tenant claim is cross-checked by
    the ``(tenant_id, external_subject)`` lookup (OD-SSO-1-C). ``Principal.user_id`` is the resolved
    ``app_user.id`` — the value ``has_permission`` joins on — NOT the raw ``sub``. Every failure
    returns an opaque 401 (no user-enumeration signal). The lookup runs after arming the claimed
    tenant's RLS context, so ``app_user`` (a FORCE-RLS table) is visible for exactly that tenant.
    """
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid credentials"
    )
    if not authorization:
        raise unauthorized
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise unauthorized
    try:
        claims = get_verifier().verify(token.strip())
    except TokenError as exc:
        raise unauthorized from exc

    set_tenant_context(db, claims.tenant)
    user = db.execute(
        select(AppUser).where(
            AppUser.tenant_id == claims.tenant,
            AppUser.external_subject == claims.subject,
            AppUser.is_active.is_(True),
        )
    ).scalar_one_or_none()
    if user is None:
        raise unauthorized
    return Principal(user_id=user.id, tenant_id=user.tenant_id)


def get_tenant_session(
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
) -> Iterator[Session]:
    """Yield a session scoped to the principal's tenant (sets ``app.current_tenant``, AD-016).

    ``set_tenant_context`` issues the first statement, which **autobegins** the session's
    transaction; the GUC is set transaction-locally and auto-clears when ``get_db`` closes the
    session at request end (plus the pool RESET).

    **Invariant (single-transaction request):** do not COMMIT/ROLLBACK this session mid-request — a
    new autobegun transaction would run with no tenant context and RLS would fail closed (hide
    rows / reject writes). A handler that must transact mid-request must call ``set_tenant_context``
    again afterward. (AD-016 revisit for request-spanning work.)
    """
    set_tenant_context(db, principal.tenant_id)
    yield db


def require_permission(permission_code: str):  # noqa: ANN201 - returns a FastAPI dependency
    """Return a dependency that allows the request only if the principal holds the permission
    in its own tenant; otherwise 403 (deny-by-default). Runs under the tenant session so RLS
    does not hide the principal's own ``role``/``user_role`` rows (false-deny)."""

    def _dependency(
        principal: Principal = Depends(get_principal),
        db: Session = Depends(get_tenant_session),
    ) -> Principal:
        if not has_permission(db, principal, permission_code, principal.tenant_id):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="permission denied")
        return principal

    return _dependency


def map_refusal(
    exc: Exception, error_map: dict[type[Exception], tuple[int, str]]
) -> tuple[int, str]:
    """Resolve the (status, opaque detail) for a refusal exception by walking the MRO — a
    SUBCLASS of a mapped exception otherwise KeyErrors into a 500 (P3-C1, OD-F; shared by the
    risk/exposure/snapshot routers). The nearest mapped ancestor wins; an unmapped exception
    raises KeyError loudly (a genuine programming error)."""
    for klass in type(exc).__mro__:
        if klass in error_map:
            return error_map[klass]
    raise KeyError(type(exc))
