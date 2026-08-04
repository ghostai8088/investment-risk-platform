"""The `/classification/assignments` list endpoint — first route-level coverage.

The Wave-14 close found this route had ZERO tests anywhere (the P11 class: a shipped surface
nobody ever counted). Added with the close fold that wired the endpoint's current-heads path to
``classification.service.list_assignments`` — which is what gives the route its refusal: the
hand-rolled filter it replaced returned a SILENT [] for a typo'd ``dimension_kind``, so "no such
kind" read as "a clean book" (the vacuous-read class).

SQLite has no RLS; tenancy floors live in the PG tier. This file proves the wiring, the refusal,
and the 403 deny-by-default.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from irp_backend.api.classification import router as classification_router
from irp_backend.deps import get_db
from irp_shared.classification.models import (
    DIMENSION_KIND_LIQUIDITY_TIER,
    SCHEME_FAMILY_SEC_22E4,
)
from irp_shared.classification.service import (
    ClassificationActor,
    capture_assignment,
    create_node,
    create_scheme,
)
from irp_shared.db.session import make_engine, make_session_factory
from irp_shared.entitlement.models import AppUser, Permission, Role, RolePermission, UserRole
from irp_shared.entitlement.service import Principal
from irp_shared.models import Base

_PERMS = ("reference.classification_assignment.view",)


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
    db.commit()

    actor = ClassificationActor(tenant_id=tenant_id, actor_id="steward")
    scheme = create_scheme(
        db,
        actor=actor,
        scheme_family=SCHEME_FAMILY_SEC_22E4,
        version_label="2024",
        name="SEC 22e-4",
        dimension_kind=DIMENSION_KIND_LIQUIDITY_TIER,
        authority="SEC",
    )
    create_node(db, actor=actor, scheme_id=scheme.id, code="ILLIQUID", name="Illiquid", level=1)
    instrument = str(uuid.uuid4())
    capture_assignment(
        db,
        actor=actor,
        entity_type="instrument",
        entity_id=instrument,
        scheme_id=scheme.id,
        dimension_kind=DIMENSION_KIND_LIQUIDITY_TIER,
        node_code="ILLIQUID",
    )
    db.commit()
    principal = Principal(user_id=user.id, tenant_id=tenant_id)

    def _override_db() -> Iterator[Session]:
        yield db

    app = FastAPI()
    app.include_router(classification_router)
    app.dependency_overrides[get_db] = _override_db
    try:
        yield TestClient(app), principal, db, instrument
    finally:
        db.close()
        engine.dispose()


def _h(p: Principal) -> dict[str, str]:
    return {"X-User-Id": p.user_id, "X-Tenant-Id": p.tenant_id}


def test_the_current_heads_path_lists_through_the_service_verb(ctx) -> None:  # noqa: ANN001
    client, p, _db, instrument = ctx
    resp = client.get(
        "/classification/assignments",
        params={"entity_id": instrument, "dimension_kind": DIMENSION_KIND_LIQUIDITY_TIER},
        headers=_h(p),
    )
    assert resp.status_code == 200, resp.text
    rows = resp.json()
    assert len(rows) == 1
    assert rows[0]["node_code"] == "ILLIQUID"


def test_a_typoed_dimension_kind_is_a_422_not_a_silent_empty_list(ctx) -> None:  # noqa: ANN001
    """The P9 fire test for the wiring's refusal.

    Before the fold this returned 200 [] — "no such kind" indistinguishable from "a clean book".
    The service verb refuses, and the endpoint maps it to 422 with the kind named.
    """
    client, p, _db, _instrument = ctx
    resp = client.get(
        "/classification/assignments",
        params={"dimension_kind": "LIQUIDTY_TIER"},  # the typo
        headers=_h(p),
    )
    assert resp.status_code == 422, resp.text
    assert "dimension_kind" in resp.json()["detail"]


def test_deny_by_default(ctx) -> None:  # noqa: ANN001
    client, p, _db, _instrument = ctx
    resp = client.get(
        "/classification/assignments",
        headers={"X-User-Id": str(uuid.uuid4()), "X-Tenant-Id": p.tenant_id},
    )
    assert resp.status_code == 403


def test_the_valid_at_branch_keeps_its_own_contract(ctx) -> None:  # noqa: ANN001
    """The as_of branch is DELIBERATELY not wired to the verb: its ratified contract is the
    valid-axis instant on the current system view, a different axis pairing from the verb's
    known_at. This pin stops a helpful refactor from silently changing a shipped read's meaning."""
    client, p, _db, instrument = ctx
    resp = client.get(
        "/classification/assignments",
        params={"entity_id": instrument, "as_of": datetime(2030, 1, 1, tzinfo=UTC).isoformat()},
        headers=_h(p),
    )
    assert resp.status_code == 200
    assert len(resp.json()) == 1
