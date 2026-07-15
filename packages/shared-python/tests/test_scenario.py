"""SQLite unit/behavior tests for P3-6 stress/scenario (ENT-029/030, the TENTH governed number).

Covers: the scenario_definition EV protocol (create/update/list; vocab enforced); the scenario_shock
FR protocol (capture/supersede/correct/reconstruct/list; the MD-H1 window-coherence 422; CURRENCY-
scope refusal); the FULL-STACK golden over a REAL chain (portfolio -> exposure -> factor-exposure ->
scenario) with the P&L hand-derived from the fixture; TR-09 reproducibility (both sides); the
partial-coverage semantics + coverage counts; the exact-sum invariant; the pre-create refusal
battery (ambiguous input, unregistered model, empty shock set) with NO RUNNING orphan; and the
append-only / run_type!=metric / zero-RISK.*-audit / migration-head guards. PG legs live in
test_scenario_pg.py.

Golden derivation: the factor-exposure run yields FX_USD exposure 30000 (inst I-USD: qty 100 x mark
300, USD) + FX_EUR exposure 40000 (inst I-EUR: qty 100 x mark 400 x fx 1.0, base USD). Shocking
FX_USD by -0.10 and FX_EUR by +0.05: pnl_USD = 30000*-0.10 = -3000; pnl_EUR = 40000*0.05 = +2000;
total = -1000. FX_EUR left UNSHOCKED in the partial-coverage test -> pnl_EUR = 0, total = -3000.
"""

from __future__ import annotations

import pathlib
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from run_assertions import assert_no_running_orphan
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from irp_shared.audit.models import AppendOnlyViolation, AuditEvent
from irp_shared.calc.models import CalculationRun, RunStatus
from irp_shared.db.session import make_engine, make_session_factory
from irp_shared.entitlement.bootstrap import SYSTEM_TENANT_ID
from irp_shared.exposure import ExposureActor, run_exposure
from irp_shared.marketdata import (
    FactorActor,
    FxRateActor,
    capture_factor,
    capture_factor_return,
    capture_fx_rate,
    resolve_factor,
)
from irp_shared.model.service import UnregisteredModelError
from irp_shared.models import Base
from irp_shared.portfolio import PortfolioActor, create_portfolio
from irp_shared.position import create_position
from irp_shared.position.service import PositionActor
from irp_shared.reference.instrument import create_instrument
from irp_shared.reference.models import Currency
from irp_shared.reference.service import ReferenceActor
from irp_shared.risk import (
    METRIC_TYPE_SCENARIO_PNL,
    METRIC_TYPE_SCENARIO_PNL_TOTAL,
    RUN_TYPE_SCENARIO,
    FactorExposureActor,
    ScenarioActor,
    ScenarioInputError,
    ScenarioValueError,
    capture_scenario_shock,
    create_scenario_definition,
    list_scenario_results,
    list_scenario_shocks,
    reconstruct_scenario_shock_as_of,
    register_factor_exposure_model,
    register_scenario_model,
    run_factor_exposure,
    run_scenario,
    supersede_scenario_shock,
    update_scenario_definition,
)
from irp_shared.snapshot import ScenarioSnapshotError, verify_snapshot
from irp_shared.valuation import create_valuation
from irp_shared.valuation.service import ValuationActor

T0 = datetime(2026, 1, 1, tzinfo=UTC)
VALID_AT = datetime(2026, 6, 1, tzinfo=UTC)
KNOWN_AT = datetime(2030, 1, 1, tzinfo=UTC)
VD = date(2026, 6, 1)
D1, D2, D3, D4 = (date(2026, 5, 26), date(2026, 5, 27), date(2026, 5, 28), date(2026, 5, 29))
ACT = ScenarioActor(actor_id="analyst")


@pytest.fixture
def session() -> Session:
    engine = make_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    db = make_session_factory(engine)()
    try:
        yield db
    finally:
        db.close()
        engine.dispose()


