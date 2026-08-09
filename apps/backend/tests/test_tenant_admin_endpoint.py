"""ONBOARD-1b at the wire — the four-eyes flow, the orphan refusal, and tenant-locality.

The service tests prove the invariants; these prove the SURFACE honors them: that the route layer
does not commit a refused act, does not leak another tenant's roster, and reports the four-eyes
outcome in a form a caller can act on.

The tenant-locality tests matter more than they look. No route here takes a ``{tenant_id}``
parameter — the principal's tenant IS the scope — so the thing worth proving is that a second
tenant's admin, hitting the same URLs, sees and touches only their own.
"""

from __future__ import annotations

import os
import uuid
import warnings

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

os.environ.setdefault("IRP_AUTH_MODE", "dev_header")
os.environ.setdefault("IRP_APP_ENV", "local")

from irp_shared.db.base import Base  # noqa: E402
from irp_shared.db.session import make_engine, make_session_factory  # noqa: E402
from irp_shared.entitlement.bootstrap import (  # noqa: E402
    PERMISSIONS,
    permission_id,
)
from irp_shared.entitlement.models import (  # noqa: E402
    AppUser,
    Permission,
    Role,
    RolePermission,
    UserRole,
)
from irp_shared.tenancy.models import Tenant  # noqa: E402
from irp_shared.tenancy.service import FIRST_ADMIN_ROLE  # noqa: E402

with warnings.catch_warnings():
    warnings.simplefilter("ignore")
    from irp_backend.main import app


@pytest.fixture
def wired():  # noqa: ANN201
    from irp_backend.deps import get_db

    engine = make_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    db = make_session_factory(engine)()
    for code, desc in PERMISSIONS:
        db.add(Permission(id=permission_id(code), code=code, description=desc))
    db.flush()
    app.dependency_overrides[get_db] = lambda: db
    try:
        yield TestClient(app), db
    finally:
        app.dependency_overrides.pop(get_db, None)
        db.close()
        engine.dispose()


def _tenant_with_admin(db: Session, code: str) -> tuple[str, str, str]:
    """A registered tenant, its tenant_admin role (with the four verbs), and one admin."""
    tid = str(uuid.uuid4())
    db.add(Tenant(id=tid, code=code, display_name=code, status="ACTIVE", provenance="ONBOARDED"))
    role = Role(id=str(uuid.uuid4()), tenant_id=tid, code=FIRST_ADMIN_ROLE, name="Tenant Admin")
    db.add(role)
    db.add(Role(id=str(uuid.uuid4()), tenant_id=tid, code="risk_analyst_1l", name="Analyst"))
    db.flush()
    for verb in ("user.manage", "role.assign", "user.view", "role.approve"):
        db.add(
            RolePermission(id=str(uuid.uuid4()), role_id=role.id, permission_id=permission_id(verb))
        )
    admin = AppUser(
        id=str(uuid.uuid4()),
        tenant_id=tid,
        external_subject=f"admin@{code}",
        display_name="Admin",
        is_active=True,
    )
    db.add(admin)
    db.flush()
    db.add(UserRole(id=str(uuid.uuid4()), tenant_id=tid, user_id=admin.id, role_id=role.id))
    db.flush()
    return tid, role.id, admin.id


def _add_admin(db: Session, tid: str, role_id: str, label: str) -> str:
    user = AppUser(
        id=str(uuid.uuid4()),
        tenant_id=tid,
        external_subject=f"{label}@{tid[:8]}",
        display_name=label,
        is_active=True,
    )
    db.add(user)
    db.flush()
    db.add(UserRole(id=str(uuid.uuid4()), tenant_id=tid, user_id=user.id, role_id=role_id))
    db.flush()
    return user.id


def _h(uid: str, tid: str) -> dict[str, str]:
    return {"X-User-Id": uid, "X-Tenant-Id": tid}


def test_a_lone_admin_creates_a_user_and_grants_DIRECTLY(wired) -> None:  # noqa: ANN001
    client, db = wired
    tid, role_id, admin = _tenant_with_admin(db, "acme")
    analyst = db.execute(
        select(Role.id).where(Role.tenant_id == tid, Role.code == "risk_analyst_1l")
    ).scalar_one()
    db.commit()

    created = client.post(
        "/users",
        json={"external_subject": "new@acme", "display_name": "New Joiner"},
        headers=_h(admin, tid),
    )
    assert created.status_code == 201, created.text
    uid = created.json()["id"]

    granted = client.post(
        f"/users/{uid}/roles", json={"role_id": str(analyst)}, headers=_h(admin, tid)
    )
    assert granted.status_code == 200, granted.text
    body = granted.json()
    assert body["status"] == "DIRECT" and body["direct"] is True

    roster = client.get("/users", headers=_h(admin, tid)).json()
    assert {r["id"]: r["roles"] for r in roster}[uid] == ["risk_analyst_1l"]


