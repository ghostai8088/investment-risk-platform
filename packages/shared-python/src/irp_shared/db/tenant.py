"""Tenant context for PostgreSQL row-level security (AD-016, BR-17).

Application sessions set ``app.current_tenant`` **transaction-locally** via ``set_config`` so
the RLS policy (``USING tenant_id::text = current_setting('app.current_tenant', true)``) admits
only the acting tenant's rows. A pool **check-in** listener issues an explicit
``RESET app.current_tenant`` as defense-in-depth against a recycled connection retaining
session-scoped context. On non-PostgreSQL engines (SQLite in unit tests) these are no-ops.

Cross-tenant operational tasks use a separate **BYPASSRLS ops role** (AD-015), never the app role.
"""

from __future__ import annotations

import weakref
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


#: The live re-arm listener per session (review fold: re-arming a session for a NEW tenant must
#: REPLACE the old listener, not stack under it — a stacked stale listener would silently flip the
#: RLS scope back to the previous tenant on the next transaction).
_REARM_LISTENERS: weakref.WeakKeyDictionary[Session, Callable[..., None]] = (
    weakref.WeakKeyDictionary()
)


def persistent_tenant_context(session: Session, tenant_id: str) -> Callable[[], None]:
    """Arm ``app.current_tenant`` NOW and RE-ARM it at every new transaction (commit-safe).

    ``set_tenant_context``'s ``SET LOCAL`` semantics auto-clear at COMMIT/ROLLBACK — correct for
    the per-request app path (one transaction per request), but a recurring trap for LONG-LIVED
    sessions that commit mid-flow and read after (the MD-H1 annex-4 incident: a PG test read 0 rows
    post-commit because the re-arm was forgotten). This registers an ``after_begin`` listener that
    re-issues the transaction-local ``set_config`` whenever the session opens a new transaction, so
    a forgotten manual re-arm can no longer silently drop the tenant scope.

    Re-invoking on the same session (a NEW tenant) REPLACES the prior listener — never stacks
    (review fold). The dialect check reads the ``connection`` the event delivered, not
    ``session.get_bind()`` (correct for externally-bound sessions). Returns a ``detach`` callable
    that removes the listener (call it before dropping back to plain per-transaction scoping).
    """
    prior = _REARM_LISTENERS.pop(session, None)
    if prior is not None:
        event.remove(session, "after_begin", prior)
    set_tenant_context(session, tenant_id)

    def _rearm(sess: Session, transaction: Any, connection: Any) -> None:
        if connection.dialect.name == "postgresql":
            connection.execute(
                text("SELECT set_config('app.current_tenant', :t, true)"), {"t": str(tenant_id)}
            )

    event.listen(session, "after_begin", _rearm)
    _REARM_LISTENERS[session] = _rearm

    def detach() -> None:
        if _REARM_LISTENERS.pop(session, None) is _rearm:
            event.remove(session, "after_begin", _rearm)

    return detach


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
