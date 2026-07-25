"""NOTIF-1 worker breach-notification phase — the FOURTH phase of the per-tenant operational tick.

Runs after ``poll_tenant_breach_deadlines`` inside the SAME tenant-scoped non-BYPASSRLS session (the
alarm leg rides the SCH-1 cadence — a PHASE of the single per-tenant tick, not a new entrypoint).
Turns each unnotified ``BREACH.DETECT``/``BREACH.ESCALATE`` audit event into durable
``breach_notification`` attempt rows (Fable demand #3: assembled per-tenant INSIDE the tick, IA
attempt evidence, never a cross-tenant sweep).

**Commit topology (the API-2b P1 discipline):** each ALARM EVENT is processed in its OWN TOP-LEVEL
transaction (``notify_for_event`` is atomic — every recipient gets a durable terminal row, sink
exceptions caught → FAILED). This keeps the derived high-water (``MAX(source_sequence_no)``) always
at a FULLY-covered event: a DB failure rolls back the whole event → ``MAX`` unchanged → the event is
reprocessed next tick; a benign ``IntegrityError`` on the ``(tenant, seq, recipient)`` unique key
means a prior tick already recorded it (crash-retry dedup). Deadlock ordering: each
``breach_notification`` INSERT takes a ``FOR KEY SHARE`` lock on its ``breach`` FK row, THEN the
audit advisory (``record_event``) — the SAME row-lock-before-advisory order as the HTTP breach
verbs (``FOR UPDATE`` then advisory), so no cross-holding cycle can close (deadlock-safe by uniform
ordering, NOT by lock absence — a future reorder emitting before the insert would reintroduce it).
The caller MUST hold a ``persistent_tenant_context`` re-arm — the RLS GUC is transaction-local, and
an un-re-armed post-commit transaction would read ZERO audit rows and notify NOTHING (fail-open).
"""

from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from irp_shared.notification.service import default_sink, notify_for_event, pending_alarm_events
from irp_shared.notification.sink import NotificationSink

_LOGGER = logging.getLogger("irp_worker.notifications")

#: The unique constraint that backstops the per-(event, recipient) idempotency. ONLY a violation of
#: THIS is the benign already-notified crash-retry dedup.
_NOTIFY_DEDUP_CONSTRAINT = "uq_breach_notification_event_recipient"


def _is_notify_dedup(exc: IntegrityError) -> bool:
    """True only when ``exc`` is the ``(tenant, seq, recipient)`` notification dedup, NOT some other
    constraint violation (psycopg ``diag.constraint_name`` + message fallback)."""
    orig = getattr(exc, "orig", None)
    diag = getattr(orig, "diag", None)
    if getattr(diag, "constraint_name", None) == _NOTIFY_DEDUP_CONSTRAINT:
        return True
    return _NOTIFY_DEDUP_CONSTRAINT in str(exc)


def poll_tenant_notifications(
    session: Session,
    now: datetime,
    *,
    acting_tenant: str,
    sink: NotificationSink | None = None,
) -> list[str]:
    """Notify every unnotified alarm event for the current tenant; return the notified event ids.

    Each event is its own TOP-LEVEL transaction. ONLY a ``uq_breach_notification_event_recipient``
    violation is the benign crash-retry dedup; any OTHER failure is LOGGED and the event is NOT
    advanced (the derived high-water excludes it), so it is reprocessed next tick — never masked as
    'notified'.
    """
    channel = sink or default_sink()
    notified: list[str] = []
    # Snapshot the (id, instance) pairs: the plain ``event_id`` string survives each commit's expiry
    # (used at ``notified.append``); the ``event`` object still refreshes on attribute access after
    # a commit, but under the re-armed GUC over immutable audit rows that is correct + stale-free.
    events = [
        (event.id, event) for event in pending_alarm_events(session, acting_tenant=acting_tenant)
    ]
    for event_id, event in events:
        try:
            notify_for_event(session, event, now, sink=channel)
            session.commit()  # per-event TOP-LEVEL commit (atomic; row→advisory order safe)
            notified.append(event_id)
        except IntegrityError as exc:
            session.rollback()
            if _is_notify_dedup(exc):
                # A prior tick already recorded this event's notifications — benign dedup; the
                # derived high-water is already >= this event, so skipping it cannot open a gap.
                continue
            # A REAL non-dedup failure: the derived high-water is MAX(source_sequence_no), which
            # cannot represent a GAP — if we processed a LATER (higher-seq) event now, its commit
            # would advance MAX past THIS failed event and it would never be rescanned (a silent
            # permanent no-notify, the exact fail-open this slice exists to close). So we STOP the
            # batch here (fail-CLOSED head-of-line): the high-water stays below this event and the
            # whole tail is retried next tick. (A permanently-poison head event stalls the tenant's
            # queue with loud logs — a v2 dead-letter/skip-after-N is the refinement.)
            _LOGGER.error(
                "notification hit a non-dedup IntegrityError for audit event %s; stopping the "
                "batch to avoid a cursor gap: %s",
                event_id,
                exc,
            )
            break
        except Exception as exc:  # noqa: BLE001 - fail-CLOSED per-event isolation
            session.rollback()
            _LOGGER.error(
                "notification failed for audit event %s; stopping the batch to avoid a cursor "
                "gap: %s",
                event_id,
                exc,
            )
            break
    return notified
