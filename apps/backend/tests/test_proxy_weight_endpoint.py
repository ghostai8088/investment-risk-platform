"""End-to-end tests of the PA-3 proxy-weight regression endpoints (ENT-057).

SQLite has no RLS (tenant isolation + append-only proofs live in the PG leg); here we prove the
governed model registration (201 / idempotent / 409 on a different declared floor), the
build-in-request run + read round-trip, entitlement gating (view-only cannot run — the REUSED
``risk.run``/``risk.view``), and the PROMOTION endpoint (a REGRESSION weight cites a COMPLETED
estimate run; citing a wrong-type run is refused).
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from irp_backend.api.marketdata import proxy_mapping_router
from irp_backend.api.risk import router as risk_router
from irp_backend.deps import get_db
from irp_shared.db.session import make_engine, make_session_factory
from irp_shared.entitlement.bootstrap import SYSTEM_TENANT_ID
from irp_shared.entitlement.models import AppUser, Permission, Role, RolePermission, UserRole
from irp_shared.entitlement.service import Principal
from irp_shared.marketdata.factor import (
    FactorActor,
    capture_factor,
    capture_factor_return,
    resolve_factor,
)
from irp_shared.models import Base
from irp_shared.perf import (
    DesmoothedReturnActor,
    register_desmoothed_return_model,
    run_desmoothed_return,
)
from irp_shared.portfolio import PortfolioActor, create_portfolio
from irp_shared.reference.instrument import create_instrument
from irp_shared.reference.models import Currency
from irp_shared.reference.service import ReferenceActor
from irp_shared.valuation import create_valuation
from irp_shared.valuation.service import ValuationActor

_PERMS = ("risk.run", "risk.view", "model.inventory.register", "marketdata.ingest")
_T0 = datetime(2024, 6, 1, tzinfo=UTC)
MARK_DATES = (
    date(2024, 9, 30),
    date(2024, 12, 31),
    date(2025, 3, 31),
    date(2025, 6, 30),
    date(2025, 9, 30),
    date(2025, 12, 31),
)
MARK_VALUES = ("100.00", "103.00", "104.50", "108.00", "106.00", "111.00")


@pytest.fixture
def ctx() -> Iterator[tuple[TestClient, Principal, Session, str, str, str, str]]:
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
        code="ACCT",
        name="acct",
        node_type="ACCOUNT",
        actor=PortfolioActor(actor_id="s"),
    ).id
    inst = create_instrument(
        db,
        tenant_id=tenant_id,
        code="FUND",
        name="fund",
        asset_class="PRIVATE_EQUITY",
        actor=ReferenceActor(actor_id="s"),
    ).id
    for d, v in zip(MARK_DATES, MARK_VALUES, strict=True):
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
    dm = register_desmoothed_return_model(
        db, tenant_id=tenant_id, actor_id="s", code_version="v1", alpha="0.5"
    )
    dr = run_desmoothed_return(
        db,
        acting_tenant=tenant_id,
        actor=DesmoothedReturnActor(actor_id="a"),
        code_version="v1",
        environment_id="ci",
        model_version_id=str(dm.id),
        portfolio_id=pf,
        instrument_id=inst,
        window_start=date(2024, 6, 1),
        window_end=date(2026, 1, 1),
    )
    fx_usd = capture_factor(
        db,
        factor_code="FX_USD",
        factor_source="VENDOR_F",
        factor_family="CURRENCY",
        currency_code=None,
        acting_tenant=tenant_id,
        actor=FactorActor(actor_id="s"),
        valid_from=_T0,
    ).id
    fx_eur = capture_factor(
        db,
        factor_code="FX_EUR",
        factor_source="VENDOR_F",
        factor_family="CURRENCY",
        currency_code=None,
        acting_tenant=tenant_id,
        actor=FactorActor(actor_id="s"),
        valid_from=_T0,
    ).id
    for fid, vals in (
        (fx_usd, ["0.01", "0.02", "-0.01", "0.03", "0.00"]),
        (fx_eur, ["0.02", "-0.01", "0.01", "0.00", "0.02"]),
    ):
        factor = resolve_factor(db, fid, acting_tenant=tenant_id)
        for d, v in zip(MARK_DATES[1:], vals, strict=True):
            capture_factor_return(
                db,
                factor,
                return_date=d,
                return_value=Decimal(v),
                acting_tenant=tenant_id,
                actor=FactorActor(actor_id="s"),
                valid_from=_T0,
            )
    db.commit()
    principal = Principal(user_id=user.id, tenant_id=tenant_id)

    def _override_db() -> Iterator[Session]:
        yield db

    app = FastAPI()
    app.include_router(risk_router)
    app.include_router(proxy_mapping_router, prefix="/marketdata")
    app.dependency_overrides[get_db] = _override_db
    try:
        yield TestClient(app), principal, db, str(dr.run.run_id), fx_usd, fx_eur, inst
    finally:
        db.close()
        engine.dispose()


def _h(p: Principal) -> dict[str, str]:
    return {"X-User-Id": p.user_id, "X-Tenant-Id": p.tenant_id}


def _register(client: TestClient, p: Principal, min_obs: int = 4) -> str:
    resp = client.post(
        "/risk/models/proxy-weight-regression",
        json={"code_version": "risk-v1", "min_observations": min_obs},
        headers=_h(p),
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["model_version_id"]


def test_register_idempotent_and_conflict(ctx) -> None:  # noqa: ANN001
    client, p, _db, *_ = ctx
    mv = _register(client, p)
    # idempotent: same identity -> same version.
    assert _register(client, p) == mv
    # a different declared floor on the same label is a governed 409.
    resp = client.post(
        "/risk/models/proxy-weight-regression",
        json={"code_version": "risk-v1", "min_observations": 6},
        headers=_h(p),
    )
    assert resp.status_code == 409, resp.text
    # a sub-floor min_observations is a 422.
    resp = client.post(
        "/risk/models/proxy-weight-regression",
        json={"code_version": "risk-v2", "min_observations": 2},
        headers=_h(p),
    )
    assert resp.status_code == 422, resp.text


def test_run_and_read_roundtrip(ctx) -> None:  # noqa: ANN001
    client, p, _db, dr, fx_usd, fx_eur, _inst = ctx
    mv = _register(client, p)
    resp = client.post(
        "/risk/proxy-weight-estimates/runs",
        json={
            "code_version": "risk-v1",
            "environment_id": "ci",
            "model_version_id": mv,
            "desmoothed_run_id": dr,
            "factor_ids": [fx_usd, fx_eur],
        },
        headers=_h(p),
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["status"] == "COMPLETED"
    assert body["run_type"] == "PROXY_WEIGHT_ESTIMATE"
    metrics = sorted(r["metric_type"] for r in body["rows"])
    assert metrics == ["ESTIMATION_SUMMARY", "INTERCEPT", "WEIGHT", "WEIGHT"]
    # the read round-trip surfaces the same rows.
    read = client.get(f"/risk/proxy-weight-estimates/runs/{body['run_id']}", headers=_h(p))
    assert read.status_code == 200 and len(read.json()["rows"]) == 4
    # API-1 by-id PARITY read: the single result row round-trips (run-pinned); unknown id 404s.
    one_id = body["rows"][0]["id"]
    one = client.get(f"/risk/proxy-weight-estimates/{one_id}", headers=_h(p))
    assert one.status_code == 200 and one.json()["id"] == one_id
    assert one.json()["calculation_run_id"] == body["run_id"]
    assert (
        client.get(f"/risk/proxy-weight-estimates/{uuid.uuid4()}", headers=_h(p)).status_code == 404
    )


def test_view_only_cannot_run(ctx) -> None:  # noqa: ANN001
    client, p, db, dr, fx_usd, fx_eur, _inst = ctx
    mv = _register(client, p)
    # Strip risk.run from the role: view-only must be denied (403), no run created.
    from irp_shared.entitlement.models import Permission, RolePermission

    run_perm = db.execute(
        __import__("sqlalchemy").select(Permission).where(Permission.code == "risk.run")
    ).scalar_one()
    db.query(RolePermission).filter(RolePermission.permission_id == run_perm.id).delete()
    db.commit()
    resp = client.post(
        "/risk/proxy-weight-estimates/runs",
        json={
            "code_version": "risk-v1",
            "environment_id": "ci",
            "model_version_id": mv,
            "desmoothed_run_id": dr,
            "factor_ids": [fx_usd, fx_eur],
        },
        headers=_h(p),
    )
    assert resp.status_code == 403, resp.text


def test_promote_endpoint(ctx) -> None:  # noqa: ANN001
    client, p, _db, dr, fx_usd, _fx_eur, inst = ctx
    mv = _register(client, p)
    run = client.post(
        "/risk/proxy-weight-estimates/runs",
        json={
            "code_version": "risk-v1",
            "environment_id": "ci",
            "model_version_id": mv,
            "desmoothed_run_id": dr,
            "factor_ids": [fx_usd, _fx_eur],
        },
        headers=_h(p),
    ).json()
    est_run = run["run_id"]
    # promote: a REGRESSION weight citing the COMPLETED estimate run.
    promoted = client.post(
        "/marketdata/proxy-mappings/promote-estimate",
        json={
            "private_instrument_id": inst,
            "factor_id": fx_usd,
            "weight": "0.6",
            "source_calculation_run_id": est_run,
        },
        headers=_h(p),
    )
    assert promoted.status_code == 201, promoted.text
    assert promoted.json()["mapping_method"] == "REGRESSION"
    # citing a NON-estimate run (the desmoothed run) is refused.
    bad = client.post(
        "/marketdata/proxy-mappings/promote-estimate",
        json={
            "private_instrument_id": inst,
            "factor_id": _fx_eur,
            "weight": "0.3",
            "source_calculation_run_id": dr,
        },
        headers=_h(p),
    )
    assert bad.status_code == 422, bad.text
    # HG-1 (OD-HG-1-A): the additive opt-in bound round-trips. This estimate run has a REAL
    # snapshot whose span end is the fixture's desmoothed window — a generous bound passes...
    ok = client.post(
        "/marketdata/proxy-mappings/promote-estimate",
        json={
            "private_instrument_id": inst,
            "factor_id": _fx_eur,
            "weight": "0.3",
            "source_calculation_run_id": est_run,
            "max_promotion_age_days": 100000,
        },
        headers=_h(p),
    )
    assert ok.status_code == 201, ok.text
    # ... a bound of 1 day refuses with the AGE-SPECIFIC 422 detail (the distinct exact-type
    # map entry — never the false "cited run is not visible" detail).
    stale = client.post(
        "/marketdata/proxy-mappings/promote-estimate",
        json={
            "private_instrument_id": inst,
            "factor_id": fx_usd,
            "weight": "0.5",
            "source_calculation_run_id": est_run,
            "max_promotion_age_days": 1,
        },
        headers=_h(p),
    )
    assert stale.status_code == 422, stale.text
    assert "max_promotion_age_days" in stale.json()["detail"]
    assert "not a visible COMPLETED" not in stale.json()["detail"]