def _currency_factor(db: Session, tenant: str, code: str, ccy: str) -> str:
    if (
        db.execute(
            select(Currency).where(Currency.tenant_id == SYSTEM_TENANT_ID, Currency.code == ccy)
        ).scalar_one_or_none()
        is None
    ):
        db.add(Currency(tenant_id=SYSTEM_TENANT_ID, code=ccy, name=ccy, valid_from=T0))
        db.flush()
    fid = capture_factor(
        db,
        factor_code=code,
        factor_source="VENDOR_F",
        factor_family="CURRENCY",
        currency_code=ccy,
        acting_tenant=tenant,
        actor=FactorActor(actor_id="s"),
        valid_from=T0,
    ).id
    factor = resolve_factor(db, fid, acting_tenant=tenant)
    for d, v in zip((D1, D2, D3, D4), ["0.01", "0.02", "0.03", "0.04"], strict=True):
        capture_factor_return(
            db,
            factor,
            return_date=d,
            return_value=Decimal(v),
            acting_tenant=tenant,
            actor=FactorActor(actor_id="s"),
            valid_from=T0,
        )
    db.flush()
    return fid


def _seed_factor_exposure_run(db: Session, tenant: str) -> tuple[str, str, str]:
    """Seed portfolio -> exposure -> factor-exposure run. Returns (fx_run_id, fid_usd, fid_eur)
    with FX_USD exposure 30000 + FX_EUR exposure 40000, base USD."""
    for code in ("USD", "EUR"):
        if (
            db.execute(
                select(Currency).where(
                    Currency.tenant_id == SYSTEM_TENANT_ID, Currency.code == code
                )
            ).scalar_one_or_none()
            is None
        ):
            db.add(Currency(tenant_id=SYSTEM_TENANT_ID, code=code, name=code, valid_from=T0))
    db.flush()
    pf = create_portfolio(
        db,
        tenant_id=tenant,
        code=f"ACCT-{uuid.uuid4().hex[:6]}",
        name="acct",
        node_type="ACCOUNT",
        actor=PortfolioActor(actor_id="s"),
    ).id
    for code, mark, ccy in (("I-USD", "300.00", "USD"), ("I-EUR", "400.00", "EUR")):
        inst = create_instrument(
            db,
            tenant_id=tenant,
            code=f"{code}-{uuid.uuid4().hex[:6]}",
            name="i",
            asset_class="BOND",
            actor=ReferenceActor(actor_id="s"),
        ).id
        create_position(
            db,
            portfolio_id=pf,
            instrument_id=inst,
            acting_tenant=tenant,
            actor=PositionActor(actor_id="s"),
            quantity=Decimal("100"),
            valid_from=T0,
        )
        create_valuation(
            db,
            portfolio_id=pf,
            instrument_id=inst,
            valuation_date=VD,
            acting_tenant=tenant,
            actor=ValuationActor(actor_id="s"),
            mark_value=Decimal(mark),
            currency_code=ccy,
            valid_from=T0,
        )
    capture_fx_rate(
        db,
        base_currency="EUR",
        quote_currency="USD",
        rate_date=VD,
        rate=Decimal("1.000000000000"),
        acting_tenant=tenant,
        actor=FxRateActor(actor_id="s"),
        valid_from=T0,
    )
    exposure = run_exposure(
        db,
        acting_tenant=tenant,
        actor=ExposureActor(actor_id="a"),
        code_version="v1",
        environment_id="ci",
        portfolio_id=pf,
        as_of_valid_at=VALID_AT,
        as_of_known_at=KNOWN_AT,
        base_currency="USD",
    )
    fid_usd = _currency_factor(db, tenant, "FX_USD", "USD")
    fid_eur = _currency_factor(db, tenant, "FX_EUR", "EUR")
    fx_mv = register_factor_exposure_model(
        db, tenant_id=tenant, actor_id="a", code_version="risk-v1"
    )
    fx_run = run_factor_exposure(
        db,
        acting_tenant=tenant,
        actor=FactorExposureActor(actor_id="a"),
        code_version="risk-v1",
        environment_id="ci",
        model_version_id=fx_mv.id,
        exposure_run_id=exposure.run.run_id,
        factor_ids=[fid_usd, fid_eur],
    )
    assert exposure.status == RunStatus.COMPLETED.value
    assert fx_run.status == RunStatus.COMPLETED.value and len(fx_run.rows) == 2
    return fx_run.run.run_id, fid_usd, fid_eur


