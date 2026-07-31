"""End-to-end tests of the API-2 limit endpoints (POST/PATCH/approve/suspend/resume + reads).

SQLite has no RLS, so cross-tenant isolation is proven at the PG tier; here we prove the API-2
controls: the person-level SoD survives the HTTP boundary (D1), the role gate (limit.approve) is
DISTINCT from the maker gate (limit.manage), the no-second-write-path (status is a forbidden field —
D3), deny-by-default gating (D4), the SoD/state refusals are 409 not 422/403 (B1/OQ-3), the
create-duplicate is a uniform 409 (N4), the decimal contract holds at a scientific boundary, the
explicit-tenant-predicate refuses a cross-tenant id, and the tick-only verbs are not exposed (D10).
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from irp_backend.api.limits import _limit_actor
from irp_backend.api.limits import router as limits_router
from irp_backend.deps import get_db
from irp_shared.db.session import make_engine, make_session_factory
from irp_shared.entitlement.models import AppUser, Permission, Role, RolePermission, UserRole
from irp_shared.entitlement.service import Principal
from irp_shared.models import Base
from irp_shared.portfolio import PortfolioActor, create_portfolio
from irp_shared.reference.models import Issuer, LegalEntity

_ALL = ("limit.manage", "limit.approve", "limit.view")
_MANAGE_ONLY = ("limit.manage", "limit.view")  # NO limit.approve


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
    maker = AppUser(tenant_id=tenant, display_name="Maker")
    approver = AppUser(tenant_id=tenant, display_name="Approver")
    mgr = AppUser(tenant_id=tenant, display_name="ManageOnly")
    db.add_all([maker, approver, mgr])
    db.flush()
    _grant(db, tenant, maker.id, _ALL)
    _grant(db, tenant, approver.id, _ALL)
    _grant(db, tenant, mgr.id, _MANAGE_ONLY)
    pf = create_portfolio(
        db,
        tenant_id=tenant,
        code="PF",
        name="pf",
        node_type="ACCOUNT",
        actor=PortfolioActor(actor_id="steward"),
    )
    # A SECOND tenant, for the cross-tenant refusal test.
    tenant_b = str(uuid.uuid4())
    user_b = AppUser(tenant_id=tenant_b, display_name="B")
    db.add(user_b)
    db.flush()
    _grant(db, tenant_b, user_b.id, _ALL)
    db.commit()

    def _override_db() -> Iterator[Session]:
        yield db

    app = FastAPI()
    app.include_router(limits_router)
    app.dependency_overrides[get_db] = _override_db
    try:
        yield {
            "client": TestClient(app),
            "tenant": tenant,
            "maker": maker.id,
            "approver": approver.id,
            "manage_only": mgr.id,
            "pf": str(pf.id),
            "tenant_b": tenant_b,
            "user_b": user_b.id,
            "db": db,
        }
    finally:
        db.close()
        engine.dispose()


def _hdr(user_id: str, tenant: str) -> dict[str, str]:
    return {"X-User-Id": user_id, "X-Tenant-Id": tenant}


def _body(pf: str, code: str = "VAR-CEIL", threshold: str = "5000000") -> dict[str, object]:
    return {
        "code": code,
        "name": code,
        "target_run_type": "VAR",
        "metric_type": "VAR_PARAMETRIC",
        "scope_portfolio_id": pf,
        "threshold_value": threshold,
        "threshold_unit": "CURRENCY",
        "breach_direction": "ABOVE",
        "limit_kind": "HARD",
    }


def _create(c: dict, uid: str, *, code: str = "VAR-CEIL", threshold: str = "5000000") -> dict:
    body = _body(c["pf"], code=code, threshold=threshold)
    r = c["client"].post("/limits", json=body, headers=_hdr(uid, c["tenant"]))
    assert r.status_code == 201, r.text
    return r.json()


def _approve(c: dict, lid: str, uid: str) -> object:
    return c["client"].post(
        f"/limits/{lid}/approve", json={"approval_ref": "RC"}, headers=_hdr(uid, c["tenant"])
    )


# --- create + gating -----------------------------------------------------------------------
def test_create_yields_draft(ctx) -> None:
    lim = _create(ctx, ctx["maker"])
    assert lim["status"] == "DRAFT"
    assert lim["threshold_value"] == "5000000"
    assert lim["created_by"] == ctx["maker"]


def test_create_denied_without_permission(ctx) -> None:
    r = ctx["client"].post(
        "/limits", json=_body(ctx["pf"]), headers=_hdr(str(uuid.uuid4()), ctx["tenant"])
    )
    assert r.status_code == 403


# --- the person-level SoD + the DISTINCT role gate (finder-4 HIGH-1) -----------------------
def test_self_approval_refused_through_http(ctx) -> None:
    lim = _create(ctx, ctx["maker"])
    r = _approve(ctx, lim["id"], ctx["maker"])  # maker HOLDS limit.approve — only the SoD stops it
    assert r.status_code == 409, r.text  # separation of duties, NOT 422/403
    # (The case-variance form is PG-specific and proven at the canonicalization unit level in
    #  packages/shared-python/tests/test_limit.py::test_actor_id_canonicalization_*.)


def test_approve_requires_limit_approve_permission_distinct_from_manage(ctx) -> None:
    # A principal with limit.manage but NOT limit.approve is a 403 (role gate) — distinct from the
    # maker's 409 (person SoD). Proves approve is gated on limit.approve, not limit.manage.
    lim = _create(ctx, ctx["maker"])
    r = _approve(ctx, lim["id"], ctx["manage_only"])
    assert r.status_code == 403


def test_distinct_approver_activates(ctx) -> None:
    lim = _create(ctx, ctx["maker"])
    r = _approve(ctx, lim["id"], ctx["approver"])
    assert r.status_code == 200 and r.json()["status"] == "ACTIVE"


def test_approve_requires_approval_ref(ctx) -> None:
    lim = _create(ctx, ctx["maker"])
    r = ctx["client"].post(
        f"/limits/{lim['id']}/approve",
        json={"approval_ref": "  "},
        headers=_hdr(ctx["approver"], ctx["tenant"]),
    )
    assert r.status_code == 422  # a base LimitError (non-empty ref), NOT 409


def test_reapprove_of_active_is_409(ctx) -> None:
    lim = _create(ctx, ctx["maker"])
    _approve(ctx, lim["id"], ctx["approver"])  # -> ACTIVE
    r = _approve(ctx, lim["id"], ctx["approver"])  # again -> state conflict
    assert r.status_code == 409


# --- no second write path (D3) -------------------------------------------------------------
def test_create_forbids_a_smuggled_status(ctx) -> None:
    body = _body(ctx["pf"])
    body["status"] = "ACTIVE"  # unknown field -> loud 422 (extra="forbid")
    r = ctx["client"].post("/limits", json=body, headers=_hdr(ctx["maker"], ctx["tenant"]))
    assert r.status_code == 422


def test_patch_forbids_a_smuggled_status(ctx) -> None:
    lim = _create(ctx, ctx["maker"])
    _approve(ctx, lim["id"], ctx["approver"])
    r = ctx["client"].patch(
        f"/limits/{lim['id']}",
        json={"status": "SUSPENDED"},
        headers=_hdr(ctx["maker"], ctx["tenant"]),
    )
    assert r.status_code == 422  # forbidden field, not a silent no-op


def test_patch_name_only_stays_active(ctx) -> None:
    lim = _create(ctx, ctx["maker"])
    _approve(ctx, lim["id"], ctx["approver"])
    r = ctx["client"].patch(
        f"/limits/{lim['id']}", json={"name": "renamed"}, headers=_hdr(ctx["maker"], ctx["tenant"])
    )
    assert r.status_code == 200 and r.json()["status"] == "ACTIVE" and r.json()["name"] == "renamed"


def test_material_change_demotes_to_draft(ctx) -> None:
    lim = _create(ctx, ctx["maker"])
    _approve(ctx, lim["id"], ctx["approver"])
    r = ctx["client"].patch(
        f"/limits/{lim['id']}",
        json={"threshold_value": "9000000"},
        headers=_hdr(ctx["maker"], ctx["tenant"]),
    )
    assert r.status_code == 200 and r.json()["status"] == "DRAFT"


# --- suspend/resume + state conflicts (409) -----------------------------------------------
def test_suspend_then_resume(ctx) -> None:
    lim = _create(ctx, ctx["maker"])
    _approve(ctx, lim["id"], ctx["approver"])
    c, t, m = ctx["client"], ctx["tenant"], ctx["maker"]
    assert (
        c.post(f"/limits/{lim['id']}/suspend", headers=_hdr(m, t)).json()["status"] == "SUSPENDED"
    )
    assert c.post(f"/limits/{lim['id']}/resume", headers=_hdr(m, t)).json()["status"] == "ACTIVE"


def test_suspend_a_draft_is_409(ctx) -> None:
    lim = _create(ctx, ctx["maker"])  # DRAFT
    r = ctx["client"].post(
        f"/limits/{lim['id']}/suspend", headers=_hdr(ctx["maker"], ctx["tenant"])
    )
    assert r.status_code == 409  # illegal transition from DRAFT, not 422


# --- reads ---------------------------------------------------------------------------------
def test_get_by_id_round_trips(ctx) -> None:
    lim = _create(ctx, ctx["maker"])
    r = ctx["client"].get(f"/limits/{lim['id']}", headers=_hdr(ctx["maker"], ctx["tenant"]))
    assert r.status_code == 200 and r.json()["code"] == "VAR-CEIL" and r.json()["status"] == "DRAFT"


def test_list_by_status_is_the_approval_queue(ctx) -> None:
    a = _create(ctx, ctx["maker"], code="A")
    _create(ctx, ctx["maker"], code="B")  # stays DRAFT
    _approve(ctx, a["id"], ctx["approver"])
    drafts = (
        ctx["client"].get("/limits?status=DRAFT", headers=_hdr(ctx["maker"], ctx["tenant"])).json()
    )
    assert {x["code"] for x in drafts} == {"B"}
    assert len(ctx["client"].get("/limits", headers=_hdr(ctx["maker"], ctx["tenant"])).json()) == 2


def test_health_never_evaluable_is_not_false_green(ctx) -> None:
    lim = _create(ctx, ctx["maker"])
    _approve(ctx, lim["id"], ctx["approver"])
    health = ctx["client"].get("/limits/health", headers=_hdr(ctx["maker"], ctx["tenant"])).json()
    # EXACT dict equality, kept deliberately: it is what makes a silently-widened health payload a
    # failing test rather than an unnoticed contract change. LIM-2 added the three orthogonal
    # signals below, and this assertion is where that had to be declared.
    assert health == [
        {
            "limit_id": lim["id"],
            "code": "VAR-CEIL",
            "state": "NEVER_EVALUABLE",
            "latest_run_id": None,
            "latest_breach_id": None,
            # Orthogonal to `state` (LIM-2 record 3.5): a limit can be breached AND stale AND
            # drifting at once, so these are fields rather than extra enum values.
            "latest_run_failed": False,
            "scheme_drift_from": None,
            "scheme_drift_to": None,
            "refusal_reason": None,
        }
    ]


def test_decimal_contract_no_scientific_notation(ctx) -> None:
    # A 1E-8 threshold must serialize fixed-point, never `1E-8` (finder-4 MED-2) — the boundary that
    # distinguishes f"{x:f}" from str(x). A CURRENCY VaR ceiling admits any positive value.
    lim = _create(ctx, ctx["maker"], code="TINY", threshold="0.00000001")
    tv = lim["threshold_value"]
    assert "e" not in tv.lower() and tv.startswith("0.00000001")


# --- cross-tenant, duplicate, 404, 401, tick-verbs ----------------------------------------
def test_cross_tenant_id_is_404(ctx) -> None:
    lim = _create(ctx, ctx["maker"])  # tenant A's limit
    hb = _hdr(ctx["user_b"], ctx["tenant_b"])  # acting as tenant B
    assert ctx["client"].get(f"/limits/{lim['id']}", headers=hb).status_code == 404
    assert ctx["client"].get("/limits", headers=hb).json() == []  # B sees none of A's limits


def test_duplicate_code_is_409(ctx) -> None:
    _create(ctx, ctx["maker"], code="DUP")
    r = ctx["client"].post(
        "/limits", json=_body(ctx["pf"], code="DUP"), headers=_hdr(ctx["maker"], ctx["tenant"])
    )
    assert r.status_code == 409


def test_unknown_limit_is_404(ctx) -> None:
    r = ctx["client"].get(f"/limits/{uuid.uuid4()}", headers=_hdr(ctx["maker"], ctx["tenant"]))
    assert r.status_code == 404


def test_limit_actor_fails_closed_on_non_uuid() -> None:
    # The dev-header contract (D1/F2): a non-UUID user_id fails closed at the actor boundary (401).
    with pytest.raises(HTTPException) as exc:
        _limit_actor(Principal(user_id="not-a-uuid", tenant_id=str(uuid.uuid4())))
    assert exc.value.status_code == 401


def test_tick_only_verbs_are_not_exposed(ctx) -> None:
    paths = set(ctx["client"].app.openapi()["paths"])
    assert not any("evaluate" in p or "escalate" in p for p in paths)
    assert {p for p in paths if p.startswith("/limits")} == {
        "/limits",
        "/limits/{limit_id}",
        "/limits/{limit_id}/approve",
        "/limits/{limit_id}/suspend",
        "/limits/{limit_id}/resume",
        "/limits/health",
    }


def test_the_limit_refusal_detail_strings_are_a_pinned_contract(ctx) -> None:
    """Wave-12 close fold (the M-1 class, limits side). The operations UI classifies limit 409s on
    the same `detail` markers as the breach verbs (apps/frontend/src/api/writes.ts SOD_MARKER +
    the illegal-transition marker), but until this test only the STATUS codes were asserted here —
    a backend reword shipped with zero failing tests and silently degraded every approve refusal
    explanation to a generic "conflict". One UNCONDITIONAL exact-string assertion per 409 cause."""
    lim = _create(ctx, ctx["maker"])
    # SEPARATION OF DUTIES: the maker self-approves — person-level, not the role gate.
    sod = _approve(ctx, lim["id"], ctx["maker"])
    assert sod.status_code == 409
    assert sod.json()["detail"] == "separation of duties: the actor shaped this limit"
    # DUPLICATE IDENTITY: a second limit with the same code.
    dup = ctx["client"].post(
        "/limits", json=_body(ctx["pf"]), headers=_hdr(ctx["maker"], ctx["tenant"])
    )
    assert dup.status_code == 409
    assert dup.json()["detail"] == "a limit with that code already exists"
    # ILLEGAL TRANSITION: suspend a DRAFT.
    ill = ctx["client"].post(
        f"/limits/{lim['id']}/suspend", headers=_hdr(ctx["maker"], ctx["tenant"])
    )
    assert ill.status_code == 409
    assert ill.json()["detail"] == "illegal transition from the current limit state"


def test_limit_deadlock_maps_to_503(ctx) -> None:
    # Wave-12 close fold: phases 1-2 of the tick hold the audit advisory while a new-breach INSERT
    # waits on the parent limit row's FK KEY SHARE, so a limit verb (FOR UPDATE -> advisory) is a
    # reachable 40P01 victim — it must get the same retryable 503 the breach verbs give (B-F1
    # symmetry), not a raw 500. The real interleave needs PG; a synthetic OperationalError pins
    # the mapping.
    from unittest.mock import patch

    from sqlalchemy.exc import OperationalError

    class _Orig(Exception):
        sqlstate = "40P01"

    def _boom(*a, **k):
        raise OperationalError("deadlock", {}, _Orig())

    lim = _create(ctx, ctx["maker"])
    _approve(ctx, lim["id"], ctx["approver"])
    with patch("irp_backend.api.limits.suspend_limit", _boom):
        r = ctx["client"].post(
            f"/limits/{lim['id']}/suspend", headers=_hdr(ctx["maker"], ctx["tenant"])
        )
    assert r.status_code == 503
    assert r.headers.get("Retry-After") == "1"


def test_limit_non_deadlock_operational_error_is_not_swallowed(ctx) -> None:
    # The 503 mapping must NOT mask other OperationalErrors (fail loud).
    from unittest.mock import patch

    from sqlalchemy.exc import OperationalError

    class _Orig(Exception):
        sqlstate = "57014"  # query canceled — not a deadlock

    def _boom(*a, **k):
        raise OperationalError("canceled", {}, _Orig())

    lim = _create(ctx, ctx["maker"])
    with patch("irp_backend.api.limits.approve_limit", _boom), pytest.raises(OperationalError):
        ctx["client"].post(
            f"/limits/{lim['id']}/approve",
            json={"approval_ref": "RC"},
            headers=_hdr(ctx["approver"], ctx["tenant"]),
        )


# --- LIM-2: the issuer-identity disclosure fence, on EVERY read surface --------------------
# CON-1 minted `concentration.issuer.view` so the auditor line could differ, and deliberately
# excluded `auditor_3l` from it while that role DOES hold `limit.view`. LIM-2 lets a limit NAME an
# issuer, so the fence has to follow the data onto this surface.
#
# Every fence assertion below carries its POSITIVE CONTROL in the same test: a caller WITH the code
# must still receive the limit. Without that, a read that was simply broken would pass as a fence.
_ISSUER_CODE = "concentration.issuer.view"
_WITH_ISSUER = ("limit.manage", "limit.approve", "limit.view", _ISSUER_CODE)


def _principals_either_side_of_the_fence(ctx) -> tuple[str, str]:  # noqa: ANN001
    """Two principals in the acting tenant: one holding the issuer code, one without it."""
    db: Session = ctx["db"]
    tenant: str = ctx["tenant"]
    holder = AppUser(tenant_id=tenant, display_name="HoldsIssuerView")
    fenced = AppUser(tenant_id=tenant, display_name="NoIssuerView")
    db.add_all([holder, fenced])
    db.flush()
    _grant(db, tenant, holder.id, _WITH_ISSUER)
    _grant(db, tenant, fenced.id, _ALL)  # limit.view but NOT concentration.issuer.view
    db.commit()
    return str(holder.id), str(fenced.id)


def _real_issuer(ctx) -> str:  # noqa: ANN001
    """A REAL issuer in the acting tenant.

    A bare uuid does not work, and that is the P3-5 guard doing its job: `create_limit` re-resolves
    `issuer_id` tenant-filtered before the write, because a PostgreSQL FK check bypasses RLS and a
    foreign issuer id here would be a cross-tenant identity DISCLOSURE, not merely a bad reference.
    Discovering that from a 422 is the guard proving itself."""
    db: Session = ctx["db"]
    tenant: str = ctx["tenant"]
    core = LegalEntity(
        tenant_id=tenant, code=f"LE-{uuid.uuid4().hex[:6]}", name="Acme", is_active=True
    )
    db.add(core)
    db.flush()
    issuer = Issuer(tenant_id=tenant, legal_entity_id=core.id, is_active=True)
    db.add(issuer)
    db.commit()
    return str(issuer.id)


def _create_issuer_limit(ctx, uid: str) -> dict:  # noqa: ANN001
    """A named-issuer concentration limit over a REAL issuer."""
    issuer_id = _real_issuer(ctx)
    body = {
        "code": f"ISS-{uuid.uuid4().hex[:6]}",
        "name": "issuer X <= 5%",
        "target_run_type": "CONCENTRATION",
        "metric_type": "SHARE",
        "scope_portfolio_id": ctx["pf"],
        "threshold_value": "0.05",
        "threshold_unit": "FRACTION",
        "breach_direction": "ABOVE",
        "limit_kind": "HARD",
        "dimension_kind": "ISSUER",
        "bucket_code": issuer_id,
        "issuer_id": issuer_id,
        "denominator_basis": "INVESTED_LONG",
    }
    r = ctx["client"].post("/limits", json=body, headers=_hdr(uid, ctx["tenant"]))
    assert r.status_code == 201, r.text
    return r.json()


def test_the_limit_list_excludes_issuer_named_limits_from_a_fenced_caller(ctx) -> None:
    holder, fenced = _principals_either_side_of_the_fence(ctx)
    lim = _create_issuer_limit(ctx, holder)

    seen_by_fenced = ctx["client"].get("/limits", headers=_hdr(fenced, ctx["tenant"])).json()
    assert lim["id"] not in {x["id"] for x in seen_by_fenced}

    # POSITIVE CONTROL — the holder DOES see it, so the exclusion above is a fence and not a
    # read that returns nothing for everyone.
    seen_by_holder = ctx["client"].get("/limits", headers=_hdr(holder, ctx["tenant"])).json()
    assert lim["id"] in {x["id"] for x in seen_by_holder}


def test_fetching_a_fenced_limit_is_404_not_403(ctx) -> None:
    """A 403 would itself be the disclosure — it confirms a limit exists at that id. The fenced
    caller must get the SAME answer as for an id that does not exist."""
    holder, fenced = _principals_either_side_of_the_fence(ctx)
    lim = _create_issuer_limit(ctx, holder)

    fenced_get = ctx["client"].get(f"/limits/{lim['id']}", headers=_hdr(fenced, ctx["tenant"]))
    missing_get = ctx["client"].get(f"/limits/{uuid.uuid4()}", headers=_hdr(fenced, ctx["tenant"]))
    assert fenced_get.status_code == 404
    assert fenced_get.status_code == missing_get.status_code
    assert fenced_get.json() == missing_get.json()  # indistinguishable, body included

    # POSITIVE CONTROL — the holder gets 200 with the issuer identity present.
    ok = ctx["client"].get(f"/limits/{lim['id']}", headers=_hdr(holder, ctx["tenant"]))
    assert ok.status_code == 200 and ok.json()["issuer_id"] == lim["issuer_id"]


def test_the_health_surface_does_not_leak_issuer_named_limits(ctx) -> None:
    """**The hole this test was written for.** `limit_health` iterates `select_active_limits` —
    the TICK's query, which must see every limit or enforcement silently stops. Sharing it with a
    read surface handed a fenced caller a row per issuer-named limit, disclosing its existence and
    its `code` (which a maker would plausibly name after the issuer). The fence belongs where the
    disclosure is, not where the enforcement is."""
    holder, fenced = _principals_either_side_of_the_fence(ctx)
    lim = _create_issuer_limit(ctx, holder)
    assert _approve(ctx, lim["id"], ctx["approver"]).status_code == 200  # ACTIVE => in health

    fenced_health = ctx["client"].get("/limits/health", headers=_hdr(fenced, ctx["tenant"])).json()
    assert lim["id"] not in {h["limit_id"] for h in fenced_health}
    assert lim["code"] not in {h["code"] for h in fenced_health}

    # POSITIVE CONTROL — the holder sees the health row, so the exclusion is the fence and not
    # `limit_health` having stopped reporting concentration limits altogether.
    holder_health = ctx["client"].get("/limits/health", headers=_hdr(holder, ctx["tenant"])).json()
    assert lim["id"] in {h["limit_id"] for h in holder_health}


def test_a_non_issuer_concentration_limit_is_visible_to_everyone(ctx) -> None:
    """The fence keys on issuer identity, NOT on the concentration family. A sector limit carries
    no proprietary identity and must not be swept up — otherwise the fence would quietly hide the
    slice's headline feature from most of its users."""
    _holder, fenced = _principals_either_side_of_the_fence(ctx)
    body = {
        "code": f"TECH-{uuid.uuid4().hex[:6]}",
        "name": "tech <= 20%",
        "target_run_type": "CONCENTRATION",
        "metric_type": "SHARE",
        "scope_portfolio_id": ctx["pf"],
        "threshold_value": "0.20",
        "threshold_unit": "FRACTION",
        "breach_direction": "ABOVE",
        "limit_kind": "HARD",
        "dimension_kind": "SECTOR_INDUSTRY",
        "bucket_code": "J",
        "scheme_family": "ISIC",
        "authored_scheme_id": str(uuid.uuid4()),
        "denominator_basis": "INVESTED_LONG",
    }
    r = ctx["client"].post("/limits", json=body, headers=_hdr(ctx["maker"], ctx["tenant"]))
    assert r.status_code == 201, r.text
    seen = ctx["client"].get("/limits", headers=_hdr(fenced, ctx["tenant"])).json()
    assert r.json()["id"] in {x["id"] for x in seen}


def test_a_fenced_limit_remains_approvable_and_editable(ctx) -> None:
    """The mutation paths must NOT be fenced: they are separately gated on limit.manage /
    limit.approve, and a fenced load would silently make every named-issuer limit unapprovable —
    a control that cannot be operated is a control that does not exist."""
    holder, _fenced = _principals_either_side_of_the_fence(ctx)
    lim = _create_issuer_limit(ctx, holder)
    # The approver holds _ALL — i.e. limit.approve WITHOUT concentration.issuer.view.
    assert _approve(ctx, lim["id"], ctx["approver"]).status_code == 200
    patched = ctx["client"].patch(
        f"/limits/{lim['id']}",
        json={"name": "renamed"},
        headers=_hdr(ctx["maker"], ctx["tenant"]),
    )
    assert patched.status_code == 200, patched.text
