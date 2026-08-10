"""ALERT-1 at the wire — the alarm-health read, its permission fence, and its payload shape.

The service tests prove the fields mean what they say; these prove the SURFACE honors the two
promises the ratification made about it: only the five ``schedule.view`` roles can read it, and the
payload carries COUNTS AND BOOLEANS ONLY — no verdict id, no reason text, no ``first_divergence``.

That second one is a disclosure boundary, not a style preference. REPRO-1 carry (n) binds a
redaction residual to the moment a read surface appears over ENT-073, because an UNREPRODUCIBLE
reason can embed a binder's exception text and some binder messages interpolate row identifiers.
This route reads AGGREGATES; the field-set assertion below is what keeps it that way.
"""

from __future__ import annotations

import os
import uuid
import warnings

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

os.environ.setdefault("IRP_AUTH_MODE", "dev_header")
os.environ.setdefault("IRP_APP_ENV", "local")

from irp_shared.db.base import Base  # noqa: E402
from irp_shared.db.session import make_engine, make_session_factory  # noqa: E402
from irp_shared.entitlement.bootstrap import PERMISSIONS, permission_id  # noqa: E402
from irp_shared.entitlement.models import (  # noqa: E402
    AppUser,
    Permission,
    Role,
    RolePermission,
    UserRole,
)
from irp_shared.tenancy.models import Tenant  # noqa: E402

with warnings.catch_warnings():
    warnings.simplefilter("ignore")
    from irp_backend.main import app

#: Exactly what the response may contain. A new field here is a DECISION — the counts-only promise
#: is the discharge of carry (n)'s boundary for this surface, so widening it must be deliberate.
EXPECTED_FIELDS = {
    "healthy",
    "unreadable_rows",
    "lost_verdicts",
    "failed_sweeps",
    "sweep_overdue",
    "dead_channel",
    "undeliverable_attempts",
    "exhausted_verdicts",
    "queued",
    "no_schedule",
    "paused_schedules",
    "nothing_to_reproduce",
    "last_terminal_sweep_at",
}


@pytest.fixture
def wired():  # noqa: ANN201
    from irp_backend.deps import get_db

    engine = make_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    db = make_session_factory(engine)()
    for code, desc in PERMISSIONS:
        db.add(Permission(id=permission_id(code), code=code, description=desc))
    db.flush()
    app.dependency_overrides[get_db] = lambda: db
    try:
        yield TestClient(app), db
    finally:
        app.dependency_overrides.pop(get_db, None)
        db.close()
        engine.dispose()


def _user_with(db: Session, tenant_id: str, *codes: str) -> str:
    role = Role(
        id=str(uuid.uuid4()), tenant_id=tenant_id, code=f"r-{uuid.uuid4().hex[:6]}", name="R"
    )
    db.add(role)
    db.flush()
    for code in codes:
        db.add(
            RolePermission(id=str(uuid.uuid4()), role_id=role.id, permission_id=permission_id(code))
        )
    user = AppUser(
        id=str(uuid.uuid4()),
        tenant_id=tenant_id,
        external_subject=f"u-{uuid.uuid4().hex[:6]}@x",
        display_name="U",
        is_active=True,
    )
    db.add(user)
    db.flush()
    db.add(UserRole(id=str(uuid.uuid4()), tenant_id=tenant_id, user_id=user.id, role_id=role.id))
    db.flush()
    return user.id


def _tenant(db: Session) -> str:
    tid = str(uuid.uuid4())
    db.add(
        Tenant(
            id=tid,
            code=f"t{uuid.uuid4().hex[:6]}",
            display_name="T",
            status="ACTIVE",
            provenance="ONBOARDED",
        )
    )
    db.flush()
    return tid


def test_a_schedule_view_holder_reads_the_health(wired) -> None:  # noqa: ANN001
    client, db = wired
    tid = _tenant(db)
    uid = _user_with(db, tid, "schedule.view")
    db.commit()

    resp = client.get("/reproduction/alarm-health", headers={"X-User-Id": uid, "X-Tenant-Id": tid})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert set(body) == EXPECTED_FIELDS, (
        "the alarm-health payload's field set changed — counts-only is a disclosure boundary "
        "(carry (n)), so a new field is a decision, not a detail"
    )
    # A tenant with nothing at all: no schedule, nothing owed, nothing broken.
    assert body["healthy"] is True
    assert body["no_schedule"] is True
    assert body["queued"] == 0


def test_a_user_without_schedule_view_is_403(wired) -> None:  # noqa: ANN001
    """Deny-by-default. `breach.review` is the ALARM RECIPIENT permission — being paged by the
    channel does not entitle you to audit whether the channel works."""
    client, db = wired
    tid = _tenant(db)
    uid = _user_with(db, tid, "breach.review")
    db.commit()
    resp = client.get("/reproduction/alarm-health", headers={"X-User-Id": uid, "X-Tenant-Id": tid})
    assert resp.status_code == 403


def test_a_TENANT_ADMIN_cannot_read_the_channel_health(wired) -> None:  # noqa: ANN001
    """A ratified decision, pinned so nobody "fixes" it as an oversight.

    `tenant_admin` holds the four tenant-administration verbs and NOT `schedule.view`: a tenant
    administrator administers PEOPLE, not the risk control plane. That was asked and answered at
    the ALERT-1 gate (2026-08-09) with a revisit trigger — the first real operator who needs it —
    so it is a decision with a reason, and this test is what says so to whoever finds it surprising.
    """
    client, db = wired
    tid = _tenant(db)
    uid = _user_with(db, tid, "user.manage", "role.assign", "user.view", "role.approve")
    db.commit()
    resp = client.get("/reproduction/alarm-health", headers={"X-User-Id": uid, "X-Tenant-Id": tid})
    assert resp.status_code == 403


def test_a_bare_request_is_401(wired) -> None:  # noqa: ANN001
    client, _db = wired
    assert client.get("/reproduction/alarm-health").status_code == 401


def test_the_route_is_read_only(wired) -> None:  # noqa: ANN001
    """No write verb exists on this surface — acknowledgement is carry (j)'s slice, not this one."""
    client, db = wired
    tid = _tenant(db)
    uid = _user_with(db, tid, "schedule.view")
    db.commit()
    headers = {"X-User-Id": uid, "X-Tenant-Id": tid}
    assert client.post("/reproduction/alarm-health", headers=headers).status_code == 405
    assert client.delete("/reproduction/alarm-health", headers=headers).status_code == 405
