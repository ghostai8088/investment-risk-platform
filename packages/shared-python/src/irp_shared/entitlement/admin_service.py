"""Tenant-local user and role administration, with SOD-04's four-eyes (ONBOARD-1b).

Two controls live here and they interact, which is why they share a module rather than a comment:

**The four-eyes gate (OQ-ONB-9A).** An entitlement-affecting act is born PENDING when the tenant
has **≥1 currently-valid OTHER admin**, and needs a second admin's approval before it takes
effect. With no other admin it executes directly, recorded as ``DIRECT`` — a bootstrap window
bounded by the admin count itself, every use of it countable.

**The orphan-proof invariant (OQ-ONB-4A).** A tenant must at all times have **≥1 currently-valid,
ACTIVE-user admin**. Enforced identically against FOUR paths, because each was a real bypass of
the others:

* revoking the last admin's role;
* END-DATING it (``user_role.valid_to``) — the same outcome, spelled as an update, and a naive
  count over "grants that exist" misses it entirely;
* DEACTIVATING the last admin's user (``is_active=False``) — ``get_principal`` refuses inactive
  users, so this orphans the tenant just as thoroughly while touching no grant at all;
* two admins revoking each other CONCURRENTLY — both count-checks see the other as remaining,
  both pass, and the tenant ends with zero. That one is not a logic bug; it is a missing lock.

The two controls compose in a way worth stating: the four-eyes flow means a revocation may be
PENDING rather than immediate, so the orphan check runs **at the moment the act takes effect**
(direct execution, or approval) — never only at request time, when the tenant's admin count may
still be comfortable.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import func, or_, select, text
from sqlalchemy.orm import Session

from irp_shared.audit.actions import ACTION_CREATE, ACTION_STATUS_CHANGE, ACTION_UPDATE
from irp_shared.audit.service import record_event
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

#: Audit codes minted by ONBOARD-1b (R-07, ratified at the ONBOARD-1 gate as OQ-ONB-9A's machinery).
ROLE_GRANT_REQUEST_EVENT = "ROLE.GRANT_REQUEST"
ROLE_GRANT_APPROVE_EVENT = "ROLE.GRANT_APPROVE"


class EntitlementError(ValueError):
    """A refusal. NOTHING has been written."""


class TenantWouldBeOrphaned(EntitlementError):
    """The act would leave the tenant with no valid, active administrator."""


@dataclass(frozen=True)
class AdminActor:
    """The acting administrator. Canonicalized at construction — the API-2 lesson: canonicalize in
    the ACTOR dataclass so the value STAMPED equals the value COMPARED, or the person-level SoD
    compares two spellings of the same person and lets them approve themselves."""

    actor_id: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "actor_id", _canonical(self.actor_id))


def _canonical(actor_id: str) -> str:
    try:
        return str(uuid.UUID(str(actor_id)))
    except (ValueError, AttributeError, TypeError):
        return str(actor_id).strip().lower()


def _lock_tenant(session: Session, tenant_id: str) -> None:
    """Serialize entitlement changes within a tenant (PostgreSQL; no-op elsewhere).

    Without this, the orphan check is a TOCTOU: two admins revoking each other each read the other
    as remaining, both pass, and the tenant is orphaned by two individually-legal acts. Keyed on
    the tenant, transaction-scoped, released at COMMIT.
    """
    if session.bind is not None and session.bind.dialect.name == "postgresql":
        key = int.from_bytes(uuid.UUID(tenant_id).bytes[:8], "big", signed=True)
        session.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": key})


def _admin_role_id(session: Session, tenant_id: str) -> str | None:
    return session.execute(
        select(Role.id).where(Role.tenant_id == tenant_id, Role.code == FIRST_ADMIN_ROLE)
    ).scalar_one_or_none()


def valid_admin_user_ids(
    session: Session, tenant_id: str, *, now: datetime | None = None
) -> set[str]:
    """Users who are administrators RIGHT NOW: an active user, holding a currently-valid grant.

    Both halves matter and each was a separate bypass. ``valid_to`` is honored because end-dating
    a grant removes authority without deleting a row; ``is_active`` is honored because a
    deactivated user cannot authenticate, so counting them as an administrator counts a person who
    cannot administer.
    """
    at = now or datetime.now(UTC)
    admin_role = _admin_role_id(session, tenant_id)
    if admin_role is None:
        return set()
    rows = (
        session.execute(
            select(UserRole.user_id)
            .join(AppUser, AppUser.id == UserRole.user_id)
            .where(
                UserRole.tenant_id == tenant_id,
                UserRole.role_id == admin_role,
                AppUser.is_active.is_(True),
                UserRole.valid_from <= at,
                or_(UserRole.valid_to.is_(None), UserRole.valid_to > at),
            )
        )
        .scalars()
        .all()
    )
    return {str(u) for u in rows}


def _assert_not_orphaning(
    session: Session, tenant_id: str, *, losing_admin: str, now: datetime | None = None
) -> None:
    """Refuse if removing ``losing_admin``'s administration would leave the tenant with none."""
    remaining = valid_admin_user_ids(session, tenant_id, now=now) - {losing_admin}
    if not remaining:
        raise TenantWouldBeOrphaned(
            "refused: this would leave the tenant with no active administrator. "
            "Grant tenant_admin to another active user first."
        )


