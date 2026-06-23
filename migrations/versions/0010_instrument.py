"""P1B-3: instrument (EV identity) + instrument_terms (FR) + identifier_xref (EV) (REQ-SMR-001/003).

Adds three tenant-scoped PROPRIETARY tables under the **SYMMETRIC** tenant-isolation RLS loop
(``USING == WITH CHECK == own-tenant``) — the SAME pattern as 0004/0005/0007/0009. NOT hybrid, no
SYSTEM_TENANT rows, no asymmetric disjunct (the 0008 hybrid loop + ``HYBRID_TABLES`` are untouched).

- ``instrument`` (ENT-001 identity, **EV**) — identity/master only; nullable ``issuer_id`` FK to the
  ``issuer`` profile; ``UNIQUE(tenant_id, code)``.
- ``instrument_terms`` (ENT-001 terms, **FR** — the first real bitemporal table) — the four FR columns
  (``valid_from/valid_to`` + ``system_from/system_to``); ``instrument_id`` FK; ``supersedes_id`` self-FK
  (TR-08); a current-head partial-unique ``(tenant_id, instrument_id) WHERE valid_to IS NULL AND
  system_to IS NULL``. **NOT append-only** (no ``irp_prevent_mutation`` trigger) — the bitemporal
  protocol UPDATEs the ``valid_to``/``system_to`` close-out columns.
- ``identifier_xref`` (ENT-004, **EV**) — polymorphic ``(entity_type, entity_id)`` (no domain FK); the
  OD-P1B-G active partial-unique ``(tenant_id, scheme, value) WHERE valid_to IS NULL``.

Partial-index names + ``postgresql_where`` match the ORM ``Index`` objects so ``alembic check`` is
drift-clean (the 0009 ``uq_legal_entity_tenant_lei`` precedent). No new audit code/permission table.

Revision ID: 0010_instrument
Revises: 0009_legal_entity
Create Date: 2026-06-23
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0010_instrument"
down_revision: str | None = "0009_legal_entity"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: Symmetric tenant-isolation (NOT hybrid). NONE is append-only (FR needs close-out UPDATEs).
TENANT_SCOPED_TABLES = ("instrument", "instrument_terms", "identifier_xref")


def _timestamp_columns() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(length=255), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by", sa.String(length=255), nullable=True),
    ]


def _ev_head_columns() -> list[sa.Column]:
    return [
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_to", sa.DateTime(timezone=True), nullable=True),
        *_timestamp_columns(),
    ]


def _fr_head_columns() -> list[sa.Column]:
    return [
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("system_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("system_to", sa.DateTime(timezone=True), nullable=True),
        *_timestamp_columns(),
    ]


def upgrade() -> None:
    op.create_table(
        "instrument",
        *_ev_head_columns(),
        sa.Column("code", sa.String(length=150), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("asset_class", sa.String(length=50), nullable=False),
        sa.Column("instrument_type", sa.String(length=50), nullable=True),
        sa.Column("issuer_id", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("currency_code", sa.String(length=3), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("record_version", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_instrument"),
        sa.UniqueConstraint("tenant_id", "code", name="uq_instrument_tenant_code"),
        sa.ForeignKeyConstraint(
            ["issuer_id"], ["issuer.id"], name="fk_instrument_issuer_id_issuer"
        ),
    )
    op.create_index("ix_instrument_tenant_id", "instrument", ["tenant_id"])
    op.create_index("ix_instrument_issuer_id", "instrument", ["issuer_id"])

    op.create_table(
        "instrument_terms",
        *_fr_head_columns(),
        sa.Column("instrument_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("coupon_rate", sa.Numeric(precision=12, scale=6), nullable=True),
        sa.Column("coupon_frequency", sa.String(length=20), nullable=True),
        sa.Column("issue_date", sa.Date(), nullable=True),
        sa.Column("maturity_date", sa.Date(), nullable=True),
        sa.Column("day_count", sa.String(length=20), nullable=True),
        sa.Column("denomination_currency", sa.String(length=3), nullable=True),
        sa.Column("face_value", sa.Numeric(precision=20, scale=4), nullable=True),
        sa.Column("term_source", sa.String(length=150), nullable=True),
        sa.Column("restatement_reason", sa.String(length=255), nullable=True),
        sa.Column("supersedes_id", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("record_version", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_instrument_terms"),
        sa.ForeignKeyConstraint(
            ["instrument_id"],
            ["instrument.id"],
            name="fk_instrument_terms_instrument_id_instrument",
        ),
        sa.ForeignKeyConstraint(
            ["supersedes_id"],
            ["instrument_terms.id"],
            name="fk_instrument_terms_supersedes_id_instrument_terms",
        ),
    )
    op.create_index("ix_instrument_terms_tenant_id", "instrument_terms", ["tenant_id"])
    op.create_index("ix_instrument_terms_instrument_id", "instrument_terms", ["instrument_id"])
    # Current-head invariant: at most one version OPEN ON BOTH axes per (tenant, instrument).
    op.create_index(
        "uq_instrument_terms_current",
        "instrument_terms",
        ["tenant_id", "instrument_id"],
        unique=True,
        postgresql_where=sa.text("valid_to IS NULL AND system_to IS NULL"),
    )

    op.create_table(
        "identifier_xref",
        *_ev_head_columns(),
        sa.Column("entity_type", sa.String(length=50), nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("scheme", sa.String(length=50), nullable=False),
        sa.Column("value", sa.String(length=255), nullable=False),
        sa.Column("source", sa.String(length=150), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("record_version", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_identifier_xref"),
    )
    op.create_index("ix_identifier_xref_tenant_id", "identifier_xref", ["tenant_id"])
    op.create_index(
        "ix_identifier_xref_entity", "identifier_xref", ["entity_type", "entity_id"]
    )
    # OD-P1B-G active-only structural uniqueness for the deterministic-or-ambiguity resolver.
    op.create_index(
        "uq_identifier_xref_active",
        "identifier_xref",
        ["tenant_id", "scheme", "value"],
        unique=True,
        postgresql_where=sa.text("valid_to IS NULL"),
    )

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
    op.drop_table("identifier_xref")
    op.drop_table("instrument_terms")
    op.drop_table("instrument")
