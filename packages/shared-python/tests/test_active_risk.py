"""SQLite-local unit/behavior tests for P3-7 ex-ante active risk (the sixth governed RISK number
and the second DERIVED-OF-DERIVED one; ENT-027 `risk_result` realized as `active_risk_result`).

RLS is a no-op on SQLite (FORCE-RLS isolation + the P0001 trigger live in ``test_active_risk_pg``);
here we prove: the pure kernel against **hand-computed exact references** (``TE = √(wₐᵀΣwₐ)``:
active weights (0.03, 0.04) over uncorrelated 1E-4-variance factors => TE = 0.0005 exactly; fully
correlated => 0.0007; a benchmark-matching book => TE 0) + positive-homogeneity + the non-PSD /
tiny-negative clamp regimes; the ``code_version``-only model identity (OD-P3-7-D — no numeric
parameter; a same-label re-register with a different ``code_version`` is a 409; a generic-minted
twin is a WrongModelVersionError); the four-kind snapshot consumption + the active-weight
construction + COVERAGE / NULL-or-unmappable-currency / non-positive-Σweight / zero-book
adjudication (fail-closed, both entry paths, NO imputation); the exact hand-reference tracking
error **through the full governed consume path** (a hand-minted ACTIVE_RISK_INPUT snapshot,
TE = 0.007211102551); the REACHABLE non-PSD radicand FAILED path; exact re-run + pin invariance
under upstream RE-RUNS **and a benchmark restatement**; CALC.RUN_* audit (+ NO RISK.* code);
lineage; the append-only ORM guard; entitlement REUSE parity; the methodology doc; the load-bearing
scope fences; and the migration head.
"""

from __future__ import annotations

import ast
import json
import math
import pathlib
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from irp_shared.audit.models import AppendOnlyViolation, AuditEvent
from irp_shared.calc.models import CalculationRun, RunStatus
from irp_shared.db.session import make_engine, make_session_factory
from irp_shared.entitlement.bootstrap import ROLE_TEMPLATES, SYSTEM_TENANT_ID
from irp_shared.exposure import ExposureActor, run_exposure
from irp_shared.lineage.models import (
    EDGE_KIND_ORIGIN,
    SOURCE_TYPE_CALCULATION_RUN,
    LineageEdge,
)
from irp_shared.marketdata import FxRateActor, capture_fx_rate
from irp_shared.marketdata.benchmark import (
    BenchmarkActor,
    ConstituentInput,
    capture_benchmark,
    capture_membership,
    resolve_benchmark,
    supersede_membership,
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
    ACTIVE_RISK_METHODOLOGY_REF,
    ActiveRiskActor,
    ActiveRiskInputError,
    ActiveRiskKernelError,
    ActiveRiskResult,
    CovarianceActor,
    FactorExposureActor,
    ModelVersionConflictError,
    WrongModelVersionError,
    compute_tracking_error,
    list_active_risks,
    register_active_risk_model,
    register_covariance_model,
    register_factor_exposure_model,
    run_active_risk,
    run_covariance,
    run_factor_exposure,
)
from irp_shared.snapshot import (
    COMPONENT_KIND_BENCHMARK,
    COMPONENT_KIND_COVARIANCE,
    COMPONENT_KIND_FACTOR,
    COMPONENT_KIND_FACTOR_EXPOSURE,
    PURPOSE_ACTIVE_RISK_INPUT,
    ActiveRiskSnapshotError,
    SnapshotActor,
    list_components,
    resolve_snapshot,
    verify_snapshot,
)
from irp_shared.valuation import create_valuation
from irp_shared.valuation.service import ValuationActor

T0 = datetime(2026, 1, 1, tzinfo=UTC)
VALID_AT = datetime(2026, 6, 1, tzinfo=UTC)
KNOWN_AT = datetime(2030, 1, 1, tzinfo=UTC)
VD = date(2026, 6, 1)
D1, D2, D3, D4 = (date(2026, 5, 26), date(2026, 5, 27), date(2026, 5, 28), date(2026, 5, 29))
ACTOR = ActiveRiskActor(actor_id="analyst")

#: HAND REFERENCE (exact): active weights w_a = (0.2, -0.2) over uncorrelated factors with variance
#: 4E-4 (a) and 9E-4 (b): radicand = 0.04*4E-4 + 0.04*9E-4 = 5.2E-5 => TE = 0.007211102551 @12dp.
#: Built through the consume path from portfolio (700/300 => w_p 0.7/0.3) minus benchmark (0.5/0.5).
REF_TE = Decimal("0.007211102551")
#: KERNEL REFERENCES: w = (0.03, 0.04) over 1E-4-variance factors; uncorrelated => TE 0.0005 exact,
#: fully correlated => 0.0007 (radicand 4.9E-7).
KREF_DIAG = Decimal("0.000500000000")
KREF_FULL = Decimal("0.000700000000")


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


def _cov(pairs: dict[tuple[str, str], str]) -> dict[tuple[str, str], Decimal]:
    return {k: Decimal(v) for k, v in pairs.items()}


_KW = _cov({("a", "a"): "0.0001", ("b", "b"): "0.0001"})
_DIAG_COV = _KW | _cov({("a", "b"): "0"})
_FULL_CORR_COV = _KW | _cov({("a", "b"): "0.0001"})
_KWEIGHTS = {"a": Decimal("0.03"), "b": Decimal("0.04")}


# ---------- (1) pure kernel — exact hand references ----------


def test_kernel_hand_reference_diagonal() -> None:
    est = compute_tracking_error(_KWEIGHTS, _DIAG_COV)
    assert est.te_value == KREF_DIAG


def test_kernel_hand_reference_full_correlation() -> None:
    est = compute_tracking_error(_KWEIGHTS, _FULL_CORR_COV)
    assert est.te_value == KREF_FULL


def test_kernel_benchmark_match_is_te_zero() -> None:
    # A book that matches its benchmark has w_a = 0 => ZERO active risk (a VALID number, not error).
    est = compute_tracking_error({"a": Decimal("0"), "b": Decimal("0")}, _DIAG_COV)
    assert est.te_value == Decimal("0.000000000000")


def test_kernel_positive_homogeneity() -> None:
    # TE is homogeneous degree 1 in the active weights: doubling w_a doubles TE.
    base = compute_tracking_error(_KWEIGHTS, _DIAG_COV).te_value
    doubled = compute_tracking_error({k: v * 2 for k, v in _KWEIGHTS.items()}, _DIAG_COV).te_value
    assert doubled == (base * 2).quantize(Decimal("1E-12"))


def test_kernel_order_and_case_invariance() -> None:
    a = compute_tracking_error({"A": Decimal("0.03"), "B": Decimal("0.04")}, _DIAG_COV)
    b = compute_tracking_error({"b": Decimal("0.04"), "a": Decimal("0.03")}, _DIAG_COV)
    assert a.te_value == b.te_value == KREF_DIAG


def test_kernel_offsetting_signs_matter() -> None:
    # With correlation, a long/short active book differs from long/long (the cross term flips sign).
    long_long = compute_tracking_error(_KWEIGHTS, _FULL_CORR_COV).te_value
    long_short = compute_tracking_error(
        {"a": Decimal("0.03"), "b": Decimal("-0.04")}, _FULL_CORR_COV
    ).te_value
    assert long_short < long_long  # offsetting active bets reduce tracking error


#: OFFSETTING active weights (along the (1,-1) eigenvector): needed to probe the negative-radicand
#: regimes — a purely long active book over a PSD-in-that-direction matrix is always non-negative.
_OFFSET = {"a": Decimal("0.04"), "b": Decimal("-0.04")}


def test_kernel_non_psd_radicand_returns_defect() -> None:
    # Σ = [[1E-4, 0.01],[0.01, 1E-4]] is non-PSD (eigenvalue 1E-4 - 0.01 < 0); an active book along
    # that eigenvector drives w_a' Σ w_a well below the tolerance floor -> te_value None.
    bad = _cov({("a", "a"): "0.0001", ("b", "b"): "0.0001", ("a", "b"): "0.01"})
    est = compute_tracking_error(_OFFSET, bad)
    assert est.te_value is None and est.radicand < -est.tolerance


