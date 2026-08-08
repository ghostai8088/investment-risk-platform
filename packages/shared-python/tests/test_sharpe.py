"""SR-1 binder + end-to-end governed run (ENT-065 — the 22nd governed number).

Drives a real PM-1 return run and a real captured risk-free ``benchmark_return`` series through the
Sharpe binder, so the pin -> relink -> month-join -> window -> emit chain is exercised end to end.
The refusal tests then attack the pre-create gate — with particular weight on the risk-free join,
which is the load-bearing NEW criterion the ratified record omitted entirely and whose "this is
structural" claim the verifier pass refuted.
"""

from __future__ import annotations

import json
import uuid
from calendar import monthrange
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
    register_sharpe_model_v2,
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
    _adjudicate_portfolio_leg,
    latest_sharpe_ratio,
    list_sharpe_ratio_rows,
    list_sharpe_ratios,
    resolve_sharpe_ratio,
    resolve_sharpe_run,
    run_sharpe_ratio,
)
from irp_shared.portfolio import PortfolioActor, create_portfolio
from irp_shared.reference.calendar import (
    HolidaySpec,
    create_calendar,
    refresh_calendar_holidays,
)
from irp_shared.reference.models import Currency
from irp_shared.reference.service import ReferenceActor
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


def test_a_CONTINUOUS_vendor_series_covering_d0s_month_still_RUNS(session: Session) -> None:
    """THE REGRESSION TEST for a defect this slice shipped and a finder found by execution.

    ``d_0``'s month is NEVER a measured month — the alignment criterion guarantees it. The first
    builder pinned from the first of ``d_0``'s month anyway, so it captured ONLY rows the binder is
    guaranteed to refuse as unconsumed pins. An ordinary continuous vendor cash series publishes
    that month like any other, so the result was a **permanently unrunnable snapshot** — immutable,
    therefore unrepairable, from a completely legal capture.

    The fixture is deliberately the NORMAL shape: a vendor with no gaps, including d_0's month.
    """
    tenant = str(uuid.uuid4())
    bounds = _month_ends(13)
    # A continuous series: every month from d_0's onward, exactly as a real vendor publishes.
    continuous = bounds[:]
    result = _run_sharpe(
        session,
        tenant,
        returns=["0.01", "0.02"] * 6,
        boundaries=bounds,
        rf_dates=continuous,
        windows=(12,),
    )
    assert result.status == "COMPLETED"
    assert all(not r.suppressed for r in result.rows)


def test_a_LAST_BUSINESS_DAY_book_against_a_CALENDAR_month_end_vendor_RUNS(
    session: Session,
) -> None:
    """THE SECOND REGRESSION TEST, for the same class at the other edge.

    ``is_month_end`` admits the last BUSINESS day (GIPS 2.A.23.b), so a compliant book may close on
    2024-08-30 when 2024-08-31 is a Saturday. The first builder truncated the risk-free window at
    that DATE while the binder joins by MONTH — so a vendor dating on the calendar month end lost
    its final row and the run was refused for a missing month. A pure calendar accident, firing in
    roughly five months of twelve.

    **This is exactly the pair the month-key join was invented to accept**, which is what makes the
    defect so pointed: the mechanism was right and the window feeding it was not.
    """
    tenant = str(uuid.uuid4())
    bounds = _month_ends(13, start_year=2023, start_month=8)  # ends 2024-08-30 (Fri; 31st is a Sat)
    assert bounds[-1] == date(2024, 8, 30), f"fixture premise moved: {bounds[-1]}"
    calendar_ends = [date(b.year, b.month, monthrange(b.year, b.month)[1]) for b in bounds[1:]]
    # PREMISE: the vendor's last date really is AFTER the book's last boundary.
    assert calendar_ends[-1] > bounds[-1]

    result = _run_sharpe(
        session,
        tenant,
        returns=["0.01", "0.02"] * 6,
        boundaries=bounds,
        rf_dates=calendar_ends,
        windows=(12,),
    )
    assert result.status == "COMPLETED"
    assert all(not r.suppressed for r in result.rows)


