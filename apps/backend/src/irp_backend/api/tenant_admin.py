"""Tenant-local user and role administration (ONBOARD-1b).

ONBOARD-1a gave a tenant a first administrator who could authenticate and manage nobody. This is
the surface that lets them manage somebody — and the surface where SOD-04's four-eyes becomes real
rather than a sentence in the SoD model.

**Every route is tenant-LOCAL, and the fence is the principal's own tenant.** There is no
``{tenant_id}`` path parameter anywhere below, deliberately: a path parameter invites the question
"what if I put a different tenant's id here?", and the answer would have to be a check that
somebody could forget to write. The principal's tenant IS the scope, armed by
``get_tenant_session`` and enforced by RLS underneath — so a cross-tenant read returns nothing and
a cross-tenant write is refused by the service's own lookup, without this module owning a rule.

**The four-eyes outcome is in the RESPONSE, not implied by the status code.** A grant that was
queued for a second admin and a grant that took effect both return 200 — they are both successful
requests — so the body carries ``status`` (``PENDING``/``DIRECT``/``APPROVED``) and the UI reads
it. Returning 202 for one and 200 for the other was considered and rejected: a caller who ignores
a status code still ignores it, whereas a caller who ignores a body field finds the act simply has
not happened, which is the direction that fails safe.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from irp_backend.deps import get_tenant_session, require_permission, require_uuid_principal_id
from irp_shared.entitlement.admin_service import (
    AdminActor,
    EntitlementError,
    approve_entitlement_change,
    create_user,
    request_entitlement_change,
)
from irp_shared.entitlement.models import AppUser, Role, UserRole
from irp_shared.entitlement.request_models import (
    ACTION_DEACTIVATE_USER,
    ACTION_GRANT_ROLE,
    ACTION_REVOKE_ROLE,
    STATUS_PENDING,
    EntitlementRequest,
)
from irp_shared.entitlement.service import Principal

router = APIRouter(tags=["tenant administration"])

#: Module-level guard singletons (deny-by-default; built once, not in argument defaults).
_require_view = require_permission("user.view")
_require_manage = require_permission("user.manage")
_require_assign = require_permission("role.assign")
_require_approve = require_permission("role.approve")


class UserOut(BaseModel):
    id: str
    display_name: str
    #: The OIDC subject. Person-identifying — which is why `user.view` EXCLUDES auditor_3l
    #: (ratified OQ-ONB-5); an entitlement roster is not governed-output oversight scope.
    external_subject: str | None
    is_active: bool
    roles: list[str]


class UserCreateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    external_subject: str = Field(min_length=1, max_length=255)
    display_name: str = Field(min_length=1, max_length=255)


class RoleGrantIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role_id: uuid.UUID
    reason: str | None = Field(default=None, max_length=500)


class EntitlementRequestOut(BaseModel):
    id: str
    seq: int
    action: str
    #: PENDING (a second admin must approve), DIRECT (the bootstrap window — no other admin
    #: existed), or APPROVED. The caller reads THIS, not the status code.
    status: str
    requested_by: str
    target_user_id: str
    target_role_id: str | None
    resolved_by: str | None
    #: True when the act took effect without a second pair of eyes. Surfaced so an operator sees
    #: it in the UI, not only an auditor in the chain.
    direct: bool


def _as_request_out(row: EntitlementRequest) -> EntitlementRequestOut:
    return EntitlementRequestOut(
        id=str(row.id),
        seq=int(row.seq),
        action=str(row.action),
        status=str(row.status),
        requested_by=str(row.requested_by),
        target_user_id=str(row.target_user_id),
        target_role_id=str(row.target_role_id) if row.target_role_id else None,
        resolved_by=str(row.resolved_by) if row.resolved_by else None,
        direct=row.status == "DIRECT",
    )


def _raise_mapped(exc: EntitlementError) -> None:
    """Refusals are 422 — the caller asked for something the platform will not do.

    ``TenantWouldBeOrphaned`` is deliberately NOT a 409: nothing is in conflict, the request is
    simply invalid against an invariant, and a 409 would invite a retry that can never succeed.
    """
    raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


@router.get("/users", response_model=list[UserOut])
def list_users(
    principal: Principal = Depends(_require_view),
    db: Session = Depends(get_tenant_session),
) -> list[UserOut]:
    """The roster: every user in the caller's tenant with their currently-valid roles."""
    users = (
        db.execute(
            select(AppUser).where(AppUser.tenant_id == principal.tenant_id).order_by(AppUser.id)
        )
        .scalars()
        .all()
    )
    grants = db.execute(
        select(UserRole.user_id, Role.code)
        .join(Role, Role.id == UserRole.role_id)
        .where(
            UserRole.tenant_id == principal.tenant_id,
            or_(UserRole.valid_to.is_(None), UserRole.valid_to > datetime.now(UTC)),
        )
    ).all()
    by_user: dict[str, list[str]] = {}
    for uid, code in grants:
        by_user.setdefault(str(uid), []).append(str(code))
    return [
        UserOut(
            id=str(u.id),
            display_name=u.display_name,
            external_subject=u.external_subject,
            is_active=bool(u.is_active),
            roles=sorted(by_user.get(str(u.id), [])),
        )
        for u in users
    ]


