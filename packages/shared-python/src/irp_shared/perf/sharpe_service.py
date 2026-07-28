"""SR-1 Sharpe-ratio binder (ENT-065 — the 22nd governed number).

Consumes ONE governed PM-1 ``PORTFOLIO_RETURN`` run and ONE captured risk-free ``benchmark_return``
series, relinks the return sub-periods to a calendar-month grid (RM-1's machinery, reused),
differences the two legs, and emits the trailing-window Sharpe ratio and its annualization.

**RUN-BOUND + SNAPSHOT-GATED + MODEL-BOUND** (AD-014 / FW-RUN / TR-15 / CTRL-003). Computes ONLY
from pinned content — neither a later PM-1 re-run nor a vendor correction to the risk-free series
can move a historical Sharpe number (TR-09).

**Nothing is read from RM-1's result rows.** ``rolling_risk_result`` stores window AGGREGATES, not
the monthly series, and its ``ROLLING_VOLATILITY`` is sigma of the PORTFOLIO series where Sharpe
(1994) needs sigma of the EXCESS series. SR-1 therefore re-derives the monthly series from the same
pins via the same kernel helpers, and the two families share substrate rather than results.

**Failure model** (the family convention, inherited verbatim). A pre-create refusal — a
missing/invalid prerequisite, an unregistered or wrong ``model_version``, a misaligned month grid,
a month at or below -100%, a risk-free gap or duplicate — raises and rolls the WHOLE unit back:
ZERO run. A post-create FAILED run (a magnitude past the emit envelope) is COMMITTED with zero
rows.

**The two refusal shapes are deliberately ASYMMETRIC, and the asymmetry is the design.** A window
the series cannot fill emits a governed SUPPRESSED row (nullable value + explicit flag + reason):
the absence is disclosed, and time alone fixes it. A missing risk-free MONTH is a pre-create
refusal naming the month: that is a capture gap an operator must act on, and computing "the windows
we can" over a gappy risk-free series would ship a partially-poisoned surface whose gaps are
invisible to every downstream read.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date as dt_date
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from irp_shared.calc.models import CalculationRun
from irp_shared.calc.parse import parse_strict_decimal
from irp_shared.calc.reads import latest_run_rows, list_governed_results
from irp_shared.calc.runs import resolve_completed_run_of_type
from irp_shared.calc.scaffold import execute_governed_run
from irp_shared.marketdata.models import BENCHMARK_RETURN_BASES, RETURN_TYPE_SIMPLE
from irp_shared.model.service import assert_model_version_of
from irp_shared.perf.bootstrap import SHARPE_MODEL_CODE, SHARPE_WINDOWS
from irp_shared.perf.events import (
    RUN_TYPE_PORTFOLIO_RETURN,
    RUN_TYPE_SHARPE,
    SharpeRatioActor,
)
from irp_shared.perf.models import (
    ANNUALIZATION_NONE,
    ANNUALIZATION_SQRT_12,
    METRIC_TYPE_SHARPE_RATIO,
    METRIC_TYPE_SHARPE_RATIO_ANN,
    SAMPLING_FREQUENCY_MONTHLY,
    SharpeRatioResult,
)
from irp_shared.perf.return_kernel import ReturnKernelError
from irp_shared.perf.rolling_kernel import (
    MonthlyReturn,
    RollingKernelError,
    SubPeriod,
    assert_above_total_loss,
    assert_month_aligned,
    relink_to_months,
)
from irp_shared.perf.sharpe_kernel import (
    ZERO_DISPERSION_REASON,
    MonthlyExcess,
    SharpeKernelError,
    build_excess_series,
    month_key,
    sharpe_windows,
)
from irp_shared.perf.stats_kernel import StatsKernelError
from irp_shared.portfolio.guards import assert_portfolio_in_tenant
from irp_shared.snapshot import (
    COMPONENT_KIND_BENCHMARK_RETURN,
    COMPONENT_KIND_PORTFOLIO_RETURN,
    PURPOSE_SHARPE_INPUT,
    list_components,
    resolve_snapshot,
)

#: PM-1's metric vocabulary, kept as a FENCE-KEPT LOCAL copy (the P3-8/PM-1/RM-1 precedent —
#: ``perf``
#: modules do not reach across for a string). Pinned equal to the source in the test suite.
_DIETZ_PERIOD = "DIETZ_PERIOD"

#: The DQ rule this binder's completeness gate registers under.
_COMPLETENESS_RULE_CODE = "perf.sharpe.completeness"
_COMPLETENESS_RULE_NAME = "Sharpe-ratio input completeness"

#: The result-scale envelope. The gate applies to the EMITTED (post-annualization) value: the ratio
#: is UNBOUNDED on admitted inputs (twelve column-legal months can yield 1E10), and annualizing
#: amplifies by another sqrt(12), so gating the pre-transform number would let an out-of-range row
#: reach the flush — OUTSIDE the caught DataQualityError, surfacing as a 500 with the run orphaned
#: in
#: RUNNING (the P3-8/RM-1 fold, inherited on day one rather than after a review).
_MAX_RESULT_ABS = Decimal("1E7")


class SharpeInputError(Exception):
    """A pre-create refusal: an ill-formed or ungovernable Sharpe input."""


class SharpeNotVisible(Exception):
    """A Sharpe row is not visible in the acting tenant."""


class SharpeRunNotVisible(Exception):
    """A Sharpe run is not visible in the acting tenant."""


@dataclass(frozen=True)
class SharpeRunResult:
    run: CalculationRun
    status: str
    rows: list[SharpeRatioResult]
    failure_reason: str | None = None


@dataclass(frozen=True)
class _ParsedInput:
    """The adjudicated pinned content — everything the compute needs, all of it from pins."""

    portfolio_return_run_id: str
    portfolio_id: str
    risk_free_benchmark_id: str
    rf_return_basis: str
    excess: list[MonthlyExcess]
    opening_boundary: dt_date


def _parse_pins(components: Sequence[Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Parse the pinned ``captured_content`` into raw portfolio-return / risk-free-series dicts
    (PURE — no live read; the AD-014 invariant)."""
    portfolio_raw: list[dict[str, Any]] = []
    rf_raw: list[dict[str, Any]] = []
    for component in components:
        if component.component_kind == COMPONENT_KIND_PORTFOLIO_RETURN:
            portfolio_raw.append(json.loads(component.captured_content))
        elif component.component_kind == COMPONENT_KIND_BENCHMARK_RETURN:
            rf_raw.append(json.loads(component.captured_content))
    return portfolio_raw, rf_raw


