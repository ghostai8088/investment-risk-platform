"""Calendar reference binder (ENT-006, EV). Create/update head + holiday children via parent write.

Holiday children are written through the parent ``create_calendar`` (the model-version assumptions /
ingestion precedent) — no standalone CRUD — and fold into the parent's single ``REFERENCE.CREATE``
event (no per-holiday audit event, no per-holiday lineage). ``tenant_id`` is server-stamped from the
parent head, so the child set is single-tenant under ``WITH CHECK``.

CAL-1a (OQ-CAL-1-11) retired the §7 "children are create-once" scope-out with ONE deliberately
narrow verb: ``refresh_calendar_holidays`` — an ADD-ONLY diff against ``UNIQUE(tenant_id,
calendar_id, holiday_date)``, one parent ``REFERENCE.UPDATE`` per effective refresh, an idempotent
no-op otherwise. There is still no removal path and no per-child mutation.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from irp_shared.reference.models import Calendar, CalendarHoliday
from irp_shared.reference.service import (
    ENTITY_CALENDAR,
    ReferenceActor,
    record_reference_create,
    record_reference_update,
)

#: Mutable head attributes ``update_calendar`` will diff/apply (child patching is out of scope, §7).
_UPDATABLE = ("name", "mic", "is_active")


@dataclass(frozen=True)
class HolidaySpec:
    """One holiday to attach to a calendar (``recurrence`` is a stored vocab tag only)."""

    holiday_date: date
    name: str | None = None
    recurrence: str | None = None


def create_calendar(
    session: Session,
    *,
    tenant_id: str,
    code: str,
    name: str,
    actor: ReferenceActor,
    mic: str | None = None,
    is_active: bool = True,
    holidays: Sequence[HolidaySpec] = (),
) -> Calendar:
    """Create a ``calendar`` head + its ``calendar_holiday`` children (governed: one MANUAL-source
    origin edge + one ``REFERENCE.CREATE``; children fold in)."""
    calendar = Calendar(
        tenant_id=str(tenant_id),
        code=code,
        name=name,
        mic=mic,
        is_active=is_active,
        record_version=1,
    )
    session.add(calendar)
    session.flush()

    for spec in holidays:
        session.add(
            CalendarHoliday(
                tenant_id=calendar.tenant_id,  # server-stamped from the resolved parent
                calendar_id=calendar.id,
                holiday_date=spec.holiday_date,
                name=spec.name,
                recurrence=spec.recurrence,
                record_version=1,
            )
        )
    if holidays:
        session.flush()

    record_reference_create(
        session,
        entity=calendar,
        entity_type=ENTITY_CALENDAR,
        after_value={
            "code": code,
            "name": name,
            "is_active": is_active,
            "mic": mic,
            "holiday_count": len(holidays),
        },
        actor=actor,
    )
    return calendar


def refresh_calendar_holidays(
    session: Session,
    calendar: Calendar,
    *,
    actor: ReferenceActor,
    holidays: Sequence[HolidaySpec],
) -> int:
    """ADD-ONLY holiday-child refresh (CAL-1a, OQ-CAL-1-11): insert the dates the calendar does
    not already carry; never delete, never mutate an existing child (an already-present date wins
    as stored — a differing name in the input is ignored, not applied). One ``REFERENCE.UPDATE``
    (EVT-141, reused) on the PARENT summarizes the diff; the head ``record_version`` bumps with
    it. An idempotent re-run (nothing to add) writes nothing, bumps nothing, and emits NO event.

    Removals are structurally impossible through this verb — a correction that must remove a date
    is a separate governed act, deliberately not built here. Duplicate specs for the same date in
    ONE input dedupe first-spec-wins (the intra-call mirror of the add-only rule), so the child
    UNIQUE is unreachable through this verb. ``tenant_id`` is server-stamped from the parent head
    (the ``create_calendar`` precedent); under the hybrid policy a cross-tenant caller is refused
    by PG at flush — the parent-head version bump refuses FIRST (own-only ``WITH CHECK`` on the
    UPDATE), and the child stamp's own ``WITH CHECK`` is independently pinned in
    ``test_reference_pg``. Concurrency contract: no parent row lock is taken (the only caller is
    the SYSTEM bootstrap path); a concurrent overlapping refresh surfaces the child UNIQUE as a
    raw ``IntegrityError`` — accepted until an API verb ships (OQ-CAL-1-11 keeps that OUT).

    **NAMED CAL-1b CARRY (review fold, 2026-08-01):** OQ-CAL-1-11's ratified
    ``holidays_complete_through`` explicit advance CANNOT ship here — the column is migration-0059
    DDL (CAL-1b) and CAL-1a is a no-migration slice. CAL-1b MUST retrofit this verb with the
    advance (+ its forward-only negative control) when 0059 lands, or OQ-4's coverage gate refuses
    every ``BUSINESS_MONTH_END`` tick forever on absent coverage."""
    existing: set[date] = set(
        session.execute(
            select(CalendarHoliday.holiday_date).where(CalendarHoliday.calendar_id == calendar.id)
        ).scalars()
    )
    fresh: dict[date, HolidaySpec] = {}
    for spec in holidays:
        if spec.holiday_date not in existing and spec.holiday_date not in fresh:
            fresh[spec.holiday_date] = spec  # first-spec-wins within one input
    additions = sorted(fresh.values(), key=lambda spec: spec.holiday_date)
    if not additions:
        return 0

    for spec in additions:
        session.add(
            CalendarHoliday(
                tenant_id=calendar.tenant_id,  # server-stamped from the resolved parent
                calendar_id=calendar.id,
                holiday_date=spec.holiday_date,
                name=spec.name,
                recurrence=spec.recurrence,
                record_version=1,
            )
        )
    calendar.record_version += 1
    session.flush()

    record_reference_update(
        session,
        entity=calendar,
        entity_type=ENTITY_CALENDAR,
        before_value={"holiday_count": len(existing)},
        after_value={
            "holiday_count": len(existing) + len(additions),
            "holidays_added": len(additions),
            "added_from": additions[0].holiday_date.isoformat(),
            "added_through": additions[-1].holiday_date.isoformat(),
        },
        actor=actor,
    )
    return len(additions)


def update_calendar(
    session: Session,
    calendar: Calendar,
    *,
    actor: ReferenceActor,
    **changes: Any,
) -> Calendar:
    """Apply mutable head changes (effective-dated supersede), bump ``record_version``, emit
    ``REFERENCE.UPDATE``. Head attributes only — holiday children are not patched here (§7)."""
    unknown = set(changes) - set(_UPDATABLE)
    if unknown:
        raise ValueError(f"non-updatable calendar attributes: {sorted(unknown)}")

    before = {key: getattr(calendar, key) for key in changes}
    for key, value in changes.items():
        setattr(calendar, key, value)
    calendar.record_version += 1
    session.flush()
    record_reference_update(
        session,
        entity=calendar,
        entity_type=ENTITY_CALENDAR,
        before_value=before,
        after_value={key: getattr(calendar, key) for key in changes},
        actor=actor,
    )
    return calendar
