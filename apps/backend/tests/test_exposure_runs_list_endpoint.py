"""End-to-end tests of the P3-C2 exposure-run listing (``GET /exposure/runs``, OD-C).

SQLite has no RLS (PG proofs live in the PG suite); here we prove the endpoint's OWN tenant
predicate (two-tenant separation), the EXPOSURE_AGGREGATE fence (a risk run in the same table
NEVER appears — the permission-family separation), fail-closed filters (unknown status /
out-of-bounds page ⇒ 422), deterministic newest-first pagination, entitlement gating (403
without ``exposure.view``; 401 without a principal), ``failure_reason`` surfacing, and
read-only-ness (405 on mutation methods).
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from irp_backend.api.exposure import router as exposure_router
from irp_backend.deps import get_db
from irp_shared.calc.models import CalculationRun
from irp_shared.db.session import make_engine, make_session_factory
from irp_shared.entitlement.models import AppUser, Permission, Role, RolePermission, UserRole
from irp_shared.models import Base

_T0 = datetime(2026, 6, 1, tzinfo=UTC)


def _grant(db: Session, tenant_id: str, *perms: str) -> str:
    user = AppUser(tenant_id=tenant_id, display_name="U")
    role = Role(tenant_id=tenant_id, code=f"r-{uuid.uuid4().hex[:8]}", name="R")
    db.add_all([user, role])
    db.flush()
    for code in perms:
        perm = db.query(Permission).filter_by(code=code).one_or_none()
        if perm is None:
            perm = Permission(code=code, description="d")
            db.add(perm)
            db.flush()
        db.add(RolePermission(role_id=role.id, permission_id=perm.id))
    db.add(UserRole(tenant_id=tenant_id, user_id=user.id, role_id=role.id))
    db.flush()
    return str(user.id)


def _mint(
    db: Session,
    tenant_id: str,
    run_type: str,
    *,
    status: str = "COMPLETED",
    created_at: datetime = _T0,
    failure_reason: str | None = None,
) -> str:
    run = CalculationRun(
        tenant_id=tenant_id,
        run_type=run_type,
        status=status,
        initiated_by="seed",
        code_version="v1",
        environment_id="test",
        created_at=created_at,
        failure_reason=failure_reason,
    )
    db.add(run)
    db.flush()
    return str(run.run_id)


@pytest.fixture
def ctx() -> Iterator[tuple[TestClient, Session, str, str, str, str]]:
    engine = make_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    db = make_session_factory(engine)()
    tenant_a, tenant_b = str(uuid.uuid4()), str(uuid.uuid4())
    viewer_a = _grant(db, tenant_a, "exposure.view")
    viewer_b = _grant(db, tenant_b, "exposure.view")
    db.commit()

    app = FastAPI()
    app.include_router(exposure_router)
    app.dependency_overrides[get_db] = lambda: db
    client = TestClient(app)
    try:
        yield client, db, tenant_a, tenant_b, viewer_a, viewer_b
    finally:
        db.close()


def _hdr(user_id: str, tenant_id: str) -> dict[str, str]:
    return {"X-User-Id": user_id, "X-Tenant-Id": tenant_id}


def test_lists_only_own_tenant_exposure_runs(ctx) -> None:
    client, db, tenant_a, tenant_b, viewer_a, viewer_b = ctx
    ea1 = _mint(db, tenant_a, "EXPOSURE_AGGREGATE", created_at=_T0)
    ea2 = _mint(db, tenant_a, "EXPOSURE_AGGREGATE", created_at=_T0 + timedelta(minutes=1))
    _mint(db, tenant_a, "VAR")  # a RISK run — must NEVER appear (the permission-family fence)
    _mint(db, tenant_a, "SENSITIVITY")
    eb = _mint(db, tenant_b, "EXPOSURE_AGGREGATE")
    db.commit()

    body = client.get("/exposure/runs", headers=_hdr(viewer_a, tenant_a)).json()
    got = [i["run_id"] for i in body["items"]]
    assert got == [ea2, ea1]  # newest first; the two risk runs excluded
    assert (
        client.get("/exposure/runs", headers=_hdr(viewer_b, tenant_b)).json()["items"][0]["run_id"]
        == eb
    )


def test_status_filter_and_failure_reason(ctx) -> None:
    client, db, tenant_a, _tb, viewer_a, _vb = ctx
    ok = _mint(db, tenant_a, "EXPOSURE_AGGREGATE", status="COMPLETED")
    bad = _mint(
        db,
        tenant_a,
        "EXPOSURE_AGGREGATE",
        status="FAILED",
        created_at=_T0 + timedelta(minutes=1),
        failure_reason="rule 'x' failed (severity=ERROR)",
    )
    db.commit()
    failed = client.get(
        "/exposure/runs", params={"status": "FAILED"}, headers=_hdr(viewer_a, tenant_a)
    ).json()
    assert [i["run_id"] for i in failed["items"]] == [bad]
    assert failed["items"][0]["failure_reason"] == "rule 'x' failed (severity=ERROR)"
    all_runs = client.get("/exposure/runs", headers=_hdr(viewer_a, tenant_a)).json()
    assert {i["run_id"] for i in all_runs["items"]} == {ok, bad}


@pytest.mark.parametrize(
    "params", [{"status": "nope"}, {"limit": 0}, {"limit": 201}, {"offset": -1}]
)
def test_fail_closed_filters_422(ctx, params: dict[str, object]) -> None:
    client, db, tenant_a, _tb, viewer_a, _vb = ctx
    _mint(db, tenant_a, "EXPOSURE_AGGREGATE")
    db.commit()
    assert (
        client.get("/exposure/runs", params=params, headers=_hdr(viewer_a, tenant_a)).status_code
        == 422
    )


def test_entitlement_gating(ctx) -> None:
    client, db, tenant_a, _tb, _va, _vb = ctx
    # A user with risk.view but NOT exposure.view is denied (permission-family separation).
    risk_only = _grant(db, tenant_a, "risk.view")
    db.commit()
    assert client.get("/exposure/runs").status_code == 401  # no principal
    assert client.get("/exposure/runs", headers=_hdr(risk_only, tenant_a)).status_code == 403


def test_no_mutation_methods(ctx) -> None:
    client, _db, tenant_a, _tb, viewer_a, _vb = ctx
    for method in ("put", "patch", "delete"):
        assert (
            getattr(client, method)("/exposure/runs", headers=_hdr(viewer_a, tenant_a)).status_code
            == 405
        )
