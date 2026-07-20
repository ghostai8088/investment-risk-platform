"""End-to-end tests of the P3-1 risk (analytic sensitivities) endpoints.

SQLite has no RLS (tenant isolation + append-only-trigger proofs are in
``packages/shared-python/tests/test_sensitivity_pg.py``); here we prove entitlement gating
(deny-by-default, no DB side-effect on denial; view-only cannot run), the governed model
registration + build-in-request run + read round-trip, decimal serialization, the unregistered/
bad-input pre-create refusals (422), the post-create FAILED response (201 + status='FAILED' + zero
rows), and no PUT/PATCH/DELETE.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from irp_backend.api.risk import router as risk_router
from irp_backend.deps import get_db
from irp_shared.calc.models import CalculationRun
from irp_shared.db.session import make_engine, make_session_factory
from irp_shared.entitlement.bootstrap import SYSTEM_TENANT_ID
from irp_shared.entitlement.models import AppUser, Permission, Role, RolePermission, UserRole
from irp_shared.entitlement.service import Principal
from irp_shared.marketdata import CurveActor, CurveNode, capture_curve
from irp_shared.models import Base
from irp_shared.reference.models import Currency

_PERMS = ("risk.run", "risk.view", "model.inventory.register")
_T0 = datetime(2026, 1, 1, tzinfo=UTC)
_VA = datetime(2026, 6, 1, tzinfo=UTC)
_KA = datetime(2030, 1, 1, tzinfo=UTC)
_CD = date(2026, 6, 1)
_SRC = "VENDOR_X"


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
    db.add(Currency(tenant_id=SYSTEM_TENANT_ID, code="USD", name="USD", valid_from=_T0))
    db.flush()
    capture_curve(
        db,
        curve_type="SWAP",
        currency_code="USD",
        curve_date=_CD,
        curve_source=_SRC,
        nodes=[
            CurveNode(
                tenor_label="1Y",
                tenor_days=365,
                value_type="ZERO_RATE",
                point_value=Decimal("0.05"),
            ),
            CurveNode(
                tenor_label="2Y",
                tenor_days=730,
                value_type="ZERO_RATE",
                point_value=Decimal("0.06"),
            ),
        ],
        acting_tenant=tenant_id,
        actor=CurveActor(actor_id="a"),
        valid_from=_T0,
    )
    db.commit()
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


def _selector(curve_type: str = "SWAP", source: str = _SRC, reference_key: str = "NONE") -> dict:
    return {
        "curve_type": curve_type,
        "currency_code": "USD",
        "curve_date": _CD.isoformat(),
        "curve_source": source,
        "reference_key": reference_key,
    }


def _register(client: TestClient, p: Principal) -> str:
    resp = client.post("/risk/models/sensitivity", json={"code_version": "risk-v1"}, headers=_h(p))
    assert resp.status_code == 201, resp.text
    return resp.json()["model_version_id"]


def _run_body(mv: str, **kw) -> dict:  # noqa: ANN003
    return {
        "code_version": "risk-v1",
        "environment_id": "ci",
        "model_version_id": mv,
        "curve_selectors": [_selector()],
        "as_of_valid_at": _VA.isoformat(),
        "as_of_known_at": _KA.isoformat(),
        **kw,
    }


def test_register_run_and_read_roundtrip(ctx) -> None:  # noqa: ANN001
    client, p, _db = ctx
    mv = _register(client, p)
    resp = client.post("/risk/sensitivities/runs", json=_run_body(mv), headers=_h(p))
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["status"] == "COMPLETED"
    assert body["model_version_id"] == mv
    assert len(body["rows"]) == 2
    assert {r["sensitivity_type"] for r in body["rows"]} == {"DV01"}
    assert Decimal(body["rows"][0]["sensitivity_value"])  # numeric-stable string

    run_id = body["run_id"]
    get_run = client.get(f"/risk/sensitivities/runs/{run_id}", headers=_h(p))
    assert get_run.status_code == 200
    assert len(get_run.json()["rows"]) == 2

    one_id = body["rows"][0]["id"]
    get_one = client.get(f"/risk/sensitivities/{one_id}", headers=_h(p))
    assert get_one.status_code == 200
    assert get_one.json()["model_version_id"] == mv


def test_api1_sensitivities_latest_and_by_id_parity(ctx) -> None:  # noqa: ANN001
    """API-1 (Class B): ``GET /risk/sensitivities/latest`` returns the newest COMPLETED run's rows
    (each pinned with ``calculation_run_id``), optionally row-filtered to a ``curve_id``; the
    literal ``/latest`` is NOT shadowed by ``/{sensitivity_id}``. Also proves the two API-1 by-id
    PARITY reads (``/risk/scenario-results/{id}`` + ``/risk/proxy-weight-estimates/{id}``) exist and
    404 on an unknown id (never a 500); ``/scenario-results/latest`` resolves silent-empty here."""
    client, p, _db = ctx
    # Empty BEFORE any run — the literal /latest route resolves to [] (not a UUID-parse 422).
    assert client.get("/risk/sensitivities/latest", headers=_h(p)).json() == []
    mv = _register(client, p)
    body = client.post("/risk/sensitivities/runs", json=_run_body(mv), headers=_h(p)).json()
    run_id = body["run_id"]
    latest = client.get("/risk/sensitivities/latest", headers=_h(p))
    assert latest.status_code == 200
    rows = latest.json()
    assert len(rows) == 2 and all(r["calculation_run_id"] == run_id for r in rows)
    # curve_id row-filter: the run's own curve returns its rows; a foreign curve is silent-empty.
    curve_id = rows[0]["curve_id"]
    assert (
        len(
            client.get(
                "/risk/sensitivities/latest", params={"curve_id": curve_id}, headers=_h(p)
            ).json()
        )
        == 2
    )
    assert (
        client.get(
            "/risk/sensitivities/latest", params={"curve_id": str(uuid.uuid4())}, headers=_h(p)
        ).json()
        == []
    )
    # The two by-id PARITY reads: 404 on an unknown id (route exists; never a 500).
    assert client.get(f"/risk/scenario-results/{uuid.uuid4()}", headers=_h(p)).status_code == 404
    assert (
        client.get(f"/risk/proxy-weight-estimates/{uuid.uuid4()}", headers=_h(p)).status_code == 404
    )
    # /scenario-results/latest resolves silent-empty (no scenario run in this fixture).
    sc = client.get("/risk/scenario-results/latest", headers=_h(p))
    assert sc.status_code == 200 and sc.json() == []
    # Deny-by-default across the new reads.
    stranger = {"X-User-Id": str(uuid.uuid4()), "X-Tenant-Id": p.tenant_id}
    assert client.get("/risk/sensitivities/latest", headers=stranger).status_code == 403
    assert (
        client.get(f"/risk/proxy-weight-estimates/{uuid.uuid4()}", headers=stranger).status_code
        == 403
    )


def test_deny_by_default_no_side_effect(ctx) -> None:  # noqa: ANN001
    client, p, db = ctx
    mv = _register(client, p)
    before = db.execute(select(func.count()).select_from(CalculationRun)).scalar_one()
    no_perm = {"X-User-Id": str(uuid.uuid4()), "X-Tenant-Id": p.tenant_id}
    resp = client.post("/risk/sensitivities/runs", json=_run_body(mv), headers=no_perm)
    assert resp.status_code == 403
    after = db.execute(select(func.count()).select_from(CalculationRun)).scalar_one()
    assert after == before  # no run created on a denied request


def test_view_only_user_cannot_run(ctx) -> None:  # noqa: ANN001
    client, p, db = ctx
    mv = _register(client, p)
    tenant = p.tenant_id
    viewer = AppUser(tenant_id=tenant, display_name="V")
    role = Role(tenant_id=tenant, code="vr", name="VR")
    db.add_all([viewer, role])
    db.flush()
    perm = db.execute(select(Permission).where(Permission.code == "risk.view")).scalar_one()
    db.add(RolePermission(role_id=role.id, permission_id=perm.id))
    db.add(UserRole(tenant_id=tenant, user_id=viewer.id, role_id=role.id))
    db.commit()
    headers = {"X-User-Id": viewer.id, "X-Tenant-Id": tenant}
    assert (
        client.post("/risk/sensitivities/runs", json=_run_body(mv), headers=headers).status_code
        == 403
    )


def test_pre_create_refusal_bad_input_422(ctx) -> None:  # noqa: ANN001
    client, p, db = ctx
    mv = _register(client, p)
    resp = client.post(
        "/risk/sensitivities/runs", json=_run_body(mv, code_version=""), headers=_h(p)
    )
    assert resp.status_code == 422
    assert db.execute(select(func.count()).select_from(CalculationRun)).scalar_one() == 0


def test_unregistered_model_version_422(ctx) -> None:  # noqa: ANN001
    client, p, db = ctx
    resp = client.post("/risk/sensitivities/runs", json=_run_body(str(uuid.uuid4())), headers=_h(p))
    assert resp.status_code == 422
    assert db.execute(select(func.count()).select_from(CalculationRun)).scalar_one() == 0


def test_missing_curve_409(ctx) -> None:  # noqa: ANN001
    client, p, _db = ctx
    mv = _register(client, p)
    # A selector for a curve that does not exist as-of -> 409.
    resp = client.post(
        "/risk/sensitivities/runs",
        json=_run_body(mv, curve_selectors=[_selector(source="MISSING_SRC")]),
        headers=_h(p),
    )
    assert resp.status_code == 409


def test_post_create_failed_returns_201_failed(ctx) -> None:  # noqa: ANN001
    client, p, db = ctx
    mv = _register(client, p)
    # Capture a PAR_RATE-only curve (no usable node) -> post-create FAILED.
    capture_curve(
        db,
        curve_type="GOVT",
        currency_code="USD",
        curve_date=_CD,
        curve_source=_SRC,
        nodes=[
            CurveNode(
                tenor_label="1Y", tenor_days=365, value_type="PAR_RATE", point_value=Decimal("0.05")
            )
        ],
        acting_tenant=p.tenant_id,
        actor=CurveActor(actor_id="a"),
        valid_from=_T0,
    )
    db.commit()
    resp = client.post(
        "/risk/sensitivities/runs",
        json=_run_body(mv, curve_selectors=[_selector(curve_type="GOVT")]),
        headers=_h(p),
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "FAILED"
    assert body["rows"] == []
    assert body["failure_reason"]
    # The committed FAILED run is READABLE (200, status='FAILED') — durable refusal evidence.
    got = client.get(f"/risk/sensitivities/runs/{body['run_id']}", headers=_h(p))
    assert got.status_code == 200
    assert got.json()["status"] == "FAILED"
    # P3-C1: the persisted reason SURFACES on read (previously hardcoded None).
    assert got.json()["failure_reason"] == body["failure_reason"]


def test_no_mutating_verbs(ctx) -> None:  # noqa: ANN001
    client, p, _db = ctx
    rid = str(uuid.uuid4())
    assert client.put(f"/risk/sensitivities/{rid}", json={}, headers=_h(p)).status_code == 405
    assert client.delete(f"/risk/sensitivities/{rid}", headers=_h(p)).status_code == 405
