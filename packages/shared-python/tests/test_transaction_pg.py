"""PostgreSQL SYMMETRIC-RLS + APPEND-ONLY tests for P1C-2 transaction (PROPRIETARY, IA).

Gated on ``IRP_TEST_DATABASE_URL``; enforcement runs under the constrained non-superuser ``irp_app``
role (NOSUPERUSER NOBYPASSRLS). Proves: cross-tenant invisibility + no-context->zero rows; the
**append-only P0001 TRIGGER** (grant irp_app UPDATE/DELETE so the rejection is the trigger, NOT a
privilege denial, with a POSITIVE CONTROL first so the UPDATE/DELETE provably reaches the row); the
RLS ``WITH CHECK`` backstop denies a forged-tenant INSERT (42501, distinct from the P0001 trigger);
the POSITIVE symmetric-policy + FORCE-RLS assertion AND the unchanged closed-hybrid-set; the
cross-tenant FK service-layer reject; a reversal record under FORCE RLS. Native-uuid trap.
"""

from __future__ import annotations

import os
import uuid
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.pool import NullPool

from irp_shared.audit.service import verify_chain
from irp_shared.db.session import make_engine, make_session_factory
from irp_shared.db.tenant import set_tenant_context
from irp_shared.entitlement.bootstrap import SYSTEM_TENANT_ID
from irp_shared.portfolio import PortfolioActor, PortfolioNotVisible, create_portfolio
from irp_shared.reference.instrument import create_instrument
from irp_shared.reference.service import ReferenceActor
from irp_shared.transaction import (
    TransactionActor,
    record_transaction,
    resolve_transaction,
    reverse_transaction,
)

URL = os.environ.get("IRP_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="requires PostgreSQL (IRP_TEST_DATABASE_URL)")

_P1C2 = ("transaction",)
_P1B1_HYBRID = ("currency", "calendar", "calendar_holiday", "rating_scale", "rating_grade")
_DEPS = ("portfolio", "instrument")
_RAILS = ("data_source", "lineage_edge")
_ACT = TransactionActor(actor_id="a")


def _is_rls_violation(error: ProgrammingError) -> bool:
    return (
        getattr(error.orig, "sqlstate", None) == "42501"
        or "row-level security" in str(error).lower()
    )


def _is_append_only_violation(error: ProgrammingError) -> bool:
    return getattr(error.orig, "sqlstate", None) == "P0001" or "append-only" in str(error).lower()


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
        for table in (*_P1C2, *_DEPS, *_RAILS):
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


def _seed_txn(factory, tenant: str) -> tuple[str, str, str]:  # noqa: ANN001
    pf_id, inst_id = _seed_pf_inst(factory, tenant)
    session = factory()
    try:
        set_tenant_context(session, tenant)
        txn = record_transaction(
            session,
            tenant_id=tenant,
            portfolio_id=pf_id,
            instrument_id=inst_id,
            txn_type="BUY",
            trade_date=date(2026, 3, 1),
            quantity=Decimal("100"),
            actor=_ACT,
        )
        session.commit()
        return txn.id, pf_id, inst_id
    finally:
        session.close()


def test_tenant_isolation(app_url: str) -> None:
    engine = make_engine(app_url, poolclass=NullPool)
    factory = make_session_factory(engine)
    a, b = str(uuid.uuid4()), str(uuid.uuid4())
    try:
        _seed_txn(factory, a)
        _seed_txn(factory, b)
        session = factory()
        try:
            set_tenant_context(session, a)
            tenants = {
                str(r[0])
                for r in session.execute(text("SELECT DISTINCT tenant_id FROM transaction"))
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
        _seed_txn(factory, str(uuid.uuid4()))
        session = factory()
        try:
            assert session.execute(text("SELECT count(*) FROM transaction")).scalar_one() == 0
        finally:
            session.close()
    finally:
        engine.dispose()


def test_append_only_trigger_blocks_update_and_delete(app_url: str) -> None:
    # The P0001 append-only TRIGGER: irp_app HAS UPDATE/DELETE grants, so a rejection proves the
    # trigger, not a privilege denial. A POSITIVE CONTROL first proves the row is present + visible.
    engine = make_engine(app_url, poolclass=NullPool)
    factory = make_session_factory(engine)
    a = str(uuid.uuid4())
    txn_id, _, _ = _seed_txn(factory, a)
    session = factory()
    try:
        set_tenant_context(session, a)
        # POSITIVE CONTROL: the seed row is present + RLS-visible to irp_app (so UPDATE/DELETE reach
        # it).
        assert (
            session.execute(
                text("SELECT count(*) FROM transaction WHERE id = CAST(:i AS uuid)"), {"i": txn_id}
            ).scalar_one()
            == 1
        )
        with pytest.raises(ProgrammingError) as exc:
            session.execute(
                text("UPDATE transaction SET txn_type = 'SELL' WHERE id = CAST(:i AS uuid)"),
                {"i": txn_id},
            )
        assert _is_append_only_violation(exc.value)
        session.rollback()
        set_tenant_context(session, a)
        with pytest.raises(ProgrammingError) as exc:
            session.execute(
                text("DELETE FROM transaction WHERE id = CAST(:i AS uuid)"), {"i": txn_id}
            )
        assert _is_append_only_violation(exc.value)
        session.rollback()
    finally:
        session.close()
        engine.dispose()


def test_forged_tenant_insert_denied(app_url: str) -> None:
    # The RLS WITH CHECK backstop: an INSERT stamping a FOREIGN tenant_id is denied (42501),
    # distinct
    # from the P0001 append-only trigger. (UPDATE would hit the trigger first, so we prove via
    # INSERT.)
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
                    "INSERT INTO transaction "
                    "(id, tenant_id, system_from, portfolio_id, instrument_id, txn_type, "
                    "trade_date, quantity) VALUES "
                    "(CAST(:id AS uuid), CAST(:b AS uuid), now(), CAST(:p AS uuid), "
                    "CAST(:n AS uuid), 'BUY', CURRENT_DATE, 1)"
                ),
                {"id": str(uuid.uuid4()), "b": b, "p": a_pf, "n": a_inst},
            )
        assert _is_rls_violation(exc.value)  # 42501 WITH CHECK, not P0001
        session.rollback()
    finally:
        session.close()
        engine.dispose()


