"""PostgreSQL-only proofs for PM-1 ``portfolio_return_result`` (ENT-053, IA — the governed
time-weighted return v1), run as the constrained NOSUPERUSER/NOBYPASSRLS ``irp_app`` role:

- symmetric FORCE-RLS tenant isolation (visibility + no-context zero rows + forged-tenant 42501);
- the **P0001 append-only trigger** blocks UPDATE/DELETE at the DB (``irp_app`` is GRANTED
  UPDATE/DELETE so the rejection proves the trigger, not a privilege denial);
- the symmetric policy shape + the closed 5-table hybrid set unchanged (REAL SYSTEM_TENANT_ID);
- cross-tenant snapshot consume fails closed;
- the per-tenant audit hash chain verifies.

The FULL chain (portfolio -> position -> two dated valuations -> two boundary exposure runs -> a
captured external flow -> a portfolio-return run) executes through the binders under
``set_tenant_context``.
"""

from __future__ import annotations

import os
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.pool import NullPool

from irp_shared.audit.service import verify_chain
from irp_shared.db.session import make_engine, make_session_factory
from irp_shared.db.tenant import set_tenant_context
from irp_shared.exposure import ExposureActor, run_exposure
from irp_shared.perf import (
    PortfolioReturnActor,
    register_portfolio_return_model,
    run_portfolio_return,
)
from irp_shared.portfolio import PortfolioActor, create_portfolio
from irp_shared.position import create_position
from irp_shared.position.service import PositionActor
from irp_shared.reference.instrument import create_instrument
from irp_shared.reference.service import ReferenceActor
from irp_shared.transaction import TransactionActor, record_transaction
from irp_shared.valuation import create_valuation
from irp_shared.valuation.service import ValuationActor