def _scenario(db: Session, tenant: str, fid_usd: str, fid_eur: str | None = None) -> str:
    """A CRASH scenario shocking FX_USD -10% (+ FX_EUR +5% if given). Returns the definition id."""
    d = create_scenario_definition(
        db,
        code="CRASH",
        name="Crash",
        scenario_type="HISTORICAL",
        acting_tenant=tenant,
        actor=ACT,
    )
    db.flush()
    capture_scenario_shock(
        db,
        scenario_definition_id=d.id,
        factor_id=fid_usd,
        shock_value=Decimal("-0.10"),
        acting_tenant=tenant,
        actor=ACT,
        valid_from=T0,
    )
    if fid_eur is not None:
        capture_scenario_shock(
            db,
            scenario_definition_id=d.id,
            factor_id=fid_eur,
            shock_value=Decimal("0.05"),
            acting_tenant=tenant,
            actor=ACT,
            valid_from=T0,
        )
    db.flush()
    return d.id


def _run(db: Session, tenant: str, fx_run: str, def_id: str):  # noqa: ANN202
    mv = register_scenario_model(db, tenant_id=tenant, actor_id="a", code_version="s-v1")
    return run_scenario(
        db,
        acting_tenant=tenant,
        actor=ACT,
        code_version="s-v1",
        environment_id="ci",
        model_version_id=mv.id,
        factor_exposure_run_id=fx_run,
        scenario_definition_id=def_id,
    )


# ---------- definition EV + shock FR protocol ----------


def test_definition_ev_create_update_vocab(session: Session) -> None:
    t = str(uuid.uuid4())
    d = create_scenario_definition(
        session, code="C1", name="n", scenario_type="REGULATORY", acting_tenant=t, actor=ACT
    )
    assert d.record_version == 1 and d.scenario_type == "REGULATORY"
    d2 = update_scenario_definition(
        session, d, acting_tenant=t, actor=ACT, name="n2", scenario_type="HYPOTHETICAL"
    )
    assert d2.record_version == 2 and d2.scenario_type == "HYPOTHETICAL"
    with pytest.raises(ScenarioValueError):
        create_scenario_definition(
            session, code="C2", name="n", scenario_type="BOGUS", acting_tenant=t, actor=ACT
        )


def test_shock_fr_capture_supersede_correct_reconstruct(session: Session) -> None:
    t = str(uuid.uuid4())
    fid = _currency_factor(session, t, "FX_USD", "USD")
    d = create_scenario_definition(
        session, code="C", name="n", scenario_type="HISTORICAL", acting_tenant=t, actor=ACT
    )
    session.flush()
    s1 = capture_scenario_shock(
        session,
        scenario_definition_id=d.id,
        factor_id=fid,
        shock_value=Decimal("-0.10"),
        acting_tenant=t,
        actor=ACT,
        valid_from=T0,
        now=datetime(2026, 2, 1, tzinfo=UTC),  # system-from (knowledge time)
    )
    assert s1.record_version == 1 and s1.shock_value == Decimal("-0.100000000000")
    s2 = supersede_scenario_shock(
        session,
        scenario_definition_id=d.id,
        factor_id=fid,
        shock_value=Decimal("-0.15"),
        acting_tenant=t,
        actor=ACT,
        effective_at=VALID_AT,
        now=datetime(2026, 4, 1, tzinfo=UTC),  # superseded (known) LATER than the reconstruct
    )
    assert s2.record_version == 2 and s2.supersedes_id == s1.id
    head = list_scenario_shocks(session, scenario_definition_id=d.id, acting_tenant=t)
    assert len(head) == 1 and head[0].shock_value == Decimal("-0.150000000000")
    # bitemporal reconstruct: as-known-before the supersede, the original -0.10 is current.
    prior = reconstruct_scenario_shock_as_of(
        session,
        scenario_definition_id=d.id,
        factor_id=fid,
        valid_at=T0,
        known_at=datetime(2026, 3, 1, tzinfo=UTC),
        acting_tenant=t,
    )
    assert prior is not None and prior.shock_value == Decimal("-0.100000000000")


