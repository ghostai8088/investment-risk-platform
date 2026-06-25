"""P1C-4: valuation (FR bitemporal mark history, captured marks) — REQ-PPM-003 (valuation conjunct).

The platform's second FR DOMAIN entity and third persisted bitemporal table (after the P1B-3
``instrument_terms`` + the P1C-3 ``position``). One tenant-scoped PROPRIETARY table under the
**SYMMETRIC** tenant-isolation RLS loop (``USING == WITH CHECK == own-tenant``) — the SAME pattern
as
0009..0014. NOT hybrid, no SYSTEM_TENANT (the 0008 hybrid loop is untouched).

**NOT append-only** (the FR contrast with the 0013 ``transaction`` IA table): ``valuation`` is
**NOT**
in any ``APPEND_ONLY_TABLES`` / ``irp_prevent_mutation`` trigger loop (only the symmetric RLS loop)
—
the FR protocol requires close-out UPDATEs to ``valid_to``/``system_to``. Prior-version CONTENT
immutability is service-enforced + tested. ``portfolio_id``/``instrument_id`` are NOT-NULL FKs
(resolved tenant-filtered in the binder); ``valuation_date`` is a NOT-NULL **immutable logical-key
component** (OD-P1C-F); ``supersedes_id`` is a nullable self-FK (set on a supersede/correction).
Current-head partial-unique ``(tenant_id, portfolio_id, instrument_id, valuation_date) WHERE
valid_to
IS NULL AND system_to IS NULL`` — exactly one mark per key. ``mark_value`` is NOT-NULL captured;
``mark_source`` is an inert label (NOT a market-data FK). No new audit code/permission table
(``VALUATION.*`` are caller-side constants; ``valuation.view``/``valuation.edit`` perms are added in
the entitlement bootstrap).

Revision ID: 0015_valuation
Revises: 0014_position
Create Date: 2026-06-25
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0015_valuation"
down_revision: str | None = "0014_position"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: Symmetric tenant-isolation (NOT hybrid). NOTE: NOT append-only — no APPEND_ONLY_TABLES entry,
#: no irp_prevent_mutation trigger (FR requires close-out UPDATEs).
TENANT_SCOPED_TABLES = ("valuation",)


def _timestamp_columns() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(length=255), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by", sa.String(length=255), nullable=True),
    ]


def upgrade() -> None:
    op.create_table(
        "valuation",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("system_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("system_to", sa.DateTime(timezone=True), nullable=True),
        *_timestamp_columns(),
        sa.Column("portfolio_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("instrument_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("valuation_date", sa.Date(), nullable=False),
        sa.Column("mark_value", sa.Numeric(precision=20, scale=6), nullable=False),
        sa.Column("currency_code", sa.String(length=3), nullable=True),
        sa.Column("mark_source", sa.String(length=150), nullable=True),
        sa.Column("price_basis", sa.String(length=20), nullable=True),
        sa.Column("restatement_reason", sa.String(length=255), nullable=True),
        sa.Column("supersedes_id", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("record_version", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_valuation"),
        sa.ForeignKeyConstraint(
            ["portfolio_id"], ["portfolio.id"], name="fk_valuation_portfolio_id_portfolio"
        ),
        sa.ForeignKeyConstraint(
            ["instrument_id"], ["instrument.id"], name="fk_valuation_instrument_id_instrument"
        ),
        sa.ForeignKeyConstraint(
            ["supersedes_id"], ["valuation.id"], name="fk_valuation_supersedes_id_valuation"
        ),
    )
    op.create_index("ix_valuation_tenant_id", "valuation", ["tenant_id"])
    op.create_index("ix_valuation_portfolio_id", "valuation", ["portfolio_id"])
    op.create_index("ix_valuation_instrument_id", "valuation", ["instrument_id"])
    op.create_index("ix_valuation_valuation_date", "valuation", ["valuation_date"])
    # Current-head invariant: at most one version OPEN ON BOTH axes per (tenant, portfolio,
    # instrument, valuation_date) — the OD-P1C-F grain (exactly one mark per key).
    op.create_index(
        "uq_valuation_current",
        "valuation",
        ["tenant_id", "portfolio_id", "instrument_id", "valuation_date"],
        unique=True,
        postgresql_where=sa.text("valid_to IS NULL AND system_to IS NULL"),
    )

    # --- Tenant isolation: SYMMETRIC RLS (USING == WITH CHECK == own-tenant); NOT hybrid (BR-17)
    # ---
    # NO SYSTEM_TENANT disjunct, NO append-only trigger (valuation is FR — close-out UPDATEs
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
    op.drop_table("valuation")
