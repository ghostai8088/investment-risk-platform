"""REPRO-2 — the schedule WRITE path at the wire, and the pause adjudication made real.

The write path is what makes CTRL-018 startable: before it, a schedule existed only if a proof
harness or a demo script wrote one directly. These tests prove the surface honors what the gate
ratified — the permission fence, the duplicate refusal that does NOT arrive as a 500, and the one
that carries the adjudication: **pausing every reproduction schedule turns the alarm-health
surface RED**, because a one-person reversible switch-off of the platform's only drift detector
must not read as a quiet night.
"""

from __future__ import annotations

import os
import uuid
import warnings
from datetime import date

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
from irp_shared.reproduction.models import RUN_TYPE_REPRODUCTION  # noqa: E402
from irp_shared.tenancy.models import Tenant  # noqa: E402

with warnings.catch_warnings():
    warnings.simplefilter("ignore")
    from irp_backend.main import app


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


def _tenant(db: Session) -> str:
    tid = str(uuid.uuid4())
    db.add(
        Tenant(
            id=tid,
            code=f"t{uuid.uuid4().hex[:8]}",
            display_name="T",
            status="ACTIVE",
            provenance="ONBOARDED",
        )
    )
    db.flush()
    return tid


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
        external_subject=f"u{uuid.uuid4().hex[:6]}@x",
        display_name="U",
        is_active=True,
    )
    db.add(user)
    db.flush()
    db.add(UserRole(id=str(uuid.uuid4()), tenant_id=tenant_id, user_id=user.id, role_id=role.id))
    db.flush()
    return user.id


def _payload(code: str = "nightly-repro") -> dict:
    return {
        "code": code,
        "name": "Nightly reproduction",
        "target_run_type": RUN_TYPE_REPRODUCTION,
        "environment_id": "local",
        "anchor_date": str(date(2026, 1, 1)),
        "cadence_kind": "INTERVAL",
        "interval_days": 1,
    }