def test_shock_backdated_supersede_refused(session: Session) -> None:
    # MD-H1 window-coherence: effective_at at/before the head's valid_from (T0) is refused (-> 422).
    t = str(uuid.uuid4())
    fid = _currency_factor(session, t, "FX_USD", "USD")
    d = create_scenario_definition(
        session, code="C", name="n", scenario_type="HISTORICAL", acting_tenant=t, actor=ACT
    )
    session.flush()
    capture_scenario_shock(
        session,
        scenario_definition_id=d.id,
        factor_id=fid,
        shock_value=Decimal("-0.10"),
        acting_tenant=t,
        actor=ACT,
        valid_from=T0,
    )
    session.flush()
    with pytest.raises(ScenarioValueError):
        supersede_scenario_shock(
            session,
            scenario_definition_id=d.id,
            factor_id=fid,
            shock_value=Decimal("-0.15"),
            acting_tenant=t,
            actor=ACT,
            effective_at=T0,  # == valid_from -> zero-width, refused
        )


def test_non_currency_factor_shock_refused(session: Session) -> None:
    t = str(uuid.uuid4())
    session.add(Currency(tenant_id=SYSTEM_TENANT_ID, code="USD", name="USD", valid_from=T0))
    session.flush()
    style = capture_factor(
        session,
        factor_code="MOMENTUM",
        factor_source="V",
        factor_family="STYLE",
        acting_tenant=t,
        actor=FactorActor(actor_id="s"),
        valid_from=T0,
    ).id
    d = create_scenario_definition(
        session, code="C", name="n", scenario_type="HISTORICAL", acting_tenant=t, actor=ACT
    )
    session.flush()
    with pytest.raises(ScenarioValueError):
        capture_scenario_shock(
            session,
            scenario_definition_id=d.id,
            factor_id=style,
            shock_value=Decimal("-0.10"),
            acting_tenant=t,
            actor=ACT,
        )


# ---------- the full-stack golden + coverage + TR-09 ----------


def test_full_stack_golden_and_coverage(session: Session) -> None:
    t = str(uuid.uuid4())
    fx_run, fid_usd, fid_eur = _seed_factor_exposure_run(session, t)
    def_id = _scenario(session, t, fid_usd, fid_eur)  # shocks BOTH factors
    result = _run(session, t, fx_run, def_id)
    assert result.status == RunStatus.COMPLETED.value
    rows = {(r.metric_type, r.factor_code): r for r in result.rows}
    # per-factor P&L (the hand-derived golden): -3000 and +2000.
    assert rows[(METRIC_TYPE_SCENARIO_PNL, "FX_USD")].pnl == Decimal("-3000.000000")
    assert rows[(METRIC_TYPE_SCENARIO_PNL, "FX_EUR")].pnl == Decimal("2000.000000")
    # each per-factor row ECHOES its consumed inputs.
    assert rows[(METRIC_TYPE_SCENARIO_PNL, "FX_USD")].exposure_amount == Decimal("30000.000000")
    assert rows[(METRIC_TYPE_SCENARIO_PNL, "FX_USD")].shock_value == Decimal("-0.100000000000")
    total = rows[(METRIC_TYPE_SCENARIO_PNL_TOTAL, None)]
    assert total.pnl == Decimal("-1000.000000")  # exact sum of the quantized rows
    assert total.n_factors_exposed == 2 and total.n_factors_shocked == 2
    assert total.n_shocks_unmatched == 0


def test_partial_coverage_unnamed_factor_is_zero(session: Session) -> None:
    t = str(uuid.uuid4())
    fx_run, fid_usd, _fid_eur = _seed_factor_exposure_run(session, t)
    def_id = _scenario(session, t, fid_usd, fid_eur=None)  # shocks ONLY FX_USD
    result = _run(session, t, fx_run, def_id)
    rows = {(r.metric_type, r.factor_code): r for r in result.rows}
    # FX_EUR is exposed but unnamed -> shock 0 -> pnl 0 (a row still exists, shock echoed 0).
    eur = rows[(METRIC_TYPE_SCENARIO_PNL, "FX_EUR")]
    assert eur.shock_value == Decimal("0") and eur.pnl == Decimal("0.000000")
    total = rows[(METRIC_TYPE_SCENARIO_PNL_TOTAL, None)]
    assert total.pnl == Decimal("-3000.000000")  # only FX_USD moved
    assert total.n_factors_exposed == 2 and total.n_factors_shocked == 1
    assert total.n_shocks_unmatched == 0


