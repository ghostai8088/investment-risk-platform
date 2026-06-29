"""End-to-end tests of the P2-6 benchmark (benchmark + benchmark_constituent) endpoints.

SQLite has no RLS, so cross-tenant isolation is in ``tests/test_benchmark_pg.py``;
here we prove entitlement gating (deny-by-default, no DB side-effect on denial), server-side tenant
stamping, the split audit family (REFERENCE.* definition + MARKET.* membership),
the create / update / capture / supersede / correct / as-of / list round-trip, 403/404/409/422
mapping, and no PUT/PATCH/DELETE. The verbs REUSE marketdata.view/.ingest.
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

from irp_backend.api.marketdata import benchmark_router
from irp_backend.deps import get_db
from irp_shared.audit.models import AuditEvent
from irp_shared.db.session import make_engine, make_session_factory
from irp_shared.entitlement.bootstrap import SYSTEM_TENANT_ID
from irp_shared.entitlement.models import AppUser, Permission, Role, RolePermission, UserRole
from irp_shared.entitlement.service import Principal
from irp_shared.marketdata import Benchmark
from irp_shared.models import Base
from irp_shared.reference.models import Currency, Instrument

_PERMS = ("marketdata.view", "marketdata.ingest")
_VF = datetime(2020, 1, 1, tzinfo=UTC)
_ED = date(2026, 3, 31)


@pytest.fixture
def ctx() -> Iterator[tuple[TestClient, Principal, Session, list[str]]]:
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
    inst_ids: list[str] = []
    for i in range(3):
        inst = Instrument(
            tenant_id=tenant_id,
            code=f"INS{i}",
            name=f"I{i}",
            asset_class="EQUITY",
            instrument_type="EQUITY",
            valid_from=_VF,
            record_version=1,
        )
        db.add(inst)
        db.flush()
        inst_ids.append(inst.id)
    db.commit()
    principal = Principal(user_id=user.id, tenant_id=tenant_id)

    def _override_db() -> Iterator[Session]:
        yield db

    app = FastAPI()
    app.include_router(benchmark_router)
    app.dependency_overrides[get_db] = _override_db
    try:
        yield TestClient(app), principal, db, inst_ids
    finally:
        db.close()
        engine.dispose()


def _h(p: Principal) -> dict[str, str]:
    return {"X-User-Id": p.user_id, "X-Tenant-Id": p.tenant_id}


def _no_perm(p: Principal) -> dict[str, str]:
    return {"X-User-Id": str(uuid.uuid4()), "X-Tenant-Id": p.tenant_id}


def _create_benchmark(client: TestClient, p: Principal, source: str = "SP_DJI", **kw) -> object:  # noqa: ANN003
    body = {
        "benchmark_code": "SPX",
        "benchmark_source": source,
        "benchmark_currency": "USD",
        "index_family": "S&P",
        **kw,
    }
    return client.post("/benchmarks", json=body, headers=_h(p))


def _members(ids: list[str], weights: list[str]) -> list[dict]:
    return [{"instrument_id": i, "weight": w} for i, w in zip(ids, weights, strict=False)]


def test_create_201_stamps_tenant_and_reference_audits(ctx) -> None:  # noqa: ANN001
    client, p, db, _ = ctx
    resp = _create_benchmark(client, p)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["benchmark_code"] == "SPX" and body["record_version"] == 1
    row = db.execute(select(Benchmark)).scalar_one()
    assert row.tenant_id == p.tenant_id
    # the EV definition is audited REFERENCE.CREATE (NOT MARKET.BENCHMARK_CREATE).
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
            .where(AuditEvent.event_type == "MARKET.BENCHMARK_CREATE")
        ).scalar_one()
        == 0
    )


def test_create_without_ingest_403_no_write(ctx) -> None:  # noqa: ANN001
    client, p, db, _ = ctx
    resp = client.post(
        "/benchmarks",
        json={"benchmark_code": "SPX", "benchmark_source": "SP_DJI", "benchmark_currency": "USD"},
        headers=_no_perm(p),
    )
    assert resp.status_code == 403
    assert db.execute(select(func.count()).select_from(Benchmark)).scalar_one() == 0


def test_update_definition_bumps_version(ctx) -> None:  # noqa: ANN001
    client, p, db, _ = ctx
    bid = _create_benchmark(client, p).json()["id"]
    resp = client.post(
        f"/benchmarks/{bid}/update", json={"benchmark_name": "S&P 500"}, headers=_h(p)
    )
    assert resp.status_code == 200 and resp.json()["record_version"] == 2
    assert resp.json()["benchmark_name"] == "S&P 500"
    assert (
        db.execute(
            select(func.count())
            .select_from(AuditEvent)
            .where(AuditEvent.event_type == "REFERENCE.UPDATE")
        ).scalar_one()
        == 1
    )


def test_membership_capture_supersede_correct_as_of(ctx) -> None:  # noqa: ANN001
    client, p, db, ids = ctx
    bid = _create_benchmark(client, p).json()["id"]
    cap = client.post(
        f"/benchmarks/{bid}/membership",
        json={"effective_date": _ED.isoformat(), "constituents": _members(ids[:2], ["0.6", "0.4"])},
        headers=_h(p),
    )
    assert cap.status_code == 201 and len(cap.json()["constituents"]) == 2
    assert (
        db.execute(
            select(func.count())
            .select_from(AuditEvent)
            .where(AuditEvent.event_type == "MARKET.BENCHMARK_CONSTITUENT_CREATE")
        ).scalar_one()
        == 1
    )
    sup = client.post(
        f"/benchmarks/{bid}/membership/supersede",
        json={
            "effective_date": _ED.isoformat(),
            "constituents": _members([ids[0], ids[2]], ["0.5", "0.5"]),
            "effective_at": "2026-04-01T00:00:00+00:00",
        },
        headers=_h(p),
    )
    assert sup.status_code == 201
    cor = client.post(
        f"/benchmarks/{bid}/membership/correct",
        json={
            "effective_date": _ED.isoformat(),
            "constituents": _members([ids[0], ids[2]], ["0.55", "0.45"]),
            "restatement_reason": "vendor fix",
        },
        headers=_h(p),
    )
    assert cor.status_code == 201
    got = client.get(
        f"/benchmarks/{bid}/membership/as-of",
        params={"effective_date": _ED.isoformat(), "valid_at": "2030-01-01T00:00:00+00:00"},
        headers=_h(p),
    )
    assert got.status_code == 200
    weights = sorted(c["weight"] for c in got.json()["constituents"])
    assert weights == ["0.450000000000", "0.550000000000"]


def test_list_benchmarks(ctx) -> None:  # noqa: ANN001
    client, p, _, _ = ctx
    _create_benchmark(client, p, source="SP_DJI")
    _create_benchmark(client, p, source="BLOOMBERG")
    lst = client.get("/benchmarks", headers=_h(p))
    assert lst.status_code == 200 and len(lst.json()) == 2


def test_error_mapping(ctx) -> None:  # noqa: ANN001
    client, p, db, ids = ctx
    # 404 unknown currency
    assert _create_benchmark(client, p, benchmark_currency="ZZZ").status_code == 404
    bid = _create_benchmark(client, p).json()["id"]
    # 404 unknown benchmark for membership
    assert (
        client.post(
            f"/benchmarks/{uuid.uuid4()}/membership",
            json={"effective_date": _ED.isoformat(), "constituents": _members(ids[:1], ["1.0"])},
            headers=_h(p),
        ).status_code
        == 404
    )
    # 404 unknown instrument
    assert (
        client.post(
            f"/benchmarks/{bid}/membership",
            json={
                "effective_date": _ED.isoformat(),
                "constituents": [{"instrument_id": str(uuid.uuid4()), "weight": "1.0"}],
            },
            headers=_h(p),
        ).status_code
        == 404
    )
    # 409 weight DQ (> 1)
    assert (
        client.post(
            f"/benchmarks/{bid}/membership",
            json={"effective_date": _ED.isoformat(), "constituents": _members(ids[:1], ["1.5"])},
            headers=_h(p),
        ).status_code
        == 409
    )
    # 422 empty set
    assert (
        client.post(
            f"/benchmarks/{bid}/membership",
            json={"effective_date": _ED.isoformat(), "constituents": []},
            headers=_h(p),
        ).status_code
        == 422
    )
    # 409 supersede with no current membership
    assert (
        client.post(
            f"/benchmarks/{bid}/membership/supersede",
            json={
                "effective_date": _ED.isoformat(),
                "constituents": _members(ids[:1], ["1.0"]),
                "effective_at": "2026-04-01T00:00:00+00:00",
            },
            headers=_h(p),
        ).status_code
        == 409
    )


def test_no_put_patch_delete(ctx) -> None:  # noqa: ANN001
    client, p, _, _ = ctx
    bid = _create_benchmark(client, p).json()["id"]
    for method in (client.put, client.patch, client.delete):
        assert method(f"/benchmarks/{bid}", headers=_h(p)).status_code in (404, 405)


def test_membership_as_of_unknown_benchmark_404(ctx) -> None:  # noqa: ANN001
    # a read for an unknown/cross-tenant benchmark_id fails closed with 404 (NOT an unmapped 500).
    client, p, _, _ = ctx
    resp = client.get(
        f"/benchmarks/{uuid.uuid4()}/membership/as-of",
        params={"effective_date": _ED.isoformat(), "valid_at": "2030-01-01T00:00:00+00:00"},
        headers=_h(p),
    )
    assert resp.status_code == 404


def test_update_null_currency_422(ctx) -> None:  # noqa: ANN001
    client, p, _, _ = ctx
    bid = _create_benchmark(client, p).json()["id"]
    resp = client.post(
        f"/benchmarks/{bid}/update", json={"benchmark_currency": None}, headers=_h(p)
    )
    assert resp.status_code == 422