def _as_date(value: Any) -> dt_date:
    return value if isinstance(value, dt_date) else dt_date.fromisoformat(str(value))


def _adjudicate_portfolio_leg(
    raw: list[dict[str, Any]],
) -> tuple[list[MonthlyReturn], dt_date, str, str]:
    """The RM-1 portfolio-side adjudication, applied unchanged: one run, one book, DIETZ
    sub-periods,
    the five-condition month alignment, the relink, and the ``1 + m > 0`` precondition.

    Returns ``(months, opening_boundary, run_id, portfolio_id)``.
    """
    if not raw:
        raise SharpeInputError("the snapshot pins no PORTFOLIO_RETURN rows — not a Sharpe input")
    dietz = [r for r in raw if r["metric_type"] == _DIETZ_PERIOD]
    if not dietz:
        raise SharpeInputError("the pinned return run has no DIETZ_PERIOD sub-periods")

    run_ids = {str(r["calculation_run_id"]).lower() for r in raw}
    portfolio_ids = {str(r["portfolio_id"]) for r in raw}
    if len(run_ids) != 1:
        raise SharpeInputError("the pinned return rows span multiple runs — refused")
    if len(portfolio_ids) != 1:
        raise SharpeInputError(
            f"the pinned return rows span {len(portfolio_ids)} portfolios — refused"
        )

    try:
        sub_periods = sorted(
            (
                SubPeriod(
                    period_start=_as_date(r["period_start"]),
                    period_end=_as_date(r["period_end"]),
                    # parse_strict_decimal, not a bare Decimal(): NaN parses cleanly and is not an
                    # ArithmeticError, so a hand-built snapshot carrying "NaN" would sail past a
                    # try/except and reach the arithmetic. Refused here as a 422.
                    return_value=parse_strict_decimal(
                        r["return_value"], error=SharpeInputError, field="return_value"
                    ),
                )
                for r in dietz
            ),
            key=lambda p: p.period_start,
        )
    except (KeyError, ValueError, ArithmeticError, TypeError) as exc:
        if isinstance(exc, SharpeInputError):
            raise
        raise SharpeInputError(
            f"a pinned PORTFOLIO_RETURN component is malformed and cannot be read: {exc}"
        ) from exc

    # The boundary grid: d_0 is the first sub-period's START (the close of the month BEFORE the
    # first
    # measured month), then every sub-period end.
    boundaries = [sub_periods[0].period_start] + [p.period_end for p in sub_periods]
    try:
        assert_month_aligned(boundaries)
        months = relink_to_months(sub_periods)
        assert_above_total_loss(months)
    except RollingKernelError as exc:
        # Converted at the binder boundary: a caller owed a governed refusal must not receive a
        # kernel error. The kernel's own raises stay defense-in-depth.
        raise SharpeInputError(str(exc)) from exc

    return months, boundaries[0], next(iter(run_ids)), next(iter(portfolio_ids))


