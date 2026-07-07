"""P3-5: var_result (ENT-027 realized, IA — the fourth governed risk number).

``var_result`` is a tenant-scoped PROPRIETARY table under the **SYMMETRIC** tenant-isolation RLS
loop (``USING == WITH CHECK == own-tenant``) — the SAME pattern as 0009..0025. NOT hybrid, no
SYSTEM_TENANT (the 0008 hybrid loop + ``HYBRID_TABLES`` are untouched; the closed 5-table hybrid
set is unchanged). **TRULY IMMUTABLE / append-only** (the ``covariance_result`` precedent): in
this migration's local ``APPEND_ONLY_TABLES`` -> the ``irp_prevent_mutation`` P0001 trigger
(REUSING the 0001 function), paired with the ORM before_update/before_delete guard. Run-bound +
snapshot-gated + model-bound (NOT-NULL FKs to ``calculation_run`` + ``dataset_snapshot`` +
``model_version``) PLUS the two hard-FK PROVENANCE columns ``exposure_run_id``/
``covariance_run_id`` -> ``calculation_run.run_id`` (the first derived-of-derived number: which
upstream governed runs fed it, queryable without parsing the snapshot). ONE summary row per
COMPLETED run (UNIQUE ``(calculation_run_id, metric_type)``; ``VAR_PARAMETRIC`` v1,
``ES_PARAMETRIC`` reserved by value).

No schema change for ``COMPONENT_KIND_FACTOR_EXPOSURE`` / ``COMPONENT_KIND_COVARIANCE`` /
``PURPOSE_VAR_INPUT`` (unconstrained strings — app constants). No new audit code (the run reuses
``CALC.RUN_*``); NO new permission (``risk.view``/``risk.run`` are REUSED — OD-P3-5-K;
``entitlement/bootstrap.py`` unchanged).

Revision ID: 0026_var
Revises: 0025_covariance
Create Date: 2026-07-07
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0026_var"
down_revision: str | None = "0025_covariance"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: Symmetric tenant-isolation (NOT hybrid).
TENANT_SCOPED_TABLES = ("var_result",)
#: Truly immutable append-only (the irp_prevent_mutation P0001 trigger, reusing the 0001 function).
APPEND_ONLY_TABLES = ("var_result",)


def upgrade() -> None:
    op.create_table(
        "var_result",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("system_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("calculation_run_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("input_snapshot_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("model_version_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("exposure_run_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("covariance_run_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("metric_type", sa.String(length=30), nullable=False),
        sa.Column("base_currency", sa.String(length=3), nullable=False),
        sa.Column("confidence_level", sa.Numeric(6, 4), nullable=False),
        sa.Column("horizon_days", sa.Integer(), nullable=False),
        sa.Column("z_score", sa.Numeric(20, 12), nullable=False),
        sa.Column("sigma", sa.Numeric(28, 6), nullable=False),
        sa.Column("var_value", sa.Numeric(28, 6), nullable=False),
        sa.Column("n_factors", sa.Integer(), nullable=False),
        sa.Column("n_observations", sa.Integer(), nullable=False),
        sa.Column("window_start", sa.Date(), nullable=False),
        sa.Column("window_end", sa.Date(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_var_result"),
        sa.ForeignKeyConstraint(
            ["calculation_run_id"],
            ["calculation_run.run_id"],
            name="fk_var_result_calculation_run_id_calculation_run",
        ),
        sa.ForeignKeyConstraint(
            ["input_snapshot_id"],
            ["dataset_snapshot.id"],
            name="fk_var_result_input_snapshot_id_dataset_snapshot",
        ),
        sa.ForeignKeyConstraint(
            ["model_version_id"],
            ["model_version.id"],
            name="fk_var_result_model_version_id_model_version",
        ),
        sa.ForeignKeyConstraint(
            ["exposure_run_id"],
            ["calculation_run.run_id"],
            name="fk_var_result_exposure_run_id_calculation_run",
        ),
        sa.ForeignKeyConstraint(
            ["covariance_run_id"],
            ["calculation_run.run_id"],
            name="fk_var_result_covariance_run_id_calculation_run",
        ),
        sa.UniqueConstraint("calculation_run_id", "metric_type", name="uq_var_result_run_grain"),
    )
    op.create_index("ix_var_result_tenant_id", "var_result", ["tenant_id"])
    op.create_index("ix_var_result_calculation_run_id", "var_result", ["calculation_run_id"])
    op.create_index("ix_var_result_input_snapshot_id", "var_result", ["input_snapshot_id"])
    op.create_index("ix_var_result_model_version_id", "var_result", ["model_version_id"])
    op.create_index("ix_var_result_exposure_run_id", "var_result", ["exposure_run_id"])
    op.create_index("ix_var_result_covariance_run_id", "var_result", ["covariance_run_id"])

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
    op.drop_table("var_result")
