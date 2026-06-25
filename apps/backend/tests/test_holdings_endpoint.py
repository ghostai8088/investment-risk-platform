"""End-to-end tests of the P1C-5 holdings endpoint (GET /portfolios/{id}/holdings) — READ-ONLY.

SQLite has no RLS (tenant isolation is proven in the PG file); here we prove the read composition,
entitlement gating (deny-by-default; portfolio.view + position.view required; valuation.view checked
in-handler before any mark lookup; auditor denied), the as-of params, subtree composition, 404 for
unknown/cross-tenant portfolio, 422 for missing valid_at / include_marks-without-valuation_date, 409
for a corrupt subtree, that marks are display-only, and that a holdings read emits ZERO audit events
and exposes NO write method.
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

from irp_backend.api.holdings import router as holdings_router
from irp_backend.deps import get_db
from irp_shared.audit.models import AuditEvent
from irp_shared.db.session import make_engine, make_session_factory
from irp_shared.entitlement.models import AppUser, Permission, Role, RolePermission, UserRole
from irp_shared.entitlement.service import Principal
from irp_shared.models import Base
from irp_shared.portfolio import PortfolioActor, create_portfolio
from irp_shared.position import create_position
from irp_shared.position.service import PositionActor
from irp_shared.reference.instrument import create_instrument
from irp_shared.reference.service import ReferenceActor
from irp_shared.valuation import create_valuation
from irp_shared.valuation.service import ValuationActor

T1 = "2026-06-01T00:00:00+00:00"
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
def ctx() -> Iterator[dict]:
    engine = make_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    db = make_session_factory(engine)()

    tenant_id = str(uuid.uuid4())
    full = _grant(db, tenant_id, ("portfolio.view", "position.view", "valuation.view"))
    no_marks = _grant(db, tenant_id, ("portfolio.view", "position.view"))  # no valuation.view
    no_position = _grant(db, tenant_id, ("portfolio.view",))  # missing position.view
    auditor = _grant(db, tenant_id, ("auditor.something",))  # holds none of the .view perms

    root = create_portfolio(
        db,
        tenant_id=tenant_id,
        code="ROOT",
        name="root",
        node_type="ACCOUNT",
        actor=PortfolioActor(actor_id=full.user_id),
    )
    child = create_portfolio(
        db,
        tenant_id=tenant_id,
        code="CHILD",
        name="child",
        node_type="ACCOUNT",
        parent_portfolio_id=root.id,
        actor=PortfolioActor(actor_id=full.user_id),
    )
    i1 = create_instrument(
        db,
        tenant_id=tenant_id,
        code="I1",
        name="i1",
        asset_class="BOND",
        actor=ReferenceActor(actor_id=full.user_id),
    )
    i2 = create_instrument(
        db,
        tenant_id=tenant_id,
        code="I2",
        name="i2",
        asset_class="BOND",
        actor=ReferenceActor(actor_id=full.user_id),
    )
    create_position(
        db,
        portfolio_id=root.id,
        instrument_id=i1.id,
        acting_tenant=tenant_id,
        actor=PositionActor(actor_id=full.user_id),
        quantity=Decimal("100"),
        valid_from=datetime(2026, 1, 1, tzinfo=UTC),
    )
    create_position(
        db,
        portfolio_id=child.id,
        instrument_id=i2.id,
        acting_tenant=tenant_id,
        actor=PositionActor(actor_id=full.user_id),
        quantity=Decimal("250"),
        valid_from=datetime(2026, 1, 1, tzinfo=UTC),
    )
    create_valuation(
        db,
        portfolio_id=root.id,
        instrument_id=i1.id,
        valuation_date=date(2026, 3, 31),
        acting_tenant=tenant_id,
        actor=ValuationActor(actor_id=full.user_id),
        mark_value=Decimal("101.5"),
        currency_code="USD",
        valid_from=datetime(2026, 1, 1, tzinfo=UTC),  # effective at the test's valid_at=T1
    )
    db.commit()

    def _override_db() -> Iterator[Session]:
        yield db

    app = FastAPI()
    app.include_router(holdings_router)
    app.dependency_overrides[get_db] = _override_db
    try:
        yield {
            "client": TestClient(app),
            "db": db,
            "tenant": tenant_id,
            "full": full,
            "no_marks": no_marks,
            "no_position": no_position,
            "auditor": auditor,
            "root": root.id,
            "child": child.id,
            "i1": i1.id,
            "i2": i2.id,
        }
    finally:
        db.close()
        engine.dispose()


def _h(p: Principal) -> dict[str, str]:
    return {"X-User-Id": p.user_id, "X-Tenant-Id": p.tenant_id}


# --- 200 reads ---


def test_node_level_holdings_200(ctx) -> None:  # noqa: ANN001
    r = ctx["client"].get(
        f"/portfolios/{ctx['root']}/holdings", params={"valid_at": T1}, headers=_h(ctx["full"])
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["subtree"] is False
    assert [h["instrument_id"] for h in body["holdings"]] == [ctx["i1"]]
    assert Decimal(body["holdings"][0]["quantity"]) == Decimal("100")
    assert body["holdings"][0]["mark"] is None  # marks not requested


def test_subtree_holdings_200(ctx) -> None:  # noqa: ANN001
    r = ctx["client"].get(
        f"/portfolios/{ctx['root']}/holdings",
        params={"valid_at": T1, "subtree": "true"},
        headers=_h(ctx["full"]),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["subtree"] is True
    insts = {h["instrument_id"] for h in body["holdings"]}
    assert insts == {ctx["i1"], ctx["i2"]}  # root + child composed


def test_include_marks_display_only(ctx) -> None:  # noqa: ANN001
    r = ctx["client"].get(
        f"/portfolios/{ctx['root']}/holdings",
        params={"valid_at": T1, "include_marks": "true", "valuation_date": VD},
        headers=_h(ctx["full"]),
    )
    assert r.status_code == 200, r.text
    h = r.json()["holdings"][0]
    assert h["mark"] is not None
    assert Decimal(h["mark"]["mark_value"]) == Decimal("101.5")
    assert h["mark"]["currency_code"] == "USD"
    # Display-only: stored quantity + stored mark side by side; no computed market value field.
    assert "market_value" not in h and "market_value" not in h["mark"]


# --- entitlement ---


def test_403_without_portfolio_view(ctx) -> None:  # noqa: ANN001
    # auditor holds none of the .view perms -> denied at the route guard.
    r = ctx["client"].get(
        f"/portfolios/{ctx['root']}/holdings", params={"valid_at": T1}, headers=_h(ctx["auditor"])
    )
    assert r.status_code == 403


def test_403_without_position_view(ctx) -> None:  # noqa: ANN001
    r = ctx["client"].get(
        f"/portfolios/{ctx['root']}/holdings",
        params={"valid_at": T1},
        headers=_h(ctx["no_position"]),
    )
    assert r.status_code == 403


def test_403_include_marks_without_valuation_view_before_lookup(ctx) -> None:  # noqa: ANN001
    # no_marks holds portfolio.view + position.view but NOT valuation.view -> 403 when marks asked.
    r = ctx["client"].get(
        f"/portfolios/{ctx['root']}/holdings",
        params={"valid_at": T1, "include_marks": "true", "valuation_date": VD},
        headers=_h(ctx["no_marks"]),
    )
    assert r.status_code == 403
    # But the same principal CAN read holdings WITHOUT marks (proves the gate is mark-specific).
    ok = ctx["client"].get(
        f"/portfolios/{ctx['root']}/holdings", params={"valid_at": T1}, headers=_h(ctx["no_marks"])
    )
    assert ok.status_code == 200


# --- fail-closed errors ---


def test_404_cross_tenant_or_unknown_portfolio(ctx) -> None:  # noqa: ANN001
    r = ctx["client"].get(
        f"/portfolios/{uuid.uuid4()}/holdings", params={"valid_at": T1}, headers=_h(ctx["full"])
    )
    assert r.status_code == 404


def test_422_missing_valid_at(ctx) -> None:  # noqa: ANN001
    r = ctx["client"].get(f"/portfolios/{ctx['root']}/holdings", headers=_h(ctx["full"]))
    assert r.status_code == 422


def test_422_include_marks_without_valuation_date(ctx) -> None:  # noqa: ANN001
    r = ctx["client"].get(
        f"/portfolios/{ctx['root']}/holdings",
        params={"valid_at": T1, "include_marks": "true"},
        headers=_h(ctx["full"]),
    )
    assert r.status_code == 422


def test_409_corrupt_subtree(ctx) -> None:  # noqa: ANN001
    # Repoint root's parent to child -> a cycle root->child->root; subtree walk raises -> 409.
    from irp_shared.portfolio.models import Portfolio

    db = ctx["db"]
    root = db.get(Portfolio, ctx["root"])
    root.parent_portfolio_id = ctx["child"]
    db.commit()
    r = ctx["client"].get(
        f"/portfolios/{ctx['root']}/holdings",
        params={"valid_at": T1, "subtree": "true"},
        headers=_h(ctx["full"]),
    )
    assert r.status_code == 409


# --- read-only guarantees ---


def test_holdings_read_emits_zero_audit_events(ctx) -> None:  # noqa: ANN001
    before = ctx["db"].execute(select(func.count()).select_from(AuditEvent)).scalar_one()
    ctx["client"].get(
        f"/portfolios/{ctx['root']}/holdings",
        params={"valid_at": T1, "include_marks": "true", "valuation_date": VD},
        headers=_h(ctx["full"]),
    )
    after = ctx["db"].execute(select(func.count()).select_from(AuditEvent)).scalar_one()
    assert before == after  # a read composes; it emits NO audit event


def test_no_write_methods_on_holdings_path(ctx) -> None:  # noqa: ANN001
    # The holdings path exposes only GET — POST/PUT/PATCH/DELETE are 405 (no write surface).
    for method in ("post", "put", "patch", "delete"):
        r = getattr(ctx["client"], method)(
            f"/portfolios/{ctx['root']}/holdings", headers=_h(ctx["full"])
        )
        assert r.status_code == 405, f"{method} should be 405, got {r.status_code}"