def _adjudicate_risk_free_leg(
    rf_raw: list[dict[str, Any]], months: Sequence[MonthlyReturn]
) -> tuple[str, str, dict[tuple[int, int], Decimal]]:
    """The risk-free side: exactly one uniform series, joined to the measured months by MONTH KEY.

    Four refusals, each of which the draft record either omitted or got wrong:

    1. **more than one current-head rf row in one measured month.** The record claimed this was
       "structural, because the read returns current heads" — that is FALSE: ``benchmark_return``'s
       grain keys on ``return_date``, so two DIFFERENT dates inside one month are BOTH current heads
       and both get pinned. The binder is the control, and this is it.
    2. **a pinned rf row whose month is not a measured month.** Silently ignoring it would leave an
       unconsumed pin in the provenance — a snapshot claiming to bind an input the run never read.
    3. **a measured month with no rf row** — the completeness refusal, naming the month.
    4. **a non-uniform series** (mixed ``return_type``/``return_basis``): a Sharpe run is defined
       against ONE risk-free series, and two bases behind one head are two different numbers.
    """
    if len(rf_raw) != 1:
        raise SharpeInputError(
            f"the snapshot must pin exactly one risk-free series (got {len(rf_raw)})"
        )
    series = rf_raw[0]
    benchmark_id = str(series["benchmark_id"]).lower()
    rf_return_basis = series["return_basis"]
    if rf_return_basis not in BENCHMARK_RETURN_BASES:
        raise SharpeInputError(f"unknown risk-free return_basis {rf_return_basis!r}")
    if series["return_type"] != RETURN_TYPE_SIMPLE:
        raise SharpeInputError(
            f"the pinned risk-free series return_type {series['return_type']!r} is not SIMPLE"
        )
    rows = series["rows"]
    if not rows:
        raise SharpeInputError("the pinned risk-free series carries no rows — refused")
    if any(
        r["return_type"] != RETURN_TYPE_SIMPLE or r["return_basis"] != rf_return_basis for r in rows
    ):
        raise SharpeInputError(
            "the pinned risk-free rows are not uniform SIMPLE/return_basis — refused"
        )

    measured = {month_key(m.month_end) for m in months}
    by_month: dict[tuple[int, int], Decimal] = {}
    for row in rows:
        try:
            when = _as_date(row["return_date"])
        except (KeyError, ValueError, TypeError) as exc:
            raise SharpeInputError(
                f"a pinned risk-free row has an unreadable return_date: {exc}"
            ) from exc
        key = month_key(when)
        if key not in measured:
            raise SharpeInputError(
                f"the pinned risk-free row dated {when} falls in {key[0]}-{key[1]:02d}, which is "
                "not a measured month — refused (every pinned row must be consumed)"
            )
        if key in by_month:
            raise SharpeInputError(
                f"{key[0]}-{key[1]:02d} carries more than one risk-free return — refused; a "
                "measured month must resolve to exactly one risk-free observation"
            )
        by_month[key] = parse_strict_decimal(
            row["return_value"], error=SharpeInputError, field="rf return_value"
        )

    missing = sorted(measured - set(by_month))
    if missing:
        first = missing[0]
        raise SharpeInputError(
            f"no risk-free return for {first[0]}-{first[1]:02d}"
            + (f" (and {len(missing) - 1} further month(s))" if len(missing) > 1 else "")
            + " — refused; there is no imputation and no carry-forward"
        )
    return benchmark_id, rf_return_basis, by_month


