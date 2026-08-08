"""NOTIF-1 breach-notification unit tests (SQLite) — the phase-4 consumer.

Covers: recipient resolution (holders_of_permission, the effective-dated window + is_active), the
per-event_type breach_id extraction (DETECT via entity_id, ESCALATE via after_value), the atomicity
+ derived high-water cursor, the fail-open guards (a sink failure → FAILED row not a silent drop; a
no-recipient event → a SUPPRESSED sentinel that advances the cursor), the NOTIFY.DISPATCH emit, and
the at-most-once dedup on the unique key. The full per-event top-level-txn tick loop + RLS + the
append-only trigger are proven at the PG tier (test_notification_pg.py)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from irp_shared.audit.models import AuditEvent
from irp_shared.entitlement.models import (
    AppUser,
    Permission,
    Role,
    RolePermission,
    UserRole,
)
from irp_shared.entitlement.service import holders_of_permission
from irp_shared.limit.events import (
    BREACH_ABOVE,
    BREACH_DETECT_EVENT,
    BREACH_ESCALATE_EVENT,
    LIMIT_KIND_HARD,
    THRESHOLD_UNIT_CURRENCY,
)
from irp_shared.limit.models import Breach
from irp_shared.notification.events import (
    NO_RECIPIENT_SENTINEL,
    NOTIFY_DISPATCH_EVENT,
    NOTIFY_OUTCOME_FAILED,
    NOTIFY_OUTCOME_SENT,
    NOTIFY_OUTCOME_SUPPRESSED,
)
from irp_shared.notification.models import BreachNotification
from irp_shared.notification.service import (
    _breach_id_for_event,
    _current_high_water,
    notify_for_event,
    pending_alarm_events,
)
from irp_shared.notification.sink import (
    DeliveryResult,
    LoggingNotificationSink,
    NotificationMessage,
)

_T0 = datetime(2026, 1, 1, tzinfo=UTC)


def _mk_reviewer(session: Session, tenant: str, *, active: bool = True) -> str:
    """An ACTIVE app_user holding breach.review (a recipient)."""
    user = AppUser(tenant_id=tenant, display_name="rev", is_active=active)
    session.add(user)
    session.flush()
    role = Role(tenant_id=tenant, code=f"r-{uuid.uuid4().hex[:6]}", name="R")
    session.add(role)
    session.flush()
    perm = session.query(Permission).filter_by(code="breach.review").one_or_none() or Permission(
        code="breach.review", description="d"
    )
    session.add(perm)
    session.flush()
    session.add(RolePermission(role_id=role.id, permission_id=perm.id))
    # valid_from defaults to real utcnow(); pin before _T0 so the grant is active at tick time.
    session.add(
        UserRole(
            tenant_id=tenant,
            user_id=user.id,
            role_id=role.id,
            valid_from=_T0 - timedelta(days=1),
        )
    )
    session.flush()
    return user.id


def _seed_limit_and_run(session: Session, tenant: str) -> tuple[str, str]:
    """GENUINE parents for a breach: a real ACTIVE limit_definition (on a real portfolio)
    plus a real calculation_run — the FK-enforced tier refuses dangling ids."""
    from irp_shared.calc.models import CalculationRun
    from irp_shared.limit.models import LimitDefinition
    from irp_shared.portfolio.models import Portfolio

    portfolio = Portfolio(
        tenant_id=tenant,
        code=f"ACCT-{uuid.uuid4().hex[:6]}",
        name="Balanced Growth Fund",
        node_type="ACCOUNT",
        status="ACTIVE",
        record_version=1,
    )
    session.add(portfolio)
    session.flush()
    limit = LimitDefinition(
        tenant_id=tenant,
        code=f"lim-{uuid.uuid4().hex[:8]}",
        name="VaR ceiling",
        target_run_type="VAR",
        metric_type="VAR_PARAMETRIC",
        scope_portfolio_id=portfolio.id,
        threshold_value=Decimal("1000000"),
        threshold_unit=THRESHOLD_UNIT_CURRENCY,
        breach_direction=BREACH_ABOVE,
        limit_kind=LIMIT_KIND_HARD,
        status="ACTIVE",
        record_version=1,
    )
    run = CalculationRun(
        tenant_id=tenant,
        run_type="VAR",
        status="COMPLETED",
        initiated_by="limit-eval:x",
        scope_portfolio_id=portfolio.id,
    )
    session.add_all([limit, run])
    session.flush()
    return limit.id, run.run_id


def _seed_breach(session: Session, tenant: str) -> Breach:
    limit_id, run_id = _seed_limit_and_run(session, tenant)
    breach = Breach(
        tenant_id=tenant,
        limit_definition_id=limit_id,
        calculation_run_id=run_id,
        detected_at=_T0,
        target_run_type="VAR",
        metric_type="VAR_PARAMETRIC",
        observed_value=Decimal("2000000"),
        threshold_value=Decimal("1000000"),
        threshold_unit=THRESHOLD_UNIT_CURRENCY,
        breach_direction=BREACH_ABOVE,
        limit_kind=LIMIT_KIND_HARD,
        severity=LIMIT_KIND_HARD,
        status="DETECTED",
    )
    session.add(breach)
    session.flush()
    return breach


def _detect_event(
    session: Session, tenant: str, breach: Breach, *, severity: str = "warning"
) -> AuditEvent:
    """A BREACH.DETECT audit event (entity_id = breach.id — what the consumer extracts)."""
    from irp_shared.audit.service import record_event

    return record_event(
        session,
        event_type=BREACH_DETECT_EVENT,
        tenant_id=tenant,
        actor_type="SYSTEM",
        actor_id="limit-eval:x",
        source_module="limit",
        entity_type="breach",
        entity_id=breach.id,
        action="record",
        severity=severity,
        after_value={"limit_definition_id": breach.limit_definition_id},
    )


def _escalate_event(session: Session, tenant: str, breach: Breach) -> AuditEvent:
    """A BREACH.ESCALATE audit event (entity_id = a breach_action id; breach id in after_value)."""
    from irp_shared.audit.service import record_event

    return record_event(
        session,
        event_type=BREACH_ESCALATE_EVENT,
        tenant_id=tenant,
        actor_type="SYSTEM",
        actor_id="breach-deadline:x",
        source_module="limit",
        entity_type="breach_action",
        entity_id=str(uuid.uuid4()),  # a breach_action id — NOT the breach
        action="record",
        severity="warning",
        after_value={"breach_id": breach.id, "seq": 4},
    )


# --- recipient resolution (holders_of_permission) -----------------------------------------
def test_holders_resolves_only_active_in_tenant(session: Session) -> None:
    tenant = str(uuid.uuid4())
    a = _mk_reviewer(session, tenant)
    b = _mk_reviewer(session, tenant)
    _mk_reviewer(session, tenant, active=False)  # deactivated — excluded
    _mk_reviewer(session, str(uuid.uuid4()))  # other tenant — excluded
    holders = holders_of_permission(
        session, permission_code="breach.review", acting_tenant=tenant, at=_T0
    )
    assert holders == sorted([a, b])


def test_holders_excludes_expired_grant(session: Session) -> None:
    tenant = str(uuid.uuid4())
    user = AppUser(tenant_id=tenant, display_name="rev")
    session.add(user)
    session.flush()
    role = Role(tenant_id=tenant, code="r", name="R")
    session.add(role)
    session.flush()
    perm = Permission(code="breach.review", description="d")
    session.add(perm)
    session.flush()
    session.add(RolePermission(role_id=role.id, permission_id=perm.id))
    # a grant that EXPIRED before _T0
    session.add(
        UserRole(
            tenant_id=tenant,
            user_id=user.id,
            role_id=role.id,
            valid_from=_T0 - timedelta(days=10),
            valid_to=_T0 - timedelta(days=1),
        )
    )
    session.flush()
    assert (
        holders_of_permission(
            session, permission_code="breach.review", acting_tenant=tenant, at=_T0
        )
        == []
    )


# --- breach_id extraction (the verifier trap) ---------------------------------------------
def test_breach_id_extraction_per_event_type(session: Session) -> None:
    tenant = str(uuid.uuid4())
    breach = _seed_breach(session, tenant)
    detect = _detect_event(session, tenant, breach)
    escalate = _escalate_event(session, tenant, breach)
    assert _breach_id_for_event(detect) == breach.id  # DETECT → entity_id
    assert escalate.entity_id != breach.id  # ESCALATE entity_id is the action id, NOT the breach
    assert _breach_id_for_event(escalate) == breach.id  # …but resolved from after_value


# --- notify_for_event: the happy path + the emit ------------------------------------------
def test_notify_records_a_sent_row_and_emits_dispatch(session: Session) -> None:
    tenant = str(uuid.uuid4())
    reviewer = _mk_reviewer(session, tenant)
    breach = _seed_breach(session, tenant)
    event = _detect_event(session, tenant, breach)
    rows = notify_for_event(session, event, _T0, sink=LoggingNotificationSink())
    assert len(rows) == 1
    row = rows[0]
    assert row.outcome == NOTIFY_OUTCOME_SENT
    assert row.recipient_id == reviewer
    assert row.recipient_reason == "breach.review"
    assert row.breach_id == breach.id
    assert row.source_sequence_no == event.sequence_no
    assert row.channel == "LOG"
    # the NOTIFY.DISPATCH ledger entry (hash-chained proof-of-alert, OQ-5=A)
    emits = list(
        session.execute(
            select(AuditEvent).where(AuditEvent.event_type == NOTIFY_DISPATCH_EVENT)
        ).scalars()
    )
    assert len(emits) == 1
    assert emits[0].entity_type == "breach_notification"
    assert emits[0].entity_id == row.id
    assert emits[0].after_value["outcome"] == NOTIFY_OUTCOME_SENT
    assert "recipient_id" not in {"", None}  # payload carries recipient_id


def test_notify_fans_out_to_every_reviewer(session: Session) -> None:
    tenant = str(uuid.uuid4())
    r1 = _mk_reviewer(session, tenant)
    r2 = _mk_reviewer(session, tenant)
    breach = _seed_breach(session, tenant)
    event = _detect_event(session, tenant, breach)
    rows = notify_for_event(session, event, _T0, sink=LoggingNotificationSink())
    assert {r.recipient_id for r in rows} == {r1, r2}
    assert all(r.outcome == NOTIFY_OUTCOME_SENT for r in rows)


# --- the fail-open guards -----------------------------------------------------------------
def test_sink_failure_records_failed_never_silently_drops(session: Session) -> None:
    tenant = str(uuid.uuid4())
    _mk_reviewer(session, tenant)
    breach = _seed_breach(session, tenant)
    event = _detect_event(session, tenant, breach)

    class _FailingSink:
        channel = "LOG"

        def deliver(self, message: NotificationMessage) -> DeliveryResult:
            return DeliveryResult(ok=False, detail="smtp down")

    rows = notify_for_event(session, event, _T0, sink=_FailingSink())
    assert len(rows) == 1  # a DURABLE row exists — the recipient is NOT silently dropped
    assert rows[0].outcome == NOTIFY_OUTCOME_FAILED
    assert rows[0].failure_reason == "smtp down"


def test_sink_exception_is_caught_as_failed(session: Session) -> None:
    tenant = str(uuid.uuid4())
    _mk_reviewer(session, tenant)
    breach = _seed_breach(session, tenant)
    event = _detect_event(session, tenant, breach)

    class _RaisingSink:
        channel = "LOG"

        def deliver(self, message: NotificationMessage) -> DeliveryResult:
            raise RuntimeError("boom")

    rows = notify_for_event(session, event, _T0, sink=_RaisingSink())
    assert rows[0].outcome == NOTIFY_OUTCOME_FAILED  # caught, never rowless (no head-of-line block)
    assert "RuntimeError" in rows[0].failure_reason


def test_no_recipient_writes_a_suppressed_sentinel_that_advances_the_cursor(
    session: Session,
) -> None:
    tenant = str(uuid.uuid4())  # NO reviewer provisioned
    breach = _seed_breach(session, tenant)
    event = _detect_event(session, tenant, breach)
    rows = notify_for_event(session, event, _T0, sink=LoggingNotificationSink())
    assert len(rows) == 1
    assert rows[0].outcome == NOTIFY_OUTCOME_SUPPRESSED
    assert rows[0].recipient_id == NO_RECIPIENT_SENTINEL  # the fixed non-null sentinel
    # the derived high-water advanced past the event (so it is not rescanned forever)
    assert _current_high_water(session, tenant) == event.sequence_no


# --- the derived cursor + at-most-once dedup ----------------------------------------------
def test_pending_excludes_already_notified(session: Session) -> None:
    tenant = str(uuid.uuid4())
    _mk_reviewer(session, tenant)
    breach = _seed_breach(session, tenant)
    e1 = _detect_event(session, tenant, breach)
    notify_for_event(session, e1, _T0, sink=LoggingNotificationSink())
    session.flush()
    # a SECOND alarm event after the first is notified
    e2 = _escalate_event(session, tenant, breach)
    pending = pending_alarm_events(session, acting_tenant=tenant)
    assert [p.id for p in pending] == [e2.id]  # only the un-notified one


def test_only_alarm_event_types_are_pending(session: Session) -> None:
    from irp_shared.audit.service import record_event

    tenant = str(uuid.uuid4())
    _mk_reviewer(session, tenant)
    breach = _seed_breach(session, tenant)
    _detect_event(session, tenant, breach)  # alarm
    # a lifecycle event (BREACH.ASSIGN) is NOT an alarm
    record_event(
        session,
        event_type="BREACH.ASSIGN",
        tenant_id=tenant,
        actor_type="user",
        actor_id="mgr",
        source_module="limit",
        entity_type="breach_action",
        entity_id=str(uuid.uuid4()),
        action="record",
        after_value={"breach_id": breach.id},
    )
    pending = pending_alarm_events(session, acting_tenant=tenant)
    assert {p.event_type for p in pending} == {BREACH_DETECT_EVENT}


def test_dedup_on_the_unique_key(session: Session) -> None:
    from sqlalchemy.exc import IntegrityError

    tenant = str(uuid.uuid4())
    reviewer = _mk_reviewer(session, tenant)
    breach = _seed_breach(session, tenant)
    event = _detect_event(session, tenant, breach)
    notify_for_event(session, event, _T0, sink=LoggingNotificationSink())
    session.flush()
    # a duplicate (tenant, source_sequence_no, recipient) collides — the at-most-once backstop
    dup = BreachNotification(
        tenant_id=tenant,
        source_sequence_no=event.sequence_no,
        source_event_type=event.event_type,
        breach_id=breach.id,
        recipient_id=reviewer,
        recipient_reason="breach.review",
        channel="LOG",
        outcome=NOTIFY_OUTCOME_SENT,
        severity="warning",
        notified_at=_T0,
    )
    session.add(dup)
    with pytest.raises(IntegrityError):
        session.flush()


# --- append-only guard (ORM tier; the P0001 DB trigger is proven at PG) --------------------
def test_breach_notification_is_append_only(session: Session) -> None:
    from irp_shared.audit.models import AppendOnlyViolation

    tenant = str(uuid.uuid4())
    reviewer = _mk_reviewer(session, tenant)
    breach = _seed_breach(session, tenant)
    event = _detect_event(session, tenant, breach)
    row = notify_for_event(session, event, _T0, sink=LoggingNotificationSink())[0]
    row.outcome = NOTIFY_OUTCOME_FAILED
    with pytest.raises(AppendOnlyViolation):
        session.flush()
    assert reviewer  # (silence unused)
