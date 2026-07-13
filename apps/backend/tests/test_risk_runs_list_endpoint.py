"""End-to-end tests of the FE-1 read-only runs listing (``GET /risk/runs``, OD-FE-1-C).

SQLite has no RLS (the PG suites carry the RLS proofs); here we prove the endpoint's OWN
tenant predicate (two-tenant separation through the API), the four-run_type fence (an
exposure/MARKET_VALUE run in the same table never appears; asking for it is a 422), the
fail-closed filters (unknown status / out-of-bounds limit/offset ⇒ 422, never a silently-empty
page), deterministic newest-first pagination, entitlement gating (403 without ``risk.view``;
401 without a principal), ``failure_reason`` surfacing in the list, and read-only-ness
(no mutation methods on the route).
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from irp_backend.api.risk import router as risk_router
from irp_backend.deps import get_db
from irp_shared.calc.models import CalculationRun
from irp_shared.db.session import make_engine, make_session_factory
from irp_shared.entitlement.models import AppUser, Permission, Role, RolePermission, UserRole
from irp_shared.exposure import RUN_TYPE_EXPOSURE_AGGREGATE
from irp_shared.models import Base
from irp_shared.risk import RISK_RUN_TYPES

_T0 = datetime(2026, 6, 1, tzinfo=UTC)

#: The ratified fence, pinned as LITERALS (review fold: deriving expectations from
#: RISK_RUN_TYPES itself made the guard self-referential — a widened or shrunk constant
#: would self-adopt). A membership change must turn THIS file red first.
_RATIFIED_RISK_RUN_TYPES = frozenset(
    # VAR_BACKTEST joined at BT-1 (OD-BT-1-B, ratified 2026-07-10); SCENARIO joined at P3-6
    # (OD-P3-6-E, ratified 2026-07-12); PROXY_WEIGHT_ESTIMATE joined at PA-3 (2026-07-13, the
    # review fold — every governed risk family belongs in the listing) — all under the REUSED
    # risk.view.
    {
        "SENSITIVITY",
        "FACTOR_EXPOSURE",
        "COVARIANCE",
        "VAR",
        "ACTIVE_RISK",
        "VAR_BACKTEST",
        "SCENARIO",
        "PROXY_WEIGHT_ESTIMATE",
    }
)


def test_risk_run_types_is_exactly_the_ratified_set() -> None:
    assert RISK_RUN_TYPES == _RATIFIED_RISK_RUN_TYPES
    # The exposure family's REAL run_type (the production constant, not a lookalike) is out.
    assert RUN_TYPE_EXPOSURE_AGGREGATE == "EXPOSURE_AGGREGATE"
    assert RUN_TYPE_EXPOSURE_AGGREGATE not in RISK_RUN_TYPES


def _grant(db: Session, tenant_id: str, *perms: str) -> str:
    """Mint a user in ``tenant_id`` holding ``perms``; return the user id."""
    user = AppUser(tenant_id=tenant_id, display_name="U")
    role = Role(tenant_id=tenant_id, code=f"r-{uuid.uuid4().hex[:8]}", name="R")
    db.add_all([user, role])
    db.flush()
    for code in perms:
        perm = db.query(Permission).filter_by(code=code).one_or_none()
        if perm is None:
            perm = Permission(code=code, description="d")
            db.add(perm)
            db.flush()
        db.add(RolePermission(role_id=role.id, permission_id=perm.id))
    db.add(UserRole(tenant_id=tenant_id, user_id=user.id, role_id=role.id))
    db.flush()
    return str(user.id)


def _mint_run(
    db: Session,
    tenant_id: str,
    run_type: str,
    *,
    status: str = "COMPLETED",
    created_at: datetime = _T0,
    failure_reason: str | None = None,
) -> str:
    """Insert a bare ``calculation_run`` row directly (the listing reads the table; the
    governed creation paths are proven in their own suites)."""
    run = CalculationRun(
        tenant_id=tenant_id,
        run_type=run_type,
        status=status,
        initiated_by="seed",
        code_version="v1",
        environment_id="test",
        created_at=created_at,
        failure_reason=failure_reason,
    )
    db.add(run)
    db.flush()
    return str(run.run_id)


@pytest.fixture
def ctx() -> Iterator[tuple[TestClient, Session, str, str, str, str]]:
    engine = make_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    db = make_session_factory(engine)()

    tenant_a = str(uuid.uuid4())
    tenant_b = str(uuid.uuid4())
    viewer_a = _grant(db, tenant_a, "risk.view")
    viewer_b = _grant(db, tenant_b, "risk.view")
    db.commit()

    app = FastAPI()
    app.include_router(risk_router)
    app.dependency_overrides[get_db] = lambda: db
    client = TestClient(app)
    try:
        yield client, db, tenant_a, tenant_b, viewer_a, viewer_b
    finally:
        db.close()


def _hdr(user_id: str, tenant_id: str) -> dict[str, str]:
    return {"X-User-Id": user_id, "X-Tenant-Id": tenant_id}


def test_lists_only_own_tenant_and_only_risk_run_types(ctx) -> None:
    client, db, tenant_a, tenant_b, viewer_a, viewer_b = ctx
    ids_a = {
        _mint_run(db, tenant_a, rt, created_at=_T0 + timedelta(minutes=i))
        for i, rt in enumerate(sorted(_RATIFIED_RISK_RUN_TYPES))  # literals, not the constant
    }
    # The REAL exposure-family run_type (production writes EXPOSURE_AGGREGATE) — must NEVER
    # appear under risk.view (the review fold: a MARKET_VALUE witness guarded nothing).
    _mint_run(db, tenant_a, RUN_TYPE_EXPOSURE_AGGREGATE)
    id_b = _mint_run(db, tenant_b, "VAR")
    db.commit()

    body = client.get("/risk/runs", headers=_hdr(viewer_a, tenant_a)).json()
    got = {item["run_id"] for item in body["items"]}
    assert got == ids_a  # all five risk families, no exposure run, nothing of tenant B

    body_b = client.get("/risk/runs", headers=_hdr(viewer_b, tenant_b)).json()
    assert {item["run_id"] for item in body_b["items"]} == {id_b}


def test_filters_and_failure_reason_surfaced(ctx) -> None:
    client, db, tenant_a, _tenant_b, viewer_a, _viewer_b = ctx
    ok = _mint_run(db, tenant_a, "VAR", status="COMPLETED")
    bad = _mint_run(
        db,
        tenant_a,
        "VAR",
        status="FAILED",
        created_at=_T0 + timedelta(minutes=1),
        failure_reason="rule 'x' failed (severity=ERROR)",
    )
    _mint_run(db, tenant_a, "COVARIANCE")
    db.commit()

    body = client.get(
        "/risk/runs", params={"run_type": "VAR"}, headers=_hdr(viewer_a, tenant_a)
    ).json()
    assert [i["run_id"] for i in body["items"]] == [bad, ok]  # newest first
    assert body["items"][0]["failure_reason"] == "rule 'x' failed (severity=ERROR)"
    assert body["items"][1]["failure_reason"] is None

    failed_only = client.get(
        "/risk/runs",
        params={"run_type": "VAR", "status": "FAILED"},
        headers=_hdr(viewer_a, tenant_a),
    ).json()
    assert [i["run_id"] for i in failed_only["items"]] == [bad]


def test_pagination_is_deterministic_newest_first(ctx) -> None:
    client, db, tenant_a, _tenant_b, viewer_a, _viewer_b = ctx
    # Three runs sharing ONE created_at (the tie) + one newer. EXPLICIT run_ids inserted in
    # NON-ascending order (c, a, b) so the run_id tie-break is the ONLY thing that can produce
    # ascending pages — with random uuid4 ids, deleting the tie-break still passed ~1/6 of runs
    # (review fold: a probabilistic proof is not a proof).
    tie_ids = [f"{c}0000000-0000-0000-0000-000000000000" for c in "abc"]
    for insertion_order in (2, 0, 1):  # insert c, a, b
        run = CalculationRun(
            run_id=tie_ids[insertion_order],
            tenant_id=tenant_a,
            run_type="SENSITIVITY",
            status="COMPLETED",
            initiated_by="seed",
            created_at=_T0,
        )
        db.add(run)
        db.flush()
    tied = tie_ids
    newest = _mint_run(db, tenant_a, "SENSITIVITY", created_at=_T0 + timedelta(hours=1))
    db.commit()

    page = lambda limit, offset: [  # noqa: E731 - local test shorthand
        i["run_id"]
        for i in client.get(
            "/risk/runs",
            params={"limit": limit, "offset": offset},
            headers=_hdr(viewer_a, tenant_a),
        ).json()["items"]
    ]
    assert page(2, 0) == [newest, tied[0]]
    assert page(2, 2) == [tied[1], tied[2]]
    assert page(4, 0) == [newest, *tied]


@pytest.mark.parametrize(
    "params",
    [
        {"run_type": "EXPOSURE_AGGREGATE"},  # the REAL exposure run_type — outside the fence
        {"run_type": "NOPE"},
        {"status": "nope"},
        {"limit": 0},
        {"limit": 201},
        {"offset": -1},
    ],
)
def test_fail_closed_filters_422(ctx, params: dict[str, object]) -> None:
    client, db, tenant_a, _tenant_b, viewer_a, _viewer_b = ctx
    _mint_run(db, tenant_a, "VAR")
    db.commit()
    resp = client.get("/risk/runs", params=params, headers=_hdr(viewer_a, tenant_a))
    assert resp.status_code == 422


def test_entitlement_gating(ctx) -> None:
    client, db, tenant_a, _tenant_b, _viewer_a, _viewer_b = ctx
    nobody = _grant(db, tenant_a)  # a user with NO permissions
    db.commit()
    assert client.get("/risk/runs").status_code == 401  # no principal headers
    assert client.get("/risk/runs", headers=_hdr(nobody, tenant_a)).status_code == 403


def test_no_mutation_methods(ctx) -> None:
    client, _db, tenant_a, _tenant_b, viewer_a, _viewer_b = ctx
    for method in ("post", "put", "patch", "delete"):
        resp = getattr(client, method)("/risk/runs", headers=_hdr(viewer_a, tenant_a))
        assert resp.status_code == 405
