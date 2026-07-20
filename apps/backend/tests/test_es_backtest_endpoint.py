"""BT-3 endpoint tier — the ES-backtest + Christoffersen-v2 registrar endpoints, the error-map
wiring, and deny-by-default. LIGHT fixture (entitlements only): the full run roundtrip is
covered at the unit tier (hand-minted end-to-ends in ``test_es_backtest.py``) and LIVE at demo
stage 7 on PG — this tier pins the HTTP contract (201/403/404/409/422 shapes)."""

from __future__ import annotations

import uuid
from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from irp_backend.api.risk import router as risk_router
from irp_backend.deps import get_db
from irp_shared.db.session import make_engine, make_session_factory
from irp_shared.entitlement.models import AppUser, Permission, Role, RolePermission, UserRole
from irp_shared.entitlement.service import Principal
from irp_shared.models import Base

_PERMS = ("model.inventory.register", "risk.run", "risk.view")


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
    db.flush()
    principal = Principal(user_id=user.id, tenant_id=tenant_id)

    def _override_db() -> Iterator[Session]:
        yield db

    app = FastAPI()
    app.include_router(risk_router)
    app.dependency_overrides[get_db] = _override_db
    try:
        yield TestClient(app), principal, db
    finally:
        db.close()
        engine.dispose()


def _h(p: Principal) -> dict[str, str]:
    return {"X-User-Id": p.user_id, "X-Tenant-Id": p.tenant_id}


def test_register_es_backtest_roundtrip_and_identity(ctx) -> None:  # noqa: ANN001
    client, p, db = ctx
    resp = client.post(
        "/risk/models/es-backtest",
        json={"code_version": "bt3-v1", "significance": "0.05"},
        headers=_h(p),
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["version_label"] == "v1" and body["status"] == "REGISTERED"
    # Idempotent same-declaration re-register resolves to the SAME version.
    again = client.post(
        "/risk/models/es-backtest",
        json={"code_version": "bt3-v1", "significance": "0.05"},
        headers=_h(p),
    )
    assert again.status_code == 201
    assert again.json()["model_version_id"] == body["model_version_id"]
    # Same-label different-declaration => governed 409.
    conflict = client.post(
        "/risk/models/es-backtest",
        json={"code_version": "bt3-v2", "significance": "0.05"},
        headers=_h(p),
    )
    assert conflict.status_code == 409
    # Off-vocabulary significance => the FIXED 422 detail (never a 500).
    bad = client.post(
        "/risk/models/es-backtest",
        json={"code_version": "bt3-v1", "significance": "0.10"},
        headers=_h(p),
    )
    assert bad.status_code == 422
    assert "0.0001" in bad.json()["detail"]


def test_register_christoffersen_v2_roundtrip(ctx) -> None:  # noqa: ANN001
    client, p, db = ctx
    resp = client.post(
        "/risk/models/var-backtest-christoffersen",
        json={"code_version": "bt3-v1"},
        headers=_h(p),
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["version_label"] == "v2-christoffersen"
    # The v1 registrar remains byte-preserved beside it (same model code, distinct label).
    v1 = client.post(
        "/risk/models/var-backtest",
        json={"code_version": "bt3-v1", "alpha": "0.05"},
        headers=_h(p),
    )
    assert v1.status_code == 201
    assert v1.json()["version_label"] == "v1"
    assert v1.json()["model_id"] == resp.json()["model_id"]  # ONE model code, two versions


def test_run_refusals_and_error_map_wiring(ctx) -> None:  # noqa: ANN001
    client, p, db = ctx
    mv = client.post(
        "/risk/models/es-backtest",
        json={"code_version": "bt3-v1"},
        headers=_h(p),
    ).json()["model_version_id"]
    # Ambiguous input (snapshot_id + build args) => the EsBacktestInputError 422 mapping.
    resp = client.post(
        "/risk/es-backtests/runs",
        json={
            "code_version": "bt3-v1",
            "environment_id": "ci",
            "model_version_id": mv,
            "snapshot_id": str(uuid.uuid4()),
            "var_run_ids": [str(uuid.uuid4())],
        },
        headers=_h(p),
    )
    assert resp.status_code == 422
    assert resp.json()["detail"] == "invalid es-backtest run input"
    # A model version of the WRONG code refuses through the shared seam (422 class).
    wrong = client.post(
        "/risk/models/var-backtest",
        json={"code_version": "bt3-v1", "alpha": "0.05"},
        headers=_h(p),
    ).json()["model_version_id"]
    resp2 = client.post(
        "/risk/es-backtests/runs",
        json={
            "code_version": "bt3-v1",
            "environment_id": "ci",
            "model_version_id": wrong,
            "portfolio_return_run_id": str(uuid.uuid4()),
            "var_run_ids": [str(uuid.uuid4())],
            "es_run_ids": [str(uuid.uuid4())],
        },
        headers=_h(p),
    )
    assert resp2.status_code in (404, 422)
    # Unknown run/result reads => 404, never a 500.
    assert (
        client.get(f"/risk/es-backtests/runs/{uuid.uuid4()}", headers=_h(p)).status_code == 404
    )
    assert client.get(f"/risk/es-backtests/{uuid.uuid4()}", headers=_h(p)).status_code == 404


def test_deny_by_default(ctx) -> None:  # noqa: ANN001
    client, p, db = ctx
    stranger = {"X-User-Id": str(uuid.uuid4()), "X-Tenant-Id": p.tenant_id}
    assert (
        client.post(
            "/risk/models/es-backtest", json={"code_version": "x"}, headers=stranger
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/risk/models/var-backtest-christoffersen",
            json={"code_version": "x"},
            headers=stranger,
        ).status_code
        == 403
    )
    assert (
        client.get(f"/risk/es-backtests/runs/{uuid.uuid4()}", headers=stranger).status_code == 403
    )


def test_no_mutating_verbs(ctx) -> None:  # noqa: ANN001
    client, p, db = ctx
    for url in (f"/risk/es-backtests/{uuid.uuid4()}", f"/risk/es-backtests/runs/{uuid.uuid4()}"):
        for method in ("put", "patch", "delete"):
            assert getattr(client, method)(url, headers=_h(p)).status_code == 405
