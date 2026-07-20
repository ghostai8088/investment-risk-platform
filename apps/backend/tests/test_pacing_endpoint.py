"""CC-2 endpoint tier — the pacing registrar + run + reads, the error-map wiring, deny-by-default,
the governed-output view parity (``pacing.view``), and the rule-7 reads incl. the latest-resolver.

A full build-in-request run roundtrip is exercised here (a stage-8-shaped commitment + mark seeded
on the SQLite session); the numeric golden lives at the unit tier (``test_pacing_kernel.py`` /
``test_pacing_binder.py``) and runs LIVE at demo stage 9 on PG. This tier pins the HTTP contract
(201/403/404/422 shapes + the latest-resolver determinism)."""

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

from irp_backend.api.pacing import router as pacing_router
from irp_backend.deps import get_db
from irp_shared.db.session import make_engine, make_session_factory
from irp_shared.entitlement.models import AppUser, Permission, Role, RolePermission, UserRole
from irp_shared.entitlement.service import Principal
from irp_shared.models import Base
from irp_shared.portfolio import PortfolioActor, create_portfolio
from irp_shared.private_capital.capital_flow_service import CapitalFlowActor, capture_capital_call
from irp_shared.private_capital.commitment_service import CommitmentActor, capture_commitment
from irp_shared.reference.instrument import create_instrument
from irp_shared.reference.service import ReferenceActor
from irp_shared.valuation import create_valuation
from irp_shared.valuation.service import ValuationActor

_PERMS = ("model.inventory.register", "pacing.run", "pacing.view")
_VF = datetime(2024, 1, 1, tzinfo=UTC)


def _grant(db: Session, tenant_id: str, display: str, perms: tuple[str, ...]) -> Principal:
    """Create a user with a role granting exactly ``perms`` (idempotent per-code permission)."""
    user = AppUser(tenant_id=tenant_id, display_name=display)
    role = Role(tenant_id=tenant_id, code=f"r-{display}", name=display)
    db.add_all([user, role])
    db.flush()
    for code in perms:
        perm = db.query(Permission).filter(Permission.code == code).one_or_none() or Permission(
            code=code, description="d"
        )
        if perm.id is None:
            db.add(perm)
            db.flush()
        db.add(RolePermission(role_id=role.id, permission_id=perm.id))
    db.add(UserRole(tenant_id=tenant_id, user_id=user.id, role_id=role.id))
    db.flush()
    return Principal(user_id=user.id, tenant_id=tenant_id)


@pytest.fixture
def ctx() -> Iterator[tuple[TestClient, Principal, Principal, Session, str, str]]:
    engine = make_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    db = make_session_factory(engine)()
    tenant_id = str(uuid.uuid4())

    principal = _grant(db, tenant_id, "maker", _PERMS)
    viewer = _grant(db, tenant_id, "viewer", ("pacing.view",))  # governed-output view parity

    pf = create_portfolio(
        db,
        tenant_id=tenant_id,
        code=f"PE-{uuid.uuid4().hex[:6]}",
        name="pe",
        node_type="ACCOUNT",
        actor=PortfolioActor(actor_id="s"),
    ).id
    fund = create_instrument(
        db,
        tenant_id=tenant_id,
        code=f"FUND-{uuid.uuid4().hex[:6]}",
        name="Fund",
        asset_class="PRIVATE_EQUITY",
        actor=ReferenceActor(actor_id="s"),
    ).id
    # A stage-8-shaped commitment (25M committed 2024-06-30, 10M called) + a same-currency mark
    # (age 1 at the 2025-06-30 as-of) so a build-in-request run COMPLETES.
    capture_commitment(
        db,
        portfolio_id=pf,
        instrument_id=fund,
        committed_amount=Decimal("25000000.000000"),
        currency_code="USD",
        commitment_date=date(2024, 6, 30),
        acting_tenant=tenant_id,
        actor=CommitmentActor(actor_id="s"),
        valid_from=datetime(2024, 6, 30, tzinfo=UTC),
    )
    capture_capital_call(
        db,
        portfolio_id=pf,
        instrument_id=fund,
        event_date=date(2024, 8, 15),
        amount=Decimal("10000000.000000"),
        currency_code="USD",
        call_type="DRAWDOWN",
        acting_tenant=tenant_id,
        actor=CapitalFlowActor(actor_id="s"),
    )
    create_valuation(
        db,
        portfolio_id=pf,
        instrument_id=fund,
        valuation_date=date(2025, 6, 30),
        acting_tenant=tenant_id,
        actor=ValuationActor(actor_id="s"),
        mark_value=Decimal("11200000.000000"),
        currency_code="USD",
        valid_from=_VF,
    )
    db.commit()

    def _override_db() -> Iterator[Session]:
        yield db

    app = FastAPI()
    app.include_router(pacing_router)
    app.dependency_overrides[get_db] = _override_db
    try:
        yield TestClient(app), principal, viewer, db, pf, fund
    finally:
        db.close()
        engine.dispose()


