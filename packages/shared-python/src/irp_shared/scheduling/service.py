"""Scheduling service (SCH-1) — cadence math + due-selection + dispatch + audited schedule CRUD.

Two clean layers:

- **Pure cadence functions** (``current_tick`` / ``is_due``) — deterministic functions of
  ``(anchor, interval, now)`` and the already-fired tick set. They read NO wall clock (INV-SCH-1:
  ``scheduled_for`` is the computed ``current_tick`` grid value, never ``now``), so the whole
  scheduler is testable with an injected ``now`` — no clock abstraction (none exists in the repo;
  ``utcnow()`` is the only time source and reproducibility is the snapshot pin, AD-014).
- **DB layer** (``select_active_due`` / ``dispatch_one`` / schedule CRUD) — all tenant-scoped
  NON-BYPASSRLS (OQ-SCH-1-1=B). ``dispatch_one`` NEVER backfills: it fires the ONE current grid tick
  and leaves missed grid points as honest ledger gaps (OD-SCH-1-F, which folds the two blocking
  verifier defects — the fraudulent-backfill series + the pause/resume storm).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from datetime import date as dt_date
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from irp_shared.audit.actions import ACTION_CREATE, ACTION_UPDATE
from irp_shared.audit.service import record_event
from irp_shared.risk.covariance_service import latest_covariances
from irp_shared.risk.events import VarActor
from irp_shared.risk.factor_service import latest_factor_exposure
from irp_shared.risk.var_service import VarRunResult, run_var
from irp_shared.scheduling.events import (
    CADENCE_INTERVAL,
    CADENCE_KINDS,
    OUTCOME_DISPATCHED,
    OUTCOME_FAILED,
    SCHEDULABLE_RUN_TYPES,
    SCHEDULE_CREATE_EVENT,
    SCHEDULE_STATUS_ACTIVE,
    SCHEDULE_STATUS_PAUSED,
    SCHEDULE_STATUSES,
    SCHEDULE_UPDATE_EVENT,
    SOURCE_MODULE_SCHEDULING,
    SchedulingActor,
)
from irp_shared.scheduling.models import Schedule, ScheduledRun

#: The audit ``entity_type`` for a schedule head.
ENTITY_SCHEDULE = "schedule"

#: In-place editable head attributes (config edits — the ``scenario_definition`` EV precedent).
#: v1 allows ONLY name + status (pause/resume); a re-cadence (interval/anchor) or a redefinition
#: (scope/model/environment) is a NEW schedule — this keeps the grid fixed for a schedule's life
#: and sidesteps the re-cadence grid-shift seam (recorded v2).
_UPDATABLE = ("name", "status")


class ScheduleError(ValueError):
    """A schedule config or dispatch precondition failure (fail-closed)."""


# --------------------------------------------------------------------------- pure cadence math ---
def _anchor_dt(anchor_date: dt_date) -> datetime:
    """The anchor grid origin as a UTC-midnight instant."""
    return datetime(anchor_date.year, anchor_date.month, anchor_date.day, tzinfo=UTC)


def current_tick(anchor_date: dt_date, interval_days: int, now: datetime) -> datetime:
    """The most recent grid point at or before ``now`` (INV-SCH-1 — a PURE grid value).

    Grid = ``anchor_midnight_utc + k·interval_days``; returns the largest such point ``<= now``
    (clamped to the anchor for ``now < anchor``, though callers gate that with ``is_due``). Depends
    ONLY on ``(anchor, interval, now)`` — never on the ledger or a wall clock — so two concurrent
    polls compute the identical bucket and collide on the unique constraint.
    """
    if interval_days <= 0:
        raise ScheduleError("interval_days must be positive")
    anchor = _anchor_dt(anchor_date)
    step = timedelta(days=interval_days)
    k = (now - anchor) // step
    if k < 0:
        k = 0
    return anchor + k * step


def is_due(schedule: Schedule, now: datetime, fired_ticks: set[datetime]) -> bool:
    """Pure predicate: an ACTIVE schedule whose CURRENT grid tick has not already fired.

    No backfill: only the current tick is ever considered — missed grid points are honest gaps.
    """
    if schedule.status != SCHEDULE_STATUS_ACTIVE:
        return False
    if now < _anchor_dt(schedule.anchor_date):
        return False
    tick = current_tick(schedule.anchor_date, schedule.interval_days, now)
    return tick not in fired_ticks


# ------------------------------------------------------------------------------- DB due-select ---
def select_active_due(session: Session, now: datetime) -> list[tuple[Schedule, datetime]]:
    """Tenant-scoped: ACTIVE schedules whose current grid tick has no ``scheduled_run`` yet.

    Reads ONLY the two scheduling tables. Under OQ-SCH-1-1=B this runs inside ONE tenant's
    non-BYPASSRLS session, so RLS shows only that tenant's rows — no cross-tenant read, no ops role.
    """
    schedules = list(
        session.execute(select(Schedule).where(Schedule.status == SCHEDULE_STATUS_ACTIVE)).scalars()
    )
    due: list[tuple[Schedule, datetime]] = []
    for schedule in schedules:
        if now < _anchor_dt(schedule.anchor_date):
            continue
        tick = current_tick(schedule.anchor_date, schedule.interval_days, now)
        already = session.execute(
            select(ScheduledRun.id).where(
                ScheduledRun.schedule_id == schedule.id,
                ScheduledRun.scheduled_for == tick,
            )
        ).first()
        if already is None:
            due.append((schedule, tick))
    return due


# --------------------------------------------------------------------------------- dispatch -----
def dispatch_one(
    session: Session,
    schedule: Schedule,
    tick: datetime,
    now: datetime,
    *,
    code_version: str,
) -> ScheduledRun:
    """Fire ONE grid tick: resolve upstream, run the family binder, append the ledger row.

    Idempotent: a pre-existing ``(schedule_id, tick)`` row is returned unchanged (the unique
    constraint is the hard race backstop — a concurrent loser rolls back its phantom run at COMMIT).
    v1 dispatches VaR only (OD-SCH-1-D): resolve the latest COMPLETED FACTOR_EXPOSURE run for the
    scope (tenant-scoped — this is what ``run_var`` re-pins as ``x``, NOT a plain EXPOSURE run) +
    the latest COMPLETED COVARIANCE run (tenant-global), then ``run_var`` with build args re-pins a
    FRESH input snapshot over current data. A pre-create refusal RAISES (the caller records a FAILED
    ledger row); a post-create FAILED run returns a row with ``outcome=FAILED`` + the failed run id.
    """
    existing = session.execute(
        select(ScheduledRun).where(
            ScheduledRun.schedule_id == schedule.id,
            ScheduledRun.scheduled_for == tick,
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing

    if schedule.target_run_type not in SCHEDULABLE_RUN_TYPES:
        raise ScheduleError(
            f"target_run_type {schedule.target_run_type!r} is not schedulable in v1"
        )

    tenant = schedule.tenant_id
    fx_rows = latest_factor_exposure(
        session, acting_tenant=tenant, portfolio_id=schedule.scope_portfolio_id
    )
    if not fx_rows:
        raise ScheduleError("no COMPLETED factor-exposure run for the schedule scope")
    exposure_run_id = fx_rows[0].calculation_run_id
    cov_rows = latest_covariances(session, acting_tenant=tenant)
    if not cov_rows:
        raise ScheduleError("no COMPLETED covariance run for the tenant")
    covariance_run_id = cov_rows[0].calculation_run_id

    result: VarRunResult = run_var(
        session,
        acting_tenant=tenant,
        actor=VarActor(actor_id=f"scheduler:{schedule.id}", actor_type="SYSTEM"),
        code_version=code_version,
        environment_id=schedule.environment_id,
        model_version_id=schedule.model_version_id,
        exposure_run_id=exposure_run_id,
        covariance_run_id=covariance_run_id,
    )
    outcome = OUTCOME_DISPATCHED if result.status == "COMPLETED" else OUTCOME_FAILED
    row = ScheduledRun(
        tenant_id=tenant,
        schedule_id=schedule.id,
        scheduled_for=tick,
        fired_at=now,
        calculation_run_id=result.run.run_id,
        resolved_exposure_run_id=exposure_run_id,
        resolved_covariance_run_id=covariance_run_id,
        outcome=outcome,
        failure_reason=result.failure_reason,
    )
    session.add(row)
    session.flush()
    return row


def record_failed_dispatch(
    session: Session,
    schedule: Schedule,
    tick: datetime,
    now: datetime,
    reason: str,
) -> ScheduledRun:
    """Append a FAILED ledger row for a dispatch that RAISED before a run was created.

    Occupies the ``(schedule_id, tick)`` bucket so the SAME tick is not retried (record + continue,
    OD-SCH-1-J — the NEXT grid tick is the retry, not this one). ``calculation_run_id`` is NULL.
    """
    row = ScheduledRun(
        tenant_id=schedule.tenant_id,
        schedule_id=schedule.id,
        scheduled_for=tick,
        fired_at=now,
        calculation_run_id=None,
        outcome=OUTCOME_FAILED,
        failure_reason=reason[:2000],
    )
    session.add(row)
    session.flush()
    return row


# ------------------------------------------------------------------------------ schedule CRUD ---
def _validate_config(
    *,
    target_run_type: str,
    cadence_kind: str,
    status: str,
    interval_days: int,
    environment_id: str,
) -> None:
    if target_run_type not in SCHEDULABLE_RUN_TYPES:
        raise ScheduleError(f"target_run_type {target_run_type!r} is not schedulable in v1")
    if cadence_kind not in CADENCE_KINDS:
        raise ScheduleError(f"cadence_kind {cadence_kind!r} is not a supported v1 cadence")
    if status not in SCHEDULE_STATUSES:
        raise ScheduleError(f"status {status!r} is not a valid schedule status")
    if interval_days <= 0:
        raise ScheduleError("interval_days must be positive")
    if not environment_id:
        raise ScheduleError("environment_id is required (a governed-run pin)")


def create_schedule(
    session: Session,
    *,
    tenant_id: str,
    code: str,
    name: str,
    target_run_type: str,
    scope_portfolio_id: str,
    model_version_id: str,
    environment_id: str,
    interval_days: int,
    anchor_date: dt_date,
    actor: SchedulingActor,
    cadence_kind: str = CADENCE_INTERVAL,
    status: str = SCHEDULE_STATUS_ACTIVE,
) -> Schedule:
    """Create an ACTIVE (by default) schedule head; emit ``SCHEDULE.CREATE`` (governed R-07)."""
    _validate_config(
        target_run_type=target_run_type,
        cadence_kind=cadence_kind,
        status=status,
        interval_days=interval_days,
        environment_id=environment_id,
    )
    schedule = Schedule(
        tenant_id=str(tenant_id),
        code=code,
        name=name,
        target_run_type=target_run_type,
        scope_portfolio_id=str(scope_portfolio_id),
        model_version_id=str(model_version_id),
        environment_id=environment_id,
        cadence_kind=cadence_kind,
        interval_days=interval_days,
        anchor_date=anchor_date,
        status=status,
        record_version=1,
    )
    session.add(schedule)
    session.flush()
    _record_schedule_event(
        session,
        schedule=schedule,
        event_type=SCHEDULE_CREATE_EVENT,
        action=ACTION_CREATE,
        before_value=None,
        after_value=_schedule_metadata(schedule),
        actor=actor,
    )
    return schedule


def update_schedule(
    session: Session,
    schedule: Schedule,
    *,
    actor: SchedulingActor,
    **changes: Any,
) -> Schedule:
    """Apply an in-place head edit (name / status), bump ``record_version``, emit
    ``SCHEDULE.UPDATE``. Only ``_UPDATABLE`` attributes may change (a re-cadence/redefinition is a
    new schedule — OD-SCH-1-F)."""
    unknown = set(changes) - set(_UPDATABLE)
    if unknown:
        raise ScheduleError(f"non-updatable schedule attributes: {sorted(unknown)}")
    if "status" in changes and changes["status"] not in SCHEDULE_STATUSES:
        raise ScheduleError(f"status {changes['status']!r} is not a valid schedule status")
    before = {key: getattr(schedule, key) for key in changes}
    for key, value in changes.items():
        setattr(schedule, key, value)
    schedule.record_version += 1
    session.flush()
    _record_schedule_event(
        session,
        schedule=schedule,
        event_type=SCHEDULE_UPDATE_EVENT,
        action=ACTION_UPDATE,
        before_value=before,
        after_value={key: getattr(schedule, key) for key in changes},
        actor=actor,
    )
    return schedule


def pause_schedule(session: Session, schedule: Schedule, *, actor: SchedulingActor) -> Schedule:
    """Pause a schedule (excluded from ``select_active_due``; missed ticks are NOT backfilled)."""
    return update_schedule(session, schedule, actor=actor, status=SCHEDULE_STATUS_PAUSED)


def resume_schedule(session: Session, schedule: Schedule, *, actor: SchedulingActor) -> Schedule:
    """Resume a schedule; the next poll fires ONLY the current grid tick (no catch-up storm)."""
    return update_schedule(session, schedule, actor=actor, status=SCHEDULE_STATUS_ACTIVE)


def _schedule_metadata(schedule: Schedule) -> dict[str, Any]:
    """DC-2 metadata payload for a ``SCHEDULE.*`` event — identifying/vocab fields only."""
    return {
        "code": schedule.code,
        "target_run_type": schedule.target_run_type,
        "scope_portfolio_id": str(schedule.scope_portfolio_id),
        "cadence_kind": schedule.cadence_kind,
        "interval_days": schedule.interval_days,
        "status": schedule.status,
        "record_version": schedule.record_version,
    }


def _record_schedule_event(
    session: Session,
    *,
    schedule: Schedule,
    event_type: str,
    action: str,
    before_value: dict[str, Any] | None,
    after_value: dict[str, Any],
    actor: SchedulingActor,
) -> None:
    """Emit a ``SCHEDULE.*`` audit event caller-side to the FROZEN ``record_event`` (DC-2 only)."""
    record_event(
        session,
        event_type=event_type,
        tenant_id=schedule.tenant_id,
        actor_type=actor.actor_type,
        actor_id=actor.actor_id,
        source_module=SOURCE_MODULE_SCHEDULING,
        entity_type=ENTITY_SCHEDULE,
        entity_id=schedule.id,
        action=action,
        before_value=before_value,
        after_value=after_value,
        data_classification="DC-2",
    )
