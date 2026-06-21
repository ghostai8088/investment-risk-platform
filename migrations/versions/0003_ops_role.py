"""Create the BYPASSRLS ops role for controlled cross-tenant operations (AD-015).

Creates role ``irp_ops`` with the BYPASSRLS attribute and the minimum grants the audit-verify
ops tooling needs (SELECT on audit_event; SELECT, INSERT on audit_checkpoint). The role is
created **without LOGIN/password** here — login credentials are a privileged secret assigned by
infrastructure out-of-band (BR-10), never stored in source. The application role is never granted
BYPASSRLS. PostgreSQL-only (no-op on other engines). Role/grant changes are not schema and do not
affect the ``alembic check`` drift gate.

Revision ID: 0003_ops_role
Revises: 0002_entitlement_seed
Create Date: 2026-06-19
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0003_ops_role"
down_revision: str | None = "0002_entitlement_seed"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OPS_ROLE = "irp_ops"  # fixed identifier (no user input); interpolation is safe


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute(
        f"DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{OPS_ROLE}') "
        f"THEN CREATE ROLE {OPS_ROLE} BYPASSRLS; END IF; END $$"
    )
    op.execute(f"GRANT SELECT ON audit_event TO {OPS_ROLE}")
    op.execute(f"GRANT SELECT, INSERT ON audit_checkpoint TO {OPS_ROLE}")


def downgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute(f"REVOKE ALL ON audit_event FROM {OPS_ROLE}")
    op.execute(f"REVOKE ALL ON audit_checkpoint FROM {OPS_ROLE}")
    op.execute(f"DROP ROLE IF EXISTS {OPS_ROLE}")
