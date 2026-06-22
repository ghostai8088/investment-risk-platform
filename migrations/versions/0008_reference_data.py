"""P1B-1: reference data — currency / calendar / rating_scale (REQ-SMR-005 + REQ-SMR-004 calendar).

Adds five tenant-scoped **effective-dated (EV)** tables — ``currency`` (ENT-005), ``calendar``
(ENT-006) + ``calendar_holiday``, ``rating_scale`` (ENT-007 taxonomy) + ``rating_grade`` — and the
platform's **first asymmetric hybrid RLS loop** (AD-013-R1), distinct from the shipped symmetric loop
(0001/0004/0005/0007) which is left **untouched**:

    USING      (tenant_id = current_setting('app.current_tenant')  OR  tenant_id = SYSTEM_TENANT_ID)
    WITH CHECK (tenant_id = current_setting('app.current_tenant'))   -- single-tenant; NO system arm

So a tenant SELECTs its own rows **plus** the global SYSTEM_TENANT rows, but can only INSERT/UPDATE its
own (a write of a SYSTEM row under a tenant context fails ``WITH CHECK`` → 42501). The SYSTEM_TENANT
literal MUST appear in ``USING`` (else hybrid collapses to plain isolation) and MUST NOT appear in
``WITH CHECK`` (else any tenant could overwrite the global vocabularies — a cross-tenant breach). It is
injected as a Python f-string from the single source of truth ``entitlement.bootstrap.SYSTEM_TENANT_ID``
(a fixed reserved UUID literal, not user input). The children (``calendar_holiday`` / ``rating_grade``)
are in ``HYBRID_TABLES`` with their **own** FORCE RLS + own policy — an unpoliced child is a leak.

**None of the five is append-only** (all EV-mutable): no ``irp_prevent_mutation`` trigger, no
``APPEND_ONLY_TABLES`` entry — a ``REFERENCE.UPDATE`` must succeed at the DB. Intra-context FKs
(``calendar_holiday → calendar``, ``rating_grade → rating_scale``) carry ``fk_`` NAMING_CONVENTION
names so ``alembic check`` is drift-clean. The ``reference.*`` permissions + ``REFERENCE.CREATE`` /
``REFERENCE.UPDATE`` audit codes are seeded/activated elsewhere (bootstrap catalog + the service) —
none are created here. ``data_source`` is **NOT** made hybrid (its symmetric policy is unchanged).

Revision ID: 0008_reference_data
Revises: 0007_generic_ingestion_staging
Create Date: 2026-06-22
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from irp_shared.entitlement.bootstrap import SYSTEM_TENANT_ID

revision: str = "0008_reference_data"
down_revision: str | None = "0007_generic_ingestion_staging"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: The closed hybrid set (AD-013-R1). Every table gets the asymmetric policy; NONE is append-only.
HYBRID_TABLES = ("currency", "calendar", "calendar_holiday", "rating_scale", "rating_grade")

#: Common EV mixin columns (PrimaryKey + Tenant + EffectiveDated + Timestamp), in canonical order.
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
        "currency",
        *_ev_head_columns(),
        sa.Column("code", sa.String(length=3), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("symbol", sa.String(length=8), nullable=True),
        sa.Column("minor_units", sa.Integer(), nullable=True),
        sa.Column("numeric_code", sa.String(length=3), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("record_version", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_currency"),
        sa.UniqueConstraint("tenant_id", "code", name="uq_currency_tenant_code"),
    )
    op.create_index("ix_currency_tenant_id", "currency", ["tenant_id"])

    op.create_table(
        "calendar",
        *_ev_head_columns(),
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("mic", sa.String(length=10), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("record_version", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_calendar"),
        sa.UniqueConstraint("tenant_id", "code", name="uq_calendar_tenant_code"),
    )
    op.create_index("ix_calendar_tenant_id", "calendar", ["tenant_id"])

    op.create_table(
        "calendar_holiday",
        *_ev_head_columns(),
        sa.Column("calendar_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("holiday_date", sa.Date(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=True),
        sa.Column("recurrence", sa.String(length=20), nullable=True),
        sa.Column("record_version", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_calendar_holiday"),
        sa.ForeignKeyConstraint(
            ["calendar_id"], ["calendar.id"], name="fk_calendar_holiday_calendar_id_calendar"
        ),
        sa.UniqueConstraint(
            "tenant_id", "calendar_id", "holiday_date", name="uq_calendar_holiday_calendar_date"
        ),
    )
    op.create_index("ix_calendar_holiday_tenant_id", "calendar_holiday", ["tenant_id"])
    op.create_index("ix_calendar_holiday_calendar_id", "calendar_holiday", ["calendar_id"])

    op.create_table(
        "rating_scale",
        *_ev_head_columns(),
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("agency", sa.String(length=100), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("record_version", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_rating_scale"),
        sa.UniqueConstraint("tenant_id", "code", name="uq_rating_scale_tenant_code"),
    )
    op.create_index("ix_rating_scale_tenant_id", "rating_scale", ["tenant_id"])

    op.create_table(
        "rating_grade",
        *_ev_head_columns(),
        sa.Column("rating_scale_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("code", sa.String(length=20), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column("record_version", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_rating_grade"),
        sa.ForeignKeyConstraint(
            ["rating_scale_id"],
            ["rating_scale.id"],
            name="fk_rating_grade_rating_scale_id_rating_scale",
        ),
        sa.UniqueConstraint(
            "tenant_id", "rating_scale_id", "code", name="uq_rating_grade_scale_code"
        ),
        sa.UniqueConstraint(
            "tenant_id", "rating_scale_id", "rank", name="uq_rating_grade_scale_rank"
        ),
    )
    op.create_index("ix_rating_grade_tenant_id", "rating_grade", ["tenant_id"])
    op.create_index("ix_rating_grade_rating_scale_id", "rating_grade", ["rating_scale_id"])

    # --- Asymmetric HYBRID RLS (AD-013-R1): USING own-OR-SYSTEM, WITH CHECK own-only (NET-NEW). ---
    # Distinct from the symmetric loop; the SYSTEM literal is in USING only — NEVER in WITH CHECK.
    for table in HYBRID_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY tenant_isolation_{table} ON {table} "
            f"USING (tenant_id::text = current_setting('app.current_tenant', true) "
            f"OR tenant_id::text = '{SYSTEM_TENANT_ID}') "
            f"WITH CHECK (tenant_id::text = current_setting('app.current_tenant', true))"
        )
    # NOTE: no append-only trigger on any of the five — all EV-mutable (a REFERENCE.UPDATE succeeds).


def downgrade() -> None:
    for table in HYBRID_TABLES:
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation_{table} ON {table}")
    op.drop_table("rating_grade")
    op.drop_table("rating_scale")
    op.drop_table("calendar_holiday")
    op.drop_table("calendar")
    op.drop_table("currency")