def test_kernel_tiny_negative_radicand_clamps_to_zero() -> None:
    # cov just 1E-20 above the variance (a 20dp storage artifact): the offsetting active book yields
    # a radicand within [-tol, 0) -> the declared clamp -> TE 0, not a defect.
    tiny = _cov({("a", "a"): "0.0001", ("b", "b"): "0.0001", ("a", "b"): "0.00010000000000000001"})
    est = compute_tracking_error(_OFFSET, tiny)
    assert est.radicand < 0 and est.te_value == Decimal("0.000000000000")


def test_kernel_ill_formed_inputs_raise() -> None:
    with pytest.raises(ActiveRiskKernelError):
        compute_tracking_error({}, _DIAG_COV)  # empty vector
    with pytest.raises(ActiveRiskKernelError):
        compute_tracking_error(_KWEIGHTS, _cov({("a", "a"): "0.0001"}))  # missing pair
    with pytest.raises(ActiveRiskKernelError):
        compute_tracking_error({"a": Decimal("0.1"), "A": Decimal("0.2")}, _DIAG_COV)  # dup key


# ---------- (2) model registration (code_version identity — OD-P3-7-D) ----------


def _model(db: Session, tenant: str, code_version: str = "risk-v1") -> str:
    return register_active_risk_model(
        db, tenant_id=tenant, actor_id="analyst", code_version=code_version
    ).id


def test_model_registered_with_methodology_ref(session: Session) -> None:
    tenant = str(uuid.uuid4())
    mv_id = _model(session, tenant)
    version = session.get(ModelVersion, mv_id)
    assert version is not None
    assert version.methodology_ref == ACTIVE_RISK_METHODOLOGY_REF
    assert version.code_version == "risk-v1" and version.status == "REGISTERED"


def test_register_idempotent_and_identity_conflict(session: Session) -> None:
    tenant = str(uuid.uuid4())
    first = _model(session, tenant)
    assert _model(session, tenant) == first  # idempotent (same code_version)
    with pytest.raises(ModelVersionConflictError):
        _model(session, tenant, code_version="risk-v2")  # same label, different code_version


def test_generic_minted_twin_is_identity_refusal(session: Session) -> None:
    # A same-label 'risk.active_risk.parametric' v1 minted via the GENERIC registration (status
    # None) is a REGISTRATION conflict (the P3-C1 register/run-consistency lesson), not adopted.
    from irp_shared.model.service import register_model, register_model_version
    from irp_shared.risk import ACTIVE_RISK_MODEL_CODE

    tenant = str(uuid.uuid4())
    model = register_model(
        session,
        tenant_id=tenant,
        code=ACTIVE_RISK_MODEL_CODE,
        name="generic",
        model_type="ACTIVE_RISK",
        actor_id="a",
    )
    register_model_version(
        session,
        model=model,
        version_label="v1",
        actor_id="a",
        methodology_ref="x",
        code_version="risk-v1",
        status=None,  # generic-minted, NOT REGISTERED
        assumptions=[],
        limitations=[],
    )
    session.flush()
    with pytest.raises(WrongModelVersionError):
        register_active_risk_model(session, tenant_id=tenant, actor_id="a", code_version="risk-v1")


# ---------- full-stack fixtures (two upstream governed runs + a captured benchmark) ----------


def _seed_upstream_runs(db: Session, tenant: str) -> tuple[str, str, list[str]]:
    """Seed the FULL upstream chain -> a COMPLETED factor-exposure run (x = 30000 USD-factor +
    40000 EUR-factor, base USD) + a COMPLETED covariance run over the same factors. Returns
    (factor_exposure_run_id, covariance_run_id, factor_ids)."""
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
    from irp_shared.marketdata.models import FxRate

    if (
        db.execute(
            select(FxRate).where(FxRate.tenant_id == tenant, FxRate.base_currency == "EUR")
        ).scalar_one_or_none()
        is None
    ):
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
    # Assert the WHOLE upstream chain COMPLETED with the expected row grain (parity with the VaR
    # fixture — a silently-FAILED or wrong-cardinality upstream must fail the fixture, not a
    # downstream numeric assert, review V22).
    assert exposure.status == RunStatus.COMPLETED.value
    assert fx_run.status == RunStatus.COMPLETED.value and len(fx_run.rows) == 2
    assert cov_run.status == RunStatus.COMPLETED.value and len(cov_run.rows) == 3
    return fx_run.run.run_id, cov_run.run.run_id, factor_ids


def _seed_benchmark(
    db: Session,
    tenant: str,
    *,
    weights: tuple[str, str] = ("0.60", "0.40"),
    currencies: tuple[str | None, str | None] = ("USD", "EUR"),
    effective_date: date = D4,
) -> str:
    """Capture a benchmark + one (benchmark, effective_date) membership of two constituents in the
    given currencies (default USD/EUR — the covariance factor currencies). Returns benchmark_id."""
    bm = capture_benchmark(
        db,
        benchmark_code=f"BM-{uuid.uuid4().hex[:6]}",
        benchmark_source="VENDOR_B",
        benchmark_currency="USD",
        acting_tenant=tenant,
        actor=BenchmarkActor(actor_id="s"),
        valid_from=T0,
    )
    constituents: list[ConstituentInput] = []
    for w, ccy in zip(weights, currencies, strict=True):
        inst = create_instrument(
            db,
            tenant_id=tenant,
            code=f"BM-I-{uuid.uuid4().hex[:6]}",
            name="bmi",
            asset_class="EQUITY",
            actor=ReferenceActor(actor_id="s"),
        ).id
        constituents.append(
            ConstituentInput(instrument_id=inst, weight=Decimal(w), constituent_currency=ccy)
        )
    capture_membership(
        db,
        bm,
        effective_date=effective_date,
        constituents=constituents,
        acting_tenant=tenant,
        actor=BenchmarkActor(actor_id="s"),
        valid_from=T0,
    )
    db.flush()
    return bm.id


def _run(db: Session, tenant: str, mv: str, **kw):  # noqa: ANN202
    return run_active_risk(
        db,
        acting_tenant=tenant,
        actor=ACTOR,
        code_version="risk-v1",
        environment_id="ci",
        model_version_id=mv,
        **kw,
    )


def _build(db: Session, tenant: str, mv: str, fx_run: str, cov_run: str, bm_id: str, **kw):  # noqa: ANN202
    return _run(
        db,
        tenant,
        mv,
        exposure_run_id=fx_run,
        covariance_run_id=cov_run,
        benchmark_id=bm_id,
        benchmark_effective_date=D4,
        **kw,
    )


def _count_runs(db: Session, tenant: str) -> int:
    return db.execute(
        select(func.count())
        .select_from(CalculationRun)
        .where(CalculationRun.tenant_id == tenant, CalculationRun.run_type == "ACTIVE_RISK")
    ).scalar_one()


def _count_results(db: Session, tenant: str) -> int:
    return db.execute(
        select(func.count())
        .select_from(ActiveRiskResult)
        .where(ActiveRiskResult.tenant_id == tenant)
    ).scalar_one()


# ---------- (3) positive correctness (full stack) ----------


