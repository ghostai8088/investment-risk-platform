"""Scheduling vocabulary + actor (SCH-1, ENT-061/062 — the schedule control-plane surface).

Two GOVERNED audit codes are minted here — ``SCHEDULE.CREATE`` / ``SCHEDULE.UPDATE`` — the R-07
taxonomy amendment ratified with the SCH-1 decision record (a new ``SCHEDULE`` category, EVT-260
decade; OD-SCH-1-H). They are emitted by CALLING the FROZEN ``audit.service.record_event`` with the
``event_type`` parameter (the ``reference/service.py`` mechanic) — the frozen append engine is
unchanged.

The scheduled RUNS themselves mint NO new code and NO new ``run_type``: a fire re-invokes an
existing family binder, which appends an ordinary ``CalculationRun`` and reuses
``CALC.RUN_CREATE``/``CALC.RUN_STATUS_CHANGE`` (the governed-run scaffold). The scheduler is
provenance AROUND governed math, never governed math itself.

**SCH-2 (Wave-13 slice 0)** widened this from SCH-1's "v1 = VAR only, INTERVAL only": a second
family (``EXPOSURE_AGGREGATE``) and a second cadence (``CALENDAR_MONTH_END``) ship here, and the
family set moved OUT of this module. ``SCHEDULABLE_RUN_TYPES`` is now DERIVED from the dispatch
registry in ``scheduling.service`` (OD-SCH-2-D/F) — it cannot live here, because the registry must
import the family binders and this module is a leaf vocabulary that ``irp_worker`` imports for
two outcome constants (``OUTCOME_FAILED``, ``OUTCOME_SKIPPED_DUPLICATE`` — count verified at the
SCH-2 4-finder review; an earlier draft said three). This module keeps only the
``TARGET_RUN_TYPE_*`` literals.
"""

from __future__ import annotations

from dataclasses import dataclass

#: GOVERNED audit codes (the SCHEDULE / EVT-260 decade) — minted by the SCH-1 R-07 taxonomy
#: amendment and EMITTED (unlike the RESERVED pacing/PRIVATE codes) for schedule config changes.
SCHEDULE_CREATE_EVENT = "SCHEDULE.CREATE"
SCHEDULE_UPDATE_EVENT = "SCHEDULE.UPDATE"

#: The audit ``source_module`` tag for scheduling emits.
SOURCE_MODULE_SCHEDULING = "scheduling"

#: Cadence kinds (controlled vocab, service- AND DB-enforced since SCH-2). INTERVAL = N calendar
#: days from an anchor (SCH-1). CALENDAR_MONTH_END = the LAST WEEKDAY of each calendar month, at
#: END of that day (SCH-2, OD-SCH-2-C) — the QS-11 ``preceding`` rolling convention over a
#: WEEKEND-ONLY non-business-day predicate.
#:
#: Why last-weekday and not the calendar month end: 30.6% of calendar month-ends 2025-2027 fall on
#: a weekend, and an exposure run struck on a non-trading day has no marks, so it FAILS — and RM-1
#: refuses a return series with a missing interior month-end, so ONE miss poisons the downstream
#: governed number. The weekday rule cuts that to holiday collisions only (4 of 144 months,
#: 2.8%, over 2024-2035: 2024-03-29, 2027-05-31, 2029-03-30, 2032-05-31 — a RECORDED limitation
#: OF THIS KIND, retirable per schedule since CAL-1b: ``BUSINESS_MONTH_END`` below is the
#: holiday-aware resolution that completes QS-11's holiday leg; it
#: rides Wave-14 real-data onboarding, where the holiday reference data arrives.
#:
#: ``CALENDAR`` stays RESERVED-and-unused for a general business-day cadence (OD-SCH-1-F) — SCH-2
#: deliberately does NOT reuse the name for the month-end kind, which is a different concept.
CADENCE_INTERVAL = "INTERVAL"
CADENCE_CALENDAR_MONTH_END = "CALENDAR_MONTH_END"
#: CAL-1b: the holiday-aware last-BUSINESS-day month-end grid (QS-11 ``preceding``, full ENT-006
#: resolution). 18 chars — inside the ``String(20)`` column ceiling. ``CALENDAR_MONTH_END`` is
#: GRANDFATHERED (the v1/v2 label pattern): live grids never move; the transition for an existing
#: schedule is pause-and-recreate under the new kind (OQ-CAL-1-3's named runbook path).
CADENCE_BUSINESS_MONTH_END = "BUSINESS_MONTH_END"
CADENCE_CALENDAR_RESERVED = "CALENDAR"
CADENCE_KINDS = frozenset(
    {CADENCE_INTERVAL, CADENCE_CALENDAR_MONTH_END, CADENCE_BUSINESS_MONTH_END}
)

#: Schedule lifecycle status (controlled vocab). Only ACTIVE schedules are selected for dispatch.
SCHEDULE_STATUS_ACTIVE = "ACTIVE"
SCHEDULE_STATUS_PAUSED = "PAUSED"
SCHEDULE_STATUSES = frozenset({SCHEDULE_STATUS_ACTIVE, SCHEDULE_STATUS_PAUSED})

#: ``scheduled_run.outcome`` controlled vocab — the terminal disposition of a dispatch attempt.
OUTCOME_DISPATCHED = "DISPATCHED"
OUTCOME_SKIPPED_DUPLICATE = "SKIPPED_DUPLICATE"
OUTCOME_FAILED = "FAILED"
SCHEDULED_RUN_OUTCOMES = frozenset({OUTCOME_DISPATCHED, OUTCOME_SKIPPED_DUPLICATE, OUTCOME_FAILED})

#: ``schedule.target_run_type`` values. **These are the REAL ``calculation_run.run_type`` strings**
#: (OD-SCH-2-H / OQ-SCH-2-8 = A), not a parallel vocabulary: the same column name already ships on
#: ``limit_definition`` and ``breach`` holding actual run_types, and is rendered in the OPS-1 UI, so
#: minting a short ``"EXPOSURE"`` here would put two meanings behind one column name across three
#: entities. ``VAR`` was already the run_type by accident; ``EXPOSURE_AGGREGATE`` makes it a rule.
#:
#: The SCHEDULABLE set itself is DERIVED from the dispatch registry — see
#: ``scheduling.service.SCHEDULABLE_RUN_TYPES``. It cannot be defined here (this module must stay a
#: binder-free leaf that ``irp_worker`` can import without dragging in the compute stack; the
#: registry imports ``risk``/``exposure``).
TARGET_RUN_TYPE_VAR = "VAR"
TARGET_RUN_TYPE_EXPOSURE_AGGREGATE = "EXPOSURE_AGGREGATE"


@dataclass(frozen=True)
class SchedulingActor:
    """The principal that created/edited a schedule (mirrors ``PacingActor``/``ReferenceActor``)."""

    actor_id: str
    actor_type: str = "user"
