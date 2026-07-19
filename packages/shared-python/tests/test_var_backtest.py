"""BT-1 VaR-backtesting binder + kernel (SQLite): the NINTH governed number (ENT-055).

Covers the pure kernel goldens + an INDEPENDENT float ``math.log`` cross-check (incl. the x=0/x=N
edges and the TWO-SIDED property); the declared-alpha registrar identity; the full-stack
build-in-request + consume-existing golden over a REAL VaR chain (portfolio -> exposure ->
factor-exposure -> covariance -> parametric VaR) + a REAL PM-1 return run (exception and
no-exception single-pair cases with exact Kupiec decisions); the AD-014 / TR-09 reproducibility
invariant (a later VaR re-run or valuation append cannot move a historical backtest); the
pre-create refusal battery (unpaired forecast, horizon mismatch, MV-chain break, gap, mixed
methods, duplicate as-of, mixed currencies, foreign/unknown runs, the cross-portfolio identity
gate); the post-create FAILED magnitude gate (echo-gated — the P3-8 HIGH-fold lesson baked in);
the Basel domain gating (no zone off (0.99, 250) — constants pinned + the n-gate proven
full-stack); the append-only + run_type!=metric + migration-head + REAL-fence sync +
zero-``RISK.*``-audit guards; and the entitlement parity assertion (BT-1 REUSES
``risk.run``/``risk.view`` — NO new permission code). PG legs live in ``test_var_backtest_pg.py``.

Fixture realism (TD-1): MVs are O(1E4..1E5), daily P&L moves are small fractions of MV, VaR values
follow the exact REF1 hand construction; the out-of-band value lives ONLY in the labeled
magnitude-boundary test (a forced value).
"""

from __future__ import annotations

import math
import pathlib
import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from run_assertions import assert_no_running_orphan
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from irp_shared.audit.models import AppendOnlyViolation, AuditEvent
from irp_shared.calc.models import CalculationRun, RunStatus
from irp_shared.db.session import make_engine, make_session_factory
from irp_shared.exposure import ExposureActor, run_exposure
from irp_shared.marketdata import (
    FactorActor,
    capture_factor,
    capture_factor_return,
    resolve_factor,
)
from irp_shared.models import Base
from irp_shared.perf import (
    PortfolioReturnActor,
    register_portfolio_return_model,
    run_portfolio_return,
)
from irp_shared.portfolio import PortfolioActor, create_portfolio
from irp_shared.position import create_position
from irp_shared.position.service import PositionActor
from irp_shared.reference.instrument import create_instrument
from irp_shared.reference.models import Currency
from irp_shared.reference.service import ReferenceActor
from irp_shared.risk import (
    METRIC_TYPE_BASEL_ZONE,
    METRIC_TYPE_EXCEPTION_COUNT,
    METRIC_TYPE_EXCEPTION_INDICATOR,
    METRIC_TYPE_KUPIEC_LR,
    RUN_TYPE_VAR_BACKTEST,
    CovarianceActor,
    FactorExposureActor,
    VarActor,
    VarBacktestActor,
    VarBacktestInputError,
    VarBacktestKernelError,
    VarBacktestResult,
    basel_zone,
    exception_indicator,
    kupiec_decision,
    kupiec_lr,
    list_var_backtests,
    register_covariance_model,
    register_factor_exposure_model,
    register_var_backtest_model,
    register_var_model,
    run_covariance,
    run_factor_exposure,
    run_var,
    run_var_backtest,
)
from irp_shared.snapshot import PURPOSE_VAR_BACKTEST_INPUT, resolve_snapshot
from irp_shared.valuation import create_valuation
from irp_shared.valuation.service import ValuationActor

TENANT = str(uuid.uuid4())
T0 = datetime(2026, 1, 1, tzinfo=UTC)
VALID_AT = datetime(2026, 6, 1, tzinfo=UTC)
KNOWN_AT = datetime(2030, 1, 1, tzinfo=UTC)
VD = date(2026, 6, 1)
D1, D2, D3, D4 = (date(2026, 5, 26), date(2026, 5, 27), date(2026, 5, 28), date(2026, 5, 29))
#: The realized sub-period aligned to the VaR forecast: window_end D4, horizon 1 day.
B0, B1 = D4, D4 + timedelta(days=1)
ACTOR = VarBacktestActor(actor_id="analyst")
#: The DETERMINISTIC full-stack VaR99 of the seeded chain, hand-derived: sample covariance (n-1=3)
#: of returns (1,2,3,4)% and (4,3,2,1)% gives var = 5/3E-4 each, cov = -5/3E-4 (perfect
#: anti-correlation); x=(30000, 40000) => radicand = (9E8+16E8-24E8)*5/3E-4 = 16666.66_ =>
#: sigma_p = 129.099444_ ; VaR99 = sigma*z99(2.326347874041) = 300.330219 @6dp.
BT1_VAR99 = Decimal("300.330219")


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


# --------------------------------------------------------------------------- kernel goldens


def _float_lr(n: int, x: int, p: float) -> float:
    a = (n - x) * math.log(1 - p) + (x * math.log(p) if x else 0.0)
    b = ((n - x) * math.log(1 - x / n) if x < n else 0.0) + (x * math.log(x / n) if x else 0.0)
    return -2 * a + 2 * b


def test_kernel_goldens_and_independent_cross_check() -> None:
    """The plan-time verified goldens + an independent stdlib float cross-check (<= 1e-9)."""
    assert str(kupiec_lr(250, 5, Decimal("0.01"))) == "1.956809788231"
    assert str(kupiec_lr(250, 10, Decimal("0.01"))) == "12.955491062356"
    assert str(kupiec_lr(250, 0, Decimal("0.01"))) == "5.025167926751"
    for x in (0, 1, 5, 10, 250):  # incl. BOTH edges
        d = kupiec_lr(250, x, Decimal("0.01"))
        assert abs(float(d) - _float_lr(250, x, 0.01)) < 1e-9, x


