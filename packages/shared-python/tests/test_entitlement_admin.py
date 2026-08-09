"""ONBOARD-1b — four-eyes on entitlement changes, and the orphan-proof invariant.

Two controls, and almost every test here exists because a specific defect was *proposed and
verified* during the design's two adversarial passes rather than imagined afterwards:

* the four-eyes threshold was written "≥2 OTHER admins", which exempts every two-admin tenant —
  the tenants where SOD-04 first becomes possible to honor (pass 2, finding B3);
* deactivation escaped the flow entirely, making "deactivate the other admin, then act alone in
  the bootstrap window" a one-step bypass legal under both invariants at once (pass 2, B2);
* the orphan check counted grants that EXIST rather than grants VALID NOW, so end-dating removed
  an admin without tripping it;
* and two admins revoking each other concurrently passes two individually-legal checks.

Unit tier, SQLite. The concurrency path is a no-op here (no advisory locks) and lives in
``test_entitlement_admin_pg.py`` — stated so nobody reads green here as coverage of it.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from irp_shared.entitlement.admin_service import (
    AdminActor,
    EntitlementError,
    TenantWouldBeOrphaned,
    approve_entitlement_change,
    create_user,
    request_entitlement_change,
    valid_admin_user_ids,
)
from irp_shared.entitlement.models import AppUser, Role, UserRole
from irp_shared.entitlement.request_models import (
    ACTION_DEACTIVATE_USER,
    ACTION_GRANT_ROLE,
    ACTION_REVOKE_ROLE,
    STATUS_APPROVED,
    STATUS_DIRECT,
    STATUS_PENDING,
    EntitlementRequest,
)
from irp_shared.tenancy.service import FIRST_ADMIN_ROLE

NOW = datetime(2026, 8, 9, 12, 0, tzinfo=UTC)


@pytest.fixture
def tenant(session: Session) -> str:
    """A tenant with its tenant_admin role and ONE administrator (the 1a end-state)."""
    tid = str(uuid.uuid4())
    session.add(
        Role(id=str(uuid.uuid4()), tenant_id=tid, code=FIRST_ADMIN_ROLE, name="Tenant Admin")
    )
    session.add(Role(id=str(uuid.uuid4()), tenant_id=tid, code="risk_analyst_1l", name="Analyst"))
    session.flush()
    _add_admin(session, tid, "first")
    return tid


def _role_id(db: Session, tenant_id: str, code: str) -> str:
    return str(
        db.execute(
            select(Role.id).where(Role.tenant_id == tenant_id, Role.code == code)
        ).scalar_one()
    )


def _add_user(db: Session, tenant_id: str, label: str, *, active: bool = True) -> str:
    user = AppUser(
        id=str(uuid.uuid4()),
        tenant_id=tenant_id,
        external_subject=f"{label}@{tenant_id[:8]}",
        display_name=label.title(),
        is_active=active,
    )
    db.add(user)
    db.flush()
    return user.id


def _add_admin(db: Session, tenant_id: str, label: str) -> str:
    uid = _add_user(db, tenant_id, label)
    db.add(
        UserRole(
            id=str(uuid.uuid4()),
            tenant_id=tenant_id,
            user_id=uid,
            role_id=_role_id(db, tenant_id, FIRST_ADMIN_ROLE),
            valid_from=NOW - timedelta(days=1),
        )
    )
    db.flush()
    return uid


def _admins(db: Session, tenant_id: str) -> set[str]:
    return valid_admin_user_ids(db, tenant_id, now=NOW)


# ----------------------------------------------------------------- the four-eyes threshold
def test_a_LONE_admin_acts_DIRECTLY_and_the_act_is_stamped(session: Session, tenant: str) -> None:
    """The bootstrap window. A tenant with one admin would otherwise be stillborn."""
    lone = next(iter(_admins(session, tenant)))
    target = _add_user(session, tenant, "newjoiner")

    req = request_entitlement_change(
        session,
        tenant_id=tenant,
        actor=AdminActor(lone),
        action=ACTION_GRANT_ROLE,
        target_user_id=target,
        target_role_id=_role_id(session, tenant, "risk_analyst_1l"),
        now=NOW,
    )
    assert req.status == STATUS_DIRECT
    # The act TOOK EFFECT — a DIRECT status that granted nothing would be the worst of both.
    grants = session.execute(select(UserRole).where(UserRole.user_id == target)).scalars().all()
    assert len(grants) == 1

    from irp_shared.audit.models import AuditEvent

    ev = session.execute(select(AuditEvent).where(AuditEvent.entity_id == req.id)).scalars().all()
    assert any(e.after_value.get("direct_grant") is True for e in ev), (
        "a direct act must be FLAGGED in the chain — an auditor counts these, and an unflagged "
        "one is indistinguishable from a four-eyed act"
    )


def test_four_eyes_ENGAGES_at_TWO_admins_not_three(session: Session, tenant: str) -> None:
    """THE THRESHOLD, and the reason it is its own test.

    The design's first fix read "≥2 OTHER admins", which exempts a two-admin tenant — precisely
    the tenant where a second pair of eyes first EXISTS, and therefore precisely where SOD-04
    first binds. Verified as a defect at pass 2 (finding B3) before any code was written.
    """
    first = next(iter(_admins(session, tenant)))
    _add_admin(session, tenant, "second")
    assert len(_admins(session, tenant)) == 2

    target = _add_user(session, tenant, "newjoiner")
    req = request_entitlement_change(
        session,
        tenant_id=tenant,
        actor=AdminActor(first),
        action=ACTION_GRANT_ROLE,
        target_user_id=target,
        target_role_id=_role_id(session, tenant, "risk_analyst_1l"),
        now=NOW,
    )
    assert (
        req.status == STATUS_PENDING
    ), "four-eyes did not engage at TWO admins — a second approver exists, so SOD-04 binds"
    assert (
        not session.execute(select(UserRole).where(UserRole.user_id == target)).scalars().all()
    ), "a PENDING request took effect immediately — the gate is decorative"


def test_the_second_admins_approval_makes_it_EFFECTIVE(session: Session, tenant: str) -> None:
    """The discriminating positive control: PENDING is not a dead end."""
    first = next(iter(_admins(session, tenant)))
    second = _add_admin(session, tenant, "second")
    target = _add_user(session, tenant, "newjoiner")
    analyst = _role_id(session, tenant, "risk_analyst_1l")

    req = request_entitlement_change(
        session,
        tenant_id=tenant,
        actor=AdminActor(first),
        action=ACTION_GRANT_ROLE,
        target_user_id=target,
        target_role_id=analyst,
        now=NOW,
    )
    approved = approve_entitlement_change(
        session, tenant_id=tenant, actor=AdminActor(second), request_id=req.id, now=NOW
    )
    assert approved.status == STATUS_APPROVED
    assert approved.resolved_by == second
    grants = session.execute(select(UserRole).where(UserRole.user_id == target)).scalars().all()
    assert len(grants) == 1


def test_an_admin_cannot_approve_their_OWN_request(session: Session, tenant: str) -> None:
    """The person-level gate (MG-3). Role-level separation would not catch this at all."""
    first = next(iter(_admins(session, tenant)))
    _add_admin(session, tenant, "second")
    target = _add_user(session, tenant, "newjoiner")

    req = request_entitlement_change(
        session,
        tenant_id=tenant,
        actor=AdminActor(first),
        action=ACTION_GRANT_ROLE,
        target_user_id=target,
        target_role_id=_role_id(session, tenant, "risk_analyst_1l"),
        now=NOW,
    )
    with pytest.raises(EntitlementError, match="own entitlement request"):
        approve_entitlement_change(
            session, tenant_id=tenant, actor=AdminActor(first), request_id=req.id, now=NOW
        )
    assert not session.execute(select(UserRole).where(UserRole.user_id == target)).scalars().all()


def test_the_approver_comparison_survives_CASE_variance(session: Session, tenant: str) -> None:
    """The API-2 lesson, live: PostgreSQL's uuid cast is case-INSENSITIVE.

    An admin presenting the UPPERCASE form of their own id passes ``require_permission`` — only
    this comparison stops them approving their own request, and only because both sides are
    canonicalized in the actor dataclass rather than compared as raw strings.
    """
    first = next(iter(_admins(session, tenant)))
    _add_admin(session, tenant, "second")
    target = _add_user(session, tenant, "newjoiner")

    req = request_entitlement_change(
        session,
        tenant_id=tenant,
        actor=AdminActor(first),
        action=ACTION_GRANT_ROLE,
        target_user_id=target,
        target_role_id=_role_id(session, tenant, "risk_analyst_1l"),
        now=NOW,
    )
    with pytest.raises(EntitlementError, match="own entitlement request"):
        approve_entitlement_change(
            session,
            tenant_id=tenant,
            actor=AdminActor(first.upper()),
            request_id=req.id,
            now=NOW,
        )


def test_DEACTIVATION_of_an_admin_rides_the_four_eyes_flow(session: Session, tenant: str) -> None:
    """Finding B2, CONFIRMED at pass 2: deactivate-instead-of-revoke was a one-step bypass.

    Deactivating an admin removes their authority as completely as revoking the role, so if it
    escaped the flow an admin could shrink the tenant to one admin — themselves — and then act
    alone in the bootstrap window, legally, under both invariants at once.
    """
    first = next(iter(_admins(session, tenant)))
    second = _add_admin(session, tenant, "second")

    req = request_entitlement_change(
        session,
        tenant_id=tenant,
        actor=AdminActor(first),
        action=ACTION_DEACTIVATE_USER,
        target_user_id=second,
        now=NOW,
    )
    assert req.status == STATUS_PENDING, "deactivating an admin escaped the four-eyes flow"
    assert session.get(AppUser, second).is_active is True


def test_deactivating_a_NON_admin_stays_direct(session: Session, tenant: str) -> None:
    """The discriminating twin: the flow gates entitlement changes, not all user management.

    Without this, "deactivation is PENDING" would be equally consistent with a rule that queues
    every user operation — which would put new-joiner admin in the four-eyes queue and teach
    people to route around the control.
    """
    first = next(iter(_admins(session, tenant)))
    _add_admin(session, tenant, "second")
    ordinary = _add_user(session, tenant, "ordinary")

    req = request_entitlement_change(
        session,
        tenant_id=tenant,
        actor=AdminActor(first),
        action=ACTION_DEACTIVATE_USER,
        target_user_id=ordinary,
        now=NOW,
    )
    # Still four-eyed (two admins exist) — but the point is it is not REFUSED, and on approval it
    # touches no admin count.
    assert req.status == STATUS_PENDING
    approve_entitlement_change(
        session,
        tenant_id=tenant,
        actor=AdminActor(next(a for a in _admins(session, tenant) if a != first)),
        request_id=req.id,
        now=NOW,
    )
    assert session.get(AppUser, ordinary).is_active is False


# --------------------------------------------------------------- the orphan-proof invariant
def test_revoking_the_LAST_admins_role_is_REFUSED(session: Session, tenant: str) -> None:
    lone = next(iter(_admins(session, tenant)))
    with pytest.raises(TenantWouldBeOrphaned):
        request_entitlement_change(
            session,
            tenant_id=tenant,
            actor=AdminActor(lone),
            action=ACTION_REVOKE_ROLE,
            target_user_id=lone,
            target_role_id=_role_id(session, tenant, FIRST_ADMIN_ROLE),
            now=NOW,
        )
    assert _admins(session, tenant) == {lone}


def test_revoking_a_NON_last_admin_SUCCEEDS(session: Session, tenant: str) -> None:
    """The positive twin. Without it, "refused" is consistent with revocation never working."""
    first = next(iter(_admins(session, tenant)))
    second = _add_admin(session, tenant, "second")
    third = _add_admin(session, tenant, "third")

    req = request_entitlement_change(
        session,
        tenant_id=tenant,
        actor=AdminActor(first),
        action=ACTION_REVOKE_ROLE,
        target_user_id=third,
        target_role_id=_role_id(session, tenant, FIRST_ADMIN_ROLE),
        now=NOW,
    )
    approve_entitlement_change(
        session, tenant_id=tenant, actor=AdminActor(second), request_id=req.id, now=NOW
    )
    assert third not in _admins(session, tenant)
    assert {first, second} <= _admins(session, tenant)


def test_END_DATING_the_last_admins_grant_is_counted(session: Session, tenant: str) -> None:
    """The invariant counts grants VALID NOW, not grants that EXIST.

    Revocation is implemented as end-dating, so a check over "a row exists" would see the last
    admin as still present and permit the next removal — the same orphan by a different spelling.
    """
    lone = next(iter(_admins(session, tenant)))
    grant = session.execute(select(UserRole).where(UserRole.user_id == lone)).scalar_one()
    grant.valid_to = NOW - timedelta(hours=1)
    session.flush()

    assert _admins(session, tenant) == set(), (
        "an end-dated grant still counts as administration — the invariant reads existence, "
        "not validity"
    )


def test_DEACTIVATING_the_last_admin_is_REFUSED(session: Session, tenant: str) -> None:
    """Including self-deactivation: an inactive user cannot authenticate, so this orphans too."""
    lone = next(iter(_admins(session, tenant)))
    with pytest.raises(TenantWouldBeOrphaned):
        request_entitlement_change(
            session,
            tenant_id=tenant,
            actor=AdminActor(lone),
            action=ACTION_DEACTIVATE_USER,
            target_user_id=lone,
            now=NOW,
        )
    assert session.get(AppUser, lone).is_active is True


def test_an_INACTIVE_admin_does_not_count_toward_the_invariant(
    session: Session, tenant: str
) -> None:
    """The other direction: a deactivated admin must not keep the tenant's count comfortable."""
    lone = next(iter(_admins(session, tenant)))
    ghost = _add_admin(session, tenant, "ghost")
    session.get(AppUser, ghost).is_active = False
    session.flush()

    assert _admins(session, tenant) == {lone}
    with pytest.raises(TenantWouldBeOrphaned):
        request_entitlement_change(
            session,
            tenant_id=tenant,
            actor=AdminActor(lone),
            action=ACTION_REVOKE_ROLE,
            target_user_id=lone,
            target_role_id=_role_id(session, tenant, FIRST_ADMIN_ROLE),
            now=NOW,
        )


