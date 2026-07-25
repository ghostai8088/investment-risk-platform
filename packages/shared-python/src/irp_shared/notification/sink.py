"""NOTIF-1 delivery sink (Wave-12 slice 2).

The **record-first** boundary (OQ-1=A): the durable ``breach_notification`` row is the
system-of-record; the sink is the (v1: stubbed) act of getting the alert onto a wire. A
``NotificationSink`` is a pure egress boundary — it NEVER reads the DB, NEVER takes a lock, NEVER
sees another tenant. v1 ships ``LoggingNotificationSink`` (a structured log line). A real
EMAIL/WEBHOOK adapter is added later behind this same Protocol with NO schema change; its address
resolution + credentials arrive with user provisioning (``app_user`` has no contact column yet, and
BR-10 forbids secrets in source).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Protocol

_LOGGER = logging.getLogger("irp_shared.notification")


@dataclass(frozen=True)
class NotificationMessage:
    """The assembled alert handed to a sink (all fields already tenant-scoped + resolved)."""

    tenant_id: str
    recipient_id: str
    breach_id: str
    source_event_type: str
    severity: str


@dataclass(frozen=True)
class DeliveryResult:
    """A sink's outcome. ``ok`` True = accepted; False = a recorded FAILED attempt (durable
    evidence, terminal in v1 — no auto-retry until a v2 retry policy). ``detail`` = the reason."""

    ok: bool
    detail: str | None = None


class NotificationSink(Protocol):
    """The egress boundary. ``deliver`` MUST NOT raise for an ordinary delivery failure — it returns
    ``DeliveryResult(ok=False, detail=...)`` so the caller records a FAILED row; an unexpected
    exception is caught by the caller and recorded FAILED, never masked as 'notified'."""

    channel: str

    def deliver(self, message: NotificationMessage) -> DeliveryResult: ...


class LoggingNotificationSink:
    """v1 record-first sink: emit a structured log line (the DB row is the SoR, not the log)."""

    channel = "LOG"

    def deliver(self, message: NotificationMessage) -> DeliveryResult:
        _LOGGER.info(
            "breach-alert tenant=%s recipient=%s breach=%s event=%s severity=%s",
            message.tenant_id,
            message.recipient_id,
            message.breach_id,
            message.source_event_type,
            message.severity,
        )
        return DeliveryResult(ok=True)
