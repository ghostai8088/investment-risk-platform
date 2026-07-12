"""End-to-end tests of the P3-2 factor (factor + factor_return) endpoints.

SQLite has no RLS, so cross-tenant isolation is in ``tests/test_factor_pg.py``; here we prove
entitlement gating (deny-by-default, no DB side-effect on denial), server-side tenant stamping,
the split audit family (REFERENCE.* definition + MARKET.FACTOR_RETURN_* series), the create /
update / capture / supersede / correct / as-of / list round-trip, 403/404/409/422 mapping, and
no PUT/PATCH/DELETE. The verbs REUSE marketdata.view/.ingest.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import UTC, date, datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from irp_backend.api.marketdata import factor_router
from irp_backend.deps import get_db
from irp_shared.audit.models import AuditEvent
from irp_shared.db.session import make_engine, make_session_factory
from irp_shared.entitlement.bootstrap import SYSTEM_TENANT_ID
from irp_shared.entitlement.models import AppUser, Permission, Role, RolePermission, UserRole
from irp_shared.entitlement.service import Principal
from irp_shared.marketdata import Factor
from irp_shared.models import Base
from irp_shared.reference.models import Currency

_PERMS = ("marketdata.view", "marketdata.ingest")
_VF = datetime(2020, 1, 1, tzinfo=UTC)
_RD = date(2026, 5, 29)
_FAR = "2030-01-01T00:00:00+00:00"


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
    db.add(Currency(tenant_id=SYSTEM_TENANT_ID, code="USD", name="USD", valid_from=_VF))
    db.commit()
    principal = Principal(user_id=user.id, tenant_id=tenant_id)

    def _override_db() -> Iterator[Session]:
        yield db

    app = FastAPI()
    app.include_router(factor_router)
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


def _create_factor(client: TestClient, p: Principal, source: str = "MSCI_BARRA", **kw):  # noqa: ANN003, ANN202
    body = {
        "factor_code": "MOMENTUM",
        "factor_source": source,
        "factor_family": "STYLE",
        "currency_code": "USD",
        **kw,
    }
    return client.post("/factors", json=body, headers=_h(p))


def _capture_return(client: TestClient, p: Principal, fid: str, value: str = "0.0123"):  # noqa: ANN202
    return client.post(
        f"/factors/{fid}/returns",
        # explicit early valid_from so a later effective-dated supersede is window-coherent (MD-H1).
        json={
            "return_date": _RD.isoformat(),
            "return_value": value,
            "valid_from": "2026-06-01T00:00:00+00:00",
        },
        headers=_h(p),
    )


def test_create_201_stamps_tenant_and_reference_audits(ctx) -> None:  # noqa: ANN001
    client, p, db = ctx
    resp = _create_factor(client, p)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["factor_code"] == "MOMENTUM" and body["record_version"] == 1
    row = db.execute(select(Factor)).scalar_one()
    assert row.tenant_id == p.tenant_id
    # the EV definition is audited REFERENCE.CREATE (NOT MARKET.FACTOR_RETURN_CREATE).
    assert (
        db.execute(
            select(func.count())
            .select_from(AuditEvent)
            .where(AuditEvent.event_type == "REFERENCE.CREATE")
        ).scalar_one()
        == 1
    )
    assert (
        db.execute(
            select(func.count())
            .select_from(AuditEvent)
            .where(AuditEvent.event_type == "MARKET.FACTOR_RETURN_CREATE")
        ).scalar_one()
        == 0
    )


def test_create_without_ingest_403_no_write(ctx) -> None:  # noqa: ANN001
    client, p, db = ctx
    resp = client.post(
        "/factors",
        json={"factor_code": "MOMENTUM", "factor_source": "MSCI_BARRA", "factor_family": "STYLE"},
        headers=_no_perm(p),
    )
    assert resp.status_code == 403
    assert db.execute(select(func.count()).select_from(Factor)).scalar_one() == 0


def test_update_definition_bumps_version(ctx) -> None:  # noqa: ANN001
    client, p, db = ctx
    fid = _create_factor(client, p).json()["id"]
    resp = client.post(
        f"/factors/{fid}/update", json={"description": "Barra momentum"}, headers=_h(p)
    )
    assert resp.status_code == 200 and resp.json()["record_version"] == 2
    assert resp.json()["description"] == "Barra momentum"
    assert (
        db.execute(
            select(func.count())
            .select_from(AuditEvent)
            .where(AuditEvent.event_type == "REFERENCE.UPDATE")
        ).scalar_one()
        == 1
    )


def test_return_capture_supersede_correct_as_of(ctx) -> None:  # noqa: ANN001
    client, p, db = ctx
    fid = _create_factor(client, p).json()["id"]
    cap = _capture_return(client, p, fid, "0.0123")
    assert cap.status_code == 201 and cap.json()["record_version"] == 1
    assert (
        db.execute(
            select(func.count())
            .select_from(AuditEvent)
            .where(AuditEvent.event_type == "MARKET.FACTOR_RETURN_CREATE")
        ).scalar_one()
        == 1
    )
    sup = client.post(
        f"/factors/{fid}/returns/supersede",
        json={
            "return_date": _RD.isoformat(),
            "return_value": "0.0130",
            "effective_at": "2026-06-15T00:00:00+00:00",
        },
        headers=_h(p),
    )
    assert sup.status_code == 201 and sup.json()["record_version"] == 2
    cor = client.post(
        f"/factors/{fid}/returns/correct",
        json={
            "return_date": _RD.isoformat(),
            "return_value": "0.0125",
            "restatement_reason": "vendor fix",
        },
        headers=_h(p),
    )
    assert cor.status_code == 201 and cor.json()["record_version"] == 3
    got = client.get(
        f"/factors/{fid}/returns/as-of",
        params={"return_date": _RD.isoformat(), "valid_at": _FAR, "known_at": _FAR},
        headers=_h(p),
    )
    assert got.status_code == 200
    assert got.json()["return_value"] == "0.012500000000"  # current head after correction


def test_list_factors_and_returns(ctx) -> None:  # noqa: ANN001
    client, p, _ = ctx
    fid = _create_factor(client, p, source="MSCI_BARRA").json()["id"]
    _create_factor(client, p, source="BLOOMBERG")
    _capture_return(client, p, fid, "0.01")
    factors = client.get("/factors", headers=_h(p))
    assert factors.status_code == 200 and len(factors.json()) == 2
    returns = client.get(f"/factors/{fid}/returns", headers=_h(p))
    assert returns.status_code == 200 and len(returns.json()) == 1
    # the ?return_type= query filter binds and filters (matching -> 1, non-matching -> 0)
    assert len(client.get(f"/factors/{fid}/returns?return_type=SIMPLE", headers=_h(p)).json()) == 1
    assert len(client.get(f"/factors/{fid}/returns?return_type=LOG", headers=_h(p)).json()) == 0


def test_error_mapping(ctx) -> None:  # noqa: ANN001
    client, p, _ = ctx
    # 404 unknown currency
    assert _create_factor(client, p, currency_code="ZZZ").status_code == 404
    # 422 out-of-vocab factor_family
    assert _create_factor(client, p, factor_family="NOT_A_FAMILY").status_code == 422
    fid = _create_factor(client, p).json()["id"]
    # 404 unknown factor for a return capture
    assert (
        client.post(
            f"/factors/{uuid.uuid4()}/returns",
            json={"return_date": _RD.isoformat(), "return_value": "0.01"},
            headers=_h(p),
        ).status_code
        == 404
    )
    # 409 return DQ (<= -1 fails the > -1 economic-sanity RANGE)
    assert _capture_return(client, p, fid, "-1.5").status_code == 409
    # 409 supersede with no current return
    assert (
        client.post(
            f"/factors/{fid}/returns/supersede",
            json={
                "return_date": _RD.isoformat(),
                "return_value": "0.01",
                "effective_at": "2026-06-15T00:00:00+00:00",
            },
            headers=_h(p),
        ).status_code
        == 409
    )


def test_update_bad_family_422(ctx) -> None:  # noqa: ANN001
    client, p, _ = ctx
    fid = _create_factor(client, p).json()["id"]
    resp = client.post(
        f"/factors/{fid}/update", json={"factor_family": "NOT_A_FAMILY"}, headers=_h(p)
    )
    assert resp.status_code == 422


def test_return_as_of_unknown_factor_404(ctx) -> None:  # noqa: ANN001
    # a read for an unknown/cross-tenant factor_id fails closed with 404 (NOT an unmapped 500).
    client, p, _ = ctx
    resp = client.get(
        f"/factors/{uuid.uuid4()}/returns/as-of",
        params={"return_date": _RD.isoformat(), "valid_at": _FAR},
        headers=_h(p),
    )
    assert resp.status_code == 404


def test_no_put_patch_delete(ctx) -> None:  # noqa: ANN001
    client, p, _ = ctx
    fid = _create_factor(client, p).json()["id"]
    for method in (client.put, client.patch, client.delete):
        assert method(f"/factors/{fid}", headers=_h(p)).status_code in (404, 405)
