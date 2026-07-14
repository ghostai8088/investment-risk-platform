"""SQLite-local unit/behavior tests for PA-4 total parametric VaR (factor variance + the
idiosyncratic residual variance of proxied instruments — ENT-027's total-family realization, the
13th governed number). RLS/append-only legs live in ``test_var_total_pg.py``.

Covers: the exact hand-reference total sigma/VaR/residual_variance THROUGH the full governed
build-in-request path (a proxied instrument's REGRESSION mapping citing a completed proxy-weight
estimate); the DECOMPOSITION identity ``sigma_total^2 - residual_variance == plain sigma^2`` on
the SAME factor pins; the plain-family INVARIANCE (no proxied instrument => total ≡ parametric,
byte-exact); the ONE-binder-dispatches-on-bound-model precedent (register EITHER family, run
through the SAME ``run_var``); the symmetric binding-predicate refusal (both directions); the
snapshot-build-time citation adjudication (missing/ambiguous/wrong-instrument cited estimation
run); the service-level adjudication (wrong-type PROXY_WEIGHT pin, instrument mismatch, currency
mismatch, duplicate pin) via hand-minted snapshots; a MANUAL-only mapping carries zero
idiosyncratic risk; TR-09 (a later re-promotion does not move an already-pinned estimate); and
no-orphan on every refusal.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest
from run_assertions import assert_no_running_orphan
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from irp_shared.calc.models import CalculationRun, RunStatus
from irp_shared.calc.service import create_run, update_run_status
from irp_shared.db.session import make_engine, make_session_factory
from irp_shared.entitlement.bootstrap import SYSTEM_TENANT_ID
from irp_shared.exposure import ExposureActor, run_exposure
from irp_shared.marketdata import (
    MAPPING_METHOD_MANUAL,
    FxRateActor,
    ProxyMappingActor,
    capture_fx_rate,
    capture_proxy_mapping,
)
from irp_shared.marketdata.factor import (
    FactorActor,
    capture_factor,
    capture_factor_return,
    resolve_factor,
)
from irp_shared.models import Base
from irp_shared.portfolio import PortfolioActor, create_portfolio
from irp_shared.position import create_position
from irp_shared.position.service import PositionActor
from irp_shared.reference.instrument import create_instrument
from irp_shared.reference.models import Currency
from irp_shared.reference.service import ReferenceActor
from irp_shared.risk import (
    METRIC_TYPE_ESTIMATION_SUMMARY,
    METRIC_TYPE_VAR_PARAMETRIC,
    METRIC_TYPE_VAR_PARAMETRIC_TOTAL,
    RUN_TYPE_PROXY_WEIGHT_ESTIMATE,
    VAR_TOTAL_METHODOLOGY_REF,
    CovarianceActor,
    FactorExposureActor,
    ProxyWeightEstimateResult,
    VarActor,
    VarInputError,
    VarResult,
    WrongModelVersionError,
    declared_appraisal_days,
    promote_proxy_weight_estimate,
    register_covariance_model,
    register_factor_exposure_model,
    register_var_model,
    register_var_parametric_total_model,
    run_covariance,
    run_factor_exposure,
    run_var,
)
from irp_shared.snapshot import (
    COMPONENT_KIND_PROXY_MAPPING,
    COMPONENT_KIND_PROXY_WEIGHT,
    VAR_BINDING_PREDICATE,
    VAR_TOTAL_BINDING_PREDICATE,
    SnapshotActor,
    VarTotalSnapshotError,
    build_snapshot,
    build_var_snapshot,
    build_var_total_snapshot,
    list_components,
    verify_snapshot,
)
from irp_shared.valuation import create_valuation
from irp_shared.valuation.service import ValuationActor

T0 = datetime(2026, 1, 1, tzinfo=UTC)
VALID_AT = datetime(2026, 6, 1, tzinfo=UTC)
KNOWN_AT = datetime(2030, 1, 1, tzinfo=UTC)
VD = date(2026, 6, 1)
D1, D2, D3, D4 = (date(2026, 5, 26), date(2026, 5, 27), date(2026, 5, 28), date(2026, 5, 29))
ACTOR = VarActor(actor_id="analyst")
Z95 = Decimal("1.644853626951")
APPRAISAL_DAYS = 91  # quarterly
RESIDUAL_STDEV = Decimal("0.04")  # 4%/quarter

#: HAND REFERENCE (independently derived, PA-4): I-USD's total pinned factor exposure MV=30000
#: (the 3-4-5 REF1 book, ``test_var.py`` twin: factor_var=250000, plain sigma=500 EXACTLY),
#: proxied with residual_stdev_period=0.04 (quarterly), appraisal_days=91 =>
#: d_trading = 91*(252/365) = 62.8273972602739726027397260273972602739726027397260;
#: sigma_e_daily = 0.04/sqrt(d_trading) = 0.0050464439851412522876...;
#: residual_variance = (30000*sigma_e_daily)^2 = 22919.9372056514913657770801...
#: sigma_total = sqrt(250000 + residual_variance) = 522.4173974176659...
REF_RESIDUAL_VARIANCE = Decimal("22919.93720565149136577708")
REF_SIGMA_TOTAL = Decimal("522.417397")
REF_VAR95_TOTAL = Decimal("859.300151")
REF_SIGMA_PLAIN = Decimal("500.000000")


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


def _seed_upstream_runs(db: Session, tenant: str) -> tuple[str, str, str, dict[str, str]]:
    """The ``test_var.py`` REF1 book (3-4-5 triangle: x=(30000 USD-factor, 40000 EUR-factor),
    factor_var=250000 EXACTLY), extended to return the portfolio + instrument ids (PA-4 needs the
    instrument id to proxy-map). Returns (fx_run_id, cov_run_id, portfolio_id,
    {code: instrument_id})."""
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
    instrument_ids: dict[str, str] = {}
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
        instrument_ids[code] = inst
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
    assert fx_run.status == RunStatus.COMPLETED.value and len(fx_run.rows) == 2

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
    assert cov_run.status == RunStatus.COMPLETED.value and len(cov_run.rows) == 3
    return fx_run.run.run_id, cov_run.run.run_id, pf, instrument_ids


def _mint_estimation_summary(
    db: Session,
    tenant: str,
    *,
    portfolio_id: str,
    instrument_id: str,
    residual_stdev: Decimal | None,
    series_currency: str = "USD",
    any_other_run_id: str,
) -> str:
    """Directly persist a COMPLETED ``PROXY_WEIGHT_ESTIMATE`` run + its ``ESTIMATION_SUMMARY`` row
    (bypassing the full OLS regression chain — PA-4 needs a KNOWN, controlled ``residual_stdev``
    for the golden/precision tests, the ``test_var.py`` ``_mint_var_snapshot`` precedent applied
    to a governed RESULT row rather than a hand-minted snapshot). Every FK target is a REAL row
    (``input_snapshot_id`` a real dataset_snapshot; ``model_version_id`` a real proxy-weight
    model_version; ``source_desmoothed_run_id`` reuses ``any_other_run_id`` — the FK only requires
    an EXISTING ``calculation_run`` row, not a specific ``run_type``) so the fixture is PG-portable
    (FK-enforced) as well as SQLite-safe."""
    from irp_shared.risk.bootstrap import register_proxy_weight_regression_model
    from irp_shared.snapshot.models import PURPOSE_TEST

    snap = build_snapshot(
        db,
        acting_tenant=tenant,
        actor=SnapshotActor(actor_id="a"),
        purpose=PURPOSE_TEST,
        portfolio_id=portfolio_id,
        as_of_valid_at=VALID_AT,
        as_of_known_at=KNOWN_AT,
        as_of_valuation_date=VD,
    )
    mv = register_proxy_weight_regression_model(
        db, tenant_id=tenant, actor_id="a", code_version="risk-v1", min_observations=4
    )
    run = create_run(
        db,
        tenant_id=tenant,
        run_type=RUN_TYPE_PROXY_WEIGHT_ESTIMATE,
        initiated_by="analyst",
        input_snapshot_id=snap.id,
        model_version_id=mv.id,
        code_version="risk-v1",
        environment_id="ci",
    )
    update_run_status(db, run, RunStatus.RUNNING, actor_id="analyst")
    row = ProxyWeightEstimateResult(
        tenant_id=tenant,
        calculation_run_id=run.run_id,
        input_snapshot_id=snap.id,
        model_version_id=mv.id,
        portfolio_id=portfolio_id,
        instrument_id=instrument_id,
        source_desmoothed_run_id=any_other_run_id,
        metric_type=METRIC_TYPE_ESTIMATION_SUMMARY,
        factor_id=None,
        metric_value=Decimal("0.8"),
        std_error=None,
        n_observations=6,
        n_regressors=1,
        residual_stdev=residual_stdev,
        min_observations=4,
        series_currency=series_currency,
    )
    db.add(row)
    db.flush()
    update_run_status(db, run, RunStatus.COMPLETED, actor_id="analyst")
    return run.run_id


def _mint_empty_completed_estimate_run(db: Session, tenant: str) -> str:
    """A REAL, COMPLETED ``PROXY_WEIGHT_ESTIMATE`` run with NO result rows at all (satisfies
    ``promote_proxy_weight_estimate``'s run-visibility gate; models the "missing" ESTIMATION_
    SUMMARY class for ``build_var_total_snapshot`` — collapsed with "non-COMPLETED" since a
    non-COMPLETED run also has zero visible rows by construction)."""
    run = create_run(
        db,
        tenant_id=tenant,
        run_type=RUN_TYPE_PROXY_WEIGHT_ESTIMATE,
        initiated_by="analyst",
        code_version="risk-v1",
        environment_id="ci",
    )
    update_run_status(db, run, RunStatus.RUNNING, actor_id="analyst")
    update_run_status(db, run, RunStatus.COMPLETED, actor_id="analyst")
    return run.run_id


def _promote(
    db: Session, tenant: str, *, instrument_id: str, factor_id: str, source_run_id: str
) -> None:
    promote_proxy_weight_estimate(
        db,
        private_instrument_id=instrument_id,
        factor_id=factor_id,
        weight=Decimal("0.500000000000"),
        acting_tenant=tenant,
        actor=ProxyMappingActor(actor_id="analyst"),
        source_calculation_run_id=source_run_id,
    )


def _var_total_model(
    db: Session,
    tenant: str,
    *,
    code_version: str = "risk-v1",
    confidence: str = "0.95",
    appraisal_days: int = APPRAISAL_DAYS,
) -> str:
    return register_var_parametric_total_model(
        db,
        tenant_id=tenant,
        actor_id="analyst",
        code_version=code_version,
        confidence_level=confidence,
        appraisal_days=appraisal_days,
    ).id


def _run_total(
    db: Session,
    tenant: str,
    mv: str,
    exposure_run_id: str | None,
    covariance_run_id: str | None,
    **kw,
):  # noqa: ANN202
    return run_var(
        db,
        acting_tenant=tenant,
        actor=ACTOR,
        code_version="risk-v1",
        environment_id="ci",
        model_version_id=mv,
        exposure_run_id=exposure_run_id,
        covariance_run_id=covariance_run_id,
        **kw,
    )


def _count_var_runs(db: Session, tenant: str) -> int:
    return db.execute(
        select(func.count())
        .select_from(CalculationRun)
        .where(CalculationRun.tenant_id == tenant, CalculationRun.run_type == "VAR")
    ).scalar_one()


# ---------- (1) the exact hand-reference total VaR, through the governed consume path ----------


def test_full_stack_exact_hand_reference_via_consume_path(session: Session) -> None:
    """The exact REF1 3-4-5 triangle (x=(30000, 40000) over uncorrelated 1E-4-variance factors —
    the ``test_var.py`` hand reference) PLUS ONE proxied instrument (I-USD, MV=30000) with a
    KNOWN residual_stdev — through the governed CONSUME-EXISTING path (a hand-minted total-
    predicate snapshot; the ``test_var.py``
    ``test_full_stack_exact_hand_reference_via_consume_path`` precedent). The pinned provenance
    run ids MUST be REAL own-tenant COMPLETED runs (re-resolved before they reach hard-FK
    columns) — the exposure/covariance/proxy CONTENT is hand-picked."""
    tenant = str(uuid.uuid4())
    fx_run, cov_run, _pf, insts = _seed_upstream_runs(session, tenant)
    iid_usd, iid_eur = insts["I-USD"], insts["I-EUR"]
    fa, fb = str(uuid.uuid4()).lower(), str(uuid.uuid4()).lower()
    exposure = [
        _exposure_content(fx_run, fa, "A", iid_usd, "30000.000000"),
        _exposure_content(fx_run, fb, "B", iid_eur, "40000.000000"),
    ]
    covariance = [
        _covariance_content(cov_run, fa, fa, "0.00010000000000000000"),
        _covariance_content(cov_run, fb, fb, "0.00010000000000000000"),
        _covariance_content(cov_run, fa, fb, "0E-20"),
    ]
    mapping = [_mapping_content(iid_usd, fa)]
    weight = [_weight_content(iid_usd, str(RESIDUAL_STDEV))]
    snap = _mint_total_snapshot(session, tenant, exposure, covariance, mapping, weight)

    mv = _var_total_model(session, tenant, appraisal_days=APPRAISAL_DAYS)
    result = _run_total(session, tenant, mv, None, None, snapshot_id=snap.id)
    assert result.status == RunStatus.COMPLETED.value and len(result.rows) == 1
    row = result.rows[0]
    assert row.metric_type == METRIC_TYPE_VAR_PARAMETRIC_TOTAL
    assert row.base_currency == "USD"
    assert row.confidence_level == Decimal("0.9500") and row.horizon_days == 1
    assert row.z_score == Z95
    assert row.residual_variance == REF_RESIDUAL_VARIANCE
    assert row.sigma == REF_SIGMA_TOTAL
    assert row.var_value == REF_VAR95_TOTAL
    assert row.exposure_run_id == fx_run and row.covariance_run_id == cov_run
    # NOTE: no verify_snapshot() here — the pinned content is HAND-PICKED (fake row ids), so
    # re-resolution reports drift by construction (the test_var.py precedent: the exact-reference
    # consume-path test does not call verify_snapshot either).


def test_full_stack_governed_build_path_decomposition(session: Session) -> None:
    """The REAL governed build path (``build_var_total_snapshot`` -> ``run_var``, real computed
    sample covariance — NOT hand-picked): the DECOMPOSITION identity
    ``sigma_total^2 - residual_variance == plain_sigma^2`` holds on WHATEVER factor variance the
    real upstream chain produces (it does not depend on clean numbers), cross-checked against an
    INDEPENDENT kernel recomputation from the pinned exposure content."""
    tenant = str(uuid.uuid4())
    fx_run, cov_run, pf, insts = _seed_upstream_runs(session, tenant)
    estimate_run = _mint_estimation_summary(
        session,
        tenant,
        portfolio_id=pf,
        instrument_id=insts["I-USD"],
        residual_stdev=RESIDUAL_STDEV,
        series_currency="USD",
        any_other_run_id=fx_run,
    )
    from irp_shared.marketdata.models import Factor

    any_factor = session.execute(select(Factor).where(Factor.tenant_id == tenant)).scalars().first()
    _promote(
        session,
        tenant,
        instrument_id=insts["I-USD"],
        factor_id=any_factor.id,
        source_run_id=estimate_run,
    )

    mv = _var_total_model(session, tenant)
    result = _run_total(session, tenant, mv, fx_run, cov_run)
    assert result.status == RunStatus.COMPLETED.value and len(result.rows) == 1
    row = result.rows[0]
    assert row.metric_type == METRIC_TYPE_VAR_PARAMETRIC_TOTAL
    assert row.residual_variance is not None and row.residual_variance > 0

    plain_mv = register_var_model(
        session,
        tenant_id=tenant,
        actor_id="analyst",
        code_version="risk-v1",
        confidence_level="0.95",
    ).id
    plain = _run_total(session, tenant, plain_mv, fx_run, cov_run)
    # The decomposition identity holds in the RAW (unquantized) domain; sigma/residual_variance
    # are each independently quantize_HALF_UP'd to their OWN column scale (6dp / 20dp), so the
    # persisted-column identity is APPROXIMATE evidence, not bit-exact (the max drift is bounded
    # by the 6dp sigma quantum: d(sigma^2) ~= 2*sigma*5E-7).
    decomposed_factor_var = row.sigma * row.sigma - row.residual_variance
    plain_factor_var = plain.rows[0].sigma * plain.rows[0].sigma
    assert abs(decomposed_factor_var - plain_factor_var) < Decimal("0.001")

    # Independent cross-check: recompute BOTH legs from the pinned content FRESH (not re-executing
    # the binder) — the exact RAW factor variance (via ``compute_parametric_var``, matching the
    # binder's own ``estimate.radicand`` precisely — NOT the already-6dp-quantized plain sigma
    # squared back, which would reintroduce the same rounding drift) + the residual leg (MV_i =
    # I-USD's total pinned factor exposure + the declared appraisal_days).
    import json
    from decimal import localcontext

    from irp_shared.risk import ResidualInstrument, compute_parametric_var, total_var_residual

    comps = list_components(session, snapshot_id=row.input_snapshot_id, acting_tenant=tenant)
    exposure_rows = [
        (
            json.loads(c.captured_content)["factor_id"],
            Decimal(json.loads(c.captured_content)["exposure_amount"]),
        )
        for c in comps
        if c.component_kind == "FACTOR_EXPOSURE"
    ]
    covariance = {
        (
            json.loads(c.captured_content)["factor_id_1"],
            json.loads(c.captured_content)["factor_id_2"],
        ): Decimal(json.loads(c.captured_content)["covariance_value"])
        for c in comps
        if c.component_kind == "COVARIANCE"
    }
    mv_usd = sum(
        Decimal(json.loads(c.captured_content)["exposure_amount"])
        for c in comps
        if c.component_kind == "FACTOR_EXPOSURE"
        and json.loads(c.captured_content)["instrument_id"] == insts["I-USD"]
    )
    with localcontext() as ctx:
        ctx.prec = 50
        plain_estimate = compute_parametric_var(exposure_rows, covariance, z_score=Z95)
        factor_var_raw = plain_estimate.radicand if plain_estimate.radicand > 0 else Decimal(0)
        independent = total_var_residual(
            factor_var_raw,
            [
                ResidualInstrument(
                    instrument_id=insts["I-USD"],
                    market_value=mv_usd,
                    residual_stdev_period=RESIDUAL_STDEV,
                    mean_period_calendar_days=Decimal(APPRAISAL_DAYS),
                )
            ],
            trading_days_per_year=252,
            calendar_days_per_year=365,
        )
    assert row.residual_variance == independent.residual_variance.quantize(Decimal("1E-20"))
    assert row.sigma == independent.sigma_total.quantize(Decimal("1E-6"))


# ---------- (2) invariance: zero proxied instruments => total ≡ plain, byte-exact ----------


def test_invariance_no_proxied_instrument_equals_plain(session: Session) -> None:
    tenant = str(uuid.uuid4())
    fx_run, cov_run, _pf, _insts = _seed_upstream_runs(session, tenant)
    total_mv = _var_total_model(session, tenant)
    plain_mv = register_var_model(
        session,
        tenant_id=tenant,
        actor_id="analyst",
        code_version="risk-v1",
        confidence_level="0.95",
    ).id

    total = _run_total(session, tenant, total_mv, fx_run, cov_run)
    plain = _run_total(session, tenant, plain_mv, fx_run, cov_run)
    assert total.rows[0].residual_variance == Decimal(0)
    assert total.rows[0].sigma == plain.rows[0].sigma
    assert total.rows[0].var_value == plain.rows[0].var_value
    assert total.rows[0].metric_type == METRIC_TYPE_VAR_PARAMETRIC_TOTAL
    assert plain.rows[0].metric_type == METRIC_TYPE_VAR_PARAMETRIC
    assert plain.rows[0].residual_variance is None


def test_manual_only_mapping_carries_zero_idiosyncratic_risk(session: Session) -> None:
    """A MANUAL-method mapping is NOT pinned by ``build_var_total_snapshot`` (no estimation
    evidence exists for it) — the instrument behaves exactly as non-proxied."""
    tenant = str(uuid.uuid4())
    fx_run, cov_run, _pf, insts = _seed_upstream_runs(session, tenant)
    from irp_shared.marketdata.models import Factor

    any_factor = session.execute(select(Factor).where(Factor.tenant_id == tenant)).scalars().first()
    capture_proxy_mapping(
        session,
        private_instrument_id=insts["I-USD"],
        factor_id=any_factor.id,
        weight=Decimal("0.5"),
        acting_tenant=tenant,
        actor=ProxyMappingActor(actor_id="a"),
        mapping_method=MAPPING_METHOD_MANUAL,
    )
    total_mv = _var_total_model(session, tenant)
    plain_mv = register_var_model(
        session,
        tenant_id=tenant,
        actor_id="analyst",
        code_version="risk-v1",
        confidence_level="0.95",
    ).id
    total = _run_total(session, tenant, total_mv, fx_run, cov_run)
    plain = _run_total(session, tenant, plain_mv, fx_run, cov_run)
    assert total.rows[0].residual_variance == Decimal(0)
    assert total.rows[0].sigma == plain.rows[0].sigma


# ---------- (3) model dispatch — ONE binder serves BOTH families ----------


def test_model_registration_declared_appraisal_days(session: Session) -> None:
    tenant = str(uuid.uuid4())
    mv_id = _var_total_model(session, tenant, appraisal_days=91)
    from irp_shared.model.models import ModelVersion

    version = session.get(ModelVersion, mv_id)
    assert version is not None and version.methodology_ref == VAR_TOTAL_METHODOLOGY_REF
    assert declared_appraisal_days(session, version) == 91


def test_appraisal_days_identity_conflicts_and_floor(session: Session) -> None:
    tenant = str(uuid.uuid4())
    first = _var_total_model(session, tenant, appraisal_days=91)
    assert _var_total_model(session, tenant, appraisal_days=91) == first  # idempotent
    from irp_shared.risk import ModelVersionConflictError

    with pytest.raises(ModelVersionConflictError):
        _var_total_model(session, tenant, appraisal_days=30)  # same label, different declaration
    with pytest.raises(ValueError):
        register_var_parametric_total_model(
            session,
            tenant_id=tenant,
            actor_id="a",
            code_version="risk-v1",
            confidence_level="0.95",
            appraisal_days=0,  # must be >= 1
        )


def test_unregistered_model_version_refused(session: Session) -> None:
    """An unregistered id raises from the FIRST assert (``UnregisteredModelError``), never
    reaching the total-family fallback."""
    from irp_shared.model.service import UnregisteredModelError

    tenant = str(uuid.uuid4())
    fx_run, cov_run, _pf, _insts = _seed_upstream_runs(session, tenant)
    with pytest.raises(UnregisteredModelError):
        _run_total(session, tenant, str(uuid.uuid4()), fx_run, cov_run)
    assert_no_running_orphan(session, run_type="VAR")


def test_wrong_family_model_version_refused(session: Session) -> None:
    """A version of a THIRD, unrelated model family (covariance) is neither the plain NOR the
    total VaR family — ``WrongModelVersionError`` from the SECOND (fallback) assert (the PA-2
    one-binder-dispatches-on-bound-model precedent)."""
    tenant = str(uuid.uuid4())
    fx_run, cov_run, _pf, _insts = _seed_upstream_runs(session, tenant)
    # _seed_upstream_runs already registered the covariance model at (risk-v1, window=4) — reuse
    # the SAME identity (idempotent resolve, not a fresh registration).
    cov_mv = register_covariance_model(
        session, tenant_id=tenant, actor_id="a", code_version="risk-v1", window_observations=4
    ).id
    with pytest.raises(WrongModelVersionError):
        _run_total(session, tenant, cov_mv, fx_run, cov_run)
    assert_no_running_orphan(session, run_type="VAR")


# ---------- (4) the symmetric binding-predicate refusal (OD-PA-2-C precedent) ----------


def test_symmetric_predicate_refusal_both_directions(session: Session) -> None:
    tenant = str(uuid.uuid4())
    fx_run, cov_run, pf, insts = _seed_upstream_runs(session, tenant)
    estimate_run = _mint_estimation_summary(
        session,
        tenant,
        portfolio_id=pf,
        instrument_id=insts["I-USD"],
        residual_stdev=RESIDUAL_STDEV,
        any_other_run_id=fx_run,
    )
    from irp_shared.marketdata.models import Factor

    any_factor = session.execute(select(Factor).where(Factor.tenant_id == tenant)).scalars().first()
    _promote(
        session,
        tenant,
        instrument_id=insts["I-USD"],
        factor_id=any_factor.id,
        source_run_id=estimate_run,
    )
    total_snap = build_var_total_snapshot(
        session,
        acting_tenant=tenant,
        actor=SnapshotActor(actor_id="a"),
        exposure_run_id=fx_run,
        covariance_run_id=cov_run,
    )
    assert total_snap.binding_predicate_version == VAR_TOTAL_BINDING_PREDICATE
    plain_snap = build_var_snapshot(
        session,
        acting_tenant=tenant,
        actor=SnapshotActor(actor_id="a"),
        exposure_run_id=fx_run,
        covariance_run_id=cov_run,
    )
    assert plain_snap.binding_predicate_version == VAR_BINDING_PREDICATE

    plain_mv = register_var_model(
        session,
        tenant_id=tenant,
        actor_id="analyst",
        code_version="risk-v1",
        confidence_level="0.95",
    ).id
    total_mv = _var_total_model(session, tenant)

    # Direction 1: the plain model over a total-predicate snapshot refuses.
    with pytest.raises(VarInputError):
        _run_total(session, tenant, plain_mv, None, None, snapshot_id=total_snap.id)
    assert_no_running_orphan(session, run_type="VAR")
    # Direction 2: the total model over a plain-predicate snapshot refuses.
    with pytest.raises(VarInputError):
        _run_total(session, tenant, total_mv, None, None, snapshot_id=plain_snap.id)
    assert_no_running_orphan(session, run_type="VAR")


# ---------- (5) snapshot-build-time citation adjudication (OD-PA-4-C) ----------


def test_build_refuses_missing_cited_estimation_run(session: Session) -> None:
    tenant = str(uuid.uuid4())
    fx_run, cov_run, _pf, insts = _seed_upstream_runs(session, tenant)
    from irp_shared.marketdata.models import Factor

    any_factor = session.execute(select(Factor).where(Factor.tenant_id == tenant)).scalars().first()
    # Cite a REAL COMPLETED PROXY_WEIGHT_ESTIMATE run with NO ESTIMATION_SUMMARY row (models the
    # missing/non-COMPLETED cited-run class collapsed into one check).
    empty_run = _mint_empty_completed_estimate_run(session, tenant)
    _promote(
        session,
        tenant,
        instrument_id=insts["I-USD"],
        factor_id=any_factor.id,
        source_run_id=empty_run,
    )
    with pytest.raises(VarTotalSnapshotError):
        build_var_total_snapshot(
            session,
            acting_tenant=tenant,
            actor=SnapshotActor(actor_id="a"),
            exposure_run_id=fx_run,
            covariance_run_id=cov_run,
        )


def test_build_refuses_wrong_instrument_citation(session: Session) -> None:
    tenant = str(uuid.uuid4())
    fx_run, cov_run, pf, insts = _seed_upstream_runs(session, tenant)
    # The estimation run's summary names I-EUR, but I-USD's mapping cites it.
    estimate_run = _mint_estimation_summary(
        session,
        tenant,
        portfolio_id=pf,
        instrument_id=insts["I-EUR"],
        residual_stdev=RESIDUAL_STDEV,
        any_other_run_id=fx_run,
    )
    from irp_shared.marketdata.models import Factor

    any_factor = session.execute(select(Factor).where(Factor.tenant_id == tenant)).scalars().first()
    _promote(
        session,
        tenant,
        instrument_id=insts["I-USD"],
        factor_id=any_factor.id,
        source_run_id=estimate_run,
    )
    with pytest.raises(VarTotalSnapshotError):
        build_var_total_snapshot(
            session,
            acting_tenant=tenant,
            actor=SnapshotActor(actor_id="a"),
            exposure_run_id=fx_run,
            covariance_run_id=cov_run,
        )


def test_build_refuses_ambiguous_multi_run_citation(session: Session) -> None:
    """TWO open REGRESSION mappings for the SAME instrument citing TWO DIFFERENT estimation runs
    (a two-factor blend promoted piecemeal from different vintages) — an ambiguous residual
    citation, refused BEFORE any write."""
    tenant = str(uuid.uuid4())
    fx_run, cov_run, pf, insts = _seed_upstream_runs(session, tenant)
    run_a = _mint_estimation_summary(
        session,
        tenant,
        portfolio_id=pf,
        instrument_id=insts["I-USD"],
        residual_stdev=RESIDUAL_STDEV,
        any_other_run_id=fx_run,
    )
    run_b = _mint_estimation_summary(
        session,
        tenant,
        portfolio_id=pf,
        instrument_id=insts["I-USD"],
        residual_stdev=Decimal("0.05"),
        any_other_run_id=fx_run,
    )
    from irp_shared.marketdata.models import Factor

    factors = session.execute(select(Factor).where(Factor.tenant_id == tenant)).scalars().all()
    _promote(
        session, tenant, instrument_id=insts["I-USD"], factor_id=factors[0].id, source_run_id=run_a
    )
    _promote(
        session, tenant, instrument_id=insts["I-USD"], factor_id=factors[1].id, source_run_id=run_b
    )
    with pytest.raises(VarTotalSnapshotError):
        build_var_total_snapshot(
            session,
            acting_tenant=tenant,
            actor=SnapshotActor(actor_id="a"),
            exposure_run_id=fx_run,
            covariance_run_id=cov_run,
        )


# ---------- (6) service-level adjudication via hand-minted snapshots ----------


def _mint_total_snapshot(
    session: Session,
    tenant: str,
    exposure_rows: list[dict],
    covariance_rows: list[dict],
    proxy_mapping_rows: list[dict],
    proxy_weight_rows: list[dict],
):  # noqa: ANN202
    """Hand-mint a total-predicate VAR_INPUT snapshot with ARBITRARY pinned content (bypassing the
    governed builder) — the service-layer adjudication-gate probe (the ``test_var.py``
    ``_mint_var_snapshot`` precedent, extended with the two PA-4 component kinds)."""
    from irp_shared.snapshot.service import _persist_snapshot

    specs: list = []
    for content in exposure_rows:
        content = dict(content)
        anchor_id = content.pop("_anchor", None) or content["id"]
        anchor = SimpleNamespace(id=anchor_id, valid_from=None, system_from=T0, record_version=None)
        specs.append(("FACTOR_EXPOSURE", "factor_exposure_result", anchor, json_dump(content)))
    for content in covariance_rows:
        content = dict(content)
        anchor_id = content.pop("_anchor", None) or content["id"]
        anchor = SimpleNamespace(id=anchor_id, valid_from=None, system_from=T0, record_version=None)
        specs.append(("COVARIANCE", "covariance_result", anchor, json_dump(content)))
    for content in proxy_mapping_rows:
        content = dict(content)
        anchor_id = content.pop("_anchor", None) or content["id"]
        anchor = SimpleNamespace(id=anchor_id, valid_from=None, system_from=T0, record_version=None)
        specs.append((COMPONENT_KIND_PROXY_MAPPING, "proxy_mapping", anchor, json_dump(content)))
    for content in proxy_weight_rows:
        content = dict(content)
        anchor_id = content.pop("_anchor", None) or content["id"]
        anchor = SimpleNamespace(id=anchor_id, valid_from=None, system_from=T0, record_version=None)
        specs.append(
            (
                COMPONENT_KIND_PROXY_WEIGHT,
                "proxy_weight_estimate_result",
                anchor,
                json_dump(content),
            )
        )
    from irp_shared.audit.hashing import sha256_hex

    full_specs = [(kind, ttype, row, cc, sha256_hex(cc)) for kind, ttype, row, cc in specs]
    header = _persist_snapshot(
        session,
        acting_tenant=tenant,
        actor=SnapshotActor(actor_id="a"),
        specs=full_specs,
        label="",
        purpose="VAR_INPUT",
        as_of_valid_at=VALID_AT,
        as_of_known_at=KNOWN_AT,
        as_of_valuation_date=VD,
        binding_predicate_version=VAR_TOTAL_BINDING_PREDICATE,
    )
    return header


def json_dump(content: dict) -> str:
    from irp_shared.snapshot.serialize import serialize_content

    return serialize_content(content)


def _exposure_content(
    run_id: str, fid: str, code: str, instrument_id: str, amount: str, base: str = "USD"
) -> dict:
    return {
        "id": str(uuid.uuid4()),
        "tenant_id": "t",
        "calculation_run_id": run_id,
        "input_snapshot_id": str(uuid.uuid4()),
        "model_version_id": str(uuid.uuid4()),
        "system_from": T0.isoformat(),
        "portfolio_id": str(uuid.uuid4()),
        "instrument_id": instrument_id,
        "factor_id": fid,
        "factor_code": code,
        "factor_family": "CURRENCY",
        "base_currency": base,
        "mark_currency": base,
        "loading": "1.000000000000",
        "exposure_amount": amount,
    }


def _covariance_content(run_id: str, f1: str, f2: str, value: str, n: int = 4) -> dict:
    return {
        "id": str(uuid.uuid4()),
        "tenant_id": "t",
        "calculation_run_id": run_id,
        "input_snapshot_id": str(uuid.uuid4()),
        "model_version_id": str(uuid.uuid4()),
        "system_from": T0.isoformat(),
        "factor_id_1": min(f1, f2),
        "factor_id_2": max(f1, f2),
        "statistic_type": "COVARIANCE",
        "return_type": "SIMPLE",
        "frequency": "DAILY",
        "n_observations": n,
        "window_start": D1.isoformat(),
        "window_end": D4.isoformat(),
        "covariance_value": value,
    }


def _weight_content(
    instrument_id: str,
    residual_stdev: str,
    series_currency: str = "USD",
    metric_type: str = "ESTIMATION_SUMMARY",
) -> dict:
    return {
        "id": str(uuid.uuid4()),
        "tenant_id": "t",
        "calculation_run_id": str(uuid.uuid4()),
        "input_snapshot_id": str(uuid.uuid4()),
        "model_version_id": str(uuid.uuid4()),
        "portfolio_id": str(uuid.uuid4()),
        "instrument_id": instrument_id,
        "source_desmoothed_run_id": str(uuid.uuid4()),
        "metric_type": metric_type,
        "factor_id": None,
        "metric_value": "0.800000000000",
        "std_error": None,
        "n_observations": 6,
        "n_regressors": 1,
        "residual_stdev": residual_stdev,
        "min_observations": 4,
        "series_currency": series_currency,
        "system_from": T0.isoformat(),
    }


def _mapping_content(instrument_id: str, factor_id: str) -> dict:
    return {
        "id": str(uuid.uuid4()),
        "tenant_id": "t",
        "private_instrument_id": instrument_id,
        "factor_id": factor_id,
        "weight": "0.500000000000",
        "mapping_method": "REGRESSION",
        "valid_from": T0.isoformat(),
        "system_from": T0.isoformat(),
        "record_version": 1,
    }


_ONE_FACTOR_COV = {("f", "f"): "0.0001"}


def _one_factor_pins(run_id: str, instrument_id: str, amount: str = "30000"):
    exposure = [_exposure_content(run_id, "f", "FX", instrument_id, amount)]
    covariance = [_covariance_content(run_id, "f", "f", "0.0001")]
    return exposure, covariance


def test_service_refuses_wrong_type_proxy_weight_pin(session: Session) -> None:
    tenant = str(uuid.uuid4())
    fx_run, cov_run, _pf, insts = _seed_upstream_runs(session, tenant)
    iid = insts["I-USD"]
    exposure, covariance = _one_factor_pins(fx_run, iid)
    weight = _weight_content(iid, "0.040000000000", metric_type="WEIGHT")  # wrong type
    mapping = [_mapping_content(iid, "f")]
    snap = _mint_total_snapshot(session, tenant, exposure, covariance, mapping, [weight])
    total_mv = _var_total_model(session, tenant)
    with pytest.raises(VarInputError):
        _run_total(session, tenant, total_mv, None, None, snapshot_id=snap.id)
    assert_no_running_orphan(session, run_type="VAR")


def test_service_refuses_instrument_mismatch_weight_without_mapping(session: Session) -> None:
    tenant = str(uuid.uuid4())
    fx_run, cov_run, _pf, insts = _seed_upstream_runs(session, tenant)
    iid = insts["I-USD"]
    exposure, covariance = _one_factor_pins(fx_run, iid)
    weight = [_weight_content(iid, "0.040000000000")]
    snap = _mint_total_snapshot(session, tenant, exposure, covariance, [], weight)  # no mapping
    total_mv = _var_total_model(session, tenant)
    with pytest.raises(VarInputError):
        _run_total(session, tenant, total_mv, None, None, snapshot_id=snap.id)
    assert_no_running_orphan(session, run_type="VAR")


def test_service_refuses_instrument_mismatch_mapping_without_weight(session: Session) -> None:
    tenant = str(uuid.uuid4())
    fx_run, cov_run, _pf, insts = _seed_upstream_runs(session, tenant)
    iid = insts["I-USD"]
    exposure, covariance = _one_factor_pins(fx_run, iid)
    mapping = [_mapping_content(iid, "f")]
    snap = _mint_total_snapshot(session, tenant, exposure, covariance, mapping, [])  # no weight
    total_mv = _var_total_model(session, tenant)
    with pytest.raises(VarInputError):
        _run_total(session, tenant, total_mv, None, None, snapshot_id=snap.id)
    assert_no_running_orphan(session, run_type="VAR")


def test_service_refuses_weight_for_unexposed_instrument(session: Session) -> None:
    tenant = str(uuid.uuid4())
    fx_run, cov_run, _pf, insts = _seed_upstream_runs(session, tenant)
    iid = insts["I-USD"]
    other_iid = str(uuid.uuid4())
    exposure, covariance = _one_factor_pins(fx_run, iid)
    weight = [_weight_content(other_iid, "0.040000000000")]
    mapping = [_mapping_content(other_iid, "f")]
    snap = _mint_total_snapshot(session, tenant, exposure, covariance, mapping, weight)
    total_mv = _var_total_model(session, tenant)
    with pytest.raises(VarInputError):
        _run_total(session, tenant, total_mv, None, None, snapshot_id=snap.id)
    assert_no_running_orphan(session, run_type="VAR")


def test_service_refuses_duplicate_weight_pin(session: Session) -> None:
    tenant = str(uuid.uuid4())
    fx_run, cov_run, _pf, insts = _seed_upstream_runs(session, tenant)
    iid = insts["I-USD"]
    exposure, covariance = _one_factor_pins(fx_run, iid)
    w = _weight_content(iid, "0.040000000000")
    w2 = dict(w)
    w2["id"] = str(uuid.uuid4())  # a distinct component target, SAME instrument
    mapping = [_mapping_content(iid, "f")]
    snap = _mint_total_snapshot(session, tenant, exposure, covariance, mapping, [w, w2])
    total_mv = _var_total_model(session, tenant)
    with pytest.raises(VarInputError):
        _run_total(session, tenant, total_mv, None, None, snapshot_id=snap.id)
    assert_no_running_orphan(session, run_type="VAR")


def test_service_refuses_currency_mismatch(session: Session) -> None:
    tenant = str(uuid.uuid4())
    fx_run, cov_run, _pf, insts = _seed_upstream_runs(session, tenant)
    iid = insts["I-USD"]
    exposure, covariance = _one_factor_pins(fx_run, iid)
    weight = [_weight_content(iid, "0.040000000000", series_currency="EUR")]  # book is USD
    mapping = [_mapping_content(iid, "f")]
    snap = _mint_total_snapshot(session, tenant, exposure, covariance, mapping, weight)
    total_mv = _var_total_model(session, tenant)
    with pytest.raises(VarInputError):
        _run_total(session, tenant, total_mv, None, None, snapshot_id=snap.id)
    assert_no_running_orphan(session, run_type="VAR")


def test_service_refuses_negative_residual_stdev(session: Session) -> None:
    tenant = str(uuid.uuid4())
    fx_run, cov_run, _pf, insts = _seed_upstream_runs(session, tenant)
    iid = insts["I-USD"]
    exposure, covariance = _one_factor_pins(fx_run, iid)
    weight = [_weight_content(iid, "-0.040000000000")]
    mapping = [_mapping_content(iid, "f")]
    snap = _mint_total_snapshot(session, tenant, exposure, covariance, mapping, weight)
    total_mv = _var_total_model(session, tenant)
    with pytest.raises(VarInputError):
        _run_total(session, tenant, total_mv, None, None, snapshot_id=snap.id)
    assert_no_running_orphan(session, run_type="VAR")


# ---------- (7) TR-09: a later re-promotion does not move an already-pinned estimate ----------


def test_tr09_repromotion_does_not_move_pinned_run(session: Session) -> None:
    tenant = str(uuid.uuid4())
    fx_run, cov_run, pf, insts = _seed_upstream_runs(session, tenant)
    estimate_run = _mint_estimation_summary(
        session,
        tenant,
        portfolio_id=pf,
        instrument_id=insts["I-USD"],
        residual_stdev=RESIDUAL_STDEV,
        any_other_run_id=fx_run,
    )
    from irp_shared.marketdata.models import Factor

    factors = session.execute(select(Factor).where(Factor.tenant_id == tenant)).scalars().all()
    _promote(
        session,
        tenant,
        instrument_id=insts["I-USD"],
        factor_id=factors[0].id,
        source_run_id=estimate_run,
    )

    total_mv = _var_total_model(session, tenant)
    first = _run_total(session, tenant, total_mv, fx_run, cov_run)
    assert first.rows[0].residual_variance == REF_RESIDUAL_VARIANCE

    # A later re-promotion (a new estimate, a new weight) supersedes the OPEN mapping head.
    new_estimate_run = _mint_estimation_summary(
        session,
        tenant,
        portfolio_id=pf,
        instrument_id=insts["I-USD"],
        residual_stdev=Decimal("0.10"),
        any_other_run_id=fx_run,
    )
    _promote(
        session,
        tenant,
        instrument_id=insts["I-USD"],
        factor_id=factors[0].id,
        source_run_id=new_estimate_run,
    )

    # The FIRST run's pinned content is byte-stable (verify_snapshot ok) and its persisted row is
    # untouched (re-reading it returns the SAME residual_variance).
    v = verify_snapshot(session, snapshot_id=first.rows[0].input_snapshot_id, acting_tenant=tenant)
    assert v.ok
    reread = session.get(VarResult, first.rows[0].id)
    assert reread.residual_variance == REF_RESIDUAL_VARIANCE
