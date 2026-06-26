"""P2-1: dataset_snapshot + dataset_snapshot_component (ENT-049/050, IA — the AD-014 reproducibility
primitive).

Two tenant-scoped PROPRIETARY tables under the **SYMMETRIC** tenant-isolation RLS loop
(``USING == WITH CHECK == own-tenant``) — the SAME pattern as 0009..0015. NOT hybrid, no
SYSTEM_TENANT (the 0008 hybrid loop + ``HYBRID_TABLES`` are untouched; the closed 5-table hybrid set
is unchanged). **TRULY IMMUTABLE / append-only** (the ``transaction`` precedent, NOT the
status-mutable ``calculation_run``/``ingestion_batch``): both tables are in this migration's local
``APPEND_ONLY_TABLES`` -> the ``irp_prevent_mutation`` P0001 trigger (REUSING the 0001 function; the
0001 module tuple is UNTOUCHED), paired with the ORM before_update/before_delete guard. No new audit
code (``SNAPSHOT.CREATE`` is a caller-side constant) and no new permission table (``snapshot.*``
perms are added in the entitlement bootstrap and seeded by 0002 on a fresh migrate).

Revision ID: 0016_dataset_snapshot
Revises: 0015_valuation
Create Date: 2026-06-26
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0016_dataset_snapshot"
down_revision: str | None = "0015_valuation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: Symmetric tenant-isolation (NOT hybrid) — both snapshot tables.
TENANT_SCOPED_TABLES = ("dataset_snapshot", "dataset_snapshot_component")
#: Truly immutable append-only (the irp_prevent_mutation P0001 trigger, reusing the 0001 function).
APPEND_ONLY_TABLES = ("dataset_snapshot", "dataset_snapshot_component")


def upgrade() -> None:
    op.create_table(
        "dataset_snapshot",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("system_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(length=255), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by", sa.String(length=255), nullable=True),
        sa.Column("label", sa.String(length=255), nullable=False),
        sa.Column("purpose", sa.String(length=50), nullable=False),
        sa.Column("as_of_valid_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("as_of_known_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("as_of_valuation_date", sa.Date(), nullable=False),
        sa.Column("binding_predicate_version", sa.String(length=50), nullable=False),
        sa.Column("component_count", sa.Integer(), nullable=False),
        sa.Column("manifest_hash", sa.String(length=64), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_dataset_snapshot"),
    )
    op.create_index("ix_dataset_snapshot_tenant_id", "dataset_snapshot", ["tenant_id"])

    op.create_table(
        "dataset_snapshot_component",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("system_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("snapshot_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("component_kind", sa.String(length=50), nullable=False),
        sa.Column("target_entity_type", sa.String(length=50), nullable=False),
        sa.Column("target_entity_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("pinned_valid_from", sa.DateTime(timezone=True), nullable=True),
        sa.Column("pinned_system_from", sa.DateTime(timezone=True), nullable=True),
        sa.Column("pinned_record_version", sa.Integer(), nullable=True),
        sa.Column("captured_content", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_dataset_snapshot_component"),
        sa.ForeignKeyConstraint(
            ["snapshot_id"],
            ["dataset_snapshot.id"],
            name="fk_dataset_snapshot_component_snapshot_id_dataset_snapshot",
        ),
        sa.UniqueConstraint(
            "snapshot_id",
            "component_kind",
            "target_entity_id",
            name="uq_dataset_snapshot_component_snapshot_kind_target",
        ),
    )
    op.create_index(
        "ix_dataset_snapshot_component_tenant_id", "dataset_snapshot_component", ["tenant_id"]
    )
    op.create_index(
        "ix_dataset_snapshot_component_snapshot_id", "dataset_snapshot_component", ["snapshot_id"]
    )

    # --- Tenant isolation: SYMMETRIC RLS (USING == WITH CHECK == own-tenant); NOT hybrid (BR-17)
    for table in TENANT_SCOPED_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY tenant_isolation_{table} ON {table} "
            f"USING (tenant_id::text = current_setting('app.current_tenant', true)) "
            f"WITH CHECK (tenant_id::text = current_setting('app.current_tenant', true))"
        )

    # --- Append-only: truly immutable IA tables (BR-12/BR-18 / AUD-01), reuse the 0001 function
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
    op.drop_table("dataset_snapshot_component")
    op.drop_table("dataset_snapshot")
