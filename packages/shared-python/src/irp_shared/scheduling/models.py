"""Scheduling ORM models (SCH-1, ENT-061 ``schedule`` + ENT-062 ``scheduled_run``).

- ``Schedule`` (ENT-061, **EV**) — the cadence CONFIG header, entity-versioned in place
  (``record_version``, NOT append-only, NO system axis — the ``scenario_definition``/``factor`` EV
  precedent); ``SCHEDULE.CREATE``/``SCHEDULE.UPDATE`` audited. Says "run family ``target_run_type``
  for ``scope_portfolio_id`` under ``model_version_id`` in ``environment_id`` on the
  ``cadence_kind`` grid from ``anchor_date``." Pause/resume = a ``status`` flip. Logical identity
  ``(tenant_id, code)``. **Since SCH-2 both ``model_version_id`` and ``interval_days`` are
  NULLABLE** — each is required for some families/cadences and FORBIDDEN for others, per the
  ``service.FAMILY_REGISTRY`` declaration and the two migration-``0053`` CHECKs.
- ``ScheduledRun`` (ENT-062, **IA TRUE append-only**) — one row per fired grid tick, binding the
  tick to the governed ``calculation_run`` it produced + the upstream runs it resolved.
  ``UniqueConstraint(schedule_id, scheduled_for)`` is the per-``(schedule, tick)`` idempotency
  backstop (INV-SCH-1: ``scheduled_for`` is the deterministic ``current_tick`` grid value, NEVER a
  wall-clock read; ``fired_at`` is the wall-clock fire evidence). A re-poll of an already-fired tick
  is refused by the unique constraint — never mutated.

Both PROPRIETARY, tenant-scoped, symmetric FORCE RLS — NEVER hybrid. Migrations ``0049_scheduling``
(``schedule`` gets RLS only; ``scheduled_run`` gets RLS + the append-only trigger) and
``0053_schedule_cadence_family`` (the two SCH-2 nullability relaxations + three total-enumeration
CHECKs). Under OQ-1=B the app does all reads/writes tenant-scoped non-BYPASSRLS — the ops role has
NO grant on either table. Read-only access is ``scheduling/queries.py`` behind ``schedule.view``
(SCH-2, OQ-SCH-2-7c — so a burned month is visible when it happens).
"""

from __future__ import annotations

from datetime import date as dt_date
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    event,
)
from sqlalchemy.orm import Mapped, Mapper, mapped_column

from irp_shared.audit.models import AppendOnlyViolation
from irp_shared.db.base import Base
from irp_shared.db.mixins import (
    EffectiveDatedMixin,
    ImmutableAppendOnlyMixin,
    PrimaryKeyMixin,
    TenantMixin,
    TimestampMixin,
)
from irp_shared.db.types import GUID
from irp_shared.temporal import TemporalClass


