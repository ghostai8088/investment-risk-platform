"""Schedule read endpoints (SCH-2, OQ-SCH-2-7c — the operator visibility surface).

**READ-ONLY by design.** SCH-1 minted ``schedule.manage`` (the maker verb) alongside
``schedule.view``, but SCH-2 ships NO write route: schedules are created by the demo/in-process
path, and a create/pause API is its own slice with its own maker-checker question. This router is
gated exclusively on the already-minted ``schedule.view`` — **no new R-07 permission**, and this is
that permission's FIRST consumer (SCH-1 minted it with no reader).

**Why it exists at all.** A FAILED fire burns its ``(schedule, tick)`` bucket permanently — IA
append-only ledger, ``uq(schedule_id, scheduled_for)``, and ``_UPDATABLE`` forbidding a re-cadence —
so at monthly cadence one transient failure loses that month with no re-run mechanism, and RM-1
refuses a return series with a missing interior month-end. The ratified answer (OQ-SCH-2-7 = accept
+ runbook + minimal read) accepts the burn and requires the failure to be **visible when it
happens**; before this router the only detector was an RM-1 refusal months later.

Two reads:

- ``GET /schedules`` — the heads, each stamped with its LAST fire. A month-end schedule whose last
  fire is two months stale is the only signal that a tick was missed ENTIRELY (a worker outage
  leaves no ledger row at all — ``record_failed_dispatch`` occupies the bucket only when the tick
  phase actually ran).
- ``GET /schedules/runs`` — the fired-tick ledger; ``?outcome=FAILED`` is a burned-month feed.

Both are tenant-RLS-scoped with an explicit tenant predicate underneath (``scheduling/queries.py``)
and silent-empty rather than 404-on-unknown-id (no existence oracle).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from irp_backend.deps import get_tenant_session, require_permission
from irp_shared.entitlement.service import Principal
from irp_shared.scheduling.models import ScheduledRun
from irp_shared.scheduling.queries import (
    ScheduleWithLastFire,
    list_scheduled_runs,
    list_schedules,
)

router = APIRouter(prefix="/schedules", tags=["schedules"])

#: Module-level guard singleton (deny-by-default; built once, not in an argument default).
#: The SCH-1-minted ``schedule.view``. Holder set VERIFIED against ``entitlement/bootstrap.py``
#: (an earlier hand-written version of this comment was wrong in both directions):
#: ``platform_admin``, ``data_steward``, ``risk_analyst_1l``, ``risk_manager_2l``, ``auditor_3l``.
#: ``ops`` does NOT hold it — the ops role holds only ``ops.audit.verify``.
#:
#: ``auditor_3l`` is the holder that constrains what may be surfaced here: it holds NO
#: ``valuation.view`` / ``position.view`` / ``marketdata.view``, so a ledger field must never carry
#: raw row data (see ``scheduling.service.redact_failure_reason``, which enforces that upstream).
_require_schedule_view = require_permission("schedule.view")


def _utc(value: datetime | None) -> datetime | None:
    """Normalize a stored instant to tz-aware UTC (PG returns aware; SQLite drops the tz — the
    ``db/bitemporal.py`` convention). The repo now carries three near-identical copies of this
    normalizer (here, ``db/bitemporal.py``, ``limit/lifecycle.py``); consolidating them is recorded
    for the OPS-H1 hygiene slice rather than done here, where it would breach the SCH-2 fence."""
    if value is None:
        return None
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


class ScheduleOut(BaseModel):
    """A schedule head + its last fire. ``interval_days``/``model_version_id`` are BOTH nullable
    since SCH-2, and ``scope_portfolio_id`` joined them at REPRO-1 (each is required for some
    cadences/families and forbidden for others), so the DTO mirrors the column nullability rather
    than inventing a placeholder."""

    # Why mirroring matters, kept OUT of the docstring because this class's docstring is published
    # as the OpenAPI schema description and generated into the frontend types: a DTO field narrower
    # than its column turns the FIRST row using the new shape into a 500 for the WHOLE page rather
    # than a per-row degradation. `mypy` caught this one when scope_portfolio_id became nullable;
    # nothing would have caught it at runtime until a tenant-wide reproduction schedule existed.

    id: str
    code: str
    name: str
    target_run_type: str
    scope_portfolio_id: str | None
    model_version_id: str | None
    environment_id: str
    cadence_kind: str
    interval_days: int | None
    anchor_date: str  # ISO date
    status: str
    record_version: int
    # The last fire (all NULL when the schedule has never fired).
    last_scheduled_for: datetime | None
    last_fired_at: datetime | None
    last_outcome: str | None
    last_failure_reason: str | None


class ScheduleListOut(BaseModel):
    items: list[ScheduleOut]


class ScheduledRunOut(BaseModel):
    """One fired grid tick. ``scheduled_for`` is the deterministic grid value (INV-SCH-1);
    ``fired_at`` is the wall clock. ``calculation_run_id`` is NULL when dispatch was refused BEFORE
    a run was created — the operator's cue that there is no run to inspect, only ``failure_reason``.
    """

    id: str
    schedule_id: str
    scheduled_for: datetime
    fired_at: datetime
    calculation_run_id: str | None
    resolved_exposure_run_id: str | None
    resolved_covariance_run_id: str | None
    outcome: str
    failure_reason: str | None


class ScheduledRunListOut(BaseModel):
    items: list[ScheduledRunOut]


def _schedule_out(item: ScheduleWithLastFire) -> ScheduleOut:
    s = item.schedule
    return ScheduleOut(
        id=s.id,
        code=s.code,
        name=s.name,
        target_run_type=s.target_run_type,
        scope_portfolio_id=s.scope_portfolio_id,
        model_version_id=s.model_version_id,
        environment_id=s.environment_id,
        cadence_kind=s.cadence_kind,
        interval_days=s.interval_days,
        anchor_date=s.anchor_date.isoformat(),
        status=s.status,
        record_version=s.record_version,
        last_scheduled_for=_utc(item.last_scheduled_for),
        last_fired_at=_utc(item.last_fired_at),
        last_outcome=item.last_outcome,
        last_failure_reason=item.last_failure_reason,
    )


def _run_out(row: ScheduledRun) -> ScheduledRunOut:
    scheduled_for = _utc(row.scheduled_for)
    fired_at = _utc(row.fired_at)
    assert scheduled_for is not None and fired_at is not None  # NOT NULL columns
    return ScheduledRunOut(
        id=row.id,
        schedule_id=row.schedule_id,
        scheduled_for=scheduled_for,
        fired_at=fired_at,
        calculation_run_id=row.calculation_run_id,
        resolved_exposure_run_id=row.resolved_exposure_run_id,
        resolved_covariance_run_id=row.resolved_covariance_run_id,
        outcome=row.outcome,
        failure_reason=row.failure_reason,
    )


# NOTE: ``/runs`` is declared BEFORE any future ``/{schedule_id}`` route — FastAPI matches in
# declaration order, so a path-parameter route added above this one would swallow the literal.
@router.get("/runs", response_model=ScheduledRunListOut)
def list_scheduled_runs_endpoint(
    schedule_id: uuid.UUID | None = Query(default=None),
    outcome: str | None = Query(default=None),
    since: datetime | None = Query(default=None),
    until: datetime | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    principal: Principal = Depends(_require_schedule_view),
    db: Session = Depends(get_tenant_session),
) -> ScheduledRunListOut:
    """The acting tenant's fired-tick ledger, newest first, filtered + paginated.

    ``since``/``until`` bound ``scheduled_for`` (the GRID tick — what an operator reasons about
    calendar-wise), not ``fired_at``. ``outcome=FAILED`` is the burned-month feed the ratification
    asked for. Unknown/foreign ``schedule_id`` is silently empty (no existence oracle).
    """
    rows = list_scheduled_runs(
        db,
        acting_tenant=principal.tenant_id,
        schedule_id=(str(schedule_id) if schedule_id is not None else None),
        outcome=outcome,
        since=since,
        until=until,
        limit=limit,
        offset=offset,
    )
    return ScheduledRunListOut(items=[_run_out(r) for r in rows])


@router.get("", response_model=ScheduleListOut)
def list_schedules_endpoint(
    status: str | None = Query(default=None),
    principal: Principal = Depends(_require_schedule_view),
    db: Session = Depends(get_tenant_session),
) -> ScheduleListOut:
    """The acting tenant's schedule heads (``code`` ASC), each stamped with its last fire.

    A stale ``last_scheduled_for`` relative to the cadence is the ONLY signal of a tick that never
    ran at all — a failed fire leaves a ledger row, an outage leaves nothing. Read-only.
    """
    items = list_schedules(db, acting_tenant=principal.tenant_id, status=status)
    return ScheduleListOut(items=[_schedule_out(i) for i in items])
