"""End-to-end tests of the PA-4 total-parametric-VaR endpoints (``POST /risk/models/var-
parametric-total`` dispatched through the SAME ``POST /risk/vars/runs``/``GET`` family as the
plain P3-5 family — the ``test_var_endpoint.py`` twin, extended with a proxied instrument).

SQLite has no RLS (the RLS/append-only proofs are in ``test_var_total_pg.py`` at the
``shared-python`` layer); here we prove the register + build-in-request run + read round-trip
(``residual_variance`` visible on the wire), the appraisal_days vocabulary floor (422), and the
symmetric binding-predicate refusal via the consume-existing path (422).
"""

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
from irp_shared.calc.models import RunStatus
from irp_shared.calc.service import create_run, update_run_status
from irp_shared.db.session import make_engine, make_session_factory
from irp_shared.entitlement.bootstrap import SYSTEM_TENANT_ID
from irp_shared.entitlement.models import AppUser, Permission, Role, RolePermission, UserRole
from irp_shared.entitlement.service import Principal
from irp_shared.exposure import ExposureActor, run_exposure
from irp_shared.marketdata import FxRateActor, ProxyMappingActor, capture_fx_rate
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
    METRIC_TYPE_ESTIMATION_SUMMARY,
    RUN_TYPE_PROXY_WEIGHT_ESTIMATE,
    CovarianceActor,
    FactorExposureActor,
    ProxyWeightEstimateResult,
    promote_proxy_weight_estimate,
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
_APPRAISAL_DAYS = 91
_MAX_ESTIMATE_AGE_DAYS = 400  # BT-2: the declared staleness policy


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
    instrument_ids: dict[str, str] = {}
    for code, mark, ccy in (("I-USD", "300.00", "USD"), ("I-EUR", "400.00", "EUR")):
        inst = create_instrument(
            db,
            tenant_id=tenant_id,
            code=code,
            name="i",
            asset_class="BOND",
            actor=ReferenceActor(actor_id="s"),
        ).id
        instrument_ids[code] = inst
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

    # PA-4: proxy-map I-USD via a REGRESSION mapping citing a completed proxy-weight estimate.
    from irp_shared.risk.bootstrap import register_proxy_weight_regression_model
    from irp_shared.snapshot import SnapshotActor
    from irp_shared.snapshot.models import PURPOSE_PROXY_WEIGHT_INPUT
    from irp_shared.snapshot.service import _persist_snapshot

    # BT-2 fixture realism: the estimate's input snapshot must be what the REAL chain persists —
    # a PROXY_WEIGHT_INPUT header whose as_of_valuation_date is the regression SPAN END (the
    # staleness gate reads exactly those two fields; a TEST-purpose header models an estimate that
    # cannot exist). Span end = 30 days before the covariance window end -> a fresh estimate.
    snap = _persist_snapshot(
        db,
        acting_tenant=tenant_id,
        actor=SnapshotActor(actor_id="a"),
        specs=[],
        label="",
        purpose=PURPOSE_PROXY_WEIGHT_INPUT,
        as_of_valid_at=_VA,
        as_of_known_at=_KA,
        as_of_valuation_date=_D[3] - timedelta(days=30),
        binding_predicate_version="v1:test",
    )
    pw_mv = register_proxy_weight_regression_model(
        db, tenant_id=tenant_id, actor_id="a", code_version="risk-v1", min_observations=4
    )
    est_run = create_run(
        db,
        tenant_id=tenant_id,
        run_type=RUN_TYPE_PROXY_WEIGHT_ESTIMATE,
        initiated_by="a",
        input_snapshot_id=snap.id,
        model_version_id=pw_mv.id,
        code_version="risk-v1",
        environment_id="ci",
    )
    update_run_status(db, est_run, RunStatus.RUNNING, actor_id="a")
    db.add(
        ProxyWeightEstimateResult(
            tenant_id=tenant_id,
            calculation_run_id=est_run.run_id,
            input_snapshot_id=snap.id,
            model_version_id=pw_mv.id,
            portfolio_id=pf,
            instrument_id=instrument_ids["I-USD"],
            source_desmoothed_run_id=fx_run.run.run_id,
            metric_type=METRIC_TYPE_ESTIMATION_SUMMARY,
            factor_id=None,
            metric_value=Decimal("0.8"),
            std_error=None,
            n_observations=6,
            n_regressors=1,
            residual_stdev=Decimal("0.04"),
            min_observations=4,
            series_currency="USD",
        )
    )
    db.flush()
    update_run_status(db, est_run, RunStatus.COMPLETED, actor_id="a")
    promote_proxy_weight_estimate(
        db,
        private_instrument_id=instrument_ids["I-USD"],
        factor_id=factor_ids[0],
        weight=Decimal("0.5"),
        acting_tenant=tenant_id,
        actor=ProxyMappingActor(actor_id="a"),
        source_calculation_run_id=est_run.run_id,
    )
    db.commit()
    principal = Principal(user_id=user.id, tenant_id=tenant_id)

    def _override_db() -> Iterator[Session]:
        yield db

    app = FastAPI()
    app.include_router(risk_router)
    app.dependency_overrides[get_db] = _override_db
    try:
        yield (
            TestClient(app),
            principal,
            db,
            fx_run.run.run_id,
            cov_run.run.run_id,
            instrument_ids["I-USD"],
        )
    finally:
        db.close()
        engine.dispose()


