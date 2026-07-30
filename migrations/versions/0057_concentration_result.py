"""CON-1 (Wave-14 slice 1): ENT-069 ``concentration_result`` — the 23rd governed number family.

The ratified v6 grain (CON-1 decision record, OQ-CON-1-23): ``row_kind`` discriminator + a single
always-filled ``bucket_code`` key (dunder sentinels), TWO PARTIAL unique indexes with stated
predicates, row-kind-qualified CHECKs (summary = the nine summary names, ``SHARE`` refused;
``scheme_id`` echo decided by name-AND-dimension; a real ISSUER bucket carries its issuer FK).
Symmetric FORCE RLS (proprietary — NEVER hybrid); IA true append-only via the 0001
``irp_prevent_mutation`` P0001 trigger.

**Downgrade, specified at the gate (the SCH-2 zero-rows lesson made it mandatory scope):** drop
the trigger, the policy, then the table — children before parents; the partial indexes and CHECKs
ride the table drop; NO permission rows ride this migration (the R-07 mint lands via bootstrap).
Honestly destructive: every concentration row (IA governed evidence) is dropped, and the P4 dry
run proves the drop destructive with rows STAGED, never against an empty table.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0057_concentration_result"
down_revision: str | None = "0056_classification"
branch_labels: str | None = None
depends_on: str | None = None

#: Proprietary/symmetric — the SYSTEM literal must never touch this table.
TENANT_SCOPED_TABLES: tuple[str, ...] = ("concentration_result",)
#: IA true append-only — the 0001 trigger function is reused, never redefined.
APPEND_ONLY_TABLES: tuple[str, ...] = ("concentration_result",)

#: The nine summary metric names + the classification six (mirrors the ORM CHECK text exactly —
#: frozen literals, never imported from application constants (the shared-constant landmine)).
_SUMMARY_METRICS = (
    "'MAX_SHARE_ISSUER', 'MAX_SHARE_SECTOR_INDUSTRY', 'MAX_SHARE_COUNTRY_OF_RISK', "
    "'HHI_ISSUER', 'HHI_SECTOR_INDUSTRY', 'HHI_COUNTRY_OF_RISK', "
    "'CR_5_ISSUER', 'CR_5_SECTOR_INDUSTRY', 'CR_5_COUNTRY_OF_RISK'"
)
_CLASSIFICATION_SUMMARY = (
    "'MAX_SHARE_SECTOR_INDUSTRY', 'MAX_SHARE_COUNTRY_OF_RISK', "
    "'HHI_SECTOR_INDUSTRY', 'HHI_COUNTRY_OF_RISK', "
    "'CR_5_SECTOR_INDUSTRY', 'CR_5_COUNTRY_OF_RISK'"
)

#: Every DDL identifier this migration mints — asserted ≤ 63 at import (the P3-8/BT-1 lesson).
_IDENTIFIERS = (
    "concentration_result",
    "pk_concentration_result",
    "uq_concentration_summary",
    "uq_concentration_detail",
    "ck_concentration_result_row_kind",
    "ck_concentration_result_summary_shape",
    "ck_concentration_result_detail_shape",
    "ck_concentration_result_issuer_bucket",
    "ck_concentration_result_dimension_kind",
    "fk_concentration_result_calculation_run_id_calculation_run",
    "fk_concentration_result_input_snapshot_id_dataset_snapshot",
    "fk_concentration_result_model_version_id_model_version",
    "fk_concentration_result_issuer_id_issuer",
    "ix_concentration_result_tenant_id",
    "ix_concentration_result_calculation_run_id",
    "ix_concentration_result_input_snapshot_id",
    "ix_concentration_result_model_version_id",
    "ix_concentration_result_portfolio_id",
    "ix_concentration_result_issuer_id",
    "concentration_result_append_only",
    "tenant_isolation_concentration_result",
)
assert all(len(name) <= 63 for name in _IDENTIFIERS), [
    name for name in _IDENTIFIERS if len(name) > 63
]


def upgrade() -> None:
    op.create_table(
        "concentration_result",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("system_from", sa.DateTime(timezone=True), nullable=False),
        # Run-bound + snapshot-gated + model-bound (AD-014 at the DB).
        sa.Column("calculation_run_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("input_snapshot_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("model_version_id", postgresql.UUID(as_uuid=False), nullable=False),
        # The run's aggregation scope (= the upstream run's scope_portfolio_id; NULL-scope
        # upstream runs are refused PRE-BUILD). No FK — the exposure_aggregate precedent.
        sa.Column("portfolio_id", postgresql.UUID(as_uuid=False), nullable=False),
        # The grain: every key column NOT NULL (the NULL-vacuity class is structurally gone).
        sa.Column("row_kind", sa.String(length=10), nullable=False),
        sa.Column("dimension_kind", sa.String(length=30), nullable=False),
        sa.Column("metric_type", sa.String(length=30), nullable=False),
        sa.Column("bucket_code", sa.String(length=100), nullable=False),
        # Echoes OUTSIDE the keys. issuer: same-tenant proprietary FK. scheme: HYBRID — NO FK
        # (PostgreSQL referential checks bypass RLS; the OQ-CON-1-14 refusal).
        sa.Column("issuer_id", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("scheme_id", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("basis", sa.String(length=50), nullable=False),
        sa.Column("denominator_basis", sa.String(length=30), nullable=False),
        # Kernel-computed evidence from the signed atoms (LONG = exposure_amount > 0).
        sa.Column("gross_amount", sa.Numeric(precision=28, scale=6), nullable=False),
        sa.Column("long_amount", sa.Numeric(precision=28, scale=6), nullable=False),
        sa.Column("short_amount", sa.Numeric(precision=28, scale=6), nullable=False),
        sa.Column("net_amount", sa.Numeric(precision=28, scale=6), nullable=False),
        sa.Column("share_invested_long", sa.Numeric(precision=20, scale=6), nullable=True),
        sa.Column("metric_value", sa.Numeric(precision=20, scale=6), nullable=True),
        # The per-dimension coverage pair (SUMMARY rows only).
        sa.Column("coverage_ratio", sa.Numeric(precision=20, scale=6), nullable=True),
        sa.Column("coverage_classifiable", sa.Numeric(precision=20, scale=6), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_concentration_result"),
        sa.ForeignKeyConstraint(
            ["calculation_run_id"],
            ["calculation_run.run_id"],
            name="fk_concentration_result_calculation_run_id_calculation_run",
        ),
        sa.ForeignKeyConstraint(
            ["input_snapshot_id"],
            ["dataset_snapshot.id"],
            name="fk_concentration_result_input_snapshot_id_dataset_snapshot",
        ),
        sa.ForeignKeyConstraint(
            ["model_version_id"],
            ["model_version.id"],
            name="fk_concentration_result_model_version_id_model_version",
        ),
        sa.ForeignKeyConstraint(
            ["issuer_id"], ["issuer.id"], name="fk_concentration_result_issuer_id_issuer"
        ),
        # Row-kind census (fails CLOSED for an unenumerated kind).
        sa.CheckConstraint(
            "row_kind IN ('DETAIL', 'SUMMARY')",
            name="ck_concentration_result_row_kind",
        ),
        # SUMMARY shape: sentinel bucket, no issuer identity, the NINE names (SHARE refused),
        # scheme echo by name (classification six NOT NULL, issuer trio NULL).
        sa.CheckConstraint(
            "row_kind != 'SUMMARY' OR ("
            "bucket_code = '__SUMMARY__' AND issuer_id IS NULL "
            f"AND metric_type IN ({_SUMMARY_METRICS}) "
            f"AND ((metric_type IN ({_CLASSIFICATION_SUMMARY})) = (scheme_id IS NOT NULL))"
            ")",
            name="ck_concentration_result_summary_shape",
        ),
        # DETAIL shape: SHARE only; scheme echo by dimension.
        sa.CheckConstraint(
            "row_kind != 'DETAIL' OR ("
            "metric_type = 'SHARE' AND bucket_code != '__SUMMARY__' "
            "AND ((dimension_kind = 'ISSUER') = (scheme_id IS NULL))"
            ")",
            name="ck_concentration_result_detail_shape",
        ),
        # A real ISSUER bucket carries its issuer FK (residual sentinels exempt).
        sa.CheckConstraint(
            "NOT (row_kind = 'DETAIL' AND dimension_kind = 'ISSUER' "
            "AND bucket_code NOT IN ('__UNCLASSIFIED__', '__UNCLASSIFIABLE__')) "
            "OR issuer_id IS NOT NULL",
            name="ck_concentration_result_issuer_bucket",
        ),
        sa.CheckConstraint(
            "dimension_kind IN ('ISSUER', 'SECTOR_INDUSTRY', 'COUNTRY_OF_RISK')",
            name="ck_concentration_result_dimension_kind",
        ),
    )
    op.create_index("ix_concentration_result_tenant_id", "concentration_result", ["tenant_id"])
    for column in (
        "calculation_run_id",
        "input_snapshot_id",
        "model_version_id",
        "portfolio_id",
        "issuer_id",
    ):
        op.create_index(f"ix_concentration_result_{column}", "concentration_result", [column])
    # THE TWO RATIFIED GRAINS — partial unique indexes, predicates stated (OQ-CON-1-23).
    op.create_index(
        "uq_concentration_summary",
        "concentration_result",
        ["calculation_run_id", "metric_type"],
        unique=True,
        postgresql_where=sa.text("row_kind = 'SUMMARY'"),
    )
    op.create_index(
        "uq_concentration_detail",
        "concentration_result",
        ["calculation_run_id", "dimension_kind", "bucket_code"],
        unique=True,
        postgresql_where=sa.text("row_kind = 'DETAIL'"),
    )

    # --- Tenant isolation: SYMMETRIC RLS (USING == WITH CHECK == own-tenant); NOT hybrid.
    for table in TENANT_SCOPED_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY tenant_isolation_{table} ON {table} "
            f"USING (tenant_id::text = current_setting('app.current_tenant', true)) "
            f"WITH CHECK (tenant_id::text = current_setting('app.current_tenant', true))"
        )

    # --- Append-only: truly immutable IA table, reuse the 0001 function.
    for table in APPEND_ONLY_TABLES:
        op.execute(
            f"CREATE TRIGGER {table}_append_only BEFORE UPDATE OR DELETE ON {table} "
            f"FOR EACH ROW EXECUTE FUNCTION irp_prevent_mutation()"
        )


def downgrade() -> None:
    # The ratified downgrade body: trigger, policy, table — children before parents; DROP TABLE
    # is DDL, not a row mutation, so the append-only trigger never fires (the SCH-2 doctrine).
    for table in APPEND_ONLY_TABLES:
        op.execute(f"DROP TRIGGER IF EXISTS {table}_append_only ON {table}")
    for table in TENANT_SCOPED_TABLES:
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation_{table} ON {table}")
    op.drop_table("concentration_result")
