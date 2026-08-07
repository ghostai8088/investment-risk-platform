"""RPT-2 report endpoints — the guard census, the hostile-caller battery, and the I1/I2 proofs.

Every refusal here fires against the LIKELY hostile input (a REAL foreign-owned object, never a
random UUID — the LIM-2 lesson), and the generate refusals assert the ABSENCE of all three
artifacts a half-completed generation would leave (the RPT-1 audit's N1 widening).
"""

from __future__ import annotations

import hashlib
import uuid
from collections.abc import Iterator
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from sqlalchemy import event, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from irp_backend.api.reports import router
from irp_backend.deps import get_db
from irp_shared.calc.models import CalculationRun, RunStatus
from irp_shared.calc.service import create_run, update_run_status
from irp_shared.concentration.bootstrap import (
    CONCENTRATION_METHODOLOGY_REF,
    CONCENTRATION_MODEL_CODE,
)
from irp_shared.concentration.events import RUN_TYPE_CONCENTRATION
from irp_shared.concentration.models import ConcentrationResult
from irp_shared.db.session import make_engine, make_session_factory
from irp_shared.entitlement.models import (
    AppUser,
    Permission,
    Role,
    RolePermission,
    UserRole,
)
from irp_shared.model.models import Model, ModelVersion
from irp_shared.models import Base
from irp_shared.portfolio.models import Portfolio
from irp_shared.report.models import RUN_TYPE_REPORT, ReportGeneration
from irp_shared.snapshot.models import DatasetSnapshot

_AS_OF = date(2026, 6, 30)
_NOW = datetime(2026, 7, 1, 12, 0, tzinfo=UTC)


# --- the P11 route census -------------------------------------------------------------------------


def _permission_codes(route: APIRoute) -> set[str]:
    codes: set[str] = set()
    for dep in route.dependant.dependencies:
        fn: Any = dep.call
        if fn is None or getattr(fn, "__name__", "") != "_dependency" or fn.__closure__ is None:
            continue
        for cell in fn.__closure__:
            if isinstance(cell.cell_contents, str):
                codes.add(cell.cell_contents)
    return codes


def _report_routes() -> dict[tuple[str, str], set[str]]:
    out: dict[tuple[str, str], set[str]] = {}
    for route in router.routes:
        if isinstance(route, APIRoute):
            for method in route.methods:
                if method != "HEAD":
                    out[(method, route.path)] = _permission_codes(route)
    return out


def test_every_report_route_is_guarded_by_the_ratified_code() -> None:
    """The EXACT route→code census (a new unguarded or re-guarded route fails by name)."""
    assert _report_routes() == {
        ("POST", "/reports"): {"report.generate"},
        ("GET", "/reports"): {"report.view"},
        ("GET", "/reports/{report_id}"): {"report.view"},
        ("GET", "/reports/{report_id}/html"): {"report.view"},
    }


def test_the_write_route_demands_the_generate_code_not_the_view_code() -> None:
    """The verb-class split by name: POST must demand the maker code and must NOT be satisfiable
    by the auditor-held view code (the REF-1 wrong-guard class)."""
    codes = _report_routes()[("POST", "/reports")]
    assert "report.generate" in codes
    assert "report.view" not in codes


# --- the e2e harness ------------------------------------------------------------------------------


def _grant(db: Session, tenant_id: str, *perms: str) -> str:
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


def _seed_portfolio(db: Session, tenant: str) -> str:
    pf = Portfolio(
        tenant_id=tenant,
        code=f"PF-{uuid.uuid4().hex[:8]}",
        name="Report endpoint book",
        node_type="ACCOUNT",
        status="ACTIVE",
        record_version=1,
    )
    db.add(pf)
    db.flush()
    return str(pf.id)


