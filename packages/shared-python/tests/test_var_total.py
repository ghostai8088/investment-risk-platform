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
from datetime import UTC, date, datetime, timedelta
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
from irp_shared.model.models import ModelVersion
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
    VAR_Z_SCORES,
    CovarianceActor,
    FactorExposureActor,
    ProxyWeightEstimateResult,
    VarActor,
    VarInputError,
    VarResult,
    WrongModelVersionError,
    declared_appraisal_days,
    declared_max_estimate_age_days,
    promote_proxy_weight_estimate,
    register_covariance_model,
    register_factor_exposure_model,
    register_var_model,
    register_var_parametric_total_model,
    run_covariance,
    run_factor_exposure,
    run_var,
)
from irp_shared.risk.bootstrap import (
    APPRAISAL_DAYS_ASSUMPTION_PREFIX,
    MAX_ESTIMATE_AGE_ASSUMPTION_PREFIX,
)
from irp_shared.snapshot import (
    COMPONENT_KIND_PROXY_MAPPING,
    COMPONENT_KIND_PROXY_WEIGHT,
    VAR_BINDING_PREDICATE,
    VAR_TOTAL_BINDING_PREDICATE,
    SnapshotActor,
    VarTotalSnapshotError,
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
# BT-2: the declared staleness policy. 400 days ~ "the estimate may be up to a year-and-a-bit
# old" — a plausible governance choice for a quarterly-appraised book (a fresh estimate arrives
# each appraisal, so a >1y-old one means several cycles were skipped). The default keeps the
# PA-4 fixtures (whose estimates are days old) comfortably inside the gate.
MAX_ESTIMATE_AGE_DAYS = 400
RESIDUAL_STDEV = Decimal("0.04")  # 4%/quarter

#: HAND REFERENCE (independently derived, PA-4): I-USD's total pinned factor exposure MV=30000
#: (the 3-4-5 REF1 book, ``test_var.py`` twin: factor_var=250000, plain sigma=500 EXACTLY),
#: proxied with residual_stdev_period=0.04 (quarterly), appraisal_days=91 =>
#: d_trading = 91*(252/365) = 62.8273972602739726027397260273972602739726027397260;
#: sigma_e_daily = 0.04/sqrt(d_trading) = 0.0050464439851412522876...;
#: residual_variance = (30000*sigma_e_daily)^2 = 22919.9372056514913657770801...
#: sigma_total = sqrt(250000 + residual_variance) = 522.41739749519396280801883332...
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
    estimate_span_end: date | None = None,
) -> str:
    """Directly persist a COMPLETED ``PROXY_WEIGHT_ESTIMATE`` run + its ``ESTIMATION_SUMMARY`` row
    (bypassing the full OLS regression chain — PA-4 needs a KNOWN, controlled ``residual_stdev``
    for the golden/precision tests, the ``test_var.py`` ``_mint_var_snapshot`` precedent applied
    to a governed RESULT row rather than a hand-minted snapshot). Every FK target is a REAL row
    (``input_snapshot_id`` a real dataset_snapshot; ``model_version_id`` a real proxy-weight
    model_version; ``source_desmoothed_run_id`` reuses ``any_other_run_id`` — the FK only requires
    an EXISTING ``calculation_run`` row, not a specific ``run_type``) so the fixture is PG-portable
    (FK-enforced) as well as SQLite-safe.

    BT-2 fixture-realism fold: the input snapshot now carries the purpose the REAL chain produces
    (``PROXY_WEIGHT_INPUT``, not the ``TEST`` shortcut) and an ``as_of_valuation_date`` =
    ``estimate_span_end`` — the regression SPAN END. The staleness gate reads exactly those two
    fields off this header, so a TEST-purpose/valuation-date-VD shortcut modelled an estimate that
    does not exist (and, at VD > D4, one that looks ahead). Default: 30 days before the covariance
    window end — a plausible "estimated last month" fixture."""
    from irp_shared.risk.bootstrap import register_proxy_weight_regression_model

    # `_estimate_snapshot` (not the generic `build_snapshot`, whose purpose vocabulary excludes
    # PROXY_WEIGHT_INPUT) mirrors what `build_proxy_weight_snapshot` really persists.
    snap = _estimate_snapshot(db, tenant, estimate_span_end or (D4 - timedelta(days=30)))
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
    SUMMARY class for ``build_var_total_snapshot``). The "non-COMPLETED cited run" class is
    COLLAPSED into this one check because through the GOVERNED write path result rows are
    inserted only on the success path immediately before the COMPLETED transition
    (``calc/scaffold.py`` — a FAILED estimation run persists ZERO rows; IA rows cannot
    un-complete), so a visible ESTIMATION_SUMMARY implies a COMPLETED run. The
    ``_mint_estimation_summary`` fixture writes rows DIRECTLY (bypassing the scaffold) — that is
    a fixture liberty, not a governed-path counterexample (2026-07 review reconciliation)."""
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
    max_estimate_age_days: int = MAX_ESTIMATE_AGE_DAYS,
) -> str:
    return register_var_parametric_total_model(
        db,
        tenant_id=tenant,
        actor_id="analyst",
        code_version=code_version,
        confidence_level=confidence,
        appraisal_days=appraisal_days,
        max_estimate_age_days=max_estimate_age_days,
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


def _count_snapshots(db: Session, tenant: str) -> int:
    from irp_shared.snapshot import DatasetSnapshot

    return db.execute(
        select(func.count()).select_from(DatasetSnapshot).where(DatasetSnapshot.tenant_id == tenant)
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


def test_full_stack_governed_build_path_decomposition_multi_proxied(session: Session) -> None:
    """The REAL governed build path (``build_var_total_snapshot`` -> ``run_var``, real computed
    sample covariance — NOT hand-picked) with TWO proxied instruments (distinct estimates —
    the builder's per-instrument citation loop + the service's acceptance of multiple weight
    pins for DIFFERENT instruments, exercised end-to-end; 2026-07 review): the DECOMPOSITION
    identity ``sigma_total^2 - residual_variance == plain_sigma^2`` holds on WHATEVER factor
    variance the real upstream chain produces, cross-checked against an INDEPENDENT kernel
    recomputation from the pinned exposure content."""
    tenant = str(uuid.uuid4())
    fx_run, cov_run, pf, insts = _seed_upstream_runs(session, tenant)
    from irp_shared.marketdata.models import Factor

    factors = session.execute(select(Factor).where(Factor.tenant_id == tenant)).scalars().all()
    # I-USD proxied at 4%/quarter; I-EUR proxied at 6%/quarter (a plausible second private leg).
    residual_by_inst = {"I-USD": RESIDUAL_STDEV, "I-EUR": Decimal("0.06")}
    for code, factor in zip(("I-USD", "I-EUR"), factors, strict=False):
        estimate_run = _mint_estimation_summary(
            session,
            tenant,
            portfolio_id=pf,
            instrument_id=insts[code],
            residual_stdev=residual_by_inst[code],
            series_currency="USD",
            any_other_run_id=fx_run,
        )
        _promote(
            session,
            tenant,
            instrument_id=insts[code],
            factor_id=factor.id,
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
    # persisted-column identity is APPROXIMATE evidence, not bit-exact. The DERIVED worst-case
    # bound (2026-07 numeric-finder fold — a fixed 0.001 was NOT derived and sat under the true
    # bound for this book): each quantize moves sigma by <= q/2 = 5E-7, so each sigma^2 moves by
    # <= sigma*q (+ q^2/4, negligible); both sides drift independently, plus the 20dp residual
    # quantum. bound = (sigma_total + sigma_plain)*1E-6 + 1E-20 (+ tiny q^2 slack).
    decomposed_factor_var = row.sigma * row.sigma - row.residual_variance
    plain_factor_var = plain.rows[0].sigma * plain.rows[0].sigma
    bound = (row.sigma + plain.rows[0].sigma) * Decimal("1E-6") + Decimal("1E-12")
    assert abs(decomposed_factor_var - plain_factor_var) <= bound

    # Independent cross-check: recompute BOTH legs from the pinned content FRESH (not re-executing
    # the binder) — the exact RAW factor variance (via ``compute_parametric_var``, matching the
    # binder's own ``estimate.radicand`` precisely — NOT the already-6dp-quantized plain sigma
    # squared back, which would reintroduce the same rounding drift) + the residual leg (MV_i =
    # each instrument's total pinned factor exposure + the declared appraisal_days).
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

    def _mv_of(instrument_id: str) -> Decimal:
        return sum(
            (
                Decimal(json.loads(c.captured_content)["exposure_amount"])
                for c in comps
                if c.component_kind == "FACTOR_EXPOSURE"
                and json.loads(c.captured_content)["instrument_id"] == instrument_id
            ),
            Decimal(0),
        )

    with localcontext() as ctx:
        ctx.prec = 50
        plain_estimate = compute_parametric_var(exposure_rows, covariance, z_score=Z95)
        factor_var_raw = plain_estimate.radicand if plain_estimate.radicand > 0 else Decimal(0)
        independent = total_var_residual(
            factor_var_raw,
            [
                ResidualInstrument(
                    instrument_id=insts[code],
                    market_value=_mv_of(insts[code]),
                    residual_stdev_period=residual_by_inst[code],
                    mean_period_calendar_days=Decimal(APPRAISAL_DAYS),
                )
                for code in ("I-USD", "I-EUR")
            ],
            trading_days_per_year=252,
            calendar_days_per_year=365,
        )
    assert row.residual_variance == independent.residual_variance.quantize(Decimal("1E-20"))
    assert row.sigma == independent.sigma_total.quantize(Decimal("1E-6"))


def test_rerun_and_consume_equals_build(session: Session) -> None:
    """Consume-existing ≡ build-in-request + exact re-run reproducibility for the TOTAL family
    (the ``test_var.py`` ``test_exact_rerun_and_consume_equals_build`` precedent; 2026-07 review —
    the shipped consume tests used only hand-minted snapshots, so a governed-BUILT total snapshot
    was never consumed on the happy path): a second run CONSUMING the first run's governed-built
    snapshot produces a byte-identical row under a NEW run id."""
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
    first = _run_total(session, tenant, mv, fx_run, cov_run)
    assert first.status == RunStatus.COMPLETED.value
    second = _run_total(
        session, tenant, mv, None, None, snapshot_id=first.rows[0].input_snapshot_id
    )
    assert second.status == RunStatus.COMPLETED.value
    a, b = first.rows[0], second.rows[0]
    assert a.calculation_run_id != b.calculation_run_id  # a genuinely NEW run
    assert a.input_snapshot_id == b.input_snapshot_id  # over the SAME pinned input
    assert (a.sigma, a.var_value, a.residual_variance) == (
        b.sigma,
        b.var_value,
        b.residual_variance,
    )
    assert (a.metric_type, a.base_currency, a.z_score) == (
        b.metric_type,
        b.base_currency,
        b.z_score,
    )


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
            max_estimate_age_days=MAX_ESTIMATE_AGE_DAYS,
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

    # ES-1: the SAME symmetry on the two ES families — all FOUR codes, both directions (8 cases).
    # The gates read `family.total`, so today the ES families inherit them for free; this pins that.
    # The failure it guards is a REFACTOR that re-keys the predicate check onto a model CODE (e.g.
    # `code == VAR_TOTAL_MODEL_CODE`) — that would drop the gate for ES-total ONLY, letting an
    # ES-total model complete over a plain snapshot while silently discarding the pinned
    # idiosyncratic evidence (the OD-PA-2-C failure), with the compute path still correct and every
    # other test green.
    from irp_shared.risk import register_var_parametric_es_model

    es_mv = register_var_parametric_es_model(
        session,
        tenant_id=tenant,
        actor_id="analyst",
        code_version="risk-v1",
        confidence_level="0.95",
    ).id
    es_total_mv = _var_es_total_model(session, tenant)
    # Direction 3: the plain-ES model over a total-predicate snapshot refuses.
    with pytest.raises(VarInputError):
        _run_total(session, tenant, es_mv, None, None, snapshot_id=total_snap.id)
    assert_no_running_orphan(session, run_type="VAR")
    # Direction 4: the ES-total model over a plain-predicate snapshot refuses.
    with pytest.raises(VarInputError):
        _run_total(session, tenant, es_total_mv, None, None, snapshot_id=plain_snap.id)
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
    before = _count_snapshots(session, tenant)
    with pytest.raises(VarTotalSnapshotError):
        build_var_total_snapshot(
            session,
            acting_tenant=tenant,
            actor=SnapshotActor(actor_id="a"),
            exposure_run_id=fx_run,
            covariance_run_id=cov_run,
        )
    assert _count_snapshots(session, tenant) == before  # refused BEFORE any write


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
    before = _count_snapshots(session, tenant)
    with pytest.raises(VarTotalSnapshotError):
        build_var_total_snapshot(
            session,
            acting_tenant=tenant,
            actor=SnapshotActor(actor_id="a"),
            exposure_run_id=fx_run,
            covariance_run_id=cov_run,
        )
    assert _count_snapshots(session, tenant) == before  # refused BEFORE any write


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
    before = _count_snapshots(session, tenant)
    with pytest.raises(VarTotalSnapshotError):
        build_var_total_snapshot(
            session,
            acting_tenant=tenant,
            actor=SnapshotActor(actor_id="a"),
            exposure_run_id=fx_run,
            covariance_run_id=cov_run,
        )
    assert _count_snapshots(session, tenant) == before  # refused BEFORE any write


# ---------- (6) service-level adjudication via hand-minted snapshots ----------


def _mint_total_snapshot(
    session: Session,
    tenant: str,
    exposure_rows: list[dict],
    covariance_rows: list[dict],
    proxy_mapping_rows: list[dict],
    proxy_weight_rows: list[dict],
    *,
    estimate_span_end: date | None = None,
):  # noqa: ANN202
    """Hand-mint a total-predicate VAR_INPUT snapshot with ARBITRARY pinned content (bypassing the
    governed builder) — the service-layer adjudication-gate probe (the ``test_var.py``
    ``_mint_var_snapshot`` precedent, extended with the two PA-4 component kinds).

    BT-2: every weight pin is pointed at ONE real, resolvable estimation snapshot whose
    ``as_of_valuation_date`` is ``estimate_span_end`` (default ``VD`` — a same-day, age-0
    estimate), so the staleness gate can evaluate. The age battery passes an older span end to
    drive the gate; a test wanting the unresolvable-citation refusal keeps a weight row's own
    fabricated ``input_snapshot_id`` by passing it explicitly to ``_weight_content``."""
    from irp_shared.snapshot.service import _persist_snapshot

    est_snapshot = _estimate_snapshot(session, tenant, estimate_span_end or VD)
    rewritten: list[dict] = []
    for w in proxy_weight_rows:
        w = dict(w)
        # `_keep_snapshot` (popped, never pinned) opts a row OUT of the rewrite so a test can
        # probe the unresolvable-citation refusal with its own fabricated id.
        if not w.pop("_keep_snapshot", False):
            w["input_snapshot_id"] = est_snapshot.id
        rewritten.append(w)
    proxy_weight_rows = rewritten
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


def _estimate_snapshot(session: Session, tenant: str, span_end: date):  # noqa: ANN202
    """Mint a minimal PROXY_WEIGHT_INPUT snapshot HEADER whose ``as_of_valuation_date`` is the
    regression SPAN END — the anchor BT-2's staleness gate measures a cited estimate's age
    against (OD-BT-2-C). Hand-minted pins cite it so the age is controllable per test."""
    from irp_shared.snapshot.service import _persist_snapshot

    return _persist_snapshot(
        session,
        acting_tenant=tenant,
        actor=SnapshotActor(actor_id="a"),
        specs=[],
        label="",
        purpose="PROXY_WEIGHT_INPUT",
        as_of_valid_at=VALID_AT,
        as_of_known_at=KNOWN_AT,
        as_of_valuation_date=span_end,
        binding_predicate_version="v1:test",
    )


def _weight_content(
    instrument_id: str,
    residual_stdev: str,
    series_currency: str = "USD",
    metric_type: str = "ESTIMATION_SUMMARY",
    input_snapshot_id: str | None = None,
) -> dict:
    return {
        "id": str(uuid.uuid4()),
        "tenant_id": "t",
        "calculation_run_id": str(uuid.uuid4()),
        # BT-2: a genuine pin always cites its estimation snapshot; the age gate resolves it.
        # Tests that don't care about age pass a fresh one via `input_snapshot_id`.
        "input_snapshot_id": input_snapshot_id or str(uuid.uuid4()),
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


def _one_factor_pins(
    run_id: str, instrument_id: str, amount: str = "30000", covariance_run_id: str | None = None
):
    """One-factor pin pair. Refusal tests (which never reach the pinned-provenance
    re-resolution) may pin both under one run id; SUCCESS/FAILED-path tests MUST pass the real
    ``covariance_run_id`` — the binder re-resolves both pinned run ids by run_type before the
    compute (2026-07 review note)."""
    exposure = [_exposure_content(run_id, "f", "FX", instrument_id, amount)]
    covariance = [_covariance_content(covariance_run_id or run_id, "f", "f", "0.0001")]
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

    # SIDE 1: the FIRST run's pinned content is byte-stable (verify_snapshot ok) and its persisted
    # row is untouched (re-reading it returns the SAME residual_variance).
    v = verify_snapshot(session, snapshot_id=first.rows[0].input_snapshot_id, acting_tenant=tenant)
    assert v.ok
    reread = session.get(VarResult, first.rows[0].id)
    assert reread.residual_variance == REF_RESIDUAL_VARIANCE

    # SIDE 2 (2026-07 review — TR-09's other half): a FRESH build-path run AFTER the re-promotion
    # picks up the NEW estimate. Independent derivation: residual scales as sigma_e^2, so
    # rv(0.10) = rv(0.04)*(0.10/0.04)^2 = 22919.93720565149136577708...*6.25
    #          = 143249.60753532182103610675 @20dp (probe-verified against the raw product).
    fresh = _run_total(session, tenant, total_mv, fx_run, cov_run)
    assert fresh.status == RunStatus.COMPLETED.value
    assert fresh.rows[0].residual_variance == Decimal("143249.60753532182103610675")
    assert fresh.rows[0].input_snapshot_id != first.rows[0].input_snapshot_id


# ---------- (8) post-create FAILED + boundary battery (2026-07 review folds) ----------


def test_column_legal_extreme_magnitude_fails_closed_not_500(session: Session) -> None:
    """The total-path magnitude gate (the plain family's ``test_column_legal_extreme_magnitude...``
    twin, 2026-07 review — the gate had ZERO coverage): a residual_stdev JUST INSIDE its
    source-column envelope (99999999 < 1E8) drives residual_variance ~1.43E23 past the
    Numeric(38,20) bound — a committed FAILED run with evidence, never a PG overflow 500."""
    tenant = str(uuid.uuid4())
    fx_run, cov_run, _pf, insts = _seed_upstream_runs(session, tenant)
    iid = insts["I-USD"]
    # A post-create outcome REACHES the pinned-provenance re-resolution — real run ids required.
    exposure, covariance = _one_factor_pins(fx_run, iid, covariance_run_id=cov_run)
    weight = [_weight_content(iid, "99999999.000000000000")]  # column-legal, envelope-passing
    mapping = [_mapping_content(iid, "f")]
    snap = _mint_total_snapshot(session, tenant, exposure, covariance, mapping, weight)
    total_mv = _var_total_model(session, tenant)
    result = _run_total(session, tenant, total_mv, None, None, snapshot_id=snap.id)
    assert result.status == RunStatus.FAILED.value and result.rows == []
    assert "magnitude-out-of-range" in (result.failure_reason or "")
    assert_no_running_orphan(session, run_type="VAR")


def test_manual_method_mapping_pin_refused(session: Session) -> None:
    """A hand-minted total-predicate snapshot pinning a MANUAL-method mapping + a matching
    ESTIMATION_SUMMARY must refuse (2026-07 adversarial fold — without the mapping_method
    vocabulary gate it COMPLETED with the residual attached, contradicting the registered
    'MANUAL-method instruments carry ZERO idiosyncratic variance' assumption)."""
    tenant = str(uuid.uuid4())
    fx_run, cov_run, _pf, insts = _seed_upstream_runs(session, tenant)
    iid = insts["I-USD"]
    exposure, covariance = _one_factor_pins(fx_run, iid)
    manual_mapping = dict(_mapping_content(iid, "f"))
    manual_mapping["mapping_method"] = "MANUAL"
    weight = [_weight_content(iid, "0.040000000000")]
    snap = _mint_total_snapshot(session, tenant, exposure, covariance, [manual_mapping], weight)
    total_mv = _var_total_model(session, tenant)
    with pytest.raises(VarInputError):
        _run_total(session, tenant, total_mv, None, None, snapshot_id=snap.id)
    assert_no_running_orphan(session, run_type="VAR")


def test_residual_stdev_boundaries(session: Session) -> None:
    """The residual_stdev parse boundaries (2026-07 review fold — previously untested): a ZERO
    pinned residual is a legitimate accepted input contributing zero variance (the estimate said
    'no residual' — distinct from MANUAL's not-pinned-at-all); a NULL pin refuses; an
    envelope-hitting pin (exactly 1E8) refuses."""
    tenant = str(uuid.uuid4())
    fx_run, cov_run, _pf, insts = _seed_upstream_runs(session, tenant)
    iid = insts["I-USD"]
    total_mv = _var_total_model(session, tenant)

    # ZERO: accepted, zero contribution — sigma_total = sqrt(30000^2 * 1E-4) = 300 exactly.
    # (COMPLETES, so it reaches the pinned-provenance re-resolution — real run ids required.)
    exposure, covariance = _one_factor_pins(fx_run, iid, covariance_run_id=cov_run)
    snap = _mint_total_snapshot(
        session,
        tenant,
        exposure,
        covariance,
        [_mapping_content(iid, "f")],
        [_weight_content(iid, "0.000000000000")],
    )
    result = _run_total(session, tenant, total_mv, None, None, snapshot_id=snap.id)
    assert result.status == RunStatus.COMPLETED.value
    assert result.rows[0].residual_variance == Decimal(0)
    assert result.rows[0].sigma == Decimal("300.000000")

    # NULL: refused (a summary pinned without residual evidence is not a total-VaR input).
    exposure, covariance = _one_factor_pins(fx_run, iid)
    null_weight = _weight_content(iid, "0.040000000000")
    null_weight["residual_stdev"] = None
    snap = _mint_total_snapshot(
        session, tenant, exposure, covariance, [_mapping_content(iid, "f")], [null_weight]
    )
    with pytest.raises(VarInputError):
        _run_total(session, tenant, total_mv, None, None, snapshot_id=snap.id)
    assert_no_running_orphan(session, run_type="VAR")

    # ENVELOPE: exactly 1E8 (the strict PreciseDecimal(20,12) bound) refuses pre-create.
    exposure, covariance = _one_factor_pins(fx_run, iid)
    snap = _mint_total_snapshot(
        session,
        tenant,
        exposure,
        covariance,
        [_mapping_content(iid, "f")],
        [_weight_content(iid, "100000000.000000000000")],
    )
    with pytest.raises(VarInputError):
        _run_total(session, tenant, total_mv, None, None, snapshot_id=snap.id)
    assert_no_running_orphan(session, run_type="VAR")


def test_generically_minted_appraisal_days_zero_refused_at_bind(session: Session) -> None:
    """``appraisal_days=0`` minted via the GENERIC registration (the P3-4/HS review attack class —
    POST /models can stamp any assumptions) must refuse at BIND time with the fail-closed
    identity error, NOT surface later as a kernel non-positive-period FAILED run (2026-07 review,
    numeric + adversarial finders independently; the ``_hs_window_floor`` parse-time precedent)."""
    from irp_shared.model.service import register_model, register_model_version
    from irp_shared.risk import VAR_TOTAL_MODEL_CODE
    from irp_shared.risk.bootstrap import VAR_TOTAL_METHODOLOGY_REF, declared_appraisal_days

    tenant = str(uuid.uuid4())
    fx_run, cov_run, _pf, _insts = _seed_upstream_runs(session, tenant)
    model = register_model(
        session,
        tenant_id=tenant,
        code=VAR_TOTAL_MODEL_CODE,
        name="generic",
        model_type="VAR",
        actor_id="a",
    )
    version = register_model_version(
        session,
        model=model,
        version_label="v1",
        actor_id="a",
        methodology_ref=VAR_TOTAL_METHODOLOGY_REF,
        code_version="risk-v1",
        status="REGISTERED",
        assumptions=[
            "confidence_level=0.9500",
            "horizon_days=1",
            f"z_score={Z95}",
            "appraisal_days=0",
        ],
        limitations=[],
    )
    session.flush()
    with pytest.raises(WrongModelVersionError):
        declared_appraisal_days(session, version)
    with pytest.raises(WrongModelVersionError):
        _run_total(session, tenant, version.id, fx_run, cov_run)
    assert_no_running_orphan(session, run_type="VAR")


def test_migration_chain_0038(session: Session) -> None:
    """The PA-4 migration's chain position (every-slice pattern; the head bump itself is asserted
    across the 17 sibling files)."""
    import pathlib

    from alembic.config import Config
    from alembic.script import ScriptDirectory

    root = pathlib.Path(__file__).resolve().parents[3]
    cfg = Config(str(root / "alembic.ini"))
    cfg.set_main_option("script_location", str(root / "migrations"))
    script = ScriptDirectory.from_config(cfg)
    assert script.get_current_head() == "0045_pacing_projection"  # CC-2
    assert (
        script.get_revision("0038_var_residual_variance").down_revision
        == "0037_proxy_weight_estimate"
    )


# --------------------------------------------------------------------- BT-2: the estimate-age gate


def _legacy_total_v1_version(
    session: Session,
    tenant: str,
    *,
    extra_assumptions: tuple[str, ...] = (),
) -> str:
    """Mint a pre-BT-2 total ``v1`` version — a row declaring the PA-4 four parameters and NO
    ``max_estimate_age_days``. The BT-2 registrar mints only v2, so the grandfather is reproduced
    the way it genuinely exists in a tenant that registered before this slice: the model head +
    a REGISTERED version carrying the old assumption set."""
    from irp_shared.model.service import register_model_version, resolve_or_register_model
    from irp_shared.risk.bootstrap import (
        CONFIDENCE_ASSUMPTION_PREFIX,
        HORIZON_ASSUMPTION_PREFIX,
        VAR_MODEL_TYPE,
        VAR_TOTAL_MODEL_CODE,
        VAR_TOTAL_MODEL_NAME,
        Z_ASSUMPTION_PREFIX,
    )

    model = resolve_or_register_model(
        session,
        tenant_id=tenant,
        code=VAR_TOTAL_MODEL_CODE,
        name=VAR_TOTAL_MODEL_NAME,
        model_type=VAR_MODEL_TYPE,
        actor_id="legacy",
    )
    version = register_model_version(
        session,
        model=model,
        version_label="v1",  # the pre-BT-2 label
        actor_id="legacy",
        methodology_ref="05_analytics_methodologies/var_parametric_total_v1.md",
        code_version="risk-v1",
        status="REGISTERED",
        assumptions=(
            f"{CONFIDENCE_ASSUMPTION_PREFIX}0.9500",
            f"{HORIZON_ASSUMPTION_PREFIX}1",
            f"{Z_ASSUMPTION_PREFIX}{VAR_Z_SCORES['0.9500']}",
            f"{APPRAISAL_DAYS_ASSUMPTION_PREFIX}{APPRAISAL_DAYS}",
            *extra_assumptions,
        ),
    )
    session.flush()
    return version.id


def _aged_total_run(
    session: Session,
    tenant: str,
    *,
    span_end: date,
    max_age: int = MAX_ESTIMATE_AGE_DAYS,
):  # noqa: ANN202
    """Run a total VaR whose single cited estimate's regression span ends at ``span_end``. The
    run's own as-of is the pinned covariance ``window_end`` (D4), so the age the gate sees is
    ``(D4 - span_end).days``."""
    fx_run, cov_run, _pf, insts = _seed_upstream_runs(session, tenant)
    iid = insts["I-USD"]
    mv = _var_total_model(session, tenant, max_estimate_age_days=max_age)
    exposure, covariance = _one_factor_pins(fx_run, iid, covariance_run_id=cov_run)
    snap = _mint_total_snapshot(
        session,
        tenant,
        exposure,
        covariance,
        [_mapping_content(iid, "f")],
        [_weight_content(iid, "0.040000000000")],
        estimate_span_end=span_end,
    )
    return _run_total(session, tenant, mv, None, None, snapshot_id=snap.id)


def test_fresh_estimate_binds_and_echoes_age(session: Session) -> None:
    """A same-day estimate: the gate passes and the age is ECHOED as evidence (OD-BT-2-D)."""
    result = _aged_total_run(session, str(uuid.uuid4()), span_end=D4)
    assert result.status == RunStatus.COMPLETED.value
    assert result.rows[0].estimate_age_days == 0


def test_stale_estimate_refused_pre_create(session: Session) -> None:
    """An estimate older than the DECLARED policy refuses PRE-CREATE (422, zero run) — the
    staleness register item's mechanical half (OD-BT-2-C)."""
    tenant = str(uuid.uuid4())
    with pytest.raises(VarInputError, match="max_estimate_age_days"):
        _aged_total_run(session, tenant, span_end=D4 - timedelta(days=401), max_age=400)
    session.rollback()
    assert_no_running_orphan(session, run_type="VAR")


