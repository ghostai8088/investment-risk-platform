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
    ProxyWeightEstimateActor,
    ProxyWeightInputError,
    ProxyWeightKernelError,
    estimate_ols,
    list_proxy_weight_results,
    promote_proxy_weight_estimate,
    register_proxy_weight_regression_model,
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


def _desmoothed_run(db: Session, tenant: str) -> tuple[str, str, str]:
    """Seed a PE instrument + quarterly marks and run desmoothing. Returns
    (desmoothed_run_id, portfolio_id, instrument_id)."""
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
    for d, v in zip(MARK_DATES, MARK_VALUES, strict=True):
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
