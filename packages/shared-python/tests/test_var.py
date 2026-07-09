"""SQLite-local unit/behavior tests for P3-5 parametric VaR (the fourth governed RISK number and
the first DERIVED-OF-DERIVED one; ENT-027 `risk_result` realized as `var_result`).

RLS is a no-op on SQLite (FORCE-RLS isolation + the P0001 trigger live in ``test_var_pg.py``);
here we prove: the pure kernel against **hand-computed exact references** (perfect-square
constructions: the 3-4-5 exposure triangle => sigma_p = 500 exactly; a fully-correlated pair =>
sigma_p = 7) + the **numpy float cross-check** + positive-homogeneity/monotonicity/
order-invariance properties + the **`math.erf` round-trip of the registered z constants** (the
dual-path standing rule); the declared-parameter version identity (OD-P3-5-D — confidence/
horizon/z parsed from assumptions; malformed/absent declarations refuse fail-closed; identity
conflicts 409); the two-run consumption + COVERAGE adjudication (fail-closed, both entry paths,
NO zero-variance imputation); the exact hand-reference VaR **through the full governed consume
path** (a hand-minted VAR_INPUT snapshot); the REACHABLE non-PSD radicand FAILED path; exact
re-run + pin invariance under upstream RE-RUNS; CALC.RUN_* audit (+ NO RISK.* code); lineage;
the append-only ORM guard; entitlement REUSE parity; the methodology doc; the load-bearing scope
fences; and the migration head.
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
    EDGE_KIND_DEPENDENCY,
    EDGE_KIND_ORIGIN,
    SOURCE_TYPE_CALCULATION_RUN,
    SOURCE_TYPE_DATA_SNAPSHOT,
    LineageEdge,
)
from irp_shared.marketdata import FxRateActor, capture_fx_rate
from irp_shared.marketdata.factor import (
    FactorActor,
    capture_factor,
    capture_factor_return,
    resolve_factor,
)
from irp_shared.model.models import ModelAssumption, ModelVersion
from irp_shared.model.service import UnregisteredModelError
from irp_shared.models import Base
from irp_shared.portfolio import PortfolioActor, create_portfolio
from irp_shared.position import create_position
from irp_shared.position.service import PositionActor
from irp_shared.reference.instrument import create_instrument
from irp_shared.reference.models import Currency
from irp_shared.reference.service import ReferenceActor
from irp_shared.risk import (
    VAR_METHODOLOGY_REF,
    VAR_Z_SCORES,
    CovarianceActor,
    FactorExposureActor,
    ModelVersionConflictError,
    VarActor,
    VarInputError,
    VarKernelError,
    VarResult,
    WrongModelVersionError,
    compute_parametric_var,
    declared_var_parameters,
    list_vars,
    register_covariance_model,
    register_factor_exposure_model,
    register_var_model,
    run_covariance,
    run_factor_exposure,
    run_var,
)
from irp_shared.snapshot import (
    COMPONENT_KIND_COVARIANCE,
    COMPONENT_KIND_FACTOR_EXPOSURE,
    PURPOSE_VAR_INPUT,
    SnapshotActor,
    VarSnapshotError,
    build_var_snapshot,
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
ACTOR = VarActor(actor_id="analyst")
Z95 = Decimal(VAR_Z_SCORES["0.9500"])
Z99 = Decimal(VAR_Z_SCORES["0.9900"])
_Q6 = Decimal("0.000001")

#: HAND REFERENCE 1 (exact rational construction): x = (30000, 40000) — the 3-4-5 triangle —
#: over UNCORRELATED factors with variance 1E-4 (1% daily vol): radicand = (9E8+16E8)*1E-4 =
#: 25E4 => sigma_p = 500 EXACTLY; VaR95 = 500*z95 = 822.426813475500 -> 822.426813 @6dp;
#: VaR99 = 500*z99 = 1163.173937 @6dp.
REF1_SIGMA = Decimal("500.000000")
REF1_VAR95 = Decimal("822.426813")
REF1_VAR99 = Decimal("1163.173937")
#: HAND REFERENCE 2: x = (300, 400) over PERFECTLY correlated 1%-vol factors:
#: radicand = 9 + 16 + 2*12*1 = 49 => sigma_p = 7 EXACTLY; VaR95 = 11.513975 @6dp.
REF2_SIGMA = Decimal("7.000000")
REF2_VAR95 = Decimal("11.513975")


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


_DIAG_COV = _cov({("a", "a"): "0.0001", ("b", "b"): "0.0001", ("a", "b"): "0"})
_FULL_CORR_COV = _cov({("a", "a"): "0.0001", ("b", "b"): "0.0001", ("a", "b"): "0.0001"})


# ---------- (1) pure kernel — the dual-path verification ----------


def test_kernel_hand_reference_diagonal() -> None:
    e = compute_parametric_var(
        [("a", Decimal("30000")), ("b", Decimal("40000"))], _DIAG_COV, z_score=Z95
    )
    assert e.sigma == REF1_SIGMA and e.var_value == REF1_VAR95
    e99 = compute_parametric_var(
        [("a", Decimal("30000")), ("b", Decimal("40000"))], _DIAG_COV, z_score=Z99
    )
    assert e99.var_value == REF1_VAR99


def test_kernel_hand_reference_full_correlation() -> None:
    e = compute_parametric_var(
        [("a", Decimal("300")), ("b", Decimal("400"))], _FULL_CORR_COV, z_score=Z95
    )
    assert e.sigma == REF2_SIGMA and e.var_value == REF2_VAR95


def test_kernel_hand_reference_three_factor_diagonal() -> None:
    # x = (20000, 30000, 60000) — the 2-3-6 triple (4+9+36 = 49) — over uncorrelated 1%-vol
    # factors: radicand = 49E4 => sigma_p = 700 EXACTLY (the >2-factor exactness backstop).
    cov = _cov(
        {
            ("a", "a"): "0.0001",
            ("b", "b"): "0.0001",
            ("c", "c"): "0.0001",
            ("a", "b"): "0",
            ("a", "c"): "0",
            ("b", "c"): "0",
        }
    )
    e = compute_parametric_var(
        [("a", Decimal("20000")), ("b", Decimal("30000")), ("c", Decimal("60000"))],
        cov,
        z_score=Z95,
    )
    assert e.sigma == Decimal("700.000000")
    assert e.var_value == (Z95 * 700).quantize(_Q6)


def test_kernel_totals_rows_per_factor_and_ignores_order_and_case() -> None:
    # Per-factor totaling (two rows summing to 30000), row order, and id case are all invariant.
    rows_a = [("a", Decimal("10000")), ("A", Decimal("20000")), ("b", Decimal("40000"))]
    rows_b = [("b", Decimal("40000")), ("a", Decimal("30000"))]
    e_a = compute_parametric_var(rows_a, _DIAG_COV, z_score=Z95)
    e_b = compute_parametric_var(rows_b, _DIAG_COV, z_score=Z95)
    assert e_a.sigma == e_b.sigma == REF1_SIGMA
    assert e_a.var_value == e_b.var_value == REF1_VAR95


def test_kernel_positive_homogeneity() -> None:
    # VaR(lambda*x) = lambda*VaR(x) holds EXACTLY for the unrounded value; after the 6dp
    # quantization it holds to within ONE quantum on the scaled side (quantize(lambda*v) !=
    # lambda*quantize(v) when v carries digits past the quantum — z is 12dp, so z*sigma
    # generally does). sigma itself scales exactly here (perfect-square radicands).
    base = compute_parametric_var(
        [("a", Decimal("30000")), ("b", Decimal("40000"))], _DIAG_COV, z_score=Z95
    )
    scaled = compute_parametric_var(
        [("a", Decimal("300000")), ("b", Decimal("400000"))], _DIAG_COV, z_score=Z95
    )
    assert base.sigma is not None and scaled.sigma is not None
    assert base.var_value is not None and scaled.var_value is not None
    assert scaled.sigma == base.sigma * 10  # 500 -> 5000, exact
    # |quantize(lambda*v) - lambda*quantize(v)| <= (lambda+1)/2 quanta = 5.5 quanta for
    # lambda=10 (each quantize contributes a half-quantum, one side scaled by lambda).
    assert abs(scaled.var_value - base.var_value * 10) <= Decimal("0.0000055")
    # And EXACT at the quantum when z*sigma terminates within 6dp (sigma a multiple of 1E6:
    # z is 12dp, so z*1E6 has exactly 6dp).
    mega = compute_parametric_var(
        [("a", Decimal("60000000")), ("b", Decimal("80000000"))], _DIAG_COV, z_score=Z95
    )
    assert mega.sigma == Decimal("1000000.000000")
    assert mega.var_value == Z95 * Decimal(10**6)  # 1644853.626951 exactly


def test_kernel_confidence_monotonicity() -> None:
    rows = [("a", Decimal("30000")), ("b", Decimal("40000"))]
    v95 = compute_parametric_var(rows, _DIAG_COV, z_score=Z95).var_value
    v99 = compute_parametric_var(rows, _DIAG_COV, z_score=Z99).var_value
    assert v99 is not None and v95 is not None and v99 > v95 > 0


def test_kernel_short_and_offsetting_positions() -> None:
    # Signs flow through x; a fully-offsetting perfectly-correlated book has EXACTLY zero risk.
    e = compute_parametric_var(
        [("a", Decimal("1000000")), ("b", Decimal("-1000000"))], _FULL_CORR_COV, z_score=Z95
    )
    assert e.radicand == 0 and e.sigma == Decimal("0.000000") and e.var_value == Decimal("0.000000")


def test_kernel_non_psd_radicand_returns_defect() -> None:
    # "Correlation" of 2 is not a covariance matrix: radicand < -tol => sigma/var None (the
    # binder's post-create FAILED gate — REACHABLE, unlike the P3-4 defensive gate).
    bad = _cov({("a", "a"): "0.0001", ("b", "b"): "0.0001", ("a", "b"): "0.0002"})
    e = compute_parametric_var([("a", Decimal("1")), ("b", Decimal("-1"))], bad, z_score=Z95)
    assert e.sigma is None and e.var_value is None
    assert e.radicand < -e.tolerance < 0


def test_kernel_tiny_negative_radicand_clamps_to_zero() -> None:
    # Within the DECLARED tolerance the negative radicand is the 20dp storage artifact: clamp.
    tiny = _cov(
        {("a", "a"): "0.0001", ("b", "b"): "0.0001", ("a", "b"): "0.00010000000000000000005"}
    )
    e = compute_parametric_var([("a", Decimal("1")), ("b", Decimal("-1"))], tiny, z_score=Z95)
    # radicand = -1E-22, tolerance = 4 * 1 * 1E-19 => clamped
    assert e.radicand < 0 and e.radicand >= -e.tolerance
    assert e.sigma == Decimal("0.000000") and e.var_value == Decimal("0.000000")


def test_kernel_ill_formed_inputs_raise() -> None:
    with pytest.raises(VarKernelError):
        compute_parametric_var([], _DIAG_COV, z_score=Z95)  # empty portfolio vector
    with pytest.raises(VarKernelError):
        compute_parametric_var([("a", Decimal(1))], _DIAG_COV, z_score=Decimal(0))  # z <= 0
    with pytest.raises(VarKernelError):
        compute_parametric_var(  # missing pair (coverage is a precondition)
            [("a", Decimal(1)), ("c", Decimal(1))], _DIAG_COV, z_score=Z95
        )


def test_kernel_numpy_cross_check_seeded_random() -> None:
    # The independent-implementation leg (numpy TEST-ONLY; fixed seed — QS-18 spirit).
    import numpy as np

    rng = np.random.default_rng(20260708)
    for f_count in (2, 4, 7):
        a = rng.normal(0.0, 0.01, size=(f_count, 40))
        s = np.cov(a, ddof=1)  # a REAL PSD sample covariance
        x = rng.normal(0.0, 1e6, size=f_count).round(6)
        ids = [f"f{i}" for i in range(f_count)]
        cov = {}
        for i in range(f_count):
            for j in range(i, f_count):
                cov[(ids[i], ids[j])] = Decimal(f"{s[i][j]:.20f}")
        rows = [(ids[i], Decimal(f"{x[i]:.6f}")) for i in range(f_count)]
        e = compute_parametric_var(rows, cov, z_score=Z95)
        assert e.sigma is not None and e.var_value is not None
        want = float(Z95) * math.sqrt(
            float(
                sum(
                    Decimal(f"{x[i]:.6f}")
                    * Decimal(f"{x[j]:.6f}")
                    * cov[tuple(sorted((ids[i], ids[j])))]
                    for i in range(f_count)
                    for j in range(f_count)
                )
            )
        )
        got = float(e.var_value)
        assert abs(got - want) <= 1e-9 * max(abs(want), 1e-300), (f_count, got, want)


def test_z_constants_erf_round_trip_and_bisection() -> None:
    # The registered z constants are VERIFIED, not trusted: Phi(z) = (1+erf(z/sqrt(2)))/2 must
    # reproduce alpha to 1e-12, and an independent bisection inversion must reproduce z to 12dp.
    for alpha_text, z_text in VAR_Z_SCORES.items():
        alpha, z = float(alpha_text), float(z_text)
        phi = (1 + math.erf(z / math.sqrt(2))) / 2
        assert abs(phi - alpha) < 1e-12, (alpha_text, phi)
        lo, hi = 0.0, 10.0
        for _ in range(200):
            mid = (lo + hi) / 2
            if (1 + math.erf(mid / math.sqrt(2))) / 2 < alpha:
                lo = mid
            else:
                hi = mid
        assert abs(round((lo + hi) / 2, 12) - z) < 5e-13, (alpha_text, (lo + hi) / 2)


# ---------- (2) model governance (declared-parameter identity, OD-P3-5-D) ----------


def _var_model(
    db: Session, tenant: str, code_version: str = "risk-v1", confidence: str = "0.95"
) -> str:
    return register_var_model(
        db,
        tenant_id=tenant,
        actor_id="analyst",
        code_version=code_version,
        confidence_level=confidence,
    ).id


def test_model_registered_with_declared_parameters(session: Session) -> None:
    tenant = str(uuid.uuid4())
    mv_id = _var_model(session, tenant, confidence="0.99")
    version = session.get(ModelVersion, mv_id)
    assert version is not None and version.methodology_ref == VAR_METHODOLOGY_REF
    declared = declared_var_parameters(session, version)
    assert declared.confidence_level == Decimal("0.9900")
    assert declared.horizon_days == 1
    assert declared.z_score == Z99
    texts = [
        r.assumption_text
        for r in session.execute(
            select(ModelAssumption).where(ModelAssumption.model_version_id == mv_id)
        ).scalars()
    ]
    assert "confidence_level=0.9900" in texts
    assert "horizon_days=1" in texts
    assert f"z_score={Z99}" in texts


def test_register_idempotent_vocabulary_floor_and_identity_conflicts(session: Session) -> None:
    tenant = str(uuid.uuid4())
    first = _var_model(session, tenant, confidence="0.95")
    assert _var_model(session, tenant, confidence="0.95") == first  # idempotent
    with pytest.raises(ModelVersionConflictError):
        _var_model(session, tenant, confidence="0.99")  # same label, different declaration
    with pytest.raises(ModelVersionConflictError):
        _var_model(session, tenant, code_version="risk-v2", confidence="0.95")  # new code
    with pytest.raises(ValueError):
        _var_model(session, tenant, confidence="0.975")  # outside the v1 vocabulary
    with pytest.raises(ValueError):
        _var_model(session, tenant, confidence="0.94995")  # near-vocabulary: REFUSED, not coerced
    with pytest.raises(ValueError):
        _var_model(session, tenant, confidence="abc")  # malformed: ValueError, never a crash
    with pytest.raises(ValueError):
        register_var_model(
            session,
            tenant_id=tenant,
            actor_id="a",
            code_version="risk-v1",
            confidence_level="0.95",
            horizon_days=10,  # v1 is 1-day only
        )


def test_malformed_declared_parameters_refused_not_500(session: Session) -> None:
    # A 'risk.var.parametric' version minted via the GENERIC registration (same permission) with
    # malformed/absent/tampered declarations must refuse as a model-identity failure (the P3-4
    # review lesson), incl. a z_score that does not match the registered table for the declared
    # confidence (a tampered constant must not drive a governed number).
    from irp_shared.model.service import register_model, register_model_version
    from irp_shared.risk.bootstrap import VAR_MODEL_CODE

    tenant = str(uuid.uuid4())
    model = register_model(
        session,
        tenant_id=tenant,
        code=VAR_MODEL_CODE,
        name="generic",
        model_type="VAR",
        actor_id="a",
    )
    cases = (
        ("v1", ["confidence_level=abc", "horizon_days=1", f"z_score={Z95}"]),
        ("v2", ["horizon_days=1", f"z_score={Z95}"]),  # confidence absent
        ("v3", ["confidence_level=0.9500", "horizon_days=one", f"z_score={Z95}"]),
        ("v4", ["confidence_level=0.9500", "horizon_days=1", "z_score=9.999999999999"]),  # tampered
        (
            "v5",
            [
                "confidence_level=0.9500",
                "confidence_level=0.9900",
                "horizon_days=1",
                f"z_score={Z95}",
            ],
        ),
        # A WELL-FORMED non-v1 horizon: the number is 1-day (no sqrt(h)); a declared 250 would
        # make the immutable row misstate its own horizon (the 2026-07 review fix).
        ("v6", ["confidence_level=0.9500", "horizon_days=250", f"z_score={Z95}"]),
        ("v7", ["confidence_level=0.9500", "horizon_days=\u00b2", f"z_score={Z95}"]),  # unicode
    )
    for label, assumptions in cases:
        version = register_model_version(
            session,
            model=model,
            version_label=label,
            actor_id="a",
            methodology_ref=VAR_METHODOLOGY_REF,
            code_version="risk-v1",
            status="REGISTERED",
            assumptions=assumptions,
            limitations=[],
        )
        session.flush()
        with pytest.raises(WrongModelVersionError):
            declared_var_parameters(session, version)
    # And the governed registration path maps a same-label malformed twin to the identity error.
    with pytest.raises(WrongModelVersionError):
        register_var_model(
            session, tenant_id=tenant, actor_id="a", code_version="risk-v1", confidence_level="0.95"
        )


# ---------- full-stack fixtures (the two upstream governed runs) ----------


def _seed_upstream_runs(db: Session, tenant: str) -> tuple[str, str]:
    """Seed the FULL upstream chain: two holdings (USD + EUR marks) -> a COMPLETED exposure run
    -> a COMPLETED factor-exposure run over FX_USD/FX_EUR (x = 30000 USD-factor + 40000
    EUR-factor, base USD) + captured return windows on the same factors -> a COMPLETED
    covariance run. Returns (factor_exposure_run_id, covariance_run_id)."""
    for code in ("USD", "EUR"):  # idempotent (the fixture may seed twice per tenant)
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
    from irp_shared.marketdata.models import FxRate

    fx_exists = db.execute(
        select(FxRate).where(FxRate.tenant_id == tenant, FxRate.base_currency == "EUR")
    ).scalar_one_or_none()
    if fx_exists is None:  # idempotent (the fixture may seed twice per tenant)
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

    from irp_shared.marketdata.models import Factor

    factor_ids: list[str] = []
    for code, ccy, values in (
        ("FX_USD", "USD", ["0.01", "0.02", "0.03", "0.04"]),
        ("FX_EUR", "EUR", ["0.04", "0.03", "0.02", "0.01"]),
    ):
        existing = db.execute(
            select(Factor).where(Factor.tenant_id == tenant, Factor.factor_code == code)
        ).scalar_one_or_none()
        if existing is not None:  # idempotent: reuse the factor + its captured returns
            factor_ids.append(existing.id)
            continue
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
    return fx_run.run.run_id, cov_run.run.run_id


def _run(
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


def _count_runs(db: Session, tenant: str) -> int:
    return db.execute(
        select(func.count())
        .select_from(CalculationRun)
        .where(CalculationRun.tenant_id == tenant, CalculationRun.run_type == "VAR")
    ).scalar_one()


def _count_results(db: Session, tenant: str) -> int:
    return db.execute(
        select(func.count()).select_from(VarResult).where(VarResult.tenant_id == tenant)
    ).scalar_one()


# ---------- (3) positive correctness (full stack) ----------


def test_full_stack_build_path_bindings_and_numpy_agreement(session: Session) -> None:
    import numpy as np

    tenant = str(uuid.uuid4())
    fx_run, cov_run = _seed_upstream_runs(session, tenant)
    mv = _var_model(session, tenant, confidence="0.95")
    result = _run(session, tenant, mv, fx_run, cov_run)
    assert result.status == RunStatus.COMPLETED.value and len(result.rows) == 1
    row = result.rows[0]
    assert row.metric_type == "VAR_PARAMETRIC"
    assert row.base_currency == "USD"
    assert row.confidence_level == Decimal("0.9500") and row.horizon_days == 1
    assert row.z_score == Z95
    assert row.exposure_run_id == fx_run and row.covariance_run_id == cov_run
    assert row.n_factors == 2 and row.n_observations == 4
    assert row.window_start == D1 and row.window_end == D4
    assert row.calculation_run_id == result.run.run_id
    assert row.input_snapshot_id == result.run.input_snapshot_id
    # Independent float recomputation from the PINNED snapshot content (numpy cross-check).
    comps = list_components(session, snapshot_id=row.input_snapshot_id, acting_tenant=tenant)
    x: dict[str, float] = {}
    cov: dict[tuple[str, str], float] = {}
    for c in comps:
        data = json.loads(c.captured_content)
        if c.component_kind == COMPONENT_KIND_FACTOR_EXPOSURE:
            fid = data["factor_id"]
            x[fid] = x.get(fid, 0.0) + float(data["exposure_amount"])
        else:
            cov[(data["factor_id_1"], data["factor_id_2"])] = float(data["covariance_value"])
    ids = sorted(x)
    mat = np.array([[cov[tuple(sorted((r, c)))] for c in ids] for r in ids])
    vec = np.array([x[i] for i in ids])
    want = float(Z95) * math.sqrt(float(vec @ mat @ vec))
    assert abs(float(row.var_value) - want) <= 1e-9 * want
    v = verify_snapshot(session, snapshot_id=row.input_snapshot_id, acting_tenant=tenant)
    assert v.ok  # IA-row pins are byte-stable


def _mint_var_snapshot(
    session: Session, tenant: str, exposure_rows: list[dict], covariance_rows: list[dict]
):  # noqa: ANN202
    """Hand-mint a VAR_INPUT snapshot with ARBITRARY pinned content (bypassing the governed
    builder) — the adjudication-gate probe AND the exact-hand-reference consume-path vehicle."""
    from irp_shared.snapshot.service import _append_spec, _persist_snapshot

    specs: list = []
    for content in exposure_rows:
        content = dict(content)
        # "_anchor" decouples the component target id from the captured content id — the
        # duplicate-content smuggle vector (distinct components, identical pinned row).
        anchor_id = content.pop("_anchor", None) or content["id"]
        anchor = SimpleNamespace(id=anchor_id, valid_from=None, system_from=T0, record_version=None)
        _append_spec(
            specs, COMPONENT_KIND_FACTOR_EXPOSURE, "factor_exposure_result", anchor, content
        )
    for content in covariance_rows:
        content = dict(content)
        anchor_id = content.pop("_anchor", None) or content["id"]
        anchor = SimpleNamespace(id=anchor_id, valid_from=None, system_from=T0, record_version=None)
        _append_spec(specs, COMPONENT_KIND_COVARIANCE, "covariance_result", anchor, content)
    header = _persist_snapshot(
        session,
        acting_tenant=tenant,
        actor=SnapshotActor(actor_id="s"),
        specs=specs,
        label="",
        purpose=PURPOSE_VAR_INPUT,
        as_of_valid_at=VALID_AT,
        as_of_known_at=VALID_AT,
        as_of_valuation_date=D4,
        binding_predicate_version="test:hand-minted",
    )
    session.flush()
    return header


def _exposure_content(run_id: str, fid: str, code: str, amount: str, base: str = "USD") -> dict:
    return {
        "id": str(uuid.uuid4()),
        "tenant_id": str(uuid.uuid4()),
        "calculation_run_id": run_id,
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


def test_full_stack_exact_hand_reference_via_consume_path(session: Session) -> None:
    # The exact 3-4-5 reference THROUGH the governed consume path: a hand-minted VAR_INPUT
    # snapshot pinning x=(30000, 40000) over uncorrelated 1E-4-variance factors. The pinned
    # provenance run ids must be REAL own-tenant COMPLETED runs (the 2026-07 review fix
    # re-resolves them before they reach the hard-FK columns).
    tenant = str(uuid.uuid4())
    exp_run, cov_run = _seed_upstream_runs(session, tenant)
    mv = _var_model(session, tenant, confidence="0.95")
    fa, fb = str(uuid.uuid4()).lower(), str(uuid.uuid4()).lower()
    snap = _mint_var_snapshot(
        session,
        tenant,
        [
            _exposure_content(exp_run, fa, "A", "30000.000000"),
            _exposure_content(exp_run, fb, "B", "40000.000000"),
        ],
        [
            _covariance_content(cov_run, fa, fa, "0.00010000000000000000"),
            _covariance_content(cov_run, fb, fb, "0.00010000000000000000"),
            _covariance_content(cov_run, fa, fb, "0E-20"),
        ],
    )
    result = _run(session, tenant, mv, None, None, snapshot_id=snap.id)
    assert result.status == RunStatus.COMPLETED.value
    row = result.rows[0]
    assert row.sigma == REF1_SIGMA
    assert row.var_value == REF1_VAR95
    assert row.exposure_run_id == exp_run and row.covariance_run_id == cov_run


# ---------- (4) reproducibility + pin invariance ----------


def test_exact_rerun_and_consume_equals_build(session: Session) -> None:
    tenant = str(uuid.uuid4())
    fx_run, cov_run = _seed_upstream_runs(session, tenant)
    mv = _var_model(session, tenant)
    first = _run(session, tenant, mv, fx_run, cov_run)
    second = _run(session, tenant, mv, None, None, snapshot_id=first.run.input_snapshot_id)
    assert (
        second.rows[0].sigma == first.rows[0].sigma
        and second.rows[0].var_value == first.rows[0].var_value
    )


def test_pin_invariance_under_upstream_reruns(session: Session) -> None:
    # New upstream runs must not move a pinned VaR — proven NON-VACUOUSLY (the 2026-07 review
    # fold): the upstream data CHANGES (a vendor supersede), a fresh BUILD produces a DIFFERENT
    # number (so a live-read defect would be caught), and the pinned consume stays invariant.
    from irp_shared.marketdata.factor import supersede_factor_return
    from irp_shared.marketdata.models import Factor

    tenant = str(uuid.uuid4())
    fx_run, cov_run = _seed_upstream_runs(session, tenant)
    mv = _var_model(session, tenant)
    first = _run(session, tenant, mv, fx_run, cov_run)
    # Vendor supersede moves a window return -> a NEW covariance run yields a different Sigma.
    usd = session.execute(
        select(Factor).where(Factor.tenant_id == tenant, Factor.factor_code == "FX_USD")
    ).scalar_one()
    supersede_factor_return(
        session,
        usd,
        return_date=D2,
        # a realistic restatement, distinct from the pinned 0.02 head
        return_value=Decimal("-0.02"),
        acting_tenant=tenant,
        actor=FactorActor(actor_id="s"),
        effective_at=datetime(2026, 5, 27, tzinfo=UTC),
    )
    session.flush()
    cov_mv = register_covariance_model(
        session, tenant_id=tenant, actor_id="a", code_version="risk-v1", window_observations=4
    )
    eur = session.execute(
        select(Factor).where(Factor.tenant_id == tenant, Factor.factor_code == "FX_EUR")
    ).scalar_one()
    cov_run2 = run_covariance(
        session,
        acting_tenant=tenant,
        actor=CovarianceActor(actor_id="a"),
        code_version="risk-v1",
        environment_id="ci",
        model_version_id=cov_mv.id,
        factor_ids=[usd.id, eur.id],
    )
    fresh = _run(session, tenant, mv, fx_run, cov_run2.run.run_id)
    assert fresh.rows[0].var_value != first.rows[0].var_value  # the change IS detectable
    # ... yet the PINNED snapshot reproduces the original number exactly.
    second = _run(session, tenant, mv, None, None, snapshot_id=first.run.input_snapshot_id)
    assert second.rows[0].var_value == first.rows[0].var_value
    v = verify_snapshot(session, snapshot_id=first.run.input_snapshot_id, acting_tenant=tenant)
    assert v.ok


# ---------- (5) pre-create refusals (zero run / zero rows / fail-closed) ----------


def test_missing_inputs_and_wrong_model_refused(session: Session) -> None:
    tenant = str(uuid.uuid4())
    fx_run, cov_run = _seed_upstream_runs(session, tenant)
    mv = _var_model(session, tenant)
    for kw in ({"code_version": ""}, {"environment_id": ""}, {"model_version_id": ""}):
        with pytest.raises(VarInputError):
            run_var(
                session,
                acting_tenant=tenant,
                actor=ACTOR,
                **{
                    "code_version": "risk-v1",
                    "environment_id": "ci",
                    "model_version_id": mv,
                    "exposure_run_id": fx_run,
                    "covariance_run_id": cov_run,
                    **kw,
                },
            )
    with pytest.raises(VarInputError):
        _run(session, tenant, mv, fx_run, None)  # covariance_run_id missing
    with pytest.raises(UnregisteredModelError):
        _run(session, tenant, str(uuid.uuid4()), fx_run, cov_run)
    wrong_family = register_covariance_model(
        session, tenant_id=tenant, actor_id="a", code_version="risk-v1", window_observations=4
    ).id
    with pytest.raises(WrongModelVersionError):
        _run(session, tenant, wrong_family, fx_run, cov_run)
    assert _count_runs(session, tenant) == 0
    assert _count_results(session, tenant) == 0


def test_coverage_gap_refused_no_imputation(session: Session) -> None:
    # An exposure factor NOT covered by the covariance matrix is a pre-create refusal.
    tenant = str(uuid.uuid4())
    mv = _var_model(session, tenant)
    fa, fb, fc = (str(uuid.uuid4()).lower() for _ in range(3))
    exp_run, cov_run = str(uuid.uuid4()).lower(), str(uuid.uuid4()).lower()
    snap = _mint_var_snapshot(
        session,
        tenant,
        [
            _exposure_content(exp_run, fa, "A", "30000.000000"),
            _exposure_content(exp_run, fc, "C", "1.000000"),  # uncovered factor
        ],
        [
            _covariance_content(cov_run, fa, fa, "0.0001"),
            _covariance_content(cov_run, fb, fb, "0.0001"),
            _covariance_content(cov_run, fa, fb, "0"),
        ],
    )
    with pytest.raises(VarInputError, match="not covered"):
        _run(session, tenant, mv, None, None, snapshot_id=snap.id)
    assert _count_runs(session, tenant) == 0


def test_mixed_run_and_mixed_currency_and_wrong_vocab_refused(session: Session) -> None:
    tenant = str(uuid.uuid4())
    mv = _var_model(session, tenant)
    fa, fb = str(uuid.uuid4()).lower(), str(uuid.uuid4()).lower()
    run1, run2, cov_run = (str(uuid.uuid4()).lower() for _ in range(3))
    diag = lambda cr: [  # noqa: E731
        _covariance_content(cr, fa, fa, "0.0001"),
        _covariance_content(cr, fb, fb, "0.0001"),
        _covariance_content(cr, fa, fb, "0"),
    ]
    # (a) mixed exposure runs
    snap = _mint_var_snapshot(
        session,
        tenant,
        [
            _exposure_content(run1, fa, "A", "1.000000"),
            _exposure_content(run2, fb, "B", "1.000000"),
        ],
        diag(cov_run),
    )
    with pytest.raises(VarInputError, match="multiple runs"):
        _run(session, tenant, mv, None, None, snapshot_id=snap.id)
    # (b) mixed base currency
    rows = [
        _exposure_content(run1, fa, "A", "1.000000", base="USD"),
        _exposure_content(run1, fb, "B", "1.000000", base="EUR"),
    ]
    snap = _mint_var_snapshot(session, tenant, rows, diag(cov_run))
    with pytest.raises(VarInputError, match="base currencies"):
        _run(session, tenant, mv, None, None, snapshot_id=snap.id)
    # (c) wrong covariance vocabulary
    bad_vocab = diag(cov_run)
    for c in bad_vocab:
        c["frequency"] = "WEEKLY"
    snap = _mint_var_snapshot(
        session,
        tenant,
        [
            _exposure_content(run1, fa, "A", "1.000000"),
            _exposure_content(run1, fb, "B", "1.000000"),
        ],
        bad_vocab,
    )
    with pytest.raises(VarInputError, match="vocabulary|COVARIANCE/SIMPLE/DAILY"):
        _run(session, tenant, mv, None, None, snapshot_id=snap.id)
    assert _count_runs(session, tenant) == 0


def test_adjudication_pair_shape_probes(session: Session) -> None:
    # Reversed-order pins, duplicate canonical pairs, a missing OFF-DIAGONAL pair (all factors
    # covered), and a duplicated exposure pin each refuse pre-create (the 2026-07 review folds).
    tenant = str(uuid.uuid4())
    mv = _var_model(session, tenant)
    fa, fb, fc = sorted(str(uuid.uuid4()).lower() for _ in range(3))
    run1, cov_run = str(uuid.uuid4()).lower(), str(uuid.uuid4()).lower()
    exposure = [
        _exposure_content(run1, fa, "A", "1.000000"),
        _exposure_content(run1, fb, "B", "1.000000"),
    ]
    reversed_pair = _covariance_content(cov_run, fa, fb, "0")
    reversed_pair["factor_id_1"], reversed_pair["factor_id_2"] = (
        reversed_pair["factor_id_2"],
        reversed_pair["factor_id_1"],
    )
    snap = _mint_var_snapshot(
        session,
        tenant,
        exposure,
        [
            _covariance_content(cov_run, fa, fa, "0.0001"),
            _covariance_content(cov_run, fb, fb, "0.0001"),
            reversed_pair,
        ],
    )
    with pytest.raises(VarInputError, match="non-canonical"):
        _run(session, tenant, mv, None, None, snapshot_id=snap.id)
    snap = _mint_var_snapshot(
        session,
        tenant,
        exposure,
        [
            _covariance_content(cov_run, fa, fa, "0.0001"),
            _covariance_content(cov_run, fb, fb, "0.0001"),
            _covariance_content(cov_run, fa, fb, "0"),
            _covariance_content(cov_run, fa, fb, "0.0001"),  # conflicting duplicate
        ],
    )
    with pytest.raises(VarInputError, match="duplicate covariance pair"):
        _run(session, tenant, mv, None, None, snapshot_id=snap.id)
    exposure3 = exposure + [_exposure_content(run1, fc, "C", "1.000000")]
    snap = _mint_var_snapshot(
        session,
        tenant,
        exposure3,
        [
            _covariance_content(cov_run, fa, fa, "0.0001"),
            _covariance_content(cov_run, fb, fb, "0.0001"),
            _covariance_content(cov_run, fc, fc, "0.0001"),
            _covariance_content(cov_run, fa, fb, "0"),
            _covariance_content(cov_run, fa, fc, "0"),
        ],
    )
    with pytest.raises(VarInputError, match="missing the pair"):
        _run(session, tenant, mv, None, None, snapshot_id=snap.id)
    dup_row = _exposure_content(run1, fa, "A", "1.000000")
    dup_twin = dict(dup_row)  # same captured id — would double-count x_a
    dup_twin["_anchor"] = str(uuid.uuid4())  # a DISTINCT component target (the smuggle shape)
    snap = _mint_var_snapshot(
        session,
        tenant,
        [dup_row, dup_twin, _exposure_content(run1, fb, "B", "1.000000")],
        [
            _covariance_content(cov_run, fa, fa, "0.0001"),
            _covariance_content(cov_run, fb, fb, "0.0001"),
            _covariance_content(cov_run, fa, fb, "0"),
        ],
    )
    with pytest.raises(VarInputError, match="duplicate pinned exposure"):
        _run(session, tenant, mv, None, None, snapshot_id=snap.id)
    assert _count_runs(session, tenant) == 0


def test_adjudication_magnitude_and_malformed_content_probes(session: Session) -> None:
    tenant = str(uuid.uuid4())
    mv = _var_model(session, tenant)
    fa, fb = sorted(str(uuid.uuid4()).lower() for _ in range(2))
    run1, cov_run = str(uuid.uuid4()).lower(), str(uuid.uuid4()).lower()
    diag = [
        _covariance_content(cov_run, fa, fa, "0.0001"),
        _covariance_content(cov_run, fb, fb, "0.0001"),
        _covariance_content(cov_run, fa, fb, "0"),
    ]
    snap = _mint_var_snapshot(
        session,
        tenant,
        [
            _exposure_content(run1, fa, "A", "1E+50"),  # beyond the source-column envelope
            _exposure_content(run1, fb, "B", "1.000000"),
        ],
        diag,
    )
    with pytest.raises(VarInputError, match="source-column envelope"):
        _run(session, tenant, mv, None, None, snapshot_id=snap.id)
    bad = [dict(d) for d in diag]
    bad[2]["covariance_value"] = "n/a"  # structurally malformed: 422 class, never a raw 500
    snap = _mint_var_snapshot(
        session,
        tenant,
        [
            _exposure_content(run1, fa, "A", "1.000000"),
            _exposure_content(run1, fb, "B", "1.000000"),
        ],
        bad,
    )
    with pytest.raises(VarInputError, match="well-formed v1 input"):
        _run(session, tenant, mv, None, None, snapshot_id=snap.id)
    missing = [dict(d) for d in diag]
    del missing[0]["n_observations"]  # a missing required key
    snap = _mint_var_snapshot(
        session,
        tenant,
        [
            _exposure_content(run1, fa, "A", "1.000000"),
            _exposure_content(run1, fb, "B", "1.000000"),
        ],
        missing,
    )
    with pytest.raises(VarInputError, match="well-formed v1 input"):
        _run(session, tenant, mv, None, None, snapshot_id=snap.id)
    assert _count_runs(session, tenant) == 0


def test_pinned_provenance_run_ids_must_resolve_own_tenant(session: Session) -> None:
    # The 2026-07 review's principal finding: the provenance ids come from pinned content and
    # feed hard-FK columns (PG FK checks bypass RLS) — they MUST re-resolve own-tenant.
    tenant, victim = str(uuid.uuid4()), str(uuid.uuid4())
    foreign_fx_run, foreign_cov_run = _seed_upstream_runs(session, victim)  # tenant B's runs
    mv = _var_model(session, tenant)
    fa, fb = sorted(str(uuid.uuid4()).lower() for _ in range(2))
    snap = _mint_var_snapshot(
        session,
        tenant,  # minted UNDER tenant A but pinning tenant B's run ids in the content
        [
            _exposure_content(foreign_fx_run, fa, "A", "1.000000"),
            _exposure_content(foreign_fx_run, fb, "B", "1.000000"),
        ],
        [
            _covariance_content(foreign_cov_run, fa, fa, "0.0001"),
            _covariance_content(foreign_cov_run, fb, fb, "0.0001"),
            _covariance_content(foreign_cov_run, fa, fb, "0"),
        ],
    )
    from irp_shared.risk import FactorExposureRunNotVisible

    with pytest.raises(FactorExposureRunNotVisible):
        _run(session, tenant, mv, None, None, snapshot_id=snap.id)
    assert _count_runs(session, tenant) == 0


def test_column_legal_extreme_magnitude_fails_closed_not_500(session: Session) -> None:
    # sigma ~1e24 from column-legal pins overflows Numeric(28,6) on PG — the magnitude gate
    # converts it into a committed FAILED run with evidence (the 2026-07 review fix).
    tenant = str(uuid.uuid4())
    exp_run, cov_run = _seed_upstream_runs(session, tenant)
    mv = _var_model(session, tenant)
    fa, fb = sorted(str(uuid.uuid4()).lower() for _ in range(2))
    snap = _mint_var_snapshot(
        session,
        tenant,
        [
            _exposure_content(exp_run, fa, "A", "1000000000000000000.000000"),  # 1e18
            _exposure_content(exp_run, fb, "B", "1.000000"),
        ],
        [
            _covariance_content(cov_run, fa, fa, "1000000000000.00000000000000000000"),  # 1e12
            _covariance_content(cov_run, fb, fb, "0.0001"),
            _covariance_content(cov_run, fa, fb, "0"),
        ],
    )
    result = _run(session, tenant, mv, None, None, snapshot_id=snap.id)
    assert result.status == RunStatus.FAILED.value and result.rows == []
    assert result.failure_reason and "magnitude-out-of-range" in result.failure_reason


def test_wrong_purpose_unknown_snapshot_and_upstream_states_refused(session: Session) -> None:
    from irp_shared.snapshot import SnapshotNotFound

    tenant = str(uuid.uuid4())
    fx_run, cov_run = _seed_upstream_runs(session, tenant)
    mv = _var_model(session, tenant)
    with pytest.raises(SnapshotNotFound):
        _run(session, tenant, mv, None, None, snapshot_id=str(uuid.uuid4()))
    # Wrong purpose: consume a COVARIANCE_INPUT snapshot id.
    cov_run_row = session.execute(
        select(CalculationRun).where(CalculationRun.run_id == cov_run)
    ).scalar_one()
    with pytest.raises(VarInputError, match="purpose"):
        _run(session, tenant, mv, None, None, snapshot_id=cov_run_row.input_snapshot_id)
    # Cross-run-type ids on the build path (a covariance run where an exposure run belongs).
    from irp_shared.risk import FactorExposureRunNotVisible

    with pytest.raises(FactorExposureRunNotVisible):
        _run(session, tenant, mv, cov_run, cov_run)
    assert _count_runs(session, tenant) == 0


def test_builder_refuses_empty_upstream_rows(session: Session) -> None:
    tenant = str(uuid.uuid4())
    with pytest.raises(VarSnapshotError):
        build_var_snapshot(
            session,
            acting_tenant=tenant,
            actor=SnapshotActor(actor_id="s"),
            exposure_run_id=str(uuid.uuid4()),
            covariance_run_id=str(uuid.uuid4()),
        )


# ---------- (6) post-create FAILED (the REACHABLE non-PSD radicand gate) ----------


def test_non_psd_snapshot_fails_closed_post_create(session: Session) -> None:
    tenant = str(uuid.uuid4())
    exp_run, cov_run = _seed_upstream_runs(session, tenant)  # REAL provenance runs (review fix)
    mv = _var_model(session, tenant)
    fa, fb = str(uuid.uuid4()).lower(), str(uuid.uuid4()).lower()
    snap = _mint_var_snapshot(
        session,
        tenant,
        [
            _exposure_content(exp_run, fa, "A", "1.000000"),
            _exposure_content(exp_run, fb, "B", "-1.000000"),
        ],
        [
            _covariance_content(cov_run, fa, fa, "0.0001"),
            _covariance_content(cov_run, fb, fb, "0.0001"),
            _covariance_content(cov_run, fa, fb, "0.0002"),  # "correlation" 2: NOT PSD
        ],
    )
    result = _run(session, tenant, mv, None, None, snapshot_id=snap.id)
    assert result.status == RunStatus.FAILED.value
    assert result.rows == [] and _count_results(session, tenant) == 0
    assert result.failure_reason and "non-psd-radicand" in result.failure_reason
    # Durable evidence: the FAILED transition audit + persisted DQ rows + the DEPENDS_ON edge.
    from irp_shared.dq.models import DataQualityResult

    failed_events = (
        session.execute(
            select(AuditEvent).where(
                AuditEvent.entity_id == result.run.run_id,
                AuditEvent.event_type == "CALC.RUN_STATUS_CHANGE",
                AuditEvent.outcome == "failure",
            )
        )
        .scalars()
        .all()
    )
    assert len(failed_events) == 1
    dq_rows = (
        session.execute(
            select(DataQualityResult).where(
                DataQualityResult.target_entity_type == "calculation_run",
                DataQualityResult.target_entity_id == result.run.run_id,
            )
        )
        .scalars()
        .all()
    )
    assert dq_rows
    dep = (
        session.execute(
            select(LineageEdge).where(
                LineageEdge.source_type == SOURCE_TYPE_DATA_SNAPSHOT,
                LineageEdge.target_entity_id == result.run.run_id,
                LineageEdge.edge_kind == EDGE_KIND_DEPENDENCY,
            )
        )
        .scalars()
        .all()
    )
    assert len(dep) == 1


# ---------- (7) output contract / audit / lineage / append-only / grain ----------


def test_audit_calc_run_events_no_risk_event(session: Session) -> None:
    tenant = str(uuid.uuid4())
    fx_run, cov_run = _seed_upstream_runs(session, tenant)
    mv = _var_model(session, tenant)
    result = _run(session, tenant, mv, fx_run, cov_run)
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
    assert risk_events == []  # RISK.VAR_CREATE stays reserved-not-emitted


def test_lineage_origin_and_var_result_append_only(session: Session) -> None:
    from irp_shared.temporal import TemporalClass

    assert VarResult.__temporal_class__ == TemporalClass.IMMUTABLE_APPEND_ONLY
    tenant = str(uuid.uuid4())
    fx_run, cov_run = _seed_upstream_runs(session, tenant)
    mv = _var_model(session, tenant)
    result = _run(session, tenant, mv, fx_run, cov_run)
    origin = (
        session.execute(
            select(LineageEdge).where(
                LineageEdge.source_type == SOURCE_TYPE_CALCULATION_RUN,
                LineageEdge.target_entity_type == "var_result",
                LineageEdge.edge_kind == EDGE_KIND_ORIGIN,
            )
        )
        .scalars()
        .all()
    )
    assert {e.target_entity_id for e in origin} == {result.rows[0].id}
    session.commit()
    row = result.rows[0]
    row.var_value = Decimal("0")
    with pytest.raises(AppendOnlyViolation):
        session.flush()
    session.rollback()
    with pytest.raises(AppendOnlyViolation):
        session.delete(result.rows[0])
        session.flush()


def test_single_summary_row_grain_and_reader(session: Session) -> None:
    tenant = str(uuid.uuid4())
    fx_run, cov_run = _seed_upstream_runs(session, tenant)
    mv = _var_model(session, tenant)
    result = _run(session, tenant, mv, fx_run, cov_run)
    listed = list_vars(session, run_id=result.run.run_id, acting_tenant=tenant)
    assert len(listed) == 1 and listed[0].id == result.rows[0].id
    snap = resolve_snapshot(session, result.run.input_snapshot_id, acting_tenant=tenant)
    assert snap.purpose == PURPOSE_VAR_INPUT
    comps = list_components(session, snapshot_id=snap.id, acting_tenant=tenant)
    kinds = {c.component_kind for c in comps}
    assert kinds == {COMPONENT_KIND_FACTOR_EXPOSURE, COMPONENT_KIND_COVARIANCE}
    for c in comps:  # the IA-row pin flavor
        assert c.pinned_valid_from is None and c.pinned_record_version is None
        assert c.pinned_system_from is not None


# ---------- (8) entitlement REUSE parity (no new permission — OD-P3-5-K) ----------


def test_risk_permissions_reused_no_new_codes() -> None:
    all_codes = {code for perms in ROLE_TEMPLATES.values() for code in perms}
    assert "risk.run" in all_codes and "risk.view" in all_codes
    assert not {c for c in all_codes if "var" in c.split(".") or "value_at_risk" in c}


# ---------- (9) methodology doc ----------

_ROOT = pathlib.Path(__file__).resolve().parents[3]
_VAR_SERVICE_SRC = (_ROOT / "packages/shared-python/src/irp_shared/risk/var_service.py").read_text()
_VAR_KERNEL_SRC = (_ROOT / "packages/shared-python/src/irp_shared/risk/var_kernel.py").read_text()


def test_methodology_doc_exists_and_has_required_sections() -> None:
    doc = (_ROOT / VAR_METHODOLOGY_REF).read_text()
    for section in (
        "## Purpose & applicability",
        "## Inputs & data policy",
        "## Formulas & numerical standards",
        "## Assumptions",
        "## Limitations",
        "## Validation / reproduction tests",
        "## Known limitations",
    ):
        assert section in doc, section
    assert "SPECIFIC/IDIOSYNCRATIC RISK = 0" in doc  # the first-class honesty gap
    assert "1.644853626951" in doc and "2.326347874041" in doc  # the registered constants


def test_methodology_ref_matches_registered_version(session: Session) -> None:
    tenant = str(uuid.uuid4())
    mv_id = _var_model(session, tenant)
    version = session.get(ModelVersion, mv_id)
    assert version is not None and version.methodology_ref == VAR_METHODOLOGY_REF
    assert (_ROOT / version.methodology_ref).exists()


# ---------- (10) load-bearing scope fences ----------


def test_scope_fence_no_live_reads_in_compute_path() -> None:
    tree = ast.parse(_VAR_SERVICE_SRC)
    forbidden = {
        "list_factor_exposures",
        "list_covariances",
        "resolve_factor_exposure_run",
        "resolve_covariance_run",
        "resolve_factor",
    }
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name in ("_parse_pins", "_adjudicate_pins"):
            found.add(node.name)
            names = {n.id for n in ast.walk(node) if isinstance(n, ast.Name)}
            attrs = {n.attr for n in ast.walk(node) if isinstance(n, ast.Attribute)}
            assert not (names & forbidden), (node.name, names & forbidden)
            assert not (attrs & forbidden), (node.name, attrs & forbidden)
    assert found == {"_parse_pins", "_adjudicate_pins"}, found  # never vacuous


def test_scope_fence_no_future_method_imports_or_identifiers() -> None:
    for src in (_VAR_SERVICE_SRC, _VAR_KERNEL_SRC):
        tree = ast.parse(src)
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)
            elif isinstance(node, ast.Import):
                imported.update(a.name for a in node.names)
        for mod in imported:
            parts = set(mod.split("."))
            assert not (
                parts
                & {"scenario", "stress", "benchmark", "numpy", "scipy", "random", "statistics"}
            ), f"forbidden import {mod}"
        idents = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)} | {
            n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)
        }
        forbidden_idents = {
            "expected_shortfall",
            "historical",
            "monte_carlo",
            "simulate",
            "simulation",
            "random_seed",
            "backtest",
            "erf",
            "ppf",
            "norm_inv",
            "quantile",
            "annualize",
            "scenario_result",
            "stress_test",
            "tracking_error",
            "attribution",
        }
        assert not (idents & forbidden_idents), idents & forbidden_idents


# ---------- (11) migration head ----------


def test_migration_head_is_var() -> None:
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    cfg = Config(str(_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(_ROOT / "migrations"))
    script = ScriptDirectory.from_config(cfg)
    assert script.get_current_head() == "0030_active_risk"
    assert script.get_revision("0026_var").down_revision == "0025_covariance"
