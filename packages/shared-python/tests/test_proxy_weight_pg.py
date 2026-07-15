"""PostgreSQL-only proofs for PA-3 ``proxy_weight_estimate_result`` (ENT-057, IA — the governed OLS
proxy-weight regression v1), run as the constrained NOSUPERUSER/NOBYPASSRLS ``irp_app`` role:

- symmetric FORCE-RLS tenant isolation (visibility + no-context zero rows + forged-tenant 42501);
- the **P0001 append-only trigger** blocks UPDATE/DELETE at the DB (``irp_app`` is GRANTED
  UPDATE/DELETE so the rejection proves the trigger, not a privilege denial);
- the symmetric policy shape + the closed 5-table hybrid set unchanged;
- the per-tenant audit hash chain verifies.

The full chain (portfolio -> private instrument -> quarterly marks -> a DESMOOTHED_RETURN run ->
candidate CURRENCY factors + returns -> a proxy-weight estimate) executes through the binders under
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
from irp_shared.marketdata.factor import (
    FactorActor,
    capture_factor,
    capture_factor_return,
    resolve_factor,
)
from irp_shared.perf import (
    DesmoothedReturnActor,
    register_desmoothed_return_model,
    run_desmoothed_return,
)
from irp_shared.portfolio import PortfolioActor, create_portfolio
from irp_shared.reference.instrument import create_instrument
from irp_shared.reference.service import ReferenceActor
from irp_shared.risk import (
    ProxyWeightEstimateActor,
    register_proxy_weight_regression_model,
    run_proxy_weight_estimate,
)
from irp_shared.valuation import create_valuation
from irp_shared.valuation.service import ValuationActor

URL = os.environ.get("IRP_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="requires PostgreSQL (IRP_TEST_DATABASE_URL)")

_PA_3 = ("proxy_weight_estimate_result",)
_P1B1_HYBRID = ("currency", "calendar", "calendar_holiday", "rating_scale", "rating_grade")
_DEPS = (
    "portfolio",
    "instrument",
    "legal_entity",
    "issuer",
    "currency",
    "valuation",
    "factor",
    "factor_return",
    "desmoothed_return_result",
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
_T0 = datetime(2024, 6, 1, tzinfo=UTC)
_MARK_DATES = (
    date(2024, 9, 30),
    date(2024, 12, 31),
    date(2025, 3, 31),
    date(2025, 6, 30),
    date(2025, 9, 30),
    date(2025, 12, 31),
)
_MARK_VALUES = ("100.00", "103.00", "104.50", "108.00", "106.00", "111.00")


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
        for table in (*_PA_3, *_RUN, *_SNAP, *_DEPS, *_RAILS):
            conn.execute(text(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO irp_app"))
        conn.execute(text("GRANT SELECT, INSERT ON audit_event TO irp_app"))
    superuser.dispose()
    return (
        make_url(URL)
        .set(username="irp_app", password="ci_app_pw")
        .render_as_string(hide_password=False)
    )


def _seed_and_run(factory, tenant: str) -> str:  # noqa: ANN001
    """The full chain -> a COMPLETED proxy-weight estimate run (its run_id)."""
    from irp_shared.reference.models import Currency

    session = factory()
    try:
        set_tenant_context(session, tenant)
        session.add(Currency(tenant_id=tenant, code="USD", name="USD", valid_from=_T0))
        session.flush()
        pf = create_portfolio(
            session,
            tenant_id=tenant,
            code=f"PE-{uuid.uuid4().hex[:6]}",
            name="book",
            node_type="ACCOUNT",
            actor=PortfolioActor(actor_id="s"),
        ).id
        inst = create_instrument(
            session,
            tenant_id=tenant,
            code=f"FUND-{uuid.uuid4().hex[:6]}",
            name="Buyout Fund",
            asset_class="PRIVATE_EQUITY",
            actor=ReferenceActor(actor_id="s"),
        ).id
        for d, v in zip(_MARK_DATES, _MARK_VALUES, strict=True):
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
        dm = register_desmoothed_return_model(
            session, tenant_id=tenant, actor_id="a", code_version="pa1-v1", alpha="0.5"
        )
        session.flush()
        dr = run_desmoothed_return(
            session,
            acting_tenant=tenant,
            actor=DesmoothedReturnActor(actor_id="a"),
            code_version="pa1-v1",
            environment_id="ci",
            model_version_id=dm.id,
            portfolio_id=pf,
            instrument_id=inst,
            window_start=date(2024, 6, 1),
            window_end=date(2026, 1, 1),
        )
        fx_usd = capture_factor(
            session,
            factor_code="FX_USD",
            factor_source="VENDOR_F",
            factor_family="CURRENCY",
            currency_code=None,
            acting_tenant=tenant,
            actor=FactorActor(actor_id="s"),
            valid_from=_T0,
        ).id
        fx_eur = capture_factor(
            session,
            factor_code="FX_EUR",
            factor_source="VENDOR_F",
            factor_family="CURRENCY",
            currency_code=None,
            acting_tenant=tenant,
            actor=FactorActor(actor_id="s"),
            valid_from=_T0,
        ).id
        for fid, vals in (
            (fx_usd, ["0.01", "0.02", "-0.01", "0.03", "0.00"]),
            (fx_eur, ["0.02", "-0.01", "0.01", "0.00", "0.02"]),
        ):
            factor = resolve_factor(session, fid, acting_tenant=tenant)
            for d, v in zip(_MARK_DATES[1:], vals, strict=True):
                capture_factor_return(
                    session,
                    factor,
                    return_date=d,
                    return_value=Decimal(v),
                    acting_tenant=tenant,
                    actor=FactorActor(actor_id="s"),
                    valid_from=_T0,
                )
        session.flush()
        pm = register_proxy_weight_regression_model(
            session, tenant_id=tenant, actor_id="a", code_version="pa3-v1", min_observations=4
        )
        session.flush()
        result = run_proxy_weight_estimate(
            session,
            acting_tenant=tenant,
            actor=ProxyWeightEstimateActor(actor_id="a"),
            code_version="pa3-v1",
            environment_id="ci",
            model_version_id=str(pm.id),
            desmoothed_run_id=str(dr.run.run_id),
            factor_ids=[fx_usd, fx_eur],
        )
        # INTERCEPT + 2 WEIGHT + ESTIMATION_SUMMARY.
        assert result.status == "COMPLETED" and len(result.rows) == 4
        session.commit()
        return str(result.run.run_id)
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
            text("SELECT calculation_run_id FROM proxy_weight_estimate_result")
        ).fetchall()
        assert rows and all(str(r[0]) == run1 for r in rows)
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
            text("SELECT count(*) FROM proxy_weight_estimate_result")
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
            session.execute(text("UPDATE proxy_weight_estimate_result SET metric_value = 0"))
        assert _is_append_only_violation(upd.value)
        session.rollback()
        set_tenant_context(session, tenant)
        with pytest.raises(ProgrammingError) as dele:
            session.execute(text("DELETE FROM proxy_weight_estimate_result"))
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
                "SELECT calculation_run_id, input_snapshot_id, model_version_id, portfolio_id, "
                "instrument_id, source_desmoothed_run_id FROM proxy_weight_estimate_result LIMIT 1"
            )
        ).one()
        with pytest.raises(ProgrammingError) as forged:
            session.execute(
                text(
                    "INSERT INTO proxy_weight_estimate_result (id, tenant_id, system_from, "
                    "calculation_run_id, input_snapshot_id, model_version_id, portfolio_id, "
                    "instrument_id, source_desmoothed_run_id, metric_type, metric_value, "
                    "min_observations, series_currency) "
                    "VALUES (:id, :victim, now(), :run, :snap, :mv, :pf, :inst, :src, "
                    "'INTERCEPT', 0.01, 4, 'USD')"
                ),
                {
                    "id": str(uuid.uuid4()),
                    "victim": victim,
                    "run": str(row[0]),
                    "snap": str(row[1]),
                    "mv": str(row[2]),
                    "pf": str(row[3]),
                    "inst": str(row[4]),
                    "src": str(row[5]),
                },
            )
        assert _is_rls_violation(forged.value)
        session.rollback()
    finally:
        session.close()
        engine.dispose()


def test_symmetric_policy_and_closed_hybrid_set_unchanged(app_url: str) -> None:
    engine = make_engine(URL, poolclass=NullPool)
    try:
        with engine.connect() as conn:
            qual, check = conn.execute(
                text(
                    "SELECT qual, with_check FROM pg_policies "
                    "WHERE tablename = 'proxy_weight_estimate_result'"
                )
            ).one()
            assert "app.current_tenant" in qual and "app.current_tenant" in check
            assert "SYSTEM" not in qual.upper().replace("CURRENT_SETTING", "")
            from irp_shared.entitlement.bootstrap import SYSTEM_TENANT_ID

            hybrid = conn.execute(
                text("SELECT tablename FROM pg_policies WHERE qual LIKE :pat ORDER BY tablename"),
                {"pat": f"%{SYSTEM_TENANT_ID}%"},
            ).fetchall()
            assert {r[0] for r in hybrid} == set(_P1B1_HYBRID)
    finally:
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