def test_kernel_two_sided_and_decisions() -> None:
    """POF is TWO-SIDED: x=0 over 250 pairs @99% REJECTS at 0.05 (too FEW exceptions — an
    over-conservative model fails coverage too)."""
    lr0 = kupiec_lr(250, 0, Decimal("0.01"))
    assert kupiec_decision(lr0, Decimal("0.05")) == "REJECT"
    assert kupiec_decision(lr0, Decimal("0.01")) == "FAIL_TO_REJECT"  # 5.025 < 6.634897
    lr5 = kupiec_lr(250, 5, Decimal("0.01"))
    assert kupiec_decision(lr5, Decimal("0.05")) == "FAIL_TO_REJECT"
    assert kupiec_decision(lr5, Decimal("0.01")) == "FAIL_TO_REJECT"
    lr10 = kupiec_lr(250, 10, Decimal("0.01"))
    assert kupiec_decision(lr10, Decimal("0.05")) == "REJECT"
    assert kupiec_decision(lr10, Decimal("0.01")) == "REJECT"


def test_kernel_zone_table_and_indicator() -> None:
    assert [basel_zone(n) for n in (0, 4, 5, 9, 10, 25)] == [
        "GREEN",
        "GREEN",
        "YELLOW",
        "YELLOW",
        "RED",
        "RED",
    ]
    # STRICT: a loss exactly AT VaR is NOT an exception.
    assert exception_indicator(Decimal("-101"), Decimal("100")) == 1
    assert exception_indicator(Decimal("-100"), Decimal("100")) == 0
    assert exception_indicator(Decimal("50"), Decimal("100")) == 0  # a gain is never an exception


def test_kernel_pathologies_refuse() -> None:
    with pytest.raises(VarBacktestKernelError):
        kupiec_lr(0, 0, Decimal("0.01"))  # n < 1
    with pytest.raises(VarBacktestKernelError):
        kupiec_lr(10, 11, Decimal("0.01"))  # x > n
    with pytest.raises(VarBacktestKernelError):
        kupiec_lr(10, 1, Decimal("1"))  # coverage outside (0, 1)
    with pytest.raises(VarBacktestKernelError):
        kupiec_decision(Decimal("1"), Decimal("0.10"))  # off the declared critical set
    with pytest.raises(VarBacktestKernelError):
        basel_zone(-1)


# --------------------------------------------------------------------------- full-stack fixtures


def _seed_var_chain(db: Session, tenant: str = TENANT) -> tuple[str, str, str]:
    """The FULL upstream chain (the test_var fixture shape): two USD/EUR holdings -> a COMPLETED
    exposure run (x = 30000 USD-factor + 40000 EUR-factor, base USD) -> factor-exposure +
    covariance runs over uncorrelated 1E-4-variance factors. Returns (pf, fx_run_id, cov_run_id)."""
    from irp_shared.entitlement.bootstrap import SYSTEM_TENANT_ID
    from irp_shared.marketdata import FxRateActor, capture_fx_rate

    for code in ("USD", "EUR"):
        exists = db.execute(
            select(Currency).where(Currency.tenant_id == SYSTEM_TENANT_ID, Currency.code == code)
        ).scalar_one_or_none()
        if exists is None:
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
    insts: list[str] = []
    for code, qty, mark, ccy in (
        ("I-USD", "100", "300.00", "USD"),
        ("I-EUR", "100", "400.00", "EUR"),
    ):
        inst = create_instrument(
            db,
            tenant_id=tenant,
            code=f"{code}-{uuid.uuid4().hex[:6]}",
            name="i",
            asset_class="BOND",
            actor=ReferenceActor(actor_id="s"),
        ).id
        insts.append(inst)
        create_position(
            db,
            portfolio_id=pf,
            instrument_id=inst,
            acting_tenant=tenant,
            actor=PositionActor(actor_id="s"),
            quantity=Decimal(qty),
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
    assert exposure.status == RunStatus.COMPLETED.value

    factor_ids: list[str] = []
    for code, ccy, values in (
        ("FX_USD", "USD", ["0.01", "0.02", "0.03", "0.04"]),
        ("FX_EUR", "EUR", ["0.04", "0.03", "0.02", "0.01"]),
    ):
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
        for d, v in zip((D1, D2, D3, D4), values, strict=True):
            capture_factor_return(
                db,
                factor,
                return_date=d,
                return_value=Decimal(v),
                acting_tenant=tenant,
                actor=FactorActor(actor_id="s"),
                valid_from=T0,
            )
        factor_ids.append(fid)
    db.flush()

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
        factor_ids=factor_ids,
    )
    assert fx_run.status == RunStatus.COMPLETED.value

    cov_mv = register_covariance_model(
        db, tenant_id=tenant, actor_id="a", code_version="risk-v1", window_observations=4
    )
    cov_run = run_covariance(
        db,
        acting_tenant=tenant,
        actor=CovarianceActor(actor_id="a"),
        code_version="risk-v1",
        environment_id="ci",
        model_version_id=cov_mv.id,
        factor_ids=factor_ids,
        as_of_valid_at=VALID_AT,
    )
    assert cov_run.status == RunStatus.COMPLETED.value
    return pf, fx_run.run.run_id, cov_run.run.run_id


def _var_run(db: Session, fx_run: str, cov_run: str, tenant: str = TENANT) -> str:
    """One COMPLETED parametric-VaR run @0.99 over the seeded chain (window_end = D4)."""
    mv = register_var_model(
        db, tenant_id=tenant, actor_id="a", code_version="risk-v1", confidence_level="0.99"
    ).id
    result = run_var(
        db,
        acting_tenant=tenant,
        actor=VarActor(actor_id="a"),
        code_version="risk-v1",
        environment_id="ci",
        model_version_id=mv,
        exposure_run_id=fx_run,
        covariance_run_id=cov_run,
    )
    assert result.status == RunStatus.COMPLETED.value
    row = result.rows[0]
    assert row.window_end == D4 and str(row.var_value) == str(BT1_VAR99)
    return result.run.run_id


def _boundary_run(
    db: Session, pf: str, insts_marks: list[tuple[str, str | None]], vdate: date
) -> str:
    """One COMPLETED exposure boundary run at ``vdate`` with USD marks per instrument (a ``None``
    mark reuses the valuation already captured at that date)."""
    for inst, mark in insts_marks:
        if mark is None:
            continue
        create_valuation(
            db,
            portfolio_id=pf,
            instrument_id=inst,
            valuation_date=vdate,
            acting_tenant=TENANT,
            actor=ValuationActor(actor_id="s"),
            mark_value=Decimal(mark),
            currency_code="USD",
            valid_from=T0,
        )
    result = run_exposure(
        db,
        acting_tenant=TENANT,
        actor=ExposureActor(actor_id="a"),
        code_version="v1",
        environment_id="ci",
        portfolio_id=pf,
        as_of_valid_at=datetime(vdate.year, vdate.month, vdate.day, tzinfo=UTC),
        as_of_known_at=KNOWN_AT,
        base_currency="USD",
    )
    assert result.status == RunStatus.COMPLETED.value
    return result.run.run_id