def test_full_stack_build_path_bindings_and_numpy_agreement(session: Session) -> None:
    import numpy as np

    tenant = str(uuid.uuid4())
    fx_run, cov_run, _fids = _seed_upstream_runs(session, tenant)
    bm_id = _seed_benchmark(session, tenant)
    mv = _model(session, tenant)
    result = _build(session, tenant, mv, fx_run, cov_run, bm_id)
    assert result.status == RunStatus.COMPLETED.value and len(result.rows) == 1
    row = result.rows[0]
    assert row.metric_type == "TRACKING_ERROR"
    assert row.base_currency == "USD"
    assert row.factor_exposure_run_id == fx_run and row.covariance_run_id == cov_run
    assert row.benchmark_id == bm_id and row.benchmark_effective_date == D4
    assert row.n_factors == 2 and row.n_constituents == 2
    assert row.portfolio_value == Decimal("70000.000000")
    assert row.calculation_run_id == result.run.run_id
    assert row.input_snapshot_id == result.run.input_snapshot_id
    # Independent float recomputation of TE from the PINNED snapshot content (numpy cross-check):
    # build w_a = w_p - w_b over the currency-factor partition, then sqrt(w_a' Σ w_a).
    comps = list_components(session, snapshot_id=row.input_snapshot_id, acting_tenant=tenant)
    ccy_to_fid: dict[str, str] = {}
    exp_by_fid: dict[str, float] = {}
    bench_by_ccy: dict[str, float] = {}
    cov: dict[tuple[str, str], float] = {}
    for c in comps:
        d = json.loads(c.captured_content)
        if c.component_kind == COMPONENT_KIND_FACTOR:
            ccy_to_fid[d["currency_code"]] = d["id"]
        elif c.component_kind == COMPONENT_KIND_FACTOR_EXPOSURE:
            exp_by_fid[d["factor_id"]] = exp_by_fid.get(d["factor_id"], 0.0) + float(
                d["exposure_amount"]
            )
        elif c.component_kind == COMPONENT_KIND_COVARIANCE:
            cov[(d["factor_id_1"], d["factor_id_2"])] = float(d["covariance_value"])
        elif c.component_kind == COMPONENT_KIND_BENCHMARK:
            bench_by_ccy[d["constituent_currency"]] = bench_by_ccy.get(
                d["constituent_currency"], 0.0
            ) + float(d["weight"])
    pv = sum(exp_by_fid.values())
    total_w = sum(bench_by_ccy.values())
    ids = sorted(set(exp_by_fid) | {ccy_to_fid[c] for c in bench_by_ccy})
    wp = {fid: exp_by_fid.get(fid, 0.0) / pv for fid in ids}
    wb = {ccy_to_fid[c]: bench_by_ccy[c] / total_w for c in bench_by_ccy}
    wa = np.array([wp.get(fid, 0.0) - wb.get(fid, 0.0) for fid in ids])
    mat = np.array([[cov[tuple(sorted((r, c)))] for c in ids] for r in ids])
    want = math.sqrt(float(wa @ mat @ wa))
    assert abs(float(row.te_value) - want) <= 1e-9 * max(want, 1e-12)
    v = verify_snapshot(session, snapshot_id=row.input_snapshot_id, acting_tenant=tenant)
    assert v.ok  # IA-row + FR-version pins are byte-stable


def _factor_content(fid: str, code: str, ccy: str) -> dict:
    return {
        "id": fid,
        "tenant_id": str(uuid.uuid4()),
        "factor_code": code,
        "factor_source": "VENDOR_F",
        "factor_family": "CURRENCY",
        "factor_type": "RISK",
        "region": None,
        "currency_code": ccy,
        "asset_class": None,
        "frequency": "DAILY",
        "factor_name": code,
        "description": None,
        "valid_from": T0.isoformat(),
        "record_version": 1,
    }


def _exposure_content(run_id: str, fid: str, code: str, amount: str, base: str = "USD") -> dict:
    return {
        "id": str(uuid.uuid4()),
        "tenant_id": str(uuid.uuid4()),
        "calculation_run_id": run_id,
        "input_snapshot_id": str(uuid.uuid4()),
        "model_version_id": str(uuid.uuid4()),
        "system_from": T0.isoformat(),
        "portfolio_id": str(uuid.uuid4()),
        "instrument_id": str(uuid.uuid4()),
        "factor_id": fid,
        "factor_code": code,
        "factor_family": "CURRENCY",
        "base_currency": base,
        "mark_currency": base,
        "loading": "1.000000000000",
        "exposure_amount": amount,
    }


def _covariance_content(run_id: str, f1: str, f2: str, value: str, n: int = 4) -> dict:
    a, b = sorted((f1, f2))
    return {
        "id": str(uuid.uuid4()),
        "tenant_id": str(uuid.uuid4()),
        "calculation_run_id": run_id,
        "input_snapshot_id": str(uuid.uuid4()),
        "model_version_id": str(uuid.uuid4()),
        "system_from": T0.isoformat(),
        "factor_id_1": a,
        "factor_id_2": b,
        "factor_code_1": "F1",
        "factor_code_2": "F2",
        "statistic_type": "COVARIANCE",
        "return_type": "SIMPLE",
        "frequency": "DAILY",
        "n_observations": n,
        "window_start": D1.isoformat(),
        "window_end": D4.isoformat(),
        "covariance_value": value,
    }


def _benchmark_content(bm_id: str, ccy: str | None, weight: str, ed: date = D4) -> dict:
    return {
        "id": str(uuid.uuid4()),
        "tenant_id": str(uuid.uuid4()),
        "benchmark_id": bm_id,
        "benchmark_code": "BM",
        "benchmark_source": "VENDOR_B",
        "benchmark_currency": "USD",
        "effective_date": ed.isoformat(),
        "instrument_id": str(uuid.uuid4()),
        "weight": weight,
        "constituent_currency": ccy,
        "valid_from": T0.isoformat(),
        "system_from": T0.isoformat(),
        "record_version": 1,
    }


def _mint_snapshot(
    session: Session,
    tenant: str,
    *,
    exposure_rows: list[dict],
    covariance_rows: list[dict],
    factor_rows: list[dict],
    benchmark_rows: list[dict],
    purpose: str = PURPOSE_ACTIVE_RISK_INPUT,
):  # noqa: ANN202
    """Hand-mint an ACTIVE_RISK_INPUT snapshot with ARBITRARY pinned content (bypassing the governed
    builder) — the adjudication-gate probe AND the exact-hand-reference consume-path vehicle."""
    from irp_shared.snapshot.service import _append_spec, _persist_snapshot

    specs: list = []
    kinds = (
        (COMPONENT_KIND_FACTOR_EXPOSURE, "factor_exposure_result", exposure_rows),
        (COMPONENT_KIND_COVARIANCE, "covariance_result", covariance_rows),
        (COMPONENT_KIND_FACTOR, "factor", factor_rows),
        (COMPONENT_KIND_BENCHMARK, "benchmark_constituent", benchmark_rows),
    )
    for kind, ent, rows in kinds:
        for content in rows:
            content = dict(content)
            anchor_id = content.pop("_anchor", None) or content["id"]
            anchor = SimpleNamespace(
                id=anchor_id, valid_from=None, system_from=T0, record_version=None
            )
            _append_spec(specs, kind, ent, anchor, content)
    header = _persist_snapshot(
        session,
        acting_tenant=tenant,
        actor=SnapshotActor(actor_id="s"),
        specs=specs,
        label="",
        purpose=purpose,
        as_of_valid_at=VALID_AT,
        as_of_known_at=VALID_AT,
        as_of_valuation_date=D4,
        binding_predicate_version="test:hand-minted",
    )
    session.flush()
    return header


def _ref_snapshot(session: Session, tenant: str, exp_run: str, cov_run: str, bm_id: str):  # noqa: ANN202
    """The exact 0.007211102551 reference construction: w_p (0.7, 0.3) minus w_b (0.5, 0.5) =>
    w_a (0.2, -0.2) over uncorrelated factors var 4E-4 / 9E-4."""
    fa, fb = str(uuid.uuid4()).lower(), str(uuid.uuid4()).lower()
    return _mint_snapshot(
        session,
        tenant,
        exposure_rows=[
            _exposure_content(exp_run, fa, "A", "700.000000"),
            _exposure_content(exp_run, fb, "B", "300.000000"),
        ],
        covariance_rows=[
            _covariance_content(cov_run, fa, fa, "0.00040000000000000000"),
            _covariance_content(cov_run, fb, fb, "0.00090000000000000000"),
            _covariance_content(cov_run, fa, fb, "0E-20"),
        ],
        factor_rows=[_factor_content(fa, "A", "USD"), _factor_content(fb, "B", "EUR")],
        benchmark_rows=[
            _benchmark_content(bm_id, "USD", "0.500000000000"),
            _benchmark_content(bm_id, "EUR", "0.500000000000"),
        ],
    ), (fa, fb)


