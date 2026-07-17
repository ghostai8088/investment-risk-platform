"""P3-8 ex-post benchmark-relative binder + kernel (SQLite): the EIGHTH governed number (ENT-054).

Covers the pure kernel goldens + an INDEPENDENT ``statistics`` cross-check; the full-stack
build-in-request + consume-existing golden (realized active return / tracking difference / tracking
error / information ratio over a real PM-1 ``PORTFOLIO_RETURN`` run + a captured benchmark
series — ENT-052's FIRST governed consumer); the conditional-emission rules (n=1 => no TE/IR;
TE=0 => no IR); the pre-create refusal battery (linkage mismatch, currency mismatch, non-uniform
basis, zero-benchmark window, multi-run / multi-portfolio, unordered/overlapping sub-periods, a
foreign/unknown return run + benchmark + portfolio); the post-create FAILED magnitude gate (the
gate is UNREACHABLE via a real PM-1 run — PM-1's own gate bounds r_p first — so it is exercised by
forcing an out-of-range active, the PM-1 precedent); the AD-014 / TR-09 reproducibility invariant (a
benchmark vendor correction AFTER the snapshot cannot move a historical result); the append-only +
run_type!=metric_type + migration-head + fence-sync + zero-``PERF.*``-audit guards; and the
entitlement parity assertion (P3-8 REUSES ``perf.run``/``perf.view`` — NO new permission code). The
PG-specific RLS / trigger / downgrade legs live in ``test_benchmark_relative_pg.py``.

Fixture realism (TD-1): index-relative returns are small fractions; the deliberately out-of-band
active value lives ONLY in the labeled magnitude-boundary test (a forced kernel value).
"""

from __future__ import annotations

import pathlib
import statistics
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from irp_shared.audit.models import AppendOnlyViolation, AuditEvent
from irp_shared.calc.models import CalculationRun, RunStatus
from irp_shared.db.session import make_engine, make_session_factory
from irp_shared.exposure import ExposureActor, run_exposure
from irp_shared.marketdata import (
    RETURN_BASIS_TOTAL,
    RETURN_TYPE_SIMPLE,
    BenchmarkActor,
    capture_benchmark,
    capture_benchmark_return,
    correct_benchmark_return,
    resolve_benchmark,
)
from irp_shared.models import Base
from irp_shared.perf import (
    METRIC_TYPE_ACTIVE_RETURN,
    METRIC_TYPE_INFORMATION_RATIO,
    METRIC_TYPE_TRACKING_DIFFERENCE,
    METRIC_TYPE_TRACKING_ERROR,
    RUN_TYPE_BENCHMARK_RELATIVE,
    BenchmarkRelativeActor,
    BenchmarkRelativeInputError,
    BenchmarkRelativeResult,
    PortfolioReturnActor,
    active_series,
    compound_returns,
    information_ratio,
    list_benchmark_relatives,
    mean_return,
    register_benchmark_relative_model,
    register_portfolio_return_model,
    run_benchmark_relative,
    run_portfolio_return,
    sample_stdev,
)
from irp_shared.perf.benchmark_relative_kernel import BenchmarkRelativeKernelError
from irp_shared.portfolio import PortfolioActor, create_portfolio
from irp_shared.position import create_position
from irp_shared.position.service import PositionActor
from irp_shared.reference.instrument import create_instrument
from irp_shared.reference.models import Currency
from irp_shared.reference.service import ReferenceActor
from irp_shared.snapshot import PURPOSE_BENCHMARK_RELATIVE_INPUT, resolve_snapshot
from irp_shared.valuation import create_valuation
from irp_shared.valuation.service import ValuationActor

TENANT = str(uuid.uuid4())
T0 = datetime(2026, 1, 1, tzinfo=UTC)
KNOWN_AT = datetime(2030, 1, 1, tzinfo=UTC)
D0, D1, D2 = date(2026, 1, 1), date(2026, 1, 31), date(2026, 3, 2)  # two sub-periods
ACTOR = BenchmarkRelativeActor(actor_id="analyst")


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


def test_kernel_goldens_and_independent_cross_check() -> None:
    """Realized statistics over an aligned pair, cross-checked vs ``statistics`` + float."""
    portfolio = [Decimal("0.03"), Decimal("-0.02"), Decimal("0.01")]
    benchmark = [Decimal("0.025"), Decimal("-0.015"), Decimal("0.005")]
    active = active_series(portfolio, benchmark)
    assert active == [Decimal("0.005"), Decimal("-0.005"), Decimal("0.005")]
    assert str(mean_return(active)) == "0.001666666667"
    assert str(sample_stdev(active)) == "0.005773502692"
    assert str(information_ratio(mean_return(active), sample_stdev(active))) == "0.288675134647"
    assert str(compound_returns(portfolio)) == "0.019494000000"
    assert str(compound_returns(benchmark)) == "0.014673125000"
    assert str(compound_returns(portfolio) - compound_returns(benchmark)) == "0.004820875000"
    # Independent cross-check: NumPy-free stdlib + float arithmetic, 9dp tolerance.
    fa = [float(p) - float(b) for p, b in zip(portfolio, benchmark, strict=True)]
    assert abs(float(sample_stdev(active)) - statistics.stdev(fa)) < 1e-9
    assert abs(float(mean_return(active)) - statistics.fmean(fa)) < 1e-9