def _seed_concentration_run(db: Session, tenant: str, portfolio_id: str) -> str:
    """A COMPLETED concentration run with real rows AND a real registered model version — the
    provenance path resolves from the row, so a fake version id is a refusal, not a fixture."""
    model = db.execute(
        select(Model).where(Model.tenant_id == tenant, Model.code == CONCENTRATION_MODEL_CODE)
    ).scalar_one_or_none()
    if model is None:
        model = Model(
            tenant_id=tenant,
            code=CONCENTRATION_MODEL_CODE,
            name="seeded",
            model_type="RISK",
            is_active=True,
        )
        db.add(model)
        db.flush()
    version = db.execute(
        select(ModelVersion).where(
            ModelVersion.tenant_id == tenant,
            ModelVersion.model_id == str(model.id),
            ModelVersion.version_label == "v1",
        )
    ).scalar_one_or_none()
    if version is None:
        version = ModelVersion(
            tenant_id=tenant,
            model_id=str(model.id),
            version_label="v1",
            methodology_ref=CONCENTRATION_METHODOLOGY_REF,
            status="REGISTERED",
        )
        db.add(version)
        db.flush()
    snap = DatasetSnapshot(
        tenant_id=tenant,
        label="src",
        purpose="CONCENTRATION_INPUT",
        as_of_valid_at=_NOW,
        as_of_known_at=_NOW,
        as_of_valuation_date=_AS_OF,
        binding_predicate_version="v1",
        component_count=0,
        manifest_hash="h",
    )
    db.add(snap)
    db.flush()
    run = create_run(
        db,
        tenant_id=tenant,
        run_type=RUN_TYPE_CONCENTRATION,
        initiated_by="seed",
        input_snapshot_id=str(snap.id),
        scope_portfolio_id=portfolio_id,
    )
    db.flush()
    db.add(
        ConcentrationResult(
            tenant_id=tenant,
            calculation_run_id=run.run_id,
            input_snapshot_id=snap.id,
            model_version_id=str(version.id),
            portfolio_id=portfolio_id,
            row_kind="SUMMARY",
            dimension_kind="SECTOR_INDUSTRY",
            bucket_code="__SUMMARY__",
            metric_type="MAX_SHARE_SECTOR_INDUSTRY",
            metric_value=Decimal("0.412300"),
            share_invested_long=None,
            scheme_id=str(uuid.uuid4()),
            basis="NOT_APPLICABLE",
            gross_amount=Decimal("1000.000000"),
            long_amount=Decimal("1000.000000"),
            short_amount=Decimal("0.000000"),
            net_amount=Decimal("1000.000000"),
            denominator_basis="INVESTED_LONG",
        )
    )
    update_run_status(db, run, RunStatus.COMPLETED, actor_id="seed")
    db.flush()
    return str(run.run_id)


@pytest.fixture
def ctx() -> Iterator[tuple[TestClient, Session, dict[str, str]]]:
    """A two-tenant world with FK enforcement ON (the RPT-1 lesson: the shared engine's default-off
    pragma let eighteen tests bind a portfolio that did not exist)."""
    engine = make_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def _fk(dbapi_conn: object, _rec: object) -> None:
        cur = dbapi_conn.cursor()  # type: ignore[attr-defined]
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

    Base.metadata.create_all(engine)
    db = make_session_factory(engine)()

    tenant_a, tenant_b = str(uuid.uuid4()), str(uuid.uuid4())
    ids = {
        "tenant_a": tenant_a,
        "tenant_b": tenant_b,
        "maker_a": _grant(db, tenant_a, "report.generate", "report.view"),
        "viewer_a": _grant(db, tenant_a, "report.view"),
        "maker_b": _grant(db, tenant_b, "report.generate", "report.view"),
        "nobody_a": _grant(db, tenant_a, "exposure.view"),
    }
    ids["pf_a"] = _seed_portfolio(db, tenant_a)
    ids["pf_b"] = _seed_portfolio(db, tenant_b)
    ids["run_a"] = _seed_concentration_run(db, tenant_a, ids["pf_a"])
    ids["run_b"] = _seed_concentration_run(db, tenant_b, ids["pf_b"])
    db.commit()

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_db] = lambda: db
    client = TestClient(app)
    try:
        yield client, db, ids
    finally:
        db.close()
        engine.dispose()


def _hdr(user_id: str, tenant_id: str) -> dict[str, str]:
    return {"X-User-Id": user_id, "X-Tenant-Id": tenant_id}


def _generate_payload(ids: dict[str, str]) -> dict[str, Any]:
    return {
        "portfolio_id": ids["pf_a"],
        "as_of_date": _AS_OF.isoformat(),
        "family_runs": {"concentration": ids["run_a"]},
    }


def _assert_nothing_persisted(db: Session) -> None:
    assert db.query(ReportGeneration).count() == 0
    runs = (
        db.execute(select(CalculationRun).where(CalculationRun.run_type == RUN_TYPE_REPORT))
        .scalars()
        .all()
    )
    assert not runs, "a refusal left a REPORT run behind"
    snaps = (
        db.execute(select(DatasetSnapshot).where(DatasetSnapshot.purpose == "REPORT_INPUT"))
        .scalars()
        .all()
    )
    assert not snaps, "a refusal left a REPORT_INPUT snapshot behind"