def test_cross_tenant_portfolio_rejected_service_layer(app_url: str) -> None:
    engine = make_engine(app_url, poolclass=NullPool)
    factory = make_session_factory(engine)
    a, b = str(uuid.uuid4()), str(uuid.uuid4())
    b_pf, _b_inst = _seed_pf_inst(factory, b)
    a_pf, a_inst = _seed_pf_inst(factory, a)
    session = factory()
    try:
        set_tenant_context(session, a)
        with pytest.raises(PortfolioNotVisible):  # service predicate, NOT a 42501
            record_transaction(
                session,
                tenant_id=a,
                portfolio_id=b_pf,
                instrument_id=a_inst,
                txn_type="BUY",
                trade_date=date(2026, 3, 1),
                quantity=Decimal("1"),
                actor=_ACT,
            )
        session.rollback()
    finally:
        session.close()
        engine.dispose()


def test_policies_symmetric_and_force_rls(app_url: str) -> None:
    engine = make_engine(app_url, poolclass=NullPool)
    try:
        with engine.connect() as conn:
            for table in _P1C2:
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


def test_reversal_under_rls(app_url: str) -> None:
    engine = make_engine(app_url, poolclass=NullPool)
    factory = make_session_factory(engine)
    a = str(uuid.uuid4())
    txn_id, _, _ = _seed_txn(factory, a)
    session = factory()
    try:
        set_tenant_context(session, a)
        original = resolve_transaction(session, txn_id, acting_tenant=a)
        reversal = reverse_transaction(session, original, actor=_ACT, reason="err")
        session.commit()
        set_tenant_context(session, a)  # re-set after commit before read-back
        assert reversal.reverses_transaction_id == txn_id
        assert session.execute(text("SELECT count(*) FROM transaction")).scalar_one() == 2
        n = session.execute(
            text("SELECT count(*) FROM audit_event WHERE event_type = 'TRANSACTION.REVERSE'")
        ).scalar_one()
        assert n == 1
        assert verify_chain(session, a).ok is True
    finally:
        session.close()
        engine.dispose()
