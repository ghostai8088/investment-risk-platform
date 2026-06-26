"""End-to-end tests of the P2-1 dataset_snapshot endpoints (POST /snapshots, GET, GET /verify).

SQLite has no RLS, so cross-tenant isolation + the append-only trigger are proven in
``packages/shared-python/tests/test_snapshot_pg.py``; here we prove entitlement gating (deny-by-
default,
no DB side-effect on denial), server-side tenant stamping, the create->read->verify round-trip, the
completeness 409 (a bound position without a mark), and 404/422 mapping.
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

from irp_backend.api.snapshots import router as snapshots_router
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
from irp_shared.snapshot import DatasetSnapshot
from irp_shared.valuation import create_valuation
from irp_shared.valuation.service import ValuationActor

_PERMS = ("snapshot.view", "snapshot.create")
_VALID_AT = datetime(2026, 6, 1, tzinfo=UTC)
_VD = date(2026, 3, 31)


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
    app.include_router(snapshots_router)
    app.dependency_overrides[get_db] = _override_db
    try:
        yield TestClient(app), principal, db
    finally:
        db.close()
        engine.dispose()


def _headers(p: Principal) -> dict[str, str]:
    return {"X-User-Id": p.user_id, "X-Tenant-Id": p.tenant_id}


def _no_perm_headers(p: Principal) -> dict[str, str]:
    return {"X-User-Id": str(uuid.uuid4()), "X-Tenant-Id": p.tenant_id}


def _seed_complete(db: Session, tenant: str) -> str:
    """A complete portfolio (1 instrument, 1 position, 1 marked valuation). Returns pf id."""
    pf = create_portfolio(
        db,
        tenant_id=tenant,
        code="PF",
        name="pf",
        node_type="ACCOUNT",
        actor=PortfolioActor(actor_id="steward"),
    )
    inst = create_instrument(
        db,
        tenant_id=tenant,
        code="INST",
        name="i",
        asset_class="BOND",
        actor=ReferenceActor(actor_id="steward"),
    )
    create_position(
        db,
        portfolio_id=pf.id,
        instrument_id=inst.id,
        acting_tenant=tenant,
        actor=PositionActor(actor_id="steward"),
        quantity=Decimal("100"),
        valid_from=_VALID_AT,
    )
    create_valuation(
        db,
        portfolio_id=pf.id,
        instrument_id=inst.id,
        valuation_date=_VD,
        acting_tenant=tenant,
        actor=ValuationActor(actor_id="steward"),
        mark_value=Decimal("12.50"),
        valid_from=_VALID_AT,
    )
    db.commit()
    return pf.id


def _seed_gap(db: Session, tenant: str) -> str:
    """A portfolio with a non-zero position but NO mark (a completeness gap). Returns pf id."""
    pf = create_portfolio(
        db,
        tenant_id=tenant,
        code="GAP",
        name="gap",
        node_type="ACCOUNT",
        actor=PortfolioActor(actor_id="steward"),
    )
    inst = create_instrument(
        db,
        tenant_id=tenant,
        code="GINST",
        name="i",
        asset_class="BOND",
        actor=ReferenceActor(actor_id="steward"),
    )
    create_position(
        db,
        portfolio_id=pf.id,
        instrument_id=inst.id,
        acting_tenant=tenant,
        actor=PositionActor(actor_id="steward"),
        quantity=Decimal("100"),
        valid_from=_VALID_AT,
    )
    db.commit()
    return pf.id


def _create(client: TestClient, principal: Principal, pf_id: str, **kw) -> dict:  # noqa: ANN003
    body = {
        "portfolio_id": pf_id,
        "as_of_valid_at": _VALID_AT.isoformat(),
        "purpose": "TEST",
        "as_of_valuation_date": _VD.isoformat(),
        **kw,
    }
    return client.post("/snapshots", json=body, headers=_headers(principal))


def test_create_snapshot_201_stamps_tenant_and_audits(
    ctx: tuple[TestClient, Principal, Session],
) -> None:
    client, principal, db = ctx
    pf_id = _seed_complete(db, principal.tenant_id)
    resp = _create(client, principal, pf_id)
    assert resp.status_code == 201, resp.text
    payload = resp.json()
    assert payload["snapshot"]["tenant_id"] == principal.tenant_id  # server-stamped
    assert payload["snapshot"]["component_count"] == 3  # 1 portfolio + 1 position + 1 valuation
    # The 201 body carries the components (not an empty list): the response is built pre-commit so
    # the tenant-scoped read is not blanked by the post-commit GUC clear under PG FORCE RLS.
    assert len(payload["components"]) == payload["snapshot"]["component_count"]
    assert len(payload["snapshot"]["manifest_hash"]) == 64
    row = db.execute(select(DatasetSnapshot)).scalar_one()
    assert row.tenant_id == principal.tenant_id
    assert (
        db.execute(
            select(func.count())
            .select_from(AuditEvent)
            .where(AuditEvent.event_type == "SNAPSHOT.CREATE")
        ).scalar_one()
        == 1
    )


def test_create_without_create_perm_403_no_write(
    ctx: tuple[TestClient, Principal, Session],
) -> None:
    client, principal, db = ctx
    pf_id = _seed_complete(db, principal.tenant_id)
    resp = client.post(
        "/snapshots",
        json={"portfolio_id": pf_id, "as_of_valid_at": _VALID_AT.isoformat(), "purpose": "TEST"},
        headers=_no_perm_headers(principal),
    )
    assert resp.status_code == 403
    assert db.execute(select(func.count()).select_from(DatasetSnapshot)).scalar_one() == 0


def test_get_snapshot_round_trips(ctx: tuple[TestClient, Principal, Session]) -> None:
    client, principal, db = ctx
    pf_id = _seed_complete(db, principal.tenant_id)
    created = _create(client, principal, pf_id).json()
    sid = created["snapshot"]["id"]
    got = client.get(f"/snapshots/{sid}", headers=_headers(principal))
    assert got.status_code == 200
    assert got.json()["snapshot"]["manifest_hash"] == created["snapshot"]["manifest_hash"]
    assert len(got.json()["components"]) == created["snapshot"]["component_count"]


def test_verify_ok_after_create(ctx: tuple[TestClient, Principal, Session]) -> None:
    client, principal, db = ctx
    pf_id = _seed_complete(db, principal.tenant_id)
    sid = _create(client, principal, pf_id).json()["snapshot"]["id"]
    resp = client.get(f"/snapshots/{sid}/verify", headers=_headers(principal))
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True and body["drifted_components"] == []


def test_get_unknown_snapshot_404(ctx: tuple[TestClient, Principal, Session]) -> None:
    client, principal, _ = ctx
    resp = client.get(f"/snapshots/{uuid.uuid4()}", headers=_headers(principal))
    assert resp.status_code == 404


def test_create_over_incomplete_scope_409(ctx: tuple[TestClient, Principal, Session]) -> None:
    client, principal, db = ctx
    pf_id = _seed_gap(db, principal.tenant_id)
    resp = _create(client, principal, pf_id)
    assert resp.status_code == 409  # completeness gap — fail closed
    assert db.execute(select(func.count()).select_from(DatasetSnapshot)).scalar_one() == 0


def test_invalid_purpose_422(ctx: tuple[TestClient, Principal, Session]) -> None:
    client, principal, db = ctx
    pf_id = _seed_complete(db, principal.tenant_id)
    resp = _create(client, principal, pf_id, purpose="BOGUS")
    assert resp.status_code == 422


def test_malformed_portfolio_id_422(ctx: tuple[TestClient, Principal, Session]) -> None:
    client, principal, _ = ctx
    resp = client.post(
        "/snapshots",
        json={"portfolio_id": "not-a-uuid", "as_of_valid_at": _VALID_AT.isoformat()},
        headers=_headers(principal),
    )
    assert resp.status_code == 422
