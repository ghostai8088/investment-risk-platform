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


def test_rejected_model_version_run_is_422_not_500(ctx) -> None:  # noqa: ANN001
    """VW-1 OD-B end-to-end through a REAL family run endpoint: a latest-outcome REJECTED validation
    on the bound VaR model_version makes a new run refuse with a governed 422 (RejectedModelVersion
    Error mapped in risk.py's _ERROR_MAP + except tuple), NOT a raw 500 — the seam-only unit test
    can't catch a missing API error-map, so this drives the client-facing path (finder fold)."""
    from irp_shared.model.validation import (
        ModelValidationActor,
        RecordValidationRequest,
        record_validation,
    )

    client, p, db, fx_run, cov_run = ctx
    mv = _register(client, p)
    # A REGISTERED VaR version exists; a 2L validator REJECTS it (recorded via the service).
    record_validation(
        db,
        acting_tenant=p.tenant_id,
        actor=ModelValidationActor(actor_id="validator-2l"),
        request=RecordValidationRequest(
            model_version_id=mv,
            validation_type="INITIAL",
            outcome="REJECTED",
            scope_summary="Conceptual soundness deficiency; not fit for use.",
        ),
    )
    db.commit()
    before = _count_var_runs(db, p.tenant_id)
    resp = client.post("/risk/vars/runs", json=_run_body(mv, fx_run, cov_run), headers=_h(p))
    assert resp.status_code == 422, resp.text  # governed refusal, not a 500
    assert "REJECTED" in resp.json()["detail"]
    assert _count_var_runs(db, p.tenant_id) == before  # no run persisted (whole-unit rollback)


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


def test_api1b_var_entity_read_copy_forward(ctx) -> None:  # noqa: ANN001
    """API-1b (Class C): the VaR run copies its ROOT ``scope_portfolio_id`` forward from the
    exposure→factor chain, and the flagship 'latest VaR for portfolio P' read resolves via that
    column — ``var_result`` has no portfolio_id of its own."""
    client, p, db, fx_run, cov_run = ctx
    mv = _register(client, p)
    resp = client.post("/risk/vars/runs", json=_run_body(mv, fx_run, cov_run), headers=_h(p))
    assert resp.status_code == 201, resp.text
    run_id = resp.json()["run_id"]
    row = resp.json()["rows"][0]

    # copy-forward: the run carries a NON-NULL scope stamped from the upstream exposure run.
    scope = db.execute(
        select(CalculationRun.scope_portfolio_id).where(CalculationRun.run_id == run_id)
    ).scalar_one()
    assert scope is not None

    # the flagship latest-for-P read (+ the /latest route is NOT shadowed by /{var_id}).
    latest = client.get("/risk/vars/latest", params={"portfolio_id": scope}, headers=_h(p))
    assert latest.status_code == 200 and [r["id"] for r in latest.json()] == [row["id"]]
    foreign = client.get(
        "/risk/vars/latest", params={"portfolio_id": str(uuid.uuid4())}, headers=_h(p)
    )
    assert foreign.status_code == 200 and foreign.json() == []

    # the entity list + the optional metric_type filter.
    listed = client.get("/risk/vars", params={"portfolio_id": scope}, headers=_h(p))
    assert [r["id"] for r in listed.json()] == [row["id"]]
    by_mt = client.get(
        "/risk/vars",
        params={"portfolio_id": scope, "metric_type": row["metric_type"]},
        headers=_h(p),
    )
    assert [r["id"] for r in by_mt.json()] == [row["id"]]
    wrong_mt = client.get(
        "/risk/vars", params={"portfolio_id": scope, "metric_type": "VAR_HISTORICAL"}, headers=_h(p)
    )
    assert wrong_mt.json() == []


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
        # outside the vocabulary. The probe was 0.975 until ES-1 (OQ-ES-1-4) admitted that value
        # to the shared VAR_Z_SCORES; it would now register (409, not 422). 0.98 is unregistered.
        json={"code_version": "risk-v1", "confidence_level": "0.98"},
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
    # P3-C1: the persisted reason SURFACES on read (previously hardcoded None).
    assert read.json()["failure_reason"] == body["failure_reason"]


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


