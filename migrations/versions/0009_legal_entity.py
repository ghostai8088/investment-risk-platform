"""P1B-2: legal_entity core + issuer / counterparty role profiles (REQ-SMR-002 / OD-P1B-D).

Adds three tenant-scoped **effective-dated (EV)** tables — ``legal_entity`` (implementation-only shared
core, NO canonical ENT id), ``issuer`` (ENT-002) and ``counterparty`` (ENT-003) as 1:1 role profiles —
under the **SYMMETRIC** tenant-isolation RLS loop (``USING == WITH CHECK == own-tenant``), the SAME
pattern as 0004/0005/0007. These are **PROPRIETARY** entities (OD-P1B-C hard invariant): **NOT hybrid,
no SYSTEM_TENANT rows, no asymmetric SYSTEM disjunct** — the hybrid loop (migration 0008) is untouched
and ``HYBRID_TABLES`` stays exactly the five P1B-1 tables.

**None of the three is append-only** (all EV-mutable): no ``irp_prevent_mutation`` trigger, no
``APPEND_ONLY_TABLES`` entry — a ``REFERENCE.UPDATE`` (re-parent / is_active flip) must succeed at the DB.
``legal_entity.parent_legal_entity_id`` is an intra-tenant self-FK (the hierarchy adjacency hook — no
stored rollup column). ``issuer``/``counterparty`` carry a NOT-NULL ``legal_entity_id`` FK +
``UNIQUE(tenant_id, legal_entity_id)`` (the 1:1 contract). ``legal_entity.lei`` has a Postgres
partial-unique ``(tenant_id, lei) WHERE lei IS NOT NULL``. Intra-context FKs carry ``fk_``
NAMING_CONVENTION names so ``alembic check`` is drift-clean. No new audit code, no new permission table.

Revision ID: 0009_legal_entity
Revises: 0008_reference_data
Create Date: 2026-06-22
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0009_legal_entity"
down_revision: str | None = "0008_reference_data"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: Symmetric tenant-isolation (NOT hybrid). NONE is append-only.
TENANT_SCOPED_TABLES = ("legal_entity", "issuer", "counterparty")


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
        "legal_entity",
        *_ev_head_columns(),
        sa.Column("code", sa.String(length=150), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("lei", sa.String(length=20), nullable=True),
        sa.Column("jurisdiction", sa.String(length=10), nullable=True),
        sa.Column("entity_type", sa.String(length=50), nullable=True),
        sa.Column("parent_legal_entity_id", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("record_version", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_legal_entity"),
        sa.UniqueConstraint("tenant_id", "code", name="uq_legal_entity_tenant_code"),
        sa.ForeignKeyConstraint(
            ["parent_legal_entity_id"],
            ["legal_entity.id"],
            name="fk_legal_entity_parent_legal_entity_id_legal_entity",
        ),
    )
    op.create_index("ix_legal_entity_tenant_id", "legal_entity", ["tenant_id"])
    op.create_index(
        "ix_legal_entity_parent_legal_entity_id", "legal_entity", ["parent_legal_entity_id"]
    )
    # LEI unique per tenant WHEN PRESENT (Postgres partial). Matches the ORM Index so alembic check is
    # drift-clean. On SQLite this is a plain unique index, but NULL leis are distinct so behaviour matches.
    op.create_index(
        "uq_legal_entity_tenant_lei",
        "legal_entity",
        ["tenant_id", "lei"],
        unique=True,
        postgresql_where=sa.text("lei IS NOT NULL"),
    )

    op.create_table(
        "issuer",
        *_ev_head_columns(),
        sa.Column("legal_entity_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("issuer_type", sa.String(length=50), nullable=True),
        sa.Column("sector", sa.String(length=100), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("record_version", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_issuer"),
        sa.UniqueConstraint(
            "tenant_id", "legal_entity_id", name="uq_issuer_tenant_legal_entity"
        ),
        sa.ForeignKeyConstraint(
            ["legal_entity_id"], ["legal_entity.id"], name="fk_issuer_legal_entity_id_legal_entity"
        ),
    )
    op.create_index("ix_issuer_tenant_id", "issuer", ["tenant_id"])
    op.create_index("ix_issuer_legal_entity_id", "issuer", ["legal_entity_id"])

    op.create_table(
        "counterparty",
        *_ev_head_columns(),
        sa.Column("legal_entity_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("counterparty_type", sa.String(length=50), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("record_version", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_counterparty"),
        sa.UniqueConstraint(
            "tenant_id", "legal_entity_id", name="uq_counterparty_tenant_legal_entity"
        ),
        sa.ForeignKeyConstraint(
            ["legal_entity_id"],
            ["legal_entity.id"],
            name="fk_counterparty_legal_entity_id_legal_entity",
        ),
    )
    op.create_index("ix_counterparty_tenant_id", "counterparty", ["tenant_id"])
    op.create_index("ix_counterparty_legal_entity_id", "counterparty", ["legal_entity_id"])

    # --- Tenant isolation: SYMMETRIC RLS (USING == WITH CHECK == own-tenant); NOT hybrid (BR-17) ---
    # NO SYSTEM_TENANT disjunct, NO append-only trigger. Proprietary entities (OD-P1B-C).
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
    op.drop_table("counterparty")
    op.drop_table("issuer")
    op.drop_table("legal_entity")
