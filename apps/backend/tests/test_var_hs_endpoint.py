"""End-to-end tests of the VAR-HS-1 historical-simulation VaR endpoints: registration (incl.
the adequacy-floor 422 and the identity 409), the build-path run + read round-trip through the
EXISTING GET /risk/vars/* family (metric_type='VAR_HISTORICAL'; z_score/sigma/covariance_run_id
honestly null), decimal string serialization, entitlement gating, the both-modes 422, and
no-mutation methods. RLS/append-only proofs live in the PG suite."""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from irp_backend.api.risk import router as risk_router
from irp_backend.deps import get_db
from irp_shared.db.session import make_engine, make_session_factory
from irp_shared.entitlement.bootstrap import SYSTEM_TENANT_ID
from irp_shared.entitlement.models import AppUser, Permission, Role, RolePermission, UserRole
from irp_shared.exposure import ExposureActor, run_exposure
from irp_shared.marketdata import FxRateActor, capture_fx_rate
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
from irp_shared.risk import FactorExposureActor, register_factor_exposure_model, run_factor_exposure
from irp_shared.valuation import create_valuation
from irp_shared.valuation.service import ValuationActor

_PERMS = ("risk.run", "risk.view", "model.inventory.register")
_T0 = datetime(2026, 1, 1, tzinfo=UTC)
_VA = datetime(2026, 6, 1, tzinfo=UTC)
_KA = datetime(2030, 1, 1, tzinfo=UTC)
_VD = date(2026, 6, 1)


@pytest.fixture
def ctx() -> Iterator[tuple[TestClient, dict[str, str], Session, str]]:
    engine = make_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    db = make_session_factory(engine)()

    tenant = str(uuid.uuid4())
    user = AppUser(tenant_id=tenant, display_name="U")
    role = Role(tenant_id=tenant, code="r", name="R")
    db.add_all([user, role])
    db.flush()
    for code in _PERMS:
        perm = Permission(code=code, description="d")
        db.add(perm)
        db.flush()
        db.add(RolePermission(role_id=role.id, permission_id=perm.id))
    db.add(UserRole(tenant_id=tenant, user_id=user.id, role_id=role.id))
    for code in ("USD", "EUR"):
        db.add(Currency(tenant_id=SYSTEM_TENANT_ID, code=code, name=code, valid_from=_T0))
    db.flush()

    # The chain: P&L_i = -10*i over 20 dates (see test_var_hs.py's hand-reference design).
    pf = create_portfolio(
        db,
        tenant_id=tenant,
        code="ACCT",
        name="a",
        node_type="ACCOUNT",
        actor=PortfolioActor(actor_id="s"),
    ).id
    for code, mark, ccy in (("I-USD", "300.00", "USD"), ("I-EUR", "400.00", "EUR")):
        inst = create_instrument(
            db,
            tenant_id=tenant,
            code=code,
            name="i",
            asset_class="BOND",
            actor=ReferenceActor(actor_id="s"),
        ).id
        create_position(
            db,
            portfolio_id=pf,
            instrument_id=inst,
            acting_tenant=tenant,
            actor=PositionActor(actor_id="s"),
            quantity=Decimal("100"),
            valid_from=_T0,
        )
        create_valuation(
            db,
            portfolio_id=pf,
            instrument_id=inst,
            valuation_date=_VD,
            acting_tenant=tenant,
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
        acting_tenant=tenant,
        actor=FxRateActor(actor_id="s"),
        valid_from=_T0,
    )
    exposure = run_exposure(
        db,
        acting_tenant=tenant,
        actor=ExposureActor(actor_id="a"),
        code_version="v1",
        environment_id="ci",
        portfolio_id=pf,
        as_of_valid_at=_VA,
        as_of_known_at=_KA,
        base_currency="USD",
    )
    factor_ids: list[str] = []
    base_day = date(2026, 4, 1)
    for code, ccy, sign in (("FX_USD", "USD", 1), ("FX_EUR", "EUR", -1)):
        fid = capture_factor(
            db,
            factor_code=code,
            factor_source="V",
            factor_family="CURRENCY",
            currency_code=ccy,
            acting_tenant=tenant,
            actor=FactorActor(actor_id="s"),
            valid_from=_T0,
        ).id
        factor = resolve_factor(db, fid, acting_tenant=tenant)
        for i in range(1, 22):
            capture_factor_return(
                db,
                factor,
                return_date=base_day + timedelta(days=i),
                return_value=Decimal(sign * i) / Decimal(1000),
                acting_tenant=tenant,
                actor=FactorActor(actor_id="s"),
                valid_from=_T0,
            )
        factor_ids.append(fid)
    fx_mv = register_factor_exposure_model(db, tenant_id=tenant, actor_id="a", code_version="v1")
    fx_run = run_factor_exposure(
        db,
        acting_tenant=tenant,
        actor=FactorExposureActor(actor_id="a"),
        code_version="v1",
        environment_id="ci",
        model_version_id=fx_mv.id,
        exposure_run_id=exposure.run.run_id,
        factor_ids=factor_ids,
    )
    db.commit()

    app = FastAPI()
    app.include_router(risk_router)
    app.dependency_overrides[get_db] = lambda: db
    client = TestClient(app)
    headers = {"X-User-Id": str(user.id), "X-Tenant-Id": tenant}
    try:
        yield client, headers, db, fx_run.run.run_id
    finally:
        db.close()


