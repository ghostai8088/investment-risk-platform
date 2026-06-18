"""Audit ORM models (ENT-045) with application-level append-only enforcement.

``event_time`` is stored as a canonical UTC ISO-8601 string so the hash chain is
deterministic regardless of the database's datetime round-tripping. The ORM-level
append-only guard (AUD-01) blocks update/delete from the application; the foundation
migration adds an equivalent PostgreSQL trigger for out-of-app protection.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import JSON, BigInteger, String, UniqueConstraint, event
from sqlalchemy.orm import Mapped, Mapper, mapped_column

from irp_shared.audit.hashing import HASH_ALGORITHM, HASH_VERSION
from irp_shared.db.base import Base
from irp_shared.db.mixins import ImmutableAppendOnlyMixin, PrimaryKeyMixin
from irp_shared.temporal import TemporalClass


class AppendOnlyViolation(Exception):
    """Raised when application code attempts to update or delete an append-only record."""


class AuditEvent(PrimaryKeyMixin, ImmutableAppendOnlyMixin, Base):
    __tablename__ = "audit_event"
    __temporal_class__ = TemporalClass.IMMUTABLE_APPEND_ONLY
    __table_args__ = (UniqueConstraint("chain_id", "sequence_no", name="uq_audit_event_chain_id"),)

    # Chain linkage (HC-01): one stream per tenant by default.
    chain_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    sequence_no: Mapped[int] = mapped_column(BigInteger, nullable=False)

    # Event identity / context.
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    event_time: Mapped[str] = mapped_column(String(40), nullable=False)  # canonical UTC ISO-8601
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    actor_type: Mapped[str] = mapped_column(String(20), nullable=False)
    actor_id: Mapped[str] = mapped_column(String(255), nullable=False)
    on_behalf_of: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_module: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    entity_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    before_value: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    after_value: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    justification: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    approval_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    correlation_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    outcome: Mapped[str] = mapped_column(String(20), nullable=False, default="success")
    severity: Mapped[str] = mapped_column(String(20), nullable=False, default="info")
    data_classification: Mapped[str] = mapped_column(String(10), nullable=False, default="DC-2")
    agent_model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    agent_model_version: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Hash chain (BR-18).
    previous_event_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    event_payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    event_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    hash_algorithm: Mapped[str] = mapped_column(String(20), nullable=False, default=HASH_ALGORITHM)
    hash_version: Mapped[str] = mapped_column(String(10), nullable=False, default=HASH_VERSION)


class AuditCheckpoint(PrimaryKeyMixin, ImmutableAppendOnlyMixin, Base):
    """Periodic signed checkpoint (CP-01..04). ``signature`` is a placeholder until signing
    is wired (later-hardening)."""

    __tablename__ = "audit_checkpoint"
    __temporal_class__ = TemporalClass.IMMUTABLE_APPEND_ONLY

    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    chain_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    sequence_no: Mapped[int] = mapped_column(BigInteger, nullable=False)
    last_event_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    signature: Mapped[str | None] = mapped_column(String(512), nullable=True)


def _block_mutation(mapper: Mapper[Any], connection: Any, target: Any) -> None:
    raise AppendOnlyViolation(
        f"{type(target).__name__} is append-only (AUD-01); update/delete is forbidden"
    )


for _model in (AuditEvent, AuditCheckpoint):
    event.listen(_model, "before_update", _block_mutation)
    event.listen(_model, "before_delete", _block_mutation)
