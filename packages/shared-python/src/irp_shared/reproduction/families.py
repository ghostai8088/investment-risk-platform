"""The sixteen adapters REPRO-1 deferred (REPRO-2, ratified OQ-REP2-4).

REPRO-1 shipped three reproducers and enumerated eighteen families it could not check, each with a
reason. Sixteen of those reasons said "not yet adapted" — the family HAS a consume path and only
wanted its key/field declaration. This module is those sixteen, moving the coverage census from
3+18 to 19+2. The two that stay out are structural and keep their triggers: CONCENTRATION (no
snapshot consume path at all) and LIQUIDITY (a wall clock inside a shipped governed refusal, which
is a model-identity question rather than a reproduction one).

**Three of the sixteen "not yet adapted" reasons were FACTUALLY WRONG, and following them would
have produced adapters that refuse every run.** They are corrected in place at the registry, and
recorded here because the class matters more than the instances — the same class as REPRO-1's
``_WHY_RENDER_INPUT``, a reason that reads well and is false about the code it describes:

* **BENCHMARK_RELATIVE** — "needs return_basis + benchmark_id read back off the stored rows". The
  binder REFUSES those arguments alongside ``snapshot_id`` ("ambiguous input"), and adjudicates
  both out of the pinned components itself. An adapter written to that instruction raises on every
  single run.
* **PROXY_WEIGHT_ESTIMATE** — "two binders … needs binder resolution by model code". There is only
  ONE model code (``risk.proxy_weight.regression``); both binders assert it. Model-code resolution
  cannot discriminate them, so the VAR pattern is unimplementable here. What DOES discriminate is
  the version's declared ESTIMATOR CONVENTION, which is also how production dispatches.
* **COVARIANCE_PRIVATE** — "shares covariance_result with COVARIANCE; needs binder resolution by
  model code". The TABLE is shared; the RUN TYPE is not, and the sweep resolves subjects per run
  type. The two families never collide, so no resolution is needed at all.

**Why a factory for most of them and hand-written functions for five.** Eleven families have
literally the same shape — read the run's rows in key order; call one binder with the run's own
pinned ``snapshot_id`` and ``model_version_id``; project. Writing that eleven times would be
eleven chances to typo a fence, and the field-level declarations (which is what a reader needs to
audit) would be buried in boilerplate. So the shape is written once, in ``_consume_adapter``.

The five exceptions are exceptions BECAUSE the factory would be a lie about them, and each is
documented at its own definition: two backtests need binder resolution by model code (the genuine
VAR-shaped case), ROLLING_RISK and SHARPE need ``window_months`` recovered off their stored rows,
and PROXY_WEIGHT_ESTIMATE needs both a convention-based binder choice and a derived recovery of a
caller-supplied argument that has NO stored column. The factory refuses to hide any of that.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from irp_shared.calc.models import CalculationRun
from irp_shared.reproduction.registry import (
    ComparableRow,
    ReproducibleFamily,
    ReproductionUnsupported,
    _rows_of,
)

# --------------------------------------------------------------------------- shared exclusions ---
#: The two by-construction classes, identical for every family below because every result model
#: carries the same three mixins and the same three governed-run FKs. Spelled as reusable
#: constants rather than repeated strings: sixteen hand-copied 90-character reasons would drift,
#: and a census that checks reason LENGTH cannot see drift.
_WHY_ROW_IDENTITY = (
    "differs by construction on any re-execution: this is the row's own identity / knowledge time, "
    "not the arithmetic it recorded"
)
_WHY_EXECUTION_FK = (
    "differs by construction on any re-execution: it names THIS execution's run, snapshot or model "
    "version rather than the values that were computed"
)

#: `id`, `tenant_id`, `system_from` + the three governed-run FKs — the floor every family shares.
_STANDARD_UNCOMPARED: dict[str, str] = {
    "id": _WHY_ROW_IDENTITY,
    "tenant_id": _WHY_ROW_IDENTITY,
    "system_from": _WHY_ROW_IDENTITY,
    "calculation_run_id": _WHY_EXECUTION_FK,
    "input_snapshot_id": _WHY_EXECUTION_FK,
    "model_version_id": _WHY_EXECUTION_FK,
}


def _uncompared(**extra: str) -> dict[str, str]:
    """The standard floor plus this family's own exclusions."""
    return {**_STANDARD_UNCOMPARED, **extra}


