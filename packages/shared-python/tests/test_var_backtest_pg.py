"""PostgreSQL-only proofs for BT-1 ``var_backtest_result`` (ENT-055, IA — the governed VaR
backtest v1), run as the constrained NOSUPERUSER/NOBYPASSRLS ``irp_app`` role:

- symmetric FORCE-RLS tenant isolation (visibility + no-context zero rows + forged-tenant 42501);
- the **P0001 append-only trigger** blocks UPDATE/DELETE at the DB (``irp_app`` is GRANTED
  UPDATE/DELETE so the rejection proves the trigger, not a privilege denial);
- the symmetric policy shape + the closed 5-table hybrid set unchanged (REAL SYSTEM_TENANT_ID);
- cross-tenant snapshot consume fails closed;
- the per-tenant audit hash chain verifies.

The FULL chain (portfolio -> exposure -> factor-exposure -> covariance -> parametric VaR + a PM-1
PORTFOLIO_RETURN run over aligned boundaries -> a var-backtest run) executes through the binders
under ``set_tenant_context``.
"""

from __future__ import annotations

import os
import uuid
from datetime import UTC, date, datetime, timedelta
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
from irp_shared.marketdata import (
    FactorActor,
    FxRateActor,
    capture_factor,
    capture_factor_return,
    capture_fx_rate,
    resolve_factor,
)
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
from irp_shared.risk import (
    CovarianceActor,
    FactorExposureActor,
    VarActor,
    VarBacktestActor,
    register_covariance_model,
    register_factor_exposure_model,
    register_var_backtest_model,
    register_var_model,
    run_covariance,
    run_factor_exposure,
    run_var,
    run_var_backtest,
)
from irp_shared.valuation import create_valuation
from irp_shared.valuation.service import ValuationActor

