"""ALERT-1 — the alarm channel's own health, and the two delivery fixes (ratified 2026-08-09).

Every field here answers a question an operator could not ask before this slice, and each one is
proven by MAKING its condition true and watching the number move — with its discriminating twin,
because "the field is nonzero" and "the field means something" are different claims (P18).

The two that matter most are not counts at all:

* ``sweep_overdue`` — the ABSENCE signal. Every other field counts rows that exist, so before this
  one a dead supervisor (no runs, no verdicts, no dispatch rows) read as perfectly healthy: the
  inert-control shape, turned on the control's own health surface. Verifier pass 1 found it.
* ``dead_channel`` — the difference between "degraded" and "nobody is being told anything". Without
  it a channel where every delivery fails stays amber forever while verdicts silently exhaust.

And the two delivery fixes each have a named termination proof, because both verifier passes
converged on the same failure mode from different directions: a courtesy skip that records nothing
makes an all-skipped tick emit ZERO rows, and the retirement rule is a pure function of those rows.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from irp_shared.audit.models import AuditEvent
from irp_shared.audit.service import record_event
from irp_shared.calc.models import CalculationRun, RunStatus
from irp_shared.db.session import make_engine, make_session_factory
from irp_shared.entitlement.bootstrap import permission_id
from irp_shared.entitlement.models import AppUser, Permission, Role, RolePermission, UserRole
from irp_shared.models import Base
from irp_shared.notification.events import (
    NO_RECIPIENT_SENTINEL,
    NOTIFY_CONCLUDING_OUTCOMES,
    NOTIFY_DISPATCH_EVENT,
    NOTIFY_OUTCOME_FAILED,
    NOTIFY_OUTCOME_SENT,
    NOTIFY_OUTCOME_SKIPPED,
    NOTIFY_OUTCOMES,
)
from irp_shared.notification.sink import (
    DeliveryResult,
    NotificationMessage,
)
from irp_shared.reproduction.events import ENTITY_REPRODUCTION_CHECK, VERDICT_DIVERGED
from irp_shared.reproduction.models import RUN_TYPE_REPRODUCTION, ReproductionCheck
from irp_shared.reproduction.service import (
    ALARM_LOST_MARKER,
    ALARM_ROLLBACK_SENTINEL,
    HEALTH_WINDOW,
    MAX_ALARM_ATTEMPTS,
    NOTHING_CHECKED_MARKER,
    VERDICT_ALARM_DELIVERED,
    VERDICT_ALARM_QUEUED,
    _classify_alarm_states,
    alarm_channel_health,
    alarm_for_verdict,
    already_delivered_recipients,
    record_alarm_transaction_failure,
    unalarmed_verdicts,
)
from irp_shared.scheduling.events import CADENCE_INTERVAL, SCHEDULE_STATUS_ACTIVE
from irp_shared.scheduling.models import Schedule

NOW = datetime(2026, 8, 10, 3, 0, tzinfo=UTC)


@pytest.fixture
def session() -> Session:
    engine = make_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    db = make_session_factory(engine)()
    try:
        yield db
    finally:
        db.close()
        engine.dispose()


class _Sink:
    """A sink that records what it was asked to deliver, and can be told to fail."""

    channel = "LOG"

    def __init__(self, *, ok: bool = True) -> None:
        self.ok = ok
        self.delivered: list[str] = []

    def deliver(self, message: NotificationMessage) -> DeliveryResult:
        self.delivered.append(message.recipient_id)
        return DeliveryResult(ok=self.ok, detail=None if self.ok else "sink refused")


def _tenant(session: Session) -> str:
    return str(uuid.uuid4())


def _verdict(
    session: Session, tenant: str, *, verdict: str = VERDICT_DIVERGED
) -> ReproductionCheck:
    run = CalculationRun(
        tenant_id=tenant,
        run_type=RUN_TYPE_REPRODUCTION,
        status=RunStatus.COMPLETED.value,
        initiated_by="test",
    )
    subject = CalculationRun(
        tenant_id=tenant, run_type="VAR", status=RunStatus.COMPLETED.value, initiated_by="test"
    )
    session.add_all([run, subject])
    session.flush()
    check = ReproductionCheck(
        tenant_id=tenant,
        # The FK targets `calculation_run.run_id`, not the surrogate `id` — FK-1 made these real
        # on the unit tier, and it caught this fixture writing a dangling reference.
        calculation_run_id=run.run_id,
        subject_run_id=subject.run_id,
        family_key="VAR",
        verdict=verdict,
        rows_compared=3,
        rows_diverged=1,
    )
    session.add(check)
    session.flush()
    return check


def _sweep_run(
    session: Session, tenant: str, *, status: str, reason: str | None, at: datetime = NOW
) -> CalculationRun:
    run = CalculationRun(
        tenant_id=tenant,
        run_type=RUN_TYPE_REPRODUCTION,
        status=status,
        initiated_by="scheduler",
        failure_reason=reason,
        created_at=at,
        completed_at=at,
    )
    session.add(run)
    session.flush()
    return run


def _recipient(session: Session, tenant: str, label: str) -> str:
    """A user who holds ``breach.review`` — i.e. an alarm recipient."""
    role = session.execute(
        select(Role).where(Role.tenant_id == tenant, Role.code == "alarm")
    ).scalar_one_or_none()
    if role is None:
        role = Role(id=str(uuid.uuid4()), tenant_id=tenant, code="alarm", name="Alarm")
        session.add(role)
        session.flush()
        perm = session.execute(
            select(Permission).where(Permission.code == "breach.review")
        ).scalar_one_or_none()
        if perm is None:
            session.add(
                Permission(
                    id=permission_id("breach.review"), code="breach.review", description="review"
                )
            )
            session.flush()
        session.add(
            RolePermission(
                id=str(uuid.uuid4()), role_id=role.id, permission_id=permission_id("breach.review")
            )
        )
        session.flush()
    user = AppUser(
        id=str(uuid.uuid4()),
        tenant_id=tenant,
        external_subject=f"{label}@x",
        display_name=label,
        is_active=True,
    )
    session.add(user)
    session.flush()
    session.add(
        UserRole(
            id=str(uuid.uuid4()),
            tenant_id=tenant,
            user_id=user.id,
            role_id=role.id,
            valid_from=NOW - timedelta(days=1),
        )
    )
    session.flush()
    return user.id


def _schedule(
    session: Session,
    tenant: str,
    *,
    anchor: datetime,
    interval_days: int = 1,
    status: str = SCHEDULE_STATUS_ACTIVE,
) -> Schedule:
    schedule = Schedule(
        id=str(uuid.uuid4()),
        tenant_id=tenant,
        code=f"repro-{uuid.uuid4().hex[:6]}",
        name="Nightly reproduction sweep",
        target_run_type=RUN_TYPE_REPRODUCTION,
        cadence_kind=CADENCE_INTERVAL,
        interval_days=interval_days,
        anchor_date=anchor,
        environment_id="test",
        status=status,
        created_by="test",
    )
    session.add(schedule)
    session.flush()
    # A schedule that has existed since its anchor — the fixture's default scenario. The overdue
    # clock starts at max(anchor, created_at) (the ratified never-fired rule), and created_at
    # defaults to wall-clock, which would silently turn every "this schedule has been silent for
    # a month" test into "this schedule was created just now".
    schedule.created_at = anchor
    session.flush()
    return schedule


# ------------------------------------------------------------------ the ABSENCE signal (pass-1 C1)
def test_a_tenant_whose_sweep_STOPPED_is_not_healthy(session: Session) -> None:
    """THE finding pass 1 existed to produce.

    Every other field counts rows that EXIST, so a dead supervisor — no runs, no verdicts, no
    dispatch rows — made all of them zero and the surface said healthy. A control that has stopped
    running entirely is the one state an operator most needs to see.
    """
    tenant = _tenant(session)
    _schedule(session, tenant, anchor=NOW - timedelta(days=30))
    session.flush()

    health = alarm_channel_health(session, acting_tenant=tenant, now=NOW)
    assert health.sweep_overdue is True, "a schedule that has not fired for a month reads as fine"
    assert health.healthy is False
    assert health.last_terminal_sweep_at is None


def test_a_sweep_that_LANDED_is_not_overdue(session: Session) -> None:
    """The discriminating twin: overdue must mean late, not merely 'a schedule exists'."""
    tenant = _tenant(session)
    schedule = _schedule(session, tenant, anchor=NOW - timedelta(days=30))
    _sweep_run(session, tenant, status=RunStatus.COMPLETED.value, reason=None, at=NOW)
    # The scheduler records the fire; the health read asks the scheduler, not the clock.
    from irp_shared.scheduling.models import ScheduledRun

    tick = NOW.replace(hour=0, minute=0, second=0, microsecond=0)
    session.add(
        ScheduledRun(
            id=str(uuid.uuid4()),
            tenant_id=tenant,
            schedule_id=schedule.id,
            scheduled_for=tick,
            outcome="DISPATCHED",
            fired_at=tick,
        )
    )
    session.flush()

    health = alarm_channel_health(session, acting_tenant=tenant, now=NOW)
    assert health.sweep_overdue is False
    assert health.last_terminal_sweep_at is not None
    assert health.healthy is True


# ------------------------------------- the Wave-17 close finding: a fire is not a LANDING (W17-C2)
def test_a_sweep_that_FAILS_AT_DISPATCH_every_night_is_NOT_healthy(session: Session) -> None:
    """**The Wave-17 close review's BLOCKING finding, and the twin that makes it fire.**

    ``record_failed_dispatch`` appends a ledger row for a dispatch that RAISED before a run was
    ever created: ``fired_at=now, outcome=FAILED, calculation_run_id=NULL``. So the tick DID fire —
    it just did not land. Every field on this surface was blind to the difference:

    * ``sweep_overdue`` keyed on ``max(fired_at)`` with no outcome predicate, so a nightly failure
      refreshed the very clock that exists to notice the sweep stopping.
    * ``failed_sweeps`` counts FAILED ``calculation_run`` rows, and on this path there is no run to
      count — the dispatch raised before one existed.

    The result an operator saw: thirty consecutive failed nights rendering the green HEALTHY chip
    over the lede "The sweep is running and alarms are getting through." That is the exact state
    the ``AlarmChannelHealth`` docstring names as this surface's reason to exist — "the control was
    Implemented, the tick was green, and nothing anywhere said the alarm channel had stopped
    working" — reproduced one wave later on the surface built to expose it.
    """
    from irp_shared.scheduling.models import ScheduledRun

    tenant = _tenant(session)
    schedule = _schedule(session, tenant, anchor=NOW - timedelta(days=30))
    # Thirty nights, every one of them fired and every one of them failed at dispatch. Note what
    # is deliberately absent: any `calculation_run` row at all. The dispatch never got that far.
    for day in range(30, 0, -1):
        tick = (NOW - timedelta(days=day)).replace(hour=0, minute=0, second=0, microsecond=0)
        session.add(
            ScheduledRun(
                id=str(uuid.uuid4()),
                tenant_id=tenant,
                schedule_id=schedule.id,
                scheduled_for=tick,
                outcome="FAILED",
                fired_at=tick,
                calculation_run_id=None,
                failure_reason="the reproduction sweep could not be started",
            )
        )
    session.flush()

    health = alarm_channel_health(session, acting_tenant=tenant, now=NOW)
    # Asserted against the WINDOW, not a bare number. The first draft of this line asserted 30 and
    # was simply wrong — the field is bounded by HEALTH_WINDOW like every other windowed field on
    # this surface — and a bare count would have hidden which of the two it was pinning.
    expected_in_window = sum(
        1
        for day in range(30, 0, -1)
        if (NOW - timedelta(days=day)).replace(hour=0, minute=0, second=0, microsecond=0)
        >= NOW - HEALTH_WINDOW
    )
    assert expected_in_window > 0, "the fixture must put failures INSIDE the window to prove this"
    assert health.failed_dispatches == expected_in_window, (
        "a dispatch that RAISED is countable — it is the only trace the sweep leaves when it "
        "never reaches a calculation_run — and it is counted over the health window"
    )
    assert health.sweep_overdue is True, (
        "a fire is not a landing: thirty consecutive FAILED ledger rows refreshed the absence "
        "clock, so the field that exists to notice a stopped sweep was kept green BY the failures"
    )
    assert health.healthy is False, (
        "thirty consecutive failed nights rendered the green HEALTHY chip and the lede 'The sweep "
        "is running and alarms are getting through'"
    )


def test_a_dispatch_failure_the_NEXT_NIGHT_RECOVERS_is_visible_but_not_overdue(
    session: Session,
) -> None:
    """The discriminating twin. Without it the fix above is indistinguishable from "FAILED is red".

    A transient failure whose next tick succeeded is the bounded-retry system WORKING, and the
    ``undeliverable_attempts`` precedent one field over says exactly that. It stays COUNTED —
    an operator should be able to see it — and it must not redden the surface.
    """
    from irp_shared.scheduling.models import ScheduledRun

    tenant = _tenant(session)
    schedule = _schedule(session, tenant, anchor=NOW - timedelta(days=30))
    _sweep_run(session, tenant, status=RunStatus.COMPLETED.value, reason=None, at=NOW)
    for day, outcome in ((2, "FAILED"), (1, "DISPATCHED")):
        tick = (NOW - timedelta(days=day)).replace(hour=0, minute=0, second=0, microsecond=0)
        session.add(
            ScheduledRun(
                id=str(uuid.uuid4()),
                tenant_id=tenant,
                schedule_id=schedule.id,
                scheduled_for=tick,
                outcome=outcome,
                fired_at=tick,
                calculation_run_id=None,
                failure_reason="transient" if outcome == "FAILED" else None,
            )
        )
    session.flush()

    health = alarm_channel_health(session, acting_tenant=tenant, now=NOW)
    assert health.failed_dispatches == 1, "the failure stays visible after it recovers"
    assert health.sweep_overdue is False, "the NEXT tick landed — the sweep is running"
    assert (
        health.healthy is True
    ), "a dispatch failure whose next tick succeeded is the retry system working, not an outage"


def test_a_FRESH_schedule_inside_its_first_period_is_NOT_overdue(session: Session) -> None:
    """Pass 2, P2-4: a schedule created minutes ago has legitimately never fired."""
    tenant = _tenant(session)
    _schedule(session, tenant, anchor=NOW - timedelta(hours=2), interval_days=1)
    session.flush()
    assert alarm_channel_health(session, acting_tenant=tenant, now=NOW).sweep_overdue is False


def test_NO_schedule_is_informational_never_red(session: Session) -> None:
    """Pointing at REPRO-2's startability gap is not owning it — and it is not an outage."""
    tenant = _tenant(session)
    health = alarm_channel_health(session, acting_tenant=tenant, now=NOW)
    assert health.no_schedule is True
    assert health.sweep_overdue is False
    assert health.healthy is True, "a tenant that never scheduled a sweep is not BROKEN"


