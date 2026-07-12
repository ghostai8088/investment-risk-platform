"""End-to-end tests of the P1B-3 instrument / instrument_terms / identifier endpoints.

SQLite has no RLS, so cross-tenant isolation is proven in
``packages/shared-python/tests/test_reference_instruments_pg.py``; here we prove entitlement gating
(deny-by-default, no DB side-effect on denial), server-side tenant stamping, the terms POST dispatch
(create / supersede / correct), the FR ``/terms/as-of`` reconstruction, identifier resolve 200/404,
and 404/422 shapes.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from irp_backend.api.reference_instruments import router as reference_instruments_router
from irp_backend.deps import get_db
from irp_shared.audit.models import AuditEvent
from irp_shared.db.session import make_engine, make_session_factory
from irp_shared.entitlement.models import AppUser, Permission, Role, RolePermission, UserRole
from irp_shared.entitlement.service import Principal
from irp_shared.models import Base
from irp_shared.reference.models import Instrument

_PERMS = (
    "reference.instrument.view",
    "reference.instrument.edit",
    "reference.identifier.view",
    "reference.identifier.edit",
    "reference.identifier.resolve",
)


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
    db.commit()
    principal = Principal(user_id=user.id, tenant_id=tenant_id)

    def _override_db() -> Iterator[Session]:
        yield db

    app = FastAPI()
    app.include_router(reference_instruments_router)
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


def _make_instrument(client: TestClient, p: Principal, code: str = "BOND1", **kw) -> dict:  # noqa: ANN003
    body = {"code": code, "name": code, "asset_class": "BOND", **kw}
    resp = client.post("/reference/instruments", json=body, headers=_h(p))
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_create_instrument_201_stamps_tenant_and_audits(ctx) -> None:  # noqa: ANN001
    client, principal, db = ctx
    out = _make_instrument(client, principal, currency_code="USD")
    assert out["asset_class"] == "BOND" and out["issuer_id"] is None
    inst = db.get(Instrument, out["id"])
    assert inst is not None and inst.tenant_id == principal.tenant_id  # server-stamped
    n = db.execute(
        select(func.count()).select_from(AuditEvent).where(AuditEvent.entity_id == out["id"])
    ).scalar_one()
    assert n == 1


def test_create_instrument_denied_no_perm_no_side_effect(ctx) -> None:  # noqa: ANN001
    client, principal, db = ctx
    resp = client.post(
        "/reference/instruments",
        json={"code": "X", "name": "X", "asset_class": "BOND"},
        headers=_no_perm(principal),
    )
    assert resp.status_code == 403
    assert db.execute(select(func.count()).select_from(Instrument)).scalar_one() == 0


def test_get_instrument_404_unknown_and_422_malformed(ctx) -> None:  # noqa: ANN001
    client, principal, _ = ctx
    assert (
        client.get(f"/reference/instruments/{uuid.uuid4()}", headers=_h(principal)).status_code
        == 404
    )
    assert client.get("/reference/instruments/not-a-uuid", headers=_h(principal)).status_code == 422


def test_terms_create_supersede_correct_and_as_of(ctx) -> None:  # noqa: ANN001
    client, principal, _ = ctx
    inst = _make_instrument(client, principal)
    iid = inst["id"]
    # create
    r = client.post(
        f"/reference/instruments/{iid}/terms",
        json={"mode": "create", "valid_from": "2026-01-01T00:00:00Z", "coupon_rate": "5.5"},
        headers=_h(principal),
    )
    assert r.status_code == 201, r.text
    v1 = r.json()
    assert v1["valid_to"] is None and v1["record_version"] == 1
    # supersede
    r = client.post(
        f"/reference/instruments/{iid}/terms",
        json={"mode": "supersede", "effective_at": "2027-01-01T00:00:00Z", "coupon_rate": "6.0"},
        headers=_h(principal),
    )
    assert r.status_code == 201, r.text
    assert r.json()["record_version"] == 2 and r.json()["supersedes_id"] == v1["id"]
    # correct the latest version
    v2_id = r.json()["id"]
    r = client.post(
        f"/reference/instruments/{iid}/terms",
        json={
            "mode": "correct",
            "terms_id": v2_id,
            "restatement_reason": "fix",
            "coupon_rate": "6.25",
        },
        headers=_h(principal),
    )
    assert r.status_code == 201, r.text
    assert r.json()["restatement_reason"] == "fix"
    # as-of current view at 2028 = corrected
    r = client.get(
        f"/reference/instruments/{iid}/terms/as-of",
        params={"valid_at": "2028-01-01T00:00:00Z"},
        headers=_h(principal),
    )
    from decimal import Decimal

    assert r.status_code == 200 and Decimal(r.json()["coupon_rate"]) == Decimal("6.25")


def test_terms_supersede_without_effective_at_422(ctx) -> None:  # noqa: ANN001
    client, principal, _ = ctx
    inst = _make_instrument(client, principal)
    r = client.post(
        f"/reference/instruments/{inst['id']}/terms",
        json={"mode": "supersede"},
        headers=_h(principal),
    )
    assert r.status_code == 422


def test_terms_supersede_backdated_effective_at_is_422(ctx) -> None:  # noqa: ANN001
    # MD-H1 window-coherence end-to-end: effective_at at/before the head's valid_from is a
    # pre-write refusal surfaced as 422, not a silent inverted window.
    client, principal, _ = ctx
    inst = _make_instrument(client, principal)
    r = client.post(
        f"/reference/instruments/{inst['id']}/terms",
        json={"mode": "create", "valid_from": "2026-01-01T00:00:00Z", "coupon_rate": "5.5"},
        headers=_h(principal),
    )
    assert r.status_code == 201, r.text
    r = client.post(
        f"/reference/instruments/{inst['id']}/terms",
        json={"mode": "supersede", "effective_at": "2025-12-01T00:00:00Z", "coupon_rate": "6.0"},
        headers=_h(principal),
    )
    assert r.status_code == 422, r.text
    assert "strictly after" in r.json()["detail"]


def test_identifier_create_and_resolve(ctx) -> None:  # noqa: ANN001
    client, principal, _ = ctx
    inst = _make_instrument(client, principal)
    r = client.post(
        "/reference/identifier-xrefs",
        json={"instrument_id": inst["id"], "scheme": "ISIN", "value": "US0000009"},
        headers=_h(principal),
    )
    assert r.status_code == 201, r.text
    assert r.json()["entity_type"] == "instrument"
    # resolve -> 200 the instrument
    r = client.get(
        "/reference/identifiers/resolve",
        params={"scheme": "ISIN", "value": "US0000009"},
        headers=_h(principal),
    )
    assert r.status_code == 200 and r.json()["id"] == inst["id"]
    # unknown -> 404
    assert (
        client.get(
            "/reference/identifiers/resolve",
            params={"scheme": "ISIN", "value": "NOPE"},
            headers=_h(principal),
        ).status_code
        == 404
    )


def test_resolve_denied_no_perm(ctx) -> None:  # noqa: ANN001
    client, principal, _ = ctx
    r = client.get(
        "/reference/identifiers/resolve",
        params={"scheme": "ISIN", "value": "X"},
        headers=_no_perm(principal),
    )
    assert r.status_code == 403


def test_resolve_ambiguous_409(ctx) -> None:  # noqa: ANN001
    from datetime import UTC, datetime

    from irp_shared.reference.models import IdentifierXref

    client, principal, db = ctx
    i1 = _make_instrument(client, principal, "I1")
    i2 = _make_instrument(client, principal, "I2")
    tenant = principal.tenant_id
    # One active row (valid_to NULL) + one future-dated-close row for the SAME (scheme, value) but
    # DIFFERENT instruments — both match as-of now, so endpoint resolution is ambiguous (409), never
    # a silent pick. The active partial-unique permits this (only one row has valid_to NULL).
    db.add_all(
        [
            IdentifierXref(
                tenant_id=tenant,
                entity_type="instrument",
                entity_id=i1["id"],
                scheme="CUSIP",
                value="DUP",
                valid_from=datetime(2026, 1, 1, tzinfo=UTC),
                valid_to=None,
                is_active=True,
                record_version=1,
            ),
            IdentifierXref(
                tenant_id=tenant,
                entity_type="instrument",
                entity_id=i2["id"],
                scheme="CUSIP",
                value="DUP",
                valid_from=datetime(2026, 1, 1, tzinfo=UTC),
                valid_to=datetime(2099, 1, 1, tzinfo=UTC),
                is_active=True,
                record_version=1,
            ),
        ]
    )
    db.commit()
    r = client.get(
        "/reference/identifiers/resolve",
        params={"scheme": "CUSIP", "value": "DUP"},
        headers=_h(principal),
    )
    assert r.status_code == 409, r.text
    assert r.json()["detail"]["error"] == "ambiguous_identifier"
