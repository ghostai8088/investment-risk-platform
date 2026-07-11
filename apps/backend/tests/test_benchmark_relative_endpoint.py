"""End-to-end tests of the P3-8 ex-post benchmark-relative endpoints (ENT-054; REUSES perf.run/
perf.view — NO new permission code).

SQLite has no RLS (tenant isolation + append-only proofs live in
``packages/shared-python/tests/test_benchmark_relative_pg.py``); here we prove entitlement gating on
the REUSED verbs (deny-by-default; view-only cannot run), the ``code_version``-only model
registration (+ the 409 identity conflict), the build-in-request run + read round-trip (the five
governed rows), fixed-point decimal serialization, the pre-create refusals (422 unregistered/both-
modes/unknown benchmark), the ``/perf/runs`` listing surfacing the BENCHMARK_RELATIVE run, and
no PUT/PATCH/DELETE on the route families.
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

from irp_backend.api.perf import router as perf_router
from irp_backend.deps import get_db
from irp_shared.calc.models import CalculationRun
from irp_shared.db.session import make_engine, make_session_factory
from irp_shared.entitlement.bootstrap import SYSTEM_TENANT_ID
from irp_shared.entitlement.models import AppUser, Permission, Role, RolePermission, UserRole
from irp_shared.entitlement.service import Principal
from irp_shared.exposure import ExposureActor, run_exposure
from irp_shared.marketdata import (
    RETURN_BASIS_TOTAL,
    BenchmarkActor,
    capture_benchmark,
    capture_benchmark_return,
    resolve_benchmark,
)
from irp_shared.models import Base
from irp_shared.perf import (
    PortfolioReturnActor,
    register_portfolio_return_model,
    run_portfolio_return,
)
from irp_shared.portfolio import PortfolioActor, create_portfolio
from irp_shared.position import create_position
from irp_shared.position.service import PositionActor
from irp_shared.reference.instrument import create_instrument
from irp_shared.reference.models import Currency
from irp_shared.reference.service import ReferenceActor
from irp_shared.valuation import create_valuation
from irp_shared.valuation.service import ValuationActor

_PERMS = ("perf.run", "perf.view", "model.inventory.register")
_T0 = datetime(2026, 1, 1, tzinfo=UTC)
_KA = datetime(2030, 1, 1, tzinfo=UTC)
_D0, _D1, _D2 = date(2026, 1, 1), date(2026, 1, 31), date(2026, 3, 2)


def _boundary_run(db, tenant, pf, inst, vdate, mark):  # noqa: ANN001, ANN202
    create_valuation(
        db,
        portfolio_id=pf,
        instrument_id=inst,
        valuation_date=vdate,
        acting_tenant=tenant,
        actor=ValuationActor(actor_id="s"),
        mark_value=Decimal(mark),
        currency_code="USD",
        valid_from=_T0,
    )
    return run_exposure(
        db,
        acting_tenant=tenant,
        actor=ExposureActor(actor_id="a"),
        code_version="v1",
        environment_id="ci",
        portfolio_id=pf,
        as_of_valid_at=datetime(vdate.year, vdate.month, vdate.day, tzinfo=UTC),
        as_of_known_at=_KA,
        base_currency="USD",
    ).run.run_id


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
    db.add(Currency(tenant_id=SYSTEM_TENANT_ID, code="USD", name="USD", valid_from=_T0))
    db.flush()

    pf = create_portfolio(
        db,
        tenant_id=tenant_id,
        code=f"ACCT-{uuid.uuid4().hex[:6]}",
        name="acct",
        node_type="ACCOUNT",
        actor=PortfolioActor(actor_id="s"),
    ).id
    inst = create_instrument(
        db,
        tenant_id=tenant_id,
        code=f"I-{uuid.uuid4().hex[:6]}",
        name="i",
        asset_class="EQUITY",
        actor=ReferenceActor(actor_id="s"),
    ).id
    create_position(
        db,
        portfolio_id=pf,
        instrument_id=inst,
        acting_tenant=tenant_id,
        actor=PositionActor(actor_id="s"),
        quantity=Decimal("1"),
        valid_from=_T0,
    )
    r0 = _boundary_run(db, tenant_id, pf, inst, _D0, "1000000")
    r1 = _boundary_run(db, tenant_id, pf, inst, _D1, "1030000")
    r2 = _boundary_run(db, tenant_id, pf, inst, _D2, "1019700")
    ret_mv = register_portfolio_return_model(
        db, tenant_id=tenant_id, actor_id="a", code_version="perf-v1"
    )
    db.flush()
    ret = run_portfolio_return(
        db,
        acting_tenant=tenant_id,
        actor=PortfolioReturnActor(actor_id="a"),
        code_version="perf-v1",
        environment_id="ci",
        model_version_id=ret_mv.id,
        exposure_run_ids=[r0, r1, r2],
    )
    assert ret.status == "COMPLETED"
    bm = capture_benchmark(
        db,
        benchmark_code=f"SPX-{uuid.uuid4().hex[:6]}",
        benchmark_source="SP_DJI",
        benchmark_currency="USD",
        acting_tenant=tenant_id,
        actor=BenchmarkActor(actor_id="s"),
        index_family="S&P",
        valid_from=_T0,
    )
    db.flush()
    bm = resolve_benchmark(db, bm.id, acting_tenant=tenant_id)
    for rdate, val in ((_D1, "0.025"), (_D2, "0.005")):
        capture_benchmark_return(
            db,
            bm,
            return_date=rdate,
            return_basis=RETURN_BASIS_TOTAL,
            return_value=Decimal(val),
            acting_tenant=tenant_id,
            actor=BenchmarkActor(actor_id="s"),
            valid_from=_T0,
        )
    db.commit()
    principal = Principal(user_id=user.id, tenant_id=tenant_id)

    def _override_db() -> Iterator[Session]:
        yield db

    app = FastAPI()
    app.include_router(perf_router)
    app.dependency_overrides[get_db] = _override_db
    try:
        yield TestClient(app), principal, db, ret.run.run_id, bm.id
    finally:
        db.close()
        engine.dispose()


def _h(p: Principal) -> dict[str, str]:
    return {"X-User-Id": p.user_id, "X-Tenant-Id": p.tenant_id}


def _register(client: TestClient, p: Principal, code_version: str = "br-v1") -> str:
    resp = client.post(
        "/perf/models/benchmark-relative", json={"code_version": code_version}, headers=_h(p)
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["model_version_id"]


def _run_body(mv: str, run_id: str, bm: str, **kw) -> dict:  # noqa: ANN003
    return {
        "code_version": "br-v1",
        "environment_id": "ci",
        "model_version_id": mv,
        "portfolio_return_run_id": run_id,
        "benchmark_id": bm,
        "return_basis": RETURN_BASIS_TOTAL,
        **kw,
    }


def _count_runs(db: Session, tenant: str) -> int:
    return db.execute(
        select(func.count())
        .select_from(CalculationRun)
        .where(CalculationRun.tenant_id == tenant, CalculationRun.run_type == "BENCHMARK_RELATIVE")
    ).scalar_one()


def test_register_run_and_read_roundtrip(ctx) -> None:  # noqa: ANN001
    client, p, db, run_id, bm = ctx
    mv = _register(client, p)
    resp = client.post(
        "/perf/benchmark-relative/runs", json=_run_body(mv, run_id, bm), headers=_h(p)
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["status"] == "COMPLETED" and body["run_type"] == "BENCHMARK_RELATIVE"
    assert len(body["rows"]) == 5  # 2 ACTIVE_RETURN + TD + TE + IR
    td = next(r for r in body["rows"] if r["metric_type"] == "TRACKING_DIFFERENCE")
    assert td["metric_value"] == "-0.010425000000"
    te = next(r for r in body["rows"] if r["metric_type"] == "TRACKING_ERROR")
    assert te["metric_value"] == "0.014142135624"
    assert te["portfolio_return_value"] is None  # TE carries no per-side echo
    for r in body["rows"]:
        assert "E" not in r["metric_value"] and "e" not in r["metric_value"]  # fixed-point
    run_read = client.get(f"/perf/benchmark-relative/runs/{body['run_id']}", headers=_h(p))
    assert run_read.status_code == 200 and len(run_read.json()["rows"]) == 5
    row_read = client.get(f"/perf/benchmark-relative/{td['id']}", headers=_h(p))
    assert row_read.status_code == 200 and row_read.json()["metric_value"] == td["metric_value"]
    listing = client.get("/perf/runs", headers=_h(p))
    assert listing.status_code == 200
    assert any(item["run_id"] == body["run_id"] for item in listing.json()["items"])


def test_register_idempotent_and_conflict(ctx) -> None:  # noqa: ANN001
    client, p, db, run_id, bm = ctx
    mv = _register(client, p)
    assert _register(client, p) == mv  # idempotent same code_version
    resp = client.post(
        "/perf/models/benchmark-relative", json={"code_version": "br-v2"}, headers=_h(p)
    )
    assert resp.status_code == 409  # same label, different code_version


def test_deny_by_default_and_view_only_cannot_run(ctx) -> None:  # noqa: ANN001
    client, p, db, run_id, bm = ctx
    mv = _register(client, p)
    nobody = Principal(user_id=str(uuid.uuid4()), tenant_id=p.tenant_id)
    resp = client.post(
        "/perf/benchmark-relative/runs", json=_run_body(mv, run_id, bm), headers=_h(nobody)
    )
    assert resp.status_code == 403
    viewer = AppUser(tenant_id=p.tenant_id, display_name="V")
    view_role = Role(tenant_id=p.tenant_id, code="v", name="V")
    db.add_all([viewer, view_role])
    db.flush()
    perm_id = db.execute(select(Permission.id).where(Permission.code == "perf.view")).scalar_one()
    db.add(RolePermission(role_id=view_role.id, permission_id=perm_id))
    db.add(UserRole(tenant_id=p.tenant_id, user_id=viewer.id, role_id=view_role.id))
    db.commit()
    vp = Principal(user_id=viewer.id, tenant_id=p.tenant_id)
    resp = client.post(
        "/perf/benchmark-relative/runs", json=_run_body(mv, run_id, bm), headers=_h(vp)
    )
    assert resp.status_code == 403  # .view does not grant .run
    assert _count_runs(db, p.tenant_id) == 0


def test_pre_create_refusals(ctx) -> None:  # noqa: ANN001
    client, p, db, run_id, bm = ctx
    mv = _register(client, p)
    # Unregistered model_version (CTRL-003 fail-closed).
    resp = client.post(
        "/perf/benchmark-relative/runs",
        json=_run_body(str(uuid.uuid4()), run_id, bm),
        headers=_h(p),
    )
    assert resp.status_code == 422
    # Both modes at once => 422.
    resp = client.post(
        "/perf/benchmark-relative/runs",
        json=_run_body(mv, run_id, bm, snapshot_id=str(uuid.uuid4())),
        headers=_h(p),
    )
    assert resp.status_code == 422
    # Unknown benchmark id on the build path => 422 (uniform pre-create refusal; review fold).
    resp = client.post(
        "/perf/benchmark-relative/runs",
        json=_run_body(mv, run_id, str(uuid.uuid4())),
        headers=_h(p),
    )
    assert resp.status_code == 422
    assert _count_runs(db, p.tenant_id) == 0  # every refusal left ZERO run


def test_no_mutating_verbs(ctx) -> None:  # noqa: ANN001
    client, p, db, run_id, bm = ctx
    for verb in ("put", "patch", "delete"):
        resp = getattr(client, verb)("/perf/benchmark-relative/runs", headers=_h(p))
        assert resp.status_code == 405
