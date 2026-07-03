"""P3-2: factor (EV definition header) + factor_return (FR bitemporal captured return series) —
ENT-025, the fifth market-data entity (after fx_rate + price_point + curve + benchmark).

``factor`` is an EV effective-dated reference/definition entity (the ``benchmark`` precedent —
entity-versioned in place via ``record_version``; valid time only, no system axis; audited
``REFERENCE.*``). ``factor_return`` is the next persisted FR bitemporal table — the captured
vendor/external return series that re-versions over time (audited ``MARKET.FACTOR_RETURN_*``).
Tenant-scoped PROPRIETARY under the **SYMMETRIC** tenant-isolation RLS loop (``USING == WITH CHECK
==
own``) — the SAME pattern as 0009..0022. **NOT hybrid** (vendor factor data is per-tenant
licensed).
The 0008 hybrid loop + the closed 5-table hybrid set are UNCHANGED.

**NEITHER table is append-only** — ``factor`` (EV) mutates in place (record_version bump);
``factor_return`` (FR) requires close-out UPDATEs to ``valid_to``/``system_to``. So
``APPEND_ONLY_TABLES`` is empty and NO ``irp_prevent_mutation`` trigger is installed (the 0021
benchmark precedent). Content-immutability is service-enforced + tested.

``factor`` EV identity ``UNIQUE(tenant_id, factor_code, factor_source)``; ``factor_return``
current-head partial-unique ``(tenant_id, factor_id, return_date, return_type) WHERE valid_to IS
NULL
AND system_to IS NULL``; ``return_value`` ``Numeric(20, 12)``. **Captured INPUT only** — NO
``calculation_run``, NO ``model_version``, NO snapshot pin. No new audit code / permission table
(``REFERENCE.*``/``MARKET.FACTOR_RETURN_*`` are caller-side constants;
``marketdata.view``/``.ingest``
REUSED).

Revision ID: 0023_factor_return
Revises: 0022_sensitivity
Create Date: 2026-07-02
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0023_factor_return"
down_revision: str | None = "0022_sensitivity"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: Symmetric tenant-isolation (NOT hybrid) — both factor tables.
TENANT_SCOPED_TABLES = ("factor", "factor_return")
#: NEITHER table is append-only — factor is EV (in-place), factor_return is FR (close-out UPDATEs).
#: NO irp_prevent_mutation trigger (the 0021 benchmark precedent).
APPEND_ONLY_TABLES: tuple[str, ...] = ()


def _timestamp_columns() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(length=255), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by", sa.String(length=255), nullable=True),
    ]


def upgrade() -> None:
    # --- factor (EV definition header) — valid time only (no system axis) ---
    op.create_table(
        "factor",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_to", sa.DateTime(timezone=True), nullable=True),
        *_timestamp_columns(),
        # Promoted identity-key columns — DB-level NOT NULL.
        sa.Column("factor_code", sa.String(length=150), nullable=False),
        sa.Column("factor_source", sa.String(length=150), nullable=False),
        sa.Column("factor_family", sa.String(length=30), nullable=False),
        sa.Column("factor_type", sa.String(length=100), nullable=True),
        sa.Column("region", sa.String(length=50), nullable=True),
        sa.Column("currency_code", sa.String(length=3), nullable=True),
        sa.Column("asset_class", sa.String(length=50), nullable=True),
        sa.Column("frequency", sa.String(length=20), nullable=False),
        sa.Column("factor_name", sa.String(length=255), nullable=True),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column("record_version", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_factor"),
        sa.UniqueConstraint(
            "tenant_id", "factor_code", "factor_source", name="uq_factor_tenant_code_source"
        ),
    )
    op.create_index("ix_factor_tenant_id", "factor", ["tenant_id"])

    # --- factor_return (FR bitemporal captured return series) ---
    op.create_table(
        "factor_return",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("system_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("system_to", sa.DateTime(timezone=True), nullable=True),
        *_timestamp_columns(),
        sa.Column("factor_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("return_date", sa.Date(), nullable=False),
        sa.Column("return_type", sa.String(length=20), nullable=False),
        sa.Column("return_value", sa.Numeric(precision=20, scale=12), nullable=False),
        sa.Column("restatement_reason", sa.String(length=255), nullable=True),
        sa.Column("supersedes_id", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("record_version", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_factor_return"),
        sa.ForeignKeyConstraint(
            ["factor_id"], ["factor.id"], name="fk_factor_return_factor_id_factor"
        ),
        sa.ForeignKeyConstraint(
            ["supersedes_id"],
            ["factor_return.id"],
            name="fk_factor_return_supersedes_id_factor_return",
        ),
    )
    op.create_index("ix_factor_return_tenant_id", "factor_return", ["tenant_id"])
    op.create_index("ix_factor_return_factor_id", "factor_return", ["factor_id"])
    op.create_index("ix_factor_return_return_date", "factor_return", ["return_date"])
    op.create_index(
        "uq_factor_return_current",
        "factor_return",
        ["tenant_id", "factor_id", "return_date", "return_type"],
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

    # --- NO append-only trigger: factor (EV) + factor_return (FR) are NOT append-only
    # --- (APPEND_ONLY_TABLES is empty — the 0021 benchmark precedent). ---
    for table in APPEND_ONLY_TABLES:  # pragma: no cover - empty in P3-2
        op.execute(
            f"CREATE TRIGGER {table}_append_only BEFORE UPDATE OR DELETE ON {table} "
            f"FOR EACH ROW EXECUTE FUNCTION irp_prevent_mutation()"
        )


def downgrade() -> None:
    for table in APPEND_ONLY_TABLES:  # pragma: no cover - empty in P3-2
        op.execute(f"DROP TRIGGER IF EXISTS {table}_append_only ON {table}")
    for table in TENANT_SCOPED_TABLES:
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation_{table} ON {table}")
    op.drop_table("factor_return")
    op.drop_table("factor")