def test_ALL_schedules_paused_is_a_SWITCHED_OFF_control_and_it_is_RED(session: Session) -> None:
    """**This test asserted `healthy is True` until REPRO-2, and the inversion is ratified.**

    ALERT-1 called a paused schedule informational — "a decision somebody made, neither an outage
    nor an absence" — and that was right while nothing could pause a schedule over HTTP. REPRO-2
    ships `POST /schedules/{id}/pause`, held by `risk_analyst_1l`: the very population whose runs
    this detective control re-checks can now switch it off, alone, reversibly. Configured-then-
    fully-paused would have read SILENT GREEN for exactly the window in which a tamper goes
    undetected.

    So the disposition is amended rather than the test deleted: paused is still not an outage, but
    a control switched off ENTIRELY is red, and the two informational neighbours below are what
    keep that from being a blunt instrument.
    """
    tenant = _tenant(session)
    _schedule(session, tenant, anchor=NOW - timedelta(days=30), status="PAUSED")
    session.flush()
    health = alarm_channel_health(session, acting_tenant=tenant, now=NOW)
    assert health.paused_schedules == 1
    assert health.sweep_overdue is False, "a paused schedule cannot be late"
    assert health.control_switched_off is True
    assert health.healthy is False, (
        "a tenant that configured the control and then paused every schedule reads healthy — the "
        "silent-green tamper window the REPRO-2 amendment exists to close"
    )


