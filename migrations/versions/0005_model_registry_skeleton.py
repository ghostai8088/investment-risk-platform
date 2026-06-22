"""P1A-2: model registry skeleton (REQ-MDG-001 / DEP-MREG).

Adds four tenant-scoped tables — ``model`` (ENT-035, EV), ``model_version`` (ENT-035, IA),
``model_assumption`` + ``model_limitation`` (ENT-036, IA) — with the same PostgreSQL enforcement
the foundation/lineage tables use:
- Row-level security (tenant isolation, BR-17) with an **explicit ``WITH CHECK``** on all four.
- The append-only trigger (BR-12 / AUD-01) on the three IA tables, reusing ``irp_prevent_mutation``
  from migration 0001. ``model`` is EV (mutable governance head) and is not append-only.

Intra-context FKs (model_version->model, assumption/limitation->model_version) are declared with
``fk_`` names matching the ORM NAMING_CONVENTION so ``alembic check`` is drift-clean. The
``model.inventory.register``/``view`` permissions and ``MODEL.REGISTER``/``MODEL.VERSION`` audit
codes already exist — none are created here.

Revision ID: 0005_model_registry_skeleton
Revises: 0004_lineage_skeleton
Create Date: 2026-06-21
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005_model_registry_skeleton"
down_revision: str | None = "0004_lineage_skeleton"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TENANT_SCOPED_TABLES = ("model", "model_version", "model_assumption", "model_limitation")
APPEND_ONLY_TABLES = ("model_version", "model_assumption", "model_limitation")


def upgrade() -> None:
    op.create_table(
        "model",
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
        sa.Column("model_type", sa.String(length=50), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("owner", sa.String(length=255), nullable=True),
        sa.Column("developer", sa.String(length=255), nullable=True),
        sa.Column("tier", sa.String(length=20), nullable=True),
        sa.Column("validation_status", sa.String(length=30), nullable=True),
        sa.Column("approved_use", sa.String(length=500), nullable=True),
        sa.Column("restricted_use", sa.Boolean(), nullable=True),
        sa.Column("restriction_reason", sa.String(length=500), nullable=True),
        sa.Column("approval_status", sa.String(length=20), nullable=True),
        sa.Column("approval_ref", sa.String(length=255), nullable=True),
        sa.Column("made_by", sa.String(length=255), nullable=True),
        sa.Column("checked_by", sa.String(length=255), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_model"),
        sa.UniqueConstraint("tenant_id", "code", name="uq_model_tenant_code"),
    )
    op.create_index("ix_model_tenant_id", "model", ["tenant_id"])

    op.create_table(
        "model_version",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("system_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("model_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("version_label", sa.String(length=50), nullable=False),
        sa.Column("methodology_ref", sa.String(length=500), nullable=True),
        sa.Column("code_version", sa.String(length=100), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_model_version"),
        sa.ForeignKeyConstraint(
            ["model_id"], ["model.id"], name="fk_model_version_model_id_model"
        ),
        sa.UniqueConstraint(
            "tenant_id", "model_id", "version_label", name="uq_model_version_tenant_model_label"
        ),
    )
    op.create_index("ix_model_version_tenant_id", "model_version", ["tenant_id"])
    op.create_index("ix_model_version_model_id", "model_version", ["model_id"])

    op.create_table(
        "model_assumption",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("system_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("model_version_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("assumption_text", sa.String(length=2000), nullable=False),
        sa.Column("category", sa.String(length=50), nullable=True),
        sa.Column("authored_by", sa.String(length=255), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_model_assumption"),
        sa.ForeignKeyConstraint(
            ["model_version_id"],
            ["model_version.id"],
            name="fk_model_assumption_model_version_id_model_version",
        ),
    )
    op.create_index("ix_model_assumption_tenant_id", "model_assumption", ["tenant_id"])
    op.create_index(
        "ix_model_assumption_model_version_id", "model_assumption", ["model_version_id"]
    )

    op.create_table(
        "model_limitation",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("system_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("model_version_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("limitation_text", sa.String(length=2000), nullable=False),
        sa.Column("severity", sa.String(length=20), nullable=True),
        sa.Column("authored_by", sa.String(length=255), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_model_limitation"),
        sa.ForeignKeyConstraint(
            ["model_version_id"],
            ["model_version.id"],
            name="fk_model_limitation_model_version_id_model_version",
        ),
    )
    op.create_index("ix_model_limitation_tenant_id", "model_limitation", ["tenant_id"])
    op.create_index(
        "ix_model_limitation_model_version_id", "model_limitation", ["model_version_id"]
    )

    # --- Tenant isolation: RLS with explicit USING + WITH CHECK (BR-17 / OQ-P1A-2-SEC-1) ---
    for table in TENANT_SCOPED_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY tenant_isolation_{table} ON {table} "
            f"USING (tenant_id::text = current_setting('app.current_tenant', true)) "
            f"WITH CHECK (tenant_id::text = current_setting('app.current_tenant', true))"
        )

    # --- Append-only on the IA tables (BR-12 / AUD-01), reusing the 0001 trigger function ---
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

    op.drop_table("model_limitation")
    op.drop_table("model_assumption")
    op.drop_table("model_version")
    op.drop_table("model")
