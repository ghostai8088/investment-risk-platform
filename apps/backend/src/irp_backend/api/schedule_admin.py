"""The schedule WRITE path (REPRO-2, ratified OQ-REP2-2) — the control becomes startable.

SCH-1 minted ``schedule.manage`` as the maker verb and shipped no route for it; SCH-2 shipped the
reads and deliberately reserved the write path — *"a create/pause API is its own slice with its own
maker-checker question"*. This is that slice, and this module is the forward-gate's discharge: the
code leaves ``UNROUTED_FORWARD_GATES`` because it is now routed.

**The maker-checker question, answered — and it is not one answer.** SOD-04's class is authority
and limits: acts whose EFFECT is a change in who may do what, or what the book may hold.

* **Create and resume are not in that class.** They only ADD detection. Every act a schedule
  triggers is itself fully governed (a run, a snapshot, model gates, IA results), creating one
  grants nobody anything, and putting "turn the nightly check on" behind a second administrator
  would be friction on precisely the control this wave exists to start.
* **Pause is the hard case, and it was adjudicated rather than waved through.** Pausing a
  REPRODUCTION schedule is a one-person, reversible switch-off of the platform's only detective
  control over governed-number drift — held by ``risk_analyst_1l``, the very population whose runs
  that control re-checks. The ratified answer is compensating VISIBILITY rather than friction:
  pause stays one-person and audit-trailed, and a tenant that has configured schedules and then
  paused them ALL now reads RED on the alarm-health surface (``control_switched_off``). A silent
  green during a tamper window was the actual risk; a second approver on a reversible act was the
  expensive way to not fix it.

Holders of ``schedule.manage``, recomputed from ``ROLE_TEMPLATES`` at the ratification:
``data_steward``, ``risk_analyst_1l``, ``platform_admin`` — and since ``platform_admin`` is never
cloned into a customer tenant, in practice **``data_steward`` and ``risk_analyst_1l``**.
``tenant_admin`` holds nothing schedule-shaped (it administers people), so a fresh tenant's first
administrator grants one of those roles before the control can be started — a two-step onboarding
stated here rather than discovered by an operator.
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import NoReturn

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from irp_backend.deps import get_tenant_session, require_permission, require_uuid_principal_id
from irp_shared.entitlement.service import Principal
from irp_shared.scheduling.events import (
    CADENCE_KINDS,
    SCHEDULE_STATUS_ACTIVE,
    SchedulingActor,
)
from irp_shared.scheduling.models import Schedule
from irp_shared.scheduling.service import (
    ScheduleError,
    create_schedule,
    pause_schedule,
    resume_schedule,
)

router = APIRouter(tags=["schedules"])

_require_manage = require_permission("schedule.manage")


class ScheduleCreateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=1, max_length=150)
    name: str = Field(min_length=1, max_length=255)
    target_run_type: str = Field(min_length=1, max_length=100)
    environment_id: str = Field(min_length=1, max_length=100)
    anchor_date: date
    cadence_kind: str
    interval_days: int | None = Field(default=None, gt=0)
    calendar_id: uuid.UUID | None = None
    scope_portfolio_id: uuid.UUID | None = None
    model_version_id: uuid.UUID | None = None


class ScheduleOut(BaseModel):
    id: str
    code: str
    name: str
    target_run_type: str
    cadence_kind: str
    interval_days: int | None
    status: str


def _out(schedule: Schedule) -> ScheduleOut:
    return ScheduleOut(
        id=str(schedule.id),
        code=schedule.code,
        name=schedule.name,
        target_run_type=schedule.target_run_type,
        cadence_kind=schedule.cadence_kind,
        interval_days=schedule.interval_days,
        status=schedule.status,
    )


def _refuse(detail: str) -> NoReturn:
    """Refusals are 422 — the caller asked for something the platform will not do.

    Typed ``NoReturn`` so the type checker knows control does not come back: without it, every
    guard below reads as "maybe refused, maybe fell through", which is precisely the ambiguity a
    fail-closed guard must not have.
    """
    raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=detail)


def _load(db: Session, principal: Principal, schedule_id: uuid.UUID) -> Schedule:
    """Tenant-scoped load. A foreign or absent id is the SAME refusal — no existence oracle."""
    schedule = db.execute(
        select(Schedule).where(
            Schedule.id == str(schedule_id), Schedule.tenant_id == principal.tenant_id
        )
    ).scalar_one_or_none()
    if schedule is None:
        _refuse("schedule not found in this tenant")
    return schedule


@router.post("/schedules", response_model=ScheduleOut, status_code=status.HTTP_201_CREATED)
def create(
    payload: ScheduleCreateIn,
    principal: Principal = Depends(_require_manage),
    db: Session = Depends(get_tenant_session),
) -> ScheduleOut:
    """Create a schedule. The route adds TRANSPORT; every rule is the existing service's.

    The one thing it adds is the duplicate-code refusal, and the mechanism matters: a pre-check
    alone cannot deliver it. Two concurrent creates with the same code both pass any pre-check and
    the loser dies at flush, so the UNIQUE violation is CAUGHT and mapped to the same refusal the
    pre-check gives — the pre-check survives only as the ordinary-path courtesy with the better
    message.
    """
    if payload.cadence_kind not in CADENCE_KINDS:
        _refuse(f"unknown cadence_kind: {payload.cadence_kind!r}")
    existing = db.execute(
        select(Schedule.id).where(
            Schedule.tenant_id == principal.tenant_id, Schedule.code == payload.code
        )
    ).scalar_one_or_none()
    if existing is not None:
        _refuse(f"a schedule with code {payload.code!r} already exists in this tenant")

    actor = SchedulingActor(actor_id=require_uuid_principal_id(principal), actor_type="HUMAN")
    try:
        schedule = create_schedule(
            db,
            tenant_id=principal.tenant_id,
            code=payload.code,
            name=payload.name,
            target_run_type=payload.target_run_type,
            environment_id=payload.environment_id,
            anchor_date=payload.anchor_date,
            cadence_kind=payload.cadence_kind,
            interval_days=payload.interval_days,
            calendar_id=str(payload.calendar_id) if payload.calendar_id else None,
            scope_portfolio_id=(
                str(payload.scope_portfolio_id) if payload.scope_portfolio_id else None
            ),
            model_version_id=(str(payload.model_version_id) if payload.model_version_id else None),
            actor=actor,
        )
        db.commit()
    except ScheduleError as exc:
        db.rollback()
        _refuse(str(exc))
    except IntegrityError:
        db.rollback()
        # Usually the concurrent duplicate: another request committed the same code between the
        # pre-check and this flush. But the same exception class also carries every OTHER
        # constraint violation (a foreign calendar_id, say), and claiming "already exists" for
        # those would be a false statement in a governed refusal — so ask the database which
        # case this is. After the rollback the racing winner's committed row is visible.
        raced = db.execute(
            select(Schedule.id).where(
                Schedule.tenant_id == principal.tenant_id, Schedule.code == payload.code
            )
        ).scalar_one_or_none()
        if raced is not None:
            _refuse(f"a schedule with code {payload.code!r} already exists in this tenant")
        _refuse("the schedule violates a database constraint — check the referenced ids")
    return _out(schedule)


@router.post("/schedules/{schedule_id}/pause", response_model=ScheduleOut)
def pause(
    schedule_id: uuid.UUID,
    principal: Principal = Depends(_require_manage),
    db: Session = Depends(get_tenant_session),
) -> ScheduleOut:
    """Pause a schedule — one person, audit-trailed, and VISIBLE.

    See the module docstring: this is the act the maker-checker adjudication turned on. Pausing
    every reproduction schedule in a tenant switches off its detective control, so the alarm-health
    surface reads RED (`control_switched_off`) for exactly that state.
    """
    schedule = _load(db, principal, schedule_id)
    actor = SchedulingActor(actor_id=require_uuid_principal_id(principal), actor_type="HUMAN")
    try:
        paused = pause_schedule(db, schedule, actor=actor)
        db.commit()
    except ScheduleError as exc:
        db.rollback()
        _refuse(str(exc))
    return _out(paused)


@router.post("/schedules/{schedule_id}/resume", response_model=ScheduleOut)
def resume(
    schedule_id: uuid.UUID,
    principal: Principal = Depends(_require_manage),
    db: Session = Depends(get_tenant_session),
) -> ScheduleOut:
    """Resume a paused schedule. No four-eyes: resuming only ADDS detection back."""
    schedule = _load(db, principal, schedule_id)
    actor = SchedulingActor(actor_id=require_uuid_principal_id(principal), actor_type="HUMAN")
    try:
        resumed = resume_schedule(db, schedule, actor=actor)
        db.commit()
    except ScheduleError as exc:
        db.rollback()
        _refuse(str(exc))
    return _out(resumed)


__all__ = ["SCHEDULE_STATUS_ACTIVE", "router"]