def test_estimate_age_boundary_is_strict(session: Session) -> None:
    """age == max PASSES (the gate is a strict >), age == max+1 refuses — the boundary pinned."""
    result = _aged_total_run(session, str(uuid.uuid4()), span_end=D4 - timedelta(days=400))
    assert result.status == RunStatus.COMPLETED.value
    assert result.rows[0].estimate_age_days == 400
    with pytest.raises(VarInputError):
        _aged_total_run(session, str(uuid.uuid4()), span_end=D4 - timedelta(days=401))


def test_look_ahead_estimate_passes_and_echoes_negative(session: Session) -> None:
    """A NEGATIVE age (the estimate's data ends AFTER this run's as-of — a look-ahead) PASSES: the
    ratified policy is a MAXIMUM age; a look-ahead gate is a different, unratified concern (the
    recorded limitation, decision record Part 3 item 5). It is echoed honestly."""
    result = _aged_total_run(session, str(uuid.uuid4()), span_end=D4 + timedelta(days=10))
    assert result.status == RunStatus.COMPLETED.value
    assert result.rows[0].estimate_age_days == -10


def test_echo_is_max_across_cited_estimates(session: Session) -> None:
    """Two proxied instruments with DIFFERENT estimate ages: the echo is the MAX (the binding
    constraint), not the mean/min."""
    tenant = str(uuid.uuid4())
    fx_run, cov_run, _pf, insts = _seed_upstream_runs(session, tenant)
    a, b = insts["I-USD"], insts["I-EUR"]
    mv = _var_total_model(session, tenant)
    exposure, covariance = _one_factor_pins(fx_run, a, covariance_run_id=cov_run)
    exposure = exposure + [_exposure_content(fx_run, "f", "F", b, "10000.000000")]
    older = _estimate_snapshot(session, tenant, D4 - timedelta(days=200))
    newer = _estimate_snapshot(session, tenant, D4 - timedelta(days=5))
    weights = [
        {
            **_weight_content(a, "0.040000000000", input_snapshot_id=older.id),
            "_keep_snapshot": True,
        },
        {
            **_weight_content(b, "0.030000000000", input_snapshot_id=newer.id),
            "_keep_snapshot": True,
        },
    ]
    snap = _mint_total_snapshot(
        session,
        tenant,
        exposure,
        covariance,
        [_mapping_content(a, "f"), _mapping_content(b, "f")],
        weights,
    )
    result = _run_total(session, tenant, mv, None, None, snapshot_id=snap.id)
    assert result.status == RunStatus.COMPLETED.value
    assert result.rows[0].estimate_age_days == 200  # the OLDER one binds