def test_with_a_SECOND_admin_the_grant_is_PENDING_until_approved(wired) -> None:  # noqa: ANN001
    """The four-eyes flow end to end at the wire, with its discriminating halves."""
    client, db = wired
    tid, role_id, first = _tenant_with_admin(db, "acme")
    second = _add_admin(db, tid, role_id, "second")
    analyst = db.execute(
        select(Role.id).where(Role.tenant_id == tid, Role.code == "risk_analyst_1l")
    ).scalar_one()
    db.commit()

    uid = client.post(
        "/users",
        json={"external_subject": "n@acme", "display_name": "N"},
        headers=_h(first, tid),
    ).json()["id"]
    req = client.post(
        f"/users/{uid}/roles", json={"role_id": str(analyst)}, headers=_h(first, tid)
    ).json()
    assert req["status"] == "PENDING" and req["direct"] is False

    # NOT yet effective — the half that makes PENDING mean something.
    roster = client.get("/users", headers=_h(first, tid)).json()
    assert {r["id"]: r["roles"] for r in roster}[uid] == []

    # The requester cannot approve their own request.
    self_approve = client.post(f"/entitlement-requests/{req['id']}/approve", headers=_h(first, tid))
    assert self_approve.status_code == 422, self_approve.text

    # The second admin can, and then it IS effective.
    ok = client.post(f"/entitlement-requests/{req['id']}/approve", headers=_h(second, tid))
    assert ok.status_code == 200, ok.text
    assert ok.json()["status"] == "APPROVED"
    roster = client.get("/users", headers=_h(first, tid)).json()
    assert {r["id"]: r["roles"] for r in roster}[uid] == ["risk_analyst_1l"]


def test_the_pending_queue_is_visible_and_empties_on_approval(wired) -> None:  # noqa: ANN001
    client, db = wired
    tid, role_id, first = _tenant_with_admin(db, "acme")
    second = _add_admin(db, tid, role_id, "second")
    analyst = db.execute(
        select(Role.id).where(Role.tenant_id == tid, Role.code == "risk_analyst_1l")
    ).scalar_one()
    db.commit()
    uid = client.post(
        "/users", json={"external_subject": "q@acme", "display_name": "Q"}, headers=_h(first, tid)
    ).json()["id"]
    req = client.post(
        f"/users/{uid}/roles", json={"role_id": str(analyst)}, headers=_h(first, tid)
    ).json()

    queue = client.get("/entitlement-requests", headers=_h(second, tid)).json()
    assert [q["id"] for q in queue] == [req["id"]]
    client.post(f"/entitlement-requests/{req['id']}/approve", headers=_h(second, tid))
    assert client.get("/entitlement-requests", headers=_h(second, tid)).json() == []


def test_revoking_the_LAST_admin_is_422_with_nothing_changed(wired) -> None:  # noqa: ANN001
    client, db = wired
    tid, role_id, admin = _tenant_with_admin(db, "acme")
    db.commit()

    resp = client.delete(f"/users/{admin}/roles/{role_id}", headers=_h(admin, tid))
    assert resp.status_code == 422, resp.text
    assert "no active administrator" in resp.text
    # Still an admin: the refusal did not half-apply.
    assert client.get("/users", headers=_h(admin, tid)).status_code == 200


def test_deactivating_the_LAST_admin_is_422(wired) -> None:  # noqa: ANN001
    client, db = wired
    tid, _role, admin = _tenant_with_admin(db, "acme")
    db.commit()
    resp = client.post(f"/users/{admin}/deactivate", headers=_h(admin, tid))
    assert resp.status_code == 422, resp.text
    assert client.get("/users", headers=_h(admin, tid)).status_code == 200


def test_an_admin_sees_and_touches_ONLY_their_own_tenant(wired) -> None:  # noqa: ANN001
    """Tenant-locality, proven with a real second tenant rather than asserted by design."""
    client, db = wired
    tid_a, _ra, admin_a = _tenant_with_admin(db, "acme")
    tid_b, role_b, admin_b = _tenant_with_admin(db, "beta")
    db.commit()

    roster_a = client.get("/users", headers=_h(admin_a, tid_a)).json()
    assert {r["id"] for r in roster_a} == {admin_a}, "tenant A saw a foreign user"

    # A's admin cannot deactivate B's admin — the target lookup is tenant-scoped.
    resp = client.post(f"/users/{admin_b}/deactivate", headers=_h(admin_a, tid_a))
    assert resp.status_code == 422
    assert "not found in this tenant" in resp.text


def test_a_user_without_the_verbs_is_403(wired) -> None:  # noqa: ANN001
    """Deny-by-default: the roster is not readable by an ordinary tenant user."""
    client, db = wired
    tid, _role, _admin = _tenant_with_admin(db, "acme")
    plain = AppUser(
        id=str(uuid.uuid4()),
        tenant_id=tid,
        external_subject="plain@acme",
        display_name="Plain",
        is_active=True,
    )
    db.add(plain)
    db.commit()
    assert client.get("/users", headers=_h(plain.id, tid)).status_code == 403


def test_an_unexpected_field_is_REFUSED_not_ignored(wired) -> None:  # noqa: ANN001
    client, db = wired
    tid, _role, admin = _tenant_with_admin(db, "acme")
    db.commit()
    resp = client.post(
        "/users",
        json={"external_subject": "x@acme", "display_name": "X", "is_active": False},
        headers=_h(admin, tid),
    )
    assert resp.status_code == 422
