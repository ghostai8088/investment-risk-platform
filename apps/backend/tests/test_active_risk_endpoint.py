"""End-to-end tests of the P3-7 risk (ex-ante active risk / tracking error v1) endpoints.

SQLite has no RLS (tenant isolation + append-only-trigger proofs are in
``packages/shared-python/tests/test_active_risk_pg.py``); here we prove entitlement gating
(deny-by-default, no DB side-effect on denial; view-only cannot run — the REUSED ``risk.run``/
``risk.view``), the ``code_version``-only model registration (incl. the 409 identity conflict), the
build-in-request run + read round-trip over the two upstream governed runs + the captured benchmark,
fixed-point decimal serialization, the pre-create refusals (422/404), the post-create FAILED
contract, the both-modes 422, and no PUT/PATCH/DELETE on the new route families.
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

from irp_backend.api.risk import router as risk_router
from irp_backend.deps import get_db
from irp_shared.calc.models import CalculationRun
from irp_shared.db.session import make_engine, make_session_factory
from irp_shared.entitlement.bootstrap import SYSTEM_TENANT_ID
from irp_shared.entitlement.models import AppUser, Permission, Role, RolePermission, UserRole
from irp_shared.entitlement.service import Principal
from irp_shared.exposure import ExposureActor, run_exposure
from irp_shared.marketdata import FxRateActor, capture_fx_rate
from irp_shared.marketdata.benchmark import (
    BenchmarkActor,
    ConstituentInput,
    capture_benchmark,
    capture_membership,
)
from irp_shared.marketdata.factor import (
    FactorActor,
    capture_factor,
    capture_factor_return,
    resolve_factor,
)
from irp_shared.models import Base
from irp_shared.portfolio import PortfolioActor, create_portfolio
from irp_shared.position import create_position
from irp_shared.position.service import PositionActor
from irp_shared.reference.instrument import create_instrument
from irp_shared.reference.models import Currency
from irp_shared.reference.service import ReferenceActor
from irp_shared.risk import (
    CovarianceActor,
    FactorExposureActor,
    register_covariance_model,
    register_factor_exposure_model,
    run_covariance,
    run_factor_exposure,
)
from irp_shared.valuation import create_valuation
from irp_shared.valuation.service import ValuationActor

_PERMS = ("risk.run", "risk.view", "model.inventory.register")
_T0 = datetime(2026, 1, 1, tzinfo=UTC)
_VA = datetime(2026, 6, 1, tzinfo=UTC)
_KA = datetime(2030, 1, 1, tzinfo=UTC)
_VD = date(2026, 6, 1)
_D = (date(2026, 5, 26), date(2026, 5, 27), date(2026, 5, 28), date(2026, 5, 29))
_ED = _D[-1]


@pytest.fixture
def ctx() -> Iterator[tuple[TestClient, Principal, Session, str, str, str]]:
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
    for code in ("USD", "EUR"):
        db.add(Currency(tenant_id=SYSTEM_TENANT_ID, code=code, name=code, valid_from=_T0))
    db.flush()

    pf = create_portfolio(
        db,
        tenant_id=tenant_id,
        code="ACCT",
        name="acct",
        node_type="ACCOUNT",
        actor=PortfolioActor(actor_id="s"),
    ).id
    for code, mark, ccy in (("I-USD", "300.00", "USD"), ("I-EUR", "400.00", "EUR")):
        inst = create_instrument(
            db,
            tenant_id=tenant_id,
            code=code,
            name="i",
            asset_class="BOND",
            actor=ReferenceActor(actor_id="s"),
        ).id
        create_position(
            db,
            portfolio_id=pf,
            instrument_id=inst,
            acting_tenant=tenant_id,
            actor=PositionActor(actor_id="s"),
            quantity=Decimal("100"),
            valid_from=_T0,
        )
        create_valuation(
            db,
            portfolio_id=pf,
            instrument_id=inst,
            valuation_date=_VD,
            acting_tenant=tenant_id,
            actor=ValuationActor(actor_id="s"),
            mark_value=Decimal(mark),
            currency_code=ccy,
            valid_from=_T0,
        )
    capture_fx_rate(
        db,
        base_currency="EUR",
        quote_currency="USD",
        rate_date=_VD,
        rate=Decimal("1.000000000000"),
        acting_tenant=tenant_id,
        actor=FxRateActor(actor_id="s"),
        valid_from=_T0,
    )
    exposure = run_exposure(
        db,
        acting_tenant=tenant_id,
        actor=ExposureActor(actor_id="a"),
        code_version="v1",
        environment_id="ci",
        portfolio_id=pf,
        as_of_valid_at=_VA,
        as_of_known_at=_KA,
        base_currency="USD",
    )
    factor_ids: list[str] = []
    for code, ccy, values in (
        ("FX_USD", "USD", ("0.01", "0.02", "0.03", "0.04")),
        ("FX_EUR", "EUR", ("0.04", "0.03", "0.02", "0.01")),
    ):
        fid = capture_factor(
            db,
            factor_code=code,
            factor_source="VENDOR_F",
            factor_family="CURRENCY",
            currency_code=ccy,
            acting_tenant=tenant_id,
            actor=FactorActor(actor_id="s"),
            valid_from=_T0,
        ).id
        factor = resolve_factor(db, fid, acting_tenant=tenant_id)
        for d, v in zip(_D, values, strict=True):
            capture_factor_return(
                db,
                factor,
                return_date=d,
                return_value=Decimal(v),
                acting_tenant=tenant_id,
                actor=FactorActor(actor_id="s"),
                valid_from=_T0,
            )
        factor_ids.append(fid)
    fx_mv = register_factor_exposure_model(
        db, tenant_id=tenant_id, actor_id="a", code_version="risk-v1"
    )
    fx_run = run_factor_exposure(
        db,
        acting_tenant=tenant_id,
        actor=FactorExposureActor(actor_id="a"),
        code_version="risk-v1",
        environment_id="ci",
        model_version_id=fx_mv.id,
        exposure_run_id=exposure.run.run_id,
        factor_ids=factor_ids,
    )
    cov_mv = register_covariance_model(
        db, tenant_id=tenant_id, actor_id="a", code_version="risk-v1", window_observations=4
    )
    cov_run = run_covariance(
        db,
        acting_tenant=tenant_id,
        actor=CovarianceActor(actor_id="a"),
        code_version="risk-v1",
        environment_id="ci",
        model_version_id=cov_mv.id,
        factor_ids=factor_ids,
        as_of_valid_at=_VA,
    )
    # A benchmark with a USD/EUR membership (the covariance factor currencies).
    bm = capture_benchmark(
        db,
        benchmark_code="BM",
        benchmark_source="VENDOR_B",
        benchmark_currency="USD",
        acting_tenant=tenant_id,
        actor=BenchmarkActor(actor_id="s"),
        valid_from=_T0,
    )
    constituents: list[ConstituentInput] = []
    for w, ccy in (("0.60", "USD"), ("0.40", "EUR")):
        binst = create_instrument(
            db,
            tenant_id=tenant_id,
            code=f"BM-{ccy}",
            name="bmi",
            asset_class="EQUITY",
            actor=ReferenceActor(actor_id="s"),
        ).id
        constituents.append(
            ConstituentInput(instrument_id=binst, weight=Decimal(w), constituent_currency=ccy)
        )
    capture_membership(
        db,
        bm,
        effective_date=_ED,
        constituents=constituents,
        acting_tenant=tenant_id,
        actor=BenchmarkActor(actor_id="s"),
        valid_from=_T0,
    )
    db.commit()
    principal = Principal(user_id=user.id, tenant_id=tenant_id)

    def _override_db() -> Iterator[Session]:
        yield db

    app = FastAPI()
    app.include_router(risk_router)
    app.dependency_overrides[get_db] = _override_db
    try:
        yield TestClient(app), principal, db, fx_run.run.run_id, cov_run.run.run_id, bm.id
    finally:
        db.close()
        engine.dispose()


def _h(p: Principal) -> dict[str, str]:
    return {"X-User-Id": p.user_id, "X-Tenant-Id": p.tenant_id}


def _register(client: TestClient, p: Principal, code_version: str = "risk-v1") -> str:
    resp = client.post(
        "/risk/models/active-risk",
        json={"code_version": code_version},
        headers=_h(p),
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["model_version_id"]


def _run_body(mv: str, fx_run: str, cov_run: str, bm_id: str, **kw) -> dict:  # noqa: ANN003
    return {
        "code_version": "risk-v1",
        "environment_id": "ci",
        "model_version_id": mv,
        "exposure_run_id": fx_run,
        "covariance_run_id": cov_run,
        "benchmark_id": bm_id,
        "benchmark_effective_date": _ED.isoformat(),
        **kw,
    }


def _count_runs(db: Session, tenant: str) -> int:
    return db.execute(
        select(func.count())
        .select_from(CalculationRun)
        .where(CalculationRun.tenant_id == tenant, CalculationRun.run_type == "ACTIVE_RISK")
    ).scalar_one()


def test_register_run_and_read_roundtrip(ctx) -> None:  # noqa: ANN001
    client, p, db, fx_run, cov_run, bm_id = ctx
    mv = _register(client, p)
    resp = client.post(
        "/risk/active-risk/runs", json=_run_body(mv, fx_run, cov_run, bm_id), headers=_h(p)
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["status"] == "COMPLETED" and body["run_type"] == "ACTIVE_RISK"
    assert len(body["rows"]) == 1
    row = body["rows"][0]
    assert row["metric_type"] == "TRACKING_ERROR"
    assert row["base_currency"] == "USD"
    assert row["n_factors"] == 2 and row["n_constituents"] == 2
    assert row["benchmark_id"] == bm_id and row["benchmark_effective_date"] == _ED.isoformat()
    assert row["factor_exposure_run_id"] == fx_run and row["covariance_run_id"] == cov_run
    assert Decimal(row["te_value"]) >= 0
    assert Decimal(row["portfolio_value"]) == Decimal("70000.000000")
    for field in ("te_value", "portfolio_value"):
        assert "E" not in row[field] and "e" not in row[field]  # fixed-point, never scientific
    run_read = client.get(f"/risk/active-risk/runs/{body['run_id']}", headers=_h(p))
    assert run_read.status_code == 200 and len(run_read.json()["rows"]) == 1
    row_read = client.get(f"/risk/active-risk/{row['id']}", headers=_h(p))
    assert row_read.status_code == 200
    assert row_read.json()["te_value"] == row["te_value"]


def test_api1b_active_risk_entity_read_copy_forward(ctx) -> None:  # noqa: ANN001
    """API-1b (Class C): the active-risk run copies its ROOT ``scope_portfolio_id`` forward from the
    exposure→factor chain (proving the write-boundary stamp end-to-end), and the flagship
    'latest active-risk for portfolio P' read resolves via that column — the read ``var_result``/
    ``active_risk_result`` cannot do row-natively (no portfolio_id)."""
    client, p, db, fx_run, cov_run, bm_id = ctx
    mv = _register(client, p)
    resp = client.post(
        "/risk/active-risk/runs", json=_run_body(mv, fx_run, cov_run, bm_id), headers=_h(p)
    )
    assert resp.status_code == 201, resp.text
    run_id = resp.json()["run_id"]
    row_id = resp.json()["rows"][0]["id"]

    # (1) copy-forward: the run carries a NON-NULL scope stamped from the upstream exposure run.
    scope = db.execute(
        select(CalculationRun.scope_portfolio_id).where(CalculationRun.run_id == run_id)
    ).scalar_one()
    assert scope is not None  # the root propagated exposure→factor→active-risk

    # (2) the flagship latest-for-P read resolves via scope_portfolio_id.
    latest = client.get("/risk/active-risk/latest", params={"portfolio_id": scope}, headers=_h(p))
    assert latest.status_code == 200
    assert [r["id"] for r in latest.json()] == [row_id]

    # (3) /latest is NOT shadowed by /{active_risk_id} — it returns a LIST, and a foreign portfolio
    # is silent-empty (not a 404 for a stray id).
    foreign = client.get(
        "/risk/active-risk/latest", params={"portfolio_id": str(uuid.uuid4())}, headers=_h(p)
    )
    assert foreign.status_code == 200 and foreign.json() == []

    # (4) the entity list read + the native benchmark_id filter both resolve.
    listed = client.get("/risk/active-risk", params={"portfolio_id": scope}, headers=_h(p))
    assert listed.status_code == 200 and [r["id"] for r in listed.json()] == [row_id]
    by_bm = client.get(
        "/risk/active-risk",
        params={"portfolio_id": scope, "benchmark_id": bm_id},
        headers=_h(p),
    )
    assert [r["id"] for r in by_bm.json()] == [row_id]
    other_bm = client.get(
        "/risk/active-risk",
        params={"portfolio_id": scope, "benchmark_id": str(uuid.uuid4())},
        headers=_h(p),
    )
    assert other_bm.json() == []


def test_register_idempotent_and_conflict(ctx) -> None:  # noqa: ANN001
    client, p, db, fx_run, cov_run, bm_id = ctx
    mv = _register(client, p)
    assert _register(client, p) == mv  # idempotent same code_version
    resp = client.post("/risk/models/active-risk", json={"code_version": "risk-v2"}, headers=_h(p))
    assert resp.status_code == 409  # same label, different code_version


def test_deny_by_default_and_view_only_cannot_run(ctx) -> None:  # noqa: ANN001
    client, p, db, fx_run, cov_run, bm_id = ctx
    mv = _register(client, p)
    nobody = Principal(user_id=str(uuid.uuid4()), tenant_id=p.tenant_id)
    resp = client.post(
        "/risk/active-risk/runs", json=_run_body(mv, fx_run, cov_run, bm_id), headers=_h(nobody)
    )
    assert resp.status_code == 403
    viewer = AppUser(tenant_id=p.tenant_id, display_name="V")
    view_role = Role(tenant_id=p.tenant_id, code="v", name="V")
    db.add_all([viewer, view_role])
    db.flush()
    perm_id = db.execute(select(Permission.id).where(Permission.code == "risk.view")).scalar_one()
    db.add(RolePermission(role_id=view_role.id, permission_id=perm_id))
    db.add(UserRole(tenant_id=p.tenant_id, user_id=viewer.id, role_id=view_role.id))
    db.commit()
    vp = Principal(user_id=viewer.id, tenant_id=p.tenant_id)
    resp = client.post(
        "/risk/active-risk/runs", json=_run_body(mv, fx_run, cov_run, bm_id), headers=_h(vp)
    )
    assert resp.status_code == 403  # .view does not grant .run
    assert _count_runs(db, p.tenant_id) == 0


def test_pre_create_refusals(ctx) -> None:  # noqa: ANN001
    client, p, db, fx_run, cov_run, bm_id = ctx
    mv = _register(client, p)
    body = _run_body(mv, fx_run, cov_run, bm_id)
    body.pop("benchmark_id")  # incomplete build-arg set
    assert client.post("/risk/active-risk/runs", json=body, headers=_h(p)).status_code == 422
    resp = client.post(  # unregistered model_version (CTRL-003 fail-closed)
        "/risk/active-risk/runs",
        json=_run_body(str(uuid.uuid4()), fx_run, cov_run, bm_id),
        headers=_h(p),
    )
    assert resp.status_code == 422
    resp = client.post(  # unknown exposure run
        "/risk/active-risk/runs",
        json=_run_body(mv, str(uuid.uuid4()), cov_run, bm_id),
        headers=_h(p),
    )
    assert resp.status_code == 404
    resp = client.post(  # unknown benchmark
        "/risk/active-risk/runs",
        json=_run_body(mv, fx_run, cov_run, str(uuid.uuid4())),
        headers=_h(p),
    )
    assert resp.status_code == 404
    body = _run_body(mv, fx_run, cov_run, bm_id)
    for k in ("exposure_run_id", "covariance_run_id", "benchmark_id", "benchmark_effective_date"):
        body.pop(k)
    body["snapshot_id"] = str(uuid.uuid4())  # unknown consume-path snapshot
    assert client.post("/risk/active-risk/runs", json=body, headers=_h(p)).status_code == 404
    assert _count_runs(db, p.tenant_id) == 0


def test_post_create_failed_returns_201_failed(ctx, monkeypatch: pytest.MonkeyPatch) -> None:  # noqa: ANN001
    # The durable-refusal contract at the HTTP layer: a post-create gate defect returns 201 +
    # status=FAILED + failure_reason, and the committed FAILED run reads back 200/FAILED, not 404.
    client, p, db, fx_run, cov_run, bm_id = ctx
    mv = _register(client, p)
    import irp_shared.risk.active_risk_service as ars
    from irp_shared.risk.active_risk_kernel import TeEstimate

    def poisoned(active_weights, covariance):  # noqa: ANN001, ANN202
        return TeEstimate(radicand=Decimal("-1"), tolerance=Decimal("1E-19"), te_value=None)

    monkeypatch.setattr(ars, "compute_tracking_error", poisoned)
    resp = client.post(
        "/risk/active-risk/runs", json=_run_body(mv, fx_run, cov_run, bm_id), headers=_h(p)
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["status"] == "FAILED" and body["rows"] == []
    assert body["failure_reason"] and "non-psd-radicand" in body["failure_reason"]
    read = client.get(f"/risk/active-risk/runs/{body['run_id']}", headers=_h(p))
    assert read.status_code == 200 and read.json()["status"] == "FAILED"
    assert read.json()["failure_reason"] == body["failure_reason"]


def test_both_modes_422(ctx) -> None:  # noqa: ANN001
    client, p, db, fx_run, cov_run, bm_id = ctx
    mv = _register(client, p)
    body = _run_body(mv, fx_run, cov_run, bm_id) | {"snapshot_id": str(uuid.uuid4())}
    resp = client.post("/risk/active-risk/runs", json=body, headers=_h(p))
    assert resp.status_code == 422
    assert _count_runs(db, p.tenant_id) == 0


def test_no_mutating_verbs(ctx) -> None:  # noqa: ANN001
    client, p, db, fx_run, cov_run, bm_id = ctx
    for path in (
        f"/risk/active-risk/{uuid.uuid4()}",
        f"/risk/active-risk/runs/{uuid.uuid4()}",
        "/risk/models/active-risk",
    ):
        for method in ("put", "patch", "delete"):
            resp = getattr(client, method)(path, headers=_h(p))
            assert resp.status_code == 405, (method, path)
