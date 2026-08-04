"""RM-1 rolling-risk binder (ENT-064 — the 21st governed number).

Consumes ONE governed PM-1 ``PORTFOLIO_RETURN`` run, relinks its ``DIETZ_PERIOD`` sub-periods to a
calendar-month grid, and emits trailing-window statistics: rolling return (raw + annualized),
rolling volatility (raw + annualized), and maximum drawdown.

**RUN-BOUND + SNAPSHOT-GATED + MODEL-BOUND** (AD-014 / FW-RUN / TR-15 / CTRL-003). Computes ONLY
from pinned content — a later re-run of the upstream PM-1 run cannot move a historical rolling
number (TR-09).

**Failure model.** A pre-create refusal (missing/invalid prerequisite, an unregistered or wrong
``model_version``, a misaligned month grid, a month at or below -100%) raises and rolls the WHOLE
unit back — ZERO run. A post-create FAILED run (a magnitude past the ``Numeric(20,12)`` envelope) is
COMMITTED with zero rows, the governed-run precedent.

**Preconditions live HERE, not in the kernel** (OD-RM-1-M). The kernel's raises are defense-in-depth
and stay structurally unreachable through the governed path: this binder adjudicates the pinned
content first, so a caller never sees a kernel error where a governed refusal was owed.

**Suppression is a first-class emitted state** (OD-RM-1-I). A window the series cannot fill emits a
governed row with a NULL value, ``suppressed=True`` and a reason — never a stuffed zero, because
``0`` is a LEGITIMATE value for all three metrics and a consumer would read "not computable" as "no
drawdown, excellent". Granularity is one suppressed row per ``(metric_type, window_months)`` per run
(per-evaluation-point would collide on the grain at n=12 and is the worse reading of GIPS 4.C.36).
"""

from __future__ import annotations

import json
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
from irp_shared.model.service import assert_model_version_of
from irp_shared.perf.bootstrap import (
    MONTH_END_BUSINESS_CONVENTION,
    ROLLING_RISK_MODEL_CODE,
    ROLLING_RISK_WINDOWS,
    declared_month_end_parameters,
)
from irp_shared.perf.events import (
    RUN_TYPE_PORTFOLIO_RETURN,
    RUN_TYPE_ROLLING_RISK,
    RollingRiskActor,
)
from irp_shared.perf.holiday_binding import assert_boundaries_covered, parse_pinned_holidays
from irp_shared.perf.models import (
    ANNUALIZATION_GEOMETRIC_12,
    ANNUALIZATION_NONE,
    ANNUALIZATION_SQRT_12,
    METRIC_TYPE_MAX_DRAWDOWN,
    METRIC_TYPE_ROLLING_RETURN,
    METRIC_TYPE_ROLLING_RETURN_ANN,
    METRIC_TYPE_ROLLING_VOLATILITY,
    METRIC_TYPE_ROLLING_VOLATILITY_ANN,
    SAMPLING_FREQUENCY_MONTHLY,
    RollingRiskResult,
)
from irp_shared.perf.return_kernel import ReturnKernelError
from irp_shared.perf.rolling_kernel import (
    MONTHS_PER_YEAR,
    MonthlyReturn,
    RollingKernelError,
    SubPeriod,
    assert_above_total_loss,
    assert_month_aligned,
    relink_to_months,
    rolling_windows,
)
from irp_shared.perf.stats_kernel import StatsKernelError
from irp_shared.portfolio.guards import assert_portfolio_in_tenant
from irp_shared.snapshot import (
    COMPONENT_KIND_HOLIDAY_CALENDAR,
    COMPONENT_KIND_PORTFOLIO_RETURN,
    PURPOSE_ROLLING_RISK_INPUT,
    list_components,
    resolve_snapshot,
)

