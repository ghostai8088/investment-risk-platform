"""P1A-4: generic ingestion staging (REQ-INT-001).

Adds two tenant-scoped tables — ``ingestion_batch`` (ENT-047, IA-classed but **status-mutable**, the
CalculationRun precedent) and ``ingestion_staged_record`` (ENT-048, IA truly immutable) — with the
same PostgreSQL enforcement the foundation/lineage/model/dq tables use:
- Row-level security (tenant isolation, BR-17) with an **explicit ``WITH CHECK``** on both.
- The append-only trigger (BR-12 / AUD-01) on the IA staged-record table ONLY, reusing
  ``irp_prevent_mutation`` from migration 0001. ``ingestion_batch`` is status-mutable and is
  **deliberately NOT** append-only (the trigger would block every status transition).

``ingestion_batch.data_source_id`` is a real intra-context FK to ``data_source.id``;
``ingestion_staged_record.batch_id`` is a real intra-context FK to ``ingestion_batch.id`` (both
declared with ``fk_`` names matching the NAMING_CONVENTION so ``alembic check`` is drift-clean).
No FK points at any domain/canonical table; ``payload`` is a single generic JSONB column. No new
audit code and no new permission are introduced (``DATA.INGEST`` is activated; ``data.upload`` exists).

Revision ID: 0007_generic_ingestion_staging
Revises: 0006_data_quality_skeleton
Create Date: 2026-06-22
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0007_generic_ingestion_staging"
down_revision: str | None = "0006_data_quality_skeleton"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TENANT_SCOPED_TABLES = ("ingestion_batch", "ingestion_staged_record")
# Only the truly-immutable staged record gets the mutation trigger; the batch is status-mutable.
APPEND_ONLY_TABLES = ("ingestion_staged_record",)


def upgrade() -> None:
    op.create_table(
        "ingestion_batch",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("system_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("data_source_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("content_type", sa.String(length=100), nullable=True),
        sa.Column("byte_size", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("scan_status", sa.String(length=20), nullable=False),
        sa.Column("row_count", sa.Integer(), nullable=True),
        sa.Column("staged_count", sa.Integer(), nullable=True),
        sa.Column("failed_count", sa.Integer(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_ingestion_batch"),
        sa.ForeignKeyConstraint(
            ["data_source_id"],
            ["data_source.id"],
            name="fk_ingestion_batch_data_source_id_data_source",
        ),
    )
    op.create_index("ix_ingestion_batch_tenant_id", "ingestion_batch", ["tenant_id"])
    op.create_index("ix_ingestion_batch_data_source_id", "ingestion_batch", ["data_source_id"])

    op.create_table(
        "ingestion_staged_record",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("system_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("batch_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("row_number", sa.Integer(), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_ingestion_staged_record"),
        sa.ForeignKeyConstraint(
            ["batch_id"],
            ["ingestion_batch.id"],
            name="fk_ingestion_staged_record_batch_id_ingestion_batch",
        ),
        sa.UniqueConstraint(
            "batch_id", "row_number", name="uq_ingestion_staged_record_batch_row"
        ),
    )
    op.create_index(
        "ix_ingestion_staged_record_tenant_id", "ingestion_staged_record", ["tenant_id"]
    )
    op.create_index(
        "ix_ingestion_staged_record_batch_id", "ingestion_staged_record", ["batch_id"]
    )

    # --- Tenant isolation: RLS with explicit USING + WITH CHECK (BR-17) ---
    for table in TENANT_SCOPED_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY tenant_isolation_{table} ON {table} "
            f"USING (tenant_id::text = current_setting('app.current_tenant', true)) "
            f"WITH CHECK (tenant_id::text = current_setting('app.current_tenant', true))"
        )

    # --- Append-only on the IA staged-record table only (BR-12 / AUD-01), reusing the 0001 fn ---
    for table in APPEND_ONLY_TABLES:
        op.execute(
            f"CREATE TRIGGER {table}_append_only BEFORE UPDATE OR DELETE ON {table} "
            f"FOR EACH ROW EXECUTE FUNCTION irp_prevent_mutation()"
        )


def downgrade() -> None:
    for table in APPEND_ONLY_TABLES:
        op.execute(f"DROP TRIGGER IF EXISTS {table}_append_only ON {table}")
    for table in TENANT_SCOPED_TABLES:
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation_{table} ON {table}")

    op.drop_table("ingestion_staged_record")
    op.drop_table("ingestion_batch")