def test_full_stack_exact_hand_reference_via_consume_path(session: Session) -> None:
    # The exact 0.2/-0.2 reference THROUGH the governed consume path. The pinned provenance run ids
    # + benchmark id must be REAL own-tenant COMPLETED runs / a visible benchmark (re-resolved
    # before they reach the hard-FK columns).
    tenant = str(uuid.uuid4())
    exp_run, cov_run, _fids = _seed_upstream_runs(session, tenant)
    bm_id = _seed_benchmark(session, tenant)
    mv = _model(session, tenant)
    snap, _ = _ref_snapshot(session, tenant, exp_run, cov_run, bm_id)
    result = _run(session, tenant, mv, snapshot_id=snap.id)
    assert result.status == RunStatus.COMPLETED.value
    row = result.rows[0]
    assert row.te_value == REF_TE
    assert row.portfolio_value == Decimal("1000.000000")
    assert row.factor_exposure_run_id == exp_run and row.covariance_run_id == cov_run
    assert row.benchmark_id == bm_id


# ---------- (4) reproducibility + pin invariance ----------


def test_exact_rerun_and_consume_equals_build(session: Session) -> None:
    tenant = str(uuid.uuid4())
    fx_run, cov_run, _fids = _seed_upstream_runs(session, tenant)
    bm_id = _seed_benchmark(session, tenant)
    mv = _model(session, tenant)
    first = _build(session, tenant, mv, fx_run, cov_run, bm_id)
    again = _build(session, tenant, mv, fx_run, cov_run, bm_id)
    assert first.rows[0].te_value == again.rows[0].te_value
    consumed = _run(session, tenant, mv, snapshot_id=first.run.input_snapshot_id)
    assert consumed.rows[0].te_value == first.rows[0].te_value


def test_pin_invariance_under_upstream_reruns_and_benchmark_restatement(session: Session) -> None:
    tenant = str(uuid.uuid4())
    fx_run, cov_run, factor_ids = _seed_upstream_runs(session, tenant)
    bm_id = _seed_benchmark(session, tenant)
    mv = _model(session, tenant)
    baseline = _build(session, tenant, mv, fx_run, cov_run, bm_id)
    snap_id = baseline.run.input_snapshot_id

    # A later covariance RE-RUN (new rows under a NEW run, SAME registered model) + a benchmark
    # RESTATEMENT (supersede) must NOT move the number pinned by the earlier snapshot.
    cov_mv = register_covariance_model(
        session, tenant_id=tenant, actor_id="a", code_version="risk-v1", window_observations=4
    )  # idempotent: the same model_version
    run_covariance(
        session,
        acting_tenant=tenant,
        actor=CovarianceActor(actor_id="a"),
        code_version="risk-v1",
        environment_id="ci",
        model_version_id=cov_mv.id,
        factor_ids=factor_ids,
        as_of_valid_at=VALID_AT,
    )
    bm = resolve_benchmark(session, bm_id, acting_tenant=tenant)
    new_inst = create_instrument(
        session,
        tenant_id=tenant,
        code=f"BM-I-{uuid.uuid4().hex[:6]}",
        name="bmi",
        asset_class="EQUITY",
        actor=ReferenceActor(actor_id="s"),
    ).id
    supersede_membership(
        session,
        bm,
        effective_date=D4,
        constituents=[
            ConstituentInput(
                instrument_id=new_inst, weight=Decimal("1.00"), constituent_currency="USD"
            )
        ],
        acting_tenant=tenant,
        actor=BenchmarkActor(actor_id="s"),
        effective_at=datetime(2026, 8, 1, tzinfo=UTC),  # after the snapshot's as-of instant
    )
    session.flush()
    replay = _run(session, tenant, mv, snapshot_id=snap_id)
    assert replay.rows[0].te_value == baseline.rows[0].te_value


# ---------- (5) pre-create refusals (both paths adjudicate the pinned content) ----------


def test_missing_inputs_and_wrong_model_refused(session: Session) -> None:
    tenant = str(uuid.uuid4())
    fx_run, cov_run, _ = _seed_upstream_runs(session, tenant)
    bm_id = _seed_benchmark(session, tenant)
    from irp_shared.model.service import UnregisteredModelError

    mv = _model(session, tenant)

    def _call(**over):  # noqa: ANN003, ANN202
        args = dict(
            code_version="risk-v1",
            environment_id="ci",
            model_version_id=mv,
            exposure_run_id=fx_run,
            covariance_run_id=cov_run,
            benchmark_id=bm_id,
            benchmark_effective_date=D4,
        )
        args.update(over)
        return run_active_risk(session, acting_tenant=tenant, actor=ACTOR, **args)

    # Blank required anchors + an incomplete build-arg set (a missing benchmark leg) all refuse.
    for over in (
        {"code_version": ""},
        {"environment_id": ""},
        {"model_version_id": ""},
        {"benchmark_id": None},
        {"benchmark_effective_date": None},
    ):
        with pytest.raises(ActiveRiskInputError):
            _call(**over)
    # An unregistered model_version fails closed (CTRL-003).
    with pytest.raises(UnregisteredModelError):
        _call(model_version_id=str(uuid.uuid4()))
    assert _count_runs(session, tenant) == 0


def test_ambiguous_both_modes_refused(session: Session) -> None:
    tenant = str(uuid.uuid4())
    fx_run, cov_run, _ = _seed_upstream_runs(session, tenant)
    bm_id = _seed_benchmark(session, tenant)
    mv = _model(session, tenant)
    with pytest.raises(ActiveRiskInputError):
        _build(session, tenant, mv, fx_run, cov_run, bm_id, snapshot_id=str(uuid.uuid4()))
    assert _count_runs(session, tenant) == 0


def test_null_and_unmappable_constituent_currency_refused(session: Session) -> None:
    tenant = str(uuid.uuid4())
    exp_run, cov_run, _ = _seed_upstream_runs(session, tenant)
    bm_id = _seed_benchmark(session, tenant)
    mv = _model(session, tenant)
    fa, fb = str(uuid.uuid4()).lower(), str(uuid.uuid4()).lower()
    base = dict(
        exposure_rows=[
            _exposure_content(exp_run, fa, "A", "700.000000"),
            _exposure_content(exp_run, fb, "B", "300.000000"),
        ],
        covariance_rows=[
            _covariance_content(cov_run, fa, fa, "0.00040000000000000000"),
            _covariance_content(cov_run, fb, fb, "0.00090000000000000000"),
            _covariance_content(cov_run, fa, fb, "0E-20"),
        ],
        factor_rows=[_factor_content(fa, "A", "USD"), _factor_content(fb, "B", "EUR")],
    )
    # NULL constituent_currency -> refuse (no header-currency imputation, OQ-6).
    snap_null = _mint_snapshot(
        session,
        tenant,
        benchmark_rows=[
            _benchmark_content(bm_id, None, "0.500000000000"),
            _benchmark_content(bm_id, "EUR", "0.500000000000"),
        ],
        **base,
    )
    with pytest.raises(ActiveRiskInputError):
        _run(session, tenant, mv, snapshot_id=snap_null.id)
    # An UNMAPPABLE currency (no pinned factor) -> refuse.
    snap_unmap = _mint_snapshot(
        session,
        tenant,
        benchmark_rows=[
            _benchmark_content(bm_id, "JPY", "0.500000000000"),
            _benchmark_content(bm_id, "EUR", "0.500000000000"),
        ],
        **base,
    )
    with pytest.raises(ActiveRiskInputError):
        _run(session, tenant, mv, snapshot_id=snap_unmap.id)
    assert _count_runs(session, tenant) == 0