#: PM-1's metric vocabulary, kept as a FENCE-KEPT LOCAL copy (the P3-8/PM-1 precedent — ``perf``
#: modules do not reach across for a string). Pinned equal to the source in the test suite.
_DIETZ_PERIOD = "DIETZ_PERIOD"

#: The DQ rule this binder's completeness gate registers under.
_COMPLETENESS_RULE_CODE = "perf.rolling_risk.completeness"
_COMPLETENESS_RULE_NAME = "Rolling-risk input completeness"

#: The result-scale envelope. The magnitude gate applies to the EMITTED (post-annualization) value:
#: annualizing can amplify, so gating the pre-transform number would let an out-of-range row reach
#: the flush — which happens OUTSIDE the caught DataQualityError and would surface as a 500 with the
#: run orphaned in RUNNING (the P3-8 review fold, inherited deliberately).
_MAX_RESULT_ABS = Decimal("1E7")


class RollingRiskInputError(Exception):
    """A pre-create refusal: an ill-formed or ungovernable rolling-risk input."""


class RollingRiskNotVisible(Exception):
    """A rolling-risk row is not visible in the acting tenant."""


class RollingRiskRunNotVisible(Exception):
    """A rolling-risk run is not visible in the acting tenant."""


@dataclass(frozen=True)
class RollingRiskRunResult:
    run: CalculationRun
    status: str
    rows: list[RollingRiskResult]
    failure_reason: str | None = None


@dataclass(frozen=True)
class _ParsedInput:
    """The adjudicated pinned content — everything the compute needs, all of it from pins."""

    portfolio_return_run_id: str
    portfolio_id: str
    months: list[MonthlyReturn]
    opening_boundary: dt_date


def _parse_pins(components: list[Any]) -> list[dict[str, Any]]:
    """Parse the pinned ``captured_content`` into raw portfolio-return dicts (PURE — no live read).

    The existing ``portfolio_return_content`` serializer is sufficient with NO new pin-key surface:
    it carries ``metric_type``, ``period_start``, ``period_end`` and ``return_value``, which is
    everything the month partition, the relink, the volatility, the rolling return AND the
    compounded-index drawdown need. That also means no historical pin drifts.
    """
    rows: list[dict[str, Any]] = []
    for component in components:
        if component.component_kind == COMPONENT_KIND_PORTFOLIO_RETURN:
            rows.append(json.loads(component.captured_content))
    return rows


def _as_date(value: Any) -> dt_date:
    return value if isinstance(value, dt_date) else dt_date.fromisoformat(str(value))


