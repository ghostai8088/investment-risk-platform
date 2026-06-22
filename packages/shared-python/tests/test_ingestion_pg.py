"""PostgreSQL RLS + append-only tests for generic ingestion staging (P1A-4; BR-17, AD-016, AD-015).

Gated on ``IRP_TEST_DATABASE_URL`` (a superuser URL). Enforcement runs under the constrained,
**non-superuser, non-BYPASSRLS** ``irp_app`` role. Applies the CI lessons: native ``uuid`` → ORM/
``GUID`` for inserts, ``CAST(:i AS uuid)`` for raw by-id mutations, ``str()`` for uuid reads;
SQLSTATE 42501 (``_is_rls_violation``); the staged-record append-only proof is the P0001 trigger
(``_is_append_only_violation``) with ``irp_app`` granted UPDATE/DELETE, while the batch is the
status-mutable negative control (a raw UPDATE under context SUCCEEDS).
"""

from __future__ import annotations

import os
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.pool import NullPool

from irp_shared.db.session import make_engine, make_session_factory
from irp_shared.db.tenant import set_tenant_context
from irp_shared.dq.service import register_dq_rule
from irp_shared.ingestion.models import IngestionBatch
from irp_shared.ingestion.service import STAGING_ROW_TARGET, stage_upload
from irp_shared.lineage.service import register_data_source

