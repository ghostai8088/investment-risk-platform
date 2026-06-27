"""Data-source & lineage ORM models (ENT-038 data_source, ENT-042 lineage_edge).

``data_source`` (EV) is mutable effective-dated provenance config; ``lineage_edge`` (IA) is an
immutable, append-only fact-of-capture. ``lineage_edge`` carries a **polymorphic** target
reference (``target_entity_type`` / ``target_entity_id``) with **no domain foreign key**, mirroring
``audit_event`` — this is what keeps the table domain-agnostic. The ORM append-only guard mirrors
``audit/models.py``; the foundation migration adds the equivalent PostgreSQL trigger.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import Boolean, Integer, String, UniqueConstraint, event
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

#: Upstream node kinds for ``lineage_edge.source_type``.
SOURCE_TYPE_DATA_SOURCE = "data_source"
#: P2-1: a ``dataset_snapshot`` (ENT-049) source node — snapshot -> pinned-input-version edges.
SOURCE_TYPE_DATA_SNAPSHOT = "data_snapshot"
#: P2-3 (OD-P2-3-J): a ``calculation_run`` (ENT-026) source node — run -> derived-result edges.
SOURCE_TYPE_CALCULATION_RUN = "calculation_run"

#: Edge relationship roles (controlled vocab).
EDGE_KIND_ORIGIN = "ORIGIN"
#: P2-3 (OD-P2-3-J): a dependency edge (``dataset_snapshot`` --DEPENDS_ON--> ``calculation_run``).
#: (NOTE: "DEP-LIN" is the RTM/control traceability token, NOT an ``edge_kind`` — DR-P2-3-J.)
EDGE_KIND_DEPENDENCY = "DEPENDS_ON"


class DataSource(PrimaryKeyMixin, TenantMixin, EffectiveDatedMixin, TimestampMixin, Base):
    """Provenance root (ENT-038, EV). Registered/updated only via ``lineage.service`` utilities;
    no public create endpoint. The DR-P1-3 maker-checker hook columns are nullable and
    **non-enforcing** until approval workflow lands (P6)."""

    __tablename__ = "data_source"
    __temporal_class__ = TemporalClass.EFFECTIVE_DATED
    __table_args__ = (UniqueConstraint("tenant_id", "code", name="uq_data_source_tenant_code"),)

    code: Mapped[str] = mapped_column(String(150), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    source_type: Mapped[str] = mapped_column(String(50), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # EV system-time versioning aspect (EffectiveDatedMixin omits it); canonical §4 common column.
    record_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    # DR-P1-3 maker-checker hooks — nullable, non-enforcing (P6).
    approval_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    approval_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    made_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    checked_by: Mapped[str | None] = mapped_column(String(255), nullable=True)


class LineageEdge(PrimaryKeyMixin, TenantMixin, ImmutableAppendOnlyMixin, Base):
    """Immutable lineage capture (ENT-042, IA). A thin generic join: upstream node
    (``source_type``/``source_id``) → polymorphic target (``target_entity_type``/
    ``target_entity_id``). No domain FK; integrity is by-convention + the BX-LIN test."""

    __tablename__ = "lineage_edge"
    __temporal_class__ = TemporalClass.IMMUTABLE_APPEND_ONLY

    source_type: Mapped[str] = mapped_column(String(50), nullable=False)
    source_id: Mapped[str] = mapped_column(GUID, nullable=False)
    target_entity_type: Mapped[str] = mapped_column(String(100), nullable=False)
    target_entity_id: Mapped[str] = mapped_column(GUID, nullable=False)
    edge_kind: Mapped[str] = mapped_column(String(50), nullable=False, default=EDGE_KIND_ORIGIN)
    # Logical (non-FK) reference to calculation_run.run_id (FW-RUN); null for non-run origins.
    run_id: Mapped[str | None] = mapped_column(GUID, nullable=True)


def _block_mutation(mapper: Mapper[Any], connection: Any, target: Any) -> None:
    raise AppendOnlyViolation(
        f"{type(target).__name__} is append-only (AUD-01); update/delete is forbidden"
    )


event.listen(LineageEdge, "before_update", _block_mutation)
event.listen(LineageEdge, "before_delete", _block_mutation)
