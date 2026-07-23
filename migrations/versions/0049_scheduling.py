"""SCH-1 scheduling: schedule (ENT-061, EV) + scheduled_run (ENT-062, IA append-only).

The first operational-cadence control plane (Wave-11 slice 1). Both tables are PROPRIETARY,
tenant-scoped, symmetric FORCE RLS — NEVER hybrid. ``scheduled_run`` additionally gets the
migration-0001 ``irp_prevent_mutation()`` append-only trigger; ``schedule`` (EV, edited in place via
``record_version``) does NOT.

Under OQ-SCH-1-1=B (infra-driven per-tenant dispatch), the app does ALL reads/writes tenant-scoped
NON-BYPASSRLS. This migration therefore grants the ``irp_ops`` BYPASSRLS role NOTHING on either
table — preserving the standing ``test_ops_role_has_no_grant_on_*`` isolation invariant that every
prior slice upholds (Option A, an ops-role cross-tenant read, was REJECTED at ratification).

Mints NO new governed number and NO new ``run_type``: a fire re-invokes an existing family binder.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0049_scheduling"
down_revision: str | None = "0048_var_private_variance"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TENANT_SCOPED_TABLES = ("schedule", "scheduled_run")
APPEND_ONLY_TABLES = ("scheduled_run",)

_IDENTIFIERS = (
    "schedule",
    "pk_schedule",
    "fk_schedule_scope_portfolio_id_portfolio",
    "fk_schedule_model_version_id_model_version",
    "uq_schedule_tenant_code",
    "ix_schedule_tenant_id",
    "ix_schedule_scope_portfolio_id",
    "ix_schedule_model_version_id",
    "tenant_isolation_schedule",
    "scheduled_run",
    "pk_scheduled_run",
    "fk_scheduled_run_schedule_id_schedule",
    "fk_scheduled_run_calculation_run_id_calculation_run",
    "uq_scheduled_run_schedule_tick",
    "ix_scheduled_run_tenant_id",
    "ix_scheduled_run_schedule_id",
    "ix_scheduled_run_calculation_run_id",
    "tenant_isolation_scheduled_run",
    "scheduled_run_append_only",
)
assert all(len(name) <= 63 for name in _IDENTIFIERS), [
    name for name in _IDENTIFIERS if len(name) > 63
]


def upgrade() -> None:
    # --- ENT-061 schedule (EV config header; entity-versioned in place, NOT append-only) ---
    op.create_table(
        "schedule",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(length=255), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_by", sa.String(length=255), nullable=True),
        sa.Column("code", sa.String(length=150), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("target_run_type", sa.String(length=100), nullable=False),
        sa.Column("scope_portfolio_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("model_version_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("environment_id", sa.String(length=100), nullable=False),
        sa.Column("cadence_kind", sa.String(length=20), nullable=False),
        sa.Column("interval_days", sa.Integer(), nullable=False),
        sa.Column("anchor_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("record_version", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_schedule"),
        sa.ForeignKeyConstraint(
            ["scope_portfolio_id"], ["portfolio.id"],
            name="fk_schedule_scope_portfolio_id_portfolio",
        ),
        sa.ForeignKeyConstraint(
            ["model_version_id"], ["model_version.id"],
            name="fk_schedule_model_version_id_model_version",
        ),
        sa.UniqueConstraint("tenant_id", "code", name="uq_schedule_tenant_code"),
    )
    op.create_index("ix_schedule_tenant_id", "schedule", ["tenant_id"])
    op.create_index("ix_schedule_scope_portfolio_id", "schedule", ["scope_portfolio_id"])
    op.create_index("ix_schedule_model_version_id", "schedule", ["model_version_id"])

    # --- ENT-062 scheduled_run (IA TRUE append-only ledger; one row per fired grid tick) ---
    op.create_table(
        "scheduled_run",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("system_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("schedule_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("scheduled_for", sa.DateTime(timezone=True), nullable=False),
        sa.Column("fired_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("calculation_run_id", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("resolved_exposure_run_id", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("resolved_covariance_run_id", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("outcome", sa.String(length=20), nullable=False),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_scheduled_run"),
        sa.ForeignKeyConstraint(
            ["schedule_id"], ["schedule.id"],
            name="fk_scheduled_run_schedule_id_schedule",
        ),
        sa.ForeignKeyConstraint(
            ["calculation_run_id"], ["calculation_run.run_id"],
            name="fk_scheduled_run_calculation_run_id_calculation_run",
        ),
        sa.UniqueConstraint(
            "schedule_id", "scheduled_for", name="uq_scheduled_run_schedule_tick"
        ),
    )
    op.create_index("ix_scheduled_run_tenant_id", "scheduled_run", ["tenant_id"])
    op.create_index("ix_scheduled_run_schedule_id", "scheduled_run", ["schedule_id"])
    op.create_index(
        "ix_scheduled_run_calculation_run_id", "scheduled_run", ["calculation_run_id"]
    )

    # --- symmetric FORCE RLS on both (PROPRIETARY; NO ops-role grant — OQ-1=B) ---
    for table in TENANT_SCOPED_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY tenant_isolation_{table} ON {table} "
            f"USING (tenant_id::text = current_setting('app.current_tenant', true)) "
            f"WITH CHECK (tenant_id::text = current_setting('app.current_tenant', true))"
        )

    # --- append-only trigger on scheduled_run ONLY (reuses the 0001 P0001 function) ---
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
    op.drop_table("scheduled_run")
    op.drop_table("schedule")
