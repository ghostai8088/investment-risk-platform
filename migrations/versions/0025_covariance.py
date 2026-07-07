"""P3-4: covariance_result (ENT-051, IA — the third governed risk number).

``covariance_result`` is a tenant-scoped PROPRIETARY table under the **SYMMETRIC**
tenant-isolation RLS loop (``USING == WITH CHECK == own-tenant``) — the SAME pattern as
0009..0024. NOT hybrid, no SYSTEM_TENANT (the 0008 hybrid loop + ``HYBRID_TABLES`` are untouched;
the closed 5-table hybrid set is unchanged). **TRULY IMMUTABLE / append-only** (the
``sensitivity_result``/``factor_exposure_result`` precedent): in this migration's local
``APPEND_ONLY_TABLES`` -> the ``irp_prevent_mutation`` P0001 trigger (REUSING the 0001 function),
paired with the ORM before_update/before_delete guard. Run-bound + snapshot-gated + model-bound
(NOT-NULL FKs to ``calculation_run`` + ``dataset_snapshot`` + ``model_version`` — the AD-014 +
CTRL-003 invariant at the DB). One row per canonical unordered factor pair INCLUDING the
diagonal; the canonical ordering ``factor_id_1 <= factor_id_2`` is service-enforced + tested (NO
CHECK constraint — the genericity rule); ``factor_id_*`` are deliberately NOT hard FKs (the
pinned snapshot components are authoritative — the ``factor_exposure_result.factor_id``
precedent).

No schema change for ``COMPONENT_KIND_FACTOR_RETURN`` / ``PURPOSE_COVARIANCE_INPUT``
(unconstrained strings — app constants). No new audit code (the run reuses ``CALC.RUN_*``); NO
new permission (``risk.view``/``risk.run`` are REUSED — OD-P3-4-M; ``entitlement/bootstrap.py``
unchanged).

Revision ID: 0025_covariance
Revises: 0024_factor_exposure
Create Date: 2026-07-07
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0025_covariance"
down_revision: str | None = "0024_factor_exposure"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: Symmetric tenant-isolation (NOT hybrid).
TENANT_SCOPED_TABLES = ("covariance_result",)
#: Truly immutable append-only (the irp_prevent_mutation P0001 trigger, reusing the 0001 function).
APPEND_ONLY_TABLES = ("covariance_result",)


def upgrade() -> None:
    op.create_table(
        "covariance_result",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("system_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("calculation_run_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("input_snapshot_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("model_version_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("factor_id_1", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("factor_id_2", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("factor_code_1", sa.String(length=150), nullable=False),
        sa.Column("factor_code_2", sa.String(length=150), nullable=False),
        sa.Column("statistic_type", sa.String(length=30), nullable=False),
        sa.Column("return_type", sa.String(length=30), nullable=False),
        sa.Column("frequency", sa.String(length=20), nullable=False),
        sa.Column("n_observations", sa.Integer(), nullable=False),
        sa.Column("window_start", sa.Date(), nullable=False),
        sa.Column("window_end", sa.Date(), nullable=False),
        sa.Column("covariance_value", sa.Numeric(38, 20), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_covariance_result"),
        sa.ForeignKeyConstraint(
            ["calculation_run_id"],
            ["calculation_run.run_id"],
            name="fk_covariance_result_calculation_run_id_calculation_run",
        ),
        sa.ForeignKeyConstraint(
            ["input_snapshot_id"],
            ["dataset_snapshot.id"],
            name="fk_covariance_result_input_snapshot_id_dataset_snapshot",
        ),
        sa.ForeignKeyConstraint(
            ["model_version_id"],
            ["model_version.id"],
            name="fk_covariance_result_model_version_id_model_version",
        ),
        sa.UniqueConstraint(
            "calculation_run_id",
            "factor_id_1",
            "factor_id_2",
            name="uq_covariance_result_run_grain",
        ),
    )
    op.create_index("ix_covariance_result_tenant_id", "covariance_result", ["tenant_id"])
    op.create_index(
        "ix_covariance_result_calculation_run_id", "covariance_result", ["calculation_run_id"]
    )
    op.create_index(
        "ix_covariance_result_input_snapshot_id", "covariance_result", ["input_snapshot_id"]
    )
    op.create_index(
        "ix_covariance_result_model_version_id", "covariance_result", ["model_version_id"]
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
    op.drop_table("covariance_result")