def test_zero_proxied_total_run_echoes_null_age(session: Session) -> None:
    """The byte-invariance case (no proxied instrument ⇒ total ≡ plain parametric): nothing to
    age, so the echo is NULL — max() over an empty set must not raise."""
    tenant = str(uuid.uuid4())
    fx_run, cov_run, _pf, insts = _seed_upstream_runs(session, tenant)
    mv = _var_total_model(session, tenant)
    exposure, covariance = _one_factor_pins(fx_run, insts["I-USD"], covariance_run_id=cov_run)
    snap = _mint_total_snapshot(session, tenant, exposure, covariance, [], [])
    result = _run_total(session, tenant, mv, None, None, snapshot_id=snap.id)
    assert result.status == RunStatus.COMPLETED.value
    assert result.rows[0].estimate_age_days is None
    assert result.rows[0].residual_variance == Decimal(0)


def test_gated_bind_refuses_unresolvable_estimate_snapshot(session: Session) -> None:
    """A GATED (v2) bind citing an estimation snapshot that is not visible cannot evaluate the
    declared policy ⇒ fail-closed refusal (OD-BT-2-C)."""
    tenant = str(uuid.uuid4())
    fx_run, cov_run, _pf, insts = _seed_upstream_runs(session, tenant)
    iid = insts["I-USD"]
    mv = _var_total_model(session, tenant)
    exposure, covariance = _one_factor_pins(fx_run, iid, covariance_run_id=cov_run)
    phantom = {**_weight_content(iid, "0.040000000000"), "_keep_snapshot": True}  # random id
    snap = _mint_total_snapshot(
        session, tenant, exposure, covariance, [_mapping_content(iid, "f")], [phantom]
    )
    with pytest.raises(VarInputError, match="not visible"):
        _run_total(session, tenant, mv, None, None, snapshot_id=snap.id)
    session.rollback()
    assert_no_running_orphan(session, run_type="VAR")


