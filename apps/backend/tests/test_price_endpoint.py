"""End-to-end tests of the P2-4 price-history (price_point) endpoints.

SQLite has no RLS, so cross-tenant isolation + the foreign-instrument visibility proofs are in
``packages/shared-python/tests/test_price_point_pg.py``; here we prove entitlement gating
(deny-by-default, no DB side-effect on denial), server-side tenant stamping, the
capture->supersede->correct->read round-trip, 403/404/409/422 mapping, and no PUT/PATCH/DELETE.
The verbs REUSE marketdata.view/.ingest (no new permission).
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

from irp_backend.api.marketdata import price_router
from irp_backend.deps import get_db
from irp_shared.audit.models import AuditEvent
from irp_shared.db.session import make_engine, make_session_factory
from irp_shared.entitlement.bootstrap import SYSTEM_TENANT_ID
from irp_shared.entitlement.models import AppUser, Permission, Role, RolePermission, UserRole
from irp_shared.entitlement.service import Principal
from irp_shared.marketdata import PricePoint
from irp_shared.models import Base
from irp_shared.reference.models import Currency, Instrument

_PERMS = ("marketdata.view", "marketdata.ingest")
_VA = datetime(2026, 6, 1, tzinfo=UTC)
_PD = date(2026, 6, 1)


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
    inst = Instrument(
        tenant_id=tenant_id, code="AAPL", name="Apple", asset_class="EQUITY", valid_from=_VA
    )
    db.add(inst)
    db.commit()
    principal = Principal(user_id=user.id, tenant_id=tenant_id)
    iid = inst.id

    def _override_db() -> Iterator[Session]:
        yield db

    app = FastAPI()
    app.include_router(price_router)
    app.dependency_overrides[get_db] = _override_db
    try:
        yield TestClient(app), principal, db, iid
    finally:
        db.close()
        engine.dispose()


def _h(p: Principal) -> dict[str, str]:
    return {"X-User-Id": p.user_id, "X-Tenant-Id": p.tenant_id}


def _no_perm(p: Principal) -> dict[str, str]:
    return {"X-User-Id": str(uuid.uuid4()), "X-Tenant-Id": p.tenant_id}


def _capture(
    client: TestClient,
    p: Principal,
    iid: str,
    price="150.25",
    source="BLOOMBERG",
    **kw,  # noqa: ANN001
) -> dict:
    body = {
        "instrument_id": iid,
        "price_date": _PD.isoformat(),
        "price": price,
        "currency_code": "USD",
        "price_source": source,
        "valid_from": _VA.isoformat(),
        **kw,
    }
    return client.post("/prices", json=body, headers=_h(p))


def test_capture_201_stamps_tenant_and_audits(ctx) -> None:  # noqa: ANN001
    client, p, db, iid = ctx
    resp = _capture(client, p, iid, price="150.25")
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["instrument_id"] == iid and Decimal(body["price"]) == Decimal("150.25")
    assert body["price_type"] == "CLOSE" and body["currency_code"] == "USD"
    row = db.execute(select(PricePoint)).scalar_one()
    assert row.tenant_id == p.tenant_id
    assert (
        db.execute(
            select(func.count())
            .select_from(AuditEvent)
            .where(AuditEvent.event_type == "MARKET.PRICE_CREATE")
        ).scalar_one()
        == 1
    )


def test_capture_without_ingest_403_no_write(ctx) -> None:  # noqa: ANN001
    client, p, db, iid = ctx
    resp = client.post(
        "/prices",
        json={
            "instrument_id": iid,
            "price_date": _PD.isoformat(),
            "price": "150.25",
            "currency_code": "USD",
            "price_source": "BLOOMBERG",
        },
        headers=_no_perm(p),
    )
    assert resp.status_code == 403
    assert db.execute(select(func.count()).select_from(PricePoint)).scalar_one() == 0


def test_supersede_and_correct_round_trip(ctx) -> None:  # noqa: ANN001
    client, p, _, iid = ctx
    pid = _capture(client, p, iid).json()["id"]
    sup = client.post(
        f"/prices/{pid}/supersede",
        json={"effective_at": "2026-06-02T00:00:00+00:00", "price": "151.00"},
        headers=_h(p),
    )
    assert sup.status_code == 201 and Decimal(sup.json()["price"]) == Decimal("151.00")
    assert sup.json()["record_version"] == 2
    cor = client.post(
        f"/prices/{pid}/correct",
        json={"restatement_reason": "vendor fix", "price": "150.2600"},
        headers=_h(p),
    )
    assert cor.status_code == 201 and cor.json()["restatement_reason"] == "vendor fix"


def test_get_as_of_and_list(ctx) -> None:  # noqa: ANN001
    client, p, _, iid = ctx
    _capture(client, p, iid, price="150.25")
    q = {
        "instrument_id": iid,
        "currency_code": "USD",
        "price_source": "BLOOMBERG",
        "valid_at": _VA.isoformat(),
    }
    got = client.get("/prices/as-of", params={"price_date": _PD.isoformat(), **q}, headers=_h(p))
    assert got.status_code == 200 and Decimal(got.json()["price"]) == Decimal("150.25")
    lst = client.get(
        "/prices",
        params={"price_date_from": _PD.isoformat(), "price_date_to": _PD.isoformat(), **q},
        headers=_h(p),
    )
    assert lst.status_code == 200 and len(lst.json()) == 1


def test_error_mapping(ctx) -> None:  # noqa: ANN001
    client, p, _, iid = ctx
    # 404 unknown currency
    assert _capture(client, p, iid, price="1", currency_code="ZZZ").status_code == 404
    # 404 unknown instrument
    assert _capture(client, p, str(uuid.uuid4()), price="1").status_code == 404
    # 422 bad price_type
    assert _capture(client, p, iid, price="1", price_type="BID").status_code == 422
    # 409 non-positive price (DQ gate)
    assert _capture(client, p, iid, price="0").status_code == 409
    # 404 as-of unknown
    assert (
        client.get(
            "/prices/as-of",
            params={
                "instrument_id": iid,
                "price_date": _PD.isoformat(),
                "currency_code": "USD",
                "price_source": "NONE",
                "valid_at": _VA.isoformat(),
            },
            headers=_h(p),
        ).status_code
        == 404
    )
    # 404 supersede with no resolvable head
    assert (
        client.post(
            f"/prices/{uuid.uuid4()}/supersede",
            json={"effective_at": _VA.isoformat()},
            headers=_h(p),
        ).status_code
        == 404
    )


def test_no_put_patch_delete(ctx) -> None:  # noqa: ANN001
    client, p, _, iid = ctx
    pid = _capture(client, p, iid).json()["id"]
    for method in (client.put, client.patch, client.delete):
        assert method(f"/prices/{pid}", headers=_h(p)).status_code in (404, 405)
