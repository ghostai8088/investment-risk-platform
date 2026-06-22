"""P1A-3: data quality skeleton (REQ-DQR-001 / DEP-DQF).

Adds two tenant-scoped tables — ``data_quality_rule`` (ENT-039, EV) and ``data_quality_result``
(ENT-039, IA) — with the same PostgreSQL enforcement the foundation/lineage/model tables use:
- Row-level security (tenant isolation, BR-17) with an **explicit ``WITH CHECK``** on both.
- The append-only trigger (BR-12 / AUD-01) on the IA result table, reusing ``irp_prevent_mutation``
  from migration 0001. ``data_quality_rule`` is EV (mutable rule config) and is not append-only.

``data_quality_result.rule_id`` and ``data_source_id`` are real intra-context FKs (declared with
``fk_`` names matching the ORM NAMING_CONVENTION so ``alembic check`` is drift-clean);
``ingestion_batch_id`` is a nullable NO-FK placeholder reserved for P1A-4. The ``DATA.VALIDATE``
audit code is reused for runs; ``DATA.DQ_RULE_DEFINE``/``DATA.DQ_RULE_UPDATE`` are new (taxonomy doc).
No new permission is created (``dq.rule.manage``/``dq.result.view`` already exist).

Revision ID: 0006_data_quality_skeleton
Revises: 0005_model_registry_skeleton
Create Date: 2026-06-22
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006_data_quality_skeleton"
down_revision: str | None = "0005_model_registry_skeleton"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TENANT_SCOPED_TABLES = ("data_quality_rule", "data_quality_result")
APPEND_ONLY_TABLES = ("data_quality_result",)


def upgrade() -> None:
    op.create_table(
        "data_quality_rule",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(length=255), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by", sa.String(length=255), nullable=True),
        sa.Column("record_version", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(length=150), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("rule_type", sa.String(length=50), nullable=False),
        sa.Column("params", postgresql.JSONB(), nullable=False),
        sa.Column("target_entity_type", sa.String(length=100), nullable=True),
        sa.Column("severity", sa.String(length=20), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("approval_status", sa.String(length=20), nullable=True),
        sa.Column("approval_ref", sa.String(length=255), nullable=True),
        sa.Column("made_by", sa.String(length=255), nullable=True),
        sa.Column("checked_by", sa.String(length=255), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_data_quality_rule"),
        sa.UniqueConstraint("tenant_id", "code", name="uq_data_quality_rule_tenant_code"),
    )
    op.create_index("ix_data_quality_rule_tenant_id", "data_quality_rule", ["tenant_id"])

    op.create_table(
        "data_quality_result",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("system_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("rule_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("target_entity_type", sa.String(length=100), nullable=True),
        sa.Column("target_entity_id", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("passed", sa.Boolean(), nullable=False),
        sa.Column("outcome", sa.String(length=20), nullable=False),
        sa.Column("observed_value", sa.String(length=500), nullable=True),
        sa.Column("detail", sa.String(length=2000), nullable=True),
        sa.Column("evaluated_count", sa.Integer(), nullable=True),
        sa.Column("failed_count", sa.Integer(), nullable=True),
        sa.Column("data_source_id", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("ingestion_batch_id", postgresql.UUID(as_uuid=False), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_data_quality_result"),
        sa.ForeignKeyConstraint(
            ["rule_id"],
            ["data_quality_rule.id"],
            name="fk_data_quality_result_rule_id_data_quality_rule",
        ),
        sa.ForeignKeyConstraint(
            ["data_source_id"],
            ["data_source.id"],
            name="fk_data_quality_result_data_source_id_data_source",
        ),
    )
    op.create_index("ix_data_quality_result_tenant_id", "data_quality_result", ["tenant_id"])
    op.create_index("ix_data_quality_result_rule_id", "data_quality_result", ["rule_id"])
    op.create_index(
        "ix_data_quality_result_data_source_id", "data_quality_result", ["data_source_id"]
    )

    # --- Tenant isolation: RLS with explicit USING + WITH CHECK (BR-17 / OQ-P1A-3-SEC-1) ---
    for table in TENANT_SCOPED_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY tenant_isolation_{table} ON {table} "
            f"USING (tenant_id::text = current_setting('app.current_tenant', true)) "
            f"WITH CHECK (tenant_id::text = current_setting('app.current_tenant', true))"
        )

    # --- Append-only on the IA result table (BR-12 / AUD-01), reusing the 0001 trigger function ---
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

    op.drop_table("data_quality_result")
    op.drop_table("data_quality_rule")