def test_a_schedule_manage_holder_CREATES_a_schedule(wired) -> None:  # noqa: ANN001
    """The forward gate, discharged: the maker verb finally has a route."""
    client, db = wired
    tid = _tenant(db)
    uid = _user_with(db, tid, "schedule.manage")
    db.commit()

    resp = client.post(
        "/schedules", json=_payload(), headers={"X-User-Id": uid, "X-Tenant-Id": tid}
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["status"] == "ACTIVE"
    assert body["target_run_type"] == RUN_TYPE_REPRODUCTION


def test_a_schedule_view_holder_CANNOT_write(wired) -> None:  # noqa: ANN001
    """Reading the ledger is not starting the engine — SCH-1 minted two verbs for a reason."""
    client, db = wired
    tid = _tenant(db)
    uid = _user_with(db, tid, "schedule.view")
    db.commit()
    resp = client.post(
        "/schedules", json=_payload(), headers={"X-User-Id": uid, "X-Tenant-Id": tid}
    )
    assert resp.status_code == 403


def test_a_bare_request_is_401(wired) -> None:  # noqa: ANN001
    client, _db = wired
    assert client.post("/schedules", json=_payload()).status_code == 401


def test_a_DUPLICATE_code_is_a_refusal_not_a_500(wired) -> None:  # noqa: ANN001
    """The uniqueness is a DB constraint, and an uncaught one arrives as a 500 — an operator
    retrying a create should be told what is wrong, not handed a crash."""
    client, db = wired
    tid = _tenant(db)
    uid = _user_with(db, tid, "schedule.manage")
    db.commit()
    headers = {"X-User-Id": uid, "X-Tenant-Id": tid}
    assert client.post("/schedules", json=_payload(), headers=headers).status_code == 201
    second = client.post("/schedules", json=_payload(), headers=headers)
    assert second.status_code == 422, second.text
    assert "already exists" in second.text


def test_an_unexpected_field_is_REFUSED_not_ignored(wired) -> None:  # noqa: ANN001
    client, db = wired
    tid = _tenant(db)
    uid = _user_with(db, tid, "schedule.manage")
    db.commit()
    resp = client.post(
        "/schedules",
        json={**_payload(), "status": "PAUSED"},
        headers={"X-User-Id": uid, "X-Tenant-Id": tid},
    )
    assert resp.status_code == 422


def test_PAUSING_the_only_schedule_turns_the_health_surface_RED(wired) -> None:  # noqa: ANN001
    """THE adjudication, end to end at the wire.

    The gate answered the maker-checker question by ADJUDICATING pause rather than waving it
    through: it stays a one-person act, and the compensating control is that switching the
    detector off is impossible to miss. This is that compensation, proven through both surfaces —
    the write path pauses, the health read reddens.
    """
    client, db = wired
    tid = _tenant(db)
    uid = _user_with(db, tid, "schedule.manage", "schedule.view")
    db.commit()
    headers = {"X-User-Id": uid, "X-Tenant-Id": tid}

    created = client.post("/schedules", json=_payload(), headers=headers)
    assert created.status_code == 201
    schedule_id = created.json()["id"]

    # Configured and running: the control is on.
    before = client.get("/reproduction/alarm-health", headers=headers).json()
    assert before["control_switched_off"] is False

    paused = client.post(f"/schedules/{schedule_id}/pause", headers=headers)
    assert paused.status_code == 200, paused.text
    assert paused.json()["status"] == "PAUSED"

    after = client.get("/reproduction/alarm-health", headers=headers).json()
    assert after["control_switched_off"] is True
    assert after["healthy"] is False, (
        "every reproduction schedule is paused and the surface still reads healthy — the silent "
        "green a one-person switch-off would hide behind"
    )

    # And RESUMING restores it — the twin, so 'red' is not just 'red forever'.
    resumed = client.post(f"/schedules/{schedule_id}/resume", headers=headers)
    assert resumed.status_code == 200
    restored = client.get("/reproduction/alarm-health", headers=headers).json()
    assert restored["control_switched_off"] is False


def test_a_schedule_in_ANOTHER_tenant_cannot_be_paused(wired) -> None:  # noqa: ANN001
    """Tenant-locality, with a live second tenant; absent and foreign are the same refusal."""
    client, db = wired
    tid_a = _tenant(db)
    tid_b = _tenant(db)
    uid_a = _user_with(db, tid_a, "schedule.manage")
    uid_b = _user_with(db, tid_b, "schedule.manage")
    db.commit()

    created = client.post(
        "/schedules", json=_payload(), headers={"X-User-Id": uid_b, "X-Tenant-Id": tid_b}
    )
    assert created.status_code == 201
    foreign_id = created.json()["id"]

    resp = client.post(
        f"/schedules/{foreign_id}/pause", headers={"X-User-Id": uid_a, "X-Tenant-Id": tid_a}
    )
    assert resp.status_code == 422
    assert "not found in this tenant" in resp.text


def test_a_duplicate_that_races_PAST_the_pre_check_is_still_a_refusal(  # noqa: ANN201
    wired, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The mechanism the pre-check CANNOT deliver, tested directly.

    Under READ COMMITTED two concurrent creates both pass any pre-check and the loser dies at
    flush. The route therefore catches the unique violation and maps it to the SAME refusal — and
    this test exists because the mutation battery proved the catch had no test at all: deleting it
    left every duplicate test green, since they all take the pre-check path.

    The exception is injected rather than raced: the race itself is a PostgreSQL proof, and what
    is checked here is the mapping — an IntegrityError from the write must reach the caller as the
    refusal, never as a 500.
    """
    from sqlalchemy.exc import IntegrityError

    from irp_shared.scheduling.service import create_schedule as real_create

    client, db = wired
    tid = _tenant(db)
    uid = _user_with(db, tid, "schedule.manage")
    db.commit()

    def _racing_winner_commits_then_we_lose(session, *a: object, **k: object) -> None:  # noqa: ANN001
        # The race, simulated at the seam: the OTHER request's row lands and COMMITS (a real
        # winner's commit survives our rollback — committing here is what models that in a
        # single-session harness), and OUR write dies on the unique constraint.
        real_create(session, *a, **k)
        session.commit()
        raise IntegrityError("INSERT ...", {}, Exception("uq_schedule_tenant_code"))

    monkeypatch.setattr(
        "irp_backend.api.schedule_admin.create_schedule", _racing_winner_commits_then_we_lose
    )
    resp = client.post(
        "/schedules", json=_payload(), headers={"X-User-Id": uid, "X-Tenant-Id": tid}
    )
    assert resp.status_code == 422, (
        f"a unique-violation from the write escaped as {resp.status_code} — an operator retrying "
        "a create gets a crash instead of being told what is wrong"
    )
    assert "already exists" in resp.text


def test_a_NON_duplicate_integrity_violation_does_not_LIE_about_its_cause(  # noqa: ANN201
    wired, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The review's twin to the race test: `IntegrityError` is a CLASS, not a diagnosis.

    A foreign-key violation (a calendar id from another tenant surviving to the flush, say) raises
    the same exception as the duplicate race, and the first draft mapped BOTH to "a schedule with
    this code already exists" — a false statement in a governed refusal. The route now asks the
    database which case it is: no visible duplicate means the refusal must not claim one.
    """
    from sqlalchemy.exc import IntegrityError

    client, db = wired
    tid = _tenant(db)
    uid = _user_with(db, tid, "schedule.manage")
    db.commit()

    def _fk_boom(*_a: object, **_k: object) -> None:
        raise IntegrityError("INSERT ...", {}, Exception("fk_schedule_calendar_id"))

    monkeypatch.setattr("irp_backend.api.schedule_admin.create_schedule", _fk_boom)
    resp = client.post(
        "/schedules", json=_payload(), headers={"X-User-Id": uid, "X-Tenant-Id": tid}
    )
    assert resp.status_code == 422
    assert (
        "already exists" not in resp.text
    ), "a non-duplicate constraint violation was reported as a duplicate code — the refusal lied"
    assert "constraint" in resp.text