def test_nonpositive_weight_sum_and_zero_portfolio_refused(session: Session) -> None:
    tenant = str(uuid.uuid4())
    exp_run, cov_run, _ = _seed_upstream_runs(session, tenant)
    bm_id = _seed_benchmark(session, tenant)
    mv = _model(session, tenant)
    fa, fb = str(uuid.uuid4()).lower(), str(uuid.uuid4()).lower()
    factors = [_factor_content(fa, "A", "USD"), _factor_content(fb, "B", "EUR")]
    cov = [
        _covariance_content(cov_run, fa, fa, "0.00040000000000000000"),
        _covariance_content(cov_run, fb, fb, "0.00090000000000000000"),
        _covariance_content(cov_run, fa, fb, "0E-20"),
    ]
    # Σw_b == 0 -> cannot normalize.
    snap_zero_w = _mint_snapshot(
        session,
        tenant,
        exposure_rows=[
            _exposure_content(exp_run, fa, "A", "700.000000"),
            _exposure_content(exp_run, fb, "B", "300.000000"),
        ],
        covariance_rows=cov,
        factor_rows=factors,
        benchmark_rows=[
            _benchmark_content(bm_id, "USD", "0E-12"),
            _benchmark_content(bm_id, "EUR", "0E-12"),
        ],
    )
    with pytest.raises(ActiveRiskInputError):
        _run(session, tenant, mv, snapshot_id=snap_zero_w.id)
    # portfolio_value == 0 (offsetting exposures) -> active weights undefined.
    snap_zero_pv = _mint_snapshot(
        session,
        tenant,
        exposure_rows=[
            _exposure_content(exp_run, fa, "A", "700.000000"),
            _exposure_content(exp_run, fb, "B", "-700.000000"),
        ],
        covariance_rows=cov,
        factor_rows=factors,
        benchmark_rows=[
            _benchmark_content(bm_id, "USD", "0.500000000000"),
            _benchmark_content(bm_id, "EUR", "0.500000000000"),
        ],
    )
    with pytest.raises(ActiveRiskInputError):
        _run(session, tenant, mv, snapshot_id=snap_zero_pv.id)
    assert _count_runs(session, tenant) == 0


def test_coverage_gap_and_factor_set_mismatch_refused(session: Session) -> None:
    tenant = str(uuid.uuid4())
    exp_run, cov_run, _ = _seed_upstream_runs(session, tenant)
    bm_id = _seed_benchmark(session, tenant)
    mv = _model(session, tenant)
    fa, fb = str(uuid.uuid4()).lower(), str(uuid.uuid4()).lower()
    benchmark = [
        _benchmark_content(bm_id, "USD", "0.500000000000"),
        _benchmark_content(bm_id, "EUR", "0.500000000000"),
    ]
    # An exposure factor NOT covered by the single-factor covariance set -> refuse (no imputation).
    snap_gap = _mint_snapshot(
        session,
        tenant,
        exposure_rows=[
            _exposure_content(exp_run, fa, "A", "700.000000"),
            _exposure_content(exp_run, fb, "B", "300.000000"),
        ],
        covariance_rows=[_covariance_content(cov_run, fa, fa, "0.00040000000000000000")],
        factor_rows=[_factor_content(fa, "A", "USD")],
        benchmark_rows=[_benchmark_content(bm_id, "USD", "1.000000000000")],
    )
    with pytest.raises(ActiveRiskInputError):
        _run(session, tenant, mv, snapshot_id=snap_gap.id)
    # A FACTOR-definition set that does not EXACTLY match the covariance factor set -> refuse.
    snap_mismatch = _mint_snapshot(
        session,
        tenant,
        exposure_rows=[
            _exposure_content(exp_run, fa, "A", "700.000000"),
            _exposure_content(exp_run, fb, "B", "300.000000"),
        ],
        covariance_rows=[
            _covariance_content(cov_run, fa, fa, "0.00040000000000000000"),
            _covariance_content(cov_run, fb, fb, "0.00090000000000000000"),
            _covariance_content(cov_run, fa, fb, "0E-20"),
        ],
        factor_rows=[_factor_content(fa, "A", "USD")],  # missing fb's definition
        benchmark_rows=benchmark,
    )
    with pytest.raises(ActiveRiskInputError):
        _run(session, tenant, mv, snapshot_id=snap_mismatch.id)
    assert _count_runs(session, tenant) == 0


def test_mixed_run_wrong_vocab_and_malformed_refused(session: Session) -> None:
    tenant = str(uuid.uuid4())
    exp_run, cov_run, _ = _seed_upstream_runs(session, tenant)
    bm_id = _seed_benchmark(session, tenant)
    mv = _model(session, tenant)
    fa, fb = str(uuid.uuid4()).lower(), str(uuid.uuid4()).lower()
    factors = [_factor_content(fa, "A", "USD"), _factor_content(fb, "B", "EUR")]
    benchmark = [
        _benchmark_content(bm_id, "USD", "0.500000000000"),
        _benchmark_content(bm_id, "EUR", "0.500000000000"),
    ]
    exposure = [
        _exposure_content(exp_run, fa, "A", "700.000000"),
        _exposure_content(exp_run, fb, "B", "300.000000"),
    ]

    def _cov_rows(**over):  # noqa: ANN003, ANN202
        rows = [
            _covariance_content(cov_run, fa, fa, "0.00040000000000000000"),
            _covariance_content(cov_run, fb, fb, "0.00090000000000000000"),
            _covariance_content(cov_run, fa, fb, "0E-20"),
        ]
        for r in rows:
            r.update(over)
        return rows

    # Covariance rows spanning two runs.
    mixed = _cov_rows()
    mixed[0]["calculation_run_id"] = str(uuid.uuid4())
    # Wrong statistic vocabulary.
    wrong_vocab = _cov_rows(statistic_type="CORRELATION")
    # Malformed covariance value.
    malformed = _cov_rows()
    malformed[0]["covariance_value"] = "not-a-decimal"
    for cov_rows in (mixed, wrong_vocab, malformed):
        snap = _mint_snapshot(
            session,
            tenant,
            exposure_rows=exposure,
            covariance_rows=cov_rows,
            factor_rows=factors,
            benchmark_rows=benchmark,
        )
        with pytest.raises(ActiveRiskInputError):
            _run(session, tenant, mv, snapshot_id=snap.id)
    assert _count_runs(session, tenant) == 0


def test_pinned_provenance_ids_must_resolve_own_tenant(session: Session) -> None:
    # FK columns bypass RLS: a hand-minted snapshot referencing a FOREIGN tenant's runs/benchmark
    # must be refused before those ids reach the hard-FK columns (the P3-5 review principal finding,
    # extended to benchmark_id).
    tenant, victim = str(uuid.uuid4()), str(uuid.uuid4())
    v_exp, v_cov, _ = _seed_upstream_runs(session, victim)  # tenant B's runs
    v_bm = _seed_benchmark(session, victim)
    own_exp, own_cov, _ = _seed_upstream_runs(session, tenant)
    own_bm = _seed_benchmark(session, tenant)
    mv = _model(session, tenant)
    fa, fb = str(uuid.uuid4()).lower(), str(uuid.uuid4()).lower()

    def _snap(exp_run, cov_run, bm_id):  # noqa: ANN001, ANN202
        return _mint_snapshot(
            session,
            tenant,
            exposure_rows=[
                _exposure_content(exp_run, fa, "A", "700.000000"),
                _exposure_content(exp_run, fb, "B", "300.000000"),
            ],
            covariance_rows=[
                _covariance_content(cov_run, fa, fa, "0.00040000000000000000"),
                _covariance_content(cov_run, fb, fb, "0.00090000000000000000"),
                _covariance_content(cov_run, fa, fb, "0E-20"),
            ],
            factor_rows=[_factor_content(fa, "A", "USD"), _factor_content(fb, "B", "EUR")],
            benchmark_rows=[
                _benchmark_content(bm_id, "USD", "0.500000000000"),
                _benchmark_content(bm_id, "EUR", "0.500000000000"),
            ],
        )

    from irp_shared.marketdata.benchmark import BenchmarkNotVisible
    from irp_shared.risk import CovarianceRunNotVisible, FactorExposureRunNotVisible

    # Each foreign hard-FK id re-resolves fail-closed to its OWN domain NotVisible exception (the
    # binder never stamps a cross-tenant id into a hard-FK column).
    for exp_run, cov_run, bm_id, exc in (
        (v_exp, own_cov, own_bm, FactorExposureRunNotVisible),
        (own_exp, v_cov, own_bm, CovarianceRunNotVisible),
        (own_exp, own_cov, v_bm, BenchmarkNotVisible),
    ):
        snap = _snap(exp_run, cov_run, bm_id)
        with pytest.raises(exc):
            _run(session, tenant, mv, snapshot_id=snap.id)
    assert _count_runs(session, tenant) == 0