def _adjudicate_pins(
    portfolio_raw: list[dict[str, Any]], rf_raw: list[dict[str, Any]]
) -> _ParsedInput:
    """PRE-CREATE adjudication of the FULL pinned input. Raises :class:`SharpeInputError`.

    Order matters: the portfolio leg first (it defines which months are MEASURED, and therefore what
    the risk-free leg is judged against), then the risk-free leg, then the difference.
    """
    months, opening_boundary, run_id, portfolio_id = _adjudicate_portfolio_leg(portfolio_raw)
    benchmark_id, rf_return_basis, by_month = _adjudicate_risk_free_leg(rf_raw, months)
    try:
        excess = build_excess_series(months, by_month)
    except SharpeKernelError as exc:  # defense-in-depth: the completeness gate above precedes it
        raise SharpeInputError(str(exc)) from exc
    return _ParsedInput(
        portfolio_return_run_id=run_id,
        portfolio_id=portfolio_id,
        risk_free_benchmark_id=benchmark_id,
        rf_return_basis=rf_return_basis,
        excess=excess,
        opening_boundary=opening_boundary,
    )


def _resolve_return_run(session: Session, run_id: str, *, acting_tenant: str) -> CalculationRun:
    """Re-resolve the consumed PORTFOLIO_RETURN run under the acting tenant (+ run_type + COMPLETED)
    BEFORE its id is stamped into the ``portfolio_return_run_id`` hard FK — PG FK checks bypass RLS,
    so a hand-minted snapshot could otherwise reference a FOREIGN tenant's run (P3-5)."""
    return resolve_completed_run_of_type(
        session,
        run_id,
        acting_tenant=acting_tenant,
        run_type=RUN_TYPE_PORTFOLIO_RETURN,
        label="portfolio-return",
        error=SharpeInputError,
    )


def _format_reason(gate: Exception, gaps: list[str]) -> str:
    return f"sharpe completeness failed: {'; '.join(gaps) or gate}"


