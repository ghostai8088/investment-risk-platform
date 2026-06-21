"""PostgreSQL RLS tenant-context integration tests (AD-016, AD-015; BR-17).

Gated on ``IRP_TEST_DATABASE_URL`` (a PostgreSQL **superuser** URL) — SQLite has no RLS, so these
run in the CI ``migration`` job after ``alembic upgrade head`` (schema + the ``irp_ops`` BYPASSRLS
role from migration 0003).

**RLS enforcement tests run under a constrained app role, not the superuser.** PostgreSQL
superusers bypass row-level security even under ``FORCE ROW LEVEL SECURITY``; the ``app_url``
fixture creates a non-superuser, non-BYPASSRLS ``irp_app`` role (ephemeral CI-only credential) so
the denial/isolation tests actually exercise RLS. GUC-mechanics tests (context set / auto-clear /
recycle) are role-agnostic and use the superuser URL directly.
"""

from __future__ import annotations

import os
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.pool import NullPool, QueuePool

from irp_shared.audit.service import record_event
from irp_shared.db.session import make_engine, make_session_factory
from irp_shared.db.tenant import current_tenant, run_in_tenant, set_tenant_context

URL = os.environ.get("IRP_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="requires PostgreSQL (IRP_TEST_DATABASE_URL)")


def _factory(poolclass=NullPool, **kw):  # noqa: ANN001,ANN202 - test helper (superuser)
    engine = make_engine(URL, poolclass=poolclass, **kw)
    return engine, make_session_factory(engine)


def _emit(session, tenant):  # noqa: ANN001,ANN202
    record_event(
        session,
        event_type="TEST.EVENT",
        tenant_id=tenant,
        actor_type="user",
        actor_id="u",
        source_module="test",
        action="create",
    )


def _is_rls_violation(error: ProgrammingError) -> bool:
    return (
        getattr(error.orig, "sqlstate", None) == "42501"  # insufficient_privilege
        or "row-level security" in str(error).lower()
    )


@pytest.fixture(scope="module")
def app_url() -> str:
    """Constrained NON-superuser, NON-BYPASSRLS app role so RLS is actually enforced.

    Created with an ephemeral CI-only credential; production uses a real non-superuser app role.
    """
    superuser = make_engine(URL, poolclass=NullPool)
    with superuser.begin() as conn:
        conn.execute(
            text(
                "DO $$ BEGIN "
                "IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'irp_app') "
                "THEN CREATE ROLE irp_app LOGIN NOSUPERUSER NOBYPASSRLS PASSWORD 'ci_app_pw'; "
                "ELSE ALTER ROLE irp_app LOGIN NOSUPERUSER NOBYPASSRLS PASSWORD 'ci_app_pw'; "
                "END IF; END $$"
            )
        )
        conn.execute(text("GRANT USAGE ON SCHEMA public TO irp_app"))
        conn.execute(text("GRANT SELECT, INSERT ON audit_event TO irp_app"))
    superuser.dispose()
    return (
        make_url(URL)
        .set(username="irp_app", password="ci_app_pw")
        .render_as_string(hide_password=False)
    )


# --- GUC-mechanics tests (role-agnostic; superuser URL) ---


def test_context_set_within_transaction() -> None:
    engine, factory = _factory()
    session = factory()
    try:
        tenant = str(uuid.uuid4())
        set_tenant_context(session, tenant)
        assert current_tenant(session) == tenant
    finally:
        session.close()
        engine.dispose()


def test_transaction_local_auto_clear() -> None:
    engine, factory = _factory()
    session = factory()
    try:
        tenant = str(uuid.uuid4())
        set_tenant_context(session, tenant)
        assert current_tenant(session) == tenant
        session.commit()  # is_local=true context is discarded at COMMIT
        assert current_tenant(session) is None
    finally:
        session.close()
        engine.dispose()


def test_pooled_connection_recycle_safety() -> None:
    # 1-connection pool so the second session reuses the same physical connection.
    engine = make_engine(URL, poolclass=QueuePool, pool_size=1, max_overflow=0)
    factory = make_session_factory(engine)
    tenant = str(uuid.uuid4())
    first = factory()
    # Set SESSION-scoped context (is_local=false) — the case the check-in RESET must clear.
    first.execute(text("SELECT set_config('app.current_tenant', :t, false)"), {"t": tenant})
    first.commit()
    first.close()  # check-in -> RESET app.current_tenant fires (durably committed)
    second = factory()  # reuses the same pooled connection
    try:
        assert current_tenant(second) is None
    finally:
        second.close()
        engine.dispose()


def test_worker_tenant_job_path_uses_context() -> None:
    # The worker entry point irp_worker.jobs.run_tenant_job is a thin wrapper over this shared
    # helper. The migration CI job installs only shared-python (not apps/worker), so we exercise
    # the shared helper here on PostgreSQL; the worker wrapper itself is covered on SQLite
    # (apps/worker/tests/test_jobs.py).
    engine, factory = _factory()
    try:
        tenant = str(uuid.uuid4())
        seen = run_in_tenant(factory, tenant, current_tenant)
        assert seen == tenant
    finally:
        engine.dispose()


# --- RLS enforcement tests (constrained non-superuser app role) ---


def test_missing_context_fails_closed(app_url: str) -> None:
    engine = make_engine(app_url, poolclass=NullPool)
    factory = make_session_factory(engine)
    session = factory()
    try:
        with pytest.raises(ProgrammingError) as exc_info:
            _emit(session, str(uuid.uuid4()))  # no context -> RLS rejects the insert
        assert _is_rls_violation(exc_info.value)
        session.rollback()
        # Reads also fail closed: with no context, RLS hides every tenant's rows.
        assert session.execute(text("SELECT count(*) FROM audit_event")).scalar() == 0
    finally:
        session.close()
        engine.dispose()


def test_tenant_mismatch_denied(app_url: str) -> None:
    engine = make_engine(app_url, poolclass=NullPool)
    factory = make_session_factory(engine)
    session = factory()
    try:
        tenant_a, tenant_b = str(uuid.uuid4()), str(uuid.uuid4())
        set_tenant_context(session, tenant_a)
        with pytest.raises(ProgrammingError) as exc_info:
            _emit(session, tenant_b)  # insert tenant_b under context A -> RLS rejects
        assert _is_rls_violation(exc_info.value)
        session.rollback()
    finally:
        session.close()
        engine.dispose()


def test_tenant_isolation_reads_only_own_rows(app_url: str) -> None:
    engine = make_engine(app_url, poolclass=NullPool)
    factory = make_session_factory(engine)
    tenant_a, tenant_b = str(uuid.uuid4()), str(uuid.uuid4())
    for tenant in (tenant_a, tenant_b):
        session = factory()
        try:
            set_tenant_context(session, tenant)
            _emit(session, tenant)
            session.commit()
        finally:
            session.close()

    session = factory()
    try:
        set_tenant_context(session, tenant_a)
        chains = {
            row[0] for row in session.execute(text("SELECT DISTINCT chain_id FROM audit_event"))
        }
        assert tenant_a in chains  # sees its own tenant
        assert tenant_b not in chains  # RLS isolates: A cannot see B
    finally:
        session.close()
        engine.dispose()


# --- BYPASSRLS ops role (AD-015) ---


def test_ops_bypassrls_reads_across_tenants() -> None:
    # Seed events for two tenants (each under its own context).
    engine, factory = _factory()
    tenant_a, tenant_b = str(uuid.uuid4()), str(uuid.uuid4())
    for tenant in (tenant_a, tenant_b):
        session = factory()
        try:
            set_tenant_context(session, tenant)
            _emit(session, tenant)
            session.commit()
        finally:
            session.close()
    engine.dispose()

    # Give the BYPASSRLS ops role (created by migration 0003) a login + ephemeral CI password.
    superuser = make_engine(URL, poolclass=NullPool)
    with superuser.connect() as conn:
        conn.execute(text("ALTER ROLE irp_ops LOGIN PASSWORD 'ci_ops_pw'"))  # CI-only ephemeral
        conn.commit()
    superuser.dispose()

    ops_url = (
        make_url(URL)
        .set(username="irp_ops", password="ci_ops_pw")
        .render_as_string(hide_password=False)
    )
    ops_engine = make_engine(ops_url, poolclass=NullPool)
    try:
        with ops_engine.connect() as conn:
            # No tenant context set, yet BYPASSRLS sees every tenant's chain.
            chains = {
                row[0] for row in conn.execute(text("SELECT DISTINCT chain_id FROM audit_event"))
            }
        assert {tenant_a, tenant_b} <= chains
    finally:
        ops_engine.dispose()
