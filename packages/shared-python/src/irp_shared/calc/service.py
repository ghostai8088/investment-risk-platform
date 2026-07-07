"""Calculation-run create/update utilities. Every lifecycle change is audited (BR-6, BR-12)."""

from __future__ import annotations

from sqlalchemy.orm import Session

from irp_shared.audit.service import record_event
from irp_shared.calc.models import TERMINAL_STATUSES, CalculationRun, RunStatus
from irp_shared.db.mixins import utcnow


def create_run(
    session: Session,
    *,
    tenant_id: str,
    run_type: str,
    initiated_by: str,
    random_seed: int | None = None,
    input_snapshot_id: str | None = None,
    model_version_id: str | None = None,
    assumption_set_id: str | None = None,
    code_version: str | None = None,
    environment_id: str | None = None,
) -> CalculationRun:
    run = CalculationRun(
        tenant_id=str(tenant_id),
        run_type=run_type,
        status=RunStatus.CREATED.value,
        initiated_by=initiated_by,
        random_seed=random_seed,
        input_snapshot_id=input_snapshot_id,
        model_version_id=model_version_id,
        assumption_set_id=assumption_set_id,
        code_version=code_version,
        environment_id=environment_id,
    )
    session.add(run)
    session.flush()

    record_event(
        session,
        event_type="CALC.RUN_CREATE",
        tenant_id=str(tenant_id),
        actor_type="user",
        actor_id=initiated_by,
        source_module="calc",
        entity_type="calculation_run",
        entity_id=run.run_id,
        action="create",
        after_value={"status": run.status, "run_type": run_type},
    )
    return run


def update_run_status(
    session: Session,
    run: CalculationRun,
    new_status: RunStatus,
    *,
    actor_id: str | None = None,
    outcome: str = "success",
    failure_reason: str | None = None,
) -> CalculationRun:
    """Transition the run's ``status`` (in place) and emit ``CALC.RUN_STATUS_CHANGE``.

    ``outcome`` (P2-3, OD-P2-3-F/H — additive, default ``"success"`` so every existing caller is
    behavior-unchanged) forwards to the FROZEN ``record_event``; a P2-3 exposure run passes
    ``outcome="failure"`` on a **post-create FAILED** transition (a gate failing after RUNNING ⇒ the
    FAILED run + this event are committed, with ZERO result rows). ``audit/service.py`` is untouched
    —
    ``record_event`` already accepts ``outcome``."""
    before = run.status
    run.status = new_status.value
    if new_status in TERMINAL_STATUSES:
        run.completed_at = utcnow()
    if failure_reason is not None and new_status is RunStatus.FAILED:
        # P3-C1 (OD-C, additive - default None keeps every existing caller byte-identical; the
        # audit event payload below is deliberately UNCHANGED). FAILED-only by contract: the
        # model comment promises NULL on non-failed runs and readers treat non-NULL as "failed"
        # (the 2026-07 review's footgun guard).
        run.failure_reason = failure_reason
    session.flush()

    record_event(
        session,
        event_type="CALC.RUN_STATUS_CHANGE",
        tenant_id=run.tenant_id,
        actor_type="system" if actor_id is None else "user",
        actor_id=actor_id or "system",
        source_module="calc",
        entity_type="calculation_run",
        entity_id=run.run_id,
        action="status_change",
        before_value={"status": before},
        after_value={"status": run.status},
        outcome=outcome,
    )
    return run
