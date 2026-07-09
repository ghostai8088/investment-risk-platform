"""End-to-end tests of the P2-7 benchmark time-series endpoints (levels + returns).

SQLite has no RLS, so cross-tenant isolation is in ``tests/test_benchmark_series_pg.py``; here we
prove entitlement gating (deny-by-default, no DB side-effect on denial), the capture / supersede /
correct / as-of / list round-trip, DECIMAL values serialized BYTE-FOR-BYTE as strings (never a
float), 403/404/422/409 mapping, and no PUT/PATCH/DELETE. The verbs REUSE marketdata.view/.ingest.

Fixture realism (TD-1): index levels O(10^3), returns small fractions; out-of-band values only in
the mapping tests.
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
from irp_shared.db.session import make_engine, make_session_factory
from irp_shared.entitlement.bootstrap import SYSTEM_TENANT_ID
from irp_shared.entitlement.models import AppUser, Permission, Role, RolePermission, UserRole
from irp_shared.entitlement.service import Principal
from irp_shared.marketdata import BenchmarkLevel, BenchmarkReturn
from irp_shared.models import Base
from irp_shared.reference.models import Currency

_PERMS = ("marketdata.view", "marketdata.ingest")
_VF = datetime(2020, 1, 1, tzinfo=UTC)
_LD = date(2026, 5, 29)
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
    app.include_router(benchmark_router)
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


def _create_benchmark(client: TestClient, p: Principal) -> str:
    resp = client.post(
        "/benchmarks",
        json={"benchmark_code": "SPX", "benchmark_source": "SP_DJI", "benchmark_currency": "USD"},
        headers=_h(p),
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _capture_level(client, p, bid, value="4500.25", ltype="PRICE_RETURN"):  # noqa: ANN001, ANN202
    return client.post(
        f"/benchmarks/{bid}/levels",
        json={"level_date": _LD.isoformat(), "level_type": ltype, "level_value": value},
        headers=_h(p),
    )


def _capture_return(client, p, bid, value="0.0123", basis="PRICE"):  # noqa: ANN001, ANN202
    return client.post(
        f"/benchmarks/{bid}/returns",
        json={"return_date": _LD.isoformat(), "return_basis": basis, "return_value": value},
        headers=_h(p),
    )


def test_capture_and_read_back_decimal_is_string_and_canonical(ctx) -> None:  # noqa: ANN001
    """Decimals are serialized as STRINGS (never a float). The POST echoes the submitted value; a
    GET returns the PERSISTED canonical NUMERIC(p,s) form — byte-for-byte stable + cross-engine
    identical (the reproducibility property P3-7 pins). Both are numerically exact."""
    from decimal import Decimal

    client, p, db = ctx
    bid = _create_benchmark(client, p)
    lvl = _capture_level(client, p, bid, "4500.25")
    assert lvl.status_code == 201, lvl.text
    body = lvl.json()
    assert body["benchmark_id"] == bid and body["level_type"] == "PRICE_RETURN"
    assert isinstance(body["level_value"], str) and Decimal(body["level_value"]) == Decimal(
        "4500.25"
    )

    ret = _capture_return(client, p, bid, "0.0123")
    assert ret.status_code == 201
    assert isinstance(ret.json()["return_value"], str)
    assert Decimal(ret.json()["return_value"]) == Decimal("0.0123")

    # Read-back: the persisted canonical form (scale-fixed) is stable byte-for-byte across reads.
    got1 = client.get(
        f"/benchmarks/{bid}/levels/as-of",
        params={"level_date": _LD.isoformat(), "level_type": "PRICE_RETURN", "valid_at": _FAR},
        headers=_h(p),
    ).json()["level_value"]
    got2 = client.get(
        f"/benchmarks/{bid}/levels/as-of",
        params={"level_date": _LD.isoformat(), "level_type": "PRICE_RETURN", "valid_at": _FAR},
        headers=_h(p),
    ).json()["level_value"]
    assert got1 == got2 == "4500.250000" and Decimal(got1) == Decimal("4500.25")
    assert db.execute(select(func.count()).select_from(BenchmarkLevel)).scalar_one() == 1
    assert db.execute(select(func.count()).select_from(BenchmarkReturn)).scalar_one() == 1


def test_capture_without_ingest_403_no_write(ctx) -> None:  # noqa: ANN001
    client, p, db = ctx
    bid = _create_benchmark(client, p)
    resp = client.post(
        f"/benchmarks/{bid}/levels",
        json={
            "level_date": _LD.isoformat(),
            "level_type": "PRICE_RETURN",
            "level_value": "4500.25",
        },
        headers=_no_perm(p),
    )
    assert resp.status_code == 403
    assert db.execute(select(func.count()).select_from(BenchmarkLevel)).scalar_one() == 0


def test_level_supersede_correct_as_of_list_roundtrip(ctx) -> None:  # noqa: ANN001
    client, p, _ = ctx
    bid = _create_benchmark(client, p)
    _capture_level(client, p, bid, "4500.25")
    sup = client.post(
        f"/benchmarks/{bid}/levels/supersede",
        json={
            "level_date": _LD.isoformat(),
            "level_type": "PRICE_RETURN",
            "level_value": "4512.75",
            "effective_at": "2026-06-15T00:00:00+00:00",
        },
        headers=_h(p),
    )
    assert sup.status_code == 201 and sup.json()["record_version"] == 2
    cor = client.post(
        f"/benchmarks/{bid}/levels/correct",
        json={
            "level_date": _LD.isoformat(),
            "level_type": "PRICE_RETURN",
            "level_value": "4511.90",
            "restatement_reason": "vendor restatement",
        },
        headers=_h(p),
    )
    assert cor.status_code == 201 and cor.json()["record_version"] == 3
    got = client.get(
        f"/benchmarks/{bid}/levels/as-of",
        params={
            "level_date": _LD.isoformat(),
            "level_type": "PRICE_RETURN",
            "valid_at": "2026-06-15T00:00:00+00:00",
            "known_at": _FAR,
        },
        headers=_h(p),
    )
    # the GET returns the persisted canonical NUMERIC(20,6) form (scale-fixed)
    assert got.status_code == 200 and got.json()["level_value"] == "4511.900000"
    listed = client.get(f"/benchmarks/{bid}/levels", headers=_h(p))
    assert listed.status_code == 200 and len(listed.json()) == 1  # one current head


def test_return_coexisting_bases_and_list(ctx) -> None:  # noqa: ANN001
    client, p, _ = ctx
    bid = _create_benchmark(client, p)
    assert _capture_return(client, p, bid, "0.0123", basis="PRICE").status_code == 201
    assert _capture_return(client, p, bid, "0.0131", basis="TOTAL").status_code == 201
    listed = client.get(f"/benchmarks/{bid}/returns", headers=_h(p))
    assert listed.status_code == 200
    assert {r["return_basis"] for r in listed.json()} == {"PRICE", "TOTAL"}


def test_404_unknown_benchmark(ctx) -> None:  # noqa: ANN001
    client, p, _ = ctx
    resp = _capture_level(client, p, str(uuid.uuid4()), "4500.25")
    assert resp.status_code == 404


def test_422_bad_vocab(ctx) -> None:  # noqa: ANN001
    client, p, _ = ctx
    bid = _create_benchmark(client, p)
    assert _capture_level(client, p, bid, "4500.25", ltype="BOGUS").status_code == 422


def test_409_return_below_minus_one_dq(ctx) -> None:  # noqa: ANN001
    client, p, db = ctx
    bid = _create_benchmark(client, p)
    # A boundary fixture: a simple return < -100% fails the DQ RANGE -> 409, no write.
    resp = _capture_return(client, p, bid, "-2")
    assert resp.status_code == 409
    assert db.execute(select(func.count()).select_from(BenchmarkReturn)).scalar_one() == 0


def test_409_supersede_no_current_head(ctx) -> None:  # noqa: ANN001
    """review fold: the NoCurrentBenchmarkSeries endpoint mapping is 409 (the factor precedent), not
    the 422 an earlier binder docstring claimed."""
    client, p, _ = ctx
    bid = _create_benchmark(client, p)
    resp = client.post(
        f"/benchmarks/{bid}/levels/supersede",
        json={
            "level_date": _LD.isoformat(),
            "level_type": "PRICE_RETURN",
            "level_value": "4500.25",
            "effective_at": "2026-06-15T00:00:00+00:00",
        },
        headers=_h(p),
    )
    assert resp.status_code == 409


def test_no_put_patch_delete(ctx) -> None:  # noqa: ANN001
    client, p, _ = ctx
    bid = _create_benchmark(client, p)
    for method in (client.put, client.patch, client.delete):
        assert method(f"/benchmarks/{bid}/levels", headers=_h(p)).status_code == 405
