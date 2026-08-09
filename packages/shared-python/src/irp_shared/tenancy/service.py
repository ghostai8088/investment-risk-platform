"""Tenant onboarding — the platform's ignition (ONBOARD-1a).

One transaction creates a tenant: its registry row, its role clones, its first administrator, and
that administrator's grant. All of it or none of it.

**The GUC choreography, and why the order is what it is.** The onboarding act spans two RLS
contexts, and an earlier draft had the order wrong in a way that would only have failed on
PostgreSQL:

1. under the **SYSTEM** context — check the caller's ``tenant.create``, and **read the SYSTEM
   template rows into memory**. This read must happen HERE: ``role`` and ``role_permission`` are
   FORCE-RLS tenant-scoped, so after the re-arm the SYSTEM templates are invisible and the clone
   would silently copy nothing (a green test on SQLite, an empty tenant on PG);
2. write the ``tenant`` row (PLATFORM-GLOBAL, no RLS) and its SYSTEM-chain audit event;
3. **re-arm** to the new tenant — ``set_config(..., true)`` is transaction-local and a second call
   replaces the first, which the verifier pass proved by execution against PG 16 with the real
   policy DDL: no BYPASSRLS is needed anywhere in this flow;
4. write the clones, the first admin and the seed grant, with the new tenant's own audit events —
   which genesis-anchor its chain automatically (``record_event`` starts an empty chain at
   ``sequence_no=1``).

**Why the duplicate-code check is a savepointed pre-check rather than a caught IntegrityError.**
On PostgreSQL a raised integrity error leaves the transaction ABORTED, and the request session is
a single transaction by AD-016 — so catching it would hand the caller a session on which every
later statement fails. The savepoint contains the probe; the refusal is raised before anything is
written. (REPRO-1 spent three scrutiny stages on exactly this class, with a unit test that stayed
green because SQLite does not poison a session.)

**What this module deliberately does NOT do.** It does not grant through ``grant_role``: that
function refuses a cross-tenant actor, correctly, and the seed grant is the one act where the
actor is a SYSTEM operator writing into a tenant that did not exist a moment ago. The refusal
stays intact for every other path and this exception carries a census row naming it.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from irp_shared.audit.actions import ACTION_CREATE
from irp_shared.audit.service import record_event
from irp_shared.db.tenant import set_tenant_context
from irp_shared.entitlement.bootstrap import (
    CLONED_TEMPLATES,
    SYSTEM_TENANT_ID,
    tenant_role_id,
    tenant_role_permission_id,
)
from irp_shared.entitlement.models import AppUser, Role, RolePermission, UserRole
from irp_shared.tenancy.models import (
    PROVENANCE_ONBOARDED,
    TENANT_STATUS_ACTIVE,
    Tenant,
)

#: The audit codes this slice mints (R-07, ratified at the ONBOARD-1 gate).
TENANT_CREATE_EVENT = "TENANT.CREATE"
USER_PROVISION_EVENT = "USER.PROVISION"

#: The role the first administrator receives. Its VERBS arrive with ONBOARD-1b.
FIRST_ADMIN_ROLE = "tenant_admin"


class TenantOnboardingError(ValueError):
    """A refusal: the request cannot be satisfied and NOTHING has been written."""


@dataclass(frozen=True)
class OnboardingResult:
    tenant_id: str
    code: str
    admin_user_id: str
    roles_cloned: tuple[str, ...]
    grants_cloned: int
    #: Templates skipped because the tenant already had a role with that code. Empty for a new
    #: tenant; non-empty only when onboarding is re-run against a backfilled tenant.
    roles_skipped: tuple[str, ...]


def _system_templates(session: Session) -> dict[str, list[str]]:
    """The SYSTEM template roles and their granted codes, READ FROM THE DATABASE.

    Not from ``ROLE_TEMPLATES``. The constant is the seed's intent; the rows are the truth after an
    administrator has revoked something. Cloning from the constant would re-materialize a revoked
    template grant into every newly onboarded tenant — the same resurrection class migration
    ``0066`` was built to close, arriving through a second door.

    Caller MUST have the SYSTEM context armed (``role`` is FORCE-RLS).
    """
    rows = session.execute(
        select(Role.code, RolePermission.permission_id)
        .join(RolePermission, RolePermission.role_id == Role.id)
        .where(Role.tenant_id == SYSTEM_TENANT_ID, Role.code.in_(CLONED_TEMPLATES))
    ).all()
    templates: dict[str, list[str]] = {name: [] for name in CLONED_TEMPLATES}
    for code, permission_id in rows:
        templates.setdefault(str(code), []).append(str(permission_id))
    # A template with no grants is legitimate (tenant_admin is deliberately empty until 1b), so an
    # empty list is kept rather than treated as "not found".
    present = {
        str(c)
        for c in session.execute(
            select(Role.code).where(
                Role.tenant_id == SYSTEM_TENANT_ID, Role.code.in_(CLONED_TEMPLATES)
            )
        )
        .scalars()
        .all()
    }
    return {name: codes for name, codes in templates.items() if name in present}


def onboard_tenant(
    session: Session,
    *,
    code: str,
    display_name: str,
    admin_external_subject: str,
    admin_display_name: str,
    actor_id: str,
    tenant_id: str | None = None,
) -> OnboardingResult:
    """Create a tenant, clone its roles, seed its first administrator. One transaction.

    ``actor_id`` is the platform operator's principal id — the audit actor for every event this
    writes, in BOTH chains. Callers arm the SYSTEM context before calling; this function re-arms to
    the new tenant partway through and leaves it armed (the request ends immediately after).
    """
    code = (code or "").strip()
    display_name = (display_name or "").strip()
    admin_external_subject = (admin_external_subject or "").strip()
    admin_display_name = (admin_display_name or "").strip()
    if not code:
        raise TenantOnboardingError("tenant code is required")
    if not display_name:
        raise TenantOnboardingError("tenant display_name is required")
    if not admin_external_subject:
        raise TenantOnboardingError("the first administrator's subject is required")
    if not admin_display_name:
        raise TenantOnboardingError("the first administrator's display_name is required")

    # --- the duplicate-code refusal, contained in a savepoint (see the module docstring) --------
    with session.begin_nested():
        existing = session.execute(
            select(Tenant.id).where(Tenant.code == code)
        ).scalar_one_or_none()
    if existing is not None:
        raise TenantOnboardingError(f"tenant code {code!r} already exists")

    new_tenant_id = str(uuid.UUID(tenant_id)) if tenant_id else str(uuid.uuid4())

    # --- 1. read the SYSTEM templates while the SYSTEM context is still armed -------------------
    templates = _system_templates(session)

    # --- 2. the registry row (PLATFORM-GLOBAL) + the SYSTEM-chain event -------------------------
    session.add(
        Tenant(
            id=new_tenant_id,
            code=code,
            display_name=display_name,
            status=TENANT_STATUS_ACTIVE,
            provenance=PROVENANCE_ONBOARDED,
        )
    )
    session.flush()
    record_event(
        session,
        tenant_id=SYSTEM_TENANT_ID,
        event_type=TENANT_CREATE_EVENT,
        action=ACTION_CREATE,
        entity_type="tenant",
        entity_id=new_tenant_id,
        actor_id=actor_id,
        actor_type="HUMAN",
        source_module="tenancy",
        outcome="success",
        after_value={"code": code, "display_name": display_name, "status": TENANT_STATUS_ACTIVE},
    )
    session.flush()

    # --- 3. re-arm to the new tenant ------------------------------------------------------------
    set_tenant_context(session, new_tenant_id)

    # --- 4. clones, first admin, seed grant, in the NEW tenant's chain --------------------------
    existing_codes = {
        str(c)
        for c in session.execute(select(Role.code).where(Role.tenant_id == new_tenant_id))
        .scalars()
        .all()
    }
    cloned: list[str] = []
    skipped: list[str] = []
    grants = 0
    for name in CLONED_TEMPLATES:
        if name not in templates:
            continue
        if name in existing_codes:
            # A backfilled tenant may already hold an ad-hoc role with a template's code, under
            # uq_role_tenant_id. Skipping is the ratified rule: onboarding must not rewrite roles
            # somebody else created, and must not fail because they exist.
            skipped.append(name)
            continue
        role_id = tenant_role_id(new_tenant_id, name)
        session.add(
            Role(
                id=role_id,
                tenant_id=new_tenant_id,
                code=name,
                name=name.replace("_", " ").title(),
            )
        )
        for permission_id in templates[name]:
            session.add(
                RolePermission(
                    id=tenant_role_permission_id(new_tenant_id, name, permission_id),
                    role_id=role_id,
                    permission_id=permission_id,
                )
            )
            grants += 1
        cloned.append(name)
    session.flush()

    admin = AppUser(
        id=str(uuid.uuid4()),
        tenant_id=new_tenant_id,
        external_subject=admin_external_subject,
        display_name=admin_display_name,
        is_active=True,
    )
    session.add(admin)
    session.flush()

    if FIRST_ADMIN_ROLE in cloned:
        session.add(
            UserRole(
                id=str(uuid.uuid4()),
                tenant_id=new_tenant_id,
                user_id=admin.id,
                role_id=tenant_role_id(new_tenant_id, FIRST_ADMIN_ROLE),
            )
        )
    elif FIRST_ADMIN_ROLE in skipped:
        # The tenant already had a role by that code; bind the admin to the EXISTING role rather
        # than minting a second one under the same unique key.
        existing_role_id = session.execute(
            select(Role.id).where(Role.tenant_id == new_tenant_id, Role.code == FIRST_ADMIN_ROLE)
        ).scalar_one()
        session.add(
            UserRole(
                id=str(uuid.uuid4()),
                tenant_id=new_tenant_id,
                user_id=admin.id,
                role_id=str(existing_role_id),
            )
        )
    else:
        # The admin role template is missing from the SYSTEM catalog entirely — the tenant would be
        # born with an administrator who is not one. Fail CLOSED rather than ship a stillborn
        # tenant: this is a platform misconfiguration, not a caller error.
        raise TenantOnboardingError(
            f"the {FIRST_ADMIN_ROLE!r} template is absent from the SYSTEM catalog — "
            "the tenant would have no administrator"
        )
    session.flush()

    record_event(
        session,
        tenant_id=new_tenant_id,
        event_type=USER_PROVISION_EVENT,
        action=ACTION_CREATE,
        entity_type="app_user",
        entity_id=admin.id,
        actor_id=actor_id,
        actor_type="HUMAN",
        source_module="tenancy",
        outcome="success",
        after_value={
            "display_name": admin_display_name,
            "role": FIRST_ADMIN_ROLE,
            "seeded_by": "onboarding",
        },
    )
    session.flush()

    return OnboardingResult(
        tenant_id=new_tenant_id,
        code=code,
        admin_user_id=admin.id,
        roles_cloned=tuple(cloned),
        grants_cloned=grants,
        roles_skipped=tuple(skipped),
    )


__all__ = [
    "FIRST_ADMIN_ROLE",
    "TENANT_CREATE_EVENT",
    "USER_PROVISION_EVENT",
    "OnboardingResult",
    "TenantOnboardingError",
    "onboard_tenant",
]