def _h(p: Principal) -> dict[str, str]:
    return {"X-User-Id": p.user_id, "X-Tenant-Id": p.tenant_id}


def _register_total(
    client: TestClient,
    p: Principal,
    confidence: str = "0.95",
    appraisal_days: int = _APPRAISAL_DAYS,
    max_estimate_age_days: int = _MAX_ESTIMATE_AGE_DAYS,
) -> str:
    resp = client.post(
        "/risk/models/var-parametric-total",
        json={
            "code_version": "risk-v1",
            "confidence_level": confidence,
            "appraisal_days": appraisal_days,
            # BT-2: the declared staleness policy is REQUIRED on the v2 identity.
            "max_estimate_age_days": max_estimate_age_days,
        },
        headers=_h(p),
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["model_version_id"]


def _register_plain(client: TestClient, p: Principal, confidence: str = "0.95") -> str:
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


def test_register_run_and_read_roundtrip(ctx) -> None:  # noqa: ANN001
    client, p, db, fx_run, cov_run, _iid = ctx
    mv = _register_total(client, p)
    resp = client.post("/risk/vars/runs", json=_run_body(mv, fx_run, cov_run), headers=_h(p))
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["status"] == "COMPLETED" and body["run_type"] == "VAR"
    row = body["rows"][0]
    assert row["metric_type"] == "VAR_PARAMETRIC_TOTAL"
    assert Decimal(row["residual_variance"]) > 0
    for field in ("sigma", "var_value", "residual_variance"):
        assert "E" not in row[field] and "e" not in row[field]  # fixed-point, never scientific
    run_read = client.get(f"/risk/vars/runs/{body['run_id']}", headers=_h(p))
    assert run_read.status_code == 200
    row_read = client.get(f"/risk/vars/{row['id']}", headers=_h(p))
    assert row_read.status_code == 200
    assert row_read.json()["residual_variance"] == row["residual_variance"]


def test_appraisal_days_vocabulary_floor(ctx) -> None:  # noqa: ANN001
    client, p, _db, _fx_run, _cov_run, _iid = ctx
    resp = client.post(
        "/risk/models/var-parametric-total",
        json={
            "code_version": "risk-v1",
            "confidence_level": "0.95",
            "appraisal_days": 0,
            "max_estimate_age_days": _MAX_ESTIMATE_AGE_DAYS,
        },
        headers=_h(p),
    )
    assert resp.status_code == 422


def test_symmetric_predicate_refusal_via_consume_path(ctx) -> None:  # noqa: ANN001
    client, p, db, fx_run, cov_run, _iid = ctx
    plain_mv = _register_plain(client, p)
    # Build a PLAIN VAR_INPUT snapshot (no idiosyncratic pins) via the plain model's own build
    # path, then try to consume it under the TOTAL model — refused (OD-PA-4-C).
    resp = client.post("/risk/vars/runs", json=_run_body(plain_mv, fx_run, cov_run), headers=_h(p))
    assert resp.status_code == 201
    plain_snapshot_id = resp.json()["input_snapshot_id"]

    total_mv = _register_total(client, p)
    resp = client.post(
        "/risk/vars/runs",
        json={
            "code_version": "risk-v1",
            "environment_id": "ci",
            "model_version_id": total_mv,
            "snapshot_id": plain_snapshot_id,
        },
        headers=_h(p),
    )
    assert resp.status_code == 422
