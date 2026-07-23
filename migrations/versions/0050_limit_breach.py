"""LIM-1 limit/breach: limit_definition (ENT-031, EV) + breach (ENT-033, IA append-only).

The first governed write-side control (Wave-11 slice 2). Both tables are PROPRIETARY, tenant-scoped,
symmetric FORCE RLS — NEVER hybrid. ``breach`` additionally gets the migration-0001
``irp_prevent_mutation()`` append-only trigger; ``limit_definition`` (EV, edited in place via
``record_version``) does NOT.

The app does ALL reads/writes tenant-scoped NON-BYPASSRLS (the SCH-1 posture) — this migration
grants the ``irp_ops`` BYPASSRLS role NOTHING on either table (the standing no-grant invariant).

Realizes the pre-reserved ENT-031/033 entities; activates the reserved LIMIT.*/BREACH.* audit codes.
Mints NO new governed number and NO new ``run_type`` (a breach references an already-governed run).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0050_limit_breach"
down_revision: str | None = "0049_scheduling"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TENANT_SCOPED_TABLES = ("limit_definition", "breach")
APPEND_ONLY_TABLES = ("breach",)

_IDENTIFIERS = (
    "limit_definition",
    "pk_limit_definition",
    "fk_limit_definition_scope_portfolio_id_portfolio",
    "fk_limit_definition_benchmark_id_benchmark",
    "uq_limit_definition_tenant_code",
    "ix_limit_definition_tenant_id",
    "ix_limit_definition_benchmark_id",
    "ix_limit_definition_scope_portfolio_id",
    "tenant_isolation_limit_definition",
    "breach",
    "pk_breach",
    "fk_breach_limit_definition_id_limit_definition",
    "fk_breach_calculation_run_id_calculation_run",
    "uq_breach_limit_run",
    "ix_breach_tenant_id",
    "ix_breach_limit_definition_id",
    "ix_breach_calculation_run_id",
    "tenant_isolation_breach",
    "breach_append_only",
)
assert all(len(name) <= 63 for name in _IDENTIFIERS), [
    name for name in _IDENTIFIERS if len(name) > 63
]


def upgrade() -> None:
    # --- ENT-031 limit_definition (EV config header; entity-versioned in place, not append-only) --
    op.create_table(
        "limit_definition",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(length=255), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by", sa.String(length=255), nullable=True),
        sa.Column("code", sa.String(length=150), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("target_run_type", sa.String(length=100), nullable=False),
        sa.Column("metric_type", sa.String(length=30), nullable=False),
        sa.Column("benchmark_id", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("scope_portfolio_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("threshold_value", sa.Numeric(precision=28, scale=12), nullable=False),
        sa.Column("threshold_unit", sa.String(length=20), nullable=False),
        sa.Column("breach_direction", sa.String(length=8), nullable=False),
        sa.Column("limit_kind", sa.String(length=10), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("record_version", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_limit_definition"),
        sa.ForeignKeyConstraint(
            ["scope_portfolio_id"],
            ["portfolio.id"],
            name="fk_limit_definition_scope_portfolio_id_portfolio",
        ),
        sa.ForeignKeyConstraint(
            ["benchmark_id"],
            ["benchmark.id"],
            name="fk_limit_definition_benchmark_id_benchmark",
        ),
        sa.UniqueConstraint("tenant_id", "code", name="uq_limit_definition_tenant_code"),
    )
    op.create_index("ix_limit_definition_tenant_id", "limit_definition", ["tenant_id"])
    op.create_index("ix_limit_definition_benchmark_id", "limit_definition", ["benchmark_id"])
    op.create_index(
        "ix_limit_definition_scope_portfolio_id", "limit_definition", ["scope_portfolio_id"]
    )

    # --- ENT-033 breach (IA TRUE append-only; one row per detected breach, self-describing) ---
    op.create_table(
        "breach",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("system_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("limit_definition_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("calculation_run_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("detected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("target_run_type", sa.String(length=100), nullable=False),
        sa.Column("metric_type", sa.String(length=30), nullable=False),
        sa.Column("benchmark_id", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("observed_value", sa.Numeric(precision=28, scale=12), nullable=False),
        sa.Column("threshold_value", sa.Numeric(precision=28, scale=12), nullable=False),
        sa.Column("threshold_unit", sa.String(length=20), nullable=False),
        sa.Column("breach_direction", sa.String(length=8), nullable=False),
        sa.Column("limit_kind", sa.String(length=10), nullable=False),
        sa.Column("severity", sa.String(length=10), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_breach"),
        sa.ForeignKeyConstraint(
            ["limit_definition_id"],
            ["limit_definition.id"],
            name="fk_breach_limit_definition_id_limit_definition",
        ),
        sa.ForeignKeyConstraint(
            ["calculation_run_id"],
            ["calculation_run.run_id"],
            name="fk_breach_calculation_run_id_calculation_run",
        ),
        sa.UniqueConstraint(
            "limit_definition_id", "calculation_run_id", name="uq_breach_limit_run"
        ),
    )
    op.create_index("ix_breach_tenant_id", "breach", ["tenant_id"])
    op.create_index("ix_breach_limit_definition_id", "breach", ["limit_definition_id"])
    op.create_index("ix_breach_calculation_run_id", "breach", ["calculation_run_id"])

    # --- symmetric FORCE RLS on both (PROPRIETARY; NO ops-role grant) ---
    for table in TENANT_SCOPED_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY tenant_isolation_{table} ON {table} "
            f"USING (tenant_id::text = current_setting('app.current_tenant', true)) "
            f"WITH CHECK (tenant_id::text = current_setting('app.current_tenant', true))"
        )

    # --- append-only trigger on breach ONLY (reuses the 0001 P0001 function) ---
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
    op.drop_table("breach")
    op.drop_table("limit_definition")
