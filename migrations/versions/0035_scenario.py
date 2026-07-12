"""P3-6: scenario_definition + scenario_shock + scenario_result (ENT-029/030 — the tenth governed number).

Three cohesive stress/scenario tables, all tenant-scoped PROPRIETARY under the **SYMMETRIC**
tenant-isolation RLS loop (``USING == WITH CHECK == own-tenant``) — the 0009..0034 pattern; NOT
hybrid, no SYSTEM_TENANT.

- ``scenario_definition`` (ENT-029, **EV**) — versioned saved scenario header (BR-8); valid-time
  only, ``record_version``; NOT append-only (the ``factor`` EV precedent).
- ``scenario_shock`` (ENT-029 detail, **FR bitemporal**) — one signed shock per (definition,
  factor); full both-axes history + close-out UPDATEs; NOT append-only (the ``proxy_mapping``
  precedent); current-head partial-unique on (tenant, definition, factor) WHERE both axes open.
- ``scenario_result`` (ENT-030, **IA TRUE append-only**) — deterministic factor-shock P&L; in this
  migration's ``APPEND_ONLY_TABLES`` -> the ``irp_prevent_mutation`` P0001 trigger (reusing the 0001
  function) + the ORM guard. Run-bound + snapshot-gated + model-bound (NOT-NULL FKs).

No new audit code (``RISK.SCENARIO_CREATE`` RESERVED, not minted; the run reuses ``CALC.RUN_*``);
NO new permission (``risk.run``/``risk.view`` REUSED); no schema change for ``SCENARIO_INPUT`` /
``COMPONENT_KIND_SCENARIO`` (unconstrained app-constant strings). ``PreciseDecimal`` renders
``NUMERIC(p,s)`` on PG. Every DDL identifier <= 63 chars (asserted below — the 0032/0033 lesson).

Revision ID: 0035_scenario
Revises: 0034_proxy_mapping
Create Date: 2026-07-12
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0035_scenario"
down_revision: str | None = "0034_proxy_mapping"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: Symmetric tenant-isolation (NOT hybrid) — all three tables.
TENANT_SCOPED_TABLES = ("scenario_definition", "scenario_shock", "scenario_result")
#: Truly immutable append-only — the RESULT only (the definition/shock are EV/FR, revisable).
APPEND_ONLY_TABLES = ("scenario_result",)

#: The 0032/0033 lesson, made structural: every name this migration mints, checked at import time
#: (the MD-H1 repo-wide sweep also validates it — belt and braces).
_IDENTIFIERS = (
    "scenario_definition",
    "pk_scenario_definition",
    "uq_scenario_definition_tenant_code",
    "ix_scenario_definition_tenant_id",
    "tenant_isolation_scenario_definition",
    "scenario_shock",
    "pk_scenario_shock",
    "fk_scenario_shock_scenario_definition_id_scenario_definition",
    "fk_scenario_shock_factor_id_factor",
    "fk_scenario_shock_supersedes_id_scenario_shock",
    "uq_scenario_shock_current",
    "ix_scenario_shock_tenant_id",
    "ix_scenario_shock_scenario_definition_id",
    "ix_scenario_shock_factor_id",
    "tenant_isolation_scenario_shock",
    "scenario_result",
    "pk_scenario_result",
    "fk_scenario_result_calculation_run_id_calculation_run",
    "fk_scenario_result_input_snapshot_id_dataset_snapshot",
    "fk_scenario_result_model_version_id_model_version",
    "uq_scenario_result_run_grain",
    "ix_scenario_result_tenant_id",
    "ix_scenario_result_calculation_run_id",
    "ix_scenario_result_input_snapshot_id",
    "ix_scenario_result_model_version_id",
    "tenant_isolation_scenario_result",
    "scenario_result_append_only",
)
assert all(len(name) <= 63 for name in _IDENTIFIERS), [
    name for name in _IDENTIFIERS if len(name) > 63
]


def _timestamp_columns() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(length=255), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by", sa.String(length=255), nullable=True),
    ]


def upgrade() -> None:
    # --- scenario_definition (EV) ---
    op.create_table(
        "scenario_definition",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_to", sa.DateTime(timezone=True), nullable=True),
        *_timestamp_columns(),
        sa.Column("code", sa.String(length=150), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("scenario_type", sa.String(length=20), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column("record_version", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_scenario_definition"),
        sa.UniqueConstraint("tenant_id", "code", name="uq_scenario_definition_tenant_code"),
    )
    op.create_index("ix_scenario_definition_tenant_id", "scenario_definition", ["tenant_id"])

    # --- scenario_shock (FR bitemporal) ---
    op.create_table(
        "scenario_shock",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("system_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("system_to", sa.DateTime(timezone=True), nullable=True),
        *_timestamp_columns(),
        sa.Column("scenario_definition_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("factor_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("shock_value", sa.Numeric(precision=20, scale=12), nullable=False),
        sa.Column("shock_type", sa.String(length=20), nullable=False),
        sa.Column("restatement_reason", sa.String(length=255), nullable=True),
        sa.Column("supersedes_id", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("record_version", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_scenario_shock"),
        sa.ForeignKeyConstraint(
            ["scenario_definition_id"],
            ["scenario_definition.id"],
            name="fk_scenario_shock_scenario_definition_id_scenario_definition",
        ),
        sa.ForeignKeyConstraint(
            ["factor_id"], ["factor.id"], name="fk_scenario_shock_factor_id_factor"
        ),
        sa.ForeignKeyConstraint(
            ["supersedes_id"],
            ["scenario_shock.id"],
            name="fk_scenario_shock_supersedes_id_scenario_shock",
        ),
    )
    op.create_index("ix_scenario_shock_tenant_id", "scenario_shock", ["tenant_id"])
    op.create_index(
        "ix_scenario_shock_scenario_definition_id", "scenario_shock", ["scenario_definition_id"]
    )
    op.create_index("ix_scenario_shock_factor_id", "scenario_shock", ["factor_id"])
    op.create_index(
        "uq_scenario_shock_current",
        "scenario_shock",
        ["tenant_id", "scenario_definition_id", "factor_id"],
        unique=True,
        postgresql_where=sa.text("valid_to IS NULL AND system_to IS NULL"),
    )

    # --- scenario_result (IA append-only) ---
    op.create_table(
        "scenario_result",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("system_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("calculation_run_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("input_snapshot_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("model_version_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("scenario_definition_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("scenario_code", sa.String(length=150), nullable=False),
        sa.Column("metric_type", sa.String(length=30), nullable=False),
        sa.Column("factor_id", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("factor_code", sa.String(length=150), nullable=True),
        sa.Column("factor_family", sa.String(length=30), nullable=True),
        sa.Column("pnl", sa.Numeric(28, 6), nullable=False),
        sa.Column("shock_value", sa.Numeric(precision=20, scale=12), nullable=True),
        sa.Column("exposure_amount", sa.Numeric(28, 6), nullable=True),
        sa.Column("n_factors_exposed", sa.Integer(), nullable=True),
        sa.Column("n_factors_shocked", sa.Integer(), nullable=True),
        sa.Column("n_shocks_unmatched", sa.Integer(), nullable=True),
        sa.Column("base_currency", sa.String(length=3), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_scenario_result"),
        sa.ForeignKeyConstraint(
            ["calculation_run_id"],
            ["calculation_run.run_id"],
            name="fk_scenario_result_calculation_run_id_calculation_run",
        ),
        sa.ForeignKeyConstraint(
            ["input_snapshot_id"],
            ["dataset_snapshot.id"],
            name="fk_scenario_result_input_snapshot_id_dataset_snapshot",
        ),
        sa.ForeignKeyConstraint(
            ["model_version_id"],
            ["model_version.id"],
            name="fk_scenario_result_model_version_id_model_version",
        ),
        sa.UniqueConstraint(
            "calculation_run_id",
            "metric_type",
            "factor_id",
            name="uq_scenario_result_run_grain",
        ),
    )
    op.create_index("ix_scenario_result_tenant_id", "scenario_result", ["tenant_id"])
    op.create_index(
        "ix_scenario_result_calculation_run_id", "scenario_result", ["calculation_run_id"]
    )
    op.create_index(
        "ix_scenario_result_input_snapshot_id", "scenario_result", ["input_snapshot_id"]
    )
    op.create_index(
        "ix_scenario_result_model_version_id", "scenario_result", ["model_version_id"]
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

    # --- Append-only: the RESULT only (IA); reuse the 0001 irp_prevent_mutation function.
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
    op.drop_table("scenario_result")
    op.drop_table("scenario_shock")
    op.drop_table("scenario_definition")