def test_wrong_purpose_and_unknown_snapshot_refused(session: Session) -> None:
    tenant = str(uuid.uuid4())
    exp_run, cov_run, _ = _seed_upstream_runs(session, tenant)
    mv = _model(session, tenant)
    from irp_shared.snapshot import SnapshotNotFound

    with pytest.raises(SnapshotNotFound):
        _run(session, tenant, mv, snapshot_id=str(uuid.uuid4()))
    wrong = _mint_snapshot(
        session,
        tenant,
        exposure_rows=[_exposure_content(exp_run, str(uuid.uuid4()).lower(), "A", "700.000000")],
        covariance_rows=[],
        factor_rows=[],
        benchmark_rows=[],
        purpose="VAR_INPUT",  # wrong purpose
    )
    with pytest.raises(ActiveRiskInputError):
        _run(session, tenant, mv, snapshot_id=wrong.id)
    assert _count_runs(session, tenant) == 0


def test_builder_refuses_empty_membership(session: Session) -> None:
    tenant = str(uuid.uuid4())
    fx_run, cov_run, _ = _seed_upstream_runs(session, tenant)
    # A benchmark with NO membership for the requested effective_date -> the builder fails closed.
    bm = capture_benchmark(
        session,
        benchmark_code=f"BM-{uuid.uuid4().hex[:6]}",
        benchmark_source="VENDOR_B",
        benchmark_currency="USD",
        acting_tenant=tenant,
        actor=BenchmarkActor(actor_id="s"),
        valid_from=T0,
    )
    session.flush()
    mv = _model(session, tenant)
    # The builder fails closed with the active-risk-specific error (review: the wire detail must
    # name the right family, not "VaR snapshot input failed closed").
    with pytest.raises(ActiveRiskSnapshotError) as exc:
        _build(session, tenant, mv, fx_run, cov_run, bm.id)
    assert "active-risk snapshot input failed closed" in str(exc.value)
    assert _count_runs(session, tenant) == 0


# ---------- (5b) review-hardening: adversarial hand-minted pins the gate must refuse ----------


def _ref_rows(exp_run: str, cov_run: str, bm_id: str, fa: str, fb: str) -> dict:
    """The well-formed 0.007211102551 reference row-set (portfolio 700/300, benchmark USD/EUR
    0.5/0.5, uncorrelated var 4E-4/9E-4) as kwargs for :func:`_mint_snapshot` — each probe mutates
    ONE leg to prove the corresponding guard."""
    return dict(
        exposure_rows=[
            _exposure_content(exp_run, fa, "A", "700.000000"),
            _exposure_content(exp_run, fb, "B", "300.000000"),
        ],
        covariance_rows=[
            _covariance_content(cov_run, fa, fa, "0.00040000000000000000"),
            _covariance_content(cov_run, fb, fb, "0.00090000000000000000"),
            _covariance_content(cov_run, fa, fb, "0E-20"),
        ],
        factor_rows=[_factor_content(fa, "A", "USD"), _factor_content(fb, "B", "EUR")],
        benchmark_rows=[
            _benchmark_content(bm_id, "USD", "0.500000000000"),
            _benchmark_content(bm_id, "EUR", "0.500000000000"),
        ],
    )


def test_duplicate_factor_pins_with_conflicting_currency_refused(session: Session) -> None:
    # A repeated FACTOR content id with a DIFFERENT currency collapses in the set-equality check;
    # without a dup guard it would silently merge two currencies onto one factor (review V3).
    tenant = str(uuid.uuid4())
    exp_run, cov_run, _ = _seed_upstream_runs(session, tenant)
    bm_id = _seed_benchmark(session, tenant)
    mv = _model(session, tenant)
    fa, fb = str(uuid.uuid4()).lower(), str(uuid.uuid4()).lower()
    rows = _ref_rows(exp_run, cov_run, bm_id, fa, fb)
    # fa pinned TWICE: once USD, once EUR (distinct component ids via _anchor); {fa,fa,fb}=={fa,fb}.
    rows["factor_rows"] = [
        _factor_content(fa, "A", "USD"),
        {**_factor_content(fa, "A2", "EUR"), "_anchor": str(uuid.uuid4())},
        _factor_content(fb, "B", "EUR"),
    ]
    snap = _mint_snapshot(session, tenant, **rows)
    with pytest.raises(ActiveRiskInputError, match="duplicate pinned FACTOR"):
        _run(session, tenant, mv, snapshot_id=snap.id)
    assert _count_runs(session, tenant) == 0


def test_null_or_nonascii_base_currency_refused(session: Session) -> None:
    # A uniformly-NULL or non-3-letter base_currency passes the set-of-one check but would reach the
    # NOT-NULL varchar(3) column as a post-create 500 (review V5): refuse pre-create.
    tenant = str(uuid.uuid4())
    exp_run, cov_run, _ = _seed_upstream_runs(session, tenant)
    bm_id = _seed_benchmark(session, tenant)
    mv = _model(session, tenant)
    fa, fb = str(uuid.uuid4()).lower(), str(uuid.uuid4()).lower()
    for bad in (None, "USDX"):
        rows = _ref_rows(exp_run, cov_run, bm_id, fa, fb)
        rows["exposure_rows"] = [
            _exposure_content(exp_run, fa, "A", "700.000000", base=bad),  # type: ignore[arg-type]
            _exposure_content(exp_run, fb, "B", "300.000000", base=bad),  # type: ignore[arg-type]
        ]
        snap = _mint_snapshot(session, tenant, **rows)
        with pytest.raises(ActiveRiskInputError, match="base_currency is not a 3-letter code"):
            _run(session, tenant, mv, snapshot_id=snap.id)
    assert _count_runs(session, tenant) == 0


def test_empty_string_currency_refused(session: Session) -> None:
    # "" is not None, so the is-None named-gap check alone would let a blank denomination through
    # build_factor_index and mint a governed number from gap data (review V6).
    tenant = str(uuid.uuid4())
    exp_run, cov_run, _ = _seed_upstream_runs(session, tenant)
    bm_id = _seed_benchmark(session, tenant)
    mv = _model(session, tenant)
    fa, fb = str(uuid.uuid4()).lower(), str(uuid.uuid4()).lower()
    # (a) a blank FACTOR currency_code -> refuse.
    rows = _ref_rows(exp_run, cov_run, bm_id, fa, fb)
    rows["factor_rows"] = [_factor_content(fa, "A", ""), _factor_content(fb, "B", "EUR")]
    snap = _mint_snapshot(session, tenant, **rows)
    with pytest.raises(ActiveRiskInputError, match="blank/NULL currency_code"):
        _run(session, tenant, mv, snapshot_id=snap.id)
    # (b) a blank constituent_currency (with a matching blank factor) -> refuse (no imputation).
    rows = _ref_rows(exp_run, cov_run, bm_id, fa, fb)
    rows["factor_rows"] = [_factor_content(fa, "A", ""), _factor_content(fb, "B", "EUR")]
    rows["benchmark_rows"] = [
        _benchmark_content(bm_id, "", "0.500000000000"),
        _benchmark_content(bm_id, "EUR", "0.500000000000"),
    ]
    snap = _mint_snapshot(session, tenant, **rows)
    with pytest.raises(ActiveRiskInputError, match="blank/NULL currency_code|blank constituent"):
        _run(session, tenant, mv, snapshot_id=snap.id)
    assert _count_runs(session, tenant) == 0