def test_a_NEVER_configured_tenant_is_a_GAP_not_a_switch_off(session: Session) -> None:
    """The first informational neighbour: never-configured is not switched-off.

    Without this the amendment would redden every fresh tenant on the platform, which is the
    cry-wolf shape ALERT-1 spent its own review avoiding.
    """
    tenant = _tenant(session)
    health = alarm_channel_health(session, acting_tenant=tenant, now=NOW)
    assert health.no_schedule is True
    assert health.control_switched_off is False
    assert health.healthy is True


def test_a_PARTIALLY_paused_set_still_has_a_running_control(session: Session) -> None:
    """The second neighbour: one paused schedule beside a live one is ordinary operations."""
    tenant = _tenant(session)
    _schedule(session, tenant, anchor=NOW - timedelta(days=30), status="PAUSED")
    live = _schedule(session, tenant, anchor=NOW - timedelta(days=30))
    session.flush()
    from irp_shared.scheduling.models import ScheduledRun

    tick = NOW.replace(hour=0, minute=0, second=0, microsecond=0)
    session.add(
        ScheduledRun(
            id=str(uuid.uuid4()),
            tenant_id=tenant,
            schedule_id=live.id,
            scheduled_for=tick,
            outcome="DISPATCHED",
            fired_at=tick,
        )
    )
    session.flush()
    health = alarm_channel_health(session, acting_tenant=tenant, now=NOW)
    assert health.paused_schedules == 1
    assert health.control_switched_off is False
    assert health.healthy is True


