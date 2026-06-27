"""End-to-end tests of the P2-3 exposure endpoints.

SQLite has no RLS (tenant isolation + append-only-trigger proofs are in
``packages/shared-python/tests/test_exposure_pg.py``); here we prove entitlement gating
(deny-by-default, no DB side-effect on denial), the build-in-request run + read round-trip, decimal
serialization, the post-create FAILED response (201 + status='FAILED' + zero rows), pre-create
refusal mapping (422/404/409), and no PUT/PATCH/DELETE.
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

from irp_backend.api.exposure import router as exposure_router
from irp_backend.deps import get_db
from irp_shared.calc.models import CalculationRun
from irp_shared.db.session import make_engine, make_session_factory
from irp_shared.entitlement.bootstrap import SYSTEM_TENANT_ID
from irp_shared.entitlement.models import AppUser, Permission, Role, RolePermission, UserRole
from irp_shared.entitlement.service import Principal
from irp_shared.marketdata import FxRateActor, capture_fx_rate
from irp_shared.models import Base
from irp_shared.portfolio import PortfolioActor, create_portfolio
from irp_shared.position import create_position
from irp_shared.position.service import PositionActor
from irp_shared.reference.instrument import create_instrument
from irp_shared.reference.models import Currency
from irp_shared.reference.service import ReferenceActor
from irp_shared.valuation import create_valuation
from irp_shared.valuation.service import ValuationActor

_PERMS = ("exposure.aggregate.run", "exposure.view")
_VA = datetime(2026, 6, 1, tzinfo=UTC)
_VD = date(2026, 6, 1)


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
    for ccy in ("USD", "EUR"):
        db.add(Currency(tenant_id=SYSTEM_TENANT_ID, code=ccy, name=ccy, valid_from=_VA))
    db.flush()
    pf = create_portfolio(
        db,
        tenant_id=tenant_id,
        code="PF",
        name="pf",
        node_type="ACCOUNT",
        actor=PortfolioActor(actor_id="a"),
    )
    for n, (qty, mark, c) in enumerate([("100", "12.50", "USD"), ("-200", "7.00", "EUR")]):
        inst = create_instrument(
            db,
            tenant_id=tenant_id,
            code=f"I{n}",
            name="i",
            asset_class="BOND",
            actor=ReferenceActor(actor_id="a"),
        )
        create_position(
            db,
            portfolio_id=pf.id,
            instrument_id=inst.id,
            acting_tenant=tenant_id,
            actor=PositionActor(actor_id="a"),
            quantity=Decimal(qty),
            valid_from=_VA,
        )
        create_valuation(
            db,
            portfolio_id=pf.id,
            instrument_id=inst.id,
            valuation_date=_VD,
            acting_tenant=tenant_id,
            actor=ValuationActor(actor_id="a"),
            mark_value=Decimal(mark),
            currency_code=c,
            valid_from=_VA,
        )
    capture_fx_rate(
        db,
        base_currency="EUR",
        quote_currency="USD",
        rate_date=_VD,
        rate=Decimal("1.10"),
        acting_tenant=tenant_id,
        actor=FxRateActor(actor_id="a"),
        valid_from=_VA,
    )
    db.commit()
    principal = Principal(user_id=user.id, tenant_id=tenant_id)

    def _override_db() -> Iterator[Session]:
        yield db

    app = FastAPI()
    app.include_router(exposure_router)
    app.dependency_overrides[get_db] = _override_db
    try:
        yield TestClient(app), principal, db, pf.id
    finally:
        db.close()
        engine.dispose()


def _h(p: Principal) -> dict[str, str]:
    return {"X-User-Id": p.user_id, "X-Tenant-Id": p.tenant_id}


def _no_perm(p: Principal) -> dict[str, str]:
    return {"X-User-Id": str(uuid.uuid4()), "X-Tenant-Id": p.tenant_id}


def _run_body(pf: str, **kw) -> dict:  # noqa: ANN003
    return {
        "code_version": "v1",
        "environment_id": "ci",
        "portfolio_id": pf,
        "as_of_valid_at": _VA.isoformat(),
        "base_currency": "USD",
        **kw,
    }


def test_run_and_read_roundtrip(ctx) -> None:  # noqa: ANN001
    client, p, _db, pf = ctx
    resp = client.post("/exposure/runs", json=_run_body(pf), headers=_h(p))
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["status"] == "COMPLETED"
    assert len(body["rows"]) == 2
    total = sum(Decimal(r["exposure_amount"]) for r in body["rows"])
    assert total == Decimal("-290.000000")
    # decimal serialization is numeric-stable strings.
    assert all(Decimal(r["fx_rate"]) for r in body["rows"] if r["mark_currency"] != "USD")

    run_id = body["run_id"]
    get_run = client.get(f"/exposure/runs/{run_id}", headers=_h(p))
    assert get_run.status_code == 200
    assert len(get_run.json()["rows"]) == 2

    one_id = body["rows"][0]["id"]
    get_one = client.get(f"/exposure/{one_id}", headers=_h(p))
    assert get_one.status_code == 200
    assert get_one.json()["exposure_type"] == "MARKET_VALUE"


def test_deny_by_default_no_side_effect(ctx) -> None:  # noqa: ANN001
    client, p, db, pf = ctx
    before = db.execute(select(func.count()).select_from(CalculationRun)).scalar_one()
    resp = client.post("/exposure/runs", json=_run_body(pf), headers=_no_perm(p))
    assert resp.status_code == 403
    after = db.execute(select(func.count()).select_from(CalculationRun)).scalar_one()
    assert after == before  # no run created on a denied request


def test_pre_create_refusal_bad_input_422(ctx) -> None:  # noqa: ANN001
    client, p, db, pf = ctx
    # Missing code_version -> ExposureInputError -> 422; no run created.
    resp = client.post("/exposure/runs", json=_run_body(pf, code_version=""), headers=_h(p))
    assert resp.status_code == 422
    assert db.execute(select(func.count()).select_from(CalculationRun)).scalar_one() == 0


def test_unknown_portfolio_404(ctx) -> None:  # noqa: ANN001
    client, p, _db, _pf = ctx
    resp = client.post("/exposure/runs", json=_run_body(str(uuid.uuid4())), headers=_h(p))
    assert resp.status_code == 404


def test_post_create_failed_returns_201_failed(ctx) -> None:  # noqa: ANN001
    client, p, _db, pf = ctx
    # Build a USD snapshot, then consume it requesting JPY (no JPY legs) -> FAILED.
    built = client.post("/exposure/runs", json=_run_body(pf), headers=_h(p)).json()
    snap_id = built["input_snapshot_id"]
    resp = client.post(
        "/exposure/runs",
        json={
            "code_version": "v1",
            "environment_id": "ci",
            "snapshot_id": snap_id,
            "base_currency": "JPY",
        },
        headers=_h(p),
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "FAILED"
    assert body["rows"] == []
    assert body["failure_reason"]
    # The committed FAILED run is READABLE (200, status='FAILED', real metadata) — the auditor's
    # durable refusal evidence — NOT a 404. Run metadata reflects the real run, not a faked one.
    got = client.get(f"/exposure/runs/{body['run_id']}", headers=_h(p))
    assert got.status_code == 200
    g = got.json()
    assert g["status"] == "FAILED"
    assert g["rows"] == []
    assert g["code_version"] == "v1" and g["environment_id"] == "ci"


def test_no_mutating_verbs(ctx) -> None:  # noqa: ANN001
    client, p, _db, _pf = ctx
    rid = str(uuid.uuid4())
    assert client.put(f"/exposure/{rid}", json={}, headers=_h(p)).status_code == 405
    assert client.delete(f"/exposure/{rid}", headers=_h(p)).status_code == 405


def test_view_only_user_cannot_run(ctx) -> None:  # noqa: ANN001
    # A user with exposure.view but NOT exposure.aggregate.run is denied the run (deny-by-default).
    client, p, db, pf = ctx
    tenant = p.tenant_id
    viewer = AppUser(tenant_id=tenant, display_name="V")
    role = Role(tenant_id=tenant, code="vr", name="VR")
    db.add_all([viewer, role])
    db.flush()
    perm = db.execute(select(Permission).where(Permission.code == "exposure.view")).scalar_one()
    db.add(RolePermission(role_id=role.id, permission_id=perm.id))
    db.add(UserRole(tenant_id=tenant, user_id=viewer.id, role_id=role.id))
    db.commit()
    headers = {"X-User-Id": viewer.id, "X-Tenant-Id": tenant}
    assert client.post("/exposure/runs", json=_run_body(pf), headers=headers).status_code == 403
