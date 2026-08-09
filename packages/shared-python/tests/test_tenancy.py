"""ONBOARD-1a — tenant onboarding, the clones, and the escalation the design exists to prevent.

The Wave-16 close review found the platform had no way to create a tenant, user or role. The
design that closes it was broken **11-BLOCKING deep** by its first verifier pass, and the single
finding five independent lanes converged on is the one this suite pins hardest: minting
``tenant.create`` into ``PERMISSIONS`` would have handed it to every customer tenant, through three
individually-correct steps (``ALL_CODES`` → the ``platform_admin`` template → the onboarding
clone). Every test below that looks like paranoia is a defect that was actually proposed.

Unit tier, SQLite. Two properties this tier CANNOT prove, stated so no reader mistakes green here
for coverage: the boundary exists-check is dialect-gated (PostgreSQL only, by mechanism — see
``tenancy/boundary.py``), and the cross-context GUC choreography is a no-op on SQLite. Both live
in ``test_tenancy_pg.py``.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from irp_shared.entitlement.bootstrap import (
    ALL_CODES,
    CLONED_TEMPLATES,
    PERMISSIONS,
    ROLE_TEMPLATES,
    SYSTEM_TENANT_ID,
    permission_id,
    role_id,
    role_permission_id,
    tenant_role_id,
)
from irp_shared.entitlement.models import AppUser, Permission, Role, RolePermission, UserRole
from irp_shared.entitlement.platform_catalog import (
    PLATFORM_CODES,
    PLATFORM_OPERATOR_ROLE,
    PLATFORM_ROLES,
    platform_permission_id,
    platform_role_id,
    platform_role_permission_id,
)
from irp_shared.tenancy.models import (
    PROVENANCE_ONBOARDED,
    TENANT_STATUS_ACTIVE,
    Tenant,
)
from irp_shared.tenancy.service import (
    FIRST_ADMIN_ROLE,
    TENANT_CREATE_EVENT,
    USER_PROVISION_EVENT,
    TenantOnboardingError,
    onboard_tenant,
)


def _seed_system_catalog(db: Session) -> None:
    """Seed what migration 0002 + 0067 would: the permissions, the SYSTEM templates, the platform
    catalog. The suite seeds it rather than importing a fixture so each test's starting state is
    visible in one place."""
    from irp_shared.entitlement.platform_catalog import PLATFORM_PERMISSIONS

    for code, desc in PERMISSIONS:
        db.add(Permission(id=permission_id(code), code=code, description=desc))
    for code, desc in PLATFORM_PERMISSIONS:
        db.add(Permission(id=platform_permission_id(code), code=code, description=desc))
    db.flush()
    for name, codes in ROLE_TEMPLATES.items():
        db.add(
            Role(
                id=role_id(name),
                tenant_id=SYSTEM_TENANT_ID,
                code=name,
                name=name.replace("_", " ").title(),
            )
        )
        for code in codes:
            db.add(
                RolePermission(
                    id=role_permission_id(name, code),
                    role_id=role_id(name),
                    permission_id=permission_id(code),
                )
            )
    for name, codes in PLATFORM_ROLES.items():
        db.add(
            Role(
                id=platform_role_id(name),
                tenant_id=SYSTEM_TENANT_ID,
                code=name,
                name=name.replace("_", " ").title(),
            )
        )
        for code in codes:
            db.add(
                RolePermission(
                    id=platform_role_permission_id(name, code),
                    role_id=platform_role_id(name),
                    permission_id=platform_permission_id(code),
                )
            )
    db.add(
        Tenant(
            id=SYSTEM_TENANT_ID,
            code="system",
            display_name="System",
            status="SYSTEM",
            provenance="0067_system",
        )
    )
    db.flush()


@pytest.fixture
def catalog(session: Session) -> Session:
    _seed_system_catalog(session)
    return session


def _onboard(db: Session, code: str = "acme", **kw: object) -> object:
    return onboard_tenant(
        db,
        code=code,
        display_name=kw.pop("display_name", "Acme Asset Management"),  # type: ignore[arg-type]
        admin_external_subject=kw.pop("admin_external_subject", "auth0|acme-admin"),  # type: ignore[arg-type]
        admin_display_name=kw.pop("admin_display_name", "Ada Admin"),  # type: ignore[arg-type]
        actor_id=kw.pop("actor_id", "operator-1"),  # type: ignore[arg-type]
        **kw,  # type: ignore[arg-type]
    )


# ---------------------------------------------------------------- the happy path, asserted whole
def test_onboarding_creates_the_tenant_its_clones_and_its_first_admin(catalog: Session) -> None:
    result = _onboard(catalog)

    tenant = catalog.execute(select(Tenant).where(Tenant.id == result.tenant_id)).scalar_one()
    assert (tenant.code, tenant.status, tenant.provenance) == (
        "acme",
        TENANT_STATUS_ACTIVE,
        PROVENANCE_ONBOARDED,
    )

    admin = catalog.execute(select(AppUser).where(AppUser.id == result.admin_user_id)).scalar_one()
    assert admin.tenant_id == result.tenant_id
    assert admin.external_subject == "auth0|acme-admin"
    assert admin.is_active is True

    # The admin holds tenant_admin — the role whose VERBS arrive with ONBOARD-1b.
    grant = catalog.execute(select(UserRole).where(UserRole.user_id == admin.id)).scalar_one()
    assert grant.role_id == tenant_role_id(result.tenant_id, FIRST_ADMIN_ROLE)


def test_the_clone_matches_the_SYSTEM_templates_exactly(catalog: Session) -> None:
    """Exact set equality, both directions — the P7 hierarchy's top rung.

    A subset check would pass a clone that dropped a role; a superset check would pass one that
    invented grants. Both directions or the proof is half a proof.
    """
    result = _onboard(catalog)

    def matrix(tenant_id: str) -> set[tuple[str, str]]:
        rows = catalog.execute(
            select(Role.code, RolePermission.permission_id)
            .join(RolePermission, RolePermission.role_id == Role.id)
            .where(Role.tenant_id == tenant_id)
        ).all()
        return {(str(c), str(p)) for c, p in rows}

    system = {rc for rc in matrix(SYSTEM_TENANT_ID) if rc[0] in CLONED_TEMPLATES}
    assert matrix(result.tenant_id) == system
    assert set(result.roles_cloned) == set(CLONED_TEMPLATES)


# ------------------------------------------------------------ THE escalation the design prevents
def test_no_cloned_role_holds_a_PLATFORM_code(catalog: Session) -> None:
    """The census that makes the catalog split structural instead of remembered.

    Asserted against the DATABASE AFTER an onboarding, not against the constants — the constants
    were never what leaked. The leak path was: mint into PERMISSIONS → ALL_CODES → the
    platform_admin template → the clone. This asserts the end of that path is empty.
    """
    result = _onboard(catalog)
    platform_permission_ids = {platform_permission_id(c) for c in PLATFORM_CODES}
    cloned_grants = (
        catalog.execute(
            select(RolePermission.permission_id)
            .join(Role, Role.id == RolePermission.role_id)
            .where(Role.tenant_id == result.tenant_id)
        )
        .scalars()
        .all()
    )
    leaked = {str(p) for p in cloned_grants} & platform_permission_ids
    assert not leaked, (
        "a cloned tenant role holds a PLATFORM permission — the tenant can now create tenants. "
        "This is the exact escalation five verifier lanes found in the first design draft."
    )


def test_the_ops_and_platform_admin_templates_are_NOT_cloned(catalog: Session) -> None:
    """Ratified OQ-ONB-6, and the two exclusions have different reasons.

    `ops` holds only a code whose consumer is the BYPASSRLS ops CLI — authority with no HTTP
    surface. `platform_admin` is ALL_CODES: inside one tenant it puts a single person on both
    sides of every SoD partition the matrix builds.
    """
    result = _onboard(catalog)
    codes = {
        str(c)
        for c in catalog.execute(select(Role.code).where(Role.tenant_id == result.tenant_id))
        .scalars()
        .all()
    }
    assert "ops" not in codes and "platform_admin" not in codes
    assert codes == set(CLONED_TEMPLATES)


def test_the_platform_operator_role_is_not_a_template(catalog: Session) -> None:
    """The role holding `tenant.create` must never be in the set onboarding iterates."""
    assert PLATFORM_OPERATOR_ROLE not in ROLE_TEMPLATES
    assert PLATFORM_OPERATOR_ROLE not in CLONED_TEMPLATES
    assert not set(PLATFORM_CODES) & set(ALL_CODES)


# --------------------------------------------------------------------------- refusals, and P18
def test_a_duplicate_code_is_refused_with_NOTHING_persisted(catalog: Session) -> None:
    """The absence is asserted, not inferred (the DATA-1 hostile-caller shape).

    A refusal that left a half-built tenant would be worse than a crash: the registry would carry
    a tenant nobody can enter and the next attempt would collide with it forever.
    """
    first = _onboard(catalog, code="dup")
    tenants_before = catalog.execute(select(Tenant.id)).scalars().all()
    users_before = catalog.execute(select(AppUser.id)).scalars().all()

    with pytest.raises(TenantOnboardingError, match="already exists"):
        _onboard(catalog, code="dup", admin_external_subject="auth0|other")

    assert set(catalog.execute(select(Tenant.id)).scalars().all()) == set(tenants_before)
    assert set(catalog.execute(select(AppUser.id)).scalars().all()) == set(users_before)
    # The POSITIVE control (P18): the harness CAN create tenants — otherwise "nothing persisted"
    # is equally consistent with a service that never writes anything.
    second = _onboard(catalog, code="not-a-dup", admin_external_subject="auth0|second")
    assert second.tenant_id != first.tenant_id


@pytest.mark.parametrize(
    "field",
    ["code", "display_name", "admin_external_subject", "admin_display_name"],
)
def test_every_required_field_is_refused_when_blank(catalog: Session, field: str) -> None:
    kwargs: dict[str, str] = {
        "code": "x",
        "display_name": "X",
        "admin_external_subject": "auth0|x",
        "admin_display_name": "X Admin",
        "actor_id": "operator-1",
    }
    kwargs[field] = "   "
    with pytest.raises(TenantOnboardingError):
        onboard_tenant(catalog, **kwargs)  # type: ignore[arg-type]
    assert catalog.execute(select(Tenant).where(Tenant.code == "x")).scalar_one_or_none() is None


def test_a_missing_admin_template_FAILS_CLOSED(catalog: Session) -> None:
    """A tenant born without an administrator is stillborn — refuse rather than ship it.

    Reachable only by platform misconfiguration (the template deleted from the SYSTEM catalog),
    which is exactly the class where failing open produces a tenant nobody can ever enter and no
    error anywhere says so.
    """
    catalog.execute(
        RolePermission.__table__.delete().where(RolePermission.role_id == role_id(FIRST_ADMIN_ROLE))
    )
    catalog.execute(Role.__table__.delete().where(Role.id == role_id(FIRST_ADMIN_ROLE)))
    catalog.flush()

    with pytest.raises(TenantOnboardingError, match="no administrator"):
        _onboard(catalog, code="stillborn")


# ------------------------------------------------------------------- the clone SOURCE, and 0066
def test_the_clone_reads_the_DATABASE_not_the_constant(catalog: Session) -> None:
    """A revoked SYSTEM template grant must NOT reappear in a newly onboarded tenant.

    ``ROLE_TEMPLATES`` is the seed's intent; the rows are the truth after an administrator revokes
    something. Cloning from the constant would re-materialize the revoked grant into every new
    tenant — the same resurrection class migration ``0066`` was built to close, arriving through a
    second door one wave later.

    The DISCRIMINATING control is the pair: the same code lands for a tenant onboarded BEFORE the
    revocation. Without it, "absent" is equally consistent with a clone that copies nothing.
    """
    revoked_code = "perf.view"
    before = _onboard(catalog, code="before-revocation")
    assert (
        tenant_role_id(before.tenant_id, "risk_manager_2l"),
        permission_id(revoked_code),
    ) in {
        (str(r), str(p))
        for r, p in catalog.execute(
            select(RolePermission.role_id, RolePermission.permission_id)
            .join(Role, Role.id == RolePermission.role_id)
            .where(Role.tenant_id == before.tenant_id)
        ).all()
    }

    catalog.execute(
        RolePermission.__table__.delete().where(
            RolePermission.id == role_permission_id("risk_manager_2l", revoked_code)
        )
    )
    catalog.flush()

    after = _onboard(catalog, code="after-revocation", admin_external_subject="auth0|after")
    codes_after = {
        str(p)
        for p in catalog.execute(
            select(RolePermission.permission_id)
            .join(Role, Role.id == RolePermission.role_id)
            .where(Role.tenant_id == after.tenant_id, Role.code == "risk_manager_2l")
        )
        .scalars()
        .all()
    }
    assert permission_id(revoked_code) not in codes_after, (
        "the clone resurrected a revoked SYSTEM template grant — it is reading ROLE_TEMPLATES "
        "instead of the database rows"
    )


def test_a_template_code_the_tenant_already_holds_is_SKIPPED(catalog: Session) -> None:
    """The collision rule (ratified): a backfilled tenant's ad-hoc roles are never rewritten.

    The demo tenant already holds roles under the SAME codes as the templates with ad-hoc ids,
    under ``uq_role_tenant_id``. Onboarding must neither collide nor silently replace them.
    """
    tenant_id = str(uuid.uuid4())
    pre_existing = Role(
        id=str(uuid.uuid4()),
        tenant_id=tenant_id,
        code="risk_manager_2l",
        name="Pre-existing ad-hoc",
    )
    catalog.add(pre_existing)
    catalog.flush()

    result = onboard_tenant(
        catalog,
        code="had-roles",
        display_name="Had Roles",
        admin_external_subject="auth0|had",
        admin_display_name="Had Admin",
        actor_id="operator-1",
        tenant_id=tenant_id,
    )
    assert result.roles_skipped == ("risk_manager_2l",)
    still_there = catalog.execute(
        select(Role).where(Role.tenant_id == tenant_id, Role.code == "risk_manager_2l")
    ).scalar_one()
    assert still_there.id == pre_existing.id
    assert still_there.name == "Pre-existing ad-hoc"


def test_a_pre_existing_admin_role_binds_the_admin_to_it(catalog: Session) -> None:
    """The skip must not leave the first admin ungranted — the tenant would be stillborn."""
    tenant_id = str(uuid.uuid4())
    existing = Role(
        id=str(uuid.uuid4()), tenant_id=tenant_id, code=FIRST_ADMIN_ROLE, name="Existing Admin"
    )
    catalog.add(existing)
    catalog.flush()

    result = onboard_tenant(
        catalog,
        code="had-admin",
        display_name="Had Admin Role",
        admin_external_subject="auth0|hadadmin",
        admin_display_name="Admin",
        actor_id="operator-1",
        tenant_id=tenant_id,
    )
    grant = catalog.execute(
        select(UserRole).where(UserRole.user_id == result.admin_user_id)
    ).scalar_one()
    assert grant.role_id == existing.id


# ------------------------------------------------------------------------------- the audit trail
def test_both_audit_chains_are_written(catalog: Session) -> None:
    """The SYSTEM chain records the tenant's creation; the new tenant's chain is genesis-anchored.

    An earlier design draft was SILENT on which chain the onboarding act lands in, even though
    "auditable" was the deciding virtue of this authority model over the out-of-band alternative.
    Silence there would have shipped whichever the code happened to do.
    """
    from irp_shared.audit.models import AuditEvent

    result = _onboard(catalog, code="audited")
    events = catalog.execute(select(AuditEvent.chain_id, AuditEvent.event_type)).all()
    by_chain = {(str(c), str(e)) for c, e in events}
    assert (
        SYSTEM_TENANT_ID,
        TENANT_CREATE_EVENT,
    ) in by_chain, "the tenant's creation is not recorded in the SYSTEM chain"
    assert (
        result.tenant_id,
        USER_PROVISION_EVENT,
    ) in by_chain, "the first admin's provisioning is not recorded in the new tenant's own chain"


# ------------------------------------------------------------------ the operator seed (prepare)
def test_the_operator_seed_is_idempotent_and_grants_the_platform_role(catalog: Session) -> None:
    """Outcome 11: the operator is seeded by the deploy PREPARE step, never a migration.

    Idempotency is the deploy bar (`seed_system_reference`'s): a re-run after a partial failure
    must change nothing. And the grant must be the PLATFORM role — an operator seeded without it
    would be an identity that can log in and do nothing, which reads as a broken deployment.
    """
    from irp_shared.deploy.prepare import seed_platform_operator
    from irp_shared.entitlement.platform_catalog import PLATFORM_OPERATOR_ROLE, platform_role_id

    first = seed_platform_operator(catalog, subject="op@platform")
    second = seed_platform_operator(catalog, subject="op@platform")
    assert (
        first == second
    ), "re-seeding minted a SECOND operator — the prepare step is not re-runnable"

    grants = catalog.execute(select(UserRole).where(UserRole.user_id == first)).scalars().all()
    assert [g.role_id for g in grants] == [platform_role_id(PLATFORM_OPERATOR_ROLE)]
    user = catalog.execute(select(AppUser).where(AppUser.id == first)).scalar_one()
    assert user.tenant_id == SYSTEM_TENANT_ID