URL = os.environ.get("IRP_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="requires PostgreSQL (IRP_TEST_DATABASE_URL)")

_TABLES = (
    "ingestion_batch",
    "ingestion_staged_record",
    "data_source",
    "data_quality_rule",
    "data_quality_result",
    "lineage_edge",
)


def _is_rls_violation(error: ProgrammingError) -> bool:
    return (
        getattr(error.orig, "sqlstate", None) == "42501"
        or "row-level security" in str(error).lower()
    )


def _is_append_only_violation(error: ProgrammingError) -> bool:
    return getattr(error.orig, "sqlstate", None) == "P0001" or "append-only" in str(error).lower()


@pytest.fixture(scope="module")
def app_url() -> str:
    """Constrained non-superuser app role; UPDATE/DELETE on the IA staged record so its append-only
    rejection is the TRIGGER (P0001), not a privilege denial (42501)."""
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
        for table in _TABLES:
            conn.execute(text(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO irp_app"))
        conn.execute(text("GRANT SELECT, INSERT ON audit_event TO irp_app"))
    superuser.dispose()
    return (
        make_url(URL)
        .set(username="irp_app", password="ci_app_pw")
        .render_as_string(hide_password=False)
    )


def _seed_batch(factory, tenant: str) -> tuple[str, str]:  # noqa: ANN001
    """Stage a clean upload under ``tenant`` context; return (batch_id, staged_record_id)."""
    session = factory()
    try:
        set_tenant_context(session, tenant)
        source = register_data_source(
            session, tenant_id=tenant, code="S", name="S", source_type="upload", actor_id="a"
        )
        register_dq_rule(
            session,
            tenant_id=tenant,
            code="CCY",
            name="r",
            rule_type="ALLOWED_VALUES",
            actor_id="a",
            params={"column": "ccy", "allowed": ["USD"]},
            target_entity_type=STAGING_ROW_TARGET,
        )
        batch = stage_upload(
            session,
            tenant_id=tenant,
            data_source_id=source.id,
            filename="p.csv",
            content_type="text/csv",
            raw_bytes=b"ccy\nUSD\n",
            actor_id="a",
        )
        session.commit()
        staged_id = session.execute(
            text("SELECT id FROM ingestion_staged_record WHERE batch_id = CAST(:b AS uuid)"),
            {"b": batch.id},
        ).scalar_one()
        return batch.id, str(staged_id)
    finally:
        session.close()


def test_batch_and_staged_tenant_isolation(app_url: str) -> None:
    # Cross-tenant payload invisibility — the highest-value RLS proof (DC-2+ raw client data).
    engine = make_engine(app_url, poolclass=NullPool)
    factory = make_session_factory(engine)
    a, b = str(uuid.uuid4()), str(uuid.uuid4())
    _seed_batch(factory, a)
    _seed_batch(factory, b)
    session = factory()
    try:
        set_tenant_context(session, a)
        batch_tenants = {
            str(r[0])
            for r in session.execute(text("SELECT DISTINCT tenant_id FROM ingestion_batch"))
        }
        staged_tenants = {
            str(r[0])
            for r in session.execute(text("SELECT DISTINCT tenant_id FROM ingestion_staged_record"))
        }
        assert a in batch_tenants and b not in batch_tenants
        assert staged_tenants == {a}  # tenant B's raw staged rows are invisible to A
    finally:
        session.close()
        engine.dispose()


def test_batch_no_context_fails_closed(app_url: str) -> None:
    engine = make_engine(app_url, poolclass=NullPool)
    factory = make_session_factory(engine)
    session = factory()
    try:
        session.add(
            IngestionBatch(
                tenant_id=str(uuid.uuid4()),
                data_source_id=str(uuid.uuid4()),
                filename="x.csv",
                byte_size=1,
                status="RECEIVED",
            )
        )
        with pytest.raises(ProgrammingError) as exc:
            session.flush()  # no app.current_tenant -> RLS WITH CHECK rejects
        assert _is_rls_violation(exc.value)
        session.rollback()
        assert session.execute(text("SELECT count(*) FROM ingestion_batch")).scalar() == 0
    finally:
        session.close()
        engine.dispose()


def test_tenant_mismatch_write_denied(app_url: str) -> None:
    engine = make_engine(app_url, poolclass=NullPool)
    factory = make_session_factory(engine)
    session = factory()
    try:
        a, b = str(uuid.uuid4()), str(uuid.uuid4())
        set_tenant_context(session, a)
        session.add(
            IngestionBatch(
                tenant_id=b,  # forged tenant under context A -> WITH CHECK rejects
                data_source_id=str(uuid.uuid4()),
                filename="x.csv",
                byte_size=1,
                status="RECEIVED",
            )
        )
        with pytest.raises(ProgrammingError) as exc:
            session.flush()
        assert _is_rls_violation(exc.value)
        session.rollback()
    finally:
        session.close()
        engine.dispose()


def test_staged_record_append_only_at_db(app_url: str) -> None:
    engine = make_engine(app_url, poolclass=NullPool)
    factory = make_session_factory(engine)
    tenant = str(uuid.uuid4())
    _, staged_id = _seed_batch(factory, tenant)
    session = factory()
    try:
        set_tenant_context(session, tenant)
        with pytest.raises(ProgrammingError) as exc:
            session.execute(
                text(
                    "UPDATE ingestion_staged_record SET row_number = 9 WHERE id = CAST(:i AS uuid)"
                ),
                {"i": staged_id},
            )
        assert _is_append_only_violation(exc.value)
        session.rollback()
        set_tenant_context(session, tenant)
        with pytest.raises(ProgrammingError) as exc:
            session.execute(
                text("DELETE FROM ingestion_staged_record WHERE id = CAST(:i AS uuid)"),
                {"i": staged_id},
            )
        assert _is_append_only_violation(exc.value)
        session.rollback()
    finally:
        session.close()
        engine.dispose()


def test_batch_is_mutable_at_db(app_url: str) -> None:
    # Negative control (CalculationRun precedent): batch is NOT append-only -> UPDATE succeeds.
    engine = make_engine(app_url, poolclass=NullPool)
    factory = make_session_factory(engine)
    tenant = str(uuid.uuid4())
    batch_id, _ = _seed_batch(factory, tenant)
    session = factory()
    try:
        set_tenant_context(session, tenant)
        result = session.execute(
            text("UPDATE ingestion_batch SET status = 'COMPLETED' WHERE id = CAST(:i AS uuid)"),
            {"i": batch_id},
        )
        assert result.rowcount == 1
        session.rollback()
    finally:
        session.close()
        engine.dispose()


def test_cross_tenant_batch_lookup_returns_none(app_url: str) -> None:
    engine = make_engine(app_url, poolclass=NullPool)
    factory = make_session_factory(engine)
    a = str(uuid.uuid4())
    b_batch_id, _ = _seed_batch(factory, str(uuid.uuid4()))
    session = factory()
    try:
        set_tenant_context(session, a)
        assert session.get(IngestionBatch, b_batch_id) is None  # RLS-hidden -> 404
    finally:
        session.close()
        engine.dispose()


def test_ops_role_has_no_grant_on_ingestion_tables() -> None:
    engine = make_engine(URL, poolclass=NullPool)
    try:
        with engine.connect() as conn:
            for table in ("ingestion_batch", "ingestion_staged_record"):
                for priv in ("SELECT", "INSERT", "UPDATE", "DELETE"):
                    has = conn.execute(
                        text("SELECT has_table_privilege('irp_ops', :t, :p)"),
                        {"t": table, "p": priv},
                    ).scalar()
                    assert has is False, f"irp_ops unexpectedly has {priv} on {table}"
    finally:
        engine.dispose()
