"""MG-1 OD-H ride-along: the estimate-seam integration test — ONE test chaining the REAL
private-asset leg into a REAL total-v2 VaR consume with NO hand-minted estimation row anywhere.

RETIRES the Wave-5 close finding that "the 14-number chain is demonstrated in two halves that
meet at a hand-minted seam": every prior total-VaR test obtains its ``ESTIMATION_SUMMARY`` from
``_mint_estimation_summary`` (a hand-fixed ``residual_stdev`` written directly to the results
table, bypassing the OLS), so the PA-0→PA-1→PA-3 half and the PA-4 half had never met as one
chain. Here the chain is real end to end: quarterly appraisal marks (``create_valuation``) → a
real desmoothing run (PA-1) → a real PA-3 OLS estimate over the desmoothed series + captured
candidate factor returns → ``promote_proxy_weight_estimate`` → a governed total-v2 VaR
build-in-request (``run_var`` → ``build_var_total_snapshot``) — and the decomposition is asserted
against the RUN'S OWN σ_e: ``residual_variance = (MV · σ_e_daily)²`` is recomputed independently
from the ``ESTIMATION_SUMMARY`` row the OLS actually produced (read back from the DB), never from
a hand-fixed constant.

MG-1 census constraints exercised on the way through: the estimate's regression span end vs the
covariance ``window_end`` inside the declared ``max_estimate_age_days`` (the BT-2 staleness gate;
the ``estimate_age_days`` echo is asserted EXACTLY); the proxied instrument's ``series_currency``
== the book's ``base_currency`` (USD appraisals, USD book); the declared ``appraisal_days`` (91)
consistent with the real quarterly appraisal cadence of the marks. Fixture realism per TD-1: a
buyout-fund position appraised quarterly, small FX factor returns, a public bond alongside.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal, localcontext

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from irp_shared.db.session import make_engine, make_session_factory
from irp_shared.entitlement.bootstrap import SYSTEM_TENANT_ID
from irp_shared.exposure import ExposureActor, run_exposure
from irp_shared.marketdata import (
    MAPPING_METHOD_REGRESSION,
    FactorActor,
    FxRateActor,
    ProxyMappingActor,
    capture_factor,
    capture_factor_return,
    capture_fx_rate,
    resolve_factor,
)
from irp_shared.models import Base
from irp_shared.perf import (
    DesmoothedReturnActor,
    register_desmoothed_return_model,
    run_desmoothed_return,
)
from irp_shared.portfolio import PortfolioActor, create_portfolio
from irp_shared.position import create_position
from irp_shared.position.service import PositionActor
from irp_shared.reference.instrument import create_instrument
from irp_shared.reference.models import Currency
from irp_shared.reference.service import ReferenceActor
from irp_shared.risk import (
    METRIC_TYPE_ESTIMATION_SUMMARY,
    METRIC_TYPE_VAR_PARAMETRIC_TOTAL,
    METRIC_TYPE_WEIGHT,
    CovarianceActor,
    FactorExposureActor,
    ProxyWeightEstimateActor,
    ProxyWeightEstimateResult,
    VarActor,
    compute_parametric_var,
    promote_proxy_weight_estimate,
    register_covariance_model,
    register_factor_exposure_model,
    register_proxy_weight_regression_model,
    register_var_model,
    register_var_parametric_total_model,
    run_covariance,
    run_factor_exposure,
    run_proxy_weight_estimate,
    run_var,
)
from irp_shared.snapshot import COMPONENT_KIND_PROXY_WEIGHT, list_components
from irp_shared.valuation import create_valuation
from irp_shared.valuation.service import ValuationActor

T0 = datetime(2024, 6, 1, tzinfo=UTC)  # book inception — before the first appraisal
VALID_AT = datetime(2026, 6, 1, tzinfo=UTC)
KNOWN_AT = datetime(2030, 1, 1, tzinfo=UTC)
VD = date(2026, 6, 1)  # the VaR-side valuation date
# Six quarterly appraisal marks => five observed returns => four desmoothed periods (PA-1).
MARK_DATES = (
    date(2024, 9, 30),
    date(2024, 12, 31),
    date(2025, 3, 31),
    date(2025, 6, 30),
    date(2025, 9, 30),
    date(2025, 12, 31),
)
MARK_VALUES = ("100.00", "103.00", "104.50", "108.00", "106.00", "111.00")
DESMOOTH_WINDOW = (date(2024, 6, 1), date(2026, 1, 1))
# Quarterly candidate-factor returns, one per appraisal period end (each period compounds a
# single value — the test_proxy_weight pattern); plausible quarterly FX-factor magnitudes.
QUARTERLY_FX_USD = ("0.012", "0.018", "-0.008", "0.026", "0.004")
QUARTERLY_FX_EUR = ("0.020", "-0.011", "0.009", "0.002", "0.016")
# Daily factor returns for the covariance window (the four most recent COMMON dates — the
# quarterly OLS observations above sit earlier on the same series and stay out of the window).
COV_DATES = (date(2026, 5, 26), date(2026, 5, 27), date(2026, 5, 28), date(2026, 5, 29))
DAILY_FX_USD = ("0.0012", "-0.0008", "0.0005", "-0.0010")
DAILY_FX_EUR = ("-0.0009", "0.0011", "-0.0004", "0.0007")
APPRAISAL_DAYS = 91  # declared on the total model; consistent with the real quarterly marks
MAX_ESTIMATE_AGE_DAYS = 400  # the BT-2 declared staleness policy (quarterly-appraisal plausible)


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


def _factor(db: Session, tenant: str, code: str, ccy: str) -> str:
    return capture_factor(
        db,
        factor_code=code,
        factor_source="VENDOR_F",
        factor_family="CURRENCY",
        currency_code=ccy,
        acting_tenant=tenant,
        actor=FactorActor(actor_id="s"),
        valid_from=T0,
    ).id


def _returns(db: Session, tenant: str, factor_id: str, dated: list[tuple[date, str]]) -> None:
    factor = resolve_factor(db, factor_id, acting_tenant=tenant)
    for d, v in dated:
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


def test_real_estimate_chain_total_var_decomposition(session: Session) -> None:
    tenant = str(uuid.uuid4())
    for ccy in ("USD", "EUR"):
        _currency(session, ccy)

    # --- The book: a quarterly-appraised buyout fund (the private leg) + a public EUR bond. ---
    pf = create_portfolio(
        session,
        tenant_id=tenant,
        code=f"ACCT-{uuid.uuid4().hex[:6]}",
        name="mixed book",
        node_type="ACCOUNT",
        actor=PortfolioActor(actor_id="s"),
    ).id
    fund = create_instrument(
        session,
        tenant_id=tenant,
        code=f"FUND-{uuid.uuid4().hex[:6]}",
        name="Buyout Fund",
        asset_class="PRIVATE_EQUITY",
        actor=ReferenceActor(actor_id="s"),
    ).id
    bond = create_instrument(
        session,
        tenant_id=tenant,
        code=f"BOND-{uuid.uuid4().hex[:6]}",
        name="EUR bond",
        asset_class="BOND",
        actor=ReferenceActor(actor_id="s"),
    ).id
    for inst, qty in ((fund, "100"), (bond, "100")):
        create_position(
            session,
            portfolio_id=pf,
            instrument_id=inst,
            acting_tenant=tenant,
            actor=PositionActor(actor_id="s"),
            quantity=Decimal(qty),
            valid_from=T0,
        )
    # REAL appraisal marks — the smoothed NAV series the whole private leg hangs off.
    for d, v in zip(MARK_DATES, MARK_VALUES, strict=True):
        create_valuation(
            session,
            portfolio_id=pf,
            instrument_id=fund,
            valuation_date=d,
            acting_tenant=tenant,
            actor=ValuationActor(actor_id="s"),
            mark_value=Decimal(v),
            currency_code="USD",
        )
    session.flush()

    # --- PA-1: the real desmoothing run over the appraisal series. ---
    desmooth_model = register_desmoothed_return_model(
        session, tenant_id=tenant, actor_id="s", code_version="v1", alpha="0.5"
    )
    desmoothed = run_desmoothed_return(
        session,
        acting_tenant=tenant,
        actor=DesmoothedReturnActor(actor_id="a"),
        code_version="v1",
        environment_id="ci",
        model_version_id=str(desmooth_model.id),
        portfolio_id=pf,
        instrument_id=fund,
        window_start=DESMOOTH_WINDOW[0],
        window_end=DESMOOTH_WINDOW[1],
    )
    assert desmoothed.status == "COMPLETED"

    # --- PA-3: the real OLS estimate over the desmoothed series + candidate factor returns. ---
    fx_usd = _factor(session, tenant, "FX_USD", "USD")
    fx_eur = _factor(session, tenant, "FX_EUR", "EUR")
    _returns(session, tenant, fx_usd, list(zip(MARK_DATES[1:], QUARTERLY_FX_USD, strict=True)))
    _returns(session, tenant, fx_eur, list(zip(MARK_DATES[1:], QUARTERLY_FX_EUR, strict=True)))
    proxy_model = register_proxy_weight_regression_model(
        session, tenant_id=tenant, actor_id="s", code_version="v1", min_observations=4
    )
    estimate = run_proxy_weight_estimate(
        session,
        acting_tenant=tenant,
        actor=ProxyWeightEstimateActor(actor_id="a"),
        code_version="v1",
        environment_id="ci",
        model_version_id=str(proxy_model.id),
        desmoothed_run_id=str(desmoothed.run.run_id),
        factor_ids=[fx_usd, fx_eur],
    )
    assert estimate.status == "COMPLETED"
    est_run_id = str(estimate.run.run_id)

    # The estimate row the OLS ACTUALLY produced — read back from the DB. Its residual_stdev is
    # THE σ_e of this test; nothing below re-declares it.
    est_row = session.execute(
        select(ProxyWeightEstimateResult).where(
            ProxyWeightEstimateResult.calculation_run_id == est_run_id,
            ProxyWeightEstimateResult.metric_type == METRIC_TYPE_ESTIMATION_SUMMARY,
        )
    ).scalar_one()
    assert est_row.residual_stdev is not None and est_row.residual_stdev > 0  # non-vacuous
    assert est_row.series_currency == "USD"  # == book base_currency (the census constraint)

    # --- Promote the estimated coefficient (analyst-mediated, the PA-3 loop-closer). ---
    weight_row = session.execute(
        select(ProxyWeightEstimateResult).where(
            ProxyWeightEstimateResult.calculation_run_id == est_run_id,
            ProxyWeightEstimateResult.metric_type == METRIC_TYPE_WEIGHT,
            ProxyWeightEstimateResult.factor_id == fx_usd.lower(),
        )
    ).scalar_one()
    promoted = promote_proxy_weight_estimate(
        session,
        private_instrument_id=fund,
        factor_id=fx_usd,
        weight=weight_row.metric_value,
        acting_tenant=tenant,
        actor=ProxyMappingActor(actor_id="analyst"),
        source_calculation_run_id=est_run_id,
    )
    assert promoted.mapping_method == MAPPING_METHOD_REGRESSION
    assert str(promoted.source_calculation_run_id) == est_run_id

    # --- The VaR-side upstream chain: current marks -> exposure -> factor exposure -> covariance.
    for inst, mark, ccy in ((fund, "112.00", "USD"), (bond, "400.00", "EUR")):
        create_valuation(
            session,
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
        session,
        base_currency="EUR",
        quote_currency="USD",
        rate_date=VD,
        rate=Decimal("1.100000000000"),
        acting_tenant=tenant,
        actor=FxRateActor(actor_id="s"),
        valid_from=T0,
    )
    exposure = run_exposure(
        session,
        acting_tenant=tenant,
        actor=ExposureActor(actor_id="a"),
        code_version="risk-v1",
        environment_id="ci",
        portfolio_id=pf,
        as_of_valid_at=VALID_AT,
        as_of_known_at=KNOWN_AT,
        base_currency="USD",
    )
    assert exposure.status == "COMPLETED"
    _returns(session, tenant, fx_usd, list(zip(COV_DATES, DAILY_FX_USD, strict=True)))
    _returns(session, tenant, fx_eur, list(zip(COV_DATES, DAILY_FX_EUR, strict=True)))
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
        factor_ids=[fx_usd, fx_eur],
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
        factor_ids=[fx_usd, fx_eur],
        as_of_valid_at=VALID_AT,
    )
    assert cov_run.status == "COMPLETED"

    # --- The total-v2 consume: run_var via build_var_total_snapshot (the governed build path). ---
    total_mv = register_var_parametric_total_model(
        session,
        tenant_id=tenant,
        actor_id="analyst",
        code_version="risk-v1",
        confidence_level="0.95",
        appraisal_days=APPRAISAL_DAYS,
        max_estimate_age_days=MAX_ESTIMATE_AGE_DAYS,
    ).id
    result = run_var(
        session,
        acting_tenant=tenant,
        actor=VarActor(actor_id="analyst"),
        code_version="risk-v1",
        environment_id="ci",
        model_version_id=total_mv,
        exposure_run_id=fx_run.run.run_id,
        covariance_run_id=cov_run.run.run_id,
    )
    assert result.status == "COMPLETED" and len(result.rows) == 1
    row = result.rows[0]
    assert row.metric_type == METRIC_TYPE_VAR_PARAMETRIC_TOTAL
    assert row.base_currency == "USD"

    # The seam itself: the snapshot pinned the very ESTIMATION_SUMMARY row the OLS wrote.
    comps = list_components(session, snapshot_id=row.input_snapshot_id, acting_tenant=tenant)
    pw_pins = [
        json.loads(c.captured_content)
        for c in comps
        if c.component_kind == COMPONENT_KIND_PROXY_WEIGHT
    ]
    assert len(pw_pins) == 1
    assert pw_pins[0]["id"] == str(est_row.id).lower()
    assert Decimal(pw_pins[0]["residual_stdev"]) == est_row.residual_stdev

    # Date alignment (the BT-2 staleness gate, exercised for real): the regression span end is the
    # last appraisal date; the covariance window_end is the last daily return date.
    expected_age = (COV_DATES[-1] - MARK_DATES[-1]).days
    assert row.window_end == COV_DATES[-1]
    assert row.estimate_age_days == expected_age
    assert 0 < expected_age <= MAX_ESTIMATE_AGE_DAYS

    # --- The decomposition, against the RUN's OWN σ_e (nothing hand-fixed). ---
    exposure_pins = [
        json.loads(c.captured_content) for c in comps if c.component_kind == "FACTOR_EXPOSURE"
    ]
    covariance_pins = {
        (p["factor_id_1"], p["factor_id_2"]): Decimal(p["covariance_value"])
        for p in (json.loads(c.captured_content) for c in comps if c.component_kind == "COVARIANCE")
    }
    fund_mv = sum(
        (
            Decimal(p["exposure_amount"])
            for p in exposure_pins
            if p["instrument_id"] == str(fund).lower()
        ),
        Decimal(0),
    )
    assert fund_mv == Decimal("11200.000000")  # 100 units x the 112.00 current mark
    with localcontext() as ctx:
        ctx.prec = 50  # the kernels' declared compute precision
        # residual_variance = (MV * sigma_e_daily)^2 with sigma_e_daily = sigma_e_period /
        # sqrt(appraisal_days * 252/365) — recomputed HERE from est_row.residual_stdev (the OLS's
        # own output), independent of the total_var_residual kernel.
        d_trading = Decimal(APPRAISAL_DAYS) * (Decimal(252) / Decimal(365))
        sigma_e_daily = est_row.residual_stdev / d_trading.sqrt()
        contribution = fund_mv * sigma_e_daily
        residual_raw = contribution * contribution
        # The factor leg, recomputed fresh from the pinned content (the binder's own radicand).
        plain_estimate = compute_parametric_var(
            [(p["factor_id"], Decimal(p["exposure_amount"])) for p in exposure_pins],
            covariance_pins,
            z_score=row.z_score,
        )
        factor_var_raw = plain_estimate.radicand if plain_estimate.radicand > 0 else Decimal(0)
        sigma_total_raw = (factor_var_raw + residual_raw).sqrt()
        expected_sigma = sigma_total_raw.quantize(Decimal("1E-6"))
        expected_var = (row.z_score * sigma_total_raw).quantize(Decimal("1E-6"))
        expected_residual = residual_raw.quantize(Decimal("1E-20"))
    assert residual_raw > 0  # a real, non-degenerate idiosyncratic leg
    assert row.residual_variance == expected_residual
    assert row.sigma == expected_sigma
    assert row.var_value == expected_var

    # Cross-family: the SAME upstream runs through the PLAIN family — the persisted-column
    # decomposition identity sigma_total^2 - residual_variance ≈ sigma_plain^2 (the derived
    # quantization bound from test_var_total's decomposition test).
    plain_mv = register_var_model(
        session,
        tenant_id=tenant,
        actor_id="analyst",
        code_version="risk-v1",
        confidence_level="0.95",
    ).id
    plain = run_var(
        session,
        acting_tenant=tenant,
        actor=VarActor(actor_id="analyst"),
        code_version="risk-v1",
        environment_id="ci",
        model_version_id=plain_mv,
        exposure_run_id=fx_run.run.run_id,
        covariance_run_id=cov_run.run.run_id,
    )
    assert plain.status == "COMPLETED"
    bound = (row.sigma + plain.rows[0].sigma) * Decimal("1E-6") + Decimal("1E-12")
    decomposed = row.sigma * row.sigma - row.residual_variance
    assert abs(decomposed - plain.rows[0].sigma * plain.rows[0].sigma) <= bound
