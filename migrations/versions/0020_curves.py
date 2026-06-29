"""P2-5: curve (FR bitemporal header) + curve_point (IA append-only version-pinned nodes) — ENT-021/
023, the third market-data entity (after fx_rate + price_point).

``curve`` is the SIXTH persisted FR bitemporal table (after instrument_terms / position / valuation /
fx_rate / price_point). ``curve_point`` is an IA TRUE append-only child (the
``dataset_snapshot_component`` precedent — in ``APPEND_ONLY_TABLES`` -> the ``irp_prevent_mutation``
P0001 trigger + the ORM guard). Both tenant-scoped PROPRIETARY under the **SYMMETRIC** tenant-isolation
RLS loop (``USING == WITH CHECK == own-tenant``) — the SAME pattern as 0009..0019. **NOT hybrid, no
SYSTEM_TENANT** (vendor curve data is per-tenant licensed; OD-P2-5-N; a shared global set would be an
AD-013-R2 event). The 0008 hybrid loop + the closed 5-table hybrid set are UNCHANGED.

``curve`` is **NOT append-only** (the FR protocol requires close-out UPDATEs to ``valid_to``/
``system_to``; content-immutability service-enforced). ``curve_point`` IS append-only (a re-version =
a new header + a fresh node set; nodes never updated/deleted). ``curve_type``/``currency_code``/
``reference_key``/``curve_date``/``curve_source`` are the immutable logical-key components (all DB-level
NOT NULL); current-head partial-unique ``(tenant_id, curve_type, currency_code, reference_key,
curve_date, curve_source) WHERE valid_to IS NULL AND system_to IS NULL``. ``curve_point`` UNIQUE
``(curve_id, value_type, tenor_days)``; ``point_value`` ``Numeric(20, 12)``. No new audit code/
permission table (``MARKET.CURVE_*`` are caller-side constants; ``marketdata.view``/``.ingest`` REUSED).

Revision ID: 0020_curves
Revises: 0019_price_point
Create Date: 2026-06-28
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0020_curves"
down_revision: str | None = "0019_price_point"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: Symmetric tenant-isolation (NOT hybrid) — both curve tables.
TENANT_SCOPED_TABLES = ("curve", "curve_point")
#: Truly immutable append-only — ONLY curve_point (the irp_prevent_mutation P0001 trigger, reusing the
#: 0001 function). curve is FR (NOT append-only) — no trigger.
APPEND_ONLY_TABLES = ("curve_point",)


def _timestamp_columns() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(length=255), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by", sa.String(length=255), nullable=True),
    ]


def upgrade() -> None:
    # --- curve (FR header) ---
    op.create_table(
        "curve",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("system_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("system_to", sa.DateTime(timezone=True), nullable=True),
        *_timestamp_columns(),
        # Promoted key columns — DB-level NOT NULL (so the current-head key is not defeasible).
        sa.Column("curve_type", sa.String(length=30), nullable=False),
        sa.Column("currency_code", sa.String(length=3), nullable=False),
        sa.Column("reference_key", sa.String(length=150), nullable=False),
        sa.Column("curve_date", sa.Date(), nullable=False),
        sa.Column("curve_source", sa.String(length=150), nullable=False),
        sa.Column("interpolation_method", sa.String(length=50), nullable=True),
        sa.Column("point_count", sa.Integer(), nullable=False),
        sa.Column("restatement_reason", sa.String(length=255), nullable=True),
        sa.Column("supersedes_id", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("record_version", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_curve"),
        sa.ForeignKeyConstraint(
            ["supersedes_id"], ["curve.id"], name="fk_curve_supersedes_id_curve"
        ),
    )
    op.create_index("ix_curve_tenant_id", "curve", ["tenant_id"])
    op.create_index("ix_curve_curve_date", "curve", ["curve_date"])
    op.create_index(
        "uq_curve_current",
        "curve",
        ["tenant_id", "curve_type", "currency_code", "reference_key", "curve_date", "curve_source"],
        unique=True,
        postgresql_where=sa.text("valid_to IS NULL AND system_to IS NULL"),
    )

    # --- curve_point (IA append-only version-pinned nodes) ---
    op.create_table(
        "curve_point",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("system_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("curve_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("tenor_label", sa.String(length=10), nullable=False),
        sa.Column("tenor_days", sa.Integer(), nullable=False),
        sa.Column("value_type", sa.String(length=30), nullable=False),
        sa.Column("point_value", sa.Numeric(precision=20, scale=12), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_curve_point"),
        sa.ForeignKeyConstraint(["curve_id"], ["curve.id"], name="fk_curve_point_curve_id_curve"),
        sa.UniqueConstraint(
            "curve_id", "value_type", "tenor_days", name="uq_curve_point_curve_value_tenor"
        ),
    )
    op.create_index("ix_curve_point_tenant_id", "curve_point", ["tenant_id"])
    op.create_index("ix_curve_point_curve_id", "curve_point", ["curve_id"])

    # --- Tenant isolation: SYMMETRIC RLS (USING == WITH CHECK == own-tenant); NOT hybrid (BR-17) ---
    for table in TENANT_SCOPED_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY tenant_isolation_{table} ON {table} "
            f"USING (tenant_id::text = current_setting('app.current_tenant', true)) "
            f"WITH CHECK (tenant_id::text = current_setting('app.current_tenant', true))"
        )

    # --- Append-only: curve_point is truly immutable (BR-12/BR-18 / AUD-01), reuse the 0001 function
    # --- (curve, the FR header, is NOT append-only — close-out UPDATEs required). ---
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
    op.drop_table("curve_point")
    op.drop_table("curve")