def _adjudicate_pins(
    raw: list[dict[str, Any]],
    holidays: frozenset[dt_date] = frozenset(),
    holidays_complete_through: dt_date | None = None,
) -> _ParsedInput:
    """PRE-CREATE adjudication of the full pinned input. Raises :class:`RollingRiskInputError`.

    Order matters: structural checks first (is this even a return run?), then the v2 coverage
    gate (CAL-1b — a span beyond the pinned calendar's DECLARED horizon refuses before alignment
    is even asked), then the month grid, then the economic precondition. ``holidays`` is empty
    for v1 (byte-identical acceptance) and the PINNED set for v2.
    """
    if not raw:
        raise RollingRiskInputError(
            "the snapshot pins no PORTFOLIO_RETURN rows — not a rolling-risk input"
        )
    dietz = [r for r in raw if r["metric_type"] == _DIETZ_PERIOD]
    if not dietz:
        raise RollingRiskInputError("the pinned return run has no DIETZ_PERIOD sub-periods")

    run_ids = {str(r["calculation_run_id"]).lower() for r in raw}
    portfolio_ids = {str(r["portfolio_id"]) for r in raw}
    if len(run_ids) != 1:
        raise RollingRiskInputError("the pinned return rows span multiple runs — refused")
    if len(portfolio_ids) != 1:
        raise RollingRiskInputError(
            f"the pinned return rows span {len(portfolio_ids)} portfolios — refused"
        )

    try:
        sub_periods = sorted(
            (
                SubPeriod(
                    period_start=_as_date(r["period_start"]),
                    period_end=_as_date(r["period_end"]),
                    # parse_strict_decimal, not a bare Decimal() — the Wave-13 close fold, and the
                    # SR-1 sibling's shipped comment names the exact hazard: Decimal("NaN") parses
                    # CLEANLY (no ArithmeticError), so a hand-built snapshot carrying "NaN" sailed
                    # past the except envelope below and detonated LATER, in
                    # assert_above_total_loss's ordering comparison, as a decimal.InvalidOperation
                    # that nothing caught — a raw 500 where this binder owes a governed 422, and a
                    # convention split from SR-1 over the SAME pin shape in the SAME wave.
                    return_value=parse_strict_decimal(
                        r["return_value"], error=RollingRiskInputError, field="return_value"
                    ),
                )
                for r in dietz
            ),
            key=lambda p: p.period_start,
        )
    except (KeyError, ValueError, ArithmeticError, TypeError) as exc:
        # Malformed pinned content is a pre-create REFUSAL, not a 500. The generic `build_snapshot`
        # accepts this purpose (it is an allow-list member), so a hand-built snapshot can carry
        # components whose captured_content lacks a key or holds a non-numeric return — and those
        # reached the bare subscript/Decimal() as a raw KeyError/InvalidOperation (4-finder review).
        # (parse_strict_decimal's own raise is RollingRiskInputError, which is not in this tuple,
        # so its precise per-field message propagates rather than being double-wrapped.)
        raise RollingRiskInputError(
            f"a pinned PORTFOLIO_RETURN component is malformed and cannot be read: {exc}"
        ) from exc

    # The boundary grid: d_0 is the first sub-period's START (the close of the month BEFORE the
    # first measured month), then every sub-period end.
    boundaries = [sub_periods[0].period_start] + [p.period_end for p in sub_periods]
    if holidays_complete_through is not None:
        # BOTH coverage sides, shared (holiday_binding.assert_boundaries_covered): the end side is
        # OQ-CAL-1-4; the start side is the Wave-14 close's HIGH — the first shipment checked only
        # boundaries[-1], so a window opening before the dataset's first covered year rolled
        # weekend-only, silently.
        assert_boundaries_covered(
            boundaries,
            holidays=holidays,
            holidays_complete_through=holidays_complete_through,
            error=RollingRiskInputError,
        )
    try:
        assert_month_aligned(boundaries, holidays)
        months = relink_to_months(sub_periods)
        assert_above_total_loss(months)
    except ValueError as exc:
        # Converted at the binder boundary: a caller owed a governed refusal must not receive a
        # kernel error. ``RollingKernelError`` subclasses ValueError, and the WIDER catch also
        # converts calmath's exhausted-month raise (a hand-built pin whose dates blanket a
        # boundary month reached it as a raw 500 — the CAL-1b review's HIGH). The kernel's own
        # raises stay defense-in-depth.
        raise RollingRiskInputError(str(exc)) from exc

    return _ParsedInput(
        portfolio_return_run_id=next(iter(run_ids)),
        portfolio_id=next(iter(portfolio_ids)),
        months=months,
        opening_boundary=boundaries[0],
    )


def _resolve_return_run(session: Session, run_id: str, *, acting_tenant: str) -> CalculationRun:
    """Re-resolve the consumed PORTFOLIO_RETURN run under the acting tenant (+ run_type +
    COMPLETED) BEFORE its id is stamped into the ``portfolio_return_run_id`` hard FK — PG FK checks
    bypass RLS, so a hand-minted snapshot could otherwise reference a FOREIGN tenant's run (P3-5).
    """
    return resolve_completed_run_of_type(
        session,
        run_id,
        acting_tenant=acting_tenant,
        run_type=RUN_TYPE_PORTFOLIO_RETURN,
        label="portfolio-return",
        error=RollingRiskInputError,
    )