def run_sharpe_ratio(
    session: Session,
    *,
    acting_tenant: str,
    actor: SharpeRatioActor,
    code_version: str,
    environment_id: str,
    model_version_id: str,
    window_months: tuple[int, ...],
    snapshot_id: str,
) -> SharpeRunResult:
    """Run a governed Sharpe calculation over a pinned ``SHARPE_INPUT`` snapshot.

    ``window_months`` must lie inside the REGISTERED model version's declared domain ({12, 36} in
    v1) — enforced here, PRE-create, on day one rather than after a review (RM-1's fold, inherited).
    """
    # --- Pre-create prerequisite gate (raise BEFORE create_run => zero run/result/run-audit) ---
    if not code_version:
        raise SharpeInputError("code_version is required (FW-RUN/TR-15)")
    if not environment_id:
        raise SharpeInputError("environment_id is required (FW-RUN/TR-15)")
    if actor is None or not actor.actor_id:
        raise SharpeInputError("initiator is required (FW-RUN/TR-15)")
    if not model_version_id:
        raise SharpeInputError("model_version_id is required (CTRL-003 inventory-before-use)")
    if not window_months:
        raise SharpeInputError("at least one window is required")
    if len(set(window_months)) != len(window_months):
        raise SharpeInputError(f"duplicate windows {window_months} — refused")
    outside = sorted(set(window_months) - set(SHARPE_WINDOWS))
    if outside:
        raise SharpeInputError(
            f"window(s) {outside} are outside the registered domain {list(SHARPE_WINDOWS)} for "
            "this model version — a governed run may only use a declared window"
        )

    assert_model_version_of(
        session,
        str(model_version_id),
        tenant_id=acting_tenant,
        expected_model_code=SHARPE_MODEL_CODE,
    )

    snapshot = resolve_snapshot(session, snapshot_id, acting_tenant=acting_tenant)
    if snapshot.purpose != PURPOSE_SHARPE_INPUT:
        raise SharpeInputError(
            f"snapshot {snapshot_id} has purpose {snapshot.purpose!r}, expected "
            f"{PURPOSE_SHARPE_INPUT!r}"
        )

    parsed = _adjudicate_pins(
        *_parse_pins(
            list(list_components(session, snapshot_id=snapshot.id, acting_tenant=acting_tenant))
        )
    )
    # Re-resolve EVERY id out of the PINNED content before any of them is stamped into a hard FK
    # (P3-5: PG FK checks bypass RLS, so the DB alone would durably admit a foreign tenant's run,
    # book or benchmark head). The risk-free head is included deliberately — it is the newest of the
    # three hard FKs and the one a hand-minted snapshot is most likely to point across a tenant.
    _resolve_return_run(session, parsed.portfolio_return_run_id, acting_tenant=acting_tenant)
    assert_portfolio_in_tenant(
        session, parsed.portfolio_id, acting_tenant=acting_tenant, error=SharpeInputError
    )
    _assert_benchmark_in_tenant(session, parsed.risk_free_benchmark_id, acting_tenant=acting_tenant)

    def _compute(run: CalculationRun) -> tuple[list[SharpeRatioResult], list[str]]:
        gaps: list[str] = []
        rows: list[SharpeRatioResult] = []

        def _row(
            metric_type: str,
            window: int,
            period_start: dt_date,
            period_end: dt_date,
            *,
            value: Decimal | None,
            basis: str,
            n_observations: int | None,
            suppression_reason: str | None = None,
        ) -> SharpeRatioResult:
            return SharpeRatioResult(
                tenant_id=str(acting_tenant),
                calculation_run_id=run.run_id,
                input_snapshot_id=snapshot.id,
                model_version_id=str(model_version_id),
                portfolio_id=parsed.portfolio_id,
                portfolio_return_run_id=parsed.portfolio_return_run_id,
                risk_free_benchmark_id=parsed.risk_free_benchmark_id,
                rf_return_basis=parsed.rf_return_basis,
                metric_type=metric_type,
                window_months=window,
                period_start=period_start,
                period_end=period_end,
                metric_value=value,
                suppressed=value is None,
                suppression_reason=suppression_reason,
                annualization_basis=basis,
                sampling_frequency=SAMPLING_FREQUENCY_MONTHLY,
                n_observations=n_observations,
            )

        span_start, span_end = parsed.opening_boundary, parsed.excess[-1].month_end
        # BOTH metrics at EVERY window — including W = 12. RM-1 suppresses its redundant annualized
        # RETURN at 12 months because the geometric exponent is exactly 1 there; sqrt(12) x SR is
        # never SR, so that rationale does not transfer and is deliberately not imported.
        pair = (
            (METRIC_TYPE_SHARPE_RATIO, ANNUALIZATION_NONE),
            (METRIC_TYPE_SHARPE_RATIO_ANN, ANNUALIZATION_SQRT_12),
        )

        for window in sorted(window_months):
            if len(parsed.excess) < window:
                reason = (
                    f"only {len(parsed.excess)} monthly observations are available for a "
                    f"{window}-month window"
                )
                for metric, basis in pair:
                    rows.append(
                        _row(
                            metric,
                            window,
                            span_start,
                            span_end,
                            value=None,
                            basis=basis,
                            # NULL because there IS no sample — distinguishable on the read surface
                            # from a zero-dispersion suppression, which carries its n.
                            n_observations=None,
                            suppression_reason=reason,
                        )
                    )
                continue

            try:
                windows = sharpe_windows(
                    parsed.excess, window, opening_boundary=parsed.opening_boundary
                )
            except (SharpeKernelError, RollingKernelError, ReturnKernelError, StatsKernelError):
                # ALL FOUR independent ValueError subclasses, for RM-1's reason: catching only the
                # sibling left the extreme band escaping AFTER create_run, giving neither declared
                # outcome — not a pre-create refusal, not a committed FAILED run, but an uncaught
                # raise with the run stranded in RUNNING. Here the reachable one is
                # StatsKernelError, raised by `quantize_result` when |SR x sqrt(12)| leaves the 12dp
                # envelope; the others are carried because the call graph can reach them.
                gaps.append(f"magnitude-out-of-range:window={window}")
                return [], gaps

            for evaluated in windows:
                emitted: list[tuple[str, Decimal | None, str]] = [
                    (METRIC_TYPE_SHARPE_RATIO, evaluated.sharpe, ANNUALIZATION_NONE),
                    (
                        METRIC_TYPE_SHARPE_RATIO_ANN,
                        evaluated.annualized_sharpe,
                        ANNUALIZATION_SQRT_12,
                    ),
                ]
                for metric, value, basis in emitted:
                    if value is not None and abs(value) >= _MAX_RESULT_ABS:
                        gaps.append(f"magnitude-out-of-range:{metric}:{value:E}")
                        return [], gaps
                    rows.append(
                        _row(
                            metric,
                            window,
                            evaluated.period_start,
                            evaluated.period_end,
                            value=value,
                            basis=basis,
                            # A zero-dispersion suppression KEEPS its observation count: the sample
                            # exists, the ratio does not. That is a different state from "the window
                            # could not be filled", and the read surface can tell them apart.
                            n_observations=evaluated.n_observations,
                            suppression_reason=(
                                None if value is not None else ZERO_DISPERSION_REASON
                            ),
                        )
                    )
        return rows, gaps

    outcome = execute_governed_run(
        session,
        acting_tenant=str(acting_tenant),
        actor_id=actor.actor_id,
        actor_type=actor.actor_type,
        run_type=RUN_TYPE_SHARPE,
        snapshot_id=snapshot.id,
        model_version_id=str(model_version_id),
        code_version=code_version,
        environment_id=environment_id,
        rule_code=_COMPLETENESS_RULE_CODE,
        rule_name=_COMPLETENESS_RULE_NAME,
        rule_target_entity_type="calculation_run",
        result_entity_type="sharpe_ratio_result",
        compute=_compute,
        format_reason=_format_reason,
        scope_portfolio_id=parsed.portfolio_id,
    )
    return SharpeRunResult(
        run=outcome.run,
        status=outcome.status,
        rows=list(outcome.rows),
        failure_reason=outcome.failure_reason,
    )


