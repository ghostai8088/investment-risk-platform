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

import uuid
from collections.abc import Iterator
from functools import lru_cache

from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, sessionmaker

from irp_backend.auth import TokenError, get_verifier
from irp_backend.config import settings
from irp_shared.db.session import make_engine, make_session_factory
from irp_shared.db.tenant import set_tenant_context
from irp_shared.entitlement.bootstrap import SYSTEM_TENANT_ID
from irp_shared.entitlement.models import AppUser
from irp_shared.entitlement.service import Principal, has_permission
from irp_shared.tenancy.boundary import TenantNotAdmitted, assert_tenant_admitted

#: Path prefixes a SYSTEM-tenant principal may reach (ONBOARD-1a, the OQ-ONB-2A fence).
#:
#: Seeding the platform operator makes the SYSTEM tenant AUTHENTICATABLE for the first time in the
#: platform's life — the verifier pass established that nothing refuses a SYSTEM tenant claim
#: today, and that it 401s only because no SYSTEM ``app_user`` exists. From the moment one does,
#: any token an IdP signs with the SYSTEM tenant claim resolves. This allow-list is what keeps that
#: token worth exactly the provisioning surface and nothing else: not a portfolio, not a governed
#: number, not the audit trail.
#:
#: An ALLOW-list, never a deny-list, and a census walks every route asserting the classification is
#: total — a router added next year is refused to SYSTEM principals until somebody decides
#: otherwise, which is the only safe default for a fence.
SYSTEM_TENANT_ALLOWED_PREFIXES: tuple[str, ...] = ("/tenants",)


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
    request: Request,
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

    **ONBOARD-1a adds two boundary refusals, and they sit HERE rather than in the OIDC verifier so
    they bind BOTH auth modes** (a control that only covers the production path leaves the deployed
    stack — which runs ``dev_header`` — unprotected, which is precisely where the ignition proof
    runs):

    1. the claimed tenant must be REGISTERED and ADMITTED (``assert_tenant_admitted`` — see that
       module for why it is dialect-gated and what the unit tier therefore does not prove);
    2. a SYSTEM-tenant principal may reach only the provisioning surface.

    Both return the same opaque 401 as every other resolution failure: distinguishing "no such
    tenant" from "suspended" from "wrong surface" at the wire is a free enumeration oracle.
    """
    if settings.auth_mode == "dev_header":
        # Defense in depth: the startup guard already forbids dev_header outside local, but never
        # trust the unverified shim in a non-local process even if it somehow booted (DR-P1A0-3).
        if settings.app_env != "local":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid credentials"
            )
        principal = _principal_from_headers(x_user_id, x_tenant_id)
        # The registry check runs AFTER canonicalization and BEFORE anything arms a context.
        _assert_admitted_or_401(db, principal.tenant_id)
    else:
        principal = _principal_from_token(authorization, db)
    _assert_system_principal_is_fenced(request, principal)
    return principal


def _assert_admitted_or_401(db: Session, tenant_id: str) -> None:
    try:
        assert_tenant_admitted(db, tenant_id)
    except TenantNotAdmitted as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid credentials"
        ) from exc


def _assert_system_principal_is_fenced(request: Request, principal: Principal) -> None:
    """A SYSTEM-tenant principal may reach only the provisioning surface (ONBOARD-1a).

    Matched on the request PATH rather than on a route object: a path is what the client actually
    asked for, and it is the same string the census walks, so the fence and its proof cannot drift
    apart by looking at different things.
    """
    if principal.tenant_id != SYSTEM_TENANT_ID:
        return
    path = request.url.path
    if any(path == p or path.startswith(p + "/") for p in SYSTEM_TENANT_ALLOWED_PREFIXES):
        return
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid credentials")


def _principal_from_headers(x_user_id: str | None, x_tenant_id: str | None) -> Principal:
    """The DEV shim: trust the caller's asserted identity headers (local only).

    **The tenant header is CANONICALIZED before it can arm the RLS GUC** (OPS-H1 H1-5 — the OQ-a
    class's third boundary). The SSO-1 standing rule is *any code path arming a tenant GUC from an
    external string canonicalizes first*; this path is dev-only (refused outside
    ``app_env == "local"``), but a rule with a carve-out is weaker than a rule — an uppercased or
    brace-wrapped UUID here would arm a GUC that matches NO ``tenant_id::text``, turning every read
    silently empty (the fail-open-looking fail-closed that wastes a debugging afternoon). A
    non-UUID header is a 401, same as the OIDC path's claim treatment.
    """
    if not x_user_id or not x_tenant_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="missing principal")
    try:
        tenant = str(uuid.UUID(x_tenant_id))  # canonicalize so RLS's tenant_id::text matches
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="missing principal"
        ) from None
    return Principal(user_id=x_user_id, tenant_id=tenant)


def _principal_from_token(authorization: str | None, db: Session) -> Principal:
    """Verify a Bearer JWT and resolve ``(tenant_claim, sub)`` → an active ``app_user`` row.

    The token's ``sub`` binds to ``app_user.external_subject``; the tenant claim is cross-checked by
    the ``(tenant_id, external_subject)`` lookup (OD-SSO-1-C). ``Principal.user_id`` is the resolved
    ``app_user.id`` — the value ``has_permission`` joins on — NOT the raw ``sub``. Every failure
    returns an opaque 401 (no user-enumeration signal). The lookup runs after arming the claimed
    tenant's RLS context, so ``app_user`` (a FORCE-RLS table) is visible for exactly that tenant.

    The tenant claim is **canonicalized** (``str(uuid.UUID(...))``) before it arms the RLS GUC: the
    ``tenant_isolation`` policy compares ``tenant_id::text`` (which PostgreSQL renders as
    lowercase-hyphenated) against ``current_setting('app.current_tenant')``, so a valid-but-non-
    canonical UUID claim (uppercase, or braces/urn form) would be RLS-hidden — a false-deny of a
    legitimate user — without normalization. A non-UUID claim raises ``ValueError`` → opaque 401.
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
        verifier = get_verifier()
    except (OSError, TokenError) as exc:  # JWKS/discovery unreachable — fail closed, never open
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="authentication temporarily unavailable",
        ) from exc
    try:
        claims = verifier.verify(token.strip())
    except TokenError as exc:
        raise unauthorized from exc
    try:
        tenant = str(uuid.UUID(claims.tenant))  # canonicalize so RLS's tenant_id::text matches
    except ValueError as exc:
        raise unauthorized from exc

    # ONBOARD-1a: the registry check precedes the context arming, so an unregistered or suspended
    # tenant never gets a GUC set for it at all.
    _assert_admitted_or_401(db, tenant)
    set_tenant_context(db, tenant)
    user = db.execute(
        select(AppUser).where(
            AppUser.tenant_id == tenant,
            AppUser.external_subject == claims.subject,
            AppUser.is_active.is_(True),
        )
    ).scalar_one_or_none()
    if user is None:
        raise unauthorized
    return Principal(user_id=user.id, tenant_id=tenant)


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


