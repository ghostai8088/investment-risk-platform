"""PPF-1: private_factor_return_result (ENT-060 — the EIGHTEENTH governed number).

``private_factor_return_result`` is a tenant-scoped PROPRIETARY table under the **SYMMETRIC**
tenant-isolation RLS loop (``USING == WITH CHECK == own-tenant``) — the SAME pattern as
0009..0046. NOT hybrid, no SYSTEM_TENANT (the closed 5-table hybrid set is unchanged). **TRULY
IMMUTABLE / append-only** (the ``pacing_projection_result`` / ``proxy_weight_estimate_result``
precedent): the ``irp_prevent_mutation`` P0001 trigger (REUSING the 0001 function), paired with the
ORM before_update/before_delete guard. Run-bound + snapshot-gated + model-bound (NOT-NULL FKs to
``calculation_run`` + ``dataset_snapshot`` + ``model_version``) PLUS ``segment_factor_id`` (the
PRIVATE segment — deliberately NOT a hard FK, the ``factor_exposure_result`` precedent: the pinned
``COMPONENT_KIND_FACTOR`` is authoritative). One row per pooled appraisal period (``metric_type``
``PURE_PRIVATE_PERIOD``) + one ``PURE_PRIVATE_SUMMARY`` singleton; grain
``(calculation_run_id, metric_type, period_start)``. ``metric_value`` Numeric(20,12) is a FRACTION
(a pooled return, or the summary's pooled stdev — NOT currency).

No schema change for ``COMPONENT_KIND_*`` / ``PURPOSE_PRIVATE_FACTOR_RETURN_INPUT`` (unconstrained
strings — app constants). No new audit code (the run reuses ``CALC.RUN_*``). ``PreciseDecimal``
renders ``NUMERIC(p,s)`` on PG — ``alembic check`` no-op. Every DDL identifier here is <= 63 chars
(asserted below — the P3-8/BT-1 lesson). Downgrade is honestly destructive (drops the trigger,
policy, and table + every pooled row).

Revision ID: 0047_private_factor_return
Revises: 0046_run_scope_portfolio
Create Date: 2026-07-22
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0047_private_factor_return"
down_revision: str | None = "0046_run_scope_portfolio"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: Symmetric tenant-isolation (NOT hybrid).
TENANT_SCOPED_TABLES = ("private_factor_return_result",)
#: Truly immutable append-only (the irp_prevent_mutation P0001 trigger, reusing the 0001 function).
APPEND_ONLY_TABLES = ("private_factor_return_result",)

#: Every name this migration mints, checked at import time (the P3-8/BT-1 63-char lesson).
_IDENTIFIERS = (
    "private_factor_return_result",
    "pk_private_factor_return_result",
    "fk_private_factor_return_result_calc_run",
    "fk_private_factor_return_result_input_snapshot",
    "fk_private_factor_return_result_model_version",
    "uq_private_factor_return_result_run_grain",
    "ix_private_factor_return_result_tenant_id",
    "ix_private_factor_return_result_calculation_run_id",
    "ix_private_factor_return_result_input_snapshot_id",
    "ix_private_factor_return_result_model_version_id",
    "ix_private_factor_return_result_segment_factor_id",
    "tenant_isolation_private_factor_return_result",
    "private_factor_return_result_append_only",
)
assert all(len(name) <= 63 for name in _IDENTIFIERS), [
    name for name in _IDENTIFIERS if len(name) > 63
]


def upgrade() -> None:
    op.create_table(
        "private_factor_return_result",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("system_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("calculation_run_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("input_snapshot_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("model_version_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("segment_factor_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("metric_type", sa.String(length=30), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("metric_value", sa.Numeric(20, 12), nullable=False),
        sa.Column("member_count", sa.Integer(), nullable=False),
        sa.Column("period_count", sa.Integer(), nullable=True),
        sa.Column("pooling_convention", sa.String(length=20), nullable=False),
        sa.Column("intercept_convention", sa.String(length=20), nullable=False),
        sa.Column("min_members", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_private_factor_return_result"),
        sa.ForeignKeyConstraint(
            ["calculation_run_id"],
            ["calculation_run.run_id"],
            name="fk_private_factor_return_result_calc_run",
        ),
        sa.ForeignKeyConstraint(
            ["input_snapshot_id"],
            ["dataset_snapshot.id"],
            name="fk_private_factor_return_result_input_snapshot",
        ),
        sa.ForeignKeyConstraint(
            ["model_version_id"],
            ["model_version.id"],
            name="fk_private_factor_return_result_model_version",
        ),
        sa.UniqueConstraint(
            "calculation_run_id",
            "metric_type",
            "period_start",
            name="uq_private_factor_return_result_run_grain",
        ),
    )
    op.create_index(
        "ix_private_factor_return_result_tenant_id",
        "private_factor_return_result",
        ["tenant_id"],
    )
    op.create_index(
        "ix_private_factor_return_result_calculation_run_id",
        "private_factor_return_result",
        ["calculation_run_id"],
    )
    op.create_index(
        "ix_private_factor_return_result_input_snapshot_id",
        "private_factor_return_result",
        ["input_snapshot_id"],
    )
    op.create_index(
        "ix_private_factor_return_result_model_version_id",
        "private_factor_return_result",
        ["model_version_id"],
    )
    op.create_index(
        "ix_private_factor_return_result_segment_factor_id",
        "private_factor_return_result",
        ["segment_factor_id"],
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
    # Honestly destructive: drops every pooled pure-private-return row.
    for table in APPEND_ONLY_TABLES:
        op.execute(f"DROP TRIGGER IF EXISTS {table}_append_only ON {table}")
    for table in TENANT_SCOPED_TABLES:
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation_{table} ON {table}")
    op.drop_table("private_factor_return_result")