# --- the happy path, and I1 -----------------------------------------------------------------------


def test_generate_then_fetch_html_and_the_BYTES_HASH_TO_THE_STORED_HASH(ctx) -> None:  # noqa: ANN001
    """I1 end to end over HTTP: the HTML endpoint re-renders from the pin, and the bytes it serves
    hash to exactly the content_hash the POST returned."""
    client, _db, ids = ctx
    r = client.post(
        "/reports", json=_generate_payload(ids), headers=_hdr(ids["maker_a"], ids["tenant_a"])
    )
    assert r.status_code == 201, r.text
    meta = r.json()
    assert meta["portfolio_id"] == ids["pf_a"]
    assert len(meta["content_hash"]) == 64

    h = client.get(f"/reports/{meta['id']}/html", headers=_hdr(ids["viewer_a"], ids["tenant_a"]))
    assert h.status_code == 200
    assert (
        hashlib.sha256(h.content).hexdigest() == meta["content_hash"]
    ), "the served bytes do not hash to the stored identity — the read is not a reproduction"
    assert "0.412300" in h.text  # the governed number, verbatim


def test_list_and_get_return_the_generated_report(ctx) -> None:  # noqa: ANN001
    client, _db, ids = ctx
    r = client.post(
        "/reports", json=_generate_payload(ids), headers=_hdr(ids["maker_a"], ids["tenant_a"])
    )
    rid = r.json()["id"]
    listed = client.get("/reports", headers=_hdr(ids["viewer_a"], ids["tenant_a"]))
    assert listed.status_code == 200
    assert [i["id"] for i in listed.json()["items"]] == [rid]
    got = client.get(f"/reports/{rid}", headers=_hdr(ids["viewer_a"], ids["tenant_a"]))
    assert got.status_code == 200
    assert got.json()["content_hash"] == r.json()["content_hash"]


# --- I2: the wire cannot assert evidence time -----------------------------------------------------


def test_a_caller_supplied_generated_at_is_REFUSED_not_ignored(ctx) -> None:  # noqa: ANN001
    """extra='forbid' is the fence: an ignored field would be indistinguishable, to the caller,
    from an honored one. Nothing may be persisted on the refusal."""
    client, db, ids = ctx
    payload = _generate_payload(ids) | {"generated_at": "1999-01-01T00:00:00+00:00"}
    r = client.post("/reports", json=payload, headers=_hdr(ids["maker_a"], ids["tenant_a"]))
    assert r.status_code == 422
    _assert_nothing_persisted(db)


def test_generated_at_is_SERVER_stamped(ctx) -> None:  # noqa: ANN001
    client, _db, ids = ctx
    before = datetime.now(UTC)
    r = client.post(
        "/reports", json=_generate_payload(ids), headers=_hdr(ids["maker_a"], ids["tenant_a"])
    )
    after = datetime.now(UTC)
    stamped = datetime.fromisoformat(r.json()["generated_at"])
    assert before <= stamped <= after, "generated_at did not come from the server clock"


# --- I3: entitlement + tenant fences, hostile inputs ----------------------------------------------


def test_the_view_code_CANNOT_generate(ctx) -> None:  # noqa: ANN001
    """The auditor-held code must not reach the write verb (the verb-class split, live)."""
    client, db, ids = ctx
    r = client.post(
        "/reports", json=_generate_payload(ids), headers=_hdr(ids["viewer_a"], ids["tenant_a"])
    )
    assert r.status_code == 403
    _assert_nothing_persisted(db)


def test_an_unrelated_permission_is_DENIED_everywhere(ctx) -> None:  # noqa: ANN001
    client, _db, ids = ctx
    hdr = _hdr(ids["nobody_a"], ids["tenant_a"])
    assert client.get("/reports", headers=hdr).status_code == 403
    assert client.post("/reports", json=_generate_payload(ids), headers=hdr).status_code == 403


def test_no_principal_is_401(ctx) -> None:  # noqa: ANN001
    client, _db, _ids = ctx
    assert client.get("/reports").status_code == 401


def test_a_FOREIGN_portfolio_is_refused_with_NOTHING_persisted(ctx) -> None:  # noqa: ANN001
    """The REAL foreign-owned object, not a random UUID: tenant A names tenant B's actual book."""
    client, db, ids = ctx
    payload = _generate_payload(ids) | {"portfolio_id": ids["pf_b"]}
    r = client.post("/reports", json=payload, headers=_hdr(ids["maker_a"], ids["tenant_a"]))
    assert r.status_code == 404, "a foreign portfolio must 404 (not 403 — that would disclose it)"
    _assert_nothing_persisted(db)


