"""End-to-end tests of the P1C-2 transaction endpoints (IA append-only, capture-only).

SQLite has no RLS (isolation + the P0001 trigger are proven in the PG file); here we prove
entitlement
gating (deny-by-default; view-only cannot record), server-side tenant stamping, the record / reverse
dispatch, 404 for cross-tenant/unknown portfolio/instrument/transaction, the reversal-as-new-record
(linked + original preserved), the filters, and that there is NO update/delete endpoint (405).
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

from irp_backend.api.transactions import router as transactions_router
from irp_backend.deps import get_db
from irp_shared.audit.models import AuditEvent
from irp_shared.db.session import make_engine, make_session_factory
from irp_shared.entitlement.models import AppUser, Permission, Role, RolePermission, UserRole
from irp_shared.entitlement.service import Principal
from irp_shared.models import Base
from irp_shared.portfolio import PortfolioActor, create_portfolio
from irp_shared.reference.instrument import create_instrument
from irp_shared.reference.service import ReferenceActor
from irp_shared.transaction.models import Transaction


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
    recorder = _grant(db, tenant_id, ("transaction.view", "transaction.record"))  # data_steward eq
    viewer = _grant(db, tenant_id, ("transaction.view",))  # read-tier; cannot record
    pf = create_portfolio(
        db,
        tenant_id=tenant_id,
        code="PF",
        name="pf",
        node_type="ACCOUNT",
        actor=PortfolioActor(actor_id=recorder.user_id),
    )
    inst = create_instrument(
        db,
        tenant_id=tenant_id,
        code="BOND1",
        name="b",
        asset_class="BOND",
        actor=ReferenceActor(actor_id=recorder.user_id),
    )
    db.commit()

    def _override_db() -> Iterator[Session]:
        yield db

    app = FastAPI()
    app.include_router(transactions_router)
    app.dependency_overrides[get_db] = _override_db
    try:
        yield TestClient(app), recorder, viewer, db, pf.id, inst.id
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
        "txn_type": "BUY",
        "trade_date": "2026-03-01",
        "quantity": "100",
    }
    base.update(kw)
    return base


def _record(client: TestClient, p: Principal, pf_id: str, inst_id: str, **kw) -> dict:  # noqa: ANN003
    r = client.post("/transactions", json=_body(pf_id, inst_id, **kw), headers=_h(p))
    assert r.status_code == 201, r.text
    return r.json()


def test_record_201_stamps_tenant_and_audits(ctx) -> None:  # noqa: ANN001
    client, recorder, _v, db, pf_id, inst_id = ctx
    out = _record(client, recorder, pf_id, inst_id, gross_amount="1000")
    assert out["txn_type"] == "BUY" and out["reverses_transaction_id"] is None
    txn = db.get(Transaction, out["id"])
    assert txn is not None and txn.tenant_id == recorder.tenant_id
    n = db.execute(
        select(func.count()).select_from(AuditEvent).where(AuditEvent.entity_id == out["id"])
    ).scalar_one()
    assert n == 1


def test_record_denied_no_perm(ctx) -> None:  # noqa: ANN001
    client, recorder, _v, db, pf_id, inst_id = ctx
    r = client.post("/transactions", json=_body(pf_id, inst_id), headers=_no_perm(recorder))
    assert r.status_code == 403
    assert db.execute(select(func.count()).select_from(Transaction)).scalar_one() == 0


def test_viewer_cannot_record(ctx) -> None:  # noqa: ANN001
    client, _r, viewer, _db, pf_id, inst_id = ctx
    r = client.post("/transactions", json=_body(pf_id, inst_id), headers=_h(viewer))
    assert r.status_code == 403  # transaction.view does not grant record


def test_record_unknown_portfolio_404(ctx) -> None:  # noqa: ANN001
    client, recorder, _v, _db, _pf, inst_id = ctx
    r = client.post("/transactions", json=_body(str(uuid.uuid4()), inst_id), headers=_h(recorder))
    assert r.status_code == 404


def test_record_unknown_instrument_404(ctx) -> None:  # noqa: ANN001
    client, recorder, _v, _db, pf_id, _inst = ctx
    r = client.post("/transactions", json=_body(pf_id, str(uuid.uuid4())), headers=_h(recorder))
    assert r.status_code == 404


def test_get_and_404(ctx) -> None:  # noqa: ANN001
    client, recorder, _v, _db, pf_id, inst_id = ctx
    out = _record(client, recorder, pf_id, inst_id)
    assert client.get(f"/transactions/{out['id']}", headers=_h(recorder)).status_code == 200
    assert client.get(f"/transactions/{uuid.uuid4()}", headers=_h(recorder)).status_code == 404


def test_bad_uuid_422(ctx) -> None:  # noqa: ANN001
    client, recorder, _v, _db, _pf, _inst = ctx
    assert client.get("/transactions/not-a-uuid", headers=_h(recorder)).status_code == 422


def test_reverse_books_linked_record(ctx) -> None:  # noqa: ANN001
    client, recorder, _v, db, pf_id, inst_id = ctx
    original = _record(client, recorder, pf_id, inst_id, quantity="100")
    r = client.post(
        f"/transactions/{original['id']}/reverse", json={"reason": "err"}, headers=_h(recorder)
    )
    assert r.status_code == 201, r.text
    reversal = r.json()
    assert reversal["reverses_transaction_id"] == original["id"]
    assert reversal["txn_type"] == "REVERSAL" and reversal["quantity"] == "-100.00000000"
    # original preserved + exactly two rows.
    assert db.execute(select(func.count()).select_from(Transaction)).scalar_one() == 2


def test_reverse_unknown_404(ctx) -> None:  # noqa: ANN001
    client, recorder, _v, _db, _pf, _inst = ctx
    r = client.post(f"/transactions/{uuid.uuid4()}/reverse", json={}, headers=_h(recorder))
    assert r.status_code == 404


def test_list_filter(ctx) -> None:  # noqa: ANN001
    client, recorder, _v, _db, pf_id, inst_id = ctx
    _record(client, recorder, pf_id, inst_id, txn_type="BUY")
    _record(client, recorder, pf_id, inst_id, txn_type="SELL")
    sells = client.get("/transactions?txn_type=SELL", headers=_h(recorder)).json()
    assert [t["txn_type"] for t in sells] == ["SELL"]
    by_pf = client.get(f"/transactions?portfolio_id={pf_id}", headers=_h(recorder)).json()
    assert len(by_pf) == 2


def test_no_update_or_delete_endpoint(ctx) -> None:  # noqa: ANN001
    client, recorder, _v, _db, pf_id, inst_id = ctx
    out = _record(client, recorder, pf_id, inst_id)
    # immutable: no PUT/PATCH/DELETE route exists -> 405 Method Not Allowed.
    assert (
        client.put(f"/transactions/{out['id']}", json={}, headers=_h(recorder)).status_code == 405
    )
    assert client.delete(f"/transactions/{out['id']}", headers=_h(recorder)).status_code == 405
