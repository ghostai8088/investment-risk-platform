"""End-to-end test of GET /lineage/edges/{id} (200 / 401 / 403 / 404).

SQLite has no RLS, so the cross-tenant *RLS-hidden* 404 is proven in
``packages/shared-python/tests/test_lineage_pg.py``; here we prove entitlement gating
(deny-by-default) and that a missing edge yields 404.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from irp_backend.api.lineage import router as lineage_router
from irp_backend.deps import get_db
from irp_shared.db.session import make_engine, make_session_factory
from irp_shared.entitlement.models import AppUser, Permission, Role, RolePermission, UserRole
from irp_shared.entitlement.service import Principal
from irp_shared.lineage.service import record_lineage, register_data_source
from irp_shared.models import Base


@pytest.fixture
def client_and_edge() -> Iterator[tuple[TestClient, Principal, str]]:
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
    perm = Permission(code="lineage.view", description="d")
    db.add_all([user, role, perm])
    db.flush()
    db.add(RolePermission(role_id=role.id, permission_id=perm.id))
    db.add(UserRole(tenant_id=tenant_id, user_id=user.id, role_id=role.id))

    src = register_data_source(
        db, tenant_id=tenant_id, code="SRC", name="n", source_type="INTERNAL", actor_id="a"
    )
    edge = record_lineage(
        db, source=src, target_entity_type="synthetic.t", target_entity_id=str(uuid.uuid4())
    )
    db.commit()
    principal = Principal(user_id=user.id, tenant_id=tenant_id)

    def _override_db() -> Iterator[Session]:
        yield db

    app = FastAPI()
    app.include_router(lineage_router)
    app.dependency_overrides[get_db] = _override_db

    try:
        yield TestClient(app), principal, edge.id
    finally:
        db.close()
        engine.dispose()


def _headers(p: Principal) -> dict[str, str]:
    return {"X-User-Id": p.user_id, "X-Tenant-Id": p.tenant_id}


def test_get_edge_allows_granted_principal(
    client_and_edge: tuple[TestClient, Principal, str],
) -> None:
    client, principal, edge_id = client_and_edge
    resp = client.get(f"/lineage/edges/{edge_id}", headers=_headers(principal))
    assert resp.status_code == 200
    assert resp.json()["id"] == edge_id
    assert resp.json()["source_type"] == "data_source"


def test_missing_principal_is_401(client_and_edge: tuple[TestClient, Principal, str]) -> None:
    client, _, edge_id = client_and_edge
    assert client.get(f"/lineage/edges/{edge_id}").status_code == 401


def test_unauthorized_principal_is_403(
    client_and_edge: tuple[TestClient, Principal, str],
) -> None:
    client, principal, edge_id = client_and_edge
    resp = client.get(
        f"/lineage/edges/{edge_id}",
        headers={"X-User-Id": str(uuid.uuid4()), "X-Tenant-Id": principal.tenant_id},
    )
    assert resp.status_code == 403


def test_unknown_edge_is_404(client_and_edge: tuple[TestClient, Principal, str]) -> None:
    client, principal, _ = client_and_edge
    resp = client.get(f"/lineage/edges/{uuid.uuid4()}", headers=_headers(principal))
    assert resp.status_code == 404
    # Fixed body so a not-found and a (PG) cross-tenant-hidden id stay indistinguishable.
    assert resp.json()["detail"] == "lineage edge not found"


def test_malformed_edge_id_is_422(client_and_edge: tuple[TestClient, Principal, str]) -> None:
    client, principal, _ = client_and_edge
    # A non-UUID id is rejected uniformly (422) before any DB hit — no 500 / oracle distinction.
    resp = client.get("/lineage/edges/not-a-uuid", headers=_headers(principal))
    assert resp.status_code == 422
