"""Sync the entitlement catalog into EXISTING databases (RPT-2 review finding, BLOCKING class).

**The defect this repairs is platform-wide and predates RPT-2.** Since P0.5 the mint procedure has
been "append to ``entitlement/bootstrap.py``; ``0002`` live-imports it; a fresh ``alembic upgrade
head`` seeds it" — recorded as the precedent in ``0002``'s own docstring and in
``entitlement_sod_model.md``. That is true only for a database created AFTER the mint. ``0002`` is
long since applied on any live deployment, so ``upgrade head`` is a no-op there and **every code
minted after a database was created has never reached it**.

Proven by execution on the local PG at head ``0063`` (RPT-2 review):

    report.* rows before        -> 0   (simulating the pre-mint state of a live database)
    alembic upgrade head        -> UPGRADE_EXIT=0
    report.* rows after         -> 0   ← the mint is undeliverable

The consequence is not cosmetic. ``require_permission`` is deny-by-default: a code absent from the
database denies EVERY holder, so on a live deployment the RPT-2 report surface would 403 for all
five ratified roles — while every unit test, the fresh-database smoke, and CI all pass, because
each of them builds its database from empty. The same silence has covered `liquidity.*`,
`concentration.*`, `schedule.*`, `limit.*`, `breach.*` and the rest since their mints.

**This migration is the class fix (P10), not the instance fix.** It syncs the WHOLE catalog and the
WHOLE role-template grant set, so every code minted since P0.5 lands wherever it is missing.

**Idempotent by construction, and additive only.** Every id is a deterministic ``uuid5``
(``permission_id`` / ``role_id`` / ``role_permission_id``), so "insert what is absent" needs no
bookkeeping and re-running changes nothing. It NEVER updates or deletes: a description edited in a
live database stays edited, and a grant an operator revoked deliberately is NOT silently restored —
this migration can add a missing grant, never re-add a removed one is beyond its knowledge, so it
adds only rows whose deterministic id is absent entirely. Revoking a template grant is an
operational act that lives in the database; this migration must not fight it.

**The standing consequence, recorded so the next mint does not re-learn it:** appending to
``bootstrap.py`` is NOT sufficient for a live deployment. A mint needs either its own sync
migration or a re-run of this pattern. The RPT-2 slice record carries this as a ratification item.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

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

revision: str = "0064_entitlement_sync"
down_revision: str | None = "0063_report_generation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SYNC_TS = datetime(2026, 8, 7, 0, 0, 0, tzinfo=UTC)

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
    """The system-tenant RLS context — ``role`` is tenant-scoped (the 0002 pattern)."""
    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            sa.text("SELECT set_config('app.current_tenant', :t, true)").bindparams(
                t=SYSTEM_TENANT_ID
            )
        )


def _existing_ids(table: sa.TableClause, ids: list[str]) -> set[str]:
    """Which of these deterministic ids are already present."""
    if not ids:
        return set()
    bind = op.get_bind()
    rows = bind.execute(sa.select(table.c.id).where(table.c.id.in_(ids))).scalars().all()
    return {str(r) for r in rows}


def upgrade() -> None:
    # --- permissions -----------------------------------------------------------------------
    want_perms = {permission_id(code): (code, desc) for code, desc in PERMISSIONS}
    have = _existing_ids(_permission, list(want_perms))
    missing = [
        {
            "id": pid,
            "code": code,
            "description": desc,
            "created_at": SYNC_TS,
            "updated_at": SYNC_TS,
        }
        for pid, (code, desc) in want_perms.items()
        if pid not in have
    ]
    if missing:
        op.bulk_insert(_permission, missing)

    # --- roles (tenant-scoped: RLS context first) ------------------------------------------
    _set_system_tenant()
    want_roles = {role_id(name): name for name in ROLE_TEMPLATES}
    have_roles = _existing_ids(_role, list(want_roles))
    missing_roles = [
        {
            "id": rid,
            "tenant_id": SYSTEM_TENANT_ID,
            "code": name,
            "name": name.replace("_", " ").title(),
            "created_at": SYNC_TS,
            "updated_at": SYNC_TS,
        }
        for rid, name in want_roles.items()
        if rid not in have_roles
    ]
    if missing_roles:
        op.bulk_insert(_role, missing_roles)

    # --- grants ------------------------------------------------------------------------------
    want_grants = {
        role_permission_id(name, code): (name, code)
        for name, codes in ROLE_TEMPLATES.items()
        for code in codes
    }
    have_grants = _existing_ids(_role_permission, list(want_grants))
    missing_grants = [
        {"id": gid, "role_id": role_id(name), "permission_id": permission_id(code)}
        for gid, (name, code) in want_grants.items()
        if gid not in have_grants
    ]
    if missing_grants:
        op.bulk_insert(_role_permission, missing_grants)


def downgrade() -> None:
    """Deliberately a NO-OP.

    This migration cannot know which rows it inserted versus which ``0002`` (or an operator)
    created — the ids are deterministic, so they are indistinguishable by construction. Deleting
    the catalog on downgrade would revoke permissions this migration never granted and take the
    entitlement surface of a live deployment with it. A no-op downgrade is the honest behaviour;
    the schema is unchanged either way.
    """
