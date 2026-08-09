"""The catalog sync — ONE implementation, and it consults the revocation ledger (P17).

Permissions live in ``bootstrap.PERMISSIONS`` and are seeded by migration ``0002`` into a database
built from empty. A database already running never sees a code appended afterwards, so appending to
the constant is not a mint — it is a mint for future deployments only, while ``require_permission``
denies by default and 403s every holder in production. Migration ``0064`` is the class fix: sync
the whole catalog into whatever is already there.

**Why the logic lives here rather than inline in the migration.** Two properties must hold for
every sync that will ever run, not just the first one:

1. it is additive and idempotent (deterministic ``uuid5`` ids, insert-what-is-absent), and
2. it does not resurrect a grant an administrator deliberately revoked.

Property 2 is the Wave-16 close finding. A revoked grant and a never-delivered grant are the SAME
database state — the id is a function of ``(role, code)`` alone — so no amount of care inside a
migration can distinguish them. The only thing that can is a record of the revocation, which is
what ``role_permission_revocation`` is. Keeping both properties in one function is what stops the
next sync migration from re-deriving only the first one; FK-1 retired a duplicated control for
exactly this reason (two mechanisms for one property is how the next reader trusts the wrong one).

The ledger's ABSENCE is tolerated and REPORTED, never inferred as "nothing was revoked": a database
below the migration that creates the table has no ledger, and the honest statement is "could not
consult", which ``SyncReport.ledger_present`` carries to the caller.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.engine import Connection

from irp_shared.db.types import GUID
from irp_shared.entitlement.bootstrap import (
    PERMISSIONS,
    ROLE_TEMPLATES,
    SYSTEM_TENANT_ID,
    permission_id,
    role_id,
    role_permission_id,
)

logger = logging.getLogger(__name__)

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
_revocation = sa.table(
    "role_permission_revocation",
    sa.column("id", GUID()),
    sa.column("role_id", GUID()),
    sa.column("permission_id", GUID()),
)


@dataclass(frozen=True)
class SyncReport:
    """What a sync actually did — returned so a caller can log it and a test can assert on it."""

    permissions_inserted: int = 0
    roles_inserted: int = 0
    grants_inserted: int = 0
    #: ``(role_code, permission_code)`` pairs the ledger said were revoked and the sync SKIPPED.
    grants_skipped_revoked: tuple[tuple[str, str], ...] = ()
    #: False when the revocation table does not exist yet (a database below its migration). The
    #: sync still runs; the caller is told it could not consult rather than told nothing was
    #: revoked — those are different facts and only one of them is knowable here.
    ledger_present: bool = True
    #: Deferred log lines, emitted by ``sync_catalog`` — kept on the report so tests can read them.
    messages: tuple[str, ...] = field(default=())


def _table_exists(bind: Connection, name: str) -> bool:
    return sa.inspect(bind).has_table(name)


def revoked_grant_ids(bind: Connection) -> tuple[set[str], bool]:
    """Deterministic ``role_permission`` ids the ledger records as revoked, and whether it existed.

    Returns ``(ids, ledger_present)``. An absent table yields ``(set(), False)`` — deliberately not
    an exception: a sync must still be able to run on a database created before the ledger.
    """
    if not _table_exists(bind, "role_permission_revocation"):
        return set(), False
    rows = bind.execute(sa.select(_revocation.c.role_id, _revocation.c.permission_id)).all()
    revoked_pairs = {(str(r), str(p)) for r, p in rows}
    # The ledger stores the ROLE and PERMISSION ids (mirroring ``role_permission``); the sync works
    # in grant ids. Map through the deterministic derivation rather than storing a third id.
    return (
        {
            role_permission_id(name, code)
            for name, codes in ROLE_TEMPLATES.items()
            for code in codes
            if (role_id(name), permission_id(code)) in revoked_pairs
        },
        True,
    )


def _existing_ids(bind: Connection, table: sa.TableClause, ids: list[str]) -> set[str]:
    if not ids:
        return set()
    rows = bind.execute(sa.select(table.c.id).where(table.c.id.in_(ids))).scalars().all()
    return {str(r) for r in rows}


def sync_catalog(bind: Connection, *, now: datetime) -> SyncReport:
    """Insert every catalog row that is absent, EXCEPT grants the ledger records as revoked.

    Additive only: never UPDATEs, never DELETEs. A description edited in a live database stays
    edited; a role renamed stays renamed. ``now`` is passed in rather than read from the clock so a
    migration stamps a fixed, reproducible timestamp.
    """
    messages: list[str] = []

    want_perms = {permission_id(code): (code, desc) for code, desc in PERMISSIONS}
    have = _existing_ids(bind, _permission, list(want_perms))
    missing = [
        {
            "id": pid,
            "code": code,
            "description": desc,
            "created_at": now,
            "updated_at": now,
        }
        for pid, (code, desc) in want_perms.items()
        if pid not in have
    ]
    if missing:
        bind.execute(_permission.insert(), missing)

    # ``role`` is tenant-scoped, so the system-tenant RLS context must be armed before touching it.
    if bind.dialect.name == "postgresql":
        bind.execute(
            sa.text("SELECT set_config('app.current_tenant', :t, true)").bindparams(
                t=SYSTEM_TENANT_ID
            )
        )
    want_roles = {role_id(name): name for name in ROLE_TEMPLATES}
    have_roles = _existing_ids(bind, _role, list(want_roles))
    missing_roles = [
        {
            "id": rid,
            "tenant_id": SYSTEM_TENANT_ID,
            "code": name,
            "name": name.replace("_", " ").title(),
            "created_at": now,
            "updated_at": now,
        }
        for rid, name in want_roles.items()
        if rid not in have_roles
    ]
    if missing_roles:
        bind.execute(_role.insert(), missing_roles)

    revoked, ledger_present = revoked_grant_ids(bind)
    if not ledger_present:
        messages.append(
            "entitlement sync: role_permission_revocation is absent — revoked template grants "
            "COULD NOT be consulted on this database (not: none were revoked)"
        )

    want_grants = {
        role_permission_id(name, code): (name, code)
        for name, codes in ROLE_TEMPLATES.items()
        for code in codes
    }
    have_grants = _existing_ids(bind, _role_permission, list(want_grants))
    skipped: list[tuple[str, str]] = []
    missing_grants = []
    for gid, (name, code) in want_grants.items():
        if gid in have_grants:
            continue
        if gid in revoked:
            skipped.append((name, code))
            continue
        missing_grants.append(
            {"id": gid, "role_id": role_id(name), "permission_id": permission_id(code)}
        )
    if missing_grants:
        bind.execute(_role_permission.insert(), missing_grants)
    for name, code in sorted(skipped):
        messages.append(
            f"entitlement sync: NOT restoring {name} -> {code} — revoked in "
            "role_permission_revocation"
        )

    for line in messages:
        logger.warning(line)

    return SyncReport(
        permissions_inserted=len(missing),
        roles_inserted=len(missing_roles),
        grants_inserted=len(missing_grants),
        grants_skipped_revoked=tuple(sorted(skipped)),
        ledger_present=ledger_present,
        messages=tuple(messages),
    )
