"""Entitlement bootstrap seed: baseline permissions and role templates (P0.5).

Data-only migration (no DDL): seeds the global permission catalog and baseline role
templates (under the reserved system tenant) so later phases' deny-by-default checks resolve
against real grants. Roles are tenant-scoped (row-level security), so role inserts/deletes run
with the system-tenant RLS context via ``set_config('app.current_tenant', …, local=true)``.

Catalog/templates live in ``irp_shared.entitlement.bootstrap`` (one importable source of truth).

Revision ID: 0002_entitlement_seed
Revises: 0001_foundation
Create Date: 2026-06-19
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timezone

import sqlalchemy as sa
from alembic import op

from irp_shared.db.types import GUID
from irp_shared.entitlement.bootstrap import (
    PERMISSIONS,
    ROLE_TEMPLATES,
    SYSTEM_TENANT_ID,
    permission_id,
    role_id,
    role_permission_id,
)

revision: str = "0002_entitlement_seed"
down_revision: str | None = "0001_foundation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SEED_TS = datetime(2026, 6, 19, 0, 0, 0, tzinfo=timezone.utc)

_permission = sa.table(
    "permission",
    sa.column("id", GUID()),
    sa.column("code", sa.String()),
    sa.column("description", sa.String()),
    sa.column("created_at", sa.DateTime(timezone=True)),
    sa.column("updated_at", sa.DateTime(timezone=True)),
)
_role = sa.table(
    "role",
    sa.column("id", GUID()),
    sa.column("tenant_id", GUID()),
    sa.column("code", sa.String()),
    sa.column("name", sa.String()),
    sa.column("created_at", sa.DateTime(timezone=True)),
    sa.column("updated_at", sa.DateTime(timezone=True)),
)
_role_permission = sa.table(
    "role_permission",
    sa.column("id", GUID()),
    sa.column("role_id", GUID()),
    sa.column("permission_id", GUID()),
)


def _set_system_tenant() -> None:
    """Set the system-tenant RLS context for the current (transactional) migration."""
    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            sa.text("SELECT set_config('app.current_tenant', :t, true)").bindparams(
                t=SYSTEM_TENANT_ID
            )
        )


def upgrade() -> None:
    op.bulk_insert(
        _permission,
        [
            {"id": permission_id(code), "code": code, "description": desc,
             "created_at": SEED_TS, "updated_at": SEED_TS}
            for code, desc in PERMISSIONS
        ],
    )

    _set_system_tenant()  # role is tenant-scoped (RLS)
    op.bulk_insert(
        _role,
        [
            {"id": role_id(name), "tenant_id": SYSTEM_TENANT_ID, "code": name,
             "name": name.replace("_", " ").title(), "created_at": SEED_TS, "updated_at": SEED_TS}
            for name in ROLE_TEMPLATES
        ],
    )

    op.bulk_insert(
        _role_permission,
        [
            {"id": role_permission_id(name, code), "role_id": role_id(name),
             "permission_id": permission_id(code)}
            for name, codes in ROLE_TEMPLATES.items()
            for code in codes
        ],
    )


def downgrade() -> None:
    rp_ids = [
        role_permission_id(name, code)
        for name, codes in ROLE_TEMPLATES.items()
        for code in codes
    ]
    role_ids = [role_id(name) for name in ROLE_TEMPLATES]
    perm_ids = [permission_id(code) for code, _ in PERMISSIONS]

    op.execute(_role_permission.delete().where(_role_permission.c.id.in_(rp_ids)))
    _set_system_tenant()  # role is tenant-scoped (RLS)
    op.execute(_role.delete().where(_role.c.id.in_(role_ids)))
    op.execute(_permission.delete().where(_permission.c.id.in_(perm_ids)))
