"""PostgreSQL RLS tests for the data quality skeleton (P1A-3; BR-17, AD-016, AD-015).

Gated on ``IRP_TEST_DATABASE_URL`` (a superuser URL). RLS enforcement runs under a constrained,
**non-superuser, non-BYPASSRLS** ``irp_app`` role. Applies the P1A-1/P1A-2 CI lessons: native
``uuid`` → ORM/``GUID`` for inserts, ``CAST(:i AS uuid)`` for raw by-id mutations, ``str()`` for raw
``uuid`` reads; assert SQLSTATE 42501 (``_is_rls_violation``); IA append-only proven via the P0001
trigger (``_is_append_only_violation``) with ``irp_app`` granted UPDATE/DELETE on the result table.
"""

from __future__ import annotations

import os
import uuid

import pytest
from sqlalchemy import select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.pool import NullPool

from irp_shared.db.integrity import resolve_or_insert
from irp_shared.db.session import make_engine, make_session_factory
from irp_shared.db.tenant import set_tenant_context
from irp_shared.dq.models import DataQualityResult, DataQualityRule
from irp_shared.dq.service import (
    DQReferenceNotVisible,
    QualityCheckFailedError,
    assert_passed_quality_checks,
    register_dq_rule,
    run_quality_check,
)
from irp_shared.entitlement.bootstrap import SYSTEM_TENANT_ID