def _compared(model: Any, key_fields: Sequence[str], uncompared: dict[str, str]) -> tuple[str, ...]:
    """Everything left over — DERIVED from the model, not hand-listed.

    This inverts REPRO-1's convention deliberately, and the inversion is the safer half of its own
    lesson. There, ``compared_fields`` was hand-written and silently omitted six governed columns;
    the census now catches that, but only AFTER someone has already shipped the omission and only
    for columns that exist at write time. Deriving the compared set as "the model minus what was
    explicitly excused" makes the omission unrepresentable: a new column lands in the comparison by
    DEFAULT, and leaving it out requires writing a reason down. The census still runs — it is now
    a tautology for these families, which is what a census should become once the thing it watched
    for cannot be expressed.

    Order is the model's own column order, which is stable and human-readable in a diff.
    """
    excused = set(key_fields) | set(uncompared)
    return tuple(c.name for c in model.__table__.columns if c.name not in excused)


# ------------------------------------------------------------------------------- the two shapes ---
def _stored_reader(
    model: Any, key_fields: tuple[str, ...], compared_fields: tuple[str, ...]
) -> Callable[[Session, str, CalculationRun], list[ComparableRow]]:
    """Read one run's stored rows, tenant-fenced and ordered by the family's own key.

    The tenant predicate sits UNDER RLS rather than instead of it — the platform's belt-and-braces
    convention — and the ordering is by the declared key so two executions' row lists line up
    positionally as well as by key.
    """

    def _read(session: Session, acting_tenant: str, run: CalculationRun) -> list[ComparableRow]:
        columns = model.__table__.columns
        rows = (
            session.execute(
                select(model)
                .where(
                    model.calculation_run_id == str(run.run_id),
                    model.tenant_id == acting_tenant,
                )
                .order_by(*[columns[f] for f in key_fields])
            )
            .scalars()
            .all()
        )
        return _rows_of(list(rows), key_fields, compared_fields)

    return _read


def _consume_adapter(
    *,
    binder: Callable[..., Any],
    actor_cls: Any,
    key_fields: tuple[str, ...],
    compared_fields: tuple[str, ...],
    refusal_types: tuple[type[Exception], ...],
) -> Callable[[Session, str, CalculationRun, str], list[ComparableRow]]:
    """Re-execute a family whose binder needs NOTHING but the run's own pins.

    Eleven of the sixteen qualify, and the qualification is not "it looked similar" — it is that
    every value-bearing input is either inside the pinned snapshot or declared on the bound model
    version, and the binder REFUSES its build-mode arguments alongside ``snapshot_id`` rather than
    silently merging them. That refusal is what makes the shape safe: the RPT-1 B1 defect (a
    caller-supplied value that reaches the output through a silent default) cannot occur where the
    argument is rejected rather than defaulted.

    ``refusal_types`` is the family's own input-error class. It is mapped to
    ``ReproductionUnsupported`` deliberately: a binder that refuses because an upstream run is no
    longer visible or COMPLETED is telling us the check CANNOT BE PERFORMED, which is a different
    fact from "the platform's promise broke" and must not be recorded as a divergence. Every one of
    these binders has such a gate, so this mapping is load-bearing for all eleven, not defensive
    decoration.
    """

    def _recompute(
        session: Session, acting_tenant: str, run: CalculationRun, code_version: str
    ) -> list[ComparableRow]:
        if run.input_snapshot_id is None:
            raise ReproductionUnsupported(
                f"run {run.run_id} has no input_snapshot_id, so there is nothing to re-execute "
                "against"
            )
        if run.model_version_id is None:
            raise ReproductionUnsupported(
                f"run {run.run_id} binds no model_version, so its binder cannot be parameterised"
            )
        try:
            result = binder(
                session,
                acting_tenant=acting_tenant,
                actor=actor_cls(actor_id="reproduction", actor_type="SYSTEM"),
                code_version=code_version,
                environment_id=run.environment_id or "reproduction",
                model_version_id=str(run.model_version_id),
                snapshot_id=str(run.input_snapshot_id),
            )
        except refusal_types as exc:
            raise ReproductionUnsupported(
                f"the binder refused to re-execute run {run.run_id}: {exc}"
            ) from exc
        return _rows_of(list(result.rows), key_fields, compared_fields)

    return _recompute


