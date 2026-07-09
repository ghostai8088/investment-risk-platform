"""P3-7: active_risk_result (ENT-027 realized, IA — the sixth governed risk number).

``active_risk_result`` is a tenant-scoped PROPRIETARY table under the **SYMMETRIC** tenant-isolation
RLS loop (``USING == WITH CHECK == own-tenant``) — the SAME pattern as 0009..0029. NOT hybrid, no
SYSTEM_TENANT (the 0008 hybrid loop + the closed 5-table hybrid set are unchanged). **TRULY
IMMUTABLE / append-only** (the ``var_result`` precedent): in this migration's local
``APPEND_ONLY_TABLES`` -> the ``irp_prevent_mutation`` P0001 trigger (REUSING the 0001 function),
paired with the ORM before_update/before_delete guard. Run-bound + snapshot-gated + model-bound
(NOT-NULL FKs to ``calculation_run`` + ``dataset_snapshot`` + ``model_version``) PLUS the hard-FK
PROVENANCE columns ``factor_exposure_run_id``/``covariance_run_id`` -> ``calculation_run.run_id``
and ``benchmark_id`` -> ``benchmark.id`` (which upstream governed runs + which captured benchmark
fed it). ONE summary row per COMPLETED run (UNIQUE ``(calculation_run_id, metric_type)``;
``TRACKING_ERROR`` v1, extend by value). ``te_value`` Numeric(20,12) (a daily active-return
volatility FRACTION); ``portfolio_value`` Numeric(28,6) (the weight denominator, evidence).

No schema change for ``COMPONENT_KIND_BENCHMARK`` / ``PURPOSE_ACTIVE_RISK_INPUT`` (unconstrained
strings — app constants; the ``dataset_snapshot``/``component`` tables are unchanged). No new audit
code (the run reuses ``CALC.RUN_*``); NO new permission (``risk.view``/``risk.run`` REUSED — OD-P3-7-A;
``entitlement/bootstrap.py`` unchanged). ``PreciseDecimal`` renders ``NUMERIC(p,s)`` on PG — no DDL
surprise; ``alembic check`` stays a no-op.

Revision ID: 0030_active_risk
Revises: 0029_benchmark_series
Create Date: 2026-07-09
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0030_active_risk"
down_revision: str | None = "0029_benchmark_series"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: Symmetric tenant-isolation (NOT hybrid).
TENANT_SCOPED_TABLES = ("active_risk_result",)
#: Truly immutable append-only (the irp_prevent_mutation P0001 trigger, reusing the 0001 function).
APPEND_ONLY_TABLES = ("active_risk_result",)


def upgrade() -> None:
    op.create_table(
        "active_risk_result",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("system_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("calculation_run_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("input_snapshot_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("model_version_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("factor_exposure_run_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("covariance_run_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("benchmark_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("benchmark_effective_date", sa.Date(), nullable=False),
        sa.Column("metric_type", sa.String(length=30), nullable=False),
        sa.Column("base_currency", sa.String(length=3), nullable=False),
        sa.Column("te_value", sa.Numeric(20, 12), nullable=False),
        sa.Column("portfolio_value", sa.Numeric(28, 6), nullable=False),
        sa.Column("n_factors", sa.Integer(), nullable=False),
        sa.Column("n_constituents", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_active_risk_result"),
        sa.ForeignKeyConstraint(
            ["calculation_run_id"],
            ["calculation_run.run_id"],
            name="fk_active_risk_result_calculation_run_id_calculation_run",
        ),
        sa.ForeignKeyConstraint(
            ["input_snapshot_id"],
            ["dataset_snapshot.id"],
            name="fk_active_risk_result_input_snapshot_id_dataset_snapshot",
        ),
        sa.ForeignKeyConstraint(
            ["model_version_id"],
            ["model_version.id"],
            name="fk_active_risk_result_model_version_id_model_version",
        ),
        sa.ForeignKeyConstraint(
            ["factor_exposure_run_id"],
            ["calculation_run.run_id"],
            name="fk_active_risk_result_factor_exposure_run_id_calculation_run",
        ),
        sa.ForeignKeyConstraint(
            ["covariance_run_id"],
            ["calculation_run.run_id"],
            name="fk_active_risk_result_covariance_run_id_calculation_run",
        ),
        sa.ForeignKeyConstraint(
            ["benchmark_id"],
            ["benchmark.id"],
            name="fk_active_risk_result_benchmark_id_benchmark",
        ),
        sa.UniqueConstraint(
            "calculation_run_id", "metric_type", name="uq_active_risk_result_run_grain"
        ),
    )
    op.create_index("ix_active_risk_result_tenant_id", "active_risk_result", ["tenant_id"])
    op.create_index(
        "ix_active_risk_result_calculation_run_id", "active_risk_result", ["calculation_run_id"]
    )
    op.create_index(
        "ix_active_risk_result_input_snapshot_id", "active_risk_result", ["input_snapshot_id"]
    )
    op.create_index(
        "ix_active_risk_result_model_version_id", "active_risk_result", ["model_version_id"]
    )
    op.create_index(
        "ix_active_risk_result_factor_exposure_run_id",
        "active_risk_result",
        ["factor_exposure_run_id"],
    )
    op.create_index(
        "ix_active_risk_result_covariance_run_id", "active_risk_result", ["covariance_run_id"]
    )
    op.create_index("ix_active_risk_result_benchmark_id", "active_risk_result", ["benchmark_id"])

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
    op.drop_table("active_risk_result")
