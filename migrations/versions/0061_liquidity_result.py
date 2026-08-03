"""LQ-1 (Wave-14 slice 4): ENT-071 ``liquidity_result`` — the illiquid share of the long book.

The ratified grain (LQ-1 decision record, OQ-LQ-1-6/19): ``row_kind`` discriminator + a single
always-filled ``bucket_code``, TWO PARTIAL unique indexes with stated predicates, row-kind-qualified
CHECKs. Symmetric FORCE RLS (proprietary — NEVER hybrid); IA true append-only via the 0001
``irp_prevent_mutation`` P0001 trigger.

**The detail key includes ``portfolio_id``, unlike 0057's.** CON-1's detail key is
``(run, dimension_kind, bucket_code)`` because a concentration run is single-scope. This family's
key is ``(run, portfolio_id, bucket_code)`` so that a future multi-portfolio run cannot silently
collapse two portfolios' identical tier buckets into one row. Adding the column later would be a
grain change on an append-only table — i.e. not possible without a new family.

**No UNCLASSIFIABLE sentinel exists here** (OQ-LQ-1-19). Unlike CON-1's issuer dimension there is no
upstream edge whose absence makes an instrument structurally unclassifiable, so the only residual is
``__UNCLASSIFIED__`` — and the CHECK below enumerates exactly that, which is what stops a future
caller inventing an excluded bucket and quietly making the coverage floor unfireable.

**Downgrade, specified at the gate:** drop the trigger, the policy, then the table — children before
parents; the partial indexes and CHECKs ride the table drop; NO permission rows ride this migration
(the R-07 mint lands via bootstrap). Honestly destructive: every liquidity row (IA governed
evidence) is dropped, and the P4 dry run proves the drop destructive with rows STAGED, never against
an empty table.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0061_liquidity_result"
down_revision: str | None = "0060_benchmark_rate"
branch_labels: str | None = None
depends_on: str | None = None

#: Proprietary/symmetric — the SYSTEM literal must never touch this table.
TENANT_SCOPED_TABLES: tuple[str, ...] = ("liquidity_result",)
#: IA true append-only — the 0001 trigger function is reused, never redefined.
APPEND_ONLY_TABLES: tuple[str, ...] = ("liquidity_result",)

#: Frozen literals mirroring the ORM vocabularies EXACTLY — never imported from application
#: constants. A migration that imports a live constant silently re-writes history when the constant
#: moves (the shared-constant landmine).
_TIER_CODES = "'HIGHLY_LIQUID', 'MODERATELY_LIQUID', 'LESS_LIQUID', 'ILLIQUID'"
_SUMMARY_METRICS = "'ILLIQUID_SHARE', 'HIGHLY_LIQUID_SHARE'"

#: Every DDL identifier this migration mints — asserted ≤ 63 at import (the P3-8/BT-1 lesson).
#: NOTE the CHECK names below are declared SUFFIX-ONLY in ``sa.CheckConstraint``; the naming
#: convention prepends ``ck_<table>_``, so these entries are the FINAL names and passing a full name
#: to the constraint would mint ``ck_liquidity_result_ck_liquidity_result_<suffix>`` and be
#: PG-truncated at 63 with a hash — the CON-1 defect that only a live-catalog assertion catches.
_IDENTIFIERS = (
    "liquidity_result",
    "pk_liquidity_result",
    "uq_liquidity_result_detail",
    "uq_liquidity_result_summary",
    "ck_liquidity_result_row_kind",
    "ck_liquidity_result_detail_shape",
    "ck_liquidity_result_summary_shape",
    "ck_liquidity_result_denominator_basis",
    "ck_liquidity_result_coverage_only_on_summary",
    "fk_liquidity_result_calculation_run_id_calculation_run",
    "fk_liquidity_result_input_snapshot_id_dataset_snapshot",
    "fk_liquidity_result_model_version_id_model_version",
    "ix_liquidity_result_tenant_id",
    "ix_liquidity_result_calculation_run_id",
    "ix_liquidity_result_input_snapshot_id",
    "ix_liquidity_result_model_version_id",
    "ix_liquidity_result_portfolio_id",
    "liquidity_result_append_only",
    "tenant_isolation_liquidity_result",
)
assert all(len(name) <= 63 for name in _IDENTIFIERS), [
    name for name in _IDENTIFIERS if len(name) > 63
]


def upgrade() -> None:
    op.create_table(
        "liquidity_result",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("system_from", sa.DateTime(timezone=True), nullable=False),
        # Run-bound + snapshot-gated + model-bound (AD-014 at the DB, not merely in the binder).
        sa.Column("calculation_run_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("input_snapshot_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("model_version_id", postgresql.UUID(as_uuid=False), nullable=False),
        # The run's aggregation scope. No FK — the exposure_aggregate precedent.
        sa.Column("portfolio_id", postgresql.UUID(as_uuid=False), nullable=False),
        # The grain: every key column NOT NULL (a nullable column inside a UNIQUE key is VACUOUS on
        # PostgreSQL under NULLS DISTINCT — the CON-1 v3 defect).
        sa.Column("row_kind", sa.String(length=10), nullable=False),
        sa.Column("bucket_code", sa.String(length=100), nullable=False),
        sa.Column("metric_type", sa.String(length=30), nullable=False),
        # The ladder echo. HYBRID table — NO FK (referential checks bypass RLS, the CON-1 OQ-14
        # refusal).
        sa.Column("scheme_id", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("denominator_basis", sa.String(length=30), nullable=False),
        # Kernel-computed evidence (LONG = exposure_amount > 0).
        sa.Column("long_amount", sa.Numeric(precision=28, scale=6), nullable=False),
        sa.Column("tier_share", sa.Numeric(precision=20, scale=6), nullable=True),
        sa.Column("metric_value", sa.Numeric(precision=20, scale=6), nullable=True),
        sa.Column("coverage_ratio", sa.Numeric(precision=20, scale=6), nullable=True),
        sa.Column("coverage_classifiable", sa.Numeric(precision=28, scale=6), nullable=True),
        sa.Column("untiered_instrument_count", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_liquidity_result"),
        sa.ForeignKeyConstraint(
            ["calculation_run_id"],
            ["calculation_run.run_id"],
            name="fk_liquidity_result_calculation_run_id_calculation_run",
        ),
        sa.ForeignKeyConstraint(
            ["input_snapshot_id"],
            ["dataset_snapshot.id"],
            name="fk_liquidity_result_input_snapshot_id_dataset_snapshot",
        ),
        sa.ForeignKeyConstraint(
            ["model_version_id"],
            ["model_version.id"],
            name="fk_liquidity_result_model_version_id_model_version",
        ),
        # Row-kind census (fails CLOSED for an unenumerated kind).
        sa.CheckConstraint(
            "row_kind IN ('DETAIL', 'SUMMARY')",
            name="row_kind",  # SUFFIX ONLY — the convention prepends ck_<table>_
        ),
        # DETAIL shape: a real tier code OR the single residual sentinel — and NOTHING else. This
        # is what stops a future caller inventing an excluded residual bucket and thereby making
        # the coverage floor unfireable (OQ-LQ-1-19).
        sa.CheckConstraint(
            "row_kind != 'DETAIL' OR ("
            "metric_type = 'TIER_SHARE' "
            f"AND bucket_code IN ({_TIER_CODES}, '__UNCLASSIFIED__') "
            "AND tier_share IS NOT NULL AND metric_value IS NULL"
            ")",
            name="detail_shape",  # SUFFIX ONLY
        ),
        # SUMMARY shape: sentinel bucket, one of the two declared metrics, the value present and
        # the DETAIL-only column absent.
        sa.CheckConstraint(
            "row_kind != 'SUMMARY' OR ("
            "bucket_code = '__SUMMARY__' "
            f"AND metric_type IN ({_SUMMARY_METRICS}) "
            "AND metric_value IS NOT NULL AND tier_share IS NULL"
            ")",
            name="summary_shape",  # SUFFIX ONLY
        ),
        # The denominator is single-valued for this family and stated on every row, so a reader
        # never infers which book a share was taken against (OQ-LQ-1-5).
        sa.CheckConstraint(
            "denominator_basis = 'INVESTED_LONG'",
            name="denominator_basis",  # SUFFIX ONLY
        ),
        # Coverage is a SUMMARY-only concept. Without this a DETAIL row could carry a coverage
        # figure that no reader would expect and no test would look for.
        sa.CheckConstraint(
            "row_kind = 'SUMMARY' OR ("
            "coverage_ratio IS NULL AND coverage_classifiable IS NULL "
            "AND untiered_instrument_count IS NULL"
            ")",
            name="coverage_only_on_summary",  # SUFFIX ONLY
        ),
    )
    op.create_index("ix_liquidity_result_tenant_id", "liquidity_result", ["tenant_id"])
    for column in (
        "calculation_run_id",
        "input_snapshot_id",
        "model_version_id",
        "portfolio_id",
    ):
        op.create_index(f"ix_liquidity_result_{column}", "liquidity_result", [column])

    # THE TWO RATIFIED GRAINS — partial unique indexes, predicates stated. portfolio_id is IN both
    # keys (see the module docstring): a multi-portfolio run must not collapse two portfolios'
    # identical tier buckets, and this is not fixable later on an append-only table.
    op.create_index(
        "uq_liquidity_result_detail",
        "liquidity_result",
        ["calculation_run_id", "portfolio_id", "bucket_code"],
        unique=True,
        postgresql_where=sa.text("row_kind = 'DETAIL'"),
    )
    op.create_index(
        "uq_liquidity_result_summary",
        "liquidity_result",
        ["calculation_run_id", "portfolio_id", "metric_type"],
        unique=True,
        postgresql_where=sa.text("row_kind = 'SUMMARY'"),
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
    # Trigger, policy, table — children before parents. DROP TABLE is DDL, not a row mutation, so
    # the append-only trigger never fires (the SCH-2 doctrine).
    for table in APPEND_ONLY_TABLES:
        op.execute(f"DROP TRIGGER IF EXISTS {table}_append_only ON {table}")
    for table in TENANT_SCOPED_TABLES:
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation_{table} ON {table}")
    op.drop_table("liquidity_result")
