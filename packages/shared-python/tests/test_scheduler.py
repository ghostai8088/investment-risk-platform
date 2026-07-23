"""SCH-1 scheduler unit tests (SQLite) — pure cadence, schedule CRUD + audit, append-only,
and the no-backfill / idempotency behavior of ``select_active_due`` (hand-seeded, no real VaR;
the end-to-end dispatch → run_var chain is exercised in the PG/demo tier)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from datetime import date as dt_date

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from irp_shared.audit.models import AppendOnlyViolation, AuditEvent
from irp_shared.scheduling.events import (
    OUTCOME_DISPATCHED,
    SCHEDULE_CREATE_EVENT,
    SCHEDULE_STATUS_ACTIVE,
    SCHEDULE_STATUS_PAUSED,
    SCHEDULE_UPDATE_EVENT,
    SchedulingActor,
)
from irp_shared.scheduling.models import Schedule, ScheduledRun
from irp_shared.scheduling.service import (
    ScheduleError,
    create_schedule,
    current_tick,
    is_due,
    pause_schedule,
    resume_schedule,
    select_active_due,
    update_schedule,
)

_ACTOR = SchedulingActor(actor_id="analyst-1", actor_type="user")
_ANCHOR = dt_date(2026, 1, 1)


def _mk(session: Session, tenant: str, **over: object) -> Schedule:
    kwargs: dict[str, object] = {
        "tenant_id": tenant,
        "code": f"sched-{uuid.uuid4().hex[:8]}",
        "name": "Daily VaR",
        "target_run_type": "VAR",
        "scope_portfolio_id": str(uuid.uuid4()),
        "model_version_id": str(uuid.uuid4()),
        "environment_id": "ci",
        "interval_days": 7,
        "anchor_date": _ANCHOR,
        "actor": _ACTOR,
    }
    kwargs.update(over)
    return create_schedule(session, **kwargs)  # type: ignore[arg-type]


# ------------------------------------------------------------------------- pure cadence math ---
def test_current_tick_on_grid_point_returns_itself() -> None:
    now = datetime(2026, 1, 15, 0, 0, tzinfo=UTC)  # anchor + 2*7d exactly
    assert current_tick(_ANCHOR, 7, now) == datetime(2026, 1, 15, 0, 0, tzinfo=UTC)


def test_current_tick_mid_interval_floors_to_the_last_grid_point() -> None:
    now = datetime(2026, 1, 20, 12, 0, tzinfo=UTC)  # between Jan15 and Jan22
    assert current_tick(_ANCHOR, 7, now) == datetime(2026, 1, 15, 0, 0, tzinfo=UTC)


def test_current_tick_overdue_jumps_to_the_single_current_point_no_backfill() -> None:
    # 21 weeks past the anchor — the current tick is ONE point, not a backfilled series.
    now = datetime(2026, 6, 1, 0, 0, tzinfo=UTC)
    tick = current_tick(_ANCHOR, 7, now)
    assert tick == datetime(2026, 5, 28, 0, 0, tzinfo=UTC)  # the most recent grid point <= now


def test_current_tick_at_anchor_is_the_anchor() -> None:
    assert current_tick(_ANCHOR, 7, datetime(2026, 1, 1, 0, 0, tzinfo=UTC)) == datetime(
        2026, 1, 1, 0, 0, tzinfo=UTC
    )


def test_current_tick_rejects_non_positive_interval() -> None:
    with pytest.raises(ScheduleError):
        current_tick(_ANCHOR, 0, datetime(2026, 1, 2, tzinfo=UTC))


def test_is_due_true_for_active_unfired_current_tick(session: Session) -> None:
    tenant = str(uuid.uuid4())
    sched = _mk(session, tenant)
    now = datetime(2026, 1, 15, tzinfo=UTC)
    assert is_due(sched, now, fired_ticks=set()) is True


def test_is_due_false_when_paused(session: Session) -> None:
    tenant = str(uuid.uuid4())
    sched = _mk(session, tenant, status=SCHEDULE_STATUS_PAUSED)
    now = datetime(2026, 1, 15, tzinfo=UTC)
    assert is_due(sched, now, fired_ticks=set()) is False


def test_is_due_false_before_anchor(session: Session) -> None:
    tenant = str(uuid.uuid4())
    sched = _mk(session, tenant, anchor_date=dt_date(2026, 3, 1))
    now = datetime(2026, 1, 15, tzinfo=UTC)
    assert is_due(sched, now, fired_ticks=set()) is False


def test_is_due_false_when_current_tick_already_fired(session: Session) -> None:
    tenant = str(uuid.uuid4())
    sched = _mk(session, tenant)
    now = datetime(2026, 1, 15, tzinfo=UTC)
    tick = current_tick(_ANCHOR, 7, now)
    assert is_due(sched, now, fired_ticks={tick}) is False


# ----------------------------------------------------------------- schedule CRUD + audit ---
def test_create_schedule_emits_schedule_create_and_sets_v1(session: Session) -> None:
    tenant = str(uuid.uuid4())
    sched = _mk(session, tenant)
    assert sched.record_version == 1
    assert sched.status == SCHEDULE_STATUS_ACTIVE
    events = list(
        session.execute(
            select(AuditEvent).where(AuditEvent.event_type == SCHEDULE_CREATE_EVENT)
        ).scalars()
    )
    assert len(events) == 1
    assert events[0].chain_id == tenant


def test_pause_then_resume_emits_updates_and_bumps_version(session: Session) -> None:
    tenant = str(uuid.uuid4())
    sched = _mk(session, tenant)
    pause_schedule(session, sched, actor=_ACTOR)
    assert sched.status == SCHEDULE_STATUS_PAUSED
    assert sched.record_version == 2
    resume_schedule(session, sched, actor=_ACTOR)
    assert sched.status == SCHEDULE_STATUS_ACTIVE
    assert sched.record_version == 3
    updates = list(
        session.execute(
            select(AuditEvent).where(AuditEvent.event_type == SCHEDULE_UPDATE_EVENT)
        ).scalars()
    )
    assert len(updates) == 2


def test_create_rejects_unschedulable_run_type(session: Session) -> None:
    with pytest.raises(ScheduleError):
        _mk(session, str(uuid.uuid4()), target_run_type="ACTIVE_RISK")


def test_create_rejects_non_positive_interval_and_empty_environment(session: Session) -> None:
    with pytest.raises(ScheduleError):
        _mk(session, str(uuid.uuid4()), interval_days=0)
    with pytest.raises(ScheduleError):
        _mk(session, str(uuid.uuid4()), environment_id="")


def test_update_rejects_non_updatable_attribute(session: Session) -> None:
    tenant = str(uuid.uuid4())
    sched = _mk(session, tenant)
    with pytest.raises(ScheduleError):
        update_schedule(session, sched, actor=_ACTOR, interval_days=3)


# ------------------------------------------------------------------------- append-only guard ---
def test_scheduled_run_is_append_only(session: Session) -> None:
    tenant = str(uuid.uuid4())
    sched = _mk(session, tenant)
    row = ScheduledRun(
        tenant_id=tenant,
        schedule_id=sched.id,
        scheduled_for=datetime(2026, 1, 15, tzinfo=UTC),
        fired_at=datetime(2026, 1, 15, 6, 0, tzinfo=UTC),
        outcome=OUTCOME_DISPATCHED,
    )
    session.add(row)
    session.flush()
    row.outcome = "FAILED"
    with pytest.raises(AppendOnlyViolation):
        session.flush()


# ------------------------------------------------- select_active_due: no-backfill + idem ---
def _seed_fired(session: Session, sched: Schedule, tick: datetime) -> None:
    session.add(
        ScheduledRun(
            tenant_id=sched.tenant_id,
            schedule_id=sched.id,
            scheduled_for=tick,
            fired_at=tick,
            outcome=OUTCOME_DISPATCHED,
        )
    )
    session.flush()


def test_select_active_due_returns_the_current_tick_for_a_fresh_schedule(
    session: Session,
) -> None:
    tenant = str(uuid.uuid4())
    sched = _mk(session, tenant)
    now = datetime(2026, 1, 20, tzinfo=UTC)
    due = select_active_due(session, now)
    assert len(due) == 1
    got_sched, got_tick = due[0]
    assert got_sched.id == sched.id
    assert got_tick == datetime(2026, 1, 15, tzinfo=UTC)  # current tick, not the anchor


def test_select_active_due_excludes_a_paused_schedule(session: Session) -> None:
    tenant = str(uuid.uuid4())
    _mk(session, tenant, status=SCHEDULE_STATUS_PAUSED)
    assert select_active_due(session, datetime(2026, 1, 20, tzinfo=UTC)) == []


def test_select_active_due_excludes_an_already_fired_current_tick(session: Session) -> None:
    tenant = str(uuid.uuid4())
    sched = _mk(session, tenant)
    now = datetime(2026, 1, 20, tzinfo=UTC)
    _seed_fired(session, sched, current_tick(_ANCHOR, 7, now))
    assert select_active_due(session, now) == []  # idempotent — no re-fire of the same tick


def test_select_active_due_overdue_fires_one_tick_not_a_backfill_series(
    session: Session,
) -> None:
    tenant = str(uuid.uuid4())
    _mk(session, tenant)
    now = datetime(2026, 6, 1, tzinfo=UTC)  # ~21 intervals past the anchor
    due = select_active_due(session, now)
    assert len(due) == 1  # exactly ONE due tick, never a burst of the missed intervals
    assert due[0][1] == datetime(2026, 5, 28, tzinfo=UTC)


def test_paused_over_a_window_then_resume_fires_only_the_current_tick(session: Session) -> None:
    # Fire an early tick, pause across many intervals, resume far later: only the CURRENT tick is
    # due — NOT a catch-up storm of the paused window (the OD-SCH-1-F / verifier 3B fold).
    tenant = str(uuid.uuid4())
    sched = _mk(session, tenant)
    _seed_fired(session, sched, datetime(2026, 1, 8, tzinfo=UTC))  # an early fire
    pause_schedule(session, sched, actor=_ACTOR)
    assert select_active_due(session, datetime(2026, 4, 1, tzinfo=UTC)) == []  # paused
    resume_schedule(session, sched, actor=_ACTOR)
    now = datetime(2026, 4, 2, tzinfo=UTC)
    due = select_active_due(session, now)
    assert len(due) == 1
    assert due[0][1] == current_tick(_ANCHOR, 7, now)  # the current tick, one fire only
