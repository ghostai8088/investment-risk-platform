"""NOTIF-1 notification service — the phase-4 consumer + the read (Wave-12 slice 2).

Consumes the tenant's ``BREACH.DETECT``/``BREACH.ESCALATE`` audit stream since a DERIVED high-water
(``MAX(source_sequence_no)`` over ``breach_notification`` — OQ-4=B, no separate cursor table),
resolves the in-tenant ``breach.review`` holders (OQ-3=A), and appends a durable attempt row per
(event, recipient) + a ``NOTIFY.DISPATCH`` audit emit (OQ-5=A, hash-chained proof-of-alert).

**The atomicity invariant (the verifier's fail-open fold + OQ-4=B):** each alarm event is processed
ATOMICALLY — ``notify_for_event`` appends a durable terminal row (SENT/FAILED/SUPPRESSED) for EVERY
resolved recipient within the caller's single transaction; a sink exception is CAUGHT and recorded
FAILED (never left rowless, never head-of-line-blocks). So the worker's per-event commit either
lands ALL of an event's rows (the derived ``MAX`` advances past a FULLY-covered event) or, on a DB
failure, rolls back ALL of them (``MAX`` unchanged → the event is reprocessed next tick). This is
why a per-RECIPIENT commit would be wrong here: it could advance ``MAX`` past an event on its first
recipient and skip a later failed one — the silent no-notify. **The worker's other half of the
guarantee (``poll_tenant_notifications``): STOP the batch on the first non-dedup failure** — because
a DERIVED ``MAX`` cannot represent a gap, processing a LATER (higher-seq) event after an EARLIER one
failed would let the later commit leapfrog ``MAX`` past the failed event, orphaning it forever
(4-finder HIGH). Fail-CLOSED: the failed event and its tail retry next tick.

Delivery ordering (4-finder MED): ``notify_for_event`` calls the sink for ALL recipients FIRST, then
records + emits — so NO sink runs while the per-tenant audit advisory lock is held (the v1 LOG sink
has no I/O; this keeps a drop-in v2 network sink from holding the audit-chain lock across I/O, the
API-2b P1 anti-pattern). A real v2 channel still moves delivery fully outside the audit txn.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from irp_shared.audit.actions import ACTION_RECORD
from irp_shared.audit.models import AuditEvent
from irp_shared.audit.queries import list_events_since_sequence
from irp_shared.audit.service import record_event
from irp_shared.entitlement.service import holders_of_permission
from irp_shared.limit.events import BREACH_DETECT_EVENT
from irp_shared.notification.events import (
    ENTITY_BREACH_NOTIFICATION,
    NO_RECIPIENT_SENTINEL,
    NOTIFY_ALARM_EVENT_TYPES,
    NOTIFY_DISPATCH_EVENT,
    NOTIFY_OUTCOME_FAILED,
    NOTIFY_OUTCOME_SENT,
    NOTIFY_OUTCOME_SUPPRESSED,
    NOTIFY_RECIPIENT_PERMISSION,
    SOURCE_MODULE_NOTIFICATION,
)
from irp_shared.notification.models import BreachNotification
from irp_shared.notification.sink import (
    LoggingNotificationSink,
    NotificationMessage,
    NotificationSink,
    WebhookNotificationSink,
)


def _current_high_water(session: Session, acting_tenant: str) -> int:
    """The per-tenant derived cursor = ``MAX(source_sequence_no)`` over already-recorded rows, or 0
    (OQ-4=B). Because events are processed atomically, this MAX is always a FULLY-covered event's
    sequence_no — never a partially-notified one (the atomicity invariant)."""
    return (
        session.execute(
            select(func.max(BreachNotification.source_sequence_no)).where(
                BreachNotification.tenant_id == str(acting_tenant)
            )
        ).scalar_one_or_none()
        or 0
    )


def pending_alarm_events(
    session: Session, *, acting_tenant: str, limit: int | None = None
) -> list[AuditEvent]:
    """The tenant's unnotified alarm events (``BREACH.DETECT``/``BREACH.ESCALATE`` with
    ``sequence_no > high_water``), oldest-first — the phase-4 work list."""
    return list_events_since_sequence(
        session,
        acting_tenant=acting_tenant,
        after_sequence_no=_current_high_water(session, acting_tenant),
        event_types=NOTIFY_ALARM_EVENT_TYPES,
        limit=limit,
    )


def _breach_id_for_event(event: AuditEvent) -> str:
    """The subject breach id, extracted PER event_type (the verifier trap): ``BREACH.DETECT`` sets
    ``entity_id = breach.id``; ``BREACH.ESCALATE`` sets ``entity_id = breach_action.id`` and carries
    the breach id in ``after_value["breach_id"]``. A naive 'entity_id is the breach' would write a
    ``breach_action.id`` into the FK and fail the insert."""
    if event.event_type == BREACH_DETECT_EVENT:
        return str(event.entity_id)
    after = event.after_value or {}
    return str(after["breach_id"])


def _record_notification(
    session: Session,
    *,
    event: AuditEvent,
    breach_id: str,
    recipient_id: str,
    recipient_reason: str,
    channel: str,
    outcome: str,
    failure_reason: str | None,
    now: datetime,
) -> BreachNotification:
    """Append ONE ``breach_notification`` attempt row + emit its ``NOTIFY.DISPATCH`` audit event
    (OQ-5=A — hash-chained proof-of-alert, caller-side to the FROZEN ``record_event``)."""
    row = BreachNotification(
        tenant_id=event.tenant_id,
        source_sequence_no=event.sequence_no,
        source_event_type=event.event_type,
        breach_id=breach_id,
        recipient_id=recipient_id,
        recipient_reason=recipient_reason,
        channel=channel,
        outcome=outcome,
        failure_reason=failure_reason[:2000] if failure_reason else None,
        severity=event.severity,
        notified_at=now,
    )
    session.add(row)
    session.flush()
    record_event(
        session,
        event_type=NOTIFY_DISPATCH_EVENT,
        tenant_id=event.tenant_id,
        actor_type="SYSTEM",
        actor_id=f"notify:{event.tenant_id}",
        source_module=SOURCE_MODULE_NOTIFICATION,
        entity_type=ENTITY_BREACH_NOTIFICATION,
        entity_id=row.id,
        action=ACTION_RECORD,
        # the alarm's severity rides through (a HARD DETECT / any ESCALATE is a warning).
        severity=event.severity,
        after_value={
            "breach_id": str(breach_id),
            "recipient_id": recipient_id,
            "recipient_reason": recipient_reason,
            "source_sequence_no": event.sequence_no,
            "source_event_type": event.event_type,
            "channel": channel,
            "outcome": outcome,
        },
        data_classification="DC-2",
    )
    return row


def notify_for_event(
    session: Session,
    event: AuditEvent,
    now: datetime,
    *,
    sink: NotificationSink,
) -> list[BreachNotification]:
    """Process ONE alarm event ATOMICALLY within the caller's transaction: resolve the in-tenant
    ``breach.review`` holders (OQ-3=A) and append a durable terminal row for EVERY recipient (a sink
    exception is caught → ``FAILED``, never left rowless). A no-recipient event writes ONE
    ``SUPPRESSED`` sentinel row (positive 'checked, nobody to notify' evidence; keeps the derived
    cursor and the read uniform). The caller (worker phase 4) commits this as one unit."""
    breach_id = _breach_id_for_event(event)
    recipients = holders_of_permission(
        session,
        permission_code=NOTIFY_RECIPIENT_PERMISSION,
        acting_tenant=event.tenant_id,
        at=now,
    )
    if not recipients:
        return [
            _record_notification(
                session,
                event=event,
                breach_id=breach_id,
                recipient_id=NO_RECIPIENT_SENTINEL,
                recipient_reason=NOTIFY_RECIPIENT_PERMISSION,
                # DEP-1: the SINK's channel, not a LOG literal — the delivered rows already recorded
                # sink.channel, and a SUPPRESSED row claiming LOG under a webhook sink would be a
                # false record in a durable evidence table.
                channel=sink.channel,
                outcome=NOTIFY_OUTCOME_SUPPRESSED,
                failure_reason=None,
                now=now,
            )
        ]
    # PHASE A — deliver to EVERY recipient BEFORE recording anything (4-finder MED: the FIRST
    # ``_record_notification`` takes the per-tenant audit ADVISORY lock, held to commit; calling a
    # sink for later recipients under that lock would hold it across the sink's work — harmless for
    # the v1 LOG sink but a foot-gun for a drop-in v2 network sink, exactly the API-2b P1
    # lock-hold-across-I/O anti-pattern. So NO sink runs while the advisory is held.
    outcomes: list[tuple[str, str, str | None]] = []
    for recipient_id in recipients:
        message = NotificationMessage(
            tenant_id=event.tenant_id,
            recipient_id=recipient_id,
            breach_id=breach_id,
            source_event_type=event.event_type,
            severity=event.severity,
        )
        try:
            result = sink.deliver(message)
            outcome = NOTIFY_OUTCOME_SENT if result.ok else NOTIFY_OUTCOME_FAILED
            failure = None if result.ok else (result.detail or "delivery failed")
        except Exception as exc:  # noqa: BLE001 - a sink must never rowless-drop a recipient
            outcome = NOTIFY_OUTCOME_FAILED
            failure = f"{type(exc).__name__}: {exc}"
        outcomes.append((recipient_id, outcome, failure))
    # PHASE B — record the durable rows + NOTIFY.DISPATCH emits (the advisory lock is taken HERE,
    # after all delivery; every recipient has a terminal outcome, so none is left rowless).
    return [
        _record_notification(
            session,
            event=event,
            breach_id=breach_id,
            recipient_id=recipient_id,
            recipient_reason=NOTIFY_RECIPIENT_PERMISSION,
            channel=sink.channel,
            outcome=outcome,
            failure_reason=failure,
            now=now,
        )
        for recipient_id, outcome, failure in outcomes
    ]


def default_sink() -> NotificationSink:
    """The configured sink: WEBHOOK when ``IRP_NOTIFY_WEBHOOK_URL`` is set, else the v1 LOG sink.

    DEP-1 (Wave-15): the promised "real EMAIL/WEBHOOK adapter behind the same Protocol" —
    config-driven exactly as the sink module predicted, no schema change. The URL comes from the
    ENVIRONMENT (BR-10: a webhook URL routinely embeds a secret token, so it never lands in
    source); unset or empty means the LOG sink, so every existing environment is unchanged.
    """
    import os

    url = os.environ.get("IRP_NOTIFY_WEBHOOK_URL", "").strip()
    if url:
        return WebhookNotificationSink(url)
    return LoggingNotificationSink()


def list_breach_notifications(
    session: Session,
    *,
    acting_tenant: str,
    breach_id: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[BreachNotification]:
    """The tenant's notification attempts, newest-first (``breach.view``-gated read). Explicit
    ``tenant_id`` predicate atop RLS; optional ``breach_id`` filter; paginated (the endpoint bounds
    limit/offset). Silent-empty on no match."""
    stmt = select(BreachNotification).where(BreachNotification.tenant_id == str(acting_tenant))
    if breach_id is not None:
        stmt = stmt.where(BreachNotification.breach_id == str(breach_id))
    stmt = (
        stmt.order_by(BreachNotification.notified_at.desc(), BreachNotification.id)
        .limit(limit)
        .offset(offset)
    )
    return list(session.execute(stmt).scalars().all())
