"""NOTIF-1 ORM model — ``breach_notification`` (Wave-12 slice 2).

``BreachNotification`` (ENT-064, **IA TRUE append-only**): one durable attempt row per
(alarm audit event, recipient) — the system-of-record for "who was owed an alert, for what breach
event, when, with what outcome" (OQ-1=A record-first). It binds NO snapshot/run/model (not a
governed number — OD parity with ``breach``). PROPRIETARY, tenant-scoped, symmetric FORCE RLS.

**The idempotency backstop:** ``UniqueConstraint(tenant_id, source_sequence_no, recipient_id)`` =
at-most-once per recipient per alarm event (the ``uq_breach_escalation``/``uq_breach_limit_run``
pattern). A re-tick's duplicate is a benign SAVEPOINT-caught ``IntegrityError``. The per-tenant
high-water is DERIVED from ``MAX(source_sequence_no)`` over this table (OQ-4=B — no separate cursor
table); a no-recipient event writes ONE ``SUPPRESSED`` sentinel row (``recipient_id`` = the fixed
non-null ``NO_RECIPIENT_SENTINEL``) so the derived cursor still advances.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    event,
)
from sqlalchemy.orm import Mapped, Mapper, mapped_column

from irp_shared.audit.models import AppendOnlyViolation
from irp_shared.db.base import Base
from irp_shared.db.mixins import ImmutableAppendOnlyMixin, PrimaryKeyMixin, TenantMixin
from irp_shared.db.types import GUID
from irp_shared.temporal import TemporalClass


class BreachNotification(PrimaryKeyMixin, TenantMixin, ImmutableAppendOnlyMixin, Base):
    """One notification attempt for one (alarm event, recipient) — ENT-064, IA TRUE append-only."""

    __tablename__ = "breach_notification"
    __temporal_class__ = TemporalClass.IMMUTABLE_APPEND_ONLY
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "source_sequence_no",
            "recipient_id",
            name="uq_breach_notification_event_recipient",
        ),
        Index("ix_breach_notification_breach_id", "breach_id"),
        # the derived-high-water scan: "alarm events already notified for this tenant".
        Index("ix_breach_notification_tenant_seq", "tenant_id", "source_sequence_no"),
    )

    #: The ``audit_event.sequence_no`` (per-tenant gap-free monotonic cursor) that triggered this —
    #: the dedup + ordering key; the derived high-water is ``MAX(source_sequence_no)`` per tenant.
    source_sequence_no: Mapped[int] = mapped_column(BigInteger, nullable=False)
    #: The alarm event type (``BREACH.DETECT`` | ``BREACH.ESCALATE``).
    source_event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    #: The subject breach. Extracted PER event_type: DETECT → audit ``entity_id`` (the breach id);
    #: ESCALATE → ``after_value["breach_id"]`` (its ``entity_id`` is the breach_action id).
    breach_id: Mapped[str] = mapped_column(GUID, ForeignKey("breach.id"), nullable=False)
    #: The in-tenant ``app_user.id`` owed the alert, OR ``NO_RECIPIENT_SENTINEL`` for a SUPPRESSED
    #: (no-recipient) row. Canonicalized; the queue/read filter compares canonical-to-canonical.
    recipient_id: Mapped[str] = mapped_column(String(255), nullable=False)
    #: WHY they are a recipient (the permission code) — the evidence of correct addressing.
    recipient_reason: Mapped[str] = mapped_column(String(64), nullable=False)
    #: Delivery channel (v1 ``LOG``; future ``EMAIL``/``WEBHOOK``).
    channel: Mapped[str] = mapped_column(String(20), nullable=False)
    #: Terminal outcome (``SENT`` | ``FAILED`` | ``SUPPRESSED``).
    outcome: Mapped[str] = mapped_column(String(20), nullable=False)
    #: WHY a FAILED send failed (the ``ScheduledRun.failure_reason`` presentation precedent).
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    #: The source event's severity, carried for the sink/recipient to filter (warning/info).
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    #: The wall-clock instant of the attempt (operational evidence).
    notified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


def _block_mutation(mapper: Mapper[Any], connection: Any, target: Any) -> None:
    raise AppendOnlyViolation(
        f"{type(target).__name__} is append-only (AUD-01); update/delete is forbidden"
    )


# IA TRUE append-only (the ORM guard paired with the P0001 DB trigger, migration 0052).
event.listen(BreachNotification, "before_update", _block_mutation)
event.listen(BreachNotification, "before_delete", _block_mutation)
