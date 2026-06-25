"""Valuation endpoints (P1C-4, REQ-PPM-003 valuation conjunct) — FR bitemporal, captured marks.

Thin layer over the ``irp_shared.valuation`` binder. PROPRIETARY tenant-scoped (NEVER hybrid), FR
(NOT append-only). Each write is gated deny-by-default; ``tenant_id`` is server-stamped from the
principal; ``portfolio_id``/``instrument_id`` are resolved tenant-filtered (cross-tenant/unknown ->
indistinguishable 404); a single end-of-request ``db.commit()``.

There is **no PUT/PATCH/DELETE** (no in-place content edit, no delete). A mark is *superseded* (a
new
effective-dated re-mark for the same ``valuation_date``) or *corrected* (an as-known restatement) —
both append NEW versions; the prior version's content is never mutated. The as-of read is a **single
valuation** reconstruction (read-only, no aggregation). **No holdings view / no rollup / no market
value / no exposure / no pricing model / no price lookup** (capture-only; those are later slices).
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from irp_backend.deps import get_tenant_session, require_permission
from irp_shared.entitlement.service import Principal
from irp_shared.portfolio import PortfolioNotVisible
from irp_shared.reference.instrument import InstrumentNotVisible
from irp_shared.valuation import (
    NoCurrentValuation,
    Valuation,
    ValuationActor,
    ValuationNotVisible,
    correct_valuation,
    create_valuation,
    reconstruct_valuation_as_of,
    resolve_valuation,
    supersede_valuation,
)

router = APIRouter(prefix="/valuations", tags=["valuations"])

#: Module-level guard singletons (deny-by-default; built once, not in argument defaults).
_require_edit = require_permission("valuation.edit")
_require_view = require_permission("valuation.view")


def _actor(principal: Principal) -> ValuationActor:
    return ValuationActor(actor_id=principal.user_id, correlation_id=str(uuid.uuid4()))


class ValuationIn(BaseModel):
    portfolio_id: uuid.UUID  # malformed -> 422
    instrument_id: uuid.UUID
    valuation_date: date  # the immutable logical-key date the mark is FOR
    mark_value: Decimal  # captured value (required); never computed
    valid_from: datetime | None = None  # FR valid-time; defaults to now
    currency_code: str | None = None
    mark_source: str | None = None  # inert provenance label (NOT a market-data FK)
    price_basis: str | None = None  # inert captured metadata


class ValuationSupersedeIn(BaseModel):
    effective_at: datetime  # the new valid-time the re-mark is effective
    mark_value: Decimal | None = (
        None  # only fields set here override the carried-forward prior mark
    )
    currency_code: str | None = None
    mark_source: str | None = None
    price_basis: str | None = None


class ValuationCorrectIn(BaseModel):
    restatement_reason: str
    mark_value: Decimal | None = None
    currency_code: str | None = None
    mark_source: str | None = None
    price_basis: str | None = None


class ValuationOut(BaseModel):
    id: str
    portfolio_id: str
    instrument_id: str
    valuation_date: date
    mark_value: Decimal
    currency_code: str | None
    mark_source: str | None
    price_basis: str | None
    valid_from: datetime
    valid_to: datetime | None
    system_from: datetime
    system_to: datetime | None
    restatement_reason: str | None
    supersedes_id: str | None
    record_version: int


def _out(row: Valuation) -> ValuationOut:
    return ValuationOut(
        id=row.id,
        portfolio_id=row.portfolio_id,
        instrument_id=row.instrument_id,
        valuation_date=row.valuation_date,
        mark_value=row.mark_value,
        currency_code=row.currency_code,
        mark_source=row.mark_source,
        price_basis=row.price_basis,
        valid_from=row.valid_from,
        valid_to=row.valid_to,
        system_from=row.system_from,
        system_to=row.system_to,
        restatement_reason=row.restatement_reason,
        supersedes_id=row.supersedes_id,
        record_version=row.record_version,
    )


@router.post("", status_code=status.HTTP_201_CREATED, response_model=ValuationOut)
def create_valuation_endpoint(
    body: ValuationIn,
    principal: Principal = Depends(_require_edit),
    db: Session = Depends(get_tenant_session),
) -> ValuationOut:
    try:
        row = create_valuation(
            db,
            portfolio_id=str(body.portfolio_id),
            instrument_id=str(body.instrument_id),
            valuation_date=body.valuation_date,
            acting_tenant=principal.tenant_id,  # server-stamped; body has no tenant_id
            actor=_actor(principal),
            mark_value=body.mark_value,
            valid_from=body.valid_from,
            currency_code=body.currency_code,
            mark_source=body.mark_source,
            price_basis=body.price_basis,
        )
    except (PortfolioNotVisible, InstrumentNotVisible):  # cross-tenant/unknown -> 404
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="portfolio or instrument not found"
        ) from None
    db.commit()
    return _out(row)


@router.post(
    "/{valuation_id}/supersede", status_code=status.HTTP_201_CREATED, response_model=ValuationOut
)
def supersede_valuation_endpoint(
    valuation_id: uuid.UUID,
    body: ValuationSupersedeIn,
    principal: Principal = Depends(_require_edit),
    db: Session = Depends(get_tenant_session),
) -> ValuationOut:
    """Book a new effective-dated re-mark for the head's (portfolio, instrument, valuation_date)."""
    try:
        head = resolve_valuation(db, str(valuation_id), acting_tenant=principal.tenant_id)
        new = supersede_valuation(
            db,
            portfolio_id=head.portfolio_id,
            instrument_id=head.instrument_id,
            valuation_date=head.valuation_date,
            acting_tenant=principal.tenant_id,
            actor=_actor(principal),
            effective_at=body.effective_at,
            **body.model_dump(exclude_unset=True, exclude={"effective_at"}),
        )
    except ValuationNotVisible:  # cross-tenant/unknown -> 404
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="valuation not found"
        ) from None
    except NoCurrentValuation:  # no open head to supersede -> 409
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="no current open valuation to supersede"
        ) from None
    db.commit()
    return _out(new)


