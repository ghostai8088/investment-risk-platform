"""Proxy-weight regression run service (PA-3, ENT-057) — the TWELFTH governed number and the
loop-closer: OLS of a private instrument's DESMOOTHED appraisal return series (PA-1's governed
output — its FIRST downstream consumer) on the candidate public factor returns.

``run_proxy_weight_estimate`` reads the PINNED ``DESMOOTHED_PERIOD`` rows (the regression target
``y``) + each candidate factor's pinned SIMPLE-return window, compounds each factor's returns over
every appraisal period to align frequencies, fits the OLS kernel, and persists one ``WEIGHT`` row
per candidate factor (coefficient + standard error) + one ``INTERCEPT`` row + one
``ESTIMATION_SUMMARY`` row (R^2 / n / n_regressors / residual stdev). Build-in-request
(``desmoothed_run_id`` + ``factor_ids`` → builds a ``PROXY_WEIGHT_INPUT`` snapshot) or
consume-existing (``snapshot_id``); BOTH paths adjudicate the PINNED content pre-create (AD-014 —
never a live read; a later mark/return correction cannot move a historical estimate, TR-09).

Estimates are MODEL OUTPUT — snapshot/run/model-bound, IA append-only — and are **never written**
into ``proxy_mapping`` by the run (OD-PA-3-A). Promotion is a deliberate second capture step (the
``marketdata`` REGRESSION-method path citing this run).

The declared ``min_observations`` is the MODEL identity (OD-PA-3-D) — parsed from the registered
version, never a request parameter — and echoed on every persisted row; the run additionally
enforces ``n >= max(declared, k + 2)``.

Failure model (the established governed-run shape):
- **Pre-create refusal (422, its own ``ProxyWeightInputError``)** — missing prerequisite, ambiguous
  input, wrong-purpose/cross-tenant snapshot, malformed pinned content, too few periods, a
  non-CURRENCY candidate factor, a per-period factor-coverage gap, a mixed subject/currency series,
  a SINGULAR/collinear design, or a CONSTANT target (the kernel's structural refusals). NO run.
- **Post-create FAILED (magnitude gate)** — a committed FAILED run + ZERO rows + a naming
  ``failure_reason`` when a raw coefficient/std-error clears the ``Numeric(20,12)`` envelope.

Reuses ``risk.run``/``risk.view`` (no mint) + ``CALC.RUN_*`` (``RISK.PROXY_WEIGHT_ESTIMATE_CREATE``
reserved-not-emitted). One-way imports: ``risk -> {snapshot, calc, model, marketdata,
portfolio.guards, reference.guards}`` (``marketdata`` for the CURRENCY-family constant + the
``promote_proxy_weight_estimate`` capture — the run-TYPE gate ``marketdata`` itself cannot see).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, localcontext
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from irp_shared.calc.models import CalculationRun
from irp_shared.calc.parse import parse_strict_decimal
from irp_shared.calc.runs import resolve_completed_run_of_type, resolve_run_of_type
from irp_shared.calc.scaffold import execute_governed_run
from irp_shared.marketdata.models import (
    FACTOR_FAMILY_CURRENCY,
    MAPPING_METHOD_REGRESSION,
    ProxyMapping,
)
from irp_shared.marketdata.proxy_mapping import ProxyMappingActor, capture_proxy_mapping
from irp_shared.model.service import assert_model_version_of
from irp_shared.portfolio.guards import assert_portfolio_in_tenant
from irp_shared.reference.guards import assert_instrument_in_tenant
from irp_shared.risk.bootstrap import PROXY_WEIGHT_MODEL_CODE, declared_min_observations
from irp_shared.risk.events import RUN_TYPE_PROXY_WEIGHT_ESTIMATE, ProxyWeightEstimateActor
from irp_shared.risk.models import (
    METRIC_TYPE_ESTIMATION_SUMMARY,
    METRIC_TYPE_INTERCEPT,
    METRIC_TYPE_WEIGHT,
    ProxyWeightEstimateResult,
)
from irp_shared.risk.proxy_weight_kernel import ProxyWeightKernelError, estimate_ols
from irp_shared.snapshot import (
    COMPONENT_KIND_DESMOOTHED_RETURN,
    COMPONENT_KIND_FACTOR,
    COMPONENT_KIND_FACTOR_RETURN,
    PURPOSE_PROXY_WEIGHT_INPUT,
    SnapshotActor,
    build_proxy_weight_snapshot,
    list_components,
    resolve_snapshot,
)

#: Per-tenant governed completeness DQ rule (resolve-or-register; the established pattern).
_COMPLETENESS_RULE_CODE = "risk.proxy_weight.completeness"
#: The Numeric(20,12) ceiling is |value| < 1E8; the gate bounds EVERY persisted coefficient /
#: std_error / R^2 / residual_stdev (the P3-8/BT-1/PA-1/PA-2 envelope lesson baked in from birth).
_MAX_RESULT_ABS = Decimal("1E8")
#: Column quantum (quantize at assign so SQLite + PG persist byte-identical values).
_RESULT_QUANTUM = Decimal("1E-12")
#: Compute precision for per-period factor compounding (matches the kernel context).
_CTX_PRECISION = 50


class ProxyWeightInputError(Exception):
    """A missing/invalid prerequisite detected BEFORE the run is created — pre-create refusal (no
    run, no result, no run-audit). Its OWN class. Maps to 422."""


class ProxyWeightEstimateResultNotVisible(Exception):
    """Raised when a ``proxy_weight_estimate_result`` id is not visible in the acting tenant."""

    def __init__(self, result_id: str) -> None:
        super().__init__(f"proxy_weight_estimate_result {result_id} is not visible in the tenant")
        self.result_id = str(result_id)


class ProxyWeightEstimateRunNotVisible(Exception):
    """Raised when a proxy-weight-estimate ``calculation_run`` id is not visible in the tenant."""

    def __init__(self, run_id: str) -> None:
        super().__init__(f"proxy-weight-estimate run {run_id} is not visible in the current tenant")
        self.run_id = str(run_id)


@dataclass(frozen=True)
class ProxyWeightEstimateRunResult:
    """The outcome of ``run_proxy_weight_estimate``: the ``calculation_run`` + status + result rows.
    ``status`` is ``COMPLETED`` (``rows`` = the WEIGHT rows + INTERCEPT + ESTIMATION_SUMMARY) or
    ``FAILED`` (the magnitude gate: a committed FAILED run + ZERO rows + a naming reason)."""

    run: CalculationRun
    status: str
    rows: list[ProxyWeightEstimateResult] = field(default_factory=list)
    failure_reason: str | None = None


@dataclass(frozen=True)
class _Period:
    """One adjudicated appraisal period: its span + the desmoothed return (regression target)."""

    period_start: date
    period_end: date
    desmoothed_return: Decimal


@dataclass(frozen=True)
class _Candidate:
    """One adjudicated candidate factor: identity + its pinned (date, SIMPLE-return) rows."""

    factor_id: str
    factor_code: str
    returns: tuple[tuple[date, Decimal], ...]  # ordered by return_date


@dataclass(frozen=True)
class _ParsedInput:
    """Adjudicated pinned input: the ordered target periods + candidate factors + run-uniform
    descriptors + the consumed desmoothed run id (provenance echo)."""

    periods: tuple[_Period, ...]  # ordered by period_start
    candidates: tuple[_Candidate, ...]  # ordered by factor_id
    portfolio_id: str
    instrument_id: str
    series_currency: str
    source_desmoothed_run_id: str


def _parse_pins(
    comps: list[Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """Split the pinned ``captured_content`` into (desmoothed-period, factor, factor-return) raw
    dicts (PURE — no live read; AD-014)."""
    desmoothed = [
        json.loads(c.captured_content)
        for c in comps
        if c.component_kind == COMPONENT_KIND_DESMOOTHED_RETURN
    ]
    factors = [
        json.loads(c.captured_content) for c in comps if c.component_kind == COMPONENT_KIND_FACTOR
    ]
    factor_returns = [
        json.loads(c.captured_content)
        for c in comps
        if c.component_kind == COMPONENT_KIND_FACTOR_RETURN
    ]
    return desmoothed, factors, factor_returns


def _compound(returns: list[Decimal]) -> Decimal:
    """Compound a period's SIMPLE returns: ``prod(1 + r) - 1`` (prec-50; the caller quantizes
    nothing — the raw value feeds the kernel)."""
    with localcontext() as ctx:
        ctx.prec = _CTX_PRECISION
        acc = Decimal(1)
        for r in returns:
            acc *= Decimal(1) + r
        return acc - Decimal(1)


def _adjudicate_pins(
    desmoothed_raw: list[dict[str, Any]],
    factor_raw: list[dict[str, Any]],
    factor_return_raw: list[dict[str, Any]],
    *,
    min_observations: int,
) -> _ParsedInput:
    """Adjudicate the pinned content pre-create (OD-PA-3-B/C/D, fail-closed, no imputation): one
    subject/currency target series; CURRENCY-only candidate factors paired 1:1 with a return window;
    ``n >= max(min_observations, k + 2)``; every appraisal period covered by every candidate factor
    (compounded). Raises :class:`ProxyWeightInputError` on any ill-formed input."""
    if not desmoothed_raw:
        raise ProxyWeightInputError("no pinned desmoothed-period rows — refused")

    # --- The target series (one subject/currency; ordered by period_start). ---
    portfolios: set[str] = set()
    instruments: set[str] = set()
    currencies: set[str] = set()
    source_runs: set[str] = set()
    periods: list[_Period] = []
    seen_period_starts: set[date] = set()
    for row in desmoothed_raw:
        p_start = date.fromisoformat(str(row["period_start"]))
        p_end = date.fromisoformat(str(row["period_end"]))
        if p_start in seen_period_starts:
            raise ProxyWeightInputError(f"duplicate desmoothed period_start {p_start} — refused")
        seen_period_starts.add(p_start)
        y = parse_strict_decimal(
            row["metric_value"], error=ProxyWeightInputError, field="metric_value"
        )
        currency = str(row["mark_currency"] or "")
        if len(currency) != 3:
            raise ProxyWeightInputError(f"malformed mark_currency {currency!r} — refused")
        portfolios.add(str(row["portfolio_id"]).lower())
        instruments.add(str(row["instrument_id"]).lower())
        currencies.add(currency)
        source_runs.add(str(row["calculation_run_id"]).lower())
        periods.append(_Period(period_start=p_start, period_end=p_end, desmoothed_return=y))
    if len(portfolios) != 1:
        raise ProxyWeightInputError("the pinned target spans multiple portfolios — refused")
    if len(instruments) != 1:
        raise ProxyWeightInputError("the pinned target spans multiple instruments — refused")
    if len(currencies) != 1:
        raise ProxyWeightInputError("the pinned target spans multiple currencies — refused")
    if len(source_runs) != 1:
        raise ProxyWeightInputError("the pinned target spans multiple desmoothed runs — refused")
    periods.sort(key=lambda p: p.period_start)

    # --- The candidate factors (CURRENCY-only; paired with a return window; ordered by id). ---
    if not factor_raw:
        raise ProxyWeightInputError("no candidate factors pinned — refused")
    returns_by_factor: dict[str, list[tuple[date, Decimal]]] = {}
    for fr in factor_return_raw:
        fid = str(fr["factor_id"]).lower()
        rows = [
            (
                date.fromisoformat(str(r["return_date"])),
                parse_strict_decimal(
                    r["return_value"], error=ProxyWeightInputError, field="return_value"
                ),
            )
            for r in fr["rows"]
        ]
        returns_by_factor[fid] = sorted(rows, key=lambda x: x[0])
    candidates: list[_Candidate] = []
    seen_factor_ids: set[str] = set()
    for f in factor_raw:
        fid = str(f["id"]).lower()
        if fid in seen_factor_ids:
            raise ProxyWeightInputError(f"duplicate candidate factor {fid} — refused")
        seen_factor_ids.add(fid)
        if str(f["factor_family"]) != FACTOR_FAMILY_CURRENCY:
            raise ProxyWeightInputError(
                f"candidate factor {f['factor_code']!r} is family {f['factor_family']!r} — "
                f"v1 supports {FACTOR_FAMILY_CURRENCY} only; refused"
            )
        if fid not in returns_by_factor:
            raise ProxyWeightInputError(
                f"candidate factor {f['factor_code']!r} has no pinned return window — refused"
            )
        candidates.append(
            _Candidate(
                factor_id=fid,
                factor_code=str(f["factor_code"]),
                returns=tuple(returns_by_factor[fid]),
            )
        )
    candidates.sort(key=lambda c: c.factor_id)

    # --- Observation floor (declared + structural) + per-period coverage. ---
    n = len(periods)
    k = len(candidates)
    floor = max(int(min_observations), k + 2)
    if n < floor:
        raise ProxyWeightInputError(
            f"{n} appraisal periods for {k} candidate factor(s) — need >= {floor} "
            f"(max(min_observations={min_observations}, k+2)); refused"
        )
    # Every appraisal period must have >= 1 factor return to compound for EVERY candidate (NO
    # zero-fill — the P3-7 named-gap rule). The coverage window is (period_start, period_end].
    for period in periods:
        for cand in candidates:
            covering = [
                value
                for (rdate, value) in cand.returns
                if period.period_start < rdate <= period.period_end
            ]
            if not covering:
                raise ProxyWeightInputError(
                    f"candidate factor {cand.factor_code!r} has no return covering appraisal "
                    f"period ({period.period_start}..{period.period_end}] — refused (NO zero-fill)"
                )
    return _ParsedInput(
        periods=tuple(periods),
        candidates=tuple(candidates),
        portfolio_id=next(iter(portfolios)),
        instrument_id=next(iter(instruments)),
        series_currency=next(iter(currencies)),
        source_desmoothed_run_id=next(iter(source_runs)),
    )


def _build_design(parsed: _ParsedInput) -> tuple[list[Decimal], list[list[Decimal]]]:
    """Build the OLS target ``y`` and the ``k`` factor columns: each period's regressor is the
    factor's returns COMPOUNDED over ``(period_start, period_end]`` (frequency alignment)."""
    y = [p.desmoothed_return for p in parsed.periods]
    columns: list[list[Decimal]] = []
    for cand in parsed.candidates:
        column = [
            _compound(
                [value for (rdate, value) in cand.returns if p.period_start < rdate <= p.period_end]
            )
            for p in parsed.periods
        ]
        columns.append(column)
    return y, columns