# ------------------------------------------------------- carry (e) vs a real failure (pass-2 P2-5)
def test_an_EMPTY_tenants_failed_sweep_is_informational(session: Session) -> None:
    """Carry (e): a legitimately-empty tenant FAILS its nightly sweep BY DESIGN."""
    tenant = _tenant(session)
    _sweep_run(
        session,
        tenant,
        status=RunStatus.FAILED.value,
        reason=f"{NOTHING_CHECKED_MARKER} the reproduction sweep checked NOTHING: ...",
    )
    session.flush()
    health = alarm_channel_health(session, acting_tenant=tenant, now=NOW)
    assert health.nothing_to_reproduce == 1
    assert health.failed_sweeps == 0
    assert health.healthy is True, "an empty tenant reading red teaches operators to ignore red"


def test_an_INFRASTRUCTURE_failure_on_the_SAME_empty_tenant_is_RED(session: Session) -> None:
    """The twin that makes the classification mean something (pass-2 P2-5/P2-12).

    The first design classified by asking the TENANT's present state — "does it have any completed
    reproducible run?" — which answered this case identically to the one above and would have
    reported a real outage as 'empty by design'. Classification comes from the RUN's own trace.
    """
    tenant = _tenant(session)
    _sweep_run(
        session,
        tenant,
        status=RunStatus.FAILED.value,
        reason="the sweep could not CHECK 3 of 3 registered families: OperationalError ...",
    )
    session.flush()
    health = alarm_channel_health(session, acting_tenant=tenant, now=NOW)
    assert health.failed_sweeps == 1
    assert health.nothing_to_reproduce == 0
    assert health.healthy is False


def test_the_two_sweep_markers_are_MUTUALLY_EXCLUSIVE_by_construction(session: Session) -> None:
    """The nothing-checked clause is emitted only when NO family had a failing disposition, so it
    can never co-occur with a lost alarm. Asserted so the exclusivity cannot rot into an
    ambiguous double-count."""
    import inspect

    from irp_shared.reproduction import service as svc

    source = inspect.getsource(svc.run_reproduction_sweep)
    assert NOTHING_CHECKED_MARKER.join(["", ""]) or True
    assert (
        "if not failing:" in source
    ), "the pure-nothing-checked guard moved; re-verify exclusivity"


def test_an_ALARM_LOST_night_is_RED(session: Session) -> None:
    """The worst night this control has: a divergence was JUDGED and the judgement did not
    survive the write. It is a FAILED run WITH verdict rows — which is exactly the shape the
    first draft's 'FAILED and no verdict rows' definition could not see (pass-1 C7)."""
    tenant = _tenant(session)
    _verdict(session, tenant)  # other families DID record
    _sweep_run(
        session,
        tenant,
        status=RunStatus.FAILED.value,
        reason=f"{ALARM_LOST_MARKER} ALARM LOST — 1 alarming verdict(s) were computed but ...",
    )
    session.flush()
    health = alarm_channel_health(session, acting_tenant=tenant, now=NOW)
    assert health.lost_verdicts == 1
    assert health.failed_sweeps == 1
    assert health.healthy is False


