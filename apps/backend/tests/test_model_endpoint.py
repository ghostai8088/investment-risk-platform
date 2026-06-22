"""End-to-end tests of the model-registry endpoints (POST/GET; 201/200/401/403/404/422).

SQLite has no RLS, so the cross-tenant RLS-hidden 404 is proven in
``packages/shared-python/tests/test_model_registry_pg.py``; here we prove entitlement gating
(deny-by-default), server-side tenant stamping, audit emission, and the read shapes.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from irp_backend.api.models import router as models_router
from irp_backend.deps import get_db
from irp_shared.audit.models import AuditEvent
from irp_shared.db.session import make_engine, make_session_factory
from irp_shared.entitlement.models import AppUser, Permission, Role, RolePermission, UserRole
from irp_shared.entitlement.service import Principal
from irp_shared.model.models import Model
from irp_shared.models import Base


@pytest.fixture
def client_and_principal() -> Iterator[tuple[TestClient, Principal, Session]]:
    engine = make_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    db = make_session_factory(engine)()

    tenant_id = str(uuid.uuid4())
    user = AppUser(tenant_id=tenant_id, display_name="U")
    role = Role(tenant_id=tenant_id, code="r", name="R")
    db.add_all([user, role])
    db.flush()
    for code in ("model.inventory.view", "model.inventory.register"):
        perm = Permission(code=code, description="d")
        db.add(perm)
        db.flush()
        db.add(RolePermission(role_id=role.id, permission_id=perm.id))
    db.add(UserRole(tenant_id=tenant_id, user_id=user.id, role_id=role.id))
    db.commit()
    principal = Principal(user_id=user.id, tenant_id=tenant_id)

    def _override_db() -> Iterator[Session]:
        yield db

    app = FastAPI()
    app.include_router(models_router)
    app.dependency_overrides[get_db] = _override_db
    try:
        yield TestClient(app), principal, db
    finally:
        db.close()
        engine.dispose()


def _headers(p: Principal) -> dict[str, str]:
    return {"X-User-Id": p.user_id, "X-Tenant-Id": p.tenant_id}


_BODY = {
    "code": "M1",
    "name": "A model",
    "model_type": "STATISTICAL",
    "version_label": "1.0.0",
    "assumptions": ["a1"],
    "limitations": ["l1"],
}


def test_register_model_201_and_audited(
    client_and_principal: tuple[TestClient, Principal, Session],
) -> None:
    client, principal, db = client_and_principal
    resp = client.post("/models", json=_BODY, headers=_headers(principal))
    assert resp.status_code == 201
    body = resp.json()
    assert body["code"] == "M1" and body["version_label"] == "1.0.0"
    # MODEL.REGISTER emitted.
    assert (
        db.execute(
            select(func.count())
            .select_from(AuditEvent)
            .where(AuditEvent.event_type == "MODEL.REGISTER")
        ).scalar_one()
        == 1
    )


def test_register_stamps_caller_tenant_ignoring_body(
    client_and_principal: tuple[TestClient, Principal, Session],
) -> None:
    client, principal, db = client_and_principal
    forged = {**_BODY, "code": "M2", "tenant_id": str(uuid.uuid4())}  # forged tenant_id is ignored
    resp = client.post("/models", json=forged, headers=_headers(principal))
    assert resp.status_code == 201
    model = db.execute(select(Model).where(Model.code == "M2")).scalar_one()
    assert model.tenant_id == principal.tenant_id  # server-stamped, not the forged value


def test_register_without_permission_403(
    client_and_principal: tuple[TestClient, Principal, Session],
) -> None:
    client, principal, _ = client_and_principal
    resp = client.post(
        "/models",
        json=_BODY,
        headers={"X-User-Id": str(uuid.uuid4()), "X-Tenant-Id": principal.tenant_id},
    )
    assert resp.status_code == 403


def test_register_missing_principal_401(
    client_and_principal: tuple[TestClient, Principal, Session],
) -> None:
    client, _, _ = client_and_principal
    assert client.post("/models", json=_BODY).status_code == 401


def test_list_and_get_model(
    client_and_principal: tuple[TestClient, Principal, Session],
) -> None:
    client, principal, _ = client_and_principal
    created = client.post("/models", json=_BODY, headers=_headers(principal)).json()
    listed = client.get("/models", headers=_headers(principal))
    assert listed.status_code == 200 and any(m["code"] == "M1" for m in listed.json())
    detail = client.get(f"/models/{created['id']}", headers=_headers(principal))
    assert detail.status_code == 200
    body = detail.json()
    assert body["validation_status"] == "UNVALIDATED"
    assert body["versions"][0]["assumptions"] == ["a1"]
    assert body["versions"][0]["limitations"] == ["l1"]


def test_get_unknown_is_404_fixed_body(
    client_and_principal: tuple[TestClient, Principal, Session],
) -> None:
    client, principal, _ = client_and_principal
    resp = client.get(f"/models/{uuid.uuid4()}", headers=_headers(principal))
    assert resp.status_code == 404
    assert resp.json()["detail"] == "model not found"


def test_get_malformed_id_422(
    client_and_principal: tuple[TestClient, Principal, Session],
) -> None:
    client, principal, _ = client_and_principal
    assert client.get("/models/not-a-uuid", headers=_headers(principal)).status_code == 422


def test_get_without_view_403(
    client_and_principal: tuple[TestClient, Principal, Session],
) -> None:
    client, principal, _ = client_and_principal
    resp = client.get(
        "/models",
        headers={"X-User-Id": str(uuid.uuid4()), "X-Tenant-Id": principal.tenant_id},
    )
    assert resp.status_code == 403
