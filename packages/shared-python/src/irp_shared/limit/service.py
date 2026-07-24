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
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from irp_shared.audit.actions import (
    ACTION_CREATE,
    ACTION_RECORD,
    ACTION_STATUS_CHANGE,
    ACTION_UPDATE,
)
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
    LIMIT_APPROVE_EVENT,
    LIMIT_CHANGE_EVENT,
    LIMIT_DEFINE_EVENT,
    LIMIT_KIND_HARD,
    LIMIT_KINDS,
    LIMIT_STATUS_ACTIVE,
    LIMIT_STATUS_DRAFT,
    LIMIT_STATUS_SUSPENDED,
    LIMIT_STATUSES,
    SOURCE_MODULE_LIMIT,
    THRESHOLD_UNIT_CURRENCY,
    THRESHOLD_UNIT_FRACTION,
    LimitActor,
)
from irp_shared.limit.models import Breach, LimitDefinition
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


class LimitSodError(LimitError):
    """A person-level SoD violation on a limit approval (the approver is the draft's own maker —
    SOD-02 / REQ-LIM-001; the MG-2 ``BreachSodError`` analog applied to a scalar maker)."""


class DuplicateLimitError(LimitError):
    """A limit with the same ``(tenant, code)`` already exists (the pre-check twin of the
    ``uq_limit_definition_tenant_code`` race — API-2 maps both to a uniform 409)."""


class LimitStateError(LimitError):
    """An illegal lifecycle transition from the current state (approve a non-DRAFT; set/clear DRAFT
    via update; the double-approve loser) — a STATE CONFLICT, not a validation error (API-2 maps it
    to 409, uniform with the SoD conflict; verifier MED-1)."""


def _threshold(value: Decimal | str) -> Decimal:
    """Parse a threshold to Decimal, fail-closed to a clean ``LimitError`` (422 at the API) on a
    malformed string — never a raw ``InvalidOperation`` (a 500). Accepts the API's string input."""
    try:
        return Decimal(value)
    except (InvalidOperation, ValueError, TypeError):
        raise LimitError(f"threshold_value {value!r} is not a valid decimal") from None


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

#: The MATERIAL governing fields (MG-3, OQ-MG-3-5=A): a real change to any of these on a
#: previously-approved limit (ACTIVE **or** SUSPENDED) re-enters the maker-checker gate (the limit
#: returns to DRAFT for a non-maker re-approval — REQ-LIM-001 "limit CHANGES are maker-checked").
#: ``name`` is cosmetic and does NOT trigger it; ``status`` is the lifecycle toggle
#: (suspend/resume), which may not be combined with a governing change in one edit (ambiguous).
_GOVERNING_FIELDS = ("threshold_value", "limit_kind", "breach_direction")


def _governing_value_changed(limit: LimitDefinition, changes: dict[str, Any]) -> bool:
    """True iff a governing field's NEW value actually differs from the current one — presence in
    ``changes`` is not enough (a no-op re-save of the same value must not demote a live limit)."""
    for key in _GOVERNING_FIELDS:
        if key not in changes:
            continue
        if key == "threshold_value":
            if Decimal(changes[key]) != Decimal(getattr(limit, key)):
                return True
        elif changes[key] != getattr(limit, key):
            return True
    return False


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


# --- reads (API-2) ------------------------------------------------------------------------
def list_limits(
    session: Session, *, acting_tenant: str, status: str | None = None
) -> list[LimitDefinition]:
    """Tenant-scoped limit list, optionally filtered by status (``status=DRAFT`` = the approval
    queue). Explicit tenant predicate atop RLS (belt-and-suspenders, the ``select_active_limits``
    pattern). Ordered by code for a stable read surface."""
    if status is not None and status not in LIMIT_STATUSES:
        raise LimitError(f"status {status!r} is invalid")
    stmt = select(LimitDefinition).where(LimitDefinition.tenant_id == str(acting_tenant))
    if status is not None:
        stmt = stmt.where(LimitDefinition.status == status)
    return list(session.execute(stmt.order_by(LimitDefinition.code)).scalars())