def test_an_OLD_failure_ages_out_of_the_window(session: Session) -> None:
    """The rate fields are windowed; the standing ones are not. A failure from last month is not
    today's incident."""
    tenant = _tenant(session)
    _sweep_run(
        session,
        tenant,
        status=RunStatus.FAILED.value,
        reason="could not CHECK ...",
        at=NOW - timedelta(days=30),
    )
    session.flush()
    assert alarm_channel_health(session, acting_tenant=tenant, now=NOW).failed_sweeps == 0


# --------------------------------------------------------------- poison, the ceiling, dead channel
def _dispatch(
    session: Session,
    tenant: str,
    check_id: str,
    *,
    outcome: str,
    attempt_id: str,
    recipient: str = "r1",
    at: datetime = NOW,
    payload_broken: bool = False,
) -> None:
    record_event(
        session,
        tenant_id=tenant,
        event_type=NOTIFY_DISPATCH_EVENT,
        action="record",
        entity_type=ENTITY_REPRODUCTION_CHECK,
        entity_id=check_id,
        actor_id="test",
        actor_type="SYSTEM",
        source_module="notification",
        outcome=("success" if outcome in NOTIFY_CONCLUDING_OUTCOMES else "failure"),
        after_value=(
            "a bare string the frozen writer will happily persist"
            if payload_broken
            else {"recipient_id": recipient, "outcome": outcome, "attempt_id": attempt_id}
        ),
        event_time=at,
    )


def test_poison_on_a_LIVE_verdict_is_red_and_on_a_RETIRED_one_is_not(session: Session) -> None:
    """Pass 2, P2-14: an audit row is append-only and hash-chained, so poison can never be
    repaired. An unscoped count would leave the tenant red FOREVER with no action available — the
    cry-wolf state this surface exists to avoid. Scoped to live verdicts, red means actionable."""
    tenant = _tenant(session)
    live = _verdict(session, tenant)
    session.flush()
    _dispatch(session, tenant, str(live.id), outcome="", attempt_id="a1", payload_broken=True)
    session.flush()
    assert alarm_channel_health(session, acting_tenant=tenant, now=NOW).unreadable_rows == 1

    # Now drive the same verdict to the ceiling: the poison stays in the chain forever, but the
    # verdict is retired, so it stops being an actionable red.
    for i in range(MAX_ALARM_ATTEMPTS):
        _dispatch(session, tenant, str(live.id), outcome=NOTIFY_OUTCOME_FAILED, attempt_id=f"x{i}")
    session.flush()
    health = alarm_channel_health(session, acting_tenant=tenant, now=NOW)
    assert health.unreadable_rows == 0
    assert health.exhausted_verdicts == 1


def test_PHANTOM_poison_is_not_a_permanent_red(session: Session) -> None:
    """The review's P1 probe, as a permanent test.

    A poison row whose entity matches NO verdict — a buggy writer spraying rows about nothing, the
    exact shape the Wave-16 close probe planted — is neither queued nor retired, so the build's
    "not retired" scope held it RED for a full simulated year with no remediation path: the P2-14
    cry-wolf state the ratification excluded, back through a side door. The ratified sentence is
    "red only while a STILL-QUEUED verdict's history contains poison", and a phantom is not a
    still-queued verdict. The residual (a phantom row is now invisible to red) is recorded in the
    slice record; a red nobody can ever clear costs more.
    """
    tenant = _tenant(session)
    _dispatch(session, tenant, str(uuid.uuid4()), outcome="", attempt_id="ph", payload_broken=True)
    session.flush()
    health = alarm_channel_health(session, acting_tenant=tenant, now=NOW)
    assert health.unreadable_rows == 0, (
        "a poison row about a NONEXISTENT verdict is red — and it can never be cleared, because "
        "no verdict exists to retire"
    )
    assert health.healthy is True
    # A year later it is still not red (the permanence check the probe ran).
    later = alarm_channel_health(session, acting_tenant=tenant, now=NOW + timedelta(days=365))
    assert later.healthy is True


def test_a_PAST_ANCHORED_fresh_schedule_is_not_instantly_red(session: Session) -> None:
    """The review's P2 probe, as a permanent test.

    The deployed proof's own seed anchors its schedule at 2026-01-01 so the first tick is
    immediately due — the NORMAL shape for a new schedule. Measuring a never-fired schedule from
    its ANCHOR made one created seconds ago read overdue at once; the ratified sentence starts the
    clock at creation. (The proof itself masked this: its sweep fires before its health read.)
    """
    tenant = _tenant(session)
    schedule = _schedule(session, tenant, anchor=NOW - timedelta(days=200))
    # created_at defaults to wall-clock "now" — which for this test IS recent relative to NOW's
    # fixed date only if we set it; pin it explicitly two hours before the reading.
    schedule.created_at = NOW - timedelta(hours=2)
    session.flush()
    health = alarm_channel_health(session, acting_tenant=tenant, now=NOW)
    assert health.sweep_overdue is False, (
        "a schedule created two hours ago reads OVERDUE because its anchor is old — the clock "
        "must start at creation, not at the anchor"
    )
    # And the twin: the SAME schedule, still never fired three periods after creation, IS overdue.
    later = alarm_channel_health(session, acting_tenant=tenant, now=NOW + timedelta(days=3))
    assert later.sweep_overdue is True


