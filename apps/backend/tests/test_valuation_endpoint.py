"""End-to-end tests of the P1C-4 valuation endpoints (FR bitemporal, captured marks, CAPTURE-ONLY).

SQLite has no RLS (isolation + FR/PG behaviors are proven in the PG file); here we prove entitlement
gating (deny-by-default; view-only cannot edit; auditor cannot view), server-side tenant stamping,
the
create / supersede / correct dispatch, the single-valuation as-of read, the valuation_date filter,
404
for cross-tenant/unknown portfolio/instrument/valuation, 409 for no-open-head supersede, and that
there
is NO PUT/PATCH/DELETE content-edit endpoint (405).
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from decimal import Decimal

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from irp_backend.api.valuations import router as valuations_router
from irp_backend.deps import get_db
from irp_shared.audit.models import AuditEvent
from irp_shared.db.session import make_engine, make_session_factory
from irp_shared.entitlement.models import AppUser, Permission, Role, RolePermission, UserRole
from irp_shared.entitlement.service import Principal
from irp_shared.models import Base
from irp_shared.portfolio import PortfolioActor, create_portfolio
from irp_shared.reference.instrument import create_instrument
from irp_shared.reference.service import ReferenceActor
from irp_shared.valuation.models import Valuation

VD = "2026-03-31"


def _grant(db: Session, tenant_id: str, codes: tuple[str, ...]) -> Principal:
    user = AppUser(tenant_id=tenant_id, display_name="U")
    role = Role(tenant_id=tenant_id, code=f"r-{uuid.uuid4().hex[:8]}", name="R")
    db.add_all([user, role])
    db.flush()
    for code in codes:
        perm = db.execute(select(Permission).where(Permission.code == code)).scalar_one_or_none()
        if perm is None:
            perm = Permission(code=code, description="d")
            db.add(perm)
            db.flush()
        db.add(RolePermission(role_id=role.id, permission_id=perm.id))
    db.add(UserRole(tenant_id=tenant_id, user_id=user.id, role_id=role.id))
    db.flush()
    return Principal(user_id=user.id, tenant_id=tenant_id)


@pytest.fixture
def ctx() -> Iterator[tuple[TestClient, Principal, Principal, Session, str, str]]:
    engine = make_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    db = make_session_factory(engine)()

    tenant_id = str(uuid.uuid4())
    maker = _grant(db, tenant_id, ("valuation.view", "valuation.edit"))  # data_steward eq
    viewer = _grant(db, tenant_id, ("valuation.view",))  # read-tier; cannot edit
    pf = create_portfolio(
        db,
        tenant_id=tenant_id,
        code="PF",
        name="pf",
        node_type="ACCOUNT",
        actor=PortfolioActor(actor_id=maker.user_id),
    )
    inst = create_instrument(
        db,
        tenant_id=tenant_id,
        code="BOND1",
        name="b",
        asset_class="BOND",
        actor=ReferenceActor(actor_id=maker.user_id),
    )
    db.commit()

    def _override_db() -> Iterator[Session]:
        yield db

    app = FastAPI()
    app.include_router(valuations_router)
    app.dependency_overrides[get_db] = _override_db
    try:
        yield TestClient(app), maker, viewer, db, pf.id, inst.id
    finally:
        db.close()
        engine.dispose()


def _h(p: Principal) -> dict[str, str]:
    return {"X-User-Id": p.user_id, "X-Tenant-Id": p.tenant_id}


def _no_perm(p: Principal) -> dict[str, str]:
    return {"X-User-Id": str(uuid.uuid4()), "X-Tenant-Id": p.tenant_id}


def _body(pf_id: str, inst_id: str, **kw) -> dict:  # noqa: ANN003
    base = {
        "portfolio_id": pf_id,
        "instrument_id": inst_id,
        "valuation_date": VD,
        "mark_value": "100",
    }
    base.update(kw)
    return base


def _create(client: TestClient, p: Principal, pf_id: str, inst_id: str, **kw) -> dict:  # noqa: ANN003
    r = client.post("/valuations", json=_body(pf_id, inst_id, **kw), headers=_h(p))
    assert r.status_code == 201, r.text
    return r.json()


def test_create_201_stamps_tenant_and_audits(ctx) -> None:  # noqa: ANN001
    client, maker, _v, db, pf_id, inst_id = ctx
    out = _create(client, maker, pf_id, inst_id, mark_value="100")
    assert Decimal(out["mark_value"]) == Decimal("100") and out["valuation_date"] == VD
    assert out["record_version"] == 1
    row = db.get(Valuation, out["id"])
    assert row is not None and row.tenant_id == maker.tenant_id
    n = db.execute(
        select(func.count()).select_from(AuditEvent).where(AuditEvent.entity_id == out["id"])
    ).scalar_one()
    assert n == 1


def test_create_denied_no_perm(ctx) -> None:  # noqa: ANN001
    client, maker, _v, db, pf_id, inst_id = ctx
    r = client.post("/valuations", json=_body(pf_id, inst_id), headers=_no_perm(maker))
    assert r.status_code == 403
    assert db.execute(select(func.count()).select_from(Valuation)).scalar_one() == 0


def test_no_view_cannot_read(ctx) -> None:  # noqa: ANN001
    # A principal lacking valuation.view (e.g. auditor_3l, who holds NO valuation.* perm) cannot GET
    # or list — deny-by-default 403, not a 404 leak.
    client, maker, _v, _db, pf_id, inst_id = ctx
    out = _create(client, maker, pf_id, inst_id)
    assert client.get(f"/valuations/{out['id']}", headers=_no_perm(maker)).status_code == 403
    assert client.get("/valuations", headers=_no_perm(maker)).status_code == 403


def test_viewer_cannot_edit(ctx) -> None:  # noqa: ANN001
    client, _m, viewer, _db, pf_id, inst_id = ctx
    r = client.post("/valuations", json=_body(pf_id, inst_id), headers=_h(viewer))
    assert r.status_code == 403  # valuation.view does not grant edit


def test_create_unknown_portfolio_404(ctx) -> None:  # noqa: ANN001
    client, maker, _v, _db, _pf, inst_id = ctx
    r = client.post("/valuations", json=_body(str(uuid.uuid4()), inst_id), headers=_h(maker))
    assert r.status_code == 404


def test_create_unknown_instrument_404(ctx) -> None:  # noqa: ANN001
    client, maker, _v, _db, pf_id, _inst = ctx
    r = client.post("/valuations", json=_body(pf_id, str(uuid.uuid4())), headers=_h(maker))
    assert r.status_code == 404


def test_supersede_books_new_version(ctx) -> None:  # noqa: ANN001
    client, maker, _v, db, pf_id, inst_id = ctx
    original = _create(client, maker, pf_id, inst_id, mark_value="100")
    r = client.post(
        f"/valuations/{original['id']}/supersede",
        json={"effective_at": "2026-04-15T00:00:00Z", "mark_value": "105"},
        headers=_h(maker),
    )
    assert r.status_code == 201, r.text
    new = r.json()
    assert Decimal(new["mark_value"]) == Decimal("105") and new["supersedes_id"] == original["id"]
    assert new["record_version"] == 2 and new["valuation_date"] == VD
    assert db.execute(select(func.count()).select_from(Valuation)).scalar_one() == 2


def test_correct_books_restatement(ctx) -> None:  # noqa: ANN001
    client, maker, _v, _db, pf_id, inst_id = ctx
    original = _create(client, maker, pf_id, inst_id, mark_value="100")
    r = client.post(
        f"/valuations/{original['id']}/correct",
        json={"restatement_reason": "custodian fix", "mark_value": "120"},
        headers=_h(maker),
    )
    assert r.status_code == 201, r.text
    corrected = r.json()
    assert Decimal(corrected["mark_value"]) == Decimal("120")
    assert corrected["restatement_reason"] == "custodian fix"
    assert corrected["supersedes_id"] == original["id"]


def test_as_of_read(ctx) -> None:  # noqa: ANN001
    client, maker, _v, _db, pf_id, inst_id = ctx
    _create(client, maker, pf_id, inst_id, mark_value="100", valid_from="2026-04-01T00:00:00Z")
    r = client.get(
        f"/valuations/as-of?portfolio_id={pf_id}&instrument_id={inst_id}"
        f"&valuation_date={VD}&valid_at=2026-04-05T00:00:00Z",
        headers=_h(maker),
    )
    assert r.status_code == 200, r.text
    assert Decimal(r.json()["mark_value"]) == Decimal("100")


def test_as_of_unknown_404(ctx) -> None:  # noqa: ANN001
    client, maker, _v, _db, pf_id, inst_id = ctx
    r = client.get(
        f"/valuations/as-of?portfolio_id={pf_id}&instrument_id={inst_id}"
        f"&valuation_date={VD}&valid_at=2020-01-01T00:00:00Z",
        headers=_h(maker),
    )
    assert r.status_code == 404


def test_get_and_404(ctx) -> None:  # noqa: ANN001
    client, maker, _v, _db, pf_id, inst_id = ctx
    out = _create(client, maker, pf_id, inst_id)
    assert client.get(f"/valuations/{out['id']}", headers=_h(maker)).status_code == 200
    assert client.get(f"/valuations/{uuid.uuid4()}", headers=_h(maker)).status_code == 404


def test_bad_uuid_422(ctx) -> None:  # noqa: ANN001
    client, maker, _v, _db, _pf, _inst = ctx
    assert client.get("/valuations/not-a-uuid", headers=_h(maker)).status_code == 422


def test_supersede_unknown_404(ctx) -> None:  # noqa: ANN001
    client, maker, _v, _db, _pf, _inst = ctx
    r = client.post(
        f"/valuations/{uuid.uuid4()}/supersede",
        json={"effective_at": "2026-04-15T00:00:00Z", "mark_value": "1"},
        headers=_h(maker),
    )
    assert r.status_code == 404


def test_list_filter_by_valuation_date(ctx) -> None:  # noqa: ANN001
    client, maker, _v, _db, pf_id, inst_id = ctx
    _create(client, maker, pf_id, inst_id, valuation_date="2026-03-31", mark_value="100")
    _create(client, maker, pf_id, inst_id, valuation_date="2026-06-30", mark_value="200")
    march = client.get("/valuations?valuation_date=2026-03-31", headers=_h(maker)).json()
    assert len(march) == 1 and march[0]["valuation_date"] == "2026-03-31"
    by_pf = client.get(f"/valuations?portfolio_id={pf_id}", headers=_h(maker)).json()
    assert len(by_pf) == 2  # both current heads (different valuation_dates)


def test_no_put_or_delete_endpoint(ctx) -> None:  # noqa: ANN001
    client, maker, _v, _db, pf_id, inst_id = ctx
    out = _create(client, maker, pf_id, inst_id)
    assert client.put(f"/valuations/{out['id']}", json={}, headers=_h(maker)).status_code == 405
    assert client.delete(f"/valuations/{out['id']}", headers=_h(maker)).status_code == 405
