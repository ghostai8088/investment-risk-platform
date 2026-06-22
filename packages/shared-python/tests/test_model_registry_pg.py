"""PostgreSQL RLS tests for the model registry skeleton (P1A-2; BR-17, AD-016, AD-015).

Gated on ``IRP_TEST_DATABASE_URL`` (a superuser URL). RLS enforcement runs under a constrained,
**non-superuser, non-BYPASSRLS** ``irp_app`` role. Applies the P1A-1 CI lessons: native ``uuid``
columns -> ORM/``GUID`` for inserts, ``CAST(:i AS uuid)`` for raw ``text()`` by-id mutations,
``str()`` for raw ``uuid`` reads; assert SQLSTATE 42501 via ``_is_rls_violation``.
"""

from __future__ import annotations

import os
import uuid

import pytest
from sqlalchemy import select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.pool import NullPool

from irp_shared.db.session import make_engine, make_session_factory
from irp_shared.db.tenant import set_tenant_context
from irp_shared.model.models import Model, ModelAssumption, ModelLimitation, ModelVersion
from irp_shared.model.service import ModelNotVisible, register_model, register_model_version

URL = os.environ.get("IRP_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="requires PostgreSQL (IRP_TEST_DATABASE_URL)")


def _is_rls_violation(error: ProgrammingError) -> bool:
    return (
        getattr(error.orig, "sqlstate", None) == "42501"
        or "row-level security" in str(error).lower()
    )


def _is_append_only_violation(error: ProgrammingError) -> bool:
    # The append-only trigger RAISE EXCEPTION is SQLSTATE P0001 — distinct from a 42501 privilege
    # denial, so the test proves the TRIGGER fired (not merely that the role lacks UPDATE/DELETE).
    return getattr(error.orig, "sqlstate", None) == "P0001" or "append-only" in str(error).lower()


@pytest.fixture(scope="module")
def app_url() -> str:
    """Constrained non-superuser app role with only the grants the registry path needs."""
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
        # UPDATE/DELETE on the registry tables so the EV head is genuinely mutable AND the IA
        # tables' append-only rejection is the TRIGGER (P0001), not a privilege denial (42501).
        for tbl in ("model", "model_version", "model_assumption", "model_limitation"):
            conn.execute(text(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {tbl} TO irp_app"))
        conn.execute(text("GRANT SELECT, INSERT ON audit_event TO irp_app"))
    superuser.dispose()
    return (
        make_url(URL)
        .set(username="irp_app", password="ci_app_pw")
        .render_as_string(hide_password=False)
    )


def _seed_model(factory, tenant: str, code: str) -> str:  # noqa: ANN001
    session = factory()
    try:
        set_tenant_context(session, tenant)
        model = register_model(
            session, tenant_id=tenant, code=code, name="n", model_type="STATISTICAL", actor_id="a"
        )
        session.commit()
        return model.id
    finally:
        session.close()


def _seed_version(factory, tenant: str, code: str) -> tuple[str, str]:  # noqa: ANN001
    session = factory()
    try:
        set_tenant_context(session, tenant)
        model = register_model(
            session, tenant_id=tenant, code=code, name="n", model_type="STATISTICAL", actor_id="a"
        )
        version = register_model_version(session, model=model, version_label="1.0.0", actor_id="a")
        session.commit()
        return model.id, version.id
    finally:
        session.close()


def test_model_tenant_isolation(app_url: str) -> None:
    engine = make_engine(app_url, poolclass=NullPool)
    factory = make_session_factory(engine)
    a, b = str(uuid.uuid4()), str(uuid.uuid4())
    _seed_model(factory, a, "A_M")
    _seed_model(factory, b, "B_M")
    session = factory()
    try:
        set_tenant_context(session, a)
        codes = {r[0] for r in session.execute(text("SELECT code FROM model"))}
        assert "A_M" in codes and "B_M" not in codes
    finally:
        session.close()
        engine.dispose()


def test_model_version_tenant_isolation(app_url: str) -> None:
    engine = make_engine(app_url, poolclass=NullPool)
    factory = make_session_factory(engine)
    a, b = str(uuid.uuid4()), str(uuid.uuid4())
    _seed_version(factory, a, "A_MV")
    _seed_version(factory, b, "B_MV")
    session = factory()
    try:
        set_tenant_context(session, a)
        # psycopg3 returns native uuid columns as uuid.UUID -> stringify to compare with str ids.
        tenants = {
            str(r[0]) for r in session.execute(text("SELECT DISTINCT tenant_id FROM model_version"))
        }
        assert a in tenants and b not in tenants
    finally:
        session.close()
        engine.dispose()


def test_model_no_context_fails_closed(app_url: str) -> None:
    engine = make_engine(app_url, poolclass=NullPool)
    factory = make_session_factory(engine)
    session = factory()
    try:
        session.add(Model(tenant_id=str(uuid.uuid4()), code="X", name="n", model_type="X"))
        with pytest.raises(ProgrammingError) as exc:
            session.flush()  # no app.current_tenant -> RLS rejects
        assert _is_rls_violation(exc.value)
        session.rollback()
        assert session.execute(text("SELECT count(*) FROM model")).scalar() == 0
    finally:
        session.close()
        engine.dispose()


def test_model_version_no_context_fails_closed(app_url: str) -> None:
    # Child table: seed a real parent (FK satisfied) so the rejection is RLS (42501), not FK.
    engine = make_engine(app_url, poolclass=NullPool)
    factory = make_session_factory(engine)
    tenant = str(uuid.uuid4())
    model_id = _seed_model(factory, tenant, "PARENT")
    session = factory()
    try:
        session.add(ModelVersion(tenant_id=tenant, model_id=model_id, version_label="9.9.9"))
        with pytest.raises(ProgrammingError) as exc:
            session.flush()  # valid FK, but no tenant context -> RLS 42501
        assert _is_rls_violation(exc.value)
        session.rollback()
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
            register_model(
                session, tenant_id=b, code="X", name="n", model_type="X", actor_id="a"
            )  # WITH CHECK rejects tenant b under context a
        assert _is_rls_violation(exc.value)
        session.rollback()
    finally:
        session.close()
        engine.dispose()


def test_cross_tenant_parent_reference_fails_closed(app_url: str) -> None:
    engine = make_engine(app_url, poolclass=NullPool)
    factory = make_session_factory(engine)
    a, b = str(uuid.uuid4()), str(uuid.uuid4())
    b_model_id = _seed_model(factory, b, "B_ONLY")
    session = factory()
    try:
        set_tenant_context(session, a)
        phantom = Model(tenant_id=b, code="B_ONLY", name="n", model_type="X")
        phantom.id = b_model_id  # a tenant-B model id, invisible under context A
        with pytest.raises(ModelNotVisible):
            register_model_version(session, model=phantom, version_label="1.0.0", actor_id="a")
    finally:
        session.close()
        engine.dispose()


def test_ia_tables_append_only_at_db(app_url: str) -> None:
    # irp_app HAS update/delete grants, so a rejection here is the append-only TRIGGER (P0001),
    # not a privilege denial (42501) — proving the DB-layer immutability of all three IA tables.
    engine = make_engine(app_url, poolclass=NullPool)
    factory = make_session_factory(engine)
    tenant = str(uuid.uuid4())
    session = factory()
    try:
        set_tenant_context(session, tenant)
        model = register_model(
            session, tenant_id=tenant, code="AO_M", name="n", model_type="X", actor_id="a"
        )
        version = register_model_version(
            session,
            model=model,
            version_label="1.0.0",
            actor_id="a",
            assumptions=["a1"],
            limitations=["l1"],
        )
        # Capture child ids before COMMIT clears the transaction-local context.
        a_id = (
            session.execute(
                select(ModelAssumption.id).where(ModelAssumption.model_version_id == version.id)
            )
            .scalars()
            .one()
        )
        l_id = (
            session.execute(
                select(ModelLimitation.id).where(ModelLimitation.model_version_id == version.id)
            )
            .scalars()
            .one()
        )
        session.commit()
        targets = {
            "model_version": (version.id, "status"),
            "model_assumption": (a_id, "category"),
            "model_limitation": (l_id, "severity"),
        }
    finally:
        session.close()

    for table, (row_id, col) in targets.items():
        session = factory()
        try:
            # Re-set context so the row is RLS-visible for the per-row trigger; CAST text->uuid.
            set_tenant_context(session, tenant)
            with pytest.raises(ProgrammingError) as exc:
                session.execute(
                    text(f"UPDATE {table} SET {col} = 'X' WHERE id = CAST(:i AS uuid)"),
                    {"i": row_id},
                )
            assert _is_append_only_violation(exc.value), f"{table} UPDATE not trigger-blocked"
            session.rollback()
            set_tenant_context(session, tenant)
            with pytest.raises(ProgrammingError) as exc:
                session.execute(
                    text(f"DELETE FROM {table} WHERE id = CAST(:i AS uuid)"), {"i": row_id}
                )
            assert _is_append_only_violation(exc.value), f"{table} DELETE not trigger-blocked"
            session.rollback()
        finally:
            session.close()
    engine.dispose()


def test_model_version_tenant_mismatch_write_denied(app_url: str) -> None:
    # WITH CHECK on a child IA table: a tenant-B version under context A is rejected (42501).
    engine = make_engine(app_url, poolclass=NullPool)
    factory = make_session_factory(engine)
    a, b = str(uuid.uuid4()), str(uuid.uuid4())
    a_model_id = _seed_model(factory, a, "A_PARENT")
    session = factory()
    try:
        set_tenant_context(session, a)
        session.add(ModelVersion(tenant_id=b, model_id=a_model_id, version_label="1.0.0"))
        with pytest.raises(ProgrammingError) as exc:
            session.flush()
        assert _is_rls_violation(exc.value)
        session.rollback()
    finally:
        session.close()
        engine.dispose()


def test_model_head_is_mutable_at_db(app_url: str) -> None:
    # EV negative-control: model is not append-only -> a raw UPDATE under context succeeds.
    engine = make_engine(app_url, poolclass=NullPool)
    factory = make_session_factory(engine)
    tenant = str(uuid.uuid4())
    model_id = _seed_model(factory, tenant, "EV_M")
    session = factory()
    try:
        set_tenant_context(session, tenant)
        result = session.execute(
            text("UPDATE model SET tier = 'Tier 2' WHERE id = CAST(:i AS uuid)"), {"i": model_id}
        )
        assert result.rowcount == 1  # no append-only trigger on the EV head
        session.rollback()
    finally:
        session.close()
        engine.dispose()


def test_cross_tenant_model_lookup_returns_none(app_url: str) -> None:
    # Basis for the endpoint's indistinguishable 404: tenant A cannot resolve tenant B's model id.
    engine = make_engine(app_url, poolclass=NullPool)
    factory = make_session_factory(engine)
    a, b = str(uuid.uuid4()), str(uuid.uuid4())
    b_model_id = _seed_model(factory, b, "B_HIDDEN")
    session = factory()
    try:
        set_tenant_context(session, a)
        assert session.get(Model, b_model_id) is None  # RLS-hidden -> 404
    finally:
        session.close()
        engine.dispose()


def test_ops_role_has_no_grant_on_model_tables() -> None:
    engine = make_engine(URL, poolclass=NullPool)
    try:
        with engine.connect() as conn:
            for table in ("model", "model_version", "model_assumption", "model_limitation"):
                for priv in ("SELECT", "INSERT", "UPDATE", "DELETE"):
                    has = conn.execute(
                        text("SELECT has_table_privilege('irp_ops', :t, :p)"),
                        {"t": table, "p": priv},
                    ).scalar()
                    assert has is False, f"irp_ops unexpectedly has {priv} on {table}"
    finally:
        engine.dispose()