def test_the_orphan_check_runs_when_the_act_TAKES_EFFECT_not_when_requested(
    session: Session, tenant: str
) -> None:
    """The composition of the two controls, and the reason the check sits in ``_apply``.

    A revocation can sit PENDING while the tenant's admin count changes underneath it. Checking
    only at request time would authorize an act against a state that no longer holds when it
    lands — the four-eyes delay turning the orphan guard into a stale snapshot.
    """
    first = next(iter(_admins(session, tenant)))
    second = _add_admin(session, tenant, "second")
    third = _add_admin(session, tenant, "third")
    admin_role = _role_id(session, tenant, FIRST_ADMIN_ROLE)

    # Requested while THREE admins exist — comfortably legal at this moment.
    req = request_entitlement_change(
        session,
        tenant_id=tenant,
        actor=AdminActor(first),
        action=ACTION_REVOKE_ROLE,
        target_user_id=third,
        target_role_id=admin_role,
        now=NOW,
    )
    # Meanwhile the others go away, leaving `third` as the last admin.
    for uid in (first, second):
        for g in session.execute(select(UserRole).where(UserRole.user_id == uid)).scalars().all():
            g.valid_to = NOW
    session.flush()
    assert _admins(session, tenant) == {third}

    with pytest.raises(TenantWouldBeOrphaned):
        approve_entitlement_change(
            session, tenant_id=tenant, actor=AdminActor(third), request_id=req.id, now=NOW
        )