def test_a_hand_built_snapshot_pinning_a_NON_measured_month_is_refused(session: Session) -> None:
    """The unconsumed-pin guard, now unreachable through the BUILD path and tested through a FORGED
    snapshot instead — the `test_var_hs`/`test_benchmark_relative` pattern.

    Keeping the guard is right: it defends the provenance against a hand-built snapshot, where a
    pinned row the run never reads is a lie about what the number was computed from. But testing it
    through the builder would now require the builder to be wrong, which is the defect above.
    """
    from irp_shared.snapshot.serialize import benchmark_return_series_content

    tenant = str(uuid.uuid4())
    bounds = _month_ends(13)
    run, _pf, _b = _seed_return_run(
        session, tenant, returns=["0.01", "0.02"] * 6, boundaries=bounds
    )
    head = _seed_risk_free(
        session,
        tenant,
        dates=[*bounds[1:], date(2030, 3, 29)],  # one row in a month the book never measured
        values=["0.004"] * 13,
    )
    snapshot = build_sharpe_snapshot(
        session,
        acting_tenant=tenant,
        actor=_SNAP_ACTOR,
        portfolio_return_run_id=run.run_id,
        risk_free_benchmark_id=head.id,
        rf_return_basis=RETURN_BASIS_TOTAL,
    )
    # PREMISE: the BUILDER correctly excluded the foreign month — so the guard below is genuinely
    # about hand-built content, not about the build path.
    from irp_shared.snapshot import COMPONENT_KIND_BENCHMARK_RETURN, list_components

    pinned = [
        json.loads(c.captured_content)
        for c in list_components(session, snapshot_id=snapshot.id, acting_tenant=tenant)
        if c.component_kind == COMPONENT_KIND_BENCHMARK_RETURN
    ]
    assert pinned and all(
        r["return_date"] != "2030-03-29" for r in pinned[0]["rows"]
    ), "the builder pinned a non-measured month — the window fix regressed"

    # Now forge it: adjudicate content carrying that foreign row directly.
    from irp_shared.perf.sharpe_service import _adjudicate_pins, _parse_pins

    portfolio_raw, rf_raw = _parse_pins(
        list(list_components(session, snapshot_id=snapshot.id, acting_tenant=tenant))
    )
    rf_raw[0]["rows"].append(
        {
            "id": str(uuid.uuid4()),
            "return_date": "2030-03-29",
            "return_type": "SIMPLE",
            "return_basis": RETURN_BASIS_TOTAL,
            "return_value": "0.004",
        }
    )
    with pytest.raises(SharpeInputError) as caught:
        _adjudicate_pins(portfolio_raw, rf_raw)
    assert "not a measured month" in str(caught.value)
    assert benchmark_return_series_content  # the serializer the forged shape mirrors


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


def _forge_snapshot_with(session: Session, tenant: str, *, mutate) -> tuple[str, str]:  # noqa: ANN001
    """Build a legitimate SHARPE_INPUT snapshot, then persist a SECOND one whose pinned content has
    been tampered with — the `test_var_hs`/`test_benchmark_relative` forged-snapshot pattern.

    This is what makes the binder's cross-tenant re-resolutions testable AT THE BINDER. Calling the
    private helpers directly proves the helpers work and proves nothing about the binder calling
    them — the project's own "a control passing on another layer's evidence" defect, which a review
    found in the first version of these tests.
    """
    from irp_shared.snapshot import list_components
    from irp_shared.snapshot.service import _persist_snapshot

    run, _pf, bounds = _seed_return_run(session, tenant, returns=["0.01", "0.02"] * 6)
    head = _seed_risk_free(session, tenant, dates=bounds[1:], values=["0.004"] * 12)
    good = build_sharpe_snapshot(
        session,
        acting_tenant=tenant,
        actor=_SNAP_ACTOR,
        portfolio_return_run_id=run.run_id,
        risk_free_benchmark_id=head.id,
        rf_return_basis=RETURN_BASIS_TOTAL,
    )
    specs: list = []
    for comp in list_components(session, snapshot_id=good.id, acting_tenant=tenant):
        content = json.loads(comp.captured_content)
        mutate(content, comp.component_kind)
        raw = json.dumps(content, sort_keys=True, separators=(",", ":"))
        specs.append(
            (
                comp.component_kind,
                comp.target_entity_type,
                type("Row", (), {"id": comp.target_entity_id})(),
                raw,
                comp.content_hash,
            )
        )
    forged = _persist_snapshot(
        session,
        acting_tenant=tenant,
        actor=_SNAP_ACTOR,
        specs=specs,
        label="",
        purpose="SHARPE_INPUT",
        as_of_valid_at=good.as_of_valid_at,
        as_of_known_at=good.as_of_known_at,
        as_of_valuation_date=good.as_of_valuation_date,
        binding_predicate_version=good.binding_predicate_version,
    )
    version = register_sharpe_model(
        session, tenant_id=tenant, actor_id="steward", code_version=_CODE_VERSION
    )
    return forged.id, str(version.id)


