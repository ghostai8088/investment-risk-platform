"""ENT-077 ``ingestion_mapping_version`` — the ratifiable source mapping (W19-S3a, REQ-INT-001).

The artifact behind INGEST-1's ratified spine (OQ-ING-1..4, 2026-08-12): *the AI proposes a
mapping, a human ratifies it, the platform executes the ratified version deterministically
forever, and every loaded row records which version loaded it.* A mapping is **versioned DATA
interpreted** by a closed operation vocabulary (OQ-ING-1=A) — never generated code — so onboarding
a client's file needs no software release.

**Temporal class: IA, status-mutable — the ``ingestion_batch`` / ``calculation_run`` precedent, and
the choice is stated rather than left to be inferred.** ``status`` transitions PROPOSED → RATIFIED
→ SUPERSEDED, so the row is deliberately **NOT** in ``APPEND_ONLY_TABLES``, carries **no**
``irp_prevent_mutation`` trigger and **no** ORM ``before_update`` guard; the authoritative history
is the append-only ``DATA.MAPPING`` audit chain. The commoner choice on this project is true IA
plus the trigger (ENT-076, ENT-075), which is exactly why this docstring says which one this is.

**Content immutability is service-enforced** (``service.assert_only_lifecycle_fields_change``), not
trigger-enforced — nothing at the DB layer will catch a content edit, the same posture as
``position`` and for the same reason. An edited mapping is a NEW version that SUPERSEDES its
predecessor.

PROPRIETARY, tenant-scoped, **symmetric** FORCE RLS (``USING`` == ``WITH CHECK`` == own tenant).
NEVER hybrid — the AD-013-R2 hybrid set is closed at seven and DB-censused.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from irp_shared.db.base import Base
from irp_shared.db.mixins import ImmutableAppendOnlyMixin, PrimaryKeyMixin, TenantMixin
from irp_shared.db.types import GUID
from irp_shared.temporal import TemporalClass

#: Lifecycle vocabulary — plain controlled-vocab strings, NO enum and NO vocabulary CHECK
#: (genericity, MG-01: extend by value, never a migration).
STATUS_PROPOSED = "PROPOSED"
STATUS_RATIFIED = "RATIFIED"
STATUS_SUPERSEDED = "SUPERSEDED"
STATUS_WITHDRAWN = "WITHDRAWN"

#: Authorship vocabulary. ``MODEL_PROPOSED`` is the ratified thesis' left-hand side;
#: ``HAND_AUTHORED`` is the honest label for an operator-written mapping. The SYMMETRIC check
#: constraint below binds each to its evidence — REQ-INT-001 clause (7).
AUTHORSHIP_MODEL_PROPOSED = "MODEL_PROPOSED"
AUTHORSHIP_HAND_AUTHORED = "HAND_AUTHORED"

#: The source types a mapping may target. ONE end to end first (OQ-ING-4=A: positions, then prices
#: and benchmarks). A plain string — a new source type is a value, not a migration.
SOURCE_TYPE_POSITIONS = "POSITIONS"

#: The CHECK constraint's SUFFIX ONLY, on BOTH sides. ``env.py`` passes ``target_metadata`` so
#: ``op.create_table`` applies ``ck_%(table_name)s_%(constraint_name)s`` itself; passing the full
#: name mints a doubled, 63-char-truncated name that silently DRIFTS from the ORM's, and
#: ``alembic check`` does not compare CHECK constraints (the 0055/0057 lesson, inherited rather
#: than re-learned). Budget: ``ck_ingestion_mapping_version_`` is 29 of 63, leaving 34 for this.
CHECK_AUTHORSHIP = "authorship_evidence"

#: The lifecycle columns a RATIFIED/SUPERSEDED transition is allowed to move. Everything else on
#: the row is content, and is immutable by service guard.
LIFECYCLE_FIELDS = frozenset(
    {"status", "ratified_by_actor_id", "ratified_at", "superseded_at", "supersedes_id"}
)


class IngestionMappingVersion(PrimaryKeyMixin, TenantMixin, ImmutableAppendOnlyMixin, Base):
    """ENT-077 — one ratifiable version of a source-file-to-canonical mapping."""

    __tablename__ = "ingestion_mapping_version"
    __temporal_class__ = TemporalClass.IMMUTABLE_APPEND_ONLY
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "data_source_id",
            "source_type",
            "version_label",
            name="uq_ingestion_mapping_version_label",
        ),
        # At most ONE ratified mapping per (tenant, source, source_type) at a time. The predicate
        # is spelled TWICE and IDENTICALLY on purpose: a `postgresql_where`-only index renders on
        # SQLite as a PLAIN unique index with the predicate SILENTLY DROPPED (verified by
        # execution, not by reading), and the unit tier builds its schema on SQLite — so the
        # omission would make the unit tier reject a legal second PROPOSED row while proving
        # nothing at all about Postgres. Both shipped precedents (`uq_position_current`,
        # `uq_identifier_xref_active`) carry the twin predicate.
        Index(
            "uq_ingestion_mapping_version_active",
            "tenant_id",
            "data_source_id",
            "source_type",
            unique=True,
            postgresql_where=text("status = 'RATIFIED'"),
            sqlite_where=text("status = 'RATIFIED'"),
        ),
        # Clause (7)'s teeth at the DATABASE, and SYMMETRIC in both directions. One-directional was
        # the first draft: it let a HAND_AUTHORED row carry stale or forged model attribution that
        # a reviewer reads as provenance — the mirror of the false record the clause prevents.
        CheckConstraint(
            "(authorship = 'MODEL_PROPOSED' AND proposer_model_version_id IS NOT NULL "
            "AND proposal_prompt_hash IS NOT NULL) OR "
            "(authorship = 'HAND_AUTHORED' AND proposer_model_version_id IS NULL "
            "AND proposal_prompt_hash IS NULL)",
            name=CHECK_AUTHORSHIP,
        ),
    )

    data_source_id: Mapped[str] = mapped_column(
        GUID, ForeignKey("data_source.id"), nullable=False, index=True
    )
    # Controlled-vocab plain string (POSITIONS today; prices/benchmarks extend by value, OQ-ING-4).
    source_type: Mapped[str] = mapped_column(String(30), nullable=False)
    version_label: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default=STATUS_PROPOSED)

    # The ordered closed-set operation list. Generic JSON — no domain shape, no per-operation
    # table: a mapping is DATA, and its vocabulary is policed by the interpreter's exact-set
    # census, not by a schema needing a migration per new operation (OQ-ING-1=A's whole point).
    operations: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    # sha256 over the canonical serialization of `operations` — clause (9)'s reproducibility key.
    operations_hash: Mapped[str] = mapped_column(String(64), nullable=False)

    authorship: Mapped[str] = mapped_column(String(20), nullable=False)
    # Hard FK: model_version is tenant-scoped and PROPRIETARY, the same class as this table. The FK
    # is NOT the tenancy control — PostgreSQL FK checks BYPASS RLS — so the writer re-resolves the
    # id tenant-filtered (`assert_model_version_in_tenant`) before stamping it. EXPLICIT constraint
    # name: the convention-generated one is 68 chars and PostgreSQL truncates at 63 SILENTLY (the
    # classification_assignment.supersedes_id precedent, found by an executed dry run).
    proposer_model_version_id: Mapped[str | None] = mapped_column(
        GUID,
        ForeignKey("model_version.id", name="fk_ingestion_mapping_version_model_version"),
        nullable=True,
        index=True,
    )
    # Prompt IDENTITY, not the prompt: sha256 of the committed artifact `proposal_prompt_ref`
    # names, so the recorded provenance is checkable rather than merely asserted.
    proposal_prompt_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    proposal_prompt_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    proposal_response_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)

    proposed_by_actor_id: Mapped[str] = mapped_column(String(255), nullable=False)
    proposed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ratified_by_actor_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    ratified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    superseded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Self-reference. Explicit name for the same 63-char reason as the model_version FK above (the
    # convention-generated form is 68).
    supersedes_id: Mapped[str | None] = mapped_column(
        GUID,
        ForeignKey("ingestion_mapping_version.id", name="fk_ingestion_mapping_version_supersedes"),
        nullable=True,
    )


# NOTE: deliberately NO event.listen(before_update/before_delete) here, and deliberately NOT in
# APPEND_ONLY_TABLES — the status projection MUST transition. The IA guarantee this table gives is
# the one `ingestion_batch` gives: the CONTENT is immutable (service-enforced, mutation-proven) and
# the history is the audit chain. Do not "fix" the asymmetry; the negative controls in
# test_ingest_mapping.py pin both halves, and one of them compares this class's listener set to a
# genuinely append-only peer so an empty result cannot mean "wrong attribute".