def test_ungated_v1_grandfather_binds_and_echoes(session: Session) -> None:
    """The recorded grandfather (OD-BT-2-C): a total version declaring NO max_estimate_age_days —
    an immutable pre-BT-2 v1 row — binds UNGATED (a years-stale estimate does NOT refuse) while
    the age is still ECHOED as evidence. Minted here the only way such a row can exist: the
    GENERIC registration path, then status-forced (the registrar itself mints only v2)."""
    tenant = str(uuid.uuid4())
    fx_run, cov_run, _pf, insts = _seed_upstream_runs(session, tenant)
    iid = insts["I-USD"]
    v1 = _legacy_total_v1_version(session, tenant)
    exposure, covariance = _one_factor_pins(fx_run, iid, covariance_run_id=cov_run)
    snap = _mint_total_snapshot(
        session,
        tenant,
        exposure,
        covariance,
        [_mapping_content(iid, "f")],
        [_weight_content(iid, "0.040000000000")],
        estimate_span_end=D4 - timedelta(days=3000),  # ~8 years stale
    )
    result = _run_total(session, tenant, v1, None, None, snapshot_id=snap.id)
    assert result.status == RunStatus.COMPLETED.value  # ungated: no new refusal
    assert result.rows[0].estimate_age_days == 3000  # but the staleness is VISIBLE


