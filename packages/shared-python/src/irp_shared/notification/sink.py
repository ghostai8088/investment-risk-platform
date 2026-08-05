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


class WebhookNotificationSink:
    """DEP-1 (Wave-15): the first REAL delivery channel — an HTTP POST behind the same Protocol.

    Design constraints, each inherited from a recorded decision rather than invented here:

    - **Never raises from ``deliver``** (the Protocol contract): every network/HTTP failure returns
      ``DeliveryResult(ok=False, detail=...)`` so the caller records a durable FAILED row. A
      construction-time misconfiguration (empty URL, non-HTTP scheme) DOES raise — that is a config
      error owed to the operator at startup, not a delivery outcome owed a row.
    - **The URL never appears in ``detail``.** Webhook URLs routinely EMBED a secret token in the
      path (the Slack pattern), and ``detail`` lands in the durable ``failure_reason`` column —
      BR-10 forbids secrets at rest, so every detail string is redacted against the configured URL
      before it is returned.
    - **Short timeout (default 5s), stdlib ``urllib`` only.** ``irp_shared`` declares exactly one
      runtime dependency and a notification channel is not the reason to grow that; and although
      NOTIF-1's phase-A/phase-B split means no sink runs under the audit advisory lock, delivery
      still runs inside the caller's transaction, so an unbounded hang would hold a transaction
      open — the API-2b lock-across-I/O anti-pattern one layer down.
    """

    channel = "WEBHOOK"

    def __init__(self, url: str, *, timeout_seconds: float = 5.0) -> None:
        if not url:
            raise ValueError("WebhookNotificationSink requires a non-empty URL")
        if not url.startswith(("http://", "https://")):
            raise ValueError(
                "WebhookNotificationSink requires an http(s) URL — refusing a scheme that could "
                "reach the filesystem or an arbitrary handler"
            )
        self._url = url
        self._timeout = timeout_seconds

    def _redact(self, text: str) -> str:
        return text.replace(self._url, "<webhook-url>")

    def deliver(self, message: NotificationMessage) -> DeliveryResult:
        import json
        import urllib.error
        import urllib.request

        payload = json.dumps(
            {
                "type": "breach-alert",
                "tenant_id": message.tenant_id,
                "recipient_id": message.recipient_id,
                "breach_id": message.breach_id,
                "source_event_type": message.source_event_type,
                "severity": message.severity,
            }
        ).encode("utf-8")
        request = urllib.request.Request(
            self._url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self._timeout) as response:
                status = response.status
                if 200 <= status < 300:
                    return DeliveryResult(ok=True)
                return DeliveryResult(ok=False, detail=f"webhook returned HTTP {status}")
        except urllib.error.HTTPError as exc:
            return DeliveryResult(ok=False, detail=f"webhook returned HTTP {exc.code}")
        except Exception as exc:  # noqa: BLE001 - the Protocol forbids raising for delivery failures
            return DeliveryResult(
                ok=False,
                detail=self._redact(f"webhook unreachable: {type(exc).__name__}: {exc}"),
            )


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