def _next_seq(session: Session, tenant_id: str) -> int:
    """Per-tenant monotonic sequence, assigned under the tenant lock (the MG-2 pattern)."""
    current = session.execute(
        select(func.max(EntitlementRequest.seq)).where(EntitlementRequest.tenant_id == tenant_id)
    ).scalar()
    return int(current or 0) + 1


def _four_eyes_required(
    session: Session, tenant_id: str, *, requester: str, now: datetime | None = None
) -> bool:
    """True when a SECOND admin exists to approve — i.e. at two admins, not three.

    The threshold is "≥1 OTHER admin". An earlier fix wrote "≥2 other", which exempted every
    two-admin tenant — exactly the tenants where four-eyes first becomes possible, and therefore
    exactly where SOD-04 first binds (verifier pass 2, finding B3).

    **``now`` is threaded through, and it was not at first.** This function read the wall clock
    while ``_assert_not_orphaning`` honored the caller's ``now``, so the two controls in this
    module answered "who are the admins?" against DIFFERENT clocks. Any caller supplying an
    explicit ``now`` — every deterministic one — could get a four-eyes decision computed from a
    population the orphan check would then disagree about. Found while diagnosing a concurrency
    test, which is a roundabout way to find it and exactly why one clock per operation is a rule
    and not a preference.
    """
    return bool(valid_admin_user_ids(session, tenant_id, now=now) - {requester})


def request_entitlement_change(
    session: Session,
    *,
    tenant_id: str,
    actor: AdminActor,
    action: str,
    target_user_id: str,
    target_role_id: str | None = None,
    reason: str | None = None,
    now: datetime | None = None,
) -> EntitlementRequest:
    """Request an entitlement change. Executes directly, or is born PENDING for a second admin.

    Returns the request row either way — ``status`` says which happened, and a caller that ignores
    it will find the act simply has not taken effect (the refusal direction that fails safe).
    """
    at = now or datetime.now(UTC)
    if action not in (ACTION_GRANT_ROLE, ACTION_REVOKE_ROLE, ACTION_DEACTIVATE_USER):
        raise EntitlementError(f"unknown entitlement action: {action!r}")
    if action in (ACTION_GRANT_ROLE, ACTION_REVOKE_ROLE) and not target_role_id:
        raise EntitlementError(f"{action} requires a target role")

    _lock_tenant(session, tenant_id)

    target = session.execute(
        select(AppUser).where(AppUser.id == target_user_id, AppUser.tenant_id == tenant_id)
    ).scalar_one_or_none()
    if target is None:
        # Tenant-scoped by construction: an admin cannot reach into another tenant, and the
        # refusal is the same whether the user is absent or foreign (no cross-tenant oracle).
        raise EntitlementError("target user not found in this tenant")

    pending = _four_eyes_required(session, tenant_id, requester=actor.actor_id, now=at)
    status = STATUS_PENDING if pending else STATUS_DIRECT

    request = EntitlementRequest(
        id=str(uuid.uuid4()),
        tenant_id=tenant_id,
        seq=_next_seq(session, tenant_id),
        action=action,
        status=status,
        requested_by=actor.actor_id,
        requested_at=at,
        target_user_id=target_user_id,
        target_role_id=target_role_id,
        resolved_by=None if pending else actor.actor_id,
        resolved_at=None if pending else at,
        reason=reason,
    )
    session.add(request)
    session.flush()

    if not pending:
        # The bootstrap window: no second admin exists, so the act executes now — and the orphan
        # check still runs, because "nobody can approve this" is not "anything goes".
        _apply(session, request, tenant_id=tenant_id, now=at)

    record_event(
        session,
        tenant_id=tenant_id,
        event_type=ROLE_GRANT_REQUEST_EVENT,
        action=ACTION_CREATE,
        entity_type="entitlement_request",
        entity_id=request.id,
        actor_id=actor.actor_id,
        actor_type="HUMAN",
        source_module="entitlement",
        outcome="success",
        after_value={
            "action": action,
            "status": status,
            "target_user_id": target_user_id,
            "target_role_id": target_role_id,
            # The flag an auditor counts: every act taken without a second pair of eyes, visible
            # in the chain rather than inferable from an absence.
            "direct_grant": status == STATUS_DIRECT,
        },
    )
    session.flush()
    return request