def test_declared_policy_duplicate_declaration_refuses(session: Session) -> None:
    """A version declaring the policy TWICE is ambiguous — fail-closed, never a silent ungate
    (the parse spec's asymmetry: absent -> ungated, ambiguous -> refuse)."""
    tenant = str(uuid.uuid4())
    version = _legacy_total_v1_version(
        session,
        tenant,
        extra_assumptions=(
            f"{MAX_ESTIMATE_AGE_ASSUMPTION_PREFIX}400",
            f"{MAX_ESTIMATE_AGE_ASSUMPTION_PREFIX}30",
        ),
    )
    from irp_shared.model.service import WrongModelVersionError

    with pytest.raises(WrongModelVersionError):
        declared_max_estimate_age_days(session, session.get(ModelVersion, version))


def test_var_result_pin_key_set_is_frozen() -> None:
    """The 0038 false-drift LANDMINE, now guarded (BT-2 plan Step 2): ``var_result_content`` pins
    the BT-1-era column set. Adding a key — ``residual_variance`` (PA-4) or ``estimate_age_days``
    (BT-2) — would change the recomputed bytes of every ALREADY-PINNED var_result component and
    make ``verify_snapshot`` report FALSE DRIFT on historical snapshots. Both columns are
    deliberately absent; this test fails loudly if a future slice "completes" the serializer."""
    from types import SimpleNamespace

    from irp_shared.snapshot.serialize import var_result_content

    row = SimpleNamespace(
        id=str(uuid.uuid4()),
        tenant_id=str(uuid.uuid4()),
        calculation_run_id=str(uuid.uuid4()),
        input_snapshot_id=str(uuid.uuid4()),
        model_version_id=str(uuid.uuid4()),
        exposure_run_id=str(uuid.uuid4()),
        covariance_run_id=None,
        metric_type=METRIC_TYPE_VAR_PARAMETRIC_TOTAL,
        base_currency="USD",
        confidence_level=Decimal("0.9500"),
        horizon_days=1,
        z_score=None,
        sigma=Decimal("1.000000"),
        var_value=Decimal("1.000000"),
        n_factors=1,
        n_observations=4,
        window_start=D1,
        window_end=D4,
        system_from=T0,
        residual_variance=Decimal("1.00000000000000000000"),  # present on the row...
        estimate_age_days=42,  # ...and so is the BT-2 echo
    )
    keys = set(var_result_content(row))
    assert "residual_variance" not in keys  # ...but NEITHER is pinned
    assert "estimate_age_days" not in keys
    assert keys == {
        "id",
        "tenant_id",
        "calculation_run_id",
        "input_snapshot_id",
        "model_version_id",
        "exposure_run_id",
        "covariance_run_id",
        "metric_type",
        "base_currency",
        "confidence_level",
        "horizon_days",
        "z_score",
        "sigma",
        "var_value",
        "n_factors",
        "n_observations",
        "window_start",
        "window_end",
        "system_from",
    }


