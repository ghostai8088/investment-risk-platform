"""End-to-end tests of the P3-3 risk (factor exposure, allocation v1) endpoints.

SQLite has no RLS (tenant isolation + append-only-trigger proofs are in
``packages/shared-python/tests/test_factor_exposure_pg.py``); here we prove entitlement gating
(deny-by-default, no DB side-effect on denial; view-only cannot run — the REUSED ``risk.run``/
``risk.view``), the governed model registration + build-in-request run + read round-trip, decimal
serialization, the pre-create refusals (422/404), the post-create FAILED response (201 +
status='FAILED' + zero rows — an unmapped atom), and no PUT/PATCH/DELETE.
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
from irp_shared.marketdata.factor import FactorActor, capture_factor
from irp_shared.models import Base
from irp_shared.portfolio import PortfolioActor, create_portfolio
from irp_shared.position import create_position
from irp_shared.position.service import PositionActor
from irp_shared.reference.instrument import create_instrument
from irp_shared.reference.models import Currency
from irp_shared.reference.service import ReferenceActor
from irp_shared.valuation import create_valuation
from irp_shared.valuation.service import ValuationActor

_PERMS = ("risk.run", "risk.view", "model.inventory.register")
_T0 = datetime(2026, 1, 1, tzinfo=UTC)
_VA = datetime(2026, 6, 1, tzinfo=UTC)
_KA = datetime(2030, 1, 1, tzinfo=UTC)
_VD = date(2026, 6, 1)


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

    # A governed COMPLETED exposure run (the atoms) + a CURRENCY factor.
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
        code="I0",
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
        mark_value=Decimal("12.50"),
        currency_code="USD",
        valid_from=_T0,
    )
    exp = run_exposure(
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
    fac = capture_factor(
        db,
        factor_code="FX_USD",
        factor_source="VENDOR_F",
        factor_family="CURRENCY",
        currency_code="USD",
        acting_tenant=tenant_id,
        actor=FactorActor(actor_id="s"),
        valid_from=_T0,
    ).id
    db.commit()
    principal = Principal(user_id=user.id, tenant_id=tenant_id)

    def _override_db() -> Iterator[Session]:
        yield db

    app = FastAPI()
    app.include_router(risk_router)
    app.dependency_overrides[get_db] = _override_db
    try:
        yield TestClient(app), principal, db, exp.run.run_id, fac
    finally:
        db.close()
        engine.dispose()


def _h(p: Principal) -> dict[str, str]:
    return {"X-User-Id": p.user_id, "X-Tenant-Id": p.tenant_id}


def _register(client: TestClient, p: Principal) -> str:
    resp = client.post(
        "/risk/models/factor-exposure", json={"code_version": "risk-v1"}, headers=_h(p)
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["model_version_id"]


def _run_body(mv: str, exp_run: str, factor_ids: list[str], **kw) -> dict:  # noqa: ANN003
    return {
        "code_version": "risk-v1",
        "environment_id": "ci",
        "model_version_id": mv,
        "exposure_run_id": exp_run,
        "factor_ids": factor_ids,
        **kw,
    }


def _count_fx_runs(db: Session, tenant: str) -> int:
    return db.execute(
        select(func.count())
        .select_from(CalculationRun)
        .where(CalculationRun.tenant_id == tenant, CalculationRun.run_type == "FACTOR_EXPOSURE")
    ).scalar_one()


def test_register_run_and_read_roundtrip(ctx) -> None:  # noqa: ANN001
    client, p, db, exp_run, fac = ctx
    mv = _register(client, p)
    resp = client.post(
        "/risk/factor-exposures/runs", json=_run_body(mv, exp_run, [fac]), headers=_h(p)
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["status"] == "COMPLETED" and body["run_type"] == "FACTOR_EXPOSURE"
    assert len(body["rows"]) == 1
    row = body["rows"][0]
    assert row["factor_code"] == "FX_USD" and row["factor_family"] == "CURRENCY"
    assert Decimal(row["exposure_amount"]) == Decimal("1250.000000")  # 100 x 12.50, exact
    assert Decimal(row["loading"]) == Decimal("1")
    # Read the run back + a single row.
    run_read = client.get(f"/risk/factor-exposures/runs/{body['run_id']}", headers=_h(p))
    assert run_read.status_code == 200 and len(run_read.json()["rows"]) == 1
    row_read = client.get(f"/risk/factor-exposures/{row['id']}", headers=_h(p))
    assert row_read.status_code == 200
    assert row_read.json()["exposure_amount"] == row["exposure_amount"]


def test_deny_by_default_no_side_effect(ctx) -> None:  # noqa: ANN001
    client, p, db, exp_run, fac = ctx
    mv = _register(client, p)
    nobody = Principal(user_id=str(uuid.uuid4()), tenant_id=p.tenant_id)  # no roles at all
    resp = client.post(
        "/risk/factor-exposures/runs", json=_run_body(mv, exp_run, [fac]), headers=_h(nobody)
    )
    assert resp.status_code == 403
    assert _count_fx_runs(db, p.tenant_id) == 0  # denial leaves no run


def test_view_only_user_cannot_run(ctx) -> None:  # noqa: ANN001
    client, p, db, exp_run, fac = ctx
    mv = _register(client, p)
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
        "/risk/factor-exposures/runs", json=_run_body(mv, exp_run, [fac]), headers=_h(vp)
    )
    assert resp.status_code == 403  # .view does not grant .run (auditor-style read-only)
    assert _count_fx_runs(db, p.tenant_id) == 0


def test_pre_create_refusal_bad_input_422(ctx) -> None:  # noqa: ANN001
    client, p, db, exp_run, fac = ctx
    mv = _register(client, p)
    body = _run_body(mv, exp_run, [fac])
    body.pop("exposure_run_id")
    body.pop("factor_ids")
    resp = client.post("/risk/factor-exposures/runs", json=body, headers=_h(p))
    assert resp.status_code == 422
    assert _count_fx_runs(db, p.tenant_id) == 0


def test_unregistered_model_version_422(ctx) -> None:  # noqa: ANN001
    client, p, db, exp_run, fac = ctx
    resp = client.post(
        "/risk/factor-exposures/runs",
        json=_run_body(str(uuid.uuid4()), exp_run, [fac]),
        headers=_h(p),
    )
    assert resp.status_code == 422  # CTRL-003 fail-closed
    assert _count_fx_runs(db, p.tenant_id) == 0


def test_unknown_exposure_run_404(ctx) -> None:  # noqa: ANN001
    client, p, db, exp_run, fac = ctx
    mv = _register(client, p)
    resp = client.post(
        "/risk/factor-exposures/runs",
        json=_run_body(mv, str(uuid.uuid4()), [fac]),
        headers=_h(p),
    )
    assert resp.status_code == 404
    assert _count_fx_runs(db, p.tenant_id) == 0


def test_duplicate_currency_factor_set_422(ctx) -> None:  # noqa: ANN001
    client, p, db, exp_run, fac = ctx
    mv = _register(client, p)
    fac2 = capture_factor(
        db,
        factor_code="FX_USD_B",
        factor_source="VENDOR_F",
        factor_family="CURRENCY",
        currency_code="USD",
        acting_tenant=p.tenant_id,
        actor=FactorActor(actor_id="s"),
        valid_from=_T0,
    ).id
    db.commit()
    resp = client.post(
        "/risk/factor-exposures/runs", json=_run_body(mv, exp_run, [fac, fac2]), headers=_h(p)
    )
    assert resp.status_code == 422  # ambiguous partition refused pre-create
    assert _count_fx_runs(db, p.tenant_id) == 0


def test_post_create_failed_returns_201_failed(ctx) -> None:  # noqa: ANN001
    client, p, db, exp_run, fac = ctx
    mv = _register(client, p)
    db.add(Currency(tenant_id=SYSTEM_TENANT_ID, code="EUR", name="EUR", valid_from=_T0))
    db.flush()
    eur_factor = capture_factor(
        db,
        factor_code="FX_EUR",
        factor_source="VENDOR_F",
        factor_family="CURRENCY",
        currency_code="EUR",
        acting_tenant=p.tenant_id,
        actor=FactorActor(actor_id="s"),
        valid_from=_T0,
    ).id
    db.commit()
    # The USD atom is unmapped against an EUR-only factor set -> post-create FAILED, zero rows.
    resp = client.post(
        "/risk/factor-exposures/runs", json=_run_body(mv, exp_run, [eur_factor]), headers=_h(p)
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["status"] == "FAILED" and body["rows"] == []
    assert body["failure_reason"]
    # The FAILED run is durable + readable (NOT a 404).
    read = client.get(f"/risk/factor-exposures/runs/{body['run_id']}", headers=_h(p))
    assert read.status_code == 200 and read.json()["status"] == "FAILED"
    # P3-C1: the persisted reason SURFACES on read (previously hardcoded None).
    assert read.json()["failure_reason"] == body["failure_reason"]


def test_no_mutating_verbs(ctx) -> None:  # noqa: ANN001
    client, p, db, exp_run, fac = ctx
    for method in ("put", "patch", "delete"):
        resp = getattr(client, method)(f"/risk/factor-exposures/{uuid.uuid4()}", headers=_h(p))
        assert resp.status_code == 405  # append-only surface: no mutation verbs


def test_p3c1_status_twin_refused_at_run_and_register(ctx) -> None:  # noqa: ANN001
    """P3-C1 endpoint proofs: a generically-minted status=None same-family version is refused
    by the RUN endpoint (the CTRL-003 status gate) AND the governed REGISTER endpoint refuses
    the squatted label as an identity conflict (422) instead of returning it as a success —
    the register/run consistency fold."""
    from irp_shared.model.service import register_model, register_model_version
    from irp_shared.risk.bootstrap import FACTOR_EXPOSURE_MODEL_CODE

    client, p, db, exp_run, fac = ctx
    model = register_model(
        db,
        tenant_id=p.tenant_id,
        code=FACTOR_EXPOSURE_MODEL_CODE,
        name="g",
        model_type="X",
        actor_id="a",
    )
    twin = register_model_version(
        db,
        model=model,
        version_label="v1",
        actor_id="a",
        methodology_ref="x",
        code_version="risk-v1",
        status=None,
        assumptions=[],
        limitations=[],
    ).id
    db.commit()
    resp = client.post(
        "/risk/factor-exposures/runs", json=_run_body(twin, exp_run, [fac]), headers=_h(p)
    )
    assert resp.status_code == 422  # the status gate at the run endpoint
    resp = client.post(
        "/risk/models/factor-exposure", json={"code_version": "risk-v1"}, headers=_h(p)
    )
    assert resp.status_code == 422  # register refuses the squatted non-REGISTERED twin
    assert _count_fx_runs(db, p.tenant_id) == 0


def test_p3c1_both_modes_422(ctx) -> None:  # noqa: ANN001
    """P3-C1: posting BOTH input modes (build args + snapshot_id) is a 422 ambiguity refusal."""
    client, p, db, exp_run, fac = ctx
    mv = _register(client, p)
    body = _run_body(mv, exp_run, [fac]) | {"snapshot_id": str(uuid.uuid4())}
    resp = client.post("/risk/factor-exposures/runs", json=body, headers=_h(p))
    assert resp.status_code == 422
    assert _count_fx_runs(db, p.tenant_id) == 0