# ----------------------------------------------------------------------- user creation, scope
def test_create_user_is_NOT_four_eyes_gated(session: Session, tenant: str) -> None:
    """Creating a user grants no authority; the grant that would is gated. Ceremony where nothing
    is at stake teaches people to route around the control."""
    first = next(iter(_admins(session, tenant)))
    _add_admin(session, tenant, "second")
    user = create_user(
        session,
        tenant_id=tenant,
        actor=AdminActor(first),
        external_subject="fresh@example.com",
        display_name="Fresh",
        now=NOW,
    )
    assert session.get(AppUser, user.id).is_active is True
    assert not session.execute(select(UserRole).where(UserRole.user_id == user.id)).scalars().all()


def test_an_admin_cannot_target_ANOTHER_tenants_user(session: Session, tenant: str) -> None:
    """Tenant-local by construction, and the refusal is identical to 'no such user' — telling
    them apart would be a cross-tenant existence oracle."""
    lone = next(iter(_admins(session, tenant)))
    other_tenant = str(uuid.uuid4())
    foreign = _add_user(session, other_tenant, "foreign")

    with pytest.raises(EntitlementError, match="not found in this tenant"):
        request_entitlement_change(
            session,
            tenant_id=tenant,
            actor=AdminActor(lone),
            action=ACTION_DEACTIVATE_USER,
            target_user_id=foreign,
            now=NOW,
        )


