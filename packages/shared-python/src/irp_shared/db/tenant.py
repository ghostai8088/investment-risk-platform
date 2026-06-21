"""Tenant context for PostgreSQL row-level security (AD-016, BR-17).

Application sessions set ``app.current_tenant`` **transaction-locally** via ``set_config`` so
the RLS policy (``USING tenant_id::text = current_setting('app.current_tenant', true)``) admits
only the acting tenant's rows. A pool **check-in** listener issues an explicit
``RESET app.current_tenant`` as defense-in-depth against a recycled connection retaining
session-scoped context. On non-PostgreSQL engines (SQLite in unit tests) these are no-ops.

Cross-tenant operational tasks use a separate **BYPASSRLS ops role** (AD-015), never the app role.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Any, TypeVar

from sqlalchemy import event, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

#: Future security-event type for DB-level RLS denials (OQ-P1A-0-4a). Deferred per DR-P1A0-4 —
#: not yet emitted; ``classify_rls_denied`` is the seam to map denials to the audit taxonomy later.
RLS_DENIED_EVENT_TYPE = "SECURITY.RLS_DENIED"

T = TypeVar("T")


def _is_postgres(session: Session) -> bool:
    return session.get_bind().dialect.name == "postgresql"


def set_tenant_context(session: Session, tenant_id: str) -> None:
    """Set transaction-local ``app.current_tenant`` (AD-016). No-op on non-PostgreSQL engines.

    Uses ``set_config`` (NOT parameterized ``SET``, which PostgreSQL cannot bind). The value is
    scoped to the session's current transaction and auto-clears at COMMIT/ROLLBACK.
    """
    if _is_postgres(session):
        session.execute(
            text("SELECT set_config('app.current_tenant', :t, true)"), {"t": str(tenant_id)}
        )


def current_tenant(session: Session) -> str | None:
    """Return the active ``app.current_tenant``, or None if unset / non-PostgreSQL."""
    if not _is_postgres(session):
        return None
    value = session.execute(text("SELECT current_setting('app.current_tenant', true)")).scalar()
    return value or None


def attach_tenant_reset(engine: Engine) -> None:
    """Register a pool check-in handler that ``RESET``s ``app.current_tenant`` (defense-in-depth).

    Guards against a recycled pooled connection retaining session-scoped context (SQLAlchemy's
    default rollback-on-return clears transaction-local but not session-level GUCs). No-op on
    non-PostgreSQL engines.
    """
    if engine.dialect.name != "postgresql":
        return

    @event.listens_for(engine, "checkin")
    def _reset_tenant_on_checkin(dbapi_connection: Any, connection_record: Any) -> None:
        try:
            cursor = dbapi_connection.cursor()
            try:
                cursor.execute("RESET app.current_tenant")
            finally:
                cursor.close()
            # Make the RESET durable: commit so it is not left in an uncommitted transaction
            # that a later rollback could revert (no-op when the connection is in autocommit).
            dbapi_connection.commit()
        except Exception:
            connection_record.invalidate()  # never reuse a connection we could not reset


@contextmanager
def tenant_session(session_factory: sessionmaker[Session], tenant_id: str) -> Iterator[Session]:
    """Open a session with tenant context set, for worker/job/CLI **tenant-scoped** paths (AD-016).

    Not for cross-tenant ops (those use the BYPASSRLS ops role, AD-015).
    """
    session = session_factory()
    try:
        set_tenant_context(session, tenant_id)
        yield session
    finally:
        session.close()


def run_in_tenant(
    session_factory: sessionmaker[Session], tenant_id: str, work: Callable[[Session], T]
) -> T:
    """Run ``work(session)`` under a tenant-scoped session and commit (worker/job entry point)."""
    with tenant_session(session_factory, tenant_id) as session:
        result = work(session)
        session.commit()
        return result


def classify_rls_denied(error: BaseException) -> str | None:
    """Hook (placeholder, OQ-P1A-0-4a) mapping a DB error to an RLS-denial security event.

    Deferred per DR-P1A0-4: returns None today (DB-level RLS denials mostly surface as empty
    result sets, not errors). A later step classifies and emits ``SECURITY.RLS_DENIED`` /
    ``AUTH.DENIED`` without redesigning callers.
    """
    return None
