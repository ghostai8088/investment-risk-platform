"""SR-1 binder + end-to-end governed run (ENT-065 — the 22nd governed number).

Drives a real PM-1 return run and a real captured risk-free ``benchmark_return`` series through the
Sharpe binder, so the pin -> relink -> month-join -> window -> emit chain is exercised end to end.
The refusal tests then attack the pre-create gate — with particular weight on the risk-free join,
which is the load-bearing NEW criterion the ratified record omitted entirely and whose "this is
structural" claim the verifier pass refuted.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from irp_shared.calc.models import CalculationRun
from irp_shared.marketdata import (
    BenchmarkActor,
    capture_benchmark,
    capture_benchmark_return,
    resolve_benchmark,
)
from irp_shared.marketdata.models import RETURN_BASIS_TOTAL
from irp_shared.perf.bootstrap import (
    SHARPE_MODEL_CODE,
    SHARPE_WINDOWS,
    register_rolling_risk_model,
    register_sharpe_model,
)
from irp_shared.perf.events import RUN_TYPE_SHARPE, SharpeRatioActor
from irp_shared.perf.models import (
    ANNUALIZATION_NONE,
    ANNUALIZATION_SQRT_12,
    METRIC_TYPE_DIETZ_PERIOD,
    METRIC_TYPE_SHARPE_RATIO,
    METRIC_TYPE_SHARPE_RATIO_ANN,
    METRIC_TYPE_TWR_LINKED,
    PortfolioReturnResult,
)
from irp_shared.perf.rolling_kernel import last_weekday_of_month
from irp_shared.perf.sharpe_kernel import ZERO_DISPERSION_REASON
from irp_shared.perf.sharpe_service import (
    SharpeInputError,
    SharpeNotVisible,
    SharpeRunNotVisible,
    latest_sharpe_ratio,
    list_sharpe_ratio_rows,
    list_sharpe_ratios,
    resolve_sharpe_ratio,
    resolve_sharpe_run,
    run_sharpe_ratio,
)
from irp_shared.portfolio import PortfolioActor, create_portfolio
from irp_shared.reference.models import Currency
from irp_shared.snapshot import (
    PURPOSE_ROLLING_RISK_INPUT,
    build_rolling_risk_snapshot,
    build_sharpe_snapshot,
)
from irp_shared.snapshot.events import SnapshotActor

D = Decimal
_ACTOR = SharpeRatioActor(actor_id="analyst-1")
_SNAP_ACTOR = SnapshotActor(actor_id="analyst-1")
_BENCH_ACTOR = BenchmarkActor(actor_id="steward")
_CODE_VERSION = "sr1-test"
_T0 = datetime(2023, 1, 1, tzinfo=UTC)

#: The portfolio leg of the GOLDEN fixture. Differencing it against a constant 0.004 risk-free rate
#: reproduces ``test_sharpe_kernel``'s golden excess series exactly, so the end-to-end run is pinned
#: to the SAME hand-computed number as the kernel — the binder cannot silently re-derive it.
_GOLDEN_PORTFOLIO = (
    "0.014",
    "0.024",
    "0.004",
    "0.034",
    "-0.006",
    "0.024",
    "0.014",
    "0.004",
    "0.024",
    "0.014",
    "0.034",
    "-0.016",
)
_GOLDEN_RF = "0.004"
_GOLDEN_SHARPE = D("0.650443635588")
_GOLDEN_SHARPE_ANN = D("2.253202848596")


def _month_ends(count: int, *, start_year: int = 2024, start_month: int = 1) -> list[date]:
    out: list[date] = []
    year, month = start_year, start_month
    for _ in range(count):
        out.append(last_weekday_of_month(year, month))
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return out


def _seed_currency(db: Session, code: str) -> None:
    from irp_shared.entitlement.bootstrap import SYSTEM_TENANT_ID

    if (
        db.execute(
            select(Currency).where(Currency.tenant_id == SYSTEM_TENANT_ID, Currency.code == code)
        ).scalar_one_or_none()
        is None
    ):
        db.add(Currency(tenant_id=SYSTEM_TENANT_ID, code=code, name=code, valid_from=_T0))
    db.flush()


def _seed_return_run(
    session: Session,
    tenant: str,
    *,
    returns: list[str],
    boundaries: list[date] | None = None,
) -> tuple[CalculationRun, str, list[date]]:
    """A COMPLETED PM-1 run shaped exactly as PM-1 writes it, so the pin serializer SR-1 reuses
    produces real content. Hand-seeded on purpose: driving PM-1 here would test PM-1."""
    portfolio = create_portfolio(
        session,
        tenant_id=tenant,
        code=f"pf-{uuid.uuid4().hex[:8]}",
        name="Book",
        node_type="ACCOUNT",
        actor=PortfolioActor(actor_id="steward"),
    )
    run = CalculationRun(
        tenant_id=tenant,
        run_type="PORTFOLIO_RETURN",
        status="COMPLETED",
        initiated_by="seed",
        code_version="pm1",
        environment_id="test",
        completed_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    session.add(run)
    session.flush()

    bounds = boundaries if boundaries is not None else _month_ends(len(returns) + 1)
    assert len(bounds) == len(returns) + 1, "one more boundary than sub-periods"

    def _row(metric: str, start: date, end: date, value: str, n_periods: int) -> None:
        session.add(
            PortfolioReturnResult(
                tenant_id=tenant,
                calculation_run_id=run.run_id,
                input_snapshot_id=str(uuid.uuid4()),
                model_version_id=str(uuid.uuid4()),
                portfolio_id=str(portfolio.id),
                metric_type=metric,
                period_start=start,
                period_end=end,
                begin_mv=D("1000000.000000"),
                end_mv=D("1000000.000000"),
                net_external_flow=D("0.000000"),
                return_value=D(value),
                n_flows=0,
                n_periods=n_periods,
                base_currency="USD",
            )
        )

    for i, value in enumerate(returns):
        _row(METRIC_TYPE_DIETZ_PERIOD, bounds[i], bounds[i + 1], value, 1)
    _row(METRIC_TYPE_TWR_LINKED, bounds[0], bounds[-1], "0.0", len(returns))
    session.flush()
    return run, str(portfolio.id), bounds


def _seed_risk_free(
    session: Session,
    tenant: str,
    *,
    dates: list[date],
    values: list[str],
    code: str | None = None,
):  # noqa: ANN202
    """A captured vendor-published monthly cash series carried as an ordinary benchmark head."""
    _seed_currency(session, "USD")
    head = capture_benchmark(
        session,
        benchmark_code=code or f"USD-CASH-1M-{uuid.uuid4().hex[:6]}",
        benchmark_source="DEMO_VENDOR",
        benchmark_currency="USD",
        acting_tenant=tenant,
        actor=_BENCH_ACTOR,
        index_family="CASH",
        valid_from=_T0,
    )
    session.flush()
    head = resolve_benchmark(session, head.id, acting_tenant=tenant)
    for when, value in zip(dates, values, strict=True):
        capture_benchmark_return(
            session,
            head,
            return_date=when,
            return_basis=RETURN_BASIS_TOTAL,
            return_value=D(value),
            acting_tenant=tenant,
            actor=_BENCH_ACTOR,
            valid_from=_T0,
        )
    session.flush()
    return head


def _run_sharpe(
    session: Session,
    tenant: str,
    *,
    returns: list[str],
    rf: list[str] | str = "0.004",
    rf_dates: list[date] | None = None,
    boundaries: list[date] | None = None,
    windows: tuple[int, ...] = SHARPE_WINDOWS,
):  # noqa: ANN202
    run, _pf, bounds = _seed_return_run(session, tenant, returns=returns, boundaries=boundaries)
    # One rf row per MEASURED month: the months the sub-periods END in (d_0's month contributes no
    # observation and therefore needs no risk-free row).
    measured = rf_dates if rf_dates is not None else bounds[1:]
    values = rf if isinstance(rf, list) else [rf] * len(measured)
    head = _seed_risk_free(session, tenant, dates=measured, values=values)
    version = register_sharpe_model(
        session, tenant_id=tenant, actor_id="steward", code_version=_CODE_VERSION
    )
    snapshot = build_sharpe_snapshot(
        session,
        acting_tenant=tenant,
        actor=_SNAP_ACTOR,
        portfolio_return_run_id=run.run_id,
        risk_free_benchmark_id=head.id,
        rf_return_basis=RETURN_BASIS_TOTAL,
    )
    return run_sharpe_ratio(
        session,
        acting_tenant=tenant,
        actor=_ACTOR,
        code_version=_CODE_VERSION,
        environment_id="test",
        model_version_id=str(version.id),
        window_months=windows,
        snapshot_id=snapshot.id,
    )


# --- 1. the end-to-end governed run --------------------------------------------------------------


def test_the_governed_run_reproduces_the_GOLDEN_number_end_to_end(session: Session) -> None:
    """THE NUMBER, through the whole chain — not merely in the kernel.

    The portfolio leg minus a constant 0.004 risk-free rate IS ``test_sharpe_kernel``'s golden
    excess series, so this pins the binder's month-join, its ordering and its quantization against
    the same hand computation. A binder that dropped the risk-free leg, joined it wrongly, or
    re-quantized an operand would emit a different literal here.
    """
    tenant = str(uuid.uuid4())
    result = _run_sharpe(session, tenant, returns=list(_GOLDEN_PORTFOLIO), windows=(12,))
    assert result.status == "COMPLETED"
    assert result.run.run_type == RUN_TYPE_SHARPE

    by_metric = {r.metric_type: r for r in result.rows}
    assert by_metric[METRIC_TYPE_SHARPE_RATIO].metric_value == _GOLDEN_SHARPE
    assert by_metric[METRIC_TYPE_SHARPE_RATIO_ANN].metric_value == _GOLDEN_SHARPE_ANN


def test_both_metrics_are_emitted_at_EVERY_window_including_twelve(session: Session) -> None:
    """RM-1 suppresses its redundant annualized RETURN at W = 12 (the geometric exponent is exactly
    1 there). ``sqrt(12) x SR != SR`` at any window, so that convention does NOT transfer — and a
    future edit importing it would leave every 12-month annualized Sharpe row missing."""
    tenant = str(uuid.uuid4())
    result = _run_sharpe(session, tenant, returns=["0.01", "0.02"] * 7, windows=(12,))
    assert {r.metric_type for r in result.rows} == {
        METRIC_TYPE_SHARPE_RATIO,
        METRIC_TYPE_SHARPE_RATIO_ANN,
    }
    # 14 months, a 12-month window => 3 complete windows, 2 metrics each.
    assert len(result.rows) == 6
    bases = {(r.metric_type, r.annualization_basis) for r in result.rows}
    assert bases == {
        (METRIC_TYPE_SHARPE_RATIO, ANNUALIZATION_NONE),
        (METRIC_TYPE_SHARPE_RATIO_ANN, ANNUALIZATION_SQRT_12),
    }


def test_every_row_is_run_snapshot_model_and_PROVENANCE_bound(session: Session) -> None:
    """The AD-014 / CTRL-003 invariant at the row level, plus the provenance ENT-065 exists for: a
    Sharpe row that cannot say which risk-free series it was measured against is not evidence."""
    tenant = str(uuid.uuid4())
    result = _run_sharpe(session, tenant, returns=["0.01", "0.02"] * 6, windows=(12,))
    for row in result.rows:
        assert row.calculation_run_id == result.run.run_id
        assert row.input_snapshot_id and row.model_version_id
        assert row.portfolio_return_run_id and row.portfolio_id
        assert row.risk_free_benchmark_id
        assert row.rf_return_basis == RETURN_BASIS_TOTAL
        assert row.sampling_frequency == "MONTHLY"


def test_the_annualized_pair_reconciles_on_the_PERSISTED_rows(session: Session) -> None:
    """Consumes the EMITTED rows, not the kernel — the RM-1 lesson that a reconciliation test
    restating the implementation is vacuous. A consumer multiplying the raw row by sqrt(12) must
    land exactly on the annualized row."""
    from decimal import ROUND_HALF_UP, localcontext

    tenant = str(uuid.uuid4())
    result = _run_sharpe(session, tenant, returns=["0.01", "0.02", "0.005"] * 5, windows=(12,))
    raw = {
        (r.window_months, r.period_end): r.metric_value
        for r in result.rows
        if r.metric_type == METRIC_TYPE_SHARPE_RATIO
    }
    annualized = {
        (r.window_months, r.period_end): r.metric_value
        for r in result.rows
        if r.metric_type == METRIC_TYPE_SHARPE_RATIO_ANN
    }
    assert raw and raw.keys() == annualized.keys()
    for key, stored in raw.items():
        assert stored is not None
        with localcontext() as ctx:
            ctx.prec = 50
            expected = (stored * D(12).sqrt()).quantize(D(1).scaleb(-12), rounding=ROUND_HALF_UP)
        assert annualized[key] == expected


# --- 2. suppression: the two shapes, and why they are distinguishable ----------------------------


def test_an_unfillable_window_emits_SUPPRESSED_rows_with_no_sample(session: Session) -> None:
    tenant = str(uuid.uuid4())
    result = _run_sharpe(session, tenant, returns=["0.01", "0.02"] * 7, windows=(12, 36))
    unfillable = [r for r in result.rows if r.window_months == 36]
    assert len(unfillable) == 2  # BOTH metrics suppressed, never one of the pair
    for row in unfillable:
        assert row.suppressed and row.metric_value is None
        assert "14 monthly observations" in (row.suppression_reason or "")
        assert row.n_observations is None  # there IS no sample


def test_a_constant_excess_series_suppresses_but_KEEPS_its_observation_count(
    session: Session,
) -> None:
    """The two suppression states are DIFFERENT and the read surface can tell them apart: an
    unfillable window has no sample (``n_observations`` NULL); a zero-dispersion window has a
    perfectly good sample and an undefined ratio."""
    tenant = str(uuid.uuid4())
    # A constant portfolio return against a constant rf => a constant excess series.
    result = _run_sharpe(session, tenant, returns=["0.01"] * 12, rf="0.004", windows=(12,))
    assert result.status == "COMPLETED"
    assert len(result.rows) == 2
    for row in result.rows:
        assert row.suppressed and row.metric_value is None
        assert row.suppression_reason == ZERO_DISPERSION_REASON
        assert row.n_observations == 12  # the sample exists; the ratio does not


def test_a_book_that_exactly_earns_cash_emits_a_GENUINE_ZERO(session: Session) -> None:
    """Zero is a legitimate governed Sharpe ratio, which is the entire reason ``metric_value`` is
    nullable instead of carrying a sentinel."""
    tenant = str(uuid.uuid4())
    returns = ["0.014", "-0.006"] * 6
    result = _run_sharpe(session, tenant, returns=returns, rf="0.004", windows=(12,))
    raw = next(r for r in result.rows if r.metric_type == METRIC_TYPE_SHARPE_RATIO)
    assert raw.metric_value == D("0E-12")
    assert raw.suppressed is False and raw.suppression_reason is None


# --- 3. the risk-free join: the load-bearing new criterion ---------------------------------------


def test_the_risk_free_leg_joins_by_MONTH_not_by_DATE(session: Session) -> None:
    """A vendor dating its monthly return on the FIRST of the month must still align with a book
    valuing on the last business day. Joining on the date would refuse this pair outright."""
    tenant = str(uuid.uuid4())
    bounds = _month_ends(13)
    first_of_month = [date(b.year, b.month, 1) for b in bounds[1:]]
    result = _run_sharpe(
        session,
        tenant,
        returns=["0.01", "0.02"] * 6,
        boundaries=bounds,
        rf_dates=first_of_month,
        windows=(12,),
    )
    assert result.status == "COMPLETED"
    assert all(not r.suppressed for r in result.rows)


def test_a_missing_risk_free_MONTH_is_a_pre_create_refusal_naming_the_month(
    session: Session,
) -> None:
    """Deliberately ASYMMETRIC with the per-window suppression convention: window-insufficiency is
    structural and time fills it, but a risk-free gap is a CAPTURE GAP an operator must fix, and
    computing "the windows we can" would ship a partially-poisoned surface."""
    tenant = str(uuid.uuid4())
    bounds = _month_ends(13)
    partial = bounds[1:]
    del partial[7]  # a SECOND gap, so the binder's multi-gap phrasing is reachable
    del partial[3]
    with pytest.raises(SharpeInputError) as caught:
        _run_sharpe(
            session,
            tenant,
            returns=["0.01", "0.02"] * 6,
            boundaries=bounds,
            rf_dates=partial,
            windows=(12,),
        )
    # The BINDER's own phrasing, not the kernel's fallback: it reports how many FURTHER months are
    # missing, which the kernel (stopping at the first) cannot. Without this the binder's
    # completeness check could be deleted outright and the kernel's defense-in-depth would keep the
    # test green — a control passing on another layer's evidence.
    assert "2024-05" in str(caught.value)
    assert "further month(s)" in str(caught.value)
    assert (
        session.execute(
            select(CalculationRun).where(
                CalculationRun.tenant_id == tenant, CalculationRun.run_type == RUN_TYPE_SHARPE
            )
        ).first()
        is None
    ), "a pre-create refusal must mint NO run"


def test_TWO_risk_free_rows_in_one_month_are_refused(session: Session) -> None:
    """THE CLAIM THE RECORD GOT WRONG. The draft called this "structural, because the read returns
    current heads" — but ``benchmark_return``'s grain keys on ``return_date``, so two different
    dates inside one month are BOTH current heads and both get pinned. The binder is the control."""
    tenant = str(uuid.uuid4())
    bounds = _month_ends(13)
    doubled = [*bounds[1:], date(bounds[2].year, bounds[2].month, 5)]
    with pytest.raises(SharpeInputError) as caught:
        _run_sharpe(
            session,
            tenant,
            returns=["0.01", "0.02"] * 6,
            boundaries=bounds,
            rf_dates=doubled,
            windows=(12,),
        )
    assert "more than one risk-free return" in str(caught.value)


def test_a_pinned_risk_free_row_outside_the_measured_months_is_refused(session: Session) -> None:
    """An unconsumed pin is a lie in the provenance: the snapshot would claim to bind an input the
    run never read."""
    tenant = str(uuid.uuid4())
    bounds = _month_ends(13)
    # The OPENING boundary's month is d_0 — it contributes no observation, so a row there is
    # pinned by the builder's window but must never be silently ignored.
    with pytest.raises(SharpeInputError) as caught:
        _run_sharpe(
            session,
            tenant,
            returns=["0.01", "0.02"] * 6,
            boundaries=bounds,
            rf_dates=[bounds[0], *bounds[1:]],
            windows=(12,),
        )
    assert "not a measured month" in str(caught.value)


def test_a_risk_free_series_with_no_rows_in_the_span_fails_closed_before_any_write(
    session: Session,
) -> None:
    from irp_shared.snapshot import SharpeSnapshotError

    tenant = str(uuid.uuid4())
    run, _pf, bounds = _seed_return_run(session, tenant, returns=["0.01"] * 12)
    head = _seed_risk_free(
        session, tenant, dates=[date(2030, 6, 28)], values=["0.004"]
    )  # entirely out of span
    with pytest.raises(SharpeSnapshotError):
        build_sharpe_snapshot(
            session,
            acting_tenant=tenant,
            actor=_SNAP_ACTOR,
            portfolio_return_run_id=run.run_id,
            risk_free_benchmark_id=head.id,
            rf_return_basis=RETURN_BASIS_TOTAL,
        )


def test_a_FOREIGN_tenants_risk_free_head_is_refused(session: Session) -> None:
    """P3-5: PG FK checks bypass RLS, so a hand-minted snapshot could durably stamp another tenant's
    benchmark into the ``risk_free_benchmark_id`` hard FK. Re-resolved under the acting tenant
    BEFORE the stamp."""
    from irp_shared.perf.sharpe_service import _assert_benchmark_in_tenant

    tenant, other = str(uuid.uuid4()), str(uuid.uuid4())
    head = _seed_risk_free(session, other, dates=[date(2024, 1, 31)], values=["0.004"])
    with pytest.raises(SharpeInputError):
        _assert_benchmark_in_tenant(session, str(head.id), acting_tenant=tenant)


# --- 4. the pre-create gate ----------------------------------------------------------------------


def test_a_window_outside_the_registered_domain_is_refused(session: Session) -> None:
    """The parameter domain is where GIPS-style annualization discipline is actually enforced, and
    RM-1 shipped without it until its review. Inherited here on day one."""
    tenant = str(uuid.uuid4())
    with pytest.raises(SharpeInputError) as caught:
        _run_sharpe(session, tenant, returns=["0.01", "0.02"] * 7, windows=(24,))
    assert "outside the registered domain" in str(caught.value)


def test_a_model_version_of_the_WRONG_family_is_refused(session: Session) -> None:
    tenant = str(uuid.uuid4())
    run, _pf, bounds = _seed_return_run(session, tenant, returns=["0.01"] * 12)
    head = _seed_risk_free(session, tenant, dates=bounds[1:], values=["0.004"] * 12)
    wrong = register_rolling_risk_model(
        session, tenant_id=tenant, actor_id="steward", code_version=_CODE_VERSION
    )
    snapshot = build_sharpe_snapshot(
        session,
        acting_tenant=tenant,
        actor=_SNAP_ACTOR,
        portfolio_return_run_id=run.run_id,
        risk_free_benchmark_id=head.id,
        rf_return_basis=RETURN_BASIS_TOTAL,
    )
    with pytest.raises(Exception, match=SHARPE_MODEL_CODE):
        run_sharpe_ratio(
            session,
            acting_tenant=tenant,
            actor=_ACTOR,
            code_version=_CODE_VERSION,
            environment_id="test",
            model_version_id=str(wrong.id),
            window_months=(12,),
            snapshot_id=snapshot.id,
        )


def test_a_snapshot_of_the_WRONG_PURPOSE_is_refused(session: Session) -> None:
    tenant = str(uuid.uuid4())
    run, _pf, _bounds = _seed_return_run(session, tenant, returns=["0.01"] * 12)
    rolling_snapshot = build_rolling_risk_snapshot(
        session, acting_tenant=tenant, actor=_SNAP_ACTOR, portfolio_return_run_id=run.run_id
    )
    version = register_sharpe_model(
        session, tenant_id=tenant, actor_id="steward", code_version=_CODE_VERSION
    )
    with pytest.raises(SharpeInputError) as caught:
        run_sharpe_ratio(
            session,
            acting_tenant=tenant,
            actor=_ACTOR,
            code_version=_CODE_VERSION,
            environment_id="test",
            model_version_id=str(version.id),
            window_months=(12,),
            snapshot_id=rolling_snapshot.id,
        )
    assert PURPOSE_ROLLING_RISK_INPUT in str(caught.value)


def test_a_misaligned_month_grid_is_refused(session: Session) -> None:
    """RM-1's five-condition alignment gate, reused unchanged — a mid-month CLOSE is not a grid
    point, and pooling a part-month observation with whole ones is what the gate exists to stop."""
    tenant = str(uuid.uuid4())
    bounds = _month_ends(13)
    bounds[-1] = date(bounds[-1].year, bounds[-1].month, 15)
    with pytest.raises(SharpeInputError):
        _run_sharpe(session, tenant, returns=["0.01"] * 12, boundaries=bounds, windows=(12,))


def test_a_month_at_or_below_total_loss_is_refused(session: Session) -> None:
    """POLICY, not domain necessity — Sharpe's arithmetic computes cleanly at -150%. The monthly
    series is SHARED SUBSTRATE with RM-1, and a book RM-1 refuses to carry a drawdown for must not
    quietly carry a Sharpe ratio."""
    tenant = str(uuid.uuid4())
    returns = ["0.01"] * 11 + ["-1.5"]
    with pytest.raises(SharpeInputError) as caught:
        _run_sharpe(session, tenant, returns=returns, windows=(12,))
    assert "-100%" in str(caught.value)


# --- 5. the magnitude gate ------------------------------------------------------------------------


def test_an_out_of_envelope_ratio_becomes_a_COMMITTED_FAILED_run_with_zero_rows(
    session: Session,
) -> None:
    """The ratio is UNBOUNDED on admitted inputs. The declared outcome is a COMMITTED FAILED run
    with DQ evidence and zero rows — never a partial emit, and never an uncaught raise with the run
    stranded in RUNNING."""
    tenant = str(uuid.uuid4())
    # A near-constant excess series with a tiny, non-zero dispersion: the mean is ~0.01 and sigma is
    # ~1e-12, so the ratio leaves the 1E7 envelope while every INPUT stays column-legal.
    returns = ["0.010000000001"] * 11 + ["0.010000000002"]
    result = _run_sharpe(session, tenant, returns=returns, rf="0.004", windows=(12,))
    assert result.status == "FAILED"
    assert result.rows == []
    assert "magnitude-out-of-range" in (result.failure_reason or "")
    # COMMITTED: the refusal is durable evidence, resolvable through the read surface.
    assert resolve_sharpe_run(session, result.run.run_id, acting_tenant=tenant) is not None


# --- 6. the rule-7 read surface -------------------------------------------------------------------


def test_the_reads_are_tenant_scoped_and_filterable(session: Session) -> None:
    tenant, other = str(uuid.uuid4()), str(uuid.uuid4())
    result = _run_sharpe(session, tenant, returns=["0.01", "0.02"] * 7, windows=(12, 36))
    session.flush()

    everything = list_sharpe_ratios(session, acting_tenant=tenant)
    assert len(everything) == len(result.rows)
    assert list_sharpe_ratios(session, acting_tenant=other) == []

    twelve = list_sharpe_ratios(session, acting_tenant=tenant, window_months=12)
    assert twelve and all(r.window_months == 12 for r in twelve)
    raw_only = list_sharpe_ratios(
        session, acting_tenant=tenant, metric_type=METRIC_TYPE_SHARPE_RATIO
    )
    assert raw_only and all(r.metric_type == METRIC_TYPE_SHARPE_RATIO for r in raw_only)

    portfolio_id = result.rows[0].portfolio_id
    assert latest_sharpe_ratio(session, acting_tenant=tenant, portfolio_id=portfolio_id)
    assert len(list_sharpe_ratio_rows(session, run_id=result.run.run_id, acting_tenant=tenant)) == (
        len(result.rows)
    )
    row = resolve_sharpe_ratio(session, result.rows[0].id, acting_tenant=tenant)
    assert row.id == result.rows[0].id
    with pytest.raises(SharpeNotVisible):
        resolve_sharpe_ratio(session, result.rows[0].id, acting_tenant=other)
    with pytest.raises(SharpeRunNotVisible):
        resolve_sharpe_run(session, result.run.run_id, acting_tenant=other)


# --- 7. the family conventions --------------------------------------------------------------------


def test_the_run_family_is_NEVER_a_metric_type_for_ANY_family(session: Session) -> None:
    """GS2, pinned platform-wide rather than as per-slice prose.

    Every prior slice asserted this for itself in its own file, which is why SR-1's ratified record
    could name ``RUN_TYPE_SHARPE_RATIO`` — a value identical to ``METRIC_TYPE_SHARPE_RATIO`` — while
    invoking the rule it breaks. One test for all of them now.
    """
    import irp_shared.perf.events as events
    import irp_shared.perf.models as models

    run_types = {v for k, v in vars(events).items() if k.startswith("RUN_TYPE_")}
    metric_types = {v for k, v in vars(models).items() if k.startswith("METRIC_TYPE_")}
    assert run_types and metric_types
    collisions = run_types & metric_types
    assert not collisions, f"run_type values that are also metric_type values: {sorted(collisions)}"


def test_the_binder_emits_NO_PERF_audit_code(session: Session) -> None:
    """The ``PERF.*`` block stays RESERVED-not-minted: the run reuses ``CALC.RUN_*``."""
    from irp_shared.audit.models import AuditEvent

    tenant = str(uuid.uuid4())
    _run_sharpe(session, tenant, returns=["0.01", "0.02"] * 7, windows=(12,))
    session.flush()
    codes = {
        e.event_type
        for e in session.execute(select(AuditEvent).where(AuditEvent.tenant_id == tenant)).scalars()
    }
    assert not any(c.startswith("PERF.") for c in codes), sorted(codes)
    assert any(c.startswith("CALC.RUN_") for c in codes)


def test_the_fence_kept_metric_constant_matches_PM_1s(session: Session) -> None:
    """``perf`` modules do not reach across for a string, so the copy is pinned to its source."""
    from irp_shared.perf.sharpe_service import _DIETZ_PERIOD

    assert _DIETZ_PERIOD == METRIC_TYPE_DIETZ_PERIOD