class Schedule(PrimaryKeyMixin, TenantMixin, EffectiveDatedMixin, TimestampMixin, Base):
    """A cadence CONFIG header (ENT-061, EV entity-versioned in place).

    ``SCHEDULE.CREATE``/``SCHEDULE.UPDATE`` audited; the shock-free ``scenario_definition`` EV
    precedent (``record_version`` bump, stable ``id`` so the ``scheduled_run`` FK is always
    satisfiable). Logical identity ``(tenant_id, code)``.
    """

    __tablename__ = "schedule"
    __temporal_class__ = TemporalClass.EFFECTIVE_DATED
    __table_args__ = (UniqueConstraint("tenant_id", "code", name="uq_schedule_tenant_code"),)

    code: Mapped[str] = mapped_column(String(150), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    #: The family binder to dispatch. The controlled vocab is ``service.SCHEDULABLE_RUN_TYPES``,
    #: DERIVED from ``FAMILY_REGISTRY`` — since SCH-2 ``{VAR, EXPOSURE_AGGREGATE}``, and these are
    #: the REAL ``calculation_run.run_type`` strings, not a parallel vocabulary (OQ-SCH-2-8).
    target_run_type: Mapped[str] = mapped_column(String(100), nullable=False)
    #: The WITHIN-TENANT portfolio scope the fired number is computed for (a hard FK — a schedule
    #: targets a real book; exposure resolution is scope-filtered). NOT a security boundary.
    scope_portfolio_id: Mapped[str] = mapped_column(
        GUID, ForeignKey("portfolio.id"), nullable=False, index=True
    )
    #: The REGISTERED model version the fired run binds (CTRL-003 inventory-before-use). NULLABLE
    #: since SCH-2 because it is required for SOME families and FORBIDDEN for others: the EXPOSURE
    #: family is the MODEL-LESS deterministic rollup and cannot honestly nominate one. Which is
    #: which is declared ONCE in ``service.FAMILY_REGISTRY`` and enforced three ways — a DB CHECK
    #: (``ck_schedule_model_version_by_family``), ``_validate_config`` in both directions, and the
    #: registry-gated CAD-1 FK guard. Never treat "a value was supplied" as the rule (a CTRL-003
    #: fail-open); always ask the registry.
    model_version_id: Mapped[str | None] = mapped_column(
        GUID, ForeignKey("model_version.id"), nullable=True, index=True
    )
    #: The run-environment label pinned on every fired run (a required governed-run pin — the
    #: ``calculation_run.environment_id`` free String(100) label; NOT a security boundary).
    environment_id: Mapped[str] = mapped_column(String(100), nullable=False)
    #: Cadence kind (controlled vocab ``CADENCE_KINDS``: ``INTERVAL`` | ``CALENDAR_MONTH_END``).
    cadence_kind: Mapped[str] = mapped_column(String(20), nullable=False)
    #: Interval length in calendar days — the ``INTERVAL`` grid step. NULLABLE since SCH-2: it is
    #: meaningless under ``CALENDAR_MONTH_END`` and is FORBIDDEN there (DB CHECK
    #: ``ck_schedule_interval_days_by_cadence``, which also carries the ``> 0`` rule the DB
    #: previously lacked).
    interval_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    #: The grid anchor — the schedule's START BOUNDARY. Under ``INTERVAL`` it also generates the
    #: grid (every tick lands on ``anchor + k·interval_days``); under ``CALENDAR_MONTH_END`` the
    #: grid is calendar-generated and the anchor is ONLY the start boundary. That boundary is
    #: tested against the TICK **and** the clock — see ``service._outside_start_boundary``, where
    #: both legs are load-bearing (the tick leg is the one a calendar grid needs).
    anchor_date: Mapped[dt_date] = mapped_column(Date, nullable=False)
    #: Lifecycle status (controlled vocab; only ``ACTIVE`` is selected for dispatch).
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    record_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class ScheduledRun(PrimaryKeyMixin, TenantMixin, ImmutableAppendOnlyMixin, Base):
    """One fired grid tick of a schedule (ENT-062, IA TRUE append-only).

    ``UniqueConstraint(schedule_id, scheduled_for)`` = the per-tick idempotency backstop. A re-poll
    of an already-fired tick loses at COMMIT and rolls back its phantom governed run (the scaffold
    only ``flush()``es). ``scheduled_for`` = the deterministic ``current_tick`` (INV-SCH-1);
    ``fired_at`` = wall-clock evidence. ``calculation_run_id`` is nullable (NULL only when dispatch
    failed BEFORE the run was created).
    """

    __tablename__ = "scheduled_run"
    __temporal_class__ = TemporalClass.IMMUTABLE_APPEND_ONLY
    __table_args__ = (
        UniqueConstraint("schedule_id", "scheduled_for", name="uq_scheduled_run_schedule_tick"),
    )

    schedule_id: Mapped[str] = mapped_column(
        GUID, ForeignKey("schedule.id"), nullable=False, index=True
    )
    #: The grid tick this row fires (INV-SCH-1: the computed ``current_tick``, never a wall clock).
    scheduled_for: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    #: The wall-clock instant the fire actually ran (the operational fact / TR-09 evidence).
    fired_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    #: The governed run produced (NULL only if dispatch failed before ``create_run``).
    calculation_run_id: Mapped[str | None] = mapped_column(
        GUID, ForeignKey("calculation_run.run_id"), nullable=True, index=True
    )
    #: The upstream runs resolved at tick (evidence of what "current" resolved to). Soft refs.
    resolved_exposure_run_id: Mapped[str | None] = mapped_column(GUID, nullable=True)
    resolved_covariance_run_id: Mapped[str | None] = mapped_column(GUID, nullable=True)
    #: Terminal disposition (controlled vocab ``SCHEDULED_RUN_OUTCOMES``).
    outcome: Mapped[str] = mapped_column(String(20), nullable=False)
    #: WHY a FAILED dispatch failed (the ``calculation_run.failure_reason`` presentation precedent).
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)


def _block_mutation(mapper: Mapper[Any], connection: Any, target: Any) -> None:
    raise AppendOnlyViolation(
        f"{type(target).__name__} is append-only (AUD-01); update/delete is forbidden"
    )


# scheduled_run is IA TRUE append-only (the ORM guard paired with the migration-0049 P0001
# trigger). schedule (EV) is edited in place (record_version bump) and is NOT append-only.
event.listen(ScheduledRun, "before_update", _block_mutation)
event.listen(ScheduledRun, "before_delete", _block_mutation)