def _family(
    *,
    family_key: str,
    model: Any,
    key_fields: tuple[str, ...],
    binder: Callable[..., Any],
    actor_cls: Any,
    refusal_types: tuple[type[Exception], ...],
    uncompared: dict[str, str],
) -> ReproducibleFamily:
    """One standard-shape family, declared once."""
    compared = _compared(model, key_fields, uncompared)
    return ReproducibleFamily(
        family_key=family_key,
        key_fields=key_fields,
        compared_fields=compared,
        read_stored=_stored_reader(model, key_fields, compared),
        recompute=_consume_adapter(
            binder=binder,
            actor_cls=actor_cls,
            key_fields=key_fields,
            compared_fields=compared,
            refusal_types=refusal_types,
        ),
        model=model,
        uncompared=uncompared,
    )


# ====================================================================== the eleven standard ones ==
def _standard_families() -> dict[str, ReproducibleFamily]:
    """The eleven whose binders need nothing but the run's own pins.

    Imports are function-local for the same reason REPRO-1's recompute functions import locally:
    `irp_shared.reproduction` must not acquire a load-time edge to every compute package on the
    platform, and the import-direction fences would (correctly) refuse it.
    """
    from irp_shared.pacing.events import PacingActor
    from irp_shared.pacing.models import PacingProjectionResult
    from irp_shared.pacing.service import PacingInputError, run_pacing_projection
    from irp_shared.perf.benchmark_relative_service import (
        BenchmarkRelativeInputError,
        run_benchmark_relative,
    )
    from irp_shared.perf.desmoothing_service import DesmoothingInputError, run_desmoothed_return
    from irp_shared.perf.events import (
        BenchmarkRelativeActor,
        DesmoothedReturnActor,
        PortfolioReturnActor,
    )
    from irp_shared.perf.models import (
        BenchmarkRelativeResult,
        DesmoothedReturnResult,
        PortfolioReturnResult,
    )
    from irp_shared.perf.return_service import PortfolioReturnInputError, run_portfolio_return
    from irp_shared.risk.active_risk_service import ActiveRiskInputError, run_active_risk
    from irp_shared.risk.covariance_service import CovarianceInputError, run_covariance
    from irp_shared.risk.events import (
        ActiveRiskActor,
        CovarianceActor,
        FactorExposureActor,
        PurePrivateCovarianceActor,
        PurePrivateFactorActor,
        SensitivityActor,
    )
    from irp_shared.risk.factor_service import FactorExposureInputError, run_factor_exposure
    from irp_shared.risk.models import (
        ActiveRiskResult,
        CovarianceResult,
        FactorExposureResult,
        PrivateFactorReturnResult,
        SensitivityResult,
    )
    from irp_shared.risk.private_covariance_service import (
        PrivateCovarianceInputError,
        run_private_covariance,
    )
    from irp_shared.risk.private_factor_service import (
        PurePrivateFactorInputError,
        run_pure_private_factor_return,
    )
    from irp_shared.risk.scenario_models import ScenarioResult
    from irp_shared.risk.scenario_service import ScenarioActor, ScenarioInputError, run_scenario
    from irp_shared.risk.service import SensitivityInputError, run_sensitivities

    return {
        # COVARIANCE and COVARIANCE_PRIVATE share `covariance_result` but NOT their run type, and
        # the sweep resolves one subject per run type — so they never collide and neither needs
        # binder resolution. (The registry's "needs binder resolution by model code" reason was
        # describing the shared TABLE; corrected at the move.)
        "COVARIANCE": _family(
            family_key="COVARIANCE",
            model=CovarianceResult,
            key_fields=("factor_id_1", "factor_id_2"),
            binder=run_covariance,
            actor_cls=CovarianceActor,
            refusal_types=(CovarianceInputError,),
            uncompared=_uncompared(),
        ),
        "COVARIANCE_PRIVATE": _family(
            family_key="COVARIANCE_PRIVATE",
            model=CovarianceResult,
            key_fields=("factor_id_1", "factor_id_2"),
            binder=run_private_covariance,
            actor_cls=PurePrivateCovarianceActor,
            refusal_types=(PrivateCovarianceInputError,),
            uncompared=_uncompared(),
        ),
        # The row SET is itself a signal here: a zero-weight proxy leg emits no row at all, so a
        # change in leg selection shows up as a missing/extra key rather than a changed value —
        # which `compare_rows` already reports distinctly.
        "FACTOR_EXPOSURE": _family(
            family_key="FACTOR_EXPOSURE",
            model=FactorExposureResult,
            key_fields=("portfolio_id", "instrument_id", "factor_id"),
            binder=run_factor_exposure,
            actor_cls=FactorExposureActor,
            refusal_types=(FactorExposureInputError,),
            uncompared=_uncompared(),
        ),
        "SENSITIVITY": _family(
            family_key="SENSITIVITY",
            model=SensitivityResult,
            key_fields=("curve_id", "value_type", "tenor_days", "sensitivity_type"),
            binder=run_sensitivities,
            actor_cls=SensitivityActor,
            refusal_types=(SensitivityInputError,),
            uncompared=_uncompared(),
        ),
        # `factor_id` is NULL on the single PNL_TOTAL row, and PostgreSQL treats NULLs as distinct
        # — so the unique constraint does not actually enforce that singleton; the WRITER does.
        # The key still discriminates (the projection stringifies NULL to "None" exactly once).
        "SCENARIO": _family(
            family_key="SCENARIO",
            model=ScenarioResult,
            key_fields=("metric_type", "factor_id"),
            binder=run_scenario,
            actor_cls=ScenarioActor,
            refusal_types=(ScenarioInputError,),
            uncompared=_uncompared(),
        ),
        "ACTIVE_RISK": _family(
            family_key="ACTIVE_RISK",
            model=ActiveRiskResult,
            key_fields=("metric_type",),
            binder=run_active_risk,
            actor_cls=ActiveRiskActor,
            refusal_types=(ActiveRiskInputError,),
            # `factor_exposure_run_id` / `covariance_run_id` are COMPARED, not excused. The first
            # draft of this module excused them as execution FKs by analogy with VAR's columns of
            # the same NAME — and that reason was false: the writer sets them from `parsed.*`, the
            # ADJUDICATED PIN, so a re-execution over the same snapshot reproduces them exactly.
            # Excusing them would have been a well-written, false `uncompared` reason — the very
            # class this module's docstring is about — caught here by reading the writer instead
            # of the column name.
            uncompared=_uncompared(),
        ),
        "PORTFOLIO_RETURN": _family(
            family_key="PORTFOLIO_RETURN",
            model=PortfolioReturnResult,
            key_fields=("metric_type", "period_start"),
            binder=run_portfolio_return,
            actor_cls=PortfolioReturnActor,
            refusal_types=(PortfolioReturnInputError,),
            uncompared=_uncompared(),
        ),
        # `benchmark_id` and `return_basis` are COMPARED, not read back — see the module docstring:
        # the binder refuses them alongside `snapshot_id` and re-derives both from the pinned
        # content, so comparing them checks the adjudicator rather than comparing a value with
        # itself. `portfolio_return_run_id` is likewise re-derived from the pin, so it is compared
        # too rather than being excused as an execution FK.
        "BENCHMARK_RELATIVE": _family(
            family_key="BENCHMARK_RELATIVE",
            model=BenchmarkRelativeResult,
            key_fields=("metric_type", "period_start"),
            binder=run_benchmark_relative,
            actor_cls=BenchmarkRelativeActor,
            refusal_types=(BenchmarkRelativeInputError,),
            uncompared=_uncompared(),
        ),
        "DESMOOTHED_RETURN": _family(
            family_key="DESMOOTHED_RETURN",
            model=DesmoothedReturnResult,
            key_fields=("metric_type", "period_start"),
            binder=run_desmoothed_return,
            actor_cls=DesmoothedReturnActor,
            refusal_types=(DesmoothingInputError,),
            uncompared=_uncompared(),
        ),
        "PURE_PRIVATE_FACTOR": _family(
            family_key="PURE_PRIVATE_FACTOR",
            model=PrivateFactorReturnResult,
            key_fields=("metric_type", "period_start"),
            binder=run_pure_private_factor_return,
            actor_cls=PurePrivateFactorActor,
            refusal_types=(PurePrivateFactorInputError,),
            uncompared=_uncompared(),
        ),
        "PACING_PROJECTION": _family(
            family_key="PACING_PROJECTION",
            model=PacingProjectionResult,
            key_fields=("period_index",),
            binder=run_pacing_projection,
            actor_cls=PacingActor,
            refusal_types=(PacingInputError,),
            uncompared=_uncompared(),
        ),
    }


