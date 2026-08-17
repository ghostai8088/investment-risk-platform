"""End-to-end tests of the P2-3 exposure endpoints.

SQLite has no RLS (tenant isolation + append-only-trigger proofs are in
``packages/shared-python/tests/test_exposure_pg.py``); here we prove entitlement gating
(deny-by-default, no DB side-effect on denial), the build-in-request run + read round-trip, decimal
serialization, the post-create FAILED response (201 + status='FAILED' + zero rows), pre-create
refusal mapping (422/404/409), and no PUT/PATCH/DELETE.
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

from irp_backend.api.exposure import router as exposure_router
from irp_backend.deps import get_db
from irp_shared.calc.models import CalculationRun
from irp_shared.db.session import make_engine, make_session_factory
from irp_shared.entitlement.bootstrap import SYSTEM_TENANT_ID
from irp_shared.entitlement.models import AppUser, Permission, Role, RolePermission, UserRole
from irp_shared.entitlement.service import Principal
from irp_shared.marketdata import FxRateActor, capture_fx_rate
from irp_shared.models import Base
from irp_shared.portfolio import PortfolioActor, create_portfolio
from irp_shared.position import create_position
from irp_shared.position.service import PositionActor
from irp_shared.reference.instrument import create_instrument
from irp_shared.reference.models import Currency
from irp_shared.reference.service import ReferenceActor
from irp_shared.valuation import create_valuation
from irp_shared.valuation.service import ValuationActor

_PERMS = ("exposure.aggregate.run", "exposure.view")
_VA = datetime(2026, 6, 1, tzinfo=UTC)
_VD = date(2026, 6, 1)


@pytest.fixture
def ctx() -> Iterator[tuple[TestClient, Principal, Session, str]]:
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
    for ccy in ("USD", "EUR"):
        db.add(Currency(tenant_id=SYSTEM_TENANT_ID, code=ccy, name=ccy, valid_from=_VA))
    db.flush()
    pf = create_portfolio(
        db,
        tenant_id=tenant_id,
        code="PF",
        name="pf",
        node_type="ACCOUNT",
        actor=PortfolioActor(actor_id="a"),
    )
    for n, (qty, mark, c) in enumerate([("100", "12.50", "USD"), ("-200", "7.00", "EUR")]):
        inst = create_instrument(
            db,
            tenant_id=tenant_id,
            code=f"I{n}",
            name="i",
            asset_class="EQUITY",
            actor=ReferenceActor(actor_id="a"),
        )
        create_position(
            db,
            portfolio_id=pf.id,
            instrument_id=inst.id,
            acting_tenant=tenant_id,
            actor=PositionActor(actor_id="a"),
            quantity=Decimal(qty),
            valid_from=_VA,
        )
        create_valuation(
            db,
            portfolio_id=pf.id,
            instrument_id=inst.id,
            valuation_date=_VD,
            acting_tenant=tenant_id,
            actor=ValuationActor(actor_id="a"),
            mark_value=Decimal(mark),
            currency_code=c,
            valid_from=_VA,
        )
    capture_fx_rate(
        db,
        base_currency="EUR",
        quote_currency="USD",
        rate_date=_VD,
        rate=Decimal("1.10"),
        acting_tenant=tenant_id,
        actor=FxRateActor(actor_id="a"),
        valid_from=_VA,
    )
    db.commit()
    principal = Principal(user_id=user.id, tenant_id=tenant_id)

    def _override_db() -> Iterator[Session]:
        yield db

    app = FastAPI()
    app.include_router(exposure_router)
    app.dependency_overrides[get_db] = _override_db
    try:
        yield TestClient(app), principal, db, pf.id
    finally:
        db.close()
        engine.dispose()


def _h(p: Principal) -> dict[str, str]:
    return {"X-User-Id": p.user_id, "X-Tenant-Id": p.tenant_id}


def _no_perm(p: Principal) -> dict[str, str]:
    return {"X-User-Id": str(uuid.uuid4()), "X-Tenant-Id": p.tenant_id}


def _run_body(pf: str, **kw) -> dict:  # noqa: ANN003
    return {
        "code_version": "v1",
        "environment_id": "ci",
        "portfolio_id": pf,
        "as_of_valid_at": _VA.isoformat(),
        "base_currency": "USD",
        **kw,
    }


def test_run_and_read_roundtrip(ctx) -> None:  # noqa: ANN001
    client, p, _db, pf = ctx
    resp = client.post("/exposure/runs", json=_run_body(pf), headers=_h(p))
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["status"] == "COMPLETED"
    assert len(body["rows"]) == 2
    total = sum(Decimal(r["exposure_amount"]) for r in body["rows"])
    assert total == Decimal("-290.000000")
    # decimal serialization is numeric-stable strings.
    assert all(Decimal(r["fx_rate"]) for r in body["rows"] if r["mark_currency"] != "USD")

    run_id = body["run_id"]
    get_run = client.get(f"/exposure/runs/{run_id}", headers=_h(p))
    assert get_run.status_code == 200
    assert len(get_run.json()["rows"]) == 2

    one_id = body["rows"][0]["id"]
    get_one = client.get(f"/exposure/{one_id}", headers=_h(p))
    assert get_one.status_code == 200
    assert get_one.json()["exposure_type"] == "MARKET_VALUE"


def test_api1_exposure_entity_reads(ctx) -> None:  # noqa: ANN001
    """API-1 (Class A/exposure): the entity + /latest reads return the run's exposure rows for the
    portfolio (each pinned with calculation_run_id), are silent-empty on a foreign id, require
    portfolio_id on /latest (not shadowed by /{exposure_id}), and deny-by-default."""
    client, p, _db, pf = ctx
    run_id = client.post("/exposure/runs", json=_run_body(pf), headers=_h(p)).json()["run_id"]
    rows = client.get("/exposure", params={"portfolio_id": pf}, headers=_h(p))
    assert rows.status_code == 200
    data = rows.json()
    assert len(data) == 2 and all(r["portfolio_id"] == pf for r in data)
    assert {r["calculation_run_id"] for r in data} == {run_id}
    # Silent-empty on a foreign portfolio.
    assert (
        client.get("/exposure", params={"portfolio_id": str(uuid.uuid4())}, headers=_h(p)).json()
        == []
    )
    # /latest resolves (route not shadowed by /{exposure_id}) + requires portfolio_id.
    latest = client.get("/exposure/latest", params={"portfolio_id": pf}, headers=_h(p))
    assert latest.status_code == 200
    assert {r["calculation_run_id"] for r in latest.json()} == {run_id}
    assert client.get("/exposure/latest", headers=_h(p)).status_code == 422
    # Deny-by-default: no exposure.view.
    assert (
        client.get("/exposure", params={"portfolio_id": pf}, headers=_no_perm(p)).status_code == 403
    )


def test_deny_by_default_no_side_effect(ctx) -> None:  # noqa: ANN001
    client, p, db, pf = ctx
    before = db.execute(select(func.count()).select_from(CalculationRun)).scalar_one()
    resp = client.post("/exposure/runs", json=_run_body(pf), headers=_no_perm(p))
    assert resp.status_code == 403
    after = db.execute(select(func.count()).select_from(CalculationRun)).scalar_one()
    assert after == before  # no run created on a denied request


def test_pre_create_refusal_bad_input_422(ctx) -> None:  # noqa: ANN001
    client, p, db, pf = ctx
    # Missing code_version -> ExposureInputError -> 422; no run created.
    resp = client.post("/exposure/runs", json=_run_body(pf, code_version=""), headers=_h(p))
    assert resp.status_code == 422
    assert db.execute(select(func.count()).select_from(CalculationRun)).scalar_one() == 0


def test_unknown_portfolio_404(ctx) -> None:  # noqa: ANN001
    client, p, _db, _pf = ctx
    resp = client.post("/exposure/runs", json=_run_body(str(uuid.uuid4())), headers=_h(p))
    assert resp.status_code == 404


def test_post_create_failed_returns_201_failed(ctx) -> None:  # noqa: ANN001
    client, p, _db, pf = ctx
    # Build a USD snapshot, then consume it requesting JPY (no JPY legs) -> FAILED.
    built = client.post("/exposure/runs", json=_run_body(pf), headers=_h(p)).json()
    snap_id = built["input_snapshot_id"]
    resp = client.post(
        "/exposure/runs",
        json={
            "code_version": "v1",
            "environment_id": "ci",
            "snapshot_id": snap_id,
            "base_currency": "JPY",
            "scope_node_id": pf,  # STRUCT-3 (DP-7)
        },
        headers=_h(p),
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "FAILED"
    assert body["rows"] == []
    assert body["failure_reason"]
    # The committed FAILED run is READABLE (200, status='FAILED', real metadata) — the auditor's
    # durable refusal evidence — NOT a 404. Run metadata reflects the real run, not a faked one.
    got = client.get(f"/exposure/runs/{body['run_id']}", headers=_h(p))
    assert got.status_code == 200
    g = got.json()
    assert g["status"] == "FAILED"
    assert g["rows"] == []
    assert g["code_version"] == "v1" and g["environment_id"] == "ci"


def test_no_mutating_verbs(ctx) -> None:  # noqa: ANN001
    client, p, _db, _pf = ctx
    rid = str(uuid.uuid4())
    assert client.put(f"/exposure/{rid}", json={}, headers=_h(p)).status_code == 405
    assert client.delete(f"/exposure/{rid}", headers=_h(p)).status_code == 405


def test_view_only_user_cannot_run(ctx) -> None:  # noqa: ANN001
    # A user with exposure.view but NOT exposure.aggregate.run is denied the run (deny-by-default).
    client, p, db, pf = ctx
    tenant = p.tenant_id
    viewer = AppUser(tenant_id=tenant, display_name="V")
    role = Role(tenant_id=tenant, code="vr", name="VR")
    db.add_all([viewer, role])
    db.flush()
    perm = db.execute(select(Permission).where(Permission.code == "exposure.view")).scalar_one()
    db.add(RolePermission(role_id=role.id, permission_id=perm.id))
    db.add(UserRole(tenant_id=tenant, user_id=viewer.id, role_id=role.id))
    db.commit()
    headers = {"X-User-Id": viewer.id, "X-Tenant-Id": tenant}
    assert client.post("/exposure/runs", json=_run_body(pf), headers=headers).status_code == 403


# ---------- STRUCT-1 (REQ-PPM-006): the measure filter over HTTP ----------


def _seed_bond(db: Session, tenant_id: str, pf: str) -> str:
    from irp_shared.reference.instrument_terms import create_instrument_terms

    inst = create_instrument(
        db,
        tenant_id=tenant_id,
        code="B0",
        name="UST 2031",
        asset_class="BOND",
        actor=ReferenceActor(actor_id="a"),
    )
    create_instrument_terms(
        db,
        instrument_id=inst.id,
        acting_tenant=tenant_id,
        actor=ReferenceActor(actor_id="a"),
        valid_from=_VA,
        face_value=Decimal("1000.0000"),
        denomination_currency="USD",
    )
    create_position(
        db,
        portfolio_id=pf,
        instrument_id=inst.id,
        acting_tenant=tenant_id,
        actor=PositionActor(actor_id="a"),
        quantity=Decimal("10"),
        valid_from=_VA,
    )
    create_valuation(
        db,
        portfolio_id=pf,
        instrument_id=inst.id,
        valuation_date=_VD,
        acting_tenant=tenant_id,
        actor=ValuationActor(actor_id="a"),
        mark_value=Decimal("985.40"),
        currency_code="USD",
        valid_from=_VA,
    )
    db.commit()
    return inst.id


def test_exposure_type_filter_over_http(ctx) -> None:  # noqa: ANN001
    client, principal, db, pf = ctx
    inst = _seed_bond(db, principal.tenant_id, pf)
    run = client.post("/exposure/runs", json=_run_body(pf), headers=_h(principal))
    assert run.status_code == 201, run.text
    assert run.json()["status"] == "COMPLETED"

    both = client.get(
        "/exposure", params={"portfolio_id": pf, "instrument_id": inst}, headers=_h(principal)
    )
    assert both.status_code == 200
    assert {r["exposure_type"] for r in both.json()} == {"MARKET_VALUE", "NOTIONAL"}

    only = client.get(
        "/exposure",
        params={"portfolio_id": pf, "instrument_id": inst, "exposure_type": "NOTIONAL"},
        headers=_h(principal),
    )
    assert only.status_code == 200
    assert {r["exposure_type"] for r in only.json()} == {"NOTIONAL"}
    assert only.json()[0]["exposure_amount"] == "10000.000000"

    latest = client.get(
        "/exposure/latest",
        params={"portfolio_id": pf, "exposure_type": "MARKET_VALUE"},
        headers=_h(principal),
    )
    assert latest.status_code == 200
    assert {r["exposure_type"] for r in latest.json()} == {"MARKET_VALUE"}


def test_unknown_exposure_type_is_422_not_empty(ctx) -> None:  # noqa: ANN001
    client, principal, _db, pf = ctx
    for path, params in (
        ("/exposure", {"exposure_type": "GROSS_DELTA"}),
        ("/exposure/latest", {"portfolio_id": pf, "exposure_type": "GROSS_DELTA"}),
    ):
        resp = client.get(path, params=params, headers=_h(principal))
        assert resp.status_code == 422, (path, resp.text)
        assert "unknown exposure_type" in resp.json()["detail"]


# ------- STRUCT-2 (REQ-PPM-007): the ADDITIVE positive case + the mixed-measure refusal -------


def test_summed_exposure_requires_one_measure_and_hand_totals(ctx) -> None:  # noqa: ANN001
    client, principal, db, pf = ctx
    _seed_bond2(db, principal.tenant_id, pf)
    run = client.post("/exposure/runs", json=_run_body(pf), headers=_h(principal))
    assert run.status_code == 201 and run.json()["status"] == "COMPLETED"

    # The mixed-measure refusal, fail-closed BY CONSTRUCTION: no measure named -> 422 (never a
    # silent cross-measure sum; mixture detection over rows would pass vacuously on a
    # single-measure book).
    refused = client.get("/exposure/latest/sum", params={"portfolio_id": pf}, headers=_h(principal))
    assert refused.status_code == 422
    assert "refused, never converted" in refused.json()["detail"]

    # The additive positive case, hand totals: MV = 100x12.50 + (-200x7.00x1.10) + 10x985.40
    # = 1250 - 1540 + 9854 = 9564; NOTIONAL = 10x1000 = 10000.
    mv = client.get(
        "/exposure/latest/sum",
        params={"portfolio_id": pf, "exposure_type": "MARKET_VALUE"},
        headers=_h(principal),
    )
    assert mv.status_code == 200, mv.text
    assert mv.json()["total"] == "9564.000000"
    assert mv.json()["n_rows"] == 3
    notional = client.get(
        "/exposure/latest/sum",
        params={"portfolio_id": pf, "exposure_type": "NOTIONAL"},
        headers=_h(principal),
    )
    assert notional.status_code == 200
    assert notional.json()["total"] == "10000.000000"
    assert notional.json()["calculation_run_id"] == mv.json()["calculation_run_id"]


def _seed_bond2(db: Session, tenant_id: str, pf: str) -> str:
    from irp_shared.reference.instrument_terms import create_instrument_terms

    inst = create_instrument(
        db,
        tenant_id=tenant_id,
        code="B2",
        name="UST 2032",
        asset_class="BOND",
        actor=ReferenceActor(actor_id="a"),
    )
    create_instrument_terms(
        db,
        instrument_id=inst.id,
        acting_tenant=tenant_id,
        actor=ReferenceActor(actor_id="a"),
        valid_from=_VA,
        face_value=Decimal("1000.0000"),
        denomination_currency="USD",
    )
    create_position(
        db,
        portfolio_id=pf,
        instrument_id=inst.id,
        acting_tenant=tenant_id,
        actor=PositionActor(actor_id="a"),
        quantity=Decimal("10"),
        valid_from=_VA,
    )
    create_valuation(
        db,
        portfolio_id=pf,
        instrument_id=inst.id,
        valuation_date=_VD,
        acting_tenant=tenant_id,
        actor=ValuationActor(actor_id="a"),
        mark_value=Decimal("985.40"),
        currency_code="USD",
        valid_from=_VA,
    )
    db.commit()
    return inst.id


def test_summed_exposure_empty_book_is_409_and_fires(ctx) -> None:  # noqa: ANN001
    """P9 for the empty-population refusal (review fold): a valid measure over a book with NO
    completed run of it is 409 — a state of the world, not a caller defect — and the refusal is
    EXECUTED, not declared."""
    client, principal, _db, pf = ctx
    resp = client.get(
        "/exposure/latest/sum",
        params={"portfolio_id": pf, "exposure_type": "NOTIONAL"},
        headers=_h(principal),
    )
    assert resp.status_code == 409, resp.text
    assert "nothing to sum" in resp.json()["detail"]


# ------- STRUCT-3 review folds: the rollup endpoint through HTTP -------


def test_rollup_endpoint_happy_path_and_refusals(ctx) -> None:  # noqa: ANN001
    client, principal, db, pf = ctx
    run = client.post("/exposure/runs", json=_run_body(pf), headers=_h(principal)).json()
    rid = run["run_id"]

    ok = client.get(f"/exposure/runs/{rid}/rollup", params={"node_id": pf}, headers=_h(principal))
    assert ok.status_code == 200, ok.text
    body = ok.json()
    assert {r["exposure_type"] for r in body} == {"MARKET_VALUE"}
    assert body[0]["base_currency"] == "USD"
    # 100x12.50 + (-200x7.00x1.10) = -290, the flat book's own total.
    assert body[0]["total"] == "-290.000000"

    outside = client.get(
        f"/exposure/runs/{rid}/rollup",
        params={"node_id": str(uuid.uuid4())},
        headers=_h(principal),
    )
    assert outside.status_code == 422
    assert "pinned subtree" in outside.json()["detail"]

    unknown_run = client.get(
        f"/exposure/runs/{uuid.uuid4()}/rollup", params={"node_id": pf}, headers=_h(principal)
    )
    assert unknown_run.status_code == 404

    denied = client.get(
        f"/exposure/runs/{rid}/rollup", params={"node_id": pf}, headers=_no_perm(principal)
    )
    assert denied.status_code == 403


def test_rollup_contract_refusal_reaches_http_as_422(ctx, monkeypatch) -> None:  # noqa: ANN001
    """The PPM-007 through-HTTP refusal for the rollup read (review fold): flip the operator and
    the endpoint answers 422, never 500."""
    from irp_shared.aggregation.contracts import (
        AGGREGATION_CONTRACTS,
        OPERATOR_NOT_AGGREGATABLE,
    )

    client, principal, _db, pf = ctx
    run = client.post("/exposure/runs", json=_run_body(pf), headers=_h(principal)).json()
    monkeypatch.setitem(
        AGGREGATION_CONTRACTS["EXPOSURE_AGGREGATE"],
        "exposure_amount",
        OPERATOR_NOT_AGGREGATABLE,
    )
    resp = client.get(
        f"/exposure/runs/{run['run_id']}/rollup", params={"node_id": pf}, headers=_h(principal)
    )
    assert resp.status_code == 422, resp.text
    assert "cannot be summed" in resp.json()["detail"]


# ------- STRUCT-4 (REQ-PPM-010): DP-11 refusals + the visible conversion path over HTTP -------


def _declared_eur_book(db: Session, tenant_id: str) -> str:
    """A declared-EUR fund holding one USD instrument (one reciprocal leg — the translated leg
    count 1 > 0) and one GBP instrument (review fold C11: the TRIANGULATED path over HTTP — no
    GBP/EUR rate exists, so the row carries two legs and a STATED pivot the API must surface)."""
    from irp_shared.entitlement.bootstrap import SYSTEM_TENANT_ID
    from irp_shared.reference.models import Currency

    db.add(Currency(tenant_id=SYSTEM_TENANT_ID, code="GBP", name="GBP", valid_from=_VA))
    db.flush()
    fund = create_portfolio(
        db,
        tenant_id=tenant_id,
        code="FX-EUR-FUND",
        name="fx eur fund",
        node_type="FUND",
        base_currency_code="EUR",
        actor=PortfolioActor(actor_id="a"),
    )
    for code, qty, mark, ccy in (("FX-I1", "10", "11.00", "USD"), ("FX-I2", "5", "8.00", "GBP")):
        inst = create_instrument(
            db,
            tenant_id=tenant_id,
            code=code,
            name="i",
            asset_class="EQUITY",
            actor=ReferenceActor(actor_id="a"),
        )
        create_position(
            db,
            portfolio_id=fund.id,
            instrument_id=inst.id,
            acting_tenant=tenant_id,
            actor=PositionActor(actor_id="a"),
            quantity=Decimal(qty),
            valid_from=_VA,
        )
        create_valuation(
            db,
            portfolio_id=fund.id,
            instrument_id=inst.id,
            valuation_date=_VD,
            acting_tenant=tenant_id,
            actor=ValuationActor(actor_id="a"),
            mark_value=Decimal(mark),
            currency_code=ccy,
            valid_from=_VA,
        )
    capture_fx_rate(
        db,
        base_currency="GBP",
        quote_currency="USD",
        rate_date=_VD,
        rate=Decimal("1.25"),
        acting_tenant=tenant_id,
        actor=FxRateActor(actor_id="a"),
        valid_from=_VA,
    )
    db.commit()
    return fund.id


def test_undeclared_root_refusal_is_422_with_its_own_detail(ctx) -> None:  # noqa: ANN001
    """DP-11 through the real entry point: the fixture book declares NOTHING, so omitting
    base_currency answers the subclass's OWN 422 detail (the API-2 error-map lesson) — the
    pre-STRUCT-4 behavior was a silent USD run. Zero runs committed (negative control)."""
    client, principal, _db, pf = ctx
    body = _run_body(pf)
    del body["base_currency"]
    resp = client.post("/exposure/runs", json=body, headers=_h(principal))
    assert resp.status_code == 422, resp.text
    assert resp.json()["detail"] == "no reporting currency declared on the scope or any ancestor"
    runs = client.get("/exposure/runs", headers=_h(principal)).json()["items"]
    assert runs == []


def test_conflict_override_refusal_is_422_over_http(ctx) -> None:  # noqa: ANN001
    """The override clause through the real entry point: an explicit base contradicting the
    node's declared EUR on a v3 node-scoped consume is refused with its own detail; the
    declaration-default consume (no base at all) COMPLETES in EUR (positive control)."""
    client, principal, db, _pf = ctx
    fund = _declared_eur_book(db, principal.tenant_id)
    body = _run_body(fund)
    del body["base_currency"]  # DP-11: the declaration IS the default now
    built = client.post("/exposure/runs", json=body, headers=_h(principal)).json()
    assert built["status"] == "COMPLETED"
    assert {r["base_currency"] for r in built["rows"]} == {"EUR"}

    conflict = client.post(
        "/exposure/runs",
        json={
            "code_version": "v1",
            "environment_id": "ci",
            "snapshot_id": built["input_snapshot_id"],
            "scope_node_id": fund,
            "base_currency": "USD",
        },
        headers=_h(principal),
    )
    assert conflict.status_code == 422, conflict.text
    assert (
        conflict.json()["detail"]
        == "base_currency contradicts the node's declared reporting currency"
    )


def test_conversion_path_is_visible_over_http(ctx) -> None:  # noqa: ANN001
    """The read-endpoints-without-screens gap's API half: the run rows carry fx_legs + the DP-12
    fx_pivot, and the rollup carries the translation evidence. The translated-leg count is
    asserted > 0 BEFORE any leg assertion (P18 clause 1)."""
    client, principal, db, _pf = ctx
    fund = _declared_eur_book(db, principal.tenant_id)
    body = _run_body(fund)
    del body["base_currency"]
    built = client.post("/exposure/runs", json=body, headers=_h(principal)).json()

    translated = [r for r in built["rows"] if r["fx_legs"]]
    assert len(translated) > 0  # P18: this book actually translates
    # USD -> EUR with only EUR/USD published = ONE reciprocal leg; no pivot on a 1-leg path.
    one_leg = [r for r in translated if len(r["fx_legs"]) == 1]
    assert [leg["direction"] for leg in one_leg[0]["fx_legs"]] == ["reciprocal"]
    assert one_leg[0]["fx_pivot"] is None
    # Review fold C11: the TRIANGULATED row over HTTP — the fx_pivot wiring (derive_pivot at
    # _row_out) must be load-bearing through the real endpoint, and the stored legs STATE the
    # pivot (DP-12). Deleting the API wiring or the stated key goes red HERE.
    two_leg = [r for r in translated if len(r["fx_legs"]) == 2]
    assert len(two_leg) == 1  # the GBP row: GBP->USD direct, then USD->EUR reciprocal
    assert two_leg[0]["fx_pivot"] == "USD"
    assert [leg["pivot"] for leg in two_leg[0]["fx_legs"]] == ["USD", "USD"]

    rollup = client.get(
        f"/exposure/runs/{built['run_id']}/rollup",
        params={"node_id": fund},
        headers=_h(principal),
    ).json()
    row = rollup[0]
    # The fund's own declared EUR: identity translation, exact, with the evidence fields shaped.
    assert (row["reporting_currency"], row["translated_currency"]) == ("EUR", "EUR")
    assert row["translated_total"] == row["total"]
    assert row["translation_fx_rate"] == "1"
    assert (row["translation_legs"], row["translation_pivot"], row["missing_fx"]) == (
        [],
        None,
        None,
    )