def _run_forged(session: Session, tenant: str, snapshot_id: str, version_id: str):  # noqa: ANN202
    return run_sharpe_ratio(
        session,
        acting_tenant=tenant,
        actor=_ACTOR,
        code_version=_CODE_VERSION,
        environment_id="test",
        model_version_id=version_id,
        window_months=(12,),
        snapshot_id=snapshot_id,
    )


def test_the_BINDER_refuses_a_foreign_tenants_risk_free_head(session: Session) -> None:
    """P3-5 at the BINDER, not at the helper. PG FK checks bypass RLS, so a hand-minted snapshot
    could durably stamp another tenant's benchmark into the `risk_free_benchmark_id` hard FK.

    A mutation deleting the binder's `_assert_benchmark_in_tenant` call survived the first version
    of this suite, because the only test called that helper directly.
    """
    tenant, other = str(uuid.uuid4()), str(uuid.uuid4())
    foreign = _seed_risk_free(session, other, dates=[date(2024, 1, 31)], values=["0.004"])

    def _swap(content: dict, kind: str) -> None:
        if kind == "BENCHMARK_RETURN":
            content["benchmark_id"] = str(foreign.id)

    snapshot_id, version_id = _forge_snapshot_with(session, tenant, mutate=_swap)
    with pytest.raises(SharpeInputError, match="not visible"):
        _run_forged(session, tenant, snapshot_id, version_id)


def test_the_BINDER_refuses_a_foreign_tenants_portfolio(session: Session) -> None:
    """The same guard on the measured book. Had NO test at all before a review found the gap."""
    tenant, other = str(uuid.uuid4()), str(uuid.uuid4())
    foreign_book = create_portfolio(
        session,
        tenant_id=other,
        code=f"pf-{uuid.uuid4().hex[:8]}",
        name="Foreign",
        node_type="ACCOUNT",
        actor=PortfolioActor(actor_id="steward"),
    )
    session.flush()

    def _swap(content: dict, kind: str) -> None:
        if kind == "PORTFOLIO_RETURN":
            content["portfolio_id"] = str(foreign_book.id)

    snapshot_id, version_id = _forge_snapshot_with(session, tenant, mutate=_swap)
    with pytest.raises(SharpeInputError):
        _run_forged(session, tenant, snapshot_id, version_id)


