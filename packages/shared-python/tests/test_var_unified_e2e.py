"""End-to-end SQLite tests for PPF-3 — the UNIFIED public+private parametric VaR
(``run_var_unified``, ``risk.var.parametric_unified``, the 20th governed number, §2.1 arc slice 3,
the final assembly). RLS/append-only legs live in ``test_var_unified_pg.py``.

Proves the number ASSEMBLES end-to-end over the REAL substrate. The book is TWO PRIVATE_EQUITY
funds in ONE portfolio, each: currency-denominated + factor-exposed (the public factor leg),
carrying a full PPF-1 pure-private run (a desmoothing run + a promoted {FX_USD,FX_EUR} REGRESSION
blend) AND a MANUAL pure-private-segment membership. A public DAILY covariance spans the two FX
factors; an Ω_pp APPRAISAL block spans the two segments. The three legs are NON-OVERLAPPING by the
OD-3-G REPARTITION.

Two tests, each seeding the book once:

* ``test_unified_assembles_three_legs_and_repartitions`` — the happy-path assembly. (1) the unified
  run COMPLETES and persists ``metric_type=VAR_PARAMETRIC_UNIFIED`` with ``private_variance`` +
  ``private_covariance_run_id``; (2) THREE-LEG RECONCILIATION against two INDEPENDENT governed runs
  over the SAME pins — ``sigma_unified**2 == plain_sigma**2 (leg 1) + private_variance (leg 2) +
  residual_variance (leg 3)``; (3) THE REPARTITION / double-count fix — the SAME book run as a
  TOTAL VaR carries a STRICTLY POSITIVE idiosyncratic residual, while the unified run's residual is
  EXACTLY ZERO (both members are pure-private, so their variance lives in leg 2, never twice).

* ``test_per_family_predicate_isolation`` — the verifier's OD-3-F fold, end-to-end: a unified
  snapshot is REFUSED by both the plain and the total binder; a plain and a total snapshot are each
  REFUSED by the unified binder; and every family CONSUMES its own snapshot (no false refusal).
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from irp_shared.calc.models import RunStatus
from irp_shared.db.session import make_engine, make_session_factory
from irp_shared.entitlement.bootstrap import SYSTEM_TENANT_ID
from irp_shared.exposure import ExposureActor, run_exposure
from irp_shared.marketdata import (
    ProxyMappingActor,
    capture_proxy_mapping,
)
from irp_shared.marketdata.factor import (
    FactorActor,
    capture_factor,
    capture_factor_return,
    resolve_factor,
)
from irp_shared.models import Base
from irp_shared.perf import DesmoothedReturnActor, register_desmoothed_return_model
from irp_shared.perf.desmoothing_service import run_desmoothed_return
from irp_shared.portfolio import PortfolioActor, create_portfolio
from irp_shared.position import create_position
from irp_shared.position.service import PositionActor
from irp_shared.reference.instrument import create_instrument
from irp_shared.reference.models import Currency
from irp_shared.reference.service import ReferenceActor
from irp_shared.risk import (
    METRIC_TYPE_VAR_PARAMETRIC,
    METRIC_TYPE_VAR_PARAMETRIC_TOTAL,
    METRIC_TYPE_VAR_PARAMETRIC_UNIFIED,
    CovarianceActor,
    FactorExposureActor,
    ProxyWeightEstimateActor,
    PurePrivateCovarianceActor,
    PurePrivateFactorActor,
    VarActor,
    VarInputError,
    latest_var_for_portfolio,
    promote_proxy_weight_estimate,
    register_covariance_model,
    register_factor_exposure_model,
    register_private_covariance_model,
    register_proxy_weight_regression_model,
    register_pure_private_factor_model,
    register_var_model,
    register_var_parametric_total_model,
    register_var_parametric_unified_model,
    run_covariance,
    run_factor_exposure,
    run_private_covariance,
    run_proxy_weight_estimate,
    run_pure_private_factor_return,
    run_var,
    run_var_unified,
)
from irp_shared.snapshot import (
    SnapshotActor,
    build_var_snapshot,
    build_var_total_snapshot,
    build_var_unified_snapshot,
)
from irp_shared.valuation import create_valuation
from irp_shared.valuation.service import ValuationActor

_T0 = datetime(2024, 6, 1, tzinfo=UTC)
_MARK_DATES = (
    date(2024, 9, 30),
    date(2024, 12, 31),
    date(2025, 3, 31),
    date(2025, 6, 30),
    date(2025, 9, 30),
    date(2025, 12, 31),
)
# Two DIFFERENT NAV series => two DIFFERENT pure-private series over the SAME grid (a non-degenerate
# Ω_pp; the same {FX} blend is subtracted from each). Both strictly positive (desmoothing needs it).
_MARK_A = ("100.00", "103.00", "104.50", "108.00", "106.00", "111.00")
_MARK_B = ("100.00", "101.50", "103.00", "102.00", "105.00", "107.50")
_WINDOW = (date(2024, 6, 1), date(2026, 1, 1))
_W_USD, _W_EUR = Decimal("0.6"), Decimal("0.3")  # the promoted blend weights (both funds)
# The shared public FX factor returns over ``_MARK_DATES[1:]`` (5 obs; not collinear).
_FX_USD_RET = ("0.010", "0.020", "-0.010", "0.030", "0.000")
_FX_EUR_RET = ("0.020", "-0.010", "0.010", "0.000", "0.020")
_VALID_AT = datetime(2025, 12, 31, 23, 59, tzinfo=UTC)  # picks the last (2025-12-31) mark
_KNOWN_AT = datetime(2030, 1, 1, tzinfo=UTC)
_VD = date(2025, 12, 31)
_APPRAISAL_DAYS = 91  # quarterly appraisal cadence (the Ω_pp de-scale)
_MAX_AGE = 400
_CONF = "0.95"


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
            Currency.__table__.select().where(
                Currency.tenant_id == SYSTEM_TENANT_ID, Currency.code == code
            )
        ).first()
        is None
    ):
        db.add(Currency(tenant_id=SYSTEM_TENANT_ID, code=code, name=code, valid_from=_T0))
        db.flush()


def _factor(db: Session, tenant: str, code: str, ccy: str, rets: tuple[str, ...]) -> str:
    """A currency-coded public factor (for the allocation exposure) with returns over
    ``_MARK_DATES[1:]`` (the shared public-covariance + REGRESSION grid)."""
    fid = capture_factor(
        db,
        factor_code=code,
        factor_source="VENDOR_F",
        factor_family="CURRENCY",
        currency_code=ccy,
        acting_tenant=tenant,
        actor=FactorActor(actor_id="s"),
        valid_from=_T0,
    ).id
    factor = resolve_factor(db, fid, acting_tenant=tenant)
    for d, v in zip(_MARK_DATES[1:], rets, strict=True):
        capture_factor_return(
            db,
            factor,
            return_date=d,
            return_value=Decimal(v),
            acting_tenant=tenant,
            actor=FactorActor(actor_id="s"),
            valid_from=_T0,
        )
    db.flush()
    return fid


def _fund(
    db: Session,
    tenant: str,
    pf: str,
    *,
    code: str,
    ccy: str,
    marks: tuple[str, ...],
    ppf_model: str,
    fx_usd: str,
    fx_eur: str,
) -> tuple[str, str]:
    """One PRIVATE_EQUITY fund in the shared book: instrument + position + NAV series, then the full
    PPF-1 chain (desmoothing run + promoted {FX_USD,FX_EUR} REGRESSION blend + MANUAL pure-private-
    segment membership + pure-private run). Returns (instrument_id, segment_factor_id)."""
    inst = create_instrument(
        db,
        tenant_id=tenant,
        code=f"{code}-{uuid.uuid4().hex[:6]}",
        name=code,
        asset_class="PRIVATE_EQUITY",
        actor=ReferenceActor(actor_id="s"),
    ).id
    create_position(
        db,
        portfolio_id=pf,
        instrument_id=inst,
        acting_tenant=tenant,
        actor=PositionActor(actor_id="s"),
        quantity=Decimal("1"),
        valid_from=_T0,
    )
    for d, v in zip(_MARK_DATES, marks, strict=True):
        create_valuation(
            db,
            portfolio_id=pf,
            instrument_id=inst,
            valuation_date=d,
            acting_tenant=tenant,
            actor=ValuationActor(actor_id="s"),
            mark_value=Decimal(v),
            currency_code=ccy,
            valid_from=_T0,
        )
    db.flush()
    dmodel = register_desmoothed_return_model(
        db, tenant_id=tenant, actor_id="s", code_version="v1", alpha="0.5"
    )
    dout = run_desmoothed_return(
        db,
        acting_tenant=tenant,
        actor=DesmoothedReturnActor(actor_id="a"),
        code_version="v1",
        environment_id="test",
        model_version_id=str(dmodel.id),
        portfolio_id=pf,
        instrument_id=inst,
        window_start=_WINDOW[0],
        window_end=_WINDOW[1],
    )
    assert dout.status == "COMPLETED", dout.failure_reason
    desmoothed_run = str(dout.run.run_id)
    est = run_proxy_weight_estimate(
        db,
        acting_tenant=tenant,
        actor=ProxyWeightEstimateActor(actor_id="a"),
        code_version="v1",
        environment_id="test",
        model_version_id=str(
            register_proxy_weight_regression_model(
                db, tenant_id=tenant, actor_id="s", code_version="v1", min_observations=4
            ).id
        ),
        desmoothed_run_id=desmoothed_run,
        factor_ids=[fx_usd, fx_eur],
    )
    assert est.status == "COMPLETED", est.failure_reason
    for fid, w in ((fx_usd, _W_USD), (fx_eur, _W_EUR)):
        promote_proxy_weight_estimate(
            db,
            private_instrument_id=inst,
            factor_id=fid,
            weight=w,
            acting_tenant=tenant,
            actor=ProxyMappingActor(actor_id="s"),
            source_calculation_run_id=str(est.run.run_id),
        )
    seg = capture_factor(
        db,
        factor_code=f"SEG-{uuid.uuid4().hex[:6]}",
        factor_source="PPF",
        factor_family="PRIVATE",
        frequency="APPRAISAL",
        acting_tenant=tenant,
        actor=FactorActor(actor_id="s"),
        valid_from=_T0,
    ).id
    capture_proxy_mapping(  # the MANUAL membership: this fund is a member of its pure-private seg
        db,
        private_instrument_id=inst,
        factor_id=seg,
        weight=Decimal("1"),
        acting_tenant=tenant,
        actor=ProxyMappingActor(actor_id="s"),
        valid_from=_T0,
    )
    pout = run_pure_private_factor_return(
        db,
        acting_tenant=tenant,
        actor=PurePrivateFactorActor(actor_id="a"),
        code_version="v1",
        environment_id="test",
        model_version_id=str(ppf_model),
        segment_factor_id=seg,
        member_desmoothed_run_ids=[desmoothed_run],
    )
    assert pout.status == "COMPLETED", pout.failure_reason
    return inst, str(seg)


class _Book:
    """The seeded two-fund unified book: the three provenance run ids + the portfolio id."""

    def __init__(
        self,
        *,
        exposure_run_id: str,
        covariance_run_id: str,
        private_covariance_run_id: str,
        portfolio_id: str,
    ) -> None:
        self.exposure_run_id = exposure_run_id
        self.covariance_run_id = covariance_run_id
        self.private_covariance_run_id = private_covariance_run_id
        self.portfolio_id = portfolio_id


def _seed_unified_book(db: Session, tenant: str) -> _Book:
    """One portfolio; two USD PRIVATE_EQUITY funds (distinct NAV series => distinct pure-private
    segments), each factor-exposed AND a pure-private-segment member; a public DAILY covariance over
    {FX_USD,FX_EUR}; an Ω_pp APPRAISAL block over the two segments. Returns the three run ids the
    unified binder consumes. (Both funds are USD so the repartition-proof TOTAL run is valid — PA-4
    v1's residual leg refuses a non-base series_currency, the no-FX limitation.)"""
    for code in ("USD", "EUR"):
        _currency(db, code)
    pf = create_portfolio(
        db,
        tenant_id=tenant,
        code=f"ACCT-{uuid.uuid4().hex[:6]}",
        name="two-fund book",
        node_type="ACCOUNT",
        actor=PortfolioActor(actor_id="s"),
    ).id
    fx_usd = _factor(db, tenant, f"FX_USD-{uuid.uuid4().hex[:4]}", "USD", _FX_USD_RET)
    fx_eur = _factor(db, tenant, f"FX_EUR-{uuid.uuid4().hex[:4]}", "EUR", _FX_EUR_RET)
    ppf = str(
        register_pure_private_factor_model(
            db, tenant_id=tenant, actor_id="s", code_version="v1", min_members=1
        ).id
    )
    _inst_a, seg_a = _fund(
        db,
        tenant,
        pf,
        code="FUND-A",
        ccy="USD",
        marks=_MARK_A,
        ppf_model=ppf,
        fx_usd=fx_usd,
        fx_eur=fx_eur,
    )
    _inst_b, seg_b = _fund(
        db,
        tenant,
        pf,
        code="FUND-B",
        ccy="USD",
        marks=_MARK_B,
        ppf_model=ppf,
        fx_usd=fx_usd,
        fx_eur=fx_eur,
    )
    exposure = run_exposure(
        db,
        acting_tenant=tenant,
        actor=ExposureActor(actor_id="a"),
        code_version="v1",
        environment_id="ci",
        portfolio_id=pf,
        as_of_valid_at=_VALID_AT,
        as_of_known_at=_KNOWN_AT,
        base_currency="USD",
    )
    assert exposure.status == RunStatus.COMPLETED.value, exposure.failure_reason
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
        factor_ids=[fx_usd, fx_eur],
    )
    assert fx_run.status == RunStatus.COMPLETED.value, fx_run.failure_reason
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
        factor_ids=[fx_usd, fx_eur],
        as_of_valid_at=_VALID_AT,
    )
    assert cov_run.status == RunStatus.COMPLETED.value, cov_run.failure_reason
    priv_mv = register_private_covariance_model(
        db, tenant_id=tenant, actor_id="s", code_version="v1", window_observations=4
    )
    omega = run_private_covariance(
        db,
        acting_tenant=tenant,
        actor=PurePrivateCovarianceActor(actor_id="a"),
        code_version="v1",
        environment_id="test",
        model_version_id=str(priv_mv.id),
        segment_factor_ids=[seg_a, seg_b],
    )
    assert omega.status == "COMPLETED", omega.failure_reason
    return _Book(
        exposure_run_id=str(fx_run.run.run_id),
        covariance_run_id=str(cov_run.run.run_id),
        private_covariance_run_id=str(omega.run.run_id),
        portfolio_id=str(pf),
    )


