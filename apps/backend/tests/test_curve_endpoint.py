"""End-to-end tests of the P2-5 curve (curve + curve_point) endpoints.

SQLite has no RLS, so cross-tenant isolation + the curve_point append-only P0001 proof are in
``packages/shared-python/tests/test_curve_pg.py``; we prove entitlement gating (deny-by-default,
no DB side-effect on denial), server-side tenant stamping, the capture->supersede->correct->read
round-trip (header + nodes), 403/404/409/422 mapping (incl. the reference_key invariant + the
value-type-conditional DQ), and no PUT/PATCH/DELETE. The verbs REUSE marketdata.view/.ingest.
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

from irp_backend.api.marketdata import curve_router
from irp_backend.deps import get_db
from irp_shared.audit.models import AuditEvent
from irp_shared.db.session import make_engine, make_session_factory
from irp_shared.entitlement.bootstrap import SYSTEM_TENANT_ID
from irp_shared.entitlement.models import AppUser, Permission, Role, RolePermission, UserRole
from irp_shared.entitlement.service import Principal
from irp_shared.marketdata import Curve
from irp_shared.models import Base
from irp_shared.reference.models import Currency

_PERMS = ("marketdata.view", "marketdata.ingest")
_VA = datetime(2026, 6, 1, tzinfo=UTC)
_CD = date(2026, 6, 1)
_NODES = [
    {"tenor_label": "3M", "tenor_days": 90, "value_type": "ZERO_RATE", "point_value": "0.0425"},
    {
        "tenor_label": "1Y",
        "tenor_days": 365,
        "value_type": "DISCOUNT_FACTOR",
        "point_value": "0.956",
    },
]


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
    db.add(Currency(tenant_id=SYSTEM_TENANT_ID, code="USD", name="USD", valid_from=_VA))
    db.commit()
    principal = Principal(user_id=user.id, tenant_id=tenant_id)

    def _override_db() -> Iterator[Session]:
        yield db

    app = FastAPI()
    app.include_router(curve_router)
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


def _capture(client: TestClient, p: Principal, source="BLOOMBERG", nodes=None, **kw) -> dict:  # noqa: ANN001
    body = {
        "curve_type": "TREASURY",
        "currency_code": "USD",
        "curve_date": _CD.isoformat(),
        "curve_source": source,
        "nodes": _NODES if nodes is None else nodes,
        "valid_from": _VA.isoformat(),
        **kw,
    }
    return client.post("/curves", json=body, headers=_h(p))


def test_capture_201_stamps_tenant_and_audits(ctx) -> None:  # noqa: ANN001
    client, p, db = ctx
    resp = _capture(client, p)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["curve_type"] == "TREASURY" and body["point_count"] == 2
    assert len(body["nodes"]) == 2 and body["reference_key"] == "NONE"
    row = db.execute(select(Curve)).scalar_one()
    assert row.tenant_id == p.tenant_id
    assert (
        db.execute(
            select(func.count())
            .select_from(AuditEvent)
            .where(AuditEvent.event_type == "MARKET.CURVE_CREATE")
        ).scalar_one()
        == 1  # ONE event per curve
    )


def test_capture_without_ingest_403_no_write(ctx) -> None:  # noqa: ANN001
    client, p, db = ctx
    resp = client.post(
        "/curves",
        json={
            "curve_type": "TREASURY",
            "currency_code": "USD",
            "curve_date": _CD.isoformat(),
            "curve_source": "BLOOMBERG",
            "nodes": _NODES,
        },
        headers=_no_perm(p),
    )
    assert resp.status_code == 403
    assert db.execute(select(func.count()).select_from(Curve)).scalar_one() == 0


def test_supersede_and_correct_round_trip(ctx) -> None:  # noqa: ANN001
    client, p, _ = ctx
    cid = _capture(client, p).json()["id"]
    sup = client.post(
        f"/curves/{cid}/supersede",
        json={
            "effective_at": "2026-06-02T00:00:00+00:00",
            "nodes": [
                {
                    "tenor_label": "3M",
                    "tenor_days": 90,
                    "value_type": "ZERO_RATE",
                    "point_value": "0.05",
                }
            ],
        },
        headers=_h(p),
    )
    assert sup.status_code == 201 and sup.json()["record_version"] == 2
    assert sup.json()["point_count"] == 1
    cor = client.post(
        f"/curves/{cid}/correct",
        json={
            "restatement_reason": "vendor fix",
            "nodes": [
                {
                    "tenor_label": "3M",
                    "tenor_days": 90,
                    "value_type": "ZERO_RATE",
                    "point_value": "0.0426",
                }
            ],
        },
        headers=_h(p),
    )
    assert cor.status_code == 201 and cor.json()["restatement_reason"] == "vendor fix"


def test_get_as_of_and_list(ctx) -> None:  # noqa: ANN001
    client, p, _ = ctx
    _capture(client, p)
    q = {
        "curve_type": "TREASURY",
        "currency_code": "USD",
        "curve_source": "BLOOMBERG",
        "valid_at": _VA.isoformat(),
    }
    got = client.get("/curves/as-of", params={"curve_date": _CD.isoformat(), **q}, headers=_h(p))
    assert got.status_code == 200 and len(got.json()["nodes"]) == 2
    lst = client.get(
        "/curves",
        params={"curve_date_from": _CD.isoformat(), "curve_date_to": _CD.isoformat(), **q},
        headers=_h(p),
    )
    assert lst.status_code == 200 and len(lst.json()) == 1 and lst.json()[0]["point_count"] == 2


def test_error_mapping(ctx) -> None:  # noqa: ANN001
    client, p, _ = ctx
    # 404 unknown currency
    assert _capture(client, p, currency_code="ZZZ").status_code == 404
    # 422 out-of-vocab curve_type
    assert _capture(client, p, curve_type="JUNK").status_code == 422
    # 422 reference_key invariant (rate curve + non-NONE)
    assert _capture(client, p, reference_key="RATING:BBB").status_code == 422
    # 422 bad value_type
    bad_vt = [{"tenor_label": "1Y", "tenor_days": 365, "value_type": "VOL", "point_value": "0.2"}]
    assert _capture(client, p, nodes=bad_vt).status_code == 422
    # 409 value-type-conditional DQ (DISCOUNT_FACTOR <= 0)
    bad_df = [
        {
            "tenor_label": "1Y",
            "tenor_days": 365,
            "value_type": "DISCOUNT_FACTOR",
            "point_value": "0",
        }
    ]
    assert _capture(client, p, nodes=bad_df).status_code == 409
    # 404 as-of unknown
    assert (
        client.get(
            "/curves/as-of",
            params={
                "curve_type": "TREASURY",
                "currency_code": "USD",
                "curve_date": _CD.isoformat(),
                "curve_source": "NONE",
                "valid_at": _VA.isoformat(),
            },
            headers=_h(p),
        ).status_code
        == 404
    )
    # 404 supersede with no resolvable head
    assert (
        client.post(
            f"/curves/{uuid.uuid4()}/supersede",
            json={"effective_at": _VA.isoformat(), "nodes": _NODES},
            headers=_h(p),
        ).status_code
        == 404
    )


def test_no_put_patch_delete(ctx) -> None:  # noqa: ANN001
    client, p, _ = ctx
    cid = _capture(client, p).json()["id"]
    for method in (client.put, client.patch, client.delete):
        assert method(f"/curves/{cid}", headers=_h(p)).status_code in (404, 405)
