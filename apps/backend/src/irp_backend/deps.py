"""FastAPI dependencies wiring the foundation frameworks into the API.

- ``get_db`` yields a SQLAlchemy session (configured from ``DATABASE_URL``).
- ``get_principal`` resolves the caller. **DEV PLACEHOLDER**: it reads ``X-User-Id`` /
  ``X-Tenant-Id`` headers. Real identity comes from OIDC/SSO (AD-007); this shim exists only
  so the entitlement dependency is exercisable before SSO lands.
- ``require_permission`` is a deny-by-default entitlement gate (BR-11, BR-17). No domain
  endpoints exist yet; this is the gate they will use.
"""

from __future__ import annotations

from collections.abc import Iterator
from functools import lru_cache

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session, sessionmaker

from irp_backend.config import settings
from irp_shared.db.session import make_engine, make_session_factory
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
    x_user_id: str | None = Header(default=None),
    x_tenant_id: str | None = Header(default=None),
) -> Principal:
    if not x_user_id or not x_tenant_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="missing principal")
    return Principal(user_id=x_user_id, tenant_id=x_tenant_id)


def require_permission(permission_code: str):  # noqa: ANN201 - returns a FastAPI dependency
    """Return a dependency that allows the request only if the principal holds the permission
    in its own tenant; otherwise 403 (deny-by-default)."""

    def _dependency(
        principal: Principal = Depends(get_principal),
        db: Session = Depends(get_db),
    ) -> Principal:
        if not has_permission(db, principal, permission_code, principal.tenant_id):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="permission denied")
        return principal

    return _dependency
