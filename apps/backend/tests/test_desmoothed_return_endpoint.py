"""End-to-end tests of the PA-1 desmoothed-return endpoints (ENT-056; REUSES perf.run/perf.view —
NO new permission code).

SQLite has no RLS (tenant isolation + append-only proofs live in
``packages/shared-python/tests/test_desmoothed_return_pg.py``); here we prove entitlement gating
on the REUSED verbs (deny-by-default; view-only cannot run), the declared-alpha model registration
(+ the 409 identity conflict + the 422 out-of-domain alpha), the build-in-request run + read
round-trip (the hand-derived golden 0.0325/-0.0625 + the honest-uncertainty summary pair),
fixed-point decimal serialization, the pre-create refusals (422), the ``/perf/runs`` listing
surfacing the DESMOOTHED_RETURN run, and no PUT/PATCH/DELETE on the route family.

Golden derivation: quarterly PE marks 100.00 -> 102.00 -> 104.55 -> 103.5045 (alpha=0.4) =>
observed r = [0.02, 0.025, -0.01]; desmoothed d = [0.0325, -0.0625]; summary stdevs
0.067175144213 (desmoothed) vs 0.024748737342 (observed) — see the shared-python suite.
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
from irp_shared.models import Base
from irp_shared.portfolio import PortfolioActor, create_portfolio
from irp_shared.reference.instrument import create_instrument
from irp_shared.reference.models import Currency
from irp_shared.reference.service import ReferenceActor
from irp_shared.valuation import create_valuation
from irp_shared.valuation.service import ValuationActor

_PERMS = ("perf.run", "perf.view", "model.inventory.register")
_T0 = datetime(2025, 9, 1, tzinfo=UTC)
_DATES = (date(2025, 9, 30), date(2025, 12, 31), date(2026, 3, 31), date(2026, 6, 30))
_VALUES = ("100.00", "102.00", "104.55", "103.5045")
_WINDOW = {"window_start": "2025-09-01", "window_end": "2026-07-01"}


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
        code=f"PE-{uuid.uuid4().hex[:6]}",
        name="private book",
        node_type="ACCOUNT",
        actor=PortfolioActor(actor_id="s"),
    ).id
    inst = create_instrument(
        db,
        tenant_id=tenant_id,
        code=f"PE-FUND-{uuid.uuid4().hex[:6]}",
        name="Buyout Fund IV",
        asset_class="PRIVATE_EQUITY",
        actor=ReferenceActor(actor_id="s"),
    ).id
    for d, v in zip(_DATES, _VALUES, strict=True):
        create_valuation(
            db,
            portfolio_id=pf,
            instrument_id=inst,
            valuation_date=d,
            acting_tenant=tenant_id,
            actor=ValuationActor(actor_id="s"),
            mark_value=Decimal(v),
            currency_code="USD",
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
        yield TestClient(app), principal, db, pf, inst
    finally:
        db.close()
        engine.dispose()


def _h(p: Principal) -> dict[str, str]:
    return {"X-User-Id": p.user_id, "X-Tenant-Id": p.tenant_id}


def _register(client: TestClient, p: Principal, alpha: str = "0.4") -> str:
    resp = client.post(
        "/perf/models/desmoothed-return",
        json={"code_version": "pa1-v1", "alpha": alpha},
        headers=_h(p),
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["model_version_id"]


def _run_body(mv: str, pf: str, inst: str, **kw) -> dict:  # noqa: ANN003
    return {
        "code_version": "pa1-v1",
        "environment_id": "ci",
        "model_version_id": mv,
        "portfolio_id": pf,
        "instrument_id": inst,
        **_WINDOW,
        **kw,
    }


def _count_runs(db: Session, tenant: str) -> int:
    return db.execute(
        select(func.count())
        .select_from(CalculationRun)
        .where(CalculationRun.tenant_id == tenant, CalculationRun.run_type == "DESMOOTHED_RETURN")
    ).scalar_one()


def test_register_run_and_read_roundtrip(ctx) -> None:  # noqa: ANN001
    client, p, db, pf, inst = ctx
    mv = _register(client, p)
    resp = client.post("/perf/desmoothed-returns/runs", json=_run_body(mv, pf, inst), headers=_h(p))
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["status"] == "COMPLETED" and body["run_type"] == "DESMOOTHED_RETURN"
    assert len(body["rows"]) == 3  # 2 DESMOOTHED_PERIOD + 1 DESMOOTHING_SUMMARY

    periods = sorted(
        (r for r in body["rows"] if r["metric_type"] == "DESMOOTHED_PERIOD"),
        key=lambda r: r["period_start"],
    )
    assert periods[0]["metric_value"] == "0.032500000000"
    assert periods[0]["observed_return"] == "0.025000000000"
    assert periods[1]["metric_value"] == "-0.062500000000"
    summary = next(r for r in body["rows"] if r["metric_type"] == "DESMOOTHING_SUMMARY")
    assert summary["metric_value"] == "0.067175144213"  # desmoothed stdev
    assert summary["observed_stdev"] == "0.024748737342"  # the honest-uncertainty pair
    assert summary["n_periods"] == 2 and summary["alpha"] == "0.4"
    for r in body["rows"]:
        assert "E" not in r["metric_value"] and "e" not in r["metric_value"]  # fixed-point

    run_read = client.get(f"/perf/desmoothed-returns/runs/{body['run_id']}", headers=_h(p))
    assert run_read.status_code == 200 and len(run_read.json()["rows"]) == 3
    row_read = client.get(f"/perf/desmoothed-returns/{summary['id']}", headers=_h(p))
    assert row_read.status_code == 200
    assert row_read.json()["metric_value"] == summary["metric_value"]
    listing = client.get("/perf/runs", params={"run_type": "DESMOOTHED_RETURN"}, headers=_h(p))
    assert listing.status_code == 200
    assert any(item["run_id"] == body["run_id"] for item in listing.json()["items"])


def test_register_identity_conflicts_and_domain(ctx) -> None:  # noqa: ANN001
    client, p, db, pf, inst = ctx
    mv = _register(client, p)
    assert _register(client, p) == mv  # idempotent same (code_version, alpha)
    resp = client.post(
        "/perf/models/desmoothed-return",
        json={"code_version": "pa1-v1", "alpha": "0.5"},
        headers=_h(p),
    )
    assert resp.status_code == 409  # same label, different declared alpha
    resp = client.post(
        "/perf/models/desmoothed-return",
        json={"code_version": "pa1-v9", "alpha": "1.5"},
        headers=_h(p),
    )
    assert resp.status_code == 422  # out-of-domain alpha (never a 500)


def test_deny_by_default_and_view_only_cannot_run(ctx) -> None:  # noqa: ANN001
    client, p, db, pf, inst = ctx
    mv = _register(client, p)
    nobody = Principal(user_id=str(uuid.uuid4()), tenant_id=p.tenant_id)
    resp = client.post(
        "/perf/desmoothed-returns/runs", json=_run_body(mv, pf, inst), headers=_h(nobody)
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
        "/perf/desmoothed-returns/runs", json=_run_body(mv, pf, inst), headers=_h(vp)
    )
    assert resp.status_code == 403  # .view does not grant .run
    assert _count_runs(db, p.tenant_id) == 0


def test_pre_create_refusals(ctx) -> None:  # noqa: ANN001
    client, p, db, pf, inst = ctx
    mv = _register(client, p)
    # Unregistered model_version (CTRL-003 fail-closed) => 422.
    resp = client.post(
        "/perf/desmoothed-returns/runs",
        json=_run_body(str(uuid.uuid4()), pf, inst),
        headers=_h(p),
    )
    assert resp.status_code == 422
    # Both build args AND a snapshot_id at once => 422 (the P3-C1 XOR gate).
    resp = client.post(
        "/perf/desmoothed-returns/runs",
        json=_run_body(mv, pf, inst, snapshot_id=str(uuid.uuid4())),
        headers=_h(p),
    )
    assert resp.status_code == 422
    # A window holding fewer than 2 marks => 409 (the builder fails closed pre-write).
    resp = client.post(
        "/perf/desmoothed-returns/runs",
        json=_run_body(mv, pf, inst, window_start="2025-09-01", window_end="2025-10-15"),
        headers=_h(p),
    )
    assert resp.status_code == 409
    # An unknown instrument => 409 (the builder resolves it fail-closed).
    resp = client.post(
        "/perf/desmoothed-returns/runs",
        json=_run_body(mv, pf, str(uuid.uuid4())),
        headers=_h(p),
    )
    assert resp.status_code == 409
    assert _count_runs(db, p.tenant_id) == 0  # every refusal left ZERO run


def test_unknown_run_and_result_are_404(ctx) -> None:  # noqa: ANN001
    client, p, db, pf, inst = ctx
    assert (
        client.get(f"/perf/desmoothed-returns/runs/{uuid.uuid4()}", headers=_h(p)).status_code
        == 404
    )
    assert client.get(f"/perf/desmoothed-returns/{uuid.uuid4()}", headers=_h(p)).status_code == 404


def test_no_mutating_verbs(ctx) -> None:  # noqa: ANN001
    client, p, db, pf, inst = ctx
    for verb in ("put", "patch", "delete"):
        resp = getattr(client, verb)("/perf/desmoothed-returns/runs", headers=_h(p))
        assert resp.status_code == 405
