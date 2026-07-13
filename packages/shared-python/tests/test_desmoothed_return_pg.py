"""PostgreSQL-only proofs for PA-1 ``desmoothed_return_result`` (ENT-056, IA — the governed
Geltner desmoothing v1), run as the constrained NOSUPERUSER/NOBYPASSRLS ``irp_app`` role:

- symmetric FORCE-RLS tenant isolation (visibility + no-context zero rows + forged-tenant 42501);
- the **P0001 append-only trigger** blocks UPDATE/DELETE at the DB (``irp_app`` is GRANTED
  UPDATE/DELETE so the rejection proves the trigger, not a privilege denial);
- the symmetric policy shape + the closed 5-table hybrid set unchanged (REAL SYSTEM_TENANT_ID);
- cross-tenant snapshot consume fails closed;
- the per-tenant audit hash chain verifies.

The full chain (portfolio -> private instrument -> quarterly appraisal marks -> a desmoothing run)
executes through the binders under ``set_tenant_context``.
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
from irp_shared.perf import (
    DesmoothedReturnActor,
    register_desmoothed_return_model,
    run_desmoothed_return,
)
from irp_shared.portfolio import PortfolioActor, create_portfolio
from irp_shared.reference.instrument import create_instrument
from irp_shared.reference.service import ReferenceActor
from irp_shared.valuation import create_valuation
from irp_shared.valuation.service import ValuationActor

URL = os.environ.get("IRP_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="requires PostgreSQL (IRP_TEST_DATABASE_URL)")

_PA_1 = ("desmoothed_return_result",)
_P1B1_HYBRID = ("currency", "calendar", "calendar_holiday", "rating_scale", "rating_grade")
_DEPS = (
    "portfolio",
    "instrument",
    "legal_entity",
    "issuer",
    "currency",
    "valuation",
    "model",
    "model_version",
    "model_assumption",
    "model_limitation",
)
_SNAP = ("dataset_snapshot", "dataset_snapshot_component")
_RAILS = ("data_source", "lineage_edge", "data_quality_rule", "data_quality_result")
_RUN = ("calculation_run",)
_T0 = datetime(2025, 9, 1, tzinfo=UTC)
_DATES = (date(2025, 9, 30), date(2025, 12, 31), date(2026, 3, 31), date(2026, 6, 30))
_VALUES = ("100.00", "102.00", "104.55", "103.5045")
_ACT = DesmoothedReturnActor(actor_id="a")


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
        for table in (*_PA_1, *_RUN, *_SNAP, *_DEPS, *_RAILS):
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


def _seed_and_run(factory, tenant: str) -> str:  # noqa: ANN001
    """The full chain -> a COMPLETED desmoothing run (its run_id)."""
    session = factory()
    try:
        set_tenant_context(session, tenant)
        session.add(_currency(tenant, "USD"))
        session.flush()
        pf = create_portfolio(
            session,
            tenant_id=tenant,
            code=f"PE-{uuid.uuid4().hex[:6]}",
            name="private book",
            node_type="ACCOUNT",
            actor=PortfolioActor(actor_id="s"),
        ).id
        inst = create_instrument(
            session,
            tenant_id=tenant,
            code=f"PE-FUND-{uuid.uuid4().hex[:6]}",
            name="Buyout Fund IV",
            asset_class="PRIVATE_EQUITY",
            actor=ReferenceActor(actor_id="s"),
        ).id
        for d, v in zip(_DATES, _VALUES, strict=True):
            create_valuation(
                session,
                portfolio_id=pf,
                instrument_id=inst,
                valuation_date=d,
                acting_tenant=tenant,
                actor=ValuationActor(actor_id="s"),
                mark_value=Decimal(v),
                currency_code="USD",
                valid_from=_T0,
            )
        session.flush()
        mv = register_desmoothed_return_model(
            session, tenant_id=tenant, actor_id="a", code_version="pa1-v1", alpha="0.4"
        )
        session.flush()
        result = run_desmoothed_return(
            session,
            acting_tenant=tenant,
            actor=_ACT,
            code_version="pa1-v1",
            environment_id="ci",
            model_version_id=mv.id,
            portfolio_id=pf,
            instrument_id=inst,
            window_start=date(2025, 9, 1),
            window_end=date(2026, 7, 1),
        )
        # 2 DESMOOTHED_PERIOD rows + 1 DESMOOTHING_SUMMARY row.
        assert result.status == "COMPLETED" and len(result.rows) == 3
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
            text("SELECT calculation_run_id FROM desmoothed_return_result")
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
        count = session.execute(text("SELECT count(*) FROM desmoothed_return_result")).scalar_one()
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
            session.execute(text("UPDATE desmoothed_return_result SET metric_value = 0"))
        assert _is_append_only_violation(upd.value)
        session.rollback()
        set_tenant_context(session, tenant)
        with pytest.raises(ProgrammingError) as dele:
            session.execute(text("DELETE FROM desmoothed_return_result"))
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
                "SELECT calculation_run_id, input_snapshot_id, model_version_id, "
                "portfolio_id, instrument_id FROM desmoothed_return_result LIMIT 1"
            )
        ).one()
        with pytest.raises(ProgrammingError) as forged:
            session.execute(
                text(
                    "INSERT INTO desmoothed_return_result (id, tenant_id, system_from, "
                    "calculation_run_id, input_snapshot_id, model_version_id, portfolio_id, "
                    "instrument_id, metric_type, period_start, period_end, metric_value, "
                    "alpha, mark_currency) "
                    "VALUES (:id, :victim, now(), :run, :snap, :mv, :pf, :inst, "
                    "'DESMOOTHING_SUMMARY', :d0, :d1, 0.01, 0.4, 'USD')"
                ),
                {
                    "id": str(uuid.uuid4()),
                    "victim": victim,  # a FOREIGN tenant_id under the acting context
                    "run": str(row[0]),
                    "snap": str(row[1]),
                    "mv": str(row[2]),
                    "pf": str(row[3]),
                    "inst": str(row[4]),
                    "d0": _DATES[1],
                    "d1": _DATES[3],
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
                    "WHERE tablename = 'desmoothed_return_result'"
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
                "WHERE run_type = 'DESMOOTHED_RETURN' AND tenant_id = :t LIMIT 1"
            ),
            {"t": t1},
        ).scalar_one()
    finally:
        session.close()

    session = factory()
    try:
        set_tenant_context(session, t2)
        mv = register_desmoothed_return_model(
            session, tenant_id=t2, actor_id="a", code_version="pa1-v1", alpha="0.4"
        )
        session.flush()
        from irp_shared.snapshot import SnapshotNotFound

        with pytest.raises(SnapshotNotFound):
            run_desmoothed_return(
                session,
                acting_tenant=t2,
                actor=_ACT,
                code_version="pa1-v1",
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