@router.post("/users", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def create_tenant_user(
    payload: UserCreateIn,
    principal: Principal = Depends(_require_manage),
    db: Session = Depends(get_tenant_session),
) -> UserOut:
    """Create a user. NOT four-eyes-gated: a user with no roles holds no authority."""
    actor = AdminActor(require_uuid_principal_id(principal))
    try:
        user = create_user(
            db,
            tenant_id=principal.tenant_id,
            actor=actor,
            external_subject=payload.external_subject,
            display_name=payload.display_name,
        )
    except EntitlementError as exc:
        db.rollback()
        _raise_mapped(exc)
    db.commit()
    return UserOut(
        id=str(user.id),
        display_name=user.display_name,
        external_subject=user.external_subject,
        is_active=True,
        roles=[],
    )


@router.post("/users/{user_id}/roles", response_model=EntitlementRequestOut)
def grant_role_to_user(
    user_id: uuid.UUID,
    payload: RoleGrantIn,
    principal: Principal = Depends(_require_assign),
    db: Session = Depends(get_tenant_session),
) -> EntitlementRequestOut:
    """Grant a role — PENDING when another admin exists to approve, DIRECT otherwise."""
    return _entitlement_act(
        db,
        principal,
        action=ACTION_GRANT_ROLE,
        target_user_id=str(user_id),
        target_role_id=str(payload.role_id),
        reason=payload.reason,
    )


@router.delete("/users/{user_id}/roles/{role_id}", response_model=EntitlementRequestOut)
def revoke_role_from_user(
    user_id: uuid.UUID,
    role_id: uuid.UUID,
    principal: Principal = Depends(_require_assign),
    db: Session = Depends(get_tenant_session),
) -> EntitlementRequestOut:
    """Revoke a role. Refused if it would leave the tenant with no active administrator."""
    return _entitlement_act(
        db,
        principal,
        action=ACTION_REVOKE_ROLE,
        target_user_id=str(user_id),
        target_role_id=str(role_id),
        reason=None,
    )


@router.post("/users/{user_id}/deactivate", response_model=EntitlementRequestOut)
def deactivate_user(
    user_id: uuid.UUID,
    principal: Principal = Depends(_require_manage),
    db: Session = Depends(get_tenant_session),
) -> EntitlementRequestOut:
    """Deactivate a user.

    Rides the SAME four-eyes flow when the target holds ``tenant_admin`` — deactivation removes
    authority exactly as revocation does, and letting it escape would make
    "deactivate the other admin, then act alone" a one-step bypass of the whole control.
    """
    return _entitlement_act(
        db,
        principal,
        action=ACTION_DEACTIVATE_USER,
        target_user_id=str(user_id),
        target_role_id=None,
        reason=None,
    )


def _entitlement_act(
    db: Session,
    principal: Principal,
    *,
    action: str,
    target_user_id: str,
    target_role_id: str | None,
    reason: str | None,
) -> EntitlementRequestOut:
    actor = AdminActor(require_uuid_principal_id(principal))
    try:
        row = request_entitlement_change(
            db,
            tenant_id=principal.tenant_id,
            actor=actor,
            action=action,
            target_user_id=target_user_id,
            target_role_id=target_role_id,
            reason=reason,
        )
    except EntitlementError as exc:
        # TenantWouldBeOrphaned is a subclass — one handler, both refusals (the P3-C1 MRO rule).
        db.rollback()
        _raise_mapped(exc)
    db.commit()
    return _as_request_out(row)


@router.get("/entitlement-requests", response_model=list[EntitlementRequestOut])
def list_pending_requests(
    principal: Principal = Depends(_require_view),
    db: Session = Depends(get_tenant_session),
) -> list[EntitlementRequestOut]:
    """Requests awaiting a second admin. The queue the UI renders."""
    rows = (
        db.execute(
            select(EntitlementRequest)
            .where(
                EntitlementRequest.tenant_id == principal.tenant_id,
                EntitlementRequest.status == STATUS_PENDING,
                # A request is still pending iff NO resolution row points at it. Derived from the
                # log, never from a flag — the request row is immutable, so a flag could not be
                # set anyway.
                EntitlementRequest.id.not_in(
                    select(EntitlementRequest.resolves_request_id).where(
                        EntitlementRequest.tenant_id == principal.tenant_id,
                        EntitlementRequest.resolves_request_id.is_not(None),
                    )
                ),
            )
            .order_by(EntitlementRequest.seq)
        )
        .scalars()
        .all()
    )
    return [_as_request_out(r) for r in rows]


@router.post("/entitlement-requests/{request_id}/approve", response_model=EntitlementRequestOut)
def approve_request(
    request_id: uuid.UUID,
    principal: Principal = Depends(_require_approve),
    db: Session = Depends(get_tenant_session),
) -> EntitlementRequestOut:
    """A SECOND admin approves, and the act takes effect (SOD-04).

    The person-level refusal lives in the service, over canonicalized ids — not here, because a
    route-layer check would be one of several call paths and the invariant belongs where every
    path passes.
    """
    actor = AdminActor(require_uuid_principal_id(principal))
    try:
        row = approve_entitlement_change(
            db,
            tenant_id=principal.tenant_id,
            actor=actor,
            request_id=str(request_id),
        )
    except EntitlementError as exc:
        db.rollback()
        _raise_mapped(exc)
    db.commit()
    return _as_request_out(row)


class RoleOut(BaseModel):
    """Typed, because the FE consumes this via the generated OpenAPI contract (FE-2) — a
    ``list[dict]`` here compiles the screen against ``unknown`` and the contract guards nothing."""

    id: str
    code: str
    name: str


@router.get("/roles", response_model=list[RoleOut])
def list_roles(
    principal: Principal = Depends(_require_view),
    db: Session = Depends(get_tenant_session),
) -> list[RoleOut]:
    """The tenant's roles — what a grant can name."""
    rows = (
        db.execute(select(Role).where(Role.tenant_id == principal.tenant_id).order_by(Role.code))
        .scalars()
        .all()
    )
    return [RoleOut(id=str(r.id), code=r.code, name=r.name) for r in rows]
