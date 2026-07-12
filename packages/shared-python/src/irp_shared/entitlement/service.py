"""Entitlement checks: tenant-scoped, deny-by-default (BR-11, BR-17).

A permission is granted only when an *active* user-role assignment in the principal's
tenant links to a role that holds the permission. Any missing link, inactive window, or
tenant mismatch results in denial.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from irp_shared.audit.actions import ACTION_GRANT
from irp_shared.audit.service import record_event
from irp_shared.db.mixins import utcnow
from irp_shared.entitlement.errors import PermissionDenied
from irp_shared.entitlement.models import (
    Permission,
    Role,
    RolePermission,
    UserRole,
)


@dataclass(frozen=True)
class Principal:
    """The authenticated subject. Real identity arrives via SSO (AD-007); for now it is
    supplied explicitly by the caller / dev header shim."""

    user_id: str
    tenant_id: str


def has_permission(
    session: Session,
    principal: Principal,
    permission_code: str,
    resource_tenant_id: str,
    at: datetime | None = None,
) -> bool:
    # Tenant isolation (BR-17): a principal may only act within its own tenant.
    if str(principal.tenant_id) != str(resource_tenant_id):
        return False

    now = at or utcnow()
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)

    stmt = (
        select(Permission.code)
        .join(RolePermission, RolePermission.permission_id == Permission.id)
        .join(Role, Role.id == RolePermission.role_id)
        .join(UserRole, UserRole.role_id == Role.id)
        .where(
            UserRole.user_id == principal.user_id,
            UserRole.tenant_id == principal.tenant_id,
            UserRole.valid_from <= now,
            or_(UserRole.valid_to.is_(None), UserRole.valid_to > now),
            Permission.code == permission_code,
        )
        .limit(1)
    )
    return session.execute(stmt).first() is not None


def require_permission(
    session: Session,
    principal: Principal,
    permission_code: str,
    resource_tenant_id: str,
) -> None:
    """Raise :class:`PermissionDenied` unless the principal holds the permission."""
    if not has_permission(session, principal, permission_code, resource_tenant_id):
        raise PermissionDenied(permission_code, str(resource_tenant_id))


def grant_role(
    session: Session,
    *,
    actor: Principal,
    user_id: str,
    role_id: str,
    tenant_id: str,
) -> UserRole:
    """Create a tenant-scoped role assignment and audit it (ENTITLEMENT.GRANT, BR-7).

    The actor must be in the same tenant (SoD/maker-checker enforcement is layered on in a
    later step; this records the grant immutably for now)."""
    if str(actor.tenant_id) != str(tenant_id):
        raise PermissionDenied("entitlement.grant", str(tenant_id))

    assignment = UserRole(tenant_id=str(tenant_id), user_id=user_id, role_id=role_id)
    session.add(assignment)
    session.flush()
    record_event(
        session,
        event_type="ENTITLEMENT.GRANT",
        tenant_id=str(tenant_id),
        actor_type="user",
        actor_id=actor.user_id,
        source_module="entitlement",
        entity_type="user_role",
        entity_id=assignment.id,
        action=ACTION_GRANT,
        after_value={"user_id": user_id, "role_id": role_id},
        data_classification="DC-2",
        severity="notice",
    )
    return assignment
