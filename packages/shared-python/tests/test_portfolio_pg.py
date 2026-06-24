"""PostgreSQL SYMMETRIC-RLS tests for P1C-1 portfolio (PROPRIETARY, EV; ABAC scope anchor).

Gated on ``IRP_TEST_DATABASE_URL``; enforcement runs under the constrained non-superuser ``irp_app``
role (NOSUPERUSER NOBYPASSRLS). Proves: cross-tenant invisibility + no-context->zero rows; the
cross-tenant ``parent_portfolio_id`` guard is the SERVICE-LAYER predicate pre-commit; the RLS ``WITH
CHECK`` backstop denies a forged-tenant write (42501); the POSITIVE symmetric-policy + FORCE-RLS
assertion AND the unchanged closed-hybrid-set; EV-mutability (amend) + descendant-subtree tenant
isolation under FORCE RLS. Native-uuid trap (ORM/GUID inserts; raw reads via ``str()``).
"""

from __future__ import annotations

import os
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.pool import NullPool

from irp_shared.audit.service import verify_chain
from irp_shared.db.session import make_engine, make_session_factory
from irp_shared.db.tenant import set_tenant_context
from irp_shared.entitlement.bootstrap import SYSTEM_TENANT_ID
from irp_shared.portfolio import (
    PortfolioActor,
    PortfolioNotVisible,
    create_portfolio,
    resolve_descendants,
    resolve_portfolio,
    update_portfolio,
)

