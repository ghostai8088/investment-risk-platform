"""Scheduling vocabulary + actor (SCH-1, ENT-061/062 — the schedule control-plane surface).

Two GOVERNED audit codes are minted here — ``SCHEDULE.CREATE`` / ``SCHEDULE.UPDATE`` — the R-07
taxonomy amendment ratified with the SCH-1 decision record (a new ``SCHEDULE`` category, EVT-260
decade; OD-SCH-1-H). They are emitted by CALLING the FROZEN ``audit.service.record_event`` with the
``event_type`` parameter (the ``reference/service.py`` mechanic) — the frozen append engine is
unchanged.

The scheduled RUNS themselves mint NO new code and NO new ``run_type``: a fire re-invokes an
existing family binder (v1 ``run_var``), which appends an ordinary ``CalculationRun`` and reuses
``CALC.RUN_CREATE``/``CALC.RUN_STATUS_CHANGE`` (the governed-run scaffold). The scheduler is
provenance AROUND governed math, never governed math itself.
"""

from __future__ import annotations

from dataclasses import dataclass

#: GOVERNED audit codes (the SCHEDULE / EVT-260 decade) — minted by the SCH-1 R-07 taxonomy
#: amendment and EMITTED (unlike the RESERVED pacing/PRIVATE codes) for schedule config changes.
SCHEDULE_CREATE_EVENT = "SCHEDULE.CREATE"
SCHEDULE_UPDATE_EVENT = "SCHEDULE.UPDATE"

#: The audit ``source_module`` tag for scheduling emits.
SOURCE_MODULE_SCHEDULING = "scheduling"

#: Cadence kinds (controlled vocab, service-enforced). INTERVAL = N calendar days from an anchor
#: (SCH-1 v1). CALENDAR (business-day) is RESERVED for v2 — the calendar substrate carries no
#: business-day logic yet (OD-SCH-1-F).
CADENCE_INTERVAL = "INTERVAL"
CADENCE_CALENDAR_RESERVED = "CALENDAR"
CADENCE_KINDS = frozenset({CADENCE_INTERVAL})

#: Schedule lifecycle status (controlled vocab). Only ACTIVE schedules are selected for dispatch.
SCHEDULE_STATUS_ACTIVE = "ACTIVE"
SCHEDULE_STATUS_PAUSED = "PAUSED"
SCHEDULE_STATUSES = frozenset({SCHEDULE_STATUS_ACTIVE, SCHEDULE_STATUS_PAUSED})

#: ``scheduled_run.outcome`` controlled vocab — the terminal disposition of a dispatch attempt.
OUTCOME_DISPATCHED = "DISPATCHED"
OUTCOME_SKIPPED_DUPLICATE = "SKIPPED_DUPLICATE"
OUTCOME_FAILED = "FAILED"
SCHEDULED_RUN_OUTCOMES = frozenset(
    {OUTCOME_DISPATCHED, OUTCOME_SKIPPED_DUPLICATE, OUTCOME_FAILED}
)

#: The family binders SCH-1 v1 knows how to dispatch, keyed by the ``schedule.target_run_type``. v1
#: ships VaR only (OD-SCH-1-D); active-risk + the other build-in-request families are the recorded
#: v2 generalization (the mechanism is family-agnostic — only the upstream-resolution map differs).
TARGET_RUN_TYPE_VAR = "VAR"
SCHEDULABLE_RUN_TYPES = frozenset({TARGET_RUN_TYPE_VAR})


@dataclass(frozen=True)
class SchedulingActor:
    """The principal that created/edited a schedule (mirrors ``PacingActor``/``ReferenceActor``)."""

    actor_id: str
    actor_type: str = "user"
