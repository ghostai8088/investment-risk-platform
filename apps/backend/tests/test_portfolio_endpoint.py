"""End-to-end tests of the P1C-1 portfolio endpoints (ABAC scope anchor).

SQLite has no RLS (isolation is proven in the PG file); here we prove entitlement gating
(deny-by-default; view-only cannot edit), server-side tenant stamping, the create / amend dispatch,
the hierarchy guards at the HTTP layer (unknown parent -> 404; re-parent cycle -> 409; self-parent
->
422), the bounded subtree (/tree) read, the node_type filter, the anchor-not-enforce contract (a
view-holder sees ALL tenant nodes — no scope filtering), and 404/422 shapes.
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

from irp_backend.api.portfolios import router as portfolios_router
from irp_backend.deps import get_db
from irp_shared.audit.models import AuditEvent
from irp_shared.db.session import make_engine, make_session_factory
from irp_shared.entitlement.models import AppUser, Permission, Role, RolePermission, UserRole
from irp_shared.entitlement.service import Principal
from irp_shared.models import Base
from irp_shared.portfolio.models import Portfolio


def _grant(db: Session, tenant_id: str, codes: tuple[str, ...]) -> Principal:
    user = AppUser(tenant_id=tenant_id, display_name="U")
    role = Role(tenant_id=tenant_id, code=f"r-{uuid.uuid4().hex[:8]}", name="R")
    db.add_all([user, role])
    db.flush()
    for code in codes:
        perm = db.execute(select(Permission).where(Permission.code == code)).scalar_one_or_none()
        if perm is None:
            perm = Permission(code=code, description="d")
            db.add(perm)
            db.flush()
        db.add(RolePermission(role_id=role.id, permission_id=perm.id))
    db.add(UserRole(tenant_id=tenant_id, user_id=user.id, role_id=role.id))
    db.flush()
    return Principal(user_id=user.id, tenant_id=tenant_id)


@pytest.fixture
def ctx() -> Iterator[tuple[TestClient, Principal, Principal, Session]]:
    engine = make_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    db = make_session_factory(engine)()

    tenant_id = str(uuid.uuid4())
    maker = _grant(db, tenant_id, ("portfolio.view", "portfolio.edit"))  # data_steward equivalent
    viewer = _grant(db, tenant_id, ("portfolio.view",))  # read-tier; cannot edit
    db.commit()

    def _override_db() -> Iterator[Session]:
        yield db

    app = FastAPI()
    app.include_router(portfolios_router)
    app.dependency_overrides[get_db] = _override_db
    try:
        yield TestClient(app), maker, viewer, db
    finally:
        db.close()
        engine.dispose()


def _h(p: Principal) -> dict[str, str]:
    return {"X-User-Id": p.user_id, "X-Tenant-Id": p.tenant_id}


def _no_perm(p: Principal) -> dict[str, str]:
    return {"X-User-Id": str(uuid.uuid4()), "X-Tenant-Id": p.tenant_id}


def _make(
    client: TestClient, p: Principal, code: str = "P1", node_type: str = "PORTFOLIO", **kw
) -> dict:  # noqa: ANN003
    body = {"code": code, "name": code, "node_type": node_type, **kw}
    r = client.post("/portfolios", json=body, headers=_h(p))
    assert r.status_code == 201, r.text
    return r.json()


def test_create_201_stamps_tenant_and_audits(ctx) -> None:  # noqa: ANN001
    client, maker, _viewer, db = ctx
    out = _make(client, maker, "ROOT", base_currency_code="USD")
    assert out["status"] == "ACTIVE" and out["node_type"] == "PORTFOLIO"
    node = db.get(Portfolio, out["id"])
    assert node is not None and node.tenant_id == maker.tenant_id
    n = db.execute(
        select(func.count()).select_from(AuditEvent).where(AuditEvent.entity_id == out["id"])
    ).scalar_one()
    assert n == 1


def test_create_denied_no_perm(ctx) -> None:  # noqa: ANN001
    client, maker, _viewer, db = ctx
    r = client.post(
        "/portfolios",
        json={"code": "X", "name": "X", "node_type": "FUND"},
        headers=_no_perm(maker),
    )
    assert r.status_code == 403
    assert db.execute(select(func.count()).select_from(Portfolio)).scalar_one() == 0


def test_viewer_cannot_create(ctx) -> None:  # noqa: ANN001
    client, _maker, viewer, _db = ctx
    r = client.post(
        "/portfolios", json={"code": "X", "name": "X", "node_type": "FUND"}, headers=_h(viewer)
    )
    assert r.status_code == 403  # portfolio.view does not grant edit


def test_create_unknown_parent_404(ctx) -> None:  # noqa: ANN001
    client, maker, _viewer, _db = ctx
    r = client.post(
        "/portfolios",
        json={
            "code": "X",
            "name": "X",
            "node_type": "FUND",
            "parent_portfolio_id": str(uuid.uuid4()),
        },
        headers=_h(maker),
    )
    assert r.status_code == 404


def test_get_and_404(ctx) -> None:  # noqa: ANN001
    client, maker, _viewer, _db = ctx
    out = _make(client, maker, "P1")
    r = client.get(f"/portfolios/{out['id']}", headers=_h(maker))
    assert r.status_code == 200 and r.json()["code"] == "P1"
    assert client.get(f"/portfolios/{uuid.uuid4()}", headers=_h(maker)).status_code == 404


def test_bad_uuid_422(ctx) -> None:  # noqa: ANN001
    client, maker, _viewer, _db = ctx
    assert client.get("/portfolios/not-a-uuid", headers=_h(maker)).status_code == 422


def test_amend_rename_and_status(ctx) -> None:  # noqa: ANN001
    client, maker, _viewer, db = ctx
    out = _make(client, maker, "P1")
    r = client.post(
        f"/portfolios/{out['id']}", json={"name": "Renamed", "status": "CLOSED"}, headers=_h(maker)
    )
    assert r.status_code == 200
    body = r.json()
    assert body["name"] == "Renamed" and body["status"] == "CLOSED" and body["record_version"] == 2


def test_self_parent_422(ctx) -> None:  # noqa: ANN001
    client, maker, _viewer, _db = ctx
    out = _make(client, maker, "P1")
    r = client.post(
        f"/portfolios/{out['id']}", json={"parent_portfolio_id": out["id"]}, headers=_h(maker)
    )
    assert r.status_code == 422


def test_reparent_cycle_409(ctx) -> None:  # noqa: ANN001
    client, maker, _viewer, _db = ctx
    root = _make(client, maker, "ROOT")
    child = _make(client, maker, "CHILD", node_type="FUND", parent_portfolio_id=root["id"])
    # re-parenting the root under its own child -> cycle -> 409.
    r = client.post(
        f"/portfolios/{root['id']}",
        json={"parent_portfolio_id": child["id"]},
        headers=_h(maker),
    )
    assert r.status_code == 409


def test_tree_subtree_read(ctx) -> None:  # noqa: ANN001
    client, maker, _viewer, _db = ctx
    root = _make(client, maker, "ROOT")
    f1 = _make(client, maker, "F1", node_type="FUND", parent_portfolio_id=root["id"])
    a1 = _make(client, maker, "A1", node_type="ACCOUNT", parent_portfolio_id=f1["id"])
    r = client.get(f"/portfolios/{root['id']}/tree", headers=_h(maker))
    assert r.status_code == 200
    assert {n["id"] for n in r.json()} == {f1["id"], a1["id"]}


def test_list_filter_and_anchor_not_enforce(ctx) -> None:  # noqa: ANN001
    client, maker, viewer, _db = ctx
    root = _make(client, maker, "ROOT")
    _make(client, maker, "F1", node_type="FUND", parent_portfolio_id=root["id"])
    # node_type filter works:
    funds = client.get("/portfolios?node_type=FUND", headers=_h(maker)).json()
    assert [n["code"] for n in funds] == ["F1"]
    # anchor-not-enforce: the VIEWER (a different principal, no scope grant) sees ALL tenant nodes —
    # there is no portfolio-scope filtering in P1C-1.
    seen = client.get("/portfolios", headers=_h(viewer)).json()
    assert {n["code"] for n in seen} == {"ROOT", "F1"}
