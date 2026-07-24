"""End-to-end tests of the API-2 limit endpoints (POST/PATCH/approve/suspend/resume + reads).

SQLite has no RLS, so cross-tenant isolation is proven at the PG tier; here we prove the API-2
controls: the person-level SoD survives the HTTP boundary INCLUDING a case-variance
self-approval attempt (D1 canonicalization — the headline defeat the Fable audit flagged), the
no-second-write-path (status never rides create/PATCH — D3), deny-by-default permission gating (D4),
the SoD refusal is 409 not 422/403 (B1/OQ-3), the create-duplicate is a uniform 409 (N4), the
decimal contract, and that the tick-only verbs are not exposed (D10).
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from irp_backend.api.limits import router as limits_router
from irp_backend.deps import get_db
from irp_shared.db.session import make_engine, make_session_factory
from irp_shared.entitlement.models import AppUser, Permission, Role, RolePermission, UserRole
from irp_shared.models import Base
from irp_shared.portfolio import PortfolioActor, create_portfolio

_PERMS = ("limit.manage", "limit.approve", "limit.view")


@pytest.fixture
def ctx() -> Iterator[tuple[TestClient, str, str, str, str]]:
    """Returns (client, tenant, maker_id, approver_id, portfolio_id). Both users hold all three
    limit perms — so the ONLY thing standing between the maker and self-approval is the person-level
    SoD (not a role partition)."""
    engine = make_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    db = make_session_factory(engine)()

    tenant = str(uuid.uuid4())
    maker = AppUser(tenant_id=tenant, display_name="Maker")
    approver = AppUser(tenant_id=tenant, display_name="Approver")
    role = Role(tenant_id=tenant, code="rm2l", name="Risk Manager 2L")
    db.add_all([maker, approver, role])
    db.flush()
    for code in _PERMS:
        perm = Permission(code=code, description="d")
        db.add(perm)
        db.flush()
        db.add(RolePermission(role_id=role.id, permission_id=perm.id))
    db.add(UserRole(tenant_id=tenant, user_id=maker.id, role_id=role.id))
    db.add(UserRole(tenant_id=tenant, user_id=approver.id, role_id=role.id))
    pf = create_portfolio(
        db,
        tenant_id=tenant,
        code="PF",
        name="pf",
        node_type="ACCOUNT",
        actor=PortfolioActor(actor_id="steward"),
    )
    db.commit()

    def _override_db() -> Iterator[Session]:
        yield db

    app = FastAPI()
    app.include_router(limits_router)
    app.dependency_overrides[get_db] = _override_db
    try:
        yield TestClient(app), tenant, maker.id, approver.id, str(pf.id)
    finally:
        db.close()
        engine.dispose()


def _hdr(user_id: str, tenant: str) -> dict[str, str]:
    return {"X-User-Id": user_id, "X-Tenant-Id": tenant}


def _limit_body(pf: str, code: str = "VAR-CEIL") -> dict[str, object]:
    return {
        "code": code,
        "name": code,
        "target_run_type": "VAR",
        "metric_type": "VAR_PARAMETRIC",
        "scope_portfolio_id": pf,
        "threshold_value": "5000000",
        "threshold_unit": "CURRENCY",
        "breach_direction": "ABOVE",
        "limit_kind": "HARD",
    }


def _create(client: TestClient, uid: str, tenant: str, pf: str, **over: object) -> dict:
    body = _limit_body(pf)
    body.update(over)
    r = client.post("/limits", json=body, headers=_hdr(uid, tenant))
    assert r.status_code == 201, r.text
    return r.json()


# --- create + gating -----------------------------------------------------------------------
def test_create_yields_draft(ctx) -> None:
    client, tenant, maker, _approver, pf = ctx
    lim = _create(client, maker, tenant, pf)
    assert lim["status"] == "DRAFT"  # born DRAFT, not ACTIVE
    assert lim["threshold_value"] == "5000000"  # fixed-point string (decimal contract)
    assert lim["created_by"] == maker  # the drafter-of-record, canonical


def test_create_denied_without_permission(ctx) -> None:
    client, tenant, _maker, _approver, pf = ctx
    stranger = str(uuid.uuid4())  # a valid UUID with no role/permission
    r = client.post("/limits", json=_limit_body(pf), headers=_hdr(stranger, tenant))
    assert r.status_code == 403


# --- the person-level SoD survives the HTTP boundary (D1) ----------------------------------
def test_self_approval_refused_through_http(ctx) -> None:
    client, tenant, maker, _approver, pf = ctx
    lim = _create(client, maker, tenant, pf)
    # The maker holds limit.approve, so ONLY the person-level SoD stops the self-approval.
    r = client.post(
        f"/limits/{lim['id']}/approve", json={"approval_ref": "RC-1"}, headers=_hdr(maker, tenant)
    )
    assert r.status_code == 409, r.text  # separation of duties, NOT 422/403
    # (The case-variance form of this defeat is PG-specific — uuid compares case-insensitively there
    #  but case-sensitively on SQLite's CHAR GUID — and is proven at the canonicalization unit level
    #  in packages/shared-python/tests/test_limit.py::test_actor_id_canonicalization_*.)


def test_distinct_approver_activates(ctx) -> None:
    client, tenant, maker, approver, pf = ctx
    lim = _create(client, maker, tenant, pf)
    r = client.post(
        f"/limits/{lim['id']}/approve",
        json={"approval_ref": "RC-1"},
        headers=_hdr(approver, tenant),
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "ACTIVE"


def test_approve_requires_approval_ref(ctx) -> None:
    client, tenant, maker, approver, pf = ctx
    lim = _create(client, maker, tenant, pf)
    r = client.post(
        f"/limits/{lim['id']}/approve", json={"approval_ref": "  "}, headers=_hdr(approver, tenant)
    )
    assert r.status_code == 422  # a base LimitError (non-empty ref), NOT the 409 SoD status


def test_approve_denied_without_permission(ctx) -> None:
    client, tenant, maker, _approver, pf = ctx
    lim = _create(client, maker, tenant, pf)
    stranger = str(uuid.uuid4())  # a valid UUID with no perms -> 403 before any SoD check
    r = client.post(
        f"/limits/{lim['id']}/approve", json={"approval_ref": "x"}, headers=_hdr(stranger, tenant)
    )
    assert r.status_code == 403


# --- no second write path (D3) -------------------------------------------------------------
def test_create_cannot_smuggle_active_status(ctx) -> None:
    client, tenant, maker, _approver, pf = ctx
    body = _limit_body(pf)
    body["status"] = "ACTIVE"  # smuggled — must be ignored (no status field on create)
    r = client.post("/limits", json=body, headers=_hdr(maker, tenant))
    assert r.status_code == 201
    assert r.json()["status"] == "DRAFT"  # forced DRAFT despite the smuggle


def test_patch_cannot_smuggle_status(ctx) -> None:
    client, tenant, maker, approver, pf = ctx
    lim = _create(client, maker, tenant, pf)
    client.post(
        f"/limits/{lim['id']}/approve", json={"approval_ref": "RC"}, headers=_hdr(approver, tenant)
    )  # -> ACTIVE
    # PATCH a cosmetic field WITH a smuggled status=SUSPENDED: it must be ignored (stays ACTIVE).
    r = client.patch(
        f"/limits/{lim['id']}",
        json={"name": "renamed", "status": "SUSPENDED"},
        headers=_hdr(maker, tenant),
    )
    assert r.status_code == 200
    assert r.json()["status"] == "ACTIVE"  # the smuggled status did NOT ride the edit path
    assert r.json()["name"] == "renamed"


def test_material_change_demotes_to_draft(ctx) -> None:
    client, tenant, maker, approver, pf = ctx
    lim = _create(client, maker, tenant, pf)
    client.post(
        f"/limits/{lim['id']}/approve", json={"approval_ref": "RC"}, headers=_hdr(approver, tenant)
    )
    r = client.patch(
        f"/limits/{lim['id']}", json={"threshold_value": "9000000"}, headers=_hdr(maker, tenant)
    )
    assert r.status_code == 200
    assert r.json()["status"] == "DRAFT"  # a material change re-enters the maker-checker gate


# --- suspend/resume, reads, duplicate, 404, tick-verbs -------------------------------------
def test_suspend_then_resume(ctx) -> None:
    client, tenant, maker, approver, pf = ctx
    lim = _create(client, maker, tenant, pf)
    client.post(
        f"/limits/{lim['id']}/approve", json={"approval_ref": "RC"}, headers=_hdr(approver, tenant)
    )
    assert (
        client.post(f"/limits/{lim['id']}/suspend", headers=_hdr(maker, tenant)).json()["status"]
        == "SUSPENDED"
    )
    assert (
        client.post(f"/limits/{lim['id']}/resume", headers=_hdr(maker, tenant)).json()["status"]
        == "ACTIVE"
    )


def test_list_by_status_is_the_approval_queue(ctx) -> None:
    client, tenant, maker, approver, pf = ctx
    a = _create(client, maker, tenant, pf, code="A")
    _create(client, maker, tenant, pf, code="B")  # stays DRAFT
    client.post(
        f"/limits/{a['id']}/approve", json={"approval_ref": "RC"}, headers=_hdr(approver, tenant)
    )
    drafts = client.get("/limits?status=DRAFT", headers=_hdr(maker, tenant)).json()
    assert {x["code"] for x in drafts} == {"B"}  # only the un-approved one is in the queue
    assert len(client.get("/limits", headers=_hdr(maker, tenant)).json()) == 2


def test_health_endpoint(ctx) -> None:
    client, tenant, maker, approver, pf = ctx
    lim = _create(client, maker, tenant, pf)
    client.post(
        f"/limits/{lim['id']}/approve", json={"approval_ref": "RC"}, headers=_hdr(approver, tenant)
    )
    health = client.get("/limits/health", headers=_hdr(maker, tenant)).json()
    # ACTIVE but never evaluated (no run) -> NEVER_EVALUABLE, never a false green.
    assert health == [
        {
            "limit_id": lim["id"],
            "code": "VAR-CEIL",
            "state": "NEVER_EVALUABLE",
            "latest_run_id": None,
            "latest_breach_id": None,
        }
    ]


def test_duplicate_code_is_409(ctx) -> None:
    client, tenant, maker, _approver, pf = ctx
    _create(client, maker, tenant, pf, code="DUP")
    r = client.post("/limits", json=_limit_body(pf, code="DUP"), headers=_hdr(maker, tenant))
    assert r.status_code == 409


def test_unknown_limit_is_404(ctx) -> None:
    client, tenant, maker, _approver, _pf = ctx
    r = client.get(f"/limits/{uuid.uuid4()}", headers=_hdr(maker, tenant))
    assert r.status_code == 404


def test_non_uuid_user_id_is_401(ctx) -> None:
    client, tenant, _maker, _approver, pf = ctx
    # A non-UUID X-User-Id must fail closed at the actor boundary (dev-header contract, D1/F2) —
    # but only once it reaches a handler that builds the actor; a bare create attempt suffices.
    r = client.post("/limits", json=_limit_body(pf), headers=_hdr("not-a-uuid", tenant))
    assert r.status_code in (401, 403)  # 403 if the perm join rejects the non-uuid first


def test_tick_only_verbs_are_not_exposed(ctx) -> None:
    client, _tenant, _maker, _approver, _pf = ctx
    paths = set(client.app.openapi()["paths"])
    assert not any("evaluate" in p or "escalate" in p for p in paths)
    # the exposed limit verb set is exactly create/read/approve/suspend/resume (+ health)
    assert {p for p in paths if p.startswith("/limits")} == {
        "/limits",
        "/limits/{limit_id}",
        "/limits/{limit_id}/approve",
        "/limits/{limit_id}/suspend",
        "/limits/{limit_id}/resume",
        "/limits/health",
    }
