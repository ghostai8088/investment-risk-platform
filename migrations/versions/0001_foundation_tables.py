"""Foundation slice: audit, entitlement, and calculation-run tables.

Adds the cross-cutting foundation schema plus PostgreSQL-level enforcement:
- Row-level security (tenant isolation, BR-17 / AD-008) on tenant-scoped tables.
- Append-only triggers (BR-12 / AUD-01) on the audit tables.

This migration targets PostgreSQL (AD-004) and is validated by the CI ``migration`` job.

Revision ID: 0001_foundation
Revises:
Create Date: 2026-06-17
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_foundation"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TENANT_SCOPED_TABLES = ("app_user", "role", "user_role", "audit_event", "audit_checkpoint", "calculation_run")
APPEND_ONLY_TABLES = ("audit_event", "audit_checkpoint")


def upgrade() -> None:
    op.create_table(
        "permission",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("code", sa.String(length=150), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(length=255), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by", sa.String(length=255), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_permission"),
        sa.UniqueConstraint("code", name="uq_permission_code"),
    )

    op.create_table(
        "app_user",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("external_subject", sa.String(length=255), nullable=True),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(length=255), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by", sa.String(length=255), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_app_user"),
        sa.UniqueConstraint("tenant_id", "external_subject", name="uq_app_user_tenant_id"),
    )
    op.create_index("ix_app_user_tenant_id", "app_user", ["tenant_id"])

    op.create_table(
        "role",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("code", sa.String(length=100), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(length=255), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by", sa.String(length=255), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_role"),
        sa.UniqueConstraint("tenant_id", "code", name="uq_role_tenant_id"),
    )
    op.create_index("ix_role_tenant_id", "role", ["tenant_id"])

    op.create_table(
        "role_permission",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("role_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("permission_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_role_permission"),
        sa.ForeignKeyConstraint(["role_id"], ["role.id"], name="fk_role_permission_role_id_role"),
        sa.ForeignKeyConstraint(
            ["permission_id"], ["permission.id"], name="fk_role_permission_permission_id_permission"
        ),
        sa.UniqueConstraint("role_id", "permission_id", name="uq_role_permission_role_id"),
    )
    op.create_index("ix_role_permission_role_id", "role_permission", ["role_id"])
    op.create_index("ix_role_permission_permission_id", "role_permission", ["permission_id"])

    op.create_table(
        "user_role",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("role_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_to", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_user_role"),
        sa.ForeignKeyConstraint(["user_id"], ["app_user.id"], name="fk_user_role_user_id_app_user"),
        sa.ForeignKeyConstraint(["role_id"], ["role.id"], name="fk_user_role_role_id_role"),
    )
    op.create_index("ix_user_role_tenant_id", "user_role", ["tenant_id"])
    op.create_index("ix_user_role_user_id", "user_role", ["user_id"])
    op.create_index("ix_user_role_role_id", "user_role", ["role_id"])

    op.create_table(
        "audit_event",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("system_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("chain_id", sa.String(length=64), nullable=False),
        sa.Column("sequence_no", sa.BigInteger(), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("event_time", sa.String(length=40), nullable=False),
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column("actor_type", sa.String(length=20), nullable=False),
        sa.Column("actor_id", sa.String(length=255), nullable=False),
        sa.Column("on_behalf_of", sa.String(length=255), nullable=True),
        sa.Column("source_module", sa.String(length=100), nullable=False),
        sa.Column("entity_type", sa.String(length=100), nullable=True),
        sa.Column("entity_id", sa.String(length=255), nullable=True),
        sa.Column("action", sa.String(length=100), nullable=False),
        sa.Column("before_value", postgresql.JSONB(), nullable=True),
        sa.Column("after_value", postgresql.JSONB(), nullable=True),
        sa.Column("justification", sa.String(length=2000), nullable=True),
        sa.Column("approval_ref", sa.String(length=255), nullable=True),
        sa.Column("correlation_id", sa.String(length=255), nullable=True),
        sa.Column("outcome", sa.String(length=20), nullable=False),
        sa.Column("severity", sa.String(length=20), nullable=False),
        sa.Column("data_classification", sa.String(length=10), nullable=False),
        sa.Column("agent_model", sa.String(length=100), nullable=True),
        sa.Column("agent_model_version", sa.String(length=100), nullable=True),
        sa.Column("previous_event_hash", sa.String(length=64), nullable=False),
        sa.Column("event_payload_hash", sa.String(length=64), nullable=False),
        sa.Column("event_hash", sa.String(length=64), nullable=False),
        sa.Column("hash_algorithm", sa.String(length=20), nullable=False),
        sa.Column("hash_version", sa.String(length=10), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_audit_event"),
        sa.UniqueConstraint("chain_id", "sequence_no", name="uq_audit_event_chain_id"),
    )
    op.create_index("ix_audit_event_chain_id", "audit_event", ["chain_id"])
    op.create_index("ix_audit_event_tenant_id", "audit_event", ["tenant_id"])

    op.create_table(
        "audit_checkpoint",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("system_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("chain_id", sa.String(length=64), nullable=False),
        sa.Column("sequence_no", sa.BigInteger(), nullable=False),
        sa.Column("last_event_hash", sa.String(length=64), nullable=False),
        sa.Column("signature", sa.String(length=512), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_audit_checkpoint"),
    )
    op.create_index("ix_audit_checkpoint_tenant_id", "audit_checkpoint", ["tenant_id"])
    op.create_index("ix_audit_checkpoint_chain_id", "audit_checkpoint", ["chain_id"])

    op.create_table(
        "calculation_run",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("system_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("run_type", sa.String(length=100), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("initiated_by", sa.String(length=255), nullable=False),
        sa.Column("input_snapshot_id", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("model_version_id", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("assumption_set_id", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("random_seed", sa.BigInteger(), nullable=True),
        sa.Column("code_version", sa.String(length=100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_calculation_run"),
        sa.UniqueConstraint("run_id", name="uq_calculation_run_run_id"),
    )
    op.create_index("ix_calculation_run_tenant_id", "calculation_run", ["tenant_id"])

    # --- Tenant isolation: row-level security (BR-17 / AD-008) ---
    for table in TENANT_SCOPED_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY tenant_isolation_{table} ON {table} "
            f"USING (tenant_id::text = current_setting('app.current_tenant', true))"
        )

    # --- Append-only audit tables (BR-12 / AUD-01) ---
    op.execute(
        "CREATE OR REPLACE FUNCTION irp_prevent_mutation() RETURNS trigger AS $$ "
        "BEGIN RAISE EXCEPTION 'append-only table is immutable (AUD-01)'; END; "
        "$$ LANGUAGE plpgsql"
    )
    for table in APPEND_ONLY_TABLES:
        op.execute(
            f"CREATE TRIGGER {table}_append_only BEFORE UPDATE OR DELETE ON {table} "
            f"FOR EACH ROW EXECUTE FUNCTION irp_prevent_mutation()"
        )


def downgrade() -> None:
    for table in APPEND_ONLY_TABLES:
        op.execute(f"DROP TRIGGER IF EXISTS {table}_append_only ON {table}")
    op.execute("DROP FUNCTION IF EXISTS irp_prevent_mutation()")
    for table in TENANT_SCOPED_TABLES:
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation_{table} ON {table}")

    op.drop_table("calculation_run")
    op.drop_table("audit_checkpoint")
    op.drop_table("audit_event")
    op.drop_table("user_role")
    op.drop_table("role_permission")
    op.drop_table("role")
    op.drop_table("app_user")
    op.drop_table("permission")
