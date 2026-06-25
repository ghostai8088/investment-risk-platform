"""PostgreSQL SYMMETRIC-RLS + FR tests for P1C-3 position (PROPRIETARY, FR — NOT append-only).

Gated on ``IRP_TEST_DATABASE_URL``; enforcement runs under the constrained non-superuser ``irp_app``
role (NOSUPERUSER NOBYPASSRLS). Proves: cross-tenant invisibility + no-context->zero rows; the
POSITIVE
symmetric-policy + FORCE-RLS assertion AND the unchanged closed-hybrid-set; the RLS ``WITH CHECK``
backstop denies a forged-tenant INSERT (42501); the cross-tenant FK service-layer reject; FR
reconstruction under FORCE RLS; the current-head partial-unique enforced in PG; and the
**NOT-append-
only POSITIVE proof** — a raw close-out UPDATE is PERMITTED (rowcount == 1; there is no P0001
trigger),
the exact inversion of the transaction IA guard. Native-uuid trap.
"""

from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError, ProgrammingError
from sqlalchemy.pool import NullPool

from irp_shared.db.session import make_engine, make_session_factory
from irp_shared.db.tenant import set_tenant_context
from irp_shared.entitlement.bootstrap import SYSTEM_TENANT_ID
from irp_shared.portfolio import PortfolioActor, PortfolioNotVisible, create_portfolio
from irp_shared.position import (
    PositionActor,
    create_position,
    reconstruct_position_as_of,
)
from irp_shared.reference.instrument import create_instrument
from irp_shared.reference.service import ReferenceActor