def _assert_benchmark_in_tenant(session: Session, benchmark_id: str, *, acting_tenant: str) -> None:
    """Fail closed if the pinned risk-free head is not visible in the acting tenant (P3-5).

    A models-only read rather than ``resolve_benchmark``: the ``marketdata`` resolver raises its own
    ``BenchmarkNotVisible`` (a 404), and a pinned-content prerequisite is a 422 refusal of the
    REQUEST, not a missing resource the caller asked for.
    """
    from irp_shared.marketdata.models import Benchmark  # models-only (fence-safe)

    row = session.execute(
        select(Benchmark).where(
            Benchmark.id == str(benchmark_id), Benchmark.tenant_id == str(acting_tenant)
        )
    ).scalar_one_or_none()
    if row is None:
        raise SharpeInputError(
            f"the pinned risk-free benchmark {benchmark_id} is not visible in the acting tenant "
            "— refused"
        )


# ------------------------------------------------------------------------- rule-7 reads (SR-1) ---
def list_sharpe_ratios(
    session: Session,
    *,
    acting_tenant: str,
    portfolio_id: str | None = None,
    metric_type: str | None = None,
    window_months: int | None = None,
    as_of: datetime | None = None,
) -> list[SharpeRatioResult]:
    """Entity/time-centric read across COMPLETED Sharpe runs (the AD-019 ``calc/reads.py`` seam —
    governed-result reads never hand-roll a join to ``calculation_run``).

    Carries RM-1's ``metric_type``/``window_months`` filters for RM-1's reason: this family also
    emits one statistic under two transforms at two windows, so an unfiltered read interleaves four
    row kinds and the likeliest misuse is to read that as one series. The disambiguation key is
    ``(metric_type, window_months, annualization_basis)``.

    Silent-empty on an unknown/foreign id (the platform's entity-filter precedent).
    """
    return list_governed_results(
        session,
        SharpeRatioResult,
        acting_tenant=acting_tenant,
        filters=(
            (SharpeRatioResult.portfolio_id, portfolio_id),
            (SharpeRatioResult.metric_type, metric_type),
            (SharpeRatioResult.window_months, window_months),
        ),
        run_type=RUN_TYPE_SHARPE,
        as_of=as_of,
        order_by=(
            SharpeRatioResult.window_months,
            SharpeRatioResult.metric_type,
            SharpeRatioResult.period_end,
        ),
    )


