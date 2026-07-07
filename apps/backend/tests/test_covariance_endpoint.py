"""End-to-end tests of the P3-4 risk (covariance, sample v1) endpoints.

SQLite has no RLS (tenant isolation + append-only-trigger proofs are in
``packages/shared-python/tests/test_covariance_pg.py``); here we prove entitlement gating
(deny-by-default, no DB side-effect on denial; view-only cannot run — the REUSED ``risk.run``/
``risk.view``), the governed window-declaring model registration (incl. the 409 identity conflict
and the 422 window floor), the build-in-request run + read round-trip (values = the hand-computed
references), decimal serialization at 20dp, the pre-create refusals (422/404/409 — incl. the
fail-closed short-window 409), the post-create FAILED response (201 + status='FAILED' + zero
rows — the defensive gate, forced through the kernel seam), and no PUT/PATCH/DELETE.
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
from irp_shared.entitlement.models import AppUser, Permission, Role, RolePermission, UserRole
from irp_shared.entitlement.service import Principal
from irp_shared.marketdata.factor import (
    FactorActor,
    capture_factor,
    capture_factor_return,
    resolve_factor,
)
from irp_shared.models import Base

_PERMS = ("risk.run", "risk.view", "model.inventory.register")
_T0 = datetime(2026, 1, 1, tzinfo=UTC)
_VA = "2026-06-01T00:00:00Z"
_D = (date(2026, 5, 26), date(2026, 5, 27), date(2026, 5, 28), date(2026, 5, 29))
#: The hand-computed 2-factor references (see test_covariance.py): var = 1/6000 @ 20dp HALF_UP.
_REF_VAR = "0.00016666666666666667"
_REF_COV = "-0.00016666666666666667"


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
    db.flush()

    # Two factors with aligned 4-observation SIMPLE return windows (the hand-reference series).
    factor_ids: list[str] = []
    for code, values in (
        ("F_A", ("0.01", "0.02", "0.03", "0.04")),
        ("F_B", ("0.04", "0.03", "0.02", "0.01")),
    ):
        fid = capture_factor(
            db,
            factor_code=code,
            factor_source="VENDOR_F",
            factor_family="CURRENCY",
            currency_code=None,
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
    db.commit()
    principal = Principal(user_id=user.id, tenant_id=tenant_id)

    def _override_db() -> Iterator[Session]:
        yield db

    app = FastAPI()
    app.include_router(risk_router)
    app.dependency_overrides[get_db] = _override_db
    try:
        yield TestClient(app), principal, db, factor_ids[0], factor_ids[1]
    finally:
        db.close()
        engine.dispose()


def _h(p: Principal) -> dict[str, str]:
    return {"X-User-Id": p.user_id, "X-Tenant-Id": p.tenant_id}


def _register(client: TestClient, p: Principal, window: int = 4) -> str:
    resp = client.post(
        "/risk/models/covariance",
        json={"code_version": "risk-v1", "window_observations": window},
        headers=_h(p),
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["model_version_id"]


def _run_body(mv: str, factor_ids: list[str], **kw) -> dict:  # noqa: ANN003
    return {
        "code_version": "risk-v1",
        "environment_id": "ci",
        "model_version_id": mv,
        "factor_ids": factor_ids,
        "as_of_valid_at": _VA,
        **kw,
    }


def _count_cov_runs(db: Session, tenant: str) -> int:
    return db.execute(
        select(func.count())
        .select_from(CalculationRun)
        .where(CalculationRun.tenant_id == tenant, CalculationRun.run_type == "COVARIANCE")
    ).scalar_one()


def test_register_run_and_read_roundtrip(ctx) -> None:  # noqa: ANN001
    client, p, db, f_a, f_b = ctx
    mv = _register(client, p)
    resp = client.post("/risk/covariances/runs", json=_run_body(mv, [f_a, f_b]), headers=_h(p))
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["status"] == "COMPLETED" and body["run_type"] == "COVARIANCE"
    assert len(body["rows"]) == 3  # F·(F+1)/2 for F = 2
    diag = [r for r in body["rows"] if r["factor_id_1"] == r["factor_id_2"]]
    off = [r for r in body["rows"] if r["factor_id_1"] != r["factor_id_2"]]
    assert len(diag) == 2 and len(off) == 1
    for r in diag:
        assert Decimal(r["covariance_value"]) == Decimal(_REF_VAR)
    assert Decimal(off[0]["covariance_value"]) == Decimal(_REF_COV)
    for r in body["rows"]:
        assert r["statistic_type"] == "COVARIANCE"
        assert r["return_type"] == "SIMPLE" and r["frequency"] == "DAILY"
        assert r["n_observations"] == 4
        assert r["window_start"] == "2026-05-26" and r["window_end"] == "2026-05-29"
        assert r["factor_id_1"] <= r["factor_id_2"]  # canonical stored order
    # Read the run back + a single row.
    run_read = client.get(f"/risk/covariances/runs/{body['run_id']}", headers=_h(p))
    assert run_read.status_code == 200 and len(run_read.json()["rows"]) == 3
    row = body["rows"][0]
    row_read = client.get(f"/risk/covariances/{row['id']}", headers=_h(p))
    assert row_read.status_code == 200
    assert row_read.json()["covariance_value"] == row["covariance_value"]


def test_register_conflicts_and_floor(ctx) -> None:  # noqa: ANN001
    client, p, db, f_a, f_b = ctx
    mv = _register(client, p, window=4)
    assert _register(client, p, window=4) == mv  # idempotent same identity
    resp = client.post(
        "/risk/models/covariance",
        json={"code_version": "risk-v1", "window_observations": 5},  # same label, new window
        headers=_h(p),
    )
    assert resp.status_code == 409
    resp = client.post(
        "/risk/models/covariance",
        json={"code_version": "risk-v2", "window_observations": 4},  # same label, new code
        headers=_h(p),
    )
    assert resp.status_code == 409
    resp = client.post(
        "/risk/models/covariance",
        json={"code_version": "risk-v1", "window_observations": 1},  # the registration floor
        headers=_h(p),
    )
    assert resp.status_code == 422


def test_deny_by_default_no_side_effect(ctx) -> None:  # noqa: ANN001
    client, p, db, f_a, f_b = ctx
    mv = _register(client, p)
    nobody = Principal(user_id=str(uuid.uuid4()), tenant_id=p.tenant_id)  # no roles at all
    resp = client.post("/risk/covariances/runs", json=_run_body(mv, [f_a, f_b]), headers=_h(nobody))
    assert resp.status_code == 403
    assert _count_cov_runs(db, p.tenant_id) == 0  # denial leaves no run


def test_view_only_user_cannot_run(ctx) -> None:  # noqa: ANN001
    client, p, db, f_a, f_b = ctx
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
    resp = client.post("/risk/covariances/runs", json=_run_body(mv, [f_a, f_b]), headers=_h(vp))
    assert resp.status_code == 403  # .view does not grant .run (auditor-style read-only)
    assert _count_cov_runs(db, p.tenant_id) == 0


def test_pre_create_refusals_422_404_409(ctx) -> None:  # noqa: ANN001
    client, p, db, f_a, f_b = ctx
    mv = _register(client, p)
    body = _run_body(mv, [f_a, f_b])
    body.pop("factor_ids")  # neither factor_ids nor snapshot_id
    assert client.post("/risk/covariances/runs", json=body, headers=_h(p)).status_code == 422
    resp = client.post(  # unregistered model_version (CTRL-003 fail-closed)
        "/risk/covariances/runs", json=_run_body(str(uuid.uuid4()), [f_a, f_b]), headers=_h(p)
    )
    assert resp.status_code == 422
    resp = client.post(  # < 2 factors
        "/risk/covariances/runs", json=_run_body(mv, [f_a]), headers=_h(p)
    )
    assert resp.status_code == 422
    consume_body = {
        "code_version": "risk-v1",
        "environment_id": "ci",
        "model_version_id": mv,
        "snapshot_id": str(uuid.uuid4()),  # consume mode ONLY (no build args — P3-C1 gate)
    }
    resp = client.post("/risk/covariances/runs", json=consume_body, headers=_h(p))
    assert resp.status_code == 404
    assert _count_cov_runs(db, p.tenant_id) == 0


def test_short_window_fails_closed_409(ctx) -> None:  # noqa: ANN001
    client, p, db, f_a, f_b = ctx
    mv = _register(client, p, window=4)
    # A third factor with only TWO returns collapses the common window below the declared 4.
    f_c = capture_factor(
        db,
        factor_code="F_C",
        factor_source="VENDOR_F",
        factor_family="CURRENCY",
        currency_code=None,
        acting_tenant=p.tenant_id,
        actor=FactorActor(actor_id="s"),
        valid_from=_T0,
    ).id
    factor = resolve_factor(db, f_c, acting_tenant=p.tenant_id)
    for d, v in zip(_D[:2], ("0.01", "0.02"), strict=True):
        capture_factor_return(
            db,
            factor,
            return_date=d,
            return_value=Decimal(v),
            acting_tenant=p.tenant_id,
            actor=FactorActor(actor_id="s"),
            valid_from=_T0,
        )
    db.commit()
    resp = client.post("/risk/covariances/runs", json=_run_body(mv, [f_a, f_b, f_c]), headers=_h(p))
    assert resp.status_code == 409  # fail-closed BEFORE any write (no imputation)
    assert _count_cov_runs(db, p.tenant_id) == 0


def test_post_create_failed_returns_201_failed(ctx, monkeypatch: pytest.MonkeyPatch) -> None:  # noqa: ANN001
    client, p, db, f_a, f_b = ctx
    mv = _register(client, p)
    # The defensive gate is unreachable for the sample estimator — force a defect through the
    # kernel seam to prove the endpoint surfaces a committed FAILED run (201, zero rows).
    import irp_shared.risk.covariance_service as cs

    real = cs.estimate_covariance

    def poisoned(series):  # noqa: ANN001, ANN202
        out = real(series)
        out[sorted(out)[0]] = Decimal("-1")  # a negative diagonal
        return out

    monkeypatch.setattr(cs, "estimate_covariance", poisoned)
    resp = client.post("/risk/covariances/runs", json=_run_body(mv, [f_a, f_b]), headers=_h(p))
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["status"] == "FAILED" and body["rows"] == []
    assert body["failure_reason"]
    # The FAILED run is durable + readable (NOT a 404).
    read = client.get(f"/risk/covariances/runs/{body['run_id']}", headers=_h(p))
    assert read.status_code == 200 and read.json()["status"] == "FAILED"
    # P3-C1: the persisted reason SURFACES on read (previously hardcoded None).
    assert read.json()["failure_reason"] == body["failure_reason"]


def test_no_mutating_verbs(ctx) -> None:  # noqa: ANN001
    client, p, db, f_a, f_b = ctx
    for path in (
        f"/risk/covariances/{uuid.uuid4()}",
        f"/risk/covariances/runs/{uuid.uuid4()}",
        "/risk/models/covariance",
    ):
        for method in ("put", "patch", "delete"):
            resp = getattr(client, method)(path, headers=_h(p))
            assert resp.status_code == 405, (method, path)  # append-only: no mutation verbs