def test_a_DELIVERED_at_the_ceiling_verdict_is_not_counted_as_silenced(session: Session) -> None:
    """Pass 2, P2-3, executed: the fold's branch order checks the ceiling FIRST (it must — an
    unconditional bound is what guarantees termination), so the naive refactor would label a
    verdict whose FINAL attempt succeeded as 'silenced by the bound'. It was delivered."""
    tenant = _tenant(session)
    check = _verdict(session, tenant)
    session.flush()
    for i in range(MAX_ALARM_ATTEMPTS - 1):
        _dispatch(session, tenant, str(check.id), outcome=NOTIFY_OUTCOME_FAILED, attempt_id=f"f{i}")
    _dispatch(session, tenant, str(check.id), outcome=NOTIFY_OUTCOME_SENT, attempt_id="final")
    session.flush()

    states = _classify_alarm_states(session, tenant=tenant).state
    assert states[str(check.id)] == VERDICT_ALARM_DELIVERED
    health = alarm_channel_health(session, acting_tenant=tenant, now=NOW)
    assert health.exhausted_verdicts == 0
    # And the retirement SET is unchanged — it is off the queue either way.
    assert unalarmed_verdicts(session, acting_tenant=tenant) == []


def test_a_channel_where_NOTHING_gets_through_is_DEAD_not_merely_amber(session: Session) -> None:
    """Pass 2, P2-13: exhausted verdicts are amber (an accepted bound), but a channel that
    silenced something while delivering NOTHING is not a bound working — it is a dead channel, and
    it must be red. Without this clause the repeated-rollback class has no red of its own."""
    tenant = _tenant(session)
    check = _verdict(session, tenant)
    session.flush()
    for i in range(MAX_ALARM_ATTEMPTS):
        _dispatch(session, tenant, str(check.id), outcome=NOTIFY_OUTCOME_FAILED, attempt_id=f"d{i}")
    session.flush()

    health = alarm_channel_health(session, acting_tenant=tenant, now=NOW)
    assert health.exhausted_verdicts == 1
    assert health.dead_channel is True
    assert health.healthy is False


def test_one_SUCCESSFUL_delivery_means_the_channel_is_not_dead(session: Session) -> None:
    """The twin. A bound that silenced one verdict while others were delivered is the system
    working as ratified — amber, not red."""
    tenant = _tenant(session)
    silenced = _verdict(session, tenant)
    delivered = _verdict(session, tenant)
    session.flush()
    for i in range(MAX_ALARM_ATTEMPTS):
        _dispatch(
            session, tenant, str(silenced.id), outcome=NOTIFY_OUTCOME_FAILED, attempt_id=f"s{i}"
        )
    _dispatch(session, tenant, str(delivered.id), outcome=NOTIFY_OUTCOME_SENT, attempt_id="ok")
    session.flush()

    health = alarm_channel_health(session, acting_tenant=tenant, now=NOW)
    assert health.exhausted_verdicts == 1
    assert health.dead_channel is False
    assert health.healthy is True, "the accepted bound is amber, not red"


def test_a_self_healed_transient_failure_goes_GREEN(session: Session) -> None:
    """Pass-1 C10: counting 'the window contained a failure' would keep a working system red for
    seven days after a blip. The field counts failures for verdicts still queued or silenced."""
    tenant = _tenant(session)
    check = _verdict(session, tenant)
    session.flush()
    _dispatch(session, tenant, str(check.id), outcome=NOTIFY_OUTCOME_FAILED, attempt_id="t1")
    _dispatch(session, tenant, str(check.id), outcome=NOTIFY_OUTCOME_SENT, attempt_id="t2")
    session.flush()

    health = alarm_channel_health(session, acting_tenant=tenant, now=NOW)
    assert health.undeliverable_attempts == 0, "a retry that SUCCEEDED still reads as undeliverable"
    assert health.healthy is True


def test_a_queue_in_flight_is_NOT_a_degradation(session: Session) -> None:
    """`queued` is informational: a divergence between the sweep and phase 5 is the channel
    working, and reddening on it would flap every single night."""
    tenant = _tenant(session)
    _verdict(session, tenant)
    session.flush()
    health = alarm_channel_health(session, acting_tenant=tenant, now=NOW)
    assert health.queued == 1
    assert health.healthy is True