def test_malformed_null_field_is_422_not_typeerror(session: Session) -> None:
    # A JSON-null numeric field raises TypeError (Decimal(None)) — it must map to the governed 422
    # refusal, never escape as a raw 500 (review V2).
    tenant = str(uuid.uuid4())
    exp_run, cov_run, _ = _seed_upstream_runs(session, tenant)
    bm_id = _seed_benchmark(session, tenant)
    mv = _model(session, tenant)
    fa, fb = str(uuid.uuid4()).lower(), str(uuid.uuid4()).lower()
    for leg, key in (
        ("exposure_rows", "exposure_amount"),
        ("benchmark_rows", "weight"),
        ("covariance_rows", "covariance_value"),
    ):
        rows = _ref_rows(exp_run, cov_run, bm_id, fa, fb)
        rows[leg][0] = {**rows[leg][0], key: None, "_anchor": str(uuid.uuid4())}
        snap = _mint_snapshot(session, tenant, **rows)
        with pytest.raises(ActiveRiskInputError, match="not a well-formed v1 input"):
            _run(session, tenant, mv, snapshot_id=snap.id)
    assert _count_runs(session, tenant) == 0


def test_covariance_duplicate_and_reversed_pair_refused(session: Session) -> None:
    # The reversed-/duplicate-pair hardening (mirrored from var_service) — now test-pinned in this
    # copy too (review V15): a reversed pair and a repeated canonical pair both refuse.
    tenant = str(uuid.uuid4())
    exp_run, cov_run, _ = _seed_upstream_runs(session, tenant)
    bm_id = _seed_benchmark(session, tenant)
    mv = _model(session, tenant)
    fa, fb = sorted((str(uuid.uuid4()).lower(), str(uuid.uuid4()).lower()))
    # Reversed off-diagonal order (fb, fa) with fb > fa -> non-canonical -> refuse.
    rows = _ref_rows(exp_run, cov_run, bm_id, fa, fb)
    reversed_pair = _covariance_content(cov_run, fa, fb, "0E-20")
    reversed_pair["factor_id_1"], reversed_pair["factor_id_2"] = fb, fa  # force non-canonical order
    rows["covariance_rows"] = [
        _covariance_content(cov_run, fa, fa, "0.00040000000000000000"),
        _covariance_content(cov_run, fb, fb, "0.00090000000000000000"),
        reversed_pair,
    ]
    snap = _mint_snapshot(session, tenant, **rows)
    with pytest.raises(ActiveRiskInputError, match="non-canonical covariance pair"):
        _run(session, tenant, mv, snapshot_id=snap.id)
    # A duplicated canonical pair -> refuse.
    rows = _ref_rows(exp_run, cov_run, bm_id, fa, fb)
    rows["covariance_rows"].append(_covariance_content(cov_run, fa, fb, "0E-20"))
    snap = _mint_snapshot(session, tenant, **rows)
    with pytest.raises(ActiveRiskInputError, match="duplicate covariance pair"):
        _run(session, tenant, mv, snapshot_id=snap.id)
    assert _count_runs(session, tenant) == 0