def test_shock_on_unexposed_factor_is_unmatched(session: Session) -> None:
    t = str(uuid.uuid4())
    fx_run, fid_usd, _fid_eur = _seed_factor_exposure_run(session, t)
    # A THIRD currency factor the portfolio has NO exposure to.
    fid_gbp = _currency_factor(session, t, "FX_GBP", "GBP")
    d = create_scenario_definition(
        session, code="C", name="n", scenario_type="HISTORICAL", acting_tenant=t, actor=ACT
    )
    session.flush()
    for fid in (fid_usd, fid_gbp):
        capture_scenario_shock(
            session,
            scenario_definition_id=d.id,
            factor_id=fid,
            shock_value=Decimal("-0.10"),
            acting_tenant=t,
            actor=ACT,
            valid_from=T0,
        )
    session.flush()
    result = _run(session, t, fx_run, d.id)
    rows = {(r.metric_type, r.factor_code): r for r in result.rows}
    # GBP was shocked but not exposed -> NO row, counted in n_shocks_unmatched.
    assert (METRIC_TYPE_SCENARIO_PNL, "FX_GBP") not in rows
    total = rows[(METRIC_TYPE_SCENARIO_PNL_TOTAL, None)]
    assert total.n_shocks_unmatched == 1 and total.n_factors_shocked == 1


def test_tr09_reproducibility_both_sides(session: Session) -> None:
    t = str(uuid.uuid4())
    fx_run, fid_usd, fid_eur = _seed_factor_exposure_run(session, t)
    def_id = _scenario(session, t, fid_usd, fid_eur)
    first = _run(session, t, fx_run, def_id)
    total_1 = next(r.pnl for r in first.rows if r.metric_type == METRIC_TYPE_SCENARIO_PNL_TOTAL)
    snapshot_id = first.run.input_snapshot_id
    # (a) a LATER shock supersede must NOT move the historical run.
    supersede_scenario_shock(
        session,
        scenario_definition_id=def_id,
        factor_id=fid_usd,
        shock_value=Decimal("-0.99"),
        acting_tenant=t,
        actor=ACT,
        effective_at=datetime(2027, 1, 1, tzinfo=UTC),
    )
    session.flush()
    reread = list_scenario_results(session, first.run.run_id, acting_tenant=t)
    total_reread = next(r.pnl for r in reread if r.metric_type == METRIC_TYPE_SCENARIO_PNL_TOTAL)
    assert total_reread == total_1  # immovable
    # (b) a re-run against the SAME snapshot reproduces byte-identically.
    mv = register_scenario_model(session, tenant_id=t, actor_id="a", code_version="s-v1")
    second = run_scenario(
        session,
        acting_tenant=t,
        actor=ACT,
        code_version="s-v1",
        environment_id="ci",
        model_version_id=mv.id,
        snapshot_id=snapshot_id,
    )
    total_2 = next(r.pnl for r in second.rows if r.metric_type == METRIC_TYPE_SCENARIO_PNL_TOTAL)
    assert total_2 == total_1


# ---------- refusal battery (pre-create; no RUNNING orphan) ----------


def test_ambiguous_input_refused(session: Session) -> None:
    t = str(uuid.uuid4())
    fx_run, fid_usd, fid_eur = _seed_factor_exposure_run(session, t)
    def_id = _scenario(session, t, fid_usd, fid_eur)
    mv = register_scenario_model(session, tenant_id=t, actor_id="a", code_version="s-v1")
    before = session.execute(select(func.count()).select_from(CalculationRun)).scalar()
    with pytest.raises(ScenarioInputError):
        run_scenario(
            session,
            acting_tenant=t,
            actor=ACT,
            code_version="s-v1",
            environment_id="ci",
            model_version_id=mv.id,
            factor_exposure_run_id=fx_run,
            scenario_definition_id=def_id,
            snapshot_id=str(uuid.uuid4()),  # both build args AND a snapshot -> ambiguous
        )
    assert session.execute(select(func.count()).select_from(CalculationRun)).scalar() == before
    assert_no_running_orphan(session, run_type=RUN_TYPE_SCENARIO)


