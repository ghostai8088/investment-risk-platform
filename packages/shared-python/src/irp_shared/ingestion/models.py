"""Generic ingestion-staging ORM models (P1A-4, REQ-INT-001).

``ingestion_batch`` (ENT-047, IA-classed but **status-mutable**) is the run/event record for one
upload; it follows ``calculation_run`` — IA temporal class with a single ``system_from``
axis, a mutable ``status`` projection, **NOT** in ``APPEND_ONLY_TABLES`` (no DB mutation trigger, no
ORM guard) so transitions are allowed, and every transition is written immutably to the audit log.

``ingestion_staged_record`` (ENT-048, IA truly immutable) is a parsed/neutralized raw row; it is
append-only (ORM guard here + the DB ``irp_prevent_mutation`` trigger added by migration 0007). The
``payload`` is a single generic JSON column — NO domain shape/FK/canonical column; a re-ingest is a
NEW batch, never a mutation. Staging is domain-agnostic (no Security Master /
portfolio / position / valuation coupling) — canonical mapping of staged rows does NOT exist
(zero consumers of ``ingestion_staged_record`` outside this package); whether Wave-14's REF-1
onboarding rail completes it is a named slice-gate fork (the stale "deferred to P1B/P1C"
pointer was re-synced at the Wave-14 planning gate, OQ-W14P-7 — those phases closed without it).

``ingestion_batch.data_source_id`` is a real intra-context FK to ``data_source.id`` (the provenance
root the mandatory lineage ORIGIN edge needs). No FK points at any domain/analytical table.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    event,
)
from sqlalchemy.orm import Mapped, Mapper, mapped_column

from irp_shared.audit.models import AppendOnlyViolation
from irp_shared.db.base import Base
from irp_shared.db.mixins import (
    ImmutableAppendOnlyMixin,
    PrimaryKeyMixin,
    TenantMixin,
    utcnow,
)
from irp_shared.db.types import GUID
from irp_shared.temporal import TemporalClass

#: Batch lifecycle controlled-vocab (String, NO enum/CHECK — extend by value, never a migration).
STATUS_RECEIVED = "RECEIVED"
STATUS_VALIDATING = "VALIDATING"
STATUS_STAGED = "STAGED"
STATUS_COMPLETED = "COMPLETED"
STATUS_COMPLETED_WITH_WARNINGS = "COMPLETED_WITH_WARNINGS"
STATUS_FAILED = "FAILED"
STATUS_REJECTED = "REJECTED"

#: Statuses that close a batch (set ``completed_at`` on entry).
TERMINAL_STATUSES = frozenset(
    {STATUS_COMPLETED, STATUS_COMPLETED_WITH_WARNINGS, STATUS_FAILED, STATUS_REJECTED}
)

#: AV/malware scan controlled-vocab. Defaults to a NON-clean value (the AV is a no-op placeholder
#: seam now, OD-042); a real integration later swaps it and may gate on CLEAN — no schema change.
SCAN_PENDING = "PENDING"
SCAN_CLEAN = "CLEAN"
SCAN_SKIPPED = "SKIPPED"


class IngestionBatch(PrimaryKeyMixin, TenantMixin, ImmutableAppendOnlyMixin, Base):
    """One upload's run record (ENT-047, IA-classed status-mutable; the CalculationRun precedent).

    NOT in ``APPEND_ONLY_TABLES`` and carries NO ORM mutation guard — the ``status`` projection
    transitions through its lifecycle while the authoritative history is the append-only
    ``DATA.INGEST`` audit chain. ``data_source_id`` is a real FK (provenance root)."""

    __tablename__ = "ingestion_batch"
    __temporal_class__ = TemporalClass.IMMUTABLE_APPEND_ONLY

    data_source_id: Mapped[str] = mapped_column(
        GUID, ForeignKey("data_source.id"), nullable=False, index=True
    )
    # Sanitized basename only — NEVER the raw client path (THR-06 path-traversal).
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    byte_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    # varchar(30), NOT 20. `COMPLETED_WITH_WARNINGS` is 23 characters and this column was
    # varchar(20) from migration 0007 until W19-S3a, so a batch that finished WITH WARNINGS
    # could never be persisted on PostgreSQL — it raised StringDataRightTruncation. Invisible
    # for four waves because SQLite ignores VARCHAR length (column affinity), so the entire
    # unit tier passed, and no PG test exercised the warning path. Found by the 0075 P17
    # harness. `test_controlled_vocab_widths.py` is the mechanical gate that closes the class.
    status: Mapped[str] = mapped_column(String(30), nullable=False, default=STATUS_RECEIVED)
    scan_status: Mapped[str] = mapped_column(String(20), nullable=False, default=SCAN_PENDING)
    row_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    staged_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    failed_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # W19-S3a (REQ-INT-001 clause 2, the batch half): the RATIFIED mapping version this batch was
    # interpreted through — a HARD FK, never free text. NULLABLE because a generic non-positions
    # upload legitimately has none (this table stages files the mapping spine never interprets) and
    # because the table is populated on every live deployment; the LOAD PATH requires it, not the
    # schema. Spelled as a literal table name rather than a Python import: `irp_shared.ingestion`
    # may not import `irp_shared.ingest_mapping` (the dependency runs the other way), and the
    # `HYBRID_TABLES` literal-spelling precedent covers exactly this shape.
    mapping_version_id: Mapped[str | None] = mapped_column(
        GUID,
        ForeignKey("ingestion_mapping_version.id", name="fk_ingestion_batch_mapping_version"),
        nullable=True,
        index=True,
    )
    # The instant every code-lookup in this batch resolved against — REQ-INT-001 clause (9)'s third
    # named input. Recorded rather than assumed: without it a re-run would resolve identifiers "now"
    # and silently disagree with the original load the moment an identifier is superseded.
    lookup_as_of: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class IngestionStagedRecord(PrimaryKeyMixin, TenantMixin, ImmutableAppendOnlyMixin, Base):
    """A parsed, formula-neutralized raw row (ENT-048, IA, truly immutable / append-only).

    ``payload`` is a single generic JSON column — NO domain shape, NO domain FK, NO canonical
    column. The ORM guard below + the migration-0007 trigger forbid update/delete (AUD-01)."""

    __tablename__ = "ingestion_staged_record"
    __temporal_class__ = TemporalClass.IMMUTABLE_APPEND_ONLY
    __table_args__ = (
        UniqueConstraint("batch_id", "row_number", name="uq_ingestion_staged_record_batch_row"),
    )

    batch_id: Mapped[str] = mapped_column(
        GUID, ForeignKey("ingestion_batch.id"), nullable=False, index=True
    )
    row_number: Mapped[int] = mapped_column(Integer, nullable=False)
    # Generic parsed row; NO domain shape / NO canonical column (staging is not canonical data).
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)


def _block_mutation(mapper: Mapper[Any], connection: Any, target: Any) -> None:
    raise AppendOnlyViolation(
        f"{type(target).__name__} is append-only (AUD-01); update/delete is forbidden"
    )


# ingestion_batch is status-mutable (no guard); only the immutable staged record gets the guard.
event.listen(IngestionStagedRecord, "before_update", _block_mutation)
event.listen(IngestionStagedRecord, "before_delete", _block_mutation)