def require_uuid_principal_id(principal: Principal) -> str:
    """The principal's ``user_id``, FAIL-CLOSED on a non-UUID form (the API-2 D1/F2 dev-header
    contract: ``X-User-Id`` MUST be a parseable ``app_user.id`` — a clean 401, never a bubbled
    500). The SHARED actor-construction step for every domain actor (``LimitActor``/``BreachActor``
    — hoisted at API-2b per audit C-F11: one dependency, not per-router copies); the dataclasses
    then canonicalize so stamp == compare for the person-level SoD."""
    try:
        uuid.UUID(principal.user_id)
    except (ValueError, AttributeError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="unauthorized"
        ) from None
    return principal.user_id


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


def deadlock_503(db: Session, exc: OperationalError) -> HTTPException:
    """A 40P01 deadlock victim → 503 + Retry-After (B-F1); anything else re-raises (fail loud).

    Hoisted from the breaches router at the Wave-12 close: phases 1–2 of the tick can hold the
    audit-chain advisory lock while a new-breach INSERT waits on the parent ``limit_definition``
    row's FK KEY SHARE, so a limit verb holding FOR UPDATE and waiting on the advisory is a
    reachable 40P01 victim too — BOTH write routers must treat 40P01 as transient/retryable.
    """
    orig = getattr(exc, "orig", None)
    code = getattr(orig, "sqlstate", None) or getattr(orig, "pgcode", None)
    if code != "40P01":
        raise exc
    db.rollback()
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="transient lock contention; retry",
        headers={"Retry-After": "1"},
    )
