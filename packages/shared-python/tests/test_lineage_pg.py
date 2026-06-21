"""PostgreSQL RLS tests for the lineage skeleton (P1A-1; BR-17, AD-016, AD-015).

Gated on ``IRP_TEST_DATABASE_URL`` (a superuser URL). RLS enforcement runs under a constrained,
**non-superuser, non-BYPASSRLS** ``irp_app`` role (superusers bypass RLS even under FORCE), created
here with an ephemeral CI-only credential and granted only what the app path needs.
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
from irp_shared.entitlement.bootstrap import SYSTEM_TENANT_ID
from irp_shared.lineage.models import DataSource, LineageEdge
from irp_shared.lineage.service import (
    DataSourceNotVisible,
    record_lineage,
    register_data_source,
)

URL = os.environ.get("IRP_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="requires PostgreSQL (IRP_TEST_DATABASE_URL)")


def _is_rls_violation(error: ProgrammingError) -> bool:
    return (
        getattr(error.orig, "sqlstate", None) == "42501"  # insufficient_privilege
        or "row-level security" in str(error).lower()
    )


@pytest.fixture(scope="module")
def app_url() -> str:
    """Constrained non-superuser app role with only the grants the lineage path needs."""
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
        conn.execute(text("GRANT SELECT, INSERT ON data_source TO irp_app"))
        conn.execute(text("GRANT SELECT, INSERT ON lineage_edge TO irp_app"))
        conn.execute(text("GRANT SELECT, INSERT ON audit_event TO irp_app"))
    superuser.dispose()
    return (
        make_url(URL)
        .set(username="irp_app", password="ci_app_pw")
        .render_as_string(hide_password=False)
    )


def _seed_source(factory, tenant: str, code: str) -> str:  # noqa: ANN001
    session = factory()
    try:
        set_tenant_context(session, tenant)
        src = register_data_source(
            session, tenant_id=tenant, code=code, name="n", source_type="INTERNAL", actor_id="a"
        )
        session.commit()
        return src.id
    finally:
        session.close()


def test_data_source_tenant_isolation(app_url: str) -> None:
    engine = make_engine(app_url, poolclass=NullPool)
    factory = make_session_factory(engine)
    a, b = str(uuid.uuid4()), str(uuid.uuid4())
    _seed_source(factory, a, "A_SRC")
    _seed_source(factory, b, "B_SRC")
    session = factory()
    try:
        set_tenant_context(session, a)
        codes = {r[0] for r in session.execute(text("SELECT code FROM data_source"))}
        assert "A_SRC" in codes
        assert "B_SRC" not in codes  # RLS isolates
    finally:
        session.close()
        engine.dispose()


def test_lineage_edge_tenant_isolation(app_url: str) -> None:
    engine = make_engine(app_url, poolclass=NullPool)
    factory = make_session_factory(engine)
    a, b = str(uuid.uuid4()), str(uuid.uuid4())
    for tenant in (a, b):
        sid = _seed_source(factory, tenant, f"SRC_{tenant[:8]}")
        session = factory()
        try:
            set_tenant_context(session, tenant)
            src = session.get(DataSource, sid)
            record_lineage(
                session,
                source=src,
                target_entity_type="synthetic.t",
                target_entity_id=str(uuid.uuid4()),
            )
            session.commit()
        finally:
            session.close()
    session = factory()
    try:
        set_tenant_context(session, a)
        # psycopg3 returns native uuid columns as uuid.UUID -> stringify to compare with str ids.
        tenants = {
            str(r[0]) for r in session.execute(text("SELECT DISTINCT tenant_id FROM lineage_edge"))
        }
        assert a in tenants
        assert b not in tenants  # RLS isolates
    finally:
        session.close()
        engine.dispose()


def test_no_context_fails_closed(app_url: str) -> None:
    engine = make_engine(app_url, poolclass=NullPool)
    factory = make_session_factory(engine)
    session = factory()
    try:
        with pytest.raises(ProgrammingError) as exc:
            register_data_source(
                session,
                tenant_id=str(uuid.uuid4()),
                code="X",
                name="n",
                source_type="INTERNAL",
                actor_id="a",
            )  # no app.current_tenant -> RLS rejects the INSERT
        assert _is_rls_violation(exc.value)
        session.rollback()
        assert session.execute(text("SELECT count(*) FROM data_source")).scalar() == 0
    finally:
        session.close()
        engine.dispose()


def test_lineage_edge_no_context_fails_closed(app_url: str) -> None:
    # T22/AC-5: an INSERT into lineage_edge with no app.current_tenant is rejected (42501).
    engine = make_engine(app_url, poolclass=NullPool)
    factory = make_session_factory(engine)
    session = factory()
    try:
        # ORM insert (GUID type binds uuid columns correctly); no app.current_tenant -> RLS rejects.
        session.add(
            LineageEdge(
                tenant_id=str(uuid.uuid4()),
                source_type="data_source",
                source_id=str(uuid.uuid4()),
                target_entity_type="synthetic.t",
                target_entity_id=str(uuid.uuid4()),
                edge_kind="ORIGIN",
            )
        )
        with pytest.raises(ProgrammingError) as exc:
            session.flush()
        assert _is_rls_violation(exc.value)
        session.rollback()
        assert session.execute(text("SELECT count(*) FROM lineage_edge")).scalar() == 0
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
        with pytest.raises(ProgrammingError) as exc:
            # WITH CHECK rejects inserting a row for tenant b under context a.
            register_data_source(
                session, tenant_id=b, code="X", name="n", source_type="INTERNAL", actor_id="a"
            )
        assert _is_rls_violation(exc.value)
        session.rollback()
    finally:
        session.close()
        engine.dispose()


def test_cross_tenant_source_reference_fails_closed(app_url: str) -> None:
    engine = make_engine(app_url, poolclass=NullPool)
    factory = make_session_factory(engine)
    a, b = str(uuid.uuid4()), str(uuid.uuid4())
    b_source_id = _seed_source(factory, b, "B_ONLY")
    session = factory()
    try:
        set_tenant_context(session, a)
        phantom = DataSource(tenant_id=b, code="B_ONLY", name="n", source_type="INTERNAL")
        phantom.id = b_source_id  # a tenant-B source id, invisible under context A
        with pytest.raises(DataSourceNotVisible):
            record_lineage(
                session,
                source=phantom,
                target_entity_type="synthetic.t",
                target_entity_id=str(uuid.uuid4()),
            )
    finally:
        session.close()
        engine.dispose()


def test_cross_tenant_edge_lookup_returns_none(app_url: str) -> None:
    # The GET endpoint's RLS-scoped lookup: a tenant-A principal cannot resolve a tenant-B edge id
    # (basis for the indistinguishable 404).
    engine = make_engine(app_url, poolclass=NullPool)
    factory = make_session_factory(engine)
    a, b = str(uuid.uuid4()), str(uuid.uuid4())
    b_src = _seed_source(factory, b, "B_SRC2")
    session = factory()
    try:
        set_tenant_context(session, b)
        edge = record_lineage(
            session,
            source=session.get(DataSource, b_src),
            target_entity_type="synthetic.t",
            target_entity_id=str(uuid.uuid4()),
        )
        session.commit()
        b_edge_id = edge.id
    finally:
        session.close()
    session = factory()
    try:
        set_tenant_context(session, a)
        # ORM lookup (mirrors the endpoint; GUID type binds the uuid): RLS hides tenant-B's edge.
        found = session.get(LineageEdge, b_edge_id)
        assert found is None  # RLS-hidden -> endpoint returns 404
    finally:
        session.close()
        engine.dispose()


def test_lineage_edge_append_only_at_db(app_url: str) -> None:
    engine = make_engine(app_url, poolclass=NullPool)
    factory = make_session_factory(engine)
    tenant = str(uuid.uuid4())
    sid = _seed_source(factory, tenant, "AO_SRC")
    session = factory()
    try:
        set_tenant_context(session, tenant)
        edge = record_lineage(
            session,
            source=session.get(DataSource, sid),
            target_entity_type="synthetic.t",
            target_entity_id=str(uuid.uuid4()),
        )
        session.commit()
        edge_id = edge.id
        # Re-set context: commit cleared the transaction-local GUC, and the row must be VISIBLE
        # (RLS) for the per-row append-only trigger to fire on the attempted mutation.
        # Raw UPDATE/DELETE bypass the ORM guard but hit the DB append-only trigger.
        set_tenant_context(session, tenant)
        with pytest.raises(ProgrammingError):
            session.execute(
                text("UPDATE lineage_edge SET edge_kind = 'X' WHERE id = CAST(:i AS uuid)"),
                {"i": edge_id},
            )
        session.rollback()
        set_tenant_context(session, tenant)
        with pytest.raises(ProgrammingError):
            session.execute(
                text("DELETE FROM lineage_edge WHERE id = CAST(:i AS uuid)"), {"i": edge_id}
            )
        session.rollback()
    finally:
        session.close()
        engine.dispose()


def test_ops_role_has_no_grant_on_lineage_tables() -> None:
    engine = make_engine(URL, poolclass=NullPool)
    try:
        with engine.connect() as conn:
            for table in ("data_source", "lineage_edge"):
                for priv in ("SELECT", "INSERT", "UPDATE", "DELETE"):
                    has = conn.execute(
                        text("SELECT has_table_privilege('irp_ops', :t, :p)"),
                        {"t": table, "p": priv},
                    ).scalar()
                    assert has is False, f"irp_ops unexpectedly has {priv} on {table}"
    finally:
        engine.dispose()


def test_system_tenant_source_writable_only_under_system_context(app_url: str) -> None:
    engine = make_engine(app_url, poolclass=NullPool)
    factory = make_session_factory(engine)
    try:
        # Under a normal tenant, a SYSTEM_TENANT_ID row is rejected by WITH CHECK.
        session = factory()
        try:
            set_tenant_context(session, str(uuid.uuid4()))
            with pytest.raises(ProgrammingError) as exc:
                register_data_source(
                    session,
                    tenant_id=SYSTEM_TENANT_ID,
                    code="GLOBAL_X",
                    name="g",
                    source_type="VENDOR_FEED",
                    actor_id="a",
                )
            assert _is_rls_violation(exc.value)
            session.rollback()
        finally:
            session.close()
        # Under the system tenant context it succeeds.
        session = factory()
        try:
            set_tenant_context(session, SYSTEM_TENANT_ID)
            src = register_data_source(
                session,
                tenant_id=SYSTEM_TENANT_ID,
                code="GLOBAL_OK",
                name="g",
                source_type="VENDOR_FEED",
                actor_id="a",
            )
            session.commit()
            assert src.tenant_id == SYSTEM_TENANT_ID
        finally:
            session.close()
    finally:
        engine.dispose()
