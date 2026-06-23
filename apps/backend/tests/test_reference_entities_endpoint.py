"""End-to-end tests of the P1B-2 legal-entity / issuer / counterparty endpoints.

SQLite has no RLS, so cross-tenant isolation is proven in
``packages/shared-python/tests/test_reference_entities_pg.py``; here we prove entitlement gating
(deny-by-default per entity, no DB side-effect on denial), server-side tenant stamping, profile→core
resolution (cross-tenant/unknown core → 404), the hierarchy detail (ultimate_parent_id), 404/422.
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

from irp_backend.api.reference_entities import router as reference_entities_router
from irp_backend.deps import get_db
from irp_shared.audit.models import AuditEvent
from irp_shared.db.session import make_engine, make_session_factory
from irp_shared.entitlement.models import AppUser, Permission, Role, RolePermission, UserRole
from irp_shared.entitlement.service import Principal
from irp_shared.models import Base
from irp_shared.reference.models import Counterparty, Issuer, LegalEntity

_PERMS = (
    "reference.legal_entity.view",
    "reference.legal_entity.edit",
    "reference.issuer.view",
    "reference.issuer.edit",
    "reference.counterparty.view",
    "reference.counterparty.edit",
)


@pytest.fixture
def ctx() -> Iterator[tuple[TestClient, Principal, Session]]:
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
    for code in _PERMS:
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
    app.include_router(reference_entities_router)
    app.dependency_overrides[get_db] = _override_db
    try:
        yield TestClient(app), principal, db
    finally:
        db.close()
        engine.dispose()


def _headers(p: Principal) -> dict[str, str]:
    return {"X-User-Id": p.user_id, "X-Tenant-Id": p.tenant_id}


def _no_perm_headers(p: Principal) -> dict[str, str]:
    return {"X-User-Id": str(uuid.uuid4()), "X-Tenant-Id": p.tenant_id}


def _make_le(client: TestClient, principal: Principal, code: str = "LE", **kw) -> dict:  # noqa: ANN003
    body = {"code": code, "name": code, **kw}
    resp = client.post("/reference/legal-entities", json=body, headers=_headers(principal))
    assert resp.status_code == 201, resp.text
    return resp.json()


# --- legal_entity ---


def test_create_legal_entity_201_stamps_tenant_and_audits(
    ctx: tuple[TestClient, Principal, Session],
) -> None:
    client, principal, db = ctx
    resp = client.post(
        "/reference/legal-entities",
        json={"code": "LE1", "name": "Entity One", "lei": "LEI1", "tenant_id": str(uuid.uuid4())},
        headers=_headers(principal),
    )
    assert resp.status_code == 201, resp.text
    row = db.execute(select(LegalEntity)).scalar_one()
    assert row.tenant_id == principal.tenant_id  # forged body tenant_id ignored
    assert (
        db.execute(
            select(func.count())
            .select_from(AuditEvent)
            .where(AuditEvent.event_type == "REFERENCE.CREATE")
        ).scalar_one()
        == 1
    )


def test_create_legal_entity_without_edit_403_no_write(
    ctx: tuple[TestClient, Principal, Session],
) -> None:
    client, principal, db = ctx
    resp = client.post(
        "/reference/legal-entities",
        json={"code": "LE", "name": "x"},
        headers=_no_perm_headers(principal),
    )
    assert resp.status_code == 403
    assert db.execute(select(func.count()).select_from(LegalEntity)).scalar_one() == 0
    assert db.execute(select(func.count()).select_from(AuditEvent)).scalar_one() == 0


def test_legal_entity_hierarchy_detail_returns_ultimate_parent(
    ctx: tuple[TestClient, Principal, Session],
) -> None:
    client, principal, _ = ctx
    ult = _make_le(client, principal, "ULT")
    mid = _make_le(client, principal, "MID", parent_legal_entity_id=ult["id"])
    leaf = _make_le(client, principal, "LEAF", parent_legal_entity_id=mid["id"])
    detail = client.get(f"/reference/legal-entities/{leaf['id']}", headers=_headers(principal))
    assert detail.status_code == 200
    assert detail.json()["ultimate_parent_id"] == ult["id"]
    assert detail.json()["parent_legal_entity_id"] == mid["id"]


def test_create_legal_entity_unknown_parent_404(
    ctx: tuple[TestClient, Principal, Session],
) -> None:
    client, principal, _ = ctx
    resp = client.post(
        "/reference/legal-entities",
        json={"code": "X", "name": "x", "parent_legal_entity_id": str(uuid.uuid4())},
        headers=_headers(principal),
    )
    assert resp.status_code == 404


def test_legal_entity_404_and_422(ctx: tuple[TestClient, Principal, Session]) -> None:
    client, principal, _ = ctx
    assert (
        client.get(
            f"/reference/legal-entities/{uuid.uuid4()}", headers=_headers(principal)
        ).status_code
        == 404
    )
    assert (
        client.get("/reference/legal-entities/not-a-uuid", headers=_headers(principal)).status_code
        == 422
    )


# --- issuer / counterparty (profiles over the core) ---


def test_create_issuer_and_counterparty_via_core(
    ctx: tuple[TestClient, Principal, Session],
) -> None:
    client, principal, db = ctx
    le = _make_le(client, principal, "BANK", lei="LEIBANK")
    ir = client.post(
        "/reference/issuers",
        json={"legal_entity_id": le["id"], "issuer_type": "CORPORATE"},
        headers=_headers(principal),
    )
    cr = client.post(
        "/reference/counterparties",
        json={"legal_entity_id": le["id"], "counterparty_type": "BANK"},
        headers=_headers(principal),
    )
    assert ir.status_code == 201 and cr.status_code == 201
    assert db.execute(select(func.count()).select_from(Issuer)).scalar_one() == 1
    assert db.execute(select(func.count()).select_from(Counterparty)).scalar_one() == 1
    # Issuer detail joins the core for LEI/name.
    detail = client.get(f"/reference/issuers/{ir.json()['id']}", headers=_headers(principal))
    assert detail.status_code == 200
    assert detail.json()["legal_entity_code"] == "BANK" and detail.json()["lei"] == "LEIBANK"


def test_create_issuer_unknown_core_404(ctx: tuple[TestClient, Principal, Session]) -> None:
    client, principal, _ = ctx
    resp = client.post(
        "/reference/issuers",
        json={"legal_entity_id": str(uuid.uuid4())},
        headers=_headers(principal),
    )
    assert resp.status_code == 404


def test_create_issuer_malformed_core_id_422(
    ctx: tuple[TestClient, Principal, Session],
) -> None:
    client, principal, _ = ctx
    resp = client.post(
        "/reference/issuers",
        json={"legal_entity_id": "not-a-uuid"},
        headers=_headers(principal),
    )
    assert resp.status_code == 422


def test_issuer_deny_by_default_no_write(ctx: tuple[TestClient, Principal, Session]) -> None:
    client, principal, db = ctx
    le = _make_le(client, principal, "LE")
    resp = client.post(
        "/reference/issuers",
        json={"legal_entity_id": le["id"]},
        headers=_no_perm_headers(principal),
    )
    assert resp.status_code == 403
    assert db.execute(select(func.count()).select_from(Issuer)).scalar_one() == 0


def test_counterparty_deny_by_default(ctx: tuple[TestClient, Principal, Session]) -> None:
    client, principal, _ = ctx
    le = _make_le(client, principal, "LE")
    resp = client.post(
        "/reference/counterparties",
        json={"legal_entity_id": le["id"]},
        headers=_no_perm_headers(principal),
    )
    assert resp.status_code == 403


def test_list_endpoints_require_view(ctx: tuple[TestClient, Principal, Session]) -> None:
    client, principal, _ = ctx
    for path in ("/reference/legal-entities", "/reference/issuers", "/reference/counterparties"):
        assert client.get(path, headers=_no_perm_headers(principal)).status_code == 403


def test_missing_principal_401(ctx: tuple[TestClient, Principal, Session]) -> None:
    client, _, _ = ctx
    assert client.get("/reference/legal-entities").status_code == 401
