"""Limit/breach service (LIM-1) — the metric map + guards, the breach predicate, the evaluator,
and the audited limit CRUD.

Layers:
- **The hardcoded metric map** (``_METRIC_MAP``) — the ONLY thing that disarms the unit landmine
  (OD-C): a ``(run_type, metric_type)`` resolves to a FIXED result column + unit + benchmark-need,
  never a user column. The evaluator asserts ``spec.unit == limit.threshold_unit`` fail-closed.
- **The breach predicate** (``_breaches``) — ``breach_direction`` names the BREACH condition
  directly (ABOVE ⟺ observed > threshold; BELOW ⟺ observed < threshold; strict boundary — OD-D).
- **The evaluator** (``evaluate_limit``) — discovery via ``calc/reads`` over ``calculation_run``
  (NOT ``scheduled_run`` — so MANUAL runs are limit-checked too, Fable demand #1); idempotent on
  ``(limit_id, calculation_run_id)``; appends a SELF-DESCRIBING ``breach`` + ``BREACH.DETECT``.
- **Audited CRUD** (``create_limit``/``update_limit``) — EV in place; ``LIMIT.DEFINE``/
  ``LIMIT.CHANGE`` emitted caller-side to the FROZEN ``record_event``. Identity frozen (OD-I).
- **``limit_health``** (OD-L) — a read distinguishing IN_APPETITE / NEVER_EVALUABLE / BREACHED
  so an un-evaluable limit is never silently green.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from irp_shared.audit.actions import ACTION_CREATE, ACTION_RECORD, ACTION_UPDATE
from irp_shared.audit.payload import json_safe
from irp_shared.audit.service import record_event
from irp_shared.limit.events import (
    BREACH_ABOVE,
    BREACH_BELOW,
    BREACH_DETECT_EVENT,
    BREACH_DIRECTIONS,
    BREACH_STATUS_DETECTED,
    ENTITY_BREACH,
    ENTITY_LIMIT_DEFINITION,
    LIMIT_CHANGE_EVENT,
    LIMIT_DEFINE_EVENT,
    LIMIT_KIND_HARD,
    LIMIT_KINDS,
    LIMIT_STATUS_ACTIVE,
    LIMIT_STATUS_SUSPENDED,
    LIMIT_STATUSES,
    SOURCE_MODULE_LIMIT,
    THRESHOLD_UNIT_CURRENCY,
    THRESHOLD_UNIT_FRACTION,
    LimitActor,
)
from irp_shared.limit.models import Breach, LimitDefinition
from irp_shared.marketdata.benchmark import BenchmarkNotVisible, resolve_benchmark
from irp_shared.portfolio.guards import assert_portfolio_in_tenant
from irp_shared.risk.active_risk_service import latest_active_risk_for_portfolio
from irp_shared.risk.events import (
    METRIC_TYPE_ES_HISTORICAL,
    METRIC_TYPE_ES_PARAMETRIC,
    METRIC_TYPE_TRACKING_ERROR,
    METRIC_TYPE_VAR_HISTORICAL,
    METRIC_TYPE_VAR_PARAMETRIC,
    METRIC_TYPE_VAR_PARAMETRIC_TOTAL,
    METRIC_TYPE_VAR_PARAMETRIC_UNIFIED,
    RUN_TYPE_ACTIVE_RISK,
    RUN_TYPE_VAR,
)
from irp_shared.risk.var_service import latest_var_for_portfolio

#: The audit ``entity_type`` tags (re-exported from events for the emit helpers).
_ENTITY_LIMIT = ENTITY_LIMIT_DEFINITION
_ENTITY_BREACH = ENTITY_BREACH


class LimitError(ValueError):
    """A limit config or evaluation precondition failure (fail-closed)."""


@dataclass(frozen=True)
class MetricSpec:
    """The FIXED (result column, unit, benchmark-need) a ``(run_type, metric_type)`` thresholds."""

    result_attr: str
    unit: str
    requires_benchmark: bool


#: The HARDCODED metric map (OD-C) — the single defense that disarms the unit landmine. NOT
#: user-choosable: a ``(run_type, metric_type)`` maps to exactly ONE column + unit. VaR flavors
#: (incl. ES_* rows, whose ``var_value`` holds the ES) are CURRENCY; tracking error is a FRACTION.
_METRIC_MAP: dict[tuple[str, str], MetricSpec] = {
    (RUN_TYPE_VAR, METRIC_TYPE_VAR_PARAMETRIC): MetricSpec(
        "var_value", THRESHOLD_UNIT_CURRENCY, False
    ),
    (RUN_TYPE_VAR, METRIC_TYPE_VAR_HISTORICAL): MetricSpec(
        "var_value", THRESHOLD_UNIT_CURRENCY, False
    ),
    (RUN_TYPE_VAR, METRIC_TYPE_VAR_PARAMETRIC_TOTAL): MetricSpec(
        "var_value", THRESHOLD_UNIT_CURRENCY, False
    ),
    (RUN_TYPE_VAR, METRIC_TYPE_VAR_PARAMETRIC_UNIFIED): MetricSpec(
        "var_value", THRESHOLD_UNIT_CURRENCY, False
    ),
    (RUN_TYPE_VAR, METRIC_TYPE_ES_PARAMETRIC): MetricSpec(
        "var_value", THRESHOLD_UNIT_CURRENCY, False
    ),
    (RUN_TYPE_VAR, METRIC_TYPE_ES_HISTORICAL): MetricSpec(
        "var_value", THRESHOLD_UNIT_CURRENCY, False
    ),
    (RUN_TYPE_ACTIVE_RISK, METRIC_TYPE_TRACKING_ERROR): MetricSpec(
        "te_value", THRESHOLD_UNIT_FRACTION, True
    ),
}

#: In-place editable head attributes (OD-I): the config knobs. The IDENTITY fields
#: (``target_run_type``/``metric_type``/``scope_portfolio_id``/``benchmark_id``/``threshold_unit``)
#: are FROZEN — a re-target is a NEW limit (keeps a breach's echo meaningful).
_UPDATABLE = ("name", "threshold_value", "limit_kind", "breach_direction", "status")


# --- breach predicate ---------------------------------------------------------------------
def _breaches(observed: Decimal, threshold: Decimal, breach_direction: str) -> bool:
    """The safety-critical predicate (OD-D). ``breach_direction`` names the BREACH condition; strict
    boundary (``observed == threshold`` is COMPLIANT)."""
    if breach_direction == BREACH_ABOVE:
        return observed > threshold
    if breach_direction == BREACH_BELOW:
        return observed < threshold
    raise LimitError(f"unknown breach_direction {breach_direction!r}")


# --- discovery ----------------------------------------------------------------------------
def _resolve_latest(session: Session, limit: LimitDefinition) -> tuple[str, Decimal] | None:
    """Resolve the latest COMPLETED result for the limit's ``(run_type, scope, metric[, bmk])``
    and return ``(calculation_run_id, observed_value)`` — or None when no matching run exists (the
    NEVER-EVALUABLE / metric-cold case). Discovery is ``calculation_run``-driven (demand #1)."""
    spec = _spec_for(limit)
    if spec.unit != limit.threshold_unit:
        # Defense-in-depth (identity is frozen, so the create-time guard normally holds): a
        # CURRENCY threshold must NEVER be compared against a FRACTION metric (or vice versa).
        raise LimitError(
            f"unit drift: threshold_unit {limit.threshold_unit!r} != metric unit {spec.unit!r}"
        )
    tenant = limit.tenant_id
    rows: list[Any]
    if limit.target_run_type == RUN_TYPE_VAR:
        rows = latest_var_for_portfolio(
            session,
            acting_tenant=tenant,
            portfolio_id=limit.scope_portfolio_id,
            metric_type=limit.metric_type,
        )
    else:  # RUN_TYPE_ACTIVE_RISK (the only other admitted family)
        rows = latest_active_risk_for_portfolio(
            session,
            acting_tenant=tenant,
            portfolio_id=limit.scope_portfolio_id,
            benchmark_id=limit.benchmark_id,
        )
    matching = [r for r in rows if r.metric_type == limit.metric_type]
    if not matching:
        return None
    row = matching[0]
    observed = getattr(row, spec.result_attr)
    return str(row.calculation_run_id), Decimal(observed)


def _spec_for(limit: LimitDefinition) -> MetricSpec:
    spec = _METRIC_MAP.get((limit.target_run_type, limit.metric_type))
    if spec is None:
        raise LimitError(
            f"({limit.target_run_type}, {limit.metric_type}) is not a schedulable v1 metric"
        )
    return spec


# --- evaluation ---------------------------------------------------------------------------
def select_active_limits(session: Session, *, acting_tenant: str) -> list[LimitDefinition]:
    """Tenant-scoped: ACTIVE limits (explicit tenant predicate + RLS — belt-and-suspenders)."""
    return list(
        session.execute(
            select(LimitDefinition).where(
                LimitDefinition.status == LIMIT_STATUS_ACTIVE,
                LimitDefinition.tenant_id == str(acting_tenant),
            )
        ).scalars()
    )


def evaluate_limit(session: Session, limit: LimitDefinition, now: datetime) -> Breach | None:
    """Evaluate ONE ACTIVE limit against its latest matching COMPLETED run; append a SELF-DESCRIBING
    ``breach`` (+ ``BREACH.DETECT``) if it breaches AND has not already been recorded for that run.
    Idempotent on ``(limit_id, calculation_run_id)`` (the unique constraint is the backstop)."""
    resolved = _resolve_latest(session, limit)
    if resolved is None:
        return None  # no matching COMPLETED run — nothing to evaluate this tick
    run_id, observed = resolved
    if not _breaches(observed, Decimal(limit.threshold_value), limit.breach_direction):
        return None  # within appetite

    existing = session.execute(
        select(Breach).where(
            Breach.limit_definition_id == limit.id,
            Breach.calculation_run_id == run_id,
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing  # already recorded this (limit, run) — idempotent

    breach = Breach(
        tenant_id=limit.tenant_id,
        limit_definition_id=limit.id,
        calculation_run_id=run_id,
        detected_at=now,
        target_run_type=limit.target_run_type,
        metric_type=limit.metric_type,
        benchmark_id=limit.benchmark_id,
        observed_value=observed,
        threshold_value=Decimal(limit.threshold_value),
        threshold_unit=limit.threshold_unit,
        breach_direction=limit.breach_direction,
        limit_kind=limit.limit_kind,
        severity=limit.limit_kind,
        status=BREACH_STATUS_DETECTED,
    )
    session.add(breach)
    session.flush()
    _record_breach_event(session, breach=breach, actor_id=f"limit-eval:{limit.id}")
    return breach


# --- limit CRUD ---------------------------------------------------------------------------
def _validate_config(
    *,
    target_run_type: str,
    metric_type: str,
    benchmark_id: str | None,
    threshold_unit: str,
    threshold_value: Decimal,
    breach_direction: str,
    limit_kind: str,
    status: str,
) -> None:
    spec = _METRIC_MAP.get((target_run_type, metric_type))
    if spec is None:
        raise LimitError(f"({target_run_type}, {metric_type}) is not a v1 metric selector")
    if threshold_unit != spec.unit:
        raise LimitError(
            f"threshold_unit {threshold_unit!r} != the {metric_type} metric unit {spec.unit!r}"
        )
    if spec.requires_benchmark and not benchmark_id:
        raise LimitError(f"metric {metric_type} requires a benchmark_id")
    if not spec.requires_benchmark and benchmark_id:
        raise LimitError(f"metric {metric_type} does not take a benchmark_id")
    if breach_direction not in BREACH_DIRECTIONS:
        raise LimitError(f"breach_direction {breach_direction!r} is invalid")
    if limit_kind not in LIMIT_KINDS:
        raise LimitError(f"limit_kind {limit_kind!r} is invalid")
    if status not in LIMIT_STATUSES:
        raise LimitError(f"status {status!r} is invalid")
    if Decimal(threshold_value) <= 0:  # coerce (a str/float caller must not raise a raw TypeError)
        raise LimitError("threshold_value must be positive")


def create_limit(
    session: Session,
    *,
    tenant_id: str,
    code: str,
    name: str,
    target_run_type: str,
    metric_type: str,
    scope_portfolio_id: str,
    threshold_value: Decimal,
    threshold_unit: str,
    breach_direction: str,
    limit_kind: str,
    actor: LimitActor,
    benchmark_id: str | None = None,
    status: str = LIMIT_STATUS_ACTIVE,
) -> LimitDefinition:
    """Create a limit (2L-maker function); emit ``LIMIT.DEFINE`` (governed R-07)."""
    _validate_config(
        target_run_type=target_run_type,
        metric_type=metric_type,
        benchmark_id=benchmark_id,
        threshold_unit=threshold_unit,
        threshold_value=threshold_value,
        breach_direction=breach_direction,
        limit_kind=limit_kind,
        status=status,
    )
    # Re-resolve the FK targets tenant-filtered BEFORE the write (the P3-5 doctrine — PG FK checks
    # BYPASS RLS, so a caller-supplied FOREIGN scope/benchmark id must be refused, not stamped).
    assert_portfolio_in_tenant(
        session, str(scope_portfolio_id), acting_tenant=str(tenant_id), error=LimitError
    )
    if benchmark_id:
        try:
            resolve_benchmark(session, str(benchmark_id), acting_tenant=str(tenant_id))
        except BenchmarkNotVisible as exc:
            raise LimitError(f"benchmark {benchmark_id} is not visible in the tenant") from exc
    # Refuse a duplicate (tenant, code) with a clean domain error (not a raw IntegrityError/500).
    if session.execute(
        select(LimitDefinition.id).where(
            LimitDefinition.tenant_id == str(tenant_id), LimitDefinition.code == code
        )
    ).first():
        raise LimitError(f"a limit with code {code!r} already exists in the tenant")
    limit = LimitDefinition(
        tenant_id=str(tenant_id),
        code=code,
        name=name,
        target_run_type=target_run_type,
        metric_type=metric_type,
        benchmark_id=str(benchmark_id) if benchmark_id else None,
        scope_portfolio_id=str(scope_portfolio_id),
        threshold_value=Decimal(threshold_value),
        threshold_unit=threshold_unit,
        breach_direction=breach_direction,
        limit_kind=limit_kind,
        status=status,
        record_version=1,
    )
    session.add(limit)
    session.flush()
    _record_limit_event(
        session,
        limit=limit,
        event_type=LIMIT_DEFINE_EVENT,
        action=ACTION_CREATE,
        before_value=None,
        after_value=_limit_metadata(limit),
        actor=actor,
    )
    return limit


def update_limit(
    session: Session, limit: LimitDefinition, *, actor: LimitActor, **changes: Any
) -> LimitDefinition:
    """Apply an in-place head edit (``_UPDATABLE`` only — identity is frozen, OD-I), bump
    ``record_version``, emit ``LIMIT.CHANGE``. A re-target is a NEW limit."""
    unknown = set(changes) - set(_UPDATABLE)
    if unknown:
        raise LimitError(f"non-updatable limit attributes: {sorted(unknown)}")
    if "status" in changes and changes["status"] not in LIMIT_STATUSES:
        raise LimitError(f"status {changes['status']!r} is invalid")
    if "breach_direction" in changes and changes["breach_direction"] not in BREACH_DIRECTIONS:
        raise LimitError(f"breach_direction {changes['breach_direction']!r} is invalid")
    if "limit_kind" in changes and changes["limit_kind"] not in LIMIT_KINDS:
        raise LimitError(f"limit_kind {changes['limit_kind']!r} is invalid")
    if "threshold_value" in changes and Decimal(changes["threshold_value"]) <= 0:
        raise LimitError("threshold_value must be positive")
    before = {key: json_safe(getattr(limit, key)) for key in changes}
    for key, value in changes.items():
        setattr(limit, key, Decimal(value) if key == "threshold_value" else value)
    limit.record_version += 1
    session.flush()
    _record_limit_event(
        session,
        limit=limit,
        event_type=LIMIT_CHANGE_EVENT,
        action=ACTION_UPDATE,
        before_value=before,
        after_value={key: json_safe(getattr(limit, key)) for key in changes},
        actor=actor,
    )
    return limit


def suspend_limit(
    session: Session, limit: LimitDefinition, *, actor: LimitActor
) -> LimitDefinition:
    """Suspend a limit (excluded from evaluation)."""
    return update_limit(session, limit, actor=actor, status=LIMIT_STATUS_SUSPENDED)


def resume_limit(session: Session, limit: LimitDefinition, *, actor: LimitActor) -> LimitDefinition:
    """Resume a limit (re-admitted to evaluation)."""
    return update_limit(session, limit, actor=actor, status=LIMIT_STATUS_ACTIVE)


# --- limit health -------------------------------------------------------------------------
@dataclass(frozen=True)
class LimitHealth:
    """Per-limit evaluation health (OD-L) — distinguishes green from un-evaluable."""

    limit_id: str
    code: str
    state: str  # IN_APPETITE | NEVER_EVALUABLE | BREACHED
    latest_run_id: str | None
    latest_breach_id: str | None


HEALTH_IN_APPETITE = "IN_APPETITE"
HEALTH_NEVER_EVALUABLE = "NEVER_EVALUABLE"
HEALTH_BREACHED = "BREACHED"


def limit_health(session: Session, *, acting_tenant: str) -> list[LimitHealth]:
    """Report each ACTIVE limit's evaluation health — so an un-evaluable limit is never silently
    green (OD-L). Derived on demand from ``calc/reads`` (no new mutable state)."""
    out: list[LimitHealth] = []
    for limit in select_active_limits(session, acting_tenant=acting_tenant):
        resolved = _resolve_latest(session, limit)
        if resolved is None:
            out.append(LimitHealth(limit.id, limit.code, HEALTH_NEVER_EVALUABLE, None, None))
            continue
        run_id, observed = resolved
        # RECOMPUTE the predicate from the latest observed — do NOT infer state from the breach
        # table (a breaching-but-not-yet-evaluated run, or a threshold loosened after a breach,
        # would otherwise misreport; the 4-finder false-green fold). The breach row is only the
        # evidence reference.
        breaching = _breaches(observed, Decimal(limit.threshold_value), limit.breach_direction)
        breach = session.execute(
            select(Breach).where(
                Breach.limit_definition_id == limit.id,
                Breach.calculation_run_id == run_id,
            )
        ).scalar_one_or_none()
        state = HEALTH_BREACHED if breaching else HEALTH_IN_APPETITE
        out.append(LimitHealth(limit.id, limit.code, state, run_id, breach.id if breach else None))
    return out


# --- audit emit ---------------------------------------------------------------------------
def _limit_metadata(limit: LimitDefinition) -> dict[str, Any]:
    """DC-2 metadata payload for a ``LIMIT.*`` event — identifying/vocab fields only."""
    return {
        "code": limit.code,
        "target_run_type": limit.target_run_type,
        "metric_type": limit.metric_type,
        "scope_portfolio_id": str(limit.scope_portfolio_id),
        "benchmark_id": str(limit.benchmark_id) if limit.benchmark_id else None,
        "threshold_value": str(limit.threshold_value),
        "threshold_unit": limit.threshold_unit,
        "breach_direction": limit.breach_direction,
        "limit_kind": limit.limit_kind,
        "status": limit.status,
        "record_version": limit.record_version,
    }


def _record_limit_event(
    session: Session,
    *,
    limit: LimitDefinition,
    event_type: str,
    action: str,
    before_value: dict[str, Any] | None,
    after_value: dict[str, Any],
    actor: LimitActor,
) -> None:
    """Emit a ``LIMIT.*`` audit event caller-side to the FROZEN ``record_event`` (DC-2 only)."""
    record_event(
        session,
        event_type=event_type,
        tenant_id=limit.tenant_id,
        actor_type=actor.actor_type,
        actor_id=actor.actor_id,
        source_module=SOURCE_MODULE_LIMIT,
        entity_type=_ENTITY_LIMIT,
        entity_id=limit.id,
        action=action,
        before_value=before_value,
        after_value=after_value,
        data_classification="DC-2",
    )


def _record_breach_event(session: Session, *, breach: Breach, actor_id: str) -> None:
    """Emit ``BREACH.DETECT`` for a detected breach — a synthesized SYSTEM actor on the tick."""
    record_event(
        session,
        event_type=BREACH_DETECT_EVENT,
        tenant_id=breach.tenant_id,
        actor_type="SYSTEM",
        actor_id=actor_id,
        source_module=SOURCE_MODULE_LIMIT,
        entity_type=_ENTITY_BREACH,
        entity_id=breach.id,
        action=ACTION_RECORD,
        # A HARD breach is an incident — escalate the audit envelope severity (the domain
        # HARD/SOFT is also echoed in after_value["severity"]).
        severity="warning" if breach.limit_kind == LIMIT_KIND_HARD else "info",
        after_value={
            "limit_definition_id": str(breach.limit_definition_id),
            "calculation_run_id": str(breach.calculation_run_id),
            "target_run_type": breach.target_run_type,
            "metric_type": breach.metric_type,
            "observed_value": str(breach.observed_value),
            "threshold_value": str(breach.threshold_value),
            "breach_direction": breach.breach_direction,
            "severity": breach.severity,
        },
        data_classification="DC-2",
    )
