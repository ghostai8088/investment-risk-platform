"""CC-2: pacing_projection_result (ENT-059 — the SEVENTEENTH governed number).

``pacing_projection_result`` is a tenant-scoped PROPRIETARY table under the **SYMMETRIC**
tenant-isolation RLS loop (``USING == WITH CHECK == own-tenant``) — the SAME pattern as
0009..0044. NOT hybrid, no SYSTEM_TENANT (the 0008 hybrid loop + the closed 5-table hybrid set are
unchanged). **TRULY IMMUTABLE / append-only** (the ``portfolio_return_result`` precedent): the
``irp_prevent_mutation`` P0001 trigger (REUSING the 0001 function), paired with the ORM
before_update/before_delete guard. Run-bound + snapshot-gated + model-bound (NOT-NULL FKs to
``calculation_run`` + ``dataset_snapshot`` + ``model_version``) PLUS ``portfolio_id`` +
``instrument_id`` (the projected commitment identity). One row per projected FUTURE period; grain
``(calculation_run_id, period_index)`` where ``period_index`` is the fund AGE. The four money
columns Numeric(28,6) are in the commitment's chain-immutable ``currency_code``.

No schema change for ``COMPONENT_KIND_*`` / ``PURPOSE_PACING_INPUT`` (unconstrained strings — app
constants). No new audit code (the run reuses ``CALC.RUN_*``; ``PACING.PROJECTION_CREATE`` is
RESERVED, not minted). ``PreciseDecimal`` renders ``NUMERIC(p,s)`` on PG — ``alembic check`` no-op.
Every DDL identifier here is <= 63 chars (asserted below — the P3-8/BT-1 lesson). Downgrade is
honestly destructive (drops the trigger, policy, and table + every projected row).

Revision ID: 0045_pacing_projection
Revises: 0044_private_capital
Create Date: 2026-07-20
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0045_pacing_projection"
down_revision: str | None = "0044_private_capital"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: Symmetric tenant-isolation (NOT hybrid).
TENANT_SCOPED_TABLES = ("pacing_projection_result",)
#: Truly immutable append-only (the irp_prevent_mutation P0001 trigger, reusing the 0001 function).
APPEND_ONLY_TABLES = ("pacing_projection_result",)

#: Every name this migration mints, checked at import time (the P3-8/BT-1 63-char lesson).
_IDENTIFIERS = (
    "pacing_projection_result",
    "pk_pacing_projection_result",
    "fk_pacing_projection_result_calculation_run_id_calculation_run",
    "fk_pacing_projection_result_input_snapshot_id_dataset_snapshot",
    "fk_pacing_projection_result_model_version_id_model_version",
    "fk_pacing_projection_result_portfolio_id_portfolio",
    "fk_pacing_projection_result_instrument_id_instrument",
    "uq_pacing_projection_result_run_grain",
    "ix_pacing_projection_result_tenant_id",
    "ix_pacing_projection_result_calculation_run_id",
    "ix_pacing_projection_result_input_snapshot_id",
    "ix_pacing_projection_result_model_version_id",
    "ix_pacing_projection_result_portfolio_id",
    "ix_pacing_projection_result_instrument_id",
    "tenant_isolation_pacing_projection_result",
    "pacing_projection_result_append_only",
)
assert all(len(name) <= 63 for name in _IDENTIFIERS), [
    name for name in _IDENTIFIERS if len(name) > 63
]


def upgrade() -> None:
    op.create_table(
        "pacing_projection_result",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("system_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("calculation_run_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("input_snapshot_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("model_version_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("portfolio_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("instrument_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("period_index", sa.Integer(), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("projected_call", sa.Numeric(28, 6), nullable=False),
        sa.Column("projected_distribution", sa.Numeric(28, 6), nullable=False),
        sa.Column("projected_nav", sa.Numeric(28, 6), nullable=False),
        sa.Column("unfunded_end", sa.Numeric(28, 6), nullable=False),
        sa.Column("currency_code", sa.String(length=3), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_pacing_projection_result"),
        sa.ForeignKeyConstraint(
            ["calculation_run_id"],
            ["calculation_run.run_id"],
            name="fk_pacing_projection_result_calculation_run_id_calculation_run",
        ),
        sa.ForeignKeyConstraint(
            ["input_snapshot_id"],
            ["dataset_snapshot.id"],
            name="fk_pacing_projection_result_input_snapshot_id_dataset_snapshot",
        ),
        sa.ForeignKeyConstraint(
            ["model_version_id"],
            ["model_version.id"],
            name="fk_pacing_projection_result_model_version_id_model_version",
        ),
        sa.ForeignKeyConstraint(
            ["portfolio_id"],
            ["portfolio.id"],
            name="fk_pacing_projection_result_portfolio_id_portfolio",
        ),
        sa.ForeignKeyConstraint(
            ["instrument_id"],
            ["instrument.id"],
            name="fk_pacing_projection_result_instrument_id_instrument",
        ),
        sa.UniqueConstraint(
            "calculation_run_id",
            "period_index",
            name="uq_pacing_projection_result_run_grain",
        ),
    )
    op.create_index(
        "ix_pacing_projection_result_tenant_id", "pacing_projection_result", ["tenant_id"]
    )
    op.create_index(
        "ix_pacing_projection_result_calculation_run_id",
        "pacing_projection_result",
        ["calculation_run_id"],
    )
    op.create_index(
        "ix_pacing_projection_result_input_snapshot_id",
        "pacing_projection_result",
        ["input_snapshot_id"],
    )
    op.create_index(
        "ix_pacing_projection_result_model_version_id",
        "pacing_projection_result",
        ["model_version_id"],
    )
    op.create_index(
        "ix_pacing_projection_result_portfolio_id", "pacing_projection_result", ["portfolio_id"]
    )
    op.create_index(
        "ix_pacing_projection_result_instrument_id", "pacing_projection_result", ["instrument_id"]
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
    # Honestly destructive: drops every projected row.
    for table in APPEND_ONLY_TABLES:
        op.execute(f"DROP TRIGGER IF EXISTS {table}_append_only ON {table}")
    for table in TENANT_SCOPED_TABLES:
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation_{table} ON {table}")
    op.drop_table("pacing_projection_result")
