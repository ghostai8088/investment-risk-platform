"""End-to-end tests of the reference endpoints (currency / calendar / rating_scale).

SQLite has no RLS, so cross-tenant isolation / hybrid-read asymmetry are proven in
``packages/shared-python/tests/test_reference_pg.py``; here we prove entitlement gating
(deny-by-default per entity), server-side tenant stamping (forged body ignored), children written
via the parent POST, indistinguishable 404 / 422, and audit emission over real HTTP.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from irp_backend.api.reference import router as reference_router
from irp_backend.deps import get_db
from irp_shared.audit.models import AuditEvent
from irp_shared.db.session import make_engine, make_session_factory
from irp_shared.entitlement.models import AppUser, Permission, Role, RolePermission, UserRole
from irp_shared.entitlement.service import Principal
from irp_shared.models import Base
from irp_shared.reference.models import Calendar, CalendarHoliday, Currency, RatingGrade

#: The reference permissions the test principal holds (full steward set).
_PERMS = (
    "reference.currency.view",
    "reference.currency.edit",
    "reference.calendar.view",
    "reference.calendar.edit",
    "reference.rating_scale.view",
    "reference.rating_scale.edit",
)


@pytest.fixture
def ctx() -> Iterator[tuple[TestClient, Principal, Session]]:
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
    db.commit()
    principal = Principal(user_id=user.id, tenant_id=tenant_id)

    def _override_db() -> Iterator[Session]:
        yield db

    app = FastAPI()
    app.include_router(reference_router)
    app.dependency_overrides[get_db] = _override_db
    try:
        yield TestClient(app), principal, db
    finally:
        db.close()
        engine.dispose()


def _headers(p: Principal) -> dict[str, str]:
    return {"X-User-Id": p.user_id, "X-Tenant-Id": p.tenant_id}


def _no_perm_headers(p: Principal) -> dict[str, str]:
    return {"X-User-Id": str(uuid.uuid4()), "X-Tenant-Id": p.tenant_id}


# --- currency ---


def test_create_currency_201_stamps_tenant_and_audits(
    ctx: tuple[TestClient, Principal, Session],
) -> None:
    client, principal, db = ctx
    resp = client.post(
        "/reference/currencies",
        json={"code": "USD", "name": "US Dollar", "minor_units": 2, "tenant_id": str(uuid.uuid4())},
        headers=_headers(principal),
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["code"] == "USD" and body["minor_units"] == 2
    row = db.execute(select(Currency)).scalar_one()
    # The forged body tenant_id is ignored; the row carries the principal's tenant.
    assert row.tenant_id == principal.tenant_id and row.id == body["id"]
    assert (
        db.execute(
            select(func.count())
            .select_from(AuditEvent)
            .where(AuditEvent.event_type == "REFERENCE.CREATE")
        ).scalar_one()
        == 1
    )


def test_create_currency_without_edit_403(ctx: tuple[TestClient, Principal, Session]) -> None:
    client, principal, db = ctx
    resp = client.post(
        "/reference/currencies",
        json={"code": "USD", "name": "US Dollar"},
        headers=_no_perm_headers(principal),
    )
    assert resp.status_code == 403
    # Deny-by-default short-circuits BEFORE any governed write: nothing persisted, nothing audited.
    assert db.execute(select(func.count()).select_from(Currency)).scalar_one() == 0
    assert (
        db.execute(
            select(func.count())
            .select_from(AuditEvent)
            .where(AuditEvent.event_type == "REFERENCE.CREATE")
        ).scalar_one()
        == 0
    )


def test_list_currencies_requires_view(ctx: tuple[TestClient, Principal, Session]) -> None:
    client, principal, _ = ctx
    assert (
        client.get("/reference/currencies", headers=_no_perm_headers(principal)).status_code == 403
    )


def test_get_currency_404_and_422(ctx: tuple[TestClient, Principal, Session]) -> None:
    client, principal, _ = ctx
    assert (
        client.get(f"/reference/currencies/{uuid.uuid4()}", headers=_headers(principal)).status_code
        == 404
    )
    assert (
        client.get("/reference/currencies/not-a-uuid", headers=_headers(principal)).status_code
        == 422
    )


def test_list_and_get_currency_roundtrip(ctx: tuple[TestClient, Principal, Session]) -> None:
    client, principal, _ = ctx
    created = client.post(
        "/reference/currencies",
        json={"code": "EUR", "name": "Euro"},
        headers=_headers(principal),
    ).json()
    listing = client.get("/reference/currencies", headers=_headers(principal))
    assert listing.status_code == 200 and any(c["code"] == "EUR" for c in listing.json())
    detail = client.get(f"/reference/currencies/{created['id']}", headers=_headers(principal))
    assert detail.status_code == 200 and detail.json()["code"] == "EUR"


# --- calendar (children via parent write) ---


def test_create_calendar_with_holidays_via_parent(
    ctx: tuple[TestClient, Principal, Session],
) -> None:
    client, principal, db = ctx
    resp = client.post(
        "/reference/calendars",
        json={
            "code": "XNYS",
            "name": "NYSE",
            "mic": "XNYS",
            "holidays": [
                {"holiday_date": "2026-01-01", "name": "New Year"},
                {"holiday_date": "2026-12-25", "name": "Christmas"},
            ],
        },
        headers=_headers(principal),
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert len(body["holidays"]) == 2
    # Children persisted under the parent's tenant; exactly one REFERENCE.CREATE (children fold in).
    assert db.execute(select(func.count()).select_from(CalendarHoliday)).scalar_one() == 2
    assert (
        db.execute(
            select(func.count())
            .select_from(AuditEvent)
            .where(AuditEvent.event_type == "REFERENCE.CREATE")
        ).scalar_one()
        == 1
    )
    cal = db.execute(select(Calendar)).scalar_one()
    detail = client.get(f"/reference/calendars/{cal.id}", headers=_headers(principal))
    assert detail.status_code == 200 and len(detail.json()["holidays"]) == 2


def test_create_calendar_requires_edit(ctx: tuple[TestClient, Principal, Session]) -> None:
    client, principal, _ = ctx
    resp = client.post(
        "/reference/calendars",
        json={"code": "X", "name": "X"},
        headers=_no_perm_headers(principal),
    )
    assert resp.status_code == 403


# --- DEP-1 (OQ-W15P-5): the holiday refresh route — the F3 gap, closed and pinned ---


def _make_calendar(client: TestClient, principal: Principal) -> str:
    resp = client.post(
        "/reference/calendars",
        json={"code": "XLON", "name": "LSE", "mic": "XLON", "holidays": []},
        headers=_headers(principal),
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def test_the_horizon_is_reachable_through_the_API_at_all(
    ctx: tuple[TestClient, Principal, Session],
) -> None:
    """The F3 gap itself. Before DEP-1 nothing could set ``holidays_complete_through`` over HTTP,
    so a calendar created through this API could never reach a state where a BUSINESS_MONTH_END
    schedule ticks — it refused at every tick, fail-closed and unfixable from outside.

    The `is None` assertion on the freshly created calendar is the half that matters: it pins that
    the create path still does NOT set a horizon, so this route is genuinely the only way there.
    """
    client, principal, _ = ctx
    cal_id = _make_calendar(client, principal)
    before = client.get(f"/reference/calendars/{cal_id}", headers=_headers(principal))
    assert before.json()["holidays_complete_through"] is None

    resp = client.post(
        f"/reference/calendars/{cal_id}/holidays",
        json={
            "holidays": [{"holiday_date": "2027-01-01", "name": "New Year"}],
            "complete_through": "2027-12-31",
        },
        headers=_headers(principal),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["holidays_complete_through"] == "2027-12-31"
    assert len(resp.json()["holidays"]) == 1


def test_a_REGRESSING_horizon_is_REFUSED_422(ctx: tuple[TestClient, Principal, Session]) -> None:
    """OQ-CAL-1-4's forward-only rule, made to FIRE through the route (P9).

    Shrinking a declared horizon would silently re-open the coverage gate's refusal window behind
    schedules that already trust it — so it is refused, and refused as a governed 422 rather than
    escaping as a 500.
    """
    client, principal, _ = ctx
    cal_id = _make_calendar(client, principal)
    client.post(
        f"/reference/calendars/{cal_id}/holidays",
        json={"holidays": [], "complete_through": "2030-12-31"},
        headers=_headers(principal),
    )
    resp = client.post(
        f"/reference/calendars/{cal_id}/holidays",
        json={"holidays": [], "complete_through": "2029-12-31"},
        headers=_headers(principal),
    )
    assert resp.status_code == 422, resp.text
    assert "forward-only" in resp.json()["detail"]
    # The refusal left the declared horizon UNMOVED — a refusal that half-applied would be worse
    # than none, because the schedule's refusal window would have silently widened.
    after = client.get(f"/reference/calendars/{cal_id}", headers=_headers(principal))
    assert after.json()["holidays_complete_through"] == "2030-12-31"


def test_the_refresh_is_ADD_ONLY_and_idempotent(
    ctx: tuple[TestClient, Principal, Session],
) -> None:
    """Removal is structurally impossible through this route: re-posting a SUBSET does not delete
    the dates omitted from it. That property is what makes a child-write exception acceptable at
    all, so it is pinned rather than assumed."""
    client, principal, db = ctx
    cal_id = _make_calendar(client, principal)
    client.post(
        f"/reference/calendars/{cal_id}/holidays",
        json={
            "holidays": [
                {"holiday_date": "2027-01-01", "name": "A"},
                {"holiday_date": "2027-12-25", "name": "B"},
            ]
        },
        headers=_headers(principal),
    )
    resp = client.post(  # a SUBSET — the omitted date must survive
        f"/reference/calendars/{cal_id}/holidays",
        json={"holidays": [{"holiday_date": "2027-01-01", "name": "A"}]},
        headers=_headers(principal),
    )
    assert resp.status_code == 200
    assert len(resp.json()["holidays"]) == 2, "the refresh DELETED a date — it is not add-only"


def test_the_refresh_requires_edit(ctx: tuple[TestClient, Principal, Session]) -> None:
    client, principal, _ = ctx
    cal_id = _make_calendar(client, principal)
    resp = client.post(
        f"/reference/calendars/{cal_id}/holidays",
        json={"holidays": []},
        headers=_no_perm_headers(principal),
    )
    assert resp.status_code == 403


def test_an_unknown_calendar_is_a_404_not_a_500(
    ctx: tuple[TestClient, Principal, Session],
) -> None:
    client, principal, _ = ctx
    resp = client.post(
        f"/reference/calendars/{uuid.uuid4()}/holidays",
        json={"holidays": []},
        headers=_headers(principal),
    )
    assert resp.status_code == 404


def test_ANOTHER_TENANTS_calendar_is_refused_404(
    ctx: tuple[TestClient, Principal, Session],
) -> None:
    """The tenant fence, against the LIKELY hostile input rather than the easy one.

    Written second, because the first version of this control used a random UUID and was VACUOUS:
    removing the tenant filter from the endpoint killed no test at all. A nonexistent id 404s
    whether or not the fence exists — the input that discriminates is a REAL calendar owned by
    SOMEONE ELSE. (The LIM-2 lesson: mutate against the likely input, not the easy one.)

    This matters beyond tidiness. A SYSTEM-tenant calendar is VISIBLE to every tenant under the
    hybrid policy, so without the explicit filter the endpoint resolves a foreign row and the
    refusal lands deep in the flush as a 500 — or, on a tier without RLS, does not land at all.
    """
    client, principal, db = ctx
    foreign = Calendar(
        tenant_id=str(uuid.uuid4()),  # a real row, a real id, a DIFFERENT owner
        code="XFOR",
        name="Foreign Exchange Calendar",
        mic="XFOR",
        record_version=1,
    )
    db.add(foreign)
    db.commit()

    resp = client.post(
        f"/reference/calendars/{foreign.id}/holidays",
        json={"holidays": [{"holiday_date": "2027-01-01"}], "complete_through": "2027-12-31"},
        headers=_headers(principal),
    )
    assert resp.status_code == 404, resp.text
    db.refresh(foreign)
    assert foreign.holidays_complete_through is None, "a foreign calendar's horizon was MOVED"
    assert (
        db.execute(
            select(func.count())
            .select_from(CalendarHoliday)
            .where(CalendarHoliday.calendar_id == foreign.id)
        ).scalar_one()
        == 0
    ), "dates were written into another tenant's calendar"


# --- rating_scale (children via parent write) ---


def test_create_rating_scale_with_grades_via_parent(
    ctx: tuple[TestClient, Principal, Session],
) -> None:
    client, principal, db = ctx
    resp = client.post(
        "/reference/rating-scales",
        json={
            "code": "SP_LT",
            "name": "S&P",
            "agency": "SP",
            "grades": [
                {"code": "AAA", "rank": 1},
                {"code": "AA", "rank": 2},
                {"code": "A", "rank": 3},
            ],
        },
        headers=_headers(principal),
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert [g["code"] for g in body["grades"]] == ["AAA", "AA", "A"]
    assert db.execute(select(func.count()).select_from(RatingGrade)).scalar_one() == 3


def test_create_rating_scale_requires_edit(ctx: tuple[TestClient, Principal, Session]) -> None:
    client, principal, _ = ctx
    resp = client.post(
        "/reference/rating-scales",
        json={"code": "S", "name": "S"},
        headers=_no_perm_headers(principal),
    )
    assert resp.status_code == 403


def test_missing_principal_401(ctx: tuple[TestClient, Principal, Session]) -> None:
    client, _, _ = ctx
    assert client.get("/reference/currencies").status_code == 401