# =========================================== the two backtests: shared table, disjoint runs ==
def _backtest_families() -> dict[str, ReproducibleFamily]:
    """VAR_BACKTEST and ES_BACKTEST — a FOURTH reason the registry got wrong.

    Its note said both "share var_backtest_result; needs binder resolution by model code". The
    table is shared; the RUN TYPE is not — `run_var_backtest` only ever creates VAR_BACKTEST runs
    and `run_es_backtest` only ES_BACKTEST ones, and the sweep resolves its subject per run type.
    So each family has exactly one possible binder and the VAR-style allowlist would be dead code.

    This is the same correction as COVARIANCE_PRIVATE's, and the pair of them is the point: a
    shared RESULT TABLE was read as implying a shared dispatch problem. It does not. What creates
    the VAR family's genuine ambiguity is seven model codes writing under ONE run type.
    """
    from irp_shared.risk.es_backtest_service import EsBacktestInputError, run_es_backtest
    from irp_shared.risk.events import EsBacktestActor, VarBacktestActor
    from irp_shared.risk.models import VarBacktestResult
    from irp_shared.risk.var_backtest_service import VarBacktestInputError, run_var_backtest

    out: dict[str, ReproducibleFamily] = {}
    for family_key, binder, actor_cls, refusals in (
        ("VAR_BACKTEST", run_var_backtest, VarBacktestActor, (VarBacktestInputError,)),
        ("ES_BACKTEST", run_es_backtest, EsBacktestActor, (EsBacktestInputError,)),
    ):
        out[family_key] = _family(
            family_key=family_key,
            model=VarBacktestResult,
            # `metric_type` alone collides: the per-pair EXCEPTION_INDICATOR rows all share it and
            # are told apart by their period.
            key_fields=("metric_type", "period_start"),
            binder=binder,
            actor_cls=actor_cls,
            refusal_types=refusals,
            uncompared=_uncompared(),
        )
    return out