def _format_reason(gate: Exception, gaps: list[str]) -> str:
    return f"rolling-risk completeness failed: {'; '.join(gaps) or gate}"


def run_rolling_risk(
    session: Session,
    *,
    acting_tenant: str,
    actor: RollingRiskActor,
    code_version: str,
    environment_id: str,
    model_version_id: str,
    window_months: tuple[int, ...],
    snapshot_id: str,
) -> RollingRiskRunResult:
    """Run a governed rolling-risk calculation over a pinned ``ROLLING_RISK_INPUT`` snapshot.

    ``window_months`` comes from the REGISTERED model version's declared parameters ({12, 36} in
    v1). **That registered domain — not the kernel's guard — is where GIPS 2.A.12 is actually
    enforced**: no governed caller can request a window below 12 months, so the kernel check is
    honest defense-in-depth rather than "the invariant".
    """
    # --- Pre-create prerequisite gate (raise BEFORE create_run => zero run/result/run-audit) ---
    if not code_version:
        raise RollingRiskInputError("code_version is required (FW-RUN/TR-15)")
    if not environment_id:
        raise RollingRiskInputError("environment_id is required (FW-RUN/TR-15)")
    if actor is None or not actor.actor_id:
        raise RollingRiskInputError("initiator is required (FW-RUN/TR-15)")
    if not model_version_id:
        raise RollingRiskInputError("model_version_id is required (CTRL-003 inventory-before-use)")
    if not window_months:
        raise RollingRiskInputError("at least one window is required")
    if len(set(window_months)) != len(window_months):
        raise RollingRiskInputError(f"duplicate windows {window_months} — refused")
    # THE PARAMETER DOMAIN, actually enforced (4-finder review). The record calls {12, 36} "a
    # registered model parameter" and names it as where GIPS 2.A.12 is enforced — but the perf
    # registrar is code_version-only and has no parameter mechanism, so until this check the domain
    # was a Python constant plus prose. Two things got through: `window_months=(24,)` minted a
    # COMPLETED governed run outside the ratified domain under a v1 model whose assumptions present
    # that domain as the compliance point; and `(6,)` produced a COMMITTED FAILED run whose
    # persisted reason was mislabelled `magnitude-out-of-range:` for what is an ill-formed REQUEST.
    # Both are pre-create refusals now. A registrar-held parameter set is the recorded v2.
    outside = sorted(set(window_months) - set(ROLLING_RISK_WINDOWS))
    if outside:
        raise RollingRiskInputError(
            f"window(s) {outside} are outside the registered domain {list(ROLLING_RISK_WINDOWS)} "
            "for this model version — a governed run may only use a declared window"
        )

    version = assert_model_version_of(
        session,
        str(model_version_id),
        tenant_id=acting_tenant,
        expected_model_code=ROLLING_RISK_MODEL_CODE,
    )
    # CAL-1b (OQ-CAL-1-2): the declared month-end convention — parsed from the version's
    # assumption LITERALS (absent => the WEEKEND v1 grandfather; ambiguous/stray => fail-closed).
    params = declared_month_end_parameters(session, version, model_code=ROLLING_RISK_MODEL_CODE)

    snapshot = resolve_snapshot(session, snapshot_id, acting_tenant=acting_tenant)
    if snapshot.purpose != PURPOSE_ROLLING_RISK_INPUT:
        raise RollingRiskInputError(
            f"snapshot {snapshot_id} has purpose {snapshot.purpose!r}, expected "
            f"{PURPOSE_ROLLING_RISK_INPUT!r}"
        )

    components = list(
        list_components(session, snapshot_id=snapshot.id, acting_tenant=acting_tenant)
    )
    holidays: frozenset[dt_date] = frozenset()
    coverage: dt_date | None = None
    if params.convention != MONTH_END_BUSINESS_CONVENTION and any(
        c.component_kind == COMPONENT_KIND_HOLIDAY_CALENDAR for c in components
    ):
        # The unconsumed-pin refusal (the CAL-1b review's MED, symmetric with the no-pin-under-v2
        # arm and the rf leg's every-pin-consumed principle): a WEEKEND-convention run over a
        # snapshot PINNING a holiday calendar would bind provenance claiming an input the run
        # never read.
        raise RollingRiskInputError(
            "the snapshot pins a HOLIDAY_CALENDAR component but this model version declares the "
            "WEEKEND (v1) convention — an unconsumed pin is refused; rebuild the snapshot "
            "without holiday_calendar_code or run under a v2 version"
        )
    if params.convention == MONTH_END_BUSINESS_CONVENTION:
        assert params.holiday_calendar is not None  # the gate refused a BUSINESS row without it
        holidays, coverage = parse_pinned_holidays(
            components,
            declared_code=params.holiday_calendar,
            error=RollingRiskInputError,
        )
    parsed = _adjudicate_pins(
        _parse_pins(components), holidays=holidays, holidays_complete_through=coverage
    )
    # Re-resolve BOTH ids out of the PINNED content before either is stamped into a hard FK (P3-5:
    # PG FK checks bypass RLS, so the DB alone would durably admit a foreign tenant's run/book).
    _resolve_return_run(session, parsed.portfolio_return_run_id, acting_tenant=acting_tenant)
    assert_portfolio_in_tenant(
        session, parsed.portfolio_id, acting_tenant=acting_tenant, error=RollingRiskInputError
    )

    def _compute(run: CalculationRun) -> tuple[list[RollingRiskResult], list[str]]:
        gaps: list[str] = []
        rows: list[RollingRiskResult] = []

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
        ) -> RollingRiskResult:
            return RollingRiskResult(
                tenant_id=str(acting_tenant),
                calculation_run_id=run.run_id,
                input_snapshot_id=snapshot.id,
                model_version_id=str(model_version_id),
                portfolio_id=parsed.portfolio_id,
                portfolio_return_run_id=parsed.portfolio_return_run_id,
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

        span_start, span_end = parsed.opening_boundary, parsed.months[-1].month_end
        for window in sorted(window_months):
            if len(parsed.months) < window:
                # SUPPRESSED, not skipped and not zero: GIPS 4.C.36 wants the absence disclosed, and
                # a stuffed 0 would be indistinguishable from a legitimate zero. One row per
                # (metric, window) per run — per-point would collide on the grain at n=12.
                reason = (
                    f"only {len(parsed.months)} monthly observations are available for a "
                    f"{window}-month window"
                )
                suppressed_metrics = [
                    (METRIC_TYPE_ROLLING_RETURN, ANNUALIZATION_NONE),
                    (METRIC_TYPE_ROLLING_VOLATILITY, ANNUALIZATION_NONE),
                    (METRIC_TYPE_ROLLING_VOLATILITY_ANN, ANNUALIZATION_SQRT_12),
                    (METRIC_TYPE_MAX_DRAWDOWN, ANNUALIZATION_NONE),
                ]
                # The annualized RETURN is emitted only above 12 months (at 12 it is definitionally
                # the cumulative return), so it must be SUPPRESSED only where it would otherwise be
                # emitted. Omitting it at W > 12 left `(ROLLING_RETURN_ANN, 36, GEOMETRIC_12)` with
                # no row at all — an UNDISCLOSED absence, which is the precise state the suppression
                # design exists to prevent (4-finder review; two finders, independently).
                if window > MONTHS_PER_YEAR:
                    suppressed_metrics.append(
                        (METRIC_TYPE_ROLLING_RETURN_ANN, ANNUALIZATION_GEOMETRIC_12)
                    )
                for metric, basis in suppressed_metrics:
                    rows.append(
                        _row(
                            metric,
                            window,
                            span_start,
                            span_end,
                            value=None,
                            basis=basis,
                            n_observations=None,
                            suppression_reason=reason,
                        )
                    )
                continue

            try:
                windows = rolling_windows(
                    parsed.months, window, opening_boundary=parsed.opening_boundary
                )
            except (RollingKernelError, ReturnKernelError, StatsKernelError) as exc:
                # ALL THREE classes, not just the sibling. `rolling_windows` calls into
                # `link_periods` (raises ReturnKernelError) and `sample_stdev`/`quantize_result`
                # (raise StatsKernelError), and the three are INDEPENDENT ValueError subclasses —
                # so catching only RollingKernelError left the extreme band escaping AFTER
                # create_run, giving neither declared outcome: not a pre-create refusal, not a
                # committed FAILED run, but an uncaught raise with the run stranded in RUNNING.
                # Executed: twelve pinned sub-periods at return_value = 10000 (each below PM-1's
                # own 1E7 emit gate) reached this line as a bare ReturnKernelError.
                gaps.append(f"magnitude-out-of-range:{exc}")
                return [], gaps

            for evaluated in windows:
                emitted: list[tuple[str, Decimal | None, str]] = [
                    (METRIC_TYPE_ROLLING_RETURN, evaluated.cumulative_return, ANNUALIZATION_NONE),
                    (METRIC_TYPE_ROLLING_VOLATILITY, evaluated.volatility, ANNUALIZATION_NONE),
                    (
                        METRIC_TYPE_ROLLING_VOLATILITY_ANN,
                        evaluated.annualized_volatility,
                        ANNUALIZATION_SQRT_12,
                    ),
                    (METRIC_TYPE_MAX_DRAWDOWN, evaluated.max_drawdown, ANNUALIZATION_NONE),
                ]
                # At W == 12 the geometric exponent is exactly 1, so the annualized return is
                # DEFINITIONALLY the cumulative return; emitting both would ship two governed
                # numbers that can never differ. The kernel reports None and we omit the row.
                if evaluated.annualized_return is not None:
                    emitted.append(
                        (
                            METRIC_TYPE_ROLLING_RETURN_ANN,
                            evaluated.annualized_return,
                            ANNUALIZATION_GEOMETRIC_12,
                        )
                    )
                for metric, value, basis in emitted:
                    # The gate is on the EMITTED value — annualizing amplifies, so gating the
                    # pre-transform number would let an out-of-range row reach the flush, which is
                    # OUTSIDE the caught DataQualityError (a 500 with the run stuck in RUNNING).
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
                            n_observations=evaluated.n_observations,
                        )
                    )
        return rows, gaps

    outcome = execute_governed_run(
        session,
        acting_tenant=str(acting_tenant),
        actor_id=actor.actor_id,
        actor_type=actor.actor_type,
        run_type=RUN_TYPE_ROLLING_RISK,
        snapshot_id=snapshot.id,
        model_version_id=str(model_version_id),
        code_version=code_version,
        environment_id=environment_id,
        rule_code=_COMPLETENESS_RULE_CODE,
        rule_name=_COMPLETENESS_RULE_NAME,
        rule_target_entity_type="calculation_run",
        result_entity_type="rolling_risk_result",
        compute=_compute,
        format_reason=_format_reason,
        scope_portfolio_id=parsed.portfolio_id,
    )
    return RollingRiskRunResult(
        run=outcome.run,
        status=outcome.status,
        rows=list(outcome.rows),
        failure_reason=outcome.failure_reason,
    )


