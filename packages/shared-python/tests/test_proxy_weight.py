"""SQLite unit/behavior tests for PA-3 proxy-weight regression (ENT-057, the TWELFTH governed number
and the loop-closer). Covers: the FULL-STACK chain (portfolio → private instrument → quarterly
appraisal marks → a DESMOOTHED_RETURN run → candidate CURRENCY factors + returns → an OLS
proxy-weight estimate) with the persisted coefficients/std-errors/R^2 asserted BYTE-EQUAL to an
independent ``estimate_ols`` recomputation on the extracted (y, X); the promotion loop (a REGRESSION
capture cites the run; a MANUAL capture must not; a REGRESSION without a citation is refused); the
pre-create refusal battery (too-few periods, non-CURRENCY candidate, wrong-purpose snapshot,
coverage gap) with NO RUNNING orphan; and the append-only / run_type!=metric guards. PG legs live in
test_proxy_weight_pg.py.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from run_assertions import assert_no_running_orphan
from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from irp_shared.audit.models import AppendOnlyViolation
from irp_shared.db.session import make_engine, make_session_factory
from irp_shared.entitlement.bootstrap import SYSTEM_TENANT_ID
from irp_shared.marketdata import (
    MAPPING_METHOD_MANUAL,
    MAPPING_METHOD_REGRESSION,
    FactorActor,
    ProxyMappingActor,
    capture_factor,
    capture_factor_return,
    capture_proxy_mapping,
    resolve_factor,
)
from irp_shared.marketdata.factor import supersede_factor_return
from irp_shared.marketdata.proxy_mapping import (
    ProxyMappingValueError,
    correct_proxy_mapping,
    supersede_proxy_mapping,
)
from irp_shared.models import Base
from irp_shared.perf import (
    DesmoothedReturnActor,
    register_desmoothed_return_model,
    run_desmoothed_return,
)
from irp_shared.portfolio import PortfolioActor, create_portfolio
from irp_shared.reference.instrument import create_instrument
from irp_shared.reference.models import Currency
from irp_shared.reference.service import ReferenceActor
from irp_shared.risk import (
    METRIC_TYPE_ESTIMATION_SUMMARY,
    METRIC_TYPE_INTERCEPT,
    METRIC_TYPE_WEIGHT,
    PROXY_WEIGHT_EWMA_CONVENTION,
    PROXY_WEIGHT_SHRINKAGE_EB_CONVENTION,
    ProxyWeightEstimateActor,
    ProxyWeightInputError,
    ProxyWeightKernelError,
    WrongModelVersionError,
    declared_proxy_weight_parameters,
    estimate_ols,
    list_proxy_weight_results,
    promote_proxy_weight_estimate,
    register_proxy_weight_ewma_model,
    register_proxy_weight_regression_model,
    register_proxy_weight_shrinkage_eb_model,
    run_proxy_weight_estimate,
)
from irp_shared.snapshot import verify_snapshot
from irp_shared.valuation import create_valuation
from irp_shared.valuation.service import ValuationActor

T0 = datetime(2024, 6, 1, tzinfo=UTC)
_RQ = Decimal("1E-12")
# Six quarterly appraisal marks => five observed returns => FOUR desmoothed periods (n-2). All dates
# are in the PAST relative to the system clock so the snapshot's valid_at=now pins the full window.
MARK_DATES = (
    date(2024, 9, 30),
    date(2024, 12, 31),
    date(2025, 3, 31),
    date(2025, 6, 30),
    date(2025, 9, 30),
    date(2025, 12, 31),
)
MARK_VALUES = ("100.00", "103.00", "104.50", "108.00", "106.00", "111.00")
WINDOW = (date(2024, 6, 1), date(2026, 1, 1))


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


def _currency(db: Session, code: str) -> None:
    if (
        db.execute(
            select(Currency).where(Currency.tenant_id == SYSTEM_TENANT_ID, Currency.code == code)
        ).scalar_one_or_none()
        is None
    ):
        db.add(Currency(tenant_id=SYSTEM_TENANT_ID, code=code, name=code, valid_from=T0))
        db.flush()


def _desmoothed_run(
    db: Session, tenant: str, mark_values: tuple[str, ...] = MARK_VALUES
) -> tuple[str, str, str]:
    """Seed a PE instrument + quarterly marks and run desmoothing. Returns
    (desmoothed_run_id, portfolio_id, instrument_id). ``mark_values`` varies the instrument so a
    shrinkage cohort has heterogeneous residuals."""
    _currency(db, "USD")
    pf = create_portfolio(
        db,
        tenant_id=tenant,
        code=f"PE-{uuid.uuid4().hex[:6]}",
        name="book",
        node_type="ACCOUNT",
        actor=PortfolioActor(actor_id="s"),
    ).id
    inst = create_instrument(
        db,
        tenant_id=tenant,
        code=f"FUND-{uuid.uuid4().hex[:6]}",
        name="Buyout Fund",
        asset_class="PRIVATE_EQUITY",
        actor=ReferenceActor(actor_id="s"),
    ).id
    for d, v in zip(MARK_DATES, mark_values, strict=True):
        create_valuation(
            db,
            portfolio_id=pf,
            instrument_id=inst,
            valuation_date=d,
            acting_tenant=tenant,
            actor=ValuationActor(actor_id="s"),
            mark_value=Decimal(v),
            currency_code="USD",
        )
    db.flush()
    model = register_desmoothed_return_model(
        db, tenant_id=tenant, actor_id="s", code_version="v1", alpha="0.5"
    )
    out = run_desmoothed_return(
        db,
        acting_tenant=tenant,
        actor=DesmoothedReturnActor(actor_id="a"),
        code_version="v1",
        environment_id="test",
        model_version_id=str(model.id),
        portfolio_id=pf,
        instrument_id=inst,
        window_start=WINDOW[0],
        window_end=WINDOW[1],
    )
    assert out.status == "COMPLETED"
    return str(out.run.run_id), pf, inst


def _factor(db: Session, tenant: str, code: str, family: str = "CURRENCY") -> str:
    return capture_factor(
        db,
        factor_code=code,
        factor_source="VENDOR_F",
        factor_family=family,
        currency_code=None,
        acting_tenant=tenant,
        actor=FactorActor(actor_id="s"),
        valid_from=T0,
    ).id


def _factor_returns(db: Session, tenant: str, factor_id: str, values: list[str]) -> None:
    # One return per appraisal period_end (MARK_DATES[1:]) so each period compounds a single value.
    factor = resolve_factor(db, factor_id, acting_tenant=tenant)
    for d, v in zip(MARK_DATES[1:], values, strict=True):
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


def _proxy_model(db: Session, tenant: str, min_obs: int = 4) -> str:
    return str(
        register_proxy_weight_regression_model(
            db, tenant_id=tenant, actor_id="s", code_version="v1", min_observations=min_obs
        ).id
    )


def test_full_stack_estimate_matches_independent_ols(session: Session) -> None:
    tenant = str(uuid.uuid4())
    run_id, pf, inst = _desmoothed_run(session, tenant)
    fx_usd = _factor(session, tenant, "FX_USD")
    fx_eur = _factor(session, tenant, "FX_EUR")
    # Distinct, non-collinear return patterns across the four periods.
    _factor_returns(session, tenant, fx_usd, ["0.01", "0.02", "-0.01", "0.03", "0.00"])
    _factor_returns(session, tenant, fx_eur, ["0.02", "-0.01", "0.01", "0.00", "0.02"])
    model_id = _proxy_model(session, tenant)

    out = run_proxy_weight_estimate(
        session,
        acting_tenant=tenant,
        actor=ProxyWeightEstimateActor(actor_id="a"),
        code_version="v1",
        environment_id="test",
        model_version_id=model_id,
        desmoothed_run_id=run_id,
        factor_ids=[fx_usd, fx_eur],
    )
    assert out.status == "COMPLETED"
    rows = list_proxy_weight_results(session, str(out.run.run_id), acting_tenant=tenant)
    kinds = sorted(r.metric_type for r in rows)
    assert kinds == [
        METRIC_TYPE_ESTIMATION_SUMMARY,
        METRIC_TYPE_INTERCEPT,
        METRIC_TYPE_WEIGHT,
        METRIC_TYPE_WEIGHT,
    ]

    # --- Independent recomputation: extract y (desmoothed periods) + X (per-period factor returns),
    # run the kernel directly, assert the persisted values are byte-identical. ---
    from irp_shared.perf.models import METRIC_TYPE_DESMOOTHED_PERIOD, DesmoothedReturnResult

    periods = list(
        session.execute(
            select(DesmoothedReturnResult)
            .where(
                DesmoothedReturnResult.calculation_run_id == run_id,
                DesmoothedReturnResult.metric_type == METRIC_TYPE_DESMOOTHED_PERIOD,
            )
            .order_by(DesmoothedReturnResult.period_start)
        )
        .scalars()
        .all()
    )
    assert len(periods) == 4
    y = [p.metric_value for p in periods]
    ends = [p.period_end for p in periods]
    # one return per period_end for each factor (compound of a single value == that value)
    usd = {
        d: Decimal(v)
        for d, v in zip(MARK_DATES[1:], ["0.01", "0.02", "-0.01", "0.03", "0.00"], strict=False)
    }
    eur = {
        d: Decimal(v)
        for d, v in zip(MARK_DATES[1:], ["0.02", "-0.01", "0.01", "0.00", "0.02"], strict=False)
    }
    # candidates are ordered by factor_id (lowercase) inside the service; match that order here.
    cols_by_fid = {
        fx_usd.lower(): [usd[e] for e in ends],
        fx_eur.lower(): [eur[e] for e in ends],
    }
    ordered_fids = sorted(cols_by_fid)
    fit = estimate_ols(y, [cols_by_fid[f] for f in ordered_fids])

    intercept = next(r for r in rows if r.metric_type == METRIC_TYPE_INTERCEPT)
    assert intercept.metric_value == fit.coefficients[0].quantize(_RQ)
    assert intercept.std_error == fit.std_errors[0].quantize(_RQ)
    weights = {r.factor_id: r for r in rows if r.metric_type == METRIC_TYPE_WEIGHT}
    for j, fid in enumerate(ordered_fids):
        assert weights[fid].metric_value == fit.coefficients[j + 1].quantize(_RQ)
        assert weights[fid].std_error == fit.std_errors[j + 1].quantize(_RQ)
    summary = next(r for r in rows if r.metric_type == METRIC_TYPE_ESTIMATION_SUMMARY)
    assert summary.metric_value == fit.r_squared.quantize(_RQ)
    assert summary.residual_stdev == fit.residual_stdev.quantize(_RQ)
    assert summary.n_observations == 4 and summary.n_regressors == 3
    # every row echoes the declared identity + subject + provenance.
    for r in rows:
        assert r.min_observations == 4
        assert r.series_currency == "USD"
        assert str(r.source_desmoothed_run_id) == run_id
        assert str(r.portfolio_id) == pf and str(r.instrument_id) == inst


def test_promotion_regression_cites_run_manual_refuses(session: Session) -> None:
    tenant = str(uuid.uuid4())
    run_id, _pf, inst = _desmoothed_run(session, tenant)
    fx_usd = _factor(session, tenant, "FX_USD")
    fx_eur = _factor(session, tenant, "FX_EUR")
    _factor_returns(session, tenant, fx_usd, ["0.01", "0.02", "-0.01", "0.03", "0.00"])
    _factor_returns(session, tenant, fx_eur, ["0.02", "-0.01", "0.01", "0.00", "0.02"])
    out = run_proxy_weight_estimate(
        session,
        acting_tenant=tenant,
        actor=ProxyWeightEstimateActor(actor_id="a"),
        code_version="v1",
        environment_id="test",
        model_version_id=_proxy_model(session, tenant),
        desmoothed_run_id=run_id,
        factor_ids=[fx_usd, fx_eur],
    )
    est_run = str(out.run.run_id)

    # The governed promotion resolves the run (COMPLETED PROXY_WEIGHT_ESTIMATE) then captures a
    # REGRESSION weight citing it — the analyst picks the coefficient (0.6) to promote.
    promoted = promote_proxy_weight_estimate(
        session,
        private_instrument_id=inst,
        factor_id=fx_usd,
        weight=Decimal("0.6"),
        acting_tenant=tenant,
        actor=ProxyMappingActor(actor_id="s"),
        source_calculation_run_id=est_run,
    )
    assert promoted.mapping_method == MAPPING_METHOD_REGRESSION
    assert str(promoted.source_calculation_run_id) == est_run

    # Promoting a run that is NOT a proxy-weight-estimate (here the desmoothed run) is refused.
    with pytest.raises(ProxyWeightInputError, match="not a visible"):
        promote_proxy_weight_estimate(
            session,
            private_instrument_id=inst,
            factor_id=fx_eur,
            weight=Decimal("0.3"),
            acting_tenant=tenant,
            actor=ProxyMappingActor(actor_id="s"),
            source_calculation_run_id=run_id,  # the DESMOOTHED_RETURN run — wrong type
        )

    # A REGRESSION capture WITHOUT a citation is refused (the marketdata method-blur guard).
    with pytest.raises(ProxyMappingValueError, match="must cite"):
        capture_proxy_mapping(
            session,
            private_instrument_id=inst,
            factor_id=fx_eur,
            weight=Decimal("0.3"),
            acting_tenant=tenant,
            actor=ProxyMappingActor(actor_id="s"),
            mapping_method=MAPPING_METHOD_REGRESSION,
        )
    # A MANUAL capture citing a run is refused (methods never blur).
    with pytest.raises(ProxyMappingValueError, match="only valid with"):
        capture_proxy_mapping(
            session,
            private_instrument_id=inst,
            factor_id=fx_eur,
            weight=Decimal("0.3"),
            acting_tenant=tenant,
            actor=ProxyMappingActor(actor_id="s"),
            mapping_method=MAPPING_METHOD_MANUAL,
            source_calculation_run_id=est_run,
        )


def _estimate(session: Session, tenant: str, run_id: str, factor_ids: list[str], **kw: object):
    return run_proxy_weight_estimate(
        session,
        acting_tenant=tenant,
        actor=ProxyWeightEstimateActor(actor_id="a"),
        code_version="v1",
        environment_id="test",
        desmoothed_run_id=run_id,
        factor_ids=factor_ids,
        **kw,  # type: ignore[arg-type]
    )


def test_refusals_leave_no_running_orphan(session: Session) -> None:
    tenant = str(uuid.uuid4())
    run_id, _pf, _inst = _desmoothed_run(session, tenant)
    fx_usd = _factor(session, tenant, "FX_USD")
    fx_eur = _factor(session, tenant, "FX_EUR")
    fx_gbp = _factor(session, tenant, "FX_GBP")
    _factor_returns(session, tenant, fx_usd, ["0.01", "0.02", "-0.01", "0.03", "0.00"])
    _factor_returns(session, tenant, fx_eur, ["0.02", "-0.01", "0.01", "0.00", "0.02"])
    _factor_returns(session, tenant, fx_gbp, ["0.00", "0.01", "0.02", "-0.01", "0.01"])
    model_id = _proxy_model(session, tenant)  # min_observations=4

    # Too few periods for the regressor count: k=3 => floor max(4, k+2)=5 > n=4.
    with pytest.raises(ProxyWeightInputError, match="need >= 5"):
        _estimate(session, tenant, run_id, [fx_usd, fx_eur, fx_gbp], model_version_id=model_id)
    assert_no_running_orphan(session)

    # An UNADMITTED candidate factor family is refused. FL-1 widened the candidate gate to the
    # LOADING_FACTOR_FAMILIES allow-list (MARKET is now admitted), so the probe MOVES to OTHER —
    # the catch-all that stays refused (the ES-1 probe-move pattern).
    other = _factor(session, tenant, "OTHER_F", family="OTHER")
    _factor_returns(session, tenant, other, ["0.01", "0.02", "0.03", "0.01", "0.02"])
    with pytest.raises(ProxyWeightInputError, match="OTHER/unknown stay refused"):
        _estimate(session, tenant, run_id, [fx_usd, other], model_version_id=model_id)
    assert_no_running_orphan(session)


def test_append_only_and_run_type_not_metric(session: Session) -> None:
    tenant = str(uuid.uuid4())
    run_id, _pf, _inst = _desmoothed_run(session, tenant)
    fx_usd = _factor(session, tenant, "FX_USD")
    fx_eur = _factor(session, tenant, "FX_EUR")
    _factor_returns(session, tenant, fx_usd, ["0.01", "0.02", "-0.01", "0.03", "0.00"])
    _factor_returns(session, tenant, fx_eur, ["0.02", "-0.01", "0.01", "0.00", "0.02"])
    out = _estimate(
        session,
        tenant,
        run_id,
        [fx_usd, fx_eur],
        model_version_id=_proxy_model(session, tenant),
    )
    row = list_proxy_weight_results(session, str(out.run.run_id), acting_tenant=tenant)[0]
    # run_type (family) is never a metric_type (GS2).
    assert out.run.run_type == "PROXY_WEIGHT_ESTIMATE"
    assert out.run.run_type not in {
        METRIC_TYPE_WEIGHT,
        METRIC_TYPE_INTERCEPT,
        METRIC_TYPE_ESTIMATION_SUMMARY,
    }
    # IA append-only: mutation is blocked by the ORM guard.
    row.metric_value = Decimal("9.9")
    with pytest.raises(AppendOnlyViolation):
        session.flush()
    session.rollback()


def test_unregistered_and_wrong_purpose_snapshot(session: Session) -> None:
    tenant = str(uuid.uuid4())
    run_id, _pf, _inst = _desmoothed_run(session, tenant)
    fx_usd = _factor(session, tenant, "FX_USD")
    fx_eur = _factor(session, tenant, "FX_EUR")
    _factor_returns(session, tenant, fx_usd, ["0.01", "0.02", "-0.01", "0.03", "0.00"])
    _factor_returns(session, tenant, fx_eur, ["0.02", "-0.01", "0.01", "0.00", "0.02"])
    # A snapshot of the WRONG purpose (the desmoothing input) is refused.
    from irp_shared.snapshot import build_desmoothing_snapshot
    from irp_shared.snapshot.events import SnapshotActor

    other = build_desmoothing_snapshot(
        session,
        acting_tenant=tenant,
        actor=SnapshotActor(actor_id="s"),
        portfolio_id=_pf,
        instrument_id=_inst,
        window_start=WINDOW[0],
        window_end=WINDOW[1],
    )
    with pytest.raises(ProxyWeightInputError, match="purpose"):
        run_proxy_weight_estimate(
            session,
            acting_tenant=tenant,
            actor=ProxyWeightEstimateActor(actor_id="a"),
            code_version="v1",
            environment_id="test",
            model_version_id=_proxy_model(session, tenant),
            snapshot_id=str(other.id),
        )
    assert_no_running_orphan(session)


def test_tr09_supersede_does_not_move_estimate(session: Session) -> None:
    tenant = str(uuid.uuid4())
    run_id, _pf, _inst = _desmoothed_run(session, tenant)
    fx_usd = _factor(session, tenant, "FX_USD")
    fx_eur = _factor(session, tenant, "FX_EUR")
    _factor_returns(session, tenant, fx_usd, ["0.01", "0.02", "-0.01", "0.03", "0.00"])
    _factor_returns(session, tenant, fx_eur, ["0.02", "-0.01", "0.01", "0.00", "0.02"])
    model_id = _proxy_model(session, tenant)
    out = run_proxy_weight_estimate(
        session,
        acting_tenant=tenant,
        actor=ProxyWeightEstimateActor(actor_id="a"),
        code_version="v1",
        environment_id="test",
        model_version_id=model_id,
        desmoothed_run_id=run_id,
        factor_ids=[fx_usd, fx_eur],
    )
    snap = out.run.input_snapshot_id
    before = {
        (r.metric_type, r.factor_id): r.metric_value
        for r in list_proxy_weight_results(session, str(out.run.run_id), acting_tenant=tenant)
    }
    # Supersede a pinned factor return with a WILDLY different value, effective now.
    factor = resolve_factor(session, fx_usd, acting_tenant=tenant)
    supersede_factor_return(
        session,
        factor,
        return_date=MARK_DATES[2],
        return_value=Decimal("0.99"),
        acting_tenant=tenant,
        actor=FactorActor(actor_id="s"),
        effective_at=datetime(2026, 6, 1, tzinfo=UTC),
    )
    session.flush()
    # TR-09 side A: the pinned immutable versions are byte-stable.
    assert verify_snapshot(session, snapshot_id=str(snap), acting_tenant=tenant).ok
    # TR-09 side B: re-running the SAME snapshot reproduces the historical estimate byte-for-byte.
    out2 = run_proxy_weight_estimate(
        session,
        acting_tenant=tenant,
        actor=ProxyWeightEstimateActor(actor_id="a"),
        code_version="v1",
        environment_id="test",
        model_version_id=model_id,
        snapshot_id=str(snap),
    )
    after = {
        (r.metric_type, r.factor_id): r.metric_value
        for r in list_proxy_weight_results(session, str(out2.run.run_id), acting_tenant=tenant)
    }
    assert before == after


def test_singular_collinear_design_refused(session: Session) -> None:
    tenant = str(uuid.uuid4())
    run_id, _pf, _inst = _desmoothed_run(session, tenant)
    fx_a = _factor(session, tenant, "FX_A")
    fx_b = _factor(session, tenant, "FX_B")
    # fx_b is exactly 2x fx_a every period => the design matrix is singular/collinear.
    _factor_returns(session, tenant, fx_a, ["0.01", "0.02", "-0.01", "0.03", "0.00"])
    _factor_returns(session, tenant, fx_b, ["0.02", "0.04", "-0.02", "0.06", "0.00"])
    with pytest.raises(ProxyWeightInputError, match="singular"):
        _estimate(
            session,
            tenant,
            run_id,
            [fx_a, fx_b],
            model_version_id=_proxy_model(session, tenant),
        )
    assert_no_running_orphan(session)


def test_extreme_magnitude_is_committed_failed(session: Session) -> None:
    tenant = str(uuid.uuid4())
    run_id, _pf, _inst = _desmoothed_run(session, tenant)
    tiny = _factor(session, tenant, "FX_TINY")
    # A tiny-but-non-constant regressor => a huge OLS slope (~ y-scale / 1e-11 >> 1E8 envelope):
    # the RAW coefficient is magnitude-gated to a committed FAILED run (not a raise).
    _factor_returns(
        session,
        tenant,
        tiny,
        ["0.00000000001", "0.00000000002", "0.00000000001", "0.00000000003", "0.00000000001"],
    )
    out = _estimate(
        session,
        tenant,
        run_id,
        [tiny],
        model_version_id=_proxy_model(session, tenant, min_obs=3),
    )
    assert out.status == "FAILED"
    assert out.rows == []
    assert out.failure_reason is not None and "magnitude" in out.failure_reason
    assert_no_running_orphan(session)


def test_per_period_coverage_gap_refused(session: Session) -> None:
    # A candidate factor with returns in the span but MISSING one appraisal period's coverage is
    # refused by the binder's no-zero-fill gate (distinct from "no returns at all" — the builder
    # still pins it since it has span returns).
    tenant = str(uuid.uuid4())
    run_id, _pf, _inst = _desmoothed_run(session, tenant)
    fx_ok = _factor(session, tenant, "FX_OK")
    fx_gap = _factor(session, tenant, "FX_GAP")
    _factor_returns(session, tenant, fx_ok, ["0.01", "0.02", "-0.01", "0.03", "0.00"])
    # fx_gap: covers periods 0/2/3 but SKIPS period 1's end (MARK_DATES[3]).
    factor = resolve_factor(session, fx_gap, acting_tenant=tenant)
    for d, v in (
        (MARK_DATES[1], "0.01"),
        (MARK_DATES[2], "0.02"),
        (MARK_DATES[4], "0.03"),
        (MARK_DATES[5], "0.00"),
    ):
        capture_factor_return(
            session,
            factor,
            return_date=d,
            return_value=Decimal(v),
            acting_tenant=tenant,
            actor=FactorActor(actor_id="s"),
            valid_from=T0,
        )
    session.flush()
    with pytest.raises(ProxyWeightInputError, match="no return covering"):
        _estimate(
            session,
            tenant,
            run_id,
            [fx_ok, fx_gap],
            model_version_id=_proxy_model(session, tenant),
        )
    assert_no_running_orphan(session)


def test_kernel_refuses_constant_target() -> None:
    # A constant target series has SS_tot == 0 (R^2 undefined) — the kernel refuses structurally
    # (the service maps it to a pre-create ProxyWeightInputError, like the singular path).
    y = [Decimal("0.1")] * 5
    x = [Decimal("0.01"), Decimal("0.02"), Decimal("0.03"), Decimal("0.02"), Decimal("0.04")]
    with pytest.raises(ProxyWeightKernelError) as exc:
        estimate_ols(y, [x])
    assert exc.value.reason == "constant-target"


def test_supersede_correct_regression_citation_guards(session: Session) -> None:
    # The OD-PA-3-E invariant on the REVISION paths: a REGRESSION supersede without a citation
    # refuses (the same blur guard as capture — and the HTTP supersede body cannot carry one, so
    # via the API a REGRESSION supersede ALWAYS refuses); a correction can never mint REGRESSION
    # (v1 recorded limitation — re-promote instead).
    tenant = str(uuid.uuid4())
    _run, _pf, inst = _desmoothed_run(session, tenant)
    fx = _factor(session, tenant, "FX_USD")
    # seed a MANUAL open head to supersede/correct.
    capture_proxy_mapping(
        session,
        private_instrument_id=inst,
        factor_id=fx,
        weight=Decimal("0.5"),
        acting_tenant=tenant,
        actor=ProxyMappingActor(actor_id="s"),
        mapping_method=MAPPING_METHOD_MANUAL,
    )
    with pytest.raises(ProxyMappingValueError, match="must cite"):
        supersede_proxy_mapping(
            session,
            private_instrument_id=inst,
            factor_id=fx,
            weight=Decimal("0.6"),
            acting_tenant=tenant,
            actor=ProxyMappingActor(actor_id="s"),
            effective_at=datetime(2026, 6, 1, tzinfo=UTC),
            mapping_method=MAPPING_METHOD_REGRESSION,
        )
    with pytest.raises(ProxyMappingValueError, match="cannot mint a REGRESSION"):
        correct_proxy_mapping(
            session,
            private_instrument_id=inst,
            factor_id=fx,
            weight=Decimal("0.6"),
            acting_tenant=tenant,
            actor=ProxyMappingActor(actor_id="s"),
            restatement_reason="fix",
            mapping_method=MAPPING_METHOD_REGRESSION,
        )
    # A MANUAL supersede carrying a citation also refuses (methods never blur on revision either).
    with pytest.raises(ProxyMappingValueError, match="only valid with"):
        supersede_proxy_mapping(
            session,
            private_instrument_id=inst,
            factor_id=fx,
            weight=Decimal("0.6"),
            acting_tenant=tenant,
            actor=ProxyMappingActor(actor_id="s"),
            effective_at=datetime(2026, 6, 1, tzinfo=UTC),
            mapping_method=MAPPING_METHOD_MANUAL,
            source_calculation_run_id=str(uuid.uuid4()),
        )


def test_repromotion_supersedes_with_citation(session: Session) -> None:
    # The steady-state loop: promote once (capture), then RE-promote the same key (a
    # citation-carrying supersede) — new version, method preserved, citation updated.
    tenant = str(uuid.uuid4())
    run_id, _pf, inst = _desmoothed_run(session, tenant)
    fx_usd = _factor(session, tenant, "FX_USD")
    fx_eur = _factor(session, tenant, "FX_EUR")
    _factor_returns(session, tenant, fx_usd, ["0.01", "0.02", "-0.01", "0.03", "0.00"])
    _factor_returns(session, tenant, fx_eur, ["0.02", "-0.01", "0.01", "0.00", "0.02"])
    model_id = _proxy_model(session, tenant)
    est1 = str(
        run_proxy_weight_estimate(
            session,
            acting_tenant=tenant,
            actor=ProxyWeightEstimateActor(actor_id="a"),
            code_version="v1",
            environment_id="test",
            model_version_id=model_id,
            desmoothed_run_id=run_id,
            factor_ids=[fx_usd, fx_eur],
        ).run.run_id
    )
    act = ProxyMappingActor(actor_id="s")
    first = promote_proxy_weight_estimate(
        session,
        private_instrument_id=inst,
        factor_id=fx_usd,
        weight=Decimal("0.6"),
        acting_tenant=tenant,
        actor=act,
        source_calculation_run_id=est1,
    )
    assert first.record_version == 1 and str(first.source_calculation_run_id) == est1
    # a NEW estimate run -> the analyst re-promotes an updated weight.
    est2 = str(
        run_proxy_weight_estimate(
            session,
            acting_tenant=tenant,
            actor=ProxyWeightEstimateActor(actor_id="a"),
            code_version="v1",
            environment_id="test",
            model_version_id=model_id,
            desmoothed_run_id=run_id,
            factor_ids=[fx_usd, fx_eur],
        ).run.run_id
    )
    second = promote_proxy_weight_estimate(
        session,
        private_instrument_id=inst,
        factor_id=fx_usd,
        weight=Decimal("0.55"),
        acting_tenant=tenant,
        actor=act,
        source_calculation_run_id=est2,
    )
    assert second.record_version == 2
    assert second.mapping_method == MAPPING_METHOD_REGRESSION
    assert str(second.source_calculation_run_id) == est2
    assert str(second.supersedes_id) == str(first.id)
    # promoting a wrong-type run on the REVISION path refuses too (the run-TYPE gate).
    with pytest.raises(ProxyWeightInputError, match="not a visible"):
        promote_proxy_weight_estimate(
            session,
            private_instrument_id=inst,
            factor_id=fx_usd,
            weight=Decimal("0.5"),
            acting_tenant=tenant,
            actor=act,
            source_calculation_run_id=run_id,  # the DESMOOTHED_RETURN run
        )


# --- RS-1: the EWMA + empirical-Bayes shrinkage estimator conventions ----------------------------

_USD_RETS = ["0.01", "0.02", "-0.01", "0.03", "0.00"]
_EUR_RETS = ["0.02", "-0.01", "0.01", "0.00", "0.02"]


def _extract_yx(session: Session, run_id: str, fx_usd: str, fx_eur: str) -> tuple[list, list]:
    """Extract the (y, X) the estimate service saw — the desmoothed periods + per-period factor
    returns (one return per period_end), candidate order = factor_id ascending."""
    from irp_shared.perf.models import METRIC_TYPE_DESMOOTHED_PERIOD, DesmoothedReturnResult

    periods = list(
        session.execute(
            select(DesmoothedReturnResult)
            .where(
                DesmoothedReturnResult.calculation_run_id == run_id,
                DesmoothedReturnResult.metric_type == METRIC_TYPE_DESMOOTHED_PERIOD,
            )
            .order_by(DesmoothedReturnResult.period_start)
        )
        .scalars()
        .all()
    )
    y = [p.metric_value for p in periods]
    ends = [p.period_end for p in periods]
    usd = {d: Decimal(v) for d, v in zip(MARK_DATES[1:], _USD_RETS, strict=False)}
    eur = {d: Decimal(v) for d, v in zip(MARK_DATES[1:], _EUR_RETS, strict=False)}
    cols_by_fid = {fx_usd.lower(): [usd[e] for e in ends], fx_eur.lower(): [eur[e] for e in ends]}
    ordered = sorted(cols_by_fid)
    return y, [cols_by_fid[f] for f in ordered]


def test_ewma_estimate_reweights_residual_only(session: Session) -> None:
    """An EWMA version re-derives residual_stdev via the EWMA convention while the loadings + std
    errors + R^2 stay byte-identical to the raw run (the s2 decoupling at the persistence layer)."""
    tenant = str(uuid.uuid4())
    run_id, pf, inst = _desmoothed_run(session, tenant)
    fx_usd = _factor(session, tenant, "FX_USD")
    fx_eur = _factor(session, tenant, "FX_EUR")
    _factor_returns(session, tenant, fx_usd, _USD_RETS)
    _factor_returns(session, tenant, fx_eur, _EUR_RETS)
    raw_model = _proxy_model(session, tenant)
    ewma_version = register_proxy_weight_ewma_model(
        session,
        tenant_id=tenant,
        actor_id="s",
        code_version="v1",
        decay_lambda="0.9",
        min_observations=4,
    )
    params = declared_proxy_weight_parameters(session, ewma_version)
    assert params.estimator_convention == PROXY_WEIGHT_EWMA_CONVENTION
    assert params.decay_lambda == Decimal("0.9")
    assert params.min_observations == 4

    common = dict(
        acting_tenant=tenant,
        actor=ProxyWeightEstimateActor(actor_id="a"),
        code_version="v1",
        environment_id="test",
        desmoothed_run_id=run_id,
        factor_ids=[fx_usd, fx_eur],
    )
    raw_out = run_proxy_weight_estimate(session, model_version_id=raw_model, **common)
    ewma_out = run_proxy_weight_estimate(session, model_version_id=str(ewma_version.id), **common)
    assert raw_out.status == "COMPLETED" and ewma_out.status == "COMPLETED"
    raw_rows = list_proxy_weight_results(session, str(raw_out.run.run_id), acting_tenant=tenant)
    ewma_rows = list_proxy_weight_results(session, str(ewma_out.run.run_id), acting_tenant=tenant)

    def _summary(rows: list) -> object:
        return next(r for r in rows if r.metric_type == METRIC_TYPE_ESTIMATION_SUMMARY)

    raw_sum, ewma_sum = _summary(raw_rows), _summary(ewma_rows)
    # loadings + inference + R^2 byte-identical; only residual_stdev diverges.
    assert raw_sum.metric_value == ewma_sum.metric_value  # R^2

    def _loadings(rows: list) -> dict:
        return {
            (r.metric_type, r.factor_id): (r.metric_value, r.std_error)
            for r in rows
            if r.metric_type != METRIC_TYPE_ESTIMATION_SUMMARY
        }

    assert _loadings(raw_rows) == _loadings(ewma_rows)
    assert raw_sum.residual_stdev != ewma_sum.residual_stdev

    # correctness: both match the kernel re-derivation on the extracted (y, X).
    y, x = _extract_yx(session, run_id, fx_usd, fx_eur)
    assert raw_sum.residual_stdev == estimate_ols(y, x).residual_stdev.quantize(_RQ)
    assert ewma_sum.residual_stdev == estimate_ols(
        y, x, decay_lambda=Decimal("0.9")
    ).residual_stdev.quantize(_RQ)


def test_estimate_run_rejects_eb_shrinkage_version(session: Session) -> None:
    """A SHRINKAGE_CROSS_SECTIONAL_EB version is a transform, not an OLS estimate — the estimate run
    fails closed with WrongModelVersionError (the registry-map dispatch)."""
    tenant = str(uuid.uuid4())
    run_id, pf, inst = _desmoothed_run(session, tenant)
    fx = _factor(session, tenant, "FX_USD")
    _factor_returns(session, tenant, fx, _USD_RETS)
    eb_version = register_proxy_weight_shrinkage_eb_model(
        session, tenant_id=tenant, actor_id="s", code_version="v1"
    )
    params = declared_proxy_weight_parameters(session, eb_version)
    assert params.estimator_convention == PROXY_WEIGHT_SHRINKAGE_EB_CONVENTION
    assert params.min_observations is None and params.decay_lambda is None
    with pytest.raises(WrongModelVersionError):
        run_proxy_weight_estimate(
            session,
            acting_tenant=tenant,
            actor=ProxyWeightEstimateActor(actor_id="a"),
            code_version="v1",
            environment_id="test",
            model_version_id=str(eb_version.id),
            desmoothed_run_id=run_id,
            factor_ids=[fx],
        )


def _raw_estimate(db: Session, tenant: str, marks: tuple[str, ...]) -> str:
    """A full raw OLS estimate for one instrument (its own desmoothed run + the shared 2 factors).
    Returns the estimate run_id."""
    run_id, _pf, _inst = _desmoothed_run(db, tenant, marks)
    fx_usd = _factor(db, tenant, f"FX_USD_{uuid.uuid4().hex[:4]}")
    fx_eur = _factor(db, tenant, f"FX_EUR_{uuid.uuid4().hex[:4]}")
    _factor_returns(db, tenant, fx_usd, _USD_RETS)
    _factor_returns(db, tenant, fx_eur, _EUR_RETS)
    out = run_proxy_weight_estimate(
        db,
        acting_tenant=tenant,
        actor=ProxyWeightEstimateActor(actor_id="a"),
        code_version="v1",
        environment_id="test",
        model_version_id=_proxy_model(db, tenant),
        desmoothed_run_id=run_id,
        factor_ids=[fx_usd, fx_eur],
    )
    assert out.status == "COMPLETED"
    return str(out.run.run_id)


def _cohort(db: Session, tenant: str, n: int) -> list[str]:
    # Distinct mark paths => heterogeneous residual variances across the cohort.
    paths = [
        ("100.00", "103.00", "104.50", "108.00", "106.00", "111.00"),
        ("100.00", "101.00", "103.00", "102.00", "105.00", "104.00"),
        ("100.00", "106.00", "103.00", "110.00", "104.00", "113.00"),
        ("100.00", "100.50", "101.20", "101.80", "102.10", "103.00"),
    ]
    return [_raw_estimate(db, tenant, paths[i]) for i in range(n)]


def _eb_version(db: Session, tenant: str) -> str:
    return str(
        register_proxy_weight_shrinkage_eb_model(
            db, tenant_id=tenant, actor_id="s", code_version="v1"
        ).id
    )


def test_residual_shrinkage_matches_kernel_over_cohort(session: Session) -> None:
    """A per-instrument EB shrinkage run persists ONE ESTIMATION_SUMMARY whose residual_stdev is the
    kernel's shrunk value for the target over the pinned cohort; the target's regression identity
    (R^2 / df / instrument) is carried unchanged from its raw estimate."""
    from irp_shared.risk import run_residual_shrinkage
    from irp_shared.risk.residual_shrinkage_kernel import (
        ShrinkageMemberInput,
        shrink_residual_variances,
    )

    tenant = str(uuid.uuid4())
    cohort = _cohort(session, tenant, 3)
    target = cohort[0]
    eb = _eb_version(session, tenant)

    out = run_residual_shrinkage(
        session,
        acting_tenant=tenant,
        actor=ProxyWeightEstimateActor(actor_id="a"),
        code_version="v1",
        environment_id="test",
        model_version_id=eb,
        target_estimate_run_id=target,
        cohort_estimate_run_ids=cohort,
    )
    assert out.status == "COMPLETED"
    assert len(out.rows) == 1
    row = out.rows[0]
    assert row.metric_type == METRIC_TYPE_ESTIMATION_SUMMARY

    # Re-derive: the kernel over the cohort's PERSISTED raw summaries, in cohort order.
    raw_summaries = [
        next(
            r
            for r in list_proxy_weight_results(session, rid, acting_tenant=tenant)
            if r.metric_type == METRIC_TYPE_ESTIMATION_SUMMARY
        )
        for rid in cohort
    ]
    est = shrink_residual_variances(
        [
            ShrinkageMemberInput(s.residual_stdev, s.n_observations, s.n_regressors)
            for s in raw_summaries
        ]
    )
    expected = est.members[0].shrunk_residual_stdev.quantize(_RQ)
    assert row.residual_stdev == expected
    # identity carried from the target's raw estimate; only residual transformed.
    target_raw = raw_summaries[0]
    assert row.instrument_id == target_raw.instrument_id
    assert row.metric_value == target_raw.metric_value  # R^2 unchanged
    assert row.n_observations == target_raw.n_observations
    assert row.n_regressors == target_raw.n_regressors
    assert row.residual_stdev != target_raw.residual_stdev  # the one thing that shrank


def test_residual_shrinkage_below_min_cohort_refused(session: Session) -> None:
    tenant = str(uuid.uuid4())
    cohort = _cohort(session, tenant, 2)  # < MIN_COHORT_SIZE
    eb = _eb_version(session, tenant)
    from irp_shared.risk import ResidualShrinkageInputError, run_residual_shrinkage

    with pytest.raises(ResidualShrinkageInputError):
        run_residual_shrinkage(
            session,
            acting_tenant=tenant,
            actor=ProxyWeightEstimateActor(actor_id="a"),
            code_version="v1",
            environment_id="test",
            model_version_id=eb,
            target_estimate_run_id=cohort[0],
            cohort_estimate_run_ids=cohort,
        )
    assert_no_running_orphan(session)


# --- RS-1 review folds: the ambiguity/stray-literal gate (A1/A4) + cohort distinctness (A2) ---


def _mint_pw_version(db: Session, tenant: str, assumptions: list[str]):  # noqa: ANN202
    """Mint a proxy-weight version through the GENERIC path (arbitrary assumption rows — the
    P3-4 threat the parse-gate exists for)."""
    from irp_shared.model.service import register_model_version, resolve_or_register_model

    model = resolve_or_register_model(
        db,
        tenant_id=tenant,
        code="risk.proxy_weight.regression",
        name="pw",
        model_type="PROXY_WEIGHT",
        actor_id="s",
        description="generic mint (test)",
    )
    return register_model_version(
        db,
        model=model,
        version_label=f"vX-{uuid.uuid4().hex[:6]}",
        actor_id="s",
        methodology_ref="05_analytics_methodologies/residual_estimation_v1.md",
        code_version="v1",
        status="REGISTERED",
        assumptions=tuple(assumptions),
        limitations=(),
    )


@pytest.mark.parametrize(
    "assumptions",
    [
        # AMBIGUOUS: duplicated convention rows must NEVER collapse into the RAW grandfather.
        [
            "min_observations=6",
            "estimator_convention=EWMA_RISKMETRICS",
            "estimator_convention=EWMA_RISKMETRICS",
            "decay_lambda=0.94",
        ],
        # AMBIGUOUS: two DIFFERENT conventions.
        [
            "min_observations=6",
            "estimator_convention=EWMA_RISKMETRICS",
            "estimator_convention=SHRINKAGE_CROSS_SECTIONAL_EB",
            "decay_lambda=0.94",
        ],
        # STRAY literal on an implicit-RAW version (a lying displayed identity).
        ["min_observations=6", "decay_lambda=0.94"],
        # STRAY literals on an EB version (method-as-identity carries NO numerics).
        [
            "estimator_convention=SHRINKAGE_CROSS_SECTIONAL_EB",
            "min_observations=6",
        ],
        [
            "estimator_convention=SHRINKAGE_CROSS_SECTIONAL_EB",
            "decay_lambda=0.94",
        ],
        # Unknown convention literal.
        ["min_observations=6", "estimator_convention=KERNEL_SMOOTHED"],
    ],
)
def test_gate_refuses_ambiguous_and_stray_declarations(
    session: Session, assumptions: list[str]
) -> None:
    tenant = str(uuid.uuid4())
    version = _mint_pw_version(session, tenant, assumptions)
    with pytest.raises(WrongModelVersionError):
        declared_proxy_weight_parameters(session, version)


def test_gate_still_grandfathers_a_clean_absent_convention(session: Session) -> None:
    """The grandfather survives the ambiguity fix: zero convention rows + no stray literal
    parses as implicit RAW."""
    tenant = str(uuid.uuid4())
    version = _mint_pw_version(session, tenant, ["min_observations=6"])
    params = declared_proxy_weight_parameters(session, version)
    assert params.estimator_convention == "RAW"
    assert params.min_observations == 6 and params.decay_lambda is None


def test_shrinkage_refuses_duplicate_instrument_cohort(session: Session) -> None:
    """A2: the cross-sectional units are INSTRUMENTS — two estimate runs of the same instrument
    in one cohort are refused, never silently pooled (the N>=3 floor cannot be satisfied by
    re-estimates of one name)."""
    from irp_shared.risk import ResidualShrinkageInputError, run_residual_shrinkage

    tenant = str(uuid.uuid4())
    # Two instruments; instrument X estimated TWICE (the steady-state re-estimation shape).
    x_run_1 = _raw_estimate(
        session, tenant, ("100.00", "103.00", "104.50", "108.00", "106.00", "111.00")
    )
    y_run = _raw_estimate(
        session, tenant, ("100.00", "101.00", "103.00", "102.00", "105.00", "104.00")
    )
    # Re-estimate X: a second run over X's existing desmoothed series via its own snapshot chain.
    from irp_shared.risk.models import ProxyWeightEstimateResult as _R

    x_summary = session.execute(
        select(_R).where(
            _R.calculation_run_id == x_run_1,
            _R.metric_type == METRIC_TYPE_ESTIMATION_SUMMARY,
        )
    ).scalar_one()
    x_run_2 = run_proxy_weight_estimate(
        session,
        acting_tenant=tenant,
        actor=ProxyWeightEstimateActor(actor_id="a"),
        code_version="v1",
        environment_id="test",
        model_version_id=str(x_summary.model_version_id),
        snapshot_id=str(x_summary.input_snapshot_id),
    )
    assert x_run_2.status == "COMPLETED"
    eb = _eb_version(session, tenant)
    with pytest.raises(ResidualShrinkageInputError):
        run_residual_shrinkage(
            session,
            acting_tenant=tenant,
            actor=ProxyWeightEstimateActor(actor_id="a"),
            code_version="v1",
            environment_id="test",
            model_version_id=eb,
            target_estimate_run_id=y_run,
            cohort_estimate_run_ids=[x_run_1, str(x_run_2.run.run_id), y_run],
        )
    assert_no_running_orphan(session)
