"""Reference-data endpoints (P1B-1): governed creates + reads for currency/calendar/rating_scale.

Thin layer over the ``irp_shared.reference`` binders. Each write is gated deny-by-default by a
``reference.*.edit`` permission and each read by ``reference.*.view``; ``tenant_id`` is server-set
from the principal (never the body — a forged value is ignored, backstopped by RLS ``WITH CHECK``);
a single end-of-request ``db.commit()`` honours the one-transaction invariant. List reads apply the
application-layer ``dedupe_tenant_wins``: a tenant override shadows the SYSTEM_TENANT global of the
same ``code`` (precedence lives here, NOT in RLS). A cross-tenant/unknown id is an indistinguishable
404; a malformed UUID path is a 422 before any DB hit. Child rows (holidays/grades) are written
through the parent POST only — there is NO PUT/DELETE/bulk/search/standalone-child surface.
"""

from __future__ import annotations

import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from irp_backend.deps import get_tenant_session, require_permission
from irp_shared.entitlement.service import Principal
from irp_shared.reference.calendar import HolidaySpec, create_calendar
from irp_shared.reference.currency import create_currency
from irp_shared.reference.models import (
    Calendar,
    CalendarHoliday,
    Currency,
    RatingGrade,
    RatingScale,
)
from irp_shared.reference.rating import GradeSpec, create_rating_scale
from irp_shared.reference.service import ReferenceActor, dedupe_tenant_wins

router = APIRouter(prefix="/reference", tags=["reference"])

#: Module-level guard singletons (deny-by-default; built once, not in argument defaults).
_require_currency_edit = require_permission("reference.currency.edit")
_require_currency_view = require_permission("reference.currency.view")
_require_calendar_edit = require_permission("reference.calendar.edit")
_require_calendar_view = require_permission("reference.calendar.view")
_require_rating_scale_edit = require_permission("reference.rating_scale.edit")
_require_rating_scale_view = require_permission("reference.rating_scale.view")


def _actor(principal: Principal) -> ReferenceActor:
    return ReferenceActor(actor_id=principal.user_id, correlation_id=str(uuid.uuid4()))


# --------------------------------------------------------------------------- currency


class CurrencyIn(BaseModel):
    code: str
    name: str
    symbol: str | None = None
    minor_units: int | None = None
    numeric_code: str | None = None
    is_active: bool = True


class CurrencyOut(BaseModel):
    id: str
    code: str
    name: str
    symbol: str | None
    minor_units: int | None
    numeric_code: str | None
    is_active: bool


def _currency_out(c: Currency) -> CurrencyOut:
    return CurrencyOut(
        id=c.id,
        code=c.code,
        name=c.name,
        symbol=c.symbol,
        minor_units=c.minor_units,
        numeric_code=c.numeric_code,
        is_active=c.is_active,
    )


@router.post("/currencies", status_code=status.HTTP_201_CREATED, response_model=CurrencyOut)
def create_currency_endpoint(
    body: CurrencyIn,
    principal: Principal = Depends(_require_currency_edit),
    db: Session = Depends(get_tenant_session),
) -> CurrencyOut:
    currency = create_currency(
        db,
        tenant_id=principal.tenant_id,  # server-stamped; body has no tenant_id
        code=body.code,
        name=body.name,
        actor=_actor(principal),
        symbol=body.symbol,
        minor_units=body.minor_units,
        numeric_code=body.numeric_code,
        is_active=body.is_active,
    )
    db.commit()
    return _currency_out(currency)


@router.get("/currencies", response_model=list[CurrencyOut])
def list_currencies(
    principal: Principal = Depends(_require_currency_view),
    db: Session = Depends(get_tenant_session),
) -> list[CurrencyOut]:
    rows = db.execute(select(Currency)).scalars().all()
    return [_currency_out(c) for c in dedupe_tenant_wins(rows, principal.tenant_id)]


@router.get("/currencies/{currency_id}", response_model=CurrencyOut)
def get_currency(
    currency_id: uuid.UUID,  # malformed -> uniform 422 before any DB hit
    _: Principal = Depends(_require_currency_view),
    db: Session = Depends(get_tenant_session),
) -> CurrencyOut:
    currency = db.get(Currency, str(currency_id))
    if currency is None:  # not found OR RLS-hidden cross-tenant id -> indistinguishable 404
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="currency not found")
    return _currency_out(currency)


# --------------------------------------------------------------------------- calendar


class HolidayIn(BaseModel):
    holiday_date: date
    name: str | None = None
    recurrence: str | None = None


class HolidayOut(BaseModel):
    holiday_date: date
    name: str | None
    recurrence: str | None


class CalendarIn(BaseModel):
    code: str
    name: str
    mic: str | None = None
    is_active: bool = True
    holidays: list[HolidayIn] = Field(default_factory=list)


class CalendarOut(BaseModel):
    id: str
    code: str
    name: str
    mic: str | None
    is_active: bool


class CalendarDetailOut(CalendarOut):
    holidays: list[HolidayOut]


def _calendar_out(c: Calendar) -> CalendarOut:
    return CalendarOut(id=c.id, code=c.code, name=c.name, mic=c.mic, is_active=c.is_active)


