"""P1C-3: position (FR bitemporal holdings master, captured directly) — REQ-PPM-002.

The platform's first FR DOMAIN entity and second persisted bitemporal table (after the P1B-3
``instrument_terms``). One tenant-scoped PROPRIETARY table under the **SYMMETRIC** tenant-isolation
RLS loop (``USING == WITH CHECK == own-tenant``) — the SAME pattern as 0009..0013. NOT hybrid, no
SYSTEM_TENANT (the 0008 hybrid loop is untouched).

**NOT append-only** (the FR contrast with the 0013 ``transaction`` IA table): ``position`` is
**NOT**
in ``APPEND_ONLY_TABLES`` and gets **NO** ``irp_prevent_mutation`` trigger — the FR protocol
requires
close-out UPDATEs to ``valid_to``/``system_to``. Prior-version CONTENT immutability is service-
enforced + tested. ``portfolio_id``/``instrument_id`` are NOT-NULL FKs (resolved tenant-filtered in
the binder); ``supersedes_id`` is a nullable self-FK (set on a supersede/correction). Current-head
partial-unique ``(tenant_id, portfolio_id, instrument_id) WHERE valid_to IS NULL AND system_to IS
NULL`` (the OD-P1C-D aggregated grain). ``quantity`` is signed; ``cost_basis`` is an opaque captured
reference. No new audit code/permission table (``POSITION.*`` are caller-side constants;
``position.edit`` perm is added in the entitlement bootstrap).

Revision ID: 0014_position
Revises: 0013_transaction
Create Date: 2026-06-25
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0014_position"
down_revision: str | None = "0013_transaction"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: Symmetric tenant-isolation (NOT hybrid). NOTE: NOT append-only — no APPEND_ONLY_TABLES entry,
#: no irp_prevent_mutation trigger (FR requires close-out UPDATEs).
TENANT_SCOPED_TABLES = ("position",)


def _timestamp_columns() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(length=255), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by", sa.String(length=255), nullable=True),
    ]


def upgrade() -> None:
    op.create_table(
        "position",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("system_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("system_to", sa.DateTime(timezone=True), nullable=True),
        *_timestamp_columns(),
        sa.Column("portfolio_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("instrument_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("quantity", sa.Numeric(precision=28, scale=8), nullable=False),
        sa.Column("cost_basis", sa.Numeric(precision=20, scale=6), nullable=True),
        sa.Column("quantity_unit", sa.String(length=20), nullable=True),
        sa.Column("position_source", sa.String(length=150), nullable=True),
        sa.Column("restatement_reason", sa.String(length=255), nullable=True),
        sa.Column("supersedes_id", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("record_version", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_position"),
        sa.ForeignKeyConstraint(
            ["portfolio_id"], ["portfolio.id"], name="fk_position_portfolio_id_portfolio"
        ),
        sa.ForeignKeyConstraint(
            ["instrument_id"], ["instrument.id"], name="fk_position_instrument_id_instrument"
        ),
        sa.ForeignKeyConstraint(
            ["supersedes_id"], ["position.id"], name="fk_position_supersedes_id_position"
        ),
    )
    op.create_index("ix_position_tenant_id", "position", ["tenant_id"])
    op.create_index("ix_position_portfolio_id", "position", ["portfolio_id"])
    op.create_index("ix_position_instrument_id", "position", ["instrument_id"])
    # Current-head invariant: at most one version OPEN ON BOTH axes per (tenant, portfolio,
    # instrument) — the OD-P1C-D aggregated grain.
    op.create_index(
        "uq_position_current",
        "position",
        ["tenant_id", "portfolio_id", "instrument_id"],
        unique=True,
        postgresql_where=sa.text("valid_to IS NULL AND system_to IS NULL"),
    )

    # --- Tenant isolation: SYMMETRIC RLS (USING == WITH CHECK == own-tenant); NOT hybrid (BR-17)
    # ---
    # NO SYSTEM_TENANT disjunct, NO append-only trigger (position is FR — close-out UPDATEs
    # required).
    for table in TENANT_SCOPED_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY tenant_isolation_{table} ON {table} "
            f"USING (tenant_id::text = current_setting('app.current_tenant', true)) "
            f"WITH CHECK (tenant_id::text = current_setting('app.current_tenant', true))"
        )


def downgrade() -> None:
    for table in TENANT_SCOPED_TABLES:
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation_{table} ON {table}")
    op.drop_table("position")
