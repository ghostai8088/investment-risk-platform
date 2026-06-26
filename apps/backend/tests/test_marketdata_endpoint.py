"""End-to-end tests of the P2-2 market-data (fx_rate) endpoints.

SQLite has no RLS, so cross-tenant isolation + the SYSTEM/foreign currency-visibility proofs are in
``packages/shared-python/tests/test_fx_rate_pg.py``; here we prove entitlement gating
(deny-by-default,
no DB side-effect on denial), server-side tenant stamping, the
capture→supersede→correct→read→convert
round-trip, and 403/404/409/422 mapping + no PUT/PATCH/DELETE.
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

from irp_backend.api.marketdata import router as marketdata_router
from irp_backend.deps import get_db
from irp_shared.audit.models import AuditEvent
from irp_shared.db.session import make_engine, make_session_factory
from irp_shared.entitlement.bootstrap import SYSTEM_TENANT_ID
from irp_shared.entitlement.models import AppUser, Permission, Role, RolePermission, UserRole
from irp_shared.entitlement.service import Principal
from irp_shared.marketdata import FxRate
from irp_shared.models import Base
from irp_shared.reference.models import Currency

_PERMS = ("marketdata.view", "marketdata.ingest")
_VA = datetime(2026, 6, 1, tzinfo=UTC)
_RD = date(2026, 6, 1)


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
    for ccy in ("USD", "EUR", "JPY"):
        db.add(Currency(tenant_id=SYSTEM_TENANT_ID, code=ccy, name=ccy, valid_from=_VA))
    db.commit()
    principal = Principal(user_id=user.id, tenant_id=tenant_id)

    def _override_db() -> Iterator[Session]:
        yield db

    app = FastAPI()
    app.include_router(marketdata_router)
    app.dependency_overrides[get_db] = _override_db
    try:
        yield TestClient(app), principal, db
    finally:
        db.close()
        engine.dispose()


def _h(p: Principal) -> dict[str, str]:
    return {"X-User-Id": p.user_id, "X-Tenant-Id": p.tenant_id}


def _no_perm(p: Principal) -> dict[str, str]:
    return {"X-User-Id": str(uuid.uuid4()), "X-Tenant-Id": p.tenant_id}


def _capture(client: TestClient, p: Principal, base="EUR", quote="USD", rate="1.08", **kw) -> dict:  # noqa: ANN001
    body = {
        "base_currency": base,
        "quote_currency": quote,
        "rate_date": _RD.isoformat(),
        "rate": rate,
        "valid_from": _VA.isoformat(),
        **kw,
    }
    return client.post("/fx", json=body, headers=_h(p))


def test_capture_201_stamps_tenant_and_audits(ctx) -> None:  # noqa: ANN001
    client, p, db = ctx
    resp = _capture(client, p, rate="1.08", rate_source="ECB")
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["base_currency"] == "EUR" and Decimal(body["rate"]) == Decimal("1.08")
    row = db.execute(select(FxRate)).scalar_one()
    assert row.tenant_id == p.tenant_id
    assert (
        db.execute(
            select(func.count())
            .select_from(AuditEvent)
            .where(AuditEvent.event_type == "MARKET.FX_CREATE")
        ).scalar_one()
        == 1
    )


def test_capture_without_ingest_403_no_write(ctx) -> None:  # noqa: ANN001
    client, p, db = ctx
    resp = client.post(
        "/fx",
        json={
            "base_currency": "EUR",
            "quote_currency": "USD",
            "rate_date": _RD.isoformat(),
            "rate": "1.08",
        },
        headers=_no_perm(p),
    )
    assert resp.status_code == 403
    assert db.execute(select(func.count()).select_from(FxRate)).scalar_one() == 0


def test_supersede_and_correct_round_trip(ctx) -> None:  # noqa: ANN001
    client, p, _ = ctx
    fid = _capture(client, p).json()["id"]
    sup = client.post(
        f"/fx/{fid}/supersede",
        json={"effective_at": "2026-06-02T00:00:00+00:00", "rate": "1.10"},
        headers=_h(p),
    )
    assert sup.status_code == 201 and Decimal(sup.json()["rate"]) == Decimal("1.10")
    cor = client.post(
        f"/fx/{fid}/correct",
        json={"restatement_reason": "vendor fix", "rate": "1.0801"},
        headers=_h(p),
    )
    assert cor.status_code == 201 and cor.json()["restatement_reason"] == "vendor fix"


def test_get_as_of_and_convert(ctx) -> None:  # noqa: ANN001
    client, p, _ = ctx
    _capture(client, p, "EUR", "USD", "1.08")
    _capture(client, p, "USD", "JPY", "150")
    q = {"valid_at": _VA.isoformat()}
    got = client.get(
        "/fx/as-of",
        params={"base_currency": "EUR", "quote_currency": "USD", "rate_date": _RD.isoformat(), **q},
        headers=_h(p),
    )
    assert got.status_code == 200 and Decimal(got.json()["rate"]) == Decimal("1.08")
    # direct convert
    c1 = client.get(
        "/fx/convert",
        params={"amount": "100", "from_currency": "EUR", "to_currency": "USD", **q},
        headers=_h(p),
    )
    assert c1.status_code == 200 and Decimal(c1.json()["converted_amount"]) == Decimal("108")
    # triangulated EUR->JPY
    c2 = client.get(
        "/fx/convert",
        params={"amount": "1", "from_currency": "EUR", "to_currency": "JPY", **q},
        headers=_h(p),
    )
    assert c2.status_code == 200 and Decimal(c2.json()["converted_amount"]) == Decimal("162")


def test_error_mapping(ctx) -> None:  # noqa: ANN001
    client, p, _ = ctx
    # 404 unknown currency
    assert _capture(client, p, "EUR", "ZZZ", "1.0").status_code == 404
    # 422 bad rate_type
    assert _capture(client, p, "EUR", "USD", "1.0", rate_type="BID").status_code == 422
    # 409 non-positive rate (DQ gate)
    assert _capture(client, p, "EUR", "USD", "0").status_code == 409
    # 404 as-of unknown
    assert (
        client.get(
            "/fx/as-of",
            params={
                "base_currency": "EUR",
                "quote_currency": "USD",
                "rate_date": _RD.isoformat(),
                "valid_at": _VA.isoformat(),
            },
            headers=_h(p),
        ).status_code
        == 404
    )
    # 404 convert no path
    assert (
        client.get(
            "/fx/convert",
            params={
                "amount": "1",
                "from_currency": "GBP",
                "to_currency": "USD",
                "valid_at": _VA.isoformat(),
            },
            headers=_h(p),
        ).status_code
        == 404
    )
    # 409 supersede with no current head
    assert (
        client.post(
            f"/fx/{uuid.uuid4()}/supersede", json={"effective_at": _VA.isoformat()}, headers=_h(p)
        ).status_code
        == 404
    )


def test_no_put_patch_delete(ctx) -> None:  # noqa: ANN001
    client, p, _ = ctx
    fid = _capture(client, p).json()["id"]
    for method in (client.put, client.patch, client.delete):
        assert method(f"/fx/{fid}", headers=_h(p)).status_code in (404, 405)
