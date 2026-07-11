"""End-to-end tests of the BT-1 VaR-backtesting endpoints (ENT-055; REUSES risk.run/risk.view —
NO new permission code).

SQLite has no RLS (tenant isolation + append-only proofs live in
``packages/shared-python/tests/test_var_backtest_pg.py``); here we prove entitlement gating on the
REUSED verbs (deny-by-default; view-only cannot run), the declared-alpha model registration
(+ the 409 identity conflict + the 422 off-vocabulary alpha), the build-in-request run + read
round-trip (the three governed rows with exact Kupiec values), fixed-point decimal serialization,
the pre-create refusals (422), the ``/risk/runs`` listing surfacing the VAR_BACKTEST run, and no
PUT/PATCH/DELETE on the route families.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta
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
from irp_shared.marketdata import (
    FactorActor,
    FxRateActor,
    capture_factor,
    capture_factor_return,
    capture_fx_rate,
    resolve_factor,
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
from irp_shared.risk import (
    CovarianceActor,
    FactorExposureActor,
    VarActor,
    register_covariance_model,
    register_factor_exposure_model,
    register_var_model,
    run_covariance,
    run_factor_exposure,
    run_var,
)
from irp_shared.valuation import create_valuation
from irp_shared.valuation.service import ValuationActor

_PERMS = ("risk.run", "risk.view", "model.inventory.register")
_T0 = datetime(2026, 1, 1, tzinfo=UTC)
_VALID_AT = datetime(2026, 6, 1, tzinfo=UTC)
_KA = datetime(2030, 1, 1, tzinfo=UTC)
_VD = date(2026, 6, 1)
_D = (date(2026, 5, 26), date(2026, 5, 27), date(2026, 5, 28), date(2026, 5, 29))
_B0, _B1 = _D[3], _D[3] + timedelta(days=1)


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
    for ccy in ("USD", "EUR"):
        db.add(Currency(tenant_id=SYSTEM_TENANT_ID, code=ccy, name=ccy, valid_from=_T0))
    db.flush()

    # --- The full chain: exposure -> factor-exposure -> covariance -> VaR + a PM-1 return run.
    pf = create_portfolio(
        db,
        tenant_id=tenant_id,
        code=f"ACCT-{uuid.uuid4().hex[:6]}",
        name="acct",
        node_type="ACCOUNT",
        actor=PortfolioActor(actor_id="s"),
    ).id
    insts: list[str] = []
    for code, qty, mark, ccy in (
        ("I-USD", "100", "300.00", "USD"),
        ("I-EUR", "100", "400.00", "EUR"),
    ):
        inst = create_instrument(
            db,
            tenant_id=tenant_id,
            code=f"{code}-{uuid.uuid4().hex[:6]}",
            name="i",
            asset_class="BOND",
            actor=ReferenceActor(actor_id="s"),
        ).id
        insts.append(inst)
        create_position(
            db,
            portfolio_id=pf,
            instrument_id=inst,
            acting_tenant=tenant_id,
            actor=PositionActor(actor_id="s"),
            quantity=Decimal(qty),
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
        as_of_valid_at=_VALID_AT,
        as_of_known_at=_KA,
        base_currency="USD",
    )
    assert exposure.status == "COMPLETED"
    factor_ids: list[str] = []
    for code, ccy, values in (
        ("FX_USD", "USD", ["0.01", "0.02", "0.03", "0.04"]),
        ("FX_EUR", "EUR", ["0.04", "0.03", "0.02", "0.01"]),
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
    db.flush()
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
        as_of_valid_at=_VALID_AT,
    )
    var_mv = register_var_model(
        db, tenant_id=tenant_id, actor_id="a", code_version="risk-v1", confidence_level="0.99"
    )
    var_run = run_var(
        db,
        acting_tenant=tenant_id,
        actor=VarActor(actor_id="a"),
        code_version="risk-v1",
        environment_id="ci",
        model_version_id=var_mv.id,
        exposure_run_id=fx_run.run.run_id,
        covariance_run_id=cov_run.run.run_id,
    )
    assert var_run.status == "COMPLETED"

    boundary_runs: list[str] = []
    for vdate, marks in ((_B0, ("300.00", "400.00")), (_B1, ("290.00", "390.00"))):
        for inst, mark in zip(insts, marks, strict=True):
            create_valuation(
                db,
                portfolio_id=pf,
                instrument_id=inst,
                valuation_date=vdate,
                acting_tenant=tenant_id,
                actor=ValuationActor(actor_id="s"),
                mark_value=Decimal(mark),
                currency_code="USD",
                valid_from=_T0,
            )
        boundary = run_exposure(
            db,
            acting_tenant=tenant_id,
            actor=ExposureActor(actor_id="a"),
            code_version="v1",
            environment_id="ci",
            portfolio_id=pf,
            as_of_valid_at=datetime(vdate.year, vdate.month, vdate.day, tzinfo=UTC),
            as_of_known_at=_KA,
            base_currency="USD",
        )
        boundary_runs.append(boundary.run.run_id)
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
        exposure_run_ids=boundary_runs,
    )
    assert ret.status == "COMPLETED"
    db.commit()
    principal = Principal(user_id=user.id, tenant_id=tenant_id)

    def _override_db() -> Iterator[Session]:
        yield db

    app = FastAPI()
    app.include_router(risk_router)
    app.dependency_overrides[get_db] = _override_db
    try:
        yield TestClient(app), principal, db, ret.run.run_id, var_run.run.run_id
    finally:
        db.close()
        engine.dispose()


def _h(p: Principal) -> dict[str, str]:
    return {"X-User-Id": p.user_id, "X-Tenant-Id": p.tenant_id}


def _register(client: TestClient, p: Principal, alpha: str = "0.05") -> str:
    resp = client.post(
        "/risk/models/var-backtest",
        json={"code_version": "bt-v1", "alpha": alpha},
        headers=_h(p),
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["model_version_id"]


def _run_body(mv: str, ret_run: str, var_run: str, **kw) -> dict:  # noqa: ANN003
    return {
        "code_version": "bt-v1",
        "environment_id": "ci",
        "model_version_id": mv,
        "portfolio_return_run_id": ret_run,
        "var_run_ids": [var_run],
        **kw,
    }


def _count_runs(db: Session, tenant: str) -> int:
    return db.execute(
        select(func.count())
        .select_from(CalculationRun)
        .where(CalculationRun.tenant_id == tenant, CalculationRun.run_type == "VAR_BACKTEST")
    ).scalar_one()


def test_register_run_and_read_roundtrip(ctx) -> None:  # noqa: ANN001
    client, p, db, ret_run, var_run = ctx
    mv = _register(client, p)
    resp = client.post(
        "/risk/var-backtests/runs", json=_run_body(mv, ret_run, var_run), headers=_h(p)
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["status"] == "COMPLETED" and body["run_type"] == "VAR_BACKTEST"
    assert len(body["rows"]) == 3  # EXCEPTION_INDICATOR + EXCEPTION_COUNT + KUPIEC_LR (no Basel)
    lr = next(r for r in body["rows"] if r["metric_type"] == "KUPIEC_LR")
    assert lr["metric_value"] == "9.210340"  # -2 ln(0.01) @6dp — the exception case
    assert lr["test_decision"] == "REJECT"
    assert lr["basel_zone"] is None
    ind = next(r for r in body["rows"] if r["metric_type"] == "EXCEPTION_INDICATOR")
    assert ind["realized_pnl"] == "-2000.000000" and ind["var_metric_type"] == "VAR_PARAMETRIC"
    for r in body["rows"]:
        assert "E" not in r["metric_value"] and "e" not in r["metric_value"]  # fixed-point
    run_read = client.get(f"/risk/var-backtests/runs/{body['run_id']}", headers=_h(p))
    assert run_read.status_code == 200 and len(run_read.json()["rows"]) == 3
    row_read = client.get(f"/risk/var-backtests/{lr['id']}", headers=_h(p))
    assert row_read.status_code == 200 and row_read.json()["metric_value"] == lr["metric_value"]
    listing = client.get("/risk/runs", params={"run_type": "VAR_BACKTEST"}, headers=_h(p))
    assert listing.status_code == 200
    assert any(item["run_id"] == body["run_id"] for item in listing.json()["items"])


def test_register_identity_conflicts_and_vocabulary(ctx) -> None:  # noqa: ANN001
    client, p, db, ret_run, var_run = ctx
    mv = _register(client, p)
    assert _register(client, p) == mv  # idempotent same (code_version, alpha)
    resp = client.post(
        "/risk/models/var-backtest",
        json={"code_version": "bt-v1", "alpha": "0.01"},
        headers=_h(p),
    )
    assert resp.status_code == 409  # same label, different declared alpha
    resp = client.post(
        "/risk/models/var-backtest",
        json={"code_version": "bt-v9", "alpha": "0.10"},
        headers=_h(p),
    )
    assert resp.status_code == 422  # off-vocabulary alpha (never a 500)


def test_deny_by_default_and_view_only_cannot_run(ctx) -> None:  # noqa: ANN001
    client, p, db, ret_run, var_run = ctx
    mv = _register(client, p)
    nobody = Principal(user_id=str(uuid.uuid4()), tenant_id=p.tenant_id)
    resp = client.post(
        "/risk/var-backtests/runs", json=_run_body(mv, ret_run, var_run), headers=_h(nobody)
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
        "/risk/var-backtests/runs", json=_run_body(mv, ret_run, var_run), headers=_h(vp)
    )
    assert resp.status_code == 403  # .view does not grant .run
    assert _count_runs(db, p.tenant_id) == 0


def test_pre_create_refusals(ctx) -> None:  # noqa: ANN001
    client, p, db, ret_run, var_run = ctx
    mv = _register(client, p)
    # Unregistered model_version (CTRL-003 fail-closed).
    resp = client.post(
        "/risk/var-backtests/runs",
        json=_run_body(str(uuid.uuid4()), ret_run, var_run),
        headers=_h(p),
    )
    assert resp.status_code == 422
    # Both modes at once => 422.
    resp = client.post(
        "/risk/var-backtests/runs",
        json=_run_body(mv, ret_run, var_run, snapshot_id=str(uuid.uuid4())),
        headers=_h(p),
    )
    assert resp.status_code == 422
    # Unknown var run id => 422 (uniform pre-create refusal).
    resp = client.post(
        "/risk/var-backtests/runs",
        json=_run_body(mv, ret_run, str(uuid.uuid4())),
        headers=_h(p),
    )
    assert resp.status_code == 422
    # The runs swapped (a VAR run as the return run) => 422 (the run-type gate).
    resp = client.post(
        "/risk/var-backtests/runs",
        json=_run_body(mv, var_run, ret_run),
        headers=_h(p),
    )
    assert resp.status_code == 422
    assert _count_runs(db, p.tenant_id) == 0  # every refusal left ZERO run


def test_no_mutating_verbs(ctx) -> None:  # noqa: ANN001
    client, p, db, ret_run, var_run = ctx
    for verb in ("put", "patch", "delete"):
        resp = getattr(client, verb)("/risk/var-backtests/runs", headers=_h(p))
        assert resp.status_code == 405