def test_empty_shock_set_refused(session: Session) -> None:
    t = str(uuid.uuid4())
    fx_run, _fid_usd, _fid_eur = _seed_factor_exposure_run(session, t)
    d = create_scenario_definition(
        session, code="EMPTY", name="n", scenario_type="HISTORICAL", acting_tenant=t, actor=ACT
    )
    session.flush()  # NO shocks captured
    mv = register_scenario_model(session, tenant_id=t, actor_id="a", code_version="s-v1")
    with pytest.raises(ScenarioSnapshotError):  # empty input set fails closed at snapshot build
        run_scenario(
            session,
            acting_tenant=t,
            actor=ACT,
            code_version="s-v1",
            environment_id="ci",
            model_version_id=mv.id,
            factor_exposure_run_id=fx_run,
            scenario_definition_id=d.id,
        )
    assert_no_running_orphan(session, run_type=RUN_TYPE_SCENARIO)


def test_unregistered_model_refused(session: Session) -> None:
    t = str(uuid.uuid4())
    fx_run, fid_usd, fid_eur = _seed_factor_exposure_run(session, t)
    def_id = _scenario(session, t, fid_usd, fid_eur)
    with pytest.raises(UnregisteredModelError):
        run_scenario(
            session,
            acting_tenant=t,
            actor=ACT,
            code_version="s-v1",
            environment_id="ci",
            model_version_id=str(uuid.uuid4()),  # not a registered version
            factor_exposure_run_id=fx_run,
            scenario_definition_id=def_id,
        )
    assert_no_running_orphan(session, run_type=RUN_TYPE_SCENARIO)


def test_shock_value_exceeding_column_capacity_refused(session: Session) -> None:
    # A shock is a signed RETURN fraction with no economic bound, but scenario_shock.shock_value is
    # Numeric(20,12) = 8 integer digits. |value| >= 1E8 overflows at flush as a PG DataError the
    # write handler cannot map -> a 500; the binder refuses it as a governed 422 BEFORE the write.
    t = str(uuid.uuid4())
    _fx_run, fid_usd, _fid_eur = _seed_factor_exposure_run(session, t)
    d = create_scenario_definition(
        session, code="BIG", name="n", scenario_type="HISTORICAL", acting_tenant=t, actor=ACT
    )
    session.flush()
    with pytest.raises(ScenarioValueError):
        capture_scenario_shock(
            session,
            scenario_definition_id=d.id,
            factor_id=fid_usd,
            shock_value=Decimal("1E8"),  # at the column's integer-digit ceiling
            acting_tenant=t,
            actor=ACT,
            valid_from=T0,
        )


def test_scenario_snapshot_verifies_and_survives_supersede(session: Session) -> None:
    # The AD-014 reproducibility check must be OPERATIVE for SCENARIO_INPUT snapshots:
    # _reresolve_content needs a COMPONENT_KIND_SCENARIO branch (re-reading the shock FR row + its
    # definition), else a pristine snapshot would ALWAYS report drift via the portfolio fallthrough.
    t = str(uuid.uuid4())
    fx_run, fid_usd, fid_eur = _seed_factor_exposure_run(session, t)
    def_id = _scenario(session, t, fid_usd, fid_eur)
    result = _run(session, t, fx_run, def_id)
    snap_id = result.run.input_snapshot_id
    assert verify_snapshot(session, snapshot_id=snap_id, acting_tenant=t).ok is True
    # TR-09: a shock supersede AFTER the pin does not perturb the byte-stable pinned content.
    supersede_scenario_shock(
        session,
        scenario_definition_id=def_id,
        factor_id=fid_usd,
        shock_value=Decimal("-0.20"),
        acting_tenant=t,
        actor=ACT,
        effective_at=VALID_AT,
    )
    assert verify_snapshot(session, snapshot_id=snap_id, acting_tenant=t).ok is True


