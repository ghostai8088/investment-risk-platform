"""P3-8: benchmark_relative_result (ENT-054 — the eighth governed number; ex-post benchmark-rel).

``benchmark_relative_result`` is a tenant-scoped PROPRIETARY table under the **SYMMETRIC**
tenant-isolation RLS loop (``USING == WITH CHECK == own-tenant``) — the SAME pattern as
0009..0031. NOT hybrid, no SYSTEM_TENANT (the 0008 hybrid loop + the closed 5-table hybrid set are
unchanged). **TRULY IMMUTABLE / append-only** (the ``portfolio_return_result`` precedent): in this
migration's local ``APPEND_ONLY_TABLES`` -> the ``irp_prevent_mutation`` P0001 trigger (REUSING the
0001 function), paired with the ORM before_update/before_delete guard. Run-bound + snapshot-gated
+ model-bound (NOT-NULL FKs to ``calculation_run`` + ``dataset_snapshot`` + ``model_version``) PLUS
the
hard-FK PROVENANCE columns ``portfolio_return_run_id`` -> ``calculation_run.run_id`` (the ONE
consumed PM-1 run), ``benchmark_id`` -> ``benchmark.id``, and ``portfolio_id`` -> ``portfolio.id``.

Grain ``(calculation_run_id, metric_type, period_start)``: ``n`` ``ACTIVE_RETURN`` sub-period rows +
``TRACKING_DIFFERENCE``/``TRACKING_ERROR``/``INFORMATION_RATIO`` summary rows (an ACTIVE_RETURN row
and a summary row can share ``period_start`` because ``metric_type`` differs). ``metric_value``
Numeric(20,12) is a return/TE/TD/IR FRACTION or RATIO; ``portfolio_return_value``/
``benchmark_return_value`` Numeric(20,12) are the NULLABLE per-row return evidence.

No schema change for ``COMPONENT_KIND_PORTFOLIO_RETURN``/``COMPONENT_KIND_BENCHMARK_RETURN`` /
``PURPOSE_BENCHMARK_RELATIVE_INPUT`` (unconstrained strings — app constants; the
``dataset_snapshot``/``component`` tables are unchanged). No new audit code (the run reuses
``CALC.RUN_*``;
``PERF.BENCHMARK_RELATIVE_CREATE`` is RESERVED, not minted). NO new permission (``perf.run``/
``perf.view`` are REUSED). ``PreciseDecimal`` renders ``NUMERIC(p,s)`` on PG — no DDL surprise.

Revision ID: 0032_benchmark_relative
Revises: 0031_portfolio_return
Create Date: 2026-07-10
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0032_benchmark_relative"
down_revision: str | None = "0031_portfolio_return"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: Symmetric tenant-isolation (NOT hybrid).
TENANT_SCOPED_TABLES = ("benchmark_relative_result",)
#: Truly immutable append-only (the irp_prevent_mutation P0001 trigger, reusing the 0001 function).
APPEND_ONLY_TABLES = ("benchmark_relative_result",)


def upgrade() -> None:
    op.create_table(
        "benchmark_relative_result",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("system_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("calculation_run_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("input_snapshot_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("model_version_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("portfolio_return_run_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("benchmark_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("portfolio_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("metric_type", sa.String(length=30), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("metric_value", sa.Numeric(20, 12), nullable=False),
        sa.Column("portfolio_return_value", sa.Numeric(20, 12), nullable=True),
        sa.Column("benchmark_return_value", sa.Numeric(20, 12), nullable=True),
        sa.Column("n_benchmark_obs", sa.Integer(), nullable=False),
        sa.Column("n_periods", sa.Integer(), nullable=False),
        sa.Column("base_currency", sa.String(length=3), nullable=False),
        sa.Column("return_basis", sa.String(length=20), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_benchmark_relative_result"),
        sa.ForeignKeyConstraint(
            ["calculation_run_id"],
            ["calculation_run.run_id"],
            name="fk_benchmark_relative_result_calculation_run_id_calculation_run",
        ),
        sa.ForeignKeyConstraint(
            ["input_snapshot_id"],
            ["dataset_snapshot.id"],
            name="fk_benchmark_relative_result_input_snapshot_id_dataset_snapshot",
        ),
        sa.ForeignKeyConstraint(
            ["model_version_id"],
            ["model_version.id"],
            name="fk_benchmark_relative_result_model_version_id_model_version",
        ),
        sa.ForeignKeyConstraint(
            ["portfolio_return_run_id"],
            ["calculation_run.run_id"],
            name="fk_benchmark_relative_result_portfolio_return_run",  # 63-char PG identifier cap
        ),
        sa.ForeignKeyConstraint(
            ["benchmark_id"],
            ["benchmark.id"],
            name="fk_benchmark_relative_result_benchmark_id_benchmark",
        ),
        sa.ForeignKeyConstraint(
            ["portfolio_id"],
            ["portfolio.id"],
            name="fk_benchmark_relative_result_portfolio_id_portfolio",
        ),
        sa.UniqueConstraint(
            "calculation_run_id",
            "metric_type",
            "period_start",
            name="uq_benchmark_relative_result_run_grain",
        ),
    )
    op.create_index(
        "ix_benchmark_relative_result_tenant_id", "benchmark_relative_result", ["tenant_id"]
    )
    op.create_index(
        "ix_benchmark_relative_result_calculation_run_id",
        "benchmark_relative_result",
        ["calculation_run_id"],
    )
    op.create_index(
        "ix_benchmark_relative_result_input_snapshot_id",
        "benchmark_relative_result",
        ["input_snapshot_id"],
    )
    op.create_index(
        "ix_benchmark_relative_result_model_version_id",
        "benchmark_relative_result",
        ["model_version_id"],
    )
    op.create_index(
        "ix_benchmark_relative_result_portfolio_return_run_id",
        "benchmark_relative_result",
        ["portfolio_return_run_id"],
    )
    op.create_index(
        "ix_benchmark_relative_result_benchmark_id", "benchmark_relative_result", ["benchmark_id"]
    )
    op.create_index(
        "ix_benchmark_relative_result_portfolio_id", "benchmark_relative_result", ["portfolio_id"]
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
    op.drop_table("benchmark_relative_result")