def _unified_model(db: Session, tenant: str) -> str:
    return str(
        register_var_parametric_unified_model(
            db,
            tenant_id=tenant,
            actor_id="s",
            code_version="risk-v1",
            confidence_level=_CONF,
            appraisal_days=_APPRAISAL_DAYS,
            max_estimate_age_days=_MAX_AGE,
        ).id
    )


def _plain_model(db: Session, tenant: str) -> str:
    return str(
        register_var_model(
            db, tenant_id=tenant, actor_id="s", code_version="risk-v1", confidence_level=_CONF
        ).id
    )


def _total_model(db: Session, tenant: str) -> str:
    return str(
        register_var_parametric_total_model(
            db,
            tenant_id=tenant,
            actor_id="s",
            code_version="risk-v1",
            confidence_level=_CONF,
            appraisal_days=_APPRAISAL_DAYS,
            max_estimate_age_days=_MAX_AGE,
        ).id
    )


def test_unified_assembles_three_legs_and_repartitions(session: Session) -> None:
    tenant = str(uuid.uuid4())
    book = _seed_unified_book(session, tenant)

    # (1) The unified run COMPLETES and persists the pure-private block + its provenance.
    unified = run_var_unified(
        session,
        acting_tenant=tenant,
        actor=VarActor(actor_id="analyst"),
        code_version="risk-v1",
        environment_id="ci",
        model_version_id=_unified_model(session, tenant),
        exposure_run_id=book.exposure_run_id,
        covariance_run_id=book.covariance_run_id,
        private_covariance_run_id=book.private_covariance_run_id,
    )
    assert unified.status == RunStatus.COMPLETED.value, unified.failure_reason
    assert len(unified.rows) == 1
    urow = unified.rows[0]
    assert urow.metric_type == METRIC_TYPE_VAR_PARAMETRIC_UNIFIED
    assert urow.base_currency == "USD"
    assert urow.covariance_run_id == book.covariance_run_id  # the PUBLIC Σ provenance
    assert urow.private_covariance_run_id == book.private_covariance_run_id  # the Ω_pp provenance
    assert urow.private_variance is not None and urow.private_variance > 0  # leg 2 is REAL
    # (3) THE REPARTITION: both members are pure-private, so leg 3 (the idiosyncratic residual over
    # NON-private members) is EXACTLY zero — their variance moved to leg 2, never double-counted.
    assert urow.residual_variance == Decimal(0)

    # Rule-7 in-slice read: the flagship "latest unified VaR for portfolio P" resolves the new
    # metric through the SHARED generic resolver (unified is a metric_type on var_result +
    # run_type=VAR, scope stamped from the pinned exposure run — the OD-3 isolation payoff, so no
    # new read function is minted).
    latest = latest_var_for_portfolio(
        session,
        acting_tenant=tenant,
        portfolio_id=book.portfolio_id,
        metric_type=METRIC_TYPE_VAR_PARAMETRIC_UNIFIED,
    )
    assert len(latest) == 1 and latest[0].id == urow.id

    # (2) leg 1 — an INDEPENDENT plain VaR over the SAME exposure+covariance pins. The unified
    # factor leg IS the plain radicand (identical pins => identical σ²), so it reconciles.
    plain = run_var(
        session,
        acting_tenant=tenant,
        actor=VarActor(actor_id="analyst"),
        code_version="risk-v1",
        environment_id="ci",
        model_version_id=_plain_model(session, tenant),
        exposure_run_id=book.exposure_run_id,
        covariance_run_id=book.covariance_run_id,
    )
    assert plain.status == RunStatus.COMPLETED.value, plain.failure_reason
    prow = plain.rows[0]
    assert prow.metric_type == METRIC_TYPE_VAR_PARAMETRIC
    # sigma_unified**2 == plain_sigma**2 (leg 1) + private_variance (leg 2) + residual (leg 3).
    # A modest tolerance absorbs the 6dp σ persistence rounding (the kernel tests own exact
    # precision; this is the end-to-end LEG-ASSEMBLY identity).
    lhs = float(urow.sigma) ** 2
    rhs = float(prow.sigma) ** 2 + float(urow.private_variance) + float(urow.residual_variance)
    assert lhs == pytest.approx(rhs, rel=1e-6)
    assert urow.sigma > prow.sigma  # the pure-private block STRICTLY adds risk

    # (3) cont. — the SAME book as a TOTAL VaR: the two funds' REGRESSION residuals land in leg 3,
    # so the total residual is STRICTLY POSITIVE. The unified run repartitioned exactly that mass
    # into leg 2 (residual 0 above) — the double-count the verifier caught, provably closed.
    total = run_var(
        session,
        acting_tenant=tenant,
        actor=VarActor(actor_id="analyst"),
        code_version="risk-v1",
        environment_id="ci",
        model_version_id=_total_model(session, tenant),
        exposure_run_id=book.exposure_run_id,
        covariance_run_id=book.covariance_run_id,
    )
    assert total.status == RunStatus.COMPLETED.value, total.failure_reason
    trow = total.rows[0]
    assert trow.metric_type == METRIC_TYPE_VAR_PARAMETRIC_TOTAL
    assert trow.residual_variance > 0  # total counts the private residual in leg 3...
    assert urow.residual_variance < trow.residual_variance  # ...unified does NOT (it's in leg 2)