def _seed_large_exposure_run(
    session: Session, tenant: str, qty: Decimal, mark: Decimal
) -> tuple[str, str]:
    """A single-USD-instrument factor-exposure run with a BOUNDARY-large exposure (qty x mark);
    returns (fx_run_id, fid_usd). Extreme magnitudes are labeled-boundary-only (realism rule)."""
    if (
        session.execute(
            select(Currency).where(Currency.tenant_id == SYSTEM_TENANT_ID, Currency.code == "USD")
        ).scalar_one_or_none()
        is None
    ):
        session.add(Currency(tenant_id=SYSTEM_TENANT_ID, code="USD", name="USD", valid_from=T0))
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
        code=f"I-USD-{uuid.uuid4().hex[:6]}",
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
        quantity=qty,
        valid_from=T0,
    )
    create_valuation(
        session,
        portfolio_id=pf,
        instrument_id=inst,
        valuation_date=VD,
        acting_tenant=tenant,
        actor=ValuationActor(actor_id="s"),
        mark_value=mark,
        currency_code="USD",
        valid_from=T0,
    )
    exposure = run_exposure(
        session,
        acting_tenant=tenant,
        actor=ExposureActor(actor_id="a"),
        code_version="v1",
        environment_id="ci",
        portfolio_id=pf,
        as_of_valid_at=VALID_AT,
        as_of_known_at=KNOWN_AT,
        base_currency="USD",
    )
    fid_usd = _currency_factor(session, tenant, "FX_USD", "USD")
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
        factor_ids=[fid_usd],
    )
    assert fx_run.status == RunStatus.COMPLETED.value
    return fx_run.run.run_id, fid_usd


def test_magnitude_overflow_is_committed_failed_not_raised(session: Session) -> None:
    # BOUNDARY: exposure 1E15 x shock 1E7 = 1E22 — the per-factor quantize to 6dp needs 29
    # coefficient digits (> the 28-digit context), so an UNGUARDED quantize would raise
    # InvalidOperation and escape as a 500 AFTER the run is RUNNING. The raw-product gate must
    # convert that to a COMMITTED FAILED.
    t = str(uuid.uuid4())
    fx_run, fid = _seed_large_exposure_run(session, t, Decimal("10000000000"), Decimal("100000"))
    d = create_scenario_definition(
        session, code="XL", name="n", scenario_type="HYPOTHETICAL", acting_tenant=t, actor=ACT
    )
    session.flush()
    capture_scenario_shock(
        session,
        scenario_definition_id=d.id,
        factor_id=fid,
        shock_value=Decimal("10000000"),  # 1E7 — below the 1E8 column ceiling, product hits 1E22
        acting_tenant=t,
        actor=ACT,
        valid_from=T0,
    )
    session.flush()
    result = _run(session, t, fx_run, d.id)
    assert result.status == RunStatus.FAILED.value  # committed FAILED, NOT a raised 500
    assert result.rows == []  # zero rows on a FAILED run
    assert result.run.failure_reason  # a reason persisted for read
    assert_no_running_orphan(session, run_type=RUN_TYPE_SCENARIO)  # FAILED is terminal, not orphan


# ---------- governed-number guards ----------


def test_result_is_append_only(session: Session) -> None:
    t = str(uuid.uuid4())
    fx_run, fid_usd, fid_eur = _seed_factor_exposure_run(session, t)
    result = _run(session, t, fx_run, _scenario(session, t, fid_usd, fid_eur))
    row = result.rows[0]
    row.pnl = Decimal("999")
    with pytest.raises(AppendOnlyViolation):
        session.flush()


def test_run_type_is_not_a_metric_type(session: Session) -> None:
    # GS2: the run_type FAMILY must never equal a metric_type.
    assert RUN_TYPE_SCENARIO not in {METRIC_TYPE_SCENARIO_PNL, METRIC_TYPE_SCENARIO_PNL_TOTAL}


def test_no_risk_star_audit_emitted(session: Session) -> None:
    t = str(uuid.uuid4())
    fx_run, fid_usd, fid_eur = _seed_factor_exposure_run(session, t)
    _run(session, t, fx_run, _scenario(session, t, fid_usd, fid_eur))
    n = session.execute(
        select(func.count()).select_from(AuditEvent).where(AuditEvent.event_type.like("RISK.%"))
    ).scalar_one()
    assert n == 0  # RISK.SCENARIO_CREATE is RESERVED, not emitted (the standing EVT-220 pattern)


def test_migration_head_is_scenario() -> None:
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    root = pathlib.Path(__file__).resolve().parents[3]
    cfg = Config(str(root / "alembic.ini"))
    cfg.set_main_option("script_location", str(root / "migrations"))
    script = ScriptDirectory.from_config(cfg)
    assert script.get_current_head() == "0039_model_validation"
    assert script.get_revision("0036_desmoothed_return").down_revision == "0035_scenario"
