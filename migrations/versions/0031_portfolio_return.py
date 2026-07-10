"""PM-1: portfolio_return_result (ENT-053 — the seventh governed number, the FIRST non-risk one).

``portfolio_return_result`` is a tenant-scoped PROPRIETARY table under the **SYMMETRIC**
tenant-isolation RLS loop (``USING == WITH CHECK == own-tenant``) — the SAME pattern as
0009..0030.
NOT hybrid, no SYSTEM_TENANT (the 0008 hybrid loop + the closed 5-table hybrid set are unchanged).
**TRULY IMMUTABLE / append-only** (the ``active_risk_result`` precedent): in this migration's local
``APPEND_ONLY_TABLES`` -> the ``irp_prevent_mutation`` P0001 trigger (REUSING the 0001 function),
paired with the ORM before_update/before_delete guard. Run-bound + snapshot-gated + model-bound
(NOT-NULL FKs to ``calculation_run`` + ``dataset_snapshot`` + ``model_version``) PLUS
``portfolio_id`` -> ``portfolio.id`` (the measured book). The N boundary-run provenance lives in the
pinned EXPOSURE atoms of the ``RETURN_INPUT`` snapshot (N is variable — no per-run FK columns).

Grain ``(calculation_run_id, metric_type, period_start)``: ``n`` ``DIETZ_PERIOD`` sub-period rows +
ONE ``TWR_LINKED`` summary row (a DIETZ_PERIOD row and the TWR_LINKED row can share ``period_start``
because ``metric_type`` differs). ``return_value`` Numeric(20,12) is a return FRACTION; the
``begin_mv``/``end_mv``/``net_external_flow`` Numeric(28,6) columns are the Modified-Dietz
evidence (base currency).

No schema change for ``COMPONENT_KIND_TRANSACTION`` / ``PURPOSE_RETURN_INPUT`` (unconstrained
strings — app constants; the ``dataset_snapshot``/``component`` tables are unchanged). No new audit
code (the run reuses ``CALC.RUN_*``; ``PERF.RETURN_CREATE`` is RESERVED, not minted).
``PreciseDecimal`` renders ``NUMERIC(p,s)`` on PG — no DDL surprise; ``alembic check`` is a no-op.

Revision ID: 0031_portfolio_return
Revises: 0030_active_risk
Create Date: 2026-07-09
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0031_portfolio_return"
down_revision: str | None = "0030_active_risk"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: Symmetric tenant-isolation (NOT hybrid).
TENANT_SCOPED_TABLES = ("portfolio_return_result",)
#: Truly immutable append-only (the irp_prevent_mutation P0001 trigger, reusing the 0001 function).
APPEND_ONLY_TABLES = ("portfolio_return_result",)


def upgrade() -> None:
    op.create_table(
        "portfolio_return_result",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("system_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("calculation_run_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("input_snapshot_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("model_version_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("portfolio_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("metric_type", sa.String(length=30), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("begin_mv", sa.Numeric(28, 6), nullable=False),
        sa.Column("end_mv", sa.Numeric(28, 6), nullable=False),
        sa.Column("net_external_flow", sa.Numeric(28, 6), nullable=False),
        sa.Column("return_value", sa.Numeric(20, 12), nullable=False),
        sa.Column("n_flows", sa.Integer(), nullable=False),
        sa.Column("n_periods", sa.Integer(), nullable=False),
        sa.Column("base_currency", sa.String(length=3), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_portfolio_return_result"),
        sa.ForeignKeyConstraint(
            ["calculation_run_id"],
            ["calculation_run.run_id"],
            name="fk_portfolio_return_result_calculation_run_id_calculation_run",
        ),
        sa.ForeignKeyConstraint(
            ["input_snapshot_id"],
            ["dataset_snapshot.id"],
            name="fk_portfolio_return_result_input_snapshot_id_dataset_snapshot",
        ),
        sa.ForeignKeyConstraint(
            ["model_version_id"],
            ["model_version.id"],
            name="fk_portfolio_return_result_model_version_id_model_version",
        ),
        sa.ForeignKeyConstraint(
            ["portfolio_id"],
            ["portfolio.id"],
            name="fk_portfolio_return_result_portfolio_id_portfolio",
        ),
        sa.UniqueConstraint(
            "calculation_run_id",
            "metric_type",
            "period_start",
            name="uq_portfolio_return_result_run_grain",
        ),
    )
    op.create_index(
        "ix_portfolio_return_result_tenant_id", "portfolio_return_result", ["tenant_id"]
    )
    op.create_index(
        "ix_portfolio_return_result_calculation_run_id",
        "portfolio_return_result",
        ["calculation_run_id"],
    )
    op.create_index(
        "ix_portfolio_return_result_input_snapshot_id",
        "portfolio_return_result",
        ["input_snapshot_id"],
    )
    op.create_index(
        "ix_portfolio_return_result_model_version_id",
        "portfolio_return_result",
        ["model_version_id"],
    )
    op.create_index(
        "ix_portfolio_return_result_portfolio_id", "portfolio_return_result", ["portfolio_id"]
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
    op.drop_table("portfolio_return_result")