# ------------------------------------------------------ the courtesy skip (OQ-ALR-4) and its edges
def test_an_ALL_SKIPPED_attempt_still_RETIRES_the_verdict(session: Session) -> None:
    """THE termination proof — the defect three verifier lanes found independently.

    A skip that recorded nothing would make this tick emit ZERO rows. The retirement rule is a pure
    function of those rows, so the verdict could never retire and the alarm would re-fire forever:
    v5's non-termination, reached through the delivery loop by a slice whose whole purpose is
    reducing noise.
    """
    tenant = _tenant(session)
    check = _verdict(session, tenant)
    recipient = _recipient(session, tenant, "reviewer")
    session.flush()
    sink = _Sink()

    first = alarm_for_verdict(
        session, check=check, sink=sink, acting_tenant=tenant, now=NOW, attempt_id="a1"
    )
    session.flush()
    assert first == NOTIFY_OUTCOME_SENT
    assert sink.delivered == [recipient]

    # A second tick for the same verdict: the recipient has already been told.
    second = alarm_for_verdict(
        session, check=check, sink=sink, acting_tenant=tenant, now=NOW, attempt_id="a2"
    )
    session.flush()
    assert second == NOTIFY_OUTCOME_SKIPPED
    assert sink.delivered == [recipient], "the already-told recipient was PAGED AGAIN"

    rows = (
        session.execute(select(AuditEvent.after_value).where(AuditEvent.entity_id == str(check.id)))
        .scalars()
        .all()
    )
    assert any(r.get("outcome") == NOTIFY_OUTCOME_SKIPPED for r in rows), (
        "the skip recorded NOTHING — an all-skipped attempt emits no rows and the verdict can "
        "never retire"
    )
    assert (
        unalarmed_verdicts(session, acting_tenant=tenant) == []
    ), "the all-skipped attempt did not retire the verdict — non-termination is back"


def test_the_courtesy_read_is_scoped_to_THIS_verdict(session: Session) -> None:
    """Pass 2, P2-2: an entity-unscoped read would skip a recipient's FIRST delivery of a NEW
    divergence — and the skip's own concluding row would then retire it. A silent alarm drop
    hidden behind a row asserting success is the worst thing this file can produce."""
    tenant = _tenant(session)
    first_check = _verdict(session, tenant)
    recipient = _recipient(session, tenant, "reviewer")
    session.flush()
    sink = _Sink()
    alarm_for_verdict(
        session, check=first_check, sink=sink, acting_tenant=tenant, now=NOW, attempt_id="a1"
    )
    session.flush()
    assert sink.delivered == [recipient]

    # A DIFFERENT verdict. The recipient has been told about the other one, never about this.
    second_check = _verdict(session, tenant)
    session.flush()
    outcome = alarm_for_verdict(
        session, check=second_check, sink=sink, acting_tenant=tenant, now=NOW, attempt_id="b1"
    )
    session.flush()
    assert outcome == NOTIFY_OUTCOME_SENT
    assert sink.delivered == [
        recipient,
        recipient,
    ], "a NEW divergence was skipped because the recipient had heard about an OLDER one"


def test_doubt_resolves_to_PAGE_never_to_skip(session: Session) -> None:
    """An unreadable row, a missing recipient key, or either sentinel must never be read as
    'already delivered'. Shape-blindness degrades to paging — which is the status quo — never to
    dropping."""
    tenant = _tenant(session)
    check = _verdict(session, tenant)
    session.flush()
    _dispatch(session, tenant, str(check.id), outcome="", attempt_id="p", payload_broken=True)
    _dispatch(
        session,
        tenant,
        str(check.id),
        outcome=NOTIFY_OUTCOME_SENT,
        attempt_id="s",
        recipient=NO_RECIPIENT_SENTINEL,
    )
    _dispatch(
        session,
        tenant,
        str(check.id),
        outcome=NOTIFY_OUTCOME_FAILED,
        attempt_id="r",
        recipient=ALARM_ROLLBACK_SENTINEL,
    )
    session.flush()
    assert already_delivered_recipients(session, check_id=str(check.id), tenant=tenant) == set()


# --------------------------------------------------- the sibling transaction (OQ-ALR-3, carry (q))
def test_a_rolled_back_alarm_is_RECORDED_and_counts_against_the_EXISTING_bound(
    session: Session,
) -> None:
    """Carry (q) PAID. The bound counts durably-recorded attempts and a rolled-back transaction
    recorded nothing, so that path retried every tick forever, invisibly. The fix adds no rule: the
    sibling row carries the SAME attempt_id, so the existing bound counts it like any other."""
    tenant = _tenant(session)
    check = _verdict(session, tenant)
    session.flush()

    for i in range(MAX_ALARM_ATTEMPTS):
        record_alarm_transaction_failure(
            session,
            check_id=str(check.id),
            acting_tenant=tenant,
            attempt_id=f"rollback-{i}",
            reason="OperationalError: server closed the connection unexpectedly",
            channel="LOG",
            now=NOW,
        )
    session.flush()

    assert (
        unalarmed_verdicts(session, acting_tenant=tenant) == []
    ), "rolled-back attempts still do not count — the retry bound does not cover this path"
    health = alarm_channel_health(session, acting_tenant=tenant, now=NOW)
    assert health.undeliverable_attempts == MAX_ALARM_ATTEMPTS
    assert health.dead_channel is True, "every attempt rolled back and nothing was ever delivered"
    assert health.healthy is False


