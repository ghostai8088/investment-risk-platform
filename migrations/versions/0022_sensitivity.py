"""P3-1: sensitivity_result (ENT-028, IA — the first reproducible governed risk number).

``sensitivity_result`` is a tenant-scoped PROPRIETARY table under the **SYMMETRIC** tenant-isolation
RLS loop (``USING == WITH CHECK == own-tenant``) — the SAME pattern as 0009..0018. NOT hybrid, no
SYSTEM_TENANT (the 0008 hybrid loop + ``HYBRID_TABLES`` are untouched; the closed 5-table hybrid set
is unchanged). **TRULY IMMUTABLE / append-only** (the ``exposure_aggregate`` precedent): in this
migration's local ``APPEND_ONLY_TABLES`` -> the ``irp_prevent_mutation`` P0001 trigger (REUSING the
0001 function), paired with the ORM before_update/before_delete guard. Run-bound + snapshot-gated +
model-bound (NOT-NULL FKs to ``calculation_run`` + ``dataset_snapshot`` + ``model_version`` — the
AD-014 + CTRL-003 invariant at the DB).

No schema change for ``COMPONENT_KIND_CURVE`` (``dataset_snapshot_component.component_kind`` is an
unconstrained ``String(50)`` — the new kind is an app-constant). No new audit code (the run reuses
``CALC.RUN_*``); the ``risk.view``/``risk.run`` perms are wired in the entitlement bootstrap and
seeded by 0002 on a fresh migrate.

Revision ID: 0022_sensitivity
Revises: 0021_benchmark
Create Date: 2026-06-30
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0022_sensitivity"
down_revision: str | None = "0021_benchmark"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: Symmetric tenant-isolation (NOT hybrid).
TENANT_SCOPED_TABLES = ("sensitivity_result",)
#: Truly immutable append-only (the irp_prevent_mutation P0001 trigger, reusing the 0001 function).
APPEND_ONLY_TABLES = ("sensitivity_result",)


def upgrade() -> None:
    op.create_table(
        "sensitivity_result",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("system_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("calculation_run_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("input_snapshot_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("model_version_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("curve_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("curve_type", sa.String(length=30), nullable=False),
        sa.Column("currency_code", sa.String(length=3), nullable=False),
        sa.Column("reference_key", sa.String(length=150), nullable=False),
        sa.Column("value_type", sa.String(length=30), nullable=False),
        sa.Column("tenor_days", sa.Integer(), nullable=False),
        sa.Column("tenor_label", sa.String(length=10), nullable=False),
        sa.Column("sensitivity_type", sa.String(length=30), nullable=False),
        sa.Column("sensitivity_value", sa.Numeric(28, 12), nullable=False),
        sa.Column("bump_bps", sa.Numeric(10, 4), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_sensitivity_result"),
        sa.ForeignKeyConstraint(
            ["calculation_run_id"],
            ["calculation_run.run_id"],
            name="fk_sensitivity_result_calculation_run_id_calculation_run",
        ),
        sa.ForeignKeyConstraint(
            ["input_snapshot_id"],
            ["dataset_snapshot.id"],
            name="fk_sensitivity_result_input_snapshot_id_dataset_snapshot",
        ),
        sa.ForeignKeyConstraint(
            ["model_version_id"],
            ["model_version.id"],
            name="fk_sensitivity_result_model_version_id_model_version",
        ),
        sa.UniqueConstraint(
            "calculation_run_id",
            "curve_id",
            "value_type",
            "tenor_days",
            "sensitivity_type",
            name="uq_sensitivity_result_run_grain",
        ),
    )
    op.create_index("ix_sensitivity_result_tenant_id", "sensitivity_result", ["tenant_id"])
    op.create_index(
        "ix_sensitivity_result_calculation_run_id", "sensitivity_result", ["calculation_run_id"]
    )
    op.create_index(
        "ix_sensitivity_result_input_snapshot_id", "sensitivity_result", ["input_snapshot_id"]
    )
    op.create_index(
        "ix_sensitivity_result_model_version_id", "sensitivity_result", ["model_version_id"]
    )

    # --- Tenant isolation: SYMMETRIC RLS (USING == WITH CHECK == own-tenant); NOT hybrid (BR-17).
    for table in TENANT_SCOPED_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY tenant_isolation_{table} ON {table} "
            f"USING (tenant_id::text = current_setting('app.current_tenant', true)) "
            f"WITH CHECK (tenant_id::text = current_setting('app.current_tenant', true))"
        )

    # --- Append-only: truly immutable IA table (BR-12/BR-18 / AUD-01), reuse the 0001 function.
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
    op.drop_table("sensitivity_result")