@router.post(
    "/{valuation_id}/correct", status_code=status.HTTP_201_CREATED, response_model=ValuationOut
)
def correct_valuation_endpoint(
    valuation_id: uuid.UUID,
    body: ValuationCorrectIn,
    principal: Principal = Depends(_require_edit),
    db: Session = Depends(get_tenant_session),
) -> ValuationOut:
    """Book an as-known restatement of the given mark version (prior content never mutated)."""
    try:
        row = resolve_valuation(db, str(valuation_id), acting_tenant=principal.tenant_id)
        corrected = correct_valuation(
            db,
            row,
            restatement_reason=body.restatement_reason,
            acting_tenant=principal.tenant_id,
            actor=_actor(principal),
            **body.model_dump(exclude_unset=True, exclude={"restatement_reason"}),
        )
    except ValuationNotVisible:  # cross-tenant/unknown -> 404
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="valuation not found"
        ) from None
    db.commit()
    return _out(corrected)


@router.get("", response_model=list[ValuationOut])
def list_valuations(
    portfolio_id: uuid.UUID | None = Query(None),
    instrument_id: uuid.UUID | None = Query(None),
    valuation_date: date | None = Query(None),
    _: Principal = Depends(_require_view),
    db: Session = Depends(get_tenant_session),
) -> list[ValuationOut]:
    """List CURRENT-HEAD marks (open on both axes). Filter-only — NO sum/net/aggregate/rollup."""
    stmt = (
        select(Valuation)
        .where(Valuation.valid_to.is_(None), Valuation.system_to.is_(None))
        .order_by(Valuation.system_from)
    )
    if portfolio_id is not None:
        stmt = stmt.where(Valuation.portfolio_id == str(portfolio_id))
    if instrument_id is not None:
        stmt = stmt.where(Valuation.instrument_id == str(instrument_id))
    if valuation_date is not None:
        stmt = stmt.where(Valuation.valuation_date == valuation_date)
    rows = db.execute(stmt).scalars().all()
    return [_out(row) for row in rows]


@router.get("/as-of", response_model=ValuationOut)
def reconstruct_valuation_endpoint(
    portfolio_id: uuid.UUID,
    instrument_id: uuid.UUID,
    valuation_date: date,
    valid_at: datetime,
    known_at: datetime | None = Query(None),
    principal: Principal = Depends(_require_view),
    db: Session = Depends(get_tenant_session),
) -> ValuationOut:
    """Single-valuation bitemporal as-of read (read-only; NO aggregation / holdings view)."""
    row = reconstruct_valuation_as_of(
        db,
        acting_tenant=principal.tenant_id,
        portfolio_id=str(portfolio_id),
        instrument_id=str(instrument_id),
        valuation_date=valuation_date,
        valid_at=valid_at,
        known_at=known_at,
    )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="valuation not found")
    return _out(row)


@router.get("/{valuation_id}", response_model=ValuationOut)
def get_valuation(
    valuation_id: uuid.UUID,  # malformed -> uniform 422 before any DB hit
    _: Principal = Depends(_require_view),
    db: Session = Depends(get_tenant_session),
) -> ValuationOut:
    row = db.get(Valuation, str(valuation_id))
    if row is None:  # not found OR RLS-hidden cross-tenant -> indistinguishable 404
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="valuation not found")
    return _out(row)
