"""ONBOARD-1a: ENT-074 ``tenant``, the PLATFORM entitlement catalog, and the ``tenant_admin`` role.

**What this migration must not do, stated first because it is the hard part.** ONBOARD-1a adds a
boundary check that refuses any token whose tenant claim names no registry row. A registry that
starts empty therefore locks every existing deployment out of its own platform — the exact
undeliverable-to-live-databases class RPT-2's ``0064`` was built to close and P17 was ratified
against, one wave later, through a different door. So this migration BACKFILLS:

* the SYSTEM tenant, status ``SYSTEM`` — without it the platform operator's own token fails the
  check it exists to serve (found by the verifier pass, not by the build);
* one ``ACTIVE`` row per DISTINCT ``app_user.tenant_id``, **excluding the reserved proof
  literals**. The deploy proofs write users under a fixed ``PROOF_TENANT`` id and never clean up,
  so a naive backfill would promote a test fixture to a real tenant — a wrong fact, permanently,
  in the registry an auditor reads.

Each row records ``provenance``, because "inferred from existing app_user rows" and "an operator
created this" are different facts that no later query could tell apart.

**The template clone is deliberately NOT done here.** Backfilled tenants keep exactly the roles
they have. An earlier draft had this migration clone templates into every backfilled tenant; the
verifier pass showed the demo tenant already holds roles under the SAME codes as the templates
(``risk_manager_2l`` and friends, with ad-hoc ids) under ``uq_role_tenant_id`` — so the clone would
either collide or silently rewrite somebody's roles. Onboarding clones for tenants IT creates; the
backfill registers what exists and touches nothing else.

**The platform catalog rows are inserted inline** (``tenant.create`` + the ``platform_operator``
role + its grant). They cannot ride ``sync_catalog``'s template machinery — being outside
``ROLE_TEMPLATES`` is the entire point of the design — so delivery is explicit here, and
``sync_catalog`` gains a platform arm so future platform codes have the same story.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from irp_shared.db.types import GUID
from irp_shared.entitlement.bootstrap import (
    ROLE_TEMPLATES,
    SYSTEM_TENANT_ID,
    permission_id,
    role_id,
    role_permission_id,
)
from irp_shared.entitlement.platform_catalog import (
    PLATFORM_PERMISSIONS,
    PLATFORM_ROLES,
    platform_permission_id,
    platform_role_id,
    platform_role_permission_id,
)
from irp_shared.tenancy.models import (
    PROVENANCE_BACKFILL,
    PROVENANCE_SYSTEM,
    TENANT_STATUS_ACTIVE,
    TENANT_STATUS_SYSTEM,
    TENANT_STATUSES,
)

revision: str = "0067_tenant_registry"
down_revision: str | None = "0066_entitlement_revocation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TS = datetime(2026, 8, 9, 0, 0, 0, tzinfo=UTC)

#: The permission codes this revision DELIVERS to a running database (P17's mechanical gate).
#: ONBOARD-1a mints exactly ONE tenant-catalog code — none. `tenant_admin` ships as an EMPTY
#: template (its verbs are ONBOARD-1b's), so no tenant-catalog code is new here and the tuple is
#: empty BY MEASUREMENT, not by omission. The platform code is declared separately below because
#: it does not live in `PERMISSIONS` and the gate that walks `ALL_CODES` would never see it.
DELIVERS: tuple[str, ...] = ()

#: The PLATFORM codes this revision delivers. The P17 gate is extended in this same commit to walk
#: this tuple too — a platform code was proven by execution to escape the ALL_CODES-only gate
#: silently, and a gate that cannot see a whole catalog is not a gate for it.
DELIVERS_PLATFORM: tuple[str, ...] = ("tenant.create",)

#: Reserved tenant ids that must NEVER be registered as real tenants by the backfill.
#: Spelled as literals rather than imported: a migration must reproduce identically forever, and
#: these values are governance facts about which ids are fixtures — if `report_identity_proof.py`
#: is deleted tomorrow, the exclusion this migration applied must still be readable here.
RESERVED_TENANT_IDS: tuple[str, ...] = (
    "9f000000-0000-4000-8000-000000000001",  # PROOF_TENANT (deploy/report_identity_proof.py)
)

_tenant = sa.table(
    "tenant",
    sa.column("id", GUID()),
    sa.column("code", sa.String()),
    sa.column("display_name", sa.String()),
    sa.column("status", sa.String()),
    sa.column("provenance", sa.String()),
    sa.column("created_at", sa.DateTime(timezone=True)),
    sa.column("updated_at", sa.DateTime(timezone=True)),
)
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
    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            sa.text("SELECT set_config('app.current_tenant', :t, true)").bindparams(
                t=SYSTEM_TENANT_ID
            )
        )


def upgrade() -> None:
    bind = op.get_bind()

    # --- ENT-074 -------------------------------------------------------------------------------
    op.create_table(
        "tenant",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("code", sa.String(length=100), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("provenance", sa.String(length=40), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(length=255), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by", sa.String(length=255), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_tenant"),
        sa.UniqueConstraint("code", name="uq_tenant_code"),
    )
    # A TOTAL enumeration (the 0053 pattern): an unenumerated status must fail CLOSED at the
    # database. Generated from the ORM's declaration so the two cannot drift — the REF-1 lesson
    # about hand-mirrored copies of an expected value, applied at the one place it is cheap.
    op.create_check_constraint(
        "status", "tenant", sa.column("status").in_(list(TENANT_STATUSES))
    )

    # --- the SYSTEM row ------------------------------------------------------------------------
    op.bulk_insert(
        _tenant,
        [
            {
                "id": SYSTEM_TENANT_ID,
                "code": "system",
                "display_name": "System",
                "status": TENANT_STATUS_SYSTEM,
                "provenance": PROVENANCE_SYSTEM,
                "created_at": TS,
                "updated_at": TS,
            }
        ],
    )

    # --- backfill the tenants that already exist ------------------------------------------------
    existing = [
        str(t)
        for t in bind.execute(
            sa.text("SELECT DISTINCT tenant_id FROM app_user WHERE tenant_id IS NOT NULL")
        )
        .scalars()
        .all()
    ]
    backfill = [
        {
            "id": t,
            # The code must be unique and must not collide with a code an operator might choose.
            # A prefixed id is ugly on purpose: it reads as "this row was inferred", which is
            # exactly what an auditor should conclude.
            "code": f"backfilled-{t}",
            "display_name": f"Backfilled tenant {t}",
            "status": TENANT_STATUS_ACTIVE,
            "provenance": PROVENANCE_BACKFILL,
            "created_at": TS,
            "updated_at": TS,
        }
        for t in sorted(set(existing))
        if t != SYSTEM_TENANT_ID and t not in RESERVED_TENANT_IDS
    ]
    if backfill:
        op.bulk_insert(_tenant, backfill)

    # --- the PLATFORM catalog (inline; see the module docstring) --------------------------------
    _set_system_tenant()
    want_perms = {platform_permission_id(c): (c, d) for c, d in PLATFORM_PERMISSIONS}
    have = {
        str(r)
        for r in bind.execute(
            sa.select(_permission.c.id).where(_permission.c.id.in_(list(want_perms)))
        )
        .scalars()
        .all()
    }
    missing_perms = [
        {"id": pid, "code": c, "description": d, "created_at": TS, "updated_at": TS}
        for pid, (c, d) in want_perms.items()
        if pid not in have
    ]
    if missing_perms:
        op.bulk_insert(_permission, missing_perms)

    want_roles = {platform_role_id(name): name for name in PLATFORM_ROLES}
    have_roles = {
        str(r)
        for r in bind.execute(sa.select(_role.c.id).where(_role.c.id.in_(list(want_roles))))
        .scalars()
        .all()
    }
    missing_roles = [
        {
            "id": rid,
            "tenant_id": SYSTEM_TENANT_ID,
            "code": name,
            "name": name.replace("_", " ").title(),
            "created_at": TS,
            "updated_at": TS,
        }
        for rid, name in want_roles.items()
        if rid not in have_roles
    ]
    if missing_roles:
        op.bulk_insert(_role, missing_roles)

    want_grants = {
        platform_role_permission_id(name, code): (name, code)
        for name, codes in PLATFORM_ROLES.items()
        for code in codes
    }
    have_grants = {
        str(r)
        for r in bind.execute(
            sa.select(_role_permission.c.id).where(_role_permission.c.id.in_(list(want_grants)))
        )
        .scalars()
        .all()
    }
    missing_grants = [
        {
            "id": gid,
            "role_id": platform_role_id(name),
            "permission_id": platform_permission_id(code),
        }
        for gid, (name, code) in want_grants.items()
        if gid not in have_grants
    ]
    if missing_grants:
        op.bulk_insert(_role_permission, missing_grants)

    # --- the tenant_admin TEMPLATE role (empty until ONBOARD-1b) ---------------------------------
    admin_role_id = role_id("tenant_admin")
    exists = bind.execute(
        sa.select(_role.c.id).where(_role.c.id == admin_role_id)
    ).scalar_one_or_none()
    if exists is None:
        op.bulk_insert(
            _role,
            [
                {
                    "id": admin_role_id,
                    "tenant_id": SYSTEM_TENANT_ID,
                    "code": "tenant_admin",
                    "name": "Tenant Admin",
                    "created_at": TS,
                    "updated_at": TS,
                }
            ],
        )
    # Its grants come from ROLE_TEMPLATES, which was EMPTY for this role when 1a shipped.
    #
    # **EXISTENCE-GUARDED, and the guard is the finding.** This loop live-imports a MUTABLE
    # constant, so its behaviour changed the moment ONBOARD-1b filled the template: on a fresh
    # database `0002` (which also live-imports the constant) now seeds these four grants, and this
    # unguarded insert then collided on `pk_role_permission` — a migration that had shipped green
    # started failing because a LATER slice edited a constant it reads. Found by executing
    # `alembic upgrade head` on a reset database at 1b, not by reading.
    #
    # The class rule this makes concrete: **an insert that live-imports a mutable constant must be
    # existence-guarded**, because the constant's future is not the migration's to control. Every
    # other insert in this file already was; this one was the exception, written to be
    # forward-friendly, and being forward-friendly is precisely what broke it.
    want_admin_grants = {
        role_permission_id("tenant_admin", code): {
            "id": role_permission_id("tenant_admin", code),
            "role_id": admin_role_id,
            "permission_id": permission_id(code),
        }
        for code in ROLE_TEMPLATES.get("tenant_admin", [])
    }
    if want_admin_grants:
        present = {
            str(r)
            for r in bind.execute(
                sa.select(_role_permission.c.id).where(
                    _role_permission.c.id.in_(list(want_admin_grants))
                )
            )
            .scalars()
            .all()
        }
        admin_grants = [v for k, v in want_admin_grants.items() if k not in present]
        if admin_grants:
            op.bulk_insert(_role_permission, admin_grants)


def downgrade() -> None:
    """Drop the registry; leave the entitlement rows.

    **Honest about what is lost:** dropping ``tenant`` removes the boundary check's data, so a
    downgraded deployment stops refusing unregistered and suspended tenants. No tenant DATA is
    lost — the registry describes tenants, it does not contain them — but a control disappears,
    and that is worth saying rather than discovering.

    The platform permission/role/grant rows are deliberately NOT deleted, for the reason ``0064``
    gives: deterministic ids make an inserted row indistinguishable from one an operator created,
    and deleting entitlement rows on a downgrade is how a downgrade takes a deployment's access
    with it.
    """
    op.drop_table("tenant")
