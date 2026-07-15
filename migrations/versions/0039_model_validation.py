"""VW-1: model-validation workflow (ENT-037, SR 11-7 / P7).

Adds three tenant-scoped IA tables realizing the reserved ENT-037 ``model_validation`` — an
append-only SR 11-7 validation record at ``model_version`` grain, plus its
``model_validation_finding`` / ``model_validation_evidence`` children — with the same PostgreSQL
enforcement the registry tables use: symmetric FORCE row-level security (BR-17, explicit WITH
CHECK) and the append-only trigger (BR-12 / AUD-01, reusing ``irp_prevent_mutation`` from 0001).

Intra/inter-context FKs (validation->model_version, finding/evidence->model_validation,
evidence->calculation_run) are declared with names matching the ORM NAMING_CONVENTION so
``alembic check`` is drift-clean. No governed number, no new permission/audit code created here —
the ``model.validate`` permission (bootstrap) and the ``MODEL.VALIDATE`` audit code (reserved in
the taxonomy, activated caller-side) are outside the migration.

Every identifier this migration mints is <= 63 chars (asserted at import — the 0032/0033 lesson).

Revision ID: 0039_model_validation
Revises: 0038_var_residual_variance
Create Date: 2026-07-14
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0039_model_validation"
down_revision: str | None = "0038_var_residual_variance"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: Symmetric tenant-isolation (NOT hybrid) on all three.
TENANT_SCOPED_TABLES = (
    "model_validation",
    "model_validation_finding",
    "model_validation_evidence",
)
#: All three are truly immutable append-only (a re-validation is a NEW record).
APPEND_ONLY_TABLES = TENANT_SCOPED_TABLES

#: Every name this migration mints, checked at import time (the 0032/0033 lesson; MD-H1 sweep too).
_IDENTIFIERS = (
    "model_validation",
    "model_validation_finding",
    "model_validation_evidence",
    "pk_model_validation",
    "pk_model_validation_finding",
    "pk_model_validation_evidence",
    "fk_model_validation_model_version_id_model_version",
    "fk_model_validation_finding_validation_id_model_validation",
    "fk_model_validation_evidence_validation_id_model_validation",
    "fk_model_validation_evidence_run_id_calculation_run",
    "ix_model_validation_tenant_id",
    "ix_model_validation_latest",
    "ix_model_validation_finding_tenant_id",
    "ix_model_validation_finding_validation_id",
    "ix_model_validation_evidence_tenant_id",
    "ix_model_validation_evidence_validation_id",
    "ix_model_validation_evidence_run_id",
    "tenant_isolation_model_validation",
    "tenant_isolation_model_validation_finding",
    "tenant_isolation_model_validation_evidence",
    "model_validation_append_only",
    "model_validation_finding_append_only",
    "model_validation_evidence_append_only",
)
assert all(len(name) <= 63 for name in _IDENTIFIERS), [
    name for name in _IDENTIFIERS if len(name) > 63
]


def upgrade() -> None:
    op.create_table(
        "model_validation",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("system_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("model_version_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("validation_type", sa.String(length=20), nullable=False),
        sa.Column("outcome", sa.String(length=30), nullable=False),
        sa.Column("scope_summary", sa.String(length=2000), nullable=False),
        sa.Column("conditions", sa.String(length=2000), nullable=True),
        sa.Column("report_ref", sa.String(length=500), nullable=True),
        sa.Column("next_review_due", sa.Date(), nullable=True),
        sa.Column("validated_by", sa.String(length=255), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_model_validation"),
        sa.ForeignKeyConstraint(
            ["model_version_id"],
            ["model_version.id"],
            name="fk_model_validation_model_version_id_model_version",
        ),
    )
    op.create_index("ix_model_validation_tenant_id", "model_validation", ["tenant_id"])
    op.create_index(
        "ix_model_validation_latest",
        "model_validation",
        ["tenant_id", "model_version_id", "system_from"],
    )

    op.create_table(
        "model_validation_finding",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("system_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("validation_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("finding_text", sa.String(length=2000), nullable=False),
        sa.Column("severity", sa.String(length=20), nullable=True),
        sa.Column("authored_by", sa.String(length=255), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_model_validation_finding"),
        sa.ForeignKeyConstraint(
            ["validation_id"],
            ["model_validation.id"],
            name="fk_model_validation_finding_validation_id_model_validation",
        ),
    )
    op.create_index(
        "ix_model_validation_finding_tenant_id", "model_validation_finding", ["tenant_id"]
    )
    op.create_index(
        "ix_model_validation_finding_validation_id",
        "model_validation_finding",
        ["validation_id"],
    )

    op.create_table(
        "model_validation_evidence",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("system_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("validation_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("evidence_type", sa.String(length=30), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("reference", sa.String(length=500), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_model_validation_evidence"),
        sa.ForeignKeyConstraint(
            ["validation_id"],
            ["model_validation.id"],
            name="fk_model_validation_evidence_validation_id_model_validation",
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["calculation_run.run_id"],
            name="fk_model_validation_evidence_run_id_calculation_run",
        ),
    )
    op.create_index(
        "ix_model_validation_evidence_tenant_id", "model_validation_evidence", ["tenant_id"]
    )
    op.create_index(
        "ix_model_validation_evidence_validation_id",
        "model_validation_evidence",
        ["validation_id"],
    )
    op.create_index("ix_model_validation_evidence_run_id", "model_validation_evidence", ["run_id"])

    # --- Tenant isolation: RLS with explicit USING + WITH CHECK (BR-17) ---
    for table in TENANT_SCOPED_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY tenant_isolation_{table} ON {table} "
            f"USING (tenant_id::text = current_setting('app.current_tenant', true)) "
            f"WITH CHECK (tenant_id::text = current_setting('app.current_tenant', true))"
        )

    # --- Append-only on all three IA tables (BR-12 / AUD-01), reusing the 0001 trigger function ---
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

    op.drop_table("model_validation_evidence")
    op.drop_table("model_validation_finding")
    op.drop_table("model_validation")