def get_limit(session: Session, *, acting_tenant: str, limit_id: str) -> LimitDefinition | None:
    """Read ONE limit by id, tenant-filtered atop RLS (the P3-5 doctrine: PG FK checks bypass RLS,
    so an explicit tenant predicate is load-bearing for a caller-supplied id). Returns None on a
    missing/cross-tenant id (the API maps that to an indistinguishable 404). Doubles as the
    load-for-mutation step (``update_limit``/``approve_limit`` take the object, not an id)."""
    return session.execute(
        select(LimitDefinition).where(
            LimitDefinition.id == str(limit_id),
            LimitDefinition.tenant_id == str(acting_tenant),
        )
    ).scalar_one_or_none()


def evaluate_limit(session: Session, limit: LimitDefinition, now: datetime) -> Breach | None:
    """Evaluate ONE ACTIVE limit against its latest matching COMPLETED run; append a SELF-DESCRIBING
    ``breach`` (+ ``BREACH.DETECT``) if it breaches AND has not already been recorded for that run.
    Idempotent on ``(limit_id, calculation_run_id)`` (the unique constraint is the backstop)."""
    if limit.status != LIMIT_STATUS_ACTIVE:
        # Fail-closed backstop (MG-3): only an APPROVED, ACTIVE limit is ever evaluated. Production
        # callers already pre-filter via `select_active_limits`, but a DRAFT/SUSPENDED limit handed
        # here directly must NOT record a breach against an un-approved/suspended config.
        return None
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
def _require_human(actor: LimitActor) -> None:
    """BR-15: AI/automation is NEVER an approver — a sign-off is a human act (MG-2/VW-1 guard)."""
    if actor.actor_type != "user":
        raise LimitError("a limit approval requires a human actor (BR-15)")