def test_gated_bind_refuses_wrong_purpose_estimate_snapshot(session: Session) -> None:
    """REVIEW FOLD (two finders converged): the gate must check the cited header's PURPOSE, not
    just resolve it. Without this, a hand-minted pin citing a FRESH snapshot of some other kind
    (e.g. the run's own VAR_INPUT header) defeats a tight staleness policy — its
    as_of_valuation_date is not a regression span end at all."""
    tenant = str(uuid.uuid4())
    fx_run, cov_run, _pf, insts = _seed_upstream_runs(session, tenant)
    iid = insts["I-USD"]
    mv = _var_total_model(session, tenant, max_estimate_age_days=30)
    exposure, covariance = _one_factor_pins(fx_run, iid, covariance_run_id=cov_run)
    # A VAR_INPUT-purpose snapshot dated yesterday — fresh, real, resolvable, and WRONG.
    decoy = _mint_total_snapshot(session, tenant, exposure, covariance, [], [])
    weight = {
        **_weight_content(iid, "0.040000000000", input_snapshot_id=decoy.id),
        "_keep_snapshot": True,
    }
    snap = _mint_total_snapshot(
        session, tenant, exposure, covariance, [_mapping_content(iid, "f")], [weight]
    )
    with pytest.raises(VarInputError, match="purpose"):
        _run_total(session, tenant, mv, None, None, snapshot_id=snap.id)
    session.rollback()
    assert_no_running_orphan(session, run_type="VAR")


