"""STRUCT-3 (REQ-PPM-001 clause 2, re-adjudicated 2026-08-15): the hierarchy's OWN history.

``portfolio_hierarchy_version`` (ENT-076, IA TRUE append-only) — one appended row per structural
portfolio edit, written co-transactionally by the binder from this migration on. The head table
stays the deliberate EV-mutable design (DP-1 ratified: a history table BESIDE the head, never an
EV→FR conversion); these rows are what lets the tree resolve as-of a past time by timestamp with
NO run or snapshot in scope — the clause the re-adjudication added after the G2 question found the
pin-only exploit (a full-subtree snapshot pin satisfied every earlier sentence while the entity
kept no history at all).

**The backfill is the data path** (P17): one row per EXISTING portfolio, captured from its head at
the head's ``valid_from`` and stamped ``source='0072_BACKFILL'`` so a reader can tell recorded
history from this honest reconstruction. Pre-0072 intermediate edits are unrecoverable — the head
kept no history — so an old book's earliest resolvable view is its state at this migration. The
backfill INSERT runs BEFORE the RLS/FORCE block deliberately (review fold: the first draft ran it
after FORCE with a docstring claiming RLS "was not yet forced" — false, and the insert survived
only because every current runner is a PG superuser; a hardened NOSUPERUSER migration owner would
have aborted the upgrade).

PROPRIETARY, symmetric FORCE RLS, ``irp_prevent_mutation`` trigger (0001) — the 0068 template.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from irp_shared.db.types import GUID

revision: str = "0072_portfolio_hierarchy_version"
down_revision: str | None = "0071_exposure_type_in_grain_key"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    is_pg = bind.dialect.name == "postgresql"

    op.create_table(
        "portfolio_hierarchy_version",
        sa.Column("id", GUID, nullable=False),
        sa.Column("tenant_id", GUID, nullable=False),
        sa.Column("portfolio_id", GUID, nullable=False),
        sa.Column("parent_portfolio_id", GUID, nullable=True),
        sa.Column("node_type", sa.String(50), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("base_currency_code", sa.String(3), nullable=True),
        sa.Column("record_version", sa.Integer, nullable=False),
        sa.Column("effective_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("system_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source", sa.String(20), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_portfolio_hierarchy_version"),
        sa.ForeignKeyConstraint(
            ["portfolio_id"],
            ["portfolio.id"],
            name="fk_portfolio_hierarchy_version_portfolio_id_portfolio",
        ),
        sa.UniqueConstraint(
            "portfolio_id",
            "record_version",
            name="uq_portfolio_hierarchy_version_node_version",
        ),
    )
    op.create_index(
        "ix_portfolio_hierarchy_version_tenant_id", "portfolio_hierarchy_version", ["tenant_id"]
    )
    op.create_index(
        "ix_portfolio_hierarchy_version_portfolio_id",
        "portfolio_hierarchy_version",
        ["portfolio_id"],
    )
    # The as-of read's access path: latest row per (tenant, node) at or before a timestamp.
    op.create_index(
        "ix_portfolio_hierarchy_version_tenant_effective",
        "portfolio_hierarchy_version",
        ["tenant_id", "portfolio_id", "effective_at"],
    )

    # --- the backfill FIRST (see the module docstring): every existing node's head state ------
    _backfill(bind, is_pg)

    if is_pg:
        op.execute("ALTER TABLE portfolio_hierarchy_version ENABLE ROW LEVEL SECURITY")
        op.execute("ALTER TABLE portfolio_hierarchy_version FORCE ROW LEVEL SECURITY")
        op.execute(
            "CREATE POLICY tenant_isolation_portfolio_hierarchy_version "
            "ON portfolio_hierarchy_version "
            "USING (tenant_id::text = current_setting('app.current_tenant', true)) "
            "WITH CHECK (tenant_id::text = current_setting('app.current_tenant', true))"
        )
        op.execute(
            "CREATE TRIGGER trg_portfolio_hierarchy_version_no_mutation "
            "BEFORE UPDATE OR DELETE ON portfolio_hierarchy_version "
            "FOR EACH ROW EXECUTE FUNCTION irp_prevent_mutation()"
        )


def _backfill(bind, is_pg) -> None:  # noqa: ANN001
    if is_pg:
        new_id = "gen_random_uuid()"
    else:
        # SQLite (unit tier creates via create_all; this branch covers a migrated SQLite file).
        new_id = (
            "lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || "
            "substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab', abs(random()) % 4 + 1, 1)"
            " || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))"
        )
    backfilled = bind.execute(
        sa.text(
            f"INSERT INTO portfolio_hierarchy_version "  # noqa: S608 - constants above
            f"(id, tenant_id, portfolio_id, parent_portfolio_id, node_type, name, status, "
            f"base_currency_code, record_version, effective_at, system_from, source) "
            f"SELECT {new_id}, tenant_id, id, parent_portfolio_id, node_type, name, status, "
            f"base_currency_code, record_version, valid_from, valid_from, '0072_BACKFILL' "
            f"FROM portfolio"
        )
    )
    print(  # noqa: T201 - migration console output
        f"0072: backfilled {backfilled.rowcount} hierarchy-version row(s) from portfolio heads"
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(
            "DROP TRIGGER IF EXISTS trg_portfolio_hierarchy_version_no_mutation "
            "ON portfolio_hierarchy_version"
        )
        op.execute(
            "DROP POLICY IF EXISTS tenant_isolation_portfolio_hierarchy_version "
            "ON portfolio_hierarchy_version"
        )
    op.drop_index(
        "ix_portfolio_hierarchy_version_tenant_effective", "portfolio_hierarchy_version"
    )
    op.drop_index("ix_portfolio_hierarchy_version_portfolio_id", "portfolio_hierarchy_version")
    op.drop_index("ix_portfolio_hierarchy_version_tenant_id", "portfolio_hierarchy_version")
    op.drop_table("portfolio_hierarchy_version")
