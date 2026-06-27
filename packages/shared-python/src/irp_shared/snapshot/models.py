"""Reproducible input-snapshot ORM models (P2-1, ENT-049/050, IA — AD-014).

``dataset_snapshot`` (header) + ``dataset_snapshot_component`` (per-input physical-version pin) are
the AD-014 reproducibility primitive: an immutable, knowledge-time pin of the exact governed input
record versions a later ``calculation_run`` (P2-3) consumes. Reproducibility **infrastructure** —
it captures input versions and computes **no** derived number.

Both tables are **IA TRUE append-only** (the ``transaction`` precedent, NOT the status-mutable
``calculation_run``/``ingestion_batch`` flavor): in the migration-0016 ``APPEND_ONLY_TABLES`` ->
the ``irp_prevent_mutation`` P0001 trigger, paired with the ORM ``before_update``/``before_delete``
guard below (shared ``audit.models.AppendOnlyViolation``). A snapshot is created once and never
mutated; a new input set is a NEW snapshot. PROPRIETARY, tenant-scoped, **NEVER hybrid** (symmetric
RLS only, migration 0016). No ``valid_*`` axis (the as-of-ness lives in the pinned input versions +
the header cutoffs). **No ``status``; no ``model_version`` component** (model binds at the run,
OD-P2-C). The component captures both a physical-version PIN (``target_entity_id`` + coords) and the
``captured_content`` (the canonical-serialized value) so the snapshot is self-sufficient (§8).
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, event
from sqlalchemy.orm import Mapped, Mapper, mapped_column

from irp_shared.audit.models import AppendOnlyViolation
from irp_shared.db.base import Base
from irp_shared.db.mixins import (
    ImmutableAppendOnlyMixin,
    PrimaryKeyMixin,
    TenantMixin,
    TimestampMixin,
)
from irp_shared.db.types import GUID
from irp_shared.temporal import TemporalClass

#: Controlled-vocab ``purpose`` values (plain String, no enum/CHECK; app-side allow-list in binder).
PURPOSE_EXPOSURE_INPUT = "EXPOSURE_INPUT"
PURPOSE_ADHOC = "ADHOC"
PURPOSE_TEST = "TEST"
SNAPSHOT_PURPOSES = (PURPOSE_EXPOSURE_INPUT, PURPOSE_ADHOC, PURPOSE_TEST)

#: Controlled-vocab ``component_kind`` values (PRICE/CURVE/REFERENCE reserved later).
COMPONENT_KIND_PORTFOLIO = "PORTFOLIO"
COMPONENT_KIND_POSITION = "POSITION"
COMPONENT_KIND_VALUATION = "VALUATION"
#: P2-3 (OD-P2-3-E): a pinned ``fx_rate`` (ENT-024) leg — captured so a base-currency exposure run
#: is reproducible from the snapshot alone (the exposure compute reads this captured content, never
#: a live FX read). Minted additively; the tables are unchanged (no schema redesign).
COMPONENT_KIND_FX = "FX"
SNAPSHOT_COMPONENT_KINDS = (
    COMPONENT_KIND_PORTFOLIO,
    COMPONENT_KIND_POSITION,
    COMPONENT_KIND_VALUATION,
    COMPONENT_KIND_FX,
)


class DatasetSnapshot(PrimaryKeyMixin, TenantMixin, ImmutableAppendOnlyMixin, TimestampMixin, Base):
    """Reproducible input-snapshot HEADER (ENT-049, IA true-append-only). Created once, never
    mutated; ``id`` is the future referent of ``calculation_run.input_snapshot_id`` (P2-3)."""

    __tablename__ = "dataset_snapshot"
    __temporal_class__ = TemporalClass.IMMUTABLE_APPEND_ONLY

    label: Mapped[str] = mapped_column(String(255), nullable=False)
    purpose: Mapped[str] = mapped_column(String(50), nullable=False)  # controlled-vocab plain str
    as_of_valid_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # FROZEN at create; both the binder and verify use this concrete instant (never wall-clock now).
    as_of_known_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    as_of_valuation_date: Mapped[date] = mapped_column(Date, nullable=False)
    binding_predicate_version: Mapped[str] = mapped_column(String(50), nullable=False)
    component_count: Mapped[int] = mapped_column(Integer, nullable=False)
    manifest_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    # NO status column (created-complete; immutable). NO model_version (binds at the run, OD-P2-C).


class DatasetSnapshotComponent(PrimaryKeyMixin, TenantMixin, ImmutableAppendOnlyMixin, Base):
    """Per-input physical-version pin + captured value of a ``dataset_snapshot`` (ENT-050, IA).

    Polymorphic ``(target_entity_type, target_entity_id)`` — **no domain FK** (mirrors lineage_edge/
    identifier_xref). ``target_entity_id`` is the **surrogate row id** (the physical-version
    identity for FR; the current row id for EV). ``captured_content`` is the canonical-serialized
    immutable value; ``content_hash = sha256_hex(captured_content)``. ``pinned_system_from`` is NULL
    for the EV ``portfolio`` kind (no system axis); ``record_version`` is the authoritative EV drift
    discriminator.
    """

    __tablename__ = "dataset_snapshot_component"
    __temporal_class__ = TemporalClass.IMMUTABLE_APPEND_ONLY
    __table_args__ = (
        # A physical version is pinned at most once per snapshot.
        UniqueConstraint(
            "snapshot_id",
            "component_kind",
            "target_entity_id",
            name="uq_dataset_snapshot_component_snapshot_kind_target",
        ),
    )

    snapshot_id: Mapped[str] = mapped_column(
        GUID, ForeignKey("dataset_snapshot.id"), nullable=False, index=True
    )
    component_kind: Mapped[str] = mapped_column(String(50), nullable=False)
    target_entity_type: Mapped[str] = mapped_column(String(50), nullable=False)
    target_entity_id: Mapped[str] = mapped_column(GUID, nullable=False)
    pinned_valid_from: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    pinned_system_from: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    pinned_record_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    captured_content: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)


def _block_mutation(mapper: Mapper[Any], connection: Any, target: Any) -> None:
    raise AppendOnlyViolation(
        f"{type(target).__name__} is append-only (AUD-01); update/delete is forbidden"
    )


# True append-only: the ORM guard (paired with the migration-0016 P0001 trigger) forbids
# update/delete on BOTH the header and the component. A snapshot is never mutated — a new input
# set is a new snapshot.
for _model in (DatasetSnapshot, DatasetSnapshotComponent):
    event.listen(_model, "before_update", _block_mutation)
    event.listen(_model, "before_delete", _block_mutation)
