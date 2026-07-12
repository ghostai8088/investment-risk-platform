"""Desmoothed-return run service (PA-1, ENT-056) — the ELEVENTH governed number: Geltner AR(1)
unsmoothing of a captured private-asset appraisal mark series (the differentiation-thesis payload).

``run_desmoothed_return`` computes the observed simple-return series from the PINNED current-head
``valuation`` marks of ONE (portfolio, instrument) window, inverts it per period
(``r_t = (r_a,t − (1−α)·r_a,t−1)/α`` — the kernel), and persists ``n−2`` per-period
``DESMOOTHED_PERIOD`` rows (for ``n`` marks: ``n−1`` observed returns, the first seeding the
recursion) + ONE ``DESMOOTHING_SUMMARY`` row carrying the honest-uncertainty stdev pair
(desmoothed vs observed over the SAME periods — OD-PA-1-C). Build-in-request (``portfolio_id`` +
``instrument_id`` + ``window_start/end`` → builds a ``DESMOOTHING_INPUT`` snapshot) or
consume-existing (``snapshot_id``); BOTH paths adjudicate the PINNED content pre-create (AD-014 —
never a live read; a later mark correction cannot move a historical run, TR-09).

The declared ``alpha`` (0 < α ≤ 1) is the MODEL identity (OD-PA-1-E) — parsed back from the
registered version's ``model_assumption`` rows, never a request parameter — and echoed on every
persisted row as evidence.

Failure model (the established governed-run shape):
- **Pre-create refusal (422, its own ``DesmoothingInputError``)** — missing prerequisite,
  ambiguous input, wrong-purpose/cross-tenant snapshot, structurally malformed pinned content,
  fewer than 4 marks, a non-positive mark, duplicate valuation dates, a mixed-currency /
  mixed-portfolio / mixed-instrument series (OD-PA-1-H). NO run, NO result, NO run-audit.
- **Post-create FAILED (magnitude gate)** — a committed FAILED run + ZERO rows + a naming
  ``failure_reason``. Every persisted ``Numeric(20,12)`` value clears ``_MAX_RESULT_ABS`` (the
  PM-1 envelope gate).

Reuses ``perf.run``/``perf.view`` (no mint) + ``CALC.RUN_*`` (``PERF.DESMOOTHED_RETURN_CREATE``
reserved-not-emitted). One-way imports: ``perf -> {snapshot, calc, model, portfolio.guards}``;
imports NO ``risk`` symbol.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from irp_shared.calc.models import CalculationRun
from irp_shared.calc.parse import parse_strict_decimal
from irp_shared.calc.runs import resolve_run_of_type
from irp_shared.calc.scaffold import execute_governed_run
from irp_shared.model.service import assert_model_version_of
from irp_shared.perf.benchmark_relative_kernel import sample_stdev
from irp_shared.perf.bootstrap import (
    DESMOOTHED_RETURN_MODEL_CODE,
    declared_desmoothing_alpha,
)
from irp_shared.perf.desmoothing_kernel import desmooth_geltner, observed_returns
from irp_shared.perf.events import RUN_TYPE_DESMOOTHED_RETURN, DesmoothedReturnActor
from irp_shared.perf.models import (
    METRIC_TYPE_DESMOOTHED_PERIOD,
    METRIC_TYPE_DESMOOTHING_SUMMARY,
    DesmoothedReturnResult,
)
from irp_shared.portfolio.guards import assert_portfolio_in_tenant
from irp_shared.snapshot import (
    COMPONENT_KIND_VALUATION,
    PURPOSE_DESMOOTHING_INPUT,
    SnapshotActor,
    build_desmoothing_snapshot,
    list_components,
    resolve_snapshot,
)

#: Per-tenant governed completeness DQ rule (resolve-or-register; the established pattern).
_COMPLETENESS_RULE_CODE = "perf.desmoothed_return.completeness"
#: The Numeric(20,12) ceiling is |value| < 1E8; the gate bounds EVERY persisted return-scale value
#: (metric_value, observed_return, observed_stdev — the P3-8/BT-1 echo lesson baked in from birth;
#: alpha is domain-bounded ≤ 1 at registration).
_MAX_RESULT_ABS = Decimal("1E8")
#: The OD-PA-1-H series-quality floor: 4 marks → 3 observed returns → 2 desmoothed returns → a
#: meaningful (n−1) summary stdev.
_MIN_MARKS = 4


class DesmoothingInputError(Exception):
    """A missing/invalid prerequisite detected BEFORE the run is created — pre-create refusal (no
    run, no result, no run-audit). Its OWN class. Maps to 422."""


class DesmoothedReturnResultNotVisible(Exception):
    """Raised when a ``desmoothed_return_result`` id is not visible in the acting tenant scope."""

    def __init__(self, result_id: str) -> None:
        super().__init__(
            f"desmoothed_return_result {result_id} is not visible in the current tenant"
        )
        self.result_id = str(result_id)


class DesmoothedReturnRunNotVisible(Exception):
    """Raised when a desmoothed-return ``calculation_run`` id is not visible in the tenant."""

    def __init__(self, run_id: str) -> None:
        super().__init__(f"desmoothed-return run {run_id} is not visible in the current tenant")
        self.run_id = str(run_id)


@dataclass(frozen=True)
class DesmoothedReturnRunResult:
    """The outcome of ``run_desmoothed_return``: the ``calculation_run`` + status + result rows.
    ``status`` is ``COMPLETED`` (``rows`` = the per-period rows + the summary) or ``FAILED``
    (the magnitude gate: a committed FAILED run + ZERO rows + a naming ``failure_reason``)."""

    run: CalculationRun
    status: str
    rows: list[DesmoothedReturnResult] = field(default_factory=list)
    failure_reason: str | None = None


@dataclass(frozen=True)
class _Mark:
    """One adjudicated pinned appraisal mark."""

    valuation_date: date
    mark_value: Decimal


@dataclass(frozen=True)
class _ParsedInput:
    """Adjudicated pinned input: the date-ordered mark series + run-uniform descriptors."""

    marks: list[_Mark]  # ordered by valuation_date, unique dates, strictly positive
    portfolio_id: str
    instrument_id: str
    mark_currency: str


def _parse_pins(comps: list[Any]) -> list[dict[str, Any]]:
    """Parse the pinned ``captured_content`` into raw mark dicts (PURE — no live read; AD-014)."""
    return [
        json.loads(comp.captured_content)
        for comp in comps
        if comp.component_kind == COMPONENT_KIND_VALUATION
    ]


def _adjudicate_pins(mark_raw: list[dict[str, Any]]) -> _ParsedInput:
    """Adjudicate the pinned content pre-create (OD-PA-1-H, fail-closed, NO imputation): >= 4
    marks; unique valuation dates; strictly positive parse-hardened mark values; ONE portfolio /
    instrument / currency. Raises :class:`DesmoothingInputError` on any ill-formed input."""
    if len(mark_raw) < _MIN_MARKS:
        raise DesmoothingInputError(
            f"{len(mark_raw)} pinned mark(s) — need >= {_MIN_MARKS} (3 observed returns => 2 "
            f"desmoothed returns => a meaningful summary stdev); refused"
        )
    portfolios: set[str] = set()
    instruments: set[str] = set()
    currencies: set[str] = set()
    seen_dates: set[str] = set()
    marks: list[_Mark] = []
    for row in mark_raw:
        date_text = str(row["valuation_date"])
        if date_text in seen_dates:
            raise DesmoothingInputError(
                f"duplicate valuation_date {date_text} in the pinned mark series — refused"
            )
        seen_dates.add(date_text)
        value = parse_strict_decimal(
            row["mark_value"], error=DesmoothingInputError, field="mark_value"
        )
        if value <= 0:
            raise DesmoothingInputError(
                f"mark_value {value} at {date_text} is not strictly positive — a simple return "
                f"is undefined; refused (NO imputation)"
            )
        currency = row["currency_code"]
        if not currency:
            raise DesmoothingInputError(f"mark at {date_text} has no currency_code — refused")
        portfolios.add(str(row["portfolio_id"]).lower())
        instruments.add(str(row["instrument_id"]).lower())
        currencies.add(str(currency))
        marks.append(_Mark(valuation_date=date.fromisoformat(date_text), mark_value=value))
    if len(portfolios) != 1:
        raise DesmoothingInputError("the pinned marks span multiple portfolios — refused")
    if len(instruments) != 1:
        raise DesmoothingInputError("the pinned marks span multiple instruments — refused")
    if len(currencies) != 1:
        raise DesmoothingInputError(
            f"the pinned marks span multiple currencies {sorted(currencies)} — no FX translation "
            f"in v1; refused"
        )
    marks.sort(key=lambda m: m.valuation_date)
    return _ParsedInput(
        marks=marks,
        portfolio_id=next(iter(portfolios)),
        instrument_id=next(iter(instruments)),
        mark_currency=next(iter(currencies)),
    )


def run_desmoothed_return(
    session: Session,
    *,
    acting_tenant: str,
    actor: DesmoothedReturnActor,
    code_version: str,
    environment_id: str,
    model_version_id: str,
    portfolio_id: str | None = None,
    instrument_id: str | None = None,
    window_start: date | None = None,
    window_end: date | None = None,
    snapshot_id: str | None = None,
) -> DesmoothedReturnRunResult:
    """Run a governed Geltner desmoothing. Build-in-request (default — the four build args
    together: builds a ``DESMOOTHING_INPUT``) or consume-existing (``snapshot_id``). BOTH paths
    adjudicate the pinned content pre-create."""

    # --- Pre-create prerequisite gate (raise BEFORE create_run => zero run/result/run-audit) ---
    if not code_version:
        raise DesmoothingInputError("code_version is required (FW-RUN/TR-15)")
    if not environment_id:
        raise DesmoothingInputError("environment_id is required (FW-RUN/TR-15)")
    if actor is None or not actor.actor_id:
        raise DesmoothingInputError("initiator is required (FW-RUN/TR-15)")
    if not model_version_id:
        raise DesmoothingInputError("model_version_id is required (CTRL-003 inventory-before-use)")
    build_args = (portfolio_id, instrument_id, window_start, window_end)
    if snapshot_id is not None and any(a is not None for a in build_args):
        raise DesmoothingInputError(
            "ambiguous input — pass either snapshot_id or the build arguments "
            "(portfolio_id/instrument_id/window_start/window_end), not both"
        )
    # Inventory-before-use + model identity (CTRL-003 / OD-PA-1-E) + the declared-alpha parse-back.
    version = assert_model_version_of(
        session,
        str(model_version_id),
        tenant_id=acting_tenant,
        expected_model_code=DESMOOTHED_RETURN_MODEL_CODE,
    )
    alpha = declared_desmoothing_alpha(session, version)

    # --- Bind the snapshot (cross-tenant/unknown/ill-formed => pre-create refusal) ---
    if snapshot_id is not None:
        snapshot = resolve_snapshot(session, snapshot_id, acting_tenant=acting_tenant)
        if snapshot.purpose != PURPOSE_DESMOOTHING_INPUT:
            raise DesmoothingInputError(
                f"snapshot {snapshot_id} purpose {snapshot.purpose!r} != "
                f"{PURPOSE_DESMOOTHING_INPUT}"
            )
    else:
        if any(a is None for a in build_args):
            raise DesmoothingInputError(
                "portfolio_id + instrument_id + window_start + window_end are all required to "
                "build a desmoothing snapshot"
            )
        snapshot = build_desmoothing_snapshot(
            session,
            acting_tenant=acting_tenant,
            actor=SnapshotActor(actor_id=actor.actor_id, actor_type=actor.actor_type),
            portfolio_id=str(portfolio_id),
            instrument_id=str(instrument_id),
            window_start=window_start,
            window_end=window_end,
        )

    # --- Adjudicate the PINNED content pre-create (uniform for both paths). ---
    try:
        parsed = _adjudicate_pins(
            _parse_pins(
                list_components(session, snapshot_id=snapshot.id, acting_tenant=acting_tenant)
            )
        )
    except DesmoothingInputError:
        raise
    except (KeyError, TypeError, ValueError, ArithmeticError) as exc:
        # Structurally malformed pinned content is the SAME refusal class as a semantically bad
        # input — a governed 422, never a raw parse 500 (the P3-C3 wrapper).
        raise DesmoothingInputError(
            f"pinned content is not a well-formed v1 input ({type(exc).__name__})"
        ) from exc

    # Re-resolve the measured subject from the PINNED content under the acting tenant BEFORE
    # anything is stamped into a hard-FK column (PG FK checks bypass RLS — the P3-5 finding).
    assert_portfolio_in_tenant(
        session, parsed.portfolio_id, acting_tenant=acting_tenant, error=DesmoothingInputError
    )
    _assert_instrument_in_tenant(session, parsed.instrument_id, acting_tenant=acting_tenant)

    # --- The shared governed-run lifecycle (P3-C1 scaffold; behavior-preserving) ---
    def _compute(run: CalculationRun) -> tuple[list[DesmoothedReturnResult], list[str]]:
        gaps: list[str] = []
        marks = parsed.marks
        observed = observed_returns([m.mark_value for m in marks])
        desmoothed = desmooth_geltner(observed, alpha)
        # desmoothed[j] pairs observed (j, j+1) => the mark pair (marks[j+1], marks[j+2]).
        rows: list[DesmoothedReturnResult] = []
        for j, value in enumerate(desmoothed):
            r_obs = observed[j + 1]
            if any(abs(v) >= _MAX_RESULT_ABS for v in (value, r_obs)):
                gaps.append(f"magnitude-out-of-range:period:{marks[j + 2].valuation_date}")
                return [], gaps
            rows.append(
                DesmoothedReturnResult(
                    tenant_id=str(acting_tenant),
                    calculation_run_id=run.run_id,
                    input_snapshot_id=snapshot.id,
                    model_version_id=str(model_version_id),
                    portfolio_id=parsed.portfolio_id,
                    instrument_id=parsed.instrument_id,
                    metric_type=METRIC_TYPE_DESMOOTHED_PERIOD,
                    period_start=marks[j + 1].valuation_date,
                    period_end=marks[j + 2].valuation_date,
                    metric_value=value,
                    observed_return=r_obs,
                    begin_mark=marks[j + 1].mark_value,
                    end_mark=marks[j + 2].mark_value,
                    alpha=alpha,
                    mark_currency=parsed.mark_currency,
                )
            )
        # The honest-uncertainty pair over the SAME periods the desmoothed series covers
        # (observed[1:] aligns 1:1 with desmoothed — like-for-like, OD-PA-1-C).
        desmoothed_stdev = sample_stdev(desmoothed)
        obs_stdev = sample_stdev(observed[1:])
        if any(abs(v) >= _MAX_RESULT_ABS for v in (desmoothed_stdev, obs_stdev)):
            gaps.append("magnitude-out-of-range:summary-stdev")
            return [], gaps
        rows.append(
            DesmoothedReturnResult(
                tenant_id=str(acting_tenant),
                calculation_run_id=run.run_id,
                input_snapshot_id=snapshot.id,
                model_version_id=str(model_version_id),
                portfolio_id=parsed.portfolio_id,
                instrument_id=parsed.instrument_id,
                metric_type=METRIC_TYPE_DESMOOTHING_SUMMARY,
                period_start=marks[1].valuation_date,  # the first desmoothed period's start
                period_end=marks[-1].valuation_date,
                metric_value=desmoothed_stdev,
                observed_return=None,
                begin_mark=None,
                end_mark=None,
                alpha=alpha,
                mark_currency=parsed.mark_currency,
                observed_stdev=obs_stdev,
                n_periods=len(desmoothed),
            )
        )
        return rows, gaps

    outcome = execute_governed_run(
        session,
        acting_tenant=str(acting_tenant),
        actor_id=actor.actor_id,
        actor_type=actor.actor_type,
        run_type=RUN_TYPE_DESMOOTHED_RETURN,
        snapshot_id=snapshot.id,
        model_version_id=str(model_version_id),
        code_version=code_version,
        environment_id=environment_id,
        rule_code=_COMPLETENESS_RULE_CODE,
        rule_name="desmoothed-return output sanity (values within the Numeric(20,12) scale)",
        rule_target_entity_type="desmoothed_return_result",
        result_entity_type="desmoothed_return_result",
        compute=_compute,
        format_reason=lambda gate, gaps: f"{gate} — {'; '.join(gaps)}",
    )
    return DesmoothedReturnRunResult(
        run=outcome.run,
        status=outcome.status,
        rows=list(outcome.rows),
        failure_reason=getattr(outcome, "failure_reason", None),
    )


def _assert_instrument_in_tenant(
    session: Session, instrument_id: str, *, acting_tenant: str
) -> None:
    """Re-resolve the instrument under the acting tenant BEFORE its id is stamped into the hard FK
    (the P3-5 cross-tenant-FK guard; models-only import — no cycle)."""
    from irp_shared.reference.models import Instrument

    row = session.execute(
        select(Instrument.id).where(
            Instrument.id == str(instrument_id),
            Instrument.tenant_id == str(acting_tenant),
        )
    ).one_or_none()
    if row is None:
        raise DesmoothingInputError(
            f"instrument {instrument_id} is not visible in the acting tenant — refused"
        )


def list_desmoothed_results(
    session: Session, run_id: str, *, acting_tenant: str
) -> list[DesmoothedReturnResult]:
    """The ``desmoothed_return_result`` rows of a run (tenant-scoped; per-period rows in date
    order, then the summary)."""
    return list(
        session.execute(
            select(DesmoothedReturnResult)
            .where(
                DesmoothedReturnResult.calculation_run_id == str(run_id),
                DesmoothedReturnResult.tenant_id == str(acting_tenant),
            )
            .order_by(DesmoothedReturnResult.metric_type, DesmoothedReturnResult.period_start)
        )
        .scalars()
        .all()
    )


def resolve_desmoothed_result(
    session: Session, result_id: str, *, acting_tenant: str
) -> DesmoothedReturnResult:
    """Resolve one ``desmoothed_return_result`` row by id with an EXPLICIT tenant predicate
    (fail-closed). Raises :class:`DesmoothedReturnResultNotVisible` on a hidden/unknown id."""
    row = session.execute(
        select(DesmoothedReturnResult).where(
            DesmoothedReturnResult.id == str(result_id),
            DesmoothedReturnResult.tenant_id == str(acting_tenant),
        )
    ).scalar_one_or_none()
    if row is None:
        raise DesmoothedReturnResultNotVisible(str(result_id))
    return row


def resolve_desmoothed_return_run(
    session: Session, run_id: str, *, acting_tenant: str
) -> CalculationRun:
    """Resolve a DESMOOTHED_RETURN ``calculation_run`` by id (tenant + run_type predicated;
    fail-closed — the RD-1 shared resolver)."""
    return resolve_run_of_type(
        session,
        run_id,
        acting_tenant=acting_tenant,
        run_type=RUN_TYPE_DESMOOTHED_RETURN,
        not_visible=DesmoothedReturnRunNotVisible,
    )
