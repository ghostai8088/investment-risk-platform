"""End-to-end tests of the P3-6 stress/scenario endpoints (ENT-029/030; REUSES risk.run/risk.view —
NO new permission code).

SQLite has no RLS (tenant isolation + append-only proofs live in
``packages/shared-python/tests/test_scenario_pg.py``); here we prove entitlement gating on the
REUSED verbs (deny-by-default; view-only cannot run), the scenario_definition EV create (+ the 409
duplicate-code + the 422 off-vocabulary scenario_type), the scenario_shock FR capture/supersede/
correct/as-of protocol over the API (+ the MD-H1 backdated-supersede 422 + the 409 duplicate open
shock), the build-in-request run + read round-trip (the golden -3000/+2000/-1000 with coverage
counts), fixed-point decimal serialization, the pre-create refusals (422), the ``/risk/runs`` list
surfacing the SCENARIO run, and no PUT/PATCH/DELETE on the route families.

Golden derivation: FX_USD exposure 30000 (I-USD qty 100 x 300, USD) + FX_EUR exposure 40000 (I-EUR
qty 100 x 400 x fx 1.0, base USD). Shocks FX_USD -0.10, FX_EUR +0.05 -> pnl -3000 / +2000 / total
-1000; both factors exposed AND shocked (n_exposed=2, n_shocked=2, n_unmatched=0).
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
from irp_shared.portfolio import PortfolioActor, create_portfolio
from irp_shared.position import create_position
from irp_shared.position.service import PositionActor
from irp_shared.reference.instrument import create_instrument
from irp_shared.reference.models import Currency
from irp_shared.reference.service import ReferenceActor
from irp_shared.risk import (
    FactorExposureActor,
    register_factor_exposure_model,
    run_factor_exposure,
)
from irp_shared.valuation import create_valuation
from irp_shared.valuation.service import ValuationActor

_PERMS = ("risk.run", "risk.view", "model.inventory.register")
_T0 = datetime(2026, 1, 1, tzinfo=UTC)
_VALID_AT = datetime(2026, 6, 1, tzinfo=UTC)
_KA = datetime(2030, 1, 1, tzinfo=UTC)
_VD = date(2026, 6, 1)
_D = (date(2026, 5, 26), date(2026, 5, 27), date(2026, 5, 28), date(2026, 5, 29))


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
    for ccy in ("USD", "EUR"):
        db.add(Currency(tenant_id=SYSTEM_TENANT_ID, code=ccy, name=ccy, valid_from=_T0))
    db.flush()

    # --- The chain: exposure -> factor-exposure (FX_USD 30000 + FX_EUR 40000, base USD).
    pf = create_portfolio(
        db,
        tenant_id=tenant_id,
        code=f"ACCT-{uuid.uuid4().hex[:6]}",
        name="acct",
        node_type="ACCOUNT",
        actor=PortfolioActor(actor_id="s"),
    ).id
    for code, mark, ccy in (("I-USD", "300.00", "USD"), ("I-EUR", "400.00", "EUR")):
        inst = create_instrument(
            db,
            tenant_id=tenant_id,
            code=f"{code}-{uuid.uuid4().hex[:6]}",
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
        as_of_valid_at=_VALID_AT,
        as_of_known_at=_KA,
        base_currency="USD",
    )
    assert exposure.status == "COMPLETED"
    factor_ids: list[str] = []
    for code, ccy in (("FX_USD", "USD"), ("FX_EUR", "EUR")):
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
        for d, v in zip(_D, ["0.01", "0.02", "0.03", "0.04"], strict=True):
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
    assert fx_run.status == "COMPLETED"
    db.commit()
    principal = Principal(user_id=user.id, tenant_id=tenant_id)

    def _override_db() -> Iterator[Session]:
        yield db

    app = FastAPI()
    app.include_router(risk_router)
    app.dependency_overrides[get_db] = _override_db
    try:
        yield TestClient(app), principal, db, fx_run.run.run_id, factor_ids[0], factor_ids[1]
    finally:
        db.close()
        engine.dispose()


def _h(p: Principal) -> dict[str, str]:
    return {"X-User-Id": p.user_id, "X-Tenant-Id": p.tenant_id}


def _register(client: TestClient, p: Principal, code_version: str = "s-v1") -> str:
    resp = client.post("/risk/models/scenario", json={"code_version": code_version}, headers=_h(p))
    assert resp.status_code == 201, resp.text
    return resp.json()["model_version_id"]


def _make_definition(client: TestClient, p: Principal, code: str = "CRASH") -> str:
    resp = client.post(
        "/risk/scenarios",
        json={"code": code, "name": "Crash", "scenario_type": "HISTORICAL"},
        headers=_h(p),
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _capture(client: TestClient, p: Principal, def_id: str, fid: str, shock: str) -> None:
    resp = client.post(
        f"/risk/scenarios/{def_id}/shocks",
        json={"factor_id": fid, "shock_value": shock, "valid_from": _T0.isoformat()},
        headers=_h(p),
    )
    assert resp.status_code == 201, resp.text


def _run_body(mv: str, fx_run: str, def_id: str, **kw) -> dict:  # noqa: ANN003
    return {
        "code_version": "s-v1",
        "environment_id": "ci",
        "model_version_id": mv,
        "factor_exposure_run_id": fx_run,
        "scenario_definition_id": def_id,
        **kw,
    }


def _count_runs(db: Session, tenant: str) -> int:
    return db.execute(
        select(func.count())
        .select_from(CalculationRun)
        .where(CalculationRun.tenant_id == tenant, CalculationRun.run_type == "SCENARIO")
    ).scalar_one()


def test_full_lifecycle_run_and_read_roundtrip(ctx) -> None:  # noqa: ANN001
    client, p, db, fx_run, fid_usd, fid_eur = ctx
    mv = _register(client, p)
    def_id = _make_definition(client, p)
    _capture(client, p, def_id, fid_usd, "-0.10")
    _capture(client, p, def_id, fid_eur, "0.05")

    resp = client.post("/risk/scenario-runs", json=_run_body(mv, fx_run, def_id), headers=_h(p))
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["status"] == "COMPLETED" and body["run_type"] == "SCENARIO"
    assert len(body["rows"]) == 3  # 2 per-factor + 1 TOTAL

    by_factor = {r["factor_code"]: r for r in body["rows"] if r["metric_type"] == "SCENARIO_PNL"}
    assert by_factor["FX_USD"]["pnl"] == "-3000.000000"
    assert by_factor["FX_EUR"]["pnl"] == "2000.000000"
    total = next(r for r in body["rows"] if r["metric_type"] == "SCENARIO_PNL_TOTAL")
    assert total["pnl"] == "-1000.000000" and total["factor_code"] is None
    assert total["n_factors_exposed"] == 2
    assert total["n_factors_shocked"] == 2
    assert total["n_shocks_unmatched"] == 0
    for r in body["rows"]:
        assert "E" not in r["pnl"] and "e" not in r["pnl"]  # fixed-point, never scientific

    run_read = client.get(f"/risk/scenario-runs/{body['run_id']}", headers=_h(p))
    assert run_read.status_code == 200 and len(run_read.json()["rows"]) == 3
    listing = client.get("/risk/runs", params={"run_type": "SCENARIO"}, headers=_h(p))
    assert listing.status_code == 200
    assert any(item["run_id"] == body["run_id"] for item in listing.json()["items"])


def test_definition_vocabulary_and_duplicate_code(ctx) -> None:  # noqa: ANN001
    client, p, db, fx_run, fid_usd, fid_eur = ctx
    _make_definition(client, p, code="DUP")
    dup = client.post(
        "/risk/scenarios",
        json={"code": "DUP", "name": "again", "scenario_type": "HISTORICAL"},
        headers=_h(p),
    )
    assert dup.status_code == 409  # duplicate open code
    # The shared write-raiser DISCRIMINATES the conflict: a duplicate CODE gets a definition-worded
    # detail, never the shock-worded one (which would misdescribe the collision).
    assert "definition" in dup.json()["detail"] and "shock" not in dup.json()["detail"]
    bad = client.post(
        "/risk/scenarios",
        json={"code": "X", "name": "n", "scenario_type": "NOPE"},
        headers=_h(p),
    )
    assert bad.status_code == 422  # off-vocabulary scenario_type (never a 500)


def test_shock_value_over_column_capacity_is_422(ctx) -> None:  # noqa: ANN001
    client, p, db, fx_run, fid_usd, fid_eur = ctx
    def_id = _make_definition(client, p)
    # |value| >= 1E8 overflows Numeric(20,12); the binder refuses it as a governed 422 BEFORE the
    # write, rather than letting a PG numeric-overflow DataError escape as an opaque 500.
    resp = client.post(
        f"/risk/scenarios/{def_id}/shocks",
        json={"factor_id": fid_usd, "shock_value": "100000000", "valid_from": _T0.isoformat()},
        headers=_h(p),
    )
    assert resp.status_code == 422


def test_shock_supersede_correct_and_as_of(ctx) -> None:  # noqa: ANN001
    client, p, db, fx_run, fid_usd, fid_eur = ctx
    def_id = _make_definition(client, p)
    _capture(client, p, def_id, fid_usd, "-0.10")

    # A duplicate OPEN shock for the same (scenario, factor) is a discriminated 409.
    again = client.post(
        f"/risk/scenarios/{def_id}/shocks",
        json={"factor_id": fid_usd, "shock_value": "-0.20", "valid_from": _T0.isoformat()},
        headers=_h(p),
    )
    assert again.status_code == 409

    # An effective-dated supersede FORWARD of the open head succeeds (record_version 2).
    sup = client.post(
        f"/risk/scenarios/{def_id}/shocks/supersede",
        json={
            "factor_id": fid_usd,
            "shock_value": "-0.15",
            "effective_at": (_T0 + timedelta(days=120)).isoformat(),
        },
        headers=_h(p),
    )
    assert sup.status_code == 201, sup.text
    assert sup.json()["record_version"] == 2

    # A BACKDATED supersede (window incoherence, MD-H1) is a 422.
    back = client.post(
        f"/risk/scenarios/{def_id}/shocks/supersede",
        json={
            "factor_id": fid_usd,
            "shock_value": "-0.30",
            "effective_at": (_T0 + timedelta(days=1)).isoformat(),
        },
        headers=_h(p),
    )
    assert back.status_code == 422

    # A correction (system-time restatement) requires a reason and bumps the version.
    corr = client.post(
        f"/risk/scenarios/{def_id}/shocks/correct",
        json={"factor_id": fid_usd, "shock_value": "-0.16", "restatement_reason": "typo"},
        headers=_h(p),
    )
    assert corr.status_code == 201, corr.text

    # The bitemporal reconstruct: an instant before ANY version exists is a clean 404.
    miss = client.get(
        f"/risk/scenarios/{def_id}/shocks/as-of",
        params={
            "factor_id": fid_usd,
            "valid_at": (_T0 - timedelta(days=1)).isoformat(),
            "known_at": (_T0 - timedelta(days=1)).isoformat(),
        },
        headers=_h(p),
    )
    assert miss.status_code == 404


def test_deny_by_default_and_view_only_cannot_run(ctx) -> None:  # noqa: ANN001
    client, p, db, fx_run, fid_usd, fid_eur = ctx
    mv = _register(client, p)
    def_id = _make_definition(client, p)
    _capture(client, p, def_id, fid_usd, "-0.10")

    nobody = Principal(user_id=str(uuid.uuid4()), tenant_id=p.tenant_id)
    resp = client.post(
        "/risk/scenario-runs", json=_run_body(mv, fx_run, def_id), headers=_h(nobody)
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
    resp = client.post("/risk/scenario-runs", json=_run_body(mv, fx_run, def_id), headers=_h(vp))
    assert resp.status_code == 403  # .view does not grant .run
    # A view-only principal also cannot create a definition (defining IS the running persona).
    assert (
        client.post(
            "/risk/scenarios",
            json={"code": "Z", "name": "z", "scenario_type": "HISTORICAL"},
            headers=_h(vp),
        ).status_code
        == 403
    )
    assert _count_runs(db, p.tenant_id) == 0


def test_pre_create_refusals(ctx) -> None:  # noqa: ANN001
    client, p, db, fx_run, fid_usd, fid_eur = ctx
    mv = _register(client, p)
    def_id = _make_definition(client, p)
    _capture(client, p, def_id, fid_usd, "-0.10")

    # Unregistered model_version (CTRL-003 fail-closed) => 422.
    resp = client.post(
        "/risk/scenario-runs",
        json=_run_body(str(uuid.uuid4()), fx_run, def_id),
        headers=_h(p),
    )
    assert resp.status_code == 422

    # Both build-in-request AND a snapshot_id at once => 422 (the P3-C1 XOR gate).
    resp = client.post(
        "/risk/scenario-runs",
        json=_run_body(mv, fx_run, def_id, snapshot_id=str(uuid.uuid4())),
        headers=_h(p),
    )
    assert resp.status_code == 422

    # Unknown factor-exposure run id => 422 (uniform pre-create refusal).
    resp = client.post(
        "/risk/scenario-runs",
        json=_run_body(mv, str(uuid.uuid4()), def_id),
        headers=_h(p),
    )
    assert resp.status_code == 422

    # Unknown scenario definition id => 422.
    resp = client.post(
        "/risk/scenario-runs",
        json=_run_body(mv, fx_run, str(uuid.uuid4())),
        headers=_h(p),
    )
    assert resp.status_code == 422
    assert _count_runs(db, p.tenant_id) == 0  # every refusal left ZERO run


def test_unknown_run_and_definition_are_404(ctx) -> None:  # noqa: ANN001
    client, p, db, fx_run, fid_usd, fid_eur = ctx
    assert client.get(f"/risk/scenario-runs/{uuid.uuid4()}", headers=_h(p)).status_code == 404
    assert client.get(f"/risk/scenarios/{uuid.uuid4()}/shocks", headers=_h(p)).status_code == 404


def test_no_mutating_verbs(ctx) -> None:  # noqa: ANN001
    client, p, db, fx_run, fid_usd, fid_eur = ctx
    for verb in ("put", "patch", "delete"):
        resp = getattr(client, verb)("/risk/scenario-runs", headers=_h(p))
        assert resp.status_code == 405