# =========================================================== the two that recover their WINDOWS ==
def _window_months_of(model: Any) -> Callable[[Session, str, CalculationRun], tuple[int, ...]]:
    """Recover a run's requested ``window_months`` from the rows it wrote.

    ROLLING_RISK and SHARPE take ``window_months`` as a REQUIRED caller argument that determines
    which rows exist, and it is not pinned in the snapshot — so a reproducer that did not recover
    it could not call the binder at all. (The registry's reason called this a silent-default
    hazard; it is not. There is no default: omitting the argument is a ``TypeError``, which fails
    loud. The read-back is mandatory for a different reason — the value is simply absent.)

    The recovery is EXACT rather than a best guess: both binders emit rows for every requested
    window even when the window cannot be filled (a suppressed row carrying its own
    ``window_months``), so the distinct stored values ARE the requested tuple.
    """

    def _windows(session: Session, acting_tenant: str, run: CalculationRun) -> tuple[int, ...]:
        values = (
            session.execute(
                select(model.window_months)
                .where(
                    model.calculation_run_id == str(run.run_id),
                    model.tenant_id == acting_tenant,
                )
                .distinct()
            )
            .scalars()
            .all()
        )
        windows = tuple(sorted({int(v) for v in values}))
        if not windows:
            raise ReproductionUnsupported(
                f"run {run.run_id} stored no rows, so the window_months it was asked for cannot be "
                "recovered — there is nothing to re-execute with"
            )
        return windows

    return _windows


