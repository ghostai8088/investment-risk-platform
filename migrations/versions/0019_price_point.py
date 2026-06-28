"""P2-4: price_point (FR bitemporal captured price market data) — ENT-020, the second market-data
entity (after fx_rate).

The fifth persisted FR bitemporal table (after ``instrument_terms`` / ``position`` / ``valuation`` /
``fx_rate``). One tenant-scoped PROPRIETARY table under the **SYMMETRIC** tenant-isolation RLS loop
(``USING == WITH CHECK == own-tenant``) — the SAME pattern as 0009..0017. **NOT hybrid, no
SYSTEM_TENANT** (vendor price data is per-tenant licensed; OD-P2-4-L; a shared global set is an
AD-013-R2 event). The 0008 hybrid loop + the closed 5-table hybrid set are UNCHANGED.

**NOT append-only** (the FR contrast with the IA ``transaction``/``dataset_snapshot``/
``exposure_aggregate`` tables): ``price_point`` is NOT in any ``APPEND_ONLY_TABLES`` /
``irp_prevent_mutation`` trigger loop (only the symmetric RLS loop) — the FR protocol requires
close-out UPDATEs to ``valid_to``/``system_to``. Prior-version immutability is service-enforced
+ tested.

``instrument_id`` is a NOT-NULL FK to the ``instrument`` head (resolved tenant-filtered via
``resolve_instrument``). ``price_date``/``price_type``/``currency_code``/``price_source`` are the
immutable logical-key components (the promoted key columns ``price_type``/``currency_code``/
``price_source`` are DB-level NOT NULL — unlike inert nullable ``rate_source`` — so current-head
partial-unique is not defeasible by a NULL key). ``price`` is ``Numeric(20, 6)`` (valuation money
scale). Current-head uq ``(tenant_id, instrument_id, price_date, price_type, currency_code,
price_source) WHERE valid_to IS NULL AND system_to IS NULL``. No new audit code/permission table
(``MARKET.PRICE_*`` are caller-side constants; ``marketdata.view``/``.ingest`` are REUSED).

Revision ID: 0019_price_point
Revises: 0018_exposure_aggregate
Create Date: 2026-06-28
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0019_price_point"
down_revision: str | None = "0018_exposure_aggregate"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: Symmetric tenant-isolation (NOT hybrid). NOTE: NOT append-only — no APPEND_ONLY_TABLES entry,
#: no irp_prevent_mutation trigger (FR requires close-out UPDATEs).
TENANT_SCOPED_TABLES = ("price_point",)


def _timestamp_columns() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(length=255), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by", sa.String(length=255), nullable=True),
    ]


def upgrade() -> None:
    op.create_table(
        "price_point",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("system_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("system_to", sa.DateTime(timezone=True), nullable=True),
        *_timestamp_columns(),
        sa.Column("instrument_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("price_date", sa.Date(), nullable=False),
        sa.Column("price", sa.Numeric(precision=20, scale=6), nullable=False),
        # Promoted key columns — DB-level NOT NULL (so the current-head key is not defeasible).
        sa.Column("price_type", sa.String(length=20), nullable=False),
        sa.Column("currency_code", sa.String(length=3), nullable=False),
        sa.Column("price_source", sa.String(length=150), nullable=False),
        sa.Column("restatement_reason", sa.String(length=255), nullable=True),
        sa.Column("supersedes_id", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("record_version", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_price_point"),
        sa.ForeignKeyConstraint(
            ["instrument_id"], ["instrument.id"], name="fk_price_point_instrument_id_instrument"
        ),
        sa.ForeignKeyConstraint(
            ["supersedes_id"], ["price_point.id"], name="fk_price_point_supersedes_id_price_point"
        ),
    )
    op.create_index("ix_price_point_tenant_id", "price_point", ["tenant_id"])
    op.create_index("ix_price_point_instrument_id", "price_point", ["instrument_id"])
    op.create_index("ix_price_point_price_date", "price_point", ["price_date"])
    # Current-head invariant: at most one version OPEN ON BOTH axes per (tenant, instrument,
    # price_date, price_type, currency_code, price_source) — exactly one open price per key.
    op.create_index(
        "uq_price_point_current",
        "price_point",
        ["tenant_id", "instrument_id", "price_date", "price_type", "currency_code", "price_source"],
        unique=True,
        postgresql_where=sa.text("valid_to IS NULL AND system_to IS NULL"),
    )

    # --- Tenant isolation: SYMMETRIC RLS (USING == WITH CHECK == own-tenant); NOT hybrid (BR-17)
    # NO SYSTEM_TENANT disjunct, NO append-only trigger (price_point is FR — close-out UPDATEs
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
    op.drop_table("price_point")