URL = os.environ.get("IRP_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="requires PostgreSQL (IRP_TEST_DATABASE_URL)")

_P1C1 = ("portfolio",)
_P1B1_HYBRID = ("currency", "calendar", "calendar_holiday", "rating_scale", "rating_grade")
_RAILS = ("data_source", "lineage_edge")
_ACT = PortfolioActor(actor_id="a")


def _is_rls_violation(error: ProgrammingError) -> bool:
    return (
        getattr(error.orig, "sqlstate", None) == "42501"
        or "row-level security" in str(error).lower()
    )


@pytest.fixture(scope="module")
def app_url() -> str:
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
        for table in (*_P1C1, *_RAILS):
            conn.execute(text(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO irp_app"))
        conn.execute(text("GRANT SELECT, INSERT ON audit_event TO irp_app"))
    superuser.dispose()
    return (
        make_url(URL)
        .set(username="irp_app", password="ci_app_pw")
        .render_as_string(hide_password=False)
    )


def _seed_node(factory, tenant: str, code: str, **kw) -> str:  # noqa: ANN001, ANN003
    session = factory()
    try:
        set_tenant_context(session, tenant)
        node = create_portfolio(
            session, tenant_id=tenant, code=code, name=code, node_type="FUND", actor=_ACT, **kw
        )
        session.commit()
        return node.id
    finally:
        session.close()


def test_tenant_isolation(app_url: str) -> None:
    engine = make_engine(app_url, poolclass=NullPool)
    factory = make_session_factory(engine)
    a, b = str(uuid.uuid4()), str(uuid.uuid4())
    try:
        _seed_node(factory, a, "A_P")
        _seed_node(factory, b, "B_P")
        session = factory()
        try:
            set_tenant_context(session, a)
            tenants = {
                str(r[0]) for r in session.execute(text("SELECT DISTINCT tenant_id FROM portfolio"))
            }
            assert tenants == {a}
        finally:
            session.close()
    finally:
        engine.dispose()


def test_no_context_read_returns_zero_rows(app_url: str) -> None:
    engine = make_engine(app_url, poolclass=NullPool)
    factory = make_session_factory(engine)
    try:
        _seed_node(factory, str(uuid.uuid4()), "P")
        session = factory()
        try:
            assert session.execute(text("SELECT count(*) FROM portfolio")).scalar_one() == 0
        finally:
            session.close()
    finally:
        engine.dispose()


def test_cross_tenant_parent_rejected_service_layer(app_url: str) -> None:
    engine = make_engine(app_url, poolclass=NullPool)
    factory = make_session_factory(engine)
    a, b = str(uuid.uuid4()), str(uuid.uuid4())
    b_parent = _seed_node(factory, b, "B_PARENT")
    session = factory()
    try:
        set_tenant_context(session, a)
        with pytest.raises(PortfolioNotVisible):  # service predicate, NOT a 42501
            create_portfolio(
                session,
                tenant_id=a,
                code="A_CHILD",
                name="c",
                node_type="ACCOUNT",
                actor=_ACT,
                parent_portfolio_id=b_parent,
            )
        session.rollback()
    finally:
        session.close()
        engine.dispose()


def test_forged_tenant_update_denied(app_url: str) -> None:
    # The RLS WITH CHECK backstop: a raw UPDATE re-stamping tenant_id to a foreign tenant is denied.
    engine = make_engine(app_url, poolclass=NullPool)
    factory = make_session_factory(engine)
    a, b = str(uuid.uuid4()), str(uuid.uuid4())
    node_id = _seed_node(factory, a, "P")
    session = factory()
    try:
        set_tenant_context(session, a)
        with pytest.raises(ProgrammingError) as exc:
            session.execute(
                text(
                    "UPDATE portfolio SET tenant_id = CAST(:b AS uuid) WHERE id = CAST(:i AS uuid)"
                ),
                {"b": b, "i": node_id},
            )
        assert _is_rls_violation(exc.value)
        session.rollback()
    finally:
        session.close()
        engine.dispose()


def test_policies_symmetric_and_force_rls(app_url: str) -> None:
    engine = make_engine(app_url, poolclass=NullPool)
    try:
        with engine.connect() as conn:
            for table in _P1C1:
                qual, with_check = conn.execute(
                    text(
                        "SELECT qual, with_check FROM pg_policies "
                        "WHERE schemaname='public' AND tablename=:t"
                    ),
                    {"t": table},
                ).one()
                assert SYSTEM_TENANT_ID not in qual, f"{table} must NOT be hybrid"
                assert SYSTEM_TENANT_ID not in with_check
                enabled, forced = conn.execute(
                    text(
                        "SELECT relrowsecurity, relforcerowsecurity FROM pg_class "
                        "WHERE relname = :t AND relnamespace = 'public'::regnamespace"
                    ),
                    {"t": table},
                ).one()
                assert enabled is True and forced is True, f"{table}: FORCE RLS must be on"
    finally:
        engine.dispose()


def test_closed_hybrid_set_unchanged(app_url: str) -> None:
    engine = make_engine(app_url, poolclass=NullPool)
    try:
        with engine.connect() as conn:
            hybrid = {
                r[0]
                for r in conn.execute(
                    text(
                        "SELECT tablename FROM pg_policies "
                        "WHERE schemaname='public' AND qual LIKE :p"
                    ),
                    {"p": f"%{SYSTEM_TENANT_ID}%"},
                )
            }
            assert hybrid == set(_P1B1_HYBRID), f"hybrid set drifted: {hybrid}"
    finally:
        engine.dispose()


def test_ev_amend_and_subtree_under_rls(app_url: str) -> None:
    engine = make_engine(app_url, poolclass=NullPool)
    factory = make_session_factory(engine)
    a = str(uuid.uuid4())
    session = factory()
    try:
        set_tenant_context(session, a)
        root = create_portfolio(
            session, tenant_id=a, code="ROOT", name="R", node_type="PORTFOLIO", actor=_ACT
        )
        child = create_portfolio(
            session,
            tenant_id=a,
            code="CHILD",
            name="C",
            node_type="FUND",
            actor=_ACT,
            parent_portfolio_id=root.id,
        )
        # EV amend under FORCE RLS (the in-place UPDATE succeeds; record_version bumps).
        update_portfolio(session, child, actor=_ACT, status="CLOSED")
        session.commit()
        set_tenant_context(session, a)  # re-set after commit (GUC cleared) before read-back
        root = resolve_portfolio(session, root.id, acting_tenant=a)
        desc = resolve_descendants(session, root, acting_tenant=a)
        assert {n.id for n in desc} == {child.id}
        n = session.execute(
            text("SELECT count(*) FROM audit_event WHERE event_type = 'PORTFOLIO.UPDATE'")
        ).scalar_one()
        assert n == 1
        assert verify_chain(session, a).ok is True
    finally:
        session.close()
        engine.dispose()
