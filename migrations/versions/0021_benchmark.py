"""P2-6: benchmark (EV definition header) + benchmark_constituent (FR bitemporal membership) —
ENT-009, the fourth market-data entity (after fx_rate + price_point + curve).

``benchmark`` is an EV effective-dated reference/definition entity (the ``corporate_action``
precedent — entity-versioned in place via ``record_version``; valid time only, no system axis;
audited ``REFERENCE.*``). ``benchmark_constituent`` is the SEVENTH persisted FR bitemporal table
(after instrument_terms / position / valuation / fx_rate / price_point / curve) — the captured
membership that re-versions over time (audited ``MARKET.BENCHMARK_CONSTITUENT_*``). Tenant-scoped
PROPRIETARY under the **SYMMETRIC** tenant-isolation RLS loop (``USING == WITH CHECK == own``)
— the SAME pattern as 0009..0020. **NOT hybrid** (vendor benchmark data is per-tenant
licensed; OD-P2-6-N; a shared-global benchmark *definition* would be an AD-013-R2 event). The 0008
hybrid loop + the closed 5-table hybrid set are UNCHANGED.

**NEITHER table is append-only** — ``benchmark`` (EV) mutates in place (record_version bump);
``benchmark_constituent`` (FR) requires close-out UPDATEs to ``valid_to``/``system_to``. So
``APPEND_ONLY_TABLES`` is empty and NO ``irp_prevent_mutation`` trigger is installed (a deliberate
difference from 0020's ``curve_point``). Content-immutability is service-enforced + tested.

``benchmark`` EV identity ``UNIQUE(tenant_id, benchmark_code, benchmark_source)``;
``benchmark_constituent`` current-head partial-unique ``(tenant_id, benchmark_id, instrument_id,
effective_date) WHERE valid_to IS NULL AND system_to IS NULL``; ``weight`` ``Numeric(20, 12)``. No
new audit code/permission table (``REFERENCE.*``/``MARKET.BENCHMARK_CONSTITUENT_*`` are caller-side
constants; ``marketdata.view``/``.ingest`` REUSED).

Revision ID: 0021_benchmark
Revises: 0020_curves
Create Date: 2026-06-29
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0021_benchmark"
down_revision: str | None = "0020_curves"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: Symmetric tenant-isolation (NOT hybrid) — both benchmark tables.
TENANT_SCOPED_TABLES = ("benchmark", "benchmark_constituent")
#: NEITHER table is append-only — benchmark is EV (in-place), benchmark_constituent is FR (close-out
#: UPDATEs). NO irp_prevent_mutation trigger (a deliberate difference from 0020's curve_point).
APPEND_ONLY_TABLES: tuple[str, ...] = ()


def _timestamp_columns() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(length=255), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by", sa.String(length=255), nullable=True),
    ]


def upgrade() -> None:
    # --- benchmark (EV definition header) — valid time only (no system axis) ---
    op.create_table(
        "benchmark",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_to", sa.DateTime(timezone=True), nullable=True),
        *_timestamp_columns(),
        # Promoted key columns — DB-level NOT NULL (so the EV identity key is not defeasible).
        sa.Column("benchmark_code", sa.String(length=150), nullable=False),
        sa.Column("benchmark_source", sa.String(length=150), nullable=False),
        sa.Column("benchmark_currency", sa.String(length=3), nullable=False),
        sa.Column("benchmark_name", sa.String(length=255), nullable=True),
        sa.Column("index_family", sa.String(length=150), nullable=True),
        sa.Column("vendor_code", sa.String(length=150), nullable=True),
        sa.Column("methodology_label", sa.String(length=150), nullable=True),
        sa.Column("record_version", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_benchmark"),
        sa.UniqueConstraint(
            "tenant_id",
            "benchmark_code",
            "benchmark_source",
            name="uq_benchmark_tenant_code_source",
        ),
    )
    op.create_index("ix_benchmark_tenant_id", "benchmark", ["tenant_id"])

    # --- benchmark_constituent (FR bitemporal membership) ---
    op.create_table(
        "benchmark_constituent",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("system_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("system_to", sa.DateTime(timezone=True), nullable=True),
        *_timestamp_columns(),
        sa.Column("benchmark_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("instrument_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("effective_date", sa.Date(), nullable=False),
        sa.Column("weight", sa.Numeric(precision=20, scale=12), nullable=False),
        sa.Column("constituent_currency", sa.String(length=3), nullable=True),
        sa.Column("restatement_reason", sa.String(length=255), nullable=True),
        sa.Column("supersedes_id", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("record_version", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_benchmark_constituent"),
        sa.ForeignKeyConstraint(
            ["benchmark_id"],
            ["benchmark.id"],
            name="fk_benchmark_constituent_benchmark_id_benchmark",
        ),
        sa.ForeignKeyConstraint(
            ["instrument_id"],
            ["instrument.id"],
            name="fk_benchmark_constituent_instrument_id_instrument",
        ),
        sa.ForeignKeyConstraint(
            ["supersedes_id"],
            ["benchmark_constituent.id"],
            name="fk_benchmark_constituent_supersedes_id_benchmark_constituent",
        ),
    )
    op.create_index("ix_benchmark_constituent_tenant_id", "benchmark_constituent", ["tenant_id"])
    op.create_index(
        "ix_benchmark_constituent_benchmark_id", "benchmark_constituent", ["benchmark_id"]
    )
    op.create_index(
        "ix_benchmark_constituent_instrument_id", "benchmark_constituent", ["instrument_id"]
    )
    op.create_index(
        "ix_benchmark_constituent_effective_date", "benchmark_constituent", ["effective_date"]
    )
    op.create_index(
        "uq_benchmark_constituent_current",
        "benchmark_constituent",
        ["tenant_id", "benchmark_id", "instrument_id", "effective_date"],
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

    # --- NO append-only trigger: benchmark (EV) + benchmark_constituent (FR) are NOT append-only
    # --- (APPEND_ONLY_TABLES is empty — a deliberate difference from 0020's curve_point). ---
    for table in APPEND_ONLY_TABLES:  # pragma: no cover - empty in P2-6
        op.execute(
            f"CREATE TRIGGER {table}_append_only BEFORE UPDATE OR DELETE ON {table} "
            f"FOR EACH ROW EXECUTE FUNCTION irp_prevent_mutation()"
        )


def downgrade() -> None:
    for table in APPEND_ONLY_TABLES:  # pragma: no cover - empty in P2-6
        op.execute(f"DROP TRIGGER IF EXISTS {table}_append_only ON {table}")
    for table in TENANT_SCOPED_TABLES:
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation_{table} ON {table}")
    op.drop_table("benchmark_constituent")
    op.drop_table("benchmark")