URL = os.environ.get("IRP_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="requires PostgreSQL (IRP_TEST_DATABASE_URL)")

_PM_1 = ("portfolio_return_result",)
_P1B1_HYBRID = ("currency", "calendar", "calendar_holiday", "rating_scale", "rating_grade")
_DEPS = (
    "portfolio",
    "position",
    "valuation",
    "instrument",
    "legal_entity",
    "issuer",
    "currency",
    "fx_rate",
    "exposure_aggregate",
    "transaction",
    "model",
    "model_version",
    "model_assumption",
    "model_limitation",
)
_SNAP = ("dataset_snapshot", "dataset_snapshot_component")
_RAILS = ("data_source", "lineage_edge", "data_quality_rule", "data_quality_result")
_RUN = ("calculation_run",)
_T0 = datetime(2026, 1, 1, tzinfo=UTC)
_KNOWN_AT = datetime(2030, 1, 1, tzinfo=UTC)
_D0, _D1 = date(2026, 1, 1), date(2026, 1, 31)
_MID = date(2026, 1, 16)
_ACT = PortfolioReturnActor(actor_id="a")


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
        for table in (*_PM_1, *_RUN, *_SNAP, *_DEPS, *_RAILS):
            conn.execute(text(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO irp_app"))
        conn.execute(text("GRANT SELECT, INSERT ON audit_event TO irp_app"))
    superuser.dispose()
    return (
        make_url(URL)
        .set(username="irp_app", password="ci_app_pw")
        .render_as_string(hide_password=False)
    )


def _currency(tenant: str, code: str):  # noqa: ANN201
    from irp_shared.reference.models import Currency

    return Currency(tenant_id=tenant, code=code, name=code, valid_from=_T0)


def _boundary_run(session, tenant, pf, inst, vdate, mark):  # noqa: ANN001, ANN202
    create_valuation(
        session,
        portfolio_id=pf,
        instrument_id=inst,
        valuation_date=vdate,
        acting_tenant=tenant,
        actor=ValuationActor(actor_id="s"),
        mark_value=Decimal(mark),
        currency_code="USD",
        valid_from=_T0,
    )
    return run_exposure(
        session,
        acting_tenant=tenant,
        actor=ExposureActor(actor_id="a"),
        code_version="v1",
        environment_id="ci",
        portfolio_id=pf,
        as_of_valid_at=datetime(vdate.year, vdate.month, vdate.day, tzinfo=UTC),
        as_of_known_at=_KNOWN_AT,
        base_currency="USD",
    ).run.run_id


def _seed_and_run(factory, tenant: str) -> str:  # noqa: ANN001
    """The FULL chain: two dated boundary exposure runs + a +20,000 mid-period contribution -> a
    COMPLETED portfolio-return run (its run_id)."""
    session = factory()
    try:
        set_tenant_context(session, tenant)
        session.add(_currency(tenant, "USD"))
        session.flush()
        pf = create_portfolio(
            session,
            tenant_id=tenant,
            code=f"ACCT-{uuid.uuid4().hex[:6]}",
            name="acct",
            node_type="ACCOUNT",
            actor=PortfolioActor(actor_id="s"),
        ).id
        inst = create_instrument(
            session,
            tenant_id=tenant,
            code=f"I-{uuid.uuid4().hex[:6]}",
            name="i",
            asset_class="EQUITY",
            actor=ReferenceActor(actor_id="s"),
        ).id
        create_position(
            session,
            portfolio_id=pf,
            instrument_id=inst,
            acting_tenant=tenant,
            actor=PositionActor(actor_id="s"),
            quantity=Decimal("1"),
            valid_from=_T0,
        )
        r0 = _boundary_run(session, tenant, pf, inst, _D0, "1000000")
        r1 = _boundary_run(session, tenant, pf, inst, _D1, "1050000")
        record_transaction(
            session,
            tenant_id=tenant,
            portfolio_id=pf,
            instrument_id=inst,
            txn_type="TRANSFER_IN",
            trade_date=_MID,
            quantity=Decimal("0"),
            gross_amount=Decimal("20000"),
            currency_code="USD",
            actor=TransactionActor(actor_id="s"),
        )
        mv = register_portfolio_return_model(
            session, tenant_id=tenant, actor_id="a", code_version="perf-v1"
        )
        session.flush()
        result = run_portfolio_return(
            session,
            acting_tenant=tenant,
            actor=_ACT,
            code_version="perf-v1",
            environment_id="ci",
            model_version_id=mv.id,
            exposure_run_ids=[r0, r1],
        )
        assert result.status == "COMPLETED" and len(result.rows) == 2  # DIETZ_PERIOD + TWR_LINKED
        session.commit()
        return result.run.run_id
    finally:
        session.close()


def test_tenant_isolation(app_url: str) -> None:
    engine = make_engine(app_url, poolclass=NullPool)
    factory = make_session_factory(engine)
    t1, t2 = str(uuid.uuid4()), str(uuid.uuid4())
    run1 = _seed_and_run(factory, t1)
    _seed_and_run(factory, t2)

    session = factory()
    try:
        set_tenant_context(session, t1)
        rows = session.execute(
            text("SELECT calculation_run_id FROM portfolio_return_result")
        ).fetchall()
        assert rows and all(str(r[0]) == run1 for r in rows)  # only t1's rows visible
    finally:
        session.close()
        engine.dispose()


def test_no_context_read_returns_zero_rows(app_url: str) -> None:
    engine = make_engine(app_url, poolclass=NullPool)
    factory = make_session_factory(engine)
    _seed_and_run(factory, str(uuid.uuid4()))
    session = factory()
    try:
        count = session.execute(
            text("SELECT count(*) FROM portfolio_return_result")
        ).scalar_one()
        assert count == 0  # FORCE RLS: no tenant context -> zero rows
    finally:
        session.close()
        engine.dispose()


def test_append_only_trigger_blocks_update_and_delete(app_url: str) -> None:
    engine = make_engine(app_url, poolclass=NullPool)
    factory = make_session_factory(engine)
    tenant = str(uuid.uuid4())
    _seed_and_run(factory, tenant)

    session = factory()
    try:
        set_tenant_context(session, tenant)
        with pytest.raises(ProgrammingError) as upd:
            session.execute(text("UPDATE portfolio_return_result SET return_value = 0"))
        assert _is_append_only_violation(upd.value)
        session.rollback()
        set_tenant_context(session, tenant)
        with pytest.raises(ProgrammingError) as dele:
            session.execute(text("DELETE FROM portfolio_return_result"))
        assert _is_append_only_violation(dele.value)
        session.rollback()
    finally:
        session.close()
        engine.dispose()


def test_forged_tenant_insert_rejected(app_url: str) -> None:
    engine = make_engine(app_url, poolclass=NullPool)
    factory = make_session_factory(engine)
    tenant, victim = str(uuid.uuid4()), str(uuid.uuid4())
    _seed_and_run(factory, tenant)

    session = factory()
    try:
        set_tenant_context(session, tenant)
        row = session.execute(
            text(
                "SELECT calculation_run_id, input_snapshot_id, model_version_id, portfolio_id "
                "FROM portfolio_return_result LIMIT 1"
            )
        ).one()
        with pytest.raises(ProgrammingError) as forged:
            session.execute(
                text(
                    "INSERT INTO portfolio_return_result (id, tenant_id, system_from, "
                    "calculation_run_id, input_snapshot_id, model_version_id, portfolio_id, "
                    "metric_type, period_start, period_end, begin_mv, end_mv, net_external_flow, "
                    "return_value, n_flows, n_periods, base_currency) "
                    "VALUES (:id, :victim, now(), :run, :snap, :mv, :pf, 'TWR_LINKED', :d0, :d1, "
                    "1000000, 1050000, 20000, 0.03, 1, 1, 'USD')"
                ),
                {
                    "id": str(uuid.uuid4()),
                    "victim": victim,  # a FOREIGN tenant_id under the acting context
                    "run": str(row[0]),
                    "snap": str(row[1]),
                    "mv": str(row[2]),
                    "pf": str(row[3]),
                    "d0": _D0,
                    "d1": _D1,
                },
            )
        assert _is_rls_violation(forged.value)  # WITH CHECK rejects the forged tenant (42501)
        session.rollback()
    finally:
        session.close()
        engine.dispose()


def test_symmetric_policy_and_closed_hybrid_set_unchanged(app_url: str) -> None:
    engine = make_engine(URL, poolclass=NullPool)  # structural read as the owner
    try:
        with engine.connect() as conn:
            qual, check = conn.execute(
                text(
                    "SELECT qual, with_check FROM pg_policies "
                    "WHERE tablename = 'portfolio_return_result'"
                )
            ).one()
            assert "app.current_tenant" in qual and "app.current_tenant" in check
            assert "SYSTEM" not in qual.upper().replace("CURRENT_SETTING", "")  # never hybrid
            from irp_shared.entitlement.bootstrap import SYSTEM_TENANT_ID

            hybrid = conn.execute(
                text("SELECT tablename FROM pg_policies WHERE qual LIKE :pat ORDER BY tablename"),
                {"pat": f"%{SYSTEM_TENANT_ID}%"},
            ).fetchall()
            assert {r[0] for r in hybrid} == set(_P1B1_HYBRID)
    finally:
        engine.dispose()


def test_cross_tenant_snapshot_consume_fails_closed(app_url: str) -> None:
    engine = make_engine(app_url, poolclass=NullPool)
    factory = make_session_factory(engine)
    t1, t2 = str(uuid.uuid4()), str(uuid.uuid4())
    _seed_and_run(factory, t1)

    session = factory()
    try:
        set_tenant_context(session, t1)
        snap = session.execute(
            text(
                "SELECT input_snapshot_id FROM calculation_run "
                "WHERE run_type = 'PORTFOLIO_RETURN' AND tenant_id = :t LIMIT 1"
            ),
            {"t": t1},
        ).scalar_one()
    finally:
        session.close()

    session = factory()
    try:
        set_tenant_context(session, t2)
        mv = register_portfolio_return_model(
            session, tenant_id=t2, actor_id="a", code_version="perf-v1"
        )
        session.flush()
        from irp_shared.snapshot import SnapshotNotFound

        with pytest.raises(SnapshotNotFound):
            run_portfolio_return(
                session,
                acting_tenant=t2,
                actor=_ACT,
                code_version="perf-v1",
                environment_id="ci",
                model_version_id=mv.id,
                snapshot_id=str(snap),  # t1's snapshot under t2's context
            )
        session.rollback()
    finally:
        session.close()
        engine.dispose()


def test_audit_chain_verifies(app_url: str) -> None:
    engine = make_engine(app_url, poolclass=NullPool)
    factory = make_session_factory(engine)
    tenant = str(uuid.uuid4())
    _seed_and_run(factory, tenant)
    session = factory()
    try:
        set_tenant_context(session, tenant)
        assert verify_chain(session, tenant).ok is True
    finally:
        session.close()
        engine.dispose()
