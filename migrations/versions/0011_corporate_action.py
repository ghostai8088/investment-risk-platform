"""P1B-4: corporate_action (EV effective-dated reference data) (REQ-SMR-004 corporate_action portion).

Adds one tenant-scoped PROPRIETARY EV table under the **SYMMETRIC** tenant-isolation RLS loop
(``USING == WITH CHECK == own-tenant``) — the SAME pattern as 0009/0010. NOT hybrid, no SYSTEM_TENANT,
no asymmetric disjunct (the 0008 hybrid loop + ``HYBRID_TABLES`` are untouched). NOT append-only
(EV-mutable: in-place amend + status transition must succeed at the DB; no ``irp_prevent_mutation``
trigger). ``instrument_id`` is a NOT-NULL FK to the P1B-3 ``instrument`` head (the affected security).
``status`` is the single lifecycle flag (ANNOUNCED/CONFIRMED/CANCELLED; no ``is_active``); business
dates (announcement/ex/record/pay/effective) are inert Date columns. No new audit code/permission table.

Revision ID: 0011_corporate_action
Revises: 0010_instrument
Create Date: 2026-06-24
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0011_corporate_action"
down_revision: str | None = "0010_instrument"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: Symmetric tenant-isolation (NOT hybrid). NOT append-only (EV-mutable).
TENANT_SCOPED_TABLES = ("corporate_action",)


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
        "corporate_action",
        *_ev_head_columns(),
        sa.Column("code", sa.String(length=150), nullable=False),
        sa.Column("instrument_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("action_type", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("announcement_date", sa.Date(), nullable=True),
        sa.Column("ex_date", sa.Date(), nullable=True),
        sa.Column("record_date", sa.Date(), nullable=True),
        sa.Column("pay_date", sa.Date(), nullable=True),
        sa.Column("effective_date", sa.Date(), nullable=True),
        sa.Column("ratio", sa.Numeric(precision=18, scale=8), nullable=True),
        sa.Column("amount", sa.Numeric(precision=20, scale=6), nullable=True),
        sa.Column("currency_code", sa.String(length=3), nullable=True),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column("source", sa.String(length=150), nullable=True),
        sa.Column("record_version", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_corporate_action"),
        sa.UniqueConstraint("tenant_id", "code", name="uq_corporate_action_tenant_code"),
        sa.ForeignKeyConstraint(
            ["instrument_id"],
            ["instrument.id"],
            name="fk_corporate_action_instrument_id_instrument",
        ),
    )
    op.create_index("ix_corporate_action_tenant_id", "corporate_action", ["tenant_id"])
    op.create_index("ix_corporate_action_instrument_id", "corporate_action", ["instrument_id"])

    # --- Tenant isolation: SYMMETRIC RLS (USING == WITH CHECK == own-tenant); NOT hybrid (BR-17) ---
    # NO SYSTEM_TENANT disjunct, NO append-only trigger. Proprietary entity (OD-P1B-C).
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
    op.drop_table("corporate_action")