def latest_sharpe_ratio(
    session: Session,
    *,
    acting_tenant: str,
    portfolio_id: str,
    metric_type: str | None = None,
    window_months: int | None = None,
    as_of: datetime | None = None,
) -> list[SharpeRatioResult]:
    """The newest COMPLETED Sharpe run's rows for a book (empty when none).

    ONE run's rows, never a merge across runs: two runs can carry different window sets AND
    different risk-free series, so a merged series would silently mix both the estimator domain and
    the thing the excess is measured against.
    """
    return latest_run_rows(
        list_sharpe_ratios(
            session,
            acting_tenant=acting_tenant,
            portfolio_id=portfolio_id,
            metric_type=metric_type,
            window_months=window_months,
            as_of=as_of,
        )
    )


def list_sharpe_ratio_rows(
    session: Session, *, run_id: str, acting_tenant: str
) -> list[SharpeRatioResult]:
    """Every row of ONE Sharpe run (the run-centric read), deterministically ordered."""
    return list(
        session.execute(
            select(SharpeRatioResult)
            .where(
                SharpeRatioResult.calculation_run_id == str(run_id),
                SharpeRatioResult.tenant_id == str(acting_tenant),
            )
            .order_by(
                SharpeRatioResult.window_months,
                SharpeRatioResult.metric_type,
                SharpeRatioResult.period_end,
            )
        ).scalars()
    )


def resolve_sharpe_run(session: Session, run_id: str, *, acting_tenant: str) -> CalculationRun:
    """Resolve a Sharpe run by id with an EXPLICIT tenant predicate (fail-closed). A committed
    FAILED run is a real resource and resolves — it is durable refusal evidence, not a 404."""
    run = session.execute(
        select(CalculationRun).where(
            CalculationRun.run_id == str(run_id),
            CalculationRun.tenant_id == str(acting_tenant),
            CalculationRun.run_type == RUN_TYPE_SHARPE,
        )
    ).scalar_one_or_none()
    if run is None:
        raise SharpeRunNotVisible(f"sharpe run {run_id} is not visible")
    return run


def resolve_sharpe_ratio(
    session: Session, result_id: str, *, acting_tenant: str
) -> SharpeRatioResult:
    """Resolve one ``sharpe_ratio_result`` row by id with an EXPLICIT tenant predicate."""
    row = session.execute(
        select(SharpeRatioResult).where(
            SharpeRatioResult.id == str(result_id),
            SharpeRatioResult.tenant_id == str(acting_tenant),
        )
    ).scalar_one_or_none()
    if row is None:
        raise SharpeNotVisible(f"sharpe result {result_id} is not visible")
    return row
