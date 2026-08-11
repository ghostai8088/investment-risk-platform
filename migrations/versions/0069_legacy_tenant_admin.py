"""Wave-17 close (D3): every pre-0067 tenant gets a ``tenant_admin`` role.

**The finding this pays.** ONBOARD-1b shipped tenant self-administration — the four verbs, the
four-eyes lifecycle, the ``/admin/users`` screen — and every one of them is held by exactly two
roles, ``platform_admin`` and ``tenant_admin``. ``platform_admin`` is deliberately not in
``CLONED_TEMPLATES``. Migration ``0067`` deliberately did not clone templates into backfilled
tenants ("Backfilled tenants keep exactly the roles they have"), and ``0068`` backfilled the four
verbs only ``WHERE _role.c.code == 'tenant_admin'`` — a predicate that matches nothing in a tenant
that has no such role.

So every tenant created before 2026-08-09, **including the platform's own demo tenant**, gets a 403
on the entire feature. Measured at the Wave-17 close: ``grep tenant_admin`` over ``demo/campaign.py``
returns nothing, and ``_seed_principals`` creates only ``risk_manager_2l``, ``risk_analyst_1l`` and
``auditor_3l``. The repair code that could have fixed this from the application exists and is
unreachable — ``onboard_tenant`` takes a ``tenant_id`` parameter with exactly one non-test caller
(``api/tenants.py``) which never passes it, and ``TenantCreateIn`` refuses the field outright
(a live probe returned ``['tenant_id', 'Extra inputs are not permitted']``).

**Why a migration rather than a route** (ratified at the Wave-17 close gate, D3=A): it is the
smallest change that makes the wave's headline claim true, it mints no permission and adds no
route, and the alternative — an operator-only repair verb — widens the SYSTEM-fenced surface to fix
data that is already sitting in the database. 0067's own reasoning is not contradicted: it declined
to clone the FULL template set into backfilled tenants, and this clones exactly ONE role, the one
whose absence makes a shipped feature unreachable.

**A note on the empty-set case, because it is the one that would make this decorative.**
``valid_admin_user_ids`` returns the empty set in a tenant with no admin role, so SOD-04 four-eyes
and the orphan-proof invariant evaluate as VACUOUSLY SATISFIED there. Creating the role does not by
itself create an administrator — no ``user_role`` row is written here, because choosing who
administers a tenant is not a migration's decision to make. What this delivers is the role for an
operator to assign. That is stated plainly rather than left for a reader to discover.
"""

from __future__ import annotations

from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

from irp_shared.entitlement.bootstrap import (
    ROLE_TEMPLATES,
    SYSTEM_TENANT_ID,
    permission_id,
    tenant_role_id,
    tenant_role_permission_id,
)

revision: str = "0069_legacy_tenant_admin"
down_revision: str | None = "0068_entitlement_request"
branch_labels: None = None
depends_on: None = None

#: This revision delivers no NEW permission code — every code it grants was minted and delivered by
#: `0068`. It is a ROLE backfill, so P17's `DELIVERS` gate has nothing to read here, and saying so
#: explicitly is cheaper than a reader wondering whether the declaration was forgotten.
DELIVERS: tuple[str, ...] = ()

TS = datetime(2026, 8, 11, tzinfo=UTC)

_role = sa.table(
    "role",
    sa.column("id", sa.String),
    sa.column("tenant_id", sa.String),
    sa.column("code", sa.String),
    sa.column("name", sa.String),
    sa.column("created_at", sa.DateTime),
    sa.column("updated_at", sa.DateTime),
)
_role_permission = sa.table(
    "role_permission",
    sa.column("id", sa.String),
    sa.column("role_id", sa.String),
    sa.column("permission_id", sa.String),
)
_permission = sa.table("permission", sa.column("id", sa.String))


