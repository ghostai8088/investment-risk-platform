"""DATA-1: benchmark_rate (FR bitemporal captured PUBLISHED-RATE series) — ENT-070, the third
series-observation table under the existing ENT-009 ``benchmark`` EV header — plus the header's
DECLARED rate-series coverage horizon ``benchmark.rates_complete_through``.

``benchmark_rate`` is a captured-INPUT FR bitemporal series (the 0029 ``benchmark_level``/
``benchmark_return`` pattern verbatim: capture / effective-dated supersede / as-known correction;
audited ``MARKET.BENCHMARK_RATE_*`` — caller-side constants, the R-07 mint recorded in the
taxonomy row). The vendor's annualized rate captured VERBATIM as a decimal fraction — NEVER
re-expressed into a period return (the annualized→period conversion is a registered-model carry,
OQ-DATA-1-1). Tenant-scoped PROPRIETARY under the **SYMMETRIC** tenant-isolation RLS loop
(``USING == WITH CHECK == own``); **NOT hybrid** (per-tenant capture even of a public-domain
series — the ratified OQ-DATA-1-2 tenancy; the closed 7-table hybrid set is UNCHANGED).

**NOT append-only** — FR requires close-out UPDATEs (``APPEND_ONLY_TABLES`` empty, NO
``irp_prevent_mutation`` trigger; the 0029 precedent). Current-head partial-unique
``(tenant_id, benchmark_id, rate_date, rate_type, quote_basis) WHERE valid_to IS NULL AND
system_to IS NULL``; ``rate_value`` ``Numeric(20, 12)``. ``rates_complete_through`` is a nullable
``Date`` on ``benchmark`` — the DECLARED coverage horizon, forward-only via the verb (a derived
MAX cannot represent a gap). Captured INPUT only — NO ``calculation_run``, NO ``model_version``,
NO snapshot pin. No new permission (``marketdata.view``/``.ingest`` REUSED).

Revision ID: 0060_benchmark_rate
Revises: 0059_business_month_end
Create Date: 2026-08-02
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0060_benchmark_rate"
down_revision: str | None = "0059_business_month_end"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: Symmetric tenant-isolation (NOT hybrid) — the new rate-series table.
TENANT_SCOPED_TABLES = ("benchmark_rate",)
#: NOT append-only (FR, close-out UPDATEs). NO irp_prevent_mutation trigger (the 0029 precedent).
APPEND_ONLY_TABLES: tuple[str, ...] = ()


def _timestamp_columns() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(length=255), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by", sa.String(length=255), nullable=True),
    ]


def _fr_temporal_columns() -> list[sa.Column]:
    return [
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("system_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("system_to", sa.DateTime(timezone=True), nullable=True),
    ]


def upgrade() -> None:
    # --- benchmark_rate (FR bitemporal captured published-rate series, ENT-070) ---
    op.create_table(
        "benchmark_rate",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=False), nullable=False),
        *_fr_temporal_columns(),
        *_timestamp_columns(),
        sa.Column("benchmark_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("rate_date", sa.Date(), nullable=False),
        sa.Column("rate_type", sa.String(length=30), nullable=False),
        sa.Column("quote_basis", sa.String(length=20), nullable=False),
        sa.Column("observation_convention", sa.String(length=40), nullable=False),
        sa.Column("rate_value", sa.Numeric(precision=20, scale=12), nullable=False),
        sa.Column("restatement_reason", sa.String(length=255), nullable=True),
        sa.Column("supersedes_id", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("record_version", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_benchmark_rate"),
        sa.ForeignKeyConstraint(
            ["benchmark_id"], ["benchmark.id"], name="fk_benchmark_rate_benchmark_id_benchmark"
        ),
        sa.ForeignKeyConstraint(
            ["supersedes_id"],
            ["benchmark_rate.id"],
            name="fk_benchmark_rate_supersedes_id_benchmark_rate",
        ),
    )
    op.create_index("ix_benchmark_rate_tenant_id", "benchmark_rate", ["tenant_id"])
    op.create_index("ix_benchmark_rate_benchmark_id", "benchmark_rate", ["benchmark_id"])
    op.create_index("ix_benchmark_rate_rate_date", "benchmark_rate", ["rate_date"])
    op.create_index(
        "uq_benchmark_rate_current",
        "benchmark_rate",
        ["tenant_id", "benchmark_id", "rate_date", "rate_type", "quote_basis"],
        unique=True,
        postgresql_where=sa.text("valid_to IS NULL AND system_to IS NULL"),
    )

    # --- the header's DECLARED rate-series coverage horizon (nullable; forward-only via the verb)
    op.add_column("benchmark", sa.Column("rates_complete_through", sa.Date(), nullable=True))

    # --- Tenant isolation: SYMMETRIC RLS (USING == WITH CHECK == own-tenant); NOT hybrid (BR-17)
    for table in TENANT_SCOPED_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY tenant_isolation_{table} ON {table} "
            f"USING (tenant_id::text = current_setting('app.current_tenant', true)) "
            f"WITH CHECK (tenant_id::text = current_setting('app.current_tenant', true))"
        )

    # --- NO append-only trigger: FR (NOT append-only) — APPEND_ONLY_TABLES empty.
    for table in APPEND_ONLY_TABLES:  # pragma: no cover - empty in DATA-1
        op.execute(
            f"CREATE TRIGGER {table}_append_only BEFORE UPDATE OR DELETE ON {table} "
            f"FOR EACH ROW EXECUTE FUNCTION irp_prevent_mutation()"
        )


def downgrade() -> None:
    for table in APPEND_ONLY_TABLES:  # pragma: no cover - empty in DATA-1
        op.execute(f"DROP TRIGGER IF EXISTS {table}_append_only ON {table}")
    for table in TENANT_SCOPED_TABLES:
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation_{table} ON {table}")
    op.drop_column("benchmark", "rates_complete_through")
    op.drop_table("benchmark_rate")
