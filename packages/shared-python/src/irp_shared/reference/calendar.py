"""Calendar reference binder (ENT-006, EV). Create/update head + holiday children via parent write.

Holiday children are written through the parent ``create_calendar`` (the model-version assumptions /
ingestion precedent) — no standalone CRUD — and fold into the parent's single ``REFERENCE.CREATE``
event (no per-holiday audit event, no per-holiday lineage). ``tenant_id`` is server-stamped from the
parent head, so the child set is single-tenant under ``WITH CHECK``.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any

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