URL = os.environ.get("IRP_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="requires PostgreSQL (IRP_TEST_DATABASE_URL)")

_BT_1 = ("var_backtest_result",)
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
    "factor",
    "factor_return",
    "factor_exposure_result",
    "covariance_result",
    "var_result",
    "portfolio_return_result",
    "model",
    "model_version",
    # VW-1: every binder bind now reads the latest model_validation (the OD-B REJECTED gate).
    "model_validation",
    "model_assumption",
    "model_limitation",
)
_SNAP = ("dataset_snapshot", "dataset_snapshot_component")
_RAILS = ("data_source", "lineage_edge", "data_quality_rule", "data_quality_result")
_RUN = ("calculation_run",)
_T0 = datetime(2026, 1, 1, tzinfo=UTC)
_VALID_AT = datetime(2026, 6, 1, tzinfo=UTC)
_KNOWN_AT = datetime(2030, 1, 1, tzinfo=UTC)
_VD = date(2026, 6, 1)
_D = (date(2026, 5, 26), date(2026, 5, 27), date(2026, 5, 28), date(2026, 5, 29))
_B0, _B1 = _D[3], _D[3] + timedelta(days=1)
_ACT = VarBacktestActor(actor_id="a")


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
        for table in (*_BT_1, *_RUN, *_SNAP, *_DEPS, *_RAILS):
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
    """The FULL chain -> a COMPLETED var-backtest run (its run_id)."""
    session = factory()
    try:
        set_tenant_context(session, tenant)
        session.add(_currency(tenant, "USD"))
        session.add(_currency(tenant, "EUR"))
        session.flush()
        pf = create_portfolio(
            session,
            tenant_id=tenant,
            code=f"ACCT-{uuid.uuid4().hex[:6]}",
            name="acct",
            node_type="ACCOUNT",
            actor=PortfolioActor(actor_id="s"),
        ).id
        insts: list[str] = []
        for code, qty, mark, ccy in (
            ("I-USD", "100", "300.00", "USD"),
            ("I-EUR", "100", "400.00", "EUR"),
        ):
            inst = create_instrument(
                session,
                tenant_id=tenant,
                code=f"{code}-{uuid.uuid4().hex[:6]}",
                name="i",
                asset_class="BOND",
                actor=ReferenceActor(actor_id="s"),
            ).id
            insts.append(inst)
            create_position(
                session,
                portfolio_id=pf,
                instrument_id=inst,
                acting_tenant=tenant,
                actor=PositionActor(actor_id="s"),
                quantity=Decimal(qty),
                valid_from=_T0,
            )
            create_valuation(
                session,
                portfolio_id=pf,
                instrument_id=inst,
                valuation_date=_VD,
                acting_tenant=tenant,
                actor=ValuationActor(actor_id="s"),
                mark_value=Decimal(mark),
                currency_code=ccy,
                valid_from=_T0,
            )
        capture_fx_rate(
            session,
            base_currency="EUR",
            quote_currency="USD",
            rate_date=_VD,
            rate=Decimal("1.000000000000"),
            acting_tenant=tenant,
            actor=FxRateActor(actor_id="s"),
            valid_from=_T0,
        )
        exposure = run_exposure(
            session,
            acting_tenant=tenant,
            actor=ExposureActor(actor_id="a"),
            code_version="v1",
            environment_id="ci",
            portfolio_id=pf,
            as_of_valid_at=_VALID_AT,
            as_of_known_at=_KNOWN_AT,
            base_currency="USD",
        )
        assert exposure.status == "COMPLETED"
        factor_ids: list[str] = []
        for code, ccy, values in (
            ("FX_USD", "USD", ["0.01", "0.02", "0.03", "0.04"]),
            ("FX_EUR", "EUR", ["0.04", "0.03", "0.02", "0.01"]),
        ):
            fid = capture_factor(
                session,
                factor_code=code,
                factor_source="VENDOR_F",
                factor_family="CURRENCY",
                currency_code=ccy,
                acting_tenant=tenant,
                actor=FactorActor(actor_id="s"),
                valid_from=_T0,
            ).id
            factor = resolve_factor(session, fid, acting_tenant=tenant)
            for d, v in zip(_D, values, strict=True):
                capture_factor_return(
                    session,
                    factor,
                    return_date=d,
                    return_value=Decimal(v),
                    acting_tenant=tenant,
                    actor=FactorActor(actor_id="s"),
                    valid_from=_T0,
                )
            factor_ids.append(fid)
        session.flush()
        fx_mv = register_factor_exposure_model(
            session, tenant_id=tenant, actor_id="a", code_version="risk-v1"
        )
        fx_run = run_factor_exposure(
            session,
            acting_tenant=tenant,
            actor=FactorExposureActor(actor_id="a"),
            code_version="risk-v1",
            environment_id="ci",
            model_version_id=fx_mv.id,
            exposure_run_id=exposure.run.run_id,
            factor_ids=factor_ids,
        )
        assert fx_run.status == "COMPLETED"
        cov_mv = register_covariance_model(
            session, tenant_id=tenant, actor_id="a", code_version="risk-v1", window_observations=4
        )
        cov_run = run_covariance(
            session,
            acting_tenant=tenant,
            actor=CovarianceActor(actor_id="a"),
            code_version="risk-v1",
            environment_id="ci",
            model_version_id=cov_mv.id,
            factor_ids=factor_ids,
            as_of_valid_at=_VALID_AT,
        )
        assert cov_run.status == "COMPLETED"
        var_mv = register_var_model(
            session, tenant_id=tenant, actor_id="a", code_version="risk-v1", confidence_level="0.99"
        )
        var_run = run_var(
            session,
            acting_tenant=tenant,
            actor=VarActor(actor_id="a"),
            code_version="risk-v1",
            environment_id="ci",
            model_version_id=var_mv.id,
            exposure_run_id=fx_run.run.run_id,
            covariance_run_id=cov_run.run.run_id,
        )
        assert var_run.status == "COMPLETED"

        boundary_runs: list[str] = []
        for vdate, marks in ((_B0, ("300.00", "400.00")), (_B1, ("290.00", "390.00"))):
            for inst, mark in zip(insts, marks, strict=True):
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
            boundary = run_exposure(
                session,
                acting_tenant=tenant,
                actor=ExposureActor(actor_id="a"),
                code_version="v1",
                environment_id="ci",
                portfolio_id=pf,
                as_of_valid_at=datetime(vdate.year, vdate.month, vdate.day, tzinfo=UTC),
                as_of_known_at=_KNOWN_AT,
                base_currency="USD",
            )
            assert boundary.status == "COMPLETED"
            boundary_runs.append(boundary.run.run_id)
        ret_mv = register_portfolio_return_model(
            session, tenant_id=tenant, actor_id="a", code_version="perf-v1"
        )
        session.flush()
        ret = run_portfolio_return(
            session,
            acting_tenant=tenant,
            actor=PortfolioReturnActor(actor_id="a"),
            code_version="perf-v1",
            environment_id="ci",
            model_version_id=ret_mv.id,
            exposure_run_ids=boundary_runs,
        )
        assert ret.status == "COMPLETED"

        bt_mv = register_var_backtest_model(
            session, tenant_id=tenant, actor_id="a", code_version="bt-v1"
        )
        session.flush()
        result = run_var_backtest(
            session,
            acting_tenant=tenant,
            actor=_ACT,
            code_version="bt-v1",
            environment_id="ci",
            model_version_id=bt_mv.id,
            portfolio_return_run_id=ret.run.run_id,
            var_run_ids=[var_run.run.run_id],
        )
        # 1 EXCEPTION_INDICATOR + EXCEPTION_COUNT + KUPIEC_LR (no Basel row off-domain).
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
            text("SELECT calculation_run_id FROM var_backtest_result")
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
        count = session.execute(text("SELECT count(*) FROM var_backtest_result")).scalar_one()
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
            session.execute(text("UPDATE var_backtest_result SET metric_value = 0"))
        assert _is_append_only_violation(upd.value)
        session.rollback()
        set_tenant_context(session, tenant)
        with pytest.raises(ProgrammingError) as dele:
            session.execute(text("DELETE FROM var_backtest_result"))
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
                "portfolio_return_run_id, portfolio_id FROM var_backtest_result LIMIT 1"
            )
        ).one()
        with pytest.raises(ProgrammingError) as forged:
            session.execute(
                text(
                    "INSERT INTO var_backtest_result (id, tenant_id, system_from, "
                    "calculation_run_id, input_snapshot_id, model_version_id, "
                    "portfolio_return_run_id, portfolio_id, metric_type, var_metric_type, "
                    "period_start, period_end, metric_value, n_pairs, n_exceptions, "
                    "confidence_level, horizon_days, base_currency) "
                    "VALUES (:id, :victim, now(), :run, :snap, :mv, :retrun, :pf, "
                    "'EXCEPTION_COUNT', 'VAR_PARAMETRIC', :d0, :d1, 1, 1, 1, 0.99, 1, 'USD')"
                ),
                {
                    "id": str(uuid.uuid4()),
                    "victim": victim,  # a FOREIGN tenant_id under the acting context
                    "run": str(row[0]),
                    "snap": str(row[1]),
                    "mv": str(row[2]),
                    "retrun": str(row[3]),
                    "pf": str(row[4]),
                    "d0": _B0,
                    "d1": _B1,
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
                    "WHERE tablename = 'var_backtest_result'"
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
                "WHERE run_type = 'VAR_BACKTEST' AND tenant_id = :t LIMIT 1"
            ),
            {"t": t1},
        ).scalar_one()
    finally:
        session.close()

    session = factory()
    try:
        set_tenant_context(session, t2)
        mv = register_var_backtest_model(session, tenant_id=t2, actor_id="a", code_version="bt-v1")
        session.flush()
        from irp_shared.snapshot import SnapshotNotFound

        with pytest.raises(SnapshotNotFound):
            run_var_backtest(
                session,
                acting_tenant=t2,
                actor=_ACT,
                code_version="bt-v1",
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
