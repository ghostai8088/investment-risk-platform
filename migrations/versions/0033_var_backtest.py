"""BT-1: var_backtest_result (ENT-055 — the ninth governed number; VaR backtesting).

``var_backtest_result`` is a tenant-scoped PROPRIETARY table under the **SYMMETRIC**
tenant-isolation RLS loop (``USING == WITH CHECK == own-tenant``) — the SAME pattern as
0009..0032. NOT hybrid, no SYSTEM_TENANT (the 0008 hybrid loop + the closed 5-table hybrid set are
unchanged). **TRULY IMMUTABLE / append-only** (the ``benchmark_relative_result`` precedent): in
this migration's local ``APPEND_ONLY_TABLES`` -> the ``irp_prevent_mutation`` P0001 trigger
(REUSING the 0001 function), paired with the ORM before_update/before_delete guard. Run-bound +
snapshot-gated + model-bound (NOT-NULL FKs to ``calculation_run`` + ``dataset_snapshot`` +
``model_version``) PLUS the hard-FK PROVENANCE columns ``portfolio_return_run_id`` ->
``calculation_run.run_id`` (the ONE consumed PM-1 run) and ``portfolio_id`` -> ``portfolio.id``.

Grain ``(calculation_run_id, metric_type, period_start)``: ``n`` per-pair ``EXCEPTION_INDICATOR``
rows + ``EXCEPTION_COUNT``/``KUPIEC_LR``/``BASEL_ZONE`` summary rows (a pair row and a summary row
can share ``period_start`` because ``metric_type`` differs). ``metric_value`` Numeric(28,6) is a
0/1 indicator, a count, or the Kupiec LR statistic; ``realized_pnl``/``var_value`` Numeric(28,6)
are the NULLABLE per-pair money evidence; ``test_decision``/``basel_zone`` are NULLABLE strings.

Every DDL identifier here is <= 63 chars (asserted below — the 0032 lesson: SQLite never enforces
the PG cap; the ONE over-long auto-style FK name cost a local-PG failure).

No schema change for ``COMPONENT_KIND_VAR`` / ``PURPOSE_VAR_BACKTEST_INPUT`` (unconstrained
strings — app constants). No new audit code (the run reuses ``CALC.RUN_*``;
``RISK.VAR_BACKTEST_CREATE`` is RESERVED, not minted). NO new permission (``risk.run``/
``risk.view`` are REUSED). ``PreciseDecimal`` renders ``NUMERIC(p,s)`` on PG — no DDL surprise.

Revision ID: 0033_var_backtest
Revises: 0032_benchmark_relative
Create Date: 2026-07-10
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0033_var_backtest"
down_revision: str | None = "0032_benchmark_relative"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: Symmetric tenant-isolation (NOT hybrid).
TENANT_SCOPED_TABLES = ("var_backtest_result",)
#: Truly immutable append-only (the irp_prevent_mutation P0001 trigger, reusing the 0001 function).
APPEND_ONLY_TABLES = ("var_backtest_result",)

#: The 0032 lesson, made structural: every name this migration mints, checked at import time.
_IDENTIFIERS = (
    "var_backtest_result",
    "pk_var_backtest_result",
    "fk_var_backtest_result_calculation_run_id_calculation_run",
    "fk_var_backtest_result_input_snapshot_id_dataset_snapshot",
    "fk_var_backtest_result_model_version_id_model_version",
    "fk_var_backtest_result_portfolio_return_run_id_calculation_run",
    "fk_var_backtest_result_portfolio_id_portfolio",
    "uq_var_backtest_result_run_grain",
    "ix_var_backtest_result_tenant_id",
    "ix_var_backtest_result_calculation_run_id",
    "ix_var_backtest_result_input_snapshot_id",
    "ix_var_backtest_result_model_version_id",
    "ix_var_backtest_result_portfolio_return_run_id",
    "ix_var_backtest_result_portfolio_id",
    "tenant_isolation_var_backtest_result",
    "var_backtest_result_append_only",
)
assert all(len(name) <= 63 for name in _IDENTIFIERS), [
    name for name in _IDENTIFIERS if len(name) > 63
]


def upgrade() -> None:
    op.create_table(
        "var_backtest_result",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("system_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("calculation_run_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("input_snapshot_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("model_version_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("portfolio_return_run_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("portfolio_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("metric_type", sa.String(length=30), nullable=False),
        sa.Column("var_metric_type", sa.String(length=30), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("metric_value", sa.Numeric(28, 6), nullable=False),
        sa.Column("realized_pnl", sa.Numeric(28, 6), nullable=True),
        sa.Column("var_value", sa.Numeric(28, 6), nullable=True),
        sa.Column("n_pairs", sa.Integer(), nullable=False),
        sa.Column("n_exceptions", sa.Integer(), nullable=False),
        sa.Column("confidence_level", sa.Numeric(6, 4), nullable=False),
        sa.Column("horizon_days", sa.Integer(), nullable=False),
        sa.Column("test_decision", sa.String(length=20), nullable=True),
        sa.Column("basel_zone", sa.String(length=10), nullable=True),
        sa.Column("base_currency", sa.String(length=3), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_var_backtest_result"),
        sa.ForeignKeyConstraint(
            ["calculation_run_id"],
            ["calculation_run.run_id"],
            name="fk_var_backtest_result_calculation_run_id_calculation_run",
        ),
        sa.ForeignKeyConstraint(
            ["input_snapshot_id"],
            ["dataset_snapshot.id"],
            name="fk_var_backtest_result_input_snapshot_id_dataset_snapshot",
        ),
        sa.ForeignKeyConstraint(
            ["model_version_id"],
            ["model_version.id"],
            name="fk_var_backtest_result_model_version_id_model_version",
        ),
        sa.ForeignKeyConstraint(
            ["portfolio_return_run_id"],
            ["calculation_run.run_id"],
            # 62 chars — the naming-convention name FITS the 63-char cap (review fold: the
            # 0032 name needed shortening at 68; this one never did).
            name="fk_var_backtest_result_portfolio_return_run_id_calculation_run",
        ),
        sa.ForeignKeyConstraint(
            ["portfolio_id"],
            ["portfolio.id"],
            name="fk_var_backtest_result_portfolio_id_portfolio",
        ),
        sa.UniqueConstraint(
            "calculation_run_id",
            "metric_type",
            "period_start",
            name="uq_var_backtest_result_run_grain",
        ),
    )
    op.create_index("ix_var_backtest_result_tenant_id", "var_backtest_result", ["tenant_id"])
    op.create_index(
        "ix_var_backtest_result_calculation_run_id",
        "var_backtest_result",
        ["calculation_run_id"],
    )
    op.create_index(
        "ix_var_backtest_result_input_snapshot_id",
        "var_backtest_result",
        ["input_snapshot_id"],
    )
    op.create_index(
        "ix_var_backtest_result_model_version_id",
        "var_backtest_result",
        ["model_version_id"],
    )
    op.create_index(
        "ix_var_backtest_result_portfolio_return_run_id",
        "var_backtest_result",
        ["portfolio_return_run_id"],
    )
    op.create_index("ix_var_backtest_result_portfolio_id", "var_backtest_result", ["portfolio_id"])

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
    op.drop_table("var_backtest_result")