@router.post("/calendars", status_code=status.HTTP_201_CREATED, response_model=CalendarDetailOut)
def create_calendar_endpoint(
    body: CalendarIn,
    principal: Principal = Depends(_require_calendar_edit),
    db: Session = Depends(get_tenant_session),
) -> CalendarDetailOut:
    calendar = create_calendar(
        db,
        tenant_id=principal.tenant_id,
        code=body.code,
        name=body.name,
        actor=_actor(principal),
        mic=body.mic,
        is_active=body.is_active,
        holidays=[
            HolidaySpec(holiday_date=h.holiday_date, name=h.name, recurrence=h.recurrence)
            for h in body.holidays
        ],
    )
    db.commit()
    return _calendar_detail(db, calendar)


@router.get("/calendars", response_model=list[CalendarOut])
def list_calendars(
    principal: Principal = Depends(_require_calendar_view),
    db: Session = Depends(get_tenant_session),
) -> list[CalendarOut]:
    rows = db.execute(select(Calendar)).scalars().all()
    return [_calendar_out(c) for c in dedupe_tenant_wins(rows, principal.tenant_id)]


@router.get("/calendars/{calendar_id}", response_model=CalendarDetailOut)
def get_calendar(
    calendar_id: uuid.UUID,
    _: Principal = Depends(_require_calendar_view),
    db: Session = Depends(get_tenant_session),
) -> CalendarDetailOut:
    calendar = db.get(Calendar, str(calendar_id))
    if calendar is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="calendar not found")
    return _calendar_detail(db, calendar)


def _calendar_detail(db: Session, calendar: Calendar) -> CalendarDetailOut:
    holidays = (
        db.execute(
            select(CalendarHoliday)
            .where(CalendarHoliday.calendar_id == calendar.id)
            .order_by(CalendarHoliday.holiday_date)
        )
        .scalars()
        .all()
    )
    return CalendarDetailOut(
        id=calendar.id,
        code=calendar.code,
        name=calendar.name,
        mic=calendar.mic,
        is_active=calendar.is_active,
        holidays=[
            HolidayOut(holiday_date=h.holiday_date, name=h.name, recurrence=h.recurrence)
            for h in holidays
        ],
    )


# --------------------------------------------------------------------------- rating_scale


class GradeIn(BaseModel):
    code: str
    rank: int
    description: str | None = None


class GradeOut(BaseModel):
    code: str
    rank: int
    description: str | None


class RatingScaleIn(BaseModel):
    code: str
    name: str
    agency: str | None = None
    is_active: bool = True
    grades: list[GradeIn] = Field(default_factory=list)


class RatingScaleOut(BaseModel):
    id: str
    code: str
    name: str
    agency: str | None
    is_active: bool


class RatingScaleDetailOut(RatingScaleOut):
    grades: list[GradeOut]


def _rating_scale_out(s: RatingScale) -> RatingScaleOut:
    return RatingScaleOut(id=s.id, code=s.code, name=s.name, agency=s.agency, is_active=s.is_active)


@router.post(
    "/rating-scales", status_code=status.HTTP_201_CREATED, response_model=RatingScaleDetailOut
)
def create_rating_scale_endpoint(
    body: RatingScaleIn,
    principal: Principal = Depends(_require_rating_scale_edit),
    db: Session = Depends(get_tenant_session),
) -> RatingScaleDetailOut:
    scale = create_rating_scale(
        db,
        tenant_id=principal.tenant_id,
        code=body.code,
        name=body.name,
        actor=_actor(principal),
        agency=body.agency,
        is_active=body.is_active,
        grades=[
            GradeSpec(code=g.code, rank=g.rank, description=g.description) for g in body.grades
        ],
    )
    db.commit()
    return _rating_scale_detail(db, scale)


@router.get("/rating-scales", response_model=list[RatingScaleOut])
def list_rating_scales(
    principal: Principal = Depends(_require_rating_scale_view),
    db: Session = Depends(get_tenant_session),
) -> list[RatingScaleOut]:
    rows = db.execute(select(RatingScale)).scalars().all()
    return [_rating_scale_out(s) for s in dedupe_tenant_wins(rows, principal.tenant_id)]


@router.get("/rating-scales/{rating_scale_id}", response_model=RatingScaleDetailOut)
def get_rating_scale(
    rating_scale_id: uuid.UUID,
    _: Principal = Depends(_require_rating_scale_view),
    db: Session = Depends(get_tenant_session),
) -> RatingScaleDetailOut:
    scale = db.get(RatingScale, str(rating_scale_id))
    if scale is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="rating_scale not found")
    return _rating_scale_detail(db, scale)


def _rating_scale_detail(db: Session, scale: RatingScale) -> RatingScaleDetailOut:
    grades = (
        db.execute(
            select(RatingGrade)
            .where(RatingGrade.rating_scale_id == scale.id)
            .order_by(RatingGrade.rank)
        )
        .scalars()
        .all()
    )
    return RatingScaleDetailOut(
        id=scale.id,
        code=scale.code,
        name=scale.name,
        agency=scale.agency,
        is_active=scale.is_active,
        grades=[GradeOut(code=g.code, rank=g.rank, description=g.description) for g in grades],
    )