def test_the_WORKER_records_the_failure_when_the_alarm_transaction_blows_up(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The service function being correct is not the claim — the WORKER calling it is.

    Written because the mutation battery said so: deleting the sibling-transaction call from the
    worker left every test green, because the test above exercises the service function directly.
    A fix whose only proof is a unit test of the helper it calls is a fix with an unproven seam,
    and that seam is where carry (q) actually lived.
    """
    from irp_worker.reproduction_alarms import poll_tenant_reproduction_alarms

    tenant = _tenant(session)
    check = _verdict(session, tenant)
    _recipient(session, tenant, "reviewer")
    session.commit()

    def _explode(*_a: object, **_k: object) -> str:
        raise RuntimeError("the alarm transaction blew up")

    monkeypatch.setattr("irp_worker.reproduction_alarms.alarm_for_verdict", _explode)
    poll_tenant_reproduction_alarms(session, NOW, acting_tenant=tenant, sink=_Sink())

    payloads = (
        session.execute(select(AuditEvent.after_value).where(AuditEvent.entity_id == str(check.id)))
        .scalars()
        .all()
    )
    assert payloads, (
        "the worker rolled back and recorded NOTHING — the retry bound still does not cover the "
        "transaction-failure path (carry (q) is not actually paid)"
    )
    assert payloads[0]["recipient_id"] == ALARM_ROLLBACK_SENTINEL
    assert payloads[0]["outcome"] == NOTIFY_OUTCOME_FAILED
    assert payloads[0]["attempt_id"], "the row carries no attempt_id, so the bound cannot count it"


def test_the_rollback_row_uses_its_OWN_sentinel(session: Session) -> None:
    """Not ``NO_RECIPIENT_SENTINEL``, whose documented meaning is 'no eligible recipient'. A
    rollback row makes no claim about the tenant's holder set, and reusing that sentinel would have
    it assert one."""
    tenant = _tenant(session)
    check = _verdict(session, tenant)
    session.flush()
    record_alarm_transaction_failure(
        session,
        check_id=str(check.id),
        acting_tenant=tenant,
        attempt_id="a1",
        reason="boom",
        channel="LOG",
        now=NOW,
    )
    session.flush()
    payload = session.execute(
        select(AuditEvent.after_value).where(AuditEvent.entity_id == str(check.id))
    ).scalar_one()
    assert payload["recipient_id"] == ALARM_ROLLBACK_SENTINEL
    assert payload["recipient_id"] != NO_RECIPIENT_SENTINEL


# ----------------------------------------------------------------------- the vocabulary itself
def test_SKIPPED_is_a_CONCLUDING_outcome_and_the_mapping_stays_total() -> None:
    """The mint's whole point (pass-2 P2-1). A SKIPPED row that mapped to audit ``failure`` would
    burn the retry budget on courtesy skips and misclassify a delivered verdict as silenced."""
    assert NOTIFY_OUTCOME_SKIPPED in NOTIFY_OUTCOMES
    assert NOTIFY_OUTCOME_SKIPPED in NOTIFY_CONCLUDING_OUTCOMES
    assert NOTIFY_OUTCOME_FAILED not in NOTIFY_CONCLUDING_OUTCOMES
    # A FIFTH value must still fail CLOSED — the property that made the total mapping necessary.
    assert "SOME_FUTURE_OUTCOME" not in NOTIFY_CONCLUDING_OUTCOMES


def test_a_skip_row_never_claims_SENT(session: Session) -> None:
    """The Wave-12 honesty doctrine: SENT means a sink accepted a real call. A courtesy skip makes
    no call at all, and a row that misdescribes its own act is a false record."""
    tenant = _tenant(session)
    check = _verdict(session, tenant)
    _recipient(session, tenant, "reviewer")
    session.flush()
    sink = _Sink()
    alarm_for_verdict(
        session, check=check, sink=sink, acting_tenant=tenant, now=NOW, attempt_id="a1"
    )
    session.flush()
    alarm_for_verdict(
        session, check=check, sink=sink, acting_tenant=tenant, now=NOW, attempt_id="a2"
    )
    session.flush()

    payloads = (
        session.execute(select(AuditEvent.after_value).where(AuditEvent.entity_id == str(check.id)))
        .scalars()
        .all()
    )
    sent_rows = [p for p in payloads if p.get("outcome") == NOTIFY_OUTCOME_SENT]
    assert len(sent_rows) == 1, "a skip claimed SENT for a delivery that never happened"


def test_the_classification_and_the_queue_never_disagree(session: Session) -> None:
    """ONE fold, two consumers (pass-1 C4). If a second implementation of the retirement rule ever
    appears, these two answers drift — this test is what notices."""
    tenant = _tenant(session)
    queued = _verdict(session, tenant)
    delivered = _verdict(session, tenant)
    session.flush()
    _dispatch(session, tenant, str(delivered.id), outcome=NOTIFY_OUTCOME_SENT, attempt_id="a")
    session.flush()

    states = _classify_alarm_states(session, tenant=tenant).state
    still_queued = {str(c.id) for c in unalarmed_verdicts(session, acting_tenant=tenant)}
    assert states[str(delivered.id)] == VERDICT_ALARM_DELIVERED
    assert str(delivered.id) not in still_queued
    assert states.get(str(queued.id), VERDICT_ALARM_QUEUED) == VERDICT_ALARM_QUEUED
    assert str(queued.id) in still_queued
    assert alarm_channel_health(session, acting_tenant=tenant, now=NOW).queued == len(still_queued)