def test_kernel_conditional_and_pathologies_refuse() -> None:
    with pytest.raises(BenchmarkRelativeKernelError):
        compound_returns([])  # empty compound set
    with pytest.raises(BenchmarkRelativeKernelError):
        active_series([Decimal("0.01")], [Decimal("0.01"), Decimal("0.02")])  # length mismatch
    with pytest.raises(BenchmarkRelativeKernelError):
        sample_stdev([Decimal("0.01")])  # n < 2
    with pytest.raises(BenchmarkRelativeKernelError):
        information_ratio(Decimal("0.01"), Decimal("0"))  # zero TE


# --------------------------------------------------------------------------- full-stack fixtures


def _seed_currency(db: Session, code: str) -> None:
    from irp_shared.entitlement.bootstrap import SYSTEM_TENANT_ID

    if (
        db.execute(
            select(Currency).where(Currency.tenant_id == SYSTEM_TENANT_ID, Currency.code == code)
        ).scalar_one_or_none()
        is None
    ):
        db.add(Currency(tenant_id=SYSTEM_TENANT_ID, code=code, name=code, valid_from=T0))
    db.flush()


def _book(db: Session, tenant: str = TENANT) -> tuple[str, str]:
    _seed_currency(db, "USD")
    _seed_currency(db, "EUR")
    pf = create_portfolio(
        db,
        tenant_id=tenant,
        code=f"ACCT-{uuid.uuid4().hex[:6]}",
        name="acct",
        node_type="ACCOUNT",
        actor=PortfolioActor(actor_id="s"),
    ).id
    inst = create_instrument(
        db,
        tenant_id=tenant,
        code=f"I-{uuid.uuid4().hex[:6]}",
        name="i",
        asset_class="EQUITY",
        actor=ReferenceActor(actor_id="s"),
    ).id
    create_position(
        db,
        portfolio_id=pf,
        instrument_id=inst,
        acting_tenant=tenant,
        actor=PositionActor(actor_id="s"),
        quantity=Decimal("1"),
        valid_from=T0,
    )
    return pf, inst


