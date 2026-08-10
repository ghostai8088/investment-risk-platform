"""ONBOARD-1a — the provisioning route and the SYSTEM-tenant fence.

Two things are proven here that nothing else can:

**The fence.** Seeding the platform operator makes the SYSTEM tenant authenticatable for the first
time in the platform's life. Before this slice nothing refused a SYSTEM tenant claim; it 401'd only
because no SYSTEM ``app_user`` existed. From the moment one does, any token an IdP signs with that
claim resolves — so the allow-list in ``deps.py`` is what keeps such a token worth the provisioning
surface and nothing else. The tests below are its firing proof, with the positive control that the
same principal DOES reach provisioning (without which "refused everywhere" is equally consistent
with a principal that cannot authenticate at all).

**The guard is visible to the census.** ``POST /tenants`` uses the ordinary
``require_permission`` dependency rather than an inline check, precisely so the platform-wide
route→permission census can see it. A first draft did the inline version and would have made the
single most privileged route in the platform the one route the census could not classify.
"""

from __future__ import annotations

import os
import uuid
import warnings

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

os.environ.setdefault("IRP_AUTH_MODE", "dev_header")
os.environ.setdefault("IRP_APP_ENV", "local")

from irp_shared.entitlement.bootstrap import (  # noqa: E402
    PERMISSIONS,
    ROLE_TEMPLATES,
    SYSTEM_TENANT_ID,
    permission_id,
    role_id,
    role_permission_id,
)
from irp_shared.entitlement.models import (  # noqa: E402
    AppUser,
    Permission,
    Role,
    RolePermission,
    UserRole,
)
from irp_shared.entitlement.platform_catalog import (  # noqa: E402
    PLATFORM_OPERATOR_ROLE,
    PLATFORM_PERMISSIONS,
    PLATFORM_ROLES,
    platform_permission_id,
    platform_role_id,
    platform_role_permission_id,
)
from irp_shared.tenancy.models import Tenant  # noqa: E402

with warnings.catch_warnings():
    warnings.simplefilter("ignore")
    from irp_backend.main import app


def _seed(db: Session) -> tuple[str, str]:
    """Seed the SYSTEM catalog and one platform operator. Returns (operator_id, tenant_admin_id)."""
    for code, desc in PERMISSIONS:
        db.add(Permission(id=permission_id(code), code=code, description=desc))
    for code, desc in PLATFORM_PERMISSIONS:
        db.add(Permission(id=platform_permission_id(code), code=code, description=desc))
    db.flush()
    for name, codes in ROLE_TEMPLATES.items():
        db.add(Role(id=role_id(name), tenant_id=SYSTEM_TENANT_ID, code=name, name=name.title()))
        for code in codes:
            db.add(
                RolePermission(
                    id=role_permission_id(name, code),
                    role_id=role_id(name),
                    permission_id=permission_id(code),
                )
            )
    for name, codes in PLATFORM_ROLES.items():
        db.add(
            Role(
                id=platform_role_id(name),
                tenant_id=SYSTEM_TENANT_ID,
                code=name,
                name=name.title(),
            )
        )
        for code in codes:
            db.add(
                RolePermission(
                    id=platform_role_permission_id(name, code),
                    role_id=platform_role_id(name),
                    permission_id=platform_permission_id(code),
                )
            )
    db.add(
        Tenant(
            id=SYSTEM_TENANT_ID,
            code="system",
            display_name="System",
            status="SYSTEM",
            provenance="0067_system",
        )
    )
    operator = AppUser(
        id=str(uuid.uuid4()),
        tenant_id=SYSTEM_TENANT_ID,
        external_subject="auth0|operator",
        display_name="Platform Operator",
        is_active=True,
    )
    db.add(operator)
    db.flush()
    db.add(
        UserRole(
            id=str(uuid.uuid4()),
            tenant_id=SYSTEM_TENANT_ID,
            user_id=operator.id,
            role_id=platform_role_id(PLATFORM_OPERATOR_ROLE),
        )
    )
    db.flush()
    return operator.id, str(uuid.uuid4())


@pytest.fixture
def wired():  # noqa: ANN201
    """The REAL app with an overridden session.

    Not a throwaway ``FastAPI()`` carrying only this router (the shipped idiom for endpoint tests):
    the fence test must reach a DATA router to prove a SYSTEM principal is refused there, and a
    single-router app has none. Using the real app is what makes the refusal meaningful.
    """

    from sqlalchemy.pool import StaticPool

    from irp_backend.deps import get_db
    from irp_shared.db.base import Base
    from irp_shared.db.session import make_engine, make_session_factory

    engine = make_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    db = make_session_factory(engine)()
    app.dependency_overrides[get_db] = lambda: db
    try:
        yield TestClient(app), db
    finally:
        app.dependency_overrides.pop(get_db, None)
        db.close()
        engine.dispose()


def _operator_headers(uid: str) -> dict[str, str]:
    return {"X-User-Id": uid, "X-Tenant-Id": SYSTEM_TENANT_ID}