def run_proxy_weight_estimate(
    session: Session,
    *,
    acting_tenant: str,
    actor: ProxyWeightEstimateActor,
    code_version: str,
    environment_id: str,
    model_version_id: str,
    desmoothed_run_id: str | None = None,
    factor_ids: list[str] | None = None,
    snapshot_id: str | None = None,
) -> ProxyWeightEstimateRunResult:
    """Run a governed OLS proxy-weight estimation. Build-in-request (default — ``desmoothed_run_id``
    + ``factor_ids``: builds a ``PROXY_WEIGHT_INPUT``) or consume-existing (``snapshot_id``).
    BOTH paths adjudicate the pinned content pre-create."""

    # --- Pre-create prerequisite gate (raise BEFORE create_run => zero run/result/run-audit) ---
    if not code_version:
        raise ProxyWeightInputError("code_version is required (FW-RUN/TR-15)")
    if not environment_id:
        raise ProxyWeightInputError("environment_id is required (FW-RUN/TR-15)")
    if actor is None or not actor.actor_id:
        raise ProxyWeightInputError("initiator is required (FW-RUN/TR-15)")
    if not model_version_id:
        raise ProxyWeightInputError("model_version_id is required (CTRL-003 inventory-before-use)")
    build_args = (desmoothed_run_id, factor_ids)
    if snapshot_id is not None and any(a is not None for a in build_args):
        raise ProxyWeightInputError(
            "ambiguous input — pass either snapshot_id or the build arguments "
            "(desmoothed_run_id/factor_ids), not both"
        )
    version = assert_model_version_of(
        session,
        str(model_version_id),
        tenant_id=acting_tenant,
        expected_model_code=PROXY_WEIGHT_MODEL_CODE,
    )
    min_observations = declared_min_observations(session, version)

    # --- Bind the snapshot (cross-tenant/unknown/ill-formed => pre-create refusal) ---
    if snapshot_id is not None:
        snapshot = resolve_snapshot(session, snapshot_id, acting_tenant=acting_tenant)
        if snapshot.purpose != PURPOSE_PROXY_WEIGHT_INPUT:
            raise ProxyWeightInputError(
                f"snapshot {snapshot_id} purpose {snapshot.purpose!r} "
                f"!= {PURPOSE_PROXY_WEIGHT_INPUT}"
            )
    else:
        if desmoothed_run_id is None or factor_ids is None:
            raise ProxyWeightInputError(
                "desmoothed_run_id + factor_ids are both required to build a proxy-weight snapshot"
            )
        snapshot = build_proxy_weight_snapshot(
            session,
            acting_tenant=acting_tenant,
            actor=SnapshotActor(actor_id=actor.actor_id, actor_type=actor.actor_type),
            desmoothed_run_id=str(desmoothed_run_id),
            factor_ids=list(factor_ids),
        )

    # --- Adjudicate the PINNED content pre-create (uniform for both paths). ---
    try:
        desmoothed_raw, factor_raw, factor_return_raw = _parse_pins(
            list_components(session, snapshot_id=snapshot.id, acting_tenant=acting_tenant)
        )
        parsed = _adjudicate_pins(
            desmoothed_raw, factor_raw, factor_return_raw, min_observations=min_observations
        )
    except ProxyWeightInputError:
        raise
    except (KeyError, TypeError, ValueError, ArithmeticError) as exc:
        raise ProxyWeightInputError(
            f"pinned content is not a well-formed v1 input ({type(exc).__name__})"
        ) from exc

    # Re-resolve the measured subject from the PINNED content under the acting tenant BEFORE
    # anything is stamped into a hard-FK column (PG FK checks bypass RLS — the P3-5 finding).
    assert_portfolio_in_tenant(
        session, parsed.portfolio_id, acting_tenant=acting_tenant, error=ProxyWeightInputError
    )
    assert_instrument_in_tenant(
        session, parsed.instrument_id, acting_tenant=acting_tenant, error=ProxyWeightInputError
    )

    # Fit pre-create so a STRUCTURAL failure (singular / constant / insufficient) is a 422 refusal
    # (OD-PA-3-C/D) — the magnitude gate below is the only post-RUNNING (committed-FAILED) outcome.
    y, columns = _build_design(parsed)
    try:
        fit = estimate_ols(y, columns)
    except ProxyWeightKernelError as exc:
        raise ProxyWeightInputError(f"regression refused ({exc.reason}): {exc}") from exc

    def _compute(run: CalculationRun) -> tuple[list[ProxyWeightEstimateResult], list[str]]:
        gaps: list[str] = []
        # The raw prec-50 fit clears the Numeric(20,12) envelope BEFORE quantize (the recurring
        # detonation class) — an out-of-range coefficient/error is a committed FAILED run.
        raw_values = [*fit.coefficients, *fit.std_errors, fit.r_squared, fit.residual_stdev]
        if any(abs(v) >= _MAX_RESULT_ABS for v in raw_values):
            gaps.append("magnitude-out-of-range:coefficient-or-error")
            return [], gaps

        def _base(**kw: Any) -> ProxyWeightEstimateResult:
            return ProxyWeightEstimateResult(
                tenant_id=str(acting_tenant),
                calculation_run_id=run.run_id,
                input_snapshot_id=snapshot.id,
                model_version_id=str(model_version_id),
                portfolio_id=parsed.portfolio_id,
                instrument_id=parsed.instrument_id,
                source_desmoothed_run_id=parsed.source_desmoothed_run_id,
                min_observations=int(min_observations),
                series_currency=parsed.series_currency,
                **kw,
            )

        rows: list[ProxyWeightEstimateResult] = [
            _base(
                metric_type=METRIC_TYPE_INTERCEPT,
                factor_id=None,
                metric_value=fit.coefficients[0].quantize(_RESULT_QUANTUM),
                std_error=fit.std_errors[0].quantize(_RESULT_QUANTUM),
            )
        ]
        for j, cand in enumerate(parsed.candidates):
            rows.append(
                _base(
                    metric_type=METRIC_TYPE_WEIGHT,
                    factor_id=cand.factor_id,
                    metric_value=fit.coefficients[j + 1].quantize(_RESULT_QUANTUM),
                    std_error=fit.std_errors[j + 1].quantize(_RESULT_QUANTUM),
                )
            )
        rows.append(
            _base(
                metric_type=METRIC_TYPE_ESTIMATION_SUMMARY,
                factor_id=None,
                metric_value=fit.r_squared.quantize(_RESULT_QUANTUM),
                std_error=None,
                n_observations=fit.n_observations,
                n_regressors=fit.n_regressors,
                residual_stdev=fit.residual_stdev.quantize(_RESULT_QUANTUM),
            )
        )
        return rows, gaps

    outcome = execute_governed_run(
        session,
        acting_tenant=str(acting_tenant),
        actor_id=actor.actor_id,
        actor_type=actor.actor_type,
        run_type=RUN_TYPE_PROXY_WEIGHT_ESTIMATE,
        snapshot_id=snapshot.id,
        model_version_id=str(model_version_id),
        code_version=code_version,
        environment_id=environment_id,
        rule_code=_COMPLETENESS_RULE_CODE,
        rule_name="proxy-weight estimate sanity (values within the Numeric(20,12) scale)",
        rule_target_entity_type="proxy_weight_estimate_result",
        result_entity_type="proxy_weight_estimate_result",
        compute=_compute,
        format_reason=lambda gate, gaps: f"{gate} — {'; '.join(gaps)}",
    )
    return ProxyWeightEstimateRunResult(
        run=outcome.run,
        status=outcome.status,
        rows=list(outcome.rows),
        failure_reason=outcome.failure_reason,
    )


