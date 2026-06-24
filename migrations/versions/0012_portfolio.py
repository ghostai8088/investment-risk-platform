"""P1C-1: portfolio (EV portfolio/fund/strategy/account hierarchy) (REQ-PPM-001).

The platform's FIRST domain entity + the entitlement portfolio-scope ANCHOR. One tenant-scoped
PROPRIETARY EV table under the **SYMMETRIC** tenant-isolation RLS loop (``USING == WITH CHECK ==
own-tenant``) — the SAME pattern as 0009/0010/0011. NOT hybrid, no SYSTEM_TENANT, no asymmetric
disjunct (the 0008 hybrid loop + ``HYBRID_TABLES`` are untouched). NOT append-only (EV-mutable:
in-place amend / re-parent / status flip must succeed at the DB; no ``irp_prevent_mutation``
trigger).
``parent_portfolio_id`` is an intra-tenant self-FK adjacency (NULL = a root; the bounded cycle-safe
ancestor/descendant resolvers live in the binder). ``node_type``/``status`` are controlled-vocab
plain
strings (no enum/CHECK). A portfolio holds NOTHING — no position/valuation/holding/exposure column.
No new audit code/permission table (``PORTFOLIO.*`` are caller-side constants; the ``portfolio.*``
perms pre-exist in the entitlement catalog).

Revision ID: 0012_portfolio
Revises: 0011_corporate_action
Create Date: 2026-06-23
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0012_portfolio"
down_revision: str | None = "0011_corporate_action"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: Symmetric tenant-isolation (NOT hybrid). NOT append-only (EV-mutable).
TENANT_SCOPED_TABLES = ("portfolio",)


def _ev_head_columns() -> list[sa.Column]:
    return [
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(length=255), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by", sa.String(length=255), nullable=True),
    ]


def upgrade() -> None:
    op.create_table(
        "portfolio",
        *_ev_head_columns(),
        sa.Column("code", sa.String(length=150), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("node_type", sa.String(length=50), nullable=False),
        sa.Column("parent_portfolio_id", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("base_currency_code", sa.String(length=3), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column("record_version", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_portfolio"),
        sa.UniqueConstraint("tenant_id", "code", name="uq_portfolio_tenant_code"),
        sa.ForeignKeyConstraint(
            ["parent_portfolio_id"],
            ["portfolio.id"],
            name="fk_portfolio_parent_portfolio_id_portfolio",
        ),
    )
    op.create_index("ix_portfolio_tenant_id", "portfolio", ["tenant_id"])
    op.create_index("ix_portfolio_parent_portfolio_id", "portfolio", ["parent_portfolio_id"])

    # --- Tenant isolation: SYMMETRIC RLS (USING == WITH CHECK == own-tenant); NOT hybrid (BR-17)
    # ---
    # NO SYSTEM_TENANT disjunct, NO append-only trigger. Proprietary domain entity (AD-013-R1 /
    # AD-017). The 0008 hybrid loop + HYBRID_TABLES (the closed 5-table set) are untouched.
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
    op.drop_table("portfolio")