def _lock_limit(session: Session, limit_id: str, tenant_id: str) -> LimitDefinition:
    """Re-resolve the limit tenant-filtered AND take a row lock (linearizability backstop for the
    approve gate). The tenant filter is load-bearing (PG FK checks bypass RLS — the P3-5 doctrine).

    ``populate_existing`` is REQUIRED: ``LimitDefinition`` is EV and its ``status`` lives ON the row
    (unlike MG-2's recency-derived breach state), so an already-mapped instance would return a STALE
    ``status`` and defeat the lock's from-state check → a double-approve race. Refresh under lock.
    """
    limit = session.execute(
        select(LimitDefinition)
        .where(LimitDefinition.id == limit_id, LimitDefinition.tenant_id == tenant_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).scalar_one_or_none()
    if limit is None:
        raise LimitError(f"limit {limit_id} not found in tenant {tenant_id}")
    return limit


def _validate_config(
    *,
    target_run_type: str,
    metric_type: str,
    benchmark_id: str | None,
    threshold_unit: str,
    threshold_value: Decimal | str,
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
    if _threshold(threshold_value) <= 0:
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
    threshold_value: Decimal | str,
    threshold_unit: str,
    breach_direction: str,
    limit_kind: str,
    actor: LimitActor,
    benchmark_id: str | None = None,
) -> LimitDefinition:
    """Create a limit (2L-maker function); emit ``LIMIT.DEFINE`` (governed R-07).

    MG-3: a new limit is ALWAYS born ``DRAFT`` (never immediately ACTIVE) and is NOT evaluated until
    ``approve_limit`` — the maker-checker gate (REQ-LIM-001/BX-SOD). There is deliberately no public
    ``status=`` override: an ACTIVE-on-create seam would let the maker self-activate, the symmetric
    twin of the ``update_limit`` DRAFT bypass. ``created_by`` records the drafter for the SoD.
    """
    _validate_config(
        target_run_type=target_run_type,
        metric_type=metric_type,
        benchmark_id=benchmark_id,
        threshold_unit=threshold_unit,
        threshold_value=threshold_value,
        breach_direction=breach_direction,
        limit_kind=limit_kind,
        status=LIMIT_STATUS_DRAFT,
    )
    # Re-resolve the FK targets tenant-filtered BEFORE the write (the P3-5 doctrine — PG FK checks
    # BYPASS RLS, so a caller-supplied FOREIGN scope/benchmark id must be refused, not stamped).
    assert_portfolio_in_tenant(
        session, str(scope_portfolio_id), acting_tenant=str(tenant_id), error=LimitError
    )
    if benchmark_id and (
        # A tenant-filtered existence check via raw SQL — keeps ``limit`` off the marketdata import
        # fence (marketdata is a leaf) while still refusing a FOREIGN benchmark_id (the P3-5 guard).
        session.execute(
            text("SELECT 1 FROM benchmark WHERE id = :id AND tenant_id = :t"),
            {"id": str(benchmark_id), "t": str(tenant_id)},
        ).first()
        is None
    ):
        raise LimitError(f"benchmark {benchmark_id} is not visible in the tenant")
    # Refuse a duplicate (tenant, code) with a clean domain error (not a raw IntegrityError/500).
    if session.execute(
        select(LimitDefinition.id).where(
            LimitDefinition.tenant_id == str(tenant_id), LimitDefinition.code == code
        )
    ).first():
        raise DuplicateLimitError(f"a limit with code {code!r} already exists in the tenant")
    limit = LimitDefinition(
        tenant_id=str(tenant_id),
        code=code,
        name=name,
        target_run_type=target_run_type,
        metric_type=metric_type,
        benchmark_id=str(benchmark_id) if benchmark_id else None,
        scope_portfolio_id=str(scope_portfolio_id),
        threshold_value=_threshold(threshold_value),
        threshold_unit=threshold_unit,
        breach_direction=breach_direction,
        limit_kind=limit_kind,
        status=LIMIT_STATUS_DRAFT,
        created_by=actor.actor_id,
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
    ``record_version``, emit ``LIMIT.CHANGE``. A re-target is a NEW limit.

    MG-3 maker-checker rules:
    - ``update_limit`` may NEVER set or clear ``DRAFT`` — DRAFT is entered only via ``create_limit``
      (or the auto-demotion below) and left only via ``approve_limit``. This closes the "activate a
      draft through the edit path" bypass (the twin of the create-side force-DRAFT).
    - A MATERIAL governing-field change to a previously-approved limit (ACTIVE **or** SUSPENDED)
      auto-demotes it to DRAFT and records the editor as a maker (``updated_by``); it is not
      evaluated until a NON-maker re-approves (REQ-LIM-001/BX-SOD, OQ-MG-3-5=A). Enforcing this for
      SUSPENDED too closes the suspend->loosen->resume laundering bypass.
    - A status toggle (suspend/resume) may NOT be combined with a governing change in one edit —
      that ambiguity was a demote-suppression bypass; make the two edits separately.
    """
    unknown = set(changes) - set(_UPDATABLE)
    if unknown:
        raise LimitError(f"non-updatable limit attributes: {sorted(unknown)}")
    if "status" in changes and changes["status"] not in LIMIT_STATUSES:
        raise LimitError(f"status {changes['status']!r} is invalid")
    if "breach_direction" in changes and changes["breach_direction"] not in BREACH_DIRECTIONS:
        raise LimitError(f"breach_direction {changes['breach_direction']!r} is invalid")
    if "limit_kind" in changes and changes["limit_kind"] not in LIMIT_KINDS:
        raise LimitError(f"limit_kind {changes['limit_kind']!r} is invalid")
    if "threshold_value" in changes and _threshold(changes["threshold_value"]) <= 0:
        raise LimitError("threshold_value must be positive")
    # Take the row lock AND read the fresh status under it, so the DRAFT guard and the demote
    # decision can never act on a stale identity-map status that a concurrent approve invalidated
    # (verifier B-2 parity with approve_limit). A SCALAR select is used, not a whole-object refresh,
    # so in-flight Decimal columns keep their in-memory representation (the audit payload format).
    fresh_status = session.execute(
        select(LimitDefinition.status)
        .where(LimitDefinition.id == limit.id, LimitDefinition.tenant_id == limit.tenant_id)
        .with_for_update()
    ).scalar_one_or_none()
    if fresh_status is None:
        raise LimitError(f"limit {limit.id} not found in tenant {limit.tenant_id}")
    limit.status = fresh_status  # sync the locked truth (only the status string)
    governing_changed = _governing_value_changed(limit, changes)
    if "status" in changes:
        if governing_changed:
            raise LimitError(
                "cannot combine a status change (suspend/resume) with a governing-field change in "
                "one edit — a config change requires re-approval; make the two edits separately"
            )
        if changes["status"] == LIMIT_STATUS_DRAFT or limit.status == LIMIT_STATUS_DRAFT:
            raise LimitStateError(
                "update_limit cannot set or clear DRAFT — a draft leaves only via approve_limit "
                "(the maker-checker gate); suspend/resume operate on ACTIVE<->SUSPENDED only"
            )
    # A material change to a previously-approved (non-DRAFT) limit re-enters the maker-checker gate.
    demote = governing_changed and limit.status != LIMIT_STATUS_DRAFT
    keys = list(changes) + (["status"] if demote else [])
    before = {key: json_safe(getattr(limit, key)) for key in keys}
    for key, value in changes.items():
        setattr(limit, key, Decimal(value) if key == "threshold_value" else value)
    if demote:
        limit.status = LIMIT_STATUS_DRAFT
    # Record the editor as a maker on EVERY edit — ``approve_limit`` refuses any approver in the SET
    # {created_by, updated_by}, so both the original author and the last editor are SoD-excluded.
    limit.updated_by = actor.actor_id
    limit.record_version += 1
    session.flush()
    _record_limit_event(
        session,
        limit=limit,
        event_type=LIMIT_CHANGE_EVENT,
        action=ACTION_UPDATE,
        before_value=before,
        after_value={key: json_safe(getattr(limit, key)) for key in keys},
        actor=actor,
    )
    return limit


def approve_limit(
    session: Session, limit: LimitDefinition, *, actor: LimitActor, approval_ref: str
) -> LimitDefinition:
    """Approve a DRAFT limit into ACTIVE — the maker-checker gate (REQ-LIM-001/BX-SOD, SOD-02).

    The approver MUST be human (BR-15) and MUST NOT be in the SET of makers of this draft —
    ``{created_by, updated_by}`` (the author AND the last editor) — so neither signs off a limit
    they shaped (SOD-02). The from-state is re-read UNDER the row lock (``populate_existing``)
    so a stale read cannot double-approve. Emits ``LIMIT.APPROVE`` with the ``approval_ref``.
    """
    _require_human(actor)
    if not (approval_ref or "").strip():
        raise LimitError("approve_limit requires a non-empty approval_ref (the sign-off evidence)")
    locked = _lock_limit(session, limit.id, limit.tenant_id)
    if locked.status != LIMIT_STATUS_DRAFT:
        raise LimitStateError(
            f"only a DRAFT limit can be approved (limit {locked.id} is {locked.status})"
        )
    makers = {locked.created_by, locked.updated_by} - {None}
    if not makers:
        raise LimitSodError(
            f"limit {locked.id} is DRAFT with no recorded maker — cannot establish SoD (refused)"
        )
    if actor.actor_id in makers:
        raise LimitSodError(
            f"actor {actor.actor_id} shaped this limit (a maker); cannot approve it (SOD-02)"
        )
    before = {"status": locked.status}
    locked.status = LIMIT_STATUS_ACTIVE
    locked.record_version += 1
    session.flush()
    _record_limit_event(
        session,
        limit=locked,
        event_type=LIMIT_APPROVE_EVENT,
        action=ACTION_STATUS_CHANGE,
        before_value=before,
        # Record the makers the SoD was checked against so the two-person control is provable from
        # the immutable audit row alone (the maker columns are mutable EV state).
        after_value={
            "status": locked.status,
            "approved_by": actor.actor_id,
            "checked_makers": sorted(makers),
        },
        actor=actor,
        approval_ref=approval_ref,
    )
    return locked


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
    approval_ref: str | None = None,
) -> None:
    """Emit a ``LIMIT.*`` audit event caller-side to the FROZEN ``record_event`` (DC-2 only).
    ``approval_ref`` carries the maker-checker sign-off reference for ``LIMIT.APPROVE``."""
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
        approval_ref=approval_ref,
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