def test_kernel_magnitude_raise_becomes_committed_failed(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A te past the 12dp quantize range makes the kernel raise ActiveRiskKernelError DURING compute,
    # before the _MAX_RESULT_ABS gate can read te_value; that must convert to a committed FAILED run
    # with evidence, never escape as an uncaught 500 (review V1). Forced via the kernel seam.
    import irp_shared.risk.active_risk_service as ars

    tenant = str(uuid.uuid4())
    exp_run, cov_run, _ = _seed_upstream_runs(session, tenant)
    bm_id = _seed_benchmark(session, tenant)
    mv = _model(session, tenant)

    def _raise(active_weights, covariance):  # noqa: ANN001, ANN202
        raise ActiveRiskKernelError("tracking-error magnitude out of range")

    monkeypatch.setattr(ars, "compute_tracking_error", _raise)
    result = _build(session, tenant, mv, exp_run, cov_run, bm_id)
    assert result.status == RunStatus.FAILED.value  # committed FAILED, not a raised 500
    assert result.rows == [] and "magnitude-out-of-range" in (result.failure_reason or "")
    assert _count_results(session, tenant) == 0


def test_exact_zero_book_not_masked_by_rounding(session: Session) -> None:
    # A book whose EXACT net is zero but whose intermediate sum needs 29 significant digits would,
    # at the default 28-digit context, round to a spurious non-zero portfolio_value and evade the
    # ==0 refusal; the compute-precision accumulation keeps it exactly zero so it is refused
    # (review V4). fa's four offsetting rows net to EXACTLY 0 (28-sig-digit legs + cents).
    tenant = str(uuid.uuid4())
    exp_run, cov_run, _ = _seed_upstream_runs(session, tenant)
    bm_id = _seed_benchmark(session, tenant)
    mv = _model(session, tenant)
    fa = str(uuid.uuid4()).lower()
    snap = _mint_snapshot(
        session,
        tenant,
        exposure_rows=[
            _exposure_content(exp_run, fa, "A", "9999999999999999999999.999999"),
            _exposure_content(exp_run, fa, "A", "0.000002"),
            _exposure_content(exp_run, fa, "A", "-9999999999999999999999.999999"),
            _exposure_content(exp_run, fa, "A", "-0.000002"),
        ],
        covariance_rows=[_covariance_content(cov_run, fa, fa, "0.00040000000000000000")],
        factor_rows=[_factor_content(fa, "A", "USD")],
        benchmark_rows=[_benchmark_content(bm_id, "USD", "1.000000000000")],
    )
    with pytest.raises(ActiveRiskInputError, match="portfolio value .* is zero"):
        _run(session, tenant, mv, snapshot_id=snap.id)
    assert _count_runs(session, tenant) == 0


# ---------- (6) post-create FAILED (the reachable non-PSD radicand gate) ----------


def test_non_psd_snapshot_fails_closed_post_create(session: Session) -> None:
    tenant = str(uuid.uuid4())
    exp_run, cov_run, _ = _seed_upstream_runs(session, tenant)
    bm_id = _seed_benchmark(session, tenant)
    mv = _model(session, tenant)
    fa, fb = str(uuid.uuid4()).lower(), str(uuid.uuid4()).lower()
    # A genuinely non-PSD pinned matrix (|cov| > sqrt(var*var)) reachable via a hand-minted
    # snapshot: the run COMMITS as FAILED with a radicand-naming reason + ZERO rows.
    snap = _mint_snapshot(
        session,
        tenant,
        exposure_rows=[
            _exposure_content(exp_run, fa, "A", "700.000000"),
            _exposure_content(exp_run, fb, "B", "300.000000"),
        ],
        covariance_rows=[
            _covariance_content(cov_run, fa, fa, "0.00010000000000000000"),
            _covariance_content(cov_run, fb, fb, "0.00010000000000000000"),
            _covariance_content(cov_run, fa, fb, "0.01000000000000000000"),
        ],
        factor_rows=[_factor_content(fa, "A", "USD"), _factor_content(fb, "B", "EUR")],
        benchmark_rows=[
            _benchmark_content(bm_id, "USD", "0.500000000000"),
            _benchmark_content(bm_id, "EUR", "0.500000000000"),
        ],
    )
    result = _run(session, tenant, mv, snapshot_id=snap.id)
    assert result.status == RunStatus.FAILED.value
    assert result.rows == [] and "non-psd-radicand" in (result.failure_reason or "")
    assert _count_results(session, tenant) == 0


# ---------- (7) audit / lineage / append-only / grain ----------


def test_audit_calc_run_events_no_risk_event(session: Session) -> None:
    tenant = str(uuid.uuid4())
    fx_run, cov_run, _ = _seed_upstream_runs(session, tenant)
    bm_id = _seed_benchmark(session, tenant)
    mv = _model(session, tenant)
    result = _build(session, tenant, mv, fx_run, cov_run, bm_id)
    events = (
        session.execute(
            select(AuditEvent).where(
                AuditEvent.entity_type == "calculation_run",
                AuditEvent.entity_id == result.run.run_id,
            )
        )
        .scalars()
        .all()
    )
    types = [e.event_type for e in events]
    assert "CALC.RUN_CREATE" in types and "CALC.RUN_STATUS_CHANGE" in types
    risk_events = (
        session.execute(select(AuditEvent).where(AuditEvent.event_type.like("RISK.%")))
        .scalars()
        .all()
    )
    assert risk_events == []  # RISK.ACTIVE_RISK_CREATE stays reserved-not-emitted


def test_lineage_origin_and_append_only(session: Session) -> None:
    from irp_shared.temporal import TemporalClass

    assert ActiveRiskResult.__temporal_class__ == TemporalClass.IMMUTABLE_APPEND_ONLY
    tenant = str(uuid.uuid4())
    fx_run, cov_run, _ = _seed_upstream_runs(session, tenant)
    bm_id = _seed_benchmark(session, tenant)
    mv = _model(session, tenant)
    result = _build(session, tenant, mv, fx_run, cov_run, bm_id)
    origin = (
        session.execute(
            select(LineageEdge).where(
                LineageEdge.source_type == SOURCE_TYPE_CALCULATION_RUN,
                LineageEdge.target_entity_type == "active_risk_result",
                LineageEdge.edge_kind == EDGE_KIND_ORIGIN,
            )
        )
        .scalars()
        .all()
    )
    assert {e.target_entity_id for e in origin} == {result.rows[0].id}
    session.commit()
    row = result.rows[0]
    row.te_value = Decimal("0")
    with pytest.raises(AppendOnlyViolation):
        session.flush()
    session.rollback()
    with pytest.raises(AppendOnlyViolation):
        session.delete(result.rows[0])
        session.flush()


def test_single_summary_row_grain_and_reader(session: Session) -> None:
    tenant = str(uuid.uuid4())
    fx_run, cov_run, _ = _seed_upstream_runs(session, tenant)
    bm_id = _seed_benchmark(session, tenant)
    mv = _model(session, tenant)
    result = _build(session, tenant, mv, fx_run, cov_run, bm_id)
    listed = list_active_risks(session, run_id=result.run.run_id, acting_tenant=tenant)
    assert len(listed) == 1 and listed[0].id == result.rows[0].id
    snap = resolve_snapshot(session, result.run.input_snapshot_id, acting_tenant=tenant)
    assert snap.purpose == PURPOSE_ACTIVE_RISK_INPUT
    comps = list_components(session, snapshot_id=snap.id, acting_tenant=tenant)
    kinds = {c.component_kind for c in comps}
    assert kinds == {
        COMPONENT_KIND_FACTOR_EXPOSURE,
        COMPONENT_KIND_COVARIANCE,
        COMPONENT_KIND_FACTOR,
        COMPONENT_KIND_BENCHMARK,
    }


# ---------- (8) entitlement REUSE parity (no new permission — OD-P3-7-A) ----------


def test_risk_permissions_reused_no_new_codes() -> None:
    all_codes = {code for perms in ROLE_TEMPLATES.values() for code in perms}
    assert "risk.run" in all_codes and "risk.view" in all_codes
    assert not {
        c for c in all_codes if "active_risk" in c.split(".") or "tracking_error" in c.split(".")
    }


# ---------- (9) methodology doc ----------

_ROOT = pathlib.Path(__file__).resolve().parents[3]
_AR_SERVICE_SRC = (
    _ROOT / "packages/shared-python/src/irp_shared/risk/active_risk_service.py"
).read_text()
_AR_KERNEL_SRC = (
    _ROOT / "packages/shared-python/src/irp_shared/risk/active_risk_kernel.py"
).read_text()


def test_methodology_doc_exists_and_has_required_sections() -> None:
    doc = (_ROOT / ACTIVE_RISK_METHODOLOGY_REF).read_text()
    for section in (
        "## Purpose & applicability",
        "## Inputs & data policy",
        "## Formulas & numerical standards",
        "## Assumptions",
        "## Validation / reproduction tests",
        "## Governed-number contract",
        "## Known limitations",
    ):
        assert section in doc, section
    assert "EX-ANTE" in doc  # the ex-ante vs ex-post honesty gap
    assert "0.007211102551" in doc  # the exact hand reference
    assert "Specific/idiosyncratic active risk = 0" in doc  # the first-class honesty gap


def test_methodology_ref_matches_registered_version(session: Session) -> None:
    tenant = str(uuid.uuid4())
    mv_id = _model(session, tenant)
    version = session.get(ModelVersion, mv_id)
    assert version is not None and version.methodology_ref == ACTIVE_RISK_METHODOLOGY_REF
    assert (_ROOT / version.methodology_ref).exists()


# ---------- (10) load-bearing scope fences ----------


def test_scope_fence_no_live_reads_in_compute_path() -> None:
    tree = ast.parse(_AR_SERVICE_SRC)
    forbidden = {
        "list_active_risks",
        "resolve_factor_exposure_run",
        "resolve_covariance_run",
        "resolve_benchmark",
        "resolve_factor",
        "reconstruct_membership_as_of",
    }
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name in (
            "_parse_pins",
            "_adjudicate_pins",
            "_adjudicate_covariance",
        ):
            found.add(node.name)
            names = {n.id for n in ast.walk(node) if isinstance(n, ast.Name)}
            attrs = {n.attr for n in ast.walk(node) if isinstance(n, ast.Attribute)}
            assert not (names & forbidden), (node.name, names & forbidden)
            assert not (attrs & forbidden), (node.name, attrs & forbidden)
    assert found == {"_parse_pins", "_adjudicate_pins", "_adjudicate_covariance"}, found


def test_scope_fence_no_future_method_imports_or_identifiers() -> None:
    for src in (_AR_SERVICE_SRC, _AR_KERNEL_SRC):
        tree = ast.parse(src)
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)
            elif isinstance(node, ast.Import):
                imported.update(a.name for a in node.names)
        for mod in imported:
            parts = set(mod.split("."))
            # NOTE: ``marketdata.benchmark`` is a LEGITIMATE dependency here (the benchmark is the
            # active-risk input) — unlike VaR, it is NOT fenced out.
            assert not (
                parts & {"scenario", "stress", "numpy", "scipy", "random", "statistics"}
            ), f"forbidden import {mod}"
        idents = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)} | {
            n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)
        }
        forbidden_idents = {
            "expected_shortfall",
            "monte_carlo",
            "simulate",
            "simulation",
            "random_seed",
            "backtest",
            "annualize",
            "scenario_result",
            "stress_test",
            "information_ratio",
            "active_return",
            "realized_return",
            "ex_post",
        }
        assert not (idents & forbidden_idents), idents & forbidden_idents


# ---------- (11) migration head ----------


def test_migration_head_is_active_risk() -> None:
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    cfg = Config(str(_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(_ROOT / "migrations"))
    script = ScriptDirectory.from_config(cfg)
    assert script.get_current_head() == "0049_scheduling"  # PPF-3
    assert script.get_revision("0030_active_risk").down_revision == "0029_benchmark_series"