URL = os.environ.get("IRP_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="requires PostgreSQL (IRP_TEST_DATABASE_URL)")

_P1C3 = ("position",)
_P1B1_HYBRID = ("currency", "calendar", "calendar_holiday", "rating_scale", "rating_grade")
_DEPS = ("portfolio", "instrument")
_RAILS = ("data_source", "lineage_edge")
_ACT = PositionActor(actor_id="a")
T0 = datetime(2026, 1, 1, tzinfo=UTC)


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
        for table in (*_P1C3, *_DEPS, *_RAILS):
            conn.execute(text(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO irp_app"))
        conn.execute(text("GRANT SELECT, INSERT ON audit_event TO irp_app"))
    superuser.dispose()
    return (
        make_url(URL)
        .set(username="irp_app", password="ci_app_pw")
        .render_as_string(hide_password=False)
    )


def _seed_pf_inst(factory, tenant: str) -> tuple[str, str]:  # noqa: ANN001
    session = factory()
    try:
        set_tenant_context(session, tenant)
        pf = create_portfolio(
            session,
            tenant_id=tenant,
            code="PF",
            name="pf",
            node_type="ACCOUNT",
            actor=PortfolioActor(actor_id="a"),
        )
        inst = create_instrument(
            session,
            tenant_id=tenant,
            code="INST",
            name="i",
            asset_class="BOND",
            actor=ReferenceActor(actor_id="a"),
        )
        session.commit()
        return pf.id, inst.id
    finally:
        session.close()


def _seed_pos(factory, tenant: str) -> tuple[str, str, str]:  # noqa: ANN001
    pf_id, inst_id = _seed_pf_inst(factory, tenant)
    session = factory()
    try:
        set_tenant_context(session, tenant)
        row = create_position(
            session,
            portfolio_id=pf_id,
            instrument_id=inst_id,
            acting_tenant=tenant,
            actor=_ACT,
            quantity=Decimal("100"),
            valid_from=T0,
        )
        session.commit()
        return row.id, pf_id, inst_id
    finally:
        session.close()


def test_tenant_isolation(app_url: str) -> None:
    engine = make_engine(app_url, poolclass=NullPool)
    factory = make_session_factory(engine)
    a, b = str(uuid.uuid4()), str(uuid.uuid4())
    try:
        _seed_pos(factory, a)
        _seed_pos(factory, b)
        session = factory()
        try:
            set_tenant_context(session, a)
            tenants = {
                str(r[0]) for r in session.execute(text("SELECT DISTINCT tenant_id FROM position"))
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
        _seed_pos(factory, str(uuid.uuid4()))
        session = factory()
        try:
            assert session.execute(text("SELECT count(*) FROM position")).scalar_one() == 0
        finally:
            session.close()
    finally:
        engine.dispose()


def test_not_append_only_close_out_update_permitted(app_url: str) -> None:
    # FR positive proof: irp_app HAS UPDATE grant and there is NO P0001 trigger, so a raw close-out
    # UPDATE is PERMITTED (rowcount == 1). The exact inversion of the transaction IA P0001 guard.
    engine = make_engine(app_url, poolclass=NullPool)
    factory = make_session_factory(engine)
    a = str(uuid.uuid4())
    pos_id, _, _ = _seed_pos(factory, a)
    session = factory()
    try:
        set_tenant_context(session, a)
        # POSITIVE CONTROL: the seed row is present + RLS-visible to irp_app.
        assert (
            session.execute(
                text("SELECT count(*) FROM position WHERE id = CAST(:i AS uuid)"), {"i": pos_id}
            ).scalar_one()
            == 1
        )
        result = session.execute(
            text("UPDATE position SET system_to = now() WHERE id = CAST(:i AS uuid)"), {"i": pos_id}
        )
        assert result.rowcount == 1  # PERMITTED — no append-only trigger
        session.commit()
    finally:
        session.close()
        engine.dispose()


def test_forged_tenant_insert_denied(app_url: str) -> None:
    engine = make_engine(app_url, poolclass=NullPool)
    factory = make_session_factory(engine)
    a, b = str(uuid.uuid4()), str(uuid.uuid4())
    a_pf, a_inst = _seed_pf_inst(factory, a)
    session = factory()
    try:
        set_tenant_context(session, a)
        with pytest.raises(ProgrammingError) as exc:
            session.execute(
                text(
                    "INSERT INTO position "
                    "(id, tenant_id, valid_from, system_from, created_at, updated_at, "
                    "portfolio_id, instrument_id, quantity, record_version) VALUES "
                    "(CAST(:id AS uuid), CAST(:b AS uuid), now(), now(), now(), now(), "
                    "CAST(:p AS uuid), CAST(:n AS uuid), 1, 1)"
                ),
                {"id": str(uuid.uuid4()), "b": b, "p": a_pf, "n": a_inst},
            )
        assert _is_rls_violation(exc.value)  # 42501 WITH CHECK
        session.rollback()
    finally:
        session.close()
        engine.dispose()


def test_current_head_partial_unique_in_pg(app_url: str) -> None:
    engine = make_engine(app_url, poolclass=NullPool)
    factory = make_session_factory(engine)
    a = str(uuid.uuid4())
    _pos_id, a_pf, a_inst = _seed_pos(factory, a)
    session = factory()
    try:
        set_tenant_context(session, a)
        with pytest.raises(IntegrityError):  # a second dual-open row violates uq_position_current
            session.execute(
                text(
                    "INSERT INTO position "
                    "(id, tenant_id, valid_from, system_from, created_at, updated_at, "
                    "portfolio_id, instrument_id, quantity, record_version) VALUES "
                    "(CAST(:id AS uuid), CAST(:a AS uuid), now(), now(), now(), now(), "
                    "CAST(:p AS uuid), CAST(:n AS uuid), 5, 1)"
                ),
                {"id": str(uuid.uuid4()), "a": a, "p": a_pf, "n": a_inst},
            )
        session.rollback()
    finally:
        session.close()
        engine.dispose()


def test_cross_tenant_portfolio_rejected_service_layer(app_url: str) -> None:
    engine = make_engine(app_url, poolclass=NullPool)
    factory = make_session_factory(engine)
    a, b = str(uuid.uuid4()), str(uuid.uuid4())
    b_pf, _b_inst = _seed_pf_inst(factory, b)
    _a_pf, a_inst = _seed_pf_inst(factory, a)
    session = factory()
    try:
        set_tenant_context(session, a)
        with pytest.raises(PortfolioNotVisible):  # service predicate, NOT a 42501
            create_position(
                session,
                portfolio_id=b_pf,
                instrument_id=a_inst,
                acting_tenant=a,
                actor=_ACT,
                quantity=Decimal("1"),
                valid_from=T0,
            )
        session.rollback()
    finally:
        session.close()
        engine.dispose()


def test_reconstruct_under_rls(app_url: str) -> None:
    engine = make_engine(app_url, poolclass=NullPool)
    factory = make_session_factory(engine)
    a = str(uuid.uuid4())
    _pos_id, a_pf, a_inst = _seed_pos(factory, a)
    session = factory()
    try:
        set_tenant_context(session, a)
        row = reconstruct_position_as_of(
            session,
            acting_tenant=a,
            portfolio_id=a_pf,
            instrument_id=a_inst,
            valid_at=datetime(2026, 3, 1, tzinfo=UTC),
        )
        assert row is not None and row.quantity == Decimal("100")
    finally:
        session.close()
        engine.dispose()


def test_policies_symmetric_and_force_rls(app_url: str) -> None:
    engine = make_engine(app_url, poolclass=NullPool)
    try:
        with engine.connect() as conn:
            for table in _P1C3:
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