def test_the_BINDER_refuses_a_foreign_tenants_portfolio_return_run(session: Session) -> None:
    """And on the consumed upstream run — the third hard FK. Also had no test."""
    tenant, other = str(uuid.uuid4()), str(uuid.uuid4())
    foreign_run, _pf, _b = _seed_return_run(session, other, returns=["0.01"] * 12)

    def _swap(content: dict, kind: str) -> None:
        if kind == "PORTFOLIO_RETURN":
            content["calculation_run_id"] = str(foreign_run.run_id)

    snapshot_id, version_id = _forge_snapshot_with(session, tenant, mutate=_swap)
    with pytest.raises(SharpeInputError):
        _run_forged(session, tenant, snapshot_id, version_id)


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
    """GS2, pinned across EVERY module that declares either vocabulary.

    Every prior slice asserted this for itself in its own file, which is why SR-1's ratified record
    could name ``RUN_TYPE_SHARPE_RATIO`` — a value identical to ``METRIC_TYPE_SHARPE_RATIO`` — while
    invoking the rule it breaks.

    **The first version of THIS test was the same mistake one level up.** It scanned only
    ``perf.events`` and ``perf.models``: 5 of 18 run types and 15 of 38 metric types. A finder
    injected a genuine collision into ``risk.events`` and it stayed green — a sampled contract guard
    is false security (the standing FE-2 lesson). The module list is now DISCOVERED from the package
    rather than enumerated, so a new family is covered the moment it declares a constant, and the
    census below asserts the scan is not silently empty.
    """
    import importlib
    import pkgutil

    import irp_shared

    run_types: dict[str, str] = {}
    metric_types: dict[str, str] = {}
    scanned: list[str] = []
    failed_imports: list[str] = []
    for info in pkgutil.walk_packages(irp_shared.__path__, prefix="irp_shared."):
        if not info.name.endswith((".events", ".models")):
            continue
        try:
            module = importlib.import_module(info.name)
        except Exception:  # noqa: BLE001 - collected and ASSERTED empty below (Wave-13 close)
            failed_imports.append(info.name)
            continue
        found = False
        for name, value in vars(module).items():
            if not isinstance(value, str):
                continue
            if name.startswith("RUN_TYPE_"):
                run_types[value] = f"{info.name}.{name}"
                found = True
            elif name.startswith("METRIC_TYPE_"):
                metric_types[value] = f"{info.name}.{name}"
                found = True
        if found:
            scanned.append(info.name)

    # Wave-13 close: a silently-skipped unimportable module was a hole in the census — a declaring
    # module with a broken import would drop its whole vocabulary from the scan and the guard would
    # pass by finding less. Nothing fails to import today; if something does, THIS fails, loudly.
    assert not failed_imports, f"declaring-module candidates failed to import: {failed_imports}"
    # The scan must actually reach the modules that carry these vocabularies — otherwise a rename or
    # a package move would silently empty it and the guard would pass by finding nothing. ALL SIX
    # declaring modules are pinned since the Wave-13 close (exposure.events and pacing.events both
    # declare RUN_TYPE_* constants and were absent from this membership assert).
    assert {"irp_shared.perf.events", "irp_shared.perf.models"} <= set(scanned)
    assert {"irp_shared.risk.events", "irp_shared.risk.models"} <= set(scanned)
    assert {"irp_shared.exposure.events", "irp_shared.pacing.events"} <= set(scanned)
    # REPRO-1: the reproduction family's declaring module joins the membership pin, so a package
    # move or rename empties the scan LOUDLY instead of silently shrinking the census.
    assert {"irp_shared.reproduction.models"} <= set(scanned)
    # Exact census, not a floor (Wave-13 close: the floors sat at 15/30 against true totals of
    # 18/38, so up to 3 run types and 8 metric types could vanish from the scan without failing —
    # a census that tolerates shrinkage is a floor wearing a census's name). Adding a run type or
    # metric type legitimately moves these pins; that is what a census pin is FOR (the demo-counts
    # precedent: the pin moves consciously, with the slice that moves it).
    # 18 -> 19 at CON-1: concentration.events.RUN_TYPE_CONCENTRATION (no metric carries it).
    # REPRO-1: +REPRODUCTION (reproduction.models.RUN_TYPE_REPRODUCTION). Declared in `models`, not
    # in the service module, precisely so THIS census can see it — a RUN_TYPE_* declared in a
    # service module escapes the scan that exists to catch a run family colliding with a metric
    # name, which RPT-1 found by executing it.
    assert (
        len(run_types) == 22
    ), f"run-type census moved: {len(run_types)}: {sorted(run_types)}"  # RPT-1: +REPORT
    # 38 -> 39 at CON-1: concentration.models.METRIC_TYPE_SHARE (the detail-row metric; the nine
    # summary names live in SUMMARY_METRIC_TYPES with their own exact census — none is a run type).
    assert (
        len(metric_types) == 42
    ), (
        f"metric-type census moved: {len(metric_types)}"
    )  # LQ-1: +TIER_SHARE, +ILLIQUID_SHARE, +HIGHLY_LIQUID_SHARE

    collisions = sorted(set(run_types) & set(metric_types))
    assert not collisions, "run_type values that are also metric_type values: " + ", ".join(
        f"{v} ({run_types[v]} vs {metric_types[v]})" for v in collisions
    )


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


# --- 8. the endpoint serialization contract ------------------------------------------------------


