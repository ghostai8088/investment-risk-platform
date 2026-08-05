"""ENT-072 ``report_generation`` — the durable record of one generated risk report (RPT-1).

Symmetric per-tenant FORCE RLS (a report is proprietary: it names a book's risk position), plus the
``irp_prevent_mutation`` P0001 trigger reused from 0001 — a generated report is governed EVIDENCE of
what was shown, on what basis, when, so UPDATE and DELETE are refused at the database, not merely in
the ORM.

The single UNIQUE key is fully NOT NULL. A nullable column inside a UNIQUE key is VACUOUS on
PostgreSQL (NULLS DISTINCT) — the defect CON-1 shipped and CAL-1b re-found — so both key columns are
NOT NULL by declaration, and the SQLite tier builds the same index via ``create_all``.

Revision id kept SHORT deliberately: ``alembic_version.version_num`` is varchar(32) and a longer id
fails at the INSERT, not at parse — the trap 0062 caught by execution.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0063_report_generation"  # 22 chars, well inside varchar(32)
down_revision: str | None = "0062_concentration_denom_check"
branch_labels: None = None
depends_on: None = None

TENANT_SCOPED_TABLES = ("report_generation",)
APPEND_ONLY_TABLES = ("report_generation",)


def upgrade() -> None:
    op.create_table(
        "report_generation",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), nullable=False, index=True),
        sa.Column(
            "calculation_run_id",
            sa.Uuid(),
            sa.ForeignKey("calculation_run.run_id"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "input_snapshot_id",
            sa.Uuid(),
            sa.ForeignKey("dataset_snapshot.id"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "portfolio_id", sa.Uuid(), sa.ForeignKey("portfolio.id"), nullable=False, index=True
        ),
        sa.Column("report_code", sa.String(length=100), nullable=False),
        sa.Column("report_version_label", sa.String(length=50), nullable=False),
        sa.Column("render_format", sa.String(length=20), nullable=False),
        sa.Column("as_of_date", sa.Date(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("generated_by", sa.String(length=200), nullable=False),
        # ImmutableAppendOnlyMixin records ONLY system (knowledge) time — no record_version, no
        # created_at. `alembic check` caught the first draft declaring those two and omitting this
        # one; the ORM is the authority and the migration follows it, not the reverse.
        sa.Column("system_from", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "uq_report_generation_run_portfolio",
        "report_generation",
        ["calculation_run_id", "portfolio_id"],
        unique=True,
    )
    op.create_index(
        "ix_report_generation_lookup",
        "report_generation",
        ["tenant_id", "report_code", "as_of_date"],
    )

    # --- Tenant isolation: SYMMETRIC RLS (USING == WITH CHECK == own-tenant); NOT hybrid.
    #     A report is proprietary by construction — it states a specific book's risk position.
    for table in TENANT_SCOPED_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY tenant_isolation_{table} ON {table} "
            f"USING (tenant_id::text = current_setting('app.current_tenant', true)) "
            f"WITH CHECK (tenant_id::text = current_setting('app.current_tenant', true))"
        )

    # --- Append-only: a generated report is evidence; reuse the 0001 function.
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
    op.drop_table("report_generation")
