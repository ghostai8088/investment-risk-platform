"""End-to-end tests of the API-2b breach endpoints (assign/respond/review/close + the queue reads).

SQLite has no RLS, so cross-tenant isolation is proven at the PG tier; here we prove the API-2b
controls: the person-level SoD survives HTTP (409, distinct from the 403 role gate), the epoch-aware
review guard (A-F1) refuses ratifying a rejected response THROUGH the API, D6 (the DTO state is
recency-derived while the frozen column reads DETECTED), the OQ-1=A owner carry, expected_seq
(OQ-4=A), the D8 assignee resolution incl. the router-side breach.respond check (C-OQ2=B),
no-second-write-path (extra="forbid"), pagination, the fixed-point decimal contract, cross-tenant
404, and the D10 route-inventory pin.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from irp_backend.api.breaches import router as breaches_router
from irp_backend.deps import get_db
from irp_shared.db.session import make_engine, make_session_factory
from irp_shared.entitlement.models import AppUser, Permission, Role, RolePermission, UserRole
from irp_shared.limit.events import LIMIT_KIND_HARD, THRESHOLD_UNIT_CURRENCY, LimitActor
from irp_shared.limit.lifecycle import escalate_overdue_breach
from irp_shared.limit.models import Base as _  # noqa: F401 - model import side effects
from irp_shared.limit.models import Breach
from irp_shared.limit.service import create_limit
from irp_shared.models import Base
from irp_shared.portfolio import PortfolioActor, create_portfolio

_RESPOND = ("breach.respond", "breach.view")
_REVIEW = ("breach.review", "breach.view")
_ALL = ("breach.respond", "breach.review", "breach.view")
_VIEW = ("breach.view",)


def _grant(db: Session, tenant: str, user_id: str, codes: tuple[str, ...]) -> None:
    role = Role(tenant_id=tenant, code=f"r-{uuid.uuid4().hex[:6]}", name="R")
    db.add(role)
    db.flush()
    for code in codes:
        perm = db.query(Permission).filter_by(code=code).one_or_none() or Permission(
            code=code, description="d"
        )
        db.add(perm)
        db.flush()
        db.add(RolePermission(role_id=role.id, permission_id=perm.id))
    db.add(UserRole(tenant_id=tenant, user_id=user_id, role_id=role.id))


def _mk_user(db: Session, tenant: str, name: str, codes: tuple[str, ...]) -> str:
    user = AppUser(tenant_id=tenant, display_name=name)
    db.add(user)
    db.flush()
    _grant(db, tenant, user.id, codes)
    return user.id


def _seed_breach(db: Session, tenant: str, limit_id: str, *, code_suffix: str = "") -> str:
    breach = Breach(
        tenant_id=tenant,
        limit_definition_id=limit_id,
        calculation_run_id=str(uuid.uuid4()),
        detected_at=datetime(2026, 1, 1, tzinfo=UTC),
        target_run_type="VAR",
        metric_type="VAR_PARAMETRIC",
        observed_value=Decimal("2000000.25"),
        threshold_value=Decimal("1000000"),
        threshold_unit=THRESHOLD_UNIT_CURRENCY,
        breach_direction="ABOVE",
        limit_kind=LIMIT_KIND_HARD,
        severity=LIMIT_KIND_HARD,
        status="DETECTED",
    )
    db.add(breach)
    db.flush()
    return breach.id


@pytest.fixture
def ctx() -> Iterator[dict[str, object]]:
    engine = make_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    db = make_session_factory(engine)()

    tenant = str(uuid.uuid4())
    responder = _mk_user(db, tenant, "Responder", _RESPOND)
    responder2 = _mk_user(db, tenant, "Responder2", _RESPOND)
    reviewer = _mk_user(db, tenant, "Reviewer", _REVIEW)
    dual = _mk_user(db, tenant, "DualHat", _ALL)  # the SoD backstop target
    viewer = _mk_user(db, tenant, "Viewer", _VIEW)
    pf = create_portfolio(
        db,
        tenant_id=tenant,
        code="PF",
        name="pf",
        node_type="ACCOUNT",
        actor=PortfolioActor(actor_id="steward"),
    )
    limit = create_limit(
        db,
        tenant_id=tenant,
        code="VAR-CEIL",
        name="VaR ceiling",
        target_run_type="VAR",
        metric_type="VAR_PARAMETRIC",
        scope_portfolio_id=str(pf.id),
        threshold_value=Decimal("1000000"),
        threshold_unit=THRESHOLD_UNIT_CURRENCY,
        breach_direction="ABOVE",
        limit_kind=LIMIT_KIND_HARD,
        actor=LimitActor(actor_id="risk-mgr-2l"),
    )
    breach_id = _seed_breach(db, tenant, limit.id)
    # a second tenant for the cross-tenant refusal
    tenant_b = str(uuid.uuid4())
    user_b = _mk_user(db, tenant_b, "B", _ALL)
    db.commit()

    def _override_db() -> Iterator[Session]:
        yield db

    app = FastAPI()
    app.include_router(breaches_router)
    app.dependency_overrides[get_db] = _override_db
    try:
        yield {
            "client": TestClient(app),
            "db": db,
            "tenant": tenant,
            "responder": responder,
            "responder2": responder2,
            "reviewer": reviewer,
            "dual": dual,
            "viewer": viewer,
            "breach": breach_id,
            "limit": limit.id,
            "pf": str(pf.id),
            "tenant_b": tenant_b,
            "user_b": user_b,
        }
    finally:
        db.close()
        engine.dispose()


def _hdr(user_id: str, tenant: str) -> dict[str, str]:
    return {"X-User-Id": user_id, "X-Tenant-Id": tenant}


def _assign(c: dict, assignee: str | None = None, actor: str | None = None) -> object:
    return c["client"].post(
        f"/breaches/{c['breach']}/assign",
        json={"assigned_to": assignee or c["responder"]},
        headers=_hdr(actor or c["reviewer"], c["tenant"]),
    )


def _respond(c: dict, actor: str | None = None, narrative: str = "hedged the book") -> object:
    return c["client"].post(
        f"/breaches/{c['breach']}/respond",
        json={"narrative": narrative},
        headers=_hdr(actor or c["responder"], c["tenant"]),
    )


def _review(c: dict, outcome: str, actor: str | None = None, **extra: object) -> object:
    body: dict[str, object] = {"outcome": outcome, **extra}
    if outcome == "REJECT" and "narrative" not in body:
        body["narrative"] = "redo"
    return c["client"].post(
        f"/breaches/{c['breach']}/review",
        json=body,
        headers=_hdr(actor or c["reviewer"], c["tenant"]),
    )


def _close(c: dict, actor: str | None = None) -> object:
    return c["client"].post(
        f"/breaches/{c['breach']}/close",
        json={"evidence_ref": "ticket://RISK-42"},
        headers=_hdr(actor or c["reviewer"], c["tenant"]),
    )


# --- the lifecycle through HTTP ------------------------------------------------------------
def test_full_lifecycle_through_http(ctx) -> None:
    r = _assign(ctx)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["state"] == "ASSIGNED"
    assert body["assigned_to"] == ctx["responder"]
    assert body["response_due"] is not None
    assert _respond(ctx).json()["state"] == "RESPONDED"
    assert _review(ctx, "ACCEPT").json()["state"] == "REVIEWED"
    assert _close(ctx).json()["state"] == "CLOSED"


def test_role_gates_are_distinct(ctx) -> None:
    # respond needs breach.respond (reviewer → 403); assign/review/close need breach.review
    assert _assign(ctx, actor=ctx["responder"]).status_code == 403
    assert _assign(ctx).status_code == 200
    assert _respond(ctx, actor=ctx["reviewer"]).status_code == 403
    assert _respond(ctx).status_code == 200
    assert _review(ctx, "ACCEPT", actor=ctx["responder"]).status_code == 403
    assert _close(ctx, actor=ctx["viewer"]).status_code == 403
    # viewer can read but not act
    assert (
        ctx["client"]
        .get(f"/breaches/{ctx['breach']}", headers=_hdr(ctx["viewer"], ctx["tenant"]))
        .status_code
        == 200
    )


def test_person_level_sod_survives_http(ctx) -> None:
    # The dual-hat holds BOTH breach.respond and breach.review — only the person-level SoD
    # stops them reviewing their own response: 409, NOT 403 (they hold the role).
    _assign(ctx, assignee=ctx["dual"])
    _respond(ctx, actor=ctx["dual"])
    r = _review(ctx, "ACCEPT", actor=ctx["dual"])
    assert r.status_code == 409, r.text
    r2 = _review(ctx, "ACCEPT", actor=ctx["reviewer"])  # a distinct 2L proceeds
    assert r2.status_code == 200
    r3 = _close(ctx, actor=ctx["dual"])  # the responder cannot close either
    assert r3.status_code == 409


def test_epoch_guard_through_http(ctx) -> None:
    # THE A-F1 defeat replayed through the API: respond → REJECT → escalate → ACCEPT must 409.
    _assign(ctx)
    _respond(ctx)
    assert _review(ctx, "REJECT").status_code == 200
    db: Session = ctx["db"]  # the tick escalates the overdue epoch (service-tier, SYSTEM)
    breach = db.get(Breach, ctx["breach"])
    escalate_overdue_breach(db, breach, datetime.now(UTC) + timedelta(days=3))
    db.commit()
    r = _review(ctx, "ACCEPT")  # the only response on file was formally rejected
    assert r.status_code == 409, r.text
    assert _respond(ctx, actor=ctx["responder2"]).status_code == 200  # fresh 1L work
    assert _review(ctx, "ACCEPT").status_code == 200


def test_reject_carries_the_owner_and_requires_narrative(ctx) -> None:
    _assign(ctx)
    _respond(ctx)
    r = ctx["client"].post(
        f"/breaches/{ctx['breach']}/review",
        json={"outcome": "REJECT"},  # no narrative
        headers=_hdr(ctx["reviewer"], ctx["tenant"]),
    )
    assert r.status_code == 422  # A-F8: a bare rejection gives the 1L nothing to remediate against
    r2 = _review(ctx, "REJECT")
    assert r2.status_code == 200
    assert r2.json()["state"] == "ASSIGNED"
    assert r2.json()["assigned_to"] == ctx["responder"]  # OQ-1=A carry-forward — never None
    # explicit handoff to a responder2 (must hold breach.respond)
    _respond(ctx)
    r3 = _review(ctx, "REJECT", assigned_to=ctx["responder2"])
    assert r3.json()["assigned_to"] == ctx["responder2"]


def test_assignee_must_hold_breach_respond(ctx) -> None:
    r = _assign(
        ctx, assignee=ctx["viewer"]
    )  # viewer cannot respond → assigning guarantees escalation
    assert r.status_code == 422
    r2 = _assign(ctx, assignee=str(uuid.uuid4()))  # unknown user
    assert r2.status_code == 422


def test_expected_seq_stale_is_409(ctx) -> None:
    _assign(ctx)
    r = ctx["client"].post(
        f"/breaches/{ctx['breach']}/respond",
        json={"narrative": "x", "expected_seq": 0},  # stale — the assign advanced to 1
        headers=_hdr(ctx["responder"], ctx["tenant"]),
    )
    assert r.status_code == 409
    r2 = ctx["client"].post(
        f"/breaches/{ctx['breach']}/respond",
        json={"narrative": "x", "expected_seq": 1},
        headers=_hdr(ctx["responder"], ctx["tenant"]),
    )
    assert r2.status_code == 200


def test_state_conflicts_are_409(ctx) -> None:
    assert _respond(ctx).status_code == 409  # respond before assign
    assert _close(ctx).status_code == 409  # close before review
    _assign(ctx)
    assert _assign(ctx).status_code == 409  # double-assign


def test_smuggled_fields_are_422(ctx) -> None:
    r = ctx["client"].post(
        f"/breaches/{ctx['breach']}/assign",
        json={"assigned_to": ctx["responder"], "status": "CLOSED"},
        headers=_hdr(ctx["reviewer"], ctx["tenant"]),
    )
    assert r.status_code == 422  # extra="forbid" — no second write path (D3)


# --- reads ---------------------------------------------------------------------------------
def test_detail_state_is_recency_derived_not_the_frozen_column(ctx) -> None:
    # D6 through HTTP: the ORM column stays DETECTED forever; the DTO must report the truth.
    _assign(ctx)
    _respond(ctx)
    db: Session = ctx["db"]
    assert db.get(Breach, ctx["breach"]).status == "DETECTED"  # the frozen column
    body = (
        ctx["client"]
        .get(f"/breaches/{ctx['breach']}", headers=_hdr(ctx["viewer"], ctx["tenant"]))
        .json()
    )
    assert body["state"] == "RESPONDED"
    assert "status" not in body  # the trap column is not serialized at all


def test_queue_filters_and_pagination(ctx) -> None:
    db: Session = ctx["db"]
    second = _seed_breach(db, ctx["tenant"], ctx["limit"])
    db.commit()
    _assign(ctx)  # only the FIRST breach is assigned
    hdr = _hdr(ctx["viewer"], ctx["tenant"])
    c = ctx["client"]
    assert len(c.get("/breaches", headers=hdr).json()) == 2
    assigned = c.get("/breaches?state=ASSIGNED", headers=hdr).json()
    assert [x["id"] for x in assigned] == [ctx["breach"]]
    detected = c.get("/breaches?state=DETECTED", headers=hdr).json()
    assert [x["id"] for x in detected] == [second]  # zero-action breaches surface (coalesce)
    assert len(c.get("/breaches?open=true", headers=hdr).json()) == 2
    assert len(c.get("/breaches?limit=1", headers=hdr).json()) == 1
    assert c.get("/breaches?limit=0", headers=hdr).status_code == 422  # ge=1
    # assigned_to_me: the responder sees their queue; the reviewer's is empty
    mine = c.get("/breaches?assigned_to_me=true", headers=_hdr(ctx["responder"], ctx["tenant"]))
    assert [x["id"] for x in mine.json()] == [ctx["breach"]]
    assert (
        c.get("/breaches?assigned_to_me=true", headers=_hdr(ctx["reviewer"], ctx["tenant"])).json()
        == []
    )
    # portfolio filter (via the frozen-identity join) + the limit-code echo
    pf = c.get(f"/breaches?portfolio_id={ctx['pf']}", headers=hdr).json()
    assert len(pf) == 2 and pf[0]["limit_code"] == "VAR-CEIL"


def test_timeline_is_seq_ordered(ctx) -> None:
    _assign(ctx)
    _respond(ctx)
    _review(ctx, "REJECT")
    timeline = (
        ctx["client"]
        .get(f"/breaches/{ctx['breach']}/actions", headers=_hdr(ctx["viewer"], ctx["tenant"]))
        .json()
    )
    assert [a["seq"] for a in timeline] == [1, 2, 3]
    assert [a["action_type"] for a in timeline] == ["ASSIGN", "1L_RESPONSE", "2L_REVIEW"]
    assert timeline[2]["review_outcome"] == "REJECT"
    assert timeline[2]["assigned_to"] == ctx["responder"]  # the OQ-1=A carry is on the row


def test_decimal_contract_fixed_point(ctx) -> None:
    body = (
        ctx["client"]
        .get(f"/breaches/{ctx['breach']}", headers=_hdr(ctx["viewer"], ctx["tenant"]))
        .json()
    )
    # fixed-point at column scale (34,12) — value-equal, never scientific notation
    assert Decimal(body["observed_value"]) == Decimal("2000000.25")
    assert "e" not in body["observed_value"].lower()
    assert "e" not in body["threshold_value"].lower()


def test_cross_tenant_is_404(ctx) -> None:
    hb = _hdr(ctx["user_b"], ctx["tenant_b"])
    assert ctx["client"].get(f"/breaches/{ctx['breach']}", headers=hb).status_code == 404
    assert ctx["client"].get("/breaches", headers=hb).json() == []
    r = ctx["client"].post(
        f"/breaches/{ctx['breach']}/respond", json={"narrative": "x"}, headers=hb
    )
    assert r.status_code == 404  # transitions pre-load tenant-filtered — no existence oracle


def test_unknown_breach_is_404(ctx) -> None:
    r = ctx["client"].get(f"/breaches/{uuid.uuid4()}", headers=_hdr(ctx["viewer"], ctx["tenant"]))
    assert r.status_code == 404


def test_route_inventory_pins_the_verb_set(ctx) -> None:
    # D10: escalate/evaluate never exposed; the exact /breaches path set is pinned.
    paths = set(ctx["client"].app.openapi()["paths"])
    assert not any("escalate" in p or "evaluate" in p for p in paths)
    assert {p for p in paths if p.startswith("/breaches")} == {
        "/breaches",
        "/breaches/{breach_id}",
        "/breaches/{breach_id}/assign",
        "/breaches/{breach_id}/respond",
        "/breaches/{breach_id}/review",
        "/breaches/{breach_id}/close",
        "/breaches/{breach_id}/actions",
    }


# --- 4-finder folds: assignee taxonomy, terminal-state deadline, 40P01 mapping ---------------
def test_non_uuid_assignee_is_422_not_500(ctx) -> None:
    # Finders 1/4: a non-UUID assigned_to would reach the PG uuid cast → 22P02 → unmapped 500.
    # The router UUID-shape-checks first → a clean 422 (SQLite-invisible pre-fix; now uniform).
    r = ctx["client"].post(
        f"/breaches/{ctx['breach']}/assign",
        json={"assigned_to": "analyst-1"},  # non-blank, <=255, but not UUID-shaped
        headers=_hdr(ctx["reviewer"], ctx["tenant"]),
    )
    assert r.status_code == 422
    assert "state" not in r.json().get("detail", "")  # not the misleading 409 conflict detail


def test_inactive_assignee_is_422_not_a_false_409(ctx) -> None:
    # Finder 3 M1: an inactive-but-still-role-granted user passes the router permission gate but
    # fails service resolution — must be a 422 (request content), NOT a 409 "illegal transition"
    # (a lie about a healthy breach state).
    db: Session = ctx["db"]
    gone = AppUser(tenant_id=ctx["tenant"], display_name="Gone", is_active=False)
    db.add(gone)
    db.flush()
    _grant(db, ctx["tenant"], gone.id, _RESPOND)  # role persists after deactivation
    db.commit()
    r = ctx["client"].post(
        f"/breaches/{ctx['breach']}/assign",
        json={"assigned_to": gone.id},
        headers=_hdr(ctx["reviewer"], ctx["tenant"]),
    )
    assert r.status_code == 422, r.text


def test_terminal_states_report_no_live_deadline(ctx) -> None:
    # Finder 3 L4 / finder 4: ACCEPT clears the clock, but the governing ASSIGNED row still carries
    # the old response_due — a REVIEWED/CLOSED breach must NOT resurface it (a live-looking due).
    _assign(ctx)
    _respond(ctx)
    assert _review(ctx, "ACCEPT").json()["response_due"] is None  # REVIEWED — cleared
    assert _close(ctx).json()["response_due"] is None  # CLOSED — cleared


def test_open_filter_excludes_closed(ctx) -> None:
    # Finder 3 M3(i): the open=true → !=CLOSED exclusion was never proven against a CLOSED breach.
    _assign(ctx)
    _respond(ctx)
    _review(ctx, "ACCEPT")
    _close(ctx)  # the only breach is now CLOSED
    hdr = _hdr(ctx["viewer"], ctx["tenant"])
    c = ctx["client"]
    assert c.get("/breaches?open=true", headers=hdr).json() == []  # excluded
    assert [x["id"] for x in c.get("/breaches?state=CLOSED", headers=hdr).json()] == [ctx["breach"]]
    assert len(c.get("/breaches", headers=hdr).json()) == 1  # unfiltered still sees it


def test_deadlock_maps_to_503(ctx) -> None:
    # Finder 3 M3(iii) / finder 4: pin the 40P01 → 503 mapping directly (the real interleave is
    # unconstructible post-P1, so a synthetic OperationalError is the only way to prove it).
    from unittest.mock import patch

    from sqlalchemy.exc import OperationalError

    class _Orig(Exception):
        sqlstate = "40P01"

    def _boom(*a, **k):
        raise OperationalError("deadlock", {}, _Orig())

    with patch("irp_backend.api.breaches.respond_breach", _boom):
        r = ctx["client"].post(
            f"/breaches/{ctx['breach']}/respond",
            json={"narrative": "x"},
            headers=_hdr(ctx["responder"], ctx["tenant"]),
        )
    assert r.status_code == 503
    assert r.headers.get("Retry-After") == "1"


def test_non_deadlock_operational_error_is_not_swallowed(ctx) -> None:
    # The 503 mapping must NOT mask other OperationalErrors (fail loud).
    from unittest.mock import patch

    from sqlalchemy.exc import OperationalError

    class _Orig(Exception):
        sqlstate = "57014"  # query canceled — not a deadlock

    def _boom(*a, **k):
        raise OperationalError("canceled", {}, _Orig())

    with patch("irp_backend.api.breaches.respond_breach", _boom), pytest.raises(OperationalError):
        ctx["client"].post(
            f"/breaches/{ctx['breach']}/respond",
            json={"narrative": "x"},
            headers=_hdr(ctx["responder"], ctx["tenant"]),
        )
