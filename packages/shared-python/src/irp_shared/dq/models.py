"""Data-quality ORM models (ENT-039: data_quality_rule EV, data_quality_result IA).

``data_quality_rule`` (EV) is the mutable rule config head; ``data_quality_result`` (IA) is the
immutable run output (a flagged FAIL/WARN can never be silently cleared — no-silent-failure).
``rule_type`` is a controlled-vocab **string** (no enum / no CHECK) so generic rule kinds extend by
value; the validated target is a polymorphic ``(target_entity_type, target_entity_id)`` with no FK.
The ``data_source_id`` FK is declared by **string table name** ("data_source.id") so this package
imports nothing from ``irp_shared.lineage``; ``ingestion_batch_id`` is a nullable no-FK placeholder
reserved for P1A-4. The IA result carries an ORM append-only guard; the migration adds the trigger.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import JSON, Boolean, ForeignKey, Integer, String, UniqueConstraint, event
from sqlalchemy.orm import Mapped, Mapper, mapped_column

from irp_shared.audit.models import AppendOnlyViolation
from irp_shared.db.base import Base
from irp_shared.db.mixins import (
    EffectiveDatedMixin,
    ImmutableAppendOnlyMixin,
    PrimaryKeyMixin,
    TenantMixin,
    TimestampMixin,
)
from irp_shared.db.types import GUID
from irp_shared.temporal import TemporalClass

#: Severity controlled-vocab (drives the raise-vs-flag policy; OQ-P1A-3-2).
SEVERITY_ERROR = "ERROR"
SEVERITY_WARNING = "WARNING"

#: Result outcome controlled-vocab.
OUTCOME_PASS = "PASS"
OUTCOME_FAIL = "FAIL"
OUTCOME_WARN = "WARN"


class DataQualityRule(PrimaryKeyMixin, TenantMixin, EffectiveDatedMixin, TimestampMixin, Base):
    """DQ rule config head (ENT-039, EV). The DR-P1-3 maker-checker hooks are **non-enforcing**
    placeholders reserved for the P7 override SoD (REQ-DQR-003); P1A-3 enforces no approval."""

    __tablename__ = "data_quality_rule"
    __temporal_class__ = TemporalClass.EFFECTIVE_DATED
    __table_args__ = (
        UniqueConstraint("tenant_id", "code", name="uq_data_quality_rule_tenant_code"),
    )

    code: Mapped[str] = mapped_column(String(150), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # Controlled-vocab string (NO enum / NO CHECK) — new generic rule kinds register by value.
    rule_type: Mapped[str] = mapped_column(String(50), nullable=False)
    params: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    # Polymorphic kind of the thing the rule validates; NO FK; nullable (no domain target yet).
    target_entity_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    severity: Mapped[str] = mapped_column(String(20), nullable=False, default=SEVERITY_ERROR)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    record_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    # DR-P1-3 maker-checker hooks — nullable, non-enforcing (P6 / REQ-DQR-003).
    approval_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    approval_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    made_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    checked_by: Mapped[str | None] = mapped_column(String(255), nullable=True)


class DataQualityResult(PrimaryKeyMixin, TenantMixin, ImmutableAppendOnlyMixin, Base):
    """Immutable DQ run output (ENT-039, IA). A failing check persists here with ``passed=false``
    (the no-silent-failure detective floor); the row can never be mutated/deleted."""

    __tablename__ = "data_quality_result"
    __temporal_class__ = TemporalClass.IMMUTABLE_APPEND_ONLY

    rule_id: Mapped[str] = mapped_column(
        GUID, ForeignKey("data_quality_rule.id"), nullable=False, index=True
    )
    # Polymorphic target descriptor (no FK) — what was validated.
    target_entity_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    target_entity_id: Mapped[str | None] = mapped_column(GUID, nullable=True)
    passed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    outcome: Mapped[str] = mapped_column(String(20), nullable=False)  # PASS | FAIL | WARN
    observed_value: Mapped[str | None] = mapped_column(String(500), nullable=True)
    detail: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    evaluated_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    failed_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Nullable real intra-tenant FK to data_source (ENT-038), the thing validated (string ref).
    data_source_id: Mapped[str | None] = mapped_column(
        GUID, ForeignKey("data_source.id"), nullable=True, index=True
    )
    # FUTURE placeholder, NO FK (P1A-4 owns ingestion_batch); plain nullable GUID.
    ingestion_batch_id: Mapped[str | None] = mapped_column(GUID, nullable=True)


def _block_mutation(mapper: Mapper[Any], connection: Any, target: Any) -> None:
    raise AppendOnlyViolation(
        f"{type(target).__name__} is append-only (AUD-01); update/delete is forbidden"
    )


# data_quality_rule is EV (mutable) — only the IA result gets the ORM append-only guard.
event.listen(DataQualityResult, "before_update", _block_mutation)
event.listen(DataQualityResult, "before_delete", _block_mutation)