def approve_entitlement_change(
    session: Session,
    *,
    tenant_id: str,
    actor: AdminActor,
    request_id: str,
    now: datetime | None = None,
) -> EntitlementRequest:
    """A SECOND admin approves a pending request, and the act takes effect.

    The person-level refusal is the whole gate (MG-3): approver ≠ requester by principal id, both
    canonicalized in :class:`AdminActor` so the comparison cannot be defeated by case or format —
    the PG uuid cast is case-insensitive, so an uppercase id passes ``require_permission`` and only
    this comparison stops it.
    """
    at = now or datetime.now(UTC)
    _lock_tenant(session, tenant_id)

    request = session.execute(
        select(EntitlementRequest).where(
            EntitlementRequest.id == request_id,
            EntitlementRequest.tenant_id == tenant_id,
        )
    ).scalar_one_or_none()
    if request is None:
        raise EntitlementError("entitlement request not found in this tenant")
    if request.status != STATUS_PENDING:
        raise EntitlementError(f"request is already {request.status}")
    # Already resolved by an appended row? Re-approval must be refused, and the check is a READ of
    # the log rather than a flag on the request — the whole point of appending.
    already = session.execute(
        select(EntitlementRequest.id).where(EntitlementRequest.resolves_request_id == request.id)
    ).scalar_one_or_none()
    if already is not None:
        raise EntitlementError("request has already been resolved")
    if _canonical(request.requested_by) == actor.actor_id:
        raise EntitlementError(
            "refused: an administrator cannot approve their own entitlement request (SOD-04)"
        )

    # Apply first: if the orphan invariant refuses, NOTHING is appended and the request stays
    # PENDING for someone else to decide.
    _apply(session, request, tenant_id=tenant_id, now=at)

    # The resolution is an APPENDED ROW, never a mutation of the request. ENT-075 carries the
    # `irp_prevent_mutation` trigger, so an UPDATE here is refused by PostgreSQL outright — which
    # is how the first implementation of this function was caught: it mutated `request.status`,
    # every SQLite test accepted it, and the trigger did not.
    resolution = EntitlementRequest(
        id=str(uuid.uuid4()),
        tenant_id=tenant_id,
        seq=_next_seq(session, tenant_id),
        action=request.action,
        status=STATUS_APPROVED,
        requested_by=request.requested_by,
        requested_at=request.requested_at,
        target_user_id=request.target_user_id,
        target_role_id=request.target_role_id,
        resolved_by=actor.actor_id,
        resolved_at=at,
        resolves_request_id=request.id,
        reason=request.reason,
    )
    session.add(resolution)
    session.flush()

    record_event(
        session,
        tenant_id=tenant_id,
        event_type=ROLE_GRANT_APPROVE_EVENT,
        # `status_change`, not a new action verb: MG-3 recorded LIMIT.APPROVE the same way, and
        # the action vocabulary is a controlled R-07 list — an approval IS a status change, so
        # minting a verb for it would grow the vocabulary without adding a distinction.
        action=ACTION_STATUS_CHANGE,
        entity_type="entitlement_request",
        entity_id=resolution.id,
        actor_id=actor.actor_id,
        actor_type="HUMAN",
        source_module="entitlement",
        outcome="success",
        after_value={
            "action": request.action,
            "resolves_request_id": request.id,
            "requested_by": request.requested_by,
            "target_user_id": request.target_user_id,
        },
    )
    session.flush()
    return resolution


