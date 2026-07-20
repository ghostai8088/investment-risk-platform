"""CC-1: private capital — commitment (ENT-015, FR) + capital_call/distribution (ENT-016, IA).

The capture-first half of the Wave-8 headline (the PA-0 split): three CAPTURED-INPUT
tables — NO ``calculation_run``, NO ``model_version``, NO snapshot pin anywhere (the
house contract; the governed consumer is CC-2, a LATER slice). All three are tenant-scoped
PROPRIETARY under the **SYMMETRIC** tenant-isolation RLS loop (``USING == WITH CHECK ==
own``) — the 0009..0043 pattern. **NOT hybrid**; the 0008 hybrid loop + the closed
5-table hybrid set are UNCHANGED.

``commitment`` is FR bitemporal (close-out UPDATEs; NOT append-only — the 0034
proxy_mapping precedent) with the current-row partial-unique ``(tenant_id, portfolio_id,
instrument_id) WHERE valid_to IS NULL AND system_to IS NULL`` — exactly one OPEN
commitment per (portfolio, fund) pair; under that invariant the PAIR is the stable
commitment identity the event tables key on (version-row ids are minted per supersede
and are NOT stable link targets — the CC-1 planning verifier's structural HIGH).

``capital_call``/``distribution`` are IA append-only and TRULY immutable: BOTH are in
``APPEND_ONLY_TABLES`` (the ``irp_prevent_mutation`` P0001 trigger — the 0013
transaction mechanics) and carry the ORM guard. A correction is a FULL-REVERSAL append
(``reverses_id`` self-FK; the negation sign convention), race-closed by the per-table
partial-unique ``ON (reverses_id) WHERE reverses_id IS NOT NULL``. Their
``commitment_version_id`` is a PROVENANCE-ONLY plain GUID echo — deliberately NOT an FK.

**Downgrade is honestly destructive**: it DROPS all three tables and every captured
commitment/call/distribution row in them (captured inputs have no other home). Triggers
and policies are dropped explicitly first; the event tables drop before ``commitment``.

Every DDL identifier here is <= 63 chars (asserted below — the P3-8/BT-1 lesson).

Revision ID: 0044_private_capital
Revises: 0043_es_backtest
Create Date: 2026-07-20
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0044_private_capital"
down_revision: str | None = "0043_es_backtest"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: Symmetric tenant-isolation (NOT hybrid).
TENANT_SCOPED_TABLES = ("commitment", "capital_call", "distribution")
#: TRULY immutable IA event tables (the 0013 transaction mechanics). ``commitment`` (FR)
#: is deliberately NOT here — FR requires close-out UPDATEs (the 0034 precedent).
APPEND_ONLY_TABLES: tuple[str, ...] = ("capital_call", "distribution")

#: Every name this migration mints, checked at import time (the P3-8/BT-1 63-char lesson).
_IDENTIFIERS = (
    "commitment",
    "capital_call",
    "distribution",
    "pk_commitment",
    "pk_capital_call",
    "pk_distribution",
    "fk_commitment_portfolio_id_portfolio",
    "fk_commitment_instrument_id_instrument",
    "fk_commitment_supersedes_id_commitment",
    "fk_capital_call_portfolio_id_portfolio",
    "fk_capital_call_instrument_id_instrument",
    "fk_capital_call_reverses_id_capital_call",
    "fk_distribution_portfolio_id_portfolio",
    "fk_distribution_instrument_id_instrument",
    "fk_distribution_reverses_id_distribution",
    "ix_commitment_tenant_id",
    "ix_commitment_portfolio_id",
    "ix_commitment_instrument_id",
    "ix_capital_call_tenant_id",
    "ix_capital_call_portfolio_id",
    "ix_capital_call_instrument_id",
    "ix_distribution_tenant_id",
    "ix_distribution_portfolio_id",
    "ix_distribution_instrument_id",
    "uq_commitment_current",
    "uq_capital_call_reverses",
    "uq_distribution_reverses",
    "tenant_isolation_commitment",
    "tenant_isolation_capital_call",
    "tenant_isolation_distribution",
    "capital_call_append_only",
    "distribution_append_only",
)
assert all(len(name) <= 63 for name in _IDENTIFIERS), [
    name for name in _IDENTIFIERS if len(name) > 63
]


def _timestamp_columns() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(length=255), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by", sa.String(length=255), nullable=True),
    ]


def _event_table(name: str, extra: list[sa.Column]) -> None:
    """Create one IA event table (NO timestamp columns — the 0013 transaction shape)."""
    op.create_table(
        name,
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("system_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("portfolio_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("instrument_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("commitment_version_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("event_date", sa.Date(), nullable=False),
        sa.Column("amount", sa.Numeric(precision=20, scale=6), nullable=False),
        sa.Column("currency_code", sa.String(length=3), nullable=False),
        *extra,
        sa.Column("external_ref", sa.String(length=150), nullable=True),
        sa.Column("reverses_id", postgresql.UUID(as_uuid=False), nullable=True),
        sa.PrimaryKeyConstraint("id", name=f"pk_{name}"),
        sa.ForeignKeyConstraint(
            ["portfolio_id"], ["portfolio.id"], name=f"fk_{name}_portfolio_id_portfolio"
        ),
        sa.ForeignKeyConstraint(
            ["instrument_id"], ["instrument.id"], name=f"fk_{name}_instrument_id_instrument"
        ),
        sa.ForeignKeyConstraint(
            ["reverses_id"], [f"{name}.id"], name=f"fk_{name}_reverses_id_{name}"
        ),
    )
    op.create_index(f"ix_{name}_tenant_id", name, ["tenant_id"])
    op.create_index(f"ix_{name}_portfolio_id", name, ["portfolio_id"])
    op.create_index(f"ix_{name}_instrument_id", name, ["instrument_id"])
    op.create_index(
        f"uq_{name}_reverses",
        name,
        ["reverses_id"],
        unique=True,
        postgresql_where=sa.text("reverses_id IS NOT NULL"),
    )


def upgrade() -> None:
    op.create_table(
        "commitment",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("system_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("system_to", sa.DateTime(timezone=True), nullable=True),
        *_timestamp_columns(),
        sa.Column("portfolio_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("instrument_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("committed_amount", sa.Numeric(precision=20, scale=6), nullable=False),
        sa.Column("currency_code", sa.String(length=3), nullable=False),
        sa.Column("commitment_date", sa.Date(), nullable=False),
        sa.Column("restatement_reason", sa.String(length=255), nullable=True),
        sa.Column("supersedes_id", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("record_version", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_commitment"),
        sa.ForeignKeyConstraint(
            ["portfolio_id"], ["portfolio.id"], name="fk_commitment_portfolio_id_portfolio"
        ),
        sa.ForeignKeyConstraint(
            ["instrument_id"], ["instrument.id"], name="fk_commitment_instrument_id_instrument"
        ),
        sa.ForeignKeyConstraint(
            ["supersedes_id"], ["commitment.id"], name="fk_commitment_supersedes_id_commitment"
        ),
    )
    op.create_index("ix_commitment_tenant_id", "commitment", ["tenant_id"])
    op.create_index("ix_commitment_portfolio_id", "commitment", ["portfolio_id"])
    op.create_index("ix_commitment_instrument_id", "commitment", ["instrument_id"])
    op.create_index(
        "uq_commitment_current",
        "commitment",
        ["tenant_id", "portfolio_id", "instrument_id"],
        unique=True,
        postgresql_where=sa.text("valid_to IS NULL AND system_to IS NULL"),
    )

    _event_table(
        "capital_call",
        [sa.Column("call_type", sa.String(length=30), nullable=False)],
    )
    _event_table(
        "distribution",
        [
            sa.Column("distribution_type", sa.String(length=30), nullable=False),
            sa.Column(
                "is_recallable",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("false"),
            ),
        ],
    )

    # --- Tenant isolation: SYMMETRIC RLS (USING == WITH CHECK == own-tenant); NOT hybrid (BR-17).
    for table in TENANT_SCOPED_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY tenant_isolation_{table} ON {table} "
            f"USING (tenant_id::text = current_setting('app.current_tenant', true)) "
            f"WITH CHECK (tenant_id::text = current_setting('app.current_tenant', true))"
        )

    # --- Truly immutable IA event tables: the irp_prevent_mutation P0001 trigger (0013 mechanics).
    for table in APPEND_ONLY_TABLES:
        op.execute(
            f"CREATE TRIGGER {table}_append_only BEFORE UPDATE OR DELETE ON {table} "
            f"FOR EACH ROW EXECUTE FUNCTION irp_prevent_mutation()"
        )


def downgrade() -> None:
    # Honestly destructive: drops every captured commitment/call/distribution row.
    for table in APPEND_ONLY_TABLES:
        op.execute(f"DROP TRIGGER IF EXISTS {table}_append_only ON {table}")
    for table in TENANT_SCOPED_TABLES:
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation_{table} ON {table}")
    # Event tables first (no cross-FK to commitment exists — the provenance echo is a
    # plain column — but children-first is the stated order).
    op.drop_table("capital_call")
    op.drop_table("distribution")
    op.drop_table("commitment")