# ------------------------------------------------------------------------- rule-7 reads (RM-1) ---
def list_rolling_risks(
    session: Session,
    *,
    acting_tenant: str,
    portfolio_id: str | None = None,
    metric_type: str | None = None,
    window_months: int | None = None,
    as_of: datetime | None = None,
) -> list[RollingRiskResult]:
    """Entity/time-centric read across COMPLETED rolling-risk runs (the AD-019 ``calc/reads.py``
    seam — governed-result reads never hand-roll a join to ``calculation_run``).

    **``metric_type`` and ``window_months`` filters are offered deliberately, breaking a family
    precedent on its merits** (OD-RM-1-K). No perf read has ever taken a ``metric_type`` filter —
    but no perf family has ever emitted the SAME statistic under two transforms at two windows
    either. Without them a caller asking "the rolling volatility" receives four metric types across
    two windows interleaved, and the most likely way to misread this surface is to treat that as one
    series. The disambiguation key is ``(metric_type, window_months, annualization_basis)``; the
    third is always stamped on the row, and the first two are filterable here.

    Silent-empty on an unknown/foreign id (the platform's entity-filter precedent).
    """
    return list_governed_results(
        session,
        RollingRiskResult,
        acting_tenant=acting_tenant,
        filters=(
            (RollingRiskResult.portfolio_id, portfolio_id),
            (RollingRiskResult.metric_type, metric_type),
            (RollingRiskResult.window_months, window_months),
        ),
        run_type=RUN_TYPE_ROLLING_RISK,
        as_of=as_of,
        order_by=(
            RollingRiskResult.window_months,
            RollingRiskResult.metric_type,
            RollingRiskResult.period_end,
        ),
    )


