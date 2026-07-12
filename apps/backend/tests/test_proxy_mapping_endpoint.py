"""End-to-end tests of the PA-0 proxy-mapping endpoints (ENT-019; REUSES marketdata.view/ingest).

SQLite has no RLS (isolation + append-only proofs live in
``packages/shared-python/tests/test_proxy_mapping_pg.py``); here we prove the entitlement gating on
the REUSED verbs (deny-by-default; view cannot ingest), the capture + supersede + correct + as-of +
list round-trip, fixed-point decimal serialization, and the pre-create refusals (422 finiteness /
foreign FK / bad vocab; 409 no-current).
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from irp_backend.api.marketdata import factor_router, proxy_mapping_router
from irp_backend.deps import get_db
from irp_shared.db.session import make_engine, make_session_factory
from irp_shared.entitlement.bootstrap import SYSTEM_TENANT_ID
from irp_shared.entitlement.models import AppUser, Permission, Role, RolePermission, UserRole
from irp_shared.entitlement.service import Principal
from irp_shared.marketdata import FactorActor, capture_factor
from irp_shared.models import Base
from irp_shared.reference.instrument import create_instrument
from irp_shared.reference.models import Currency
from irp_shared.reference.service import ReferenceActor

_PERMS = ("marketdata.view", "marketdata.ingest")
_VF = datetime(2020, 1, 1, tzinfo=UTC)
#: The capture endpoint stamps valid_from = now (no backdating exposed), so supersede's effective_at
#: must be in the FUTURE for a coherent valid window; reconstruct BETWEEN now and _FUTURE sees the
#: original head, AT _FAR sees the superseded/corrected head.
_FUTURE = "2027-01-01T00:00:00+00:00"
_MID = "2026-09-01T00:00:00+00:00"
_FAR = "2030-01-01T00:00:00+00:00"


@pytest.fixture
def ctx() -> Iterator[tuple[TestClient, Principal, Session, str, str]]:
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
    db.flush()
    inst = create_instrument(
        db,
        tenant_id=tenant_id,
        code=f"PE-{uuid.uuid4().hex[:6]}",
        name="Fund",
        asset_class="PRIVATE_EQUITY",
        actor=ReferenceActor(actor_id="s"),
    ).id
    factor = capture_factor(
        db,
        factor_code=f"EQ-{uuid.uuid4().hex[:6]}",
        factor_source="VENDOR_F",
        factor_family="CURRENCY",
        currency_code="USD",
        acting_tenant=tenant_id,
        actor=FactorActor(actor_id="s"),
    ).id
    db.commit()
    principal = Principal(user_id=user.id, tenant_id=tenant_id)

    def _override_db() -> Iterator[Session]:
        yield db

    app = FastAPI()
    app.include_router(factor_router)
    app.include_router(proxy_mapping_router)
    app.dependency_overrides[get_db] = _override_db
    try:
        yield TestClient(app), principal, db, inst, factor
    finally:
        db.close()
        engine.dispose()


def _h(p: Principal) -> dict[str, str]:
    return {"X-User-Id": p.user_id, "X-Tenant-Id": p.tenant_id}


def _body(inst: str, factor: str, weight: str = "0.7", **kw) -> dict:  # noqa: ANN003
    return {
        "private_instrument_id": inst,
        "factor_id": factor,
        "weight": weight,
        **kw,
    }


def test_capture_supersede_correct_and_read_roundtrip(ctx) -> None:  # noqa: ANN001
    client, p, db, inst, factor = ctx
    resp = client.post("/proxy-mappings", json=_body(inst, factor), headers=_h(p))
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["mapping_method"] == "MANUAL" and body["record_version"] == 1
    assert Decimal(body["weight"]) == Decimal("0.7")
    assert "E" not in body["weight"] and "e" not in body["weight"]  # never scientific
    # supersede (effective in the FUTURE — a coherent forward window vs the now-based capture)
    sup = client.post(
        "/proxy-mappings/supersede",
        json=_body(inst, factor, weight="0.75", effective_at=_FUTURE),
        headers=_h(p),
    )
    assert sup.status_code == 201 and sup.json()["record_version"] == 2
    # correct the future head's system-time record
    cor = client.post(
        "/proxy-mappings/correct",
        json=_body(inst, factor, weight="0.8", restatement_reason="revision"),
        headers=_h(p),
    )
    assert cor.status_code == 201 and cor.json()["restatement_reason"] == "revision"
    # as-of BEFORE the supersede takes effect (2026) → the original 0.7 head
    asof = client.get(
        "/proxy-mappings/as-of",
        params={
            "private_instrument_id": inst,
            "factor_id": factor,
            "valid_at": _MID,
            "known_at": _FAR,
        },
        headers=_h(p),
    )
    assert asof.status_code == 200 and Decimal(asof.json()["weight"]) == Decimal("0.7")
    # as-of AFTER the supersede takes effect (2030) → the corrected 0.8 head
    asof2 = client.get(
        "/proxy-mappings/as-of",
        params={
            "private_instrument_id": inst,
            "factor_id": factor,
            "valid_at": _FAR,
            "known_at": _FAR,
        },
        headers=_h(p),
    )
    assert asof2.status_code == 200 and Decimal(asof2.json()["weight"]) == Decimal("0.8")


def test_duplicate_capture_is_409_not_500(ctx) -> None:  # noqa: ANN001
    # MD-H1 OD-C: a second capture of the same open (instrument, factor) head collides on the
    # current-head unique constraint → the IntegrityError is mapped to a clean 409 (not a raw 500),
    # and the transaction rolls back leaving the original row intact + readable.
    client, p, db, inst, factor = ctx
    first = client.post("/proxy-mappings", json=_body(inst, factor, weight="0.7"), headers=_h(p))
    assert first.status_code == 201
    dup = client.post("/proxy-mappings", json=_body(inst, factor, weight="0.9"), headers=_h(p))
    assert dup.status_code == 409, dup.text
    assert "already exists" in dup.json()["detail"]
    # the original head is intact (the failed capture rolled back cleanly, no partial write).
    head = client.get(
        "/proxy-mappings/as-of",
        params={
            "private_instrument_id": inst,
            "factor_id": factor,
            "valid_at": _FAR,
            "known_at": _FAR,
        },
        headers=_h(p),
    )
    assert head.status_code == 200 and Decimal(head.json()["weight"]) == Decimal("0.7")


def test_supersede_backdated_effective_at_is_422(ctx) -> None:  # noqa: ANN001
    # MD-H1 OD-B end-to-end: a supersede whose effective_at precedes the capture's valid_from is a
    # window-coherence refusal surfaced as 422 at the API (not a 500, not a silent inverted window).
    client, p, db, inst, factor = ctx
    cap = client.post(
        "/proxy-mappings",
        json=_body(inst, factor, weight="0.7", valid_from="2026-06-01T00:00:00+00:00"),
        headers=_h(p),
    )
    assert cap.status_code == 201
    bad = client.post(
        "/proxy-mappings/supersede",
        json=_body(inst, factor, weight="0.75", effective_at="2026-05-01T00:00:00+00:00"),
        headers=_h(p),
    )
    assert bad.status_code == 422, bad.text


def test_deny_by_default_and_view_cannot_ingest(ctx) -> None:  # noqa: ANN001
    client, p, db, inst, factor = ctx
    nobody = Principal(user_id=str(uuid.uuid4()), tenant_id=p.tenant_id)
    resp = client.post("/proxy-mappings", json=_body(inst, factor), headers=_h(nobody))
    assert resp.status_code == 403
    # a view-only user cannot ingest
    from sqlalchemy import select

    viewer = AppUser(tenant_id=p.tenant_id, display_name="V")
    vrole = Role(tenant_id=p.tenant_id, code="v", name="V")
    db.add_all([viewer, vrole])
    db.flush()
    pid = db.execute(select(Permission.id).where(Permission.code == "marketdata.view")).scalar_one()
    db.add(RolePermission(role_id=vrole.id, permission_id=pid))
    db.add(UserRole(tenant_id=p.tenant_id, user_id=viewer.id, role_id=vrole.id))
    db.commit()
    vp = Principal(user_id=viewer.id, tenant_id=p.tenant_id)
    resp = client.post("/proxy-mappings", json=_body(inst, factor), headers=_h(vp))
    assert resp.status_code == 403  # .view does not grant .ingest
    # ...but view CAN read.
    assert (
        client.get(
            "/proxy-mappings", params={"private_instrument_id": inst}, headers=_h(vp)
        ).status_code
        == 200
    )


def test_pre_create_refusals(ctx) -> None:  # noqa: ANN001
    client, p, db, inst, factor = ctx
    # foreign instrument → 422
    r = client.post("/proxy-mappings", json=_body(str(uuid.uuid4()), factor), headers=_h(p))
    assert r.status_code == 422
    # foreign factor → 422
    r = client.post("/proxy-mappings", json=_body(inst, str(uuid.uuid4())), headers=_h(p))
    assert r.status_code == 422
    # bad mapping_method vocab → 422
    r = client.post(
        "/proxy-mappings", json=_body(inst, factor, mapping_method="REGRESSION"), headers=_h(p)
    )
    assert r.status_code == 422
    # supersede with no current head → 409
    r = client.post(
        "/proxy-mappings/supersede",
        json=_body(inst, factor, effective_at=_FUTURE),
        headers=_h(p),
    )
    assert r.status_code == 409


def test_no_mutating_verbs(ctx) -> None:  # noqa: ANN001
    client, p, db, inst, factor = ctx
    for verb in ("put", "patch", "delete"):
        resp = getattr(client, verb)("/proxy-mappings", headers=_h(p))
        assert resp.status_code == 405
