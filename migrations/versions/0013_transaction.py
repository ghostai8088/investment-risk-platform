"""P1C-2: transaction (IA append-only trade/cashflow event log) — REQ-PPM-003 transaction half.

The platform's FIRST domain IA entity. One tenant-scoped PROPRIETARY table under the **SYMMETRIC**
tenant-isolation RLS loop (``USING == WITH CHECK == own-tenant``) — the SAME pattern as 0009..0012.
NOT hybrid, no SYSTEM_TENANT (the 0008 hybrid loop + ``HYBRID_TABLES`` are untouched). **TRULY
IMMUTABLE / append-only** (unlike the IA-status-mutable ``ingestion_batch``/``calculation_run``):
``transaction`` is in ``APPEND_ONLY_TABLES`` -> the ``irp_prevent_mutation`` P0001 trigger (reusing
the
0001 function) forbids UPDATE/DELETE (paired with the ORM before_update/before_delete guard).
``portfolio_id``/``instrument_id`` are NOT-NULL FKs (resolved tenant-filtered in the binder);
``reverses_transaction_id`` is a nullable self-FK (set on a reversal record). Partial-unique
``external_ref`` per tenant (idempotency). No new audit code/permission table (``TRANSACTION.*`` are
caller-side constants; ``transaction.*`` perms are added in the entitlement bootstrap).

Revision ID: 0013_transaction
Revises: 0012_portfolio
Create Date: 2026-06-24
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0013_transaction"
down_revision: str | None = "0012_portfolio"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: Symmetric tenant-isolation (NOT hybrid).
TENANT_SCOPED_TABLES = ("transaction",)
#: Truly immutable append-only (the irp_prevent_mutation P0001 trigger, reusing the 0001 function).
APPEND_ONLY_TABLES = ("transaction",)


def upgrade() -> None:
    op.create_table(
        "transaction",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("system_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("portfolio_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("instrument_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("txn_type", sa.String(length=50), nullable=False),
        sa.Column("trade_date", sa.Date(), nullable=False),
        sa.Column("settle_date", sa.Date(), nullable=True),
        sa.Column("quantity", sa.Numeric(precision=28, scale=8), nullable=False),
        sa.Column("price", sa.Numeric(precision=20, scale=6), nullable=True),
        sa.Column("gross_amount", sa.Numeric(precision=20, scale=6), nullable=True),
        sa.Column("currency_code", sa.String(length=3), nullable=True),
        sa.Column("external_ref", sa.String(length=150), nullable=True),
        sa.Column("reverses_transaction_id", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_transaction"),
        sa.ForeignKeyConstraint(
            ["portfolio_id"], ["portfolio.id"], name="fk_transaction_portfolio_id_portfolio"
        ),
        sa.ForeignKeyConstraint(
            ["instrument_id"], ["instrument.id"], name="fk_transaction_instrument_id_instrument"
        ),
        sa.ForeignKeyConstraint(
            ["reverses_transaction_id"],
            ["transaction.id"],
            name="fk_transaction_reverses_transaction_id_transaction",
        ),
    )
    op.create_index("ix_transaction_tenant_id", "transaction", ["tenant_id"])
    op.create_index("ix_transaction_portfolio_id", "transaction", ["portfolio_id"])
    op.create_index("ix_transaction_instrument_id", "transaction", ["instrument_id"])
    op.create_index(
        "ix_transaction_reverses_transaction_id", "transaction", ["reverses_transaction_id"]
    )
    # Idempotency: partial-unique external_ref per tenant (NULLs coexist) — the LEI precedent.
    op.create_index(
        "uq_transaction_tenant_external_ref",
        "transaction",
        ["tenant_id", "external_ref"],
        unique=True,
        postgresql_where=sa.text("external_ref IS NOT NULL"),
    )

    # --- Tenant isolation: SYMMETRIC RLS (USING == WITH CHECK == own-tenant); NOT hybrid (BR-17)
    # ---
    for table in TENANT_SCOPED_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY tenant_isolation_{table} ON {table} "
            f"USING (tenant_id::text = current_setting('app.current_tenant', true)) "
            f"WITH CHECK (tenant_id::text = current_setting('app.current_tenant', true))"
        )

    # --- Append-only: truly immutable IA table (BR-12/BR-18 / AUD-01), reusing the 0001 function
    # ---
    for table in APPEND_ONLY_TABLES:
        op.execute(
            f"CREATE TRIGGER {table}_append_only BEFORE UPDATE OR DELETE ON {table} "
            f"FOR EACH ROW EXECUTE FUNCTION irp_prevent_mutation()"
        )


def downgrade() -> None:
    for table in APPEND_ONLY_TABLES:
        op.execute(f"DROP TRIGGER IF EXISTS {table}_append_only ON {table}")
    for table in TENANT_SCOPED_TABLES:
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation_{table} ON {table}")
    op.drop_table("transaction")