def _apply(session: Session, request: EntitlementRequest, *, tenant_id: str, now: datetime) -> None:
    """Make the requested act take effect. The orphan check runs HERE, not at request time.

    A revocation may sit PENDING while the tenant's admin count changes underneath it, so checking
    at request time would authorize an act against a state that no longer holds by the time it
    lands.
    """
    admin_role = _admin_role_id(session, tenant_id)
    target = str(request.target_user_id)

    if request.action == ACTION_GRANT_ROLE:
        existing = session.execute(
            select(UserRole).where(
                UserRole.tenant_id == tenant_id,
                UserRole.user_id == target,
                UserRole.role_id == request.target_role_id,
                or_(UserRole.valid_to.is_(None), UserRole.valid_to > now),
            )
        ).scalar_one_or_none()
        if existing is None:
            session.add(
                UserRole(
                    id=str(uuid.uuid4()),
                    tenant_id=tenant_id,
                    user_id=target,
                    role_id=request.target_role_id,
                    valid_from=now,
                )
            )
    elif request.action == ACTION_REVOKE_ROLE:
        if request.target_role_id == admin_role:
            _assert_not_orphaning(session, tenant_id, losing_admin=target, now=now)
        grants = (
            session.execute(
                select(UserRole).where(
                    UserRole.tenant_id == tenant_id,
                    UserRole.user_id == target,
                    UserRole.role_id == request.target_role_id,
                    or_(UserRole.valid_to.is_(None), UserRole.valid_to > now),
                )
            )
            .scalars()
            .all()
        )
        for grant in grants:
            # END-DATE rather than delete: a grant that existed is a fact, and the effective-dated
            # model is how every other tenant-scoped config records "no longer".
            grant.valid_to = now
    elif request.action == ACTION_DEACTIVATE_USER:
        # Deactivation is an entitlement change (finding B2). It also orphans exactly as
        # thoroughly as revocation, so it takes the same check — including when an admin
        # deactivates THEMSELVES.
        if target in valid_admin_user_ids(session, tenant_id, now=now):
            _assert_not_orphaning(session, tenant_id, losing_admin=target, now=now)
        user = session.get(AppUser, target)
        if user is not None:
            user.is_active = False
    session.flush()


def create_user(
    session: Session,
    *,
    tenant_id: str,
    actor: AdminActor,
    external_subject: str,
    display_name: str,
    now: datetime | None = None,
) -> AppUser:
    """Create a user in the acting admin's tenant. NOT four-eyes-gated, deliberately.

    A user with no roles holds no authority — creating one grants nothing. SOD-04 governs
    entitlement CHANGES, and the grant that would give this user authority is itself gated. Gating
    creation too would add ceremony at the point where nothing is at stake, and (worse) would make
    the four-eyes queue a place where new-joiner admin sits, which is how a control acquires a
    reputation for being in the way.
    """
    subject = (external_subject or "").strip()
    name = (display_name or "").strip()
    if not subject:
        raise EntitlementError("external_subject is required")
    if not name:
        raise EntitlementError("display_name is required")
    clash = session.execute(
        select(AppUser).where(AppUser.tenant_id == tenant_id, AppUser.external_subject == subject)
    ).scalar_one_or_none()
    if clash is not None:
        raise EntitlementError(f"a user with subject {subject!r} already exists in this tenant")

    user = AppUser(
        id=str(uuid.uuid4()),
        tenant_id=tenant_id,
        external_subject=subject,
        display_name=name,
        is_active=True,
    )
    session.add(user)
    session.flush()
    record_event(
        session,
        tenant_id=tenant_id,
        event_type="USER.PROVISION",
        action=ACTION_UPDATE,
        entity_type="app_user",
        entity_id=user.id,
        actor_id=actor.actor_id,
        actor_type="HUMAN",
        source_module="entitlement",
        outcome="success",
        after_value={"display_name": name, "seeded_by": "tenant_admin"},
    )
    session.flush()
    return user


__all__ = [
    "ROLE_GRANT_APPROVE_EVENT",
    "ROLE_GRANT_REQUEST_EVENT",
    "AdminActor",
    "EntitlementError",
    "TenantWouldBeOrphaned",
    "approve_entitlement_change",
    "create_user",
    "request_entitlement_change",
    "valid_admin_user_ids",
]