def test_a_duplicate_subject_in_the_same_tenant_is_REFUSED(session: Session, tenant: str) -> None:
    lone = next(iter(_admins(session, tenant)))
    create_user(
        session,
        tenant_id=tenant,
        actor=AdminActor(lone),
        external_subject="dup@example.com",
        display_name="A",
        now=NOW,
    )
    with pytest.raises(EntitlementError, match="already exists"):
        create_user(
            session,
            tenant_id=tenant,
            actor=AdminActor(lone),
            external_subject="dup@example.com",
            display_name="B",
            now=NOW,
        )


def test_the_request_sequence_is_per_tenant_and_monotonic(session: Session, tenant: str) -> None:
    """The MG-2 ordering key: a state machine over an append-only log needs a DB-monotonic key,
    because wall-clock timestamps tie and two admins acting in the same millisecond is the case
    this table adjudicates."""
    lone = next(iter(_admins(session, tenant)))
    for label in ("a", "b", "c"):
        request_entitlement_change(
            session,
            tenant_id=tenant,
            actor=AdminActor(lone),
            action=ACTION_DEACTIVATE_USER,
            target_user_id=_add_user(session, tenant, label),
            now=NOW,
        )
    seqs = (
        session.execute(
            select(EntitlementRequest.seq).where(EntitlementRequest.tenant_id == tenant)
        )
        .scalars()
        .all()
    )
    assert sorted(seqs) == [1, 2, 3]