def _windowed_adapter(
    *,
    model: Any,
    binder: Callable[..., Any],
    actor_cls: Any,
    key_fields: tuple[str, ...],
    compared_fields: tuple[str, ...],
    refusal_types: tuple[type[Exception], ...],
) -> Callable[[Session, str, CalculationRun, str], list[ComparableRow]]:
    """The standard shape plus the recovered ``window_months``.

    A refusal here has one cause worth naming: both binders police the window domain against the
    model's declared windows, so a HISTORICAL run whose windows have since left that domain cannot
    be re-executed. That is honestly ``UNREPRODUCIBLE`` — the platform can no longer produce the
    run it once produced — and reporting it as a divergence would be a lie about the arithmetic.
    """
    windows_of = _window_months_of(model)

    def _recompute(
        session: Session, acting_tenant: str, run: CalculationRun, code_version: str
    ) -> list[ComparableRow]:
        if run.input_snapshot_id is None:
            raise ReproductionUnsupported(
                f"run {run.run_id} has no input_snapshot_id, so there is nothing to re-execute "
                "against"
            )
        if run.model_version_id is None:
            raise ReproductionUnsupported(
                f"run {run.run_id} binds no model_version, so its binder cannot be parameterised"
            )
        windows = windows_of(session, acting_tenant, run)
        try:
            result = binder(
                session,
                acting_tenant=acting_tenant,
                actor=actor_cls(actor_id="reproduction", actor_type="SYSTEM"),
                code_version=code_version,
                environment_id=run.environment_id or "reproduction",
                model_version_id=str(run.model_version_id),
                window_months=windows,
                snapshot_id=str(run.input_snapshot_id),
            )
        except refusal_types as exc:
            raise ReproductionUnsupported(
                f"the binder refused to re-execute run {run.run_id} over its recovered windows "
                f"{windows}: {exc}"
            ) from exc
        return _rows_of(list(result.rows), key_fields, compared_fields)

    return _recompute


def _windowed_families() -> dict[str, ReproducibleFamily]:
    from irp_shared.perf.events import RollingRiskActor, SharpeRatioActor
    from irp_shared.perf.models import RollingRiskResult, SharpeRatioResult
    from irp_shared.perf.rolling_service import RollingRiskInputError, run_rolling_risk
    from irp_shared.perf.sharpe_service import SharpeInputError, run_sharpe_ratio

    out: dict[str, ReproducibleFamily] = {}
    for family_key, model, binder, actor_cls, refusals in (
        (
            "ROLLING_RISK",
            RollingRiskResult,
            run_rolling_risk,
            RollingRiskActor,
            (RollingRiskInputError,),
        ),
        ("SHARPE", SharpeRatioResult, run_sharpe_ratio, SharpeRatioActor, (SharpeInputError,)),
    ):
        # `window_months` is in the KEY, not merely compared: two windows write rows that are
        # otherwise identically keyed, so omitting it would collapse them and compare a 12-month
        # figure against a 36-month one.
        key_fields = ("metric_type", "window_months", "period_start")
        # `portfolio_return_run_id` is COMPARED: the writer sets it from `parsed.*` (the pinned
        # content), so it reproduces exactly and excusing it as an execution FK would be a false
        # reason. See the ACTIVE_RISK note above — same mistake, caught the same way.
        uncompared = _uncompared()
        compared = _compared(model, key_fields, uncompared)
        out[family_key] = ReproducibleFamily(
            family_key=family_key,
            key_fields=key_fields,
            compared_fields=compared,
            read_stored=_stored_reader(model, key_fields, compared),
            recompute=_windowed_adapter(
                model=model,
                binder=binder,
                actor_cls=actor_cls,
                key_fields=key_fields,
                compared_fields=compared,
                refusal_types=refusals,
            ),
            model=model,
            uncompared=uncompared,
        )
    return out