def _boundary_run(
    db: Session, pf: str, inst: str, vdate: date, mark: str, tenant: str = TENANT
) -> str:
    create_valuation(
        db,
        portfolio_id=pf,
        instrument_id=inst,
        valuation_date=vdate,
        acting_tenant=tenant,
        actor=ValuationActor(actor_id="s"),
        mark_value=Decimal(mark),
        currency_code="USD",
        valid_from=T0,
    )
    result = run_exposure(
        db,
        acting_tenant=tenant,
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


def _return_run(
    db: Session, marks: list[tuple[date, str]], tenant: str = TENANT
) -> tuple[str, str]:
    """A COMPLETED PORTFOLIO_RETURN run over ``marks`` (no external flows). Returns (run_id, pf)."""
    pf, inst = _book(db, tenant)
    runs = [_boundary_run(db, pf, inst, d, m, tenant) for d, m in marks]
    mv = register_portfolio_return_model(
        db, tenant_id=tenant, actor_id="a", code_version="perf-v1"
    ).id
    result = run_portfolio_return(
        db,
        acting_tenant=tenant,
        actor=PortfolioReturnActor(actor_id="analyst"),
        code_version="perf-v1",
        environment_id="ci",
        model_version_id=mv,
        exposure_run_ids=runs,
    )
    assert result.status == RunStatus.COMPLETED.value
    return result.run.run_id, pf


def _benchmark(db: Session, tenant: str = TENANT, *, currency: str = "USD"):  # noqa: ANN202
    _seed_currency(db, currency)
    bm = capture_benchmark(
        db,
        benchmark_code=f"SPX-{uuid.uuid4().hex[:6]}",
        benchmark_source="SP_DJI",
        benchmark_currency=currency,
        acting_tenant=tenant,
        actor=BenchmarkActor(actor_id="s"),
        index_family="S&P",
        valid_from=T0,
    )
    db.flush()
    return resolve_benchmark(db, bm.id, acting_tenant=tenant)


def _bench_return(db: Session, bm, rdate: date, value: str, tenant: str = TENANT) -> None:  # noqa: ANN001
    capture_benchmark_return(
        db,
        bm,
        return_date=rdate,
        return_basis=RETURN_BASIS_TOTAL,
        return_value=Decimal(value),
        acting_tenant=tenant,
        actor=BenchmarkActor(actor_id="s"),
        valid_from=T0,
    )


def _model(db: Session, tenant: str = TENANT) -> str:
    return register_benchmark_relative_model(
        db, tenant_id=tenant, actor_id="a", code_version="br-v1"
    ).id


def _run(db: Session, run_id: str, benchmark_id: str, mv: str, tenant: str = TENANT):  # noqa: ANN202
    return run_benchmark_relative(
        db,
        acting_tenant=tenant,
        actor=ACTOR,
        code_version="br-v1",
        environment_id="ci",
        model_version_id=mv,
        portfolio_return_run_id=run_id,
        benchmark_id=benchmark_id,
        return_basis=RETURN_BASIS_TOTAL,
    )


# --------------------------------------------------------------------------- golden end-to-end


def test_build_path_golden(session: Session) -> None:
    # Portfolio: 1,000,000 -> 1,030,000 (+3%) -> 1,019,700 (-1%); TWR_LINKED = 0.0197.
    run_id, pf = _return_run(session, [(D0, "1000000"), (D1, "1030000"), (D2, "1019700")])
    bm = _benchmark(session)
    _bench_return(session, bm, D1, "0.025")  # window (D0, D1]
    _bench_return(session, bm, D2, "0.005")  # window (D1, D2]
    mv = _model(session)

    result = _run(session, run_id, bm.id, mv)
    assert result.status == RunStatus.COMPLETED.value
    rows = {(r.metric_type, r.period_start): r for r in result.rows}
    active = sorted(
        (r for r in result.rows if r.metric_type == METRIC_TYPE_ACTIVE_RETURN),
        key=lambda r: r.period_start,
    )
    assert [str(a.metric_value) for a in active] == ["0.005000000000", "-0.015000000000"]
    assert active[0].period_start == D0 and active[0].period_end == D1
    assert active[0].portfolio_return_value == Decimal("0.030000000000")
    assert active[0].benchmark_return_value == Decimal("0.025000000000")
    assert active[0].n_benchmark_obs == 1 and active[0].n_periods == 1
    td = rows[(METRIC_TYPE_TRACKING_DIFFERENCE, D0)]
    assert str(td.metric_value) == "-0.010425000000"
    assert td.period_start == D0 and td.period_end == D2 and td.n_periods == 2
    assert str(td.portfolio_return_value) == "0.019700000000"
    assert str(td.benchmark_return_value) == "0.030125000000"
    te = rows[(METRIC_TYPE_TRACKING_ERROR, D0)]
    assert str(te.metric_value) == "0.014142135624"
    ir = rows[(METRIC_TYPE_INFORMATION_RATIO, D0)]
    assert str(ir.metric_value) == "-0.353553390587"
    assert td.portfolio_id == pf and td.base_currency == "USD"
    assert td.return_basis == RETURN_BASIS_TOTAL
    assert td.portfolio_return_run_id == run_id and td.benchmark_id == bm.id


def test_multi_obs_window_compounds(session: Session) -> None:
    """A window with >1 benchmark daily return compounds geometrically (not summed)."""
    run_id, _ = _return_run(session, [(D0, "1000000"), (D1, "1030000"), (D2, "1019700")])
    bm = _benchmark(session)
    # Window (D0, D1]: two daily returns compounding to (1.01)(1.014851...) ... use round pair.
    _bench_return(session, bm, date(2026, 1, 15), "0.01")
    _bench_return(session, bm, D1, "0.02")
    _bench_return(session, bm, D2, "0.005")
    mv = _model(session)
    result = _run(session, run_id, bm.id, mv)
    active = sorted(
        (r for r in result.rows if r.metric_type == METRIC_TYPE_ACTIVE_RETURN),
        key=lambda r: r.period_start,
    )
    r_b1 = compound_returns([Decimal("0.01"), Decimal("0.02")])  # (1.01)(1.02)-1
    assert active[0].benchmark_return_value == r_b1
    assert active[0].n_benchmark_obs == 2
    assert active[0].metric_value == (Decimal("0.030000000000") - r_b1)


# --------------------------------------------------------------- conditional emission


def test_single_subperiod_omits_te_and_ir(session: Session) -> None:
    run_id, _ = _return_run(session, [(D0, "1000000"), (D1, "1030000")])  # ONE sub-period
    bm = _benchmark(session)
    _bench_return(session, bm, D1, "0.025")
    mv = _model(session)
    result = _run(session, run_id, bm.id, mv)
    kinds = {r.metric_type for r in result.rows}
    assert METRIC_TYPE_ACTIVE_RETURN in kinds and METRIC_TYPE_TRACKING_DIFFERENCE in kinds
    assert METRIC_TYPE_TRACKING_ERROR not in kinds  # n < 2
    assert METRIC_TYPE_INFORMATION_RATIO not in kinds


def test_zero_tracking_error_emits_te_omits_ir(session: Session) -> None:
    """A constant active spread => TE = 0 (a valid statistic, emitted); IR undefined (omitted)."""
    run_id, _ = _return_run(session, [(D0, "1000000"), (D1, "1030000"), (D2, "1019700")])
    bm = _benchmark(session)
    _bench_return(session, bm, D1, "0.02")  # active = 0.03 - 0.02 = 0.01
    _bench_return(session, bm, D2, "-0.02")  # active = -0.01 - (-0.02) = 0.01
    mv = _model(session)
    result = _run(session, run_id, bm.id, mv)
    te = next(r for r in result.rows if r.metric_type == METRIC_TYPE_TRACKING_ERROR)
    assert te.metric_value == Decimal("0.000000000000")
    assert all(r.metric_type != METRIC_TYPE_INFORMATION_RATIO for r in result.rows)


# --------------------------------------------------------------- consume + reproducibility (TR-09)


def test_consume_existing_reproduces_and_is_correction_invariant(session: Session) -> None:
    run_id, _ = _return_run(session, [(D0, "1000000"), (D1, "1030000"), (D2, "1019700")])
    bm = _benchmark(session)
    _bench_return(session, bm, D1, "0.025")
    _bench_return(session, bm, D2, "0.005")
    mv = _model(session)
    first = _run(session, run_id, bm.id, mv)
    snap_id = first.run.input_snapshot_id
    snap = resolve_snapshot(session, snap_id, acting_tenant=TENANT)
    assert snap.purpose == PURPOSE_BENCHMARK_RELATIVE_INPUT

    # TR-09: a vendor CORRECTION of a benchmark return AFTER the snapshot must NOT move the result.
    correct_benchmark_return(
        session,
        bm,
        return_date=D1,
        return_basis=RETURN_BASIS_TOTAL,
        return_value=Decimal("0.099"),  # a large restatement
        restatement_reason="vendor correction after the pin",
        acting_tenant=TENANT,
        actor=BenchmarkActor(actor_id="s"),
    )
    rerun = run_benchmark_relative(
        session,
        acting_tenant=TENANT,
        actor=ACTOR,
        code_version="br-v1",
        environment_id="ci",
        model_version_id=mv,
        snapshot_id=snap_id,
    )
    a = next(r for r in first.rows if r.metric_type == METRIC_TYPE_TRACKING_DIFFERENCE)
    b = next(r for r in rerun.rows if r.metric_type == METRIC_TYPE_TRACKING_DIFFERENCE)
    assert a.metric_value == b.metric_value == Decimal("-0.010425000000")


# --------------------------------------------------------------- pre-create refusals (adjudication)


def _p_row(metric_type: str, start: date, end: date, val: str, **over: object) -> dict:
    base = {
        "metric_type": metric_type,
        "calculation_run_id": over.get("run_id", "run-a"),
        "portfolio_id": over.get("portfolio_id", "pf-a"),
        "base_currency": over.get("base_currency", "USD"),
        "period_start": start.isoformat(),
        "period_end": end.isoformat(),
        "return_value": val,
    }
    return base


def _b_series(rows: list[tuple[date, str]], *, currency: str = "USD", basis: str = "TOTAL", **o):
    return {
        "benchmark_id": o.get("benchmark_id", "bm-a"),
        "benchmark_currency": currency,
        "return_type": RETURN_TYPE_SIMPLE,
        "return_basis": basis,
        "rows": [
            {
                "return_date": d.isoformat(),
                "return_value": v,
                "return_type": RETURN_TYPE_SIMPLE,
                "return_basis": basis,
            }
            for d, v in rows
        ],
    }


def _valid_pins() -> tuple[list[dict], list[dict]]:
    portfolio = [
        _p_row("DIETZ_PERIOD", D0, D1, "0.030000000000"),
        _p_row("DIETZ_PERIOD", D1, D2, "-0.010000000000"),
        _p_row("TWR_LINKED", D0, D2, "0.019700000000"),
    ]
    benchmark = [_b_series([(D1, "0.025"), (D2, "0.005")])]
    return portfolio, benchmark


def test_adjudicate_valid_baseline() -> None:
    from irp_shared.perf.benchmark_relative_service import _adjudicate_pins

    parsed = _adjudicate_pins(*_valid_pins())
    assert len(parsed.sub_periods) == 2
    assert parsed.twr_linked == Decimal("0.019700000000")
    assert parsed.base_currency == "USD"


@pytest.mark.parametrize(
    "mutate",
    [
        "linkage",
        "currency",
        "basis",
        "zero_window",
        "multi_run",
        "multi_portfolio",
        "overlap",
        "gap",
        "orphan_bench_row",
        "no_dietz",
        "two_linked",
        "two_series",
    ],
)
def test_adjudicate_refusals(mutate: str) -> None:
    from irp_shared.perf.benchmark_relative_service import _adjudicate_pins

    portfolio, benchmark = _valid_pins()
    if mutate == "linkage":
        portfolio[2]["return_value"] = "0.050000000000"  # != geometric link
    elif mutate == "currency":
        benchmark[0]["benchmark_currency"] = "EUR"  # != base USD
    elif mutate == "basis":
        benchmark[0]["rows"][0]["return_basis"] = "PRICE"  # non-uniform
    elif mutate == "zero_window":
        benchmark[0]["rows"] = [{**benchmark[0]["rows"][0]}]  # only window-1 row -> window-2 empty
    elif mutate == "multi_run":
        portfolio[1]["calculation_run_id"] = "run-b"
    elif mutate == "multi_portfolio":
        portfolio[1]["portfolio_id"] = "pf-b"
    elif mutate == "overlap":
        portfolio[1]["period_start"] = D0.isoformat()  # start < prev_end -> overlap
    elif mutate == "gap":
        # A non-contiguous sub-period (start > prev_end): Feb is unmeasured, so a Feb benchmark
        # return would be silently dropped. Contiguity is enforced, so this is refused.
        portfolio[1]["period_start"] = date(2026, 2, 1).isoformat()
    elif mutate == "orphan_bench_row":
        # A benchmark row dated before the first boundary maps to no window -> all-consumed refusal.
        benchmark[0]["rows"].append(
            {
                "return_date": date(2025, 12, 15).isoformat(),
                "return_value": "0.001",
                "return_type": RETURN_TYPE_SIMPLE,
                "return_basis": "TOTAL",
            }
        )
    elif mutate == "no_dietz":
        portfolio = [portfolio[2]]  # TWR_LINKED only, no DIETZ
    elif mutate == "two_linked":
        portfolio.append(_p_row("TWR_LINKED", D0, D2, "0.019700000000"))
    elif mutate == "two_series":
        benchmark.append(_b_series([(D1, "0.01")]))
    with pytest.raises(BenchmarkRelativeInputError):
        _adjudicate_pins(portfolio, benchmark)


# --------------------------------------------------------------- pre-create refusals (security)


def test_unknown_return_run_refused(session: Session) -> None:
    bm = _benchmark(session)
    _bench_return(session, bm, D1, "0.025")
    mv = _model(session)
    before = session.execute(select(func.count()).select_from(CalculationRun)).scalar()
    with pytest.raises(BenchmarkRelativeInputError):
        _run(session, str(uuid.uuid4()), bm.id, mv)
    after = session.execute(
        select(func.count())
        .select_from(CalculationRun)
        .where(CalculationRun.run_type == RUN_TYPE_BENCHMARK_RELATIVE)
    ).scalar()
    assert after == 0
    assert before == session.execute(select(func.count()).select_from(CalculationRun)).scalar()


def test_unknown_benchmark_refused(session: Session) -> None:
    """On the BUILD path an unknown ``benchmark_id`` fails closed as a UNIFORM pre-create refusal
    (``BenchmarkRelativeInputError`` → 422), matching ``_resolve_return_run`` on the same path and
    the PM-1 exposure-run precedent — the benchmark_id is a request-body prerequisite, not the
    addressed resource (review fold — was a bare 404 ``BenchmarkNotVisible``)."""
    run_id, _ = _return_run(session, [(D0, "1000000"), (D1, "1030000")])
    mv = _model(session)
    with pytest.raises(BenchmarkRelativeInputError):
        _run(session, run_id, str(uuid.uuid4()), mv)


def test_currency_mismatch_refused_full_stack(session: Session) -> None:
    """A EUR benchmark vs a USD-base return run — no FX translation in v1; refused pre-create."""
    _seed_currency(session, "EUR")
    run_id, _ = _return_run(session, [(D0, "1000000"), (D1, "1030000")])
    bm = _benchmark(session, currency="EUR")
    _bench_return(session, bm, D1, "0.025")
    mv = _model(session)
    with pytest.raises(BenchmarkRelativeInputError):
        _run(session, run_id, bm.id, mv)


def test_zero_benchmark_window_refused_full_stack(session: Session) -> None:
    """A sub-period with no captured benchmark return — refused (no imputation)."""
    run_id, _ = _return_run(session, [(D0, "1000000"), (D1, "1030000"), (D2, "1019700")])
    bm = _benchmark(session)
    _bench_return(session, bm, D1, "0.025")  # window (D0, D1] only; window (D1, D2] empty
    mv = _model(session)
    with pytest.raises(BenchmarkRelativeInputError):
        _run(session, run_id, bm.id, mv)


def test_foreign_portfolio_id_refused_pre_create(session: Session) -> None:
    """The shared perf guard (one implementation for PM-1 + P3-8) with THIS binder's error class."""
    from irp_shared.portfolio.guards import assert_portfolio_in_tenant

    pf, _ = _book(session)
    assert_portfolio_in_tenant(session, pf, acting_tenant=TENANT, error=BenchmarkRelativeInputError)
    with pytest.raises(BenchmarkRelativeInputError):
        assert_portfolio_in_tenant(
            session, str(uuid.uuid4()), acting_tenant=TENANT, error=BenchmarkRelativeInputError
        )


def test_foreign_tenant_return_run_refused(session: Session) -> None:
    """A return run in ANOTHER tenant cannot be consumed (the P3-5 cross-tenant-FK guard)."""
    other = str(uuid.uuid4())
    run_id, _ = _return_run(session, [(D0, "1000000"), (D1, "1030000")], tenant=other)
    bm = _benchmark(session, tenant=TENANT)
    _bench_return(session, bm, D1, "0.025", tenant=TENANT)
    mv = _model(session, tenant=TENANT)
    with pytest.raises(BenchmarkRelativeInputError):
        _run(session, run_id, bm.id, mv, tenant=TENANT)


# ------------------------------------------------------------- post-create FAILED (magnitude gate)


def test_extreme_active_is_failed_run(session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    """The post-create magnitude gate: an active value past the Numeric(20,12) envelope
    (magnitude ``>= 1E7``) yields a COMMITTED FAILED run + ZERO rows + a magnitude-naming reason,
    never a PG column-overflow 500 (the PM-1 _MAX_RESULT_ABS precedent). NOTE: the gate is
    UNREACHABLE through a real PM-1 ``PORTFOLIO_RETURN`` run — PM-1's OWN identical gate bounds
    ``r_p`` first — so the only way to drive an extreme active is a malformed hand-mint; we simulate
    that by forcing the kernel to yield an out-of-range active (the PM-1 monkeypatch precedent)."""
    import irp_shared.perf.benchmark_relative_service as svc

    run_id, _ = _return_run(session, [(D0, "1000000"), (D1, "1030000")])
    bm = _benchmark(session)
    _bench_return(session, bm, D1, "0.025")
    mv = _model(session)
    monkeypatch.setattr(svc, "active_series", lambda _p, _b: [Decimal("1E9")])
    result = _run(session, run_id, bm.id, mv)
    assert result.status == RunStatus.FAILED.value
    assert result.rows == []
    assert result.failure_reason and "magnitude" in result.failure_reason
    assert list_benchmark_relatives(session, run_id=result.run.run_id, acting_tenant=TENANT) == []


def test_extreme_evidence_echo_is_failed_run(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Review fold: the EVIDENCE echoes (portfolio_return_value / benchmark_return_value) are gated
    too, not only the metric. Here the active value is forced SMALL (passes the metric gate) but the
    benchmark compounds to >= 1E7 — so the benchmark_return_value echo trips the gate. WITHOUT
    the evidence gate this row would flush and OVERFLOW the Numeric(20,12) column as a raw 500 with
    the run stuck in RUNNING (the scaffold flush is outside the caught DataQualityError). Labeled
    magnitude-boundary test (TD-1)."""
    import irp_shared.perf.benchmark_relative_service as svc

    run_id, _ = _return_run(session, [(D0, "1000000"), (D1, "1030000")])
    bm = _benchmark(session)
    _bench_return(session, bm, D1, "10000000")  # r_b = 1E7 (fits the column, trips the 1E7 gate)
    mv = _model(session)
    monkeypatch.setattr(svc, "active_series", lambda _p, _b: [Decimal("0.001")])  # metric in-range
    result = _run(session, run_id, bm.id, mv)
    assert result.status == RunStatus.FAILED.value  # the ECHO gate, not the metric gate
    assert result.rows == []
    assert result.failure_reason and "magnitude" in result.failure_reason


# ------------------------------------------------------- the RD-3 NaN fix (MG-1 OD-H ride-along)


def _mint_br_snapshot_from(db: Session, source_snapshot_id: str, *, bench_value: str | None = None):  # noqa: ANN202
    """Re-mint a ``BENCHMARK_RELATIVE_INPUT`` snapshot copying a REAL governed snapshot's pinned
    content, optionally overwriting the FIRST benchmark row's ``return_value`` — the adjudication-
    gate probe vehicle (the ``test_var_hs`` ``_mint_hs_snapshot`` precedent). The capture layer
    refuses non-finite values at write (``_validate_return_value``), so a NaN/Infinity bench row
    can only ever arrive via a hand-minted pin; every provenance id stays REAL so nothing but the
    mutated value refuses."""
    import json
    from types import SimpleNamespace

    from irp_shared.snapshot import (
        COMPONENT_KIND_BENCHMARK_RETURN,
        SnapshotActor,
        list_components,
    )
    from irp_shared.snapshot.service import _append_spec, _persist_snapshot

    specs: list = []
    for comp in list_components(db, snapshot_id=source_snapshot_id, acting_tenant=TENANT):
        content = json.loads(comp.captured_content)
        if comp.component_kind == COMPONENT_KIND_BENCHMARK_RETURN:
            if bench_value is not None:
                content["rows"][0]["return_value"] = bench_value
            anchor_id, target = content["benchmark_id"], "benchmark"
        else:
            anchor_id, target = content["id"], "portfolio_return_result"
        anchor = SimpleNamespace(id=anchor_id, valid_from=None, system_from=T0, record_version=None)
        _append_spec(specs, comp.component_kind, target, anchor, content)
    header = _persist_snapshot(
        db,
        acting_tenant=TENANT,
        actor=SnapshotActor(actor_id="s"),
        specs=specs,
        label="",
        purpose=PURPOSE_BENCHMARK_RELATIVE_INPUT,
        as_of_valid_at=KNOWN_AT,
        as_of_known_at=KNOWN_AT,
        as_of_valuation_date=D1,
        binding_predicate_version="test:hand-minted",
    )
    db.flush()
    return header


def _real_br_snapshot(db: Session) -> tuple[str, str]:
    """A REAL governed BENCHMARK_RELATIVE_INPUT snapshot (one sub-period, r_p=3% vs r_b=2.5%).
    Returns (snapshot_id, model_version_id)."""
    from irp_shared.snapshot import SnapshotActor, build_benchmark_relative_snapshot

    run_id, _ = _return_run(db, [(D0, "1000000"), (D1, "1030000")])
    bm = _benchmark(db)
    _bench_return(db, bm, D1, "0.025")
    snap = build_benchmark_relative_snapshot(
        db,
        acting_tenant=TENANT,
        actor=SnapshotActor(actor_id="s"),
        portfolio_return_run_id=run_id,
        benchmark_id=bm.id,
        return_basis=RETURN_BASIS_TOTAL,
    )
    return str(snap.id), _model(db)


def _consume(db: Session, snapshot_id: str, mv: str):  # noqa: ANN202
    return run_benchmark_relative(
        db,
        acting_tenant=TENANT,
        actor=ACTOR,
        code_version="br-v1",
        environment_id="ci",
        model_version_id=mv,
        snapshot_id=snapshot_id,
    )


def _assert_refused_no_run(db: Session, snapshot_id: str, mv: str, match: str) -> None:
    from run_assertions import assert_no_running_orphan

    with pytest.raises(BenchmarkRelativeInputError, match=match):
        _consume(db, snapshot_id, mv)
    assert_no_running_orphan(db, run_type=RUN_TYPE_BENCHMARK_RELATIVE)
    created = db.execute(
        select(func.count())
        .select_from(CalculationRun)
        .where(CalculationRun.run_type == RUN_TYPE_BENCHMARK_RELATIVE)
    ).scalar()
    assert created == 0  # pre-create refusal: ZERO run rows, not a FAILED run


def test_bench_side_nan_refused_pre_create_no_orphan(session: Session) -> None:
    """MG-1 OD-H ride-along (the RD-3 NaN fix): a hand-minted bench-row ``"NaN"`` is a PRE-CREATE
    ``BenchmarkRelativeInputError`` (422) with NO run row and NO RUNNING orphan. Before the bench
    side adopted ``parse_strict_decimal``, the raw ``Decimal()`` parsed NaN QUIETLY at adjudication
    and it detonated at the magnitude gate (a Decimal-NaN comparison raises InvalidOperation)
    outside every try — a raw 500 + a RUNNING orphan (the BT-1 orphan class). NaN was the ONLY
    orphaning input: unparseable garbage was ALREADY a pre-create 422 (InvalidOperation is an
    ArithmeticError, caught by the adjudication wrapper) — verifier-executed, MG-1 census."""
    snap_id, mv = _real_br_snapshot(session)
    minted = _mint_br_snapshot_from(session, snap_id, bench_value="NaN")
    _assert_refused_no_run(session, str(minted.id), mv, "not a finite number")


@pytest.mark.parametrize("value", ["Infinity", "-Infinity"])
def test_bench_side_infinity_refused_pre_create(session: Session, value: str) -> None:
    """The stated ±Infinity class change (MG-1 OD-H, ratified): a bench-row ±Inf previously parsed
    quietly and produced a CORRECT post-create FAILED run at the magnitude gate; with the guarded
    parse it MOVES to a pre-create 422, matching the portfolio side's behavior for the same
    input. A deliberate, recorded change to a working path — not a bug fix."""
    snap_id, mv = _real_br_snapshot(session)
    minted = _mint_br_snapshot_from(session, snap_id, bench_value=value)
    _assert_refused_no_run(session, str(minted.id), mv, "not a finite number")


def test_hand_minted_control_still_computes(session: Session) -> None:
    """Control for the two refusal probes above: the SAME mint vehicle with UNMUTATED pinned
    content passes adjudication and COMPLETES — what refuses is the non-finite value, never the
    hand-mint itself."""
    snap_id, mv = _real_br_snapshot(session)
    minted = _mint_br_snapshot_from(session, snap_id)  # no mutation
    result = _consume(session, str(minted.id), mv)
    assert result.status == RunStatus.COMPLETED.value
    active = next(r for r in result.rows if r.metric_type == METRIC_TYPE_ACTIVE_RETURN)
    assert active.metric_value == Decimal("0.005000000000")  # 0.03 - 0.025


# --------------------------------------------------------------------------- governance guards


def test_append_only_result_row(session: Session) -> None:
    run_id, _ = _return_run(session, [(D0, "1000000"), (D1, "1030000")])
    bm = _benchmark(session)
    _bench_return(session, bm, D1, "0.025")
    mv = _model(session)
    result = _run(session, run_id, bm.id, mv)
    row = result.rows[0]
    row.metric_value = Decimal("0.999999999999")
    with pytest.raises(AppendOnlyViolation):
        session.flush()
    session.rollback()


def test_run_type_is_not_a_metric() -> None:
    assert RUN_TYPE_BENCHMARK_RELATIVE not in {
        METRIC_TYPE_ACTIVE_RETURN,
        METRIC_TYPE_TRACKING_DIFFERENCE,
        METRIC_TYPE_TRACKING_ERROR,
        METRIC_TYPE_INFORMATION_RATIO,
    }


def test_no_perf_audit_events_emitted(session: Session) -> None:
    """P3-8 mints NO ``PERF.*`` code — the run reuses ``CALC.RUN_*`` (OD-P3-8-B)."""
    run_id, _ = _return_run(session, [(D0, "1000000"), (D1, "1030000")])
    bm = _benchmark(session)
    _bench_return(session, bm, D1, "0.025")
    mv = _model(session)
    _run(session, run_id, bm.id, mv)
    perf_events = session.execute(
        select(func.count()).select_from(AuditEvent).where(AuditEvent.event_type.like("PERF.%"))
    ).scalar()
    assert perf_events == 0


def test_migration_head_is_benchmark_relative() -> None:
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    root = pathlib.Path(__file__).resolve().parents[3]
    cfg = Config(str(root / "alembic.ini"))
    cfg.set_main_option("script_location", str(root / "migrations"))
    script = ScriptDirectory.from_config(cfg)
    assert script.get_current_head() == "0041_es_historical"  # ES-HS-1
    assert script.get_revision("0032_benchmark_relative").down_revision == "0031_portfolio_return"


def test_compound_returns_matches_link_periods() -> None:
    """The exact-linkage cross-check (``_adjudicate_pins``) recomputes ``compound_returns`` of the
    pinned DIETZ returns and demands EXACT equality with PM-1's stored ``TWR_LINKED`` (which PM-1
    produced via ``link_periods``). The two compounding functions live in separate perf kernels and
    MUST stay bit-identical or every benchmark-relative run against a real PM-1 run spuriously
    refuses. This pins that coupling across a range of vectors (review fold: make the invariant
    enforced, not just golden-implied)."""
    from irp_shared.perf.return_kernel import link_periods

    vectors = [
        [Decimal("0.03"), Decimal("-0.02"), Decimal("0.01")],
        [Decimal("0.029702970297")],
        [Decimal("0"), Decimal("0.000000000001"), Decimal("-0.000000000001")],
        [Decimal("0.1"), Decimal("0.1"), Decimal("0.1"), Decimal("-0.25")],
        [Decimal("-0.5"), Decimal("0.999999999999")],
    ]
    for v in vectors:
        assert compound_returns(v) == link_periods(v), v


def test_perf_permissions_reused_no_new_codes() -> None:
    """P3-8 REUSES ``perf.run``/``perf.view`` — it introduces NO new permission code (OD-P3-8-B).
    The SoD doc cites this test: the perf verbs in the catalog are EXACTLY the PM-1 pair, and no
    catalog code mentions benchmark-relative."""
    from irp_shared.entitlement.bootstrap import PERMISSIONS

    codes = {c for c, _desc in PERMISSIONS}
    perf_codes = {c for c in codes if c.startswith("perf.")}
    assert perf_codes == {"perf.run", "perf.view"}
    assert not any("benchmark_relative" in c or "benchmark-relative" in c for c in codes)


def test_methodology_doc_exists_and_has_required_sections() -> None:
    from irp_shared.perf.bootstrap import BENCHMARK_RELATIVE_METHODOLOGY_REF

    root = pathlib.Path(__file__).resolve().parents[3]
    doc = root / BENCHMARK_RELATIVE_METHODOLOGY_REF
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


def test_result_model_grain(session: Session) -> None:
    """The grain (calculation_run_id, metric_type, period_start) lets the two ACTIVE_RETURN rows +
    the three summary rows (sharing period_start D0) coexist without a unique clash."""
    run_id, _ = _return_run(session, [(D0, "1000000"), (D1, "1030000"), (D2, "1019700")])
    bm = _benchmark(session)
    _bench_return(session, bm, D1, "0.025")
    _bench_return(session, bm, D2, "0.005")
    mv = _model(session)
    result = _run(session, run_id, bm.id, mv)
    rows = list_benchmark_relatives(session, run_id=result.run.run_id, acting_tenant=TENANT)
    grain = {(r.metric_type, r.period_start) for r in rows}
    assert (METRIC_TYPE_ACTIVE_RETURN, D0) in grain
    assert (METRIC_TYPE_ACTIVE_RETURN, D1) in grain
    assert (METRIC_TYPE_TRACKING_DIFFERENCE, D0) in grain  # shares D0 with ACTIVE_RETURN, distinct
    assert isinstance(rows[0], BenchmarkRelativeResult)