def test_a_FOREIGN_run_is_refused_with_NOTHING_persisted(ctx) -> None:  # noqa: ANN001
    """Tenant A's own portfolio but tenant B's REAL run — the binder's cross-tenant refusal,
    reached over HTTP."""
    client, db, ids = ctx
    payload = _generate_payload(ids) | {"family_runs": {"concentration": ids["run_b"]}}
    r = client.post("/reports", json=payload, headers=_hdr(ids["maker_a"], ids["tenant_a"]))
    assert r.status_code == 422
    _assert_nothing_persisted(db)


def test_a_FOREIGN_report_read_is_the_same_404_as_a_missing_one(ctx) -> None:  # noqa: ANN001
    client, _db, ids = ctx
    r = client.post(
        "/reports", json=_generate_payload(ids), headers=_hdr(ids["maker_a"], ids["tenant_a"])
    )
    rid = r.json()["id"]
    foreign = client.get(f"/reports/{rid}", headers=_hdr(ids["maker_b"], ids["tenant_b"]))
    missing = client.get(f"/reports/{uuid.uuid4()}", headers=_hdr(ids["maker_b"], ids["tenant_b"]))
    assert foreign.status_code == 404
    assert missing.status_code == 404
    assert (
        foreign.json() == missing.json()
    ), "a foreign id must be INDISTINGUISHABLE from a missing one"
    html = client.get(f"/reports/{rid}/html", headers=_hdr(ids["maker_b"], ids["tenant_b"]))
    assert html.status_code == 404


def test_mutation_methods_are_405(ctx) -> None:  # noqa: ANN001
    """ENT-072 is append-only; the surface must not even route a mutation."""
    client, _db, ids = ctx
    r = client.post(
        "/reports", json=_generate_payload(ids), headers=_hdr(ids["maker_a"], ids["tenant_a"])
    )
    rid = r.json()["id"]
    hdr = _hdr(ids["maker_a"], ids["tenant_a"])
    assert client.put(f"/reports/{rid}", json={}, headers=hdr).status_code == 405
    assert client.patch(f"/reports/{rid}", json={}, headers=hdr).status_code == 405
    assert client.delete(f"/reports/{rid}", headers=hdr).status_code == 405


# --- I1's refusal arm: the tampered hash ----------------------------------------------------------


def test_a_TAMPERED_stored_hash_makes_the_html_read_a_500_not_a_4xx(ctx) -> None:  # noqa: ANN001
    """The platform failing its own BR-9 claim is a SERVER failure. Raw SQL bypasses the ORM
    append-only listeners on purpose — the unit engine has no DB trigger, and what is under test
    is the ENDPOINT's honesty, not the storage fence (that is test_report_pg's job)."""
    from sqlalchemy import text

    client, db, ids = ctx
    r = client.post(
        "/reports", json=_generate_payload(ids), headers=_hdr(ids["maker_a"], ids["tenant_a"])
    )
    rid = r.json()["id"]
    db.execute(
        text("UPDATE report_generation SET content_hash = :h WHERE id = :i"),
        {"h": "0" * 64, "i": rid},
    )
    db.commit()
    resp = client.get(f"/reports/{rid}/html", headers=_hdr(ids["viewer_a"], ids["tenant_a"]))
    assert resp.status_code == 500
    assert "identity" in resp.json()["detail"]


# --- the fences the RPT-2 review found MUTATION-BLIND ---------------------------------------------


def test_the_LIST_route_is_tenant_fenced(ctx) -> None:  # noqa: ANN001
    """The review's finding: deleting `tenant_id` from the list query left all 18 tests green.

    Every other test seeded reports for ONE tenant only, so a list that returned every tenant's
    rows was indistinguishable from a correctly fenced one. The discriminating fixture is two
    tenants that BOTH have a report — then an unfenced list returns two rows where one is correct.
    """
    client, _db, ids = ctx
    a = client.post(
        "/reports", json=_generate_payload(ids), headers=_hdr(ids["maker_a"], ids["tenant_a"])
    )
    assert a.status_code == 201
    b_payload = {
        "portfolio_id": ids["pf_b"],
        "as_of_date": _AS_OF.isoformat(),
        "family_runs": {"concentration": ids["run_b"]},
    }
    b = client.post("/reports", json=b_payload, headers=_hdr(ids["maker_b"], ids["tenant_b"]))
    assert b.status_code == 201, b.text

    seen_a = client.get("/reports", headers=_hdr(ids["viewer_a"], ids["tenant_a"])).json()["items"]
    assert [i["id"] for i in seen_a] == [
        a.json()["id"]
    ], "tenant A's list is not fenced — it can see another tenant's governed report"
    seen_b = client.get("/reports", headers=_hdr(ids["maker_b"], ids["tenant_b"])).json()["items"]
    assert [i["id"] for i in seen_b] == [b.json()["id"]]