def latest_rolling_risk(
    session: Session,
    *,
    acting_tenant: str,
    portfolio_id: str,
    metric_type: str | None = None,
    window_months: int | None = None,
    as_of: datetime | None = None,
) -> list[RollingRiskResult]:
    """The newest COMPLETED rolling-risk run's rows for a book (empty when none).

    ONE run's rows, never a merge across runs — cross-run aggregation is a CONSUMER ERROR, and it
    would be a particularly bad one here: two runs of different model versions can carry different
    window sets, so a merged series would silently mix estimator domains.
    """
    return latest_run_rows(
        list_rolling_risks(
            session,
            acting_tenant=acting_tenant,
            portfolio_id=portfolio_id,
            metric_type=metric_type,
            window_months=window_months,
            as_of=as_of,
        )
    )


def list_rolling_risk_rows(
    session: Session, *, run_id: str, acting_tenant: str
) -> list[RollingRiskResult]:
    """Every row of ONE rolling-risk run (the run-centric read), deterministically ordered."""
    return list(
        session.execute(
            select(RollingRiskResult)
            .where(
                RollingRiskResult.calculation_run_id == str(run_id),
                RollingRiskResult.tenant_id == str(acting_tenant),
            )
            .order_by(
                RollingRiskResult.window_months,
                RollingRiskResult.metric_type,
                RollingRiskResult.period_end,
            )
        ).scalars()
    )


def resolve_rolling_risk_run(
    session: Session, run_id: str, *, acting_tenant: str
) -> CalculationRun:
    """Resolve a rolling-risk run by id with an EXPLICIT tenant predicate (fail-closed). A committed
    FAILED run is a real resource and resolves — it is durable refusal evidence, not a 404."""
    run = session.execute(
        select(CalculationRun).where(
            CalculationRun.run_id == str(run_id),
            CalculationRun.tenant_id == str(acting_tenant),
            CalculationRun.run_type == RUN_TYPE_ROLLING_RISK,
        )
    ).scalar_one_or_none()
    if run is None:
        raise RollingRiskRunNotVisible(f"rolling-risk run {run_id} is not visible")
    return run


def resolve_rolling_risk(
    session: Session, result_id: str, *, acting_tenant: str
) -> RollingRiskResult:
    """Resolve one ``rolling_risk_result`` row by id with an EXPLICIT tenant predicate."""
    row = session.execute(
        select(RollingRiskResult).where(
            RollingRiskResult.id == str(result_id),
            RollingRiskResult.tenant_id == str(acting_tenant),
        )
    ).scalar_one_or_none()
    if row is None:
        raise RollingRiskNotVisible(f"rolling-risk result {result_id} is not visible")
    return row
