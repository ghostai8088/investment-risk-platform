"""Model-registry ORM models (ENT-035 model/model_version, ENT-036 assumption/limitation).

``model`` (EV) is the mutable governance head; ``model_version`` (IA) is the immutable, durable
anchor future ``CalculationRun``/lineage bind to (TR-11, AD-006); ``model_assumption`` /
``model_limitation`` (IA) are immutable captures tied to a version. The three IA tables carry an
ORM append-only guard (mirroring ``audit``/``lineage``); the migration adds the equivalent
PostgreSQL trigger. ``model_type`` is a controlled-vocabulary **string** (no enum / no CHECK) so new
model families need no schema change (MG-01 genericity). Governance columns on the head are
**non-enforcing placeholders** (reserved for REQ-MDG-002/003, P7).
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import Boolean, ForeignKey, Integer, String, UniqueConstraint, event
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

#: Non-enforcing default for the reserved validation_status placeholder (P7 advances it, not P1A-2).
VALIDATION_STATUS_UNVALIDATED = "UNVALIDATED"


class Model(PrimaryKeyMixin, TenantMixin, EffectiveDatedMixin, TimestampMixin, Base):
    """Model inventory head (ENT-035, EV). Governance columns (tier/validation_status/approved_use/
    restricted_use/owner/developer) and the DR-P1-3 maker-checker hooks are **non-enforcing**
    placeholders reserved for the P7 validation/approval workflow — P1A-2 gates on none of them."""

    __tablename__ = "model"
    __temporal_class__ = TemporalClass.EFFECTIVE_DATED
    __table_args__ = (UniqueConstraint("tenant_id", "code", name="uq_model_tenant_code"),)

    code: Mapped[str] = mapped_column(String(150), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # Controlled-vocab string (NO enum / NO CHECK) — new model families register by value (MG-01).
    model_type: Mapped[str] = mapped_column(String(50), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    record_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    # Non-enforcing governance placeholders — reserved for REQ-MDG-002/003 (P7); gate nothing.
    owner: Mapped[str | None] = mapped_column(String(255), nullable=True)
    developer: Mapped[str | None] = mapped_column(String(255), nullable=True)
    tier: Mapped[str | None] = mapped_column(String(20), nullable=True)
    validation_status: Mapped[str | None] = mapped_column(
        String(30), nullable=True, default=VALIDATION_STATUS_UNVALIDATED
    )
    approved_use: Mapped[str | None] = mapped_column(String(500), nullable=True)
    restricted_use: Mapped[bool | None] = mapped_column(Boolean, nullable=True, default=False)
    restriction_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # DR-P1-3 maker-checker hooks — nullable, non-enforcing (P6).
    approval_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    approval_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    made_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    checked_by: Mapped[str | None] = mapped_column(String(255), nullable=True)


class ModelVersion(PrimaryKeyMixin, TenantMixin, ImmutableAppendOnlyMixin, Base):
    """Immutable model version (ENT-035, IA) — the stable referent for future
    ``CalculationRun.model_version_id`` and run->result lineage (change = new version, MG-10)."""

    __tablename__ = "model_version"
    __temporal_class__ = TemporalClass.IMMUTABLE_APPEND_ONLY
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "model_id", "version_label", name="uq_model_version_tenant_model_label"
        ),
    )

    model_id: Mapped[str] = mapped_column(GUID, ForeignKey("model.id"), nullable=False, index=True)
    version_label: Mapped[str] = mapped_column(String(50), nullable=False)
    methodology_ref: Mapped[str | None] = mapped_column(String(500), nullable=True)
    code_version: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # Version status (e.g. DRAFT/REGISTERED). ENFORCING at the RISK bind since P3-C1
    # (risk.bootstrap.assert_model_version_of requires 'REGISTERED'); still NOT a validation
    # gate (P7) and non-enforcing for generic registry consumers.
    status: Mapped[str | None] = mapped_column(String(20), nullable=True)


class ModelAssumption(PrimaryKeyMixin, TenantMixin, ImmutableAppendOnlyMixin, Base):
    """Immutable assumption tied to a version (ENT-036, IA)."""

    __tablename__ = "model_assumption"
    __temporal_class__ = TemporalClass.IMMUTABLE_APPEND_ONLY

    model_version_id: Mapped[str] = mapped_column(
        GUID, ForeignKey("model_version.id"), nullable=False, index=True
    )
    assumption_text: Mapped[str] = mapped_column(String(2000), nullable=False)
    category: Mapped[str | None] = mapped_column(String(50), nullable=True)
    # MG-05 attribution: free string accepting a human OR an AI-agent principal id.
    authored_by: Mapped[str | None] = mapped_column(String(255), nullable=True)


class ModelLimitation(PrimaryKeyMixin, TenantMixin, ImmutableAppendOnlyMixin, Base):
    """Immutable limitation tied to a version (ENT-036, IA; BX-LIM/CTRL-014)."""

    __tablename__ = "model_limitation"
    __temporal_class__ = TemporalClass.IMMUTABLE_APPEND_ONLY

    model_version_id: Mapped[str] = mapped_column(
        GUID, ForeignKey("model_version.id"), nullable=False, index=True
    )
    limitation_text: Mapped[str] = mapped_column(String(2000), nullable=False)
    severity: Mapped[str | None] = mapped_column(String(20), nullable=True)
    authored_by: Mapped[str | None] = mapped_column(String(255), nullable=True)


def _block_mutation(mapper: Mapper[Any], connection: Any, target: Any) -> None:
    raise AppendOnlyViolation(
        f"{type(target).__name__} is append-only (AUD-01); update/delete is forbidden"
    )


# model is EV (mutable) — only the IA tables get the ORM append-only guard.
for _ia_model in (ModelVersion, ModelAssumption, ModelLimitation):
    event.listen(_ia_model, "before_update", _block_mutation)
    event.listen(_ia_model, "before_delete", _block_mutation)
