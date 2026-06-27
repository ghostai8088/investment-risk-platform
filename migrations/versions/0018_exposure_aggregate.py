"""P2-3: exposure_aggregate (ENT-014, IA — the first governed derived number) + the additive
calculation_run.environment_id column.

``exposure_aggregate`` is a tenant-scoped PROPRIETARY table under the **SYMMETRIC** tenant-isolation
RLS loop (``USING == WITH CHECK == own-tenant``) — the SAME pattern as 0009..0017. NOT hybrid, no
SYSTEM_TENANT (the 0008 hybrid loop + ``HYBRID_TABLES`` are untouched; the closed 5-table hybrid set
is unchanged). **TRULY IMMUTABLE / append-only** (the ``transaction``/``dataset_snapshot`` precedent,
NOT the status-mutable ``calculation_run``): in this migration's local ``APPEND_ONLY_TABLES`` -> the
``irp_prevent_mutation`` P0001 trigger (REUSING the 0001 function), paired with the ORM
before_update/before_delete guard. Run-bound + snapshot-gated (NOT-NULL FKs to ``calculation_run`` +
``dataset_snapshot``).

``calculation_run.environment_id`` (String(100), nullable) is added additively to the SHIPPED
status-mutable ``calculation_run`` table (FW-RUN §5 item 7) — a non-breaking ADD COLUMN; the table is
NOT touched otherwise and stays out of ``APPEND_ONLY_TABLES``.

No new audit code (the run reuses ``CALC.RUN_*``); the ``exposure.view``/``exposure.aggregate.run``
perms are wired in the entitlement bootstrap and seeded by 0002 on a fresh migrate.

Revision ID: 0018_exposure_aggregate
Revises: 0017_fx_rate
Create Date: 2026-06-26
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0018_exposure_aggregate"
down_revision: str | None = "0017_fx_rate"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: Symmetric tenant-isolation (NOT hybrid).
TENANT_SCOPED_TABLES = ("exposure_aggregate",)
#: Truly immutable append-only (the irp_prevent_mutation P0001 trigger, reusing the 0001 function).
APPEND_ONLY_TABLES = ("exposure_aggregate",)


def upgrade() -> None:
    # --- Additive: the FW-RUN environment_id on the SHIPPED status-mutable calculation_run table.
    op.add_column(
        "calculation_run",
        sa.Column("environment_id", sa.String(length=100), nullable=True),
    )

    op.create_table(
        "exposure_aggregate",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("system_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("calculation_run_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("input_snapshot_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("portfolio_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("instrument_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("base_currency", sa.String(length=3), nullable=False),
        sa.Column("mark_currency", sa.String(length=3), nullable=False),
        sa.Column("signed_quantity", sa.Numeric(28, 8), nullable=False),
        sa.Column("mark_value", sa.Numeric(20, 6), nullable=False),
        sa.Column("fx_rate", sa.Numeric(28, 12), nullable=False),
        sa.Column("fx_legs", sa.Text(), nullable=False),
        sa.Column("exposure_amount", sa.Numeric(28, 6), nullable=False),
        sa.Column("exposure_type", sa.String(length=30), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_exposure_aggregate"),
        sa.ForeignKeyConstraint(
            ["calculation_run_id"],
            ["calculation_run.run_id"],
            name="fk_exposure_aggregate_calculation_run_id_calculation_run",
        ),
        sa.ForeignKeyConstraint(
            ["input_snapshot_id"],
            ["dataset_snapshot.id"],
            name="fk_exposure_aggregate_input_snapshot_id_dataset_snapshot",
        ),
        sa.UniqueConstraint(
            "calculation_run_id",
            "portfolio_id",
            "instrument_id",
            "base_currency",
            name="uq_exposure_aggregate_run_grain",
        ),
    )
    op.create_index("ix_exposure_aggregate_tenant_id", "exposure_aggregate", ["tenant_id"])
    op.create_index(
        "ix_exposure_aggregate_calculation_run_id", "exposure_aggregate", ["calculation_run_id"]
    )
    op.create_index(
        "ix_exposure_aggregate_input_snapshot_id", "exposure_aggregate", ["input_snapshot_id"]
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
    op.drop_table("exposure_aggregate")
    op.drop_column("calculation_run", "environment_id")
