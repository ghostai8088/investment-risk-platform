"""API-1b: the additive ``calculation_run.scope_portfolio_id`` column + its read index.

The ROOT portfolio a governed run was scoped to (OD-API-1b-A). Added additively to the SHIPPED
status-mutable ``calculation_run`` table — the EXACT ``environment_id`` (0018) / ``failure_reason``
(0027) precedent: a non-breaking ADD COLUMN, the table is NOT otherwise touched and stays out of
``APPEND_ONLY_TABLES`` (it is status-mutable; the column is stamped-at-creation, never mutated).

**Not a security boundary** — a WITHIN-TENANT scope LABEL. Tenant isolation stays the existing
``tenant_isolation_calculation_run`` RLS policy (0001, keyed on ``tenant_id``): adding a column does
NOT touch the policy. No GRANT re-issue is needed (``irp_ops`` holds no grant on ``calculation_run``,
and PG table-level grants inherit to future columns). No trigger (``calculation_run`` is not in any
``APPEND_ONLY_TABLES``). Nullable — pre-0046 runs (and any snapshot-consume-rooted run) stay NULL and
are honestly unresolvable by the Class-C entity reads (OD-API-1b-D).

``ix_calculation_run_scope_portfolio_id`` backs the "latest VaR / active-risk for portfolio P" read
(``CalculationRun.scope_portfolio_id`` equality filter, OD-API-1b-C).

Every DDL identifier here is <= 63 chars (asserted below — the P3-8/BT-1 lesson). Downgrade is the
symmetric one-liner pair (drop the index, drop the column) — no DML, no zero-row trap, so no
dedicated non-superuser downgrade test is required (the 0018/0027 additive-column precedent).

Revision ID: 0046_run_scope_portfolio
Revises: 0045_pacing_projection
Create Date: 2026-07-21
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from irp_shared.db.types import GUID

revision: str = "0046_run_scope_portfolio"
down_revision: str | None = "0045_pacing_projection"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_IDENTIFIERS = (
    "scope_portfolio_id",
    "ix_calculation_run_scope_portfolio_id",
)
assert all(len(name) <= 63 for name in _IDENTIFIERS), [
    name for name in _IDENTIFIERS if len(name) > 63
]


def upgrade() -> None:
    # Additive nullable column on the SHIPPED status-mutable calculation_run table (the 0018
    # environment_id precedent) — no RLS/grant/trigger change.
    op.add_column(
        "calculation_run",
        sa.Column("scope_portfolio_id", GUID(), nullable=True),
    )
    op.create_index(
        "ix_calculation_run_scope_portfolio_id",
        "calculation_run",
        ["scope_portfolio_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_calculation_run_scope_portfolio_id", table_name="calculation_run")
    op.drop_column("calculation_run", "scope_portfolio_id")
