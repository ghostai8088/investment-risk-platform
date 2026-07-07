"""End-to-end tests of the P3-5 risk (parametric VaR v1) endpoints.

SQLite has no RLS (tenant isolation + append-only-trigger proofs are in
``packages/shared-python/tests/test_var_pg.py``); here we prove entitlement gating
(deny-by-default, no DB side-effect on denial; view-only cannot run — the REUSED ``risk.run``/
``risk.view``), the governed declared-parameter model registration (incl. the 409 identity
conflict and the 422 vocabulary floor), the build-in-request run + read round-trip over the two
upstream governed runs, fixed-point decimal serialization, the pre-create refusals
(422/404), and no PUT/PATCH/DELETE on all three new route families.
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
    for code in ("USD", "EUR"):
        db.add(Currency(tenant_id=SYSTEM_TENANT_ID, code=code, name=code, valid_from=_T0))
    db.flush()

    # The two upstream governed runs (the P3-3 + P3-4 chain).
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
    db.commit()
    principal = Principal(user_id=user.id, tenant_id=tenant_id)

    def _override_db() -> Iterator[Session]:
        yield db

    app = FastAPI()
    app.include_router(risk_router)
    app.dependency_overrides[get_db] = _override_db
    try:
        yield TestClient(app), principal, db, fx_run.run.run_id, cov_run.run.run_id
    finally:
        db.close()
        engine.dispose()


def _h(p: Principal) -> dict[str, str]:
    return {"X-User-Id": p.user_id, "X-Tenant-Id": p.tenant_id}


def _register(client: TestClient, p: Principal, confidence: str = "0.95") -> str:
    resp = client.post(
        "/risk/models/var",
        json={"code_version": "risk-v1", "confidence_level": confidence},
        headers=_h(p),
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["model_version_id"]


def _run_body(mv: str, fx_run: str, cov_run: str, **kw) -> dict:  # noqa: ANN003
    return {
        "code_version": "risk-v1",
        "environment_id": "ci",
        "model_version_id": mv,
        "exposure_run_id": fx_run,
        "covariance_run_id": cov_run,
        **kw,
    }


def _count_var_runs(db: Session, tenant: str) -> int:
    return db.execute(
        select(func.count())
        .select_from(CalculationRun)
        .where(CalculationRun.tenant_id == tenant, CalculationRun.run_type == "VAR")
    ).scalar_one()


def test_register_run_and_read_roundtrip(ctx) -> None:  # noqa: ANN001
    client, p, db, fx_run, cov_run = ctx
    mv = _register(client, p)
    resp = client.post("/risk/vars/runs", json=_run_body(mv, fx_run, cov_run), headers=_h(p))
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["status"] == "COMPLETED" and body["run_type"] == "VAR"
    assert len(body["rows"]) == 1
    row = body["rows"][0]
    assert row["metric_type"] == "VAR_PARAMETRIC"
    assert row["base_currency"] == "USD"
    assert row["confidence_level"] == "0.9500"
    assert row["horizon_days"] == 1
    assert row["z_score"] == "1.644853626951"
    assert row["n_factors"] == 2 and row["n_observations"] == 4
    assert row["exposure_run_id"] == fx_run and row["covariance_run_id"] == cov_run
    assert Decimal(row["sigma"]) > 0 and Decimal(row["var_value"]) > 0
    for field in ("sigma", "var_value"):
        assert "E" not in row[field] and "e" not in row[field]  # fixed-point, never scientific
    # Read the run back + the single row.
    run_read = client.get(f"/risk/vars/runs/{body['run_id']}", headers=_h(p))
    assert run_read.status_code == 200 and len(run_read.json()["rows"]) == 1
    row_read = client.get(f"/risk/vars/{row['id']}", headers=_h(p))
    assert row_read.status_code == 200
    assert row_read.json()["var_value"] == row["var_value"]


def test_register_conflicts_and_vocabulary_floor(ctx) -> None:  # noqa: ANN001
    client, p, db, fx_run, cov_run = ctx
    mv = _register(client, p, confidence="0.95")
    assert _register(client, p, confidence="0.95") == mv  # idempotent same identity
    resp = client.post(
        "/risk/models/var",
        json={"code_version": "risk-v1", "confidence_level": "0.99"},  # same label, new declared
        headers=_h(p),
    )
    assert resp.status_code == 409
    resp = client.post(
        "/risk/models/var",
        json={"code_version": "risk-v2", "confidence_level": "0.95"},  # same label, new code
        headers=_h(p),
    )
    assert resp.status_code == 409
    resp = client.post(
        "/risk/models/var",
        json={"code_version": "risk-v1", "confidence_level": "0.975"},  # outside the vocabulary
        headers=_h(p),
    )
    assert resp.status_code == 422
    resp = client.post(
        "/risk/models/var",
        json={"code_version": "risk-v1", "confidence_level": "0.95", "horizon_days": 10},
        headers=_h(p),
    )
    assert resp.status_code == 422  # v1 is 1-day only


def test_deny_by_default_and_view_only_cannot_run(ctx) -> None:  # noqa: ANN001
    client, p, db, fx_run, cov_run = ctx
    mv = _register(client, p)
    nobody = Principal(user_id=str(uuid.uuid4()), tenant_id=p.tenant_id)  # no roles at all
    resp = client.post("/risk/vars/runs", json=_run_body(mv, fx_run, cov_run), headers=_h(nobody))
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
    resp = client.post("/risk/vars/runs", json=_run_body(mv, fx_run, cov_run), headers=_h(vp))
    assert resp.status_code == 403  # .view does not grant .run
    assert _count_var_runs(db, p.tenant_id) == 0


def test_pre_create_refusals(ctx) -> None:  # noqa: ANN001
    client, p, db, fx_run, cov_run = ctx
    mv = _register(client, p)
    body = _run_body(mv, fx_run, cov_run)
    body.pop("covariance_run_id")  # half an input set
    assert client.post("/risk/vars/runs", json=body, headers=_h(p)).status_code == 422
    resp = client.post(  # unregistered model_version (CTRL-003 fail-closed)
        "/risk/vars/runs", json=_run_body(str(uuid.uuid4()), fx_run, cov_run), headers=_h(p)
    )
    assert resp.status_code == 422
    resp = client.post(  # unknown upstream run
        "/risk/vars/runs", json=_run_body(mv, str(uuid.uuid4()), cov_run), headers=_h(p)
    )
    assert resp.status_code == 404
    resp = client.post(  # swapped run types (a covariance run offered as the exposure run)
        "/risk/vars/runs", json=_run_body(mv, cov_run, cov_run), headers=_h(p)
    )
    assert resp.status_code == 404
    body = _run_body(mv, fx_run, cov_run)
    body.pop("exposure_run_id")
    body.pop("covariance_run_id")
    body["snapshot_id"] = str(uuid.uuid4())  # unknown consume-path snapshot
    assert client.post("/risk/vars/runs", json=body, headers=_h(p)).status_code == 404
    assert _count_var_runs(db, p.tenant_id) == 0


def test_post_create_failed_returns_201_failed(ctx, monkeypatch: pytest.MonkeyPatch) -> None:  # noqa: ANN001
    # The durable-refusal contract at the HTTP layer (the 2026-07 review fold): a post-create
    # gate defect returns 201 + status=FAILED + failure_reason, and the committed FAILED run
    # reads back 200/FAILED (never 404). Forced through the kernel seam (the P3-4 pattern).
    client, p, db, fx_run, cov_run = ctx
    mv = _register(client, p)
    import irp_shared.risk.var_service as vs
    from irp_shared.risk.var_kernel import VarEstimate

    def poisoned(exposure_rows, covariance, *, z_score):  # noqa: ANN001, ANN202
        return VarEstimate(
            radicand=Decimal("-1"), tolerance=Decimal("1E-19"), sigma=None, var_value=None
        )

    monkeypatch.setattr(vs, "compute_parametric_var", poisoned)
    resp = client.post("/risk/vars/runs", json=_run_body(mv, fx_run, cov_run), headers=_h(p))
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["status"] == "FAILED" and body["rows"] == []
    assert body["failure_reason"] and "non-psd-radicand" in body["failure_reason"]
    read = client.get(f"/risk/vars/runs/{body['run_id']}", headers=_h(p))
    assert read.status_code == 200 and read.json()["status"] == "FAILED"


def test_register_malformed_and_generic_minted_twin_are_4xx(ctx) -> None:  # noqa: ANN001
    # (a) a malformed confidence string is a 422, never an InvalidOperation 500; (b) a same-label
    # 'risk.var.parametric' v1 pre-minted with malformed declarations via the GENERIC governed
    # registration maps to the WrongModelVersionError 422 arm (the 2026-07 review folds).
    client, p, db, fx_run, cov_run = ctx
    for bad in ("abc", "Infinity", "0.94995", ""):
        resp = client.post(
            "/risk/models/var",
            json={"code_version": "risk-v1", "confidence_level": bad},
            headers=_h(p),
        )
        assert resp.status_code == 422, (bad, resp.status_code)
    from irp_shared.model.service import register_model, register_model_version
    from irp_shared.risk.bootstrap import VAR_MODEL_CODE

    model = register_model(
        db,
        tenant_id=p.tenant_id,
        code=VAR_MODEL_CODE,
        name="generic",
        model_type="VAR",
        actor_id="a",
    )
    register_model_version(
        db,
        model=model,
        version_label="v1",
        actor_id="a",
        methodology_ref="x",
        code_version="risk-v1",
        status="REGISTERED",
        assumptions=["confidence_level=abc", "horizon_days=1"],
        limitations=[],
    )
    db.commit()
    resp = client.post(
        "/risk/models/var",
        json={"code_version": "risk-v1", "confidence_level": "0.95"},
        headers=_h(p),
    )
    assert resp.status_code == 422  # the malformed same-label twin: identity refusal, not 500


def test_no_mutating_verbs(ctx) -> None:  # noqa: ANN001
    client, p, db, fx_run, cov_run = ctx
    for path in (
        f"/risk/vars/{uuid.uuid4()}",
        f"/risk/vars/runs/{uuid.uuid4()}",
        "/risk/models/var",
    ):
        for method in ("put", "patch", "delete"):
            resp = getattr(client, method)(path, headers=_h(p))
            assert resp.status_code == 405, (method, path)  # append-only: no mutation verbs
