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
    complete_through: date | None = None,
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

    **The CAL-1a NAMED CARRY, PAID at CAL-1b (with migration 0059):** ``complete_through``
    advances the calendar's DECLARED coverage horizon ``holidays_complete_through`` — FORWARD
    ONLY (a regression is refused: shrinking a declared horizon would silently re-open the
    coverage gate's refusal window behind existing schedules). The advance alone (no new dates)
    is still an effective refresh: it bumps ``record_version`` and emits the event, because
    coverage is head state a consumer refuses on (OQ-CAL-1-4)."""
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

    advance = False
    if complete_through is not None:
        current = calendar.holidays_complete_through
        if current is not None and complete_through < current:
            raise ValueError(
                f"holidays_complete_through may only advance: {complete_through} < the declared "
                f"{current} (forward-only — OQ-CAL-1-4)"
            )
        advance = current is None or complete_through > current

    if not additions and not advance:
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
    before_value: dict[str, Any] = {"holiday_count": len(existing)}
    after_value: dict[str, Any] = {
        "holiday_count": len(existing) + len(additions),
        "holidays_added": len(additions),
    }
    if additions:
        after_value["added_from"] = additions[0].holiday_date.isoformat()
        after_value["added_through"] = additions[-1].holiday_date.isoformat()
    if advance:
        assert complete_through is not None  # narrowed by the advance flag
        before_value["holidays_complete_through"] = (
            calendar.holidays_complete_through.isoformat()
            if calendar.holidays_complete_through is not None
            else None
        )
        calendar.holidays_complete_through = complete_through
        after_value["holidays_complete_through"] = complete_through.isoformat()
    calendar.record_version += 1
    session.flush()

    record_reference_update(
        session,
        entity=calendar,
        entity_type=ENTITY_CALENDAR,
        before_value=before_value,
        after_value=after_value,
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