def backfill_legacy_tenant_admin(bind: sa.engine.Connection) -> tuple[int, int]:
    """The whole of this revision, as a callable that needs no alembic op context.

    Written this way so it can be PROVEN rather than asserted. A migration whose only
    verification is "the suite still passes after it runs" tests that it does not CRASH, which is
    not the claim being made — the claim is that a tenant which could not administer itself now
    can. Returns ``(roles_created, grants_created)`` so a caller can see it did something.
    """

    # The population is the REGISTRY, not `app_user` — 0067 already made the judgement about which
    # tenant ids are real (it excludes the reserved proof tenants by name, "so a naive backfill
    # would promote a test fixture to a real tenant — a wrong fact, permanently"). Reusing its
    # answer rather than re-deriving one is the point; a second, subtly different definition of
    # "a tenant" is exactly the kind of drift this close review spent its length finding.
    tenants = [
        str(t)
        for t in bind.execute(sa.text("SELECT id FROM tenant")).scalars().all()
        if str(t) != SYSTEM_TENANT_ID
    ]
    if not tenants:
        return (0, 0)

    have_role = {
        (str(tid), str(rid))
        for rid, tid in bind.execute(
            sa.select(_role.c.id, _role.c.tenant_id).where(_role.c.code == "tenant_admin")
        ).all()
    }
    existing_ids = {rid for _, rid in have_role}

    new_roles = []
    for tenant_id in tenants:
        rid = tenant_role_id(tenant_id, "tenant_admin")
        if rid in existing_ids:
            continue
        new_roles.append(
            {
                "id": rid,
                "tenant_id": tenant_id,
                "code": "tenant_admin",
                "name": "Tenant Admin",
                "created_at": TS,
                "updated_at": TS,
            }
        )
    if new_roles:
        bind.execute(_role.insert(), new_roles)

    # Existence-guarded on BOTH sides, and 0067's own comment is the reason: an insert that
    # live-imports a MUTABLE constant must be existence-guarded, "because the constant's future is
    # not the migration's to control". `ROLE_TEMPLATES["tenant_admin"]` was empty at 1a and filled
    # at 1b; it will move again. The permission-side guard matters too — a code in the template
    # that no migration has delivered to THIS database would otherwise violate the FK.
    wanted_codes = list(ROLE_TEMPLATES.get("tenant_admin", ()))
    if not wanted_codes:
        return (len(new_roles), 0)
    deliverable = {
        str(p)
        for p in bind.execute(
            sa.select(_permission.c.id).where(
                _permission.c.id.in_([permission_id(c) for c in wanted_codes])
            )
        )
        .scalars()
        .all()
    }

    want_grants: dict[str, dict[str, str]] = {}
    for tenant_id in tenants:
        rid = tenant_role_id(tenant_id, "tenant_admin")
        for code in wanted_codes:
            pid = permission_id(code)
            if pid not in deliverable:
                continue
            gid = tenant_role_permission_id(tenant_id, "tenant_admin", code)
            want_grants[gid] = {"id": gid, "role_id": rid, "permission_id": pid}
    if not want_grants:
        return (len(new_roles), 0)
    present = {
        str(r)
        for r in bind.execute(
            sa.select(_role_permission.c.id).where(
                _role_permission.c.id.in_(list(want_grants))
            )
        )
        .scalars()
        .all()
    }
    missing = [v for k, v in want_grants.items() if k not in present]
    if missing:
        bind.execute(_role_permission.insert(), missing)
    return (len(new_roles), len(missing))


def upgrade() -> None:
    roles, grants = backfill_legacy_tenant_admin(op.get_bind())
    print(f"0069: backfilled {roles} tenant_admin role(s) and {grants} grant(s)")


def downgrade() -> None:
    """Remove ONLY the rows this revision could have created, and only if nobody holds them.

    A blanket ``DELETE FROM role WHERE code = 'tenant_admin'`` would take out the roles ONBOARD-1a
    clones for tenants created through the real onboarding path, which this revision did not
    create. The ids are derived, so the rows this revision is responsible for are exactly
    identifiable — and a role somebody has been ASSIGNED is not this migration's to remove.
    """
    bind = op.get_bind()
    tenants = [
        str(t)
        for t in bind.execute(sa.text("SELECT id FROM tenant")).scalars().all()
        if str(t) != SYSTEM_TENANT_ID
    ]
    role_ids = [tenant_role_id(t, "tenant_admin") for t in tenants]
    if not role_ids:
        return
    assigned = {
        str(r)
        for r in bind.execute(
            sa.text("SELECT DISTINCT role_id FROM user_role WHERE role_id IN :ids").bindparams(
                sa.bindparam("ids", value=tuple(role_ids), expanding=True)
            )
        )
        .scalars()
        .all()
    }
    removable = [r for r in role_ids if r not in assigned]
    if not removable:
        return
    bind.execute(
        sa.text("DELETE FROM role_permission WHERE role_id IN :ids").bindparams(
            sa.bindparam("ids", value=tuple(removable), expanding=True)
        )
    )
    bind.execute(
        sa.text("DELETE FROM role WHERE id IN :ids").bindparams(
            sa.bindparam("ids", value=tuple(removable), expanding=True)
        )
    )