def test_ungated_partial_resolve_echoes_null_not_subset_max(session: Session) -> None:
    """REVIEW FOLD: on an UNGATED (v1) bind where SOME cited estimate is unmeasurable, the echo is
    NULL — never the max over the resolvable subset. A subset max reads as a confident number and
    UNDERSTATES staleness: a validator triaging v1 via VW-1's sunset lever would see "30 days"
    while an unmeasured sibling could be years stale. UNKNOWN outranks any known max."""
    tenant = str(uuid.uuid4())
    fx_run, cov_run, _pf, insts = _seed_upstream_runs(session, tenant)
    a, b = insts["I-USD"], insts["I-EUR"]
    v1 = _legacy_total_v1_version(session, tenant)  # ungated grandfather
    exposure, covariance = _one_factor_pins(fx_run, a, covariance_run_id=cov_run)
    exposure = exposure + [_exposure_content(fx_run, "f", "F", b, "10000.000000")]
    resolvable = _estimate_snapshot(session, tenant, D4 - timedelta(days=30))
    weights = [
        {
            **_weight_content(a, "0.040000000000", input_snapshot_id=resolvable.id),
            "_keep_snapshot": True,
        },
        # B cites a snapshot that does not exist -> unmeasurable.
        {**_weight_content(b, "0.030000000000"), "_keep_snapshot": True},
    ]
    snap = _mint_total_snapshot(
        session,
        tenant,
        exposure,
        covariance,
        [_mapping_content(a, "f"), _mapping_content(b, "f")],
        weights,
    )
    result = _run_total(session, tenant, v1, None, None, snapshot_id=snap.id)
    assert result.status == RunStatus.COMPLETED.value  # ungated: still no new refusal
    assert result.rows[0].estimate_age_days is None  # NOT 30 — the honest answer is "unknown"


# ---------- (12) ES-1: the ES-TOTAL leg over THIS chain ----------
#
# ES_total = k_c * sigma_total, over the exact same hand reference as the total-VaR golden above —
# so this golden inherits an exactly-known sigma_total (522.41739749519396280801883332...) and the
# assertion is a hand-derived k*sigma, not a fixture echo:
#:   k_0.95 * sigma_total = 1077.5970566778119285632... -> 1077.597057 @6dp
REF_ES95_TOTAL = Decimal("1077.597057")


def _var_es_total_model(
    db: Session,
    tenant: str,
    *,
    code_version: str = "risk-v1",
    confidence: str = "0.95",
    appraisal_days: int = APPRAISAL_DAYS,
    max_estimate_age_days: int = MAX_ESTIMATE_AGE_DAYS,
) -> str:
    from irp_shared.risk import register_var_parametric_es_total_model

    return register_var_parametric_es_total_model(
        db,
        tenant_id=tenant,
        actor_id="analyst",
        code_version=code_version,
        confidence_level=confidence,
        appraisal_days=appraisal_days,
        max_estimate_age_days=max_estimate_age_days,
    ).id


def _total_chain_snapshot(db: Session, tenant: str, seeded=None):  # noqa: ANN001, ANN202
    """The hand reference, minted under the TOTAL predicate: REF1's 3-4-5 triangle + ONE proxied
    instrument with a known residual_stdev.

    ``seeded`` reuses an existing ``_seed_upstream_runs`` result — that seeder captures FX rows
    that are UNIQUE per (tenant, pair, date), so calling it twice for one tenant is an
    IntegrityError. Pass it through when a test needs two snapshots over the same chain.
    """
    fx_run, cov_run, _pf, insts = seeded if seeded is not None else _seed_upstream_runs(db, tenant)
    iid_usd, iid_eur = insts["I-USD"], insts["I-EUR"]
    fa, fb = str(uuid.uuid4()).lower(), str(uuid.uuid4()).lower()
    snap = _mint_total_snapshot(
        db,
        tenant,
        [
            _exposure_content(fx_run, fa, "A", iid_usd, "30000.000000"),
            _exposure_content(fx_run, fb, "B", iid_eur, "40000.000000"),
        ],
        [
            _covariance_content(cov_run, fa, fa, "0.00010000000000000000"),
            _covariance_content(cov_run, fb, fb, "0.00010000000000000000"),
            _covariance_content(cov_run, fa, fb, "0E-20"),
        ],
        [_mapping_content(iid_usd, fa)],
        [_weight_content(iid_usd, str(RESIDUAL_STDEV))],
    )
    return snap, fx_run, cov_run