# ================================================== PROXY_WEIGHT_ESTIMATE: two binders, one code ==
def _proxy_weight_family() -> ReproducibleFamily:
    """The one family that needed everything the factory refuses to hide.

    **Two binders under ONE model code.** ``run_proxy_weight_estimate`` (OLS / EWMA) and
    ``run_residual_shrinkage`` (cross-sectional empirical Bayes) both write
    ``proxy_weight_estimate_result`` under run type ``PROXY_WEIGHT_ESTIMATE``, and both assert the
    SAME ``risk.proxy_weight.regression`` model code. The registry said to resolve them "by model
    code"; that is unimplementable, because the resolver returns one string for both. What
    discriminates them is the version's declared ESTIMATOR CONVENTION — which is also exactly how
    production dispatches, so this reuses the platform's own rule rather than inventing a second
    one that can drift from it.

    **A caller-supplied argument with NO stored column.** ``run_residual_shrinkage`` takes
    ``target_estimate_run_id`` — which member of the pinned cohort is being shrunk — and the
    snapshot pins the WHOLE COHORT, not the target. Nothing on the result row records it. So it is
    recovered indirectly: the single stored row carries the target member's own
    ``source_desmoothed_run_id``, and exactly one cohort member should match it.

    That indirection is the weakest link in these sixteen adapters, so it fails CLOSED rather than
    guessing: no match, or more than one match, is ``ReproductionUnsupported``. A wrong target
    would re-execute a real computation over the wrong member and report the resulting difference
    as a DIVERGENCE — a false alarm indistinguishable from the true one, which is the exact defect
    class REPRO-1's ``base_currency`` read-back existed to prevent.
    """
    from irp_shared.model.service import WrongModelVersionError
    from irp_shared.risk.bootstrap import (
        PROXY_WEIGHT_REGRESSION_CONVENTIONS,
        PROXY_WEIGHT_SHRINKAGE_EB_CONVENTION,
        declared_proxy_weight_parameters,
    )
    from irp_shared.risk.events import ProxyWeightEstimateActor
    from irp_shared.risk.models import ProxyWeightEstimateResult
    from irp_shared.risk.proxy_weight_service import (
        ProxyWeightInputError,
        run_proxy_weight_estimate,
    )
    from irp_shared.risk.residual_shrinkage_service import (
        ResidualShrinkageInputError,
        recover_shrinkage_target,
        run_residual_shrinkage,
    )

    key_fields = ("metric_type", "factor_id")
    # `source_desmoothed_run_id` is COMPARED (both binders set it from the pinned content), and it
    # carries extra weight here: it is also the column the shrinkage TARGET is recovered from
    # below, so a silent change in it would break the recovery. Comparing it means that break
    # would be visible as a divergence rather than as a wrong-target recompute.
    uncompared = _uncompared()
    compared = _compared(ProxyWeightEstimateResult, key_fields, uncompared)

    def _resolve_convention(session: Session, acting_tenant: str, run: CalculationRun) -> str:
        from irp_shared.model.models import ModelVersion

        version = session.execute(
            select(ModelVersion).where(
                ModelVersion.id == str(run.model_version_id),
                ModelVersion.tenant_id == acting_tenant,
            )
        ).scalar_one_or_none()
        if version is None:
            raise ReproductionUnsupported(
                f"model_version {run.model_version_id} is not visible to this tenant"
            )
        try:
            return str(declared_proxy_weight_parameters(session, version).estimator_convention)
        except WrongModelVersionError as exc:
            # The declaration is unknown, ambiguous or malformed, so the binder CANNOT be
            # identified. This is the VAR family's "refusing to guess which kernel produced this
            # run", reached through the resolver rather than through a fall-through branch.
            #
            # The first draft had that fall-through: an `else:` arm refusing an unrecognised
            # convention. It was UNREACHABLE — `declared_proxy_weight_parameters` fails closed on
            # exactly those inputs, so the arm could never execute — and the mutation battery
            # proved it by deleting the arm without any test noticing. An unreachable guard is a
            # guard that reads as protection and provides none; this is where the protection
            # actually has to live.
            raise ReproductionUnsupported(
                f"run {run.run_id} binds a model version whose estimator convention cannot be "
                f"resolved ({exc}) — refusing to guess which kernel produced this run"
            ) from exc

    def _shrinkage_target(session: Session, acting_tenant: str, run: CalculationRun) -> str:
        """Which cohort member this run shrank — recovered, because nothing stores it."""
        source_runs = (
            session.execute(
                select(ProxyWeightEstimateResult.source_desmoothed_run_id).where(
                    ProxyWeightEstimateResult.calculation_run_id == str(run.run_id),
                    ProxyWeightEstimateResult.tenant_id == acting_tenant,
                )
            )
            .scalars()
            .all()
        )
        wanted = {str(s).lower() for s in source_runs if s is not None}
        if len(wanted) != 1:
            raise ReproductionUnsupported(
                f"run {run.run_id} stores {len(wanted)} distinct source_desmoothed_run_id values, "
                "so the shrinkage TARGET it was run against cannot be identified — refusing to "
                "guess, because the wrong target would produce a real number and report the "
                "difference as a divergence"
            )
        try:
            return recover_shrinkage_target(
                session,
                acting_tenant=acting_tenant,
                snapshot_id=str(run.input_snapshot_id),
                source_desmoothed_run_id=next(iter(wanted)),
            )
        except ResidualShrinkageInputError as exc:
            raise ReproductionUnsupported(
                f"the shrinkage target for run {run.run_id} cannot be identified: {exc}"
            ) from exc

    def _recompute(
        session: Session, acting_tenant: str, run: CalculationRun, code_version: str
    ) -> list[ComparableRow]:
        if run.input_snapshot_id is None:
            raise ReproductionUnsupported(
                f"run {run.run_id} has no input_snapshot_id, so there is nothing to re-execute "
                "against"
            )
        if run.model_version_id is None:
            raise ReproductionUnsupported(
                f"run {run.run_id} binds no model_version, so its binder cannot be identified"
            )
        convention = _resolve_convention(session, acting_tenant, run)
        actor = ProxyWeightEstimateActor(actor_id="reproduction", actor_type="SYSTEM")
        environment_id = run.environment_id or "reproduction"
        model_version_id = str(run.model_version_id)
        snapshot_id = str(run.input_snapshot_id)
        # Spelled out per call rather than splatted from a shared dict: `**kwargs` erases the
        # argument types, so mypy could not see that these two binders take DIFFERENT signatures —
        # and a dict is exactly where a wrong key would hide until runtime.
        rows: list[Any]
        try:
            if convention in PROXY_WEIGHT_REGRESSION_CONVENTIONS:
                rows = list(
                    run_proxy_weight_estimate(
                        session,
                        acting_tenant=acting_tenant,
                        actor=actor,
                        code_version=code_version,
                        environment_id=environment_id,
                        model_version_id=model_version_id,
                        snapshot_id=snapshot_id,
                    ).rows
                )
            elif convention == PROXY_WEIGHT_SHRINKAGE_EB_CONVENTION:
                rows = list(
                    run_residual_shrinkage(
                        session,
                        acting_tenant=acting_tenant,
                        actor=actor,
                        code_version=code_version,
                        environment_id=environment_id,
                        model_version_id=model_version_id,
                        snapshot_id=snapshot_id,
                        target_estimate_run_id=_shrinkage_target(session, acting_tenant, run),
                    ).rows
                )
            else:  # pragma: no cover - see `_resolve_convention`: unreachable by contract
                # Kept as a backstop ONLY because a future convention could be added to the
                # declaration vocabulary without a binder here. It is documented as unreachable
                # rather than presented as the guard — the guard is in `_resolve_convention`.
                raise ReproductionUnsupported(
                    f"estimator convention {convention!r} writes proxy_weight_estimate_result but "
                    "has no declared reproduction binder — refusing to guess which kernel produced "
                    "this run"
                )
        except (ProxyWeightInputError, ResidualShrinkageInputError) as exc:
            raise ReproductionUnsupported(
                f"the binder refused to re-execute run {run.run_id}: {exc}"
            ) from exc
        return _rows_of(rows, key_fields, compared)

    return ReproducibleFamily(
        family_key="PROXY_WEIGHT_ESTIMATE",
        key_fields=key_fields,
        compared_fields=compared,
        read_stored=_stored_reader(ProxyWeightEstimateResult, key_fields, compared),
        recompute=_recompute,
        model=ProxyWeightEstimateResult,
        uncompared=uncompared,
    )


def new_families() -> dict[str, ReproducibleFamily]:
    """The sixteen, assembled. Imported by the registry into ``REPRODUCIBLE_FAMILIES``."""
    return {
        **_standard_families(),
        **_backtest_families(),
        **_windowed_families(),
        "PROXY_WEIGHT_ESTIMATE": _proxy_weight_family(),
    }
