"""Read-only scheduling queries (SCH-2, OQ-SCH-2-7c — the operator visibility surface).

**Why this module exists.** A FAILED fire occupies its ``(schedule, tick)`` bucket permanently: the
ledger is IA append-only, the unique constraint forbids a second fire, and ``_UPDATABLE`` forbids a
re-cadence — so at monthly cadence one transient failure BURNS that month with no re-run mechanism
(OD-SCH-2-G). The ratified answer accepts that (a re-fire verb would have to be designed against the
idempotency invariant) on the condition that the failure becomes **visible when it happens** rather
than surfacing months later as an RM-1 alignment refusal. Before SCH-2 there was no API or UI for
schedules at all, so the only detector was that downstream refusal.

Two shapes answer it:

- ``list_schedules`` — the heads, each carrying its **last fire** (tick, outcome, wall clock). A
  schedule whose last fire is months stale is the only signal a tick was missed ENTIRELY (a worker
  outage leaves no ledger row at all — ``record_failed_dispatch`` only occupies the bucket when the
  tick phase actually ran). Computing the expected grid server-side would be a bigger surface than
  ratified; the last-fire stamp makes staleness legible with one join.
- ``list_scheduled_runs`` — the ledger, filterable by schedule and by ``outcome``, so
  ``?outcome=FAILED`` is a direct burned-month feed.

Separate from ``service.py`` on purpose: the service imports the risk + exposure compute stack for
its dispatch registry, and a pure read must not drag that in. The ``audit/queries.py`` precedent.

Both functions are tenant-scoped with an explicit ``tenant_id`` predicate ON TOP of RLS (the
platform's belt-and-suspenders pattern) and are read-only — no write, no audit event.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from irp_shared.scheduling.models import Schedule, ScheduledRun


@dataclass(frozen=True)
class ScheduleWithLastFire:
    """A schedule head plus the ledger row of its most recent fire (``None`` if it never fired)."""

    schedule: Schedule
    last_scheduled_for: datetime | None
    last_fired_at: datetime | None
    last_outcome: str | None
    last_failure_reason: str | None


def list_schedules(
    session: Session,
    *,
    acting_tenant: str,
    status: str | None = None,
) -> list[ScheduleWithLastFire]:
    """The acting tenant's schedule heads (``code`` ASC), each with its last fire.

    The last fire is resolved by joining the ledger on ``(schedule_id, MAX(scheduled_for))``.
    ``uq_scheduled_run_schedule_tick`` guarantees that pair matches AT MOST ONE row, so the join
    needs no tie-break — the constraint that makes a tick idempotent also makes this read exact.
    """
    tenant = str(acting_tenant)
    latest_tick = (
        select(
            ScheduledRun.schedule_id.label("schedule_id"),
            func.max(ScheduledRun.scheduled_for).label("scheduled_for"),
        )
        .where(ScheduledRun.tenant_id == tenant)
        .group_by(ScheduledRun.schedule_id)
        .subquery()
    )
    stmt = (
        select(Schedule, ScheduledRun)
        .outerjoin(
            latest_tick,
            latest_tick.c.schedule_id == Schedule.id,
        )
        .outerjoin(
            ScheduledRun,
            (ScheduledRun.schedule_id == latest_tick.c.schedule_id)
            & (ScheduledRun.scheduled_for == latest_tick.c.scheduled_for),
        )
        .where(Schedule.tenant_id == tenant)
        .order_by(Schedule.code)
    )
    if status is not None:
        stmt = stmt.where(Schedule.status == status)
    rows: list[ScheduleWithLastFire] = []
    for schedule, last in session.execute(stmt).all():
        rows.append(
            ScheduleWithLastFire(
                schedule=schedule,
                last_scheduled_for=(last.scheduled_for if last is not None else None),
                last_fired_at=(last.fired_at if last is not None else None),
                last_outcome=(last.outcome if last is not None else None),
                last_failure_reason=(last.failure_reason if last is not None else None),
            )
        )
    return rows


def list_scheduled_runs(
    session: Session,
    *,
    acting_tenant: str,
    schedule_id: str | None = None,
    outcome: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[ScheduledRun]:
    """The acting tenant's fired-tick ledger, NEWEST FIRST, filtered + paginated.

    ``since``/``until`` bound ``scheduled_for`` (the grid tick — the thing an operator reasons about
    calendar-wise), NOT ``fired_at``. Ordering is total (``scheduled_for`` DESC, ``id`` DESC) so
    pagination is stable. An unknown or foreign ``schedule_id`` is silently empty — the platform's
    entity-filter precedent, and no existence oracle.
    """
    stmt = select(ScheduledRun).where(ScheduledRun.tenant_id == str(acting_tenant))
    if schedule_id is not None:
        stmt = stmt.where(ScheduledRun.schedule_id == str(schedule_id))
    if outcome is not None:
        stmt = stmt.where(ScheduledRun.outcome == outcome)
    if since is not None:
        stmt = stmt.where(ScheduledRun.scheduled_for >= since)
    if until is not None:
        stmt = stmt.where(ScheduledRun.scheduled_for <= until)
    stmt = stmt.order_by(ScheduledRun.scheduled_for.desc(), ScheduledRun.id.desc())
    stmt = stmt.limit(limit).offset(offset)
    return list(session.execute(stmt).scalars())