def _register(client: TestClient, headers: dict[str, str], window: int = 21) -> str:
    resp = client.post(
        "/risk/models/var-historical",
        json={"code_version": "v1", "confidence_level": "0.95", "window_observations": window},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["model_version_id"]


def test_register_floor_and_conflict(ctx) -> None:
    client, headers, _db, _fx = ctx
    mv = _register(client, headers)
    # Idempotent re-register.
    assert _register(client, headers) == mv
    # Below the adequacy floor (c=0.95 needs N>=21 — the review-tightened k>=2 rule) -> 422.
    resp = client.post(
        "/risk/models/var-historical",
        json={"code_version": "v1", "confidence_level": "0.95", "window_observations": 20},
        headers=headers,
    )
    assert resp.status_code == 422
    # Same-label different declaration -> 409.
    resp = client.post(
        "/risk/models/var-historical",
        json={"code_version": "v1", "confidence_level": "0.95", "window_observations": 40},
        headers=headers,
    )
    assert resp.status_code == 409


def test_run_and_read_round_trip(ctx) -> None:
    client, headers, _db, fx_run = ctx
    mv = _register(client, headers)
    resp = client.post(
        "/risk/vars-historical/runs",
        json={
            "code_version": "v1",
            "environment_id": "ci",
            "model_version_id": mv,
            "exposure_run_id": fx_run,
        },
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["status"] == "COMPLETED"
    (row,) = body["rows"]
    assert row["metric_type"] == "VAR_HISTORICAL"
    assert row["var_value"] == "200.000000"  # the hand reference (k=2 of P&L=-10i, N=21)
    assert row["z_score"] is None and row["sigma"] is None
    assert row["covariance_run_id"] is None
    assert row["confidence_level"] == "0.9500"
    assert (row["n_factors"], row["n_observations"]) == (2, 21)

    # Read back through the EXISTING parametric-family GETs (same run family + table).
    read = client.get(f"/risk/vars/runs/{body['run_id']}", headers=headers)
    assert read.status_code == 200
    assert read.json()["rows"][0]["var_value"] == "200.000000"
    row_read = client.get(f"/risk/vars/{row['id']}", headers=headers)
    assert row_read.status_code == 200
    assert row_read.json()["sigma"] is None

    # ... and it appears in the FE-1 listing under the VAR family.
    listed = client.get("/risk/runs", params={"run_type": "VAR"}, headers=headers)
    assert body["run_id"] in {i["run_id"] for i in listed.json()["items"]}


def test_both_modes_and_entitlement_and_methods(ctx) -> None:
    client, headers, db, fx_run = ctx
    mv = _register(client, headers)
    resp = client.post(
        "/risk/vars-historical/runs",
        json={
            "code_version": "v1",
            "environment_id": "ci",
            "model_version_id": mv,
            "exposure_run_id": fx_run,
            "snapshot_id": str(uuid.uuid4()),
        },
        headers=headers,
    )
    assert resp.status_code == 422  # both-modes ambiguity refusal
    # A viewer without risk.run cannot run.
    viewer = AppUser(tenant_id=headers["X-Tenant-Id"], display_name="V")
    vrole = Role(tenant_id=headers["X-Tenant-Id"], code="v", name="V")
    db.add_all([viewer, vrole])
    db.flush()
    perm = db.query(Permission).filter_by(code="risk.view").one()
    db.add(RolePermission(role_id=vrole.id, permission_id=perm.id))
    db.add(UserRole(tenant_id=headers["X-Tenant-Id"], user_id=viewer.id, role_id=vrole.id))
    db.commit()
    vh = {"X-User-Id": str(viewer.id), "X-Tenant-Id": headers["X-Tenant-Id"]}
    resp = client.post(
        "/risk/vars-historical/runs",
        json={
            "code_version": "v1",
            "environment_id": "ci",
            "model_version_id": mv,
            "exposure_run_id": fx_run,
        },
        headers=vh,
    )
    assert resp.status_code == 403
    for method in ("put", "patch", "delete"):
        assert (
            getattr(client, method)("/risk/vars-historical/runs", headers=headers).status_code
            == 405
        )


# ---------- ES-HS-1: the empirical ES family through the SAME endpoints ----------


def _register_es(client: TestClient, headers: dict[str, str], window: int = 21) -> str:
    resp = client.post(
        "/risk/models/var-historical-es",
        json={"code_version": "v1", "confidence_level": "0.95", "window_observations": window},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["model_version_id"]


def test_es_hs_register_floor_and_conflict(ctx) -> None:
    client, headers, _db, _fx = ctx
    mv = _register_es(client, headers)
    # Idempotent re-register.
    assert _register_es(client, headers) == mv
    # Below the shared adequacy floor -> 422; same-label different declaration -> 409.
    resp = client.post(
        "/risk/models/var-historical-es",
        json={"code_version": "v1", "confidence_level": "0.95", "window_observations": 20},
        headers=headers,
    )
    assert resp.status_code == 422
    resp = client.post(
        "/risk/models/var-historical-es",
        json={"code_version": "v1", "confidence_level": "0.95", "window_observations": 40},
        headers=headers,
    )
    assert resp.status_code == 409


def test_es_hs_run_and_read_round_trip(ctx) -> None:
    """The ES-HS run enters through the EXISTING run endpoint (the binder dispatches on the
    bound model — OD-ES-HS-1-B) and reads back through the EXISTING GET family: metric_type
    ES_HISTORICAL, the hand reference 220/1.05 = 209.523810, the NULL trio honest."""
    client, headers, _db, fx_run = ctx
    mv = _register_es(client, headers)
    resp = client.post(
        "/risk/vars-historical/runs",
        json={
            "code_version": "v1",
            "environment_id": "ci",
            "model_version_id": mv,
            "exposure_run_id": fx_run,
        },
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["status"] == "COMPLETED"
    (row,) = body["rows"]
    assert row["metric_type"] == "ES_HISTORICAL"
    assert row["var_value"] == "209.523810"  # (210 + 0.05*200)/1.05 — the Prop 4.1 hand ref
    assert row["z_score"] is None and row["sigma"] is None
    assert row["covariance_run_id"] is None
    assert row["confidence_level"] == "0.9500"
    assert (row["n_factors"], row["n_observations"]) == (2, 21)

    read = client.get(f"/risk/vars/runs/{body['run_id']}", headers=headers)
    assert read.status_code == 200
    assert read.json()["rows"][0]["var_value"] == "209.523810"
    row_read = client.get(f"/risk/vars/{row['id']}", headers=headers)
    assert row_read.status_code == 200
    assert row_read.json()["sigma"] is None

    listed = client.get("/risk/runs", params={"run_type": "VAR"}, headers=headers)
    assert body["run_id"] in {i["run_id"] for i in listed.json()["items"]}


def test_es_hs_wrong_family_version_is_422(ctx) -> None:
    """A parametric model_version through the HS run endpoint refuses 422 with the PLAIN-HS
    code's message (the _resolve_hs_family first-error contract), never a 500."""
    client, headers, _db, fx_run = ctx
    resp = client.post(
        "/risk/models/var",
        json={"code_version": "v1", "confidence_level": "0.95"},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    pmv = resp.json()["model_version_id"]
    resp = client.post(
        "/risk/vars-historical/runs",
        json={
            "code_version": "v1",
            "environment_id": "ci",
            "model_version_id": pmv,
            "exposure_run_id": fx_run,
        },
        headers=headers,
    )
    assert resp.status_code == 422
