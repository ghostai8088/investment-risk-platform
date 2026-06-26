"""P2-2: fx_rate (FR bitemporal captured FX market data) — ENT-024, the first market-data entity.

The platform's first MARKET-DATA table and the fourth persisted FR bitemporal table (after
``instrument_terms`` / ``position`` / ``valuation``). One tenant-scoped PROPRIETARY table under the
**SYMMETRIC** tenant-isolation RLS loop (``USING == WITH CHECK == own-tenant``) — the SAME pattern
as
0009..0015. **NOT hybrid, no SYSTEM_TENANT** (vendor FX is per-tenant licensed; OD-P2-G; a shared
global set would be an AD-013-R2 event). The 0008 hybrid loop + the closed 5-table hybrid set are
UNCHANGED.

**NOT append-only** (the FR contrast with the IA ``transaction``/``dataset_snapshot`` tables):
``fx_rate``
is NOT in any ``APPEND_ONLY_TABLES`` / ``irp_prevent_mutation`` trigger loop (only the symmetric RLS
loop) — the FR protocol requires close-out UPDATEs to ``valid_to``/``system_to``. Prior-version
CONTENT
immutability is service-enforced + tested.

``base_currency``/``quote_currency`` are ISO String(3) CODES (validated via the hybrid-aware
``resolve_currency``, NOT FKs — the currency table is hybrid SYSTEM/tenant).
``rate_date``/``rate_type``
are immutable logical-key components; ``rate`` is ``Numeric(28, 12)`` (NOT money scale 6).
Current-head partial-unique ``(tenant_id, base_currency, quote_currency, rate_date, rate_type) WHERE
valid_to IS NULL AND system_to IS NULL``. No new audit code/permission table (``MARKET.FX_*`` are
caller-side constants; ``marketdata.view``/``.ingest`` perms are added in the entitlement
bootstrap).

Revision ID: 0017_fx_rate
Revises: 0016_dataset_snapshot
Create Date: 2026-06-26
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0017_fx_rate"
down_revision: str | None = "0016_dataset_snapshot"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: Symmetric tenant-isolation (NOT hybrid). NOTE: NOT append-only — no APPEND_ONLY_TABLES entry,
#: no irp_prevent_mutation trigger (FR requires close-out UPDATEs).
TENANT_SCOPED_TABLES = ("fx_rate",)


def _timestamp_columns() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(length=255), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by", sa.String(length=255), nullable=True),
    ]


def upgrade() -> None:
    op.create_table(
        "fx_rate",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("system_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("system_to", sa.DateTime(timezone=True), nullable=True),
        *_timestamp_columns(),
        sa.Column("base_currency", sa.String(length=3), nullable=False),
        sa.Column("quote_currency", sa.String(length=3), nullable=False),
        sa.Column("rate_date", sa.Date(), nullable=False),
        sa.Column("rate", sa.Numeric(precision=28, scale=12), nullable=False),
        sa.Column("rate_type", sa.String(length=20), nullable=False),
        sa.Column("rate_source", sa.String(length=150), nullable=True),
        sa.Column("restatement_reason", sa.String(length=255), nullable=True),
        sa.Column("supersedes_id", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("record_version", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_fx_rate"),
        sa.ForeignKeyConstraint(
            ["supersedes_id"], ["fx_rate.id"], name="fk_fx_rate_supersedes_id_fx_rate"
        ),
    )
    op.create_index("ix_fx_rate_tenant_id", "fx_rate", ["tenant_id"])
    op.create_index("ix_fx_rate_rate_date", "fx_rate", ["rate_date"])
    # Current-head invariant: at most one version OPEN ON BOTH axes per (tenant, base, quote,
    # rate_date, rate_type) — exactly one open rate per pair+date+type.
    op.create_index(
        "uq_fx_rate_current",
        "fx_rate",
        ["tenant_id", "base_currency", "quote_currency", "rate_date", "rate_type"],
        unique=True,
        postgresql_where=sa.text("valid_to IS NULL AND system_to IS NULL"),
    )

    # --- Tenant isolation: SYMMETRIC RLS (USING == WITH CHECK == own-tenant); NOT hybrid (BR-17)
    # ---
    # NO SYSTEM_TENANT disjunct, NO append-only trigger (fx_rate is FR — close-out UPDATEs
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
    op.drop_table("fx_rate")
