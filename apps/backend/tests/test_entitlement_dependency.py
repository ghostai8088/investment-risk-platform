"""End-to-end test of the entitlement FastAPI dependency (allow / 401 / 403)."""

from __future__ import annotations

import uuid
from collections.abc import Iterator

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from irp_backend.deps import get_db, require_permission
from irp_shared.db.session import make_engine, make_session_factory
from irp_shared.entitlement.models import AppUser, Permission, Role, RolePermission, UserRole
from irp_shared.entitlement.service import Principal
from irp_shared.models import Base

PERMISSION = "foundation.read"


@pytest.fixture
def client_and_principal() -> Iterator[tuple[TestClient, Principal]]:
    engine = make_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = make_session_factory(engine)
    db = factory()

    tenant_id = str(uuid.uuid4())
    user = AppUser(tenant_id=tenant_id, display_name="U")
    role = Role(tenant_id=tenant_id, code="r", name="R")
    permission = Permission(code=PERMISSION, description="d")
    db.add_all([user, role, permission])
    db.flush()
    db.add(RolePermission(role_id=role.id, permission_id=permission.id))
    db.add(UserRole(tenant_id=tenant_id, user_id=user.id, role_id=role.id))
    db.commit()
    principal = Principal(user_id=user.id, tenant_id=tenant_id)

    app = FastAPI()
    guard = require_permission(PERMISSION)

    @app.get("/_test/guarded")
    def guarded(p: Principal = Depends(guard)) -> dict[str, str]:
        return {"user_id": p.user_id}

    def _override_db() -> Iterator[Session]:
        yield db

    app.dependency_overrides[get_db] = _override_db

    try:
        yield TestClient(app), principal
    finally:
        db.close()
        engine.dispose()


def test_allows_granted_principal(client_and_principal: tuple[TestClient, Principal]) -> None:
    client, principal = client_and_principal
    resp = client.get(
        "/_test/guarded",
        headers={"X-User-Id": principal.user_id, "X-Tenant-Id": principal.tenant_id},
    )
    assert resp.status_code == 200
    assert resp.json() == {"user_id": principal.user_id}


def test_missing_principal_is_401(client_and_principal: tuple[TestClient, Principal]) -> None:
    client, _ = client_and_principal
    resp = client.get("/_test/guarded")
    assert resp.status_code == 401


def test_unknown_user_is_denied_403(client_and_principal: tuple[TestClient, Principal]) -> None:
    client, principal = client_and_principal
    resp = client.get(
        "/_test/guarded",
        headers={"X-User-Id": str(uuid.uuid4()), "X-Tenant-Id": principal.tenant_id},
    )
    assert resp.status_code == 403
