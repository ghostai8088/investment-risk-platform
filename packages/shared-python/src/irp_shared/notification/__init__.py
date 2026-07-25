"""Breach notification / alerting (NOTIF-1, Wave-12 slice 2).

A decoupled audit-stream consumer that turns ``BREACH.DETECT``/``BREACH.ESCALATE`` audit events
into durable, auditable ``breach_notification`` attempt rows — the SR 11-7 / BCBS 239 "prove the
CRO was alerted" leg. Runs as PHASE 4 of the per-tenant operational tick (per-EVENT top-level
transactions; the API-2b P1 deadlock discipline). NOT a governed number.
"""

from __future__ import annotations

from irp_shared.notification.events import (
    NO_RECIPIENT_SENTINEL,
    NOTIFY_ALARM_EVENT_TYPES,
    NOTIFY_CHANNEL_LOG,
    NOTIFY_DISPATCH_EVENT,
    NOTIFY_OUTCOME_FAILED,
    NOTIFY_OUTCOME_SENT,
    NOTIFY_OUTCOME_SUPPRESSED,
)
from irp_shared.notification.models import BreachNotification
from irp_shared.notification.service import (
    default_sink,
    list_breach_notifications,
    notify_for_event,
    pending_alarm_events,
)
from irp_shared.notification.sink import (
    DeliveryResult,
    LoggingNotificationSink,
    NotificationMessage,
    NotificationSink,
)

__all__ = [
    "NOTIFY_ALARM_EVENT_TYPES",
    "NOTIFY_CHANNEL_LOG",
    "NOTIFY_DISPATCH_EVENT",
    "NOTIFY_OUTCOME_FAILED",
    "NOTIFY_OUTCOME_SENT",
    "NOTIFY_OUTCOME_SUPPRESSED",
    "NO_RECIPIENT_SENTINEL",
    "BreachNotification",
    "DeliveryResult",
    "LoggingNotificationSink",
    "NotificationMessage",
    "NotificationSink",
    "default_sink",
    "list_breach_notifications",
    "notify_for_event",
    "pending_alarm_events",
]
