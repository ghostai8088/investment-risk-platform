"""PostgreSQL-only proofs for P3-6 stress/scenario (ENT-029/030, the TENTH governed number),
run as the constrained NOSUPERUSER/NOBYPASSRLS ``irp_app`` role:

- symmetric FORCE-RLS tenant isolation on all THREE new tables (``scenario_definition`` EV,
  ``scenario_shock`` FR, ``scenario_result`` IA): visibility + no-context zero rows + forged-tenant
  42501 on the result table;
- the **P0001 append-only trigger** blocks UPDATE/DELETE on ``scenario_result`` at the DB
  (``irp_app`` is GRANTED UPDATE/DELETE so the rejection proves the trigger, not a privilege
  denial), while the FR ``scenario_shock`` supersede (an in-place close-out UPDATE) SUCCEEDS — the
  two temporal classes living side by side;
- the symmetric policy shape ×3 + the closed 5-table hybrid set unchanged (REAL SYSTEM_TENANT_ID);
- cross-tenant snapshot consume fails closed;
- the per-tenant audit hash chain verifies.

The FULL chain (portfolio -> exposure -> factor-exposure -> scenario definition + shocks -> a
scenario run) executes through the binders under ``set_tenant_context``.
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
from irp_shared.marketdata import (
    FactorActor,
    FxRateActor,
    capture_factor,
    capture_factor_return,
    capture_fx_rate,
    resolve_factor,
)
from irp_shared.portfolio import PortfolioActor, create_portfolio
from irp_shared.position import create_position
from irp_shared.position.service import PositionActor
from irp_shared.reference.instrument import create_instrument
from irp_shared.reference.service import ReferenceActor
from irp_shared.risk import (
    FactorExposureActor,
    ScenarioActor,
    capture_scenario_shock,
    create_scenario_definition,
    register_factor_exposure_model,
    register_scenario_model,
    run_factor_exposure,
    run_scenario,
    supersede_scenario_shock,
)
from irp_shared.valuation import create_valuation
from irp_shared.valuation.service import ValuationActor

URL = os.environ.get("IRP_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="requires PostgreSQL (IRP_TEST_DATABASE_URL)")

_P3_6 = ("scenario_definition", "scenario_shock", "scenario_result")
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
    "model",
    "model_version",
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
_ACT = ScenarioActor(actor_id="a")


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
        for table in (*_P3_6, *_RUN, *_SNAP, *_DEPS, *_RAILS):
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


def _currency_factor(session, tenant: str, code: str, ccy: str) -> str:  # noqa: ANN001
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
    for d, v in zip(_D, ["0.01", "0.02", "0.03", "0.04"], strict=True):
        capture_factor_return(
            session,
            factor,
            return_date=d,
            return_value=Decimal(v),
            acting_tenant=tenant,
            actor=FactorActor(actor_id="s"),
            valid_from=_T0,
        )
    return fid


def _seed_and_run(factory, tenant: str) -> tuple[str, str]:  # noqa: ANN001
    """The FULL chain -> a COMPLETED scenario run. Returns (run_id, scenario_definition_id)."""
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
        for code, mark, ccy in (("I-USD", "300.00", "USD"), ("I-EUR", "400.00", "EUR")):
            inst = create_instrument(
                session,
                tenant_id=tenant,
                code=f"{code}-{uuid.uuid4().hex[:6]}",
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
        fid_usd = _currency_factor(session, tenant, "FX_USD", "USD")
        fid_eur = _currency_factor(session, tenant, "FX_EUR", "EUR")
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
            factor_ids=[fid_usd, fid_eur],
        )
        assert fx_run.status == "COMPLETED"

        definition = create_scenario_definition(
            session,
            code="CRASH",
            name="Crash",
            scenario_type="HISTORICAL",
            acting_tenant=tenant,
            actor=_ACT,
        )
        session.flush()
        for fid, shock in ((fid_usd, "-0.10"), (fid_eur, "0.05")):
            capture_scenario_shock(
                session,
                scenario_definition_id=definition.id,
                factor_id=fid,
                shock_value=Decimal(shock),
                acting_tenant=tenant,
                actor=_ACT,
                valid_from=_T0,
            )
        session.flush()
        sc_mv = register_scenario_model(
            session, tenant_id=tenant, actor_id="a", code_version="s-v1"
        )
        session.flush()
        result = run_scenario(
            session,
            acting_tenant=tenant,
            actor=_ACT,
            code_version="s-v1",
            environment_id="ci",
            model_version_id=sc_mv.id,
            factor_exposure_run_id=fx_run.run.run_id,
            scenario_definition_id=definition.id,
        )
        # 2 per-factor SCENARIO_PNL rows + 1 SCENARIO_PNL_TOTAL row.
        assert result.status == "COMPLETED" and len(result.rows) == 3
        session.commit()
        return result.run.run_id, definition.id
    finally:
        session.close()


def test_tenant_isolation(app_url: str) -> None:
    engine = make_engine(app_url, poolclass=NullPool)
    factory = make_session_factory(engine)
    t1, t2 = str(uuid.uuid4()), str(uuid.uuid4())
    run1, _ = _seed_and_run(factory, t1)
    _seed_and_run(factory, t2)

    session = factory()
    try:
        set_tenant_context(session, t1)
        # Visibility on all three tables is scoped to t1.
        rows = session.execute(text("SELECT calculation_run_id FROM scenario_result")).fetchall()
        assert rows and all(str(r[0]) == run1 for r in rows)
        for table in _P3_6:
            owners = session.execute(
                text(f"SELECT DISTINCT tenant_id FROM {table}")  # noqa: S608 - fixed table list
            ).fetchall()
            assert owners and all(str(r[0]) == t1 for r in owners)
    finally:
        session.close()
        engine.dispose()


def test_no_context_read_returns_zero_rows(app_url: str) -> None:
    engine = make_engine(app_url, poolclass=NullPool)
    factory = make_session_factory(engine)
    _seed_and_run(factory, str(uuid.uuid4()))
    session = factory()
    try:
        for table in _P3_6:
            count = session.execute(
                text(f"SELECT count(*) FROM {table}")  # noqa: S608 - fixed table list
            ).scalar_one()
            assert count == 0  # FORCE RLS: no tenant context -> zero rows
    finally:
        session.close()
        engine.dispose()


def test_append_only_result_but_fr_shock_supersede_succeeds(app_url: str) -> None:
    engine = make_engine(app_url, poolclass=NullPool)
    factory = make_session_factory(engine)
    tenant = str(uuid.uuid4())
    _, def_id = _seed_and_run(factory, tenant)

    session = factory()
    try:
        set_tenant_context(session, tenant)
        # The IA result table rejects UPDATE and DELETE at the trigger.
        with pytest.raises(ProgrammingError) as upd:
            session.execute(text("UPDATE scenario_result SET pnl = 0"))
        assert _is_append_only_violation(upd.value)
        session.rollback()
        set_tenant_context(session, tenant)
        with pytest.raises(ProgrammingError) as dele:
            session.execute(text("DELETE FROM scenario_result"))
        assert _is_append_only_violation(dele.value)
        session.rollback()

        # The FR shock table, by contrast, permits the close-out UPDATE a supersede performs.
        set_tenant_context(session, tenant)
        fid = session.execute(
            text(
                "SELECT factor_id FROM scenario_shock "
                "WHERE scenario_definition_id = :d AND valid_to IS NULL "
                "AND system_to IS NULL LIMIT 1"
            ),
            {"d": def_id},
        ).scalar_one()
        superseded = supersede_scenario_shock(
            session,
            scenario_definition_id=def_id,
            factor_id=str(fid),
            shock_value=Decimal("-0.20"),
            acting_tenant=tenant,
            actor=_ACT,
            effective_at=datetime(2026, 6, 15, tzinfo=UTC),
        )
        assert superseded.record_version == 2
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
                "scenario_definition_id FROM scenario_result LIMIT 1"
            )
        ).one()
        with pytest.raises(ProgrammingError) as forged:
            session.execute(
                text(
                    "INSERT INTO scenario_result (id, tenant_id, system_from, "
                    "calculation_run_id, input_snapshot_id, model_version_id, "
                    "scenario_definition_id, scenario_code, metric_type, pnl, "
                    "n_factors_exposed, n_factors_shocked, n_shocks_unmatched, base_currency) "
                    "VALUES (:id, :victim, now(), :run, :snap, :mv, :def, "
                    "'CRASH', 'SCENARIO_PNL_TOTAL', 1, 2, 2, 0, 'USD')"
                ),
                {
                    "id": str(uuid.uuid4()),
                    "victim": victim,  # a FOREIGN tenant_id under the acting context
                    "run": str(row[0]),
                    "snap": str(row[1]),
                    "mv": str(row[2]),
                    "def": str(row[3]),
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
            for table in _P3_6:
                qual, check = conn.execute(
                    text("SELECT qual, with_check FROM pg_policies WHERE tablename = :t"),
                    {"t": table},
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
    _, def1 = _seed_and_run(factory, t1)

    session = factory()
    try:
        set_tenant_context(session, t1)
        snap = session.execute(
            text(
                "SELECT input_snapshot_id FROM calculation_run "
                "WHERE run_type = 'SCENARIO' AND tenant_id = :t LIMIT 1"
            ),
            {"t": t1},
        ).scalar_one()
    finally:
        session.close()

    session = factory()
    try:
        set_tenant_context(session, t2)
        mv = register_scenario_model(session, tenant_id=t2, actor_id="a", code_version="s-v1")
        session.flush()
        from irp_shared.snapshot import SnapshotNotFound

        with pytest.raises(SnapshotNotFound):
            run_scenario(
                session,
                acting_tenant=t2,
                actor=_ACT,
                code_version="s-v1",
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