def test_es_total_exact_hand_reference_via_consume_path(session: Session) -> None:
    from irp_shared.risk import METRIC_TYPE_ES_PARAMETRIC

    tenant = str(uuid.uuid4())
    snap, fx_run, cov_run = _total_chain_snapshot(session, tenant)
    mv = _var_es_total_model(session, tenant)
    result = _run_total(session, tenant, mv, None, None, snapshot_id=snap.id)
    assert result.status == RunStatus.COMPLETED.value and len(result.rows) == 1
    row = result.rows[0]
    assert row.metric_type == METRIC_TYPE_ES_PARAMETRIC  # ONE value for BOTH ES families
    assert row.sigma == REF_SIGMA_TOTAL  # the SAME sigma_total the total-VaR family computes
    assert row.var_value == REF_ES95_TOTAL  # ...times the registered k, quantized once
    # The residual leg + BT-2's age echo ride the ES-total row exactly as they ride the total-VaR
    # row — PA-4's machinery and BT-2's gate are reused verbatim, not reimplemented.
    assert row.residual_variance == REF_RESIDUAL_VARIANCE
    assert row.estimate_age_days is not None
    assert row.exposure_run_id == fx_run and row.covariance_run_id == cov_run


def test_es_total_is_the_multiplier_over_the_same_sigma_as_total_var(session: Session) -> None:
    # The two families over the SAME hand reference: identical sigma_total + residual_variance,
    # different multiplier. Pins that the ES-total leg reuses PA-4's residual machinery rather
    # than recomputing it, and that ES > VaR at the row level for this (sigma > 0) fixture.
    tenant = str(uuid.uuid4())
    seeded = _seed_upstream_runs(session, tenant)  # ONE seed; two snapshots over the same chain
    var_snap, _, _ = _total_chain_snapshot(session, tenant, seeded)
    var_row = _run_total(
        session, tenant, _var_total_model(session, tenant), None, None, snapshot_id=var_snap.id
    ).rows[0]
    es_snap, _, _ = _total_chain_snapshot(session, tenant, seeded)
    es_row = _run_total(
        session, tenant, _var_es_total_model(session, tenant), None, None, snapshot_id=es_snap.id
    ).rows[0]
    assert es_row.sigma == var_row.sigma == REF_SIGMA_TOTAL
    assert es_row.residual_variance == var_row.residual_variance == REF_RESIDUAL_VARIANCE
    assert var_row.var_value == REF_VAR95_TOTAL and es_row.var_value == REF_ES95_TOTAL
    assert es_row.var_value > var_row.var_value


def _aged_es_total_run(
    session: Session,
    tenant: str,
    *,
    span_end: date,
    max_age: int = MAX_ESTIMATE_AGE_DAYS,
):  # noqa: ANN202
    """The `_aged_total_run` harness on the ES-TOTAL family: the run's as-of is the pinned
    covariance ``window_end`` (D4), so the age the gate sees is ``(D4 - span_end).days``."""
    fx_run, cov_run, _pf, insts = _seed_upstream_runs(session, tenant)
    iid = insts["I-USD"]
    mv = _var_es_total_model(session, tenant, max_estimate_age_days=max_age)
    exposure, covariance = _one_factor_pins(fx_run, iid, covariance_run_id=cov_run)
    snap = _mint_total_snapshot(
        session,
        tenant,
        exposure,
        covariance,
        [_mapping_content(iid, "f")],
        [_weight_content(iid, "0.040000000000")],
        estimate_span_end=span_end,
    )
    return _run_total(session, tenant, mv, None, None, snapshot_id=snap.id)


def test_es_total_staleness_gate_is_inherited_from_bt2(session: Session) -> None:
    # BT-2's gate is REUSED, not reimplemented: a cited estimate older than the DECLARED policy
    # refuses PRE-CREATE with zero run on the ES-total family exactly as on the total-VaR one,
    # and a fresh one binds with the age echoed. Same boundary semantics (a strict >).
    fresh = _aged_es_total_run(session, str(uuid.uuid4()), span_end=D4 - timedelta(days=400))
    assert fresh.status == RunStatus.COMPLETED.value
    assert fresh.rows[0].estimate_age_days == 400  # age == max PASSES

    tenant = str(uuid.uuid4())
    with pytest.raises(VarInputError, match="max_estimate_age_days"):
        _aged_es_total_run(session, tenant, span_end=D4 - timedelta(days=401), max_age=400)
    session.rollback()
    assert_no_running_orphan(session, run_type="VAR")


def test_es_total_absent_max_age_declaration_refuses_by_construction(session: Session) -> None:
    # The ES-total code is BORN with the declaration, so — unlike BT-2's grandfathered total-VaR
    # v1 — no legitimate ungated version can exist and an absent declaration must REFUSE rather
    # than degrade to ungated. Minted via the generic path (the real threat model).
    from irp_shared.model.models import ModelVersion
    from irp_shared.model.service import register_model, register_model_version
    from irp_shared.risk import ES_TOTAL_MODEL_CODE, VAR_ES_MULTIPLIERS, VAR_Z_SCORES
    from irp_shared.risk.bootstrap import declared_es_total_max_estimate_age_days

    tenant = str(uuid.uuid4())
    model = register_model(
        session,
        tenant_id=tenant,
        code=ES_TOTAL_MODEL_CODE,
        name="generic",
        model_type="VAR",
        actor_id="a",
    )
    version = register_model_version(
        session,
        model=model,
        version_label="v1",
        actor_id="a",
        methodology_ref="05_analytics_methodologies/var_parametric_es_v1.md",
        code_version="risk-v1",
        status="REGISTERED",
        assumptions=[
            "confidence_level=0.9500",
            "horizon_days=1",
            f"z_score={VAR_Z_SCORES['0.9500']}",
            f"es_multiplier={VAR_ES_MULTIPLIERS['0.9500']}",
            f"appraisal_days={APPRAISAL_DAYS}",
            # NO max_estimate_age_days — ungated on the total-VaR family, REFUSED here.
        ],
    )
    resolved = session.get(ModelVersion, version.id)
    assert resolved is not None
    with pytest.raises(WrongModelVersionError):
        declared_es_total_max_estimate_age_days(session, resolved)