def test_p3c1_both_modes_422(ctx) -> None:  # noqa: ANN001
    """P3-C1: posting BOTH input modes (build args + snapshot_id) is a 422 ambiguity refusal."""
    client, p, db, fx_run, cov_run = ctx
    mv = _register(client, p)
    body = _run_body(mv, fx_run, cov_run) | {"snapshot_id": str(uuid.uuid4())}
    resp = client.post("/risk/vars/runs", json=body, headers=_h(p))
    assert resp.status_code == 422
    assert _count_var_runs(db, p.tenant_id) == 0


# ---------- ES-1: the two new register endpoints ----------


def _register_es(client: TestClient, p: Principal, confidence: str = "0.975") -> str:
    resp = client.post(
        "/risk/models/var-es",
        json={"code_version": "risk-v1", "confidence_level": confidence},
        headers=_h(p),
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["model_version_id"]


def test_es_model_registers_and_is_idempotent(ctx) -> None:  # noqa: ANN001
    client, p, _db, _fx, _cov = ctx
    first = _register_es(client, p)
    assert _register_es(client, p) == first  # idempotent
    resp = client.post(  # same label, different declaration -> governed conflict
        "/risk/models/var-es",
        json={"code_version": "risk-v2", "confidence_level": "0.975"},
        headers=_h(p),
    )
    assert resp.status_code == 409


def test_es_model_off_vocabulary_confidence_is_422(ctx) -> None:  # noqa: ANN001
    client, p, _db, _fx, _cov = ctx
    resp = client.post(
        "/risk/models/var-es",
        json={"code_version": "risk-v1", "confidence_level": "0.98"},  # unregistered
        headers=_h(p),
    )
    assert resp.status_code == 422
    resp = client.post(
        "/risk/models/var-es",
        json={"code_version": "risk-v1", "confidence_level": "0.95", "horizon_days": 10},
        headers=_h(p),
    )
    assert resp.status_code == 422  # v1 is 1-day only


def test_es_total_model_registers_and_validates_its_declarations(ctx) -> None:  # noqa: ANN001
    client, p, _db, _fx, _cov = ctx
    body = {
        "code_version": "risk-v1",
        "confidence_level": "0.975",
        "appraisal_days": 91,
        "max_estimate_age_days": 400,
    }
    resp = client.post("/risk/models/var-es-total", json=body, headers=_h(p))
    assert resp.status_code == 201, resp.text
    assert (
        client.post("/risk/models/var-es-total", json=body, headers=_h(p)).json()[
            "model_version_id"
        ]
        == resp.json()["model_version_id"]
    )  # idempotent
    for bad in ({"appraisal_days": 0}, {"max_estimate_age_days": 0}):
        resp = client.post("/risk/models/var-es-total", json={**body, **bad}, headers=_h(p))
        assert resp.status_code == 422


def test_es_endpoints_reuse_the_existing_permissions_and_deny_by_default(ctx) -> None:  # noqa: ANN001
    # OD-ES-1-G rests on "NO new permission — risk.run/risk.view REUSED"; that is a claim about
    # these two endpoints' gating, so it gets a test (the per-family shipped precedent is
    # test_deny_by_default_and_view_only_cannot_run).
    client, p, db, _fx, _cov = ctx
    es_body = {"code_version": "risk-v1", "confidence_level": "0.975"}
    es_total_body = {**es_body, "appraisal_days": 91, "max_estimate_age_days": 400}
    nobody = Principal(user_id=str(uuid.uuid4()), tenant_id=p.tenant_id)  # no roles at all
    assert client.post("/risk/models/var-es", json=es_body, headers=_h(nobody)).status_code == 403
    assert (
        client.post("/risk/models/var-es-total", json=es_total_body, headers=_h(nobody)).status_code
        == 403
    )
    viewer = AppUser(tenant_id=p.tenant_id, display_name="V2")
    view_role = Role(tenant_id=p.tenant_id, code="v2", name="V2")
    db.add_all([viewer, view_role])
    db.flush()
    perm_id = db.execute(select(Permission.id).where(Permission.code == "risk.view")).scalar_one()
    db.add(RolePermission(role_id=view_role.id, permission_id=perm_id))
    db.add(UserRole(tenant_id=p.tenant_id, user_id=viewer.id, role_id=view_role.id))
    db.commit()
    vp = Principal(user_id=viewer.id, tenant_id=p.tenant_id)
    # .view does not grant the register permission — on the ES endpoints as on every other.
    assert client.post("/risk/models/var-es", json=es_body, headers=_h(vp)).status_code == 403
    assert (
        client.post("/risk/models/var-es-total", json=es_total_body, headers=_h(vp)).status_code
        == 403
    )


def test_es_run_dispatches_through_the_unchanged_runs_endpoint(ctx) -> None:  # noqa: ANN001
    # POST /risk/vars/runs is UNCHANGED by ES-1 — the binder dispatches on the bound model. The ES
    # number rides var_value and the row is discriminated by metric_type (VarRowOut unchanged).
    client, p, _db, fx_run, cov_run = ctx
    es_mv = _register_es(client, p, confidence="0.975")
    resp = client.post("/risk/vars/runs", json=_run_body(es_mv, fx_run, cov_run), headers=_h(p))
    assert resp.status_code == 201, resp.text
    assert resp.json()["status"] == "COMPLETED"
    rows = resp.json()["rows"]
    assert len(rows) == 1
    assert rows[0]["metric_type"] == "ES_PARAMETRIC"
    assert rows[0]["confidence_level"] == "0.9750"
    # The ES row surfaces its (unused-by-the-arithmetic) z_score and its sigma; residual_variance
    # and estimate_age_days are None off the total family — by construction, so this pins the
    # plain-ES shape only. BT-2's API assertion proper lives in test_var_total_endpoint.py's
    # roundtrip, where the age is POPULATED and the assertion can actually fail.
    assert rows[0]["z_score"] is not None and rows[0]["sigma"] is not None
    assert rows[0]["residual_variance"] is None and rows[0]["estimate_age_days"] is None
    # ES > VaR over the same book, through the API.
    var_mv = _register(client, p, confidence="0.99")
    var_resp = client.post(
        "/risk/vars/runs", json=_run_body(var_mv, fx_run, cov_run), headers=_h(p)
    )
    assert var_resp.status_code == 201
    assert Decimal(rows[0]["var_value"]) > Decimal(var_resp.json()["rows"][0]["var_value"])


def test_expired_exception_run_is_422_not_500(ctx) -> None:  # noqa: ANN001
    """MG-1 OD-F end-to-end through a REAL risk run endpoint (the VW-1 'one risk + one perf'
    proof shape): a version whose LATEST validation record is an EXPIRED use-before-validation
    EXCEPTION refuses a new run with a governed 422 (ExpiredModelExceptionError mapped in
    risk.py's _ERROR_MAP + except tuples), NOT a raw 500."""
    from datetime import UTC, datetime, timedelta

    from irp_shared.model.validation import (
        ModelValidationActor,
        RecordValidationRequest,
        record_validation,
    )

    client, p, db, fx_run, cov_run = ctx
    mv = _register(client, p)
    past = datetime(2025, 1, 1, tzinfo=UTC)
    record_validation(
        db,
        acting_tenant=p.tenant_id,
        actor=ModelValidationActor(actor_id="validator-2l"),
        request=RecordValidationRequest(
            model_version_id=mv,
            validation_type="EXCEPTION",
            outcome="APPROVED_WITH_CONDITIONS",
            scope_summary="Use-before-validation grant (POC sequencing).",
            conditions="Controls: registered limitations + backtest monitoring.",
            next_review_due=past.date() + timedelta(days=180),  # expired long ago
        ),
        now=past,
    )
    db.commit()
    before = _count_var_runs(db, p.tenant_id)
    resp = client.post("/risk/vars/runs", json=_run_body(mv, fx_run, cov_run), headers=_h(p))
    assert resp.status_code == 422, resp.text
    assert "EXCEPTION has expired" in resp.json()["detail"]
    assert _count_var_runs(db, p.tenant_id) == before