def test_the_endpoint_serializes_fixed_point_and_keeps_NULL_as_NULL() -> None:
    """Two things at once, because they fail in opposite directions.

    ``str(Decimal('1E-8'))`` flips to scientific notation, which no consumer parses as a decimal —
    so the row-out must stay fixed-point. And a SUPPRESSED row must keep ``metric_value`` NULL:
    rendering it as ``"0"`` would destroy the exact distinction the nullable column exists for, and
    a zero Sharpe ratio is a real governed value that a reader would then be unable to tell apart
    from "we could not compute this".
    """
    from irp_backend.api.perf import _sr_row_out
    from irp_shared.perf.models import SharpeRatioResult

    def _row(**over) -> SharpeRatioResult:  # noqa: ANN003
        values = {
            "tenant_id": str(uuid.uuid4()),
            "calculation_run_id": str(uuid.uuid4()),
            "input_snapshot_id": str(uuid.uuid4()),
            "model_version_id": str(uuid.uuid4()),
            "portfolio_id": str(uuid.uuid4()),
            "portfolio_return_run_id": str(uuid.uuid4()),
            "risk_free_benchmark_id": str(uuid.uuid4()),
            "rf_return_basis": RETURN_BASIS_TOTAL,
            "metric_type": METRIC_TYPE_SHARPE_RATIO,
            "window_months": 12,
            "period_start": date(2024, 12, 31),
            "period_end": date(2025, 12, 31),
            "metric_value": D("1E-8").quantize(D(1).scaleb(-12)),
            "suppressed": False,
            "suppression_reason": None,
            "annualization_basis": ANNUALIZATION_NONE,
            "sampling_frequency": "MONTHLY",
            "n_observations": 12,
        }
        values.update(over)
        row = SharpeRatioResult(**values)
        row.id = str(uuid.uuid4())
        return row

    emitted = _sr_row_out(_row())
    assert emitted.metric_value == "0.000000010000"
    assert "E" not in emitted.metric_value and "e" not in emitted.metric_value

    suppressed = _sr_row_out(
        _row(
            metric_value=None,
            suppressed=True,
            suppression_reason=ZERO_DISPERSION_REASON,
        )
    )
    assert suppressed.metric_value is None
    assert suppressed.suppressed is True
    assert suppressed.suppression_reason == ZERO_DISPERSION_REASON


def test_the_latest_route_is_declared_BEFORE_the_path_parameter_route() -> None:
    """FastAPI matches in declaration order, so ``/{result_id}`` declared first would swallow the
    literal ``/latest`` and turn a governed read into a 422 on an unparseable UUID (the house rule,
    asserted rather than assumed)."""
    from irp_backend.api.perf import router

    paths = [r.path for r in router.routes if "/perf/sharpe" in getattr(r, "path", "")]
    assert paths.index("/perf/sharpe/latest") < paths.index("/perf/sharpe/{result_id}")


# --- the strict-parse pin, mirrored from RM-1 (Wave-13 close) ------------------------------------


def test_a_NaN_pinned_return_is_refused_by_the_strict_parse(session: Session) -> None:
    """SR-1's behaviour was already correct — ``parse_strict_decimal`` with a comment naming the
    exact hazard — but NOTHING pinned it: no NaN case existed in this suite, so the shipped
    convention was one refactor away from silently regressing to the bare ``Decimal()`` its RM-1
    sibling shipped with (the Wave-13 close's cross-integration finding). The pin is symmetric with
    ``test_rolling_risk.py``'s, so the two governed families can no longer drift apart unnoticed
    on the same pin shape.
    """
    base = {
        "metric_type": METRIC_TYPE_DIETZ_PERIOD,
        "calculation_run_id": str(uuid.uuid4()),
        "portfolio_id": "p1",
        "period_start": "2026-01-30",
        "period_end": "2026-02-28",
        "return_value": "0.01",
    }
    for bad in ("NaN", "sNaN", "Infinity", "-Infinity"):
        with pytest.raises(SharpeInputError, match="not a finite number"):
            _adjudicate_portfolio_leg([{**base, "return_value": bad}])


# --- CAL-1b: the v2 holiday-aware convention, the SHARPE twins (the review's HIGH: sharpe v2 had
# zero discriminating coverage — the lockstep move needs its own proofs) ---------------------------


