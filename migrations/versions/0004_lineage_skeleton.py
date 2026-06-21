"""P1A-1: data source & lineage skeleton (REQ-LIN-001 / DEP-LIN).

Adds two tenant-scoped tables — ``data_source`` (ENT-038, EV) and ``lineage_edge`` (ENT-042, IA)
— with the same PostgreSQL enforcement the foundation uses:
- Row-level security (tenant isolation, BR-17) with an **explicit ``WITH CHECK``** so cross-tenant
  writes are rejected, not merely hidden (plan §3.3 / OQ-P1A-1-SEC-1).
- The append-only trigger (BR-12 / AUD-01) on ``lineage_edge`` (IA), reusing ``irp_prevent_mutation``
  from migration 0001. ``data_source`` is EV (mutable) and is not append-only.

The new ``lineage.source.manage`` permission + grants are seeded by ``0002_entitlement_seed`` (which
materializes ``irp_shared.entitlement.bootstrap`` at upgrade time) — not here — keeping one catalog
source of truth.

Revision ID: 0004_lineage_skeleton
Revises: 0003_ops_role
Create Date: 2026-06-21
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004_lineage_skeleton"
down_revision: str | None = "0003_ops_role"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TENANT_SCOPED_TABLES = ("data_source", "lineage_edge")
APPEND_ONLY_TABLES = ("lineage_edge",)


def upgrade() -> None:
    op.create_table(
        "data_source",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(length=255), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by", sa.String(length=255), nullable=True),
        sa.Column("code", sa.String(length=150), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("source_type", sa.String(length=50), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("record_version", sa.Integer(), nullable=False),
        sa.Column("approval_status", sa.String(length=20), nullable=True),
        sa.Column("approval_ref", sa.String(length=255), nullable=True),
        sa.Column("made_by", sa.String(length=255), nullable=True),
        sa.Column("checked_by", sa.String(length=255), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_data_source"),
        sa.UniqueConstraint("tenant_id", "code", name="uq_data_source_tenant_code"),
    )
    op.create_index("ix_data_source_tenant_id", "data_source", ["tenant_id"])

    op.create_table(
        "lineage_edge",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("system_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_type", sa.String(length=50), nullable=False),
        sa.Column("source_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("target_entity_type", sa.String(length=100), nullable=False),
        sa.Column("target_entity_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("edge_kind", sa.String(length=50), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=False), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_lineage_edge"),
    )
    op.create_index("ix_lineage_edge_tenant_id", "lineage_edge", ["tenant_id"])

    # --- Tenant isolation: RLS with explicit USING + WITH CHECK (BR-17 / OQ-P1A-1-SEC-1) ---
    for table in TENANT_SCOPED_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY tenant_isolation_{table} ON {table} "
            f"USING (tenant_id::text = current_setting('app.current_tenant', true)) "
            f"WITH CHECK (tenant_id::text = current_setting('app.current_tenant', true))"
        )

    # --- Append-only on lineage_edge (IA; BR-12 / AUD-01), reusing the 0001 trigger function ---
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

    op.drop_table("lineage_edge")
    op.drop_table("data_source")