def test_per_family_predicate_isolation(session: Session) -> None:
    tenant = str(uuid.uuid4())
    book = _seed_unified_book(session, tenant)
    actor = SnapshotActor(actor_id="analyst")

    unified_snap = build_var_unified_snapshot(
        session,
        acting_tenant=tenant,
        actor=actor,
        exposure_run_id=book.exposure_run_id,
        covariance_run_id=book.covariance_run_id,
        private_covariance_run_id=book.private_covariance_run_id,
    )
    plain_snap = build_var_snapshot(
        session,
        acting_tenant=tenant,
        actor=actor,
        exposure_run_id=book.exposure_run_id,
        covariance_run_id=book.covariance_run_id,
    )
    total_snap = build_var_total_snapshot(
        session,
        acting_tenant=tenant,
        actor=actor,
        exposure_run_id=book.exposure_run_id,
        covariance_run_id=book.covariance_run_id,
    )

    plain_mv = _plain_model(session, tenant)
    total_mv = _total_model(session, tenant)
    unified_mv = _unified_model(session, tenant)

    def _run(model_version_id: str, snapshot_id: str, *, unified: bool):  # noqa: ANN202
        fn = run_var_unified if unified else run_var
        return fn(
            session,
            acting_tenant=tenant,
            actor=VarActor(actor_id="analyst"),
            code_version="risk-v1",
            environment_id="ci",
            model_version_id=model_version_id,
            snapshot_id=snapshot_id,
        )

    # A UNIFIED snapshot pins the pure-private block: the plain AND total binders MUST refuse it
    # (they would silently drop legs 2/3 — the OD-3-F hole the verifier caught).
    with pytest.raises(VarInputError):
        _run(plain_mv, unified_snap.id, unified=False)
    with pytest.raises(VarInputError):
        _run(total_mv, unified_snap.id, unified=False)
    # A plain OR total snapshot pins NO pure-private block: the unified binder MUST refuse it.
    with pytest.raises(VarInputError):
        _run(unified_mv, plain_snap.id, unified=True)
    with pytest.raises(VarInputError):
        _run(unified_mv, total_snap.id, unified=True)

    # ...and every family CONSUMES its OWN snapshot (the refusals above are not blanket).
    assert _run(unified_mv, unified_snap.id, unified=True).status == RunStatus.COMPLETED.value
    assert _run(plain_mv, plain_snap.id, unified=False).status == RunStatus.COMPLETED.value
    assert _run(total_mv, total_snap.id, unified=False).status == RunStatus.COMPLETED.value
