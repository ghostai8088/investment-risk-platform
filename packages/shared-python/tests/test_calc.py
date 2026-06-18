"""Calculation-run tests: creation, status transitions, and audit emission."""

from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from irp_shared.audit.models import AuditEvent
from irp_shared.audit.service import verify_chain
from irp_shared.calc.models import RunStatus
from irp_shared.calc.service import create_run, update_run_status


def test_create_run_emits_audit(session: Session) -> None:
    tenant = str(uuid.uuid4())
    run = create_run(
        session,
        tenant_id=tenant,
        run_type="foundation.smoke",
        initiated_by="user-1",
        random_seed=42,
    )
    assert run.status == RunStatus.CREATED.value
    assert run.random_seed == 42
    assert run.run_id is not None

    events = session.query(AuditEvent).filter(AuditEvent.event_type == "CALC.RUN_CREATE").all()
    assert len(events) == 1
    assert events[0].entity_id == run.run_id


def test_status_change_sets_completed_and_audits(session: Session) -> None:
    tenant = str(uuid.uuid4())
    run = create_run(session, tenant_id=tenant, run_type="foundation.smoke", initiated_by="user-1")

    update_run_status(session, run, RunStatus.RUNNING, actor_id="user-1")
    assert run.completed_at is None

    update_run_status(session, run, RunStatus.COMPLETED, actor_id="user-1")
    assert run.status == RunStatus.COMPLETED.value
    assert run.completed_at is not None

    changes = (
        session.query(AuditEvent).filter(AuditEvent.event_type == "CALC.RUN_STATUS_CHANGE").all()
    )
    assert len(changes) == 2
    # Full trail: 1 create + 2 status changes, chain intact.
    assert session.query(AuditEvent).count() == 3
    assert verify_chain(session, tenant).ok is True