def _h(p: Principal) -> dict[str, str]:
    return {"X-User-Id": p.user_id, "X-Tenant-Id": p.tenant_id}


def _model_body(**kw: object) -> dict:
    base = {
        "code_version": "cc2-v1",
        "rc_schedule": ["0.25", "0.4", "0.5"],
        "fund_life": 12,
        "bow": "2.5",
        "growth": "0.13",
        "yield_floor": "0",
    }
    base.update(kw)
    return base


def _register(client: TestClient, p: Principal, **kw: object) -> str:
    resp = client.post(
        "/pacing/models/commitment-projection", json=_model_body(**kw), headers=_h(p)
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["model_version_id"]


def _run_pair(client: TestClient, p: Principal, mv: str, pf: str, fund: str) -> dict:
    resp = client.post(
        "/pacing/projections/runs",
        json={
            "code_version": "cc2-v1",
            "environment_id": "ci",
            "model_version_id": mv,
            "portfolio_id": pf,
            "instrument_id": fund,
        },
        headers=_h(p),
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_register_roundtrip_and_identity(ctx) -> None:  # noqa: ANN001
    client, p, _v, _db, _pf, _fund = ctx
    resp = client.post("/pacing/models/commitment-projection", json=_model_body(), headers=_h(p))
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["version_label"] == "v1" and body["status"] == "REGISTERED"
    # Idempotent same-declaration re-register resolves to the SAME version.
    again = client.post("/pacing/models/commitment-projection", json=_model_body(), headers=_h(p))
    assert again.status_code == 201
    assert again.json()["model_version_id"] == body["model_version_id"]
    # Same-label different-declaration => governed 409.
    conflict = client.post(
        "/pacing/models/commitment-projection", json=_model_body(growth="0.10"), headers=_h(p)
    )
    assert conflict.status_code == 409
    # Invalid parameters (rc_schedule longer than fund_life) => the FIXED 422 (never a 500).
    bad = client.post(
        "/pacing/models/commitment-projection",
        json=_model_body(fund_life=2),  # 3-entry schedule > life 2
        headers=_h(p),
    )
    assert bad.status_code == 422
    assert bad.json()["detail"] == "invalid pacing model parameters"


def test_run_roundtrip_and_reads(ctx) -> None:  # noqa: ANN001
    client, p, _v, _db, pf, fund = ctx
    mv = _register(client, p)
    body = _run_pair(client, p, mv, pf, fund)
    assert body["status"] == "COMPLETED" and body["run_type"] == "PACING_PROJECTION"
    rows = body["rows"]
    assert rows, "a completed projection has period rows"
    # Age 1 at the 2025-06-30 as-of (vintage 2024-06-30) -> first FUTURE period is 2.
    assert rows[0]["period_index"] == 2
    assert rows[-1]["period_index"] == 12
    assert rows[0]["currency_code"] == "USD"
    # unfunded(0)=25M-10M=15M; period-2 rc=0.4 (schedule[.25,.4,.5], age 2) -> call=6,000,000.
    assert rows[0]["projected_call"] == "6000000.000000"
    for f in ("projected_call", "projected_distribution", "projected_nav", "unfunded_end"):
        assert "E" not in rows[0][f] and "e" not in rows[0][f]  # fixed-point, never scientific
    # Run-centric reads.
    run_read = client.get(f"/pacing/projections/runs/{body['run_id']}", headers=_h(p))
    assert run_read.status_code == 200 and len(run_read.json()["rows"]) == len(rows)
    row_read = client.get(f"/pacing/projections/results/{rows[0]['id']}", headers=_h(p))
    assert row_read.status_code == 200
    assert row_read.json()["projected_call"] == rows[0]["projected_call"]


def test_run_body_must_be_exactly_one_form(ctx) -> None:  # noqa: ANN001
    client, p, _v, _db, pf, fund = ctx
    mv = _register(client, p)
    # Neither snapshot_id nor pair => 422.
    neither = client.post(
        "/pacing/projections/runs",
        json={"code_version": "cc2-v1", "environment_id": "ci", "model_version_id": mv},
        headers=_h(p),
    )
    assert neither.status_code == 422
    # Both snapshot_id and pair => 422.
    both = client.post(
        "/pacing/projections/runs",
        json={
            "code_version": "cc2-v1",
            "environment_id": "ci",
            "model_version_id": mv,
            "snapshot_id": str(uuid.uuid4()),
            "portfolio_id": pf,
            "instrument_id": fund,
        },
        headers=_h(p),
    )
    assert both.status_code == 422


def test_run_refusals_and_error_map_wiring(ctx) -> None:  # noqa: ANN001
    client, p, _v, _db, pf, fund = ctx
    mv = _register(client, p)
    # A consume of an unknown snapshot id => SnapshotNotFound 404.
    unknown_snap = client.post(
        "/pacing/projections/runs",
        json={
            "code_version": "cc2-v1",
            "environment_id": "ci",
            "model_version_id": mv,
            "snapshot_id": str(uuid.uuid4()),
        },
        headers=_h(p),
    )
    assert unknown_snap.status_code == 404
    # An unregistered model_version id => the CTRL-003 422 (never a 500).
    unreg = client.post(
        "/pacing/projections/runs",
        json={
            "code_version": "cc2-v1",
            "environment_id": "ci",
            "model_version_id": str(uuid.uuid4()),
            "portfolio_id": pf,
            "instrument_id": fund,
        },
        headers=_h(p),
    )
    assert unreg.status_code == 422
    # Build-in-request on a pair with NO commitment => PacingSnapshotError 409.
    orphan_pf = create_portfolio(
        _db,
        tenant_id=p.tenant_id,
        code=f"ORPH-{uuid.uuid4().hex[:6]}",
        name="orphan",
        node_type="ACCOUNT",
        actor=PortfolioActor(actor_id="s"),
    ).id
    _db.commit()
    no_commit = client.post(
        "/pacing/projections/runs",
        json={
            "code_version": "cc2-v1",
            "environment_id": "ci",
            "model_version_id": mv,
            "portfolio_id": orphan_pf,
            "instrument_id": fund,
        },
        headers=_h(p),
    )
    assert no_commit.status_code == 409
    # Unknown run/result reads => 404, never a 500.
    assert client.get(f"/pacing/projections/runs/{uuid.uuid4()}", headers=_h(p)).status_code == 404
    assert (
        client.get(f"/pacing/projections/results/{uuid.uuid4()}", headers=_h(p)).status_code == 404
    )


def test_rule7_reads_and_latest_resolver(ctx) -> None:  # noqa: ANN001
    client, p, _v, _db, pf, fund = ctx
    mv1 = _register(client, p)
    r1 = _run_pair(client, p, mv1, pf, fund)
    # A second run under a distinct version label on the same pair.
    mv2 = _register(client, p, code_version="cc2-v1b", version_label="v1b", growth="0.10")
    r2 = _run_pair(client, p, mv2, pf, fund)

    # The entity-filtered list returns BOTH runs' rows (cross-run aggregation is a consumer error).
    listing = client.get(
        "/pacing/projections",
        params={"portfolio_id": pf, "instrument_id": fund},
        headers=_h(p),
    )
    assert listing.status_code == 200
    run_ids = {row["calculation_run_id"] for row in listing.json()["items"]}
    assert run_ids == {r1["run_id"], r2["run_id"]}

    # The latest-resolver returns ONLY the newest run's rows (r2), period-ordered.
    latest = client.get(
        "/pacing/projections/latest",
        params={"portfolio_id": pf, "instrument_id": fund},
        headers=_h(p),
    )
    assert latest.status_code == 200
    lbody = latest.json()
    assert lbody["run_id"] == r2["run_id"]
    idxs = [row["period_index"] for row in lbody["rows"]]
    assert idxs == sorted(idxs)

    # A foreign pair => silent-empty list; latest => 404.
    empty = client.get(
        "/pacing/projections",
        params={"portfolio_id": str(uuid.uuid4()), "instrument_id": fund},
        headers=_h(p),
    )
    assert empty.status_code == 200 and empty.json()["items"] == []
    none_latest = client.get(
        "/pacing/projections/latest",
        params={"portfolio_id": str(uuid.uuid4()), "instrument_id": fund},
        headers=_h(p),
    )
    assert none_latest.status_code == 404


def test_view_parity_and_deny_by_default(ctx) -> None:  # noqa: ANN001
    client, p, viewer, _db, pf, fund = ctx
    mv = _register(client, p)
    body = _run_pair(client, p, mv, pf, fund)
    # A holder of ONLY pacing.view CAN read every governed-output surface (the auditor_3l parity).
    assert (
        client.get(f"/pacing/projections/runs/{body['run_id']}", headers=_h(viewer)).status_code
        == 200
    )
    assert (
        client.get(
            "/pacing/projections",
            params={"portfolio_id": pf, "instrument_id": fund},
            headers=_h(viewer),
        ).status_code
        == 200
    )
    assert (
        client.get(
            "/pacing/projections/latest",
            params={"portfolio_id": pf, "instrument_id": fund},
            headers=_h(viewer),
        ).status_code
        == 200
    )
    # …but CANNOT register or run (deny-by-default; .view grants neither maker verb).
    assert (
        client.post(
            "/pacing/models/commitment-projection", json=_model_body(), headers=_h(viewer)
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/pacing/projections/runs",
            json={
                "code_version": "cc2-v1",
                "environment_id": "ci",
                "model_version_id": mv,
                "portfolio_id": pf,
                "instrument_id": fund,
            },
            headers=_h(viewer),
        ).status_code
        == 403
    )
    # A total stranger is denied everywhere.
    stranger = {"X-User-Id": str(uuid.uuid4()), "X-Tenant-Id": p.tenant_id}
    assert (
        client.post(
            "/pacing/models/commitment-projection", json=_model_body(), headers=stranger
        ).status_code
        == 403
    )
    assert (
        client.get(f"/pacing/projections/runs/{uuid.uuid4()}", headers=stranger).status_code == 403
    )


def test_no_mutating_verbs(ctx) -> None:  # noqa: ANN001
    client, p, _v, _db, _pf, _fund = ctx
    for url in (
        f"/pacing/projections/runs/{uuid.uuid4()}",
        f"/pacing/projections/results/{uuid.uuid4()}",
    ):
        for method in ("put", "patch", "delete"):
            assert getattr(client, method)(url, headers=_h(p)).status_code == 405
