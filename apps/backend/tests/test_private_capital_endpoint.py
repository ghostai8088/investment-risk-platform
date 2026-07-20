"""End-to-end tests of the CC-1 private-capital endpoints (ENT-015/016; the three-code mint).

SQLite has no RLS (isolation + trigger proofs live in
``packages/shared-python/tests/test_private_capital_pg.py``); here we prove the
entitlement gating on the minted verbs (deny-by-default; view cannot write; **each maker
verb bites only its own surface** — edit cannot record, record cannot edit), the
commitment capture + supersede + correct + as-of + list round-trip (fixed-point decimal
serialization; the currency chain-immutability 422; the duplicate-current 409), the
event round-trip (no-commitment 409; wrong-currency 422; the negation reversal with the
Σ self-correction; double-reversal 422; foreign-id 404), and the rule-7 list filters.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from decimal import Decimal

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from irp_backend.api.private_capital import router as private_capital_router
from irp_backend.deps import get_db
from irp_shared.db.session import make_engine, make_session_factory
from irp_shared.entitlement.models import AppUser, Permission, Role, RolePermission, UserRole
from irp_shared.entitlement.service import Principal
from irp_shared.models import Base
from irp_shared.portfolio import PortfolioActor, create_portfolio
from irp_shared.reference.instrument import create_instrument
from irp_shared.reference.service import ReferenceActor

_ALL = ("commitment.view", "commitment.edit", "commitment.record")
_FUTURE = "2027-01-01T00:00:00+00:00"
_FAR = "2030-01-01T00:00:00+00:00"


@pytest.fixture
def ctx() -> Iterator[tuple[TestClient, dict[str, Principal], Session, str, str]]:
    engine = make_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    db = make_session_factory(engine)()

    tenant_id = str(uuid.uuid4())
    perms: dict[str, Permission] = {}
    for code in _ALL:
        perm = Permission(code=code, description="d")
        db.add(perm)
        db.flush()
        perms[code] = perm

    principals: dict[str, Principal] = {}
    grant_sets = {
        "full": _ALL,
        "view": ("commitment.view",),
        "edit": ("commitment.view", "commitment.edit"),
        "record": ("commitment.view", "commitment.record"),
        "none": (),
    }
    for name, codes in grant_sets.items():
        user = AppUser(tenant_id=tenant_id, display_name=name)
        role = Role(tenant_id=tenant_id, code=f"r-{name}", name=name)
        db.add_all([user, role])
        db.flush()
        for code in codes:
            db.add(RolePermission(role_id=role.id, permission_id=perms[code].id))
        db.add(UserRole(tenant_id=tenant_id, user_id=user.id, role_id=role.id))
        db.flush()
        principals[name] = Principal(user_id=user.id, tenant_id=tenant_id)

    pf = create_portfolio(
        db,
        tenant_id=tenant_id,
        code="PF",
        name="pf",
        node_type="ACCOUNT",
        actor=PortfolioActor(actor_id="s"),
    ).id
    fund = create_instrument(
        db,
        tenant_id=tenant_id,
        code=f"PE-{uuid.uuid4().hex[:6]}",
        name="Fund",
        asset_class="PRIVATE_EQUITY",
        actor=ReferenceActor(actor_id="s"),
    ).id
    db.commit()

    def _override_db() -> Iterator[Session]:
        yield db

    app = FastAPI()
    app.include_router(private_capital_router)
    app.dependency_overrides[get_db] = _override_db
    try:
        yield TestClient(app), principals, db, pf, fund
    finally:
        db.close()
        engine.dispose()


def _h(p: Principal) -> dict[str, str]:
    return {"X-User-Id": p.user_id, "X-Tenant-Id": p.tenant_id}


def _commitment_body(pf: str, fund: str, **kw) -> dict:  # noqa: ANN003
    return {
        "portfolio_id": pf,
        "instrument_id": fund,
        "committed_amount": "25000000.000000",
        "currency_code": "USD",
        "commitment_date": "2026-01-15",
        **kw,
    }


def _call_body(pf: str, fund: str, **kw) -> dict:  # noqa: ANN003
    return {
        "portfolio_id": pf,
        "instrument_id": fund,
        "event_date": "2026-02-10",
        "amount": "5000000.000000",
        "currency_code": "USD",
        "call_type": "DRAWDOWN",
        **kw,
    }


def test_commitment_roundtrip(ctx) -> None:  # noqa: ANN001
    client, P, db, pf, fund = ctx
    p = P["full"]
    resp = client.post("/commitments", json=_commitment_body(pf, fund), headers=_h(p))
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["record_version"] == 1
    assert Decimal(body["committed_amount"]) == Decimal("25000000.000000")
    assert "E" not in str(body["committed_amount"])  # never scientific
    # duplicate current head -> 409 via the partial-unique
    dup = client.post("/commitments", json=_commitment_body(pf, fund), headers=_h(p))
    assert dup.status_code == 409
    # supersede in the future window; currency change refused 422 (chain-immutable)
    bad = client.post(
        "/commitments/supersede",
        json=_commitment_body(pf, fund, currency_code="EUR", effective_at=_FUTURE),
        headers=_h(p),
    )
    assert bad.status_code == 422
    sup = client.post(
        "/commitments/supersede",
        json=_commitment_body(pf, fund, committed_amount="35000000.000000", effective_at=_FUTURE),
        headers=_h(p),
    )
    assert sup.status_code == 201 and sup.json()["record_version"] == 2
    # correct (system-axis) with a reason; no currency field exists on the body
    cor = client.post(
        "/commitments/correct",
        json={
            "portfolio_id": pf,
            "instrument_id": fund,
            "committed_amount": "36000000.000000",
            "restatement_reason": "restated",
        },
        headers=_h(p),
    )
    assert cor.status_code == 201 and cor.json()["restatement_reason"] == "restated"
    # as-of at the FAR future knows the corrected head
    asof = client.get(
        "/commitments/as-of",
        params={
            "portfolio_id": pf,
            "instrument_id": fund,
            "valid_at": _FAR,
            "known_at": _FAR,
        },
        headers=_h(p),
    )
    assert asof.status_code == 200
    assert Decimal(asof.json()["committed_amount"]) == Decimal("36000000.000000")
    # list + rule-7 filters
    lst = client.get("/commitments", params={"portfolio_id": pf}, headers=_h(p))
    assert lst.status_code == 200 and len(lst.json()["items"]) == 1
    empty = client.get("/commitments", params={"portfolio_id": str(uuid.uuid4())}, headers=_h(p))
    assert empty.status_code == 200 and empty.json()["items"] == []


def test_event_roundtrip_and_reversal(ctx) -> None:  # noqa: ANN001
    client, P, db, pf, fund = ctx
    p = P["full"]
    # no current commitment -> 409
    early = client.post("/capital-calls", json=_call_body(pf, fund), headers=_h(p))
    assert early.status_code == 409
    client.post("/commitments", json=_commitment_body(pf, fund), headers=_h(p))
    # wrong currency -> 422; bad vocab -> 422
    assert (
        client.post(
            "/capital-calls", json=_call_body(pf, fund, currency_code="EUR"), headers=_h(p)
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/capital-calls", json=_call_body(pf, fund, call_type="BOGUS"), headers=_h(p)
        ).status_code
        == 422
    )
    call = client.post("/capital-calls", json=_call_body(pf, fund), headers=_h(p))
    assert call.status_code == 201
    call_id = call.json()["id"]
    # reverse: negation + echo; double-reverse 422; foreign id 404
    rev = client.post(
        "/capital-calls/reverse",
        json={"event_id": call_id, "reason": "mis-captured"},
        headers=_h(p),
    )
    assert rev.status_code == 201
    assert Decimal(rev.json()["amount"]) == Decimal("-5000000.000000")
    assert rev.json()["reverses_id"] == call_id
    dup = client.post(
        "/capital-calls/reverse",
        json={"event_id": call_id, "reason": "again"},
        headers=_h(p),
    )
    assert dup.status_code == 422
    missing = client.post(
        "/capital-calls/reverse",
        json={"event_id": str(uuid.uuid4()), "reason": "x"},
        headers=_h(p),
    )
    assert missing.status_code == 404
    # list: Σ self-corrects to zero over the pair
    lst = client.get(
        "/capital-calls", params={"portfolio_id": pf, "instrument_id": fund}, headers=_h(p)
    )
    assert lst.status_code == 200
    amounts = [Decimal(i["amount"]) for i in lst.json()["items"]]
    assert sum(amounts) == Decimal("0")
    # distribution with the recallable flag + reversal echo
    dist = client.post(
        "/distributions",
        json={
            "portfolio_id": pf,
            "instrument_id": fund,
            "event_date": "2026-05-20",
            "amount": "1500000.000000",
            "currency_code": "USD",
            "distribution_type": "RETURN_OF_CAPITAL",
            "is_recallable": True,
        },
        headers=_h(p),
    )
    assert dist.status_code == 201 and dist.json()["is_recallable"] is True
    drev = client.post(
        "/distributions/reverse",
        json={"event_id": dist.json()["id"], "reason": "err"},
        headers=_h(p),
    )
    assert drev.status_code == 201 and drev.json()["is_recallable"] is True
    assert Decimal(drev.json()["amount"]) == Decimal("-1500000.000000")


def test_permission_parity_each_verb_bites_its_own_surface(ctx) -> None:  # noqa: ANN001
    client, P, db, pf, fund = ctx
    # none: every surface 403 (deny-by-default)
    for method, path, body in (
        ("get", "/commitments", None),
        ("post", "/commitments", _commitment_body(pf, fund)),
        ("post", "/capital-calls", _call_body(pf, fund)),
    ):
        resp = getattr(client, method)(
            path, **({"json": body} if body else {}), headers=_h(P["none"])
        )
        assert resp.status_code == 403, f"{method} {path}: {resp.status_code}"
    # view: reads pass, ALL writes 403
    assert client.get("/commitments", headers=_h(P["view"])).status_code == 200
    assert (
        client.post(
            "/commitments", json=_commitment_body(pf, fund), headers=_h(P["view"])
        ).status_code
        == 403
    )
    assert (
        client.post("/capital-calls", json=_call_body(pf, fund), headers=_h(P["view"])).status_code
        == 403
    )
    # edit: commitment writes pass; event writes 403 (the FR maker cannot record)
    assert (
        client.post(
            "/commitments", json=_commitment_body(pf, fund), headers=_h(P["edit"])
        ).status_code
        == 201
    )
    assert (
        client.post("/capital-calls", json=_call_body(pf, fund), headers=_h(P["edit"])).status_code
        == 403
    )
    # record: event writes pass; commitment writes 403 (the IA maker cannot edit)
    assert (
        client.post(
            "/capital-calls", json=_call_body(pf, fund), headers=_h(P["record"])
        ).status_code
        == 201
    )
    assert (
        client.post(
            "/commitments/correct",
            json={
                "portfolio_id": pf,
                "instrument_id": fund,
                "committed_amount": "1.000000",
                "restatement_reason": "r",
            },
            headers=_h(P["record"]),
        ).status_code
        == 403
    )
