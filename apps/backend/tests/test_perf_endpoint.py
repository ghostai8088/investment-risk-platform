"""End-to-end tests of the PM-1 performance (portfolio-return v1) endpoints.

SQLite has no RLS (tenant isolation + append-only-trigger proofs are in
``packages/shared-python/tests/test_portfolio_return_pg.py``); here we prove entitlement gating
(deny-by-default, no DB side-effect on denial; view-only cannot run — the NEW ``perf.run``/
``perf.view`` R-07 mint), the ``code_version``-only model registration (incl. the 409 identity
conflict), the build-in-request run + read round-trip over the two boundary exposure runs + the
external flow, fixed-point decimal serialization, the pre-create refusals (422/404), the both-modes
422, the ``/perf/runs`` listing, and no PUT/PATCH/DELETE on the route families.
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

from irp_backend.api.perf import router as perf_router
from irp_backend.deps import get_db
from irp_shared.calc.models import CalculationRun
from irp_shared.db.session import make_engine, make_session_factory
from irp_shared.entitlement.bootstrap import SYSTEM_TENANT_ID
from irp_shared.entitlement.models import AppUser, Permission, Role, RolePermission, UserRole
from irp_shared.entitlement.service import Principal
from irp_shared.exposure import ExposureActor, run_exposure
from irp_shared.models import Base
from irp_shared.portfolio import PortfolioActor, create_portfolio
from irp_shared.position import create_position
from irp_shared.position.service import PositionActor
from irp_shared.reference.instrument import create_instrument
from irp_shared.reference.models import Currency
from irp_shared.reference.service import ReferenceActor
from irp_shared.transaction import TransactionActor, record_transaction
from irp_shared.valuation import create_valuation
from irp_shared.valuation.service import ValuationActor

_PERMS = ("perf.run", "perf.view", "model.inventory.register")
_T0 = datetime(2026, 1, 1, tzinfo=UTC)
_KA = datetime(2030, 1, 1, tzinfo=UTC)
_D0, _D1 = date(2026, 1, 1), date(2026, 1, 31)
_MID = date(2026, 1, 16)


def _boundary_run(db, tenant, pf, inst, vdate, mark):  # noqa: ANN001, ANN202
    create_valuation(
        db,
        portfolio_id=pf,
        instrument_id=inst,
        valuation_date=vdate,
        acting_tenant=tenant,
        actor=ValuationActor(actor_id="s"),
        mark_value=Decimal(mark),
        currency_code="USD",
        valid_from=_T0,
    )
    return run_exposure(
        db,
        acting_tenant=tenant,
        actor=ExposureActor(actor_id="a"),
        code_version="v1",
        environment_id="ci",
        portfolio_id=pf,
        as_of_valid_at=datetime(vdate.year, vdate.month, vdate.day, tzinfo=UTC),
        as_of_known_at=_KA,
        base_currency="USD",
    ).run.run_id


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

    pf = create_portfolio(
        db,
        tenant_id=tenant_id,
        code=f"ACCT-{uuid.uuid4().hex[:6]}",
        name="acct",
        node_type="ACCOUNT",
        actor=PortfolioActor(actor_id="s"),
    ).id
    inst = create_instrument(
        db,
        tenant_id=tenant_id,
        code=f"I-{uuid.uuid4().hex[:6]}",
        name="i",
        asset_class="EQUITY",
        actor=ReferenceActor(actor_id="s"),
    ).id
    create_position(
        db,
        portfolio_id=pf,
        instrument_id=inst,
        acting_tenant=tenant_id,
        actor=PositionActor(actor_id="s"),
        quantity=Decimal("1"),
        valid_from=_T0,
    )
    r0 = _boundary_run(db, tenant_id, pf, inst, _D0, "1000000")
    r1 = _boundary_run(db, tenant_id, pf, inst, _D1, "1050000")
    record_transaction(
        db,
        tenant_id=tenant_id,
        portfolio_id=pf,
        instrument_id=inst,
        txn_type="TRANSFER_IN",
        trade_date=_MID,
        quantity=Decimal("0"),
        gross_amount=Decimal("20000"),
        currency_code="USD",
        actor=TransactionActor(actor_id="s"),
    )
    db.commit()
    principal = Principal(user_id=user.id, tenant_id=tenant_id)

    def _override_db() -> Iterator[Session]:
        yield db

    app = FastAPI()
    app.include_router(perf_router)
    app.dependency_overrides[get_db] = _override_db
    try:
        yield TestClient(app), principal, db, r0, r1
    finally:
        db.close()
        engine.dispose()


def _h(p: Principal) -> dict[str, str]:
    return {"X-User-Id": p.user_id, "X-Tenant-Id": p.tenant_id}


def _register(client: TestClient, p: Principal, code_version: str = "perf-v1") -> str:
    resp = client.post(
        "/perf/models/portfolio-return", json={"code_version": code_version}, headers=_h(p)
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["model_version_id"]


def _run_body(mv: str, r0: str, r1: str, **kw) -> dict:  # noqa: ANN003
    return {
        "code_version": "perf-v1",
        "environment_id": "ci",
        "model_version_id": mv,
        "exposure_run_ids": [r0, r1],
        **kw,
    }


def _count_runs(db: Session, tenant: str) -> int:
    return db.execute(
        select(func.count())
        .select_from(CalculationRun)
        .where(CalculationRun.tenant_id == tenant, CalculationRun.run_type == "PORTFOLIO_RETURN")
    ).scalar_one()


def test_rejected_model_version_run_is_422_not_500(ctx) -> None:  # noqa: ANN001
    """VW-1 OD-B end-to-end through a REAL PERF family run endpoint (the perf half of the "one risk
    + one perf" proof): a latest-outcome REJECTED validation on the bound model_version makes a new
    run refuse with a governed 422 (RejectedModelVersionError mapped in perf.py), not a raw 500."""
    from irp_shared.model.validation import (
        ModelValidationActor,
        RecordValidationRequest,
        record_validation,
    )

    client, p, db, r0, r1 = ctx
    mv = _register(client, p)
    record_validation(
        db,
        acting_tenant=p.tenant_id,
        actor=ModelValidationActor(actor_id="validator-2l"),
        request=RecordValidationRequest(
            model_version_id=mv,
            validation_type="INITIAL",
            outcome="REJECTED",
            scope_summary="Methodology not fit for use pending remediation.",
        ),
    )
    db.commit()
    resp = client.post("/perf/portfolio-returns/runs", json=_run_body(mv, r0, r1), headers=_h(p))
    assert resp.status_code == 422, resp.text
    assert "REJECTED" in resp.json()["detail"]
    assert _count_runs(db, p.tenant_id) == 0  # no run persisted


def test_register_run_and_read_roundtrip(ctx) -> None:  # noqa: ANN001
    client, p, db, r0, r1 = ctx
    mv = _register(client, p)
    resp = client.post("/perf/portfolio-returns/runs", json=_run_body(mv, r0, r1), headers=_h(p))
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["status"] == "COMPLETED" and body["run_type"] == "PORTFOLIO_RETURN"
    assert len(body["rows"]) == 2  # DIETZ_PERIOD + TWR_LINKED
    dietz = next(r for r in body["rows"] if r["metric_type"] == "DIETZ_PERIOD")
    assert dietz["return_value"] == "0.029702970297"
    assert dietz["begin_mv"] == "1000000.000000" and dietz["end_mv"] == "1050000.000000"
    assert dietz["net_external_flow"] == "20000.000000"
    assert dietz["base_currency"] == "USD" and dietz["n_flows"] == 1
    for field in ("begin_mv", "end_mv", "net_external_flow", "return_value"):
        assert "E" not in dietz[field] and "e" not in dietz[field]  # fixed-point, never scientific
    run_read = client.get(f"/perf/portfolio-returns/runs/{body['run_id']}", headers=_h(p))
    assert run_read.status_code == 200 and len(run_read.json()["rows"]) == 2
    row_read = client.get(f"/perf/portfolio-returns/{dietz['id']}", headers=_h(p))
    assert row_read.status_code == 200 and row_read.json()["return_value"] == dietz["return_value"]
    # The /perf/runs listing surfaces the run.
    listing = client.get("/perf/runs", headers=_h(p))
    assert listing.status_code == 200
    assert any(item["run_id"] == body["run_id"] for item in listing.json()["items"])


def test_register_idempotent_and_conflict(ctx) -> None:  # noqa: ANN001
    client, p, db, r0, r1 = ctx
    mv = _register(client, p)
    assert _register(client, p) == mv  # idempotent same code_version
    resp = client.post(
        "/perf/models/portfolio-return", json={"code_version": "perf-v2"}, headers=_h(p)
    )
    assert resp.status_code == 409  # same label, different code_version


def test_deny_by_default_and_view_only_cannot_run(ctx) -> None:  # noqa: ANN001
    client, p, db, r0, r1 = ctx
    mv = _register(client, p)
    nobody = Principal(user_id=str(uuid.uuid4()), tenant_id=p.tenant_id)
    resp = client.post(
        "/perf/portfolio-returns/runs", json=_run_body(mv, r0, r1), headers=_h(nobody)
    )
    assert resp.status_code == 403
    viewer = AppUser(tenant_id=p.tenant_id, display_name="V")
    view_role = Role(tenant_id=p.tenant_id, code="v", name="V")
    db.add_all([viewer, view_role])
    db.flush()
    perm_id = db.execute(select(Permission.id).where(Permission.code == "perf.view")).scalar_one()
    db.add(RolePermission(role_id=view_role.id, permission_id=perm_id))
    db.add(UserRole(tenant_id=p.tenant_id, user_id=viewer.id, role_id=view_role.id))
    db.commit()
    vp = Principal(user_id=viewer.id, tenant_id=p.tenant_id)
    resp = client.post("/perf/portfolio-returns/runs", json=_run_body(mv, r0, r1), headers=_h(vp))
    assert resp.status_code == 403  # .view does not grant .run
    assert _count_runs(db, p.tenant_id) == 0


def test_pre_create_refusals_and_both_modes(ctx) -> None:  # noqa: ANN001
    client, p, db, r0, r1 = ctx
    mv = _register(client, p)
    # Unregistered model_version (CTRL-003 fail-closed).
    resp = client.post(
        "/perf/portfolio-returns/runs", json=_run_body(str(uuid.uuid4()), r0, r1), headers=_h(p)
    )
    assert resp.status_code == 422
    # Fewer than two boundaries.
    resp = client.post(
        "/perf/portfolio-returns/runs",
        json={
            "code_version": "perf-v1",
            "environment_id": "ci",
            "model_version_id": mv,
            "exposure_run_ids": [r0],
        },
        headers=_h(p),
    )
    assert resp.status_code == 422
    # Both modes at once => 422.
    resp = client.post(
        "/perf/portfolio-returns/runs",
        json=_run_body(mv, r0, r1, snapshot_id=str(uuid.uuid4())),
        headers=_h(p),
    )
    assert resp.status_code == 422
    assert _count_runs(db, p.tenant_id) == 0  # every refusal left ZERO run


def test_run_listing_fail_closed_filter(ctx) -> None:  # noqa: ANN001
    client, p, db, r0, r1 = ctx
    # An unknown run_type is a 422, never a silently-empty page.
    resp = client.get("/perf/runs", params={"run_type": "NOT_A_TYPE"}, headers=_h(p))
    assert resp.status_code == 422


def test_no_mutating_verbs(ctx) -> None:  # noqa: ANN001
    client, p, db, r0, r1 = ctx
    for verb in ("put", "patch", "delete"):
        resp = getattr(client, verb)("/perf/portfolio-returns/runs", headers=_h(p))
        assert resp.status_code == 405


def test_expired_exception_run_is_422_not_500(ctx) -> None:  # noqa: ANN001
    """MG-1 OD-F end-to-end through a REAL PERF run endpoint (the perf half of the 'one risk +
    one perf' proof): an EXPIRED use-before-validation EXCEPTION refuses a new run with a
    governed 422 (ExpiredModelExceptionError mapped in perf.py), not a raw 500."""
    from datetime import UTC, datetime, timedelta

    from irp_shared.model.validation import (
        ModelValidationActor,
        RecordValidationRequest,
        record_validation,
    )

    client, p, db, r0, r1 = ctx
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
            conditions="Controls: registered limitations + monitoring.",
            next_review_due=past.date() + timedelta(days=180),
        ),
        now=past,
    )
    db.commit()
    resp = client.post("/perf/portfolio-returns/runs", json=_run_body(mv, r0, r1), headers=_h(p))
    assert resp.status_code == 422, resp.text
    assert "EXCEPTION has expired" in resp.json()["detail"]
    assert _count_runs(db, p.tenant_id) == 0


def test_api1_entity_reads_portfolio_returns(ctx) -> None:  # noqa: ANN001
    """API-1 (Class A): the entity/time read + latest-resolver over portfolio_return_result — the
    pacing template replicated. Confirms the entity filter, the new calculation_run_id
    discriminator, silent-empty on a foreign id, the /latest route (not shadowed by /{result_id}),
    and its portfolio_id requirement."""
    client, p, db, r0, r1 = ctx
    mv = _register(client, p)
    body = client.post(
        "/perf/portfolio-returns/runs", json=_run_body(mv, r0, r1), headers=_h(p)
    ).json()
    run_id = body["run_id"]
    pf = body["rows"][0]["portfolio_id"]
    assert body["rows"][0]["calculation_run_id"] == run_id  # the additive API-1 discriminator

    lst = client.get("/perf/portfolio-returns", params={"portfolio_id": pf}, headers=_h(p))
    assert lst.status_code == 200
    rows = lst.json()
    assert rows and all(r["portfolio_id"] == pf for r in rows)
    assert {r["calculation_run_id"] for r in rows} == {run_id}

    empty = client.get(
        "/perf/portfolio-returns", params={"portfolio_id": str(uuid.uuid4())}, headers=_h(p)
    )
    assert empty.status_code == 200 and empty.json() == []

    latest = client.get(
        "/perf/portfolio-returns/latest", params={"portfolio_id": pf}, headers=_h(p)
    )
    assert latest.status_code == 200  # /latest resolves (route ordering correct)
    assert {r["calculation_run_id"] for r in latest.json()} == {run_id}
    # /latest requires portfolio_id.
    assert client.get("/perf/portfolio-returns/latest", headers=_h(p)).status_code == 422


def test_api1_entity_reads_benchmark_relative_and_desmoothed_smoke(ctx) -> None:  # noqa: ANN001
    """API-1 (Class A/perf): the entity + /latest reads for benchmark-relative + desmoothed-returns
    resolve, are silent-empty on a tenant with no runs, require portfolio_id on /latest, and deny-
    by-default. The full-data path is the same shared calc/reads helper the portfolio-returns test +
    the CC-2 pacing golden already prove; this pins the router wiring (routes exist, /latest not
    shadowed by /{result_id}, gating)."""
    client, p, db, *_ = ctx
    pf = str(uuid.uuid4())
    inst = str(uuid.uuid4())
    # benchmark-relative: entity + /latest keyed by portfolio_id (benchmark_id optional).
    assert (
        client.get("/perf/benchmark-relative", params={"portfolio_id": pf}, headers=_h(p)).json()
        == []
    )
    br_latest = client.get(
        "/perf/benchmark-relative/latest", params={"portfolio_id": pf}, headers=_h(p)
    )
    assert br_latest.status_code == 200 and br_latest.json() == []  # /latest resolves, empty
    assert client.get("/perf/benchmark-relative/latest", headers=_h(p)).status_code == 422
    # desmoothed-returns: entity + /latest keyed by (portfolio_id, instrument_id).
    assert (
        client.get("/perf/desmoothed-returns", params={"portfolio_id": pf}, headers=_h(p)).json()
        == []
    )
    ds_latest = client.get(
        "/perf/desmoothed-returns/latest",
        params={"portfolio_id": pf, "instrument_id": inst},
        headers=_h(p),
    )
    assert ds_latest.status_code == 200 and ds_latest.json() == []
    # /latest requires BOTH keys — portfolio_id alone is a 422.
    assert (
        client.get(
            "/perf/desmoothed-returns/latest", params={"portfolio_id": pf}, headers=_h(p)
        ).status_code
        == 422
    )
    # Deny-by-default: a stranger (no perf.view) is 403 on the entity read.
    stranger = {"X-User-Id": str(uuid.uuid4()), "X-Tenant-Id": p.tenant_id}
    denied = client.get("/perf/benchmark-relative", params={"portfolio_id": pf}, headers=stranger)
    assert denied.status_code == 403