def test_a_MALFORMED_id_is_a_422_not_a_500(ctx) -> None:  # noqa: ANN001
    """The review's BLOCKING finding: the ids reach a PostgreSQL `uuid` column, where a malformed
    value raises `invalid input syntax for type uuid` — a 500. SQLite stores GUID as CHAR(36),
    matches nothing, and proved a tidy 404 production never exhibits. Typing the params as
    `uuid.UUID` makes FastAPI refuse BEFORE any query, so both engines agree."""
    client, _db, ids = ctx
    hdr = _hdr(ids["viewer_a"], ids["tenant_a"])
    assert client.get("/reports/not-a-uuid", headers=hdr).status_code == 422
    assert client.get("/reports/not-a-uuid/html", headers=hdr).status_code == 422
    assert (
        client.get("/reports", params={"portfolio_id": "not-a-uuid"}, headers=hdr).status_code
        == 422
    )
    bad = _generate_payload(ids) | {"portfolio_id": "not-a-uuid"}
    assert (
        client.post("/reports", json=bad, headers=_hdr(ids["maker_a"], ids["tenant_a"])).status_code
        == 422
    )


def test_a_run_computed_for_ANOTHER_PORTFOLIO_cannot_be_attributed_to_this_one(ctx) -> None:  # noqa: ANN001
    """The review's HIGH finding, and the one that mattered most.

    Both halves were individually correct — the portfolio was tenant-fenced, each run was
    tenant-and-type fenced — and NOTHING related them. A `report.generate` holder with one
    legitimate portfolio and one legitimate run could mint an IA append-only, byte-identically
    reproducible board artifact headed with book A's name carrying book B's numbers, complete with
    a real hash, a real snapshot and a real audit trail. Same tenant throughout: no cross-tenant
    fence would ever have fired.
    """
    client, db, ids = ctx
    other_pf = _seed_portfolio(db, ids["tenant_a"])
    other_run = _seed_concentration_run(db, ids["tenant_a"], other_pf)
    db.commit()

    payload = {
        "portfolio_id": ids["pf_a"],  # the book the report will NAME
        "as_of_date": _AS_OF.isoformat(),
        "family_runs": {"concentration": other_run},  # numbers from a DIFFERENT book
    }
    r = client.post("/reports", json=payload, headers=_hdr(ids["maker_a"], ids["tenant_a"]))
    assert r.status_code == 422, "a report attributed another book's numbers to this one"
    # The HTTP detail stays OPAQUE by house pattern (the error map's generic string); the specific
    # refusal message is asserted at the layer that raises it, in test_report_generation.py.
    _assert_nothing_persisted(db)


def test_the_artifact_carries_its_OWN_boundary_headers(ctx) -> None:  # noqa: ANN001
    """The review's HIGH finding: the FE's `sandbox=""` iframe protects the APP, and does nothing
    for a viewer who navigates directly to the artifact URL — which nginx proxies on the SPA's own
    origin, where the same bytes would run with full script capability and read
    `sessionStorage["irp.session"]` (the OIDC bearer token).

    So the RESPONSE carries its own restriction. Added with a test because the first version of
    this fix shipped WITHOUT one and mutation G5 (drop the headers) killed nothing — a security
    header nobody asserts is a comment.
    """
    client, _db, ids = ctx
    r = client.post(
        "/reports", json=_generate_payload(ids), headers=_hdr(ids["maker_a"], ids["tenant_a"])
    )
    html = client.get(
        f"/reports/{r.json()['id']}/html", headers=_hdr(ids["viewer_a"], ids["tenant_a"])
    )
    assert html.status_code == 200
    csp = html.headers.get("content-security-policy", "")
    assert "sandbox" in csp, "no CSP sandbox — a directly-navigated artifact runs in the app origin"
    assert "default-src 'none'" in csp
    assert (
        "script-src" not in csp
    ), "an explicit script-src would widen what default-src 'none' shut"
    assert html.headers.get("x-content-type-options") == "nosniff"
    assert html.headers.get("referrer-policy") == "no-referrer"