def _instruments_of(db: Session, pf: str) -> list[str]:
    from irp_shared.position.models import Position

    return list(
        db.execute(
            select(Position.instrument_id).where(Position.portfolio_id == pf).distinct()
        ).scalars()
    )


def _return_run(db: Session, pf: str, end_marks: tuple[str, str]) -> str:
    """A COMPLETED PORTFOLIO_RETURN run over (B0, B1]: begin marks (300, 400) => begin_mv 70000;
    ``end_marks`` set the end MV (no external flows). Returns the run_id."""
    insts = _instruments_of(db, pf)
    assert len(insts) == 2
    r0 = _boundary_run(db, pf, [(insts[0], "300.00"), (insts[1], "400.00")], B0)
    r1 = _boundary_run(db, pf, list(zip(insts, end_marks, strict=True)), B1)
    mv = register_portfolio_return_model(
        db, tenant_id=TENANT, actor_id="a", code_version="perf-v1"
    ).id
    result = run_portfolio_return(
        db,
        acting_tenant=TENANT,
        actor=PortfolioReturnActor(actor_id="a"),
        code_version="perf-v1",
        environment_id="ci",
        model_version_id=mv,
        exposure_run_ids=[r0, r1],
    )
    assert result.status == RunStatus.COMPLETED.value
    return result.run.run_id


def _bt_model(db: Session, alpha: str = "0.05", tenant: str = TENANT) -> str:
    return register_var_backtest_model(
        db, tenant_id=tenant, actor_id="a", code_version="bt-v1", alpha=alpha
    ).id


def _run(db: Session, return_run: str, var_runs: list[str], mv: str, tenant: str = TENANT):  # noqa: ANN202
    return run_var_backtest(
        db,
        acting_tenant=tenant,
        actor=ACTOR,
        code_version="bt-v1",
        environment_id="ci",
        model_version_id=mv,
        portfolio_return_run_id=return_run,
        var_run_ids=var_runs,
    )


# --------------------------------------------------------------------------- golden end-to-end


def test_build_path_exception_golden(session: Session) -> None:
    """70000 -> 68000 over (B0, B1]: loss 2000 > VaR99 300.330219 => ONE exception; n=1, x=1 =>
    LR = -2 ln(0.01) = 9.210340 => REJECT at the declared alpha 0.05. NO Basel row (n != 250)."""
    pf, fx_run, cov_run = _seed_var_chain(session)
    var_run = _var_run(session, fx_run, cov_run)
    return_run = _return_run(session, pf, ("290.00", "390.00"))  # end MV 68000
    mv = _bt_model(session)

    result = _run(session, return_run, [var_run], mv)
    assert result.status == RunStatus.COMPLETED.value
    rows = {r.metric_type: r for r in result.rows}
    assert set(rows) == {
        METRIC_TYPE_EXCEPTION_INDICATOR,
        METRIC_TYPE_EXCEPTION_COUNT,
        METRIC_TYPE_KUPIEC_LR,
    }  # NO BASEL_ZONE off the (0.99, 250) domain
    ind = rows[METRIC_TYPE_EXCEPTION_INDICATOR]
    assert ind.metric_value == Decimal("1.000000")
    assert ind.realized_pnl == Decimal("-2000.000000")
    assert ind.var_value == BT1_VAR99
    assert ind.period_start == B0 and ind.period_end == B1
    assert ind.n_pairs == 1 and ind.n_exceptions == 1
    assert ind.var_metric_type == "VAR_PARAMETRIC"
    assert ind.confidence_level == Decimal("0.9900") and ind.horizon_days == 1
    assert ind.base_currency == "USD" and ind.portfolio_id == pf
    count = rows[METRIC_TYPE_EXCEPTION_COUNT]
    assert count.metric_value == Decimal("1.000000") and count.n_exceptions == 1
    lr = rows[METRIC_TYPE_KUPIEC_LR]
    # -2 ln(0.01) = 9.210340371976... -> 9.210340 @6dp; > 3.841459 => REJECT.
    assert lr.metric_value == Decimal("9.210340")
    assert lr.test_decision == "REJECT"
    assert lr.basel_zone is None
    assert lr.portfolio_return_run_id == return_run


def test_build_path_no_exception_golden(session: Session) -> None:
    """70000 -> 69800: loss 200 < VaR99 300.330219 => ZERO exceptions; n=1, x=0 =>
    LR = -2 ln(0.99) = 0.020101 => FAIL_TO_REJECT at 0.05."""
    pf, fx_run, cov_run = _seed_var_chain(session)
    var_run = _var_run(session, fx_run, cov_run)
    return_run = _return_run(session, pf, ("299.00", "399.00"))  # end MV 69800: loss 200
    mv = _bt_model(session)
    result = _run(session, return_run, [var_run], mv)
    rows = {r.metric_type: r for r in result.rows}
    assert rows[METRIC_TYPE_EXCEPTION_INDICATOR].metric_value == Decimal("0.000000")
    lr = rows[METRIC_TYPE_KUPIEC_LR]
    assert lr.metric_value == Decimal("0.020101")
    assert lr.test_decision == "FAIL_TO_REJECT"
    assert lr.n_pairs == 1 and lr.n_exceptions == 0


def test_basel_domain_constants_pinned() -> None:
    """The Basel zone emits ONLY at (confidence 0.99, EXACTLY 250 pairs, 1-DAY horizon) — the
    table's defined domain (OD-BT-1-G; review fold: the horizon leg was latently missing). The
    n-gate is proven full-stack (n=1 => no zone row, above); the EMISSION branch is proven in
    test_basel_zone_emitted_on_domain; the constants are pinned here so a silent domain widening
    cannot ship."""
    from irp_shared.risk.var_backtest_service import (
        _BASEL_CONFIDENCE,
        _BASEL_HORIZON_DAYS,
        _BASEL_PAIRS,
    )

    assert _BASEL_CONFIDENCE == Decimal("0.99")
    assert _BASEL_PAIRS == 250
    assert _BASEL_HORIZON_DAYS == 1