URL = os.environ.get("IRP_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="requires PostgreSQL (IRP_TEST_DATABASE_URL)")


def _is_rls_violation(error: ProgrammingError) -> bool:
    return (
        getattr(error.orig, "sqlstate", None) == "42501"
        or "row-level security" in str(error).lower()
    )


def _is_append_only_violation(error: ProgrammingError) -> bool:
    return getattr(error.orig, "sqlstate", None) == "P0001" or "append-only" in str(error).lower()


@pytest.fixture(scope="module")
def app_url() -> str:
    """Constrained non-superuser app role; UPDATE/DELETE on the IA result so its append-only
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
        conn.execute(text("GRANT SELECT, INSERT, UPDATE, DELETE ON data_quality_rule TO irp_app"))
        conn.execute(text("GRANT SELECT, INSERT, UPDATE, DELETE ON data_quality_result TO irp_app"))
        conn.execute(text("GRANT SELECT, INSERT ON audit_event TO irp_app"))
    superuser.dispose()
    return (
        make_url(URL)
        .set(username="irp_app", password="ci_app_pw")
        .render_as_string(hide_password=False)
    )


def _seed_rule(factory, tenant: str, code: str) -> str:  # noqa: ANN001
    session = factory()
    try:
        set_tenant_context(session, tenant)
        rule = register_dq_rule(
            session,
            tenant_id=tenant,
            code=code,
            name="n",
            rule_type="NOT_NULL",
            actor_id="a",
            params={"column": "x"},
        )
        session.commit()
        return rule.id
    finally:
        session.close()


def _seed_result(factory, tenant: str, code: str) -> str:  # noqa: ANN001
    session = factory()
    try:
        set_tenant_context(session, tenant)
        rule = register_dq_rule(
            session,
            tenant_id=tenant,
            code=code,
            name="n",
            rule_type="NOT_NULL",
            actor_id="a",
            params={"column": "x"},
        )
        result = run_quality_check(session, rule=rule, dataset=[{"x": 1}], actor_id="a")
        session.commit()
        return result.id
    finally:
        session.close()


def test_rule_tenant_isolation(app_url: str) -> None:
    engine = make_engine(app_url, poolclass=NullPool)
    factory = make_session_factory(engine)
    a, b = str(uuid.uuid4()), str(uuid.uuid4())
    _seed_rule(factory, a, "A_R")
    _seed_rule(factory, b, "B_R")
    session = factory()
    try:
        set_tenant_context(session, a)
        codes = {r[0] for r in session.execute(text("SELECT code FROM data_quality_rule"))}
        assert "A_R" in codes and "B_R" not in codes
    finally:
        session.close()
        engine.dispose()


def test_result_tenant_isolation(app_url: str) -> None:
    # Includes the cross-tenant payload-invisibility proof (detail/tenant_id not visible to A).
    engine = make_engine(app_url, poolclass=NullPool)
    factory = make_session_factory(engine)
    a, b = str(uuid.uuid4()), str(uuid.uuid4())
    _seed_result(factory, a, "A_RES")
    _seed_result(factory, b, "B_RES")
    session = factory()
    try:
        set_tenant_context(session, a)
        tenants = {
            str(r[0])
            for r in session.execute(text("SELECT DISTINCT tenant_id FROM data_quality_result"))
        }
        assert a in tenants and b not in tenants
    finally:
        session.close()
        engine.dispose()


def test_rule_no_context_fails_closed(app_url: str) -> None:
    engine = make_engine(app_url, poolclass=NullPool)
    factory = make_session_factory(engine)
    session = factory()
    try:
        session.add(
            DataQualityRule(tenant_id=str(uuid.uuid4()), code="X", name="n", rule_type="NOT_NULL")
        )
        with pytest.raises(ProgrammingError) as exc:
            session.flush()
        assert _is_rls_violation(exc.value)
        session.rollback()
        assert session.execute(text("SELECT count(*) FROM data_quality_rule")).scalar() == 0
    finally:
        session.close()
        engine.dispose()


def test_result_no_context_fails_closed(app_url: str) -> None:
    engine = make_engine(app_url, poolclass=NullPool)
    factory = make_session_factory(engine)
    tenant = str(uuid.uuid4())
    rule_id = _seed_rule(factory, tenant, "PARENT")
    session = factory()
    try:
        session.add(
            DataQualityResult(tenant_id=tenant, rule_id=rule_id, passed=True, outcome="PASS")
        )
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
            register_dq_rule(
                session, tenant_id=b, code="X", name="n", rule_type="NOT_NULL", actor_id="a"
            )  # WITH CHECK rejects tenant b under context a
        assert _is_rls_violation(exc.value)
        session.rollback()
    finally:
        session.close()
        engine.dispose()


def test_cross_tenant_rule_reference_fails_closed(app_url: str) -> None:
    engine = make_engine(app_url, poolclass=NullPool)
    factory = make_session_factory(engine)
    a, b = str(uuid.uuid4()), str(uuid.uuid4())
    b_rule_id = _seed_rule(factory, b, "B_ONLY")
    session = factory()
    try:
        set_tenant_context(session, a)
        phantom = DataQualityRule(tenant_id=b, code="B_ONLY", name="n", rule_type="NOT_NULL")
        phantom.id = b_rule_id  # a tenant-B rule id, invisible under context A
        with pytest.raises(DQReferenceNotVisible):
            run_quality_check(session, rule=phantom, dataset=[{"x": 1}], actor_id="a")
    finally:
        session.close()
        engine.dispose()


def test_result_append_only_at_db(app_url: str) -> None:
    engine = make_engine(app_url, poolclass=NullPool)
    factory = make_session_factory(engine)
    tenant = str(uuid.uuid4())
    result_id = _seed_result(factory, tenant, "AO_RES")
    session = factory()
    try:
        # Re-set context so the row is RLS-visible for the per-row trigger; CAST text->uuid.
        set_tenant_context(session, tenant)
        with pytest.raises(ProgrammingError) as exc:
            session.execute(
                text("UPDATE data_quality_result SET detail = 'X' WHERE id = CAST(:i AS uuid)"),
                {"i": result_id},
            )
        assert _is_append_only_violation(exc.value)
        session.rollback()
        set_tenant_context(session, tenant)
        with pytest.raises(ProgrammingError) as exc:
            session.execute(
                text("DELETE FROM data_quality_result WHERE id = CAST(:i AS uuid)"),
                {"i": result_id},
            )
        assert _is_append_only_violation(exc.value)
        session.rollback()
    finally:
        session.close()
        engine.dispose()


def test_rule_is_mutable_at_db(app_url: str) -> None:
    # EV negative-control: the rule is not append-only -> a raw UPDATE under context succeeds.
    engine = make_engine(app_url, poolclass=NullPool)
    factory = make_session_factory(engine)
    tenant = str(uuid.uuid4())
    rule_id = _seed_rule(factory, tenant, "EV_R")
    session = factory()
    try:
        set_tenant_context(session, tenant)
        result = session.execute(
            text("UPDATE data_quality_rule SET severity = 'WARNING' WHERE id = CAST(:i AS uuid)"),
            {"i": rule_id},
        )
        assert result.rowcount == 1
        session.rollback()
    finally:
        session.close()
        engine.dispose()


def test_cross_tenant_result_lookup_returns_none(app_url: str) -> None:
    engine = make_engine(app_url, poolclass=NullPool)
    factory = make_session_factory(engine)
    a = str(uuid.uuid4())
    b_result_id = _seed_result(factory, str(uuid.uuid4()), "B_HIDDEN")
    session = factory()
    try:
        set_tenant_context(session, a)
        assert session.get(DataQualityResult, b_result_id) is None  # RLS-hidden -> 404
    finally:
        session.close()
        engine.dispose()


def test_gate_is_rls_scoped(app_url: str) -> None:
    # The gate relies on RLS (no explicit tenant_id kwarg): tenant A sees its PASS and passes;
    # tenant B can't see A's result -> "no checks recorded" -> fails closed.
    engine = make_engine(app_url, poolclass=NullPool)
    factory = make_session_factory(engine)
    a, b = str(uuid.uuid4()), str(uuid.uuid4())
    target = str(uuid.uuid4())
    session = factory()
    try:
        set_tenant_context(session, a)
        rule = register_dq_rule(
            session,
            tenant_id=a,
            code="GATE",
            name="n",
            rule_type="NOT_NULL",
            actor_id="x",
            params={"column": "x"},
        )
        run_quality_check(
            session,
            rule=rule,
            dataset=[{"x": 1}],
            actor_id="x",
            target_entity_type="synthetic.t",
            target_entity_id=target,
        )
        session.commit()
    finally:
        session.close()
    session = factory()
    try:
        set_tenant_context(session, a)
        assert assert_passed_quality_checks(session, "synthetic.t", target)  # RLS-scoped pass
    finally:
        session.close()
    session = factory()
    try:
        set_tenant_context(session, b)
        with pytest.raises(QualityCheckFailedError):
            assert_passed_quality_checks(session, "synthetic.t", target)  # A's result hidden
    finally:
        session.close()
        engine.dispose()


def test_ops_role_has_no_grant_on_dq_tables() -> None:
    engine = make_engine(URL, poolclass=NullPool)
    try:
        with engine.connect() as conn:
            for table in ("data_quality_rule", "data_quality_result"):
                for priv in ("SELECT", "INSERT", "UPDATE", "DELETE"):
                    has = conn.execute(
                        text("SELECT has_table_privilege('irp_ops', :t, :p)"),
                        {"t": table, "p": priv},
                    ).scalar()
                    assert has is False, f"irp_ops unexpectedly has {priv} on {table}"
    finally:
        engine.dispose()


def test_system_tenant_rule_writable_only_under_system_context(app_url: str) -> None:
    engine = make_engine(app_url, poolclass=NullPool)
    factory = make_session_factory(engine)
    try:
        session = factory()
        try:
            set_tenant_context(session, str(uuid.uuid4()))
            with pytest.raises(ProgrammingError) as exc:
                register_dq_rule(
                    session,
                    tenant_id=SYSTEM_TENANT_ID,
                    code="GLOBAL_X",
                    name="g",
                    rule_type="NOT_NULL",
                    actor_id="a",
                )
            assert _is_rls_violation(exc.value)
            session.rollback()
        finally:
            session.close()
        session = factory()
        try:
            set_tenant_context(session, SYSTEM_TENANT_ID)
            # RD-3 OD-D: resolve-or-insert so a re-run against a dirty (unreset) local schema is a
            # no-op instead of an IntegrityError on the fixed SYSTEM-tenant code (the lineage
            # GLOBAL_OK precedent).
            rule = resolve_or_insert(
                session,
                resolve=lambda: session.execute(
                    select(DataQualityRule).where(
                        DataQualityRule.tenant_id == SYSTEM_TENANT_ID,
                        DataQualityRule.code == "GLOBAL_OK",
                    )
                ).scalar_one_or_none(),
                insert=lambda: register_dq_rule(
                    session,
                    tenant_id=SYSTEM_TENANT_ID,
                    code="GLOBAL_OK",
                    name="g",
                    rule_type="NOT_NULL",
                    actor_id="a",
                ),
            )
            session.commit()
            assert rule.tenant_id == SYSTEM_TENANT_ID
        finally:
            session.close()
        # RD-3 OD-D regression proof: a SECOND resolve-or-insert against the now-committed
        # GLOBAL_OK row must be a no-op — a real CI-exercised double-run, not just a manual local
        # one (the lineage GLOBAL_OK precedent).
        session = factory()
        try:
            set_tenant_context(session, SYSTEM_TENANT_ID)
            rule2 = resolve_or_insert(
                session,
                resolve=lambda: session.execute(
                    select(DataQualityRule).where(
                        DataQualityRule.tenant_id == SYSTEM_TENANT_ID,
                        DataQualityRule.code == "GLOBAL_OK",
                    )
                ).scalar_one_or_none(),
                insert=lambda: register_dq_rule(
                    session,
                    tenant_id=SYSTEM_TENANT_ID,
                    code="GLOBAL_OK",
                    name="g",
                    rule_type="NOT_NULL",
                    actor_id="a",
                ),
            )
            session.commit()
            assert rule2.id == rule.id  # the existing row, not a new insert
        finally:
            session.close()
    finally:
        engine.dispose()
