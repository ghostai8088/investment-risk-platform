"""P2-7: benchmark_level + benchmark_return (FR bitemporal captured index level / return series) —
ENT-052, the net-new canonical id realized under the existing ENT-009 ``benchmark`` EV header.

Both tables are captured-INPUT FR bitemporal series (the ``factor_return`` precedent — capture /
effective-dated supersede / as-known correction; re-versions over time; audited
``MARKET.BENCHMARK_LEVEL_*`` / ``MARKET.BENCHMARK_RETURN_*``). Tenant-scoped PROPRIETARY under the
**SYMMETRIC** tenant-isolation RLS loop (``USING == WITH CHECK == own``) — the SAME pattern as
0009..0023. **NOT hybrid** (vendor benchmark data is per-tenant licensed). The 0008 hybrid loop +
the closed 5-table hybrid set are UNCHANGED.

**NEITHER table is append-only** — both are FR and require close-out UPDATEs to
``valid_to``/``system_to``. So ``APPEND_ONLY_TABLES`` is empty and NO ``irp_prevent_mutation``
trigger is installed (the 0021 benchmark / 0023 factor_return precedent). Content-immutability is
service-enforced + tested.

``benchmark_level`` current-head partial-unique ``(tenant_id, benchmark_id, level_date, level_type)
WHERE valid_to IS NULL AND system_to IS NULL``; ``level_value`` ``Numeric(20, 6)``.
``benchmark_return`` current-head partial-unique ``(tenant_id, benchmark_id, return_date,
return_type, return_basis) WHERE valid_to IS NULL AND system_to IS NULL``; ``return_value``
``Numeric(20, 12)``. Both FK ``benchmark_id -> benchmark.id``. **Captured INPUT only** — NO
``calculation_run``, NO ``model_version``, NO snapshot pin. No new audit code / permission table
(``MARKET.BENCHMARK_LEVEL_*``/``_RETURN_*`` are caller-side constants; ``marketdata.view`` /
``.ingest``
REUSED). ``PreciseDecimal`` renders ``NUMERIC(p,s)`` on PG — no DDL surprise.

Revision ID: 0029_benchmark_series
Revises: 0028_var_historical
Create Date: 2026-07-09
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0029_benchmark_series"
down_revision: str | None = "0028_var_historical"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: Symmetric tenant-isolation (NOT hybrid) — both benchmark-series tables.
TENANT_SCOPED_TABLES = ("benchmark_level", "benchmark_return")
#: NEITHER table is append-only (both FR, close-out UPDATEs). NO irp_prevent_mutation trigger
#: (the 0021 benchmark / 0023 factor_return precedent).
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
    # --- benchmark_level (FR bitemporal captured index-level series) ---
    op.create_table(
        "benchmark_level",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=False), nullable=False),
        *_fr_temporal_columns(),
        *_timestamp_columns(),
        sa.Column("benchmark_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("level_date", sa.Date(), nullable=False),
        sa.Column("level_type", sa.String(length=30), nullable=False),
        sa.Column("level_value", sa.Numeric(precision=20, scale=6), nullable=False),
        sa.Column("restatement_reason", sa.String(length=255), nullable=True),
        sa.Column("supersedes_id", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("record_version", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_benchmark_level"),
        sa.ForeignKeyConstraint(
            ["benchmark_id"], ["benchmark.id"], name="fk_benchmark_level_benchmark_id_benchmark"
        ),
        sa.ForeignKeyConstraint(
            ["supersedes_id"],
            ["benchmark_level.id"],
            name="fk_benchmark_level_supersedes_id_benchmark_level",
        ),
    )
    op.create_index("ix_benchmark_level_tenant_id", "benchmark_level", ["tenant_id"])
    op.create_index("ix_benchmark_level_benchmark_id", "benchmark_level", ["benchmark_id"])
    op.create_index("ix_benchmark_level_level_date", "benchmark_level", ["level_date"])
    op.create_index(
        "uq_benchmark_level_current",
        "benchmark_level",
        ["tenant_id", "benchmark_id", "level_date", "level_type"],
        unique=True,
        postgresql_where=sa.text("valid_to IS NULL AND system_to IS NULL"),
    )

    # --- benchmark_return (FR bitemporal captured vendor-published-return series) ---
    op.create_table(
        "benchmark_return",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=False), nullable=False),
        *_fr_temporal_columns(),
        *_timestamp_columns(),
        sa.Column("benchmark_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("return_date", sa.Date(), nullable=False),
        sa.Column("return_type", sa.String(length=20), nullable=False),
        sa.Column("return_basis", sa.String(length=20), nullable=False),
        sa.Column("return_value", sa.Numeric(precision=20, scale=12), nullable=False),
        sa.Column("restatement_reason", sa.String(length=255), nullable=True),
        sa.Column("supersedes_id", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("record_version", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_benchmark_return"),
        sa.ForeignKeyConstraint(
            ["benchmark_id"], ["benchmark.id"], name="fk_benchmark_return_benchmark_id_benchmark"
        ),
        sa.ForeignKeyConstraint(
            ["supersedes_id"],
            ["benchmark_return.id"],
            name="fk_benchmark_return_supersedes_id_benchmark_return",
        ),
    )
    op.create_index("ix_benchmark_return_tenant_id", "benchmark_return", ["tenant_id"])
    op.create_index("ix_benchmark_return_benchmark_id", "benchmark_return", ["benchmark_id"])
    op.create_index("ix_benchmark_return_return_date", "benchmark_return", ["return_date"])
    op.create_index(
        "uq_benchmark_return_current",
        "benchmark_return",
        ["tenant_id", "benchmark_id", "return_date", "return_type", "return_basis"],
        unique=True,
        postgresql_where=sa.text("valid_to IS NULL AND system_to IS NULL"),
    )

    # --- Tenant isolation: SYMMETRIC RLS (USING == WITH CHECK == own-tenant); NOT hybrid (BR-17)
    for table in TENANT_SCOPED_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY tenant_isolation_{table} ON {table} "
            f"USING (tenant_id::text = current_setting('app.current_tenant', true)) "
            f"WITH CHECK (tenant_id::text = current_setting('app.current_tenant', true))"
        )

    # --- NO append-only trigger: both tables are FR (NOT append-only) — APPEND_ONLY_TABLES empty.
    for table in APPEND_ONLY_TABLES:  # pragma: no cover - empty in P2-7
        op.execute(
            f"CREATE TRIGGER {table}_append_only BEFORE UPDATE OR DELETE ON {table} "
            f"FOR EACH ROW EXECUTE FUNCTION irp_prevent_mutation()"
        )


def downgrade() -> None:
    for table in APPEND_ONLY_TABLES:  # pragma: no cover - empty in P2-7
        op.execute(f"DROP TRIGGER IF EXISTS {table}_append_only ON {table}")
    for table in TENANT_SCOPED_TABLES:
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation_{table} ON {table}")
    op.drop_table("benchmark_return")
    op.drop_table("benchmark_level")