def test_basel_zone_emitted_on_domain(session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    """The BASEL_ZONE EMISSION branch (review fold: previously zero-covered): with the pair-count
    leg of the domain narrowed to our n=1 fixture (the monkeypatch seam precedent), a 0.99 / 1-day
    backtest mints the zone row — metric_value echoes the exception count, the zone lands in the
    DEDICATED string column (x=1 => GREEN)."""
    import irp_shared.risk.var_backtest_service as svc

    pf, fx_run, cov_run = _seed_var_chain(session)
    var_run = _var_run(session, fx_run, cov_run)
    return_run = _return_run(session, pf, ("290.00", "390.00"))  # the exception case (x=1)
    mv = _bt_model(session)
    monkeypatch.setattr(svc, "_BASEL_PAIRS", 1)
    result = _run(session, return_run, [var_run], mv)
    rows = {r.metric_type: r for r in result.rows}
    zone = rows[METRIC_TYPE_BASEL_ZONE]
    assert zone.basel_zone == "GREEN"  # 1 exception -> GREEN (0-4)
    assert zone.metric_value == Decimal("1.000000")  # echoes the exception count
    assert zone.n_pairs == 1 and zone.n_exceptions == 1
    assert zone.test_decision is None


def test_build_path_historical_var_method(session: Session) -> None:
    """The SECOND method end-to-end (review fold: VAR_HISTORICAL previously had zero coverage):
    an HS-VaR run over the SAME chain (window_end D4) backtests against the same realized period —
    proving the identity gate resolves an HS row's exposure_run_id and the method echo is
    VAR_HISTORICAL."""
    from irp_shared.marketdata.models import Factor
    from irp_shared.risk import register_historical_var_model, run_var_historical

    pf, fx_run, cov_run = _seed_var_chain(session)
    # The HS adequacy floor at 0.95 needs >= 21 observations: append 17 EARLIER daily returns per
    # factor (small plausible values) — the covariance run's latest-4 window stays untouched.
    factors = session.execute(select(Factor).where(Factor.tenant_id == TENANT)).scalars().all()
    for factor in factors:
        for i in range(17):
            capture_factor_return(
                session,
                factor,
                return_date=D1 - timedelta(days=i + 1),
                return_value=Decimal("0.001") * (1 if i % 2 else -1),
                acting_tenant=TENANT,
                actor=FactorActor(actor_id="s"),
                valid_from=T0,
            )
    session.flush()
    hs_mv = register_historical_var_model(
        session,
        tenant_id=TENANT,
        actor_id="a",
        code_version="risk-v1",
        confidence_level="0.95",
        window_observations=21,
    )
    hs = run_var_historical(
        session,
        acting_tenant=TENANT,
        actor=VarActor(actor_id="a"),
        code_version="risk-v1",
        environment_id="ci",
        model_version_id=hs_mv.id,
        exposure_run_id=fx_run,
    )
    assert hs.status == RunStatus.COMPLETED.value
    hs_row = hs.rows[0]
    assert hs_row.window_end == D4 and hs_row.metric_type == "VAR_HISTORICAL"
    return_run = _return_run(session, pf, ("290.00", "390.00"))
    mv = _bt_model(session)
    result = _run(session, return_run, [hs.run.run_id], mv)
    assert result.status == RunStatus.COMPLETED.value
    rows = {r.metric_type: r for r in result.rows}
    ind = rows[METRIC_TYPE_EXCEPTION_INDICATOR]
    assert ind.var_metric_type == "VAR_HISTORICAL"
    assert ind.var_value == hs_row.var_value  # the pinned HS forecast, echoed verbatim
    assert ind.realized_pnl == Decimal("-2000.000000")


# --------------------------------------------------------------- consume + reproducibility (TR-09)


def test_consume_existing_reproduces_and_is_rerun_invariant(session: Session) -> None:
    pf, fx_run, cov_run = _seed_var_chain(session)
    var_run = _var_run(session, fx_run, cov_run)
    return_run = _return_run(session, pf, ("290.00", "390.00"))
    mv = _bt_model(session)
    first = _run(session, return_run, [var_run], mv)
    snap_id = first.run.input_snapshot_id
    assert resolve_snapshot(session, snap_id, acting_tenant=TENANT).purpose == (
        PURPOSE_VAR_BACKTEST_INPUT
    )

    # TR-09: LATER re-runs of BOTH sides after the pin must NOT move the backtest (review fold:
    # the invariance was previously proven one-sided). A NEW return run over (B1, B1+1] with fresh
    # end marks + a NEW VaR run — the pinned snapshot must reproduce the ORIGINAL rows regardless.
    _var_run(session, fx_run, cov_run)  # a new VaR run
    insts = _instruments_of(session, pf)
    b2 = B1 + timedelta(days=1)
    r0b = _boundary_run(session, pf, [(insts[0], None), (insts[1], None)], B1)  # marks reused
    r1b = _boundary_run(session, pf, [(insts[0], "285.00"), (insts[1], "380.00")], b2)
    ret_mv2 = register_portfolio_return_model(
        session, tenant_id=TENANT, actor_id="a", code_version="perf-v1"
    ).id
    rerun_return = run_portfolio_return(
        session,
        acting_tenant=TENANT,
        actor=PortfolioReturnActor(actor_id="a"),
        code_version="perf-v1",
        environment_id="ci",
        model_version_id=ret_mv2,
        exposure_run_ids=[r0b, r1b],
    )
    assert rerun_return.status == RunStatus.COMPLETED.value  # the return side moved on
    rerun = run_var_backtest(
        session,
        acting_tenant=TENANT,
        actor=ACTOR,
        code_version="bt-v1",
        environment_id="ci",
        model_version_id=mv,
        snapshot_id=snap_id,
    )
    a = next(r for r in first.rows if r.metric_type == METRIC_TYPE_KUPIEC_LR)
    b = next(r for r in rerun.rows if r.metric_type == METRIC_TYPE_KUPIEC_LR)
    assert a.metric_value == b.metric_value == Decimal("9.210340")
    assert a.test_decision == b.test_decision == "REJECT"


# --------------------------------------------------------------- pre-create refusals (adjudication)


def _p_row(mt: str, s: date, e: date, bmv: str, emv: str, flow: str = "0.000000", **o: object):
    return {
        "metric_type": mt,
        "calculation_run_id": o.get("run", "run-a"),
        "portfolio_id": o.get("pf", "pf-a"),
        "base_currency": o.get("ccy", "USD"),
        "period_start": s.isoformat(),
        "period_end": e.isoformat(),
        "begin_mv": bmv,
        "end_mv": emv,
        "net_external_flow": flow,
        "return_value": "0",
    }


def _v_row(we: date, var: str, **o: object):
    return {
        "metric_type": o.get("mt", "VAR_PARAMETRIC"),
        "confidence_level": o.get("cl", "0.9900"),
        "horizon_days": o.get("h", 31),
        "base_currency": o.get("ccy", "USD"),
        "window_end": we.isoformat(),
        "var_value": var,
        "calculation_run_id": o.get("run", "vrun-a"),
        "exposure_run_id": o.get("er", "er-a"),
    }


P0, P1, P2 = date(2026, 1, 1), date(2026, 2, 1), date(2026, 3, 4)  # 31-day contiguous periods


def _valid_pins() -> tuple[list[dict], list[dict]]:
    portfolio = [
        _p_row("DIETZ_PERIOD", P0, P1, "70000.000000", "68000.000000"),
        _p_row("DIETZ_PERIOD", P1, P2, "68000.000000", "68500.000000"),
        _p_row("TWR_LINKED", P0, P2, "70000.000000", "68500.000000"),
    ]
    var = [_v_row(P0, "1163.173937"), _v_row(P1, "1150.000000")]
    return portfolio, var


def test_adjudicate_valid_baseline() -> None:
    from irp_shared.risk.var_backtest_service import _adjudicate_pins

    parsed = _adjudicate_pins(*_valid_pins())
    assert len(parsed.pairs) == 2
    assert str(parsed.pairs[0].realized_pnl) == "-2000.000000"
    assert str(parsed.pairs[1].realized_pnl) == "500.000000"
    assert parsed.horizon_days == 31 and parsed.confidence_level == Decimal("0.9900")


@pytest.mark.parametrize(
    "mutate",
    [
        "unpaired_forecast",
        "horizon_mismatch",
        "mv_chain_break",
        "gap",
        "overlap",
        "mixed_methods",
        "duplicate_as_of",
        "mixed_currency",
        "mixed_confidence",
        "no_dietz",
        "two_linked",
        "no_var_rows",
        "unknown_method",
        "es_parametric",
    ],
)
def test_adjudicate_refusals(mutate: str) -> None:
    from irp_shared.risk.var_backtest_service import _adjudicate_pins

    portfolio, var = _valid_pins()
    if mutate == "unpaired_forecast":
        var.append(_v_row(date(2026, 6, 1), "1.000000"))  # no period starts there
    elif mutate == "horizon_mismatch":
        var[0]["horizon_days"] = 10  # ALL var rows must be uniform AND span the period
        var[1]["horizon_days"] = 10
    elif mutate == "mv_chain_break":
        portfolio[1]["begin_mv"] = "67999.000000"  # != prior end_mv 68000
    elif mutate == "gap":
        portfolio[1]["period_start"] = date(2026, 2, 2).isoformat()  # not contiguous
    elif mutate == "overlap":
        portfolio[1]["period_start"] = date(2026, 1, 15).isoformat()
    elif mutate == "mixed_methods":
        var[1]["metric_type"] = "VAR_HISTORICAL"
    elif mutate == "duplicate_as_of":
        var[1]["window_end"] = P0.isoformat()
    elif mutate == "mixed_currency":
        var[1]["base_currency"] = "EUR"
    elif mutate == "mixed_confidence":
        var[1]["confidence_level"] = "0.9500"
    elif mutate == "no_dietz":
        portfolio = [portfolio[2]]
    elif mutate == "two_linked":
        portfolio.append(_p_row("TWR_LINKED", P0, P2, "70000.000000", "68500.000000"))
    elif mutate == "no_var_rows":
        var = []
    elif mutate == "unknown_method":
        var[0]["metric_type"] = var[1]["metric_type"] = "VAR_MONTECARLO"
    elif mutate == "es_parametric":
        # ES-1 (OD-ES-1-F): ES rows are a DELIBERATE omission from METRIC_TYPES, so a backtest
        # over an ES run refuses correct-by-default. Pinned because the omission is a ratified
        # decision, not an oversight — a future maintainer must not "complete the vocabulary".
        var[0]["metric_type"] = var[1]["metric_type"] = "ES_PARAMETRIC"
    with pytest.raises(VarBacktestInputError):
        _adjudicate_pins(portfolio, var)


def test_builder_refuses_empty_var_run_ids(session: Session) -> None:
    """The BUILDER itself (not just the binder) refuses an empty var_run_ids list BEFORE any write
    (review fold: a direct library caller could previously mint immutable VAR-less governance
    garbage — the build_factor_exposure_snapshot precedent)."""
    from irp_shared.snapshot import VarBacktestSnapshotError, build_var_backtest_snapshot
    from irp_shared.snapshot.events import SnapshotActor as SA

    pf, fx_run, cov_run = _seed_var_chain(session)
    return_run = _return_run(session, pf, ("290.00", "390.00"))
    with pytest.raises(VarBacktestSnapshotError):
        build_var_backtest_snapshot(
            session,
            acting_tenant=TENANT,
            actor=SA(actor_id="s"),
            portfolio_return_run_id=return_run,
            var_run_ids=[],
        )


# --------------------------------------------------------------- pre-create refusals (security)


def test_unknown_runs_refused_zero_run(session: Session) -> None:
    pf, fx_run, cov_run = _seed_var_chain(session)
    var_run = _var_run(session, fx_run, cov_run)
    return_run = _return_run(session, pf, ("290.00", "390.00"))
    mv = _bt_model(session)
    before = session.execute(select(func.count()).select_from(CalculationRun)).scalar()
    with pytest.raises(VarBacktestInputError):
        _run(session, str(uuid.uuid4()), [var_run], mv)  # unknown return run
    with pytest.raises(VarBacktestInputError):
        _run(session, return_run, [str(uuid.uuid4())], mv)  # unknown var run
    with pytest.raises(VarBacktestInputError):
        _run(session, var_run, [var_run], mv)  # a VAR run passed as the return run (wrong type)
    after = session.execute(
        select(func.count())
        .select_from(CalculationRun)
        .where(CalculationRun.run_type == RUN_TYPE_VAR_BACKTEST)
    ).scalar()
    assert after == 0
    assert before == session.execute(select(func.count()).select_from(CalculationRun)).scalar()
    assert_no_running_orphan(session, run_type=RUN_TYPE_VAR_BACKTEST)  # MD-H1 annex item 6


def test_cross_portfolio_identity_refused(session: Session) -> None:
    """Backtesting portfolio A's VaR against portfolio B's returns must REFUSE (OD-BT-1-H): the
    VaR chain lives on pf_a; the return run measures a DIFFERENT portfolio pf_b."""
    pf_a, fx_run, cov_run = _seed_var_chain(session)
    var_run = _var_run(session, fx_run, cov_run)
    # A second portfolio with its own instruments + boundary runs at the SAME aligned dates.
    pf_b = create_portfolio(
        session,
        tenant_id=TENANT,
        code=f"ACCT-{uuid.uuid4().hex[:6]}",
        name="acct-b",
        node_type="ACCOUNT",
        actor=PortfolioActor(actor_id="s"),
    ).id
    inst = create_instrument(
        session,
        tenant_id=TENANT,
        code=f"I-{uuid.uuid4().hex[:6]}",
        name="i",
        asset_class="EQUITY",
        actor=ReferenceActor(actor_id="s"),
    ).id
    create_position(
        session,
        portfolio_id=pf_b,
        instrument_id=inst,
        acting_tenant=TENANT,
        actor=PositionActor(actor_id="s"),
        quantity=Decimal("1"),
        valid_from=T0,
    )
    r0 = _boundary_run(session, pf_b, [(inst, "70000.00")], B0)
    r1 = _boundary_run(session, pf_b, [(inst, "68000.00")], B1)
    ret_mv = register_portfolio_return_model(
        session, tenant_id=TENANT, actor_id="a", code_version="perf-v1"
    ).id
    ret = run_portfolio_return(
        session,
        acting_tenant=TENANT,
        actor=PortfolioReturnActor(actor_id="a"),
        code_version="perf-v1",
        environment_id="ci",
        model_version_id=ret_mv,
        exposure_run_ids=[r0, r1],
    )
    assert ret.status == RunStatus.COMPLETED.value
    mv = _bt_model(session)
    with pytest.raises(VarBacktestInputError):
        _run(session, ret.run.run_id, [var_run], mv)  # pf_a VaR vs pf_b returns


def test_ambiguous_and_missing_modes_refused(session: Session) -> None:
    mv = _bt_model(session)
    with pytest.raises(VarBacktestInputError):
        run_var_backtest(
            session,
            acting_tenant=TENANT,
            actor=ACTOR,
            code_version="bt-v1",
            environment_id="ci",
            model_version_id=mv,
            portfolio_return_run_id=str(uuid.uuid4()),
            var_run_ids=[str(uuid.uuid4())],
            snapshot_id=str(uuid.uuid4()),  # both modes at once
        )
    with pytest.raises(VarBacktestInputError):
        run_var_backtest(
            session,
            acting_tenant=TENANT,
            actor=ACTOR,
            code_version="bt-v1",
            environment_id="ci",
            model_version_id=mv,
            portfolio_return_run_id=str(uuid.uuid4()),
            var_run_ids=[],  # empty var set on the build path
        )


def test_unregistered_and_wrong_model_refused(session: Session) -> None:
    from irp_shared.model.service import UnregisteredModelError, WrongModelVersionError

    pf, fx_run, cov_run = _seed_var_chain(session)
    var_run = _var_run(session, fx_run, cov_run)
    return_run = _return_run(session, pf, ("290.00", "390.00"))
    with pytest.raises(UnregisteredModelError):
        _run(session, return_run, [var_run], str(uuid.uuid4()))
    # A version OF ANOTHER MODEL (the parametric-VaR one) must be refused (CTRL-003 identity).
    other = register_var_model(
        session, tenant_id=TENANT, actor_id="a", code_version="risk-v1", confidence_level="0.99"
    ).id
    with pytest.raises(WrongModelVersionError):
        _run(session, return_run, [var_run], other)


# ------------------------------------------------------------- post-create FAILED (magnitude gate)


def test_extreme_echo_is_failed_run(session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    """The echo gate (the P3-8 HIGH-fold lesson, baked in from birth): a realized P&L past the
    Numeric(28,6) envelope yields a COMMITTED FAILED run + ZERO rows + a naming reason, never a PG
    overflow 500. Forced via the kernel seam (a real pin cannot reach it — PM-1's own gates bound
    the MVs first). Labeled magnitude-boundary test (TD-1)."""
    import irp_shared.risk.var_backtest_service as svc

    pf, fx_run, cov_run = _seed_var_chain(session)
    var_run = _var_run(session, fx_run, cov_run)
    return_run = _return_run(session, pf, ("290.00", "390.00"))
    mv = _bt_model(session)
    monkeypatch.setattr(svc, "_MAX_RESULT_ABS", Decimal("1000"))  # tighten so the echo trips
    result = _run(session, return_run, [var_run], mv)
    assert result.status == RunStatus.FAILED.value
    assert result.rows == []
    assert result.failure_reason and "magnitude" in result.failure_reason
    assert list_var_backtests(session, run_id=result.run.run_id, acting_tenant=TENANT) == []


# --------------------------------------------------------------------------- governance guards


def test_append_only_result_row(session: Session) -> None:
    pf, fx_run, cov_run = _seed_var_chain(session)
    var_run = _var_run(session, fx_run, cov_run)
    return_run = _return_run(session, pf, ("290.00", "390.00"))
    mv = _bt_model(session)
    result = _run(session, return_run, [var_run], mv)
    row = result.rows[0]
    row.metric_value = Decimal("0.999999")
    with pytest.raises(AppendOnlyViolation):
        session.flush()
    session.rollback()


def test_run_type_is_not_a_metric() -> None:
    assert RUN_TYPE_VAR_BACKTEST not in {
        METRIC_TYPE_EXCEPTION_INDICATOR,
        METRIC_TYPE_EXCEPTION_COUNT,
        METRIC_TYPE_KUPIEC_LR,
        METRIC_TYPE_BASEL_ZONE,
    }


def test_no_risk_audit_events_emitted(session: Session) -> None:
    """BT-1 mints NO ``RISK.*`` code — the run reuses ``CALC.RUN_*`` (OD-BT-1-B)."""
    pf, fx_run, cov_run = _seed_var_chain(session)
    var_run = _var_run(session, fx_run, cov_run)
    return_run = _return_run(session, pf, ("290.00", "390.00"))
    mv = _bt_model(session)
    _run(session, return_run, [var_run], mv)
    risk_events = session.execute(
        select(func.count()).select_from(AuditEvent).where(AuditEvent.event_type.like("RISK.%"))
    ).scalar()
    assert risk_events == 0


def test_migration_head_is_var_backtest() -> None:
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    root = pathlib.Path(__file__).resolve().parents[3]
    cfg = Config(str(root / "alembic.ini"))
    cfg.set_main_option("script_location", str(root / "migrations"))
    script = ScriptDirectory.from_config(cfg)
    assert (
        script.get_current_head() == "0042_desmoothing_estimated_alpha"
    )  # ES-HS-1 widened the 0028 CHECK
    assert script.get_revision("0033_var_backtest").down_revision == "0032_benchmark_relative"


def test_return_run_type_fence_in_sync() -> None:
    """The binder keeps a REAL fence-kept LOCAL copy of the PORTFOLIO_RETURN run_type (risk must
    NOT import perf — this test may); pin the strings equal so a rename cannot silently break the
    run-type gate (the PM-1 ``_EXPOSURE_RUN_TYPE`` precedent)."""
    from irp_shared.perf.events import RUN_TYPE_PORTFOLIO_RETURN
    from irp_shared.risk.var_backtest_service import _RETURN_RUN_TYPE

    assert _RETURN_RUN_TYPE == RUN_TYPE_PORTFOLIO_RETURN


def test_risk_service_imports_no_perf_symbol() -> None:
    """The 'nothing imports perf' fence, enforced over the whole risk package (AST-checked — the
    PM-1 fence-test shape)."""
    import ast

    import irp_shared.risk as risk_pkg

    src = pathlib.Path(risk_pkg.__file__).parent
    for path in src.glob("*.py"):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                assert "perf" not in node.module.split("."), f"{path.name}: {node.module}"
            if isinstance(node, ast.Import):
                for a in node.names:
                    assert "perf" not in a.name.split("."), f"{path.name}: {a.name}"


def test_risk_permissions_reused_no_new_codes_bt1() -> None:
    """BT-1 REUSES ``risk.run``/``risk.view`` — it introduces NO new permission code (OD-BT-1-B).
    The SoD doc cites this test: the risk verbs in the catalog are EXACTLY the P3-1 pair, and no
    catalog code mentions backtesting."""
    from irp_shared.entitlement.bootstrap import PERMISSIONS

    codes = {c for c, _desc in PERMISSIONS}
    risk_codes = {c for c in codes if c.startswith("risk.")}
    assert risk_codes == {"risk.run", "risk.view"}
    assert not any("backtest" in c for c in codes)


def test_methodology_doc_exists_and_has_required_sections() -> None:
    from irp_shared.risk.bootstrap import VAR_BACKTEST_METHODOLOGY_REF

    root = pathlib.Path(__file__).resolve().parents[3]
    doc = root / VAR_BACKTEST_METHODOLOGY_REF
    assert doc.is_file()
    text = doc.read_text(encoding="utf-8")
    for section in (
        "Purpose & applicability",
        "Inputs & data policy",
        "Formulas & numerical standards",
        "Assumptions",
        "Validation / reproduction tests",
        "Governed-number contract",
        "Known limitations",
    ):
        assert section in text, f"missing methodology section: {section}"


def test_registrar_declared_alpha_identity(session: Session) -> None:
    from irp_shared.model.service import ModelVersionConflictError
    from irp_shared.risk import declared_var_backtest_alpha

    mv1 = register_var_backtest_model(session, tenant_id=TENANT, actor_id="a", code_version="bt-v1")
    assert declared_var_backtest_alpha(session, mv1) == Decimal("0.05")
    mv2 = register_var_backtest_model(session, tenant_id=TENANT, actor_id="a", code_version="bt-v1")
    assert mv1.id == mv2.id  # idempotent
    with pytest.raises(ModelVersionConflictError):
        register_var_backtest_model(
            session, tenant_id=TENANT, actor_id="a", code_version="bt-v1", alpha="0.01"
        )
    with pytest.raises(ModelVersionConflictError):
        register_var_backtest_model(session, tenant_id=TENANT, actor_id="a", code_version="bt-v2")
    with pytest.raises(ValueError, match="vocabulary"):
        register_var_backtest_model(
            session, tenant_id=TENANT, actor_id="a", code_version="x", alpha="0.10"
        )


def test_result_model_grain(session: Session) -> None:
    """The grain (calculation_run_id, metric_type, period_start) lets the pair row and the summary
    rows (sharing period_start = the first pair boundary) coexist without a unique clash."""
    pf, fx_run, cov_run = _seed_var_chain(session)
    var_run = _var_run(session, fx_run, cov_run)
    return_run = _return_run(session, pf, ("290.00", "390.00"))
    mv = _bt_model(session)
    result = _run(session, return_run, [var_run], mv)
    rows = list_var_backtests(session, run_id=result.run.run_id, acting_tenant=TENANT)
    grain = {(r.metric_type, r.period_start) for r in rows}
    assert (METRIC_TYPE_EXCEPTION_INDICATOR, B0) in grain
    assert (METRIC_TYPE_EXCEPTION_COUNT, B0) in grain  # shares B0, distinct metric_type
    assert (METRIC_TYPE_KUPIEC_LR, B0) in grain
    assert isinstance(rows[0], VarBacktestResult)


# ------------------------------------------------- BT-2: the TOTAL method admitted to the lane


def test_build_path_total_var_method(session: Session) -> None:
    """BT-2 (OD-BT-2-A) — the THIRD method end-to-end: a ``VAR_PARAMETRIC_TOTAL`` run backtests
    against the same realized period, proving the ratified vocabulary admit reaches the whole lane
    (adjudication -> pairing -> identity gate -> the method echo). PA-4 excluded this method by a
    single ``METRIC_TYPES`` tuple; this is the test that would have failed before the admit.

    The total run here cites NO proxied instruments — PA-4's documented byte-invariance case
    (total ≡ plain parametric, residual leg 0). That is a genuine total-family row and exactly
    what this test needs: the backtest consumes ``var_value``/``window_end``/``metric_type``, not
    the residual decomposition (the residual leg's own arithmetic + the BT-2 estimate-age gate are
    proven in ``test_var_total.py``). Keeping the chain minimal here keeps the SUBJECT the lane.
    """
    from irp_shared.risk import register_var_parametric_total_model

    pf, fx_run, cov_run = _seed_var_chain(session)
    total_mv = register_var_parametric_total_model(
        session,
        tenant_id=TENANT,
        actor_id="a",
        code_version="risk-v1",
        confidence_level="0.99",
        appraisal_days=91,
        max_estimate_age_days=400,
    ).id
    total = run_var(
        session,
        acting_tenant=TENANT,
        actor=VarActor(actor_id="a"),
        code_version="risk-v1",
        environment_id="ci",
        model_version_id=total_mv,
        exposure_run_id=fx_run,
        covariance_run_id=cov_run,
    )
    assert total.status == RunStatus.COMPLETED.value
    total_row = total.rows[0]
    assert total_row.metric_type == "VAR_PARAMETRIC_TOTAL" and total_row.window_end == D4
    assert total_row.estimate_age_days is None  # no cited estimates -> nothing to age
    # ANCHOR the invariance to the hand-derived plain-family golden (review fold): without this the
    # test only compares the total row to ITSELF, so a future residual leak into the zero-proxy
    # path (e.g. a defaulted sigma_e) would drift var_value and still pass.
    assert total_row.var_value == BT1_VAR99
    assert total_row.residual_variance == Decimal(0)

    return_run = _return_run(session, pf, ("290.00", "390.00"))  # end MV 68000 -> loss 2000
    result = _run(session, return_run, [total.run.run_id], _bt_model(session))
    assert result.status == RunStatus.COMPLETED.value
    rows = {r.metric_type: r for r in result.rows}
    ind = rows[METRIC_TYPE_EXCEPTION_INDICATOR]
    assert ind.var_metric_type == "VAR_PARAMETRIC_TOTAL"  # the admitted method, echoed
    assert ind.var_value == total_row.var_value  # the pinned total forecast, verbatim
    assert ind.realized_pnl == Decimal("-2000.000000")
    assert ind.metric_value == 1  # loss 2000 > the 99% forecast -> an exception


def test_total_and_parametric_cannot_mix_in_one_backtest(session: Session) -> None:
    """BT-2: admitting the total method does NOT relax the one-method-per-run rule — a run pinning
    both a TOTAL and a PARAMETRIC forecast still refuses (the mixed-methods gate). Cross-method
    comparison stays two runs side by side (BT-1's recorded limitation, unchanged)."""
    from irp_shared.risk import register_var_parametric_total_model

    pf, fx_run, cov_run = _seed_var_chain(session)
    plain = _var_run(session, fx_run, cov_run)
    total_mv = register_var_parametric_total_model(
        session,
        tenant_id=TENANT,
        actor_id="a",
        code_version="risk-v1",
        confidence_level="0.99",
        appraisal_days=91,
        max_estimate_age_days=400,
    ).id
    total = run_var(
        session,
        acting_tenant=TENANT,
        actor=VarActor(actor_id="a"),
        code_version="risk-v1",
        environment_id="ci",
        model_version_id=total_mv,
        exposure_run_id=fx_run,
        covariance_run_id=cov_run,
    )
    return_run = _return_run(session, pf, ("290.00", "390.00"))
    with pytest.raises(VarBacktestInputError, match="method"):
        _run(session, return_run, [plain, total.run.run_id], _bt_model(session))
    session.rollback()
    assert_no_running_orphan(session, run_type="VAR_BACKTEST")


def test_es_refusal_names_the_ratified_scope_out_not_an_unknown_vocabulary() -> None:
    """ES-1 (OD-ES-1-F): ``ES_PARAMETRIC`` is KNOWN and deliberately excluded, so the refusal must
    say so. Calling a shipped, ratified-as-out-of-scope metric "unknown" would send a validator
    hunting a vocabulary bug instead of reading the recorded scope-out — and the honest reason is
    FRTB precedent + parametric redundancy, NOT non-elicitability (which is false)."""
    from irp_shared.risk.var_backtest_service import _adjudicate_pins

    portfolio, var = _valid_pins()
    var[0]["metric_type"] = var[1]["metric_type"] = "ES_PARAMETRIC"
    with pytest.raises(VarBacktestInputError, match="DELIBERATELY not backtestable") as exc:
        _adjudicate_pins(portfolio, var)
    assert "unknown" not in str(exc.value)

    portfolio, var = _valid_pins()
    var[0]["metric_type"] = var[1]["metric_type"] = "VAR_MONTECARLO"
    with pytest.raises(VarBacktestInputError, match="unknown"):  # a genuinely unknown value still
        _adjudicate_pins(portfolio, var)  # gets the unknown-vocabulary message


def test_es_historical_refusal_names_the_bt3_tee_not_an_unknown_vocabulary() -> None:
    """ES-HS-1 (OD-ES-HS-1-D): ``ES_HISTORICAL`` is KNOWN and deliberately excluded — Kupiec
    over a tail-mean series is statistically meaningless; the genuine Acerbi-Szekely backtest is
    the named BT-3 candidate (pairing by shared input_snapshot_id). The refusal names the tee
    and points at the sibling VaR-HS run, never the unknown-vocabulary miss."""
    from irp_shared.risk.var_backtest_service import _adjudicate_pins

    portfolio, var = _valid_pins()
    var[0]["metric_type"] = var[1]["metric_type"] = "ES_HISTORICAL"
    with pytest.raises(VarBacktestInputError, match="DELIBERATELY not backtestable") as exc:
        _adjudicate_pins(portfolio, var)
    assert "unknown" not in str(exc.value)
    assert "BT-3" in str(exc.value)
    assert "input_snapshot_id" in str(exc.value)
