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

from irp_backend.api.reproduction import UNREPRODUCIBLE_WIRE_DETAIL  # noqa: E402
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
    # REPRO-2: the ratified ALERT-1 amendment. This pin is BY DESIGN the place a new field must
    # be declared — widening the payload is a decision, and this is where the decision is made.
    "control_switched_off",
    "undeliverable_attempts",
    # Wave-17 close, BLOCKING 2. Declared here deliberately, per the sentence above: a COUNT of
    # ticks that fired and did not land. It discloses no identifier and no payload — the carry-(n)
    # counts-only boundary is unchanged.
    "failed_dispatches",
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


# --------------------------------------------------- the verdict read, and carry (n)'s discharge
def _seed_verdict(db: Session, tenant_id: str, *, verdict: str, first_divergence: str | None):  # noqa: ANN202
    from irp_shared.calc.models import CalculationRun, RunStatus
    from irp_shared.reproduction.models import RUN_TYPE_REPRODUCTION, ReproductionCheck

    run = CalculationRun(
        tenant_id=tenant_id,
        run_type=RUN_TYPE_REPRODUCTION,
        status=RunStatus.COMPLETED.value,
        initiated_by="t",
    )
    subject = CalculationRun(
        tenant_id=tenant_id, run_type="VAR", status=RunStatus.COMPLETED.value, initiated_by="t"
    )
    db.add_all([run, subject])
    db.flush()
    check = ReproductionCheck(
        tenant_id=tenant_id,
        calculation_run_id=run.run_id,
        subject_run_id=subject.run_id,
        family_key="VAR",
        verdict=verdict,
        rows_compared=2,
        rows_diverged=1 if verdict == "DIVERGED" else 0,
        first_divergence=first_divergence,
    )
    db.add(check)
    db.flush()
    return check


def test_the_verdict_list_reads_for_a_schedule_view_holder(wired) -> None:  # noqa: ANN001
    client, db = wired
    tid = _tenant(db)
    uid = _user_with(db, tid, "schedule.view")
    _seed_verdict(db, tid, verdict="MATCH", first_divergence=None)
    db.commit()
    resp = client.get("/reproduction/checks", headers={"X-User-Id": uid, "X-Tenant-Id": tid})
    assert resp.status_code == 200, resp.text
    assert len(resp.json()) == 1
    assert resp.json()[0]["verdict"] == "MATCH"


def test_a_DIVERGED_row_carries_its_field_and_key_label(wired) -> None:  # noqa: ANN001
    """The half that must still be USEFUL: a divergence an operator cannot locate is not a
    finding. REPRO-1 mutation-proved this label names the row key and the field, never values."""
    client, db = wired
    tid = _tenant(db)
    uid = _user_with(db, tid, "schedule.view")
    _seed_verdict(
        db, tid, verdict="DIVERGED", first_divergence="key=(pf-1,2026-08-01) field=var_value"
    )
    db.commit()
    body = client.get("/reproduction/checks", headers={"X-User-Id": uid, "X-Tenant-Id": tid}).json()
    assert body[0]["first_divergence"] == "key=(pf-1,2026-08-01) field=var_value"


def test_an_UNREPRODUCIBLE_rows_stored_text_NEVER_reaches_the_wire(wired) -> None:  # noqa: ANN001
    """CARRY (n)'s DISCHARGE, asserted the only way it can be: with the positive twin first.

    The marker is planted in the STORED row (proving the harness delivered its input — a negative
    control whose precondition never landed proves nothing), and only then is its ABSENCE from the
    entire HTTP response asserted. The wire carries a fixed literal instead, which is why this is
    discharge by EXCLUSION: no parsing, no redaction, nothing that could be defeated by an
    exception message shaped unlike the ones we imagined.
    """
    client, db = wired
    tid = _tenant(db)
    uid = _user_with(db, tid, "schedule.view")
    marker = "ROW-IDENTIFIER-9f3a-LEAK-CANARY"
    stored = _seed_verdict(
        db,
        tid,
        verdict="UNREPRODUCIBLE",
        first_divergence=f"OperationalError: relation missing for {marker}",
    )
    db.commit()

    # POSITIVE TWIN: the marker really is in the stored row.
    assert marker in (stored.first_divergence or ""), "the harness never planted the marker"

    resp = client.get("/reproduction/checks", headers={"X-User-Id": uid, "X-Tenant-Id": tid})
    assert resp.status_code == 200
    assert marker not in resp.text, (
        "stored UNREPRODUCIBLE text reached the wire — carry (n)'s residual is live on a read "
        "surface, which is the exact thing the carry bound"
    )
    assert resp.json()[0]["first_divergence"] == UNREPRODUCIBLE_WIRE_DETAIL


def test_the_verdict_list_is_TENANT_LOCAL(wired) -> None:  # noqa: ANN001
    client, db = wired
    tid_a = _tenant(db)
    tid_b = _tenant(db)
    uid_a = _user_with(db, tid_a, "schedule.view")
    _seed_verdict(db, tid_b, verdict="DIVERGED", first_divergence="key=(x) field=y")
    db.commit()
    body = client.get(
        "/reproduction/checks", headers={"X-User-Id": uid_a, "X-Tenant-Id": tid_a}
    ).json()
    assert body == [], "another tenant's verdicts were listed"


def test_the_verdict_list_needs_schedule_view(wired) -> None:  # noqa: ANN001
    client, db = wired
    tid = _tenant(db)
    uid = _user_with(db, tid, "breach.review")
    db.commit()
    resp = client.get("/reproduction/checks", headers={"X-User-Id": uid, "X-Tenant-Id": tid})
    assert resp.status_code == 403
