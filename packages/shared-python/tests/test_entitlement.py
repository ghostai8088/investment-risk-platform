"""Entitlement tests: allow, deny, tenant mismatch, deny-by-default, grant audit."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.orm import Session

from irp_shared.audit.models import AuditEvent
from irp_shared.audit.service import verify_chain
from irp_shared.entitlement.errors import PermissionDenied
from irp_shared.entitlement.models import AppUser, Role
from irp_shared.entitlement.service import Principal, grant_role, has_permission, require_permission


def test_allow_when_granted(session: Session, seed) -> None:
    result = seed("foundation.read")
    assert has_permission(session, result.principal, "foundation.read", result.tenant_id) is True


def test_deny_missing_permission(session: Session, seed) -> None:
    # User has a role+grant but the role does not hold the requested permission.
    result = seed("foundation.read", with_permission=False)
    assert has_permission(session, result.principal, "foundation.read", result.tenant_id) is False


def test_deny_by_default_no_grant(session: Session, seed) -> None:
    result = seed("foundation.read", with_grant=False)
    assert has_permission(session, result.principal, "foundation.read", result.tenant_id) is False


def test_tenant_mismatch_denied(session: Session, seed) -> None:
    result = seed("foundation.read")
    other_tenant = str(uuid.uuid4())
    # Same principal, but the resource belongs to a different tenant.
    assert has_permission(session, result.principal, "foundation.read", other_tenant) is False


def test_require_permission_raises(session: Session, seed) -> None:
    result = seed("foundation.read", with_grant=False)
    with pytest.raises(PermissionDenied):
        require_permission(session, result.principal, "foundation.read", result.tenant_id)


def test_grant_role_is_audited(session: Session) -> None:
    tenant = str(uuid.uuid4())
    actor = Principal(user_id="admin-1", tenant_id=tenant)
    user = AppUser(tenant_id=tenant, display_name="U")
    role = Role(tenant_id=tenant, code="r", name="R")
    session.add_all([user, role])
    session.flush()

    grant_role(session, actor=actor, user_id=user.id, role_id=role.id, tenant_id=tenant)

    events = session.query(AuditEvent).filter(AuditEvent.event_type == "ENTITLEMENT.GRANT").all()
    assert len(events) == 1
    assert verify_chain(session, tenant).ok is True