def _seed_xnys_calendar(session: Session, tenant: str) -> None:
    cal = create_calendar(
        session, tenant_id=tenant, code="XNYS", name="NYSE", actor=ReferenceActor(actor_id="s")
    )
    refresh_calendar_holidays(
        session,
        cal,
        actor=ReferenceActor(actor_id="s"),
        holidays=[
            # New Year's Day of the OPENING year anchors the derived coverage start (the Wave-14
            # close's start-side gate; 2024 covers every book these fixtures open). A Jan-1
            # holiday can never move a BUSINESS month-END, so no
            # asserted boundary literal shifts. The single-2027 set this fixture previously pinned
            # was itself the degradation the gate refuses: months before 2027 rolled weekend-only.
            HolidaySpec(holiday_date=date(2024, 1, 1), name="New Year's Day"),
            HolidaySpec(holiday_date=date(2027, 5, 31), name="Memorial Day"),
        ],
        complete_through=date(2035, 12, 31),
    )


def _boundaries_ending_2027_05_28(count: int) -> list[date]:
    months = []
    year, month = 2027, 5
    for _ in range(count):
        months.append((year, month))
        year, month = (year - 1, 12) if month == 1 else (year, month - 1)
    months.reverse()
    bounds = [last_weekday_of_month(y, m) for (y, m) in months[:-1]]
    return [*bounds, date(2027, 5, 28)]


def _run_sharpe_v2(session: Session, tenant: str, *, with_pin: bool = True):  # noqa: ANN202
    bounds = _boundaries_ending_2027_05_28(14)
    run, _pf, bounds = _seed_return_run(session, tenant, returns=["0.01"] * 13, boundaries=bounds)
    head = _seed_risk_free(session, tenant, dates=bounds[1:], values=["0.004"] * 13)
    version = register_sharpe_model_v2(
        session, tenant_id=tenant, actor_id="steward", code_version=_CODE_VERSION
    )
    snapshot = build_sharpe_snapshot(
        session,
        acting_tenant=tenant,
        actor=_SNAP_ACTOR,
        portfolio_return_run_id=run.run_id,
        risk_free_benchmark_id=head.id,
        rf_return_basis=RETURN_BASIS_TOTAL,
        holiday_calendar_code="XNYS" if with_pin else None,
    )
    return run_sharpe_ratio(
        session,
        acting_tenant=tenant,
        actor=_ACTOR,
        code_version=_CODE_VERSION,
        environment_id="test",
        model_version_id=str(version.id),
        window_months=(12,),
        snapshot_id=snapshot.id,
    )


def test_sharpe_v1_refuses_the_pre_holiday_business_day(session: Session) -> None:
    tenant = str(uuid.uuid4())
    with pytest.raises(SharpeInputError, match="not a month end"):
        _run_sharpe(
            session,
            tenant,
            returns=["0.01"] * 13,
            boundaries=_boundaries_ending_2027_05_28(14),
        )


def test_sharpe_v2_accepts_it_with_the_pinned_holiday_set(session: Session) -> None:
    tenant = str(uuid.uuid4())
    _seed_xnys_calendar(session, tenant)
    result = _run_sharpe_v2(session, tenant)
    assert result.status == "COMPLETED"
    assert result.rows


def test_sharpe_v2_without_the_pin_is_refused(session: Session) -> None:
    tenant = str(uuid.uuid4())
    _seed_xnys_calendar(session, tenant)
    with pytest.raises(SharpeInputError, match="pins no HOLIDAY_CALENDAR"):
        _run_sharpe_v2(session, tenant, with_pin=False)


def test_sharpe_v2_span_beyond_the_declared_coverage_is_refused(session: Session) -> None:
    tenant = str(uuid.uuid4())
    cal = create_calendar(
        session, tenant_id=tenant, code="XNYS", name="NYSE", actor=ReferenceActor(actor_id="s")
    )
    refresh_calendar_holidays(
        session,
        cal,
        actor=ReferenceActor(actor_id="s"),
        holidays=[HolidaySpec(holiday_date=date(2027, 5, 31))],
        complete_through=date(2027, 3, 31),  # short of the series close
    )
    with pytest.raises(SharpeInputError, match="declared holiday coverage"):
        _run_sharpe_v2(session, tenant)