def list_proxy_weight_results(
    session: Session, run_id: str, *, acting_tenant: str
) -> list[ProxyWeightEstimateResult]:
    """The ``proxy_weight_estimate_result`` rows of a run (tenant-scoped; stable
    ``(metric_type, factor_id)`` order)."""
    return list(
        session.execute(
            select(ProxyWeightEstimateResult)
            .where(
                ProxyWeightEstimateResult.calculation_run_id == str(run_id),
                ProxyWeightEstimateResult.tenant_id == str(acting_tenant),
            )
            .order_by(ProxyWeightEstimateResult.metric_type, ProxyWeightEstimateResult.factor_id)
        )
        .scalars()
        .all()
    )


def resolve_proxy_weight_run(
    session: Session, run_id: str, *, acting_tenant: str
) -> CalculationRun:
    """Resolve a PROXY_WEIGHT_ESTIMATE ``calculation_run`` by id (tenant + run_type predicated;
    fail-closed — the RD-1 shared resolver)."""
    return resolve_run_of_type(
        session,
        run_id,
        acting_tenant=acting_tenant,
        run_type=RUN_TYPE_PROXY_WEIGHT_ESTIMATE,
        not_visible=ProxyWeightEstimateRunNotVisible,
    )


def promote_proxy_weight_estimate(
    session: Session,
    *,
    private_instrument_id: str,
    factor_id: str,
    weight: Decimal,
    acting_tenant: str,
    actor: ProxyMappingActor,
    source_calculation_run_id: str,
    valid_from: datetime | None = None,
) -> ProxyMapping:
    """Promote a REVIEWED estimate into a live captured proxy weight (OD-PA-3-E, the deliberate
    analyst-mediated second step). Resolves the cited run to a tenant-visible COMPLETED
    ``PROXY_WEIGHT_ESTIMATE`` run — the run-TYPE gate that ``marketdata`` cannot see (the captured-
    input fence) — then captures a ``REGRESSION``-method ``proxy_mapping`` row citing it. The
    ``weight`` is supplied by the caller (the analyst's chosen coefficient), NOT read from the run:
    the human decides which estimated loading to promote and at what value."""
    run = resolve_completed_run_of_type(
        session,
        source_calculation_run_id,
        acting_tenant=acting_tenant,
        run_type=RUN_TYPE_PROXY_WEIGHT_ESTIMATE,
        label="proxy-weight estimate",
        error=ProxyWeightInputError,
    )
    return capture_proxy_mapping(
        session,
        private_instrument_id=private_instrument_id,
        factor_id=factor_id,
        weight=weight,
        acting_tenant=acting_tenant,
        actor=actor,
        mapping_method=MAPPING_METHOD_REGRESSION,
        source_calculation_run_id=str(run.run_id),
        valid_from=valid_from,
    )
