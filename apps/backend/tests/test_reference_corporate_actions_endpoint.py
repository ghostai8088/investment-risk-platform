"""End-to-end tests of the P1B-4 corporate-action endpoints (capture-only).

SQLite has no RLS (isolation is proven in the PG file); here we prove entitlement gating
(deny-by-default), server-side tenant stamping, the create / amend / status-transition dispatch,
the lifecycle guard at the HTTP layer (illegal transition → 409; bad mode/new_status → 422),
the instrument filter, and 404/422 shapes.
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

from irp_backend.api.reference_corporate_actions import router as ca_router
from irp_backend.deps import get_db
from irp_shared.audit.models import AuditEvent
from irp_shared.db.session import make_engine, make_session_factory
from irp_shared.entitlement.models import AppUser, Permission, Role, RolePermission, UserRole
from irp_shared.entitlement.service import Principal
from irp_shared.models import Base
from irp_shared.reference.instrument import create_instrument
from irp_shared.reference.models import CorporateAction
from irp_shared.reference.service import ReferenceActor

_PERMS = ("reference.corporate_action.view", "reference.corporate_action.edit")


@pytest.fixture
def ctx() -> Iterator[tuple[TestClient, Principal, Session, str]]:
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
    # seed an instrument for the corporate_action FK (governed create, then commit).
    inst = create_instrument(
        db,
        tenant_id=tenant_id,
        code="BOND1",
        name="B",
        asset_class="BOND",
        actor=ReferenceActor(actor_id=user.id),
    )
    db.commit()
    principal = Principal(user_id=user.id, tenant_id=tenant_id)

    def _override_db() -> Iterator[Session]:
        yield db

    app = FastAPI()
    app.include_router(ca_router)
    app.dependency_overrides[get_db] = _override_db
    try:
        yield TestClient(app), principal, db, inst.id
    finally:
        db.close()
        engine.dispose()


def _h(p: Principal) -> dict[str, str]:
    return {"X-User-Id": p.user_id, "X-Tenant-Id": p.tenant_id}


def _no_perm(p: Principal) -> dict[str, str]:
    return {"X-User-Id": str(uuid.uuid4()), "X-Tenant-Id": p.tenant_id}


def _make_ca(client: TestClient, p: Principal, instr_id: str, code: str = "CA1", **kw) -> dict:  # noqa: ANN003
    body = {"code": code, "instrument_id": instr_id, "action_type": "DIVIDEND", **kw}
    r = client.post("/reference/corporate-actions", json=body, headers=_h(p))
    assert r.status_code == 201, r.text
    return r.json()


def test_create_201_stamps_tenant_and_audits(ctx) -> None:  # noqa: ANN001
    client, principal, db, instr_id = ctx
    out = _make_ca(client, principal, instr_id, ex_date="2026-03-01", effective_date="2026-03-15")
    assert out["status"] == "ANNOUNCED" and out["ex_date"] == "2026-03-01"
    ca = db.get(CorporateAction, out["id"])
    assert ca is not None and ca.tenant_id == principal.tenant_id
    n = db.execute(
        select(func.count()).select_from(AuditEvent).where(AuditEvent.entity_id == out["id"])
    ).scalar_one()
    assert n == 1


def test_create_denied_no_perm(ctx) -> None:  # noqa: ANN001
    client, principal, db, instr_id = ctx
    r = client.post(
        "/reference/corporate-actions",
        json={"code": "X", "instrument_id": instr_id, "action_type": "SPLIT"},
        headers=_no_perm(principal),
    )
    assert r.status_code == 403
    assert db.execute(select(func.count()).select_from(CorporateAction)).scalar_one() == 0


def test_create_unknown_instrument_404(ctx) -> None:  # noqa: ANN001
    client, principal, _, _ = ctx
    r = client.post(
        "/reference/corporate-actions",
        json={"code": "X", "instrument_id": str(uuid.uuid4()), "action_type": "SPLIT"},
        headers=_h(principal),
    )
    assert r.status_code == 404


def test_create_bad_initial_status_422(ctx) -> None:  # noqa: ANN001
    client, principal, db, instr_id = ctx
    r = client.post(
        "/reference/corporate-actions",
        json={"code": "X", "instrument_id": instr_id, "action_type": "SPLIT", "status": "BOGUS"},
        headers=_h(principal),
    )
    assert r.status_code == 422  # out-of-vocab initial status
    assert db.execute(select(func.count()).select_from(CorporateAction)).scalar_one() == 0


def test_get_404_and_422(ctx) -> None:  # noqa: ANN001
    client, principal, _, _ = ctx
    assert (
        client.get(
            f"/reference/corporate-actions/{uuid.uuid4()}", headers=_h(principal)
        ).status_code
        == 404
    )
    assert (
        client.get("/reference/corporate-actions/not-a-uuid", headers=_h(principal)).status_code
        == 422
    )


def test_amend_and_status_transition(ctx) -> None:  # noqa: ANN001
    client, principal, _, instr_id = ctx
    ca = _make_ca(client, principal, instr_id)
    cid = ca["id"]
    # amend
    r = client.post(
        f"/reference/corporate-actions/{cid}",
        json={"mode": "amend", "pay_date": "2026-03-20"},
        headers=_h(principal),
    )
    assert r.status_code == 200 and r.json()["pay_date"] == "2026-03-20"
    assert r.json()["record_version"] == 2 and r.json()["status"] == "ANNOUNCED"
    # status transition ANNOUNCED -> CONFIRMED
    r = client.post(
        f"/reference/corporate-actions/{cid}",
        json={"mode": "status", "new_status": "CONFIRMED", "reason": "ok"},
        headers=_h(principal),
    )
    assert r.status_code == 200 and r.json()["status"] == "CONFIRMED"


def test_illegal_transition_409(ctx) -> None:  # noqa: ANN001
    client, principal, _, instr_id = ctx
    ca = _make_ca(client, principal, instr_id, "CA_T")
    cid = ca["id"]
    # legal -> CANCELLED, then illegal CANCELLED -> CONFIRMED
    assert (
        client.post(
            f"/reference/corporate-actions/{cid}",
            json={"mode": "status", "new_status": "CANCELLED"},
            headers=_h(principal),
        ).status_code
        == 200
    )
    r = client.post(
        f"/reference/corporate-actions/{cid}",
        json={"mode": "status", "new_status": "CONFIRMED"},
        headers=_h(principal),
    )
    assert r.status_code == 409


def test_status_mode_missing_new_status_422_and_bad_mode_422(ctx) -> None:  # noqa: ANN001
    client, principal, _, instr_id = ctx
    ca = _make_ca(client, principal, instr_id, "CA_M")
    cid = ca["id"]
    assert (
        client.post(
            f"/reference/corporate-actions/{cid}", json={"mode": "status"}, headers=_h(principal)
        ).status_code
        == 422
    )
    assert (
        client.post(
            f"/reference/corporate-actions/{cid}", json={"mode": "bogus"}, headers=_h(principal)
        ).status_code
        == 422
    )


def test_list_and_instrument_filter(ctx) -> None:  # noqa: ANN001
    client, principal, _, instr_id = ctx
    _make_ca(client, principal, instr_id, "CA_A")
    _make_ca(client, principal, instr_id, "CA_B")
    r = client.get("/reference/corporate-actions", headers=_h(principal))
    assert r.status_code == 200 and len(r.json()) == 2
    r = client.get(
        "/reference/corporate-actions", params={"instrument_id": instr_id}, headers=_h(principal)
    )
    assert r.status_code == 200 and len(r.json()) == 2
    r = client.get(
        "/reference/corporate-actions",
        params={"instrument_id": str(uuid.uuid4())},
        headers=_h(principal),
    )
    assert r.status_code == 200 and r.json() == []
