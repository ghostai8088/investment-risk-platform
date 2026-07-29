"""REF-1: governed classification dimensions — scheme + node (hybrid) and assignment (proprietary).

Wave-14 slice 0. Three tables in **two tenancy classes**, ratified at OQ-REF-1-1…30:

- ``classification_scheme`` (ENT-066) + ``classification_node`` (ENT-067) — EV vocabulary, and the
  FIRST extension of the closed hybrid set since P1B-0. **AD-013-R2** takes AD-013-R1's approved
  global-standard-reference set from five tables to **seven**. Each gets the ASYMMETRIC policy:
  ``USING`` admits own-tenant OR SYSTEM, ``WITH CHECK`` stays own-tenant only, so SYSTEM rows are
  writable only under system context. Both get their own policy — an unpoliced child is a leak
  (the 0008 ``calendar_holiday``/``rating_grade`` precedent).
- ``classification_assignment`` (ENT-068) — **FR bitemporal, PROPRIETARY, SYMMETRIC** RLS. It
  attaches to a firm's own instruments/issuers, so it is never hybrid (AD-013's tenant-scoped
  "internal classifications" clause; OD-P1B-C's MNPI argument; and independently a vendor's
  issuer→code mapping is per-tenant licensed content, the ``fx_rate`` precedent). **The SYSTEM
  literal must NEVER appear in this table's policy, in either arm.**

**Why this migration creates its own policies instead of extending 0008 (OQ-REF-1-12).** Migration
0008's ``HYBRID_TABLES`` literal is not documentation and not a mirror: it DRIVES 0008's own
``CREATE POLICY`` loop and its downgrade ``DROP POLICY`` loop. Adding a name to it would make
``alembic upgrade head`` from zero attempt to police a table 0008 never creates — breaking the exact
path CI's migration job and local PG validation take. 0008 therefore stays **byte-untouched** and
each migration keeps its DDL frozen at what it shipped; the single closed-set DECLARATION for
guards is ``reference.models.HYBRID_TABLES``, which unions this migration's tables in.

**Policies are written with BOTH arms explicit.** In PostgreSQL a policy created without a
``WITH CHECK`` clause reuses ``USING`` as the write check — which on a hybrid (own-OR-SYSTEM)
policy is precisely the cross-tenant write breach 0008 warns about, and ``pg_policies.with_check``
then reads NULL so a naive "no SYSTEM in with_check" audit passes it. The floor shipped with this
slice tests ``COALESCE(with_check, qual)`` for that reason.

NOT append-only: ``classification_assignment`` is FR, and the FR protocol requires close-out
UPDATEs to ``valid_to``/``system_to`` (the 0023 ``factor_return`` / 0034 ``proxy_mapping``
precedent). Content-immutability of a closed version is service-enforced + tested.

**Downgrade is honestly destructive and is exercised for real.** Dropping these tables destroys
captured classification assignments and the seeded taxonomy. FORCE RLS binds even the table owner,
so the DELETE-then-DROP path is sandwiched with RLS toggles — an unsandwiched delete under a
non-superuser migration role silently matches ZERO rows (the 0041 lesson, proven live).

No new audit code (REFERENCE.* is reused with a new ``entity_type``), no governed number, no model
version. Counts unchanged. ``audit/service.py`` FROZEN.

Revision ID: 0056_classification
Revises: 0055_sharpe_ratio_result
Create Date: 2026-07-29
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0056_classification"
down_revision: str | None = "0055_sharpe_ratio_result"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: This migration's OWN frozen hybrid tuple — the tables IT creates and polices. Never edited by a
#: later slice (see the module docstring); a future hybrid table carries its own tuple in its own
#: migration, and ``reference.models.HYBRID_TABLES`` is the union that guards assert against.
HYBRID_TABLES: tuple[str, ...] = ("classification_scheme", "classification_node")

#: Proprietary/symmetric — the SYSTEM literal must never touch these.
TENANT_SCOPED_TABLES: tuple[str, ...] = ("classification_assignment",)

#: Mirrors ``SYSTEM_TENANT_ID`` in ``irp_shared.tenancy``; inlined as a literal because a migration
#: must be frozen against application constants (the shared-constant landmine class).
SYSTEM_TENANT_ID = "00000000-0000-0000-0000-000000000001"


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


def upgrade() -> None:
    # --- ENT-066: classification_scheme (EV, hybrid). A revision is a NEW row, so the key carries
    # --- version_label (OQ-REF-1-10) — assignments FK the scheme VERSION, never the family.
    op.create_table(
        "classification_scheme",
        *_ev_head_columns(),
        sa.Column("scheme_family", sa.String(length=50), nullable=False),
        sa.Column("version_label", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("authority", sa.String(length=100), nullable=True),
        sa.Column("dimension_kind", sa.String(length=30), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("record_version", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_classification_scheme"),
        sa.UniqueConstraint(
            "tenant_id",
            "scheme_family",
            "version_label",
            name="uq_classification_scheme_tenant_family_version",
        ),
    )
    op.create_index(
        "ix_classification_scheme_tenant_id", "classification_scheme", ["tenant_id"]
    )

    # --- ENT-067: classification_node (EV, hybrid, own policy). PLAIN parent self-FK — deliberately
    # --- not intra-tenant, so a tenant can shadow ONE node against the SYSTEM parent its USING
    # --- already admits (the rating_grade / calendar_holiday shape). An intra-tenant parent would
    # --- force a full-subtree duplication, which is not AD-013-R1's shadow-one-row override.
    op.create_table(
        "classification_node",
        *_ev_head_columns(),
        sa.Column("scheme_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("level", sa.Integer(), nullable=False),
        sa.Column("parent_node_id", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column("record_version", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_classification_node"),
        sa.UniqueConstraint(
            "tenant_id", "scheme_id", "code", name="uq_classification_node_tenant_scheme_code"
        ),
        sa.ForeignKeyConstraint(
            ["scheme_id"],
            ["classification_scheme.id"],
            name="fk_classification_node_scheme_id_classification_scheme",
        ),
        sa.ForeignKeyConstraint(
            ["parent_node_id"],
            ["classification_node.id"],
            name="fk_classification_node_parent_node_id_classification_node",
        ),
    )
    op.create_index("ix_classification_node_tenant_id", "classification_node", ["tenant_id"])
    op.create_index("ix_classification_node_scheme_id", "classification_node", ["scheme_id"])
    op.create_index(
        "ix_classification_node_parent_node_id", "classification_node", ["parent_node_id"]
    )

    # --- ENT-068: classification_assignment (FR bitemporal, PROPRIETARY/symmetric).
    # --- node_code is denormalized TEXT, not an FK: PG referential checks bypass RLS, so an FK
    # --- would let a tenant bind a node its own USING cannot see. Resolution is a fail-closed
    # --- app-side refusal in the capture binder (OQ-REF-1-20).
    op.create_table(
        "classification_assignment",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("system_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("system_to", sa.DateTime(timezone=True), nullable=True),
        *_timestamp_columns(),
        sa.Column("entity_type", sa.String(length=50), nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("scheme_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("dimension_kind", sa.String(length=30), nullable=False),
        sa.Column("node_code", sa.String(length=50), nullable=False),
        # NOT NULL with a NOT_APPLICABLE sentinel + a binder-enforced kind<->basis invariant (the
        # curve_type <-> reference_key / REFERENCE_KEY_NONE precedent, OD-P2-5-K). A nullable
        # discriminator could not do the job basis exists for: stopping two incomparable
        # conventions being silently mixed inside one concentration number.
        sa.Column("basis", sa.String(length=40), nullable=False),
        sa.Column("restatement_reason", sa.String(length=255), nullable=True),
        sa.Column("supersedes_id", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("record_version", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_classification_assignment"),
        sa.ForeignKeyConstraint(
            ["scheme_id"],
            ["classification_scheme.id"],
            name="fk_classification_assignment_scheme_id_classification_scheme",
        ),
        sa.ForeignKeyConstraint(
            ["supersedes_id"],
            ["classification_assignment.id"],
            # 63-char PG identifier limit: the convention default would be 68 (P4 dry-run find).
            name="fk_classification_assignment_supersedes_id",
        ),
    )
    op.create_index(
        "ix_classification_assignment_tenant_id", "classification_assignment", ["tenant_id"]
    )
    op.create_index(
        "ix_classification_assignment_entity_id", "classification_assignment", ["entity_id"]
    )
    op.create_index(
        "ix_classification_assignment_scheme_id", "classification_assignment", ["scheme_id"]
    )
    # Current head on BOTH axes: exactly one OPEN assignment per
    # (entity, scheme VERSION, dimension). scheme_id participates deliberately — one instrument may
    # legitimately carry an ISIC sector AND a NACE sector at once (OQ-REF-1-8).
    op.create_index(
        "uq_classification_assignment_current",
        "classification_assignment",
        ["tenant_id", "entity_type", "entity_id", "scheme_id", "dimension_kind"],
        unique=True,
        postgresql_where=sa.text("valid_to IS NULL AND system_to IS NULL"),
    )

    # --- Asymmetric HYBRID RLS (AD-013-R2): USING own-OR-SYSTEM, WITH CHECK own-only.
    # --- BOTH arms are written explicitly. Omitting WITH CHECK makes PostgreSQL reuse USING as the
    # --- write check — the cross-tenant write breach — while pg_policies.with_check reads NULL.
    for table in HYBRID_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY tenant_isolation_{table} ON {table} "
            f"USING (tenant_id::text = current_setting('app.current_tenant', true) "
            f"OR tenant_id::text = '{SYSTEM_TENANT_ID}') "
            f"WITH CHECK (tenant_id::text = current_setting('app.current_tenant', true))"
        )

    # --- Tenant isolation: SYMMETRIC RLS (USING == WITH CHECK == own-tenant); NEVER hybrid.
    for table in TENANT_SCOPED_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY tenant_isolation_{table} ON {table} "
            f"USING (tenant_id::text = current_setting('app.current_tenant', true)) "
            f"WITH CHECK (tenant_id::text = current_setting('app.current_tenant', true))"
        )


def downgrade() -> None:
    """Drop all three tables — honestly destructive, and exercised with rows present.

    NO RLS sandwich and no pre-DELETE here, deliberately. The 0041/0053 sandwich exists because
    those downgrades ran **DML** (a DELETE) against tables that SURVIVE the downgrade, and FORCE
    RLS binds even the owner so an unsandwiched DELETE silently matches ZERO rows. This downgrade
    runs **DDL**: RLS governs DML only, so ``DROP TABLE`` succeeds regardless and takes every row
    with it. Copying the sandwich here would be ceremony that proves nothing — the P4 dry run
    confirmed the drop is destructive with one row staged in each of the three tables.

    Children before parents: ``classification_assignment`` and ``classification_node`` both FK the
    scheme, and the FKs carry no ON DELETE clause.
    """
    for table in (*HYBRID_TABLES, *TENANT_SCOPED_TABLES):
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation_{table} ON {table}")

    op.drop_table("classification_assignment")
    op.drop_table("classification_node")
    op.drop_table("classification_scheme")