def test_the_operator_can_create_a_tenant(wired) -> None:  # noqa: ANN001
    client, db = wired
    operator_id, _ = _seed(db)
    db.commit()

    resp = client.post(
        "/tenants",
        json={
            "code": "acme",
            "display_name": "Acme AM",
            "admin_external_subject": "auth0|acme-admin",
            "admin_display_name": "Ada Admin",
        },
        headers=_operator_headers(operator_id),
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["code"] == "acme"
    assert body["admin_role"] == "tenant_admin"
    # REPRO-2 changed WHAT the follow-up is, and this pin changed with it rather than being
    # deleted: the tenant now ticks automatically (registry discovery), so telling an operator to
    # edit IRP_TENANT_IDS would be false instructions in a governed response. What remains true —
    # and what an operator still must be told — is that nothing is SCHEDULED yet.
    followup = body["operator_followup"]
    assert (
        "IRP_TENANT_IDS" not in followup
    ), "the response still tells the operator to hand-edit worker config — superseded at REPRO-2"
    assert "schedule" in followup.lower(), (
        "the response must state the operator's real follow-up step: a created tenant is ticked "
        "but has nothing scheduled, and a consequence nobody is told about is a silent one"
    )
    assert set(body["roles_cloned"]) and "platform_admin" not in body["roles_cloned"]


def test_a_SYSTEM_principal_is_REFUSED_on_a_data_router(wired) -> None:  # noqa: ANN001
    """THE FENCE. The same principal that may provision may not read a portfolio."""
    client, db = wired
    operator_id, _ = _seed(db)
    db.commit()

    refused = client.get("/portfolios", headers=_operator_headers(operator_id))
    assert refused.status_code == 401, (
        f"a SYSTEM-tenant principal reached a data router ({refused.status_code}) — the fence is "
        "not covering it, and an IdP-signed SYSTEM claim now buys the whole platform"
    )


def test_the_SAME_principal_IS_admitted_on_provisioning(wired) -> None:  # noqa: ANN001
    """The discriminating positive control (P18).

    Without it, the refusal above is equally consistent with a principal that cannot authenticate
    at all — which would make the fence look perfect while proving nothing about it.
    """
    client, db = wired
    operator_id, _ = _seed(db)
    db.commit()
    resp = client.post(
        "/tenants",
        json={
            "code": "fence-positive",
            "display_name": "Fence Positive",
            "admin_external_subject": "auth0|fp",
            "admin_display_name": "FP",
        },
        headers=_operator_headers(operator_id),
    )
    assert resp.status_code == 201, resp.text


def test_a_TENANT_principal_cannot_create_a_tenant(wired) -> None:  # noqa: ANN001
    """Deny-by-default over the platform catalog: a normal tenant user holds no platform code.

    This is the escalation the whole catalog split exists to prevent, asserted at the wire.
    """
    client, db = wired
    _seed(db)
    tenant_id = str(uuid.uuid4())
    user = AppUser(
        id=str(uuid.uuid4()),
        tenant_id=tenant_id,
        external_subject="auth0|normal",
        display_name="Normal",
        is_active=True,
    )
    db.add(user)
    db.add(
        Tenant(
            id=tenant_id,
            code="normal",
            display_name="Normal",
            status="ACTIVE",
            provenance="ONBOARDED",
        )
    )
    db.flush()
    # Give them the FULL platform_admin clone — the most privileged thing a tenant can hold.
    db.add(Role(id=str(uuid.uuid4()), tenant_id=tenant_id, code="platform_admin", name="PA"))
    db.commit()

    resp = client.post(
        "/tenants",
        json={
            "code": "escalated",
            "display_name": "Escalated",
            "admin_external_subject": "auth0|e",
            "admin_display_name": "E",
        },
        headers={"X-User-Id": user.id, "X-Tenant-Id": tenant_id},
    )
    assert resp.status_code == 403, resp.text


def test_a_duplicate_code_is_a_422_with_nothing_created(wired) -> None:  # noqa: ANN001
    client, db = wired
    operator_id, _ = _seed(db)
    db.commit()
    payload = {
        "code": "dup",
        "display_name": "Dup",
        "admin_external_subject": "auth0|d1",
        "admin_display_name": "D1",
    }
    assert (
        client.post("/tenants", json=payload, headers=_operator_headers(operator_id)).status_code
        == 201
    )
    before = db.execute(select(Tenant.id)).scalars().all()

    resp = client.post(
        "/tenants",
        json={**payload, "admin_external_subject": "auth0|d2"},
        headers=_operator_headers(operator_id),
    )
    assert resp.status_code == 422, resp.text
    db.expire_all()
    assert set(db.execute(select(Tenant.id)).scalars().all()) == set(before)


def test_an_unexpected_field_is_REFUSED_not_ignored(wired) -> None:  # noqa: ANN001
    """``extra='forbid'``: a caller who thinks they set the status must not be silently ignored."""
    client, db = wired
    operator_id, _ = _seed(db)
    db.commit()
    resp = client.post(
        "/tenants",
        json={
            "code": "extra",
            "display_name": "Extra",
            "admin_external_subject": "auth0|x",
            "admin_display_name": "X",
            "status": "SUSPENDED",
        },
        headers=_operator_headers(operator_id),
    )
    assert resp.status_code == 422
