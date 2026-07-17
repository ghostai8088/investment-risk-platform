"""ES-HS-1 suite: the empirical historical-simulation ES (kernel + registrar + binder).

The kernel legs re-derive every golden BY HAND in-test (exact Decimal arithmetic — the raw
pre-quantize values the kernel does not expose); the full-stack legs ride ``test_var_hs``'s
seeded chain (P&L_i = -10·i exactly). The SQLite tier CANNOT see the 0041 CHECK (migration-only,
ORM-invisible) — the CHECK legs live in ``test_es_hs_pg.py``.
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from decimal import Decimal, localcontext

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session
from test_var import session  # noqa: F401 - the shared in-memory session fixture
from test_var_hs import (  # noqa: F401 - the seeded-chain + snapshot-mint helpers
    ACTOR,
    _exp,
    _hs_run,
    _mint_hs_snapshot,
    _seed_chain,
    _win,
)

from irp_shared.calc.models import CalculationRun
from irp_shared.risk import (
    ES_HS_MODEL_CODE,
    ModelVersionConflictError,
    WrongModelVersionError,
    compute_historical_es,
    compute_historical_var,
    register_historical_var_es_model,
    register_historical_var_model,
    register_var_model,
)
from irp_shared.risk.var_hs_kernel import HsVarKernelError


def _dates(n: int) -> list[date]:
    return [date(2026, 1, 1) + timedelta(days=i) for i in range(n)]


def _series(values: list[str]) -> dict[date, dict[str, Decimal]]:
    return {d: {"f1": Decimal(v)} for d, v in zip(_dates(len(values)), values, strict=True)}


def _hand_es(pnls: list[Decimal], n: int, confidence: str) -> Decimal:
    """The Prop 4.1 reference, independently in-test: exact Decimal, single HALF_UP quantize."""
    a = Decimal(1) - Decimal(confidence)
    n_a = Decimal(n) * a
    m = int(n_a.to_integral_value(rounding="ROUND_FLOOR"))
    w = n_a - m
    ordered = sorted(pnls)
    with localcontext() as ctx:
        ctx.prec = 50
        tail = sum(ordered[:m], Decimal(0)) + w * ordered[m]
        return (-(tail / n_a)).quantize(Decimal("0.000001"), rounding="ROUND_HALF_UP")


# ---------- kernel ----------


def test_es_kernel_hand_reference_fractional_weight() -> None:
    # n=21, c=0.95: n·a = 1.05, m=1, w=0.05. Worst two P&Ls -500/-300 (x=1000):
    # ES = (500 + 0.05·300)/1.05 = 515/1.05 = 490.476190 (HALF_UP 6dp).
    exposures = {"f1": Decimal("1000")}
    values = (
        ["-0.5", "-0.3"]
        + [f"0.0{i}" for i in range(1, 10)]
        + [f"0.00{i}" for i in range(1, 10)]
        + ["0.002"]
    )
    est = compute_historical_es(exposures, _series(values), confidence=Decimal("0.9500"))
    assert est.n_observations == 21
    assert est.tail_floor_count == 1
    assert est.es_value == (Decimal("515") / Decimal("1.05")).quantize(Decimal("0.000001"))
    assert est.es_value == Decimal("490.476190")
    # The TCE trap (the ES-1 forbidden estimator): the mean of the worst ceil(n·a)=2 losses is
    # (500+300)/2 = 400 — it UNDERSTATES; the kernel must never produce it. Direction pinned,
    # magnitude never (fixture-dependent — the planning verifier's grading).
    tce = (Decimal("500") + Decimal("300")) / 2
    assert est.es_value > tce


def test_es_kernel_integer_na_zero_boundary_weight() -> None:
    # n=40, c=0.95: n·a = 2.0 EXACT, m=2, w=0 — the boundary term's coefficient is exactly
    # zero and index m+1 is still in range (index safety at the integer boundary).
    exposures = {"f1": Decimal("1000")}
    values = ["-0.5", "-0.3", "-0.2"] + [f"0.00{i % 9 + 1}" for i in range(37)]
    est = compute_historical_es(exposures, _series(values), confidence=Decimal("0.9500"))
    assert est.n_observations == 40
    assert est.tail_floor_count == 2
    assert est.es_value == Decimal("400.000000")  # (500+300)/2 — the worst-2 mean, exact


def test_es_kernel_es_geq_var_raw_grid_and_tied_equality() -> None:
    """ES >= VaR asserted at BOTH precisions across a deterministic fixture grid: the
    QUANTIZED kernel outputs, AND the RAW (unquantized, prec-50) values re-derived in-test
    from the fixture — the ratified OD-A independent guard (a sub-quantum raw inversion
    cannot hide behind monotone quantize). One LABELED tied-boundary fixture exercises raw
    EQUALITY (the worst m+1 P&Ls equal — the planning verifier's executed counterexample
    class)."""
    exposures = {"f1": Decimal("1000")}
    # Deterministic pseudo-random-ish grid: three window shapes x three tail shapes.
    grids: list[tuple[int, str, list[str]]] = []
    for n, conf in ((21, "0.9500"), (40, "0.9500"), (101, "0.9900")):
        base = [f"0.00{i % 9 + 1}" for i in range(n - 3)]
        grids.append((n, conf, ["-0.5", "-0.31", "-0.007"] + base))  # spread tail
        grids.append((n, conf, ["-0.5", "-0.5", "-0.5"] + base))  # TIED tail (equality leg)
        grids.append((n, conf, [f"0.0{i % 5 + 1}" for i in range(n)]))  # all-gains window
    for n, conf, values in grids:
        series = _series(values)
        var = compute_historical_var(exposures, series, confidence=Decimal(conf))
        es = compute_historical_es(exposures, series, confidence=Decimal(conf))
        assert es.es_value >= var.var_value, (n, conf, values[:3])
        pnls = [Decimal("1000") * Decimal(v) for v in values]
        assert es.es_value == _hand_es(pnls, n, conf), (n, conf)
        # The RAW comparison (the ratified OD-A obligation — the review's DOC-2 fold): BOTH
        # sides UNQUANTIZED at prec 50, re-derived from the fixture, independent of the
        # kernel's quantize step.
        with localcontext() as ctx:
            ctx.prec = 50
            a = Decimal(1) - Decimal(conf)
            n_a = Decimal(n) * a
            m = int(n_a.to_integral_value(rounding="ROUND_FLOOR"))
            w = n_a - m
            ordered = sorted(pnls)
            raw_es = -((sum(ordered[:m], Decimal(0)) + w * ordered[m]) / n_a)
            k = m if w == 0 else m + 1  # k = ceil(n·a)
            raw_var = -ordered[k - 1]
            assert raw_es >= raw_var, (n, conf)
    # The labeled tied fixture at the floor: raw equality ES == VaR (no quantize involved).
    tied = ["-0.5", "-0.5"] + [f"0.00{i % 9 + 1}" for i in range(19)]
    series = _series(tied)
    var = compute_historical_var(exposures, series, confidence=Decimal("0.9500"))
    es = compute_historical_es(exposures, series, confidence=Decimal("0.9500"))
    assert es.es_value == var.var_value == Decimal("500.000000")


def test_es_kernel_all_gains_negative_values_honest() -> None:
    # Every scenario a gain: VaR and ES both NEGATIVE, ES >= VaR still, never clamped.
    exposures = {"f1": Decimal("1000")}
    values = [f"0.0{i % 5 + 1}" for i in range(21)]
    series = _series(values)
    var = compute_historical_var(exposures, series, confidence=Decimal("0.9500"))
    es = compute_historical_es(exposures, series, confidence=Decimal("0.9500"))
    assert var.var_value < 0 and es.es_value < 0
    assert es.es_value >= var.var_value


def test_es_kernel_refusal_precedence_and_ill_formed() -> None:
    """Refusal precedence is part of the observable contract (the planning verifier): a
    doubly-bad input — bad confidence AND missing coverage — gets the CONFIDENCE refusal in
    BOTH kernels (validation stays ahead of the accumulation across the shared-helper
    refactor)."""
    exposures = {"f1": Decimal(1), "f2": Decimal(1)}
    missing_coverage = {date(2026, 1, 1): {"f1": Decimal("0.01")}}  # f2 has no return
    for compute in (compute_historical_var, compute_historical_es):
        with pytest.raises(HsVarKernelError, match="confidence"):
            compute(exposures, missing_coverage, confidence=Decimal("1.5"))
        with pytest.raises(HsVarKernelError, match="coverage"):
            compute(exposures, missing_coverage, confidence=Decimal("0.5"))
        with pytest.raises(HsVarKernelError, match="no exposures"):
            compute({}, missing_coverage, confidence=Decimal("0.5"))
        with pytest.raises(HsVarKernelError, match="no scenarios"):
            compute(exposures, {}, confidence=Decimal("0.5"))


def test_es_kernel_numpy_cross_check() -> None:
    """Float sorted-array arithmetic @1e-9 relative (numpy TEST-ONLY per the standing fence)."""
    numpy = pytest.importorskip("numpy")
    exposures = {"f1": Decimal("1000"), "f2": Decimal("-250")}
    n, conf = 101, "0.9900"
    v1 = [f"{(-1) ** i * ((i * 7) % 89 + 1) / 1000:.6f}" for i in range(n)]
    v2 = [f"{(-1) ** (i + 1) * ((i * 11) % 97 + 1) / 1000:.6f}" for i in range(n)]
    series = {
        d: {"f1": Decimal(a), "f2": Decimal(b)} for d, a, b in zip(_dates(n), v1, v2, strict=True)
    }
    est = compute_historical_es(exposures, series, confidence=Decimal(conf))
    pnls = numpy.sort(
        numpy.array([1000.0 * float(a) - 250.0 * float(b) for a, b in zip(v1, v2, strict=True)])
    )
    a = 1.0 - float(conf)
    n_a = n * a
    m = int(numpy.floor(n_a))
    w = n_a - m
    ref = -(pnls[:m].sum() + w * pnls[m]) / n_a
    # es_value is quantized to 6dp; the float reference is not — the bound is the quantum
    # half-step plus float noise (the raw agreement itself is pinned exactly by _hand_es above).
    assert abs(float(est.es_value) - ref) <= 5.1e-7 + 1e-9 * abs(ref)


# ---------- registrar ----------


def test_register_es_hs_identity_floor_and_conflicts(session: Session) -> None:  # noqa: F811
    tenant = str(uuid.uuid4())
    mv = register_historical_var_es_model(
        session,
        tenant_id=tenant,
        actor_id="a",
        code_version="v1",
        confidence_level="0.95",
        window_observations=21,
    )
    assert mv.status == "REGISTERED"
    # The estimator convention is REGISTRAR-STAMPED (never caller-suppliable).
    from irp_shared.risk import declared_es_hs_parameters

    declared = declared_es_hs_parameters(session, mv)
    assert declared.estimator_convention == "TAIL_MEAN_ACERBI_TASCHE_P41"
    assert (declared.confidence_level, declared.window_observations) == (Decimal("0.9500"), 21)
    # Idempotent same-declaration return.
    again = register_historical_var_es_model(
        session,
        tenant_id=tenant,
        actor_id="a",
        code_version="v1",
        confidence_level="0.95",
        window_observations=21,
    )
    assert again.id == mv.id
    # Same-label different-declaration -> the governed 409 class, never an IntegrityError.
    with pytest.raises(ModelVersionConflictError):
        register_historical_var_es_model(
            session,
            tenant_id=tenant,
            actor_id="a",
            code_version="v1",
            confidence_level="0.95",
            window_observations=40,
        )
    # The SHARED strict floor (n·(1-c) > 1) — identical to the VaR leg's.
    t2 = str(uuid.uuid4())
    for conf, bad_n in (("0.99", 100), ("0.95", 20)):
        with pytest.raises(ValueError):
            register_historical_var_es_model(
                session,
                tenant_id=t2,
                actor_id="a",
                code_version="v1",
                confidence_level=conf,
                window_observations=bad_n,
            )
    # Out-of-vocabulary confidence refused.
    with pytest.raises(ValueError):
        register_historical_var_es_model(
            session,
            tenant_id=t2,
            actor_id="a",
            code_version="v1",
            confidence_level="0.90",
            window_observations=21,
        )


# ---------- binder (full stack over the seeded chain: P&L_i = -10·i exactly) ----------


def _es_mv(db: Session, tenant: str, *, n: int = 21):  # noqa: ANN202
    return register_historical_var_es_model(
        db,
        tenant_id=tenant,
        actor_id="a",
        code_version="v1",
        confidence_level="0.95",
        window_observations=n,
    )


def test_es_hs_full_stack_build_hand_reference_n21(session: Session) -> None:  # noqa: F811
    tenant = str(uuid.uuid4())
    fx_run = _seed_chain(session, tenant, n_dates=21)
    mv = _es_mv(session, tenant)
    result = _hs_run(session, tenant, mv.id, exposure_run_id=fx_run)
    assert result.status == "COMPLETED"
    (row,) = result.rows
    # P&L_i = -10·i, worst two -210/-200; n·a = 1.05, m=1, w=0.05:
    # ES = (210 + 0.05·200)/1.05 = 220/1.05 = 209.523810 (HALF_UP 6dp) — vs VaR 200.
    assert row.var_value == Decimal("209.523810")
    assert row.metric_type == "ES_HISTORICAL"
    assert row.z_score is None and row.sigma is None and row.covariance_run_id is None
    assert row.exposure_run_id == fx_run
    assert (row.n_factors, row.n_observations) == (2, 21)
    assert row.base_currency == "USD"


def test_es_hs_full_stack_integer_na_n40(session: Session) -> None:  # noqa: F811
    tenant = str(uuid.uuid4())
    fx_run = _seed_chain(session, tenant, n_dates=40)
    mv = _es_mv(session, tenant, n=40)
    result = _hs_run(session, tenant, mv.id, exposure_run_id=fx_run)
    (row,) = result.rows
    # n·a = 2.0 exact, w=0: ES = (400+390)/2 = 395 (vs VaR 390 — the worst-2 mean).
    assert row.var_value == Decimal("395.000000")


def test_es_hs_and_var_hs_share_one_snapshot_es_geq_var(session: Session) -> None:  # noqa: F811
    """The BT-3 pairing design input, demonstrated live: the VaR-HS and ES-HS runs bound to the
    IDENTICAL input_snapshot_id see the same scenario set — the coherent (VaR, ES) pair with
    zero schema change. ES >= VaR on the shared window."""
    tenant = str(uuid.uuid4())
    fx_run = _seed_chain(session, tenant, n_dates=21)
    hs_mv = register_historical_var_model(
        session,
        tenant_id=tenant,
        actor_id="a",
        code_version="v1",
        confidence_level="0.95",
        window_observations=21,
    )
    var_result = _hs_run(session, tenant, hs_mv.id, exposure_run_id=fx_run)
    (var_row,) = var_result.rows
    es_mv = _es_mv(session, tenant)
    es_result = _hs_run(session, tenant, es_mv.id, snapshot_id=var_row.input_snapshot_id)
    (es_row,) = es_result.rows
    assert es_row.input_snapshot_id == var_row.input_snapshot_id
    assert es_row.var_value > var_row.var_value  # 209.523810 > 200 on the seeded chain
    assert {var_row.metric_type, es_row.metric_type} == {"VAR_HISTORICAL", "ES_HISTORICAL"}


def test_es_hs_wrong_family_refusals(session: Session) -> None:  # noqa: F811
    """A version of NEITHER historical family refuses with the FIRST (plain-HS) code's message
    (the _resolve_hs_family contract); the parametric binder still refuses an ES-HS version
    (reverse identity)."""
    from irp_shared.risk import VarInputError, run_var  # noqa: F401

    tenant = str(uuid.uuid4())
    fx_run = _seed_chain(session, tenant, n_dates=21)
    pmv = register_var_model(
        session, tenant_id=tenant, actor_id="a", code_version="v1", confidence_level="0.95"
    )
    with pytest.raises(WrongModelVersionError):
        _hs_run(session, tenant, pmv.id, exposure_run_id=fx_run)
    # Reverse identity: an ES-HS version cannot drive the parametric binder.
    es_mv = _es_mv(session, tenant)
    with pytest.raises(WrongModelVersionError):
        run_var(
            session,
            acting_tenant=tenant,
            actor=ACTOR,
            code_version="v1",
            environment_id="ci",
            model_version_id=str(es_mv.id),
            exposure_run_id=fx_run,
            covariance_run_id=fx_run,
        )


def test_es_hs_magnitude_gate_commits_failed_run(session: Session) -> None:  # noqa: F811
    """Column-legal-but-extreme pins drive |ES| past Numeric(28,6): a committed FAILED run +
    persisted reason + ZERO rows — the binder's abs()-envelope gate, never a 500 (the prec-50
    context keeps quantize-InvalidOperation unreachable for envelope-legal pins)."""
    tenant = str(uuid.uuid4())
    fx_run = _seed_chain(session, tenant, n_dates=21)
    mv = _es_mv(session, tenant)
    f1 = str(uuid.uuid4()).lower()
    snap = _mint_hs_snapshot(session, tenant, [_exp(fx_run, f1, "1E21")], [_win(f1, ["-10"] * 21)])
    result = _hs_run(session, tenant, mv.id, snapshot_id=snap.id)
    assert result.status == "FAILED"
    assert result.rows == []
    assert result.failure_reason is not None and "magnitude-out-of-range" in result.failure_reason
    run_row = session.execute(
        select(CalculationRun).where(CalculationRun.run_id == result.run.run_id)
    ).scalar_one()
    assert run_row.failure_reason == result.failure_reason


def test_es_hs_model_code_constant() -> None:
    assert ES_HS_MODEL_CODE == "risk.var.historical_es"


def test_es_hs_generic_mint_declared_parse_and_twin_refusals(session: Session) -> None:  # noqa: F811
    """The review's ADV-1 fold: the generic registration path can stamp ANY assumptions —
    every malformed/inadequate ES-HS declaration must refuse at BIND (WrongModelVersionError),
    incl. the floor bypass (0.9750 needs >=41), the quantile-for-estimator swap, and the
    absent/wrong/duplicated estimator convention. Plus the registrar's non-REGISTERED
    same-label twin refusal (the P3-C1 contract)."""
    from irp_shared.model.service import register_model, register_model_version
    from irp_shared.risk.bootstrap import ES_HS_MODEL_CODE as CODE

    tenant = str(uuid.uuid4())
    model = register_model(
        session, tenant_id=tenant, code=CODE, name="eshs", model_type="VAR", actor_id="a"
    )
    good = [
        "confidence_level=0.9500",
        "horizon_days=1",
        "window_observations=21",
        "estimator_convention=TAIL_MEAN_ACERBI_TASCHE_P41",
    ]
    cases = {
        "missing-estimator": good[:3],
        "wrong-estimator": good[:3] + ["estimator_convention=SIMPLE_TAIL_AVERAGE"],
        "quantile-for-estimator": good[:3] + ["quantile_convention=LOWER_ORDER_STATISTIC"],
        "dup-estimator": good + ["estimator_convention=TAIL_MEAN_ACERBI_TASCHE_P41"],
        "floor-bypass-0975-40": [
            "confidence_level=0.9750",
            "horizon_days=1",
            "window_observations=40",  # the 0.9750 floor is 41
            "estimator_convention=TAIL_MEAN_ACERBI_TASCHE_P41",
        ],
        "window-zero": [
            "confidence_level=0.9500",
            "horizon_days=1",
            "window_observations=0",
            "estimator_convention=TAIL_MEAN_ACERBI_TASCHE_P41",
        ],
        "wrong-horizon": [
            "confidence_level=0.9500",
            "horizon_days=250",
            "window_observations=21",
            "estimator_convention=TAIL_MEAN_ACERBI_TASCHE_P41",
        ],
        "short-form-confidence": [
            "confidence_level=0.95",
            "horizon_days=1",
            "window_observations=21",
            "estimator_convention=TAIL_MEAN_ACERBI_TASCHE_P41",
        ],
    }
    for label, assumptions in cases.items():
        version = register_model_version(
            session,
            model=model,
            version_label=f"gen-{label}",
            actor_id="a",
            methodology_ref="x",
            code_version="v1",
            status="REGISTERED",
            assumptions=tuple(assumptions),
            limitations=(),
        )
        with pytest.raises(WrongModelVersionError):
            _hs_run(session, tenant, version.id, exposure_run_id=str(uuid.uuid4()))
    # The squatted non-REGISTERED same-label twin refuses at the registrar.
    t2 = str(uuid.uuid4())
    model2 = register_model(
        session, tenant_id=t2, code=CODE, name="eshs", model_type="VAR", actor_id="a"
    )
    register_model_version(
        session,
        model=model2,
        version_label="v1",
        actor_id="a",
        methodology_ref="x",
        code_version="v1",
        status=None,
        assumptions=(),
        limitations=(),
    )
    with pytest.raises(WrongModelVersionError):
        register_historical_var_es_model(
            session,
            tenant_id=t2,
            actor_id="a",
            code_version="v1",
            confidence_level="0.95",
            window_observations=21,
        )
