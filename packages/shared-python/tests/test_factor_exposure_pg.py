"""PostgreSQL-only proofs for P3-3 ``factor_exposure_result`` (ENT-028 family, IA — allocation
v1), run as the constrained NOSUPERUSER/NOBYPASSRLS ``irp_app`` role (the CI/pipeline posture):

- symmetric FORCE-RLS tenant isolation (visibility + no-context zero rows + forged-tenant 42501);
- the **P0001 append-only trigger** blocks UPDATE/DELETE at the DB (``irp_app`` is GRANTED
  UPDATE/DELETE so the rejection proves the trigger, not a privilege denial);
- the symmetric policy shape + the closed 5-table hybrid set unchanged;
- cross-tenant consume fails closed;
- the per-tenant audit hash chain verifies.

The full governed setup (portfolio → position → valuation → exposure run → factor → model →
factor-exposure run) executes through the binders under ``set_tenant_context``.
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
from irp_shared.marketdata import ProxyMappingActor, capture_proxy_mapping
from irp_shared.marketdata.factor import FactorActor, capture_factor
from irp_shared.portfolio import PortfolioActor, create_portfolio
from irp_shared.position import create_position
from irp_shared.position.service import PositionActor
from irp_shared.reference.instrument import create_instrument
from irp_shared.reference.service import ReferenceActor
from irp_shared.risk import (
    FactorExposureActor,
    register_factor_exposure_model,
    register_factor_exposure_proxy_model,
    run_factor_exposure,
)
from irp_shared.valuation import create_valuation
from irp_shared.valuation.service import ValuationActor

URL = os.environ.get("IRP_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="requires PostgreSQL (IRP_TEST_DATABASE_URL)")

_P3_3 = ("factor_exposure_result",)
_P1B1_HYBRID = ("currency", "calendar", "calendar_holiday", "rating_scale", "rating_grade")
_DEPS = (
    "proxy_mapping",
    "portfolio",
    "position",
    "valuation",
    "instrument",
    "legal_entity",
    "issuer",
    "currency",
    "exposure_aggregate",
    "factor",
    "factor_return",
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
_ACT = FactorExposureActor(actor_id="a")


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
        for table in (*_P3_3, *_RUN, *_SNAP, *_DEPS, *_RAILS):
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

    return Currency(tenant_id=tenant, code=code, name=code, valid_from=_VALID_AT)


def _seed_and_run(factory, tenant: str) -> str:  # noqa: ANN001
    """A tenant with a governed exposure run + a CURRENCY factor + a registered model -> a
    COMPLETED factor-exposure run (its run_id)."""
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
            asset_class="BOND",
            actor=ReferenceActor(actor_id="s"),
        ).id
        create_position(
            session,
            portfolio_id=pf,
            instrument_id=inst,
            acting_tenant=tenant,
            actor=PositionActor(actor_id="s"),
            quantity=Decimal("100"),
            valid_from=_T0,
        )
        create_valuation(
            session,
            portfolio_id=pf,
            instrument_id=inst,
            valuation_date=_VD,
            acting_tenant=tenant,
            actor=ValuationActor(actor_id="s"),
            mark_value=Decimal("12.50"),
            currency_code="USD",
            valid_from=_T0,
        )
        exp = run_exposure(
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
        fac = capture_factor(
            session,
            factor_code=f"FX_USD_{uuid.uuid4().hex[:6]}",
            factor_source="VENDOR_F",
            factor_family="CURRENCY",
            currency_code="USD",
            acting_tenant=tenant,
            actor=FactorActor(actor_id="s"),
            valid_from=_T0,
        ).id
        mv = register_factor_exposure_model(
            session, tenant_id=tenant, actor_id="a", code_version="risk-v1"
        )
        session.flush()
        result = run_factor_exposure(
            session,
            acting_tenant=tenant,
            actor=_ACT,
            code_version="risk-v1",
            environment_id="ci",
            model_version_id=mv.id,
            exposure_run_id=exp.run.run_id,
            factor_ids=[fac],
        )
        assert result.status == "COMPLETED" and len(result.rows) == 1
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
            text("SELECT calculation_run_id FROM factor_exposure_result")
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
        count = session.execute(text("SELECT count(*) FROM factor_exposure_result")).scalar_one()
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
        # irp_app HAS UPDATE/DELETE grants -> a rejection is the P0001 trigger, not 42501.
        with pytest.raises(ProgrammingError) as upd:
            session.execute(text("UPDATE factor_exposure_result SET exposure_amount = 0"))
        assert _is_append_only_violation(upd.value)
        session.rollback()
        set_tenant_context(session, tenant)
        with pytest.raises(ProgrammingError) as dele:
            session.execute(text("DELETE FROM factor_exposure_result"))
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
                "SELECT calculation_run_id, input_snapshot_id, model_version_id "
                "FROM factor_exposure_result LIMIT 1"
            )
        ).one()
        with pytest.raises(ProgrammingError) as forged:
            session.execute(
                text(
                    "INSERT INTO factor_exposure_result (id, tenant_id, system_from, "
                    "calculation_run_id, input_snapshot_id, model_version_id, portfolio_id, "
                    "instrument_id, factor_id, factor_code, factor_family, base_currency, "
                    "mark_currency, loading, exposure_amount) VALUES (:id, :victim, now(), "
                    ":run, :snap, :mv, :pf, :inst, :fac, 'X', 'CURRENCY', 'USD', 'USD', 1, 1)"
                ),
                {
                    "id": str(uuid.uuid4()),
                    "victim": victim,  # a FOREIGN tenant_id under t1's context
                    "run": str(row[0]),
                    "snap": str(row[1]),
                    "mv": str(row[2]),
                    "pf": str(uuid.uuid4()),
                    "inst": str(uuid.uuid4()),
                    "fac": str(uuid.uuid4()),
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
                    "WHERE tablename = 'factor_exposure_result'"
                )
            ).one()
            assert "app.current_tenant" in qual and "app.current_tenant" in check
            assert "SYSTEM" not in qual.upper().replace("CURRENT_SETTING", "")  # never hybrid
            # Probe by the REAL system-tenant id from the entitlement bootstrap — the prior
            # hardcoded ...000000 UUID matched ZERO policies, making the assertion vacuous
            # (the 2026-07 P3-4 review finding).
            from irp_shared.entitlement.bootstrap import SYSTEM_TENANT_ID

            hybrid = conn.execute(
                text("SELECT tablename FROM pg_policies WHERE qual LIKE :pat ORDER BY tablename"),
                {"pat": f"%{SYSTEM_TENANT_ID}%"},
            ).fetchall()
            # EQUALITY, not subset: a dropped hybrid policy is as much a defect as an added
            # one (the 2026-07 P3-4 review fold, applied to this P3-3 twin as well).
            assert {r[0] for r in hybrid} == set(_P1B1_HYBRID)
    finally:
        engine.dispose()


def test_cross_tenant_consume_fails_closed(app_url: str) -> None:
    engine = make_engine(app_url, poolclass=NullPool)
    factory = make_session_factory(engine)
    t1, t2 = str(uuid.uuid4()), str(uuid.uuid4())
    _seed_and_run(factory, t1)

    session = factory()
    try:
        set_tenant_context(session, t1)
        exp_run = session.execute(
            text(
                "SELECT run_id FROM calculation_run "
                "WHERE run_type = 'EXPOSURE_AGGREGATE' AND tenant_id = :t LIMIT 1"
            ),
            {"t": t1},
        ).scalar_one()
    finally:
        session.close()

    session = factory()
    try:
        set_tenant_context(session, t2)
        session.add(_currency(t2, "USD"))
        session.flush()
        mv = register_factor_exposure_model(
            session, tenant_id=t2, actor_id="a", code_version="risk-v1"
        )
        fac = capture_factor(
            session,
            factor_code="FX_USD",
            factor_source="VENDOR_F",
            factor_family="CURRENCY",
            currency_code="USD",
            acting_tenant=t2,
            actor=FactorActor(actor_id="s"),
            valid_from=_T0,
        ).id
        session.flush()
        from irp_shared.exposure.service import ExposureRunNotVisible

        with pytest.raises(ExposureRunNotVisible):
            run_factor_exposure(
                session,
                acting_tenant=t2,
                actor=_ACT,
                code_version="risk-v1",
                environment_id="ci",
                model_version_id=mv.id,
                exposure_run_id=str(exp_run),  # t1's exposure run under t2's context
                factor_ids=[fac],
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


def test_failed_run_persists_reason_on_pg(app_url: str) -> None:
    """P3-C1: the scaffold's FAILED tail — incl. the UPDATE of the new
    ``calculation_run.failure_reason`` column — executed under FORCE RLS on PostgreSQL (the
    2026-07 review fold: CI previously never drove a FAILED run on PG)."""
    engine = make_engine(app_url, poolclass=NullPool)
    factory = make_session_factory(engine)
    tenant = str(uuid.uuid4())
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
        inst = create_instrument(
            session,
            tenant_id=tenant,
            code=f"I-{uuid.uuid4().hex[:6]}",
            name="i",
            asset_class="BOND",
            actor=ReferenceActor(actor_id="s"),
        ).id
        create_position(
            session,
            portfolio_id=pf,
            instrument_id=inst,
            acting_tenant=tenant,
            actor=PositionActor(actor_id="s"),
            quantity=Decimal("100"),
            valid_from=_T0,
        )
        create_valuation(
            session,
            portfolio_id=pf,
            instrument_id=inst,
            valuation_date=_VD,
            acting_tenant=tenant,
            actor=ValuationActor(actor_id="s"),
            mark_value=Decimal("12.50"),
            currency_code="USD",
            valid_from=_T0,
        )
        exp = run_exposure(
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
        eur_factor = capture_factor(  # the USD atom is UNMAPPED against an EUR-only set
            session,
            factor_code=f"FX_EUR_{uuid.uuid4().hex[:6]}",
            factor_source="VENDOR_F",
            factor_family="CURRENCY",
            currency_code="EUR",
            acting_tenant=tenant,
            actor=FactorActor(actor_id="s"),
            valid_from=_T0,
        ).id
        mv = register_factor_exposure_model(
            session, tenant_id=tenant, actor_id="a", code_version="risk-v1"
        )
        session.flush()
        result = run_factor_exposure(
            session,
            acting_tenant=tenant,
            actor=_ACT,
            code_version="risk-v1",
            environment_id="ci",
            model_version_id=mv.id,
            exposure_run_id=exp.run.run_id,
            factor_ids=[eur_factor],
        )
        assert result.status == "FAILED" and result.rows == []
        session.commit()
        run_id = result.run.run_id
        reason = result.failure_reason
    finally:
        session.close()

    session = factory()
    try:
        set_tenant_context(session, tenant)
        persisted = session.execute(
            text("SELECT failure_reason FROM calculation_run WHERE run_id = :r"), {"r": run_id}
        ).scalar_one()
        assert persisted == reason and "unmapped-atom" in persisted
    finally:
        session.close()
        engine.dispose()


def test_proxy_pins_and_run_under_rls(app_url: str) -> None:
    """PA-2: the proxy model's snapshot pins proxy_mapping FR rows and the dispatched run
    COMPLETES as the constrained irp_app role under FORCE RLS (the one promised PG proxy case;
    verify_snapshot proves the pinned proxy content re-resolves tenant-scoped)."""
    from irp_shared.snapshot import verify_snapshot

    engine = make_engine(app_url, poolclass=NullPool)
    factory = make_session_factory(engine)
    tenant = str(uuid.uuid4())
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
            code=f"I-PE-{uuid.uuid4().hex[:6]}",
            name="Buyout Fund IV",
            asset_class="PRIVATE_EQUITY",
            actor=ReferenceActor(actor_id="s"),
        ).id
        create_position(
            session,
            portfolio_id=pf,
            instrument_id=inst,
            acting_tenant=tenant,
            actor=PositionActor(actor_id="s"),
            quantity=Decimal("100"),
            valid_from=_T0,
        )
        create_valuation(
            session,
            portfolio_id=pf,
            instrument_id=inst,
            valuation_date=_VD,
            acting_tenant=tenant,
            actor=ValuationActor(actor_id="s"),
            mark_value=Decimal("500.00"),
            currency_code="USD",
            valid_from=_T0,
        )
        exp = run_exposure(
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
        fac = capture_factor(
            session,
            factor_code=f"FX_USD_{uuid.uuid4().hex[:6]}",
            factor_source="VENDOR_F",
            factor_family="CURRENCY",
            currency_code="USD",
            acting_tenant=tenant,
            actor=FactorActor(actor_id="s"),
            valid_from=_T0,
        ).id
        capture_proxy_mapping(
            session,
            private_instrument_id=inst,
            factor_id=fac,
            weight=Decimal("0.6"),
            acting_tenant=tenant,
            actor=ProxyMappingActor(actor_id="s"),
            valid_from=_T0,
        )
        mv = register_factor_exposure_proxy_model(
            session, tenant_id=tenant, actor_id="a", code_version="pa2-v1"
        )
        session.flush()
        result = run_factor_exposure(
            session,
            acting_tenant=tenant,
            actor=_ACT,
            code_version="pa2-v1",
            environment_id="ci",
            model_version_id=mv.id,
            exposure_run_id=exp.run.run_id,
            factor_ids=[fac],
        )
        assert result.status == "COMPLETED" and len(result.rows) == 1
        assert result.rows[0].loading == Decimal("0.6")
        assert result.rows[0].exposure_amount == Decimal("30000.000000")  # 0.6 * 50000
        assert verify_snapshot(
            session, snapshot_id=result.run.input_snapshot_id, acting_tenant=tenant
        ).ok
        session.commit()
    finally:
        session.close()
        engine.dispose()
